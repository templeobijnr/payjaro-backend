from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.db import transaction
from django.conf import settings
import json
import logging
from .models import PaymentMethod, Transaction, Earnings, WithdrawalRequest, Wallet
from .serializers import (
    PaymentMethodSerializer, TransactionSerializer, 
    EarningsSerializer, WithdrawalRequestSerializer, WalletSerializer
)
from .services import PaystackService, FlutterwaveService
from orders.models import Order
from entrepreneurs.models import EntrepreneurProfile

logger = logging.getLogger(__name__)

class PaymentMethodViewSet(viewsets.ModelViewSet):
    serializer_class = PaymentMethodSerializer
    permission_classes = [IsAuthenticated]
    def get_queryset(self):
        return PaymentMethod.objects.filter(user=self.request.user, is_active=True)
    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

class PaymentInitiationView(APIView):
    permission_classes = [IsAuthenticated]
    def post(self, request):
        order_id = request.data.get('order_id')
        payment_provider = request.data.get('provider', 'paystack')
        callback_url = request.data.get('callback_url', f"{settings.FRONTEND_URL}/payment/callback")
        if not order_id:
            return Response({'error': 'Order ID is required'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            order = Order.objects.get(order_id=order_id, customer=request.user)
            if order.payment_status == 'paid':
                return Response({'error': 'Order has already been paid'}, status=status.HTTP_400_BAD_REQUEST)
            if payment_provider == 'paystack':
                service = PaystackService()
                result = service.initialize_payment(order, callback_url)
            elif payment_provider == 'flutterwave':
                service = FlutterwaveService()
                result = service.initialize_payment(order, callback_url)
            else:
                return Response({'error': 'Unsupported payment provider'}, status=status.HTTP_400_BAD_REQUEST)
            if result['success']:
                transaction_obj = Transaction.objects.create(
                    transaction_id=result.get('reference'),
                    order=order,
                    user=request.user,
                    transaction_type='payment',
                    amount=order.total_amount,
                    currency='NGN',
                    status='pending',
                    provider_reference=result.get('reference', ''),
                    metadata={
                        'provider': payment_provider,
                        'callback_url': callback_url
                    }
                )
                return Response({
                    'success': True,
                    'payment_url': result.get('authorization_url') or result.get('payment_link'),
                    'reference': result.get('reference'),
                    'transaction_id': transaction_obj.transaction_id
                })
            else:
                return Response({'error': result['message']}, status=status.HTTP_400_BAD_REQUEST)
        except Order.DoesNotExist:
            return Response({'error': 'Order not found'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Payment initiation error: {str(e)}")
            return Response({'error': 'Payment initialization failed'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@method_decorator(csrf_exempt, name='dispatch')
class PaystackWebhookView(APIView):
    permission_classes = [AllowAny]
    def post(self, request):
        payload = request.body
        signature = request.META.get('HTTP_X_PAYSTACK_SIGNATURE', '')
        try:
            service = PaystackService()
            if not service.verify_webhook_signature(payload, signature):
                logger.warning("Invalid Paystack webhook signature")
                return Response({'error': 'Invalid signature'}, status=status.HTTP_400_BAD_REQUEST)
            data = json.loads(payload.decode('utf-8'))
            event = data.get('event')
            if event == 'charge.success':
                with transaction.atomic():
                    self._handle_successful_payment(data['data'])
            elif event == 'charge.failed':
                self._handle_failed_payment(data['data'])
            return Response({'status': 'success'})
        except Exception as e:
            logger.error(f"Webhook processing error: {str(e)}")
            return Response({'error': 'Webhook processing failed'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    def _handle_successful_payment(self, payment_data):
        reference = payment_data.get('reference')
        try:
            transaction_obj = Transaction.objects.get(transaction_id=reference)
            order = transaction_obj.order
            transaction_obj.status = 'completed'
            transaction_obj.metadata.update({
                'gateway_response': payment_data.get('gateway_response', ''),
                'paid_at': payment_data.get('paid_at')
            })
            transaction_obj.save()
            order.payment_status = 'paid'
            order.payment_method = 'paystack'
            order.status = 'paid'
            order.save()
            earnings = Earnings.objects.filter(order=order, status='pending')
            for earning in earnings:
                earning.status = 'paid'
                earning.payout_date = transaction_obj.created_at
                earning.save()
            entrepreneur = order.entrepreneur
            wallet, created = Wallet.objects.get_or_create(user=entrepreneur.user)
            total_earnings = sum(e.amount for e in earnings)
            wallet.balance += total_earnings
            wallet.total_earned += total_earnings
            wallet.save()
            entrepreneur.total_sales += order.total_amount
            entrepreneur.total_earnings += total_earnings
            entrepreneur.save()
            logger.info(f"Payment successful for order {order.order_id}")
        except Transaction.DoesNotExist:
            logger.error(f"Transaction not found for reference: {reference}")
        except Exception as e:
            logger.error(f"Error processing successful payment: {str(e)}")
            raise
    def _handle_failed_payment(self, payment_data):
        reference = payment_data.get('reference')
        try:
            transaction_obj = Transaction.objects.get(transaction_id=reference)
            transaction_obj.status = 'failed'
            transaction_obj.metadata.update({
                'failure_reason': payment_data.get('gateway_response', 'Payment failed')
            })
            transaction_obj.save()
            logger.info(f"Payment failed for reference: {reference}")
        except Transaction.DoesNotExist:
            logger.error(f"Transaction not found for reference: {reference}")

class EarningsViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = EarningsSerializer
    permission_classes = [IsAuthenticated]
    def get_queryset(self):
        if self.request.user.user_type != 'entrepreneur':
            return Earnings.objects.none()
        entrepreneur = get_object_or_404(EntrepreneurProfile, user=self.request.user)
        return Earnings.objects.filter(entrepreneur=entrepreneur).order_by('-created_at')
    @action(detail=False)
    def summary(self, request):
        if request.user.user_type != 'entrepreneur':
            return Response({'error': 'Only entrepreneurs can access earnings'}, status=status.HTTP_403_FORBIDDEN)
        entrepreneur = get_object_or_404(EntrepreneurProfile, user=request.user)
        wallet, created = Wallet.objects.get_or_create(user=request.user)
        from django.db.models import Sum
        total_markup = Earnings.objects.filter(
            entrepreneur=entrepreneur, earning_type='markup', status='paid'
        ).aggregate(total=Sum('amount'))['total'] or 0
        total_commission = Earnings.objects.filter(
            entrepreneur=entrepreneur, earning_type='commission', status='paid'
        ).aggregate(total=Sum('amount'))['total'] or 0
        pending_earnings = Earnings.objects.filter(
            entrepreneur=entrepreneur, status='pending'
        ).aggregate(total=Sum('amount'))['total'] or 0
        return Response({
            'available_balance': wallet.balance,
            'pending_balance': wallet.pending_balance,
            'total_earned': wallet.total_earned,
            'total_withdrawn': wallet.total_withdrawn,
            'total_markup': total_markup,
            'total_commission': total_commission,
            'pending_earnings': pending_earnings,
            'total_sales': entrepreneur.total_sales,
            'performance_tier': getattr(entrepreneur, 'performance_tier', None)
        })

class WithdrawalViewSet(viewsets.ModelViewSet):
    serializer_class = WithdrawalRequestSerializer
    permission_classes = [IsAuthenticated]
    def get_queryset(self):
        if self.request.user.user_type != 'entrepreneur':
            return WithdrawalRequest.objects.none()
        entrepreneur = get_object_or_404(EntrepreneurProfile, user=self.request.user)
        return WithdrawalRequest.objects.filter(entrepreneur=entrepreneur).order_by('-created_at')
    @transaction.atomic
    def create(self, request):
        if request.user.user_type != 'entrepreneur':
            return Response({'error': 'Only entrepreneurs can request withdrawals'}, status=status.HTTP_403_FORBIDDEN)
        entrepreneur = get_object_or_404(EntrepreneurProfile, user=request.user)
        wallet, created = Wallet.objects.get_or_create(user=request.user)
        amount = request.data.get('amount')
        withdrawal_method = request.data.get('withdrawal_method')
        destination_details = request.data.get('destination_details', {})
        from decimal import Decimal
        try:
            amount = Decimal(str(amount))
        except (ValueError, TypeError):
            return Response({'error': 'Invalid amount'}, status=status.HTTP_400_BAD_REQUEST)
        if amount <= 0:
            return Response({'error': 'Amount must be greater than zero'}, status=status.HTTP_400_BAD_REQUEST)
        if amount > wallet.balance:
            return Response({'error': 'Insufficient balance'}, status=status.HTTP_400_BAD_REQUEST)
        if amount < Decimal('1000.00'):
            return Response({'error': 'Minimum withdrawal amount is ₦1,000'}, status=status.HTTP_400_BAD_REQUEST)
        processing_fee = max(amount * Decimal('0.02'), Decimal('50.00'))
        net_amount = amount - processing_fee
        withdrawal = WithdrawalRequest.objects.create(
            entrepreneur=entrepreneur,
            amount=amount,
            withdrawal_method=withdrawal_method,
            destination_details=destination_details,
            status='pending',
            processing_fee=processing_fee,
            reference_id=f"WD{entrepreneur.id}{len(WithdrawalRequest.objects.filter(entrepreneur=entrepreneur)) + 1:04d}"
        )
        wallet.balance -= amount
        wallet.pending_balance += amount
        wallet.save()
        serializer = WithdrawalRequestSerializer(withdrawal)
        return Response(serializer.data, status=status.HTTP_201_CREATED) 
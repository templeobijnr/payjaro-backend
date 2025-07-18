# Payjaro Backend - AI Implementation Guide
## Complete Step-by-Step Instructions for Building Production-Ready MVP

---

## **CRITICAL CONTEXT FOR AI DEVELOPER**

**Current State:** Excellent Django foundation with 90% of models complete, 40% of APIs implemented
**Target:** Full-featured social commerce platform MVP ready for production
**Architecture:** Django REST Framework + PostgreSQL + Redis + AWS S3 + Payment Gateways
**Timeline:** Each phase builds on previous - DO NOT SKIP STEPS

---

## **PHASE 1: COMPLETE ORDERS API SYSTEM**

### **TASK 1.1: Implement Order Creation API with Business Logic**

**File to Create:** `orders/api.py`

```python
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db import transaction
from django.shortcuts import get_object_or_404
from decimal import Decimal
from .models import Order, OrderItem, OrderStatusHistory
from .serializers import (
    OrderSerializer, OrderCreateSerializer, 
    OrderItemSerializer, OrderStatusSerializer
)
from entrepreneurs.models import EntrepreneurProfile
from products.models import Product, ProductVariation
from payments.models import Earnings, Transaction as PaymentTransaction
import uuid
from datetime import datetime

class OrderViewSet(viewsets.ModelViewSet):
    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        if user.user_type == 'customer':
            return Order.objects.filter(customer=user)
        elif user.user_type == 'entrepreneur':
            entrepreneur = get_object_or_404(EntrepreneurProfile, user=user)
            return Order.objects.filter(entrepreneur=entrepreneur)
        elif user.user_type == 'supplier':
            # Return orders for supplier's products
            return Order.objects.filter(supplier__user=user)
        return Order.objects.none()
    
    def get_serializer_class(self):
        if self.action == 'create':
            return OrderCreateSerializer
        return OrderSerializer
    
    @transaction.atomic
    def create(self, request, *args, **kwargs):
        """
        CRITICAL: This method handles the complete order creation workflow
        1. Validate all order items and inventory
        2. Calculate pricing (markup + commission)
        3. Create order with proper relationships
        4. Reserve inventory
        5. Create earnings records
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Extract validated data
        order_data = serializer.validated_data
        items_data = order_data.pop('items')
        entrepreneur_slug = order_data.pop('entrepreneur_custom_url')
        
        # Get entrepreneur
        entrepreneur = get_object_or_404(
            EntrepreneurProfile, 
            custom_url=entrepreneur_slug
        )
        
        # Validate inventory for all items
        inventory_errors = []
        total_calculations = {
            'subtotal': Decimal('0.00'),
            'markup_amount': Decimal('0.00'),
            'commission_amount': Decimal('0.00'),
            'total_amount': Decimal('0.00')
        }
        
        validated_items = []
        
        for item_data in items_data:
            product = item_data['product']
            variation = item_data.get('variation')
            quantity = item_data['quantity']
            entrepreneur_price = Decimal(str(item_data['unit_price']))
            
            # Check inventory
            available_stock = variation.stock_quantity if variation else product.stock_quantity
            if available_stock < quantity:
                inventory_errors.append(
                    f"Insufficient stock for {product.name}. Available: {available_stock}, Requested: {quantity}"
                )
                continue
            
            # Calculate pricing
            base_price = product.base_price
            if variation and variation.price_modifier:
                base_price += variation.price_modifier
            
            item_subtotal = base_price * quantity
            markup_per_item = entrepreneur_price - base_price
            item_markup = markup_per_item * quantity
            item_commission = (entrepreneur_price * quantity) * (entrepreneur.commission_rate / 100)
            item_total = entrepreneur_price * quantity
            
            # Validate markup is not negative
            if markup_per_item < 0:
                inventory_errors.append(
                    f"Price for {product.name} cannot be less than base price ₦{base_price}"
                )
                continue
            
            validated_items.append({
                'product': product,
                'variation': variation,
                'quantity': quantity,
                'unit_price': entrepreneur_price,
                'base_price': base_price,
                'markup_amount': item_markup,
                'total_price': item_total
            })
            
            # Add to totals
            total_calculations['subtotal'] += item_subtotal
            total_calculations['markup_amount'] += item_markup
            total_calculations['commission_amount'] += item_commission
            total_calculations['total_amount'] += item_total
        
        if inventory_errors:
            return Response({
                'errors': inventory_errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Calculate shipping (basic implementation)
        shipping_fee = Decimal('500.00')  # Fixed for now
        total_calculations['total_amount'] += shipping_fee
        
        # Generate unique order ID
        order_id = f"PAY{datetime.now().strftime('%Y%m%d')}{str(uuid.uuid4())[:8].upper()}"
        
        # Create order
        order = Order.objects.create(
            order_id=order_id,
            customer=request.user,
            entrepreneur=entrepreneur,
            supplier=validated_items[0]['product'].supplier,  # Assuming single supplier per order
            status='pending',
            subtotal=total_calculations['subtotal'],
            markup_amount=total_calculations['markup_amount'],
            commission_amount=total_calculations['commission_amount'],
            shipping_fee=shipping_fee,
            total_amount=total_calculations['total_amount'],
            payment_status='pending',
            payment_method='',  # Will be set during payment
            shipping_address=order_data.get('shipping_address', {}),
            notes=order_data.get('notes', '')
        )
        
        # Create order items and reserve inventory
        for item_data in validated_items:
            OrderItem.objects.create(
                order=order,
                product=item_data['product'],
                variation=item_data['variation'],
                quantity=item_data['quantity'],
                unit_price=item_data['unit_price'],
                base_price=item_data['base_price'],
                markup_amount=item_data['markup_amount'],
                total_price=item_data['total_price']
            )
            
            # Reserve inventory
            if item_data['variation']:
                item_data['variation'].stock_quantity -= item_data['quantity']
                item_data['variation'].save()
            else:
                item_data['product'].stock_quantity -= item_data['quantity']
                item_data['product'].save()
        
        # Create status history
        OrderStatusHistory.objects.create(
            order=order,
            status='pending',
            notes='Order created',
            created_by=request.user
        )
        
        # Create earnings records (pending until payment)
        Earnings.objects.create(
            entrepreneur=entrepreneur,
            order=order,
            earning_type='markup',
            amount=total_calculations['markup_amount'],
            status='pending'
        )
        
        Earnings.objects.create(
            entrepreneur=entrepreneur,
            order=order,
            earning_type='commission',
            amount=total_calculations['commission_amount'],
            status='pending'
        )
        
        serializer = OrderSerializer(order)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    
    @action(detail=True, methods=['post'])
    def update_status(self, request, pk=None):
        """Update order status with proper validation and history tracking"""
        order = self.get_object()
        new_status = request.data.get('status')
        notes = request.data.get('notes', '')
        
        if new_status not in dict(Order.ORDER_STATUS).keys():
            return Response({
                'error': 'Invalid status'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Validate status transitions
        valid_transitions = {
            'pending': ['paid', 'cancelled'],
            'paid': ['processing', 'cancelled'],
            'processing': ['shipped', 'cancelled'],
            'shipped': ['delivered', 'returned'],
            'delivered': ['returned'],
            'cancelled': [],
            'returned': []
        }
        
        if new_status not in valid_transitions.get(order.status, []):
            return Response({
                'error': f'Cannot transition from {order.status} to {new_status}'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Update order status
        old_status = order.status
        order.status = new_status
        order.save()
        
        # Create status history
        OrderStatusHistory.objects.create(
            order=order,
            status=new_status,
            notes=notes,
            created_by=request.user
        )
        
        # Handle status-specific logic
        if new_status == 'cancelled' and old_status == 'pending':
            # Restore inventory
            for item in order.items.all():
                if item.variation:
                    item.variation.stock_quantity += item.quantity
                    item.variation.save()
                else:
                    item.product.stock_quantity += item.quantity
                    item.product.save()
            
            # Update earnings to cancelled
            Earnings.objects.filter(order=order).update(status='cancelled')
        
        return Response({
            'message': f'Order status updated to {new_status}',
            'order': OrderSerializer(order).data
        })
    
    @action(detail=False, methods=['get'])
    def entrepreneur_orders(self, request):
        """Get orders for the authenticated entrepreneur"""
        if request.user.user_type != 'entrepreneur':
            return Response({
                'error': 'Only entrepreneurs can access this endpoint'
            }, status=status.HTTP_403_FORBIDDEN)
        
        entrepreneur = get_object_or_404(EntrepreneurProfile, user=request.user)
        orders = Order.objects.filter(entrepreneur=entrepreneur).order_by('-created_at')
        
        # Add pagination
        page = self.paginate_queryset(orders)
        if page is not None:
            serializer = OrderSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = OrderSerializer(orders, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def supplier_orders(self, request):
        """Get orders for the authenticated supplier"""
        if request.user.user_type != 'supplier':
            return Response({
                'error': 'Only suppliers can access this endpoint'
            }, status=status.HTTP_403_FORBIDDEN)
        
        orders = Order.objects.filter(supplier__user=request.user).order_by('-created_at')
        
        page = self.paginate_queryset(orders)
        if page is not None:
            serializer = OrderSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = OrderSerializer(orders, many=True)
        return Response(serializer.data)
```

**File to Create:** `orders/serializers.py`

```python
from rest_framework import serializers
from .models import Order, OrderItem, OrderStatusHistory
from entrepreneurs.models import EntrepreneurProfile
from products.models import Product, ProductVariation
from products.serializers import ProductSerializer
from users.serializers import UserProfileSerializer

class OrderItemSerializer(serializers.ModelSerializer):
    product = ProductSerializer(read_only=True)
    product_name = serializers.CharField(source='product.name', read_only=True)
    
    class Meta:
        model = OrderItem
        fields = [
            'id', 'product', 'product_name', 'variation', 
            'quantity', 'unit_price', 'base_price', 
            'markup_amount', 'total_price'
        ]

class OrderItemCreateSerializer(serializers.Serializer):
    product_id = serializers.IntegerField()
    variation_id = serializers.IntegerField(required=False, allow_null=True)
    quantity = serializers.IntegerField(min_value=1)
    unit_price = serializers.DecimalField(max_digits=12, decimal_places=2)
    
    def validate(self, data):
        # Validate product exists
        try:
            product = Product.objects.get(id=data['product_id'], is_active=True)
        except Product.DoesNotExist:
            raise serializers.ValidationError("Product not found or inactive")
        
        # Validate variation if provided
        variation = None
        if data.get('variation_id'):
            try:
                variation = ProductVariation.objects.get(
                    id=data['variation_id'], 
                    product=product
                )
            except ProductVariation.DoesNotExist:
                raise serializers.ValidationError("Product variation not found")
        
        data['product'] = product
        data['variation'] = variation
        return data

class OrderStatusHistorySerializer(serializers.ModelSerializer):
    created_by = UserProfileSerializer(read_only=True)
    
    class Meta:
        model = OrderStatusHistory
        fields = ['id', 'status', 'notes', 'created_by', 'created_at']

class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    customer = UserProfileSerializer(read_only=True)
    entrepreneur = serializers.StringRelatedField(read_only=True)
    supplier = serializers.StringRelatedField(read_only=True)
    status_history = OrderStatusHistorySerializer(many=True, read_only=True)
    
    class Meta:
        model = Order
        fields = [
            'id', 'order_id', 'customer', 'entrepreneur', 'supplier',
            'status', 'subtotal', 'markup_amount', 'commission_amount',
            'shipping_fee', 'total_amount', 'payment_status', 'payment_method',
            'shipping_address', 'tracking_number', 'notes', 'created_at',
            'updated_at', 'items', 'status_history'
        ]
        read_only_fields = [
            'id', 'order_id', 'subtotal', 'markup_amount', 'commission_amount',
            'total_amount', 'created_at', 'updated_at'
        ]

class OrderCreateSerializer(serializers.Serializer):
    entrepreneur_custom_url = serializers.CharField(max_length=100)
    items = OrderItemCreateSerializer(many=True)
    shipping_address = serializers.JSONField()
    notes = serializers.CharField(required=False, allow_blank=True)
    
    def validate_entrepreneur_custom_url(self, value):
        try:
            EntrepreneurProfile.objects.get(custom_url=value, is_active=True)
        except EntrepreneurProfile.DoesNotExist:
            raise serializers.ValidationError("Entrepreneur not found")
        return value
    
    def validate_items(self, value):
        if not value:
            raise serializers.ValidationError("At least one item is required")
        return value
    
    def validate_shipping_address(self, value):
        required_fields = ['full_name', 'phone', 'address', 'city', 'state']
        for field in required_fields:
            if field not in value or not value[field]:
                raise serializers.ValidationError(f"Shipping address must include {field}")
        return value
```

**File to Create:** `orders/urls.py`

```python
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .api import OrderViewSet

router = DefaultRouter()
router.register(r'orders', OrderViewSet, basename='order')

urlpatterns = [
    path('', include(router.urls)),
]
```

**Update:** `payjaro_project/urls.py`

```python
# ADD THIS LINE to the urlpatterns list
path('api/orders/', include('orders.urls')),
```

**VALIDATION COMMANDS:**
```bash
# Run these commands in sequence
python manage.py makemigrations
python manage.py migrate
python manage.py test orders.tests
python manage.py runserver

# Test in browser/Postman:
# POST http://localhost:8000/api/orders/orders/
# GET http://localhost:8000/api/orders/orders/
```

**CRITICAL CHECKPOINTS:**
- [ ] Order creation API responds with 201 status
- [ ] Commission calculations are accurate
- [ ] Inventory is properly reserved
- [ ] Order status updates work correctly
- [ ] All tests pass without errors

---

## **PHASE 2: PAYMENT INTEGRATION SYSTEM**

### **TASK 2.1: Implement Paystack Payment Integration**

**Install Required Dependencies:**
```bash
pip install paystack-python requests cryptography
pip freeze > requirements.txt
```

**File to Create:** `payments/services.py`

```python
import os
import hashlib
import hmac
import json
import requests
from decimal import Decimal
from django.conf import settings
from .models import Transaction, PaymentMethod
import logging

logger = logging.getLogger(__name__)

class PaystackService:
    def __init__(self):
        self.secret_key = settings.PAYSTACK_SECRET_KEY
        self.public_key = settings.PAYSTACK_PUBLIC_KEY
        self.base_url = "https://api.paystack.co"
        
    def _make_request(self, method, endpoint, data=None):
        """Make authenticated request to Paystack API"""
        headers = {
            'Authorization': f'Bearer {self.secret_key}',
            'Content-Type': 'application/json'
        }
        
        url = f"{self.base_url}{endpoint}"
        
        try:
            if method == 'POST':
                response = requests.post(url, headers=headers, json=data)
            elif method == 'GET':
                response = requests.get(url, headers=headers, params=data)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
            
            response.raise_for_status()
            return response.json()
        
        except requests.exceptions.RequestException as e:
            logger.error(f"Paystack API request failed: {str(e)}")
            raise Exception(f"Payment service error: {str(e)}")
    
    def initialize_payment(self, order, callback_url):
        """Initialize payment transaction with Paystack"""
        # Convert amount to kobo (Paystack uses kobo)
        amount_kobo = int(order.total_amount * 100)
        
        data = {
            'email': order.customer.email,
            'amount': amount_kobo,
            'currency': 'NGN',
            'reference': f"PAY_{order.order_id}_{order.id}",
            'callback_url': callback_url,
            'metadata': {
                'order_id': order.order_id,
                'customer_id': order.customer.id,
                'entrepreneur_id': order.entrepreneur.id,
                'order_total': str(order.total_amount)
            }
        }
        
        try:
            response = self._make_request('POST', '/transaction/initialize', data)
            
            if response.get('status'):
                return {
                    'success': True,
                    'authorization_url': response['data']['authorization_url'],
                    'access_code': response['data']['access_code'],
                    'reference': response['data']['reference']
                }
            else:
                return {
                    'success': False,
                    'message': response.get('message', 'Payment initialization failed')
                }
        
        except Exception as e:
            return {
                'success': False,
                'message': str(e)
            }
    
    def verify_payment(self, reference):
        """Verify payment transaction with Paystack"""
        try:
            response = self._make_request('GET', f'/transaction/verify/{reference}')
            
            if response.get('status'):
                data = response['data']
                return {
                    'success': True,
                    'status': data['status'],
                    'amount': Decimal(str(data['amount'])) / 100,  # Convert from kobo
                    'currency': data['currency'],
                    'reference': data['reference'],
                    'paid_at': data['paid_at'],
                    'metadata': data.get('metadata', {}),
                    'gateway_response': data.get('gateway_response', '')
                }
            else:
                return {
                    'success': False,
                    'message': response.get('message', 'Payment verification failed')
                }
        
        except Exception as e:
            return {
                'success': False,
                'message': str(e)
            }
    
    def verify_webhook_signature(self, payload, signature):
        """Verify that webhook is from Paystack"""
        computed_signature = hmac.new(
            self.secret_key.encode('utf-8'),
            payload,
            hashlib.sha512
        ).hexdigest()
        
        return hmac.compare_digest(computed_signature, signature)

class FlutterwaveService:
    def __init__(self):
        self.secret_key = settings.FLUTTERWAVE_SECRET_KEY
        self.public_key = settings.FLUTTERWAVE_PUBLIC_KEY
        self.base_url = "https://api.flutterwave.com/v3"
    
    def _make_request(self, method, endpoint, data=None):
        """Make authenticated request to Flutterwave API"""
        headers = {
            'Authorization': f'Bearer {self.secret_key}',
            'Content-Type': 'application/json'
        }
        
        url = f"{self.base_url}{endpoint}"
        
        try:
            if method == 'POST':
                response = requests.post(url, headers=headers, json=data)
            elif method == 'GET':
                response = requests.get(url, headers=headers, params=data)
            
            response.raise_for_status()
            return response.json()
        
        except requests.exceptions.RequestException as e:
            logger.error(f"Flutterwave API request failed: {str(e)}")
            raise Exception(f"Payment service error: {str(e)}")
    
    def initialize_payment(self, order, callback_url):
        """Initialize payment with Flutterwave"""
        data = {
            'tx_ref': f"FLW_{order.order_id}_{order.id}",
            'amount': str(order.total_amount),
            'currency': 'NGN',
            'redirect_url': callback_url,
            'customer': {
                'email': order.customer.email,
                'phonenumber': order.customer.phone_number,
                'name': f"{order.customer.first_name} {order.customer.last_name}"
            },
            'customizations': {
                'title': 'Payjaro Order Payment',
                'description': f'Payment for order {order.order_id}',
                'logo': 'https://your-logo-url.com/logo.png'
            },
            'meta': {
                'order_id': order.order_id,
                'customer_id': order.customer.id,
                'entrepreneur_id': order.entrepreneur.id
            }
        }
        
        try:
            response = self._make_request('POST', '/payments', data)
            
            if response.get('status') == 'success':
                return {
                    'success': True,
                    'payment_link': response['data']['link'],
                    'reference': data['tx_ref']
                }
            else:
                return {
                    'success': False,
                    'message': response.get('message', 'Payment initialization failed')
                }
        
        except Exception as e:
            return {
                'success': False,
                'message': str(e)
            }
    
    def verify_payment(self, transaction_id):
        """Verify payment with Flutterwave"""
        try:
            response = self._make_request('GET', f'/transactions/{transaction_id}/verify')
            
            if response.get('status') == 'success':
                data = response['data']
                return {
                    'success': True,
                    'status': data['status'],
                    'amount': Decimal(str(data['amount'])),
                    'currency': data['currency'],
                    'reference': data['tx_ref'],
                    'flw_ref': data['flw_ref'],
                    'metadata': data.get('meta', {})
                }
            else:
                return {
                    'success': False,
                    'message': response.get('message', 'Payment verification failed')
                }
        
        except Exception as e:
            return {
                'success': False,
                'message': str(e)
            }
```

**File to Create:** `payments/api.py`

```python
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
        """Initialize payment for an order"""
        order_id = request.data.get('order_id')
        payment_provider = request.data.get('provider', 'paystack')  # Default to Paystack
        callback_url = request.data.get('callback_url', f"{settings.FRONTEND_URL}/payment/callback")
        
        if not order_id:
            return Response({
                'error': 'Order ID is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            order = Order.objects.get(order_id=order_id, customer=request.user)
            
            if order.payment_status == 'paid':
                return Response({
                    'error': 'Order has already been paid'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Initialize payment based on provider
            if payment_provider == 'paystack':
                service = PaystackService()
                result = service.initialize_payment(order, callback_url)
            elif payment_provider == 'flutterwave':
                service = FlutterwaveService()
                result = service.initialize_payment(order, callback_url)
            else:
                return Response({
                    'error': 'Unsupported payment provider'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            if result['success']:
                # Create transaction record
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
                return Response({
                    'error': result['message']
                }, status=status.HTTP_400_BAD_REQUEST)
        
        except Order.DoesNotExist:
            return Response({
                'error': 'Order not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        except Exception as e:
            logger.error(f"Payment initiation error: {str(e)}")
            return Response({
                'error': 'Payment initialization failed'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@method_decorator(csrf_exempt, name='dispatch')
class PaystackWebhookView(APIView):
    permission_classes = [AllowAny]
    
    def post(self, request):
        """Handle Paystack webhook notifications"""
        payload = request.body
        signature = request.META.get('HTTP_X_PAYSTACK_SIGNATURE', '')
        
        try:
            # Verify webhook signature
            service = PaystackService()
            if not service.verify_webhook_signature(payload, signature):
                logger.warning("Invalid Paystack webhook signature")
                return Response({'error': 'Invalid signature'}, status=status.HTTP_400_BAD_REQUEST)
            
            # Parse webhook data
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
        """Process successful payment"""
        reference = payment_data.get('reference')
        
        try:
            # Get transaction and order
            transaction_obj = Transaction.objects.get(transaction_id=reference)
            order = transaction_obj.order
            
            # Update transaction status
            transaction_obj.status = 'completed'
            transaction_obj.metadata.update({
                'gateway_response': payment_data.get('gateway_response', ''),
                'paid_at': payment_data.get('paid_at')
            })
            transaction_obj.save()
            
            # Update order status
            order.payment_status = 'paid'
            order.payment_method = 'paystack'
            order.status = 'paid'
            order.save()
            
            # Update earnings to paid status
            earnings = Earnings.objects.filter(order=order, status='pending')
            for earning in for earning in earnings:
                earning.status = 'paid'
                earning.payout_date = transaction_obj.created_at
                earning.save()
            
            # Update entrepreneur wallet
            entrepreneur = order.entrepreneur
            wallet, created = Wallet.objects.get_or_create(user=entrepreneur.user)
            
            total_earnings = sum(e.amount for e in earnings)
            wallet.balance += total_earnings
            wallet.total_earned += total_earnings
            wallet.save()
            
            # Update entrepreneur profile totals
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
        """Process failed payment"""
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
        """Get earnings summary for entrepreneur"""
        if request.user.user_type != 'entrepreneur':
            return Response({
                'error': 'Only entrepreneurs can access earnings'
            }, status=status.HTTP_403_FORBIDDEN)
        
        entrepreneur = get_object_or_404(EntrepreneurProfile, user=request.user)
        
        # Get wallet
        wallet, created = Wallet.objects.get_or_create(user=request.user)
        
        # Calculate earnings breakdown
        total_markup = Earnings.objects.filter(
            entrepreneur=entrepreneur, 
            earning_type='markup', 
            status='paid'
        ).aggregate(total=models.Sum('amount'))['total'] or 0
        
        total_commission = Earnings.objects.filter(
            entrepreneur=entrepreneur, 
            earning_type='commission', 
            status='paid'
        ).aggregate(total=models.Sum('amount'))['total'] or 0
        
        pending_earnings = Earnings.objects.filter(
            entrepreneur=entrepreneur, 
            status='pending'
        ).aggregate(total=models.Sum('amount'))['total'] or 0
        
        return Response({
            'available_balance': wallet.balance,
            'pending_balance': wallet.pending_balance,
            'total_earned': wallet.total_earned,
            'total_withdrawn': wallet.total_withdrawn,
            'total_markup': total_markup,
            'total_commission': total_commission,
            'pending_earnings': pending_earnings,
            'total_sales': entrepreneur.total_sales,
            'performance_tier': entrepreneur.performance_tier
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
        """Create withdrawal request"""
        if request.user.user_type != 'entrepreneur':
            return Response({
                'error': 'Only entrepreneurs can request withdrawals'
            }, status=status.HTTP_403_FORBIDDEN)
        
        entrepreneur = get_object_or_404(EntrepreneurProfile, user=request.user)
        wallet, created = Wallet.objects.get_or_create(user=request.user)
        
        amount = request.data.get('amount')
        withdrawal_method = request.data.get('withdrawal_method')
        destination_details = request.data.get('destination_details', {})
        
        # Validate amount
        try:
            amount = Decimal(str(amount))
        except (ValueError, TypeError):
            return Response({
                'error': 'Invalid amount'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        if amount <= 0:
            return Response({
                'error': 'Amount must be greater than zero'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        if amount > wallet.balance:
            return Response({
                'error': 'Insufficient balance'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Minimum withdrawal check
        if amount < Decimal('1000.00'):
            return Response({
                'error': 'Minimum withdrawal amount is ₦1,000'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Calculate processing fee (2% or minimum ₦50)
        processing_fee = max(amount * Decimal('0.02'), Decimal('50.00'))
        net_amount = amount - processing_fee
        
        # Create withdrawal request
        withdrawal = WithdrawalRequest.objects.create(
            entrepreneur=entrepreneur,
            amount=amount,
            withdrawal_method=withdrawal_method,
            destination_details=destination_details,
            status='pending',
            processing_fee=processing_fee,
            reference_id=f"WD{entrepreneur.id}{len(WithdrawalRequest.objects.filter(entrepreneur=entrepreneur)) + 1:04d}"
        )
        
        # Update wallet
        wallet.balance -= amount
        wallet.pending_balance += amount
        wallet.save()
        
        serializer = WithdrawalRequestSerializer(withdrawal)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
File to Create: payments/serializers.py
pythonfrom rest_framework import serializers
from .models import PaymentMethod, Transaction, Earnings, WithdrawalRequest, Wallet
from orders.serializers import OrderSerializer

class PaymentMethodSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentMethod
        fields = [
            'id', 'method_type', 'provider', 'details', 
            'is_default', 'is_active'
        ]
        read_only_fields = ['id']
    
    def validate_details(self, value):
        """Validate payment method details based on type"""
        method_type = self.initial_data.get('method_type')
        
        if method_type == 'bank_transfer':
            required_fields = ['account_number', 'bank_code', 'account_name']
            for field in required_fields:
                if field not in value:
                    raise serializers.ValidationError(f"Bank transfer requires {field}")
        
        elif method_type == 'crypto':
            required_fields = ['wallet_address', 'crypto_type']
            for field in required_fields:
                if field not in value:
                    raise serializers.ValidationError(f"Crypto payment requires {field}")
        
        return value

class TransactionSerializer(serializers.ModelSerializer):
    order = OrderSerializer(read_only=True)
    
    class Meta:
        model = Transaction
        fields = [
            'id', 'transaction_id', 'order', 'transaction_type',
            'amount', 'currency', 'status', 'provider_reference',
            'metadata', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']

class EarningsSerializer(serializers.ModelSerializer):
    order = OrderSerializer(read_only=True)
    
    class Meta:
        model = Earnings
        fields = [
            'id', 'order', 'earning_type', 'amount', 'status',
            'payout_date', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']

class WithdrawalRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = WithdrawalRequest
        fields = [
            'id', 'amount', 'withdrawal_method', 'destination_details',
            'status', 'processing_fee', 'reference_id', 'processed_at',
            'created_at'
        ]
        read_only_fields = [
            'id', 'status', 'processing_fee', 'reference_id', 
            'processed_at', 'created_at'
        ]

class WalletSerializer(serializers.ModelSerializer):
    class Meta:
        model = Wallet
        fields = [
            'id', 'balance', 'pending_balance', 'total_earned',
            'total_withdrawn', 'currency', 'updated_at'
        ]
        read_only_fields = ['id', 'updated_at']
File to Create: payments/urls.py
pythonfrom django.urls import path, include
from rest_framework.routers import DefaultRouter
from .api import (
    PaymentMethodViewSet, PaymentInitiationView, PaystackWebhookView,
    EarningsViewSet, WithdrawalViewSet
)

router = DefaultRouter()
router.register(r'payment-methods', PaymentMethodViewSet, basename='payment-method')
router.register(r'earnings', EarningsViewSet, basename='earnings')
router.register(r'withdrawals', WithdrawalViewSet, basename='withdrawal')

urlpatterns = [
    path('', include(router.urls)),
    path('initialize/', PaymentInitiationView.as_view(), name='payment-initialize'),
    path('webhooks/paystack/', PaystackWebhookView.as_view(), name='paystack-webhook'),
]
Update: payjaro_project/settings.py
python# ADD THESE PAYMENT SETTINGS
import os

# Payment Gateway Settings
PAYSTACK_PUBLIC_KEY = os.getenv('PAYSTACK_PUBLIC_KEY', 'pk_test_your_test_key')
PAYSTACK_SECRET_KEY = os.getenv('PAYSTACK_SECRET_KEY', 'sk_test_your_test_key')
FLUTTERWAVE_PUBLIC_KEY = os.getenv('FLUTTERWAVE_PUBLIC_KEY', 'FLWPUBK_TEST-your_test_key')
FLUTTERWAVE_SECRET_KEY = os.getenv('FLUTTERWAVE_SECRET_KEY', 'FLWSECK_TEST-your_test_key')

# Frontend URL for callbacks
FRONTEND_URL = os.getenv('FRONTEND_URL', 'http://localhost:3000')

# Logging configuration
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'file': {
            'level': 'INFO',
            'class': 'logging.FileHandler',
            'filename': 'payments.log',
        },
        'console': {
            'level': 'DEBUG',
            'class': 'logging.StreamHandler',
        },
    },
    'loggers': {
        'payments': {
            'handlers': ['file', 'console'],
            'level': 'INFO',
            'propagate': True,
        },
    },
}
Update: payjaro_project/urls.py
python# ADD THIS LINE to the urlpatterns list
path('api/payments/', include('payments.urls')),
VALIDATION COMMANDS:
bash# Install dependencies
pip install paystack-python requests cryptography

# Run migrations
python manage.py makemigrations payments
python manage.py migrate

# Test payment APIs
python manage.py test payments.tests

# Start server and test endpoints
python manage.py runserver

# Test payment initialization:
# POST http://localhost:8000/api/payments/initialize/
# Body: {"order_id": "PAY20250718ABC123", "provider": "paystack"}
CRITICAL CHECKPOINTS:

 Payment initialization returns valid payment URL
 Webhook signature verification works
 Successful payments update order and earnings
 Failed payments are handled correctly
 Earnings calculations are accurate
 Withdrawal system enforces proper validations


PHASE 3: FILE STORAGE AND MEDIA MANAGEMENT
TASK 3.1: Implement AWS S3 Integration for File Storage
Install Dependencies:
bashpip install boto3 django-storages pillow
pip freeze > requirements.txt
Update: payjaro_project/settings.py
python# ADD AWS S3 CONFIGURATION
import os

# AWS S3 Settings
AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = os.getenv('AWS_SECRET_ACCESS_KEY')
AWS_STORAGE_BUCKET_NAME = os.getenv('AWS_STORAGE_BUCKET_NAME', 'payjaro-files')
AWS_S3_REGION_NAME = os.getenv('AWS_S3_REGION_NAME', 'us-east-1')
AWS_S3_CUSTOM_DOMAIN = f'{AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com'
AWS_DEFAULT_ACL = 'public-read'
AWS_S3_OBJECT_PARAMETERS = {
    'CacheControl': 'max-age=86400',
}
AWS_LOCATION = 'static'
AWS_MEDIA_LOCATION = 'media'

# Storage backends
if not DEBUG:
    # Production storage
    DEFAULT_FILE_STORAGE = 'storages.backends.s3boto3.S3Boto3Storage'
    STATICFILES_STORAGE = 'storages.backends.s3boto3.S3StaticStorage'
    
    # URLs
    STATIC_URL = f'https://{AWS_S3_CUSTOM_DOMAIN}/{AWS_LOCATION}/'
    MEDIA_URL = f'https://{AWS_S3_CUSTOM_DOMAIN}/{AWS_MEDIA_LOCATION}/'
else:
    # Development storage
    STATIC_URL = '/static/'
    MEDIA_URL = '/media/'
    MEDIA_ROOT = BASE_DIR / 'media'

# File upload settings
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # 10MB
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # 10MB

# Add storages to INSTALLED_APPS
INSTALLED_APPS = [
    # ... existing apps
    'storages',
]
File to Create: core/file_utils.py
pythonimport os
import uuid
from PIL import Image
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

def generate_unique_filename(filename, prefix=''):
    """Generate unique filename with UUID"""
    ext = os.path.splitext(filename)[1]
    unique_filename = f"{prefix}{uuid.uuid4().hex}{ext}"
    return unique_filename

def validate_image_file(file):
    """Validate uploaded image file"""
    # Check file size (max 5MB)
    if file.size > 5 * 1024 * 1024:
        raise ValueError("Image file too large. Maximum size is 5MB.")
    
    # Check file type
    allowed_types = ['image/jpeg', 'image/png', 'image/webp']
    if file.content_type not in allowed_types:
        raise ValueError("Invalid file type. Only JPEG, PNG, and WebP are allowed.")
    
    try:
        # Validate image can be opened
        image = Image.open(file)
        image.verify()
        file.seek(0)  # Reset file pointer
        return True
    except Exception:
        raise ValueError("Invalid image file.")

def optimize_image(image_file, max_width=1200, max_height=1200, quality=85):
    """Optimize image for web use"""
    try:
        image = Image.open(image_file)
        
        # Convert RGBA to RGB if needed
        if image.mode in ('RGBA', 'LA', 'P'):
            background = Image.new('RGB', image.size, (255, 255, 255))
            if image.mode == 'P':
                image = image.convert('RGBA')
            background.paste(image, mask=image.split()[-1] if image.mode == 'RGBA' else None)
            image = background
        
        # Resize if needed
        if image.width > max_width or image.height > max_height:
            image.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)
        
        # Save optimized image
        from io import BytesIO
        output = BytesIO()
        image.save(output, format='JPEG', quality=quality, optimize=True)
        output.seek(0)
        
        return ContentFile(output.read())
    
    except Exception as e:
        logger.error(f"Image optimization failed: {str(e)}")
        raise ValueError("Image optimization failed.")

class FileUploadService:
    @staticmethod
    def upload_product_image(product, image_file, is_primary=False):
        """Upload and optimize product image"""
        try:
            # Validate image
            validate_image_file(image_file)
            
            # Generate filename
            filename = generate_unique_filename(
                image_file.name, 
                f"products/{product.id}/"
            )
            
            # Optimize image
            optimized_image = optimize_image(image_file)
            
            # Save to storage
            path = default_storage.save(filename, optimized_image)
            url = default_storage.url(path)
            
            # Create ProductImage record
            from products.models import ProductImage
            product_image = ProductImage.objects.create(
                product=product,
                image=path,
                alt_text=f"{product.name} image",
                is_primary=is_primary
            )
            
            return {
                'success': True,
                'image_id': product_image.id,
                'url': url,
                'path': path
            }
        
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    @staticmethod
    def upload_profile_image(entrepreneur, image_file, image_type='profile'):
        """Upload entrepreneur profile or banner image"""
        try:
            # Validate image
            validate_image_file(image_file)
            
            # Generate filename
            filename = generate_unique_filename(
                image_file.name,
                f"entrepreneurs/{entrepreneur.id}/{image_type}/"
            )
            
            # Optimize image
            if image_type == 'banner':
                optimized_image = optimize_image(image_file, max_width=1200, max_height=400)
            else:
                optimized_image = optimize_image(image_file, max_width=400, max_height=400)
            
            # Save to storage
            path = default_storage.save(filename, optimized_image)
            url = default_storage.url(path)
            
            # Update entrepreneur profile
            if image_type == 'profile':
                entrepreneur.profile_image = path
            elif image_type == 'banner':
                entrepreneur.banner_image = path
            entrepreneur.save()
            
            return {
                'success': True,
                'url': url,
                'path': path
            }
        
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    @staticmethod
    def delete_file(file_path):
        """Delete file from storage"""
        try:
            if default_storage.exists(file_path):
                default_storage.delete(file_path)
                return True
            return False
        except Exception as e:
            logger.error(f"File deletion failed: {str(e)}")
            return False
File to Create: products/file_api.py
pythonfrom rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from rest_framework.parsers import MultiPartParser, FormParser
from django.shortcuts import get_object_or_404
from .models import Product, ProductImage
from suppliers.models import SupplierProfile
from core.file_utils import FileUploadService

class ProductImageUploadView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    
    def post(self, request, product_id):
        """Upload product image"""
        # Verify user is supplier who owns the product
        if request.user.user_type != 'supplier':
            return Response({
                'error': 'Only suppliers can upload product images'
            }, status=status.HTTP_403_FORBIDDEN)
        
        try:
            supplier = SupplierProfile.objects.get(user=request.user)
            product = Product.objects.get(id=product_id, supplier=supplier)
        except (SupplierProfile.DoesNotExist, Product.DoesNotExist):
            return Response({
                'error': 'Product not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        image_file = request.FILES.get('image')
        if not image_file:
            return Response({
                'error': 'No image file provided'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        is_primary = request.data.get('is_primary', False)
        
        # If setting as primary, unset other primary images
        if is_primary:
            ProductImage.objects.filter(product=product, is_primary=True).update(is_primary=False)
        
        result = FileUploadService.upload_product_image(product, image_file, is_primary)
        
        if result['success']:
            return Response({
                'success': True,
                'image_id': result['image_id'],
                'url': result['url'],
                'message': 'Image uploaded successfully'
            }, status=status.HTTP_201_CREATED)
        else:
            return Response({
                'error': result['error']
            }, status=status.HTTP_400_BAD_REQUEST)
    
    def delete(self, request, product_id, image_id):
        """Delete product image"""
        if request.user.user_type != 'supplier':
            return Response({
                'error': 'Only suppliers can delete product images'
            }, status=status.HTTP_403_FORBIDDEN)
        
        try:
            supplier = SupplierProfile.objects.get(user=request.user)
            product = Product.objects.get(id=product_id, supplier=supplier)
            image = ProductImage.objects.get(id=image_id, product=product)
        except (SupplierProfile.DoesNotExist, Product.DoesNotExist, ProductImage.DoesNotExist):
            return Response({
                'error': 'Image not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Delete file from storage
        FileUploadService.delete_file(image.image.name)
        
        # Delete database record
        image.delete()
        
        return Response({
            'message': 'Image deleted successfully'
        }, status=status.HTTP_200_OK)

class BulkProductImageUploadView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    
    def post(self, request, product_id):
        """Upload multiple product images"""
        if request.user.user_type != 'supplier':
            return Response({
                'error': 'Only suppliers can upload product images'
            }, status=status.HTTP_403_FORBIDDEN)
        
        try:
            supplier = SupplierProfile.objects.get(user=request.user)
            product = Product.objects.get(id=product_id, supplier=supplier)
        except (SupplierProfile.DoesNotExist, Product.DoesNotExist):
            return Response({
                'error': 'Product not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        images = request.FILES.getlist('images')
        if not images:
            return Response({
                'error': 'No image files provided'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        results = []
        primary_set = False
        
        for i, image_file in enumerate(images):
            is_primary = i == 0 and not primary_set  # First image is primary if none set
            result = FileUploadService.upload_product_image(product, image_file, is_primary)
            
            if result['success']:
                primary_set = True
                results.append({
                    'success': True,
                    'image_id': result['image_id'],
                    'url': result['url']
                })
            else:
                results.append({
                    'success': False,
                    'error': result['error']
                })
        
        successful_uploads = [r for r in results if r['success']]
        failed_uploads = [r for r in results if not r['success']]
        
        return Response({
            'message': f'{len(successful_uploads)} images uploaded successfully',
            'successful_uploads': successful_uploads,
            'failed_uploads': failed_uploads
        }, status=status.HTTP_201_CREATED if successful_uploads else status.HTTP_400_BAD_REQUEST)
File to Create: entrepreneurs/file_api.py
pythonfrom rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from rest_framework.parsers import MultiPartParser, FormParser
from django.shortcuts import get_object_or_404
from .models import EntrepreneurProfile
from core.file_utils import FileUploadService

class EntrepreneurImageUploadView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    
    def post(self, request, image_type):
        """Upload entrepreneur profile or banner image"""
        if request.user.user_type != 'entrepreneur':
            return Response({
                'error': 'Only entrepreneurs can upload profile images'
            }, status=status.HTTP_403_FORBIDDEN)
        
        if image_type not in ['profile', 'banner']:
            return Response({
                'error': 'Invalid image type. Use "profile" or "banner"'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            entrepreneur = EntrepreneurProfile.objects.get(user=request.user)
        except EntrepreneurProfile.DoesNotExist:
            return Response({
                'error': 'Entrepreneur profile not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        image_file = request.FILES.get('image')
        if not image_file:
            return Response({
                'error': 'No image file provided'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Delete old image if exists
        old_image_path = None
        if image_type == 'profile' and entrepreneur.profile_image:
            old_image_path = entrepreneur.profile_image.name
        elif image_type == 'banner' and entrepreneur.banner_image:
            old_image_path = entrepreneur.banner_image.name
        
        result = FileUploadService.upload_profile_image(entrepreneur, image_file, image_type)
        
        if result['success']:
            # Delete old image
            if old_image_path:
                FileUploadService.delete_file(old_image_path)
            
            return Response({
                'success': True,
                'url': result['url'],
                'message': f'{image_type.title()} image uploaded successfully'
            }, status=status.HTTP_200_OK)
        else:
            return Response({
                'error': result['error']
            }, status=status.HTTP_400_BAD_REQUEST)
Update URL files to include image upload endpoints:
Add to: products/urls.py
pythonfrom .file_api import ProductImageUploadView, BulkProductImageUploadView

# ADD THESE PATTERNS
path('products/<int:product_id>/images/', ProductImageUploadView.as_view(), name='product-image-upload'),
path('products/<int:product_id>/images/<int:image_id>/', ProductImageUploadView.as_view(), name='product-image-delete'),
path('products/<int:product_id>/images/bulk/', BulkProductImageUploadView.as_view(), name='product-images-bulk-upload'),
Add to: entrepreneurs/urls.py
pythonfrom .file_api import EntrepreneurImageUploadView

# ADD THIS PATTERN
path('images/<str:image_type>/', EntrepreneurImageUploadView.as_view(), name='entrepreneur-image-upload'),
VALIDATION COMMANDS:
bash# Install dependencies
pip install boto3 django-storages pillow

# Test image uploads
python manage.py test products.tests.TestImageUpload
python manage.py test entrepreneurs.tests.TestImageUpload

# Collect static files
python manage.py collectstatic --noinput

# Test endpoints
# POST http://localhost:8000/api/products/products/1/images/
# POST http://localhost:8000/api/entrepreneurs/images/profile/
CRITICAL CHECKPOINTS:

 Image uploads work to S3 (or local in development)
 Images are properly optimized and resized
 File validation prevents invalid uploads
 Old images are cleaned up when replaced
 URLs are accessible and properly formatted


PHASE 4: SUPPLIER MANAGEMENT SYSTEM
TASK 4.1: Complete Supplier API Implementation
File to Create: suppliers/api.py
pythonfrom rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.db import transaction
from .models import SupplierProfile
from .serializers import SupplierProfileSerializer, SupplierRegistrationSerializer
from products.models import Product
from products.serializers import ProductSerializer
from orders.models import Order
from orders.serializers import OrderSerializer

class SupplierProfileViewSet(viewsets.ModelViewSet):
    serializer_class = SupplierProfileSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        if self.request.user.user_type == 'supplier':
            return SupplierProfile.objects.filter(user=self.request.user)
        elif self.request.user.user_type == 'admin':
            return SupplierProfile.objects.all()
         return SupplierProfile.objects.none()

def get_serializer_class(self):
    if self.action == 'register':
        return SupplierRegistrationSerializer
    return SupplierProfileSerializer

@action(detail=False, methods=['post'])
def register(self, request):
    """Register new supplier with verification"""
    serializer = SupplierRegistrationSerializer(data=request.data)
    if serializer.is_valid():
        with transaction.atomic():
            supplier = serializer.save()
            return Response({
                'message': 'Supplier registration successful. Verification pending.',
                'supplier': SupplierProfileSerializer(supplier).data
            }, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@action(detail=True, methods=['post'])
def verify(self, request, pk=None):
    """Admin endpoint to verify supplier"""
    if request.user.user_type != 'admin':
        return Response({
            'error': 'Only admins can verify suppliers'
        }, status=status.HTTP_403_FORBIDDEN)
    
    supplier = self.get_object()
    verification_status = request.data.get('verification_status')
    notes = request.data.get('notes', '')
    
    if verification_status not in ['verified', 'rejected']:
        return Response({
            'error': 'Invalid verification status'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    supplier.verification_status = verification_status
    supplier.save()
    
    # TODO: Send notification to supplier
    
    return Response({
        'message': f'Supplier {verification_status} successfully',
        'supplier': SupplierProfileSerializer(supplier).data
    })

@action(detail=False, methods=['get'])
def my_products(self, request):
    """Get products for authenticated supplier"""
    if request.user.user_type != 'supplier':
        return Response({
            'error': 'Only suppliers can access this endpoint'
        }, status=status.HTTP_403_FORBIDDEN)
    
    try:
        supplier = SupplierProfile.objects.get(user=request.user)
    except SupplierProfile.DoesNotExist:
        return Response({
            'error': 'Supplier profile not found'
        }, status=status.HTTP_404_NOT_FOUND)
    
    products = Product.objects.filter(supplier=supplier).order_by('-created_at')
    
    page = self.paginate_queryset(products)
    if page is not None:
        serializer = ProductSerializer(page, many=True)
        return self.get_paginated_response(serializer.data)
    
    serializer = ProductSerializer(products, many=True)
    return Response(serializer.data)

@action(detail=False, methods=['get'])
def my_orders(self, request):
    """Get orders for authenticated supplier"""
    if request.user.user_type != 'supplier':
        return Response({
            'error': 'Only suppliers can access this endpoint'
        }, status=status.HTTP_403_FORBIDDEN)
    
    try:
        supplier = SupplierProfile.objects.get(user=request.user)
    except SupplierProfile.DoesNotExist:
        return Response({
            'error': 'Supplier profile not found'
        }, status=status.HTTP_404_NOT_FOUND)
    
    orders = Order.objects.filter(supplier=supplier).order_by('-created_at')
    
    page = self.paginate_queryset(orders)
    if page is not None:
        serializer = OrderSerializer(page, many=True)
        return self.get_paginated_response(serializer.data)
    
    serializer = OrderSerializer(orders, many=True)
    return Response(serializer.data)

@action(detail=False, methods=['get'])
def dashboard(self, request):
    """Supplier dashboard analytics"""
    if request.user.user_type != 'supplier':
        return Response({
            'error': 'Only suppliers can access dashboard'
        }, status=status.HTTP_403_FORBIDDEN)
    
    try:
        supplier = SupplierProfile.objects.get(user=request.user)
    except SupplierProfile.DoesNotExist:
        return Response({
            'error': 'Supplier profile not found'
        }, status=status.HTTP_404_NOT_FOUND)
    
    # Calculate dashboard metrics
    from django.db.models import Count, Sum, Avg
    from decimal import Decimal
    
    total_products = Product.objects.filter(supplier=supplier).count()
    active_products = Product.objects.filter(supplier=supplier, is_active=True).count()
    
    orders_stats = Order.objects.filter(supplier=supplier).aggregate(
        total_orders=Count('id'),
        total_revenue=Sum('total_amount'),
        pending_orders=Count('id', filter=models.Q(status='pending')),
        completed_orders=Count('id', filter=models.Q(status='delivered'))
    )
    
    # Recent orders
    recent_orders = Order.objects.filter(supplier=supplier).order_by('-created_at')[:5]
    
    # Top products by sales
    top_products = Product.objects.filter(supplier=supplier).annotate(
        order_count=Count('orderitem__order')
    ).order_by('-order_count')[:5]
    
    return Response({
        'total_products': total_products,
        'active_products': active_products,
        'total_orders': orders_stats['total_orders'] or 0,
        'total_revenue': orders_stats['total_revenue'] or Decimal('0.00'),
        'pending_orders': orders_stats['pending_orders'] or 0,
        'completed_orders': orders_stats['completed_orders'] or 0,
        'recent_orders': OrderSerializer(recent_orders, many=True).data,
        'top_products': ProductSerializer(top_products, many=True).data,
        'verification_status': supplier.verification_status,
        'performance_rating': supplier.performance_rating
    })
class SupplierProductViewSet(viewsets.ModelViewSet):
serializer_class = ProductSerializer
permission_classes = [permissions.IsAuthenticated]
def get_queryset(self):
    if self.request.user.user_type != 'supplier':
        return Product.objects.none()
    
    try:
        supplier = SupplierProfile.objects.get(user=self.request.user)
        return Product.objects.filter(supplier=supplier)
    except SupplierProfile.DoesNotExist:
        return Product.objects.none()

def perform_create(self, serializer):
    """Create product for authenticated supplier"""
    try:
        supplier = SupplierProfile.objects.get(user=self.request.user)
        if supplier.verification_status != 'verified':
            raise ValidationError("Only verified suppliers can add products")
        serializer.save(supplier=supplier)
    except SupplierProfile.DoesNotExist:
        raise ValidationError("Supplier profile not found")

@action(detail=True, methods=['post'])
def update_inventory(self, request, pk=None):
    """Update product inventory"""
    product = self.get_object()
    new_quantity = request.data.get('quantity')
    
    if new_quantity is None:
        return Response({
            'error': 'Quantity is required'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        new_quantity = int(new_quantity)
        if new_quantity < 0:
            raise ValueError("Quantity cannot be negative")
    except (ValueError, TypeError):
        return Response({
            'error': 'Invalid quantity'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    old_quantity = product.stock_quantity
    product.stock_quantity = new_quantity
    product.save()
    
    return Response({
        'message': 'Inventory updated successfully',
        'old_quantity': old_quantity,
        'new_quantity': new_quantity,
        'product': ProductSerializer(product).data
    })

@action(detail=False, methods=['post'])
def bulk_upload(self, request):
    """Bulk upload products from CSV or JSON"""
    if request.user.user_type != 'supplier':
        return Response({
            'error': 'Only suppliers can bulk upload products'
        }, status=status.HTTP_403_FORBIDDEN)
    
    try:
        supplier = SupplierProfile.objects.get(user=request.user)
        if supplier.verification_status != 'verified':
            return Response({
                'error': 'Only verified suppliers can add products'
            }, status=status.HTTP_400_BAD_REQUEST)
    except SupplierProfile.DoesNotExist:
        return Response({
            'error': 'Supplier profile not found'
        }, status=status.HTTP_404_NOT_FOUND)
    
    products_data = request.data.get('products', [])
    if not products_data:
        return Response({
            'error': 'No products data provided'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    created_products = []
    errors = []
    
    for i, product_data in enumerate(products_data):
        try:
            serializer = ProductSerializer(data=product_data)
            if serializer.is_valid():
                product = serializer.save(supplier=supplier)
                created_products.append(ProductSerializer(product).data)
            else:
                errors.append({
                    'index': i,
                    'errors': serializer.errors
                })
        except Exception as e:
            errors.append({
                'index': i,
                'errors': str(e)
            })
    
    return Response({
        'message': f'{len(created_products)} products created successfully',
        'created_products': created_products,
        'errors': errors
    }, status=status.HTTP_201_CREATED if created_products else status.HTTP_400_BAD_REQUEST)

**File to Create:** `suppliers/serializers.py`

```python
from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import SupplierProfile

User = get_user_model()

class SupplierRegistrationSerializer(serializers.Serializer):
    # User fields
    username = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=8)
    phone_number = serializers.CharField(max_length=20)
    
    # Supplier profile fields
    company_name = serializers.CharField(max_length=200)
    business_registration = serializers.CharField(max_length=100)
    tax_id = serializers.CharField(max_length=100)
    address = serializers.CharField()
    contact_person = serializers.CharField(max_length=100)
    commission_rate = serializers.DecimalField(max_digits=5, decimal_places=2, min_value=0, max_value=50)
    payment_terms = serializers.CharField(max_length=100)
    minimum_order_value = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=0)
    
    # Optional fields
    bank_details = serializers.JSONField(required=False)
    delivery_areas = serializers.JSONField(required=False)
    business_hours = serializers.JSONField(required=False)
    
    def validate_username(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("Username already exists")
        return value
    
    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("Email already exists")
        return value
    
    def validate_phone_number(self, value):
        if User.objects.filter(phone_number=value).exists():
            raise serializers.ValidationError("Phone number already exists")
        return value
    
    def validate_business_registration(self, value):
        if SupplierProfile.objects.filter(business_registration=value).exists():
            raise serializers.ValidationError("Business registration already exists")
        return value
    
    def create(self, validated_data):
        # Extract user data
        user_data = {
            'username': validated_data.pop('username'),
            'email': validated_data.pop('email'),
            'phone_number': validated_data.pop('phone_number'),
            'user_type': 'supplier',
            'referral_code': f"SUP{validated_data['company_name'][:3].upper()}{User.objects.count() + 1:04d}"
        }
        password = validated_data.pop('password')
        
        # Create user
        user = User.objects.create_user(**user_data)
        user.set_password(password)
        user.save()
        
        # Create supplier profile
        supplier = SupplierProfile.objects.create(
            user=user,
            **validated_data
        )
        
        return supplier

class SupplierProfileSerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source='user.email', read_only=True)
    user_phone = serializers.CharField(source='user.phone_number', read_only=True)
    
    class Meta:
        model = SupplierProfile
        fields = [
            'id', 'user_email', 'user_phone', 'company_name', 
            'business_registration', 'tax_id', 'address', 'contact_person',
            'phone_number', 'email', 'bank_details', 'commission_rate',
            'payment_terms', 'minimum_order_value', 'delivery_areas',
            'business_hours', 'verification_status', 'performance_rating',
            'is_active'
        ]
        read_only_fields = [
            'id', 'verification_status', 'performance_rating', 'user_email', 'user_phone'
        ]
File to Create: suppliers/urls.py
pythonfrom django.urls import path, include
from rest_framework.routers import DefaultRouter
from .api import SupplierProfileViewSet, SupplierProductViewSet

router = DefaultRouter()
router.register(r'profiles', SupplierProfileViewSet, basename='supplier-profile')
router.register(r'products', SupplierProductViewSet, basename='supplier-product')

urlpatterns = [
    path('', include(router.urls)),
]
Update: payjaro_project/urls.py
python# ADD THIS LINE to the urlpatterns list
path('api/suppliers/', include('suppliers.urls')),
VALIDATION COMMANDS:
bash# Test supplier registration and management
python manage.py test suppliers.tests

# Test API endpoints
python manage.py runserver

# Test supplier registration:
# POST http://localhost:8000/api/suppliers/profiles/register/

# Test supplier dashboard:
# GET http://localhost:8000/api/suppliers/profiles/dashboard/

PHASE 5: SOCIAL COMMERCE & ANALYTICS
TASK 5.1: Implement Public Storefront System
File to Create: public/__init__.py
File to Create: public/apps.py
pythonfrom django.apps import AppConfig

class PublicConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "public"
File to Create: public/views.py
pythonfrom rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from django.db.models import Prefetch
from entrepreneurs.models import EntrepreneurProfile
from social.models import EntrepreneurStorefront, FeaturedProduct
from products.models import Product
from products.serializers import ProductSerializer
from entrepreneurs.serializers import EntrepreneurProfileSerializer
from social.serializers import EntrepreneurStorefrontSerializer

@api_view(['GET'])
@permission_classes([AllowAny])
def public_storefront(request, custom_url):
    """Public view of entrepreneur's storefront"""
    try:
        entrepreneur = get_object_or_404(
            EntrepreneurProfile.objects.select_related('user'),
            custom_url=custom_url,
            is_active=True
        )
        
        # Get storefront with featured products
        try:
            storefront = EntrepreneurStorefront.objects.select_related('entrepreneur').prefetch_related(
                Prefetch('featured_products', queryset=Product.objects.filter(is_active=True))
            ).get(entrepreneur=entrepreneur, is_published=True)
        except EntrepreneurStorefront.DoesNotExist:
            return Response({
                'error': 'Storefront not found or not published'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Get all products this entrepreneur is selling (not just featured)
        available_products = Product.objects.filter(
            is_active=True,
            stock_quantity__gt=0
        ).order_by('-created_at')
        
        # Track storefront view (for analytics)
        from analytics.services import AnalyticsService
        AnalyticsService.track_event(
            event_type='storefront_view',
            entrepreneur=entrepreneur,
            metadata={
                'visitor_ip': request.META.get('REMOTE_ADDR'),
                'user_agent': request.META.get('HTTP_USER_AGENT'),
                'referrer': request.META.get('HTTP_REFERER'),
                'custom_url': custom_url
            }
        )
        
        return Response({
            'entrepreneur': EntrepreneurProfileSerializer(entrepreneur).data,
            'storefront': EntrepreneurStorefrontSerializer(storefront).data,
            'featured_products': ProductSerializer(storefront.featured_products.all(), many=True).data,
            'all_products': ProductSerializer(available_products[:20], many=True).data,  # Limit for performance
            'seo': {
                'title': storefront.seo_title or f"{entrepreneur.business_name} - Payjaro Store",
                'description': storefront.seo_description or f"Shop from {entrepreneur.business_name} on Payjaro",
                'canonical_url': f"https://payjaro.com/{custom_url}",
                'og_image': entrepreneur.banner_image.url if entrepreneur.banner_image else None
            }
        })
        
    except Exception as e:
        return Response({
            'error': 'Storefront not found'
        }, status=status.HTTP_404_NOT_FOUND)

@api_view(['GET'])
@permission_classes([AllowAny])
def product_share_link(request, custom_url, product_slug):
    """Public view of product with entrepreneur context for sharing"""
    try:
        entrepreneur = get_object_or_404(
            EntrepreneurProfile,
            custom_url=custom_url,
            is_active=True
        )
        
        product = get_object_or_404(
            Product,
            slug=product_slug,
            is_active=True
        )
        
        # Track product view
        from analytics.services import AnalyticsService
        AnalyticsService.track_event(
            event_type='product_view',
            entrepreneur=entrepreneur,
            product=product,
            metadata={
                'visitor_ip': request.META.get('REMOTE_ADDR'),
                'user_agent': request.META.get('HTTP_USER_AGENT'),
                'referrer': request.META.get('HTTP_REFERER'),
                'share_link': True
            }
        )
        
        # Generate purchase link
        purchase_link = f"https://payjaro.com/order?entrepreneur={custom_url}&product={product_slug}"
        
        return Response({
            'product': ProductSerializer(product).data,
            'entrepreneur': EntrepreneurProfileSerializer(entrepreneur).data,
            'purchase_link': purchase_link,
            'share_data': {
                'title': f"{product.name} - {entrepreneur.business_name}",
                'description': product.description[:150] + "..." if len(product.description) > 150 else product.description,
                'image': product.images.filter(is_primary=True).first().image.url if product.images.filter(is_primary=True).exists() else None,
                'url': f"https://payjaro.com/{custom_url}/product/{product_slug}"
            },
            'pricing': {
                'base_price': product.base_price,
                'suggested_markup': product.suggested_markup,
                'entrepreneur_commission': entrepreneur.commission_rate
            }
        })
        
    except Exception as e:
        return Response({
            'error': 'Product or entrepreneur not found'
        }, status=status.HTTP_404_NOT_FOUND)

@api_view(['GET'])
@permission_classes([AllowAny])
def generate_share_links(request, custom_url):
    """Generate sharing links for social media platforms"""
    entrepreneur = get_object_or_404(
        EntrepreneurProfile,
        custom_url=custom_url,
        is_active=True
    )
    
    product_id = request.GET.get('product_id')
    base_url = f"https://payjaro.com/{custom_url}"
    
    if product_id:
        try:
            product = Product.objects.get(id=product_id, is_active=True)
            product_url = f"{base_url}/product/{product.slug}"
            share_text = f"Check out {product.name} from {entrepreneur.business_name}! 🛍️"
            
            return Response({
                'whatsapp': f"https://wa.me/?text={share_text} {product_url}",
                'instagram': product_url,  # For Instagram stories/posts
                'facebook': f"https://www.facebook.com/sharer/sharer.php?u={product_url}",
                'twitter': f"https://twitter.com/intent/tweet?text={share_text}&url={product_url}",
                'copy_link': product_url,
                'qr_code': f"https://api.qrserver.com/v1/create-qr-code/?size=200x200&data={product_url}"
            })
        except Product.DoesNotExist:
            return Response({
                'error': 'Product not found'
            }, status=status.HTTP_404_NOT_FOUND)
    else:
        # Share storefront
        share_text = f"Shop from {entrepreneur.business_name} on Payjaro! 🛍️"
        
        return Response({
            'whatsapp': f"https://wa.me/?text={share_text} {base_url}",
            'instagram': base_url,
            'facebook': f"https://www.facebook.com/sharer/sharer.php?u={base_url}",
            'twitter': f"https://twitter.com/intent/tweet?text={share_text}&url={base_url}",
            'copy_link': base_url,
            'qr_code': f"https://api.qrserver.com/v1/create-qr-code/?size=200x200&data={base_url}"
        })
File to Create: public/urls.py
pythonfrom django.urls import path
from . import views

urlpatterns = [
    path('<str:custom_url>/', views.public_storefront, name='public-storefront'),
    path('<str:custom_url>/product/<str:product_slug>/', views.product_share_link, name='product-share-link'),
    path('<str:custom_url>/share/', views.generate_share_links, name='generate-share-links'),
]
TASK 5.2: Implement Analytics System
File to Create: analytics/services.py
pythonfrom django.db import models
from django.utils import timezone
from .models import AnalyticsEvent, DailyMetrics
from entrepreneurs.models import EntrepreneurProfile
from products.models import Product
from orders.models import Order
import logging

logger = logging.getLogger(__name__)

class AnalyticsService:
    @staticmethod
    def track_event(event_type, entrepreneur=None, product=None, order=None, user=None, metadata=None):
        """Track analytics event"""
        try:
            AnalyticsEvent.objects.create(
                event_type=event_type,
                user=user,
                entrepreneur=entrepreneur,
                product=product,
                order=order,
                metadata=metadata or {},
                ip_address=metadata.get('visitor_ip', '127.0.0.1') if metadata else '127.0.0.1',
                user_agent=metadata.get('user_agent', '') if metadata else ''
            )
        except Exception as e:
            logger.error(f"Failed to track event {event_type}: {str(e)}")
    
    @staticmethod
    def get_entrepreneur_analytics(entrepreneur, start_date=None, end_date=None):
        """Get comprehensive analytics for entrepreneur"""
        if not start_date:
            start_date = timezone.now() - timezone.timedelta(days=30)
        if not end_date:
            end_date = timezone.now()
        
        # Basic metrics
        events = AnalyticsEvent.objects.filter(
            entrepreneur=entrepreneur,
            timestamp__range=[start_date, end_date]
        )
        
        analytics = {
            'total_views': events.filter(event_type='storefront_view').count(),
            'product_views': events.filter(event_type='product_view').count(),
            'unique_visitors': events.values('ip_address').distinct().count(),
            'social_shares': events.filter(event_type='product_share').count(),
        }
        
        # Order analytics
        orders = Order.objects.filter(
            entrepreneur=entrepreneur,
            created_at__range=[start_date, end_date]
        )
        
        order_analytics = orders.aggregate(
            total_orders=models.Count('id'),
            total_revenue=models.Sum('total_amount'),
            total_items_sold=models.Sum('items__quantity'),
            average_order_value=models.Avg('total_amount')
        )
        
        analytics.update({
            'total_orders': order_analytics['total_orders'] or 0,
            'total_revenue': order_analytics['total_revenue'] or 0,
            'total_items_sold': order_analytics['total_items_sold'] or 0,
            'average_order_value': order_analytics['average_order_value'] or 0,
            'conversion_rate': (order_analytics['total_orders'] / analytics['total_views']) * 100 if analytics['total_views'] > 0 else 0
        })
        
        # Top products
        from django.db.models import Count, Sum
        top_products = Product.objects.filter(
            orderitem__order__entrepreneur=entrepreneur,
            orderitem__order__created_at__range=[start_date, end_date]
        ).annotate(
            order_count=Count('orderitem__order'),
            total_quantity=Sum('orderitem__quantity'),
            total_revenue=Sum('orderitem__total_price')
        ).order_by('-order_count')[:5]
        
        analytics['top_products'] = [{
            'product': product,
            'order_count': product.order_count,
            'total_quantity': product.total_quantity,
            'total_revenue': product.total_revenue
        } for product in top_products]
        
        # Daily breakdown
        daily_data = []
        current_date = start_date.date()
        end_date_only = end_date.date()
        
        while current_date <= end_date_only:
            day_events = events.filter(timestamp__date=current_date)
            day_orders = orders.filter(created_at__date=current_date)
            
            daily_data.append({
                'date': current_date.isoformat(),
                'views': day_events.filter(event_type='storefront_view').count(),
                'orders': day_orders.count(),
                'revenue': day_orders.aggregate(total=models.Sum('total_amount'))['total'] or 0
            })
            
            current_date += timezone.timedelta(days=1)
        
        analytics['daily_breakdown'] = daily_data
        
        return analytics
    
    @staticmethod
    def calculate_daily_metrics():
        """Calculate and store daily metrics for all entrepreneurs"""
        yesterday = timezone.now().date() - timezone.timedelta(days=1)
        
        for entrepreneur in EntrepreneurProfile.objects.filter(is_active=True):
            try:
                analytics = AnalyticsService.get_entrepreneur_analytics(
                    entrepreneur,
                    start_date=timezone.datetime.combine(yesterday, timezone.datetime.min.time()),
                    end_date=timezone.datetime.combine(yesterday, timezone.datetime.max.time())
                )
                
                DailyMetrics.objects.update_or_create(
                    date=yesterday,
                    metric_type='entrepreneur_performance',
                    entity_type='entrepreneur',
                    entity_id=str(entrepreneur.id),
                    defaults={
                        'value': analytics['total_revenue'],
                        'metadata': {
                            'views': analytics['total_views'],
                            'orders': analytics['total_orders'],
                            'conversion_rate': analytics['conversion_rate'],
                            'average_order_value': float(analytics['average_order_value'])
                        }
                    }
                )
            except Exception as e:
                logger.error(f"Failed to calculate daily metrics for entrepreneur {entrepreneur.id}: {str(e)}")
File to Create: analytics/api.py
pythonfrom rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from django.shortcuts import get_object_or_404
from django.utils import timezone
from entrepreneurs.models import EntrepreneurProfile
from .services import AnalyticsService

class TrackEventView(APIView):
    permission_classes = [AllowAny]
    
    def post(self, request):
        """Track analytics event from frontend"""
        event_type = request.data.get('event_type')
        entrepreneur_id = request.data.get('entrepreneur_id')
        product_id = request.data.get('product_id')
        metadata = request.data.get('metadata', {})
        
        # Add request metadata
        metadata.update({
            'visitor_ip': request.META.get('REMOTE_ADDR'),
            'user_agent': request.META.get('HTTP_USER_AGENT'),
            'referrer': request.META.get('HTTP_REFERER')
        })
        
        try:
            entrepreneur = None
            if entrepreneur_id:
                entrepreneur = EntrepreneurProfile.objects.get(id=entrepreneur_id)
            
            product = None
            if product_id:
                from products.models import Product
                product = Product.objects.get(id=product_id)
            
            AnalyticsService.track_event(
                event_type=event_type,
                entrepreneur=entrepreneur,
                product=product,
                user=request.user if request.user.is_authenticated else None,
                metadata=metadata
            )
            
            return Response({'status': 'success'})
        
        except Exception as e:
            return Response({
                'error': 'Failed to track event'
            }, status=status.HTTP_400_BAD_REQUEST)

class EntrepreneurAnalyticsView(APIView):# Payjaro Backend - AI Implementation Guide
## Complete Step-by-Step Instructions for Building Production-Ready MVP

---

## **CRITICAL CONTEXT FOR AI DEVELOPER**

**Current State:** Excellent Django foundation with 90% of models complete, 40% of APIs implemented
**Target:** Full-featured social commerce platform MVP ready for production
**Architecture:** Django REST Framework + PostgreSQL + Redis + AWS S3 + Payment Gateways
**Timeline:** Each phase builds on previous - DO NOT SKIP STEPS

---

## **PHASE 1: COMPLETE ORDERS API SYSTEM**

### **TASK 1.1: Implement Order Creation API with Business Logic**

**File to Create:** `orders/api.py`

```python
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db import transaction
from django.shortcuts import get_object_or_404
from decimal import Decimal
from .models import Order, OrderItem, OrderStatusHistory
from .serializers import (
    OrderSerializer, OrderCreateSerializer, 
    OrderItemSerializer, OrderStatusSerializer
)
from entrepreneurs.models import EntrepreneurProfile
from products.models import Product, ProductVariation
from payments.models import Earnings, Transaction as PaymentTransaction
import uuid
from datetime import datetime

class OrderViewSet(viewsets.ModelViewSet):
    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        if user.user_type == 'customer':
            return Order.objects.filter(customer=user)
        elif user.user_type == 'entrepreneur':
            entrepreneur = get_object_or_404(EntrepreneurProfile, user=user)
            return Order.objects.filter(entrepreneur=entrepreneur)
        elif user.user_type == 'supplier':
            # Return orders for supplier's products
            return Order.objects.filter(supplier__user=user)
        return Order.objects.none()
    
    def get_serializer_class(self):
        if self.action == 'create':
            return OrderCreateSerializer
        return OrderSerializer
    
    @transaction.atomic
    def create(self, request, *args, **kwargs):
        """
        CRITICAL: This method handles the complete order creation workflow
        1. Validate all order items and inventory
        2. Calculate pricing (markup + commission)
        3. Create order with proper relationships
        4. Reserve inventory
        5. Create earnings records
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Extract validated data
        order_data = serializer.validated_data
        items_data = order_data.pop('items')
        entrepreneur_slug = order_data.pop('entrepreneur_custom_url')
        
        # Get entrepreneur
        entrepreneur = get_object_or_404(
            EntrepreneurProfile, 
            custom_url=entrepreneur_slug
        )
        
        # Validate inventory for all items
        inventory_errors = []
        total_calculations = {
            'subtotal': Decimal('0.00'),
            'markup_amount': Decimal('0.00'),
            'commission_amount': Decimal('0.00'),
            'total_amount': Decimal('0.00')
        }
        
        validated_items = []
        
        for item_data in items_data:
            product = item_data['product']
            variation = item_data.get('variation')
            quantity = item_data['quantity']
            entrepreneur_price = Decimal(str(item_data['unit_price']))
            
            # Check inventory
            available_stock = variation.stock_quantity if variation else product.stock_quantity
            if available_stock < quantity:
                inventory_errors.append(
                    f"Insufficient stock for {product.name}. Available: {available_stock}, Requested: {quantity}"
                )
                continue
            
            # Calculate pricing
            base_price = product.base_price
            if variation and variation.price_modifier:
                base_price += variation.price_modifier
            
            item_subtotal = base_price * quantity
            markup_per_item = entrepreneur_price - base_price
            item_markup = markup_per_item * quantity
            item_commission = (entrepreneur_price * quantity) * (entrepreneur.commission_rate / 100)
            item_total = entrepreneur_price * quantity
            
            # Validate markup is not negative
            if markup_per_item < 0:
                inventory_errors.append(
                    f"Price for {product.name} cannot be less than base price ₦{base_price}"
                )
                continue
            
            validated_items.append({
                'product': product,
                'variation': variation,
                'quantity': quantity,
                'unit_price': entrepreneur_price,
                'base_price': base_price,
                'markup_amount': item_markup,
                'total_price': item_total
            })
            
            # Add to totals
            total_calculations['subtotal'] += item_subtotal
            total_calculations['markup_amount'] += item_markup
            total_calculations['commission_amount'] += item_commission
            total_calculations['total_amount'] += item_total
        
        if inventory_errors:
            return Response({
                'errors': inventory_errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Calculate shipping (basic implementation)
        shipping_fee = Decimal('500.00')  # Fixed for now
        total_calculations['total_amount'] += shipping_fee
        
        # Generate unique order ID
        order_id = f"PAY{datetime.now().strftime('%Y%m%d')}{str(uuid.uuid4())[:8].upper()}"
        
        # Create order
        order = Order.objects.create(
            order_id=order_id,
            customer=request.user,
            entrepreneur=entrepreneur,
            supplier=validated_items[0]['product'].supplier,  # Assuming single supplier per order
            status='pending',
            subtotal=total_calculations['subtotal'],
            markup_amount=total_calculations['markup_amount'],
            commission_amount=total_calculations['commission_amount'],
            shipping_fee=shipping_fee,
            total_amount=total_calculations['total_amount'],
            payment_status='pending',
            payment_method='',  # Will be set during payment
            shipping_address=order_data.get('shipping_address', {}),
            notes=order_data.get('notes', '')
        )
        
        # Create order items and reserve inventory
        for item_data in validated_items:
            OrderItem.objects.create(
                order=order,
                product=item_data['product'],
                variation=item_data['variation'],
                quantity=item_data['quantity'],
                unit_price=item_data['unit_price'],
                base_price=item_data['base_price'],
                markup_amount=item_data['markup_amount'],
                total_price=item_data['total_price']
            )
            
            # Reserve inventory
            if item_data['variation']:
                item_data['variation'].stock_quantity -= item_data['quantity']
                item_data['variation'].save()
            else:
                item_data['product'].stock_quantity -= item_data['quantity']
                item_data['product'].save()
        
        # Create status history
        OrderStatusHistory.objects.create(
            order=order,
            status='pending',
            notes='Order created',
            created_by=request.user
        )
        
        # Create earnings records (pending until payment)
        Earnings.objects.create(
            entrepreneur=entrepreneur,
            order=order,
            earning_type='markup',
            amount=total_calculations['markup_amount'],
            status='pending'
        )
        
        Earnings.objects.create(
            entrepreneur=entrepreneur,
            order=order,
            earning_type='commission',
            amount=total_calculations['commission_amount'],
            status='pending'
        )
        
        serializer = OrderSerializer(order)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    
    @action(detail=True, methods=['post'])
    def update_status(self, request, pk=None):
        """Update order status with proper validation and history tracking"""
        order = self.get_object()
        new_status = request.data.get('status')
        notes = request.data.get('notes', '')
        
        if new_status not in dict(Order.ORDER_STATUS).keys():
            return Response({
                'error': 'Invalid status'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Validate status transitions
        valid_transitions = {
            'pending': ['paid', 'cancelled'],
            'paid': ['processing', 'cancelled'],
            'processing': ['shipped', 'cancelled'],
            'shipped': ['delivered', 'returned'],
            'delivered': ['returned'],
            'cancelled': [],
            'returned': []
        }
        
        if new_status not in valid_transitions.get(order.status, []):
            return Response({
                'error': f'Cannot transition from {order.status} to {new_status}'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Update order status
        old_status = order.status
        order.status = new_status
        order.save()
        
        # Create status history
        OrderStatusHistory.objects.create(
            order=order,
            status=new_status,
            notes=notes,
            created_by=request.user
        )
        
        # Handle status-specific logic
        if new_status == 'cancelled' and old_status == 'pending':
            # Restore inventory
            for item in order.items.all():
                if item.variation:
                    item.variation.stock_quantity += item.quantity
                    item.variation.save()
                else:
                    item.product.stock_quantity += item.quantity
                    item.product.save()
            
            # Update earnings to cancelled
            Earnings.objects.filter(order=order).update(status='cancelled')
        
        return Response({
            'message': f'Order status updated to {new_status}',
            'order': OrderSerializer(order).data
        })
    
    @action(detail=False, methods=['get'])
    def entrepreneur_orders(self, request):
        """Get orders for the authenticated entrepreneur"""
        if request.user.user_type != 'entrepreneur':
            return Response({
                'error': 'Only entrepreneurs can access this endpoint'
            }, status=status.HTTP_403_FORBIDDEN)
        
        entrepreneur = get_object_or_404(EntrepreneurProfile, user=request.user)
        orders = Order.objects.filter(entrepreneur=entrepreneur).order_by('-created_at')
        
        # Add pagination
        page = self.paginate_queryset(orders)
        if page is not None:
            serializer = OrderSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = OrderSerializer(orders, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def supplier_orders(self, request):
        """Get orders for the authenticated supplier"""
        if request.user.user_type != 'supplier':
            return Response({
                'error': 'Only suppliers can access this endpoint'
            }, status=status.HTTP_403_FORBIDDEN)
        
        orders = Order.objects.filter(supplier__user=request.user).order_by('-created_at')
        
        page = self.paginate_queryset(orders)
        if page is not None:
            serializer = OrderSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = OrderSerializer(orders, many=True)
        return Response(serializer.data)
File to Create: orders/serializers.py
pythonfrom rest_framework import serializers
from .models import Order, OrderItem, OrderStatusHistory
from entrepreneurs.models import EntrepreneurProfile
from products.models import Product, ProductVariation
from products.serializers import ProductSerializer
from users.serializers import UserProfileSerializer

class OrderItemSerializer(serializers.ModelSerializer):
    product = ProductSerializer(read_only=True)
    product_name = serializers.CharField(source='product.name', read_only=True)
    
    class Meta:
        model = OrderItem
        fields = [
            'id', 'product', 'product_name', 'variation', 
            'quantity', 'unit_price', 'base_price', 
            'markup_amount', 'total_price'
        ]

class OrderItemCreateSerializer(serializers.Serializer):
    product_id = serializers.IntegerField()
    variation_id = serializers.IntegerField(required=False, allow_null=True)
    quantity = serializers.IntegerField(min_value=1)
    unit_price = serializers.DecimalField(max_digits=12, decimal_places=2)
    
    def validate(self, data):
        # Validate product exists
        try:
            product = Product.objects.get(id=data['product_id'], is_active=True)
        except Product.DoesNotExist:
            raise serializers.ValidationError("Product not found or inactive")
        
        # Validate variation if provided
        variation = None
        if data.get('variation_id'):
            try:
                variation = ProductVariation.objects.get(
                    id=data['variation_id'], 
                    product=product
                )
            except ProductVariation.DoesNotExist:
                raise serializers.ValidationError("Product variation not found")
        
        data['product'] = product
        data['variation'] = variation
        return data

class OrderStatusHistorySerializer(serializers.ModelSerializer):
    created_by = UserProfileSerializer(read_only=True)
    
    class Meta:
        model = OrderStatusHistory
        fields = ['id', 'status', 'notes', 'created_by', 'created_at']

class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    customer = UserProfileSerializer(read_only=True)
    entrepreneur = serializers.StringRelatedField(read_only=True)
    supplier = serializers.StringRelatedField(read_only=True)
    status_history = OrderStatusHistorySerializer(many=True, read_only=True)
    
    class Meta:
        model = Order
        fields = [
            'id', 'order_id', 'customer', 'entrepreneur', 'supplier',
            'status', 'subtotal', 'markup_amount', 'commission_amount',
            'shipping_fee', 'total_amount', 'payment_status', 'payment_method',
            'shipping_address', 'tracking_number', 'notes', 'created_at',
            'updated_at', 'items', 'status_history'
        ]
        read_only_fields = [
            'id', 'order_id', 'subtotal', 'markup_amount', 'commission_amount',
            'total_amount', 'created_at', 'updated_at'
        ]

class OrderCreateSerializer(serializers.Serializer):
    entrepreneur_custom_url = serializers.CharField(max_length=100)
    items = OrderItemCreateSerializer(many=True)
    shipping_address = serializers.JSONField()
    notes = serializers.CharField(required=False, allow_blank=True)
    
    def validate_entrepreneur_custom_url(self, value):
        try:
            EntrepreneurProfile.objects.get(custom_url=value, is_active=True)
        except EntrepreneurProfile.DoesNotExist:
            raise serializers.ValidationError("Entrepreneur not found")
        return value
    
    def validate_items(self, value):
        if not value:
            raise serializers.ValidationError("At least one item is required")
        return value
    
    def validate_shipping_address(self, value):
        required_fields = ['full_name', 'phone', 'address', 'city', 'state']
        for field in required_fields:
            if field not in value or not value[field]:
                raise serializers.ValidationError(f"Shipping address must include {field}")
        return value
File to Create: orders/urls.py
pythonfrom django.urls import path, include
from rest_framework.routers import DefaultRouter
from .api import OrderViewSet

router = DefaultRouter()
router.register(r'orders', OrderViewSet, basename='order')

urlpatterns = [
    path('', include(router.urls)),
]
Update: payjaro_project/urls.py
python# ADD THIS LINE to the urlpatterns list
path('api/orders/', include('orders.urls')),
VALIDATION COMMANDS:
bash# Run these commands in sequence
python manage.py makemigrations
python manage.py migrate
python manage.py test orders.tests
python manage.py runserver

# Test in browser/Postman:
# POST http://localhost:8000/api/orders/orders/
# GET http://localhost:8000/api/orders/orders/
CRITICAL CHECKPOINTS:

 Order creation API responds with 201 status
 Commission calculations are accurate
 Inventory is properly reserved
 Order status updates work correctly
 All tests pass without errors


PHASE 2: PAYMENT INTEGRATION SYSTEM
TASK 2.1: Implement Paystack Payment Integration
Install Required Dependencies:
bashpip install paystack-python requests cryptography
pip freeze > requirements.txt
File to Create: payments/services.py
pythonimport os
import hashlib
import hmac
import json
import requests
from decimal import Decimal
from django.conf import settings
from .models import Transaction, PaymentMethod
import logging

logger = logging.getLogger(__name__)

class PaystackService:
    def __init__(self):
        self.secret_key = settings.PAYSTACK_SECRET_KEY
        self.public_key = settings.PAYSTACK_PUBLIC_KEY
        self.base_url = "https://api.paystack.co"
        
    def _make_request(self, method, endpoint, data=None):
        """Make authenticated request to Paystack API"""
        headers = {
            'Authorization': f'Bearer {self.secret_key}',
            'Content-Type': 'application/json'
        }
        
        url = f"{self.base_url}{endpoint}"
        
        try:
            if method == 'POST':
                response = requests.post(url, headers=headers, json=data)
            elif method == 'GET':
                response = requests.get(url, headers=headers, params=data)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
            
            response.raise_for_status()
            return response.json()
        
        except requests.exceptions.RequestException as e:
            logger.error(f"Paystack API request failed: {str(e)}")
            raise Exception(f"Payment service error: {str(e)}")
    
    def initialize_payment(self, order, callback_url):
        """Initialize payment transaction with Paystack"""
        # Convert amount to kobo (Paystack uses kobo)
        amount_kobo = int(order.total_amount * 100)
        
        data = {
            'email': order.customer.email,
            'amount': amount_kobo,
            'currency': 'NGN',
            'reference': f"PAY_{order.order_id}_{order.id}",
            'callback_url': callback_url,
            'metadata': {
                'order_id': order.order_id,
                'customer_id': order.customer.id,
                'entrepreneur_id': order.entrepreneur.id,
                'order_total': str(order.total_amount)
            }
        }
        
        try:
            response = self._make_request('POST', '/transaction/initialize', data)
            
            if response.get('status'):
                return {
                    'success': True,
                    'authorization_url': response['data']['authorization_url'],
                    'access_code': response['data']['access_code'],
                    'reference': response['data']['reference']
                }
            else:
                return {
                    'success': False,
                    'message': response.get('message', 'Payment initialization failed')
                }
        
        except Exception as e:
            return {
                'success': False,
                'message': str(e)
            }
    
    def verify_payment(self, reference):
        """Verify payment transaction with Paystack"""
        try:
            response = self._make_request('GET', f'/transaction/verify/{reference}')
            
            if response.get('status'):
                data = response['data']
                return {
                    'success': True,
                    'status': data['status'],
                    'amount': Decimal(str(data['amount'])) / 100,  # Convert from kobo
                    'currency': data['currency'],
                    'reference': data['reference'],
                    'paid_at': data['paid_at'],
                    'metadata': data.get('metadata', {}),
                    'gateway_response': data.get('gateway_response', '')
                }
            else:
                return {
                    'success': False,
                    'message': response.get('message', 'Payment verification failed')
                }
        
        except Exception as e:
            return {
                'success': False,
                'message': str(e)
            }
    
    def verify_webhook_signature(self, payload, signature):
        """Verify that webhook is from Paystack"""
        computed_signature = hmac.new(
            self.secret_key.encode('utf-8'),
            payload,
            hashlib.sha512
        ).hexdigest()
        
        return hmac.compare_digest(computed_signature, signature)

class FlutterwaveService:
    def __init__(self):
        self.secret_key = settings.FLUTTERWAVE_SECRET_KEY
        self.public_key = settings.FLUTTERWAVE_PUBLIC_KEY
        self.base_url = "https://api.flutterwave.com/v3"
    
    def _make_request(self, method, endpoint, data=None):
        """Make authenticated request to Flutterwave API"""
        headers = {
            'Authorization': f'Bearer {self.secret_key}',
            'Content-Type': 'application/json'
        }
        
        url = f"{self.base_url}{endpoint}"
        
        try:
            if method == 'POST':
                response = requests.post(url, headers=headers, json=data)
            elif method == 'GET':
                response = requests.get(url, headers=headers, params=data)
            
            response.raise_for_status()
            return response.json()
        
        except requests.exceptions.RequestException as e:
            logger.error(f"Flutterwave API request failed: {str(e)}")
            raise Exception(f"Payment service error: {str(e)}")
    
    def initialize_payment(self, order, callback_url):
        """Initialize payment with Flutterwave"""
        data = {
            'tx_ref': f"FLW_{order.order_id}_{order.id}",
            'amount': str(order.total_amount),
            'currency': 'NGN',
            'redirect_url': callback_url,
            'customer': {
                'email': order.customer.email,
                'phonenumber': order.customer.phone_number,
                'name': f"{order.customer.first_name} {order.customer.last_name}"
            },
            'customizations': {
                'title': 'Payjaro Order Payment',
                'description': f'Payment for order {order.order_id}',
                'logo': 'https://your-logo-url.com/logo.png'
            },
            'meta': {
                'order_id': order.order_id,
                'customer_id': order.customer.id,
                'entrepreneur_id': order.entrepreneur.id
            }
        }
        
        try:
            response = self._make_request('POST', '/payments', data)
            
            if response.get('status') == 'success':
                return {
                    'success': True,
                    'payment_link': response['data']['link'],
                    'reference': data['tx_ref']
                }
            else:
                return {
                    'success': False,
                    'message': response.get('message', 'Payment initialization failed')
                }
        
        except Exception as e:
            return {
                'success': False,
                'message': str(e)
            }
    
    def verify_payment(self, transaction_id):
        """Verify payment with Flutterwave"""
        try:
            response = self._make_request('GET', f'/transactions/{transaction_id}/verify')
            
            if response.get('status') == 'success':
                data = response['data']
                return {
                    'success': True,
                    'status': data['status'],
                    'amount': Decimal(str(data['amount'])),
                    'currency': data['currency'],
                    'reference': data['tx_ref'],
                    'flw_ref': data['flw_ref'],
                    'metadata': data.get('meta', {})
                }
            else:
                return {
                    'success': False,
                    'message': response.get('message', 'Payment verification failed')
                }
        
        except Exception as e:
            return {
                'success': False,
                'message': str(e)
            }
File to Create: payments/api.py
pythonfrom rest_framework import viewsets, status, permissions
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
        """Initialize payment for an order"""
        order_id = request.data.get('order_id')
        payment_provider = request.data.get('provider', 'paystack')  # Default to Paystack
        callback_url = request.data.get('callback_url', f"{settings.FRONTEND_URL}/payment/callback")
        
        if not order_id:
            return Response({
                'error': 'Order ID is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            order = Order.objects.get(order_id=order_id, customer=request.user)
            
            if order.payment_status == 'paid':
                return Response({
                    'error': 'Order has already been paid'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Initialize payment based on provider
            if payment_provider == 'paystack':
                service = PaystackService()
                result = service.initialize_payment(order, callback_url)
            elif payment_provider == 'flutterwave':
                service = FlutterwaveService()
                result = service.initialize_payment(order, callback_url)
            else:
                return Response({
                    'error': 'Unsupported payment provider'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            if result['success']:
                # Create transaction record
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
                return Response({
                    'error': result['message']
                }, status=status.HTTP_400_BAD_REQUEST)
        
        except Order.DoesNotExist:
            return Response({
                'error': 'Order not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        except Exception as e:
            logger.error(f"Payment initiation error: {str(e)}")
            return Response({
                'error': 'Payment initialization failed'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@method_decorator(csrf_exempt, name='dispatch')
class PaystackWebhookView(APIView):
    permission_classes = [AllowAny]
    
    def post(self, request):
        """Handle Paystack webhook notifications"""
        payload = request.body
        signature = request.META.get('HTTP_X_PAYSTACK_SIGNATURE', '')
        
        try:
            # Verify webhook signature
            service = PaystackService()
            if not service.verify_webhook_signature(payload, signature):
                logger.warning("Invalid Paystack webhook signature")
                return Response({'error': 'Invalid signature'}, status=status.HTTP_400_BAD_REQUEST)
            
            # Parse webhook data
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
        """Process successful payment"""
        reference = payment_data.get('reference')
        
        try:
            # Get transaction and order
            transaction_obj = Transaction.objects.get(transaction_id=reference)
            order = transaction_obj.order
            
            # Update transaction status
            transaction_obj.status = 'completed'
            transaction_obj.metadata.update({
                'gateway_response': payment_data.get('gateway_response', ''),
                'paid_at': payment_data.get('paid_at')
            })
            transaction_obj.save()
            
            # Update order status
            order.payment_status = 'paid'
            order.payment_method = 'paystack'
            order.status = 'paid'
            order.save()
            
            # Update earnings to paid status
            earnings = Earnings.objects.filter(order=order, status='pending')
            for earning in earnings:
                earning.status = 'paid'
                earning.payout_date = transaction_obj.created_at
                earning.save()
            
            # Update entrepreneur wallet
            entrepreneur = order.entrepreneur
            wallet, created = Wallet.objects.get_or_create(user=entrepreneur.user)
            
            total_earnings = sum(e.amount for e in earnings)
            wallet.balance += total_earnings
            wallet.total_earned += total_earnings
            wallet.save()
            
            # Update entrepreneur profile totals
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
        """Process failed payment"""
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
        """Get earnings summary for entrepreneur"""
        if request.user.user_type != 'entrepreneur':
            return Response({
                'error': 'Only entrepreneurs can access earnings'
            }, status=status.HTTP_403_FORBIDDEN)
        
        entrepreneur = get_object_or_404(EntrepreneurProfile, user=request.user)
        
        # Get wallet
        wallet, created = Wallet.objects.get_or_create(user=request.user)
        
        # Calculate earnings breakdown
        total_markup = Earnings.objects.filter(
            entrepreneur=entrepreneur, 
            earning_type='markup', 
            status='paid'
        ).aggregate(total=models.Sum('amount'))['total'] or 0
        
        total_commission = Earnings.objects.filter(
            entrepreneur=entrepreneur, 
            earning_type='commission', 
            status='paid'
        ).aggregate(total=models.Sum('amount'))['total'] or 0
        
        pending_earnings = Earnings.objects.filter(
            entrepreneur=entrepreneur, 
            status='pending'
        ).aggregate(total=models.Sum('amount'))['total'] or 0
        
        return Response({
            'available_balance': wallet.balance,
            'pending_balance': wallet.pending_balance,
            'total_earned': wallet.total_earned,
            'total_withdrawn': wallet.total_withdrawn,
            'total_markup': total_markup,
            'total_commission': total_commission,
            'pending_earnings': pending_earnings,
            'total_sales': entrepreneur.total_sales,
            'performance_tier': entrepreneur.performance_tier
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
        """Create withdrawal request"""
        if request.user.user_type != 'entrepreneur':
            return Response({
                'error': 'Only entrepreneurs can request withdrawals'
            }, status=status.HTTP_403_FORBIDDEN)
        
        entrepreneur = get_object_or_404(EntrepreneurProfile, user=request.user)
        wallet, created = Wallet.objects.get_or_create(user=request.user)
        
        amount = request.data.get('amount')
        withdrawal_method = request.data.get('withdrawal_method')
        destination_details = request.data.get('destination_details', {})
        
        # Validate amount
        try:
            amount = Decimal(str(amount))
        except (ValueError, TypeError):
            return Response({
                'error': 'Invalid amount'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        if amount <= 0:
            return Response({
                'error': 'Amount must be greater than zero'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        if amount > wallet.balance:
            return Response({
                'error': 'Insufficient balance'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Minimum withdrawal check
        if amount < Decimal('1000.00'):
            return Response({
                'error': 'Minimum withdrawal amount is ₦1,000'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Calculate processing fee (2% or minimum ₦50)
        processing_fee = max(amount * Decimal('0.02'), Decimal('50.00'))
        net_amount = amount - processing_fee
        
        # Create withdrawal request
        withdrawal = WithdrawalRequest.objects.create(
            entrepreneur=entrepreneur,
            amount=amount,
            withdrawal_method=withdrawal_method,
            destination_details=destination_details,
            status='pending',
            processing_fee=processing_fee,
            reference_id=f"WD{entrepreneur.id}{len(WithdrawalRequest.objects.filter(entrepreneur=entrepreneur)) + 1:04d}"
        )
        
        # Update wallet
        wallet.balance -= amount
        wallet.pending_balance += amount
        wallet.save()
        
        serializer = WithdrawalRequestSerializer(withdrawal)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
File to Create: payments/serializers.py
pythonfrom rest_framework import serializers
from .models import PaymentMethod, Transaction, Earnings, WithdrawalRequest, Wallet
from orders.serializers import OrderSerializer

class PaymentMethodSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentMethod
        fields = [
            'id', 'method_type', 'provider', 'details', 
            'is_default', 'is_active'
        ]
        read_only_fields = ['id']
    
    def validate_details(self, value):
        """Validate payment method details based on type"""
        method_type = self.initial_data.get('method_type')
        
        if method_type == 'bank_transfer':
            required_fields = ['account_number', 'bank_code', 'account_name']
            for field in required_fields:
                if field not in value:
                    raise serializers.ValidationError(f"Bank transfer requires {field}")
        
        elif method_type == 'crypto':
            required_fields = ['wallet_address', 'crypto_type']
            for field in required_fields:
                if field not in value:
                    raise serializers.ValidationError(f"Crypto payment requires {field}")
        
        return value

class TransactionSerializer(serializers.ModelSerializer):
    order = OrderSerializer(read_only=True)
    
    class Meta:
        model = Transaction
        fields = [
            'id', 'transaction_id', 'order', 'transaction_type',
            'amount', 'currency', 'status', 'provider_reference',
            'metadata', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']

class EarningsSerializer(serializers.ModelSerializer):
    order = OrderSerializer(read_only=True)
    
    class Meta:
        model = Earnings
        fields = [
            'id', 'order', 'earning_type', 'amount', 'status',
            'payout_date', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']

class WithdrawalRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = WithdrawalRequest
        fields = [
            'id', 'amount', 'withdrawal_method', 'destination_details',
            'status', 'processing_fee', 'reference_id', 'processed_at',
            'created_at'
        ]
        read_only_fields = [
            'id', 'status', 'processing_fee', 'reference_id', 
            'processed_at', 'created_at'
        ]

class WalletSerializer(serializers.ModelSerializer):
    class Meta:
        model = Wallet
        fields = [
            'id', 'balance', 'pending_balance', 'total_earned',
            'total_withdrawn', 'currency', 'updated_at'
        ]
        read_only_fields = ['id', 'updated_at']
File to Create: payments/urls.py
pythonfrom django.urls import path, include
from rest_framework.routers import DefaultRouter
from .api import (
    PaymentMethodViewSet, PaymentInitiationView, PaystackWebhookView,
    EarningsViewSet, WithdrawalViewSet
)

router = DefaultRouter()
router.register(r'payment-methods', PaymentMethodViewSet, basename='payment-method')
router.register(r'earnings', EarningsViewSet, basename='earnings')
router.register(r'withdrawals', WithdrawalViewSet, basename='withdrawal')

urlpatterns = [
    path('', include(router.urls)),
    path('initialize/', PaymentInitiationView.as_view(), name='payment-initialize'),
    path('webhooks/paystack/', PaystackWebhookView.as_view(), name='paystack-webhook'),
]
Update: payjaro_project/settings.py
python# ADD THESE PAYMENT SETTINGS
import os

# Payment Gateway Settings
PAYSTACK_PUBLIC_KEY = os.getenv('PAYSTACK_PUBLIC_KEY', 'pk_test_your_test_key')
PAYSTACK_SECRET_KEY = os.getenv('PAYSTACK_SECRET_KEY', 'sk_test_your_test_key')
FLUTTERWAVE_PUBLIC_KEY = os.getenv('FLUTTERWAVE_PUBLIC_KEY', 'FLWPUBK_TEST-your_test_key')
FLUTTERWAVE_SECRET_KEY = os.getenv('FLUTTERWAVE_SECRET_KEY', 'FLWSECK_TEST-your_test_key')

# Frontend URL for callbacks
FRONTEND_URL = os.getenv('FRONTEND_URL', 'http://localhost:3000')

# Logging configuration
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'file': {
            'level': 'INFO',
            'class': 'logging.FileHandler',
            'filename': 'payments.log',
        },
        'console': {
            'level': 'DEBUG',
            'class': 'logging.StreamHandler',
        },
    },
    'loggers': {
        'payments': {
            'handlers': ['file', 'console'],
            'level': 'INFO',
            'propagate': True,
        },
    },
}
Update: payjaro_project/urls.py
python# ADD THIS LINE to the urlpatterns list
path('api/payments/', include('payments.urls')),
VALIDATION COMMANDS:
bash# Install dependencies
pip install paystack-python requests cryptography

# Run migrations
python manage.py makemigrations payments
python manage.py migrate

# Test payment APIs
python manage.py test payments.tests

# Start server and test endpoints
python manage.py runserver

# Test payment initialization:
# POST http://localhost:8000/api/payments/initialize/
# Body: {"order_id": "PAY20250718ABC123", "provider": "paystack"}
CRITICAL CHECKPOINTS:

 Payment initialization returns valid payment URL
 Webhook signature verification works
 Successful payments update order and earnings
 Failed payments are handled correctly
 Earnings calculations are accurate
 Withdrawal system enforces proper validations


PHASE 3: FILE STORAGE AND MEDIA MANAGEMENT
TASK 3.1: Implement AWS S3 Integration for File Storage
Install Dependencies:
bashpip install boto3 django-storages pillow
pip freeze > requirements.txt
Update: payjaro_project/settings.py
python# ADD AWS S3 CONFIGURATION
import os

# AWS S3 Settings
AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = os.getenv('AWS_SECRET_ACCESS_KEY')
AWS_STORAGE_BUCKET_NAME = os.getenv('AWS_STORAGE_BUCKET_NAME', 'payjaro-files')
AWS_S3_REGION_NAME = os.getenv('AWS_S3_REGION_NAME', 'us-east-1')
AWS_S3_CUSTOM_DOMAIN = f'{AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com'
AWS_DEFAULT_ACL = 'public-read'
AWS_S3_OBJECT_PARAMETERS = {
    'CacheControl': 'max-age=86400',
}
AWS_LOCATION = 'static'
AWS_MEDIA_LOCATION = 'media'

# Storage backends
if not DEBUG:
    # Production storage
    DEFAULT_FILE_STORAGE = 'storages.backends.s3boto3.S3Boto3Storage'
    STATICFILES_STORAGE = 'storages.backends.s3boto3.S3StaticStorage'
    
    # URLs
    STATIC_URL = f'https://{AWS_S3_CUSTOM_DOMAIN}/{AWS_LOCATION}/'
    MEDIA_URL = f'https://{AWS_S3_CUSTOM_DOMAIN}/{AWS_MEDIA_LOCATION}/'
else:
    # Development storage
    STATIC_URL = '/static/'
    MEDIA_URL = '/media/'
    MEDIA_ROOT = BASE_DIR / 'media'

# File upload settings
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # 10MB
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # 10MB

# Add storages to INSTALLED_APPS
INSTALLED_APPS = [
    # ... existing apps
    'storages',
]
File to Create: core/file_utils.py
pythonimport os
import uuid
from PIL import Image
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

def generate_unique_filename(filename, prefix=''):
    """Generate unique filename with UUID"""
    ext = os.path.splitext(filename)[1]
    unique_filename = f"{prefix}{uuid.uuid4().hex}{ext}"
    return unique_filename

def validate_image_file(file):
    """Validate uploaded image file"""
    # Check file size (max 5MB)
    if file.size > 5 * 1024 * 1024:
        raise ValueError("Image file too large. Maximum size is 5MB.")
    
    # Check file type
    allowed_types = ['image/jpeg', 'image/png', 'image/webp']
    if file.content_type not in allowed_types:
        raise ValueError("Invalid file type. Only JPEG, PNG, and WebP are allowed.")
    
    try:
        # Validate image can be opened
        image = Image.open(file)
        image.verify()
        file.seek(0)  # Reset file pointer
        return True
    except Exception:
        raise ValueError("Invalid image file.")

def optimize_image(image_file, max_width=1200, max_height=1200, quality=85):
    """Optimize image for web use"""
    try:
        image = Image.open(image_file)
        
        # Convert RGBA to RGB if needed
        if image.mode in ('RGBA', 'LA', 'P'):
            background = Image.new('RGB', image.size, (255, 255, 255))
            if image.mode == 'P':
                image = image.convert('RGBA')
            background.paste(image, mask=image.split()[-1] if image.mode == 'RGBA' else None)
            image = background
        
        # Resize if needed
        if image.width > max_width or image.height > max_height:
            image.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)
        
        # Save optimized image
        from io import BytesIO
        output = BytesIO()
        image.save(output, format='JPEG', quality=quality, optimize=True)
        output.seek(0)
        
        return ContentFile(output.read())
    
    except Exception as e:
        logger.error(f"Image optimization failed: {str(e)}")
        raise ValueError("Image optimization failed.")

class FileUploadService:
    @staticmethod
    def upload_product_image(product, image_file, is_primary=False):
        """Upload and optimize product image"""
        try:
            # Validate image
            validate_image_file(image_file)
            
            # Generate filename
            filename = generate_unique_filename(
                image_file.name, 
                f"products/{product.id}/"
            )
            
            # Optimize image
            optimized_image = optimize_image(image_file)
            
            # Save to storage
            path = default_storage.save(filename, optimized_image)
            url = default_storage.url(path)
            
            # Create ProductImage record
            from products.models import ProductImage
            product_image = ProductImage.objects.create(
                product=product,
                image=path,
                alt_text=f"{product.name} image",
                is_primary=is_primary
            )
            
            return {
                'success': True,
                'image_id': product_image.id,
                'url': url,
                'path': path
            }
        
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    @staticmethod
    def upload_profile_image(entrepreneur, image_file, image_type='profile'):
        """Upload entrepreneur profile or banner image"""
        try:
            # Validate image
            validate_image_file(image_file)
            
            # Generate filename
            filename = generate_unique_filename(
                image_file.name,
                f"entrepreneurs/{entrepreneur.id}/{image_type}/"
            )
            
            # Optimize image
            if image_type == 'banner':
                optimized_image = optimize_image(image_file, max_width=1200, max_height=400)
            else:
                optimized_image = optimize_image(image_file, max_width=400, max_height=400)
            
            # Save to storage
            path = default_storage.save(filename, optimized_image)
            url = default_storage.url(path)
            
            # Update entrepreneur profile
            if image_type == 'profile':
                entrepreneur.profile_image = path
            elif image_type == 'banner':
                entrepreneur.banner_image = path
            entrepreneur.save()
            
            return {
                'success': True,
                'url': url,
                'path': path
            }
        
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    @staticmethod
    def delete_file(file_path):
        """Delete file from storage"""
        try:
            if default_storage.exists(file_path):
                default_storage.delete(file_path)
                return True
            return False
        except Exception as e:
            logger.error(f"File deletion failed: {str(e)}")
            return False
File to Create: products/file_api.py
pythonfrom rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from rest_framework.parsers import MultiPartParser, FormParser
from django.shortcuts import get_object_or_404
from .models import Product, ProductImage
from suppliers.models import SupplierProfile
from core.file_utils import FileUploadService

class ProductImageUploadView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    
    def post(self, request, product_id):
        """Upload product image"""
        # Verify user is supplier who owns the product
        if request.user.user_type != 'supplier':
            return Response({
                'error': 'Only suppliers can upload product images'
            }, status=status.HTTP_403_FORBIDDEN)
        
        try:
            supplier = SupplierProfile.objects.get(user=request.user)
            product = Product.objects.get(id=product_id, supplier=supplier)
        except (SupplierProfile.DoesNotExist, Product.DoesNotExist):
            return Response({
                'error': 'Product not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        image_file = request.FILES.get('image')
        if not image_file:
            return Response({
                'error': 'No image file provided'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        is_primary = request.data.get('is_primary', False)
        
        # If setting as primary, unset other primary images
        if is_primary:
            ProductImage.objects.filter(product=product, is_primary=True).update(is_primary=False)
        
        result = FileUploadService.upload_product_image(product, image_file, is_primary)
        
        if result['success']:
            return Response({
                'success': True,
                'image_id': result['image_id'],
                'url': result['url'],
                'message': 'Image uploaded successfully'
            }, status=status.HTTP_201_CREATED)
        else:
            return Response({
                'error': result['error']
            }, status=status.HTTP_400_BAD_REQUEST)
    
    def delete(self, request, product_id, image_id):
        """Delete product image"""
        if request.user.user_type != 'supplier':
            return Response({
                'error': 'Only suppliers can delete product images'
            }, status=status.HTTP_403_FORBIDDEN)
        
        try:
            supplier = SupplierProfile.objects.get(user=request.user)
            product = Product.objects.get(id=product_id, supplier=supplier)
            image = ProductImage.objects.get(id=image_id, product=product)
        except (SupplierProfile.DoesNotExist, Product.DoesNotExist, ProductImage.DoesNotExist):
            return Response({
                'error': 'Image not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Delete file from storage
        FileUploadService.delete_file(image.image.name)
        
        # Delete database record
        image.delete()
        
        return Response({
            'message': 'Image deleted successfully'
        }, status=status.HTTP_200_OK)

class BulkProductImageUploadView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    
    def post(self, request, product_id):
        """Upload multiple product images"""
        if request.user.user_type != 'supplier':
            return Response({
                'error': 'Only suppliers can upload product images'
            }, status=status.HTTP_403_FORBIDDEN)
        
        try:
            supplier = SupplierProfile.objects.get(user=request.user)
            product = Product.objects.get(id=product_id, supplier=supplier)
        except (SupplierProfile.DoesNotExist, Product.DoesNotExist):
            return Response({
                'error': 'Product not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        images = request.FILES.getlist('images')
        if not images:
            return Response({
                'error': 'No image files provided'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        results = []
        primary_set = False
        
        for i, image_file in enumerate(images):
            is_primary = i == 0 and not primary_set  # First image is primary if none set
            result = FileUploadService.upload_product_image(product, image_file, is_primary)
            
            if result['success']:
                primary_set = True
                results.append({
                    'success': True,
                    'image_id': result['image_id'],
                    'url': result['url']
                })
            else:
                results.append({
                    'success': False,
                    'error': result['error']
                })
        
        successful_uploads = [r for r in results if r['success']]
        failed_uploads = [r for r in results if not r['success']]
        
        return Response({
            'message': f'{len(successful_uploads)} images uploaded successfully',
            'successful_uploads': successful_uploads,
            'failed_uploads': failed_uploads
        }, status=status.HTTP_201_CREATED if successful_uploads else status.HTTP_400_BAD_REQUEST)
File to Create: entrepreneurs/file_api.py
pythonfrom rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from rest_framework.parsers import MultiPartParser, FormParser
from django.shortcuts import get_object_or_404
from .models import EntrepreneurProfile
from core.file_utils import FileUploadService

class EntrepreneurImageUploadView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    
    def post(self, request, image_type):
        """Upload entrepreneur profile or banner image"""
        if request.user.user_type != 'entrepreneur':
            return Response({
                'error': 'Only entrepreneurs can upload profile images'
            }, status=status.HTTP_403_FORBIDDEN)
        
        if image_type not in ['profile', 'banner']:
            return Response({
                'error': 'Invalid image type. Use "profile" or "banner"'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            entrepreneur = EntrepreneurProfile.objects.get(user=request.user)
        except EntrepreneurProfile.DoesNotExist:
            return Response({
                'error': 'Entrepreneur profile not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        image_file = request.FILES.get('image')
        if not image_file:
            return Response({
                'error': 'No image file provided'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Delete old image if exists
        old_image_path = None
        if image_type == 'profile' and entrepreneur.profile_image:
            old_image_path = entrepreneur.profile_image.name
        elif image_type == 'banner' and entrepreneur.banner_image:
            old_image_path = entrepreneur.banner_image.name
        
        result = FileUploadService.upload_profile_image(entrepreneur, image_file, image_type)
        
        if result['success']:
            # Delete old image
            if old_image_path:
                FileUploadService.delete_file(old_image_path)
            
            return Response({
                'success': True,
                'url': result['url'],
                'message': f'{image_type.title()} image uploaded successfully'
            }, status=status.HTTP_200_OK)
        else:
            return Response({
                'error': result['error']
            }, status=status.HTTP_400_BAD_REQUEST)
Update URL files to include image upload endpoints:
Add to: products/urls.py
pythonfrom .file_api import ProductImageUploadView, BulkProductImageUploadView

# ADD THESE PATTERNS
path('products/<int:product_id>/images/', ProductImageUploadView.as_view(), name='product-image-upload'),
path('products/<int:product_id>/images/<int:image_id>/', ProductImageUploadView.as_view(), name='product-image-delete'),
path('products/<int:product_id>/images/bulk/', BulkProductImageUploadView.as_view(), name='product-images-bulk-upload'),
Add to: entrepreneurs/urls.py
pythonfrom .file_api import EntrepreneurImageUploadView

# ADD THIS PATTERN
path('images/<str:image_type>/', EntrepreneurImageUploadView.as_view(), name='entrepreneur-image-upload'),
VALIDATION COMMANDS:
bash# Install dependencies
pip install boto3 django-storages pillow

# Test image uploads
python manage.py test products.tests.TestImageUpload
python manage.py test entrepreneurs.tests.TestImageUpload

# Collect static files
python manage.py collectstatic --noinput

# Test endpoints
# POST http://localhost:8000/api/products/products/1/images/
# POST http://localhost:8000/api/entrepreneurs/images/profile/
CRITICAL CHECKPOINTS:

 Image uploads work to S3 (or local in development)
 Images are properly optimized and resized
 File validation prevents invalid uploads
 Old images are cleaned up when replaced
 URLs are accessible and properly formatted


PHASE 4: SUPPLIER MANAGEMENT SYSTEM
TASK 4.1: Complete Supplier API Implementation
File to Create: suppliers/api.py
pythonfrom rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.db import transaction
from .models import SupplierProfile
from .serializers import SupplierProfileSerializer, SupplierRegistrationSerializer
from products.models import Product
from products.serializers import ProductSerializer
from orders.models import Order
from orders.serializers import OrderSerializer

class SupplierProfileViewSet(viewsets.ModelViewSet):
    serializer_class = SupplierProfileSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        if self.request.user.user_type == 'supplier':
            return SupplierProfile.objects.filter(user=self.request.user)
        elif self.request.user.user_type == 'admin':
            return SupplierProfile.objects.all()
        return Supplier

        class EntrepreneurAnalyticsView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        """Get analytics dashboard for authenticated entrepreneur"""
        if request.user.user_type != 'entrepreneur':
            return Response({
                'error': 'Only entrepreneurs can access analytics'
            }, status=status.HTTP_403_FORBIDDEN)
        
        try:
            entrepreneur = EntrepreneurProfile.objects.get(user=request.user)
        except EntrepreneurProfile.DoesNotExist:
            return Response({
                'error': 'Entrepreneur profile not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Get date range from query params
        days = int(request.GET.get('days', 30))
        start_date = timezone.now() - timezone.timedelta(days=days)
        end_date = timezone.now()
        
        analytics = AnalyticsService.get_entrepreneur_analytics(
            entrepreneur, start_date, end_date
        )
        
        return Response(analytics)

@api_view(['POST'])
@permission_classes([AllowAny])
def track_click(request):
    """Track click events for sharing links"""
    link_type = request.data.get('link_type')  # 'product_share', 'storefront_share'
    entrepreneur_id = request.data.get('entrepreneur_id')
    product_id = request.data.get('product_id')
    platform = request.data.get('platform')  # 'whatsapp', 'instagram', etc.
    
    metadata = {
        'platform': platform,
        'link_type': link_type,
        'visitor_ip': request.META.get('REMOTE_ADDR'),
        'user_agent': request.META.get('HTTP_USER_AGENT'),
        'referrer': request.META.get('HTTP_REFERER')
    }
    
    try:
        entrepreneur = EntrepreneurProfile.objects.get(id=entrepreneur_id) if entrepreneur_id else None
        
        product = None
        if product_id:
            from products.models import Product
            product = Product.objects.get(id=product_id)
        
        AnalyticsService.track_event(
            event_type='link_click',
            entrepreneur=entrepreneur,
            product=product,
            metadata=metadata
        )
        
        return Response({'status': 'success'})
    
    except Exception as e:
        return Response({
            'error': 'Failed to track click'
        }, status=status.HTTP_400_BAD_REQUEST)
```

**File to Create:** `analytics/urls.py`

```python
from django.urls import path
from .api import TrackEventView, EntrepreneurAnalyticsView, track_click

urlpatterns = [
    path('track/', TrackEventView.as_view(), name='track-event'),
    path('entrepreneur/', EntrepreneurAnalyticsView.as_view(), name='entrepreneur-analytics'),
    path('track-click/', track_click, name='track-click'),
]
```

**Update:** `payjaro_project/settings.py`

```python
# ADD public app to INSTALLED_APPS
INSTALLED_APPS = [
    # ... existing apps
    'public',
]
```

**Update:** `payjaro_project/urls.py`

```python
# ADD THESE LINES to the urlpatterns list
path('api/analytics/', include('analytics.urls')),
path('', include('public.urls')),  # Public storefront URLs (should be last)
```

---

## **PHASE 6: PRODUCTION DEPLOYMENT PREPARATION**

### **TASK 6.1: Environment Configuration & Settings**

**File to Create:** `payjaro_project/settings/base.py`

```python
import os
from pathlib import Path

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.getenv('SECRET_KEY', 'django-insecure-#tc0_1dhmidn5xgm%^*&+t_(&u&284%o7+!u^hd47rj$qicg_-')

# Application definition
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    'rest_framework',
    'rest_framework_simplejwt',
    'drf_yasg',
    'storages',
    'corsheaders',
]

LOCAL_APPS = [
    'accounts',
    'users',
    'entrepreneurs',
    'suppliers',
    'products',
    'orders',
    'payments',
    'logistics',
    'social',
    'analytics',
    'public',
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "payjaro_project.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "payjaro_project.wsgi.application"

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

# Internationalization
LANGUAGE_CODE = "en-us"
TIME_ZONE = "Africa/Lagos"
USE_I18N = True
USE_TZ = True

# Default primary key field type
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Custom User Model
AUTH_USER_MODEL = "users.User"

# REST Framework Configuration
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_FILTER_BACKENDS': [
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
}

# JWT Configuration
from datetime import timedelta
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=60),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
}

# Payment Gateway Settings
PAYSTACK_PUBLIC_KEY = os.getenv('PAYSTACK_PUBLIC_KEY')
PAYSTACK_SECRET_KEY = os.getenv('PAYSTACK_SECRET_KEY')
FLUTTERWAVE_PUBLIC_KEY = os.getenv('FLUTTERWAVE_PUBLIC_KEY')
FLUTTERWAVE_SECRET_KEY = os.getenv('FLUTTERWAVE_SECRET_KEY')

# File Upload Settings
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # 10MB
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # 10MB

# Email Configuration
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = os.getenv('EMAIL_HOST', 'smtp.sendgrid.net')
EMAIL_PORT = int(os.getenv('EMAIL_PORT', 587))
EMAIL_USE_TLS = True
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD')
DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', 'noreply@payjaro.com')

# SMS Configuration (Twilio)
TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
TWILIO_PHONE_NUMBER = os.getenv('TWILIO_PHONE_NUMBER')

# Frontend URL
FRONTEND_URL = os.getenv('FRONTEND_URL', 'http://localhost:3000')

# Security Settings
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'

# Logging Configuration
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'file': {
            'level': 'INFO',
            'class': 'logging.FileHandler',
            'filename': 'logs/payjaro.log',
            'formatter': 'verbose',
        },
        'console': {
            'level': 'DEBUG',
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
    },
    'root': {
        'handlers': ['console', 'file'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': False,
        },
        'payments': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}
```

**File to Create:** `payjaro_project/settings/development.py`

```python
from .base import *

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = ['localhost', '127.0.0.1', '0.0.0.0']

# Database
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

# Static files (CSS, JavaScript, Images)
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [
    BASE_DIR / "static",
]

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# CORS settings for development
CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOW_CREDENTIALS = True

# Cache (Redis for development)
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
    }
}

# Email backend for development
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
```

**File to Create:** `payjaro_project/settings/production.py`

```python
from .base import *
import dj_database_url

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = False

ALLOWED_HOSTS = [
    'api.payjaro.com',
    'payjaro.com',
    '*.payjaro.com',
    os.getenv('ALLOWED_HOST', 'localhost')
]

# Database
DATABASES = {
    'default': dj_database_url.config(
        default=os.getenv('DATABASE_URL', 'postgresql://user:password@localhost/payjaro')
    )
}

# AWS S3 Settings for Production
AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = os.getenv('AWS_SECRET_ACCESS_KEY')
AWS_STORAGE_BUCKET_NAME = os.getenv('AWS_STORAGE_BUCKET_NAME')
AWS_S3_REGION_NAME = os.getenv('AWS_S3_REGION_NAME', 'us-east-1')
AWS_S3_CUSTOM_DOMAIN = f'{AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com'
AWS_DEFAULT_ACL = 'public-read'
AWS_S3_OBJECT_PARAMETERS = {
    'CacheControl': 'max-age=86400',
}
AWS_LOCATION = 'static'
AWS_MEDIA_LOCATION = 'media'

# Storage backends
DEFAULT_FILE_STORAGE = 'storages.backends.s3boto3.S3Boto3Storage'
STATICFILES_STORAGE = 'storages.backends.s3boto3.S3StaticStorage'

# URLs
STATIC_URL = f'https://{AWS_S3_CUSTOM_DOMAIN}/{AWS_LOCATION}/'
MEDIA_URL = f'https://{AWS_S3_CUSTOM_DOMAIN}/{AWS_MEDIA_LOCATION}/'

# Cache (Redis for production)
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': REDIS_URL,
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
        },
        'KEY_PREFIX': 'payjaro',
    }
}

# Session storage
SESSION_ENGINE = 'django.contrib.sessions.backends.cache'
SESSION_CACHE_ALIAS = 'default'

# Security Settings for Production
SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_HSTS_SECONDS = 31536000  # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True
X_FRAME_OPTIONS = 'DENY'

# CSRF Protection
CSRF_TRUSTED_ORIGINS = [
    'https://payjaro.com',
    'https://api.payjaro.com',
    'https://www.payjaro.com'
]

# CORS settings for production
CORS_ALLOWED_ORIGINS = [
    "https://payjaro.com",
    "https://www.payjaro.com",
    "https://app.payjaro.com"
]
CORS_ALLOW_CREDENTIALS = True

# Logging for production
LOGGING['handlers']['file']['filename'] = '/var/log/payjaro/payjaro.log'
```

**File to Create:** `payjaro_project/settings/__init__.py`

```python
import os

environment = os.getenv('DJANGO_ENVIRONMENT', 'development')

if environment == 'production':
    from .production import *
elif environment == 'staging':
    from .production import *
    DEBUG = True
else:
    from .development import *
```

**File to Create:** `.env.example`

```bash
# Django Settings
SECRET_KEY=your-secret-key-here
DJANGO_ENVIRONMENT=development
DEBUG=True
ALLOWED_HOST=localhost

# Database (Production)
DATABASE_URL=postgresql://user:password@localhost:5432/payjaro

# Payment Gateways
PAYSTACK_PUBLIC_KEY=pk_test_your_public_key
PAYSTACK_SECRET_KEY=sk_test_your_secret_key
FLUTTERWAVE_PUBLIC_KEY=FLWPUBK_TEST-your_public_key
FLUTTERWAVE_SECRET_KEY=FLWSECK_TEST-your_secret_key

# AWS S3 Storage
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
AWS_STORAGE_BUCKET_NAME=payjaro-files
AWS_S3_REGION_NAME=us-east-1

# Email Configuration
EMAIL_HOST_USER=your_sendgrid_username
EMAIL_HOST_PASSWORD=your_sendgrid_password
DEFAULT_FROM_EMAIL=noreply@payjaro.com

# SMS Configuration (Twilio)
TWILIO_ACCOUNT_SID=your_twilio_sid
TWILIO_AUTH_TOKEN=your_twilio_token
TWILIO_PHONE_NUMBER=+1234567890

# Frontend URL
FRONTEND_URL=https://payjaro.com

# Redis (Production)
REDIS_URL=redis://localhost:6379/0
```

### **TASK 6.2: Docker Production Configuration**

**Update:** `dockerfile`

```dockerfile
# Multi-stage build for production
FROM python:3.11-slim as builder

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV PIP_DISABLE_PIP_VERSION_CHECK 1

# Set work directory
WORKDIR /code

# Install system dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        postgresql-client \
        gcc \
        python3-dev \
        musl-dev \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Production stage
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV DJANGO_ENVIRONMENT=production

# Create app user
RUN groupadd -r app && useradd -r -g app app

# Set work directory
WORKDIR /code

# Install runtime dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy Python packages from builder stage
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy project
COPY . .

# Create logs directory
RUN mkdir -p /var/log/payjaro && chown app:app /var/log/payjaro

# Change ownership of the app directory
RUN chown -R app:app /code

# Switch to app user
USER app

# Collect static files
RUN python manage.py collectstatic --noinput --settings=payjaro_project.settings.production

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD python manage.py check --deploy --settings=payjaro_project.settings.production

# Run gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "120", "payjaro_project.wsgi:application"]
```

**Update:** `docker-compose.yml`

```yaml
version: '3.9'

services:
  db:
    image: postgres:15
    volumes:
      - postgres_data:/var/lib/postgresql/data/
    environment:
      POSTGRES_DB: payjaro
      POSTGRES_USER: payjaro
      POSTGRES_PASSWORD: payjaro123
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U payjaro"]
      interval: 10s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 3s
      retries: 5

  web:
    build: .
    ports:
      - "8000:8000"
    environment:
      - DJANGO_ENVIRONMENT=production
      - DATABASE_URL=postgresql://payjaro:payjaro123@db:5432/payjaro
      - REDIS_URL=redis://redis:6379/0
    volumes:
      - ./logs:/var/log/payjaro
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/api/users/profile/"]
      interval: 30s
      timeout: 10s
      retries: 3
    restart: unless-stopped

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
      - ./ssl:/etc/nginx/ssl
    depends_on:
      - web
    restart: unless-stopped

volumes:
  postgres_data:
```

**File to Create:** `nginx.conf`

```nginx
events {
    worker_connections 1024;
}

http {
    upstream web {
        server web:8000;
    }

    # Rate limiting
    limit_req_zone $binary_remote_addr zone=api:10m rate=10r/s;
    limit_req_zone $binary_remote_addr zone=auth:10m rate=5r/s;

    server {
        listen 80;
        server_name api.payjaro.com payjaro.com;
        
        # Redirect HTTP to HTTPS
        return 301 https://$server_name$request_uri;
    }

    server {
        listen 443 ssl http2;
        server_name api.payjaro.com payjaro.com;

        # SSL Configuration
        ssl_certificate /etc/nginx/ssl/cert.pem;
        ssl_certificate_key /etc/nginx/ssl/key.pem;
        ssl_protocols TLSv1.2 TLSv1.3;
        ssl_ciphers ECDHE-RSA-AES256-GCM-SHA512:DHE-RSA-AES256-GCM-SHA512;
        ssl_prefer_server_ciphers off;

        # Security headers
        add_header X-Content-Type-Options nosniff;
        add_header X-Frame-Options DENY;
        add_header X-XSS-Protection "1; mode=block";
        add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

        # API endpoints
        location /api/ {
            limit_req zone=api burst=20 nodelay;
            proxy_pass http://web;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_connect_timeout 30s;
            proxy_send_timeout 30s;
            proxy_read_timeout 30s;
        }

        # Authentication endpoints (stricter rate limiting)
        location ~ ^/api/(users|auth)/ {
            limit_req zone=auth burst=10 nodelay;
            proxy_pass http://web;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }

        # Webhook endpoints (no rate limiting)
        location /api/payments/webhooks/ {
            proxy_pass http://web;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }

        # Public storefront endpoints
        location / {
            proxy_pass http://web;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }

        # Health check
        location /health/ {
            access_log off;
            return 200 "healthy\n";
            add_header Content-Type text/plain;
        }
    }
}
```

### **TASK 6.3: Comprehensive Testing Suite**

**File to Create:** `tests/test_integration.py`

```python
from django.test import TestCase, TransactionTestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status
from decimal import Decimal
import json

from entrepreneurs.models import EntrepreneurProfile
from suppliers.models import SupplierProfile
from products.models import Product, Category
from orders.models import Order
from payments.models import Transaction, Earnings

User = get_user_model()

class FullWorkflowIntegrationTest(TransactionTestCase):
    """Test complete user journey from registration to order completion"""
    
    def setUp(self):
        self.client = APIClient()
        
        # Create category
        self.category = Category.objects.create(
            name='Electronics',
            slug='electronics'
        )
    
    def test_complete_entrepreneur_workflow(self):
        """Test complete entrepreneur workflow"""
        
        # 1. Entrepreneur Registration
        entrepreneur_data = {
            'username': 'testentrepreneur',
            'email': 'entrepreneur@test.com',
            'phone_number': '08012345678',
            'password': 'TestPass123!',
            'password2': 'TestPass123!',
            'user_type': 'entrepreneur',
            'referral_code': 'ENTRE001'
        }
        
        response = self.client.post('/api/users/register/', entrepreneur_data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        # 2. Login
        login_response = self.client.post('/api/users/login/', {
            'username': 'testentrepreneur',
            'password': 'TestPass123!'
        })
        self.assertEqual(login_response.status_code, status.HTTP_200_OK)
        token = login_response.data['access']
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
        
        # 3. Create Entrepreneur Profile
        profile_data = {
            'business_name': 'Test Electronics Store',
            'custom_url': 'test-electronics',
            'bio': 'We sell quality electronics'
        }
        
        profile_response = self.client.post('/api/entrepreneurs/profile/', profile_data)
        self.assertEqual(profile_response.status_code, status.HTTP_201_CREATED)
        
        # 4. Create Storefront
        storefront_data = {
            'theme': 'default',
            'about_section': 'Welcome to our store',
            'contact_info': {'email': 'store@test.com'},
            'seo_title': 'Test Electronics Store',
            'is_published': True
        }
        
        storefront_response = self.client.post('/api/social/storefront/', storefront_data)
        self.assertEqual(storefront_response.status_code, status.HTTP_201_CREATED)
        
        # 5. Check public storefront is accessible
        public_response = self.client.get('/test-electronics/')
        self.assertEqual(public_response.status_code, status.HTTP_200_OK)
        self.assertIn('entrepreneur', public_response.data)
        self.assertIn('storefront', public_response.data)
    
    def test_complete_supplier_workflow(self):
        """Test complete supplier workflow"""
        
        # 1. Supplier Registration
        supplier_data = {
            'username': 'testsupplier',
            'email': 'supplier@test.com',
            'password': 'TestPass123!',
            'phone_number': '08098765432',
            'company_name': 'Test Electronics Supplier',
            'business_registration': 'BR123456',
            'tax_id': 'TAX123456',
            'address': 'Test Address, Lagos',
            'contact_person': 'John Doe',
            'commission_rate': 15.00,
            'payment_terms': 'Net 30',
            'minimum_order_value': 1000.00
        }
        
        response = self.client.post('/api/suppliers/profiles/register/', supplier_data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        # 2. Login as supplier
        login_response = self.client.post('/api/users/login/', {
            'username': 'testsupplier',
            'password': 'TestPass123!'
        })
        token = login_response.data['access']
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
        
        # 3. Verify supplier (admin action simulation)
        supplier = SupplierProfile.objects.get(company_name='Test Electronics Supplier')
        supplier.verification_status = 'verified'
        supplier.save()
        
        # 4. Add product
        product_data = {
            'name': 'iPhone 15 Pro',
            'slug': 'iphone-15-pro',
            'description': 'Latest iPhone model',
            'category': self.category.id,
            'sku': 'IP15PRO001',
            'base_price': 500000.00,
            'suggested_markup': 15.0,
            'stock_quantity': 50,
            'weight': 0.5,
            'is_active': True
        }
        
        product_response = self.client.post('/api/suppliers/products/', product_data)
        self.assertEqual(product_response.status_code, status.HTTP_201_CREATED)
        
        product = Product.objects.get(sku='IP15PRO001')
        self.assertEqual(product.supplier, supplier)
    
    def test_complete_order_workflow(self):
        """Test complete order and payment workflow"""
        
        # Setup: Create entrepreneur, supplier, and product
        entrepreneur_user = User.objects.create_user(
            username='entrepreneur',
            email='entrepreneur@test.com',
            phone_number='08011111111',
            user_type='entrepreneur',
            referral_code='ENT        return SupplierProfile.objects.none()
    
    def get_serializer_class(self):
        if self.action == 'register':
            return SupplierRegistrationSerializer
        return SupplierProfileSerializer
    
    @action(detail=False, methods=['post'])
    def register(self, request):
        """Register new supplier with verification"""
        serializer = SupplierRegistrationSerializer(data=request.data)
        if serializer.is_valid():
            with transaction.atomic():
                supplier = serializer.save()
                return Response({
                    'message': 'Supplier registration successful. Verification pending.',
                    'supplier': SupplierProfileSerializer(supplier).data
                }, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['post'])
    def verify(self, request, pk=None):
        """Admin endpoint to verify supplier"""
        if request.user.user_type != 'admin':
            return Response({
                'error': 'Only admins can verify suppliers'
            }, status=status.HTTP_403_FORBIDDEN)
        
        supplier = self.get_object()
        verification_status = request.data.get('verification_status')
        notes = request.data.get('notes', '')
        
        if verification_status not in ['verified', 'rejected']:
            return Response({
                'error': 'Invalid verification status'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        supplier.verification_status = verification_status
        supplier.save()
        
        # TODO: Send notification to supplier
        
        return Response({
            'message': f'Supplier {verification_status} successfully',
            'supplier': SupplierProfileSerializer(supplier).data
        })
    
    @action(detail=False, methods=['get'])
    def my_products(self, request):
        """Get products for authenticated supplier"""
        if request.user.user_type != 'supplier':
            return Response({
                'error': 'Only suppliers can access this endpoint'
            }, status=status.HTTP_403_FORBIDDEN)
        
        try:
            supplier = SupplierProfile.objects.get(user=request.user)
        except SupplierProfile.DoesNotExist:
            return Response({
                'error': 'Supplier profile not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        products = Product.objects.filter(supplier=supplier).order_by('-created_at')
        
        page = self.paginate_queryset(products)
        if page is not None:
            serializer = ProductSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = ProductSerializer(products, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def my_orders(self, request):
        """Get orders for authenticated supplier"""
        if request.user.user_type != 'supplier':
            return Response({
                'error': 'Only suppliers can access this endpoint'
            }, status=status.HTTP_403_FORBIDDEN)
        
        try:
            supplier = SupplierProfile.objects.get(user=request.user)
        except SupplierProfile.DoesNotExist:
            return Response({
                'error': 'Supplier profile not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        orders = Order.objects.filter(supplier=supplier).order_by('-created_at')
        
        page = self.paginate_queryset(orders)
        if page is not None:
            serializer = OrderSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = OrderSerializer(orders, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def dashboard(self, request):
        """Supplier dashboard analytics"""
        if request.user.user_type != 'supplier':
            return Response({
                'error': 'Only suppliers can access dashboard'
            }, status=status.HTTP_403_FORBIDDEN)
        
        try:
            supplier = SupplierProfile.objects.get(user=request.user)
        except SupplierProfile.DoesNotExist:
            return Response({
                'error': 'Supplier profile not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Calculate dashboard metrics
        from django.db.models import Count, Sum, Avg
        from decimal import Decimal
        
        total_products = Product.objects.filter(supplier=supplier).count()
        active_products = Product.objects.filter(supplier=supplier, is_active=True).count()
        
        orders_stats = Order.objects.filter(supplier=supplier).aggregate(
            total_orders=Count('id'),
            total_revenue=Sum('total_amount'),
            pending_orders=Count('id', filter=models.Q(status='pending')),
            completed_orders=Count('id', filter=models.Q(status='delivered'))
        )
        
        # Recent orders
        recent_orders = Order.objects.filter(supplier=supplier).order_by('-created_at')[:5]
        
        # Top products by sales
        top_products = Product.objects.filter(supplier=supplier).annotate(
            order_count=Count('orderitem__order')
        ).order_by('-order_count')[:5]
        
        return Response({
            'total_products': total_products,
            'active_products': active_products,
            'total_orders': orders_stats['total_orders'] or 0,
            'total_revenue': orders_stats['total_revenue'] or Decimal('0.00'),
            'pending_orders': orders_stats['pending_orders'] or 0,
            'completed_orders': orders_stats['completed_orders'] or 0,
            'recent_orders': OrderSerializer(recent_orders, many=True).data,
            'top_products': ProductSerializer(top_products, many=True).data,
            'verification_status': supplier.verification_status,
            'performance_rating': supplier.performance_rating
        })

class SupplierProductViewSet(viewsets.ModelViewSet):
    serializer_class = ProductSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        if self.request.user.user_type != 'supplier':
            return Product.objects.none()
        
        try:
            supplier = SupplierProfile.objects.get(user=self.request.user)
            return Product.objects.filter(supplier=supplier)
        except SupplierProfile.DoesNotExist:
            return Product.objects.none()
    
    def perform_create(self, serializer):
        """Create product for authenticated supplier"""
        try:
            supplier = SupplierProfile.objects.get(user=self.request.user)
            if supplier.verification_status != 'verified':
                raise ValidationError("Only verified suppliers can add products")
            serializer.save(supplier=supplier)
        except SupplierProfile.DoesNotExist:
            raise ValidationError("Supplier profile not found")
    
    @action(detail=True, methods=['post'])
    def update_inventory(self, request, pk=None):
        """Update product inventory"""
        product = self.get_object()
        new_quantity = request.data.get('quantity')
        
        if new_quantity is None:
            return Response({
                'error': 'Quantity is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            new_quantity = int(new_quantity)
            if new_quantity < 0:
                raise ValueError("Quantity cannot be negative")
        except (ValueError, TypeError):
            return Response({
                'error': 'Invalid quantity'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        old_quantity = product.stock_quantity
        product.stock_quantity = new_quantity
        product.save()
        
        return Response({
            'message': 'Inventory updated successfully',
            'old_quantity': old_quantity,
            'new_quantity': new_quantity,
            'product': ProductSerializer(product).data
        })
    
    @action(detail=False, methods=['post'])
    def bulk_upload(self, request):
        """Bulk upload products from CSV or JSON"""
        if request.user.user_type != 'supplier':
            return Response({
                'error': 'Only suppliers can bulk upload products'
            }, status=status.HTTP_403_FORBIDDEN)
        
        try:
            supplier = SupplierProfile.objects.get(user=request.user)
            if supplier.verification_status != 'verified':
                return Response({
                    'error': 'Only verified suppliers can add products'
                }, status=status.HTTP_400_BAD_REQUEST)
        except SupplierProfile.DoesNotExist:
            return Response({
                'error': 'Supplier profile not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        products_data = request.data.get('products', [])
        if not products_data:
            return Response({
                'error': 'No products data provided'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        created_products = []
        errors = []
        
        for i, product_data in enumerate(products_data):
            try:
                serializer = ProductSerializer(data=product_data)
                if serializer.is_valid():
                    product = serializer.save(supplier=supplier)
                    created_products.append(ProductSerializer(product).data)
                else:
                    errors.append({
                        'index': i,
                        'errors': serializer.errors
                    })
            except Exception as e:
                errors.append({
                    'index': i,
                    'errors': str(e)
                })
        
        return Response({
            'message': f'{len(created_products)} products created successfully',
            'created_products': created_products,
            'errors': errors
        }, status=status.HTTP_201_CREATED if created_products else status.HTTP_400_BAD_REQUEST)
```

**File to Create:** `suppliers/serializers.py`

```python
from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import SupplierProfile

User = get_user_model()

class SupplierRegistrationSerializer(serializers.Serializer):
    # User fields
    username = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=8)
    phone_number = serializers.CharField(max_length=20)
    
    # Supplier profile fields
    company_name = serializers.CharField(max_length=200)
    business_registration = serializers.CharField(max_length=100)
    tax_id = serializers.CharField(max_length=100)
    address = serializers.CharField()
    contact_person = serializers.CharField(max_length=100)
    commission_rate = serializers.DecimalField(max_digits=5, decimal_places=2, min_value=0, max_value=50)
    payment_terms = serializers.CharField(max_length=100)
    minimum_order_value = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=0)
    
    # Optional fields
    bank_details = serializers.JSONField(required=False)
    delivery_areas = serializers.JSONField(required=False)
    business_hours = serializers.JSONField(required=False)
    
    def validate_username(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("Username already exists")
        return value
    
    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("Email already exists")
        return value
    
    def validate_phone_number(self, value):
        if User.objects.filter(phone_number=value).exists():
            raise serializers.ValidationError("Phone number already exists")
        return value
    
    def validate_business_registration(self, value):
        if SupplierProfile.objects.filter(business_registration=value).exists():
            raise serializers.ValidationError("Business registration already exists")
        return value
    
    def create(self, validated_data):
        # Extract user data
        user_data = {
            'username': validated_data.pop('username'),
            'email': validated_data.pop('email'),
            'phone_number': validated_data.pop('phone_number'),
            'user_type': 'supplier',
            'referral_code': f"SUP{validated_data['company_name'][:3].upper()}{User.objects.count() + 1:04d}"
        }
        password = validated_data.pop('password')
        
        # Create user
        user = User.objects.create_user(**user_data)
        user.set_password(password)
        user.save()
        
        # Create supplier profile
        supplier = SupplierProfile.objects.create(
            user=user,
            **validated_data
        )
        
        return supplier

class SupplierProfileSerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source='user.email', read_only=True)
    user_phone = serializers.CharField(source='user.phone_number', read_only=True)
    
    class Meta:
        model = SupplierProfile
        fields = [
            'id', 'user_email', 'user_phone', 'company_name', 
            'business_registration', 'tax_id', 'address', 'contact_person',
            'phone_number', 'email', 'bank_details', 'commission_rate',
            'payment_terms', 'minimum_order_value', 'delivery_areas',
            'business_hours', 'verification_status', 'performance_rating',
            'is_active'
        ]
        read_only_fields = [
            'id', 'verification_status', 'performance_rating', 'user_email', 'user_phone'
        ]
```

**File to Create:** `suppliers/urls.py`

```python
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .api import SupplierProfileViewSet, SupplierProductViewSet

router = DefaultRouter()
router.register(r'profiles', SupplierProfileViewSet, basename='supplier-profile')
router.register(r'products', SupplierProductViewSet, basename='supplier-product')

urlpatterns = [
    path('', include(router.urls)),
]
```

**Update:** `payjaro_project/urls.py`

```python
# ADD THIS LINE to the urlpatterns list
path('api/suppliers/', include('suppliers.urls')),
```

**VALIDATION COMMANDS:**
```bash
# Test supplier registration and management
python manage.py test suppliers.tests

# Test API endpoints
python manage.py runserver

# Test supplier registration:
# POST http://localhost:8000/api/suppliers/profiles/register/

# Test supplier dashboard:
# GET http://localhost:8000/api/suppliers/profiles/dashboard/
```

---

## **PHASE 5: SOCIAL COMMERCE & ANALYTICS**

### **TASK 5.1: Implement Public Storefront System**

**File to Create:** `public/__init__.py`

**File to Create:** `public/apps.py`

```python
from django.apps import AppConfig

class PublicConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "public"
```

**File to Create:** `public/views.py`

```python
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from django.db.models import Prefetch
from entrepreneurs.models import EntrepreneurProfile
from social.models import EntrepreneurStorefront, FeaturedProduct
from products.models import Product
from products.serializers import ProductSerializer
from entrepreneurs.serializers import EntrepreneurProfileSerializer
from social.serializers import EntrepreneurStorefrontSerializer

@api_view(['GET'])
@permission_classes([AllowAny])
def public_storefront(request, custom_url):
    """Public view of entrepreneur's storefront"""
    try:
        entrepreneur = get_object_or_404(
            EntrepreneurProfile.objects.select_related('user'),
            custom_url=custom_url,
            is_active=True
        )
        
        # Get storefront with featured products
        try:
            storefront = EntrepreneurStorefront.objects.select_related('entrepreneur').prefetch_related(
                Prefetch('featured_products', queryset=Product.objects.filter(is_active=True))
            ).get(entrepreneur=entrepreneur, is_published=True)
        except EntrepreneurStorefront.DoesNotExist:
            return Response({
                'error': 'Storefront not found or not published'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Get all products this entrepreneur is selling (not just featured)
        available_products = Product.objects.filter(
            is_active=True,
            stock_quantity__gt=0
        ).order_by('-created_at')
        
        # Track storefront view (for analytics)
        from analytics.services import AnalyticsService
        AnalyticsService.track_event(
            event_type='storefront_view',
            entrepreneur=entrepreneur,
            metadata={
                'visitor_ip': request.META.get('REMOTE_ADDR'),
                'user_agent': request.META.get('HTTP_USER_AGENT'),
                'referrer': request.META.get('HTTP_REFERER'),
                'custom_url': custom_url
            }
        )
        
        return Response({
            'entrepreneur': EntrepreneurProfileSerializer(entrepreneur).data,
            'storefront': EntrepreneurStorefrontSerializer(storefront).data,
            'featured_products': ProductSerializer(storefront.featured_products.all(), many=True).data,
            'all_products': ProductSerializer(available_products[:20], many=True).data,  # Limit for performance
            'seo': {
                'title': storefront.seo_title or f"{entrepreneur.business_name} - Payjaro Store",
                'description': storefront.seo_description or f"Shop from {entrepreneur.business_name} on Payjaro",
                'canonical_url': f"https://payjaro.com/{custom_url}",
                'og_image': entrepreneur.banner_image.url if entrepreneur.banner_image else None
            }
        })
        
    except Exception as e:
        return Response({
            'error': 'Storefront not found'
        }, status=status.HTTP_404_NOT_FOUND)

@api_view(['GET'])
@permission_classes([AllowAny])
def product_share_link(request, custom_url, product_slug):
    """Public view of product with entrepreneur context for sharing"""
    try:
        entrepreneur = get_object_or_404(
            EntrepreneurProfile,
            custom_url=custom_url,
            is_active=True
        )
        
        product = get_object_or_404(
            Product,
            slug=product_slug,
            is_active=True
        )
        
        # Track product view
        from analytics.services import AnalyticsService
        AnalyticsService.track_event(
            event_type='product_view',
            entrepreneur=entrepreneur,
            product=product,
            metadata={
                'visitor_ip': request.META.get('REMOTE_ADDR'),
                'user_agent': request.META.get('HTTP_USER_AGENT'),
                'referrer': request.META.get('HTTP_REFERER'),
                'share_link': True
            }
        )
        
        # Generate purchase link
        purchase_link = f"https://payjaro.com/order?entrepreneur={custom_url}&product={product_slug}"
        
        return Response({
            'product': ProductSerializer(product).data,
            'entrepreneur': EntrepreneurProfileSerializer(entrepreneur).data,
            'purchase_link': purchase_link,
            'share_data': {
                'title': f"{product.name} - {entrepreneur.business_name}",
                'description': product.description[:150] + "..." if len(product.description) > 150 else product.description,
                'image': product.images.filter(is_primary=True).first().image.url if product.images.filter(is_primary=True).exists() else None,
                'url': f"https://payjaro.com/{custom_url}/product/{product_slug}"
            },
            'pricing': {
                'base_price': product.base_price,
                'suggested_markup': product.suggested_markup,
                'entrepreneur_commission': entrepreneur.commission_rate
            }
        })
        
    except Exception as e:
        return Response({
            'error': 'Product or entrepreneur not found'
        }, status=status.HTTP_404_NOT_FOUND)

@api_view(['GET'])
@permission_classes([AllowAny])
def generate_share_links(request, custom_url):
    """Generate sharing links for social media platforms"""
    entrepreneur = get_object_or_404(
        EntrepreneurProfile,
        custom_url=custom_url,
        is_active=True
    )
    
    product_id = request.GET.get('product_id')
    base_url = f"https://payjaro.com/{custom_url}"
    
    if product_id:
        try:
            product = Product.objects.get(id=product_id, is_active=True)
            product_url = f"{base_url}/product/{product.slug}"
            share_text = f"Check out {product.name} from {entrepreneur.business_name}! 🛍️"
            
            return Response({
                'whatsapp': f"https://wa.me/?text={share_text} {product_url}",
                'instagram': product_url,  # For Instagram stories/posts
                'facebook': f"https://www.facebook.com/sharer/sharer.php?u={product_url}",
                'twitter': f"https://twitter.com/intent/tweet?text={share_text}&url={product_url}",
                'copy_link': product_url,
                'qr_code': f"https://api.qrserver.com/v1/create-qr-code/?size=200x200&data={product_url}"
            })
        except Product.DoesNotExist:
            return Response({
                'error': 'Product not found'
            }, status=status.HTTP_404_NOT_FOUND)
    else:
        # Share storefront
        share_text = f"Shop from {entrepreneur.business_name} on Payjaro! 🛍️"
        
        return Response({
            'whatsapp': f"https://wa.me/?text={share_text} {base_url}",
            'instagram': base_url,
            'facebook': f"https://www.facebook.com/sharer/sharer.php?u={base_url}",
            'twitter': f"https://twitter.com/intent/tweet?text={share_text}&url={base_url}",
            'copy_link': base_url,
            'qr_code': f"https://api.qrserver.com/v1/create-qr-code/?size=200x200&data={base_url}"
        })
```

**File to Create:** `public/urls.py`

```python
from django.urls import path
from . import views

urlpatterns = [
    path('<str:custom_url>/', views.public_storefront, name='public-storefront'),
    path('<str:custom_url>/product/<str:product_slug>/', views.product_share_link, name='product-share-link'),
    path('<str:custom_url>/share/', views.generate_share_links, name='generate-share-links'),
]
```

### **TASK 5.2: Implement Analytics System**

**File to Create:** `analytics/services.py`

```python
from django.db import models
from django.utils import timezone
from .models import AnalyticsEvent, DailyMetrics
from entrepreneurs.models import EntrepreneurProfile
from products.models import Product
from orders.models import Order
import logging

logger = logging.getLogger(__name__)

class AnalyticsService:
    @staticmethod
    def track_event(event_type, entrepreneur=None, product=None, order=None, user=None, metadata=None):
        """Track analytics event"""
        try:
            AnalyticsEvent.objects.create(
                event_type=event_type,
                user=user,
                entrepreneur=entrepreneur,
                product=product,
                order=order,
                metadata=metadata or {},
                ip_address=metadata.get('visitor_ip', '127.0.0.1') if metadata else '127.0.0.1',
                user_agent=metadata.get('user_agent', '') if metadata else ''
            )
        except Exception as e:
            logger.error(f"Failed to track event {event_type}: {str(e)}")
    
    @staticmethod
    def get_entrepreneur_analytics(entrepreneur, start_date=None, end_date=None):
        """Get comprehensive analytics for entrepreneur"""
        if not start_date:
            start_date = timezone.now() - timezone.timedelta(days=30)
        if not end_date:
            end_date = timezone.now()
        
        # Basic metrics
        events = AnalyticsEvent.objects.filter(
            entrepreneur=entrepreneur,
            timestamp__range=[start_date, end_date]
        )
        
        analytics = {
            'total_views': events.filter(event_type='storefront_view').count(),
            'product_views': events.filter(event_type='product_view').count(),
            'unique_visitors': events.values('ip_address').distinct().count(),
            'social_shares': events.filter(event_type='product_share').count(),
        }
        
        # Order analytics
        orders = Order.objects.filter(
            entrepreneur=entrepreneur,
            created_at__range=[start_date, end_date]
        )
        
        order_analytics = orders.aggregate(
            total_orders=models.Count('id'),
            total_revenue=models.Sum('total_amount'),
            total_items_sold=models.Sum('items__quantity'),
            average_order_value=models.Avg('total_amount')
        )
        
        analytics.update({
            'total_orders': order_analytics['total_orders'] or 0,
            'total_revenue': order_analytics['total_revenue'] or 0,
            'total_items_sold': order_analytics['total_items_sold'] or 0,
            'average_order_value': order_analytics['average_order_value'] or 0,
            'conversion_rate': (order_analytics['total_orders'] / analytics['total_views']) * 100 if analytics['total_views'] > 0 else 0
        })
        
        # Top products
        from django.db.models import Count, Sum
        top_products = Product.objects.filter(
            orderitem__order__entrepreneur=entrepreneur,
            orderitem__order__created_at__range=[start_date, end_date]
        ).annotate(
            order_count=Count('orderitem__order'),
            total_quantity=Sum('orderitem__quantity'),
            total_revenue=Sum('orderitem__total_price')
        ).order_by('-order_count')[:5]
        
        analytics['top_products'] = [{
            'product': product,
            'order_count': product.order_count,
            'total_quantity': product.total_quantity,
            'total_revenue': product.total_revenue
        } for product in top_products]
        
        # Daily breakdown
        daily_data = []
        current_date = start_date.date()
        end_date_only = end_date.date()
        
        while current_date <= end_date_only:
            day_events = events.filter(timestamp__date=current_date)
            day_orders = orders.filter(created_at__date=current_date)
            
            daily_data.append({
                'date': current_date.isoformat(),
                'views': day_events.filter(event_type='storefront_view').count(),
                'orders': day_orders.count(),
                'revenue': day_orders.aggregate(total=models.Sum('total_amount'))['total'] or 0
            })
            
            current_date += timezone.timedelta(days=1)
        
        analytics['daily_breakdown'] = daily_data
        
        return analytics
    
    @staticmethod
    def calculate_daily_metrics():
        """Calculate and store daily metrics for all entrepreneurs"""
        yesterday = timezone.now().date() - timezone.timedelta(days=1)
        
        for entrepreneur in EntrepreneurProfile.objects.filter(is_active=True):
            try:
                analytics = AnalyticsService.get_entrepreneur_analytics(
                    entrepreneur,
                    start_date=timezone.datetime.combine(yesterday, timezone.datetime.min.time()),
                    end_date=timezone.datetime.combine(yesterday, timezone.datetime.max.time())
                )
                
                DailyMetrics.objects.update_or_create(
                    date=yesterday,
                    metric_type='entrepreneur_performance',
                    entity_type='entrepreneur',
                    entity_id=str(entrepreneur.id),
                    defaults={
                        'value': analytics['total_revenue'],
                        'metadata': {
                            'views': analytics['total_views'],
                            'orders': analytics['total_orders'],
                            'conversion_rate': analytics['conversion_rate'],
                            'average_order_value': float(analytics['average_order_value'])
                        }
                    }
                )
            except Exception as e:
                logger.error(f"Failed to calculate daily metrics for entrepreneur {entrepreneur.id}: {str(e)}")
```

**File to Create:** `analytics/api.py`

```python
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from django.shortcuts import get_object_or_404
from django.utils import timezone
from entrepreneurs.models import EntrepreneurProfile
from .services import AnalyticsService

class TrackEventView(APIView):
    permission_classes = [AllowAny]
    
    def post(self, request):
        """Track analytics event from frontend"""
        event_type = request.data.get('event_type')
        entrepreneur_id = request.data.get('entrepreneur_id')
        product_id = request.data.get('product_id')
        metadata = request.data.get('metadata', {})
        
        # Add request metadata
        metadata.update({
            'visitor_ip': request.META.get('REMOTE_ADDR'),
            'user_agent': request.META.get('HTTP_USER_AGENT'),
            'referrer': request.META.get('HTTP_REFERER')
        })
        
        try:
            entrepreneur = None
            if entrepreneur_id:
                entrepreneur = EntrepreneurProfile.objects.get(id=entrepreneur_id)
            
            product = None
            if product_id:
                from products.models import Product
                product = Product.objects.get(id=product_id)
            
            AnalyticsService.track_event(
                event_type=event_type,
                entrepreneur=entrepreneur,
                product=product,
                user=request.user if request.user.is_authenticated else None,
                metadata=metadata
            )
            
            return Response({'status': 'success'})
        
        except Exception as e:
            return Response({
                'error': 'Failed to track event'
            }, status=status.HTTP_400_BAD_REQUEST)

class EntrepreneurAnalyticsView(APIView):# Payjaro Backend - AI Implementation Guide
## Complete Step-by-Step Instructions for Building Production-Ready MVP

---

## **CRITICAL CONTEXT FOR AI DEVELOPER**

**Current State:** Excellent Django foundation with 90% of models complete, 40% of APIs implemented
**Target:** Full-featured social commerce platform MVP ready for production
**Architecture:** Django REST Framework + PostgreSQL + Redis + AWS S3 + Payment Gateways
**Timeline:** Each phase builds on previous - DO NOT SKIP STEPS

---

## **PHASE 1: COMPLETE ORDERS API SYSTEM**

### **TASK 1.1: Implement Order Creation API with Business Logic**

**File to Create:** `orders/api.py`

```python
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db import transaction
from django.shortcuts import get_object_or_404
from decimal import Decimal
from .models import Order, OrderItem, OrderStatusHistory
from .serializers import (
    OrderSerializer, OrderCreateSerializer, 
    OrderItemSerializer, OrderStatusSerializer
)
from entrepreneurs.models import EntrepreneurProfile
from products.models import Product, ProductVariation
from payments.models import Earnings, Transaction as PaymentTransaction
import uuid
from datetime import datetime

class OrderViewSet(viewsets.ModelViewSet):
    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        if user.user_type == 'customer':
            return Order.objects.filter(customer=user)
        elif user.user_type == 'entrepreneur':
            entrepreneur = get_object_or_404(EntrepreneurProfile, user=user)
            return Order.objects.filter(entrepreneur=entrepreneur)
        elif user.user_type == 'supplier':
            # Return orders for supplier's products
            return Order.objects.filter(supplier__user=user)
        return Order.objects.none()
    
    def get_serializer_class(self):
        if self.action == 'create':
            return OrderCreateSerializer
        return OrderSerializer
    
    @transaction.atomic
    def create(self, request, *args, **kwargs):
        """
        CRITICAL: This method handles the complete order creation workflow
        1. Validate all order items and inventory
        2. Calculate pricing (markup + commission)
        3. Create order with proper relationships
        4. Reserve inventory
        5. Create earnings records
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Extract validated data
        order_data = serializer.validated_data
        items_data = order_data.pop('items')
        entrepreneur_slug = order_data.pop('entrepreneur_custom_url')
        
        # Get entrepreneur
        entrepreneur = get_object_or_404(
            EntrepreneurProfile, 
            custom_url=entrepreneur_slug
        )
        
        # Validate inventory for all items
        inventory_errors = []
        total_calculations = {
            'subtotal': Decimal('0.00'),
            'markup_amount': Decimal('0.00'),
            'commission_amount': Decimal('0.00'),
            'total_amount': Decimal('0.00')
        }
        
        validated_items = []
        
        for item_data in items_data:
            product = item_data['product']
            variation = item_data.get('variation')
            quantity = item_data['quantity']
            entrepreneur_price = Decimal(str(item_data['unit_price']))
            
            # Check inventory
            available_stock = variation.stock_quantity if variation else product.stock_quantity
            if available_stock < quantity:
                inventory_errors.append(
                    f"Insufficient stock for {product.name}. Available: {available_stock}, Requested: {quantity}"
                )
                continue
            
            # Calculate pricing
            base_price = product.base_price
            if variation and variation.price_modifier:
                base_price += variation.price_modifier
            
            item_subtotal = base_price * quantity
            markup_per_item = entrepreneur_price - base_price
            item_markup = markup_per_item * quantity
            item_commission = (entrepreneur_price * quantity) * (entrepreneur.commission_rate / 100)
            item_total = entrepreneur_price * quantity
            
            # Validate markup is not negative
            if markup_per_item < 0:
                inventory_errors.append(
                    f"Price for {product.name} cannot be less than base price ₦{base_price}"
                )
                continue
            
            validated_items.append({
                'product': product,
                'variation': variation,
                'quantity': quantity,
                'unit_price': entrepreneur_price,
                'base_price': base_price,
                'markup_amount': item_markup,
                'total_price': item_total
            })
            
            # Add to totals
            total_calculations['subtotal'] += item_subtotal
            total_calculations['markup_amount'] += item_markup
            total_calculations['commission_amount'] += item_commission
            total_calculations['total_amount'] += item_total
        
        if inventory_errors:
            return Response({
                'errors': inventory_errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Calculate shipping (basic implementation)
        shipping_fee = Decimal('500.00')  # Fixed for now
        total_calculations['total_amount'] += shipping_fee
        
        # Generate unique order ID
        order_id = f"PAY{datetime.now().strftime('%Y%m%d')}{str(uuid.uuid4())[:8].upper()}"
        
        # Create order
        order = Order.objects.create(
            order_id=order_id,
            customer=request.user,
            entrepreneur=entrepreneur,
            supplier=validated_items[0]['product'].supplier,  # Assuming single supplier per order
            status='pending',
            subtotal=total_calculations['subtotal'],
            markup_amount=total_calculations['markup_amount'],
            commission_amount=total_calculations['commission_amount'],
            shipping_fee=shipping_fee,
            total_amount=total_calculations['total_amount'],
            payment_status='pending',
            payment_method='',  # Will be set during payment
            shipping_address=order_data.get('shipping_address', {}),
            notes=order_data.get('notes', '')
        )
        
        # Create order items and reserve inventory
        for item_data in validated_items:
            OrderItem.objects.create(
                order=order,
                product=item_data['product'],
                variation=item_data['variation'],
                quantity=item_data['quantity'],
                unit_price=item_data['unit_price'],
                base_price=item_data['base_price'],
                markup_amount=item_data['markup_amount'],
                total_price=item_data['total_price']
            )
            
            # Reserve inventory
            if item_data['variation']:
                item_data['variation'].stock_quantity -= item_data['quantity']
                item_data['variation'].save()
            else:
                item_data['product'].stock_quantity -= item_data['quantity']
                item_data['product'].save()
        
        # Create status history
        OrderStatusHistory.objects.create(
            order=order,
            status='pending',
            notes='Order created',
            created_by=request.user
        )
        
        # Create earnings records (pending until payment)
        Earnings.objects.create(
            entrepreneur=entrepreneur,
            order=order,
            earning_type='markup',
            amount=total_calculations['markup_amount'],
            status='pending'
        )
        
        Earnings.objects.create(
            entrepreneur=entrepreneur,
            order=order,
            earning_type='commission',
            amount=total_calculations['commission_amount'],
            status='pending'
        )
        
        serializer = OrderSerializer(order)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    
    @action(detail=True, methods=['post'])
    def update_status(self, request, pk=None):
        """Update order status with proper validation and history tracking"""
        order = self.get_object()
        new_status = request.data.get('status')
        notes = request.data.get('notes', '')
        
        if new_status not in dict(Order.ORDER_STATUS).keys():
            return Response({
                'error': 'Invalid status'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Validate status transitions
        valid_transitions = {
            'pending': ['paid', 'cancelled'],
            'paid': ['processing', 'cancelled'],
            'processing': ['shipped', 'cancelled'],
            'shipped': ['delivered', 'returned'],
            'delivered': ['returned'],
            'cancelled': [],
            'returned': []
        }
        
        if new_status not in valid_transitions.get(order.status, []):
            return Response({
                'error': f'Cannot transition from {order.status} to {new_status}'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Update order status
        old_status = order.status
        order.status = new_status
        order.save()
        
        # Create status history
        OrderStatusHistory.objects.create(
            order=order,
            status=new_status,
            notes=notes,
            created_by=request.user
        )
        
        # Handle status-specific logic
        if new_status == 'cancelled' and old_status == 'pending':
            # Restore inventory
            for item in order.items.all():
                if item.variation:
                    item.variation.stock_quantity += item.quantity
                    item.variation.save()
                else:
                    item.product.stock_quantity += item.quantity
                    item.product.save()
            
            # Update earnings to cancelled
            Earnings.objects.filter(order=order).update(status='cancelled')
        
        return Response({
            'message': f'Order status updated to {new_status}',
            'order': OrderSerializer(order).data
        })
    
    @action(detail=False, methods=['get'])
    def entrepreneur_orders(self, request):
        """Get orders for the authenticated entrepreneur"""
        if request.user.user_type != 'entrepreneur':
            return Response({
                'error': 'Only entrepreneurs can access this endpoint'
            }, status=status.HTTP_403_FORBIDDEN)
        
        entrepreneur = get_object_or_404(EntrepreneurProfile, user=request.user)
        orders = Order.objects.filter(entrepreneur=entrepreneur).order_by('-created_at')
        
        # Add pagination
        page = self.paginate_queryset(orders)
        if page is not None:
            serializer = OrderSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = OrderSerializer(orders, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def supplier_orders(self, request):
        """Get orders for the authenticated supplier"""
        if request.user.user_type != 'supplier':
            return Response({
                'error': 'Only suppliers can access this endpoint'
            }, status=status.HTTP_403_FORBIDDEN)
        
        orders = Order.objects.filter(supplier__user=request.user).order_by('-created_at')
        
        page = self.paginate_queryset(orders)
        if page is not None:
            serializer = OrderSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = OrderSerializer(orders, many=True)
        return Response(serializer.data)
```

**File to Create:** `orders/serializers.py`

```python
from rest_framework import serializers
from .models import Order, OrderItem, OrderStatusHistory
from entrepreneurs.models import EntrepreneurProfile
from products.models import Product, ProductVariation
from products.serializers import ProductSerializer
from users.serializers import UserProfileSerializer

class OrderItemSerializer(serializers.ModelSerializer):
    product = ProductSerializer(read_only=True)
    product_name = serializers.CharField(source='product.name', read_only=True)
    
    class Meta:
        model = OrderItem
        fields = [
            'id', 'product', 'product_name', 'variation', 
            'quantity', 'unit_price', 'base_price', 
            'markup_amount', 'total_price'
        ]

class OrderItemCreateSerializer(serializers.Serializer):
    product_id = serializers.IntegerField()
    variation_id = serializers.IntegerField(required=False, allow_null=True)
    quantity = serializers.IntegerField(min_value=1)
    unit_price = serializers.DecimalField(max_digits=12, decimal_places=2)
    
    def validate(self, data):
        # Validate product exists
        try:
            product = Product.objects.get(id=data['product_id'], is_active=True)
        except Product.DoesNotExist:
            raise serializers.ValidationError("Product not found or inactive")
        
        # Validate variation if provided
        variation = None
        if data.get('variation_id'):
            try:
                variation = ProductVariation.objects.get(
                    id=data['variation_id'], 
                    product=product
                )
            except ProductVariation.DoesNotExist:
                raise serializers.ValidationError("Product variation not found")
        
        data['product'] = product
        data['variation'] = variation
        return data

class OrderStatusHistorySerializer(serializers.ModelSerializer):
    created_by = UserProfileSerializer(read_only=True)
    
    class Meta:
        model = OrderStatusHistory
        fields = ['id', 'status', 'notes', 'created_by', 'created_at']

class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    customer = UserProfileSerializer(read_only=True)
    entrepreneur = serializers.StringRelatedField(read_only=True)
    supplier = serializers.StringRelatedField(read_only=True)
    status_history = OrderStatusHistorySerializer(many=True, read_only=True)
    
    class Meta:
        model = Order
        fields = [
            'id', 'order_id', 'customer', 'entrepreneur', 'supplier',
            'status', 'subtotal', 'markup_amount', 'commission_amount',
            'shipping_fee', 'total_amount', 'payment_status', 'payment_method',
            'shipping_address', 'tracking_number', 'notes', 'created_at',
            'updated_at', 'items', 'status_history'
        ]
        read_only_fields = [
            'id', 'order_id', 'subtotal', 'markup_amount', 'commission_amount',
            'total_amount', 'created_at', 'updated_at'
        ]

class OrderCreateSerializer(serializers.Serializer):
    entrepreneur_custom_url = serializers.CharField(max_length=100)
    items = OrderItemCreateSerializer(many=True)
    shipping_address = serializers.JSONField()
    notes = serializers.CharField(required=False, allow_blank=True)
    
    def validate_entrepreneur_custom_url(self, value):
        try:
            EntrepreneurProfile.objects.get(custom_url=value, is_active=True)
        except EntrepreneurProfile.DoesNotExist:
            raise serializers.ValidationError("Entrepreneur not found")
        return value
    
    def validate_items(self, value):
        if not value:
            raise serializers.ValidationError("At least one item is required")
        return value
    
    def validate_shipping_address(self, value):
        required_fields = ['full_name', 'phone', 'address', 'city', 'state']
        for field in required_fields:
            if field not in value or not value[field]:
                raise serializers.ValidationError(f"Shipping address must include {field}")
        return value
```

**File to Create:** `orders/urls.py`

```python
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .api import OrderViewSet

router = DefaultRouter()
router.register(r'orders', OrderViewSet, basename='order')

urlpatterns = [
    path('', include(router.urls)),
]
```

**Update:** `payjaro_project/urls.py`

```python
# ADD THIS LINE to the urlpatterns list
path('api/orders/', include('orders.urls')),
```

**VALIDATION COMMANDS:**
```bash
# Run these commands in sequence
python manage.py makemigrations
python manage.py migrate
python manage.py test orders.tests
python manage.py runserver

# Test in browser/Postman:
# POST http://localhost:8000/api/orders/orders/
# GET http://localhost:8000/api/orders/orders/
```

**CRITICAL CHECKPOINTS:**
- [ ] Order creation API responds with 201 status
- [ ] Commission calculations are accurate
- [ ] Inventory is properly reserved
- [ ] Order status updates work correctly
- [ ] All tests pass without errors

---

## **PHASE 2: PAYMENT INTEGRATION SYSTEM**

### **TASK 2.1: Implement Paystack Payment Integration**

**Install Required Dependencies:**
```bash
pip install paystack-python requests cryptography
pip freeze > requirements.txt
```

**File to Create:** `payments/services.py`

```python
import os
import hashlib
import hmac
import json
import requests
from decimal import Decimal
from django.conf import settings
from .models import Transaction, PaymentMethod
import logging

logger = logging.getLogger(__name__)

class PaystackService:
    def __init__(self):
        self.secret_key = settings.PAYSTACK_SECRET_KEY
        self.public_key = settings.PAYSTACK_PUBLIC_KEY
        self.base_url = "https://api.paystack.co"
        
    def _make_request(self, method, endpoint, data=None):
        """Make authenticated request to Paystack API"""
        headers = {
            'Authorization': f'Bearer {self.secret_key}',
            'Content-Type': 'application/json'
        }
        
        url = f"{self.base_url}{endpoint}"
        
        try:
            if method == 'POST':
                response = requests.post(url, headers=headers, json=data)
            elif method == 'GET':
                response = requests.get(url, headers=headers, params=data)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
            
            response.raise_for_status()
            return response.json()
        
        except requests.exceptions.RequestException as e:
            logger.error(f"Paystack API request failed: {str(e)}")
            raise Exception(f"Payment service error: {str(e)}")
    
    def initialize_payment(self, order, callback_url):
        """Initialize payment transaction with Paystack"""
        # Convert amount to kobo (Paystack uses kobo)
        amount_kobo = int(order.total_amount * 100)
        
        data = {
            'email': order.customer.email,
            'amount': amount_kobo,
            'currency': 'NGN',
            'reference': f"PAY_{order.order_id}_{order.id}",
            'callback_url': callback_url,
            'metadata': {
                'order_id': order.order_id,
                'customer_id': order.customer.id,
                'entrepreneur_id': order.entrepreneur.id,
                'order_total': str(order.total_amount)
            }
        }
        
        try:
            response = self._make_request('POST', '/transaction/initialize', data)
            
            if response.get('status'):
                return {
                    'success': True,
                    'authorization_url': response['data']['authorization_url'],
                    'access_code': response['data']['access_code'],
                    'reference': response['data']['reference']
                }
            else:
                return {
                    'success': False,
                    'message': response.get('message', 'Payment initialization failed')
                }
        
        except Exception as e:
            return {
                'success': False,
                'message': str(e)
            }
    
    def verify_payment(self, reference):
        """Verify payment transaction with Paystack"""
        try:
            response = self._make_request('GET', f'/transaction/verify/{reference}')
            
            if response.get('status'):
                data = response['data']
                return {
                    'success': True,
                    'status': data['status'],
                    'amount': Decimal(str(data['amount'])) / 100,  # Convert from kobo
                    'currency': data['currency'],
                    'reference': data['reference'],
                    'paid_at': data['paid_at'],
                    'metadata': data.get('metadata', {}),
                    'gateway_response': data.get('gateway_response', '')
                }
            else:
                return {
                    'success': False,
                    'message': response.get('message', 'Payment verification failed')
                }
        
        except Exception as e:
            return {
                'success': False,
                'message': str(e)
            }
    
    def verify_webhook_signature(self, payload, signature):
        """Verify that webhook is from Paystack"""
        computed_signature = hmac.new(
            self.secret_key.encode('utf-8'),
            payload,
            hashlib.sha512
        ).hexdigest()
        
        return hmac.compare_digest(computed_signature, signature)

class FlutterwaveService:
    def __init__(self):
        self.secret_key = settings.FLUTTERWAVE_SECRET_KEY
        self.public_key = settings.FLUTTERWAVE_PUBLIC_KEY
        self.base_url = "https://api.flutterwave.com/v3"
    
    def _make_request(self, method, endpoint, data=None):
        """Make authenticated request to Flutterwave API"""
        headers = {
            'Authorization': f'Bearer {self.secret_key}',
            'Content-Type': 'application/json'
        }
        
        url = f"{self.base_url}{endpoint}"
        
        try:
            if method == 'POST':
                response = requests.post(url, headers=headers, json=data)
            elif method == 'GET':
                response = requests.get(url, headers=headers, params=data)
            
            response.raise_for_status()
            return response.json()
        
        except requests.exceptions.RequestException as e:
            logger.error(f"Flutterwave API request failed: {str(e)}")
            raise Exception(f"Payment service error: {str(e)}")
    
    def initialize_payment(self, order, callback_url):
        """Initialize payment with Flutterwave"""
        data = {
            'tx_ref': f"FLW_{order.order_id}_{order.id}",
            'amount': str(order.total_amount),
            'currency': 'NGN',
            'redirect_url': callback_url,
            'customer': {
                'email': order.customer.email,
                'phonenumber': order.customer.phone_number,
                'name': f"{order.customer.first_name} {order.customer.last_name}"
            },
            'customizations': {
                'title': 'Payjaro Order Payment',
                'description': f'Payment for order {order.order_id}',
                'logo': 'https://your-logo-url.com/logo.png'
            },
            'meta': {
                'order_id': order.order_id,
                'customer_id': order.customer.id,
                'entrepreneur_id': order.entrepreneur.id
            }
        }
        
        try:
            response = self._make_request('POST', '/payments', data)
            
            if response.get('status') == 'success':
                return {
                    'success': True,
                    'payment_link': response['data']['link'],
                    'reference': data['tx_ref']
                }
            else:
                return {
                    'success': False,
                    'message': response.get('message', 'Payment initialization failed')
                }
        
        except Exception as e:
            return {
                'success': False,
                'message': str(e)
            }
    
    def verify_payment(self, transaction_id):
        """Verify payment with Flutterwave"""
        try:
            response = self._make_request('GET', f'/transactions/{transaction_id}/verify')
            
            if response.get('status') == 'success':
                data = response['data']
                return {
                    'success': True,
                    'status': data['status'],
                    'amount': Decimal(str(data['amount'])),
                    'currency': data['currency'],
                    'reference': data['tx_ref'],
                    'flw_ref': data['flw_ref'],
                    'metadata': data.get('meta', {})
                }
            else:
                return {
                    'success': False,
                    'message': response.get('message', 'Payment verification failed')
                }
        
        except Exception as e:
            return {
                'success': False,
                'message': str(e)
            }
```

**File to Create:** `payments/api.py`

```python
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
        """Initialize payment for an order"""
        order_id = request.data.get('order_id')
        payment_provider = request.data.get('provider', 'paystack')  # Default to Paystack
        callback_url = request.data.get('callback_url', f"{settings.FRONTEND_URL}/payment/callback")
        
        if not order_id:
            return Response({
                'error': 'Order ID is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            order = Order.objects.get(order_id=order_id, customer=request.user)
            
            if order.payment_status == 'paid':
                return Response({
                    'error': 'Order has already been paid'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Initialize payment based on provider
            if payment_provider == 'paystack':
                service = PaystackService()
                result = service.initialize_payment(order, callback_url)
            elif payment_provider == 'flutterwave':
                service = FlutterwaveService()
                result = service.initialize_payment(order, callback_url)
            else:
                return Response({
                    'error': 'Unsupported payment provider'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            if result['success']:
                # Create transaction record
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
                return Response({
                    'error': result['message']
                }, status=status.HTTP_400_BAD_REQUEST)
        
        except Order.DoesNotExist:
            return Response({
                'error': 'Order not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        except Exception as e:
            logger.error(f"Payment initiation error: {str(e)}")
            return Response({
                'error': 'Payment initialization failed'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@method_decorator(csrf_exempt, name='dispatch')
class PaystackWebhookView(APIView):
    permission_classes = [AllowAny]
    
    def post(self, request):
        """Handle Paystack webhook notifications"""
        payload = request.body
        signature = request.META.get('HTTP_X_PAYSTACK_SIGNATURE', '')
        
        try:
            # Verify webhook signature
            service = PaystackService()
            if not service.verify_webhook_signature(payload, signature):
                logger.warning("Invalid Paystack webhook signature")
                return Response({'error': 'Invalid signature'}, status=status.HTTP_400_BAD_REQUEST)
            
            # Parse webhook data
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
        """Process successful payment"""
        reference = payment_data.get('reference')
        
        try:
            # Get transaction and order
            transaction_obj = Transaction.objects.get(transaction_id=reference)
            order = transaction_obj.order
            
            # Update transaction status
            transaction_obj.status = 'completed'
            transaction_obj.metadata.update({
                'gateway_response': payment_data.get('gateway_response', ''),
                'paid_at': payment_data.get('paid_at')
            })
            transaction_obj.save()
            
            # Update order status
            order.payment_status = 'paid'
            order.payment_method = 'paystack'
            order.status = 'paid'
            order.save()
            
            # Update earnings to paid status
            earnings = Earnings.objects.filter(order=order, status='pending')
            for earning in earnings:
                earning.status = 'paid'
                earning.payout_date = transaction_obj.created_at
                earning.save()
            
            # Update entrepreneur wallet
            entrepreneur = order.entrepreneur
            wallet, created = Wallet.objects.get_or_create(user=entrepreneur.user)
            
            total_earnings = sum(e.amount for e in earnings)
            wallet.balance += total_earnings
            wallet.total_earned += total_earnings
            wallet.save()
            
            # Update entrepreneur profile totals
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
        """Process failed payment"""
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
        """Get earnings summary for entrepreneur"""
        if request.user.user_type != 'entrepreneur':
            return Response({
                'error': 'Only entrepreneurs can access earnings'
            }, status=status.HTTP_403_FORBIDDEN)
        
        entrepreneur = get_object_or_404(EntrepreneurProfile, user=request.user)
        
        # Get wallet
        wallet, created = Wallet.objects.get_or_create(user=request.user)
        
        # Calculate earnings breakdown
        total_markup = Earnings.objects.filter(
            entrepreneur=entrepreneur, 
            earning_type='markup', 
            status='paid'
        ).aggregate(total=models.Sum('amount'))['total'] or 0
        
        total_commission = Earnings.objects.filter(
            entrepreneur=entrepreneur, 
            earning_type='commission', 
            status='paid'
        ).aggregate(total=models.Sum('amount'))['total'] or 0
        
        pending_earnings = Earnings.objects.filter(
            entrepreneur=entrepreneur, 
            status='pending'
        ).aggregate(total=models.Sum('amount'))['total'] or 0
        
        return Response({
            'available_balance': wallet.balance,
            'pending_balance': wallet.pending_balance,
            'total_earned': wallet.total_earned,
            'total_withdrawn': wallet.total_withdrawn,
            'total_markup': total_markup,
            'total_commission': total_commission,
            'pending_earnings': pending_earnings,
            'total_sales': entrepreneur.total_sales,
            'performance_tier': entrepreneur.performance_tier
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
        """Create withdrawal request"""
        if request.user.user_type != 'entrepreneur':
            return Response({
                'error': 'Only entrepreneurs can request withdrawals'
            }, status=status.HTTP_403_FORBIDDEN)
        
        entrepreneur = get_object_or_404(EntrepreneurProfile, user=request.user)
        wallet, created = Wallet.objects.get_or_create(user=request.user)
        
        amount = request.data.get('amount')
        withdrawal_method = request.data.get('withdrawal_method')
        destination_details = request.data.get('destination_details', {})
        
        # Validate amount
        try:
            amount = Decimal(str(amount))
        except (ValueError, TypeError):
            return Response({
                'error': 'Invalid amount'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        if amount <= 0:
            return Response({
                'error': 'Amount must be greater than zero'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        if amount > wallet.balance:
            return Response({
                'error': 'Insufficient balance'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Minimum withdrawal check
        if amount < Decimal('1000.00'):
            return Response({
                'error': 'Minimum withdrawal amount is ₦1,000'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Calculate processing fee (2% or minimum ₦50)
        processing_fee = max(amount * Decimal('0.02'), Decimal('50.00'))
        net_amount = amount - processing_fee
        
        # Create withdrawal request
        withdrawal = WithdrawalRequest.objects.create(
            entrepreneur=entrepreneur,
            amount=amount,
            withdrawal_method=withdrawal_method,
            destination_details=destination_details,
            status='pending',
            processing_fee=processing_fee,
            reference_id=f"WD{entrepreneur.id}{len(WithdrawalRequest.objects.filter(entrepreneur=entrepreneur)) + 1:04d}"
        )
        
        # Update wallet
        wallet.balance -= amount
        wallet.pending_balance += amount
        wallet.save()
        
        serializer = WithdrawalRequestSerializer(withdrawal)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
```

**File to Create:** `payments/serializers.py`

```python
from rest_framework import serializers
from .models import PaymentMethod, Transaction, Earnings, WithdrawalRequest, Wallet
from orders.serializers import OrderSerializer

class PaymentMethodSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentMethod
        fields = [
            'id', 'method_type', 'provider', 'details', 
            'is_default', 'is_active'
        ]
        read_only_fields = ['id']
    
    def validate_details(self, value):
        """Validate payment method details based on type"""
        method_type = self.initial_data.get('method_type')
        
        if method_type == 'bank_transfer':
            required_fields = ['account_number', 'bank_code', 'account_name']
            for field in required_fields:
                if field not in value:
                    raise serializers.ValidationError(f"Bank transfer requires {field}")
        
        elif method_type == 'crypto':
            required_fields = ['wallet_address', 'crypto_type']
            for field in required_fields:
                if field not in value:
                    raise serializers.ValidationError(f"Crypto payment requires {field}")
        
        return value

class TransactionSerializer(serializers.ModelSerializer):
    order = OrderSerializer(read_only=True)
    
    class Meta:
        model = Transaction
        fields = [
            'id', 'transaction_id', 'order', 'transaction_type',
            'amount', 'currency', 'status', 'provider_reference',
            'metadata', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']

class EarningsSerializer(serializers.ModelSerializer):
    order = OrderSerializer(read_only=True)
    
    class Meta:
        model = Earnings
        fields = [
            'id', 'order', 'earning_type', 'amount', 'status',
            'payout_date', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']

class WithdrawalRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = WithdrawalRequest
        fields = [
            'id', 'amount', 'withdrawal_method', 'destination_details',
            'status', 'processing_fee', 'reference_id', 'processed_at',
            'created_at'
        ]
        read_only_fields = [
            'id', 'status', 'processing_fee', 'reference_id', 
            'processed_at', 'created_at'
        ]

class WalletSerializer(serializers.ModelSerializer):
    class Meta:
        model = Wallet
        fields = [
            'id', 'balance', 'pending_balance', 'total_earned',
            'total_withdrawn', 'currency', 'updated_at'
        ]
        read_only_fields = ['id', 'updated_at']
```

**File to Create:** `payments/urls.py`

```python
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .api import (
    PaymentMethodViewSet, PaymentInitiationView, PaystackWebhookView,
    EarningsViewSet, WithdrawalViewSet
)

router = DefaultRouter()
router.register(r'payment-methods', PaymentMethodViewSet, basename='payment-method')
router.register(r'earnings', EarningsViewSet, basename='earnings')
router.register(r'withdrawals', WithdrawalViewSet, basename='withdrawal')

urlpatterns = [
    path('', include(router.urls)),
    path('initialize/', PaymentInitiationView.as_view(), name='payment-initialize'),
    path('webhooks/paystack/', PaystackWebhookView.as_view(), name='paystack-webhook'),
]
```

**Update:** `payjaro_project/settings.py`

```python
# ADD THESE PAYMENT SETTINGS
import os

# Payment Gateway Settings
PAYSTACK_PUBLIC_KEY = os.getenv('PAYSTACK_PUBLIC_KEY', 'pk_test_your_test_key')
PAYSTACK_SECRET_KEY = os.getenv('PAYSTACK_SECRET_KEY', 'sk_test_your_test_key')
FLUTTERWAVE_PUBLIC_KEY = os.getenv('FLUTTERWAVE_PUBLIC_KEY', 'FLWPUBK_TEST-your_test_key')
FLUTTERWAVE_SECRET_KEY = os.getenv('FLUTTERWAVE_SECRET_KEY', 'FLWSECK_TEST-your_test_key')

# Frontend URL for callbacks
FRONTEND_URL = os.getenv('FRONTEND_URL', 'http://localhost:3000')

# Logging configuration
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'file': {
            'level': 'INFO',
            'class': 'logging.FileHandler',
            'filename': 'payments.log',
        },
        'console': {
            'level': 'DEBUG',
            'class': 'logging.StreamHandler',
        },
    },
    'loggers': {
        'payments': {
            'handlers': ['file', 'console'],
            'level': 'INFO',
            'propagate': True,
        },
    },
}
```

**Update:** `payjaro_project/urls.py`

```python
# ADD THIS LINE to the urlpatterns list
path('api/payments/', include('payments.urls')),
```

**VALIDATION COMMANDS:**
```bash
# Install dependencies
pip install paystack-python requests cryptography

# Run migrations
python manage.py makemigrations payments
python manage.py migrate

# Test payment APIs
python manage.py test payments.tests

# Start server and test endpoints
python manage.py runserver

# Test payment initialization:
# POST http://localhost:8000/api/payments/initialize/
# Body: {"order_id": "PAY20250718ABC123", "provider": "paystack"}
```

**CRITICAL CHECKPOINTS:**
- [ ] Payment initialization returns valid payment URL
- [ ] Webhook signature verification works
- [ ] Successful payments update order and earnings
- [ ] Failed payments are handled correctly
- [ ] Earnings calculations are accurate
- [ ] Withdrawal system enforces proper validations

---

## **PHASE 3: FILE STORAGE AND MEDIA MANAGEMENT**

### **TASK 3.1: Implement AWS S3 Integration for File Storage**

**Install Dependencies:**
```bash
pip install boto3 django-storages pillow
pip freeze > requirements.txt
```

**Update:** `payjaro_project/settings.py`

```python
# ADD AWS S3 CONFIGURATION
import os

# AWS S3 Settings
AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = os.getenv('AWS_SECRET_ACCESS_KEY')
AWS_STORAGE_BUCKET_NAME = os.getenv('AWS_STORAGE_BUCKET_NAME', 'payjaro-files')
AWS_S3_REGION_NAME = os.getenv('AWS_S3_REGION_NAME', 'us-east-1')
AWS_S3_CUSTOM_DOMAIN = f'{AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com'
AWS_DEFAULT_ACL = 'public-read'
AWS_S3_OBJECT_PARAMETERS = {
    'CacheControl': 'max-age=86400',
}
AWS_LOCATION = 'static'
AWS_MEDIA_LOCATION = 'media'

# Storage backends
if not DEBUG:
    # Production storage
    DEFAULT_FILE_STORAGE = 'storages.backends.s3boto3.S3Boto3Storage'
    STATICFILES_STORAGE = 'storages.backends.s3boto3.S3StaticStorage'
    
    # URLs
    STATIC_URL = f'https://{AWS_S3_CUSTOM_DOMAIN}/{AWS_LOCATION}/'
    MEDIA_URL = f'https://{AWS_S3_CUSTOM_DOMAIN}/{AWS_MEDIA_LOCATION}/'
else:
    # Development storage
    STATIC_URL = '/static/'
    MEDIA_URL = '/media/'
    MEDIA_ROOT = BASE_DIR / 'media'

# File upload settings
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # 10MB
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # 10MB

# Add storages to INSTALLED_APPS
INSTALLED_APPS = [
    # ... existing apps
    'storages',
]
```

**File to Create:** `core/file_utils.py`

```python
import os
import uuid
from PIL import Image
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

def generate_unique_filename(filename, prefix=''):
    """Generate unique filename with UUID"""
    ext = os.path.splitext(filename)[1]
    unique_filename = f"{prefix}{uuid.uuid4().hex}{ext}"
    return unique_filename

def validate_image_file(file):
    """Validate uploaded image file"""
    # Check file size (max 5MB)
    if file.size > 5 * 1024 * 1024:
        raise ValueError("Image file too large. Maximum size is 5MB.")
    
    # Check file type
    allowed_types = ['image/jpeg', 'image/png', 'image/webp']
    if file.content_type not in allowed_types:
        raise ValueError("Invalid file type. Only JPEG, PNG, and WebP are allowed.")
    
    try:
        # Validate image can be opened
        image = Image.open(file)
        image.verify()
        file.seek(0)  # Reset file pointer
        return True
    except Exception:
        raise ValueError("Invalid image file.")

def optimize_image(image_file, max_width=1200, max_height=1200, quality=85):
    """Optimize image for web use"""
    try:
        image = Image.open(image_file)
        
        # Convert RGBA to RGB if needed
        if image.mode in ('RGBA', 'LA', 'P'):
            background = Image.new('RGB', image.size, (255, 255, 255))
            if image.mode == 'P':
                image = image.convert('RGBA')
            background.paste(image, mask=image.split()[-1] if image.mode == 'RGBA' else None)
            image = background
        
        # Resize if needed
        if image.width > max_width or image.height > max_height:
            image.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)
        
        # Save optimized image
        from io import BytesIO
        output = BytesIO()
        image.save(output, format='JPEG', quality=quality, optimize=True)
        output.seek(0)
        
        return ContentFile(output.read())
    
    except Exception as e:
        logger.error(f"Image optimization failed: {str(e)}")
        raise ValueError("Image optimization failed.")

class FileUploadService:
    @staticmethod
    def upload_product_image(product, image_file, is_primary=False):
        """Upload and optimize product image"""
        try:
            # Validate image
            validate_image_file(image_file)
            
            # Generate filename
            filename = generate_unique_filename(
                image_file.name, 
                f"products/{product.id}/"
            )
            
            # Optimize image
            optimized_image = optimize_image(image_file)
            
            # Save to storage
            path = default_storage.save(filename, optimized_image)
            url = default_storage.url(path)
            
            # Create ProductImage record
            from products.models import ProductImage
            product_image = ProductImage.objects.create(
                product=product,
                image=path,
                alt_text=f"{product.name} image",
                is_primary=is_primary
            )
            
            return {
                'success': True,
                'image_id': product_image.id,
                'url': url,
                'path': path
            }
        
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    @staticmethod
    def upload_profile_image(entrepreneur, image_file, image_type='profile'):
        """Upload entrepreneur profile or banner image"""
        try:
            # Validate image
            validate_image_file(image_file)
            
            # Generate filename
            filename = generate_unique_filename(
                image_file.name,
                f"entrepreneurs/{entrepreneur.id}/{image_type}/"
            )
            
            # Optimize image
            if image_type == 'banner':
                optimized_image = optimize_image(image_file, max_width=1200, max_height=400)
            else:
                optimized_image = optimize_image(image_file, max_width=400, max_height=400)
            
            # Save to storage
            path = default_storage.save(filename, optimized_image)
            url = default_storage.url(path)
            
            # Update entrepreneur profile
            if image_type == 'profile':
                entrepreneur.profile_image = path
            elif image_type == 'banner':
                entrepreneur.banner_image = path
            entrepreneur.save()
            
            return {
                'success': True,
                'url': url,
                'path': path
            }
        
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    @staticmethod
    def delete_file(file_path):
        """Delete file from storage"""
        try:
            if default_storage.exists(file_path):
                default_storage.delete(file_path)
                return True
            return False
        except Exception as e:
            logger.error(f"File deletion failed: {str(e)}")
            return False
```

**File to Create:** `products/file_api.py`

```python
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from rest_framework.parsers import MultiPartParser, FormParser
from django.shortcuts import get_object_or_404
from .models import Product, ProductImage
from suppliers.models import SupplierProfile
from core.file_utils import FileUploadService

class ProductImageUploadView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    
    def post(self, request, product_id):
        """Upload product image"""
        # Verify user is supplier who owns the product
        if request.user.user_type != 'supplier':
            return Response({
                'error': 'Only suppliers can upload product images'
            }, status=status.HTTP_403_FORBIDDEN)
        
        try:
            supplier = SupplierProfile.objects.get(user=request.user)
            product = Product.objects.get(id=product_id, supplier=supplier)
        except (SupplierProfile.DoesNotExist, Product.DoesNotExist):
            return Response({
                'error': 'Product not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        image_file = request.FILES.get('image')
        if not image_file:
            return Response({
                'error': 'No image file provided'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        is_primary = request.data.get('is_primary', False)
        
        # If setting as primary, unset other primary images
        if is_primary:
            ProductImage.objects.filter(product=product, is_primary=True).update(is_primary=False)
        
        result = FileUploadService.upload_product_image(product, image_file, is_primary)
        
        if result['success']:
            return Response({
                'success': True,
                'image_id': result['image_id'],
                'url': result['url'],
                'message': 'Image uploaded successfully'
            }, status=status.HTTP_201_CREATED)
        else:
            return Response({
                'error': result['error']
            }, status=status.HTTP_400_BAD_REQUEST)
    
    def delete(self, request, product_id, image_id):
        """Delete product image"""
        if request.user.user_type != 'supplier':
            return Response({
                'error': 'Only suppliers can delete product images'
            }, status=status.HTTP_403_FORBIDDEN)
        
        try:
            supplier = SupplierProfile.objects.get(user=request.user)
            product = Product.objects.get(id=product_id, supplier=supplier)
            image = ProductImage.objects.get(id=image_id, product=product)
        except (SupplierProfile.DoesNotExist, Product.DoesNotExist, ProductImage.DoesNotExist):
            return Response({
                'error': 'Image not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Delete file from storage
        FileUploadService.delete_file(image.image.name)
        
        # Delete database record
        image.delete()
        
        return Response({
            'message': 'Image deleted successfully'
        }, status=status.HTTP_200_OK)

class BulkProductImageUploadView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    
    def post(self, request, product_id):
        """Upload multiple product images"""
        if request.user.user_type != 'supplier':
            return Response({
                'error': 'Only suppliers can upload product images'
            }, status=status.HTTP_403_FORBIDDEN)
        
        try:
            supplier = SupplierProfile.objects.get(user=request.user)
            product = Product.objects.get(id=product_id, supplier=supplier)
        except (SupplierProfile.DoesNotExist, Product.DoesNotExist):
            return Response({
                'error': 'Product not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        images = request.FILES.getlist('images')
        if not images:
            return Response({
                'error': 'No image files provided'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        results = []
        primary_set = False
        
        for i, image_file in enumerate(images):
            is_primary = i == 0 and not primary_set  # First image is primary if none set
            result = FileUploadService.upload_product_image(product, image_file, is_primary)
            
            if result['success']:
                primary_set = True
                results.append({
                    'success': True,
                    'image_id': result['image_id'],
                    'url': result['url']
                })
            else:
                results.append({
                    'success': False,
                    'error': result['error']
                })
        
        successful_uploads = [r for r in results if r['success']]
        failed_uploads = [r for r in results if not r['success']]
        
        return Response({
            'message': f'{len(successful_uploads)} images uploaded successfully',
            'successful_uploads': successful_uploads,
            'failed_uploads': failed_uploads
        }, status=status.HTTP_201_CREATED if successful_uploads else status.HTTP_400_BAD_REQUEST)
```

**File to Create:** `entrepreneurs/file_api.py`

```python
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from rest_framework.parsers import MultiPartParser, FormParser
from django.shortcuts import get_object_or_404
from .models import EntrepreneurProfile
from core.file_utils import FileUploadService

class EntrepreneurImageUploadView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    
    def post(self, request, image_type):
        """Upload entrepreneur profile or banner image"""
        if request.user.user_type != 'entrepreneur':
            return Response({
                'error': 'Only entrepreneurs can upload profile images'
            }, status=status.HTTP_403_FORBIDDEN)
        
        if image_type not in ['profile', 'banner']:
            return Response({
                'error': 'Invalid image type. Use "profile" or "banner"'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            entrepreneur = EntrepreneurProfile.objects.get(user=request.user)
        except EntrepreneurProfile.DoesNotExist:
            return Response({
                'error': 'Entrepreneur profile not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        image_file = request.FILES.get('image')
        if not image_file:
            return Response({
                'error': 'No image file provided'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Delete old image if exists
        old_image_path = None
        if image_type == 'profile' and entrepreneur.profile_image:
            old_image_path = entrepreneur.profile_image.name
        elif image_type == 'banner' and entrepreneur.banner_image:
            old_image_path = entrepreneur.banner_image.name
        
        result = FileUploadService.upload_profile_image(entrepreneur, image_file, image_type)
        
        if result['success']:
            # Delete old image
            if old_image_path:
                FileUploadService.delete_file(old_image_path)
            
            return Response({
                'success': True,
                'url': result['url'],
                'message': f'{image_type.title()} image uploaded successfully'
            }, status=status.HTTP_200_OK)
        else:
            return Response({
                'error': result['error']
            }, status=status.HTTP_400_BAD_REQUEST)
```

**Update URL files to include image upload endpoints:**

**Add to:** `products/urls.py`

```python
from .file_api import ProductImageUploadView, BulkProductImageUploadView

# ADD THESE PATTERNS
path('products/<int:product_id>/images/', ProductImageUploadView.as_view(), name='product-image-upload'),
path('products/<int:product_id>/images/<int:image_id>/', ProductImageUploadView.as_view(), name='product-image-delete'),
path('products/<int:product_id>/images/bulk/', BulkProductImageUploadView.as_view(), name='product-images-bulk-upload'),
```

**Add to:** `entrepreneurs/urls.py`

```python
from .file_api import EntrepreneurImageUploadView

# ADD THIS PATTERN
path('images/<str:image_type>/', EntrepreneurImageUploadView.as_view(), name='entrepreneur-image-upload'),
```

**VALIDATION COMMANDS:**
```bash
# Install dependencies
pip install boto3 django-storages pillow

# Test image uploads
python manage.py test products.tests.TestImageUpload
python manage.py test entrepreneurs.tests.TestImageUpload

# Collect static files
python manage.py collectstatic --noinput

# Test endpoints
# POST http://localhost:8000/api/products/products/1/images/
# POST http://localhost:8000/api/entrepreneurs/images/profile/
```

**CRITICAL CHECKPOINTS:**
- [ ] Image uploads work to S3 (or local in development)
- [ ] Images are properly optimized and resized
- [ ] File validation prevents invalid uploads
- [ ] Old images are cleaned up when replaced
- [ ] URLs are accessible and properly formatted

---

## **PHASE 4: SUPPLIER MANAGEMENT SYSTEM**

### **TASK 4.1: Complete Supplier API Implementation**

**File to Create:** `suppliers/api.py`

```python
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.db import transaction
from .models import SupplierProfile
from .serializers import SupplierProfileSerializer, SupplierRegistrationSerializer
from products.models import Product
from products.serializers import ProductSerializer
from orders.models import Order
from orders.serializers import OrderSerializer

class SupplierProfileViewSet(viewsets.ModelViewSet):
    serializer_class = SupplierProfileSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        if self.request.user.user_type == 'supplier':
            return SupplierProfile.objects.filter(user=self.request.user)
        elif self.request.user.user_type == 'admin':
            return SupplierProfile.objects.all()
        return Supplier
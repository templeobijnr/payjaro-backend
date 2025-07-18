from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db import transaction
from django.shortcuts import get_object_or_404
from decimal import Decimal
from .models import Order, OrderItem, OrderStatusHistory
from entrepreneurs.models import EntrepreneurProfile
from products.models import Product, ProductVariation
from payments.models import Earnings
import uuid
from datetime import datetime

class OrderViewSet(viewsets.ModelViewSet):
    serializer_class = None  # Will be set dynamically
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if hasattr(user, 'user_type') and user.user_type == 'customer':
            return Order.objects.filter(customer=user)
        elif hasattr(user, 'user_type') and user.user_type == 'entrepreneur':
            entrepreneur = get_object_or_404(EntrepreneurProfile, user=user)
            return Order.objects.filter(entrepreneur=entrepreneur)
        elif hasattr(user, 'user_type') and user.user_type == 'supplier':
            return Order.objects.filter(supplier__user=user)
        return Order.objects.none()

    def get_serializer_class(self):
        if self.action == 'create':
            from .serializers import OrderCreateSerializer
            return OrderCreateSerializer
        from .serializers import OrderSerializer
        return OrderSerializer

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        from .serializers import OrderCreateSerializer, OrderSerializer
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order_data = serializer.validated_data
        items_data = order_data.pop('items')
        entrepreneur_slug = order_data.pop('entrepreneur_custom_url')
        entrepreneur = get_object_or_404(EntrepreneurProfile, custom_url=entrepreneur_slug)
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
            available_stock = variation.stock_quantity if variation else product.stock_quantity
            if available_stock < quantity:
                inventory_errors.append(f"Insufficient stock for {product.name}. Available: {available_stock}, Requested: {quantity}")
                continue
            base_price = product.base_price
            if variation and hasattr(variation, 'price_modifier') and variation.price_modifier:
                base_price += variation.price_modifier
            item_subtotal = base_price * quantity
            markup_per_item = entrepreneur_price - base_price
            item_markup = markup_per_item * quantity
            item_commission = (entrepreneur_price * quantity) * (entrepreneur.commission_rate / 100)
            item_total = entrepreneur_price * quantity
            if markup_per_item < 0:
                inventory_errors.append(f"Price for {product.name} cannot be less than base price ₦{base_price}")
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
            total_calculations['subtotal'] += item_subtotal
            total_calculations['markup_amount'] += item_markup
            total_calculations['commission_amount'] += item_commission
            total_calculations['total_amount'] += item_total
        if inventory_errors:
            return Response({'errors': inventory_errors}, status=status.HTTP_400_BAD_REQUEST)
        shipping_fee = Decimal('500.00')
        total_calculations['total_amount'] += shipping_fee
        order_id = f"PAY{datetime.now().strftime('%Y%m%d')}{str(uuid.uuid4())[:8].upper()}"
        order = Order.objects.create(
            order_id=order_id,
            customer=request.user,
            entrepreneur=entrepreneur,
            supplier=validated_items[0]['product'].supplier if validated_items else None,
            status='pending',
            subtotal=total_calculations['subtotal'],
            markup_amount=total_calculations['markup_amount'],
            commission_amount=total_calculations['commission_amount'],
            shipping_fee=shipping_fee,
            total_amount=total_calculations['total_amount'],
            payment_status='pending',
            payment_method='',
            shipping_address=order_data.get('shipping_address', {}),
            notes=order_data.get('notes', '')
        )
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
            if item_data['variation']:
                item_data['variation'].stock_quantity -= item_data['quantity']
                item_data['variation'].save()
            else:
                item_data['product'].stock_quantity -= item_data['quantity']
                item_data['product'].save()
        OrderStatusHistory.objects.create(
            order=order,
            status='pending',
            notes='Order created',
            created_by=request.user
        )
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
        from .serializers import OrderSerializer
        order = self.get_object()
        new_status = request.data.get('status')
        notes = request.data.get('notes', '')
        if new_status not in dict(Order._meta.get_field('status').choices).keys():
            return Response({'error': 'Invalid status'}, status=status.HTTP_400_BAD_REQUEST)
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
            return Response({'error': f'Cannot transition from {order.status} to {new_status}'}, status=status.HTTP_400_BAD_REQUEST)
        old_status = order.status
        order.status = new_status
        order.save()
        OrderStatusHistory.objects.create(
            order=order,
            status=new_status,
            notes=notes,
            created_by=request.user
        )
        if new_status == 'cancelled' and old_status == 'pending':
            for item in order.items.all():
                if item.variation:
                    item.variation.stock_quantity += item.quantity
                    item.variation.save()
                else:
                    item.product.stock_quantity += item.quantity
                    item.product.save()
            Earnings.objects.filter(order=order).update(status='cancelled')
        return Response({'message': f'Order status updated to {new_status}', 'order': OrderSerializer(order).data})

    @action(detail=False, methods=['get'])
    def entrepreneur_orders(self, request):
        from .serializers import OrderSerializer
        if not hasattr(request.user, 'user_type') or request.user.user_type != 'entrepreneur':
            return Response({'error': 'Only entrepreneurs can access this endpoint'}, status=status.HTTP_403_FORBIDDEN)
        entrepreneur = get_object_or_404(EntrepreneurProfile, user=request.user)
        orders = Order.objects.filter(entrepreneur=entrepreneur).order_by('-created_at')
        page = self.paginate_queryset(orders)
        if page is not None:
            serializer = OrderSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = OrderSerializer(orders, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def supplier_orders(self, request):
        from .serializers import OrderSerializer
        if not hasattr(request.user, 'user_type') or request.user.user_type != 'supplier':
            return Response({'error': 'Only suppliers can access this endpoint'}, status=status.HTTP_403_FORBIDDEN)
        orders = Order.objects.filter(supplier__user=request.user).order_by('-created_at')
        page = self.paginate_queryset(orders)
        if page is not None:
            serializer = OrderSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = OrderSerializer(orders, many=True)
        return Response(serializer.data) 
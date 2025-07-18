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
        try:
            product = Product.objects.get(id=data['product_id'], is_active=True)
        except Product.DoesNotExist:
            raise serializers.ValidationError("Product not found or inactive")
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
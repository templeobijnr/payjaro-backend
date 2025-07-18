from rest_framework import serializers  # type: ignore
from .models import Product, Category

class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['id', 'name', 'slug', 'parent', 'image', 'is_active', 'sort_order']
        read_only_fields = ['id']

class ProductSerializer(serializers.ModelSerializer):
    category = CategorySerializer(read_only=True)
    class Meta:
        model = Product
        fields = [
            'id', 'name', 'slug', 'description', 'category', 'sku', 'base_price',
            'suggested_markup', 'min_markup', 'max_markup', 'stock_quantity',
            'low_stock_threshold', 'weight', 'dimensions', 'specifications',
            'is_active', 'created_at'
        ]
        read_only_fields = ['id', 'created_at'] 
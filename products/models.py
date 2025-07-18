from django.db import models  # type: ignore
from django.conf import settings  # type: ignore
from suppliers.models import SupplierProfile  # type: ignore

class Category(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)
    parent = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL)
    image = models.ImageField(upload_to='categories/', blank=True, null=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.IntegerField(default=0)

    def __str__(self):
        return self.name

class Product(models.Model):
    name = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)
    description = models.TextField()
    category = models.ForeignKey(Category, on_delete=models.CASCADE)
    supplier = models.ForeignKey(SupplierProfile, on_delete=models.CASCADE)
    sku = models.CharField(max_length=100, unique=True)
    base_price = models.DecimalField(max_digits=12, decimal_places=2)
    suggested_markup = models.FloatField()
    min_markup = models.FloatField(default=0)
    max_markup = models.FloatField(null=True, blank=True)
    stock_quantity = models.IntegerField()
    low_stock_threshold = models.IntegerField(default=10)
    weight = models.FloatField()
    dimensions = models.JSONField(default=dict, blank=True)
    specifications = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class ProductVariation(models.Model):
    product = models.ForeignKey(Product, related_name='variations', on_delete=models.CASCADE)
    variation_type = models.CharField(max_length=100)
    variation_value = models.CharField(max_length=100)
    price_modifier = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    stock_quantity = models.IntegerField()
    sku_suffix = models.CharField(max_length=50)

    def __str__(self):
        return f"{self.product.name} - {self.variation_type}: {self.variation_value}"

class ProductImage(models.Model):
    product = models.ForeignKey(Product, related_name='images', on_delete=models.CASCADE)
    image = models.ImageField(upload_to='products/images/')
    alt_text = models.CharField(max_length=255)
    is_primary = models.BooleanField(default=False)
    sort_order = models.IntegerField(default=0)

    def __str__(self):
        return f"{self.product.name} Image"

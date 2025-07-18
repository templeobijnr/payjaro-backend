from django.contrib import admin  # type: ignore
from .models import Category, Product, ProductVariation, ProductImage

admin.site.register(Category)
admin.site.register(Product)
admin.site.register(ProductVariation)
admin.site.register(ProductImage)

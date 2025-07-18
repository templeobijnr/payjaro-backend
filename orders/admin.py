from django.contrib import admin  # type: ignore
from .models import Order, OrderItem, OrderStatusHistory

admin.site.register(Order)
admin.site.register(OrderItem)
admin.site.register(OrderStatusHistory)

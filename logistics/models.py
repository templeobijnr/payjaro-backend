from django.db import models  # type: ignore
from orders.models import Order  # type: ignore

SHIPMENT_STATUS = [
    ("pending", "Pending"),
    ("in_transit", "In Transit"),
    ("delivered", "Delivered"),
    ("failed", "Failed"),
]

class ShippingZone(models.Model):
    name = models.CharField(max_length=100)
    areas = models.JSONField(default=list)
    base_fee = models.DecimalField(max_digits=10, decimal_places=2)
    per_kg_fee = models.DecimalField(max_digits=10, decimal_places=2)
    free_shipping_threshold = models.DecimalField(max_digits=12, decimal_places=2, null=True)
    estimated_delivery_days = models.IntegerField()
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name

class DeliveryPartner(models.Model):
    name = models.CharField(max_length=100)
    api_endpoint = models.URLField()
    api_key = models.CharField(max_length=255)
    service_areas = models.JSONField(default=list)
    pricing_structure = models.JSONField(default=dict)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name

class Shipment(models.Model):
    order = models.OneToOneField(Order, on_delete=models.CASCADE)
    delivery_partner = models.ForeignKey(DeliveryPartner, null=True, on_delete=models.SET_NULL)
    tracking_number = models.CharField(max_length=100)
    pickup_address = models.JSONField(default=dict)
    delivery_address = models.JSONField(default=dict)
    estimated_delivery = models.DateTimeField()
    actual_delivery = models.DateTimeField(null=True)
    status = models.CharField(max_length=32, choices=SHIPMENT_STATUS)
    tracking_history = models.JSONField(default=list)
    delivery_fee = models.DecimalField(max_digits=10, decimal_places=2)
    notes = models.TextField(blank=True)

    def __str__(self):
        return f"Shipment for {self.order.order_id}"

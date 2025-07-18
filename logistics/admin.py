from django.contrib import admin  # type: ignore
from .models import ShippingZone, DeliveryPartner, Shipment

admin.site.register(ShippingZone)
admin.site.register(DeliveryPartner)
admin.site.register(Shipment)

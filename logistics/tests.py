from django.test import TestCase  # type: ignore
from orders.tests import OrderFactory
from .models import ShippingZone, DeliveryPartner, Shipment

class ShippingZoneFactory:
    counter = 0
    @classmethod
    def create(cls, **kwargs):
        cls.counter += 1
        defaults = {
            'name': f'Zone {cls.counter}',
            'areas': ['Area1', 'Area2'],
            'base_fee': 100.0,
            'per_kg_fee': 10.0,
            'estimated_delivery_days': 3,
        }
        defaults.update(kwargs)
        return ShippingZone.objects.create(**defaults)

class DeliveryPartnerFactory:
    counter = 0
    @classmethod
    def create(cls, **kwargs):
        cls.counter += 1
        defaults = {
            'name': f'Partner {cls.counter}',
            'api_endpoint': f'https://api.partner{cls.counter}.com',
            'api_key': f'KEY{cls.counter}',
            'service_areas': ['Area1', 'Area2'],
            'pricing_structure': {'base': 100, 'per_kg': 10},
        }
        defaults.update(kwargs)
        return DeliveryPartner.objects.create(**defaults)

class ShipmentFactory:
    counter = 0
    @classmethod
    def create(cls, **kwargs):
        cls.counter += 1
        order = kwargs.pop('order', None) or OrderFactory.create()
        delivery_partner = kwargs.pop('delivery_partner', None) or DeliveryPartnerFactory.create()
        defaults = {
            'order': order,
            'delivery_partner': delivery_partner,
            'tracking_number': f'TRACK{cls.counter}',
            'pickup_address': {'address': 'Pickup Address'},
            'delivery_address': {'address': 'Delivery Address'},
            'estimated_delivery': '2024-12-31T00:00:00Z',
            'status': 'pending',
            'delivery_fee': 100.0,
        }
        defaults.update(kwargs)
        return Shipment.objects.create(**defaults)

class LogisticsModelsTest(TestCase):
    def test_shipping_zone_creation(self):
        zone = ShippingZoneFactory.create()
        self.assertIsNotNone(zone.id)

    def test_delivery_partner_creation(self):
        partner = DeliveryPartnerFactory.create()
        self.assertIsNotNone(partner.id)

    def test_shipment_creation(self):
        shipment = ShipmentFactory.create()
        self.assertIsNotNone(shipment.id)

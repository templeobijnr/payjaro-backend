from django.test import TestCase  # type: ignore
from django.contrib.auth import get_user_model  # type: ignore
from entrepreneurs.models import EntrepreneurProfile
from suppliers.models import SupplierProfile
from products.models import Product, ProductVariation
from .models import Order, OrderItem, OrderStatusHistory
from entrepreneurs.tests import UserFactory as EntrepreneurUserFactory, EntrepreneurProfileFactory
from suppliers.tests import UserFactory as SupplierUserFactory, SupplierProfileFactory
from products.tests import CategoryFactory, ProductFactory, ProductVariationFactory

class OrderFactory:
    counter = 0
    @classmethod
    def create(cls, **kwargs):
        cls.counter += 1
        customer = kwargs.pop('customer', None) or EntrepreneurUserFactory.create(user_type='customer')
        entrepreneur = kwargs.pop('entrepreneur', None) or EntrepreneurProfileFactory.create()
        supplier = kwargs.pop('supplier', None) or SupplierProfileFactory.create()
        defaults = {
            'order_id': f'ORDER{cls.counter}',
            'customer': customer,
            'entrepreneur': entrepreneur,
            'supplier': supplier,
            'status': 'pending',
            'subtotal': 1000.0,
            'markup_amount': 100.0,
            'commission_amount': 80.0,
            'shipping_fee': 50.0,
            'total_amount': 1230.0,
            'payment_status': 'pending',
            'payment_method': 'card',
            'shipping_address': {'address': 'Test Address'},
        }
        defaults.update(kwargs)
        return Order.objects.create(**defaults)

class OrderItemFactory:
    counter = 0
    @classmethod
    def create(cls, **kwargs):
        cls.counter += 1
        order = kwargs.pop('order', None) or OrderFactory.create()
        product = kwargs.pop('product', None) or ProductFactory.create()
        defaults = {
            'order': order,
            'product': product,
            'quantity': 2,
            'unit_price': 500.0,
            'base_price': 400.0,
            'markup_amount': 100.0,
            'total_price': 1000.0,
        }
        defaults.update(kwargs)
        return OrderItem.objects.create(**defaults)

class OrderStatusHistoryFactory:
    counter = 0
    @classmethod
    def create(cls, **kwargs):
        cls.counter += 1
        order = kwargs.pop('order', None) or OrderFactory.create()
        created_by = kwargs.pop('created_by', None) or EntrepreneurUserFactory.create()
        defaults = {
            'order': order,
            'status': 'pending',
            'created_by': created_by,
        }
        defaults.update(kwargs)
        return OrderStatusHistory.objects.create(**defaults)

class OrderModelsTest(TestCase):
    def test_order_creation(self):
        order = OrderFactory.create()
        self.assertIsNotNone(order.id)

    def test_order_item_creation(self):
        item = OrderItemFactory.create()
        self.assertIsNotNone(item.id)

    def test_order_status_history_creation(self):
        status = OrderStatusHistoryFactory.create()
        self.assertIsNotNone(status.id)

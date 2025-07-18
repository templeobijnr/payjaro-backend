from django.test import TestCase  # type: ignore
from django.contrib.auth import get_user_model  # type: ignore
from .models import SupplierProfile

class UserFactory:
    counter = 0
    @classmethod
    def create(cls, **kwargs):
        cls.counter += 1
        defaults = {
            'username': f'supplier{cls.counter}',
            'password': 'testpass123',
            'user_type': 'supplier',
            'phone_number': f'081000000{cls.counter}',
            'referral_code': f'SUPREF{cls.counter}',
        }
        defaults.update(kwargs)
        return get_user_model().objects.create_user(**defaults)

class SupplierProfileFactory:
    counter = 0
    @classmethod
    def create(cls, **kwargs):
        cls.counter += 1
        user = kwargs.pop('user', None) or UserFactory.create()
        defaults = {
            'user': user,
            'company_name': f'Supplier Co {cls.counter}',
            'business_registration': f'BR{cls.counter}',
            'tax_id': f'TAX{cls.counter}',
            'address': 'Test address',
            'contact_person': 'Test Person',
            'phone_number': f'081000000{cls.counter}',
            'email': f'supplier{cls.counter}@test.com',
            'commission_rate': 10.0,
            'payment_terms': 'Net 30',
            'minimum_order_value': 1000.0,
        }
        defaults.update(kwargs)
        return SupplierProfile.objects.create(**defaults)

class SupplierProfileTest(TestCase):
    def test_supplier_profile_creation(self):
        profile = SupplierProfileFactory.create()
        self.assertIsNotNone(profile.id)
        self.assertEqual(profile.company_name, f'Supplier Co {SupplierProfileFactory.counter}')

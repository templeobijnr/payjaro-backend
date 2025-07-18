from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model
from entrepreneurs.models import EntrepreneurProfile
from products.models import Product, Category
from social.models import EntrepreneurStorefront
from suppliers.models import SupplierProfile

User = get_user_model()

class PublicStorefrontTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.entrepreneur_user = User.objects.create_user(
            username='entreuser', password='Testpass123!', user_type='entrepreneur', email='entre@test.com', referral_code='ENTREF1', phone_number='08011112222'
        )
        self.entrepreneur = EntrepreneurProfile.objects.create(
            user=self.entrepreneur_user, business_name='Test Biz', custom_url='testbiz', is_active=True
        )
        self.supplier_user = User.objects.create_user(
            username='supplieruser', password='Testpass123!', user_type='supplier', email='sup@test.com', referral_code='SUPREF1', phone_number='08022223333'
        )
        self.supplier = SupplierProfile.objects.create(
            user=self.supplier_user, company_name='Supplier Co', business_registration='BR1', tax_id='TAX1',
            address='Addr', contact_person='Person', phone_number='08000000000', email='sup@test.com',
            commission_rate=10, payment_terms='Net 30', minimum_order_value=1000
        )
        self.category = Category.objects.create(name='Electronics', slug='electronics')
        self.storefront = EntrepreneurStorefront.objects.create(entrepreneur=self.entrepreneur)
        self.product = Product.objects.create(
            name='Test Product', slug='test-product', description='A product', category=self.category,
            supplier=self.supplier, sku='SKU1', base_price=100, suggested_markup=10, stock_quantity=10,
            weight=1.0, is_active=True
        )

    def test_public_storefront(self):
        url = reverse('public-storefront', args=[self.entrepreneur.custom_url])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn('entrepreneur', response.data)
        self.assertIn('products', response.data)

    def test_public_product_detail(self):
        url = reverse('public-product-detail', args=[self.entrepreneur.custom_url, self.product.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['name'], 'Test Product')

    def test_track_storefront_event(self):
        url = reverse('public-storefront-track', args=[self.entrepreneur.custom_url])
        data = {'event_type': 'view', 'product_id': self.product.id}
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['status'], 'success') 
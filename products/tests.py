from django.test import TestCase  # type: ignore
from rest_framework.test import APIClient  # type: ignore
from django.urls import reverse  # type: ignore
from .models import Product, Category
from suppliers.models import SupplierProfile
from django.contrib.auth import get_user_model  # type: ignore
from suppliers.tests import SupplierProfileFactory

User = get_user_model()

class ProductFactory:
    counter = 0
    @classmethod
    def create(cls, **kwargs):
        cls.counter += 1
        category = kwargs.pop('category', None) or CategoryFactory.create()
        supplier = kwargs.pop('supplier', None) or SupplierProfileFactory.create()
        defaults = {
            'name': f'Product {cls.counter}',
            'slug': f'product-{cls.counter}',
            'description': 'Test product',
            'category': category,
            'supplier': supplier,
            'sku': f'SKU{cls.counter}',
            'base_price': 100.0,
            'suggested_markup': 10.0,
            'stock_quantity': 50,
            'weight': 1.0,
        }
        defaults.update(kwargs)
        return Product.objects.create(**defaults)

class ProductVariationFactory:
    counter = 0
    @classmethod
    def create(cls, **kwargs):
        cls.counter += 1
        product = kwargs.pop('product', None) or ProductFactory.create()
        defaults = {
            'product': product,
            'variation_type': 'color',
            'variation_value': f'Value {cls.counter}',
            'stock_quantity': 10,
            'sku_suffix': f'VAR{cls.counter}',
        }
        defaults.update(kwargs)
        return ProductVariation.objects.create(**defaults)

class ProductImageFactory:
    counter = 0
    @classmethod
    def create(cls, **kwargs):
        cls.counter += 1
        product = kwargs.pop('product', None) or ProductFactory.create()
        defaults = {
            'product': product,
            'image': 'test.jpg',
            'alt_text': 'Test image',
        }
        defaults.update(kwargs)
        return ProductImage.objects.create(**defaults)

class CategoryFactory:
    counter = 0
    @classmethod
    def create(cls, **kwargs):
        cls.counter += 1
        defaults = {
            'name': f'Category {cls.counter}',
            'slug': f'category-{cls.counter}',
        }
        defaults.update(kwargs)
        return Category.objects.create(**defaults)

class ProductCatalogAPITest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.category = Category.objects.create(name='Electronics', slug='electronics')
        self.supplier_user = User.objects.create_user(
            username='supplieruser',
            password='Testpass123!',
            user_type='supplier',
            phone_number='08000000000',
            referral_code='SUPREF1',
        )
        self.supplier = SupplierProfile.objects.create(
            user=self.supplier_user, company_name='Supplier', business_registration='BR1', tax_id='TAX1',
            address='Addr', contact_person='Person', phone_number='08000000000', email='sup@test.com',
            commission_rate=10, payment_terms='Net 30', minimum_order_value=1000
        )
        self.product1 = Product.objects.create(
            name='Phone', slug='phone', description='Smartphone', category=self.category, supplier=self.supplier,
            sku='SKU1', base_price=100, suggested_markup=10, stock_quantity=10, weight=0.5
        )
        self.product2 = Product.objects.create(
            name='Laptop', slug='laptop', description='Laptop', category=self.category, supplier=self.supplier,
            sku='SKU2', base_price=500, suggested_markup=15, stock_quantity=5, weight=2.0
        )

    def test_list_products(self):
        url = reverse('product-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 2)

    def test_search_products(self):
        url = reverse('product-list')
        response = self.client.get(url, {'search': 'Phone'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['name'], 'Phone')

    def test_filter_by_category(self):
        url = reverse('product-list')
        response = self.client.get(url, {'category': 'electronics'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 2)

    def test_product_detail(self):
        url = reverse('product-detail', args=[self.product1.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['name'], 'Phone')

    def test_list_categories(self):
        url = reverse('category-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['name'], 'Electronics')

    def test_category_detail(self):
        url = reverse('category-detail', args=[self.category.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['slug'], 'electronics')

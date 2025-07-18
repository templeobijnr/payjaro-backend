from django.test import TestCase  # type: ignore
from rest_framework.test import APIClient  # type: ignore
from django.urls import reverse  # type: ignore
from django.contrib.auth import get_user_model  # type: ignore
from entrepreneurs.models import EntrepreneurProfile
from .models import EntrepreneurStorefront

User = get_user_model()

class EntrepreneurStorefrontAPITest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='entreuser',
            password='Testpass123!',
            user_type='entrepreneur',
            phone_number='08011112222',
            referral_code='ENTREF1',
        )
        self.profile = EntrepreneurProfile.objects.create(
            user=self.user,
            business_name='Test Biz',
            custom_url='testbiz',
            bio='Test bio',
        )
        self.url = reverse('entrepreneur-storefront')

    def authenticate(self):
        self.client.force_authenticate(user=self.user)

    def test_create_storefront_success(self):
        self.authenticate()
        data = {
            'theme': 'default',
            'about_section': 'About my store',
            'contact_info': {'email': 'store@example.com'},
            'social_links': {'instagram': 'myinsta'},
            'seo_title': 'SEO Title',
            'seo_description': 'SEO Desc',
            'is_published': True,
        }
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['about_section'], 'About my store')

    def test_create_storefront_duplicate(self):
        self.authenticate()
        EntrepreneurStorefront.objects.create(
            entrepreneur=self.profile,
            theme='default',
        )
        data = {'theme': 'default'}
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('detail', response.data)

    def test_get_storefront_success(self):
        self.authenticate()
        EntrepreneurStorefront.objects.create(
            entrepreneur=self.profile,
            theme='default',
            about_section='About',
        )
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['about_section'], 'About')

    def test_update_storefront_success(self):
        self.authenticate()
        storefront = EntrepreneurStorefront.objects.create(
            entrepreneur=self.profile,
            theme='default',
            about_section='About',
        )
        data = {'about_section': 'Updated About', 'is_published': False}
        response = self.client.put(self.url, data, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['about_section'], 'Updated About')
        self.assertFalse(response.data['is_published'])

    def test_permission_denied_for_non_entrepreneur(self):
        customer = User.objects.create_user(
            username='customer',
            password='Testpass123!',
            user_type='customer',
            phone_number='08033334444',
            referral_code='CUSTREF1',
        )
        self.client.force_authenticate(user=customer)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)

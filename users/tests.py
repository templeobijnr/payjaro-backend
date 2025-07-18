from django.test import TestCase  # type: ignore
from rest_framework.test import APIClient  # type: ignore
from django.urls import reverse  # type: ignore
from django.contrib.auth import get_user_model  # type: ignore
from entrepreneurs.models import EntrepreneurProfile
from social.models import EntrepreneurStorefront

User = get_user_model()

class UserFactory:
    counter = 0
    @classmethod
    def create(cls, **kwargs):
        cls.counter += 1
        defaults = {
            'username': f'user{cls.counter}',
            'password': 'testpass123',
            'user_type': 'entrepreneur',
            'phone_number': f'080000000{cls.counter}',
            'referral_code': f'REF{cls.counter}',
        }
        defaults.update(kwargs)
        return get_user_model().objects.create_user(**defaults)

class UserModelTest(TestCase):
    def test_user_creation(self):
        user = UserFactory.create()
        self.assertIsNotNone(user.id)
        self.assertEqual(user.user_type, 'entrepreneur')
        self.assertTrue(user.check_password('testpass123'))

class UserAPITest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.register_url = reverse('user-register')
        self.login_url = reverse('token_obtain_pair')
        self.profile_url = reverse('user-profile')
        self.user_data = {
            'username': 'testuser',
            'email': 'testuser@example.com',
            'phone_number': '08012345678',
            'password': 'Testpass123!',
            'password2': 'Testpass123!',
            'user_type': 'entrepreneur',
            'referral_code': 'REF123',
        }

    def test_user_registration(self):
        response = self.client.post(self.register_url, self.user_data, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertTrue(User.objects.filter(username='testuser').exists())

    def test_user_login(self):
        self.client.post(self.register_url, self.user_data, format='json')
        response = self.client.post(self.login_url, {
            'username': 'testuser',
            'password': 'Testpass123!'
        }, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)
        self.token = response.data['access']

    def test_user_profile(self):
        self.client.post(self.register_url, self.user_data, format='json')
        login_response = self.client.post(self.login_url, {
            'username': 'testuser',
            'password': 'Testpass123!'
        }, format='json')
        token = login_response.data['access']
        self.client.credentials(HTTP_AUTHORIZATION='Bearer ' + token)
        response = self.client.get(self.profile_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['username'], 'testuser')

class UserOnboardingFlowTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.register_url = reverse('user-register')
        self.login_url = reverse('token_obtain_pair')
        self.profile_url = reverse('user-profile')
        self.entre_profile_url = reverse('entrepreneur-profile')
        self.storefront_url = reverse('entrepreneur-storefront')
        self.user_data = {
            'username': 'flowuser',
            'email': 'flowuser@example.com',
            'phone_number': '08055556666',
            'password': 'Testpass123!',
            'password2': 'Testpass123!',
            'user_type': 'entrepreneur',
            'referral_code': 'FLOWREF',
        }

    def test_full_onboarding_flow(self):
        # Register
        reg_resp = self.client.post(self.register_url, self.user_data, format='json')
        self.assertEqual(reg_resp.status_code, 201)
        # Login
        login_resp = self.client.post(self.login_url, {
            'username': 'flowuser',
            'password': 'Testpass123!'
        }, format='json')
        self.assertEqual(login_resp.status_code, 200)
        token = login_resp.data['access']
        self.client.credentials(HTTP_AUTHORIZATION='Bearer ' + token)
        # Create entrepreneur profile (POST, not PUT)
        entre_data = {
            'business_name': 'Flow Biz',
            'custom_url': 'flowbiz',
            'bio': 'Flow bio',
        }
        entre_resp = self.client.post(self.entre_profile_url, entre_data, format='json')
        self.assertEqual(entre_resp.status_code, 201)
        self.assertEqual(entre_resp.data['business_name'], 'Flow Biz')
        # Create storefront
        store_data = {
            'theme': 'default',
            'about_section': 'About Flow',
            'contact_info': {'email': 'flow@store.com'},
            'social_links': {'instagram': 'flowinsta'},
            'seo_title': 'Flow SEO',
            'seo_description': 'SEO Desc',
            'is_published': True,
        }
        store_resp = self.client.post(self.storefront_url, store_data, format='json')
        self.assertEqual(store_resp.status_code, 201)
        self.assertEqual(store_resp.data['about_section'], 'About Flow')
        self.assertTrue(store_resp.data['is_published'])

from django.test import TestCase  # type: ignore
from rest_framework.test import APIClient  # type: ignore
from django.urls import reverse  # type: ignore
from django.contrib.auth import get_user_model  # type: ignore
from .models import EntrepreneurProfile
from io import BytesIO
from PIL import Image
from django.core.files.uploadedfile import SimpleUploadedFile  # type: ignore

User = get_user_model()

class EntrepreneurProfileAPITest(TestCase):
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
        self.url = reverse('entrepreneur-profile')

    def authenticate(self):
        self.client.force_authenticate(user=self.user)

    def test_get_profile_success(self):
        self.authenticate()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['business_name'], 'Test Biz')

    def test_update_profile_success(self):
        self.authenticate()
        data = {'bio': 'Updated bio', 'custom_url': 'newbizurl'}
        response = self.client.put(self.url, data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['bio'], 'Updated bio')
        self.assertEqual(response.data['custom_url'], 'newbizurl')

    def test_update_profile_duplicate_url(self):
        other_user = User.objects.create_user(
            username='otherentre',
            password='Testpass123!',
            user_type='entrepreneur',
            phone_number='08022223333',
            referral_code='ENTREF2',
        )
        EntrepreneurProfile.objects.create(
            user=other_user,
            business_name='Other Biz',
            custom_url='uniqueurl',
            bio='Other bio',
        )
        self.authenticate()
        data = {'custom_url': 'uniqueurl'}
        response = self.client.put(self.url, data)
        self.assertEqual(response.status_code, 400)
        self.assertIn('custom_url', response.data)

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

    def test_image_upload(self):
        self.authenticate()
        # Create a simple image in memory
        img = Image.new('RGB', (100, 100), color = (73, 109, 137))
        img_file = BytesIO()
        img.save(img_file, format='JPEG')
        img_file.seek(0)
        uploaded = SimpleUploadedFile('test.jpg', img_file.read(), content_type='image/jpeg')
        data = {
            'profile_image': uploaded,
        }
        response = self.client.put(self.url, data, format='multipart')
        self.assertEqual(response.status_code, 200)
        self.assertIn('profile_image', response.data)

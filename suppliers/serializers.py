from rest_framework import serializers
from .models import SupplierProfile
from django.contrib.auth import get_user_model

User = get_user_model()

class SupplierProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = SupplierProfile
        fields = '__all__'
        read_only_fields = ['id', 'user']

class SupplierRegistrationSerializer(serializers.ModelSerializer):
    username = serializers.CharField(write_only=True)
    password = serializers.CharField(write_only=True)
    email = serializers.EmailField(write_only=True)
    class Meta:
        model = SupplierProfile
        fields = [
            'username', 'password', 'email',
            'company_name', 'business_registration', 'tax_id',
            'address', 'contact_person', 'phone_number',
            'commission_rate', 'payment_terms', 'minimum_order_value'
        ]
    def create(self, validated_data):
        username = validated_data.pop('username')
        password = validated_data.pop('password')
        email = validated_data.pop('email')
        user = User.objects.create_user(
            username=username,
            password=password,
            email=email,
            user_type='supplier'
        )
        supplier = SupplierProfile.objects.create(user=user, **validated_data)
        return supplier 
from rest_framework import serializers  # type: ignore
from .models import EntrepreneurProfile

class EntrepreneurProfileSerializer(serializers.ModelSerializer):
    profile_image = serializers.ImageField(required=False, allow_null=True)
    banner_image = serializers.ImageField(required=False, allow_null=True)

    class Meta:
        model = EntrepreneurProfile
        fields = [
            'id', 'user', 'business_name', 'custom_url', 'bio',
            'profile_image', 'banner_image', 'commission_rate', 'total_sales',
            'total_earnings', 'performance_tier', 'social_media_handles',
            'bank_details', 'crypto_wallets', 'is_active'
        ]
        read_only_fields = ['id', 'user', 'commission_rate', 'total_sales', 'total_earnings', 'performance_tier']

    def validate_custom_url(self, value):
        if EntrepreneurProfile.objects.filter(custom_url=value).exclude(user=self.instance.user if self.instance else None).exists():
            raise serializers.ValidationError("This custom URL is already taken.")
        return value

    def update(self, instance, validated_data):
        # Handle image updates
        profile_image = validated_data.pop('profile_image', None)
        banner_image = validated_data.pop('banner_image', None)
        if profile_image:
            instance.profile_image = profile_image
        if banner_image:
            instance.banner_image = banner_image
        return super().update(instance, validated_data) 
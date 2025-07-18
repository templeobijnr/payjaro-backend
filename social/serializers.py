from rest_framework import serializers  # type: ignore
from .models import EntrepreneurStorefront, FeaturedProduct

class EntrepreneurStorefrontSerializer(serializers.ModelSerializer):
    class Meta:
        model = EntrepreneurStorefront
        fields = [
            'id', 'entrepreneur', 'theme', 'custom_css', 'about_section',
            'contact_info', 'social_links', 'seo_title', 'seo_description',
            'is_published'
        ]
        read_only_fields = ['id', 'entrepreneur']

    def validate_theme(self, value):
        themes = [choice[0] for choice in self.Meta.model._meta.get_field('theme').choices]
        if value not in themes:
            raise serializers.ValidationError("Invalid theme selected.")
        return value

    def update(self, instance, validated_data):
        # Allow partial updates and handle publish/unpublish
        return super().update(instance, validated_data) 
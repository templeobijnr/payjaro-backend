from django.db import models  # type: ignore
from entrepreneurs.models import EntrepreneurProfile  # type: ignore
from products.models import Product  # type: ignore
from orders.models import Order  # type: ignore

THEME_CHOICES = [
    ("default", "Default"),
    ("modern", "Modern"),
    ("classic", "Classic"),
]

SOCIAL_PLATFORMS = [
    ("whatsapp", "WhatsApp"),
    ("instagram", "Instagram"),
    ("facebook", "Facebook"),
    ("twitter", "Twitter"),
]

POST_TYPES = [
    ("story", "Story"),
    ("post", "Post"),
    ("ad", "Ad"),
]

class EntrepreneurStorefront(models.Model):
    entrepreneur = models.OneToOneField(EntrepreneurProfile, on_delete=models.CASCADE)
    theme = models.CharField(max_length=32, choices=THEME_CHOICES, default="default")
    custom_css = models.TextField(blank=True)
    featured_products = models.ManyToManyField(Product, through='FeaturedProduct')
    about_section = models.TextField(blank=True)
    contact_info = models.JSONField(default=dict, blank=True)
    social_links = models.JSONField(default=dict, blank=True)
    seo_title = models.CharField(max_length=255, blank=True)
    seo_description = models.TextField(blank=True)
    is_published = models.BooleanField(default=True)

    def __str__(self):
        return f"Storefront for {self.entrepreneur.business_name}"

class FeaturedProduct(models.Model):
    storefront = models.ForeignKey(EntrepreneurStorefront, on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    sort_order = models.IntegerField(default=0)
    custom_description = models.TextField(blank=True)

    def __str__(self):
        return f"{self.product.name} in {self.storefront.entrepreneur.business_name}"

class SocialPost(models.Model):
    entrepreneur = models.ForeignKey(EntrepreneurProfile, on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    platform = models.CharField(max_length=32, choices=SOCIAL_PLATFORMS)
    post_type = models.CharField(max_length=32, choices=POST_TYPES)
    content = models.TextField()
    media_urls = models.JSONField(default=list, blank=True)
    scheduled_time = models.DateTimeField(null=True)
    posted_time = models.DateTimeField(null=True)
    platform_post_id = models.CharField(max_length=255, blank=True)
    engagement_metrics = models.JSONField(default=dict, blank=True)
    is_posted = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.platform} post for {self.entrepreneur.business_name}"

class ReferralTracking(models.Model):
    entrepreneur = models.ForeignKey(EntrepreneurProfile, on_delete=models.CASCADE)
    source_platform = models.CharField(max_length=32)
    source_url = models.URLField()
    utm_params = models.JSONField(default=dict, blank=True)
    visitor_ip = models.GenericIPAddressField()
    user_agent = models.TextField()
    session_id = models.CharField(max_length=255)
    converted_to_sale = models.BooleanField(default=False)
    order = models.ForeignKey(Order, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Referral for {self.entrepreneur.business_name} from {self.source_platform}"

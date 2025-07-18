from django.db import models  # type: ignore
from django.conf import settings  # type: ignore

PERFORMANCE_TIERS = [
    ("bronze", "Bronze"),
    ("silver", "Silver"),
    ("gold", "Gold"),
    ("platinum", "Platinum"),
]

class EntrepreneurProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    business_name = models.CharField(max_length=100)
    custom_url = models.SlugField(unique=True)
    bio = models.TextField()
    profile_image = models.ImageField(upload_to='entrepreneurs/profile/', blank=True, null=True)
    banner_image = models.ImageField(upload_to='entrepreneurs/banner/', blank=True, null=True)
    commission_rate = models.DecimalField(max_digits=5, decimal_places=2, default=8.00)
    total_sales = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_earnings = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    performance_tier = models.CharField(max_length=20, choices=PERFORMANCE_TIERS, default="bronze")
    social_media_handles = models.JSONField(default=dict, blank=True)
    bank_details = models.JSONField(default=dict, blank=True)
    crypto_wallets = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.business_name

class EntrepreneurMetrics(models.Model):
    entrepreneur = models.ForeignKey(EntrepreneurProfile, on_delete=models.CASCADE)
    date = models.DateField()
    total_views = models.IntegerField(default=0)
    total_clicks = models.IntegerField(default=0)
    total_sales = models.IntegerField(default=0)
    revenue_generated = models.DecimalField(max_digits=12, decimal_places=2)
    commission_earned = models.DecimalField(max_digits=12, decimal_places=2)
    markup_earned = models.DecimalField(max_digits=12, decimal_places=2)
    conversion_rate = models.FloatField()
    average_order_value = models.DecimalField(max_digits=12, decimal_places=2)

    def __str__(self):
        return f"{self.entrepreneur.business_name} - {self.date}"

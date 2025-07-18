from django.db import models  # type: ignore
from django.conf import settings  # type: ignore

VERIFICATION_STATUS = [
    ("pending", "Pending"),
    ("verified", "Verified"),
    ("rejected", "Rejected"),
]

class SupplierProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    company_name = models.CharField(max_length=200)
    business_registration = models.CharField(max_length=100)
    tax_id = models.CharField(max_length=100)
    address = models.TextField()
    contact_person = models.CharField(max_length=100)
    phone_number = models.CharField(max_length=20)
    email = models.EmailField()
    bank_details = models.JSONField(default=dict, blank=True)
    commission_rate = models.DecimalField(max_digits=5, decimal_places=2)
    payment_terms = models.CharField(max_length=100)
    minimum_order_value = models.DecimalField(max_digits=12, decimal_places=2)
    delivery_areas = models.JSONField(default=dict, blank=True)
    business_hours = models.JSONField(default=dict, blank=True)
    verification_status = models.CharField(max_length=20, choices=VERIFICATION_STATUS, default="pending")
    performance_rating = models.FloatField(default=0)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.company_name

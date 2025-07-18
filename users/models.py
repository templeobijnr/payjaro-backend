from django.db import models  # type: ignore
from django.contrib.auth.models import AbstractUser  # type: ignore
from django.utils.translation import gettext_lazy as _  # type: ignore

USER_TYPES = [
    ("entrepreneur", "Entrepreneur"),
    ("supplier", "Supplier"),
    ("customer", "Customer"),
    ("admin", "Admin/Staff"),
    ("logistics", "Logistics Partner"),
]

VERIFICATION_LEVELS = [
    ("basic", "Basic"),
    ("business", "Business"),
    ("enhanced", "Enhanced"),
]

class User(AbstractUser):
    user_type = models.CharField(max_length=32, choices=USER_TYPES)
    phone_number = models.CharField(max_length=20, unique=True)
    bvn = models.CharField(max_length=20, blank=True, null=True)
    nin = models.CharField(max_length=20, blank=True, null=True)
    is_verified = models.BooleanField(default=False)
    verification_level = models.CharField(max_length=32, choices=VERIFICATION_LEVELS, default="basic")
    social_accounts = models.JSONField(default=dict, blank=True)
    referral_code = models.CharField(max_length=20, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.username

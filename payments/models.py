from django.db import models  # type: ignore
from django.conf import settings  # type: ignore
from orders.models import Order  # type: ignore
from entrepreneurs.models import EntrepreneurProfile  # type: ignore

PAYMENT_TYPES = [
    ("card", "Card"),
    ("bank_transfer", "Bank Transfer"),
    ("crypto", "Crypto"),
]

TRANSACTION_TYPES = [
    ("payment", "Payment"),
    ("withdrawal", "Withdrawal"),
    ("refund", "Refund"),
]

TRANSACTION_STATUS = [
    ("pending", "Pending"),
    ("completed", "Completed"),
    ("failed", "Failed"),
    ("refunded", "Refunded"),
]

EARNING_TYPES = [
    ("markup", "Markup"),
    ("commission", "Commission"),
]

EARNING_STATUS = [
    ("pending", "Pending"),
    ("paid", "Paid"),
]

WITHDRAWAL_METHODS = [
    ("bank", "Bank"),
    ("crypto", "Crypto"),
]

WITHDRAWAL_STATUS = [
    ("pending", "Pending"),
    ("processing", "Processing"),
    ("completed", "Completed"),
    ("failed", "Failed"),
]

class PaymentMethod(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    method_type = models.CharField(max_length=32, choices=PAYMENT_TYPES)
    provider = models.CharField(max_length=100)
    provider_id = models.CharField(max_length=100)
    details = models.JSONField(default=dict)
    is_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.user.username} - {self.method_type}"

class Transaction(models.Model):
    transaction_id = models.CharField(max_length=100, unique=True)
    order = models.ForeignKey(Order, null=True, blank=True, on_delete=models.SET_NULL)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    transaction_type = models.CharField(max_length=32, choices=TRANSACTION_TYPES)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=10, default='NGN')
    payment_method = models.ForeignKey(PaymentMethod, on_delete=models.CASCADE)
    status = models.CharField(max_length=32, choices=TRANSACTION_STATUS)
    provider_reference = models.CharField(max_length=100)
    metadata = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.transaction_id

class EscrowAccount(models.Model):
    transaction = models.OneToOneField(Transaction, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    release_date = models.DateTimeField()
    is_released = models.BooleanField(default=False)
    release_conditions = models.JSONField(default=dict)

    def __str__(self):
        return f"Escrow for {self.transaction.transaction_id}"

class Earnings(models.Model):
    entrepreneur = models.ForeignKey(EntrepreneurProfile, on_delete=models.CASCADE)
    order = models.ForeignKey(Order, on_delete=models.CASCADE)
    earning_type = models.CharField(max_length=32, choices=EARNING_TYPES)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=32, choices=EARNING_STATUS)
    payout_date = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.entrepreneur.business_name} - {self.earning_type} - {self.amount}"

class WithdrawalRequest(models.Model):
    entrepreneur = models.ForeignKey(EntrepreneurProfile, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    withdrawal_method = models.CharField(max_length=32, choices=WITHDRAWAL_METHODS)
    destination_details = models.JSONField(default=dict)
    status = models.CharField(max_length=32, choices=WITHDRAWAL_STATUS)
    processing_fee = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    reference_id = models.CharField(max_length=100)
    processed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Withdrawal {self.amount} for {self.entrepreneur.business_name}"

class Wallet(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    pending_balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_earned = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_withdrawn = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    currency = models.CharField(max_length=10, default='NGN')
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Wallet for {self.user.username}"

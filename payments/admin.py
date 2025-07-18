from django.contrib import admin  # type: ignore
from .models import PaymentMethod, Transaction, EscrowAccount, Earnings, WithdrawalRequest, Wallet

admin.site.register(PaymentMethod)
admin.site.register(Transaction)
admin.site.register(EscrowAccount)
admin.site.register(Earnings)
admin.site.register(WithdrawalRequest)
admin.site.register(Wallet)

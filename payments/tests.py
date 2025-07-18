from django.test import TestCase  # type: ignore
from django.contrib.auth import get_user_model  # type: ignore
from entrepreneurs.tests import UserFactory as EntrepreneurUserFactory, EntrepreneurProfileFactory
from orders.tests import OrderFactory
from .models import PaymentMethod, Transaction, EscrowAccount, Earnings, WithdrawalRequest, Wallet
from entrepreneurs.models import EntrepreneurProfile

class PaymentMethodFactory:
    counter = 0
    @classmethod
    def create(cls, **kwargs):
        cls.counter += 1
        user = kwargs.pop('user', None) or EntrepreneurUserFactory.create()
        defaults = {
            'user': user,
            'method_type': 'card',
            'provider': 'Paystack',
            'provider_id': f'PID{cls.counter}',
            'details': {'card': '**** **** **** 1234'},
        }
        defaults.update(kwargs)
        return PaymentMethod.objects.create(**defaults)

class TransactionFactory:
    counter = 0
    @classmethod
    def create(cls, **kwargs):
        cls.counter += 1
        user = kwargs.pop('user', None) or EntrepreneurUserFactory.create()
        payment_method = kwargs.pop('payment_method', None) or PaymentMethodFactory.create(user=user)
        defaults = {
            'transaction_id': f'TXN{cls.counter}',
            'user': user,
            'transaction_type': 'payment',
            'amount': 1000.0,
            'payment_method': payment_method,
            'status': 'completed',
            'provider_reference': f'REF{cls.counter}',
        }
        defaults.update(kwargs)
        return Transaction.objects.create(**defaults)

class EscrowAccountFactory:
    counter = 0
    @classmethod
    def create(cls, **kwargs):
        cls.counter += 1
        transaction = kwargs.pop('transaction', None) or TransactionFactory.create()
        defaults = {
            'transaction': transaction,
            'amount': 1000.0,
            'release_date': '2024-12-31T00:00:00Z',
            'release_conditions': {'condition': 'delivered'},
        }
        defaults.update(kwargs)
        return EscrowAccount.objects.create(**defaults)

class EarningsFactory:
    counter = 0
    @classmethod
    def create(cls, **kwargs):
        cls.counter += 1
        entrepreneur = kwargs.pop('entrepreneur', None) or EntrepreneurProfileFactory.create()
        order = kwargs.pop('order', None) or OrderFactory.create(entrepreneur=entrepreneur)
        defaults = {
            'entrepreneur': entrepreneur,
            'order': order,
            'earning_type': 'markup',
            'amount': 100.0,
            'status': 'pending',
        }
        defaults.update(kwargs)
        return Earnings.objects.create(**defaults)

class WithdrawalRequestFactory:
    counter = 0
    @classmethod
    def create(cls, **kwargs):
        cls.counter += 1
        entrepreneur = kwargs.pop('entrepreneur', None) or EntrepreneurProfileFactory.create()
        defaults = {
            'entrepreneur': entrepreneur,
            'amount': 500.0,
            'withdrawal_method': 'bank',
            'destination_details': {'bank': 'Test Bank'},
            'status': 'pending',
            'reference_id': f'WREF{cls.counter}',
        }
        defaults.update(kwargs)
        return WithdrawalRequest.objects.create(**defaults)

class WalletFactory:
    counter = 0
    @classmethod
    def create(cls, **kwargs):
        cls.counter += 1
        user = kwargs.pop('user', None) or EntrepreneurUserFactory.create()
        defaults = {
            'user': user,
        }
        defaults.update(kwargs)
        return Wallet.objects.create(**defaults)

class PaymentsModelsTest(TestCase):
    def test_payment_method_creation(self):
        pm = PaymentMethodFactory.create()
        self.assertIsNotNone(pm.id)

    def test_transaction_creation(self):
        txn = TransactionFactory.create()
        self.assertIsNotNone(txn.id)

    def test_escrow_account_creation(self):
        escrow = EscrowAccountFactory.create()
        self.assertIsNotNone(escrow.id)

    def test_earnings_creation(self):
        earning = EarningsFactory.create()
        self.assertIsNotNone(earning.id)

    def test_withdrawal_request_creation(self):
        withdrawal = WithdrawalRequestFactory.create()
        self.assertIsNotNone(withdrawal.id)

    def test_wallet_creation(self):
        wallet = WalletFactory.create()
        self.assertIsNotNone(wallet.id)

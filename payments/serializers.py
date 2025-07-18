from rest_framework import serializers
from .models import PaymentMethod, Transaction, Earnings, WithdrawalRequest, Wallet
from orders.serializers import OrderSerializer

class PaymentMethodSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentMethod
        fields = [
            'id', 'method_type', 'provider', 'details', 
            'is_default', 'is_active'
        ]
        read_only_fields = ['id']
    def validate_details(self, value):
        method_type = self.initial_data.get('method_type')
        if method_type == 'bank_transfer':
            required_fields = ['account_number', 'bank_code', 'account_name']
            for field in required_fields:
                if field not in value:
                    raise serializers.ValidationError(f"Bank transfer requires {field}")
        elif method_type == 'crypto':
            required_fields = ['wallet_address', 'crypto_type']
            for field in required_fields:
                if field not in value:
                    raise serializers.ValidationError(f"Crypto payment requires {field}")
        return value

class TransactionSerializer(serializers.ModelSerializer):
    order = OrderSerializer(read_only=True)
    class Meta:
        model = Transaction
        fields = [
            'id', 'transaction_id', 'order', 'transaction_type',
            'amount', 'currency', 'status', 'provider_reference',
            'metadata', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']

class EarningsSerializer(serializers.ModelSerializer):
    order = OrderSerializer(read_only=True)
    class Meta:
        model = Earnings
        fields = [
            'id', 'order', 'earning_type', 'amount', 'status',
            'payout_date', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']

class WithdrawalRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = WithdrawalRequest
        fields = [
            'id', 'amount', 'withdrawal_method', 'destination_details',
            'status', 'processing_fee', 'reference_id', 'processed_at',
            'created_at'
        ]
        read_only_fields = [
            'id', 'status', 'processing_fee', 'reference_id', 
            'processed_at', 'created_at'
        ]

class WalletSerializer(serializers.ModelSerializer):
    class Meta:
        model = Wallet
        fields = [
            'id', 'balance', 'pending_balance', 'total_earned',
            'total_withdrawn', 'currency', 'updated_at'
        ]
        read_only_fields = ['id', 'updated_at'] 
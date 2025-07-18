import os
import hashlib
import hmac
import json
import requests
from decimal import Decimal
from django.conf import settings
from .models import Transaction, PaymentMethod
import logging

logger = logging.getLogger(__name__)

class PaystackService:
    def __init__(self):
        self.secret_key = settings.PAYSTACK_SECRET_KEY
        self.public_key = settings.PAYSTACK_PUBLIC_KEY
        self.base_url = "https://api.paystack.co"
    def _make_request(self, method, endpoint, data=None):
        headers = {
            'Authorization': f'Bearer {self.secret_key}',
            'Content-Type': 'application/json'
        }
        url = f"{self.base_url}{endpoint}"
        try:
            if method == 'POST':
                response = requests.post(url, headers=headers, json=data)
            elif method == 'GET':
                response = requests.get(url, headers=headers, params=data)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Paystack API request failed: {str(e)}")
            raise Exception(f"Payment service error: {str(e)}")
    def initialize_payment(self, order, callback_url):
        amount_kobo = int(order.total_amount * 100)
        data = {
            'email': order.customer.email,
            'amount': amount_kobo,
            'currency': 'NGN',
            'reference': f"PAY_{order.order_id}_{order.id}",
            'callback_url': callback_url,
            'metadata': {
                'order_id': order.order_id,
                'customer_id': order.customer.id,
                'entrepreneur_id': order.entrepreneur.id,
                'order_total': str(order.total_amount)
            }
        }
        try:
            response = self._make_request('POST', '/transaction/initialize', data)
            if response.get('status'):
                return {
                    'success': True,
                    'authorization_url': response['data']['authorization_url'],
                    'access_code': response['data']['access_code'],
                    'reference': response['data']['reference']
                }
            else:
                return {
                    'success': False,
                    'message': response.get('message', 'Payment initialization failed')
                }
        except Exception as e:
            return {
                'success': False,
                'message': str(e)
            }
    def verify_payment(self, reference):
        try:
            response = self._make_request('GET', f'/transaction/verify/{reference}')
            if response.get('status'):
                data = response['data']
                return {
                    'success': True,
                    'status': data['status'],
                    'amount': Decimal(str(data['amount'])) / 100,
                    'currency': data['currency'],
                    'reference': data['reference'],
                    'paid_at': data['paid_at'],
                    'metadata': data.get('metadata', {}),
                    'gateway_response': data.get('gateway_response', '')
                }
            else:
                return {
                    'success': False,
                    'message': response.get('message', 'Payment verification failed')
                }
        except Exception as e:
            return {
                'success': False,
                'message': str(e)
            }
    def verify_webhook_signature(self, payload, signature):
        computed_signature = hmac.new(
            self.secret_key.encode('utf-8'),
            payload,
            hashlib.sha512
        ).hexdigest()
        return hmac.compare_digest(computed_signature, signature)

class FlutterwaveService:
    def __init__(self):
        self.secret_key = settings.FLUTTERWAVE_SECRET_KEY
        self.public_key = settings.FLUTTERWAVE_PUBLIC_KEY
        self.base_url = "https://api.flutterwave.com/v3"
    def _make_request(self, method, endpoint, data=None):
        headers = {
            'Authorization': f'Bearer {self.secret_key}',
            'Content-Type': 'application/json'
        }
        url = f"{self.base_url}{endpoint}"
        try:
            if method == 'POST':
                response = requests.post(url, headers=headers, json=data)
            elif method == 'GET':
                response = requests.get(url, headers=headers, params=data)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Flutterwave API request failed: {str(e)}")
            raise Exception(f"Payment service error: {str(e)}")
    def initialize_payment(self, order, callback_url):
        data = {
            'tx_ref': f"FLW_{order.order_id}_{order.id}",
            'amount': str(order.total_amount),
            'currency': 'NGN',
            'redirect_url': callback_url,
            'customer': {
                'email': order.customer.email,
                'phonenumber': order.customer.phone_number,
                'name': f"{order.customer.first_name} {order.customer.last_name}"
            },
            'customizations': {
                'title': 'Payjaro Order Payment',
                'description': f'Payment for order {order.order_id}',
                'logo': 'https://your-logo-url.com/logo.png'
            },
            'meta': {
                'order_id': order.order_id,
                'customer_id': order.customer.id,
                'entrepreneur_id': order.entrepreneur.id
            }
        }
        try:
            response = self._make_request('POST', '/payments', data)
            if response.get('status') == 'success':
                return {
                    'success': True,
                    'payment_link': response['data']['link'],
                    'reference': data['tx_ref']
                }
            else:
                return {
                    'success': False,
                    'message': response.get('message', 'Payment initialization failed')
                }
        except Exception as e:
            return {
                'success': False,
                'message': str(e)
            }
    def verify_payment(self, transaction_id):
        try:
            response = self._make_request('GET', f'/transactions/{transaction_id}/verify')
            if response.get('status') == 'success':
                data = response['data']
                return {
                    'success': True,
                    'status': data['status'],
                    'amount': Decimal(str(data['amount'])),
                    'currency': data['currency'],
                    'reference': data['tx_ref'],
                    'flw_ref': data['flw_ref'],
                    'metadata': data.get('meta', {})
                }
            else:
                return {
                    'success': False,
                    'message': response.get('message', 'Payment verification failed')
                }
        except Exception as e:
            return {
                'success': False,
                'message': str(e)
            } 
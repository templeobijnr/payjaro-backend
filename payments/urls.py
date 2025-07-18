from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .api import (
    PaymentMethodViewSet, PaymentInitiationView, PaystackWebhookView,
    EarningsViewSet, WithdrawalViewSet
)

router = DefaultRouter()
router.register(r'payment-methods', PaymentMethodViewSet, basename='payment-method')
router.register(r'earnings', EarningsViewSet, basename='earnings')
router.register(r'withdrawals', WithdrawalViewSet, basename='withdrawal')

urlpatterns = [
    path('', include(router.urls)),
    path('initialize/', PaymentInitiationView.as_view(), name='payment-initialize'),
    path('webhooks/paystack/', PaystackWebhookView.as_view(), name='paystack-webhook'),
] 
from django.urls import path  # type: ignore
from .api import EntrepreneurStorefrontView

urlpatterns = [
    path('storefront/', EntrepreneurStorefrontView.as_view(), name='entrepreneur-storefront'),
] 
from django.urls import path
from .views import public_storefront, public_product_detail, track_storefront_event

urlpatterns = [
    path('storefront/<str:custom_url>/', public_storefront, name='public-storefront'),
    path('storefront/<str:custom_url>/products/<int:product_id>/', public_product_detail, name='public-product-detail'),
    path('storefront/<str:custom_url>/track/', track_storefront_event, name='public-storefront-track'),
] 
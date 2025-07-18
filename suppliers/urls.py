from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .api import SupplierProfileViewSet

router = DefaultRouter()
router.register(r'profiles', SupplierProfileViewSet, basename='supplier-profile')

urlpatterns = [
    path('', include(router.urls)),
] 
"""
URL configuration for payjaro_project project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin  # type: ignore
from django.urls import path, include  # type: ignore
from rest_framework import permissions  # type: ignore
from drf_yasg.views import get_schema_view  # type: ignore
from drf_yasg import openapi  # type: ignore
from django.conf import settings  # type: ignore
from django.conf.urls.static import static  # type: ignore

schema_view = get_schema_view(
    openapi.Info(
        title="Payjaro API",
        default_version='v1',
        description="API documentation for Payjaro platform",
    ),
    public=True,
    permission_classes=(permissions.AllowAny,),
)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('public.urls')),
    path('api/users/', include('users.urls')),
    path('api/entrepreneurs/', include('entrepreneurs.urls')),
    path('api/social/', include('social.urls')),
    path('api/products/', include('products.urls')),
    path('api/orders/', include('orders.urls')),
    path('api/payments/', include('payments.urls')),
    path('api/suppliers/', include('suppliers.urls')),
    path('swagger/', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
    path('redoc/', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

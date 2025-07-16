from django.contrib import admin
from django.urls import path

from .views import payjaro

urlpatterns = [
    path("accounts/", payjaro, name='home'),
]

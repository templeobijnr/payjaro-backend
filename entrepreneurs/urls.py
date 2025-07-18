from django.urls import path  # type: ignore
from .api import EntrepreneurProfileView

urlpatterns = [
    path('profile/', EntrepreneurProfileView.as_view(), name='entrepreneur-profile'),
] 
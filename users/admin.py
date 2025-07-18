from django.contrib import admin  # type: ignore
from .models import User

admin.site.register(User)

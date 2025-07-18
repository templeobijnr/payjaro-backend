from django.contrib import admin  # type: ignore
from .models import EntrepreneurProfile, EntrepreneurMetrics

admin.site.register(EntrepreneurProfile)
admin.site.register(EntrepreneurMetrics)

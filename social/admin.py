from django.contrib import admin  # type: ignore
from .models import EntrepreneurStorefront, FeaturedProduct, SocialPost, ReferralTracking

admin.site.register(EntrepreneurStorefront)
admin.site.register(FeaturedProduct)
admin.site.register(SocialPost)
admin.site.register(ReferralTracking)

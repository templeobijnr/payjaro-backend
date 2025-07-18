from rest_framework.views import APIView  # type: ignore
from rest_framework.response import Response  # type: ignore
from rest_framework import status, permissions  # type: ignore
from .models import EntrepreneurStorefront
from .serializers import EntrepreneurStorefrontSerializer
from entrepreneurs.models import EntrepreneurProfile

class IsEntrepreneur(permissions.BasePermission):
    """Allows access only to users with user_type='entrepreneur'."""
    def has_permission(self, request, view):
        return request.user.is_authenticated and getattr(request.user, 'user_type', None) == 'entrepreneur'

class EntrepreneurStorefrontView(APIView):
    """
    Create, retrieve, or update the authenticated entrepreneur's storefront.
    Only accessible to users with user_type='entrepreneur'.
    """
    permission_classes = [permissions.IsAuthenticated, IsEntrepreneur]

    def get(self, request, *args, **kwargs):
        try:
            profile = EntrepreneurProfile.objects.get(user=request.user)
            storefront = EntrepreneurStorefront.objects.get(entrepreneur=profile)
        except (EntrepreneurProfile.DoesNotExist, EntrepreneurStorefront.DoesNotExist):
            return Response({"detail": "Storefront not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = EntrepreneurStorefrontSerializer(storefront)
        return Response(serializer.data)

    def post(self, request, *args, **kwargs):
        try:
            profile = EntrepreneurProfile.objects.get(user=request.user)
        except EntrepreneurProfile.DoesNotExist:
            return Response({"detail": "Entrepreneur profile not found."}, status=status.HTTP_404_NOT_FOUND)
        if EntrepreneurStorefront.objects.filter(entrepreneur=profile).exists():
            return Response({"detail": "Storefront already exists."}, status=status.HTTP_400_BAD_REQUEST)
        data = request.data.copy()
        data['entrepreneur'] = profile.id
        serializer = EntrepreneurStorefrontSerializer(data=data)
        if serializer.is_valid():
            serializer.save(entrepreneur=profile)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def put(self, request, *args, **kwargs):
        try:
            profile = EntrepreneurProfile.objects.get(user=request.user)
            storefront = EntrepreneurStorefront.objects.get(entrepreneur=profile)
        except (EntrepreneurProfile.DoesNotExist, EntrepreneurStorefront.DoesNotExist):
            return Response({"detail": "Storefront not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = EntrepreneurStorefrontSerializer(storefront, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST) 
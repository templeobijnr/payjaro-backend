from rest_framework.views import APIView  # type: ignore
from rest_framework.response import Response  # type: ignore
from rest_framework import status, permissions  # type: ignore
from .models import EntrepreneurProfile
from .serializers import EntrepreneurProfileSerializer

class IsEntrepreneur(permissions.BasePermission):
    """Allows access only to users with user_type='entrepreneur'."""
    def has_permission(self, request, view):
        return request.user.is_authenticated and getattr(request.user, 'user_type', None) == 'entrepreneur'

class EntrepreneurProfileView(APIView):
    """
    Retrieve or update the authenticated entrepreneur's profile.
    Only accessible to users with user_type='entrepreneur'.
    """
    permission_classes = [permissions.IsAuthenticated, IsEntrepreneur]

    def get(self, request, *args, **kwargs):
        try:
            profile = EntrepreneurProfile.objects.get(user=request.user)
        except EntrepreneurProfile.DoesNotExist:
            return Response({"detail": "Profile not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = EntrepreneurProfileSerializer(profile)
        return Response(serializer.data)

    def put(self, request, *args, **kwargs):
        try:
            profile = EntrepreneurProfile.objects.get(user=request.user)
        except EntrepreneurProfile.DoesNotExist:
            return Response({"detail": "Profile not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = EntrepreneurProfileSerializer(profile, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def post(self, request, *args, **kwargs):
        # Create entrepreneur profile if it does not exist
        if EntrepreneurProfile.objects.filter(user=request.user).exists():
            return Response({"detail": "Profile already exists."}, status=status.HTTP_400_BAD_REQUEST)
        data = request.data.copy()
        data['user'] = request.user.id
        serializer = EntrepreneurProfileSerializer(data=data)
        if serializer.is_valid():
            serializer.save(user=request.user)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST) 
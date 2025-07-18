from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.db import transaction
from .models import SupplierProfile
from .serializers import SupplierProfileSerializer, SupplierRegistrationSerializer
from products.models import Product
from products.serializers import ProductSerializer

class SupplierProfileViewSet(viewsets.ModelViewSet):
    queryset = SupplierProfile.objects.all()
    serializer_class = SupplierProfileSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if hasattr(user, 'user_type') and user.user_type == 'supplier':
            return SupplierProfile.objects.filter(user=user)
        return SupplierProfile.objects.none()

    @action(detail=False, methods=['post'], permission_classes=[permissions.AllowAny])
    def register(self, request):
        serializer = SupplierRegistrationSerializer(data=request.data)
        if serializer.is_valid():
            supplier = serializer.save()
            return Response(SupplierProfileSerializer(supplier).data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['get'])
    def dashboard(self, request):
        user = request.user
        if not hasattr(user, 'user_type') or user.user_type != 'supplier':
            return Response({'error': 'Only suppliers can access this endpoint'}, status=status.HTTP_403_FORBIDDEN)
        supplier = get_object_or_404(SupplierProfile, user=user)
        products = Product.objects.filter(supplier=supplier)
        return Response({
            'profile': SupplierProfileSerializer(supplier).data,
            'products': ProductSerializer(products, many=True).data
        }) 
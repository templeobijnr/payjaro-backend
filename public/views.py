from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from entrepreneurs.models import EntrepreneurProfile
from social.models import EntrepreneurStorefront, FeaturedProduct
from products.models import Product
from products.serializers import ProductSerializer
from entrepreneurs.serializers import EntrepreneurProfileSerializer
from social.serializers import EntrepreneurStorefrontSerializer

@api_view(['GET'])
@permission_classes([AllowAny])
def public_storefront(request, custom_url):
    """Public endpoint to view an entrepreneur's storefront and featured products."""
    entrepreneur = get_object_or_404(EntrepreneurProfile, custom_url=custom_url, is_active=True)
    storefront = get_object_or_404(EntrepreneurStorefront, entrepreneur=entrepreneur)
    featured_products = FeaturedProduct.objects.filter(storefront=storefront)
    # For demo, show all active products (in real app, filter by entrepreneur's suppliers/products)
    products = Product.objects.filter(is_active=True)
    return Response({
        'entrepreneur': EntrepreneurProfileSerializer(entrepreneur).data,
        'storefront': EntrepreneurStorefrontSerializer(storefront).data,
        'featured_products': ProductSerializer([fp.product for fp in featured_products], many=True).data,
        'products': ProductSerializer(products, many=True).data
    })

@api_view(['GET'])
@permission_classes([AllowAny])
def public_product_detail(request, custom_url, product_id):
    """Public endpoint to view a single product in an entrepreneur's storefront."""
    entrepreneur = get_object_or_404(EntrepreneurProfile, custom_url=custom_url, is_active=True)
    # For demo, just get the product by id and is_active
    product = get_object_or_404(Product, id=product_id, is_active=True)
    return Response(ProductSerializer(product).data)

@api_view(['POST'])
@permission_classes([AllowAny])
def track_storefront_event(request, custom_url):
    """Track analytics event for storefront views, clicks, etc."""
    event_type = request.data.get('event_type')
    product_id = request.data.get('product_id')
    metadata = request.data.get('metadata', {})
    # Add request metadata
    metadata.update({
        'visitor_ip': request.META.get('REMOTE_ADDR'),
        'user_agent': request.META.get('HTTP_USER_AGENT'),
        'referrer': request.META.get('HTTP_REFERER')
    })
    # Here you would call your analytics service or model
    # For now, just return success
    return Response({'status': 'success', 'event_type': event_type, 'product_id': product_id, 'metadata': metadata}) 
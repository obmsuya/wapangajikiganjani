from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import PropertyViewSet, PropertyTypeViewSet, PropertyRegistrationViewSet

router = DefaultRouter()
router.register(r'properties', PropertyViewSet, basename='property')
router.register(r'property-types', PropertyTypeViewSet, basename='property-type')
router.register('properties/registration', PropertyRegistrationViewSet, basename='property-registration')

urlpatterns = [
    path('', include(router.urls)),
]
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    BrandProfileViewSet,
    CompetitorViewSet,
    SocialPostViewSet,
    GeneratedIdeaViewSet,
)

# The DefaultRouter automatically creates the URLs for GET, POST, PUT, DELETE for each ViewSet
router = DefaultRouter()
router.register(r'brands', BrandProfileViewSet, basename='brand')
router.register(r'competitors', CompetitorViewSet, basename='competitor')
router.register(r'posts', SocialPostViewSet, basename='post')
router.register(r'ideas', GeneratedIdeaViewSet, basename='idea')

urlpatterns = [
    path('', include(router.urls)),
]

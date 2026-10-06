from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import BrandProfile, Competitor, SocialPost, GeneratedIdea
from .serializers import (
    BrandProfileSerializer,
    CompetitorSerializer,
    SocialPostSerializer,
    GeneratedIdeaSerializer,
)


class BrandProfileViewSet(viewsets.ModelViewSet):
    """
    API endpoint for managing Brand Profiles.
    Provides GET, POST, PUT, DELETE out of the box.
    """
    queryset = BrandProfile.objects.all()
    serializer_class = BrandProfileSerializer


class CompetitorViewSet(viewsets.ModelViewSet):
    """
    API endpoint for adding and viewing competitor/inspiration accounts.
    """
    queryset = Competitor.objects.all()
    serializer_class = CompetitorSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        brand_id = self.request.query_params.get('brand')
        if brand_id:
            queryset = queryset.filter(brand_id=brand_id)
        return queryset


class SocialPostViewSet(viewsets.ModelViewSet):
    """
    API endpoint for social media posts (both scraped and manually input).
    """
    queryset = SocialPost.objects.all()
    serializer_class = SocialPostSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        brand_id = self.request.query_params.get('brand')
        platform = self.request.query_params.get('platform')
        
        if brand_id:
            queryset = queryset.filter(brand_id=brand_id)
        if platform:
            queryset = queryset.filter(platform=platform)
            
        return queryset

    def perform_create(self, serializer):
        # When creating a post, check if outlier_score >= 2.5 to mark as outlier
        outlier_score = serializer.validated_data.get('outlier_score', 1.0)
        is_outlier = outlier_score >= 2.5
        serializer.save(is_manual=True, is_outlier=is_outlier)

    @action(detail=False, methods=['get'])
    def outliers(self, request):
        """
        GET /api/posts/outliers/
        Returns only posts identified as viral outliers (outlier_score >= 2.5).
        """
        outliers = self.get_queryset().filter(is_outlier=True)
        serializer = self.get_serializer(outliers, many=True)
        return Response(serializer.data)


class GeneratedIdeaViewSet(viewsets.ModelViewSet):
    """
    API endpoint for viewing and managing AI-generated post concepts and scripts.
    """
    queryset = GeneratedIdea.objects.all()
    serializer_class = GeneratedIdeaSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        brand_id = self.request.query_params.get('brand')
        platform = self.request.query_params.get('platform')

        if brand_id:
            queryset = queryset.filter(brand_id=brand_id)
        if platform:
            queryset = queryset.filter(target_platform=platform)

        return queryset

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import BrandProfile, Competitor, SocialPost, GeneratedIdea, MonthlyReport
from .serializers import (
    BrandProfileSerializer,
    CompetitorSerializer,
    SocialPostSerializer,
    GeneratedIdeaSerializer,
    MonthlyReportSerializer,
)
from .ai_service import generate_content_ideas, generate_monthly_report


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

    @action(detail=True, methods=['post'])
    def generate_ideas(self, request, pk=None):
        """
        POST /api/posts/{id}/generate_ideas/
        Takes this viral post and uses Gemini AI to generate 3 tailored scripts
        (TikTok, LinkedIn, Instagram) for the associated brand.
        Saves the results directly into GeneratedIdea table.
        """
        post = self.get_object()
        brand = post.brand

        try:
            ai_result = generate_content_ideas(
                brand_name=brand.name,
                brand_niche=brand.niche,
                target_audience=brand.target_audience,
                tone_of_voice=brand.tone_of_voice,
                post_hook=post.hook_text,
                post_content=post.full_content or post.hook_text,
            )

            created_ideas = []
            why_it_worked = ai_result.get("why_it_worked", "")

            for idea_data in ai_result.get("ideas", []):
                idea = GeneratedIdea.objects.create(
                    brand=brand,
                    source_post=post,
                    target_platform=idea_data.get("target_platform"),
                    title=idea_data.get("title"),
                    hook=idea_data.get("hook"),
                    body_content=idea_data.get("body_content"),
                    why_it_works=why_it_worked,
                )
                created_ideas.append(idea)

            serializer = GeneratedIdeaSerializer(created_ideas, many=True)
            return Response({
                "why_it_worked": why_it_worked,
                "ideas": serializer.data
            }, status=status.HTTP_201_CREATED)

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


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


class MonthlyReportViewSet(viewsets.ModelViewSet):
    """
    API endpoint for viewing, creating, and generating Executive Monthly Reports.
    """
    queryset = MonthlyReport.objects.all()
    serializer_class = MonthlyReportSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        brand_id = self.request.query_params.get('brand')
        if brand_id:
            queryset = queryset.filter(brand_id=brand_id)
        return queryset

    @action(detail=False, methods=['post'])
    def generate(self, request):
        """
        POST /api/reports/generate/
        Body: {
          "brand_id": 1,
          "month_year": "October 2026",
          "raw_metrics": { "reach": 50000, "followers_growth": 1200, ... }
        }
        Calls Gemini to create the Executive Summary, Insights, and Next Steps,
        then saves the report to the database.
        """
        brand_id = request.data.get('brand_id')
        month_year = request.data.get('month_year')
        raw_metrics = request.data.get('raw_metrics', {})

        if not brand_id or not month_year:
            return Response(
                {"error": "brand_id and month_year are required fields."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            brand = BrandProfile.objects.get(id=brand_id)
        except BrandProfile.DoesNotExist:
            return Response({"error": "Brand not found."}, status=status.HTTP_404_NOT_FOUND)

        try:
            ai_report = generate_monthly_report(
                brand_name=brand.name,
                brand_niche=brand.niche,
                month_year=month_year,
                metrics_data=raw_metrics
            )

            report = MonthlyReport.objects.create(
                brand=brand,
                month_year=month_year,
                raw_metrics=raw_metrics,
                executive_summary=ai_report.get("executive_summary", ""),
                key_insights=ai_report.get("key_insights", []),
                next_month_strategy=ai_report.get("next_month_strategy", {}),
            )

            serializer = self.get_serializer(report)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

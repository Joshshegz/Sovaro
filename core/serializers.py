from rest_framework import serializers
from .models import BrandProfile, Competitor, SocialPost, GeneratedIdea


class CompetitorSerializer(serializers.ModelSerializer):
    """Translates Competitor data to and from JSON."""
    class Meta:
        model = Competitor
        fields = ['id', 'brand', 'platform', 'handle', 'profile_url', 'created_at']
        read_only_fields = ['id', 'created_at']


class BrandProfileSerializer(serializers.ModelSerializer):
    """
    Translates BrandProfile data to and from JSON.
    Includes nested competitors when reading the profile.
    """
    competitors = CompetitorSerializer(many=True, read_only=True)

    class Meta:
        model = BrandProfile
        fields = [
            'id', 
            'name', 
            'niche', 
            'target_audience', 
            'tone_of_voice', 
            'competitors', 
            'created_at', 
            'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class SocialPostSerializer(serializers.ModelSerializer):
    """Translates SocialPost data (both manual and scraped)."""
    competitor_handle = serializers.CharField(source='competitor.handle', read_only=True)

    class Meta:
        model = SocialPost
        fields = [
            'id',
            'brand',
            'competitor',
            'competitor_handle',
            'platform',
            'post_url',
            'hook_text',
            'full_content',
            'views',
            'likes',
            'shares',
            'comments',
            'outlier_score',
            'is_outlier',
            'is_manual',
            'created_at',
        ]
        read_only_fields = ['id', 'created_at']


class GeneratedIdeaSerializer(serializers.ModelSerializer):
    """Translates AI-generated post ideas and scripts."""
    class Meta:
        model = GeneratedIdea
        fields = [
            'id',
            'brand',
            'source_post',
            'target_platform',
            'title',
            'hook',
            'body_content',
            'why_it_works',
            'created_at',
        ]
        read_only_fields = ['id', 'created_at']

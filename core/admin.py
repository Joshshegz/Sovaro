from django.contrib import admin
from .models import BrandProfile, Competitor, SocialPost, GeneratedIdea


@admin.register(BrandProfile)
class BrandProfileAdmin(admin.ModelAdmin):
    list_display = ('name', 'niche', 'created_at')
    search_fields = ('name', 'niche')


@admin.register(Competitor)
class CompetitorAdmin(admin.ModelAdmin):
    list_display = ('handle', 'platform', 'brand', 'created_at')
    list_filter = ('platform',)
    search_fields = ('handle',)


@admin.register(SocialPost)
class SocialPostAdmin(admin.ModelAdmin):
    list_display = ('hook_text', 'platform', 'outlier_score', 'is_outlier', 'is_manual', 'created_at')
    list_filter = ('platform', 'is_outlier', 'is_manual')
    search_fields = ('hook_text', 'full_content')


@admin.register(GeneratedIdea)
class GeneratedIdeaAdmin(admin.ModelAdmin):
    list_display = ('title', 'target_platform', 'brand', 'created_at')
    list_filter = ('target_platform',)
    search_fields = ('title', 'hook')

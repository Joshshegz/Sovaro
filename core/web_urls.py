from django.contrib.auth.views import LogoutView
from django.urls import path

from . import web_views

app_name = "web"

urlpatterns = [
    path("", web_views.home, name="home"),
    path("login/", web_views.SovaroLoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(next_page="web:login"), name="logout"),
    path("signup/", web_views.signup, name="signup"),
    path("dashboard/", web_views.dashboard, name="dashboard"),
    path("settings/", web_views.account_settings, name="account_settings"),
    path("brands/new/", web_views.brand_create, name="brand_create"),
    path("brands/audience-suggestion/", web_views.audience_suggestion, name="audience_suggestion"),
    path("brands/scan/", web_views.brand_scan, name="brand_scan"),
    path("brands/<int:pk>/", web_views.brand_detail, name="brand_detail"),
    path("brands/<int:pk>/profile/", web_views.brand_profile, name="brand_profile"),
    path("brands/<int:brand_pk>/strategy/brief/", web_views.strategy_brief_save, name="strategy_brief_save"),
    path("brands/<int:brand_pk>/strategy/generate/", web_views.strategy_generate, name="strategy_generate"),
    path("strategies/<int:pk>/", web_views.strategy_detail, name="strategy_detail"),
    path("brands/<int:brand_pk>/ideas/", web_views.ideas, name="ideas"),
    path("brands/<int:brand_pk>/ideas/research/", web_views.research_content_gaps_view, name="research_content_gaps"),
    path("brands/<int:brand_pk>/repurpose/", web_views.repurpose_studio, name="repurpose_studio"),
    path("repurpose/<int:pk>/", web_views.repurpose_detail, name="repurpose_detail"),
    path("brands/<int:brand_pk>/caption-analyzer/", web_views.caption_analyzer, name="caption_analyzer"),
    path("brands/<int:brand_pk>/reports/", web_views.reports, name="reports"),
    path("brands/<int:brand_pk>/reports/new/", web_views.report_create, name="report_create"),
    path("reports/<int:pk>/", web_views.report_detail, name="report_detail"),
    path("reports/<int:pk>/edit-data/", web_views.report_edit_data, name="report_edit_data"),
    path("reports/<int:pk>/pdf/", web_views.report_pdf, name="report_pdf"),
]

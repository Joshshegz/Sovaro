from django.urls import path
from .auth_views import RegisterView, GoogleLoginView

urlpatterns = [
    # POST /api/auth/register/  → create account with email + password
    path('register/', RegisterView.as_view(), name='register'),

    # POST /api/auth/google/    → sign in with Google access token from the frontend
    path('google/', GoogleLoginView.as_view(), name='google_login'),
]

from django.contrib.auth.models import User
from rest_framework import serializers, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from rest_framework_simplejwt.tokens import RefreshToken

from allauth.socialaccount.providers.google.views import GoogleOAuth2Adapter
from allauth.socialaccount.providers.oauth2.client import OAuth2Client
from dj_rest_auth.registration.views import SocialLoginView


# ─────────────────────────────────────────
# EMAIL + PASSWORD REGISTRATION
# ─────────────────────────────────────────

class RegisterSerializer(serializers.ModelSerializer):
    """
    Validates the registration form data.
    'write_only=True' means the password is accepted as input but NEVER
    returned in a response. Passwords stay safely on the server.
    """
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'password']

    def create(self, validated_data):
        # create_user() is Django's built-in method that hashes the password
        # before saving. NEVER save plain text passwords directly.
        user = User.objects.create_user(
            username=validated_data['username'],
            email=validated_data.get('email', ''),
            password=validated_data['password'],
        )
        return user


class RegisterView(APIView):
    """
    POST /api/auth/register/
    Open endpoint — no token required (that would be a paradox!).

    Accepts: { "username": "josh", "email": "josh@example.com", "password": "securepass" }
    Returns: { "user": {...}, "tokens": { "access": "...", "refresh": "..." } }
    """
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)

        if serializer.is_valid():
            user = serializer.save()

            # Auto-generate tokens on registration so the user is
            # immediately logged in without needing to call /login/ separately.
            refresh = RefreshToken.for_user(user)

            return Response({
                'user': {
                    'id': user.id,
                    'username': user.username,
                    'email': user.email,
                },
                'tokens': {
                    'access': str(refresh.access_token),
                    'refresh': str(refresh),
                }
            }, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ─────────────────────────────────────────
# GOOGLE OAUTH LOGIN
# ─────────────────────────────────────────

class GoogleLoginView(SocialLoginView):
    """
    POST /api/auth/google/

    How the frontend uses this:
    1. The frontend uses Google's JavaScript SDK to get an access_token from Google.
    2. The frontend sends: { "access_token": "<google_token_here>" }
    3. This view forwards that token to Google to verify who the user is.
    4. Django finds or creates a User account for that Google email.
    5. Returns our own JWT access + refresh tokens for the user.

    This means users never need a separate Sovaro password if they sign in with Google.
    """
    adapter_class = GoogleOAuth2Adapter
    client_class = OAuth2Client
    permission_classes = [AllowAny]

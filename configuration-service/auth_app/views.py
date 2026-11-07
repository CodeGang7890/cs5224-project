from django.db import IntegrityError
from drf_spectacular.utils import OpenApiResponse, extend_schema, extend_schema_view
from rest_framework import generics, status
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt import views as jwt_views

from . import accounts, firebase
from .serializers import (
    USERNAME_TAKEN_MESSAGE,
    FirebaseLoginResponseSerializer,
    FirebaseLoginSerializer,
    MeSerializer,
    SignUpSerializer,
    SubscriptionTierSerializer,
    TokenPairSerializer,
)
from .models import SubscriptionTier

AUTH_TAG = 'Auth'


# Thin subclasses of SimpleJWT's views so they get clear names/docs in Swagger.
# They are public endpoints (no authentication required) by design.


@extend_schema_view(
    post=extend_schema(
        tags=[AUTH_TAG],
        summary='Log in',
        description=(
            'Exchange a username and password for a JWT pair. Send the `access` token as '
            '`Authorization: Bearer <access>` on API requests. Use `refresh` to get a new access '
            'token when it expires.'
        ),
    )
)
class LoginView(jwt_views.TokenObtainPairView):
    # Rate limited per client IP (REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']): password guessing.
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'login'


@extend_schema_view(
    post=extend_schema(
        tags=[AUTH_TAG],
        summary='Refresh tokens',
        description=(
            'Exchange a refresh token for a new access token. Refresh tokens rotate: the response '
            'also contains a new `refresh` token, and the old one is blacklisted.'
        ),
    )
)
class RefreshView(jwt_views.TokenRefreshView):
    pass


@extend_schema_view(
    post=extend_schema(tags=[AUTH_TAG], summary='Verify a token', description='Returns 200 if the token is valid.')
)
class VerifyView(jwt_views.TokenVerifyView):
    pass


@extend_schema_view(
    post=extend_schema(
        tags=[AUTH_TAG],
        summary='Log out',
        description=(
            'Blacklist a refresh token so it can no longer be used. The access token stays valid '
            'until it expires (15 minutes), so clients should also discard it.'
        ),
    )
)
class LogoutView(jwt_views.TokenBlacklistView):
    pass


@extend_schema_view(get=extend_schema(tags=[AUTH_TAG], summary='Get my profile'))
class MeView(generics.RetrieveAPIView):
    """Profile of whoever is logged in, including the ID of their business."""

    serializer_class = MeSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user


class SubscriptionTiersView(APIView):
    """The subscription plans, cheapest first (public: frontend-app's landing page lists them)."""

    permission_classes = [AllowAny]
    authentication_classes: list = []

    @extend_schema(
        tags=[AUTH_TAG],
        summary='List the subscription plans',
        description='Every `subscription_tier` value with its name, cheapest first. Public. Nothing is billed yet.',
        responses=SubscriptionTierSerializer(many=True),
    )
    def get(self, request: Request) -> Response:
        tiers = [{'id': value, 'name': label} for value, label in SubscriptionTier.choices]
        return Response(SubscriptionTierSerializer(tiers, many=True).data)


class SignUpView(APIView):
    """Creates an account with a username and password and logs it in. Rate limited per client IP
    (mass sign-ups); there's no email verification yet (it needs an email provider)."""

    permission_classes = [AllowAny]
    authentication_classes: list = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'signup'

    @extend_schema(
        tags=[AUTH_TAG],
        summary='Sign up',
        description=(
            'Create an account with a username, email and password (Django\'s password rules), and get a JWT '
            'pair as if it had logged in. The account has no business yet: create one with '
            'PUT /api/configuration/business/.'
        ),
        request=SignUpSerializer,
        responses={201: TokenPairSerializer, 400: OpenApiResponse(description='Invalid or taken fields.')},
    )
    def post(self, request: Request) -> Response:
        serializer = SignUpSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            user = serializer.save()
        except IntegrityError as exc:  # someone took the username meanwhile
            raise ValidationError({'username': [USERNAME_TAKEN_MESSAGE]}) from exc
        return Response(accounts.tokens_for(user), status=status.HTTP_201_CREATED)


class SocialLoginUnavailable(APIException):
    status_code = 503
    default_detail = "Logging in with Google or Facebook isn't available right now."
    default_code = 'social_login_unavailable'


class SocialLoginFailed(APIException):
    # Not AuthenticationFailed: with no authentication classes, DRF would turn that into a 403.
    status_code = 401
    default_detail = 'The Google / Facebook login is invalid or has expired. Please try again.'
    default_code = 'social_login_failed'


class FirebaseLoginView(APIView):
    """Logs in (or signs up) with Google or Facebook, through Identity Platform (firebase.py). Rate
    limited like the password login."""

    permission_classes = [AllowAny]
    authentication_classes: list = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'login'

    @extend_schema(
        tags=[AUTH_TAG],
        summary='Log in with Google or Facebook',
        description=(
            'Exchange an Identity Platform ID token (from the Google / Facebook popup of the Firebase JS SDK) '
            'for our JWT pair. The first login makes an account (`created`), with no business yet, unless the '
            'provider verified an email that one account already has: that account is linked. 401 for an '
            'invalid token or a disabled account; 503 when not configured (FIREBASE_PROJECT_ID).'
        ),
        request=FirebaseLoginSerializer,
        responses={
            200: FirebaseLoginResponseSerializer,
            400: OpenApiResponse(description='No token.'),
            401: OpenApiResponse(description='Invalid token, or the account is disabled.'),
            503: OpenApiResponse(description='Not configured, or Google unreachable.'),
        },
    )
    def post(self, request: Request) -> Response:
        serializer = FirebaseLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            identity = firebase.verify_id_token(serializer.validated_data['id_token'])
        except firebase.FirebaseNotConfigured as exc:
            raise SocialLoginUnavailable("Logging in with Google or Facebook isn't set up.") from exc
        except firebase.FirebaseUnavailable as exc:
            raise SocialLoginUnavailable() from exc
        except firebase.InvalidFirebaseToken as exc:
            raise SocialLoginFailed() from exc
        user, created = accounts.user_for_identity(identity)
        if not user.is_active:
            raise SocialLoginFailed('This account is disabled.')
        return Response({**accounts.tokens_for(user), 'created': created})

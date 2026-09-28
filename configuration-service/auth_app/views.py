from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt import views as jwt_views

from .serializers import MeSerializer

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
    pass


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

import random

from drf_spectacular.utils import extend_schema
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import RandomNumberSerializer

RANDOM_NUMBER_MIN = 1
RANDOM_NUMBER_MAX = 10


class RandomNumberView(APIView):
    """Dummy endpoint used to verify frontend ↔ backend connectivity."""

    @extend_schema(
        summary='Get a random number',
        description=f'Returns a random integer between {RANDOM_NUMBER_MIN} and {RANDOM_NUMBER_MAX} (inclusive).',
        responses=RandomNumberSerializer,
    )
    def get(self, request: Request) -> Response:
        serializer = RandomNumberSerializer(
            {'value': random.randint(RANDOM_NUMBER_MIN, RANDOM_NUMBER_MAX)}
        )
        return Response(serializer.data)

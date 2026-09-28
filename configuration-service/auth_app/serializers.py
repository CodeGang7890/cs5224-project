from rest_framework import serializers

from .models import BusinessUser


class MeSerializer(serializers.ModelSerializer):
    """The logged-in user's profile."""

    business = serializers.PrimaryKeyRelatedField(
        read_only=True,
        allow_null=True,
        help_text='ID of the BusinessConfiguration this account belongs to (null if none).',
    )
    business_name = serializers.CharField(
        source='business.business_name', read_only=True, allow_null=True, default=None
    )

    class Meta:
        model = BusinessUser
        fields = (
            'id',
            'username',
            'email',
            'first_name',
            'last_name',
            'business',
            'business_name',
            'is_staff',
            'is_superuser',
        )
        read_only_fields = fields

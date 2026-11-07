from django.contrib.auth import password_validation
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from .accounts import NAME_MAX_LENGTH, USERNAME_MAX_LENGTH, email_taken
from .models import BusinessUser, SubscriptionTier

USERNAME_TAKEN_MESSAGE = 'This username is taken.'
EMAIL_TAKEN_MESSAGE = 'An account with this email already exists. Log in instead.'


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
            'subscription_tier',
            'is_staff',
            'is_superuser',
        )
        read_only_fields = fields


class SubscriptionTierSerializer(serializers.Serializer):
    """One subscription plan: its `subscription_tier` value and name."""

    id = serializers.ChoiceField(choices=SubscriptionTier.choices, help_text='The `subscription_tier` value.')
    name = serializers.CharField(help_text='Its name, e.g. "Business".')


class TokenPairSerializer(serializers.Serializer):
    access = serializers.CharField(help_text='Send as `Authorization: Bearer <access>` (15 minutes).')
    refresh = serializers.CharField(help_text='For POST /api/auth/token/refresh/ (7 days, rotates).')


class SignUpSerializer(serializers.Serializer):
    """A new account with a username and password. It has no business yet: frontend-app asks for one."""

    username = serializers.CharField(max_length=USERNAME_MAX_LENGTH, validators=[UnicodeUsernameValidator()])
    email = serializers.EmailField(max_length=254)
    password = serializers.CharField(write_only=True, max_length=128, style={'input_type': 'password'})
    first_name = serializers.CharField(max_length=NAME_MAX_LENGTH, required=False, allow_blank=True, default='')
    last_name = serializers.CharField(max_length=NAME_MAX_LENGTH, required=False, allow_blank=True, default='')

    def validate_username(self, value: str) -> str:
        if BusinessUser.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError(USERNAME_TAKEN_MESSAGE)
        return value

    def validate_email(self, value: str) -> str:
        if email_taken(value):
            raise serializers.ValidationError(EMAIL_TAKEN_MESSAGE)
        return value

    def validate(self, attrs: dict) -> dict:
        # Django's password validators (length, common, numeric, too similar to the username / email).
        user = BusinessUser(**{key: value for key, value in attrs.items() if key != 'password'})
        try:
            password_validation.validate_password(attrs['password'], user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({'password': list(exc.messages)}) from exc
        return attrs

    def create(self, validated_data: dict) -> BusinessUser:
        return BusinessUser.objects.create_user(**validated_data)


class FirebaseLoginSerializer(serializers.Serializer):
    id_token = serializers.CharField(
        max_length=4096, help_text="The Identity Platform ID token from the Firebase JS SDK (`user.getIdToken()`)."
    )


class FirebaseLoginResponseSerializer(TokenPairSerializer):
    created = serializers.BooleanField(help_text='Whether a new account was made (its first login).')

"""
Business-level access control shared by API viewsets.

Rule: a BusinessUser may only access records whose `business` is their own business.

- Lists only include the user's own business's records.
- Retrieving, editing or deleting another business's record returns 403 Forbidden.
- Creating a record, or moving one, for another business returns 403 Forbidden.
- Users without a business (e.g. the admin superuser) can't create or modify business data.

Usage: subclass `BusinessOwnedSerializerMixin` in the serializer (with a `business` model field)
and `BusinessScopedViewSetMixin` in the viewset. For views whose URL names a business
(e.g. /api/businesses/<business_id>/products/), use `BusinessFromUrlMixin`.
See product_app for examples.
"""

from rest_framework import permissions, serializers
from rest_framework.exceptions import PermissionDenied, ValidationError

from configuration_app.models import BusinessConfiguration

NO_BUSINESS_MESSAGE = 'Your account is not linked to a business.'
OTHER_BUSINESS_MESSAGE = 'You do not have access to this business.'


def get_user_business_id(request) -> int:
    """The logged-in user's business ID; 403 if the account isn't linked to one (plain API views)."""
    if request.user.business_id is None:
        raise PermissionDenied(NO_BUSINESS_MESSAGE)
    return request.user.business_id


def get_user_business(request) -> BusinessConfiguration:
    """The logged-in user's business; 403 if the account isn't linked to one (plain API views)."""
    get_user_business_id(request)
    return request.user.business


class IsBusinessMember(permissions.BasePermission):
    """Authenticated user who can only touch objects of their own business."""

    message = OTHER_BUSINESS_MESSAGE

    def has_permission(self, request, view) -> bool:
        if not (request.user and request.user.is_authenticated):
            return False
        if request.method not in permissions.SAFE_METHODS and request.user.business_id is None:
            raise PermissionDenied(NO_BUSINESS_MESSAGE)
        return True

    def has_object_permission(self, request, view, obj) -> bool:
        return obj.business_id is not None and obj.business_id == request.user.business_id


class CurrentUserBusinessDefault:
    """Serializer field default: the requesting user's business."""

    requires_context = True

    def __call__(self, serializer_field):
        return serializer_field.context['request'].user.business

    def __repr__(self) -> str:
        return f'{self.__class__.__name__}()'


class BusinessOwnedSerializerMixin(serializers.Serializer):
    """
    Adds a `business` field that defaults to the user's business. Sending a different
    business (to create or move a record into it) raises 403 rather than a validation error.
    """

    business = serializers.PrimaryKeyRelatedField(
        queryset=BusinessConfiguration.objects.all(),
        default=CurrentUserBusinessDefault(),
        help_text="ID of the owning business. Optional: defaults to (and must equal) your own business.",
    )

    def validate_business(self, business: BusinessConfiguration) -> BusinessConfiguration:
        user = self.context['request'].user
        if business is None or business.pk != user.business_id:
            raise PermissionDenied(OTHER_BUSINESS_MESSAGE)
        return business


class BusinessScopedViewSetMixin:
    """
    Viewset mixin: lists are filtered to the user's business, while detail routes look up
    any record so that other businesses' records return 403 (via IsBusinessMember), not 404.
    """

    permission_classes = [IsBusinessMember]

    def get_queryset(self):
        queryset = super().get_queryset().select_related('business')
        if self.action == 'list':
            return queryset.filter(business_id=self.request.user.business_id)
        return queryset


class BusinessFromUrlMixin:
    """
    For views with a `business_id` URL argument. After authentication (401 if not logged in):

    - 400 Bad Request if no BusinessConfiguration has that ID,
    - 403 Forbidden if it isn't the requesting user's business,
    - otherwise sets `self.business` for use in `get_queryset()`.
    """

    business_url_kwarg = 'business_id'
    business: BusinessConfiguration

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)  # authentication + permissions (401 first)
        business_id = kwargs[self.business_url_kwarg]
        business = BusinessConfiguration.objects.filter(pk=business_id).first()
        if business is None:
            raise ValidationError(
                {self.business_url_kwarg: [f'Business configuration with ID {business_id} does not exist.']}
            )
        if business.pk != request.user.business_id:
            raise PermissionDenied(OTHER_BUSINESS_MESSAGE)
        self.business = business

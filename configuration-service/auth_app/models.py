from django.contrib.auth.models import AbstractUser
from django.db import models


class BusinessUser(AbstractUser):
    """
    Custom user model (AUTH_USER_MODEL). Inherits every field of Django's default user
    (username, password, email, names, is_staff/is_superuser/is_active, groups,
    user_permissions, last_login, date_joined) and links the user to a business.
    """

    # Nullable: superusers / platform staff don't belong to a business.
    # SET_NULL: deleting a business keeps its user accounts (they can be reassigned).
    business = models.ForeignKey(
        'configuration_app.BusinessConfiguration',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='users',
    )

    class Meta(AbstractUser.Meta):
        verbose_name = 'business user'
        verbose_name_plural = 'business users'

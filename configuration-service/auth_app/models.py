from django.contrib.auth.models import AbstractUser
from django.db import models


class SubscriptionTier(models.TextChoices):
    """The account's plan (frontend-app's Home page lists them with their prices). Nothing is billed or
    limited by it yet: it's only shown."""

    FREE = 'free', 'Free'
    STARTER = 'starter', 'Starter'
    GROWTH = 'growth', 'Growth'
    BUSINESS = 'business', 'Business'


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
    # Identity Platform (Firebase Authentication) user ID, once the account has logged in with Google or
    # Facebook (auth_app/firebase.py). Null: username / password only.
    firebase_uid = models.CharField(
        max_length=128,
        unique=True,
        null=True,
        blank=True,
        editable=False,
        help_text='Identity Platform user ID, set when the account logs in with Google or Facebook.',
    )

    # db_default too, so rows inserted outside Django (other services never do, today) also start on Free.
    subscription_tier = models.CharField(
        max_length=20,
        choices=SubscriptionTier.choices,
        default=SubscriptionTier.FREE,
        db_default=SubscriptionTier.FREE,
        help_text="The account's subscription plan (only shown for now: nothing is billed or limited).",
    )

    class Meta(AbstractUser.Meta):
        verbose_name = 'Business User'
        verbose_name_plural = 'Business Users'

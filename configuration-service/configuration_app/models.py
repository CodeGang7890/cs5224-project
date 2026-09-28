from django.core.validators import MaxLengthValidator
from django.db import models
from django.db.models import Q

BUSINESS_NAME_MAX_LENGTH = 150
LOCATION_MAX_LENGTH = 255
DESCRIPTION_MAX_LENGTH = 2000


class BusinessConfiguration(models.Model):
    """A business (tenant) using Ansera Business Admin. Other apps' data hangs off this."""

    business_name = models.CharField(max_length=BUSINESS_NAME_MAX_LENGTH)
    # Django doesn't enforce max_length on TextField at the model level, hence the explicit validator.
    description = models.TextField(
        max_length=DESCRIPTION_MAX_LENGTH,
        blank=True,
        validators=[MaxLengthValidator(DESCRIPTION_MAX_LENGTH)],
    )
    location = models.CharField(max_length=LOCATION_MAX_LENGTH)

    class Meta:
        ordering = ['business_name']
        verbose_name = 'business configuration'
        verbose_name_plural = 'business configurations'
        constraints = [
            models.CheckConstraint(
                condition=~Q(business_name=''),
                name='business_configuration_name_not_empty',
            ),
            models.CheckConstraint(
                condition=~Q(location=''),
                name='business_configuration_location_not_empty',
            ),
        ]

    def __str__(self) -> str:
        return self.business_name

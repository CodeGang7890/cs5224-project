from django.db import models

from .validators import validate_chat_config


class ChatConfiguration(models.Model):
    """A business's chat flow: a list of blocks (see validators.validate_chat_config)."""

    business = models.OneToOneField(
        'configuration_app.BusinessConfiguration',
        on_delete=models.CASCADE,
        related_name='chat_configuration',
    )
    config_json = models.JSONField(validators=[validate_chat_config])
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['business']

    def __str__(self) -> str:
        return f'Chat configuration for {self.business}'

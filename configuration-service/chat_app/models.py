from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone

from .constants import START_BLOCK
from .validators import is_valid_block_id, validate_chat_config, validate_chat_messages

PHONE_NUMBER_MAX_LENGTH = 16  # E.164: "+" and up to 15 digits
DISPLAY_NAME_MAX_LENGTH = 150

# E.164, e.g. +6591234567: "+", a country code that doesn't start with 0, 7–15 digits in total.
phone_number_validator = RegexValidator(
    r'^\+[1-9]\d{6,14}$',
    'Enter the phone number in international format, e.g. +6591234567.',
)


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

    @property
    def start_block_id(self):
        """`id` of the START_BLOCK (a valid config_json has exactly one)."""
        return next(block['id'] for block in self.config_json if block['block_type'] == START_BLOCK)


class ChatSession(models.Model):
    """A conversation between a business and one customer (identified by phone number)."""

    business = models.ForeignKey(
        'configuration_app.BusinessConfiguration',
        on_delete=models.CASCADE,
        related_name='chat_sessions',
    )
    phone_number = models.CharField(
        max_length=PHONE_NUMBER_MAX_LENGTH,
        validators=[phone_number_validator],
        help_text="The customer's phone number, in international format (e.g. +6591234567).",
    )
    display_name = models.CharField(
        max_length=DISPLAY_NAME_MAX_LENGTH,
        blank=True,
        help_text="The customer's name, if known.",
    )
    # Not auto_now_add, which always overwrites the value: creating a session sets created_time
    # and last_chat_time to the same instant.
    created_time = models.DateTimeField(default=timezone.now, editable=False)
    last_chat_time = models.DateTimeField(default=timezone.now)
    chat_message_json = models.JSONField(default=list, blank=True, validators=[validate_chat_messages])
    # A block `id` from the business's ChatConfiguration.config_json (int or string, like the
    # block ids themselves), or null when the chat isn't at any block (e.g. no configuration).
    chat_state_id = models.JSONField(
        null=True,
        blank=True,
        help_text="ID of the chat flow block the customer is at, from the business's chat configuration.",
    )

    class Meta:
        ordering = ['business', '-last_chat_time']
        constraints = [
            models.UniqueConstraint(
                fields=['business', 'phone_number'],
                name='chat_session_phone_unique_per_business',
                violation_error_message='This business already has a chat session with this phone number.',
            ),
            models.CheckConstraint(condition=~Q(phone_number=''), name='chat_session_phone_not_empty'),
        ]

    def __str__(self) -> str:
        return f'{self.display_name or self.phone_number} ({self.business})'

    def clean(self):
        super().clean()
        self._validate_chat_state_id()

    def _validate_chat_state_id(self) -> None:
        """chat_state_id must be the id of a block in the business's chat configuration."""
        state_id = self.chat_state_id
        if state_id is None or self.business_id is None:
            return
        if not is_valid_block_id(state_id):
            raise ValidationError({'chat_state_id': 'Must be null, an integer or a non-blank string.'})
        chat_config = ChatConfiguration.objects.filter(business_id=self.business_id).first()
        if chat_config is None:
            raise ValidationError(
                {'chat_state_id': 'This business has no chat configuration, so chat_state_id must be null.'}
            )
        # Compare types too, so "1" doesn't match block 1 (same rule as next_block_id).
        block_ids = [block.get('id') for block in chat_config.config_json if isinstance(block, dict)]
        if not any(type(block_id) is type(state_id) and block_id == state_id for block_id in block_ids):
            raise ValidationError(
                {'chat_state_id': f"{state_id!r} is not a block id in this business's chat configuration."}
            )

from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone

from product_app.models import FAQ_QUESTION_MAX_LENGTH

from .constants import START_BLOCK
from .validators import (
    is_valid_block_id,
    validate_chat_config,
    validate_chat_messages,
    validate_chat_state_data,
)

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
    def start_block(self) -> dict:
        """The START_BLOCK (a valid config_json has exactly one)."""
        return next(block for block in self.config_json if block['block_type'] == START_BLOCK)

    @property
    def start_block_id(self):
        """`id` of the START_BLOCK."""
        return self.start_block['id']

    def get_block(self, block_id) -> dict | None:
        """The block with this `id`, or None. Types must match too, so "1" doesn't find block 1."""
        if block_id is None:
            return None
        return next(
            (block for block in self.config_json if type(block['id']) is type(block_id) and block['id'] == block_id),
            None,
        )


class ChatSession(models.Model):
    """A conversation between a business and one customer (identified by phone number).

    Sandbox sessions (`is_sandbox`) are test chats started by the business itself from the Chat
    Sandbox: they don't need a phone number, and a business can have any number of them.
    """

    business = models.ForeignKey(
        'configuration_app.BusinessConfiguration',
        on_delete=models.CASCADE,
        related_name='chat_sessions',
    )
    phone_number = models.CharField(
        max_length=PHONE_NUMBER_MAX_LENGTH,
        blank=True,  # only sandbox sessions may leave it empty (see clean() and the constraints)
        validators=[phone_number_validator],
        help_text="The customer's phone number, in international format (e.g. +6591234567). Optional for sandbox sessions.",
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
    is_sandbox = models.BooleanField(
        default=False,
        help_text='A test chat from the Chat Sandbox rather than a real customer.',
    )
    # What the chat flow has collected so far (chosen products, customer details, completed).
    # See validators.validate_chat_state_data and flow.py.
    chat_state_data = models.JSONField(
        default=dict,
        blank=True,
        validators=[validate_chat_state_data],
        help_text='Data collected by the chat flow so far: chosen products, customer details, completed.',
    )

    class Meta:
        ordering = ['business', '-last_chat_time']
        constraints = [
            # Sandbox sessions are excluded: they may share a number or have none.
            models.UniqueConstraint(
                fields=['business', 'phone_number'],
                condition=Q(is_sandbox=False),
                name='chat_session_phone_unique_per_business',
                violation_error_message='This business already has a chat session with this phone number.',
            ),
            models.CheckConstraint(
                condition=Q(is_sandbox=True) | ~Q(phone_number=''),
                name='chat_session_phone_required_unless_sandbox',
                violation_error_message='A phone number is required, except for sandbox sessions.',
            ),
        ]

    def __str__(self) -> str:
        name = self.display_name or self.phone_number or f'Sandbox chat #{self.pk}'
        return f'{name} ({self.business})'

    def clean(self):
        super().clean()
        if not self.is_sandbox and not self.phone_number:
            raise ValidationError({'phone_number': 'A phone number is required, except for sandbox sessions.'})
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


class QuestionStatus(models.TextChoices):
    OPEN = 'open', 'Open'  # waiting for the business
    ANSWERED = 'answered', 'Answered'  # the answer became an FAQ and was sent in the chat
    DISMISSED = 'dismissed', 'Dismissed'  # closed without an answer (e.g. not worth one)


QUESTION_STATUS_MAX_LENGTH = 16


class UnansweredQuestion(models.Model):
    """A customer question the chat assistant couldn't answer from the FAQs or product details.

    Created by the reply step's `ask_business` tool (tools.Toolbox, see questions.py). The business
    owner answers it in the Chats tab, which saves the Q&A as an FAQ and sends the answer in the
    chat, or dismisses it.
    """

    business = models.ForeignKey(
        'configuration_app.BusinessConfiguration',
        on_delete=models.CASCADE,
        related_name='unanswered_questions',
    )
    chat_session = models.ForeignKey(
        ChatSession,
        on_delete=models.CASCADE,
        related_name='unanswered_questions',
        help_text='The chat the customer asked in; the answer is sent there.',
    )
    # As long as an FAQ question, since that's what it becomes once answered.
    question = models.CharField(max_length=FAQ_QUESTION_MAX_LENGTH)
    status = models.CharField(
        max_length=QUESTION_STATUS_MAX_LENGTH,
        choices=QuestionStatus.choices,
        default=QuestionStatus.OPEN,
    )
    faq = models.ForeignKey(
        'product_app.FAQ',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='unanswered_questions',
        help_text='The FAQ the answer was saved as (editable in the FAQ tab).',
    )
    # Not auto_now_add, so fixtures and tests can set it (like ChatSession.created_time).
    created_time = models.DateTimeField(default=timezone.now, editable=False)
    answered_time = models.DateTimeField(null=True, blank=True, help_text='When it was answered (answered only).')

    class Meta:
        ordering = ['-created_time', '-id']
        constraints = [
            models.CheckConstraint(
                condition=Q(status__in=QuestionStatus.values),
                name='unanswered_question_status_valid',
            ),
            models.CheckConstraint(condition=~Q(question=''), name='unanswered_question_not_empty'),
            # answered_time is set exactly when the question was answered.
            models.CheckConstraint(
                condition=(
                    Q(status=QuestionStatus.ANSWERED, answered_time__isnull=False)
                    | (~Q(status=QuestionStatus.ANSWERED) & Q(answered_time__isnull=True))
                ),
                name='unanswered_question_answered_time',
                violation_error_message='answered_time must be set exactly when the question is answered.',
            ),
        ]

    def __str__(self) -> str:
        return self.question

    def clean(self):
        super().clean()
        errors = {}
        if self.chat_session_id and self.business_id and self.chat_session.business_id != self.business_id:
            errors['chat_session'] = "The chat session must belong to the question's business."
        if self.faq_id and self.business_id and self.faq.business_id != self.business_id:
            errors['faq'] = "The FAQ must belong to the question's business."
        if errors:
            raise ValidationError(errors)

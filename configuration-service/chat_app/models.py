from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone

from product_app.models import FAQ_QUESTION_MAX_LENGTH

from .constants import (
    BOOKING_STEPS,
    CHAT_STEPS,
    CUSTOM_STYLE_MAX_LENGTH,
    DEFAULT_REPLY_STYLE,
    REPLY_STYLE_CUSTOM,
    REPLY_STYLE_PRESETS,
    REPLY_STYLES,
    STEP_LABELS,
    STEP_START,
    WELCOME_MESSAGE_MAX_LENGTH,
)
from .validators import (
    default_detail_fields,
    validate_chat_messages,
    validate_chat_state_data,
    validate_detail_fields,
    validate_welcome_message,
)

PHONE_NUMBER_MAX_LENGTH = 16  # E.164: "+" and up to 15 digits
DISPLAY_NAME_MAX_LENGTH = 150
CHAT_STEP_MAX_LENGTH = 32

# E.164, e.g. +6591234567: "+", a country code that doesn't start with 0, 7–15 digits in total.
phone_number_validator = RegexValidator(
    r'^\+[1-9]\d{6,14}$',
    'Enter the phone number in international format, e.g. +6591234567.',
)


class ChatConfiguration(models.Model):
    """A business's settings for the chat flow's steps.

    The flow itself is fixed in code (flow.py): the router, then the order steps (Product
    selection → Details collection → Confirmation), the FAQs and order status. The business only
    configures the steps' settings: which details the Details collection step asks for (for
    product orders) and the Booking details step (for service bookings), separately; the
    welcome message sent as the reply to a chat's first message, and the style the assistant
    writes in. A business that hasn't saved any uses the defaults (for_business).
    """

    business = models.OneToOneField(
        'configuration_app.BusinessConfiguration',
        on_delete=models.CASCADE,
        related_name='chat_configuration',
    )
    product_detail_fields = models.JSONField(
        default=default_detail_fields,
        validators=[validate_detail_fields],
        help_text='The customer details the Details collection step asks for, for product orders (see validators.detail_field_errors).',
    )
    schedule_detail_fields = models.JSONField(
        default=default_detail_fields,
        validators=[validate_detail_fields],
        help_text='The customer details the Booking details step asks for, for service bookings (see validators.detail_field_errors).',
    )
    welcome_message = models.CharField(
        max_length=WELCOME_MESSAGE_MAX_LENGTH,
        blank=True,
        default='',
        validators=[validate_welcome_message],
        help_text=(
            "Sent word for word as the reply to a chat's first message (blank: none). May use {business_name}."
        ),
    )
    reply_style = models.CharField(
        max_length=20,
        choices=[(key, meta['label']) for key, meta in REPLY_STYLE_PRESETS.items()] + [(REPLY_STYLE_CUSTOM, 'Custom')],
        default=DEFAULT_REPLY_STYLE,
        help_text='How the assistant writes its replies: a preset, or custom (custom_style).',
    )
    custom_style = models.CharField(
        max_length=CUSTOM_STYLE_MAX_LENGTH,
        blank=True,
        default='',
        help_text='With reply_style "custom": how the assistant should write, in the business\'s own words.',
    )
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Chat Configuration'
        verbose_name_plural = 'Chat Configurations'
        ordering = ['business']
        constraints = [
            models.CheckConstraint(condition=Q(reply_style__in=REPLY_STYLES), name='chat_configuration_reply_style_valid'),
            models.CheckConstraint(
                condition=~Q(reply_style=REPLY_STYLE_CUSTOM) | ~Q(custom_style=''),
                name='chat_configuration_custom_style_given',
            ),
        ]

    def __str__(self) -> str:
        return f'Chat configuration for {self.business}'

    def clean(self) -> None:
        super().clean()
        if self.reply_style == REPLY_STYLE_CUSTOM and not self.custom_style.strip():
            raise ValidationError({'custom_style': 'Describe the style you want (or choose one of the presets).'})

    def detail_fields_for(self, step: str) -> list[dict]:
        """The details a step's branch asks for: schedule_detail_fields for the booking steps,
        product_detail_fields otherwise (the order steps, and Start)."""
        return self.schedule_detail_fields if step in BOOKING_STEPS else self.product_detail_fields

    @classmethod
    def for_business(cls, business) -> 'ChatConfiguration':
        """The business's configuration, or an unsaved one with the default settings."""
        config = cls.objects.filter(business=business).first() or cls()
        config.business = business  # also saves a query when the saved one reads it
        return config


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
    # The step of the (fixed) chat flow the customer is at: constants.CHAT_STEPS.
    chat_state_id = models.CharField(
        max_length=CHAT_STEP_MAX_LENGTH,
        choices=[(step, STEP_LABELS[step]) for step in CHAT_STEPS],
        default=STEP_START,
        help_text='The chat flow step the customer is at: start (no order in progress) or an order step.',
    )
    is_sandbox = models.BooleanField(
        default=False,
        help_text='A test chat from the Chat Sandbox rather than a real customer.',
    )
    # What the order steps have collected so far (chosen products, customer details, completed).
    # See validators.validate_chat_state_data and order_flow.py.
    chat_state_data = models.JSONField(
        default=dict,
        blank=True,
        validators=[validate_chat_state_data],
        help_text='Data collected by the chat flow so far: chosen products, customer details, completed.',
    )

    class Meta:
        verbose_name = 'Chat Session'
        verbose_name_plural = 'Chat Sessions'
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
            models.CheckConstraint(condition=Q(chat_state_id__in=CHAT_STEPS), name='chat_session_step_valid'),
        ]

    def __str__(self) -> str:
        name = self.display_name or self.phone_number or f'Sandbox chat #{self.pk}'
        return f'{name} ({self.business})'

    def clean(self):
        super().clean()
        if not self.is_sandbox and not self.phone_number:
            raise ValidationError({'phone_number': 'A phone number is required, except for sandbox sessions.'})


class QuestionStatus(models.TextChoices):
    OPEN = 'open', 'Open'  # waiting for the business
    ANSWERED = 'answered', 'Answered'  # the answer became an FAQ and was sent in the chat
    DISMISSED = 'dismissed', 'Dismissed'  # closed without an answer (e.g. not worth one)


QUESTION_STATUS_MAX_LENGTH = 16


class UnansweredQuestion(models.Model):
    """A customer question the chat assistant couldn't answer from the FAQs or product details.

    Saved by the chat's question check (flow.check_customer_question calls questions.ask_business)
    when the router finds a question that the business's information doesn't answer. The business
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
        verbose_name = 'Unanswered Question'
        verbose_name_plural = 'Unanswered Questions'
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

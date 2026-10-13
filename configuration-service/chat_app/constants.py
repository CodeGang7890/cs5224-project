"""Chat constants: the fixed steps, message senders, detail field types, the reply styles.

The chat flow itself (the router, the order / booking steps, the LLM) runs in messaging-service
(app/chat_flow/constants.py has the same values and more): these are what this service's models,
validators and APIs need.
"""

# --- The chat flow's steps -----------------------------------------------------------------
# Ordering products and booking a service are small state machines over these steps, each in this
# order (messaging-service's chat flow). ChatSession.chat_state_id is one of them.
STEP_START = 'start'  # nothing in progress: the router decides when an order or a booking starts
STEP_PRODUCT_SELECTION = 'product_selection'
STEP_DETAILS_COLLECTION = 'details_collection'
STEP_CONFIRMATION = 'confirmation'
STEP_SERVICE_SELECTION = 'service_selection'
STEP_SLOT_SELECTION = 'slot_selection'
STEP_BOOKING_DETAILS = 'booking_details'
STEP_BOOKING_CONFIRMATION = 'booking_confirmation'

ORDER_STEPS = [STEP_PRODUCT_SELECTION, STEP_DETAILS_COLLECTION, STEP_CONFIRMATION]  # in order
BOOKING_STEPS = [STEP_SERVICE_SELECTION, STEP_SLOT_SELECTION, STEP_BOOKING_DETAILS, STEP_BOOKING_CONFIRMATION]
CHAT_STEPS = [STEP_START, *ORDER_STEPS, *BOOKING_STEPS]

STEP_LABELS = {
    STEP_START: 'Start',
    STEP_PRODUCT_SELECTION: 'Product selection',
    STEP_DETAILS_COLLECTION: 'Details collection',
    STEP_CONFIRMATION: 'Confirmation',
    STEP_SERVICE_SELECTION: 'Service selection',
    STEP_SLOT_SELECTION: 'Time slot',
    STEP_BOOKING_DETAILS: 'Booking details',
    STEP_BOOKING_CONFIRMATION: 'Booking confirmation',
}

# Who sent a ChatSession message (chat_message_json[].sent_by).
SENT_BY_CUSTOMER = 'customer'
SENT_BY_BUSINESS_MANUAL = 'business-manual'  # typed by a person at the business
SENT_BY_BUSINESS_AUTOMATED = 'business-automated'  # sent by the chat assistant

MESSAGE_SENDERS = [
    SENT_BY_CUSTOMER,
    SENT_BY_BUSINESS_MANUAL,
    SENT_BY_BUSINESS_AUTOMATED,
]

# Types of customer detail the details steps can ask for (product_detail_fields[].type /
# schedule_detail_fields[].type). No phone type: customers chat on WhatsApp, so the chat already
# has their number (ChatSession.phone_number).
DETAIL_TYPE_TEXT = 'text'
DETAIL_TYPE_NUMBER = 'number'
DETAIL_TYPE_EMAIL = 'email'

DETAIL_FIELD_TYPES = [
    DETAIL_TYPE_TEXT,
    DETAIL_TYPE_NUMBER,
    DETAIL_TYPE_EMAIL,
]

# The details the Details collection step asks for until the business changes them
# (the default of both ChatConfiguration.product_detail_fields and schedule_detail_fields): a
# name and an email, both required.
DEFAULT_DETAIL_FIELDS = [
    {'key': 'name', 'label': 'Name', 'type': DETAIL_TYPE_TEXT, 'max_length': 150},
    {'key': 'email', 'label': 'Email', 'type': DETAIL_TYPE_EMAIL},
]

# --- The business's welcome message and reply style (ChatConfiguration) --------------------
# The welcome message is sent word for word as the reply to a chat's very first message.
WELCOME_MESSAGE_MAX_LENGTH = 1000
# Placeholders the welcome message may use (filled in when it's sent).
WELCOME_PLACEHOLDERS = ('{business_name}',)
# A custom reply style: the business's own description of how the assistant should write.
CUSTOM_STYLE_MAX_LENGTH = 500

REPLY_STYLE_FRIENDLY = 'friendly'
REPLY_STYLE_PROFESSIONAL = 'professional'
REPLY_STYLE_CASUAL = 'casual'
REPLY_STYLE_BRIEF = 'brief'
REPLY_STYLE_CUSTOM = 'custom'  # the business writes its own (custom_style)
DEFAULT_REPLY_STYLE = REPLY_STYLE_FRIENDLY

# The preset styles: a label and description for the business, and the instructions the reply
# prompts get (messaging-service's chat flow, prompts.reply_style_section). REPLY_STYLE_CUSTOM uses custom_style instead.
REPLY_STYLE_PRESETS = {
    REPLY_STYLE_FRIENDLY: {
        'label': 'Friendly',
        'description': 'Warm and helpful, in a few short sentences. The default.',
        'instructions': 'Write in a friendly, warm and helpful way, in a few short sentences.',
    },
    REPLY_STYLE_PROFESSIONAL: {
        'label': 'Professional',
        'description': 'Polite and formal, like a front desk. No slang or emoji.',
        'instructions': (
            'Write in a polite, professional and formal way, like a front desk would, in a few short sentences. '
            'Use full sentences and no slang or emoji.'
        ),
    },
    REPLY_STYLE_CASUAL: {
        'label': 'Casual',
        'description': 'Relaxed and upbeat, like chatting with a regular. An emoji now and then.',
        'instructions': (
            'Write in a relaxed, upbeat and casual way, like chatting with a regular customer, in a few short '
            'sentences. An emoji now and then is fine.'
        ),
    },
    REPLY_STYLE_BRIEF: {
        'label': 'Brief',
        'description': 'As short as possible: one or two sentences, straight to the point.',
        'instructions': 'Keep every reply as short as possible: one or two sentences, straight to the point.',
    },
}
REPLY_STYLES = [*REPLY_STYLE_PRESETS, REPLY_STYLE_CUSTOM]

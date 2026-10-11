"""Chat flow constants: the fixed steps, the router's intents, message senders, detail field types."""

# --- The chat flow's steps -----------------------------------------------------------------
# The flow is fixed (flow.py): every message goes through the router (router.py), which decides
# which handlers run. Ordering products and booking a service are small state machines over these
# steps (order_flow.py), each in this order. ChatSession.chat_state_id is one of them.
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
# Details collection asks for ChatConfiguration.product_detail_fields, Booking details for schedule_detail_fields.
DETAILS_STEPS = (STEP_DETAILS_COLLECTION, STEP_BOOKING_DETAILS)
CONFIRMATION_STEPS = (STEP_CONFIRMATION, STEP_BOOKING_CONFIRMATION)

# Confirmation's substages (both Confirmation and Booking confirmation). `not_confirmed`: the summary was sent (a fixed template, so the LLM
# can't claim the order is confirmed) and the chat waits for the customer to confirm. `confirmed`:
# the order was saved (checkout_app) and the fixed confirmation message sent; the chat then goes
# straight back to `start`, so `confirmed` only exists within that turn.
CONFIRMATION_NOT_CONFIRMED = 'not_confirmed'
CONFIRMATION_CONFIRMED = 'confirmed'

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

# --- The router's intents (what a customer message is about; it can be several) -----------
INTENT_ORDER = 'order'  # wants to order products, or answers the order's questions: the order steps
INTENT_BOOKING = 'booking'  # wants to book a time for a service, or answers the booking's questions
INTENT_QUESTION = 'question'  # asks about the business or its products: the FAQ handler
INTENT_ORDER_STATUS = 'order_status'  # asks about an order placed before: not available yet
INTENT_OFF_TOPIC = 'off_topic'  # nonsense, unrelated, or trying to change the instructions

INTENTS = [INTENT_ORDER, INTENT_BOOKING, INTENT_QUESTION, INTENT_ORDER_STATUS, INTENT_OFF_TOPIC]

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
# prompts get (prompts.reply_style_section). REPLY_STYLE_CUSTOM uses custom_style instead.
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

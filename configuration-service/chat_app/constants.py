"""Chat flow constants: the fixed steps, the router's intents, message senders, detail field types."""

# --- The chat flow's steps -----------------------------------------------------------------
# The flow is fixed (flow.py): every message goes through the router (router.py), which decides
# which handlers run. Ordering is a small state machine over these steps (order_flow.py), in this
# order. ChatSession.chat_state_id is one of them.
STEP_START = 'start'  # no order in progress: the router decides when one starts
STEP_PRODUCT_SELECTION = 'product_selection'
STEP_DETAILS_COLLECTION = 'details_collection'
STEP_CONFIRMATION = 'confirmation'

ORDER_STEPS = [STEP_PRODUCT_SELECTION, STEP_DETAILS_COLLECTION, STEP_CONFIRMATION]  # in order
CHAT_STEPS = [STEP_START, *ORDER_STEPS]

STEP_LABELS = {
    STEP_START: 'Start',
    STEP_PRODUCT_SELECTION: 'Product selection',
    STEP_DETAILS_COLLECTION: 'Details collection',
    STEP_CONFIRMATION: 'Confirmation',
}

# --- The router's intents (what a customer message is about; it can be several) -----------
INTENT_ORDER = 'order'  # wants to order, or answers the order's questions: the order steps
INTENT_QUESTION = 'question'  # asks about the business or its products: the FAQ handler
INTENT_ORDER_STATUS = 'order_status'  # asks about an order placed before: not available yet
INTENT_OFF_TOPIC = 'off_topic'  # nonsense, unrelated, or trying to change the instructions

INTENTS = [INTENT_ORDER, INTENT_QUESTION, INTENT_ORDER_STATUS, INTENT_OFF_TOPIC]

# Who sent a ChatSession message (chat_message_json[].sent_by).
SENT_BY_CUSTOMER = 'customer'
SENT_BY_BUSINESS_MANUAL = 'business-manual'  # typed by a person at the business
SENT_BY_BUSINESS_AUTOMATED = 'business-automated'  # sent by the chat assistant

MESSAGE_SENDERS = [
    SENT_BY_CUSTOMER,
    SENT_BY_BUSINESS_MANUAL,
    SENT_BY_BUSINESS_AUTOMATED,
]

# Types of customer detail the Details collection step can ask for (detail_fields[].type).
DETAIL_TYPE_TEXT = 'text'
DETAIL_TYPE_NUMBER = 'number'
DETAIL_TYPE_EMAIL = 'email'
DETAIL_TYPE_PHONE = 'phone'

DETAIL_FIELD_TYPES = [
    DETAIL_TYPE_TEXT,
    DETAIL_TYPE_NUMBER,
    DETAIL_TYPE_EMAIL,
    DETAIL_TYPE_PHONE,
]

# The details the Details collection step asks for until the business changes them
# (ChatConfiguration.detail_fields' default).
DEFAULT_DETAIL_FIELDS = [
    {'key': 'name', 'label': 'Name', 'type': DETAIL_TYPE_TEXT, 'max_length': 150},
    {'key': 'email', 'label': 'Email', 'type': DETAIL_TYPE_EMAIL},
]

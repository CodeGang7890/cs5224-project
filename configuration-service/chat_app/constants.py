"""Chat flow constants. Block types will later map to their prompts, etc."""

START_BLOCK = 'START_BLOCK'
PRODUCT_SELECTION_BLOCK = 'PRODUCT_SELECTION_BLOCK'
DETAILS_COLLECTION_BLOCK = 'DETAILS_COLLECTION_BLOCK'
CONFIRMATION_BLOCK = 'CONFIRMATION_BLOCK'
# Sends the block's fixed `message` to the customer, then moves straight on to the next block.
SEND_MESSAGE_BLOCK = 'SEND_MESSAGE_BLOCK'

BLOCK_TYPES = [
    START_BLOCK,
    PRODUCT_SELECTION_BLOCK,
    DETAILS_COLLECTION_BLOCK,
    CONFIRMATION_BLOCK,
    SEND_MESSAGE_BLOCK,
]

# Who sent a ChatSession message (chat_message_json[].sent_by).
SENT_BY_CUSTOMER = 'customer'
SENT_BY_BUSINESS_MANUAL = 'business-manual'  # typed by a person at the business
SENT_BY_BUSINESS_AUTOMATED = 'business-automated'  # sent by the chat assistant

MESSAGE_SENDERS = [
    SENT_BY_CUSTOMER,
    SENT_BY_BUSINESS_MANUAL,
    SENT_BY_BUSINESS_AUTOMATED,
]

# Types of customer detail a DETAILS_COLLECTION_BLOCK can ask for (its `fields[].type`).
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

# The details a DETAILS_COLLECTION_BLOCK asks for when it has no `fields` (e.g. saved before
# fields existed). New blocks in the frontend's workflow editor start with the same two.
DEFAULT_DETAIL_FIELDS = [
    {'key': 'name', 'label': 'Name', 'type': DETAIL_TYPE_TEXT, 'max_length': 150},
    {'key': 'email', 'label': 'Email', 'type': DETAIL_TYPE_EMAIL},
]

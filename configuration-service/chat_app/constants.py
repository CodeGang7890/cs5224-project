"""Chat flow constants. Block types will later map to their prompts, etc."""

START_BLOCK = 'START_BLOCK'
PRODUCT_SELECTION_BLOCK = 'PRODUCT_SELECTION_BLOCK'
DETAILS_COLLECTION_BLOCK = 'DETAILS_COLLECTION_BLOCK'
CONFIRMATION_BLOCK = 'CONFIRMATION_BLOCK'

BLOCK_TYPES = [
    START_BLOCK,
    PRODUCT_SELECTION_BLOCK,
    DETAILS_COLLECTION_BLOCK,
    CONFIRMATION_BLOCK,
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

# Customer details a DETAILS_COLLECTION_BLOCK collects (keys of chat_state_data['details']).
REQUIRED_CUSTOMER_DETAILS = ['name', 'email']

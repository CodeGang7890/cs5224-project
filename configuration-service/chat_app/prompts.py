"""Prompts, goals and output formats for each chat flow block type, used by flow.py.

Drafts: tune the wording freely. Each block type has:
- a goal (what the block is for);
- an extraction prompt + JSON schema: what the model must return about the conversation, so the
  flow can decide deterministically whether the block is done (see flow.py);
- reply instructions: how the assistant should answer the customer while at that block.
"""

from decimal import Decimal

from .constants import (
    CONFIRMATION_BLOCK,
    DETAILS_COLLECTION_BLOCK,
    DETAIL_TYPE_EMAIL,
    DETAIL_TYPE_NUMBER,
    DETAIL_TYPE_PHONE,
    PRODUCT_SELECTION_BLOCK,
    SEND_MESSAGE_BLOCK,
    START_BLOCK,
)
from .validators import DETAIL_TEXT_DEFAULT_MAX_LENGTH, block_detail_fields

BLOCK_LABELS = {
    START_BLOCK: 'Start',
    PRODUCT_SELECTION_BLOCK: 'Product selection',
    DETAILS_COLLECTION_BLOCK: 'Details collection',
    CONFIRMATION_BLOCK: 'Confirmation',
    SEND_MESSAGE_BLOCK: 'Send message',
}

BLOCK_GOALS = {
    START_BLOCK: 'Welcome the customer, answer their questions and find out whether they want to order.',
    PRODUCT_SELECTION_BLOCK: 'Find out which products the customer wants, and how many of each.',
    DETAILS_COLLECTION_BLOCK: 'Collect the customer details listed under "Details to collect".',
    CONFIRMATION_BLOCK: 'Show the order summary and get the customer to confirm it.',
    SEND_MESSAGE_BLOCK: "Send the business's fixed message (done automatically, without you).",
}

# --- Extraction (generate_structured) -----------------------------------------------------

_NULLABLE_STRING = {'anyOf': [{'type': 'string'}, {'type': 'null'}]}
_NULLABLE_NUMBER = {'anyOf': [{'type': 'number'}, {'type': 'null'}]}

# The DETAILS_COLLECTION_BLOCK's schema depends on its fields: see extraction_schema().

EXTRACTION_SCHEMAS = {
    START_BLOCK: {
        'type': 'object',
        'properties': {'wants_to_order': {'type': 'boolean'}},
        'required': ['wants_to_order'],
    },
    PRODUCT_SELECTION_BLOCK: {
        'type': 'object',
        'properties': {
            'items': {
                'type': 'array',
                'items': {
                    'type': 'object',
                    'properties': {
                        'product_id': {'type': 'integer'},
                        'quantity': {'anyOf': [{'type': 'integer'}, {'type': 'null'}]},
                    },
                    'required': ['product_id', 'quantity'],
                },
            },
            'done_choosing': {'type': 'boolean'},
        },
        'required': ['items', 'done_choosing'],
    },
    CONFIRMATION_BLOCK: {
        'type': 'object',
        'properties': {'decision': {'type': 'string', 'enum': ['confirm', 'change', 'none']}},
        'required': ['decision'],
    },
}

_EXTRACTION_TASKS = {
    START_BLOCK: (
        'Set "wants_to_order" to true if the customer wants to buy or order something (e.g. '
        '"I\'d like to order", "can I get 2 kopi?"), or false if they are only greeting or asking '
        'questions.'
    ),
    PRODUCT_SELECTION_BLOCK: (
        'Products on sale:\n{catalog}\n\n'
        'Currently chosen: {chosen}\n\n'
        'Return in "items" every product the customer wants to order, each as {{"product_id", '
        '"quantity"}}. Use only ids from the list above. "quantity" is the number the customer asked '
        'for, or null if they have not said. If the customer changed their mind, return the full '
        'updated list. Return an empty list if they have not chosen any product yet.\n\n'
        'Set "done_choosing" to true only if the customer\'s latest message says they do not want '
        'anything else, or agrees that the order recapped by the assistant is complete (e.g. "that\'s '
        'all", "no, that\'s it", "yes, that\'s everything"). Set it to false if they are still adding, '
        'removing or changing products, asked a question, or have not answered whether they want '
        'anything else.'
    ),
    DETAILS_COLLECTION_BLOCK: (
        'Extract these details about the customer, if they gave them anywhere in the conversation '
        '(JSON key: what it is):\n{fields}\n\n'
        'Use null for anything they have not given. Copy text exactly and never make anything up. '
        'Give numbers as JSON numbers.\n\n'
        'Already known: {known}'
    ),
    CONFIRMATION_BLOCK: (
        'The assistant has shown the customer an order summary and asked them to confirm it. Based '
        'on the customer\'s latest message, set "decision" to "confirm" if they agree (e.g. yes, '
        'ok, confirm), "change" if they want to change something in the order or their details, or '
        '"none" otherwise (e.g. they asked a question).'
    ),
}


def extraction_schema(block: dict) -> dict:
    """JSON schema the LLM's extraction must follow at this block."""
    if block['block_type'] != DETAILS_COLLECTION_BLOCK:
        return EXTRACTION_SCHEMAS[block['block_type']]
    fields = block_detail_fields(block)
    return {
        'type': 'object',
        'properties': {
            f['key']: _NULLABLE_NUMBER if f['type'] == DETAIL_TYPE_NUMBER else _NULLABLE_STRING for f in fields
        },
        'required': [f['key'] for f in fields],
    }


def build_extraction_prompt(business, block: dict, data: dict, products: list[dict], labels: dict) -> str:
    """System prompt for the extraction at `block`. `labels`: detail field key → label (detail_labels)."""
    is_details = block['block_type'] == DETAILS_COLLECTION_BLOCK
    task = _EXTRACTION_TASKS[block['block_type']].format(
        catalog=format_catalog(products),
        chosen=format_items(data.get('items', [])) or 'nothing yet',
        fields=describe_detail_fields(block_detail_fields(block), with_keys=True) if is_details else '',
        known=format_details(data.get('details', {}), labels) or 'nothing yet',
    )
    return (
        f'You read a WhatsApp conversation between {business.business_name} and a customer, and '
        'extract information from it as JSON. Reply with the JSON object only. Do not guess: if the '
        'customer has not said something, leave it null, false or empty.\n\n'
        f'Task: {task}'
    )


# --- Reply (generate_chat_reply) ----------------------------------------------------------

_REPLY_INSTRUCTIONS = {
    START_BLOCK: (
        'Greet the customer if the conversation is just starting, answer their questions using the '
        'information here or your tools, and ask whether they would like to place an order.'
    ),
    PRODUCT_SELECTION_BLOCK: (
        'Help the customer choose. If they have not chosen anything yet, briefly list the available '
        'products with their prices and ask what they would like and how many. If there are '
        'problems listed above (e.g. a missing quantity or an unavailable product), explain them '
        'and ask again. Only offer products from the list.\n'
        'Once they have chosen something, do NOT move on yet: recap their order exactly as in "What we '
        'know so far" (each item with its quantity and price, and the total), then ask whether they '
        'would like anything else or whether that is everything. Do not ask for their name, contact '
        'or other details yet: that comes after they confirm their order is complete.'
    ),
    DETAILS_COLLECTION_BLOCK: (
        'Briefly acknowledge their order, then ask only for the details listed under "Still needed". '
        'Never ask again for details that are already known.'
    ),
    CONFIRMATION_BLOCK: (
        'Show the order summary from "What we know so far" (items, quantities, prices, total and '
        'customer details) and ask the customer to reply YES to confirm, or to tell you what to '
        'change. If they asked a question, answer it first. If there are problems listed above (e.g. '
        'a product sold out), the order was NOT placed: explain them and ask what they would like to change.'
    ),
}

_COMPLETED_INSTRUCTIONS = (
    'The order is confirmed and complete. If it was confirmed just now, thank the customer, recap '
    'the order and give them the order number. Otherwise answer their follow-up questions. Do not collect order details again; if '
    'they want to change or add to the order, tell them a team member will follow up.'
)

_NO_FLOW_INSTRUCTIONS = 'Answer the customer\'s message helpfully, using the information here or your tools.'


def build_reply_prompt(
    business,
    block: dict | None,
    data: dict,
    *,
    products: list[dict],
    labels: dict | None = None,
    missing: list[str] = (),
    issues: list[str] = (),
    finished: list[str] = (),
    just_sent: list[str] = (),
) -> str:
    """System prompt for the customer reply at `block` (None: the business has no chat flow).

    `missing` / `issues` come from the deterministic checks in flow.py, and `finished` lists the
    blocks the customer completed with this message, so the reply can move the conversation on.
    `labels` maps detail field keys to labels (detail_labels), to show the collected details.
    `just_sent`: Send message blocks' fixed messages sent just before this reply.
    """
    block_type = block['block_type'] if block else None
    labels = labels or {}
    sections = [
        f'You are the customer service assistant for {business.business_name}, replying to a customer '
        f'over WhatsApp. Business description: {business.description or "not provided."} '
        f'Location: {business.location}. Reply in a friendly, concise way, in plain text suitable '
        'for a chat message. Never make up products, prices, opening hours or policies: use the '
        'information below, or your tools (list_products, list_faqs).'
    ]
    completed = bool(data.get('completed'))
    if block_type is None:
        instructions = _NO_FLOW_INSTRUCTIONS
    else:
        step = 'Done (order confirmed)' if completed else BLOCK_LABELS.get(block_type, block_type)
        status = [f'Current step: {step}.']
        if not completed:
            status.append(f'Goal of this step: {BLOCK_GOALS.get(block_type, "")}')
        if finished:
            status.append(f'The customer just completed: {", ".join(finished)}.')
        sections.append('## Where the conversation is\n' + '\n'.join(status))
        sections.append('## What we know so far\n' + format_collected(data, labels))
        if block_type == DETAILS_COLLECTION_BLOCK and not completed:
            sections.append('## Details to collect\n' + describe_detail_fields(block_detail_fields(block)))
        if missing and not completed:
            sections.append('## Still needed\n' + '\n'.join(f'- {item}' for item in missing))
        if issues:
            sections.append('## Problems to tell the customer about\n' + '\n'.join(f'- {i}' for i in issues))
        if just_sent:
            sections.append(
                '## Just sent\nThese automated messages were just sent to the customer, right before your '
                'reply (they are the last assistant messages in the conversation). Carry on from them; do '
                'not repeat them:\n' + '\n'.join(f'- "{message}"' for message in just_sent)
            )
        if completed:
            instructions = _COMPLETED_INSTRUCTIONS
        else:
            instructions = _REPLY_INSTRUCTIONS.get(block_type, _NO_FLOW_INSTRUCTIONS)
    if block_type in (None, START_BLOCK, PRODUCT_SELECTION_BLOCK) and not completed:
        sections.append('## Products on sale\n' + format_catalog(products))
    sections.append('## Your task now\n' + instructions)
    return '\n\n'.join(sections)


# --- Formatting helpers -------------------------------------------------------------------

def order_total(items: list[dict]) -> Decimal:
    return sum((Decimal(item['unit_price']) * item['quantity'] for item in items), Decimal('0.00'))


def format_catalog(products: list[dict]) -> str:
    if not products:
        return 'No products are on sale right now.'
    lines = []
    for product in products:
        stock = f'{product["quantity_available"]} available' if product['quantity_available'] else 'sold out'
        line = f'- id {product["id"]}: {product["name"]}, ${product["price"]} ({stock})'
        if product['description']:
            line += f'. {product["description"]}'
        lines.append(line)
    return '\n'.join(lines)


def format_items(items: list[dict]) -> str:
    return ', '.join(f'{item["quantity"]} × {item["name"]} (${item["unit_price"]} each)' for item in items)


def detail_labels(config_json: list[dict]) -> dict[str, str]:
    """Detail field key → label, from every DETAILS_COLLECTION_BLOCK of a chat configuration."""
    return {
        detail_field['key']: detail_field['label']
        for block in config_json
        if block['block_type'] == DETAILS_COLLECTION_BLOCK
        for detail_field in block_detail_fields(block)
    }


def describe_detail_fields(fields: list[dict], with_keys: bool = False) -> str:
    """One line per field, e.g. `- Postal code: a number from 100000 to 999999. 6 digits.`"""
    lines = []
    for detail_field in fields:
        field_type = detail_field['type']
        if field_type == DETAIL_TYPE_NUMBER:
            kind = 'a number'
            low, high = detail_field.get('min_value'), detail_field.get('max_value')
            if low is not None and high is not None:
                kind += f' from {low} to {high}'
            elif low is not None:
                kind += f' of at least {low}'
            elif high is not None:
                kind += f' of at most {high}'
        elif field_type == DETAIL_TYPE_EMAIL:
            kind = 'an email address'
        elif field_type == DETAIL_TYPE_PHONE:
            kind = 'a phone number'
        else:
            kind = f'text, at most {detail_field.get("max_length", DETAIL_TEXT_DEFAULT_MAX_LENGTH)} characters'
        name = f'"{detail_field["key"]}": {detail_field["label"]}' if with_keys else detail_field['label']
        line = f'- {name} ({kind})'
        if detail_field.get('description'):
            line += f'. {detail_field["description"]}'
        lines.append(line)
    return '\n'.join(lines)


def format_details(details: dict, labels: dict) -> str:
    return ', '.join(f'{labels.get(key, key)}: {value}' for key, value in details.items())


def format_collected(data: dict, labels: dict) -> str:
    items = data.get('items', [])
    lines = [
        f'Order: {format_items(items)}. Total: ${order_total(items)}.' if items else 'Order: nothing chosen yet.',
        f'Customer details: {format_details(data.get("details", {}), labels) or "none yet"}.',
    ]
    if data.get('order_id'):
        lines.append(f'Order number: #{data["order_id"]} (placed; payment pending).')
    return '\n'.join(lines)

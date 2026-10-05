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
    PRODUCT_SELECTION_BLOCK,
    REQUIRED_CUSTOMER_DETAILS,
    START_BLOCK,
)

BLOCK_LABELS = {
    START_BLOCK: 'Start',
    PRODUCT_SELECTION_BLOCK: 'Product selection',
    DETAILS_COLLECTION_BLOCK: 'Details collection',
    CONFIRMATION_BLOCK: 'Confirmation',
}

BLOCK_GOALS = {
    START_BLOCK: 'Welcome the customer, answer their questions and find out whether they want to order.',
    PRODUCT_SELECTION_BLOCK: 'Find out which products the customer wants, and how many of each.',
    DETAILS_COLLECTION_BLOCK: f"Collect the customer's {' and '.join(REQUIRED_CUSTOMER_DETAILS)}.",
    CONFIRMATION_BLOCK: 'Show the order summary and get the customer to confirm it.',
}

DETAIL_LABELS = {'name': 'name', 'email': 'email address'}

# --- Extraction (generate_structured) -----------------------------------------------------

_NULLABLE_STRING = {'anyOf': [{'type': 'string'}, {'type': 'null'}]}

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
        },
        'required': ['items'],
    },
    DETAILS_COLLECTION_BLOCK: {
        'type': 'object',
        'properties': {field: _NULLABLE_STRING for field in REQUIRED_CUSTOMER_DETAILS},
        'required': list(REQUIRED_CUSTOMER_DETAILS),
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
        'updated list. Return an empty list if they have not chosen any product yet.'
    ),
    DETAILS_COLLECTION_BLOCK: (
        "Extract the customer's own {fields} if they gave them anywhere in the conversation. Use "
        'null for anything they have not given. Copy them exactly; never make them up.\n\n'
        'Already known: {known}'
    ),
    CONFIRMATION_BLOCK: (
        'The assistant has shown the customer an order summary and asked them to confirm it. Based '
        'on the customer\'s latest message, set "decision" to "confirm" if they agree (e.g. yes, '
        'ok, confirm), "change" if they want to change something in the order or their details, or '
        '"none" otherwise (e.g. they asked a question).'
    ),
}


def build_extraction_prompt(business, block_type: str, data: dict, products: list[dict]) -> str:
    task = _EXTRACTION_TASKS[block_type].format(
        catalog=format_catalog(products),
        chosen=format_items(data.get('items', [])) or 'nothing yet',
        fields=' and '.join(DETAIL_LABELS[field] for field in REQUIRED_CUSTOMER_DETAILS),
        known=format_details(data.get('details', {})) or 'nothing yet',
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
        'and ask again. Only offer products from the list.'
    ),
    DETAILS_COLLECTION_BLOCK: (
        'Briefly acknowledge their order, then ask only for the details listed under "Still needed". '
        'Never ask again for details that are already known.'
    ),
    CONFIRMATION_BLOCK: (
        'Show the order summary from "What we know so far" (items, quantities, prices, total and '
        'customer details) and ask the customer to reply YES to confirm, or to tell you what to '
        'change. If they asked a question, answer it first.'
    ),
}

_COMPLETED_INSTRUCTIONS = (
    'The order is confirmed and complete. If it was confirmed just now, thank the customer and recap '
    'the order. Otherwise answer their follow-up questions. Do not collect order details again; if '
    'they want to change or add to the order, tell them a team member will follow up.'
)

_NO_FLOW_INSTRUCTIONS = 'Answer the customer\'s message helpfully, using the information here or your tools.'


def build_reply_prompt(
    business,
    block_type: str | None,
    data: dict,
    *,
    products: list[dict],
    missing: list[str] = (),
    issues: list[str] = (),
    finished: list[str] = (),
) -> str:
    """System prompt for the customer reply at `block_type` (None: the business has no chat flow).

    `missing` / `issues` come from the deterministic checks in flow.py, and `finished` lists the
    blocks the customer completed with this message, so the reply can move the conversation on.
    """
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
        sections.append('## What we know so far\n' + format_collected(data))
        if missing and not completed:
            sections.append('## Still needed\n' + '\n'.join(f'- {item}' for item in missing))
        if issues:
            sections.append('## Problems to tell the customer about\n' + '\n'.join(f'- {i}' for i in issues))
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


def format_details(details: dict) -> str:
    return ', '.join(f'{DETAIL_LABELS.get(field, field)}: {value}' for field, value in details.items())


def format_collected(data: dict) -> str:
    items = data.get('items', [])
    lines = [
        f'Order: {format_items(items)}. Total: ${order_total(items)}.' if items else 'Order: nothing chosen yet.',
        f'Customer details: {format_details(data.get("details", {})) or "none yet"}.',
    ]
    return '\n'.join(lines)

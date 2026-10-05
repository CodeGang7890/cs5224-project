"""The chat flow: replies to a customer message while moving the chat through the business's blocks.

handle_customer_message() runs one turn:
1. Save the customer message.
2. Find where the chat is: the ChatConfiguration block whose `id` is ChatSession.chat_state_id
   (the START_BLOCK if there's none, e.g. the block was deleted from the workflow).
3. Extract: ask the LLM for the block's JSON output (prompts.EXTRACTION_SCHEMAS) about the
   conversation so far.
4. Check deterministically (the CHECKS below) whether that completes the block, updating
   ChatSession.chat_state_data. If it does, move to `next_block_id` and repeat 3–4 there, so one
   message can complete several blocks ("2 Kopi C please, I'm Alice, alice@example.com").
   The last block completing marks the flow `completed`.
5. Save chat_state_id / chat_state_data, then ask the LLM for the reply, with the block's reply
   prompt (what's known, what's still missing, what went wrong), and save it.
"""

import copy
from dataclasses import dataclass, field

from django.core.exceptions import ValidationError
from django.core.validators import EmailValidator
from django.db import transaction
from django.utils import timezone

from . import llm, prompts
from .constants import (
    CONFIRMATION_BLOCK,
    DETAILS_COLLECTION_BLOCK,
    PRODUCT_SELECTION_BLOCK,
    REQUIRED_CUSTOMER_DETAILS,
    SENT_BY_BUSINESS_AUTOMATED,
    SENT_BY_CUSTOMER,
    START_BLOCK,
)
from .models import DISPLAY_NAME_MAX_LENGTH, ChatConfiguration, ChatSession
from .tools import Toolbox, active_products
from .validators import validate_chat_state_data

# How many of the latest messages the LLM sees (keeps the prompt within the context window).
HISTORY_MAX_MESSAGES = 20
EMAIL_MAX_LENGTH = 254
PRODUCTS_MISSING = 'which products, and how many of each'


@dataclass
class CheckResult:
    """Outcome of a block's deterministic check of the LLM's extraction."""

    complete: bool
    missing: list[str] = field(default_factory=list)  # still needed, for the reply prompt
    issues: list[str] = field(default_factory=list)  # problems to tell the customer about
    go_back: bool = False  # the customer wants to change something: restart after the START_BLOCK


@dataclass
class Turn:
    """Where one message left the chat."""

    block: dict
    data: dict
    missing: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    finished: list[str] = field(default_factory=list)  # labels of blocks completed by this message
    # For debugging (the Chat Sandbox shows them): each extraction + check, and why the loop stopped.
    steps: list[dict] = field(default_factory=list)
    stop_reason: str = ''


@dataclass
class TurnResult:
    reply: dict  # the saved chat message
    debug: dict  # what happened inside the turn, for the Chat Sandbox's debug panel


def handle_customer_message(session_id: int, message: str) -> TurnResult:
    """Saves the customer message, runs the flow, then saves and returns the assistant's reply.

    The customer message is saved first, so it's kept if an LLM call fails (llm.LLMError). The
    flow state is saved before the reply is generated, so it's kept if only the reply fails.
    """
    append_chat_message(session_id, message, SENT_BY_CUSTOMER)
    session = ChatSession.objects.select_related('business').get(pk=session_id)
    business = session.business
    history = to_llm_history(session.chat_message_json)
    products = active_products(business)
    chat_config = ChatConfiguration.objects.filter(business=business).first()
    before = {'chat_state_id': session.chat_state_id, 'chat_state_data': session.chat_state_data}

    if chat_config is None:  # no flow to follow (only possible for old sessions): just answer
        turn = None
        system_prompt = prompts.build_reply_prompt(business, None, {}, products=products)
    else:
        turn = advance(chat_config, session.chat_state_id, session.chat_state_data, history, products)
        save_flow_state(session_id, turn)
        system_prompt = prompts.build_reply_prompt(
            business,
            turn.block['block_type'],
            turn.data,
            products=products,
            missing=turn.missing,
            issues=turn.issues,
            finished=turn.finished,
        )
    toolbox = Toolbox(business)
    reply = llm.generate_chat_reply(system_prompt, history, toolbox)
    saved = append_chat_message(session_id, reply.strip() or '…', SENT_BY_BUSINESS_AUTOMATED)
    debug = {
        'before': before,
        'after': {
            'chat_state_id': turn.block['id'],
            'block_type': turn.block['block_type'],
            'chat_state_data': turn.data,
        } if turn else before,
        'steps': turn.steps if turn else [],
        'stop_reason': turn.stop_reason if turn else 'The business has no chat configuration: reply only.',
        'finished': turn.finished if turn else [],
        'missing': turn.missing if turn else [],
        'issues': turn.issues if turn else [],
        'reply_system_prompt': system_prompt,
        'tool_calls': toolbox.calls,
    }
    return TurnResult(reply=saved, debug=debug)


def advance(
    chat_config: ChatConfiguration, state_id, state_data: dict, history: list[dict], products: list[dict]
) -> Turn:
    """Steps 2–4: runs the extraction + check of the current block, moving on while blocks complete."""
    block = chat_config.get_block(state_id) or chat_config.start_block
    turn = Turn(block=block, data=copy.deepcopy(state_data))
    if turn.data.get('completed'):
        turn.stop_reason = 'The flow was already completed: no extraction, reply only.'
        return turn

    entered_now = False
    # Each block is visited at most twice (once more after a "change" at confirmation).
    for _ in range(2 * len(chat_config.config_json) + 1):
        block_type = block['block_type']
        check = CHECKS.get(block_type)
        # A confirmation reached with this message hasn't shown the customer the summary yet.
        if check is None:
            turn.stop_reason = f'No check for block type {block_type}.'
            break
        if block_type == CONFIRMATION_BLOCK and entered_now:
            turn.stop_reason = (
                'Confirmation reached with this message: not checked until the customer has seen the summary.'
            )
            break
        system_prompt = prompts.build_extraction_prompt(
            chat_config.business, block_type, turn.data, products
        )
        extracted = llm.generate_structured(system_prompt, history, prompts.EXTRACTION_SCHEMAS[block_type])
        result = check(extracted, turn.data, products)
        turn.missing, turn.issues = result.missing, result.issues
        turn.steps.append({
            'block_id': block['id'],
            'block_type': block_type,
            'system_prompt': system_prompt,
            'extracted': extracted,
            'complete': result.complete,
            'go_back': result.go_back,
            'missing': result.missing,
            'issues': result.issues,
            'chat_state_data': copy.deepcopy(turn.data),
        })

        if result.go_back:
            block = chat_config.get_block(chat_config.start_block['next_block_id']) or chat_config.start_block
        elif result.complete:
            next_block = chat_config.get_block(block['next_block_id'])
            if next_block is None and block_type == START_BLOCK:
                turn.stop_reason = 'A lone Start block has nothing to complete: staying there.'
                break
            turn.finished.append(prompts.BLOCK_LABELS.get(block_type, block_type))
            if next_block is None:
                turn.data['completed'] = True
                turn.stop_reason = 'The last block completed: the flow is completed.'
                break
            block = next_block
        else:
            turn.stop_reason = 'This block is not complete yet: waiting for the customer.'
            break
        entered_now = True
        turn.missing, turn.issues = [], []
    turn.block = block
    return turn


# --- Deterministic checks, one per block type ---------------------------------------------
# Each takes the LLM's extraction, the chat_state_data (updated in place) and the products on sale.

def check_start(extracted: dict, data: dict, products: list[dict]) -> CheckResult:
    return CheckResult(complete=extracted.get('wants_to_order') is True)


def check_product_selection(extracted: dict, data: dict, products: list[dict]) -> CheckResult:
    """Complete when every chosen product is on sale, with a quantity that's in stock."""
    by_id = {product['id']: product for product in products}
    raw_items = extracted.get('items')
    if not isinstance(raw_items, list) or not raw_items:
        # Nothing (new) chosen: keep an earlier choice, e.g. when coming back after a "change".
        if data.get('items'):
            return CheckResult(complete=True)
        return CheckResult(complete=False, missing=[PRODUCTS_MISSING])

    items, issues = [], []
    for raw in raw_items:
        if not isinstance(raw, dict):
            continue
        product = by_id.get(_as_int(raw.get('product_id')))
        quantity = _as_int(raw.get('quantity'))
        if product is None:
            issues.append('One of the products the customer asked for is not on sale.')
        elif quantity is None or quantity < 1:
            issues.append(f'The customer has not said how many {product["name"]} they want.')
        elif quantity > product['quantity_available']:
            issues.append(f'Only {product["quantity_available"]} {product["name"]} are available.')
        else:
            items.append({
                'product_id': product['id'],
                'name': product['name'],
                'unit_price': product['price'],
                'quantity': quantity,
            })
    if items:
        data['items'] = items
    complete = bool(items) and not issues
    return CheckResult(complete=complete, missing=[] if complete else [PRODUCTS_MISSING], issues=issues)


def check_details_collection(extracted: dict, data: dict, products: list[dict]) -> CheckResult:
    """Complete when every REQUIRED_CUSTOMER_DETAILS is known and valid. Known values are kept."""
    details = data.setdefault('details', {})
    issues = []
    for name in REQUIRED_CUSTOMER_DETAILS:
        value = extracted.get(name)
        if not isinstance(value, str) or not value.strip():
            continue  # not given (this time): keep what's known
        value = value.strip()
        problem = _detail_problem(name, value)
        if problem:
            issues.append(problem)
        else:
            details[name] = value
    if not details:
        del data['details']
    missing = [prompts.DETAIL_LABELS[name] for name in REQUIRED_CUSTOMER_DETAILS if name not in details]
    return CheckResult(complete=not missing and not issues, missing=missing, issues=issues)


def check_confirmation(extracted: dict, data: dict, products: list[dict]) -> CheckResult:
    decision = extracted.get('decision')
    return CheckResult(complete=decision == 'confirm', go_back=decision == 'change')


CHECKS = {
    START_BLOCK: check_start,
    PRODUCT_SELECTION_BLOCK: check_product_selection,
    DETAILS_COLLECTION_BLOCK: check_details_collection,
    CONFIRMATION_BLOCK: check_confirmation,
}


def _as_int(value) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _detail_problem(name: str, value: str) -> str | None:
    if name == 'name' and len(value) > DISPLAY_NAME_MAX_LENGTH:
        return f'The name is too long (max {DISPLAY_NAME_MAX_LENGTH} characters).'
    if name == 'email':
        try:
            EmailValidator()(value)
        except ValidationError:
            return f'"{value}" is not a valid email address.'
        if len(value) > EMAIL_MAX_LENGTH:
            return 'The email address is too long.'
    return None


# --- Persistence --------------------------------------------------------------------------

def to_llm_history(chat_messages: list[dict]) -> list[dict]:
    """The latest messages as LLM chat messages: the customer is `user`, the business `assistant`."""
    return [
        {'role': 'user' if item['sent_by'] == SENT_BY_CUSTOMER else 'assistant', 'content': item['message']}
        for item in chat_messages[-HISTORY_MAX_MESSAGES:]
    ]


def append_chat_message(session_id: int, message: str, sent_by: str) -> dict:
    """Appends a message (timestamped now) to a session and updates its last_chat_time.

    Row-locked in its own short transaction, so concurrent messages aren't lost. (The lock
    isn't held during the LLM call, which can take a while.)
    """
    with transaction.atomic():
        session = ChatSession.objects.select_for_update().get(pk=session_id)
        now = timezone.now()
        chat_message = {'message': message, 'sent_by': sent_by, 'message_time': now.isoformat()}
        session.chat_message_json.append(chat_message)
        session.last_chat_time = now
        session.save(update_fields=['chat_message_json', 'last_chat_time'])
    return chat_message


def save_flow_state(session_id: int, turn: Turn) -> None:
    """Saves where the chat is and what it has collected.

    A collected name also fills in an empty display_name.
    """
    validate_chat_state_data(turn.data)
    with transaction.atomic():
        session = ChatSession.objects.select_for_update().get(pk=session_id)
        session.chat_state_id = turn.block['id']
        session.chat_state_data = turn.data
        fields = ['chat_state_id', 'chat_state_data']
        name = turn.data.get('details', {}).get('name')
        if name and not session.display_name:
            session.display_name = name
            fields.append('display_name')
        session.save(update_fields=fields)

"""The order sub-flow: a small deterministic state machine over the fixed order steps.

Product selection → Details collection → Confirmation (constants.ORDER_STEPS), started from the
`start` step when the router finds the customer wants to order. advance() runs one message:
1. Extract: ask the LLM for the step's JSON output (prompts.extraction_schema) about the
   conversation so far. At the step the chat was at when the message arrived, the extraction can
   also say `go_back_to` an earlier step (GO_BACK_TARGETS): the chat then returns there, keeping
   all its data, and that step runs on the same message.
2. Check deterministically (the CHECKS below) whether that completes the step, updating
   ChatSession.chat_state_data. If it does, move to the next step and repeat 1–2 there, so one
   message can complete several steps ("2 Kopi C please, that's all, I'm Alice, alice@example.com").
   Confirmation completing marks the order `completed`.
Then commit_turn() saves chat_state_id / chat_state_data and, if the customer confirmed, places the
order (checkout_app: an OrderItem, with its stock reserved) in the same transaction.
"""

import copy
import math
import re
from dataclasses import dataclass, field

from django.core.exceptions import ValidationError
from django.core.validators import EmailValidator
from django.db import transaction

from checkout_app.services import OrderError, place_order

from . import llm, prompts
from .constants import (
    CHAT_STEPS,
    DETAIL_TYPE_EMAIL,
    DETAIL_TYPE_NUMBER,
    DETAIL_TYPE_PHONE,
    ORDER_STEPS,
    STEP_CONFIRMATION,
    STEP_DETAILS_COLLECTION,
    STEP_LABELS,
    STEP_PRODUCT_SELECTION,
    STEP_START,
)
from .models import DISPLAY_NAME_MAX_LENGTH, ChatConfiguration, ChatSession
from .validators import DETAIL_TEXT_DEFAULT_MAX_LENGTH, is_required_detail, validate_chat_state_data

EMAIL_MAX_LENGTH = 254
PRODUCTS_MISSING = 'which products, and how many of each'
PRODUCTS_CONFIRMATION_MISSING = (
    'the customer to confirm that this is everything they want (recap the order and ask if they want anything else)'
)

# The step after each order step (None: the last one).
NEXT_STEP = {
    STEP_PRODUCT_SELECTION: STEP_DETAILS_COLLECTION,
    STEP_DETAILS_COLLECTION: STEP_CONFIRMATION,
    STEP_CONFIRMATION: None,
}
# The earlier steps the customer can go back to from each step, to change what was collected there.
GO_BACK_TARGETS = {
    STEP_PRODUCT_SELECTION: [],
    STEP_DETAILS_COLLECTION: [STEP_PRODUCT_SELECTION],
    STEP_CONFIRMATION: [STEP_PRODUCT_SELECTION, STEP_DETAILS_COLLECTION],
}
# Each step is visited at most twice in one message (once more after a "change" at confirmation).
MAX_STEPS_PER_MESSAGE = 2 * len(ORDER_STEPS) + 1


@dataclass
class CheckResult:
    """Outcome of a step's deterministic check of the LLM's extraction."""

    complete: bool
    missing: list[str] = field(default_factory=list)  # still needed, for the reply prompt
    issues: list[str] = field(default_factory=list)  # problems to tell the customer about
    go_back: bool = False  # the customer wants to change something: back to Product selection


@dataclass
class Turn:
    """Where one message left the order."""

    step: str  # constants.CHAT_STEPS
    data: dict
    missing: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    finished: list[str] = field(default_factory=list)  # labels of steps completed by this message
    # For debugging (the Chat Sandbox shows them): each extraction + check, and why the loop stopped.
    steps: list[dict] = field(default_factory=list)
    stop_reason: str = ''
    # The earlier step the customer went back to with this message (go_back_to), if any.
    went_back_to: str | None = None
    # Set when Confirmation passed with this message: chat_state_data at that moment. commit_turn()
    # then places the order, or undoes the confirmation if it can't.
    confirmation: dict | None = None


def advance(
    chat_config: ChatConfiguration,
    step: str,
    state_data: dict,
    history: list[dict],
    products: list[dict],
    *,
    start_order: bool,
) -> Turn:
    """Runs the extraction + check of the current order step, moving on while steps complete.

    `step` / `state_data`: the session's chat_state_id / chat_state_data. At `start` (no order in
    progress), nothing happens unless the router found the customer wants to order (`start_order`):
    then the order starts at Product selection, on this same message.
    """
    step = step if step in CHAT_STEPS else STEP_START
    turn = Turn(step=step, data=copy.deepcopy(state_data))
    if turn.data.get('completed'):
        turn.stop_reason = 'The order was already placed: no extraction, reply only.'
        return turn
    if step == STEP_START:
        if not start_order:
            turn.stop_reason = 'No order in progress, and the router found no wish to order: reply only.'
            return turn
        step = STEP_PRODUCT_SELECTION

    business, fields = chat_config.business, chat_config.detail_fields
    # Going back is only offered at the step the chat was at when this message arrived. A step
    # reached during this message (e.g. Details collection, right after "That's all" finished
    # Product selection) would otherwise read the message that completed the earlier step as a
    # request to go back to it. This also means one go-back per message at most.
    entered_now = turn.step == STEP_START
    for _ in range(MAX_STEPS_PER_MESSAGE):
        # A confirmation reached with this message hasn't shown the customer the summary yet.
        if step == STEP_CONFIRMATION and entered_now:
            turn.stop_reason = (
                'Confirmation reached with this message: not checked until the customer has seen the summary.'
            )
            break
        targets = [] if entered_now else GO_BACK_TARGETS[step]
        system_prompt = prompts.build_extraction_prompt(business, step, turn.data, products, fields, go_back=targets)
        extracted = llm.generate_structured(system_prompt, history, prompts.extraction_schema(step, fields, targets))
        target = extracted.get('go_back_to')
        if isinstance(target, str) and target in targets:
            # Back to an earlier step, keeping everything. It runs on this same message, so "I also
            # want a Kaya Toast" updates the order straight away.
            if target == STEP_PRODUCT_SELECTION:
                turn.data.pop('items_confirmed', None)  # the order must be recapped and confirmed again
            turn.steps.append(_debug_step(step, system_prompt, extracted, CheckResult(complete=False), turn.data, target))
            turn.went_back_to = target
            step = target
            entered_now = True
            turn.missing, turn.issues = [], []
            continue

        result = CHECKS[step](extracted, turn.data, products, fields)
        turn.missing, turn.issues = result.missing, result.issues
        turn.steps.append(_debug_step(step, system_prompt, extracted, result, turn.data))

        if result.go_back:
            step = STEP_PRODUCT_SELECTION
        elif result.complete:
            if step == STEP_CONFIRMATION and 'order_id' not in turn.data and turn.confirmation is None:
                turn.confirmation = copy.deepcopy(turn.data)
            turn.finished.append(STEP_LABELS[step])
            if NEXT_STEP[step] is None:
                turn.data['completed'] = True
                turn.stop_reason = 'Confirmation completed: the order is confirmed.'
                break
            step = NEXT_STEP[step]
        else:
            turn.stop_reason = 'This step is not complete yet: waiting for the customer.'
            break
        entered_now = True
        turn.missing, turn.issues = [], []
    else:
        turn.stop_reason = f'Stopped after {MAX_STEPS_PER_MESSAGE} steps in one message.'
    turn.step = step
    return turn


def _debug_step(step: str, system_prompt: str, extracted: dict, result: CheckResult, data: dict, go_back_to=None):
    """One extraction + check, for Turn.steps (the Chat Sandbox's debug panel)."""
    return {
        'step': step,
        'system_prompt': system_prompt,
        'extracted': extracted,
        'complete': result.complete,
        'go_back': result.go_back or go_back_to is not None,
        'go_back_to': go_back_to,
        'missing': result.missing,
        'issues': result.issues,
        'chat_state_data': copy.deepcopy(data),
    }


# --- Deterministic checks, one per order step ----------------------------------------------
# Each takes the LLM's extraction, the chat_state_data (updated in place), the products on sale
# and the Details collection step's detail fields.

def check_product_selection(extracted: dict, data: dict, products: list[dict], fields: list[dict]) -> CheckResult:
    """Complete when the customer has confirmed a valid order is everything they want.

    Every chosen product must be on sale, with a quantity that's in stock. Then the customer must
    say they're done (`done_choosing`) about the cart as it already was, so they've seen it
    recapped: a message that adds or changes items ("2 Kopi C, that's all") gets a recap first.
    Once confirmed, `items_confirmed` is kept until the cart changes, so coming back here after a
    "change" at confirmation (e.g. to fix an email) passes straight through.
    A sold-out product (0 available) or a quantity above what's available can never be ordered,
    and is checked again on every message for what's already in the cart: an item that can't be
    ordered any more (e.g. sold out since it was chosen) is dropped, with the problem explained.
    """
    by_id = {product['id']: product for product in products}
    previous = data.get('items', [])
    raw_items = extracted.get('items')
    issues = []
    if isinstance(raw_items, list) and raw_items:
        items = []
        for raw in raw_items:
            if not isinstance(raw, dict):
                continue
            product = by_id.get(_as_int(raw.get('product_id')))
            quantity = _as_int(raw.get('quantity'))
            problem = item_problem(product, quantity)
            if problem:
                issues.append(problem)
            else:
                items.append({
                    'product_id': product['id'],
                    'name': product['name'],
                    'unit_price': product['price'],
                    'quantity': quantity,
                })
        if items:
            data['items'] = items
    # Nothing (new) chosen: the earlier choice stands, but only what can still be ordered.
    orderable = []
    for item in data.get('items', []):
        problem = item_problem(by_id.get(item['product_id']), item['quantity'], item['name'])
        if problem:
            issues.append(f'{problem} It was removed from the order.')
        else:
            orderable.append(item)
    if orderable:
        data['items'] = orderable
    else:
        data.pop('items', None)

    if _cart(data.get('items', [])) != _cart(previous):
        data.pop('items_confirmed', None)  # a changed cart must be confirmed again
        changed = True
    else:
        changed = False
    if not data.get('items') or issues:
        return CheckResult(complete=False, missing=[PRODUCTS_MISSING], issues=issues)
    if not changed and (extracted.get('done_choosing') is True or data.get('items_confirmed')):
        data['items_confirmed'] = True
        return CheckResult(complete=True)
    return CheckResult(complete=False, missing=[PRODUCTS_CONFIRMATION_MISSING])


def item_problem(product: dict | None, quantity: int | None, name: str | None = None) -> str | None:
    """Why `quantity` of `product` can't be ordered (for the reply prompt), or None if it can.

    `product` is None when it isn't on sale; `name` is the cart's name for it, if it was chosen earlier.
    """
    if product is None:
        if name:
            return f'{name} is no longer on sale.'
        return 'One of the products the customer asked for is not on sale.'
    available = product['quantity_available']
    if available < 1:
        return f'{product["name"]} has run out (sold out) for now, so it cannot be ordered.'
    if quantity is None or quantity < 1:
        return f'The customer has not said how many {product["name"]} they want.'
    if quantity > available:
        return f'Only {available} {product["name"]} are available, so {quantity} cannot be ordered.'
    return None


def _cart(items: list[dict]) -> list[tuple[int, int]]:
    """What a cart contains, for comparing: (product_id, quantity) pairs, in product order."""
    return sorted((item['product_id'], item['quantity']) for item in items)


def check_details_collection(extracted: dict, data: dict, products: list[dict], fields: list[dict]) -> CheckResult:
    """Complete when every *required* detail field is known and valid.

    Values are checked by field type (clean_detail_value); known values are kept when the LLM
    returns nothing for them, and an invalid value never replaces a valid one. Optional fields
    (`required: false`) are stored when given, but never hold the chat back: a problem with one is
    explained to the customer without blocking.
    """
    details = data.setdefault('details', {})
    issues, blocking = [], False
    for detail_field in fields:
        value, problem = clean_detail_value(detail_field, extracted.get(detail_field['key']))
        if problem:
            issues.append(problem)
            blocking = blocking or is_required_detail(detail_field)
        elif value is not None:
            details[detail_field['key']] = value
    if not details:
        del data['details']
    missing = [f['label'] for f in fields if is_required_detail(f) and f['key'] not in details]
    return CheckResult(complete=not missing and not blocking, missing=missing, issues=issues)


def check_confirmation(extracted: dict, data: dict, products: list[dict], fields: list[dict]) -> CheckResult:
    decision = extracted.get('decision')
    return CheckResult(complete=decision == 'confirm', go_back=decision == 'change')


CHECKS = {
    STEP_PRODUCT_SELECTION: check_product_selection,
    STEP_DETAILS_COLLECTION: check_details_collection,
    STEP_CONFIRMATION: check_confirmation,
}


def _as_int(value) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


PHONE_PATTERN = re.compile(r'^\+?[\d\s()\-]+$')


def clean_detail_value(detail_field: dict, raw) -> tuple[str | int | float | None, str | None]:
    """The LLM's value for one detail field, checked against its type: (value, None) if valid,
    (None, problem) if not, or (None, None) if it wasn't given."""
    if raw is None or isinstance(raw, bool) or (isinstance(raw, str) and not raw.strip()):
        return None, None
    label, field_type = detail_field['label'], detail_field['type']

    if field_type == DETAIL_TYPE_NUMBER:
        number = raw if isinstance(raw, (int, float)) else _parse_number(str(raw))
        if number is None:
            return None, f'{label} must be a number (got "{raw}").'
        if 'min_value' in detail_field and number < detail_field['min_value']:
            return None, f'{label} must be at least {detail_field["min_value"]}.'
        if 'max_value' in detail_field and number > detail_field['max_value']:
            return None, f'{label} must be at most {detail_field["max_value"]}.'
        return (int(number) if float(number).is_integer() else number), None

    value = str(raw).strip()
    if field_type == DETAIL_TYPE_EMAIL:
        try:
            EmailValidator()(value)
        except ValidationError:
            return None, f'"{value}" is not a valid email address.'
        if len(value) > EMAIL_MAX_LENGTH:
            return None, f'{label} is too long.'
    elif field_type == DETAIL_TYPE_PHONE:
        digits = sum(char.isdigit() for char in value)
        if not PHONE_PATTERN.match(value) or not 6 <= digits <= 15:
            return None, f'"{value}" is not a valid phone number.'
    else:  # text
        max_length = detail_field.get('max_length', DETAIL_TEXT_DEFAULT_MAX_LENGTH)
        if len(value) > max_length:
            return None, f'{label} is too long (max {max_length} characters).'
    return value, None


def _parse_number(text: str) -> int | float | None:
    try:
        number = float(text.replace(',', '').strip())
    except ValueError:
        return None
    return number if math.isfinite(number) else None


# --- Persistence --------------------------------------------------------------------------

def commit_turn(session_id: int, turn: Turn) -> None:
    """Saves where the order is and what it has collected, placing the order if the customer confirmed.

    One transaction, with the session row locked: the order (checkout_app.services.place_order,
    which locks the products and reserves their stock) and the saved state can't disagree. If the
    order can't be placed (e.g. sold out since it was chosen), the confirmation is undone: the
    chat stays at Confirmation, and the problems go into the reply prompt. A collected name also
    fills in an empty display_name.
    """
    with transaction.atomic():
        session = ChatSession.objects.select_for_update().select_related('business').get(pk=session_id)
        if turn.confirmation is not None:
            data = turn.confirmation
            if not data.get('items'):
                turn.stop_reason += ' Nothing was chosen, so no order was placed.'
            else:
                try:
                    order = place_order(
                        session.business,
                        data['items'],
                        data.get('details', {}),
                        chat_session=session,
                        is_sandbox=session.is_sandbox,
                    )
                except OrderError as exc:
                    label = STEP_LABELS[STEP_CONFIRMATION]
                    turn.step, turn.data = STEP_CONFIRMATION, data
                    turn.finished = [f for f in turn.finished if f != label]
                    turn.missing = []
                    turn.issues = [*exc.problems, 'The order was not placed: ask the customer what to change.']
                    turn.stop_reason = f'The order could not be placed: {exc}'
                else:
                    turn.data['order_id'] = order.pk
        validate_chat_state_data(turn.data)
        session.chat_state_id = turn.step
        session.chat_state_data = turn.data
        fields = ['chat_state_id', 'chat_state_data']
        name = turn.data.get('details', {}).get('name')  # a field with the key `name`, if any
        if isinstance(name, str) and not session.display_name:
            session.display_name = name[:DISPLAY_NAME_MAX_LENGTH]
            fields.append('display_name')
        session.save(update_fields=fields)

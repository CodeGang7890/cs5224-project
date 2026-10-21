"""The order and booking sub-flows: small deterministic state machines over fixed steps.

- Ordering products: Product selection → Details collection → Confirmation (constants.ORDER_STEPS),
  started from `start` when the router finds the customer wants to order.
- Booking a service: Service selection → Time slot → Booking details → Booking confirmation
  (constants.BOOKING_STEPS), started when the router finds they want to book. The free times are
  worked out in code (checkout_app.schedule): the LLM only extracts what the customer asked for
  (a number from the times offered, a day, a time, a part of the day), and the times offered are
  stored (chat_state_data.slot_options) so "the 2nd one" maps to a time the code chose.
advance() runs one message:
1. Extract: ask the LLM for the step's JSON output (prompts.extraction_schema) about the
   conversation so far. At the step the chat was at when the message arrived, the extraction can
   also say `go_back_to` an earlier step (GO_BACK_TARGETS): the chat then returns there, keeping
   all its data, and that step runs on the same message.
2. Check deterministically (the CHECKS below) whether that completes the step, updating
   ChatSession.chat_state_data. If it does, move to the next step and repeat 1–2 there, so one
   message can complete several steps ("2 Kopi C please, that's all, I'm Alice, alice@example.com").
Both confirmations have two substages: `not_confirmed` (the chat sends the summary, a fixed
template, and waits) and `confirmed`. When the customer confirms, commit_turn() places the order
(checkout_app.place_order: an OrderItem, with its stock reserved) or the booking
(checkout_app.place_booking: a ScheduleItem, taking up its time) in the same transaction as saving
the state, and only then is the customer told it's confirmed (again a fixed template). The chat
then goes back to `start`, keeping only `last_order_id` / `last_booking_id`, so the customer can
order or book again.

A port of configuration-service's chat_app/order_flow.py to SQLAlchemy: the checks that need the
database (the free times) open short sessions from StepContext.sessions; commit_turn() takes a
sessionmaker and runs one transaction.
"""

import copy
import math
from contextlib import nullcontext
import re
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from .. import llm
from ..models import BusinessConfiguration, ChatSession, Service
from . import dates as timezone  # timezone.now(), like django.utils.timezone
from . import prompts
from .checkout import BookingError, OrderError, place_booking, place_order
from .dates import parse_datetime
from .emails import validate_email
from .errors import ValidationError
from .schedule import free_slots, local, schedule_tz, start_problem
from .settings import ChatSettings
from .constants import (
    BOOKING_STEPS,
    CHAT_STEPS,
    CONFIRMATION_CONFIRMED,
    CONFIRMATION_NOT_CONFIRMED,
    CONFIRMATION_STEPS,
    DETAIL_TYPE_EMAIL,
    DETAIL_TYPE_NUMBER,
    ORDER_STEPS,
    STEP_BOOKING_CONFIRMATION,
    STEP_BOOKING_DETAILS,
    STEP_CONFIRMATION,
    STEP_DETAILS_COLLECTION,
    STEP_LABELS,
    STEP_PRODUCT_SELECTION,
    STEP_SERVICE_SELECTION,
    STEP_SLOT_SELECTION,
    STEP_START,
)
from .prompts import PARTS_OF_DAY
from .validators import DETAIL_TEXT_DEFAULT_MAX_LENGTH, SLOT_OPTIONS_MAX, is_required_detail, validate_chat_state_data

DISPLAY_NAME_MAX_LENGTH = 150  # chat_app.models
EMAIL_MAX_LENGTH = 254
PRODUCTS_MISSING = 'which products, and how many of each'
PRODUCTS_CONFIRMATION_MISSING = (
    'the customer to confirm that this is everything they want (recap the order and ask if they want anything else)'
)

SERVICE_MISSING = 'which service they would like to book'
SLOT_MISSING = 'a time for the booking: one of the times offered, or another day or time'

# The step after each step (None: the last one, a confirmation).
NEXT_STEP = {
    STEP_PRODUCT_SELECTION: STEP_DETAILS_COLLECTION,
    STEP_DETAILS_COLLECTION: STEP_CONFIRMATION,
    STEP_CONFIRMATION: None,
    STEP_SERVICE_SELECTION: STEP_SLOT_SELECTION,
    STEP_SLOT_SELECTION: STEP_BOOKING_DETAILS,
    STEP_BOOKING_DETAILS: STEP_BOOKING_CONFIRMATION,
    STEP_BOOKING_CONFIRMATION: None,
}
# Where a "change" (or a step whose earlier choice is gone) goes back to: the flow's first step.
FIRST_STEP = {step: ORDER_STEPS[0] for step in ORDER_STEPS} | {step: BOOKING_STEPS[0] for step in BOOKING_STEPS}
# The earlier steps the customer can go back to from each step, to change what was collected there.
GO_BACK_TARGETS = {
    STEP_PRODUCT_SELECTION: [],
    STEP_DETAILS_COLLECTION: [STEP_PRODUCT_SELECTION],
    STEP_CONFIRMATION: [STEP_PRODUCT_SELECTION, STEP_DETAILS_COLLECTION],
    STEP_SERVICE_SELECTION: [],
    STEP_SLOT_SELECTION: [STEP_SERVICE_SELECTION],
    STEP_BOOKING_DETAILS: [STEP_SERVICE_SELECTION, STEP_SLOT_SELECTION],
    STEP_BOOKING_CONFIRMATION: [STEP_SERVICE_SELECTION, STEP_SLOT_SELECTION, STEP_BOOKING_DETAILS],
}
# Each step is visited at most twice in one message (once more after a "change" at confirmation).
MAX_STEPS_PER_MESSAGE = 2 * max(len(ORDER_STEPS), len(BOOKING_STEPS)) + 1

# Times offered at the Time slot step: at most this many, spread out (at most a few a day).
SLOT_OPTIONS_OFFERED = min(6, SLOT_OPTIONS_MAX)
SLOT_OPTIONS_PER_DAY = 3
DEFAULT_SLOT_DAYS = 7  # when the customer hasn't said which days


@dataclass
class StepContext:
    """What the steps' checks need besides the extraction and chat_state_data."""

    products: list[dict]  # tools.active_products
    services: list[Service]  # tools.active_services
    fields: list[dict]  # the branch's detail fields (ChatSettings.detail_fields_for)
    now: datetime
    sessions: sessionmaker | None = None  # for the checks that read the database (the free times)


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
    # Set by commit_turn() once the order / booking is saved: the OrderItem's / ScheduleItem's pk.
    placed_order_id: int | None = None
    placed_booking_id: int | None = None
    # Set after commit_turn() (payments.store_payment_for_placed): the Xendit payment link the
    # customer pays with (None: no link was created; see payment_error).
    payment_link: str | None = None
    payment_error: str | None = None

    @property
    def confirmation_status(self) -> str | None:
        """Confirmation's (or Booking confirmation's) substage after this turn (None: at neither).
        Only valid after commit_turn(): `confirmed` means the order / booking is in the database."""
        if self.placed_order_id is not None or self.placed_booking_id is not None:
            return CONFIRMATION_CONFIRMED
        return CONFIRMATION_NOT_CONFIRMED if self.step in CONFIRMATION_STEPS else None


def advance(
    chat_config: ChatSettings,
    step: str,
    state_data: dict,
    history: list[dict],
    products: list[dict],
    *,
    start_order: bool,
    start_booking: bool = False,
    services: list[Service] = (),
    now: datetime | None = None,
    sessions: sessionmaker | None = None,
) -> Turn:
    """Runs the extraction + check of the current step, moving on while steps complete.

    `step` / `state_data`: the session's chat_state_id / chat_state_data. At `start` (nothing in
    progress), nothing happens unless the router found the customer wants to order (`start_order`:
    the order starts at Product selection) or book (`start_booking`, if `services` (the bookable
    ones) isn't empty: the booking starts at Service selection), on this same message. Ordering
    wins if it's both.
    """
    step = step if step in CHAT_STEPS else STEP_START
    turn = Turn(step=step, data=copy.deepcopy(state_data))
    if step == STEP_START:
        if start_order:
            step = STEP_PRODUCT_SELECTION
        elif start_booking and services:
            step = STEP_SERVICE_SELECTION
        else:
            turn.stop_reason = 'Nothing in progress, and the router found no wish to order or book: reply only.'
            return turn

    # The order steps ask for the product details, the booking steps for the schedule details (a
    # turn never moves from one branch to the other).
    business, fields = chat_config.business, chat_config.detail_fields_for(step)
    context = StepContext(
        products=products, services=list(services), fields=fields, now=now or timezone.now(), sessions=sessions
    )
    # Going back is only offered at the step the chat was at when this message arrived. A step
    # reached during this message (e.g. Details collection, right after "That's all" finished
    # Product selection) would otherwise read the message that completed the earlier step as a
    # request to go back to it. This also means one go-back per message at most.
    entered_now = turn.step == STEP_START
    for _ in range(MAX_STEPS_PER_MESSAGE):
        # A confirmation reached with this message hasn't shown the customer the summary yet: the
        # reply will (substage not_confirmed).
        if step in CONFIRMATION_STEPS and entered_now:
            turn.stop_reason = (
                f'{STEP_LABELS[step]} reached with this message: not checked until the customer has seen the summary.'
            )
            break
        targets = [] if entered_now else GO_BACK_TARGETS[step]
        system_prompt = prompts.build_extraction_prompt(
            business, step, turn.data, products, fields, go_back=targets, services=context.services, now=context.now
        )
        extracted = llm.generate_structured(system_prompt, history, prompts.extraction_schema(step, fields, targets))
        target = extracted.get('go_back_to')
        if isinstance(target, str) and target in targets:
            # Back to an earlier step, keeping everything. It runs on this same message, so "I also
            # want a Kaya Toast" updates the order straight away.
            if target == STEP_PRODUCT_SELECTION:
                turn.data.pop('items_confirmed', None)  # the order must be recapped and confirmed again
            if target == STEP_SLOT_SELECTION and 'slot' in turn.data:
                # A new time must be chosen: the old one is offered again, as number 1 (so a time
                # without a day, "11am instead", keeps its day), then the next free times.
                turn.data['slot_options'] = _reoffer(turn.data.pop('slot'), turn.data, context)
            turn.steps.append(_debug_step(step, system_prompt, extracted, CheckResult(complete=False), turn.data, target))
            turn.went_back_to = target
            step = target
            entered_now = True
            turn.missing, turn.issues = [], []
            continue

        result = CHECKS[step](extracted, turn.data, context)
        turn.missing, turn.issues = result.missing, result.issues
        turn.steps.append(_debug_step(step, system_prompt, extracted, result, turn.data))

        if result.go_back:
            step = FIRST_STEP[step]
        elif result.complete:
            turn.finished.append(STEP_LABELS[step])
            if NEXT_STEP[step] is None:  # a confirmation: commit_turn() places the order / booking
                turn.confirmation = copy.deepcopy(turn.data)
                turn.stop_reason = (
                    'The customer confirmed: placing the booking.' if step == STEP_BOOKING_CONFIRMATION
                    else 'The customer confirmed: placing the order.'
                )
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


# --- Booking checks ------------------------------------------------------------------------

def service_snapshot(service: Service) -> dict:
    """chat_state_data.service: what the customer chose, as they were shown it."""
    return {
        'service_id': service.pk,
        'name': service.name,
        'price': str(service.price),
        'duration_minutes': service.duration_minutes,
        'buffer_minutes': service.buffer_minutes,
    }


def check_service_selection(extracted: dict, data: dict, services: list[Service]) -> CheckResult:
    """Complete once a bookable service is chosen (one of `services`). Choosing another service
    drops the time chosen or offered (the times depend on the service)."""
    by_id = {service.pk: service for service in services}
    issues = []
    chosen_id = _as_int(extracted.get('service_id'))
    if chosen_id is not None:
        service = by_id.get(chosen_id)
        if service is None:
            issues.append('The service the customer asked for cannot be booked.')
        elif data.get('service', {}).get('service_id') != service.pk:
            data['service'] = service_snapshot(service)
            data.pop('slot', None)
            data.pop('slot_options', None)
    current = data.get('service')
    if current and current['service_id'] not in by_id:
        issues.append(f'{current["name"]} cannot be booked any more.')
        for key in ('service', 'slot', 'slot_options'):
            data.pop(key, None)
    if data.get('service') and not issues:
        return CheckResult(complete=True)
    return CheckResult(complete=False, missing=[SERVICE_MISSING], issues=issues)


def _parse_day(value) -> date | None:
    try:
        return date.fromisoformat(value) if isinstance(value, str) else None
    except ValueError:
        return None


def _parse_clock(value) -> time | None:
    """'14:30' (or '9:00', '14:30:00') → a time; anything else → None."""
    match = re.fullmatch(r'(\d{1,2}):(\d{2})(?::00)?', value.strip()) if isinstance(value, str) else None
    if not match or int(match[1]) > 23 or int(match[2]) > 59:
        return None
    return time(int(match[1]), int(match[2]))


def offer_slots(
    sessions: sessionmaker, service: Service, date_from: date, date_to: date, part: str | None, now: datetime
) -> list[datetime]:
    """Free start times to offer for `service` between the days (inclusive), in `part` of the day if
    given: spread out (at least the service's duration, or an hour, apart; at most
    SLOT_OPTIONS_PER_DAY a day), at most SLOT_OPTIONS_OFFERED."""
    with sessions() as db:
        slots = free_slots(db, service, date_from, date_to, now)
    if part in PARTS_OF_DAY:
        low, high = PARTS_OF_DAY[part]
        slots = [slot for slot in slots if low <= local(slot).hour < high]
    gap = timedelta(minutes=max(service.duration_minutes, 60))
    offered, per_day = [], {}
    for slot in slots:
        day = local(slot).date()
        taken = per_day.setdefault(day, [])
        if len(taken) < SLOT_OPTIONS_PER_DAY and (not taken or slot - taken[-1] >= gap):
            taken.append(slot)
            offered.append(slot)
            if len(offered) == SLOT_OPTIONS_OFFERED:
                break
    return offered


def _reoffer(old_slot: str, data: dict, context: StepContext) -> list[str]:
    """Times to offer when going back to Time slot: the old time first, then the next free ones."""
    service = next((s for s in context.services if s.pk == data.get('service', {}).get('service_id')), None)
    today = local(context.now).date()
    others = (
        offer_slots(context.sessions, service, today, today + timedelta(days=DEFAULT_SLOT_DAYS - 1), None, context.now)
        if service else []
    )
    return [old_slot, *[slot.isoformat() for slot in others if slot.isoformat() != old_slot]][:SLOT_OPTIONS_OFFERED]


def _describe_days(date_from: date, date_to: date, part: str | None) -> str:
    when = f'on {date_from:%a} {date_from.day} {date_from:%b}' if date_from == date_to else (
        f'from {date_from:%a} {date_from.day} {date_from:%b} to {date_to:%a} {date_to.day} {date_to:%b}'
    )
    return f'{when} in the {part}' if part else when


def check_slot_selection(
    extracted: dict, data: dict, services: list[Service], now: datetime, sessions: sessionmaker
) -> CheckResult:
    """Complete once a free start time for the chosen service is picked; otherwise offers some.

    The LLM only says what the customer asked for; the times are checked and chosen here
    (checkout_app.schedule.start_problem / free_slots):
    - `choice`: the number of one of the times offered (chat_state_data.slot_options) → that time,
      if it's still free;
    - `time` (HH:MM) on `date` (default: the day of the time chosen before, else of the first time
      offered, else today) → that exact time, if it's free; otherwise other times that day are offered;
    - `date` / `date_to` / `part_of_day` → times offered then (if none, the next free days);
    - nothing new: a time chosen before (e.g. back here after a "change") passes if still free;
      the times already offered stay; otherwise times in the next DEFAULT_SLOT_DAYS days are offered.
    """
    current = data.get('service', {})
    service = next((s for s in services if s.pk == current.get('service_id')), None)
    if service is None:
        for key in ('service', 'slot', 'slot_options'):
            data.pop(key, None)
        problem = f'{current["name"]} cannot be booked any more.' if current else 'No service is chosen yet.'
        return CheckResult(complete=False, missing=[SERVICE_MISSING], issues=[problem], go_back=True)

    def problem_at(start: datetime) -> str | None:
        with sessions() as db:
            return start_problem(db, service, start, now)

    today = local(now).date()
    options = [parse_datetime(option) for option in data.get('slot_options', [])]
    choice = _as_int(extracted.get('choice'))
    day, day_to = _parse_day(extracted.get('date')), _parse_day(extracted.get('date_to'))
    at = _parse_clock(extracted.get('time'))
    part = extracted.get('part_of_day') if extracted.get('part_of_day') in PARTS_OF_DAY else None
    issues: list[str] = []

    def pick(start: datetime) -> CheckResult:
        data['slot'] = start.isoformat()
        data.pop('slot_options', None)
        return CheckResult(complete=True)

    if choice is not None and options:
        if 1 <= choice <= len(options):
            problem = problem_at(options[choice - 1])
            if problem is None:
                return pick(options[choice - 1])
            issues.append(problem)  # e.g. booked by someone else since it was offered
        else:
            issues.append(f'There is no time number {choice}: please pick one of the numbers listed.')

    window = None
    if at is not None:
        if day is None and data.get('slot'):
            day = local(parse_datetime(data['slot'])).date()
        elif day is None and options:
            day = local(options[0]).date()
        on = day or today
        start = datetime.combine(on, at, tzinfo=schedule_tz())
        problem = problem_at(start)
        if problem is None:
            return pick(start)
        issues.append(problem)
        window = (on, on)  # other times that day
    elif day is not None or part is not None:
        start_day = day or today
        window = (start_day, day_to or (day if day else today + timedelta(days=DEFAULT_SLOT_DAYS - 1)))
    elif not issues and data.get('slot'):
        problem = problem_at(parse_datetime(data['slot']))
        if problem is None:
            return CheckResult(complete=True)
        issues.append(problem)
    elif not issues and options:
        return CheckResult(complete=False, missing=[SLOT_MISSING])  # still choosing from the times offered

    data.pop('slot', None)
    default = (today, today + timedelta(days=DEFAULT_SLOT_DAYS - 1))
    if window is None:
        window, part = default, None
    elif window[1] < today:
        issues.append('That day has already passed.')
        window, part = default, None
    start_day, end_day = max(window[0], today), max(window[1], window[0])
    offered = offer_slots(sessions, service, start_day, end_day, part, now)
    if not offered and window != default:
        issues.append(f'There are no free times for {service.name} {_describe_days(start_day, end_day, part)}.')
        after = max(end_day + timedelta(days=1), today)
        offered = offer_slots(sessions, service, after, after + timedelta(days=DEFAULT_SLOT_DAYS - 1), None, now)
    if offered:
        data['slot_options'] = [slot.isoformat() for slot in offered]
    else:
        data.pop('slot_options', None)
    return CheckResult(complete=False, missing=[SLOT_MISSING], issues=issues)


# Every check, by step: (extraction, chat_state_data (updated in place), StepContext) → CheckResult.
CHECKS = {
    STEP_PRODUCT_SELECTION: lambda extracted, data, ctx: check_product_selection(extracted, data, ctx.products, ctx.fields),
    STEP_DETAILS_COLLECTION: lambda extracted, data, ctx: check_details_collection(extracted, data, ctx.products, ctx.fields),
    STEP_CONFIRMATION: lambda extracted, data, ctx: check_confirmation(extracted, data, ctx.products, ctx.fields),
    STEP_SERVICE_SELECTION: lambda extracted, data, ctx: check_service_selection(extracted, data, ctx.services),
    STEP_SLOT_SELECTION: lambda extracted, data, ctx: check_slot_selection(extracted, data, ctx.services, ctx.now, ctx.sessions),
    STEP_BOOKING_DETAILS: lambda extracted, data, ctx: check_details_collection(extracted, data, ctx.products, ctx.fields),
    STEP_BOOKING_CONFIRMATION: lambda extracted, data, ctx: check_confirmation(extracted, data, ctx.products, ctx.fields),
}


def _as_int(value) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None



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
            validate_email(value)  # Django's EmailValidator
        except ValidationError:
            return None, f'"{value}" is not a valid email address.'
        if len(value) > EMAIL_MAX_LENGTH:
            return None, f'{label} is too long.'
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

def _after_placed(data: dict, key: str, pk: int) -> dict:
    """chat_state_data once an order / booking is placed: back to the start, keeping only the last
    order and booking placed (`key`: `last_order_id` or `last_booking_id`)."""
    kept = {k: data[k] for k in ('last_order_id', 'last_booking_id') if k in data}
    return {**kept, key: pk}


def commit_turn(sessions: sessionmaker, session_id: int, turn: Turn, now: datetime | None = None) -> None:
    """Saves where the chat is and what it has collected, placing the order or booking if the
    customer confirmed.

    One transaction, with the session row locked: the order (checkout_app.services.place_order,
    which locks the products and reserves their stock) or booking (place_booking, which locks the
    service's calendars) and the saved state can't disagree. Once it's saved, the chat goes back to
    `start` with only `last_order_id` / `last_booking_id` (and `turn.placed_order_id` /
    `placed_booking_id` is set, for the confirmation message). If it can't be placed, the chat goes
    back, keeping everything: an order to Product selection (e.g. sold out since it was chosen), a
    booking to Time slot with fresh times offered (e.g. someone else booked that time); the problems
    go into the reply. A collected name also fills in an empty display_name.
    """
    with sessions.begin() as db:
        session = db.scalars(select(ChatSession).where(ChatSession.id == session_id).with_for_update()).one()
        business = db.get(BusinessConfiguration, session.business_id)
        details = turn.data.get('details', {})
        booking = turn.step == STEP_BOOKING_CONFIRMATION
        if turn.confirmation is not None and not (
            turn.confirmation.get('service') and turn.confirmation.get('slot') if booking else turn.confirmation.get('items')
        ):
            # Can't happen (the earlier steps need them), but never place an empty order / booking.
            turn.confirmation, turn.step = None, FIRST_STEP[turn.step]
            turn.missing = [SERVICE_MISSING if booking else PRODUCTS_MISSING]
            turn.stop_reason += ' Nothing was chosen, so nothing was placed.'
        if turn.confirmation is not None and booking:
            _place_booking(db, session, business, turn, now)
        elif turn.confirmation is not None:
            data = turn.confirmation
            try:
                # A savepoint: if the order can't be placed, only its rows are undone (Django's atomic()).
                with db.begin_nested():
                    order = place_order(
                        db,
                        business,
                        data.get('items', []),
                        data.get('details', {}),
                        chat_session=session,
                        is_sandbox=session.is_sandbox,
                    )
            except OrderError as exc:
                label = STEP_LABELS[STEP_CONFIRMATION]
                turn.step = STEP_PRODUCT_SELECTION
                turn.data = {key: value for key, value in data.items() if key != 'items_confirmed'}
                turn.finished = [f for f in turn.finished if f != label]
                turn.missing = []
                turn.issues = [*exc.problems, 'The order was not placed: ask the customer what to change.']
                turn.stop_reason = f'The order could not be placed: {exc} Back to Product selection.'
            else:
                turn.placed_order_id = order.pk
                turn.step = STEP_START
                turn.data = _after_placed(data, 'last_order_id', order.pk)
                turn.stop_reason = f'Order #{order.pk} placed: back to the start.'
        if turn.confirmation is not None:
            details = turn.confirmation.get('details', {})
        validate_chat_state_data(turn.data)
        session.chat_state_id = turn.step
        session.chat_state_data = copy.deepcopy(turn.data)
        name = details.get('name')  # a field with the key `name`, if any
        if isinstance(name, str) and not session.display_name:
            session.display_name = name[:DISPLAY_NAME_MAX_LENGTH]


def _place_booking(db, session: ChatSession, business, turn: Turn, now: datetime | None) -> None:
    """commit_turn() for Booking confirmation: place_booking(), or back to Time slot if it can't."""
    data = turn.confirmation
    now = now or timezone.now()
    try:
        # A savepoint: if the booking can't be made, only its rows are undone (Django's atomic()).
        with db.begin_nested():
            booked = place_booking(
                db,
                business,
                data['service']['service_id'],
                parse_datetime(data['slot']),
                data.get('details', {}),
                price=data['service']['price'],
                chat_session=session,
                is_sandbox=session.is_sandbox,
                now=now,
            )
    except BookingError as exc:
        label = STEP_LABELS[STEP_BOOKING_CONFIRMATION]
        turn.step = STEP_SLOT_SELECTION
        turn.data = {key: value for key, value in data.items() if key not in ('slot', 'slot_options')}
        service = db.scalars(
            select(Service).where(
                Service.business_id == business.id, Service.id == data['service']['service_id'], Service.is_active.is_(True)
            )
        ).first()
        today = local(now).date()
        # In this transaction, like Django (the same session, not a new one).
        same_session = lambda: nullcontext(db)  # noqa: E731
        offered = (
            offer_slots(same_session, service, today, today + timedelta(days=DEFAULT_SLOT_DAYS - 1), None, now)
            if service else []
        )
        if offered:
            turn.data['slot_options'] = [slot.isoformat() for slot in offered]
        turn.finished = [f for f in turn.finished if f != label]
        turn.missing = [SLOT_MISSING]
        turn.issues = [*exc.problems, 'The booking was not made: please choose another time.']
        turn.stop_reason = f'The booking could not be made: {exc} Back to Time slot.'
    else:
        turn.placed_booking_id = booked.pk
        turn.step = STEP_START
        turn.data = _after_placed(data, 'last_booking_id', booked.pk)
        turn.stop_reason = f'Booking #{booked.pk} placed: back to the start.'

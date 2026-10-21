"""The chat flow: replies to a customer message. The flow is fixed; each business only configures
its steps' settings (ChatConfiguration).

handle_customer_message() runs one turn:
1. Save the customer message.
2. Route (router.route_message): one structured LLM call labels what the message is about (its
   intents: order, booking, question, order status, off topic). Code decides which handlers run.
3. Order / book (order_flow.advance): the order steps (Product selection → Details collection →
   Confirmation) or the booking steps (Service selection → Time slot → Booking details → Booking
   confirmation), small deterministic state machines. They run when the router finds the customer
   wants to order (or book), and on every message while one is in progress.
4. Save chat_state_id / chat_state_data (order_flow.commit_turn). If the customer confirmed, this
   also places the order (checkout_app: an OrderItem, with its stock reserved) in the same
   transaction, and the chat goes back to the start.
5. Answer questions (check_customer_question, the FAQ handler), if the router found one: one
   structured LLM call with the business's information decides whether it answers the question.
   An unanswered (real) question is saved for the business (questions.ask_business), and the
   reply prompt is told what to do about it.
6. Reply: ask the LLM for the reply, with a prompt putting together what the handlers found (the
   order step, what's known, what's still missing, what went wrong, the question, an order status
   request, an off-topic message), and save it. Except:
   - At Confirmation (and Booking confirmation), the reply is a fixed template: the summary and
     "reply CONFIRM" while it's not confirmed, or "order / booking #N is confirmed" once it is
     saved (never before). At Time slot, it's the free times offered, numbered (worked out in
     code, never by the LLM). The LLM only adds a short aside for anything else in the message
     (e.g. a question).
   - A message only about past orders or bookings (no order or booking step ran) gets the order
     status reply (below).
5b. Order status (check_order_status), if the router found it: no tools and no states. One
   structured LLM call extracts what the customer asks about (order / booking, any numbers), then
   code looks it up among the customer's own orders and bookings only (past_orders.lookup). The
   reply model gets only those records (prompts.build_order_status_prompt, or a section of the
   reply / aside prompt); a reply naming any order or booking number the records don't have is
   replaced by a message written by code (past_orders.reply_is_grounded).

A port of configuration-service's chat_app/flow.py to SQLAlchemy: every database read is a short
session (none is left open while the LLM answers), every write its own transaction.
"""

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from .. import llm
from ..models import BusinessConfiguration, ChatSession
from . import dates as timezone  # timezone.now(), like django.utils.timezone
from . import order_flow, past_orders, payments, prompts, router
from .constants import (
    SENT_BY_BUSINESS_AUTOMATED,
    SENT_BY_CUSTOMER,
    STEP_BOOKING_CONFIRMATION,
    STEP_CONFIRMATION,
    STEP_SLOT_SELECTION,
)
from .settings import ChatSettings
from .tools import (
    Toolbox,
    active_products,
    active_services,
    business_faqs,
    mentioned_products,
    mentioned_services,
    service_dict,
)

# How many of the latest messages the LLM sees (keeps the prompt within the context window).
HISTORY_MAX_MESSAGES = 20

# How the reply was made (debug.reply_kind).
REPLY_LLM = 'llm'
REPLY_CONFIRMATION_REQUEST = 'confirmation_request'  # the order summary + "reply CONFIRM" (template)
REPLY_ORDER_CONFIRMED = 'order_confirmed'  # sent only once the order is saved (template)
REPLY_SLOT_OPTIONS = 'slot_options'  # the free times offered, numbered (template)
REPLY_BOOKING_REQUEST = 'booking_confirmation_request'  # the booking summary + "reply CONFIRM" (template)
REPLY_BOOKING_CONFIRMED = 'booking_confirmed'  # sent only once the booking is saved (template)
REPLY_ORDER_STATUS = 'order_status'  # the order status prompt (only the records looked up)
REPLY_ORDER_STATUS_FALLBACK = 'order_status_fallback'  # its reply named something not in the records
REPLY_ORDER_STATUS_NOT_FOUND = 'order_status_not_found'  # nothing of theirs found: written by code, no LLM call
REPLY_WELCOME = 'welcome'  # a first message with nothing to do (e.g. "hi"): only the welcome message


@dataclass
class TurnResult:
    reply: dict  # the chat message saved as the reply (the last one sent)
    debug: dict  # what happened inside the turn, for the Chat Sandbox's debug panel
    # Every message the assistant sent this turn, oldest first: the welcome message (on a chat's
    # first message, if the business has one), then the reply (unless the welcome was all of it).
    messages: list[dict] = field(default_factory=list)


def handle_customer_message(sessions: sessionmaker, session_id: int, message: str, save_message: bool = True) -> TurnResult:
    """Saves the customer message, runs the flow, then saves and returns the assistant's reply.

    The customer message is saved first, so it's kept if an LLM call fails (llm.LLMError). The
    order state is saved before the reply is generated, so it's kept if only the reply fails.

    On a chat's first message, the business's welcome message (ChatConfiguration.welcome_message,
    if any) is sent first, word for word. If the router finds nothing to do (e.g. "hi"), it's the
    whole reply; otherwise the reply follows it, told not to greet again. Every reply prompt gets
    the business's reply style (prompts.reply_style_section).

    `save_message=False` (messaging-service only: the WhatsApp consumer, app/inbound.py): the
    customer message is already the chat's last one (saved with its InboundMessage record, so a
    redelivered message is never saved twice).
    """
    if save_message:
        append_chat_message(sessions, session_id, message, SENT_BY_CUSTOMER)
    with sessions() as db:
        session = db.get(ChatSession, session_id)
        business = db.get(BusinessConfiguration, session.business_id)
        products = active_products(db, business)
        services = active_services(db, business)
        chat_config = ChatSettings.for_business(db, business)
    history = to_llm_history(session.chat_message_json)
    style = prompts.reply_style_section(chat_config.reply_style, chat_config.custom_style)
    first_message = len(session.chat_message_json) == 1  # nothing before the message just saved
    welcome = prompts.welcome_message_text(business, chat_config.welcome_message) if first_message else ''
    before = {'chat_state_id': session.chat_state_id, 'chat_state_data': session.chat_state_data}
    now = timezone.now()

    route = router.route_message(
        business, session.chat_state_id, session.chat_state_data, history, products, services
    )
    turn = order_flow.advance(
        chat_config, session.chat_state_id, session.chat_state_data, history, products,
        start_order=route.start_order, start_booking=route.start_booking, services=services, now=now,
        sessions=sessions,
    )
    order_flow.commit_turn(sessions, session_id, turn, now)
    if turn.placed_order_id is not None or turn.placed_booking_id is not None:
        # The customer confirmed: the confirmation message ends with the Xendit payment link
        # (or a note if it could not be created).
        payments.store_payment_for_placed(sessions, turn, business)
    chosen_service = turn.data.get('service', {}).get('service_id')
    check = (
        check_customer_question(sessions, session, business, message, history, products, services, chosen_service)
        if route.question else None
    )

    status = check_order_status(sessions, session, business, history, now) if route.order_status else None
    records = status['records'] if status else None

    # The welcome message goes first (the reply model then sees it in the conversation). A first
    # message the router found nothing to do with gets only the welcome: no reply LLM call.
    welcome_only = bool(welcome) and not route.intents and not turn.steps
    sent = []
    if welcome:
        sent.append(append_chat_message(sessions, session_id, welcome, SENT_BY_BUSINESS_AUTOMATED))
        history = [*history, {'role': 'assistant', 'content': welcome}]

    toolbox = Toolbox(business, sessions)
    labels = {
        'order': prompts.detail_labels(chat_config.product_detail_fields),
        'booking': prompts.detail_labels(chat_config.schedule_detail_fields),
    }
    template = None if welcome_only else template_reply(business, turn, labels)
    if welcome_only:
        reply_kind, system_prompt, reply = REPLY_WELCOME, '', None
    elif template is not None:
        # Fixed templates: only the database decides what the customer is told is confirmed, and
        # only code which times are free. Anything else in the message gets a short LLM aside.
        reply_kind, text, context, aside_first = template
        system_prompt, parts = '', [text]
        answered = check is not None and check['kind'] != prompts.QUESTION_NONE
        if answered or route.order_status or route.off_topic:
            system_prompt = prompts.build_aside_prompt(
                business, context=context, intents=route.intents, question_check=check, order_records=records, style=style
            )
            aside = llm.generate_chat_reply(system_prompt, history, toolbox).strip()
            if aside:  # before the summary / times, or after the confirmation
                parts = [aside, text] if aside_first else [text, aside]
        reply = '\n\n'.join(parts)
    elif route.only_order_status and not turn.steps:
        # Only about past orders or bookings, and no order step ran: the order status branch. The
        # model gets the records looked up and no tools; a reply naming any other order or booking
        # number made it up, so code writes the reply instead.
        found = status['found']
        if not found.orders and not found.bookings:
            # Nothing of theirs to tell (none, or only numbers that aren't theirs): nothing for an
            # LLM to rephrase, and nothing it could get wrong.
            reply_kind, system_prompt = REPLY_ORDER_STATUS_NOT_FOUND, ''
            reply = prompts.order_status_fallback_message(found)
        else:
            reply_kind = REPLY_ORDER_STATUS
            system_prompt = prompts.build_order_status_prompt(business, records, style=style, welcomed=bool(welcome))
            reply = llm.generate_chat_reply(system_prompt, history)
            if not past_orders.reply_is_grounded(reply, found):
                reply_kind = REPLY_ORDER_STATUS_FALLBACK
                reply = prompts.order_status_fallback_message(found)
    else:
        reply_kind = REPLY_LLM
        system_prompt = prompts.build_reply_prompt(
            business,
            turn.step,
            turn.data,
            products=products,
            fields=chat_config.detail_fields_for(turn.step),
            services=services,
            missing=turn.missing,
            issues=turn.issues,
            finished=turn.finished,
            went_back=turn.went_back_to is not None and turn.went_back_to == turn.step,
            intents=route.intents,
            question_check=check,
            order_records=records,
            style=style,
            welcomed=bool(welcome),
        )
        reply = llm.generate_chat_reply(system_prompt, history, toolbox)
    if reply is not None:
        sent.append(append_chat_message(sessions, session_id, reply.strip() or '…', SENT_BY_BUSINESS_AUTOMATED))
    debug = {
        'before': before,
        'after': {'chat_state_id': turn.step, 'chat_state_data': turn.data},
        'route': {'intents': route.intents, 'extracted': route.extracted, 'system_prompt': route.system_prompt},
        'steps': turn.steps,
        'stop_reason': turn.stop_reason,
        'finished': turn.finished,
        'confirmation': turn.confirmation_status,
        'order_id': turn.placed_order_id,
        'booking_id': turn.placed_booking_id,
        'payment_link': turn.payment_link,
        'payment_error': turn.payment_error,
        'missing': turn.missing,
        'issues': turn.issues,
        'question_check': (
            {key: check[key] for key in ('kind', 'question', 'saved', 'system_prompt')} if check else None
        ),
        'order_status': (
            {key: status[key] for key in ('extracted', 'system_prompt', 'records')} | {'found': status['found'].as_dict()}
            if status else None
        ),
        'welcome_message': welcome or None,
        'reply_kind': reply_kind,
        'reply_system_prompt': system_prompt,
        'tool_calls': toolbox.calls,
    }
    return TurnResult(reply=sent[-1], debug=debug, messages=sent)


def template_reply(business, turn: order_flow.Turn, labels: dict[str, dict]) -> tuple[str, str, str, bool] | None:
    """The fixed reply for where the turn ended, if it has one: (reply_kind, the message, the aside
    prompt's context, whether an aside goes before it). None: the LLM writes the reply."""
    if turn.placed_order_id is not None:
        text = prompts.order_confirmed_message(
            business,
            turn.placed_order_id,
            turn.confirmation,
            labels['order'],
            payment_link=turn.payment_link,
            payment_note=prompts.PAYMENT_LINK_UNAVAILABLE_NOTE if turn.payment_error else None,
        )
        return REPLY_ORDER_CONFIRMED, text, prompts.aside_after_order(turn.placed_order_id), False
    if turn.placed_booking_id is not None:
        text = prompts.booking_confirmed_message(
            business,
            turn.placed_booking_id,
            turn.confirmation,
            labels['booking'],
            payment_link=turn.payment_link,
            payment_note=prompts.PAYMENT_LINK_UNAVAILABLE_NOTE if turn.payment_error else None,
        )
        return REPLY_BOOKING_CONFIRMED, text, prompts.aside_after_booking(turn.placed_booking_id), False
    if turn.step == STEP_CONFIRMATION:
        text = prompts.confirmation_request_message(turn.data, labels['order'])
        return REPLY_CONFIRMATION_REQUEST, text, prompts.ASIDE_BEFORE_ORDER_SUMMARY, True
    if turn.step == STEP_BOOKING_CONFIRMATION:
        text = prompts.booking_request_message(turn.data, labels['booking'])
        return REPLY_BOOKING_REQUEST, text, prompts.ASIDE_BEFORE_BOOKING_SUMMARY, True
    if turn.step == STEP_SLOT_SELECTION and turn.data.get('service'):
        text = prompts.slot_options_message(turn.data, turn.issues)
        return REPLY_SLOT_OPTIONS, text, prompts.ASIDE_BEFORE_SLOT_OPTIONS, True
    return None


def check_customer_question(
    sessions: sessionmaker, session: ChatSession, business: BusinessConfiguration, message: str, history: list[dict],
    products: list[dict], services: list = (), chosen_service_id: int | None = None,
) -> dict:
    """The FAQ handler: does the customer's question get answered by the business's information?

    Runs when the router finds a question. One structured LLM call (prompts.QUESTION_CHECK_SCHEMA,
    temperature 0) sees the business's description, FAQs, products on sale, bookable services and
    the full information of the products and services the message mentions (and of the service
    being booked, `chosen_service_id`), and returns a `kind`: none / answered /
    unanswered, plus the question. An unanswered question is saved for the business
    (questions.ask_business: not twice while open, at most a few per chat): this is decided here,
    not left to the reply model, which tends to answer from imagination instead of calling a tool.

    Returns `kind`, `question`, `saved` (ask_business's status, or None), `system_prompt`, and
    the information given (`faqs`, `products`, `mentioned`) for the reply prompt.
    """
    from .questions import ask_business

    with sessions() as db:
        faqs = business_faqs(db, business)
        mentioned = mentioned_products(db, business, message) + mentioned_services(db, business, message)
    # The service being booked: the question is likely about it, even if it isn't named.
    chosen = next((s for s in services if s.pk == chosen_service_id), None)
    if chosen is not None and all(item['name'] != chosen.name for item in mentioned):
        mentioned.append(service_dict(chosen, with_information=True))
    system_prompt = prompts.build_question_check_prompt(business, faqs, products, mentioned, services)
    extracted = llm.generate_structured(system_prompt, history, prompts.QUESTION_CHECK_SCHEMA)
    kind = extracted.get('kind') if extracted.get('kind') in prompts.QUESTION_KINDS else prompts.QUESTION_NONE
    question = extracted.get('question')
    question = ' '.join(question.split()) if isinstance(question, str) else ''
    if kind in (prompts.QUESTION_ANSWERED, prompts.QUESTION_UNANSWERED) and not question:
        question = ' '.join(message.split())  # the model didn't rephrase it: use the message itself
    saved = None
    if kind == prompts.QUESTION_UNANSWERED:
        with sessions.begin() as db:
            result = ask_business(db, session, question)
        saved = result.get('status') or result.get('error')
    return {
        'kind': kind,
        'question': question or None,
        'saved': saved,
        'system_prompt': system_prompt,
        'faqs': faqs,
        'products': products,
        'services': services,
        'mentioned': mentioned,
    }


def check_order_status(
    sessions: sessionmaker, session: ChatSession, business: BusinessConfiguration, history: list[dict], now
) -> dict:
    """The order status branch's first two steps: what the customer asks about, then what the
    records say. One structured LLM call (prompts.ORDER_STATUS_SCHEMA, temperature 0) only extracts
    the kind (order / booking / any) and the numbers asked about; past_orders.lookup() then finds
    them among the customer's own orders and bookings (a number that isn't theirs is "not found").

    Returns `extracted` (the LLM's JSON), `system_prompt`, `found` (past_orders.Lookup) and
    `records` (prompts.format_order_records: the only facts the reply may use).
    """
    system_prompt = prompts.build_order_status_extraction_prompt(business)
    extracted = llm.generate_structured(system_prompt, history, prompts.ORDER_STATUS_SCHEMA)
    kind, numbers = past_orders.clean_request(extracted)
    with sessions() as db:
        found = past_orders.lookup(db, session, kind, numbers, now)
    return {
        'extracted': extracted,
        'system_prompt': system_prompt,
        'found': found,
        'records': prompts.format_order_records(found),
    }


# --- Persistence --------------------------------------------------------------------------

def to_llm_history(chat_messages: list[dict]) -> list[dict]:
    """The latest messages as LLM chat messages: the customer is `user`, the business `assistant`."""
    return [
        {'role': 'user' if item['sent_by'] == SENT_BY_CUSTOMER else 'assistant', 'content': item['message']}
        for item in chat_messages[-HISTORY_MAX_MESSAGES:]
    ]


def append_chat_message(sessions: sessionmaker, session_id: int, message: str, sent_by: str) -> dict:
    """Appends a message (timestamped now) to a session and updates its last_chat_time.

    Row-locked in its own short transaction, so concurrent messages aren't lost. (The lock
    isn't held during the LLM call, which can take a while.)
    """
    with sessions.begin() as db:
        return append_in_transaction(db, session_id, message, sent_by)


def append_in_transaction(db, session_id: int, message: str, sent_by: str) -> dict:
    """append_chat_message() inside the caller's transaction (`db`), with the row locked."""
    session = db.scalars(select(ChatSession).where(ChatSession.id == session_id).with_for_update()).one()
    now = timezone.now()
    chat_message = {'message': message, 'sent_by': sent_by, 'message_time': now.isoformat()}
    # A new list (not append): SQLAlchemy only saves a JSON column that's assigned.
    session.chat_message_json = [*session.chat_message_json, chat_message]
    session.last_chat_time = now
    return chat_message

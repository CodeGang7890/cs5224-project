"""The chat flow: replies to a customer message. The flow is fixed; each business only configures
its steps' settings (ChatConfiguration).

handle_customer_message() runs one turn:
1. Save the customer message.
2. Route (router.route_message): one structured LLM call labels what the message is about (its
   intents: order, question, order status, off topic). Code decides which handlers run.
3. Order (order_flow.advance): the order steps, Product selection → Details collection →
   Confirmation, a small deterministic state machine. They run when the router finds the
   customer wants to order, and on every message while an order is in progress.
4. Save chat_state_id / chat_state_data (order_flow.commit_turn). If the customer confirmed, this
   also places the order (checkout_app: an OrderItem, with its stock reserved) in the same transaction.
5. Answer questions (check_customer_question, the FAQ handler), if the router found one: one
   structured LLM call with the business's information decides whether it answers the question.
   An unanswered (real) question is saved for the business (questions.ask_business), and the
   reply prompt is told what to do about it.
6. Reply: ask the LLM for the reply, with a prompt putting together what the handlers found (the
   order step, what's known, what's still missing, what went wrong, the question, an order status
   request, an off-topic message), and save it. A message only about a past order gets a fixed
   reply instead: checking order status isn't available yet.
"""

from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone

from . import llm, order_flow, prompts, router
from .constants import SENT_BY_BUSINESS_AUTOMATED, SENT_BY_CUSTOMER
from .models import ChatConfiguration, ChatSession
from .tools import Toolbox, active_products, business_faqs, mentioned_products

# How many of the latest messages the LLM sees (keeps the prompt within the context window).
HISTORY_MAX_MESSAGES = 20


@dataclass
class TurnResult:
    reply: dict  # the chat message saved as the reply
    debug: dict  # what happened inside the turn, for the Chat Sandbox's debug panel


def handle_customer_message(session_id: int, message: str) -> TurnResult:
    """Saves the customer message, runs the flow, then saves and returns the assistant's reply.

    The customer message is saved first, so it's kept if an LLM call fails (llm.LLMError). The
    order state is saved before the reply is generated, so it's kept if only the reply fails.
    """
    append_chat_message(session_id, message, SENT_BY_CUSTOMER)
    session = ChatSession.objects.select_related('business').get(pk=session_id)
    business = session.business
    history = to_llm_history(session.chat_message_json)
    products = active_products(business)
    chat_config = ChatConfiguration.for_business(business)
    before = {'chat_state_id': session.chat_state_id, 'chat_state_data': session.chat_state_data}

    route = router.route_message(business, session.chat_state_id, session.chat_state_data, history, products)
    turn = order_flow.advance(
        chat_config, session.chat_state_id, session.chat_state_data, history, products, start_order=route.start_order
    )
    order_flow.commit_turn(session_id, turn)
    check = check_customer_question(session, message, history, products) if route.question else None

    toolbox = Toolbox(business)
    if route.only_order_status and not turn.steps:
        # Only about a past order, and no order step ran: checking it isn't available yet.
        system_prompt = ''
        reply = prompts.ORDER_STATUS_COMING_SOON_MESSAGE
    else:
        system_prompt = prompts.build_reply_prompt(
            business,
            turn.step,
            turn.data,
            products=products,
            fields=chat_config.detail_fields,
            missing=turn.missing,
            issues=turn.issues,
            finished=turn.finished,
            went_back=turn.went_back_to is not None and turn.went_back_to == turn.step,
            intents=route.intents,
            question_check=check,
        )
        reply = llm.generate_chat_reply(system_prompt, history, toolbox)
    saved = append_chat_message(session_id, reply.strip() or '…', SENT_BY_BUSINESS_AUTOMATED)
    debug = {
        'before': before,
        'after': {'chat_state_id': turn.step, 'chat_state_data': turn.data},
        'route': {'intents': route.intents, 'extracted': route.extracted, 'system_prompt': route.system_prompt},
        'steps': turn.steps,
        'stop_reason': turn.stop_reason,
        'finished': turn.finished,
        'order_id': turn.data.get('order_id'),
        'missing': turn.missing,
        'issues': turn.issues,
        'question_check': (
            {key: check[key] for key in ('kind', 'question', 'saved', 'system_prompt')} if check else None
        ),
        'reply_system_prompt': system_prompt,
        'tool_calls': toolbox.calls,
    }
    return TurnResult(reply=saved, debug=debug)


def check_customer_question(session: ChatSession, message: str, history: list[dict], products: list[dict]) -> dict:
    """The FAQ handler: does the customer's question get answered by the business's information?

    Runs when the router finds a question. One structured LLM call (prompts.QUESTION_CHECK_SCHEMA,
    temperature 0) sees the business's description, FAQs, products on sale and the full
    information of the products the message mentions, and returns a `kind`: none / answered /
    unanswered, plus the question. An unanswered question is saved for the business
    (questions.ask_business: not twice while open, at most a few per chat): this is decided here,
    not left to the reply model, which tends to answer from imagination instead of calling a tool.

    Returns `kind`, `question`, `saved` (ask_business's status, or None), `system_prompt`, and
    the information given (`faqs`, `products`, `mentioned`) for the reply prompt.
    """
    from .questions import ask_business  # imported here: questions.py imports this module

    business = session.business
    faqs = business_faqs(business)
    mentioned = mentioned_products(business, message)
    system_prompt = prompts.build_question_check_prompt(business, faqs, products, mentioned)
    extracted = llm.generate_structured(system_prompt, history, prompts.QUESTION_CHECK_SCHEMA)
    kind = extracted.get('kind') if extracted.get('kind') in prompts.QUESTION_KINDS else prompts.QUESTION_NONE
    question = extracted.get('question')
    question = ' '.join(question.split()) if isinstance(question, str) else ''
    if kind in (prompts.QUESTION_ANSWERED, prompts.QUESTION_UNANSWERED) and not question:
        question = ' '.join(message.split())  # the model didn't rephrase it: use the message itself
    saved = None
    if kind == prompts.QUESTION_UNANSWERED:
        result = ask_business(session, question)
        saved = result.get('status') or result.get('error')
    return {
        'kind': kind,
        'question': question or None,
        'saved': saved,
        'system_prompt': system_prompt,
        'faqs': faqs,
        'products': products,
        'mentioned': mentioned,
    }


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

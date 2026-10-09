"""Questions the chat assistant couldn't answer, which the business answers or dismisses.

1. When the router finds a question that the business's information doesn't answer, the question
   check (flow.check_customer_question) calls ask_business(): it saves an open
   UnansweredQuestion for the chat, and the assistant tells the customer the team will reply.
2. The business owner sees open questions in the Chats tab (GET /api/chat/questions/).
3. answer_question() saves the Q&A as an FAQ (so the assistant can answer it next time), sends
   the answer in the chat ("Regarding your previous question about …") and marks it answered;
   dismiss_question() closes it without an answer.
"""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from product_app.models import FAQ, FAQ_QUESTION_MAX_LENGTH

from . import flow
from .constants import SENT_BY_BUSINESS_MANUAL
from .models import QuestionStatus, UnansweredQuestion
from .validators import CHAT_MESSAGE_MAX_LENGTH

# A chat can't have more open questions than this (e.g. a customer trying to flood the team).
OPEN_QUESTIONS_PER_CHAT_MAX = 5
ANSWER_MESSAGE_PREFIX = 'Regarding your previous question about "{question}": '
# Short enough that the chat message (prefix + question + answer) always fits in one message.
ANSWER_MAX_LENGTH = CHAT_MESSAGE_MAX_LENGTH - len(ANSWER_MESSAGE_PREFIX.format(question='x' * FAQ_QUESTION_MAX_LENGTH))


class QuestionClosed(Exception):
    """The question was already answered or dismissed."""


def answer_message(question: str, answer: str) -> str:
    """The chat message that sends the business's answer to the customer."""
    return ANSWER_MESSAGE_PREFIX.format(question=question) + answer


def ask_business(chat_session, question) -> dict:
    """Saves the customer's question for the business to answer (called by the question check).

    Returns a `status` (or an `error`) and a `message`. A question already open in this chat isn't saved twice, and
    a chat can have at most OPEN_QUESTIONS_PER_CHAT_MAX open questions.
    """
    text = ' '.join(question.split())[:FAQ_QUESTION_MAX_LENGTH] if isinstance(question, str) else ''
    if not text:
        return {'error': 'Give the question to ask the team.'}
    reply = (
        'The team has been asked. Tell the customer honestly that you do not know yet, that you have '
        'asked the team, and that they will reply in this chat.'
    )
    open_questions = UnansweredQuestion.objects.filter(chat_session=chat_session, status=QuestionStatus.OPEN)
    if open_questions.filter(question__iexact=text).exists():
        return {'status': 'already_asked', 'message': reply}
    if open_questions.count() >= OPEN_QUESTIONS_PER_CHAT_MAX:
        return {
            'status': 'too_many_questions',
            'message': (
                'The team already has several questions from this customer to answer. Tell the customer '
                'the team will reply to their questions in this chat.'
            ),
        }
    item = UnansweredQuestion(business_id=chat_session.business_id, chat_session=chat_session, question=text)
    item.full_clean()
    item.save()
    return {'status': 'asked', 'message': reply}


def answer_question(item: UnansweredQuestion, answer: str, question: str | None = None) -> UnansweredQuestion:
    """Answers an open question, all or nothing: saves the Q&A as an FAQ, marks the question
    answered and sends the answer in its chat (as `business-manual`).

    `question` replaces the customer's wording, e.g. to tidy it up for the FAQ. If the business
    already has an FAQ with that question, its answer is replaced (FAQ questions are unique per
    business). Raises QuestionClosed if the question isn't open, or ValidationError (FAQ rules).
    """
    with transaction.atomic():
        item = UnansweredQuestion.objects.select_for_update().select_related('chat_session').get(pk=item.pk)
        if item.status != QuestionStatus.OPEN:
            raise QuestionClosed()
        question = ' '.join((question or item.question).split())
        faq = FAQ.objects.filter(business_id=item.business_id, question=question).first() or FAQ(
            business_id=item.business_id, question=question
        )
        faq.answer = answer
        faq.full_clean()
        faq.save()

        item.question = question
        item.status = QuestionStatus.ANSWERED
        item.answered_time = timezone.now()
        item.faq = faq
        item.full_clean()
        item.save()
        message = answer_message(question, answer)
        if len(message) > CHAT_MESSAGE_MAX_LENGTH:  # only if the limits change; ANSWER_MAX_LENGTH prevents it
            raise ValidationError({'answer': 'The answer is too long to send in a chat message.'})
        flow.append_chat_message(item.chat_session_id, message, SENT_BY_BUSINESS_MANUAL)
    return item


def dismiss_question(item: UnansweredQuestion) -> UnansweredQuestion:
    """Closes an open question without an answer (nothing is sent). Raises QuestionClosed if it isn't open."""
    with transaction.atomic():
        item = UnansweredQuestion.objects.select_for_update().get(pk=item.pk)
        if item.status != QuestionStatus.OPEN:
            raise QuestionClosed()
        item.status = QuestionStatus.DISMISSED
        item.save(update_fields=['status'])
    return item

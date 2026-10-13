"""Questions the chat assistant couldn't answer, which the business answers or dismisses.

1. messaging-service's chat flow saves them (its question check calls ask_business() there,
   when the business's information doesn't answer a customer's question): an open UnansweredQuestion.
2. The business owner sees open questions in the Chats tab (GET /api/chat/questions/).
3. answer_question() saves the Q&A as an FAQ (so the assistant can answer it next time), sends
   the answer in the chat ("Regarding your previous question about …") and marks it answered;
   dismiss_question() closes it without an answer.
"""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from product_app.models import FAQ, FAQ_QUESTION_MAX_LENGTH

from .constants import SENT_BY_BUSINESS_MANUAL
from .models import ChatSession, QuestionStatus, UnansweredQuestion
from .validators import CHAT_MESSAGE_MAX_LENGTH

ANSWER_MESSAGE_PREFIX = 'Regarding your previous question about "{question}": '
# Short enough that the chat message (prefix + question + answer) always fits in one message.
ANSWER_MAX_LENGTH = CHAT_MESSAGE_MAX_LENGTH - len(ANSWER_MESSAGE_PREFIX.format(question='x' * FAQ_QUESTION_MAX_LENGTH))


class QuestionClosed(Exception):
    """The question was already answered or dismissed."""


def answer_message(question: str, answer: str) -> str:
    """The chat message that sends the business's answer to the customer."""
    return ANSWER_MESSAGE_PREFIX.format(question=question) + answer


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
        append_chat_message(item.chat_session_id, message, SENT_BY_BUSINESS_MANUAL)
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


def append_chat_message(session_id: int, message: str, sent_by: str) -> dict:
    """Appends a message (timestamped now) to a session and updates its last_chat_time, with the
    row locked (messaging-service's chat flow appends messages to the same chats)."""
    with transaction.atomic():
        session = ChatSession.objects.select_for_update().get(pk=session_id)
        now = timezone.now()
        chat_message = {'message': message, 'sent_by': sent_by, 'message_time': now.isoformat()}
        session.chat_message_json.append(chat_message)
        session.last_chat_time = now
        session.save(update_fields=['chat_message_json', 'last_chat_time'])
    return chat_message

"""Questions the chat assistant couldn't answer: ask_business() saves them for the business.

A port of the part of configuration-service's chat_app/questions.py the chat flow uses (the
question check, flow.check_customer_question, calls it). Answering or dismissing a question
(answer_question / dismiss_question) needs no LLM, so it stays in configuration-service only.
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import ChatSession, UnansweredQuestion
from . import dates

# product_app.models.FAQ_QUESTION_MAX_LENGTH: an unanswered question becomes an FAQ once answered.
FAQ_QUESTION_MAX_LENGTH = 300
# chat_app.models.QuestionStatus
QUESTION_OPEN = 'open'
# A chat can't have more open questions than this (e.g. a customer trying to flood the team).
OPEN_QUESTIONS_PER_CHAT_MAX = 5


def ask_business(db: Session, chat_session: ChatSession, question) -> dict:
    """Saves the customer's question for the business to answer (called by the question check).

    Call inside a transaction. Returns a `status` (or an `error`) and a `message`. A question
    already open in this chat isn't saved twice, and a chat can have at most
    OPEN_QUESTIONS_PER_CHAT_MAX open questions.
    """
    text = ' '.join(question.split())[:FAQ_QUESTION_MAX_LENGTH] if isinstance(question, str) else ''
    if not text:
        return {'error': 'Give the question to ask the team.'}
    reply = (
        'The team has been asked. Tell the customer honestly that you do not know yet, that you have '
        'asked the team, and that they will reply in this chat.'
    )
    open_questions = select(UnansweredQuestion).where(
        UnansweredQuestion.chat_session_id == chat_session.id, UnansweredQuestion.status == QUESTION_OPEN
    )
    # Django's question__iexact: UPPER(question) = UPPER(text).
    if db.scalars(open_questions.where(func.upper(UnansweredQuestion.question) == func.upper(text))).first():
        return {'status': 'already_asked', 'message': reply}
    if db.scalar(select(func.count()).select_from(open_questions.subquery())) >= OPEN_QUESTIONS_PER_CHAT_MAX:
        return {
            'status': 'too_many_questions',
            'message': (
                'The team already has several questions from this customer to answer. Tell the customer '
                'the team will reply to their questions in this chat.'
            ),
        }
    db.add(UnansweredQuestion(
        business_id=chat_session.business_id,
        chat_session_id=chat_session.id,
        question=text,
        status=QUESTION_OPEN,
        faq_id=None,
        created_time=dates.now(),
        answered_time=None,
    ))
    db.flush()
    return {'status': 'asked', 'message': reply}

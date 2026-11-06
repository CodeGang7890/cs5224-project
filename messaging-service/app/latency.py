"""Latency logs: how long a customer message takes end to end, and each stage of it.

Every line starts with searchable tags, broad to specific, then the duration and key=value fields:

    [LATENCY][E2E] 7.512s channel=whatsapp chat=21 msg=wamid.X outcome=replied
    [LATENCY][LLM][ROUTER] 0.913s channel=whatsapp chat=21 msg=wamid.X intents=booking
    [LATENCY][LLM][ORDER_STATUS][REPLY] 1.204s channel=sandbox chat=7

so a log search for "[LATENCY][LLM]" finds every LLM call, "[LATENCY][LLM][ORDER_STATUS]" only the
order status route's, and "msg=wamid.X" everything about one message. The tags:

- E2E: one inbound message, from when this service got it until its last reply was sent (WhatsApp),
  or one Chat Sandbox / customer API request. SUMMARY: the same total with every stage, on one line.
- PUBSUB: how long the message waited in Pub/Sub before this service got it.
- TURN: the chat flow for one message (flow.handle_customer_message).
- LLM: ROUTER, EXTRACTION][<STEP>, QUESTION_CHECK, ORDER_STATUS][EXTRACTION / REPLY, REPLY, ASIDE.
- TOOL][<NAME>: a reply tool's database lookup. DB: LOAD, COMMIT_TURN, ORDER_STATUS][LOOKUP.
- PAYMENT: creating the Xendit payment link. SEND: sending one reply on WhatsApp.

The fields bound with `bind()` (channel, chat, msg) are added to every line logged inside it, and
the stages logged inside it are collected for its SUMMARY line.
"""

import contextvars
import logging
import time
from contextlib import contextmanager

logger = logging.getLogger('app.latency')

# The fields every line gets (channel, chat, msg), and the stages logged so far in this message.
_fields: contextvars.ContextVar[dict | None] = contextvars.ContextVar('latency_fields', default=None)
_stages: contextvars.ContextVar[list | None] = contextvars.ContextVar('latency_stages', default=None)

# Stages left out of the SUMMARY line (they contain the others, or are already its total).
_NOT_SUMMED = {'E2E', 'TURN', 'SUMMARY', 'PUBSUB'}


def _format(value) -> str:
    if isinstance(value, (list, tuple, set)):
        value = ','.join(str(item) for item in value) or '-'
    text = str(value)
    return text.replace(' ', '_') if text else '-'


def log(tags: list[str], seconds: float, **fields) -> None:
    """Logs one `[LATENCY][TAG]…` line (INFO), with the bound fields, and adds it to the SUMMARY."""
    tags = [str(tag).upper() for tag in tags]
    all_fields = {**(_fields.get() or {}), **{key: value for key, value in fields.items() if value is not None}}
    logger.info(
        '[LATENCY]%s %.3fs %s',
        ''.join(f'[{tag}]' for tag in tags),
        seconds,
        ' '.join(f'{key}={_format(value)}' for key, value in all_fields.items()),
    )
    stages = _stages.get()
    if stages is not None and tags[0] not in _NOT_SUMMED:
        stages.append(('.'.join(tags[1:] or tags).lower(), seconds))


class Timer:
    """What `timed()` yields: add fields learned during the stage (e.g. `timer.fields['kind'] = …`)."""

    def __init__(self):
        self.fields: dict = {}
        self.started = time.perf_counter()

    @property
    def elapsed(self) -> float:
        return time.perf_counter() - self.started


@contextmanager
def timed(*tags: str, **fields):
    """Times the block and logs it, with `status=error` (and the error type) if it raised."""
    timer = Timer()
    timer.fields.update(fields)
    try:
        yield timer
    except BaseException as exc:
        log(list(tags), timer.elapsed, **timer.fields, status='error', error=type(exc).__name__)
        raise
    log(list(tags), timer.elapsed, **timer.fields)


@contextmanager
def bind(**fields):
    """Adds `fields` to every latency line logged inside the block. The outermost bind() also
    collects the stages for summary()."""
    token = _fields.set({**(_fields.get() or {}), **{key: value for key, value in fields.items() if value is not None}})
    stages_token = _stages.set([]) if _stages.get() is None else None
    try:
        yield
    finally:
        if stages_token is not None:
            _stages.reset(stages_token)
        _fields.reset(token)


def add_fields(**fields) -> None:
    """Adds fields learned later (e.g. the chat, once found) to the lines logged from now on, until
    the enclosing bind() ends. Outside a bind() it does nothing (nothing would remove them)."""
    current = _fields.get()
    if current is not None:
        _fields.set({**current, **{key: value for key, value in fields.items() if value is not None}})


def summary(seconds: float, **fields) -> None:
    """Logs `[LATENCY][SUMMARY]`: the total and every stage logged so far, e.g. `router=0.91`
    (a stage logged more than once, such as two extractions of one step, is added up)."""
    totals: dict[str, float] = {}
    for name, value in _stages.get() or []:
        totals[name] = totals.get(name, 0.0) + value
    log(['SUMMARY'], seconds, **fields, **{name: f'{value:.2f}' for name, value in totals.items()})

"""The router: the first step of every customer message.

One structured LLM call (prompts.ROUTER_SCHEMA, temperature 0) labels what the customer's latest
message is about: its intents (constants.INTENTS, a message can have several). Code, not the
model, then decides which handlers run (flow.handle_customer_message):
- order / booking: the order or booking steps (order_flow.advance). An intent to order (or book a
  service) starts one; once one is in progress, its steps run on every message, whatever the
  router says, because short replies like "Alice", "yes" or "2" carry no intent of their own.
- question: the FAQ handler (flow.check_customer_question): answered from the business's
  information, or sent to the business as an unanswered question.
- order_status: checking past orders isn't available yet: the customer is told it's coming soon.
- off_topic: the reply declines it politely.
"""

from dataclasses import dataclass

from . import llm, prompts
from .constants import INTENT_BOOKING, INTENT_OFF_TOPIC, INTENT_ORDER, INTENT_ORDER_STATUS, INTENT_QUESTION, INTENTS


@dataclass
class Route:
    """What the router found in a customer message."""

    intents: list[str]  # valid, unique, in INTENTS order
    system_prompt: str
    extracted: dict  # the LLM's JSON, for debugging

    @property
    def start_order(self) -> bool:
        """The customer wants to order: starts the order steps, if no order is in progress."""
        return INTENT_ORDER in self.intents

    @property
    def start_booking(self) -> bool:
        """The customer wants to book a service: starts the booking steps, if nothing is in progress."""
        return INTENT_BOOKING in self.intents

    @property
    def question(self) -> bool:
        """Run the FAQ handler (the question check)."""
        return INTENT_QUESTION in self.intents

    @property
    def order_status(self) -> bool:
        return INTENT_ORDER_STATUS in self.intents

    @property
    def off_topic(self) -> bool:
        return INTENT_OFF_TOPIC in self.intents

    @property
    def only_order_status(self) -> bool:
        """The message is only about a past order (gets the fixed "coming soon" reply, if no order
        step ran either)."""
        return self.intents == [INTENT_ORDER_STATUS]


def route_message(
    business, step: str, data: dict, history: list[dict], products: list[dict], services: list = ()
) -> Route:
    """Asks the LLM what the latest message in `history` is about. `step` / `data`: the session's
    chat_state_id / chat_state_data, so the router knows whether an order or booking is in progress.
    `services`: the bookable product_app.Service instances."""
    system_prompt = prompts.build_router_prompt(business, products, step, data, services)
    extracted = llm.generate_structured(system_prompt, history, prompts.ROUTER_SCHEMA)
    return Route(intents=clean_intents(extracted.get('intents')), system_prompt=system_prompt, extracted=extracted)


def clean_intents(raw) -> list[str]:
    """The LLM's intents, keeping only known ones, once each, in INTENTS order (anything else: none)."""
    found = {item for item in raw if isinstance(item, str)} if isinstance(raw, list) else set()
    return [intent for intent in INTENTS if intent in found]

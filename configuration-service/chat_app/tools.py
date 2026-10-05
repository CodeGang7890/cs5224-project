"""Read-only tools the assistant can call while writing a reply (Ollama tool calling).

Every tool only GETs data, and only the chatting business's data: Toolbox(business) binds
them to one business, so the model can't pass in (or guess) another business's ID.
"""

import json
from collections.abc import Callable

from product_app.models import FAQ, Product


def active_products(business) -> list[dict]:
    """The business's orderable products, as plain dicts (also used by the prompts and flow.py)."""
    return [
        {
            'id': product.pk,
            'name': product.name,
            'description': product.description,
            'price': str(product.price),
            'quantity_available': product.quantity_available,
        }
        for product in Product.objects.filter(business=business, is_active=True).order_by('name')
    ]


def _faqs(business) -> list[dict]:
    return [
        {'question': faq.question, 'answer': faq.answer}
        for faq in FAQ.objects.filter(business=business).order_by('question')
    ]


class Toolbox:
    """Tool specs to send to the model, and `run()` to execute the calls it makes."""

    def __init__(self, business):
        self.calls: list[dict] = []  # every call the model made, for debugging
        # name → (description, function). None of these tools take arguments yet.
        self._tools: dict[str, tuple[str, Callable[[], list]]] = {
            'list_products': (
                'List the products the business sells, with id, name, description, price (SGD) '
                'and quantity_available.',
                lambda: active_products(business),
            ),
            'list_faqs': (
                "List the business's frequently asked questions and their answers (opening "
                'hours, policies, etc.).',
                lambda: _faqs(business),
            ),
        }

    @property
    def specs(self) -> list[dict]:
        return [
            {
                'type': 'function',
                'function': {
                    'name': name,
                    'description': description,
                    'parameters': {'type': 'object', 'properties': {}, 'required': []},
                },
            }
            for name, (description, _) in self._tools.items()
        ]

    def run(self, name: str, arguments: dict | None = None) -> str:
        """Runs a tool and returns its result as JSON text (an `error` object for unknown tools)."""
        self.calls.append({'name': name, 'arguments': arguments or {}})
        tool = self._tools.get(name)
        if tool is None:
            return json.dumps({'error': f'Unknown tool {name!r}.'})
        return json.dumps(tool[1](), ensure_ascii=False)

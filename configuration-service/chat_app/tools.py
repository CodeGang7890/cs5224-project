"""Read-only tools the assistant can call while writing a reply (Ollama tool calling), and the
product lookups the flow uses to give the model the right information up front.

Every tool only GETs data, and only the chatting business's data: Toolbox(business) binds
them to one business, so the model can't pass in (or guess) another business's ID.
"""

import json
import re
from collections.abc import Callable

from product_app.models import FAQ, Product

# At most this many product names in a "no such product" answer.
PRODUCT_NAMES_MAX = 50


def active_products(business) -> list[dict]:
    """The business's orderable products, as plain dicts (also used by the prompts and flow.py).

    Without `information` (it can be long): only get_product_details returns it, for one product.
    `quantity_available` is derived from the orders (Product.load_stock, one query for them all).
    """
    products = Product.load_stock(Product.objects.filter(business=business, is_active=True).order_by('name'))
    return [
        {
            'id': product.pk,
            'name': product.name,
            'description': product.description,
            'price': str(product.price),
            'quantity_available': max(product.quantity_available, 0),
        }
        for product in products
    ]


def _faqs(business) -> list[dict]:
    return [
        {'question': faq.question, 'answer': faq.answer}
        for faq in FAQ.objects.filter(business=business).order_by('question')
    ]


# At most this many products' full information goes into a prompt (it can be long).
MENTIONED_PRODUCTS_MAX = 3
# Words too common in product names to tell which product a message is about.
GENERIC_NAME_WORDS = {
    'bouquet', 'flower', 'flowers', 'stem', 'stems', 'with', 'whole', 'single', 'hand', 'tied', 'gift',
    'box', 'set', 'small', 'large', 'mini', 'classic', 'tones', 'tier', 'pack', 'piece', 'pieces',
}


def _name_words(text: str) -> set[str]:
    """Distinctive lowercase words, singular ("roses" → "rose"), for matching product names."""
    words = {word.removesuffix('s') if len(word) > 4 else word for word in re.findall(r'[a-z]+', text.casefold())}
    return {word for word in words if len(word) >= 4 and word not in GENERIC_NAME_WORDS}


def mentioned_products(business, text: str, limit: int = MENTIONED_PRODUCTS_MAX) -> list[dict]:
    """The business's active products that `text` (a customer message) mentions, with their full
    `information`: a product matches if a distinctive word of its name appears in the text."""
    words = _name_words(text)
    found = []
    for product in Product.objects.filter(business=business, is_active=True).order_by('name'):
        if _name_words(product.name) & words:
            found.append({'name': product.name, 'description': product.description, 'information': product.information})
    return found[:limit]


def business_faqs(business) -> list[dict]:
    """The business's FAQs as `{question, answer}` (also what list_faqs returns)."""
    return _faqs(business)


def find_product_details(business, product) -> dict:
    """One active product's description and (long) information, by name (case-insensitive) or id.

    A name matches exactly, or else by containing / being contained in a product name, if that
    matches only one product. Otherwise the result has an `error` (and the candidate names), so the
    model can ask the customer which product they mean, or say it isn't sold.
    """
    is_text = isinstance(product, (str, int)) and not isinstance(product, bool)
    query = str(product).strip() if is_text else ''
    if not query:
        return {'error': 'Give the name of the product.'}
    products = active_products(business)
    lowered = query.casefold()
    matches = [p for p in products if query.isdigit() and p['id'] == int(query)]
    matches = matches or [p for p in products if p['name'].casefold() == lowered]
    matches = matches or [
        p for p in products if lowered in p['name'].casefold() or p['name'].casefold() in lowered
    ]
    if len(matches) == 1:
        found = matches[0]
        information = Product.objects.filter(pk=found['id']).values_list('information', flat=True).first()
        return {
            'id': found['id'],
            'name': found['name'],
            'price': found['price'],
            'quantity_available': found['quantity_available'],
            'description': found['description'] or 'No description has been written for this product.',
            'information': information or 'No further information has been written for this product.',
        }
    if matches:
        return {'error': f'Several products match "{query}".', 'matches': [p['name'] for p in matches]}
    inactive = Product.objects.filter(business=business, is_active=False, name__iexact=query).first()
    if inactive is not None:
        return {'error': f'{inactive.name} is not on sale at the moment.'}
    return {
        'error': f'No product called "{query}" is on sale.',
        'products_on_sale': [p['name'] for p in products[:PRODUCT_NAMES_MAX]],
    }


class Toolbox:
    """Tool specs to send to the model, and `run()` to execute the calls it makes."""

    def __init__(self, business):
        self.calls: list[dict] = []  # every call the model made, for debugging
        # name → (description, JSON schema of the arguments, function(arguments)).
        no_arguments = {'type': 'object', 'properties': {}, 'required': []}
        self._tools: dict[str, tuple[str, dict, Callable[[dict], object]]] = {
            'list_products': (
                'List the products the business sells, with id, name, price (SGD), quantity_available '
                'and a short description of each. For more about one product, use get_product_details.',
                no_arguments,
                lambda arguments: active_products(business),
            ),
            'get_product_details': (
                "Get one product's description and its information: the extra details the business "
                "wrote about it (ingredients, size, options, allergens, how it's made, FAQs about it, "
                'etc.), plus its price and stock. Use it whenever the customer asks a specific question '
                'about a product that its short description does not answer.',
                {
                    'type': 'object',
                    'properties': {
                        'product': {
                            'type': 'string',
                            'description': 'The product name (or its id), e.g. "Kopi C".',
                        },
                    },
                    'required': ['product'],
                },
                lambda arguments: find_product_details(business, arguments.get('product')),
            ),
            'list_faqs': (
                "List the business's frequently asked questions and their answers (opening "
                'hours, policies, etc.).',
                no_arguments,
                lambda arguments: _faqs(business),
            ),
        }

    @property
    def specs(self) -> list[dict]:
        return [
            {
                'type': 'function',
                'function': {'name': name, 'description': description, 'parameters': parameters},
            }
            for name, (description, parameters, _) in self._tools.items()
        ]

    def run(self, name: str, arguments: dict | None = None) -> str:
        """Runs a tool and returns its result as JSON text (an `error` object for unknown tools)."""
        arguments = arguments if isinstance(arguments, dict) else {}
        self.calls.append({'name': name, 'arguments': arguments})
        tool = self._tools.get(name)
        if tool is None:
            return json.dumps({'error': f'Unknown tool {name!r}.'})
        return json.dumps(tool[2](arguments), ensure_ascii=False)

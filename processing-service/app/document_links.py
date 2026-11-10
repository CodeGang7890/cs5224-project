"""Short links to the invoice / receipt PDFs for the customer's messages, instead of long signed URLs.

`<DOCUMENTS_PUBLIC_URL>/d/<token>`: configuration-service checks the token and serves the PDF from the
bucket (checkout_app/documents.py), so the link is short and doesn't expire. The token is the kind
(`i` / `r`), the payment reference and an HMAC-SHA256 of both with INTERNAL_API_KEY (the first 12
bytes, base64url): it can't be guessed or changed. Same format in configuration-service: change both
together.
"""

import base64
import hashlib
import hmac

from . import config
from .documents import INVOICE, RECEIPT

KIND_CODES = {INVOICE: 'i', RECEIPT: 'r'}
SIGNATURE_BYTES = 12


def signature(code: str, payment_reference: str, key: str) -> str:
    digest = hmac.new(key.encode(), f'document-link:{code}{payment_reference}'.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest[:SIGNATURE_BYTES]).decode()


def short_link(kind: str, payment_reference: str) -> str | None:
    """The short link to the order's / booking's invoice or receipt, or None when DOCUMENTS_PUBLIC_URL
    (or INTERNAL_API_KEY) isn't set (then the signed Cloud Storage link is used)."""
    if not config.DOCUMENTS_PUBLIC_URL or not config.INTERNAL_API_KEY:
        return None
    code = KIND_CODES[kind]
    return f'{config.DOCUMENTS_PUBLIC_URL}/d/{code}{payment_reference}{signature(code, payment_reference, config.INTERNAL_API_KEY)}'

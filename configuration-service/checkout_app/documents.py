"""The invoice / receipt PDFs processing-service stores in Cloud Storage, read back for the dashboard.

processing-service renders them and uploads them to the private bucket (`GCS_BUCKET`) as
`invoices/<business id>/<payment reference>.pdf` and `receipts/<business id>/<payment reference>.pdf`
(files made before the business folder was added have no `<business id>/`). This service only reads
them, through Cloud Storage's JSON API with its own service account (roles/storage.objectViewer on the
bucket), so the bucket stays private and nothing extra is installed (google-auth is already here).
"""

import base64
import hashlib
import hmac
import re
from urllib.parse import quote

import google.auth
from django.conf import settings
from google.auth.exceptions import GoogleAuthError
from google.auth.transport.requests import AuthorizedSession

INVOICE, RECEIPT = 'invoice', 'receipt'
KINDS = (INVOICE, RECEIPT)
# The short links processing-service puts in the customer's messages (`/d/<token>`): the kind's code, the
# payment reference and an HMAC-SHA256 of both with INTERNAL_API_KEY (its first 12 bytes, base64url). Same
# format in processing-service (app/document_links.py): change both together.
LINK_KINDS = {'i': INVOICE, 'r': RECEIPT}
LINK_SIGNATURE_BYTES = 12
LINK_TOKEN_PATTERN = re.compile(r'([ir])([0-9a-f]{32})([A-Za-z0-9_-]{16})')
READ_ONLY_SCOPE = 'https://www.googleapis.com/auth/devstorage.read_only'
TIMEOUT_SECONDS = 15

_session = None


class DocumentsUnavailable(Exception):
    """The PDFs can't be read here: no bucket configured, or Cloud Storage refused / didn't answer."""


def link_signature(code: str, payment_reference: str, key: str) -> str:
    digest = hmac.new(key.encode(), f'document-link:{code}{payment_reference}'.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest[:LINK_SIGNATURE_BYTES]).decode()


def read_link_token(token: str) -> tuple[str, str] | None:
    """(kind, payment reference) from a short link's token, or None if it's malformed or not ours."""
    key = settings.INTERNAL_API_KEY
    match = LINK_TOKEN_PATTERN.fullmatch(token)
    if not key or not match:
        return None
    code, payment_reference, signature = match.groups()
    if not hmac.compare_digest(signature, link_signature(code, payment_reference, key)):
        return None
    return LINK_KINDS[code], payment_reference


def _get_session() -> AuthorizedSession:
    global _session
    if _session is None:
        credentials, _ = google.auth.default(scopes=[READ_ONLY_SCOPE])
        _session = AuthorizedSession(credentials)
    return _session


def object_names(kind: str, business_id: int, payment_reference: str) -> list[str]:
    """Where processing-service puts the PDF: in the business's folder, else (older files) without it."""
    return [f'{kind}s/{business_id}/{payment_reference}.pdf', f'{kind}s/{payment_reference}.pdf']


def fetch_pdf(kind: str, business_id: int, payment_reference: str) -> bytes | None:
    """The PDF's bytes, or None if there's no such file (e.g. not paid yet). DocumentsUnavailable if
    there's no bucket or Cloud Storage can't be read."""
    bucket = settings.GCS_BUCKET
    if not bucket:
        raise DocumentsUnavailable('Invoices and receipts are not stored in this environment.')
    try:
        session = _get_session()
        for name in object_names(kind, business_id, payment_reference):
            url = f'https://storage.googleapis.com/storage/v1/b/{bucket}/o/{quote(name, safe="")}?alt=media'
            response = session.get(url, timeout=TIMEOUT_SECONDS)
            if response.status_code == 200:
                return response.content
            if response.status_code != 404:
                raise DocumentsUnavailable(f'Cloud Storage answered {response.status_code}.')
    except (GoogleAuthError, OSError) as exc:  # no credentials, network errors (requests' are OSErrors)
        raise DocumentsUnavailable('Could not reach Cloud Storage.') from exc
    return None

"""The invoice / receipt PDFs processing-service stores in Cloud Storage, read back for the dashboard.

processing-service renders them and uploads them to the private bucket (`GCS_BUCKET`) as
`invoices/<business id>/<payment reference>.pdf` and `receipts/<business id>/<payment reference>.pdf`
(files made before the business folder was added have no `<business id>/`). This service only reads
them, through Cloud Storage's JSON API with its own service account (roles/storage.objectViewer on the
bucket), so the bucket stays private and nothing extra is installed (google-auth is already here).
"""

from urllib.parse import quote

import google.auth
from django.conf import settings
from google.auth.exceptions import GoogleAuthError
from google.auth.transport.requests import AuthorizedSession

INVOICE, RECEIPT = 'invoice', 'receipt'
KINDS = (INVOICE, RECEIPT)
READ_ONLY_SCOPE = 'https://www.googleapis.com/auth/devstorage.read_only'
TIMEOUT_SECONDS = 15

_session = None


class DocumentsUnavailable(Exception):
    """The PDFs can't be read here: no bucket configured, or Cloud Storage refused / didn't answer."""


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

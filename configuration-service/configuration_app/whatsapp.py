"""Checks for Meta's WhatsApp webhook calls, done here so the secrets never leave this service.

messaging-ingester receives the webhooks but holds no secrets: it asks the internal API
(/api/internal/whatsapp/<business_id>/verify-…/) and gets a yes/no answer.
"""

import hashlib
import hmac

SIGNATURE_PREFIX = 'sha256='


def verify_token_matches(expected: str, given: str) -> bool:
    """Meta's subscription handshake: the hub.verify_token it sends must equal ours."""
    return bool(expected) and hmac.compare_digest(given.encode(), expected.encode())


def signature_matches(app_secret: str, payload: bytes, signature_header: str) -> bool:
    """X-Hub-Signature-256 is "sha256=" + the hex HMAC-SHA256 of the raw request body, keyed by the App Secret."""
    if not app_secret or not signature_header.startswith(SIGNATURE_PREFIX):
        return False
    expected = hmac.new(app_secret.encode(), payload, hashlib.sha256).hexdigest()
    given = signature_header.removeprefix(SIGNATURE_PREFIX).lower()
    return hmac.compare_digest(given.encode(), expected.encode())

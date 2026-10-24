"""Client for configuration-service's internal WhatsApp checks.

The ingester never sees a business's secrets. It asks configuration-service:
- verify-token: does the hub.verify_token Meta sent match the business's? (subscription handshake)
- verify-signature: is this webhook really from Meta? The raw body and Meta's X-Hub-Signature-256
  header are forwarded unchanged, because the signature covers the exact bytes.
Both answer `{valid, phone_number_id}`.

Our Meta app's own (default) webhook, /webhook (Embedded Signup), has the same two checks against
the app's verify token and App Secret: verify_app_token / verify_app_signature. Its account_update
events are then handed over with report_account_updates (configuration-service marks the connections
disconnected or banned) → how many connections changed.
"""

from dataclasses import dataclass

import httpx

from . import config
from .parsing import AccountUpdate


class BusinessNotConnectedError(Exception):
    """The business doesn't exist or hasn't connected WhatsApp (configuration-service said 404). For our
    app's own webhook: it isn't configured (no META_APP_SECRET / META_APP_WEBHOOK_VERIFY_TOKEN)."""


class VerificationUnavailableError(Exception):
    """configuration-service couldn't answer (down, timed out, wrong API key, unexpected reply)."""


@dataclass(frozen=True)
class Verification:
    valid: bool
    phone_number_id: str | None  # the business's Phone Number ID, when valid

class ConfigurationServiceClient:
    def __init__(
        self,
        base_url: str = config.CONFIGURATION_SERVICE_URL,
        api_key: str = config.INTERNAL_API_KEY,
        timeout: float = config.CONFIGURATION_SERVICE_TIMEOUT_SECONDS,
        transport: httpx.BaseTransport | None = None,  # tests pass an httpx.MockTransport
    ):
        self._client = httpx.Client(
            base_url=base_url,
            headers={config.INTERNAL_API_KEY_HEADER: api_key},
            timeout=timeout,
            transport=transport,
        )

    def verify_token(self, business_id: int, verify_token: str) -> Verification:
        return self._post(f'/internal/whatsapp/{business_id}/verify-token/', json={'verify_token': verify_token})

    def verify_signature(self, business_id: int, body: bytes, signature: str | None) -> Verification:
        headers = {'Content-Type': 'application/octet-stream'}
        if signature is not None:
            headers[config.SIGNATURE_HEADER] = signature
        return self._post(f'/internal/whatsapp/{business_id}/verify-signature/', content=body, headers=headers)

    def verify_app_token(self, verify_token: str) -> Verification:
        return self._post('/internal/whatsapp/app/verify-token/', json={'verify_token': verify_token})

    def verify_app_signature(self, body: bytes, signature: str | None) -> Verification:
        headers = {'Content-Type': 'application/octet-stream'}
        if signature is not None:
            headers[config.SIGNATURE_HEADER] = signature
        return self._post('/internal/whatsapp/app/verify-signature/', content=body, headers=headers)

    def report_account_updates(self, updates: list[AccountUpdate]) -> int:
        data = self._send('/internal/whatsapp/app/account-updates/', json={'updates': [u.to_dict() for u in updates]})
        changed = data.get('changed')
        if not isinstance(changed, int) or isinstance(changed, bool):
            raise VerificationUnavailableError(f'Unexpected reply from configuration-service: {data!r:.200}')
        return changed

    def _post(self, path: str, **kwargs) -> Verification:
        data = self._send(path, **kwargs)
        try:
            return Verification(valid=data['valid'] is True, phone_number_id=data.get('phone_number_id'))
        except (KeyError, TypeError) as exc:
            raise VerificationUnavailableError(f'Unexpected reply from configuration-service: {data!r:.200}') from exc

    def _send(self, path: str, **kwargs) -> dict:
        """POSTs to configuration-service's internal API → its JSON object."""
        try:
            response = self._client.post(path, **kwargs)
        except httpx.HTTPError as exc:  # connection refused, DNS, timeout...
            raise VerificationUnavailableError(f'Could not reach configuration-service: {exc}') from exc
        if response.status_code == 404:
            raise BusinessNotConnectedError('This business has not connected WhatsApp.')
        if response.status_code != 200:  # 403 (wrong INTERNAL_API_KEY), 400, 5xx...
            raise VerificationUnavailableError(
                f'configuration-service answered {response.status_code} to {path}: {response.text[:200]}'
            )
        try:
            data = response.json()
        except ValueError as exc:
            raise VerificationUnavailableError(f'Unexpected reply from configuration-service: {response.text[:200]}') from exc
        if not isinstance(data, dict):
            raise VerificationUnavailableError(f'Unexpected reply from configuration-service: {response.text[:200]}')
        return data

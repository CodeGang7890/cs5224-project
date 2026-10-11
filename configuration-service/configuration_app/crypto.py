"""Encryption at rest for secrets stored in the database (e.g. WhatsApp access tokens).

Uses Fernet (AES-128-CBC + HMAC-SHA256) from `cryptography`. The key is derived from
settings.CONFIGURATION_ENCRYPTION_KEY, which may be any secret string: it's hashed with SHA-256 into a
Fernet key, so e.g. a random password from a secret manager works as-is. When it's empty, SECRET_KEY
is used instead; set a separate key in deployments so SECRET_KEY can be rotated on its own.

Changing the key makes the existing ciphertexts unreadable: re-enter the secrets afterwards.
"""

import base64
import hashlib
from functools import cache

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import models


@cache
def _fernet(key_material: str) -> Fernet:
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(key_material.encode()).digest()))


def get_fernet() -> Fernet:
    key_material = settings.CONFIGURATION_ENCRYPTION_KEY or settings.SECRET_KEY
    if not key_material:
        raise ImproperlyConfigured('Set CONFIGURATION_ENCRYPTION_KEY (or SECRET_KEY) to store encrypted secrets.')
    return _fernet(key_material)


def encrypt(plaintext: str) -> str:
    return get_fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    try:
        return get_fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:
        raise ImproperlyConfigured(
            'Could not decrypt a stored secret: CONFIGURATION_ENCRYPTION_KEY has changed since it was saved.'
        ) from exc


class EncryptedTextField(models.TextField):
    """A TextField stored encrypted. In Python it's the plaintext, so validators see the real value.

    Empty strings are stored as-is (not encrypted), so "not set" stays visible in the database.
    It can't be filtered or searched on, because every encryption of the same value differs.
    """

    # The two methods below are Django Field hooks: Django calls them by these exact names, so they
    # can't be renamed. They only adapt Django's calls to encrypt() / decrypt() above.

    def from_db_value(self, value, expression, connection):
        """Reading: Django calls this for each value loaded from the database → decrypt it."""
        return decrypt(value) if value else value

    def get_prep_value(self, value):
        """Writing: Django calls this before saving a value (or using it in a query) → encrypt it."""
        value = super().get_prep_value(value)
        return encrypt(value) if value else value

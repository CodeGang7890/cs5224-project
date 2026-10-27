"""Logging in with Google or Facebook, through Google Cloud Identity Platform (Firebase Authentication).

frontend-app runs the provider's popup with the Firebase JS SDK and sends us the Identity Platform ID
token it gets (a JWT signed by Google). verify_id_token() checks it (signature against Google's public
keys, expiry, audience = our project, issuer) and returns who it is; accounts.py then finds or creates
the BusinessUser, and the view returns our usual SimpleJWT pair. So the rest of the system (frontend
tokens, messaging-service) doesn't know or care how someone logged in.

Tests patch verify_id_token (or google.oauth2.id_token.verify_firebase_token): never call Google.
"""

from dataclasses import dataclass

import google.auth.exceptions
import google.auth.transport.requests
from django.conf import settings
from google.oauth2 import id_token

# Sign-in providers we accept (Identity Platform's `firebase.sign_in_provider`).
PROVIDERS = ('google.com', 'facebook.com')


@dataclass(frozen=True)
class FirebaseIdentity:
    uid: str  # Identity Platform's user ID: the same for every login of this person
    email: str  # '' if the provider didn't share one
    name: str  # the display name, '' if none
    provider: str  # 'google.com' or 'facebook.com'


class FirebaseNotConfigured(Exception):
    """FIREBASE_PROJECT_ID isn't set."""


class FirebaseUnavailable(Exception):
    """Google's public keys couldn't be fetched (network)."""


class InvalidFirebaseToken(Exception):
    """Not a valid Identity Platform ID token for our project (or not from Google / Facebook)."""


def verify_id_token(token: str) -> FirebaseIdentity:
    project_id = settings.FIREBASE_PROJECT_ID
    if not project_id:
        raise FirebaseNotConfigured
    try:
        claims = id_token.verify_firebase_token(token, google.auth.transport.requests.Request(), audience=project_id)
    except google.auth.exceptions.TransportError as exc:
        raise FirebaseUnavailable(str(exc)) from exc
    except (ValueError, google.auth.exceptions.GoogleAuthError) as exc:
        raise InvalidFirebaseToken(str(exc)) from exc
    # verify_firebase_token checks the signature, expiry and audience, not the issuer.
    if not isinstance(claims, dict) or claims.get('iss') != f'https://securetoken.google.com/{project_id}':
        raise InvalidFirebaseToken('Wrong issuer.')
    uid = claims.get('sub')
    firebase = claims.get('firebase') if isinstance(claims.get('firebase'), dict) else {}
    provider = firebase.get('sign_in_provider')
    if not isinstance(uid, str) or not uid:
        raise InvalidFirebaseToken('No user ID.')
    if provider not in PROVIDERS:
        raise InvalidFirebaseToken(f'Unsupported sign-in provider: {provider}.')
    email, name = claims.get('email'), claims.get('name')
    return FirebaseIdentity(
        uid=uid,
        email=email if isinstance(email, str) else '',
        name=name if isinstance(name, str) else '',
        provider=provider,
    )

"""Accounts for the sign-up and Google / Facebook login endpoints, and the JWT pair they return.

user_for_identity() maps an Identity Platform identity (firebase.py) to a BusinessUser: the account made
by its first login (`firebase_uid`), else a new one (no password, no business yet: frontend-app asks for
one). It never attaches a Google / Facebook login to an existing account, even with the same email (the
user asked to keep it simple): that would need the owner to prove they own that account first.
"""

import re

from django.contrib.auth import get_user_model
from django.contrib.auth.models import update_last_login
from django.db import IntegrityError, transaction
from rest_framework_simplejwt.tokens import RefreshToken

from .firebase import FirebaseIdentity

USERNAME_MAX_LENGTH = 150  # AbstractUser.username
NAME_MAX_LENGTH = 150  # AbstractUser.first_name / last_name


def tokens_for(user) -> dict:
    """Our usual JWT pair (like POST /api/auth/token/), and the user's last_login updated."""
    refresh = RefreshToken.for_user(user)
    update_last_login(None, user)
    return {'access': str(refresh.access_token), 'refresh': str(refresh)}


def email_taken(email: str) -> bool:
    return get_user_model().objects.filter(email__iexact=email).exists()


def unique_username(seed: str) -> str:
    """A free username from an email or name: e.g. "ada.tan" for ada.tan@example.com, then ada.tan2…"""
    base = re.sub(r'[^\w.@+-]', '', seed.split('@')[0].strip().replace(' ', '.'))[:USERNAME_MAX_LENGTH - 6] or 'user'
    users = get_user_model().objects
    username, n = base, 1
    while users.filter(username__iexact=username).exists():
        n += 1
        username = f'{base}{n}'
    return username


def user_for_identity(identity: FirebaseIdentity) -> tuple[object, bool]:
    """The BusinessUser for this Google / Facebook identity, and whether it was just created."""
    users = get_user_model().objects
    user = users.filter(firebase_uid=identity.uid).first()
    if user is not None:
        return user, False

    first_name, _, last_name = identity.name.strip().partition(' ')
    user = get_user_model()(
        username=unique_username(identity.email or identity.name or 'user'),
        email=identity.email,
        first_name=first_name[:NAME_MAX_LENGTH],
        last_name=last_name.strip()[:NAME_MAX_LENGTH],
        firebase_uid=identity.uid,
    )
    user.set_unusable_password()
    try:
        with transaction.atomic():
            user.save()
    except IntegrityError:  # the same person's first login twice at once: the other one created it
        existing = users.filter(firebase_uid=identity.uid).first()
        if existing is None:
            raise
        return existing, False
    return user, True

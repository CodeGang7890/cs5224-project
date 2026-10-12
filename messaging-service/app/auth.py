"""Logins: configuration-service's SimpleJWT access tokens, checked the way its
rest_framework_simplejwt.authentication.JWTAuthentication does (same 401 bodies), so the frontend
can call this service with the token it already has (and refresh it on a 401).

A token is valid if it's signed with JWT_SIGNING_KEY (HS256, the same key as configuration-service),
not expired, has an id (`jti`), is an `access` token, and names an active user (`user_id`) in auth_app_businessuser.
"""

import jwt
from fastapi import Request
from sqlalchemy.orm import sessionmaker

from . import config
from .drf import DRFError
from .models import BusinessUser

AUTH_HEADER_TYPE = 'Bearer'
WWW_AUTHENTICATE = {'WWW-Authenticate': f'{AUTH_HEADER_TYPE} realm="api"'}


def _unauthorized(detail: str, code: str | None = None, **extra) -> DRFError:
    body = {'detail': detail, **({'code': code} if code else {}), **extra}
    return DRFError(401, body, headers=WWW_AUTHENTICATE)


def _invalid_token(message: str) -> DRFError:
    return _unauthorized(
        'Given token not valid for any token type', 'token_not_valid',
        messages=[{'token_class': 'AccessToken', 'token_type': 'access', 'message': message}],
    )


def raw_token(request: Request) -> str | None:
    """The token from `Authorization: Bearer <token>` (None: no credentials given)."""
    header = request.headers.get('Authorization', '')
    parts = header.split()
    if not parts or parts[0] != AUTH_HEADER_TYPE:
        return None
    if len(parts) != 2:
        raise _unauthorized('Authorization header must contain two space-delimited values', 'bad_authorization_header')
    return parts[1]


def authenticate(request: Request, sessions: sessionmaker) -> BusinessUser:
    """The logged-in user, or a 401 (IsAuthenticated + JWTAuthentication)."""
    token = raw_token(request)
    if token is None:
        raise _unauthorized('Authentication credentials were not provided.')
    if not config.JWT_SIGNING_KEY:
        raise _invalid_token('Token is invalid')  # misconfigured: nothing can be checked
    try:
        payload = jwt.decode(token, config.JWT_SIGNING_KEY, algorithms=[config.JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise _invalid_token('Token is expired') from None
    except jwt.InvalidTokenError:
        raise _invalid_token('Token is invalid') from None
    # SimpleJWT's Token.verify(), in its order: exp, jti, then the token type.
    if 'exp' not in payload:
        raise _invalid_token("Token has no 'exp' claim")
    if 'jti' not in payload:
        raise _invalid_token('Token has no id')
    if 'token_type' not in payload:
        raise _invalid_token('Token has no type')
    if payload['token_type'] != 'access':
        raise _invalid_token('Token has wrong type')
    user_id = payload.get('user_id')
    if user_id is None:
        raise _unauthorized('Token contained no recognizable user identification', 'token_not_valid')
    try:
        user_id = int(user_id)
    except (TypeError, ValueError):
        raise _unauthorized('User not found', 'user_not_found') from None
    with sessions() as db:
        user = db.get(BusinessUser, user_id)
    if user is None:
        raise _unauthorized('User not found', 'user_not_found')
    if not user.is_active:
        raise _unauthorized('User is inactive', 'user_inactive')
    return user

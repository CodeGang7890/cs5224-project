"""Django's EmailValidator (django.core.validators, Django 6.1), copied so the details steps accept
and reject exactly the same addresses as configuration-service."""

import ipaddress
import re

from .errors import ValidationError

_USER_REGEX = re.compile(
    # dot-atom
    r"(^[-!#$%&'*+/=?^_`{}|~0-9A-Z]+(\.[-!#$%&'*+/=?^_`{}|~0-9A-Z]+)*\Z"
    # quoted-string
    r'|^"([\001-\010\013\014\016-\037!#-\[\]-\177]|\\[\001-\011\013\014\016-\177])'
    r'*"\Z)',
    re.IGNORECASE,
)
# DomainNameValidator's hostname_re + domain_re + tld_no_fqdn_re.
_UL = '¡-￿'  # Unicode letters range (must not be a raw string)
_DOMAIN_REGEX = re.compile(
    r'^[a-z' + _UL + r'0-9](?:[a-z' + _UL + r'0-9-]{0,61}[a-z' + _UL + r'0-9])?'
    r'(?:\.(?!-)[a-z' + _UL + r'0-9-]{1,63}(?<!-))*'
    r'\.(?!-)(?:[a-z' + _UL + r'-]{2,63}|xn--[a-z0-9]{1,59})(?<!-)\Z',
    re.IGNORECASE,
)
_LITERAL_REGEX = re.compile(r'\[([A-F0-9:.]+)\]\Z', re.IGNORECASE)  # ipv4 or ipv6 address (SMTP 4.1.3)
_DOMAIN_ALLOWLIST = ['localhost']
_MAX_IPV6_ADDRESS_LENGTH = 39


def _is_ip_address(value: str) -> bool:
    try:
        ipaddress.IPv4Address(value)
        return True
    except ValueError:
        pass
    if len(value) > _MAX_IPV6_ADDRESS_LENGTH:
        return False
    try:
        ipaddress.IPv6Address(value)
    except ValueError:
        return False
    return True


def _validate_domain_part(domain_part: str) -> bool:
    if _DOMAIN_REGEX.match(domain_part):
        return True
    literal_match = _LITERAL_REGEX.match(domain_part)
    return bool(literal_match) and _is_ip_address(literal_match[1])


def validate_email(value: str) -> None:
    """Raises ValidationError unless `value` is a valid email address (Django's rules)."""
    # The maximum length of an email is 320 characters per RFC 3696 section 3.
    if not value or '@' not in value or len(value) > 320:
        raise ValidationError('Enter a valid email address.')
    user_part, domain_part = value.rsplit('@', 1)
    if not _USER_REGEX.match(user_part):
        raise ValidationError('Enter a valid email address.')
    if domain_part not in _DOMAIN_ALLOWLIST and not _validate_domain_part(domain_part):
        raise ValidationError('Enter a valid email address.')

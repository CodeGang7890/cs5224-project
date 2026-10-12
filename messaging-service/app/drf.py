"""Django REST Framework's request checks and error bodies, for the endpoints moved here from
configuration-service (app/chat_api.py), so their callers (the frontend's Chat Sandbox) see exactly
the same responses: `{"detail": "..."}` for errors, and `{"<field>": ["..."]}` for invalid input.
(The rest of this service keeps its own `{code, status, message}` bodies: app/errors.py.)
"""

import json
import re
from collections.abc import Callable

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

NO_BUSINESS_MESSAGE = 'Your account is not linked to a business.'  # auth_app.business_scope
OTHER_BUSINESS_MESSAGE = 'You do not have access to this business.'


class DRFError(Exception):
    """An error response with DRF's body (`{"detail": ...}`, or validation errors by field)."""

    def __init__(self, status_code: int, body: dict, headers: dict | None = None):
        super().__init__(body)
        self.status_code, self.body, self.headers = status_code, body, headers


def error(status_code: int, detail: str, **extra) -> DRFError:
    return DRFError(status_code, {'detail': detail, **extra})


def register_drf_errors(app: FastAPI) -> None:
    async def handler(request: Request, exc: DRFError) -> JSONResponse:
        return JSONResponse(exc.body, status_code=exc.status_code, headers=exc.headers)

    app.add_exception_handler(DRFError, handler)


async def json_object(request: Request) -> dict:
    """The request body as a JSON object (DRF's JSONParser + a Serializer's to_internal_value)."""
    raw = await request.body()
    try:
        data = json.loads(raw) if raw else {}
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise error(400, f'JSON parse error - {exc}') from exc
    if not isinstance(data, dict):
        name = {list: 'list', str: 'str', int: 'int', float: 'float', bool: 'bool', type(None): 'NoneType'}.get(type(data), type(data).__name__)
        raise DRFError(400, {'non_field_errors': [f'Invalid data. Expected a dictionary, but got {name}.']})
    return data


# --- Serializer fields: each returns (value, errors) -------------------------------------------

def char_field(data: dict, name: str, max_length: int, validators: list[Callable[[str], str | None]] = ()):
    """serializers.CharField(max_length=…): required, not null, a string (numbers become strings),
    trimmed, not blank; then the validators and max_length (every error is listed)."""
    if name not in data:
        return None, ['This field is required.']
    value = data[name]
    if value is None:
        return None, ['This field may not be null.']
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return None, ['Not a valid string.']
    value = str(value).strip()
    if not value:
        return None, ['This field may not be blank.']
    errors = [message for validator in validators if (message := validator(value))]
    if len(value) > max_length:
        errors.append(f'Ensure this field has no more than {max_length} characters.')
    return (None, errors) if errors else (value, [])


_INTEGER_DECIMALS = re.compile(r'\.0*\s*$')  # DRF's IntegerField.re_decimal


def integer_field(data: dict, name: str, min_value: int):
    """serializers.IntegerField(min_value=…)."""
    if name not in data:
        return None, ['This field is required.']
    value = data[name]
    if value is None:
        return None, ['This field may not be null.']
    try:
        if isinstance(value, bool):
            raise ValueError
        number = int(_INTEGER_DECIMALS.sub('', str(value)))
    except (TypeError, ValueError):
        return None, ['A valid integer is required.']
    if number < min_value:
        return None, [f'Ensure this value is greater than or equal to {min_value}.']
    return number, []


def regex_validator(pattern: str, message: str) -> Callable[[str], str | None]:
    compiled = re.compile(pattern)
    return lambda value: None if compiled.search(value) else message


def validated(fields: dict[str, tuple]) -> dict:
    """The fields' values, or a 400 with every field's errors (a Serializer's is_valid(raise_exception=True))."""
    values, errors = {}, {}
    for name, (value, problems) in fields.items():
        if problems:
            errors[name] = problems
        else:
            values[name] = value
    if errors:
        raise DRFError(400, errors)
    return values

"""JSON error bodies: `{code, status, message}`, and `{code, status, errors}` for validation (422)."""

from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

# FastAPI's names for where a value came from → the names used in `errors` (e.g. errors.json).
_LOCATIONS = {'body': 'json', 'query': 'query', 'path': 'path', 'header': 'headers', 'cookie': 'cookies'}


def _status_phrase(code: int) -> str:
    try:
        return HTTPStatus(code).phrase
    except ValueError:
        return 'Error'


async def _http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    body = {'code': exc.status_code, 'status': _status_phrase(exc.status_code), 'message': exc.detail}
    return JSONResponse(body, status_code=exc.status_code, headers=exc.headers)


async def _validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Groups errors by location and field, e.g. `{"json": {"prompt": ["Field required"]}}`."""
    errors: dict[str, dict[str, list[str]]] = {}
    for error in exc.errors():
        location, *path = error['loc']
        field = '.'.join(str(part) for part in path) or '_schema'
        errors.setdefault(_LOCATIONS.get(location, location), {}).setdefault(field, []).append(error['msg'])
    body = {'code': 422, 'status': _status_phrase(422), 'errors': errors}
    return JSONResponse(body, status_code=422)


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
    app.add_exception_handler(RequestValidationError, _validation_exception_handler)

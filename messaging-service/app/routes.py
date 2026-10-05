from fastapi import APIRouter

from .schemas import Message

router = APIRouter(tags=['main'])


@router.get('/', summary='Hello world')
def index() -> Message:
    return Message(message='Hello, World!')

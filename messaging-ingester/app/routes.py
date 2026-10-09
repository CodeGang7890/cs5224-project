from fastapi import APIRouter

from .schemas import Message

router = APIRouter(tags=['main'])

@router.get('/', summary='Health check')
def index() -> Message:
    return Message(message='messaging-ingester is running')

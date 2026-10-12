from fastapi import APIRouter

from .schemas import Message

router = APIRouter(tags=['main'])

@router.get('/', summary='Hello world / health check')
def index() -> Message:
    return Message(message='Hello, world! processing-service is running')

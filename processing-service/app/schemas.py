from pydantic import BaseModel, Field


class Message(BaseModel):
    message: str = Field(examples=['Hello, world! processing-service is running'])

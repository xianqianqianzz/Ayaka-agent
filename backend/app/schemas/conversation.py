from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ConversationCreate(BaseModel):
    model_id: int
    persona_id: int | None = None
    title: str | None = Field(default=None, max_length=128)


class ConversationUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=128)


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    persona_id: int | None
    model_id: int
    title: str
    created_at: datetime
    updated_at: datetime


class MessageCreate(BaseModel):
    content: str = Field(min_length=1)
    stream: bool = True


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    conversation_id: int
    role: str
    content: str
    model_id: int | None
    token_count: int | None
    created_at: datetime

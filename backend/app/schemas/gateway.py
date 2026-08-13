from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ProviderCreate(BaseModel):
    name: str
    kind: str = "custom"
    base_url: str
    api_key: str | None = None


class ProviderUpdate(BaseModel):
    name: str | None = None
    kind: str | None = None
    base_url: str | None = None
    api_key: str | None = None


class ProviderOut(BaseModel):
    id: int
    name: str
    kind: str
    base_url: str
    has_api_key: bool
    created_at: datetime


class ModelCreate(BaseModel):
    provider_id: int
    name: str
    display_name: str | None = None
    capability: str = "text-chat"


class ModelUpdate(BaseModel):
    name: str | None = None
    display_name: str | None = None
    capability: str | None = None


class ModelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    provider_id: int
    name: str
    display_name: str
    capability: str
    created_at: datetime


class ProviderModelItem(BaseModel):
    id: str
    capability: str


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    model: str | None = None
    messages: list[ChatMessage]
    stream: bool = True
    temperature: float | None = None
    max_tokens: int | None = None

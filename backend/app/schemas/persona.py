from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PersonaCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    system_prompt: str
    avatar: str | None = None
    theme_key: str = "ayaka"
    voice_model_id: int | None = None


class PersonaUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    system_prompt: str | None = None
    avatar: str | None = None
    theme_key: str | None = None
    voice_model_id: int | None = None


class PersonaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int | None
    name: str
    system_prompt: str
    avatar: str | None
    theme_key: str
    voice_model_id: int | None
    is_builtin: bool
    created_at: datetime

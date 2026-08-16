from datetime import date

from pydantic import BaseModel


class UsageSummaryItem(BaseModel):
    date: date
    capability: str
    calls: int
    prompt_tokens: int
    completion_tokens: int
    errors: int

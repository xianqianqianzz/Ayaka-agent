from app.core.db import async_session
from app.models.usage_log import UsageLog


async def log_usage(
    *,
    user_id: int,
    model_id: int | None,
    capability: str,
    prompt_tokens: int | None,
    completion_tokens: int | None,
    latency_ms: int,
    status: str,
) -> None:
    async with async_session() as db:
        db.add(
            UsageLog(
                user_id=user_id,
                model_id=model_id,
                capability=capability,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                latency_ms=latency_ms,
                status=status,
            )
        )
        await db.commit()

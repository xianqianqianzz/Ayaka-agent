from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.usage_log import UsageLog
from app.models.user import User
from app.schemas.usage import UsageSummaryItem

router = APIRouter()


@router.get("/usage/summary", response_model=list[UsageSummaryItem])
async def usage_summary(
    days: int = Query(default=7, ge=1),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows = await db.execute(
        select(
            func.date(func.timezone("UTC", UsageLog.created_at)).label("date"),
            UsageLog.capability,
            func.count(UsageLog.id).label("calls"),
            func.coalesce(func.sum(UsageLog.prompt_tokens), 0).label("prompt_tokens"),
            func.coalesce(func.sum(UsageLog.completion_tokens), 0).label(
                "completion_tokens"
            ),
            func.coalesce(
                func.sum(case((UsageLog.status == "error", 1), else_=0)), 0
            ).label("errors"),
        )
        .where(UsageLog.user_id == user.id, UsageLog.created_at >= since)
        .group_by("date", UsageLog.capability)
        .order_by("date", UsageLog.capability)
    )
    return [
        UsageSummaryItem(
            date=row.date,
            capability=row.capability,
            calls=row.calls,
            prompt_tokens=row.prompt_tokens,
            completion_tokens=row.completion_tokens,
            errors=row.errors,
        )
        for row in rows
    ]

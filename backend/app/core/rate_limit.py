import time
import uuid

import redis.asyncio as aioredis
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.config import settings
from app.core.security import decode_access_token

AUTH_WINDOW_SECONDS = 60
AUTH_LIMIT = 10
USER_WINDOW_SECONDS = 60
USER_LIMIT = 30

redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)


def _client_ip(request: Request) -> str:
    if request.client is None:
        return "unknown"
    return request.client.host


def _user_id_from_request(request: Request) -> int | None:
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        return None
    try:
        return decode_access_token(header[7:])
    except Exception:
        return None


async def _allow_request(key: str, limit: int, window_seconds: int) -> bool:
    now = time.time()
    window_start = now - window_seconds
    member = f"{now:.6f}:{uuid.uuid4().hex}"
    async with redis_client.pipeline(transaction=True) as pipe:
        pipe.zremrangebyscore(key, 0, window_start)
        pipe.zadd(key, {member: now})
        pipe.zcard(key)
        pipe.expire(key, window_seconds)
        results = await pipe.execute()
    count = int(results[2])
    return count <= limit


class RateLimitMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        path = request.url.path
        method = scope.get("method", "")

        key = None
        limit = None
        window_seconds = 60

        if path.startswith("/api/v1/auth/"):
            key = f"rl:auth:{_client_ip(request)}"
            limit = AUTH_LIMIT
            window_seconds = AUTH_WINDOW_SECONDS
        elif method == "POST" and (
            path == "/api/v1/chat/completions"
            or (
                path.startswith("/api/v1/conversations/")
                and path.endswith("/messages")
            )
        ):
            user_id = _user_id_from_request(request)
            if user_id is not None:
                key = f"rl:user:{user_id}:messages"
                limit = USER_LIMIT
                window_seconds = USER_WINDOW_SECONDS

        if key is not None and not await _allow_request(key, limit, window_seconds):
            response = JSONResponse({"detail": "请求过于频繁"}, status_code=429)
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)

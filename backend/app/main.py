import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import app.models  # noqa: F401  # 确保模型注册到 Base.metadata
from app.api.auth import router as auth_router
from app.api.conversations import router as conversations_router
from app.api.gateway import router as gateway_router
from app.api.health import router as health_router
from app.api.personas import router as personas_router
from app.api.usage import router as usage_router
from app.core.config import settings
from app.core.rate_limit import RateLimitMiddleware

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RateLimitMiddleware)

app.include_router(health_router, prefix="/api/v1", tags=["health"])
app.include_router(auth_router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(gateway_router, prefix="/api/v1", tags=["gateway"])
app.include_router(conversations_router, prefix="/api/v1", tags=["conversations"])
app.include_router(personas_router, prefix="/api/v1", tags=["personas"])
app.include_router(usage_router, prefix="/api/v1", tags=["usage"])


@app.get("/")
async def root():
    return {"app": settings.app_name, "docs": "/docs"}

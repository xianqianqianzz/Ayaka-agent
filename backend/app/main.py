from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import app.models  # noqa: F401  # 确保模型注册到 Base.metadata
from app.api.auth import router as auth_router
from app.api.gateway import router as gateway_router
from app.api.personas import router as personas_router
from app.api.health import router as health_router
from app.core.config import settings


app = FastAPI(title=settings.app_name)

# 开发阶段放开跨域；上线前应收紧为具体域名
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router, prefix="/api/v1", tags=["health"])
app.include_router(auth_router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(gateway_router, prefix="/api/v1", tags=["gateway"])
app.include_router(personas_router, prefix="/api/v1", tags=["personas"])


@app.get("/")
async def root():
    return {"app": settings.app_name, "docs": "/docs"}

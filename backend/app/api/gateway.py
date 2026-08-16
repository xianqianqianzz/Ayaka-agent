import json
import time
from typing import Any, AsyncIterator

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.security import decrypt_api_key, encrypt_api_key
from app.services.streaming import ChatStreamState, consume_sse_line
from app.services.usage import log_usage
from app.models.model import Model
from app.models.provider import Provider
from app.models.user import User
from app.schemas.gateway import (
    ChatRequest,
    ModelCreate,
    ModelOut,
    ModelUpdate,
    ProviderCreate,
    ProviderModelItem,
    ProviderOut,
    ProviderUpdate,
)

router = APIRouter()


def _provider_out(p: Provider) -> ProviderOut:
    return ProviderOut(
        id=p.id,
        name=p.name,
        kind=p.kind,
        base_url=p.base_url,
        has_api_key=bool(p.api_key_enc),
        created_at=p.created_at,
    )


# ---------- Providers ----------


@router.get("/providers", response_model=list[ProviderOut])
async def list_providers(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    providers = (
        await db.scalars(
            select(Provider).where(Provider.user_id == user.id).order_by(Provider.id)
        )
    ).all()
    return [_provider_out(p) for p in providers]


@router.post("/providers", response_model=ProviderOut, status_code=201)
async def create_provider(
    data: ProviderCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    exists = await db.scalar(
        select(Provider).where(Provider.user_id == user.id, Provider.name == data.name)
    )
    if exists:
        raise HTTPException(status_code=409, detail="Provider 名称已存在")
    provider = Provider(
        user_id=user.id,
        name=data.name,
        kind=data.kind,
        base_url=data.base_url,
        api_key_enc=encrypt_api_key(data.api_key) if data.api_key else None,
    )
    db.add(provider)
    await db.commit()
    await db.refresh(provider)
    return _provider_out(provider)


@router.put("/providers/{provider_id}", response_model=ProviderOut)
async def update_provider(
    provider_id: int,
    data: ProviderUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    provider = await db.scalar(
        select(Provider).where(Provider.id == provider_id, Provider.user_id == user.id)
    )
    if provider is None:
        raise HTTPException(status_code=404, detail="Provider 不存在")
    if data.name is not None:
        if data.name != provider.name:
            exists = await db.scalar(
                select(Provider).where(
                    Provider.user_id == user.id, Provider.name == data.name
                )
            )
            if exists:
                raise HTTPException(status_code=409, detail="Provider 名称已存在")
        provider.name = data.name
    if data.kind is not None:
        provider.kind = data.kind
    if data.base_url is not None:
        provider.base_url = data.base_url
    if data.api_key is not None:
        provider.api_key_enc = encrypt_api_key(data.api_key) if data.api_key else None
    await db.commit()
    await db.refresh(provider)
    return _provider_out(provider)


@router.delete("/providers/{provider_id}")
async def delete_provider(
    provider_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    provider = await db.scalar(
        select(Provider).where(Provider.id == provider_id, Provider.user_id == user.id)
    )
    if provider is None:
        raise HTTPException(status_code=404, detail="Provider 不存在")
    await db.delete(provider)
    await db.commit()
    return {"ok": True}


CAPABILITY_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("embedding", ("embedding", "embed", "bge", "gte-")),
    ("tts", ("tts", "speech", "voice", "cosyvoice")),
    ("asr", ("whisper", "asr", "transcribe", "speech-to-text", "sensevoice")),
    ("text-to-image", ("image", "dall-e", "dalle", "sdxl", "flux", "stable-diffusion", "draw")),
    ("text-to-video", ("video", "sora", "runway", "kling", "veo")),
]


def infer_capability(model_id: str) -> str:
    m = model_id.lower()
    for capability, keywords in CAPABILITY_KEYWORDS:
        if any(k in m for k in keywords):
            return capability
    return "text-chat"


@router.get("/providers/{provider_id}/models", response_model=list[ProviderModelItem])
async def fetch_provider_models(
    provider_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    provider = await db.scalar(
        select(Provider).where(Provider.id == provider_id, Provider.user_id == user.id)
    )
    if provider is None:
        raise HTTPException(status_code=404, detail="Provider 不存在")
    api_key = decrypt_api_key(provider.api_key_enc) if provider.api_key_enc else None
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    url = f"{provider.base_url.rstrip('/')}/models"
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(connect=10.0, read=30.0)) as client:
            resp = await client.get(url, headers=headers)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"请求服务商失败：{exc}")
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"获取模型列表失败（HTTP {resp.status_code}）：{resp.text[:500]}")
    try:
        data = resp.json()
    except ValueError:
        raise HTTPException(status_code=502, detail="服务商返回了非 JSON 响应")
    items = data.get("data", []) if isinstance(data, dict) else []
    result: list[ProviderModelItem] = []
    seen: set[str] = set()
    for it in items:
        if not isinstance(it, dict):
            continue
        mid = it.get("id")
        if not mid or mid in seen:
            continue
        seen.add(mid)
        result.append(ProviderModelItem(id=mid, capability=infer_capability(mid)))
    result.sort(key=lambda x: x.id)
    return result


# ---------- Models ----------


@router.get("/models", response_model=list[ModelOut])
async def list_models(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    return (
        await db.scalars(
            select(Model)
            .join(Provider)
            .where(Provider.user_id == user.id)
            .order_by(Model.id)
        )
    ).all()


@router.post("/models", response_model=ModelOut, status_code=201)
async def create_model(
    data: ModelCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    provider = await db.scalar(
        select(Provider).where(
            Provider.id == data.provider_id, Provider.user_id == user.id
        )
    )
    if provider is None:
        raise HTTPException(status_code=404, detail="Provider 不存在")
    model = Model(
        provider_id=data.provider_id,
        name=data.name,
        display_name=data.display_name or data.name,
        capability=data.capability,
    )
    db.add(model)
    await db.commit()
    await db.refresh(model)
    return model


@router.put("/models/{model_id}", response_model=ModelOut)
async def update_model(
    model_id: int,
    data: ModelUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    model = await db.scalar(
        select(Model)
        .join(Provider)
        .where(Model.id == model_id, Provider.user_id == user.id)
    )
    if model is None:
        raise HTTPException(status_code=404, detail="模型不存在")
    if data.name is not None:
        model.name = data.name
    if data.display_name is not None:
        model.display_name = data.display_name
    if data.capability is not None:
        model.capability = data.capability
    await db.commit()
    await db.refresh(model)
    return model


@router.delete("/models/{model_id}")
async def delete_model(
    model_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    model = await db.scalar(
        select(Model)
        .join(Provider)
        .where(Model.id == model_id, Provider.user_id == user.id)
    )
    if model is None:
        raise HTTPException(status_code=404, detail="模型不存在")
    await db.delete(model)
    await db.commit()
    return {"ok": True}


# ---------- Chat ----------


async def _resolve_model(db: AsyncSession, name: str | None, user_id: int) -> Model | None:
    if name:
        return await db.scalar(
            select(Model)
            .join(Provider)
            .where(Model.name == name, Provider.user_id == user_id)
            .order_by(Model.priority, Model.id)
            .limit(1)
        )
    return await db.scalar(
        select(Model)
        .join(Provider)
        .where(
            Provider.user_id == user_id,
            Model.capability == "text-chat",
            Model.enabled.is_(True),
        )
        .order_by(Model.priority, Model.id)
        .limit(1)
    )


async def _stream_openai(url: str, api_key: str | None, payload: dict[str, Any]) -> AsyncIterator[str]:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    timeout = httpx.Timeout(connect=10.0, read=None, write=30.0, pool=10.0)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream("POST", url, json=payload, headers=headers) as resp:
                if resp.status_code != 200:
                    body = (await resp.aread()).decode(errors="replace")[:1000]
                    yield f"data: {json.dumps({'error': {'status': resp.status_code, 'message': body}}, ensure_ascii=False)}\n\n"
                    yield "data: [DONE]\n\n"
                    return
                async for line in resp.aiter_lines():
                    yield line + "\n"
    except httpx.HTTPError as exc:
        yield f"data: {json.dumps({'error': {'message': str(exc)}}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"


async def _post_openai(url: str, api_key: str | None, payload: dict[str, Any]) -> JSONResponse:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    async with httpx.AsyncClient(timeout=httpx.Timeout(connect=10.0, read=120.0, write=30.0, pool=10.0)) as client:
        resp = await client.post(url, json=payload, headers=headers)
    if "application/json" in resp.headers.get("content-type", ""):
        body = resp.json()
    else:
        body = {"raw": resp.text[:2000]}
    return JSONResponse(body, status_code=resp.status_code)


def _post_openai_usage(resp: JSONResponse) -> tuple[dict[str, Any] | None, bool]:
    if resp.status_code != 200:
        return None, True
    try:
        body = json.loads(resp.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None, True
    usage = body.get("usage")
    return usage if isinstance(usage, dict) else None, False


async def _stream_openai_with_logging(
    url: str,
    api_key: str | None,
    payload: dict[str, Any],
    user_id: int,
    model_id: int,
    capability: str,
    started: float,
) -> AsyncIterator[str]:
    state = ChatStreamState()
    logged = False
    try:
        async for line in _stream_openai(url, api_key, payload):
            consume_sse_line(line, state)
            yield line
        latency_ms = int((time.monotonic() - started) * 1000)
        await log_usage(
            user_id=user_id,
            model_id=model_id,
            capability=capability,
            prompt_tokens=state.prompt_tokens,
            completion_tokens=state.completion_tokens,
            latency_ms=latency_ms,
            status="error" if state.error else "success",
        )
        logged = True
    finally:
        if not logged:
            latency_ms = int((time.monotonic() - started) * 1000)
            await log_usage(
                user_id=user_id,
                model_id=model_id,
                capability=capability,
                prompt_tokens=state.prompt_tokens,
                completion_tokens=state.completion_tokens,
                latency_ms=latency_ms,
                status="error",
            )


@router.post("/chat/completions")
async def chat_completions(
    data: ChatRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    model = await _resolve_model(db, data.model, user.id)
    if model is None:
        if data.model:
            raise HTTPException(status_code=404, detail=f"模型不存在：{data.model}")
        raise HTTPException(status_code=400, detail="没有可用的对话模型，请先在模型管理中添加")
    provider = await db.scalar(
        select(Provider).where(
            Provider.id == model.provider_id, Provider.user_id == user.id
        )
    )
    if provider is None:
        raise HTTPException(status_code=404, detail="模型关联的 Provider 不存在")

    payload: dict[str, Any] = {
        "model": model.name,
        "messages": [m.model_dump() for m in data.messages],
        "stream": data.stream,
    }
    if data.temperature is not None:
        payload["temperature"] = data.temperature
    if data.max_tokens is not None:
        payload["max_tokens"] = data.max_tokens

    api_key = decrypt_api_key(provider.api_key_enc) if provider.api_key_enc else None
    url = f"{provider.base_url.rstrip('/')}/chat/completions"

    started = time.monotonic()
    if data.stream:
        return StreamingResponse(
            _stream_openai_with_logging(
                url,
                api_key,
                payload,
                user.id,
                model.id,
                model.capability,
                started,
            ),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    resp = await _post_openai(url, api_key, payload)
    usage, is_error = _post_openai_usage(resp)
    await log_usage(
        user_id=user.id,
        model_id=model.id,
        capability=model.capability,
        prompt_tokens=usage.get("prompt_tokens") if usage else None,
        completion_tokens=usage.get("completion_tokens") if usage else None,
        latency_ms=int((time.monotonic() - started) * 1000),
        status="error" if is_error else "success",
    )
    return resp

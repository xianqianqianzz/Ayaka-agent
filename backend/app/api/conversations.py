import json
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.api.gateway import _post_openai, _stream_openai
from app.core.db import async_session
from app.core.security import decrypt_api_key
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.model import Model
from app.models.persona import Persona
from app.models.provider import Provider
from app.models.user import User
from app.schemas.conversation import (
    ConversationCreate,
    ConversationOut,
    ConversationUpdate,
    MessageCreate,
    MessageOut,
)

router = APIRouter()


async def _get_own_conversation(
    db: AsyncSession, conversation_id: int, user_id: int
) -> Conversation:
    conversation = await db.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id, Conversation.user_id == user_id
        )
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    return conversation


async def _get_user_model(db: AsyncSession, model_id: int, user_id: int) -> Model:
    model = await db.scalar(
        select(Model)
        .join(Provider)
        .where(Model.id == model_id, Provider.user_id == user_id)
    )
    if model is None:
        raise HTTPException(status_code=404, detail="模型不存在")
    return model


async def _get_accessible_persona(
    db: AsyncSession, persona_id: int | None, user_id: int
) -> Persona | None:
    if persona_id is None:
        return None
    persona = await db.get(Persona, persona_id)
    if persona is None or not (
        persona.user_id is None or persona.user_id == user_id
    ):
        raise HTTPException(status_code=404, detail="人设不存在")
    return persona


async def _rename_conversation(
    db: AsyncSession, conversation: Conversation, title: str
) -> Conversation:
    conversation.title = title[:128]
    await db.commit()
    await db.refresh(conversation)
    return conversation


@router.get("/conversations", response_model=list[ConversationOut])
async def list_conversations(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    conversations = (
        await db.scalars(
            select(Conversation)
            .where(Conversation.user_id == user.id)
            .order_by(Conversation.updated_at.desc())
        )
    ).all()
    return list(conversations)


@router.post("/conversations", response_model=ConversationOut, status_code=201)
async def create_conversation(
    data: ConversationCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_user_model(db, data.model_id, user.id)
    await _get_accessible_persona(db, data.persona_id, user.id)
    conversation = Conversation(
        user_id=user.id,
        persona_id=data.persona_id,
        model_id=data.model_id,
        title=data.title or "新对话",
    )
    db.add(conversation)
    await db.commit()
    await db.refresh(conversation)
    return conversation


@router.get("/conversations/{conversation_id}", response_model=ConversationOut)
async def get_conversation(
    conversation_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await _get_own_conversation(db, conversation_id, user.id)


@router.patch("/conversations/{conversation_id}", response_model=ConversationOut)
async def update_conversation(
    conversation_id: int,
    data: ConversationUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    conversation = await _get_own_conversation(db, conversation_id, user.id)
    if data.title is None:
        raise HTTPException(status_code=422, detail="请提供标题")
    return await _rename_conversation(db, conversation, data.title)


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    conversation = await _get_own_conversation(db, conversation_id, user.id)
    await db.delete(conversation)
    await db.commit()
    return {"ok": True}


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageOut])
async def list_messages(
    conversation_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_own_conversation(db, conversation_id, user.id)
    messages = (
        await db.scalars(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at, Message.id)
        )
    ).all()
    return list(messages)


@dataclass
class ChatStreamState:
    content_parts: list[str] = field(default_factory=list)
    error: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


def _consume_sse_line(line: str, state: ChatStreamState) -> None:
    data = line.strip()
    if not data.startswith("data:"):
        return
    payload = data[5:].strip()
    if not payload:
        return
    if payload == "[DONE]":
        return
    try:
        obj = json.loads(payload)
    except json.JSONDecodeError:
        return
    if "error" in obj:
        err = obj["error"]
        state.error = err.get("message") if isinstance(err, dict) else str(err)
    usage = obj.get("usage")
    if isinstance(usage, dict):
        state.prompt_tokens = usage.get("prompt_tokens")
        state.completion_tokens = usage.get("completion_tokens")
    for choice in obj.get("choices") or []:
        if not isinstance(choice, dict):
            continue
        delta = choice.get("delta") or {}
        content = delta.get("content") if isinstance(delta, dict) else None
        if isinstance(content, str):
            state.content_parts.append(content)
        message = choice.get("message") or {}
        content = message.get("content") if isinstance(message, dict) else None
        if isinstance(content, str):
            state.content_parts.append(content)


def _assistant_content(state: ChatStreamState) -> str:
    if state.error:
        return f"[错误] {state.error}"
    return "".join(state.content_parts)


async def _save_assistant_message(
    conversation_id: int, model_id: int, content: str
) -> None:
    async with async_session() as db:
        db.add(
            Message(
                conversation_id=conversation_id,
                role="assistant",
                content=content,
                model_id=model_id,
            )
        )
        await db.commit()


async def _prepare_message_payload(
    conversation_id: int, user: User, content: str
) -> tuple[Model, Provider, dict[str, Any]]:
    async with async_session() as db:
        conversation = await _get_own_conversation(db, conversation_id, user.id)
        model = await _get_user_model(db, conversation.model_id, user.id)
        provider = await db.scalar(
            select(Provider).where(
                Provider.id == model.provider_id, Provider.user_id == user.id
            )
        )
        if provider is None:
            raise HTTPException(status_code=404, detail="模型关联的 Provider 不存在")

        persona = await _get_accessible_persona(db, conversation.persona_id, user.id)
        history = (
            await db.scalars(
                select(Message)
                .where(Message.conversation_id == conversation_id)
                .order_by(Message.created_at, Message.id)
            )
        ).all()

        messages: list[dict[str, str]] = []
        if persona is not None:
            messages.append({"role": "system", "content": persona.system_prompt})
        messages.extend({"role": m.role, "content": m.content} for m in history)
        messages.append({"role": "user", "content": content})

        db.add(
            Message(
                conversation_id=conversation_id,
                role="user",
                content=content,
            )
        )
        if conversation.title == "新对话" and len(history) == 0:
            conversation.title = content[:20]
        await db.commit()

        payload: dict[str, Any] = {
            "model": model.name,
            "messages": messages,
            "stream": True,
        }
        return model, provider, payload


async def _stream_chat_and_persist(
    url: str,
    api_key: str | None,
    payload: dict[str, Any],
    conversation_id: int,
    model_id: int,
) -> AsyncIterator[str]:
    state = ChatStreamState()
    saved = False
    try:
        async for line in _stream_openai(url, api_key, payload):
            _consume_sse_line(line, state)
            yield line
        await _save_assistant_message(
            conversation_id, model_id, _assistant_content(state)
        )
        saved = True
    finally:
        if not saved:
            await _save_assistant_message(
                conversation_id, model_id, "[错误] 流式连接中断"
            )


def _non_stream_assistant_content(resp: JSONResponse) -> str:
    if resp.status_code != 200:
        return f"[错误] HTTP {resp.status_code}"
    try:
        body = json.loads(resp.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return "[错误] 服务商返回了非 JSON 响应"
    choices = body.get("choices") or []
    if choices and isinstance(choices[0], dict):
        message = choices[0].get("message") or {}
        content = message.get("content")
        if isinstance(content, str):
            return content
    return ""


@router.post("/conversations/{conversation_id}/messages")
async def create_message(
    conversation_id: int,
    data: MessageCreate,
    user: User = Depends(get_current_user),
):
    model, provider, payload = await _prepare_message_payload(
        conversation_id, user, data.content
    )
    api_key = decrypt_api_key(provider.api_key_enc) if provider.api_key_enc else None
    url = f"{provider.base_url.rstrip('/')}/chat/completions"

    if data.stream:
        return StreamingResponse(
            _stream_chat_and_persist(url, api_key, payload, conversation_id, model.id),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    payload["stream"] = False
    resp = await _post_openai(url, api_key, payload)
    await _save_assistant_message(
        conversation_id, model.id, _non_stream_assistant_content(resp)
    )
    return resp

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.persona import Persona
from app.models.user import User
from app.schemas.persona import PersonaCreate, PersonaOut, PersonaUpdate

router = APIRouter()


@router.get("/personas", response_model=list[PersonaOut])
async def list_personas(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    personas = (
        await db.scalars(
            select(Persona)
            .where(or_(Persona.user_id.is_(None), Persona.user_id == user.id))
            .order_by(Persona.is_builtin.desc(), Persona.id)
        )
    ).all()
    return list(personas)


@router.post("/personas", response_model=PersonaOut, status_code=201)
async def create_persona(
    data: PersonaCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    persona = Persona(
        user_id=user.id,
        name=data.name,
        system_prompt=data.system_prompt,
        avatar=data.avatar,
        theme_key=data.theme_key,
        voice_model_id=data.voice_model_id,
        is_builtin=False,
    )
    db.add(persona)
    await db.commit()
    await db.refresh(persona)
    return persona


async def _get_persona(db: AsyncSession, persona_id: int) -> Persona:
    persona = await db.get(Persona, persona_id)
    if persona is None:
        raise HTTPException(status_code=404, detail="人设不存在")
    return persona


def _ensure_own(persona: Persona, user: User) -> None:
    if persona.is_builtin:
        raise HTTPException(status_code=403, detail="内置人设不可修改")
    if persona.user_id != user.id:
        raise HTTPException(status_code=404, detail="人设不存在")


@router.put("/personas/{persona_id}", response_model=PersonaOut)
async def update_persona(
    persona_id: int,
    data: PersonaUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    persona = await _get_persona(db, persona_id)
    _ensure_own(persona, user)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(persona, field, value)
    await db.commit()
    await db.refresh(persona)
    return persona


@router.delete("/personas/{persona_id}")
async def delete_persona(
    persona_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    persona = await _get_persona(db, persona_id)
    _ensure_own(persona, user)
    await db.delete(persona)
    await db.commit()
    return {"ok": True}


@router.post("/personas/{persona_id}/clone", response_model=PersonaOut, status_code=201)
async def clone_persona(
    persona_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    persona = await _get_persona(db, persona_id)
    if not persona.is_builtin:
        raise HTTPException(status_code=400, detail="仅内置人设可克隆")
    cloned = Persona(
        user_id=user.id,
        name=persona.name,
        system_prompt=persona.system_prompt,
        avatar=persona.avatar,
        theme_key=persona.theme_key,
        voice_model_id=persona.voice_model_id,
        is_builtin=False,
    )
    db.add(cloned)
    await db.commit()
    await db.refresh(cloned)
    return cloned

from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional
from uuid import UUID

from app.database import get_db
from app.deps import require
from app.audit import audit
from app.models import GameApp
from app.schemas.games_apps import GameAppCreate, GameAppUpdate, GameAppOut
from app.config import get_settings
from app.game_resources import resource_path, ensure_resource, is_local_resource
from urllib.parse import urlsplit


def validate_resource(value: str, slug: str, request: Request):
    try:
        parsed = urlsplit(value)
        if value != value.strip() or any(character.isspace() for character in value) or parsed.username or parsed.password:
            raise ValueError('La dirección no debe contener espacios ni credenciales.')
        parsed.port  # Rechazar puertos mal formados.
        allowed = {urlsplit(str(request.base_url)).netloc,
                   urlsplit(get_settings().game_public_base_url or '').netloc}
        if parsed.netloc and parsed.netloc not in allowed and not is_local_resource(value, slug, allowed):
            if parsed.scheme != 'https' or not parsed.hostname or '\\' in value:
                raise ValueError('Los juegos externos deben utilizar una dirección HTTPS válida.')
            return value
        if parsed.scheme and parsed.scheme not in ('http', 'https'):
            raise ValueError('Dirección de juego no válida.')
        path = resource_path(value, slug)
        ensure_resource(slug)
        return path
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc

router = APIRouter(prefix="/games-apps", tags=["Juegos y Apps"])


def game_out(item, request: Request):
    data = GameAppOut.model_validate(item)
    base = (get_settings().game_public_base_url or str(request.base_url)).rstrip('/')
    for field in ('target_url',):
        value = getattr(data, field)
        allowed = {urlsplit(str(request.base_url)).netloc, urlsplit(base).netloc}
        local = bool(value and is_local_resource(value, item.slug, allowed))
        data.resource_kind = 'local' if local else 'external'
        if local:
            value = urlsplit(value).path
            setattr(data, field, base + value)
        if value and value.startswith('/') and not value.startswith('//'):
            setattr(data, field, base + value)
    return data


def snapshot(item: GameApp) -> dict:
    return {field: getattr(item, field) for field in (
        "title", "slug", "description", "item_type", "category", "min_tier", "is_active",
        "featured", "target_url")}

@router.get("/", response_model=List[GameAppOut])
async def list_games_apps(
    request: Request,
    db: AsyncSession = Depends(get_db),
    item_type: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    current_admin = require("games"),
):
    stmt = select(GameApp).where(GameApp.deleted_at.is_(None))
    if item_type:
        stmt = stmt.where(GameApp.item_type == item_type)
    if is_active is not None:
        stmt = stmt.where(GameApp.is_active == is_active)
    
    result = await db.execute(stmt.order_by(GameApp.created_at.desc()))
    return [game_out(item, request) for item in result.scalars().all()]

# --- NUEVA RUTA PARA SOLUCIONAR EL ERROR 405 ---
@router.get("/active", response_model=List[GameAppOut])
async def list_active_games_apps(
    request: Request,
    db: AsyncSession = Depends(get_db),
    item_type: Optional[str] = Query(None),
    #current_admin = Depends(get_current_admin)
):
    stmt = select(GameApp).where(GameApp.is_active.is_(True), GameApp.deleted_at.is_(None))
    if item_type:
        stmt = stmt.where(GameApp.item_type == item_type)
    
    result = await db.execute(stmt.order_by(GameApp.created_at.desc()))
    return [game_out(item, request) for item in result.scalars().all()]
# -----------------------------------------------

@router.post("/", response_model=GameAppOut, status_code=status.HTTP_201_CREATED)
async def create_game_app(
    payload: GameAppCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_admin = require("games", write=True),
):
    stmt = select(GameApp).where(GameApp.slug == payload.slug)
    result = await db.execute(stmt)
    if result.scalars().first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ya existe un elemento con este slug."
        )
    
    values = payload.model_dump()
    values['target_url'] = validate_resource(payload.target_url, payload.slug, request)
    new_item = GameApp(**values)
    new_item.created_by = current_admin.id
    new_item.created_by_name = current_admin.full_name
    new_item.updated_by = current_admin.id
    new_item.updated_by_name = current_admin.full_name
    db.add(new_item)
    await db.flush()
    await db.refresh(new_item)
    await audit(db, request, "games.create", "game_app", new_item.id, after=snapshot(new_item))
    return game_out(new_item, request)

@router.put("/{item_id}", response_model=GameAppOut)
async def update_game_app(
    item_id: UUID,  # <-- CAMBIADO DE int A UUID
    payload: GameAppUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_admin = require("games", write=True),
):
    item = await db.get(GameApp, item_id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No encontrado")
    
    before = snapshot(item)
    changes = payload.model_dump(exclude_unset=True)
    if 'is_active' in changes and changes['is_active'] != item.is_active:
        raise HTTPException(422, 'Activa o desactiva mediante la acción de estado, no mediante la edición.')
    if 'target_url' in changes:
        changes['target_url'] = validate_resource(changes['target_url'], item.slug, request)
    for key, value in changes.items():
        setattr(item, key, value)
    item.updated_by = current_admin.id
    item.updated_by_name = current_admin.full_name
    await db.flush()
    await db.refresh(item)
    after = snapshot(item)
    if before != after:
        await audit(db, request, "games.update", "game_app", item.id, before=before, after=after)
    return game_out(item, request)

@router.post("/{item_id}/toggle", response_model=GameAppOut)
async def toggle_game_app(
    item_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_admin = require("games", write=True),
):
    item = await db.get(GameApp, item_id)
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Juego/App no encontrado"
        )

    before = {"is_active": item.is_active, "title": item.title}
    if not item.is_active:
        if item.deleted_at is not None:
            raise HTTPException(404, 'Juego no disponible.')
        validate_resource(item.target_url or '', item.slug, request)
    item.is_active = not item.is_active
    item.updated_by = current_admin.id
    item.updated_by_name = current_admin.full_name
    await db.flush()
    await db.refresh(item)
    await audit(db, request, "games.activate" if item.is_active else "games.deactivate", "game_app", item.id,
                before=before, after={"is_active": item.is_active, "title": item.title, "slug": item.slug})
    return game_out(item, request)

@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_game_app(
    item_id: UUID,  # <-- CAMBIADO DE int A UUID
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_admin = require("games", write=True),
):
    item = await db.get(GameApp, item_id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No encontrado")
    
    await audit(db, request, "games.delete", "game_app", item.id, before=snapshot(item))
    await db.delete(item)
    return None

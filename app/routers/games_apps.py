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

router = APIRouter(prefix="/games-apps", tags=["Juegos y Apps"])


def snapshot(item: GameApp) -> dict:
    return {field: getattr(item, field) for field in (
        "title", "slug", "description", "item_type", "category", "min_tier", "is_active",
        "featured", "target_url", "icon_url", "banner_url", "preview_image_url", "sort_order")}

@router.get("/", response_model=List[GameAppOut])
async def list_games_apps(
    db: AsyncSession = Depends(get_db),
    item_type: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    current_admin = require("games"),
):
    stmt = select(GameApp)
    if item_type:
        stmt = stmt.where(GameApp.item_type == item_type)
    if is_active is not None:
        stmt = stmt.where(GameApp.is_active == is_active)
    
    result = await db.execute(stmt.order_by(GameApp.created_at.desc()))
    return result.scalars().all()

# --- NUEVA RUTA PARA SOLUCIONAR EL ERROR 405 ---
@router.get("/active", response_model=List[GameAppOut])
async def list_active_games_apps(
    db: AsyncSession = Depends(get_db),
    item_type: Optional[str] = Query(None),
    #current_admin = Depends(get_current_admin)
):
    stmt = select(GameApp).where(GameApp.is_active == True)
    if item_type:
        stmt = stmt.where(GameApp.item_type == item_type)
    
    result = await db.execute(stmt.order_by(GameApp.created_at.desc()))
    return result.scalars().all()
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
    
    new_item = GameApp(**payload.model_dump())
    new_item.updated_by = current_admin.id
    new_item.updated_by_name = current_admin.full_name
    db.add(new_item)
    await db.flush()
    await db.refresh(new_item)
    await audit(db, request, "games.create", "game_app", new_item.id, after=snapshot(new_item))
    return new_item

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
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(item, key, value)
    item.updated_by = current_admin.id
    item.updated_by_name = current_admin.full_name
    await db.flush()
    await db.refresh(item)
    after = snapshot(item)
    if before != after:
        await audit(db, request, "games.update", "game_app", item.id, before=before, after=after)
    return item

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
    item.is_active = not item.is_active
    item.updated_by = current_admin.id
    item.updated_by_name = current_admin.full_name
    await db.flush()
    await db.refresh(item)
    await audit(db, request, "games.activate" if item.is_active else "games.deactivate", "game_app", item.id,
                before=before, after={"is_active": item.is_active, "title": item.title, "slug": item.slug})
    return item

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

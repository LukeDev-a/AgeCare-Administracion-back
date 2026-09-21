from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
import uuid
from fastapi.encoders import jsonable_encoder
from app.database import get_db
from app.deps import get_current_admin
from app.models import GameApp
from app.schemas.games_apps import GameAppCreate, GameAppUpdate

router = APIRouter(prefix="/games-apps", tags=["Juegos y Apps"])

@router.get("/active")
async def get_active_games_apps(
    db: AsyncSession = Depends(get_db),
    current_admin = Depends(get_current_admin)
):
    stmt = select(GameApp).where(GameApp.is_active == True).order_by(GameApp.created_at.desc())
    result = await db.execute(stmt)
    items = result.scalars().all()
    return jsonable_encoder(items)

@router.get("/")
async def list_games_apps(
    db: AsyncSession = Depends(get_db),
    item_type: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    page_size: int = Query(200),
    current_admin = Depends(get_current_admin)
):
    stmt = select(GameApp)
    if item_type:
        stmt = stmt.where(GameApp.item_type == item_type)
    if is_active is not None:
        stmt = stmt.where(GameApp.is_active == is_active)
    
    stmt = stmt.order_by(GameApp.created_at.desc()).limit(page_size)
    result = await db.execute(stmt)
    items = result.scalars().all()
    return jsonable_encoder(items)

@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_game_app(
    payload: GameAppCreate,
    db: AsyncSession = Depends(get_db),
    current_admin = Depends(get_current_admin)
):
    stmt = select(GameApp).where(GameApp.slug == payload.slug)
    result = await db.execute(stmt)
    if result.scalars().first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ya existe un elemento con este slug."
        )
    
    new_item = GameApp(**payload.model_dump())
    db.add(new_item)
    await db.commit()
    await db.refresh(new_item)
    return jsonable_encoder(new_item)

@router.put("/{item_id}")
@router.put("/{item_id}/")
async def update_game_app(
    item_id: str,
    payload: GameAppUpdate,
    db: AsyncSession = Depends(get_db),
    current_admin = Depends(get_current_admin)
):
    try:
        parsed_id = uuid.UUID(item_id)
    except ValueError:
        parsed_id = item_id

    item = await db.get(GameApp, parsed_id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No encontrado")
    
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(item, key, value)
    
    await db.commit()
    await db.refresh(item)
    return jsonable_encoder(item)

@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
@router.delete("/{item_id}/", status_code=status.HTTP_204_NO_CONTENT)
async def delete_game_app(
    item_id: str,
    db: AsyncSession = Depends(get_db),
    current_admin = Depends(get_current_admin)
):
    try:
        parsed_id = uuid.UUID(item_id)
    except ValueError:
        parsed_id = item_id

    item = await db.get(GameApp, parsed_id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No encontrado")
    
    await db.delete(item)
    await db.commit()
    return None
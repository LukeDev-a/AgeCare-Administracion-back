from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
<<<<<<< HEAD
from typing import Optional
import uuid
from fastapi.encoders import jsonable_encoder
=======
from typing import List, Optional
from uuid import UUID

>>>>>>> dfa99a14405b591cf84eddb04598ed07e45e5355
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
<<<<<<< HEAD
    page_size: int = Query(200),
    current_admin = Depends(get_current_admin)
=======
    #current_admin = Depends(get_current_admin)
>>>>>>> dfa99a14405b591cf84eddb04598ed07e45e5355
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

<<<<<<< HEAD
@router.post("/", status_code=status.HTTP_201_CREATED)
=======
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
>>>>>>> dfa99a14405b591cf84eddb04598ed07e45e5355
async def create_game_app(
    payload: GameAppCreate,
    db: AsyncSession = Depends(get_db),
    #current_admin = Depends(get_current_admin)
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
<<<<<<< HEAD
    item_id: str,
=======
    item_id: UUID,  # <-- CAMBIADO DE int A UUID
>>>>>>> dfa99a14405b591cf84eddb04598ed07e45e5355
    payload: GameAppUpdate,
    db: AsyncSession = Depends(get_db),
    #current_admin = Depends(get_current_admin)
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
<<<<<<< HEAD
    item_id: str,
=======
    item_id: UUID,  # <-- CAMBIADO DE int A UUID
>>>>>>> dfa99a14405b591cf84eddb04598ed07e45e5355
    db: AsyncSession = Depends(get_db),
    #current_admin = Depends(get_current_admin)
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
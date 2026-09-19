from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime
from uuid import UUID

class GameAppBase(BaseModel):
    title: str = Field(..., min_length=2, max_length=150)
    slug: str = Field(..., min_length=2, max_length=100)
    description: Optional[str] = None
    item_type: Literal["game", "app"] = "game"
    category: str = Field(..., max_length=80)
    icon_url: Optional[str] = None
    banner_url: Optional[str] = None
    target_url: Optional[str] = None
    preview_image_url: Optional[str] = None  # <-- AGREGADO: Para que el frontend reciba la imagen
    is_active: bool = True
    min_tier: Literal["gratuito", "dorado", "platino"] = "gratuito"
    featured: bool = False

class GameAppCreate(GameAppBase):
    pass

class GameAppUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=2, max_length=150)
    description: Optional[str] = None
    item_type: Optional[Literal["game", "app"]] = None
    category: Optional[str] = Field(None, max_length=80)
    icon_url: Optional[str] = None
    banner_url: Optional[str] = None
    target_url: Optional[str] = None
    preview_image_url: Optional[str] = None  # <-- AGREGADO: Para permitir actualizar la imagen
    is_active: Optional[bool] = None
    min_tier: Optional[Literal["gratuito", "dorado", "platino"]] = None
    featured: Optional[bool] = None

class GameAppOut(GameAppBase):
    id: UUID  
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
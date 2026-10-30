from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import Optional, Literal
from datetime import datetime
from uuid import UUID

class GameAppBase(BaseModel):
    title: str = Field(..., min_length=2, max_length=150)
    slug: str = Field(..., min_length=2, max_length=100)
    description: Optional[str] = Field(None, max_length=4000)
    item_type: Literal["game", "app"] = "game"
    category: str = Field(..., min_length=1, max_length=80)
    target_url: Optional[str] = Field(None, max_length=500)
    is_active: bool = False
    min_tier: Literal["gratuito", "dorado", "platino"] = "gratuito"
    featured: bool = False

class GameAppCreate(GameAppBase):
    target_url: str = Field(min_length=1, max_length=500)
    is_active: Literal[False] = False

    @field_validator('title', 'category', 'slug')
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError('El campo no puede estar vacío.')
        return value

    @field_validator('slug')
    @classmethod
    def slug_format(cls, value):
        import re
        if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', value) or value == 'compartido':
            raise ValueError('Usa minúsculas, números y guiones entre palabras.')
        return value

class GameAppUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=2, max_length=150)
    description: Optional[str] = Field(None, max_length=4000)
    item_type: Optional[Literal["game", "app"]] = None
    category: Optional[str] = Field(None, min_length=1, max_length=80)
    target_url: Optional[str] = Field(None, min_length=1, max_length=500)
    is_active: Optional[bool] = None
    min_tier: Optional[Literal["gratuito", "dorado", "platino"]] = None
    featured: Optional[bool] = None

    @field_validator('title', 'category', 'item_type', 'min_tier', 'featured', 'is_active', 'target_url')
    @classmethod
    def reject_null(cls, value):
        if value is None or isinstance(value, str) and not value.strip():
            raise ValueError('El campo no puede estar vacío.')
        return value

class GameAppOut(GameAppBase):
    resource_kind: Literal['local', 'external'] = 'local'
    id: UUID  
    created_at: datetime
    updated_at: datetime
    created_by: UUID | None = None
    created_by_name: str | None = None

    model_config = ConfigDict(from_attributes=True)

"""Esquemas de configuración, legales y auditoría."""
from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.enums import LegalDocType


# ---- Configuración ----
class SettingOut(BaseModel):
    key: str
    value: Any
    schema_: dict = Field(alias="schema")
    description: str
    updated_by: dict | None
    updated_at: datetime | None
    version: int

    model_config = {"populate_by_name": True}


class SettingsOut(BaseModel):
    settings: list[SettingOut]


class SettingPutIn(BaseModel):
    value: Any
    version: int = Field(ge=1)
    change_note: str = Field(min_length=5, max_length=500)

    @field_validator('change_note', mode='before')
    @classmethod
    def trim_change_note(cls, value):
        return value.strip() if isinstance(value, str) else value


# ---- Legales ----
class LegalCurrentOut(BaseModel):
    version_id: UUID
    semver: str
    published_at: datetime | None
    effective_date: date
    requires_reacceptance: bool


class LegalDraftOut(BaseModel):
    version_id: UUID
    semver: str
    created_by_name: str | None
    updated_at: datetime


class LegalDocumentOut(BaseModel):
    doc_type: LegalDocType
    current: LegalCurrentOut | None
    drafts: list[LegalDraftOut]
    versions: list['LegalVersionDetailOut'] = Field(default_factory=list)


class LegalDocumentsOut(BaseModel):
    documents: list[LegalDocumentOut]
    computed_at: datetime
    timezone: str = 'America/Santiago'
    earliest_major_effective_date: date


class LegalVersionCreateIn(BaseModel):
    model_config = {'extra': 'forbid', 'str_strip_whitespace': True}
    semver: str = Field(pattern=r"^[0-9]+\.[0-9]+$", max_length=10)
    content_md: str = Field(min_length=100)
    changelog: str = Field(min_length=10, max_length=2000)
    effective_date: date

    @field_validator('semver')
    @classmethod
    def canonical_semver(cls, value):
        major, minor = value.split('.')
        return f'{int(major)}.{int(minor)}'


class LegalVersionOut(BaseModel):
    version_id: UUID
    doc_type: LegalDocType
    semver: str
    effective_date: date
    requires_reacceptance: bool
    status: str
    published_at: datetime | None = None
    effective_at: datetime


class LegalVersionDetailOut(LegalVersionOut):
    display_state: Literal['draft', 'scheduled', 'current', 'historical']
    content_md: str
    changelog: str
    created_by_name: str | None
    created_at: datetime
    updated_at: datetime


LegalDocumentOut.model_rebuild()
LegalDocumentsOut.model_rebuild()


# ---- Auditoría ----
class AuditEntryOut(BaseModel):
    id: UUID
    actor: dict
    action: str
    entity_type: str | None
    entity_id: UUID | None
    before: dict | None
    after: dict | None
    ip: str | None
    user_agent: str | None
    created_at: datetime
    metadata: dict = Field(default_factory=dict)
    action_label: str = ""
    module_label: str = ""
    entity_name: str = ""

"""Contrato administrativo inicial; procedencia demo explícita en cada respuesta."""
from datetime import datetime
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field
from app.enums import AppRole
from app.schemas.common import Page


class DemoSource(BaseModel):
    data_origin: Literal['demo'] = 'demo'
    deactivation_effect: Literal['demo_only'] = 'demo_only'


class EndUserOut(DemoSource):
    user_id: UUID
    full_name: str
    email: str
    is_active: bool
    memberships_count: int


class MembershipOut(BaseModel):
    patient_id: UUID
    patient_name: str
    role: AppRole
    is_owner: bool


class EndUserDetailOut(EndUserOut):
    memberships: list[MembershipOut]
    deactivated_at: datetime | None
    deactivation_reason: str | None


class PatientOut(DemoSource):
    patient_id: UUID
    full_name: str
    members_count: int


class PatientMemberOut(BaseModel):
    user_id: UUID
    full_name: str
    email: str
    role: AppRole
    is_owner: bool
    is_active: bool


class PatientDetailOut(PatientOut):
    members: list[PatientMemberOut]


class EndUserPage(Page[EndUserOut], DemoSource):
    pass


class PatientPage(Page[PatientOut], DemoSource):
    pass


class DeactivateIn(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    confirmation_user_id: UUID
    reason: str = Field(min_length=5, max_length=500)


class DeactivateOut(DemoSource):
    user: EndUserDetailOut
    mobile_sessions_revoked: Literal[False] = False

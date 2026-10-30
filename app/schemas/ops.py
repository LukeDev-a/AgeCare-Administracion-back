from datetime import datetime
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, Field, field_validator, model_validator

from app.enums import ComponentKey, ComponentStatus, IncidentStatus


class ComponentOut(BaseModel):
    key: ComponentKey
    name: str
    status: ComponentStatus
    uptime_30d: float
    latency_p50_ms: int | None
    latency_p95_ms: int | None
    note: str | None
    checked_at: datetime
    data_origin: str
    measurement_kind: str


class StatusOut(BaseModel):
    overall: ComponentStatus | None
    checked_at: datetime | None
    components: list[ComponentOut]


class LatencyRow(BaseModel):
    key: ComponentKey
    name: str
    p50_ms: int
    p95_ms: int
    sample_count: int
    computed_at: datetime
    data_origin: str
    measurement_kind: str


class LatencyOut(BaseModel):
    window: str
    components: list[LatencyRow]
    computed_at: datetime | None
    missing_components: list[ComponentKey]


class CriticalProcessOut(BaseModel):
    key: str
    name: str
    chain: str
    p95_seconds: float
    success_24h: float
    status: ComponentStatus
    computed_at: datetime
    data_origin: str
    execution_kind: str


class CriticalProcessesOut(BaseModel):
    processes: list[CriticalProcessOut]
    computed_at: datetime | None


class IncidentOut(BaseModel):
    notification_status: str
    id: UUID
    title: str
    component_key: ComponentKey | None
    severity: str
    status: IncidentStatus
    description: str
    resolution: str | None
    is_maintenance: bool
    started_at: datetime
    resolved_at: datetime | None
    created_by: UUID | None
    updated_at: datetime

    model_config = {"from_attributes": True}


class IncidentCreateIn(BaseModel):
    title: str = Field(min_length=5, max_length=160)
    component_key: ComponentKey | None = None
    severity: str = Field(pattern="^(degraded|outage)$")
    description: str = Field(min_length=1, max_length=4000)
    started_at: AwareDatetime
    is_maintenance: bool = False

    @field_validator('title', 'description', mode='before')
    @classmethod
    def trim_text(cls, value):
        return value.strip() if isinstance(value, str) else value


class IncidentPatchIn(BaseModel):
    status: IncidentStatus | None = None
    resolution: str | None = Field(default=None, min_length=1, max_length=2000)
    description: str | None = Field(default=None, min_length=1, max_length=4000)

    @field_validator('resolution', 'description', mode='before')
    @classmethod
    def trim_text(cls, value):
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode='after')
    def require_update(self):
        if not self.model_fields_set or any(getattr(self, key) is None for key in self.model_fields_set):
            raise ValueError('Envía al menos un campo y no utilices valores nulos.')
        return self

"""Sección 5 — Estado operativo."""
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Query, Request
from sqlalchemy import func, select

from app import models
from app.audit import audit
from app.incident_mail import queue_incident
from app.deps import Db, require
from app.enums import COMPONENT_NAMES, ComponentKey, ComponentStatus, IncidentStatus
from app.errors import conflict, invalid, not_found
from app.schemas.common import Page
from app.schemas.ops import (ComponentOut, CriticalProcessesOut, CriticalProcessOut,
                             IncidentCreateIn, IncidentOut, IncidentPatchIn, LatencyOut,
                             LatencyRow, StatusOut)
from app.security import as_utc, now_utc

router = APIRouter(prefix="/ops", tags=["Estado operativo"])

SYNC_COMPONENTS = [ComponentKey.database, ComponentKey.api_core, ComponentKey.auth,
                   ComponentKey.wearable_ingest, ComponentKey.storage,
                   ComponentKey.music_sync, ComponentKey.alert_engine]

_SEVERITY_ORDER = {ComponentStatus.operational: 0, ComponentStatus.degraded: 1, ComponentStatus.outage: 2}


def measurement_kind(key):
    return {ComponentKey.push: 'delivery', ComponentKey.ai_assistant: 'generation'}.get(key, 'service')


def process_chain(row):
    # Una demo no prueba que una transacción sintética haya sido ejecutada.
    if row.execution_kind == 'synthetic':
        return 'Comprobación sintética (ejecución de prueba): ' + row.chain
    return row.chain

VALID_TRANSITIONS = {
    IncidentStatus.investigating: {IncidentStatus.observing},
    IncidentStatus.observing: {IncidentStatus.resolved},
    IncidentStatus.resolved: set(),
    IncidentStatus.completed: set(),
}


# ---------- 5.1 Status ----------
@router.get("/status", response_model=StatusOut, dependencies=[require("ops")])
async def status(db: Db):
    rows = (await db.execute(select(models.ComponentState))).scalars().all()
    components = sorted(rows, key=lambda r: list(ComponentKey).index(ComponentKey(r.key)))
    overall = max((ComponentStatus(r.status) for r in rows),
                  key=lambda s: _SEVERITY_ORDER[s], default=None)
    return StatusOut(
        overall=overall,
        checked_at=max((r.checked_at for r in rows), default=None),
        components=[ComponentOut(key=ComponentKey(r.key), name=COMPONENT_NAMES[ComponentKey(r.key)],
                                 status=ComponentStatus(r.status), uptime_30d=r.uptime_30d,
                                 latency_p50_ms=r.latency_p50_ms, latency_p95_ms=r.latency_p95_ms,
                                 note=r.note, checked_at=r.checked_at, data_origin=r.data_origin,
                                 measurement_kind=measurement_kind(r.key)) for r in components])


# ---------- 5.2 Latency ----------
@router.get("/latency", response_model=LatencyOut, dependencies=[require("ops")])
async def latency(db: Db,
                  window: str = Query(default="1h"),
                  components: list[ComponentKey] | None = Query(default=None)):
    if window not in ("1h", "24h", "7d"):
        raise invalid("INVALID_WINDOW", "La ventana indicada no es válida. Usa 1h, 24h o 7d.")
    keys = list(dict.fromkeys(c.value for c in (components or SYNC_COMPONENTS)))
    rows = (await db.execute(select(models.LatencyWindow)
                             .where(models.LatencyWindow.window == window,
                                    models.LatencyWindow.component_key.in_(keys)))).scalars().all()
    rows.sort(key=lambda r: r.p95_ms)
    return LatencyOut(window=window,
                      components=[LatencyRow(key=ComponentKey(r.component_key),
                                             name=COMPONENT_NAMES[ComponentKey(r.component_key)],
                                             p50_ms=r.p50_ms, p95_ms=r.p95_ms,
                                             sample_count=r.sample_count, computed_at=r.computed_at,
                                             data_origin=r.data_origin, measurement_kind=measurement_kind(r.component_key)) for r in rows],
                      computed_at=max((r.computed_at for r in rows), default=None),
                      missing_components=[key for key in keys if key not in {r.component_key for r in rows}])


# ---------- 5.3 Critical processes ----------
@router.get("/critical-processes", response_model=CriticalProcessesOut, dependencies=[require("ops")])
async def critical_processes(db: Db):
    rows = (await db.execute(select(models.CriticalProcessState))).scalars().all()
    return CriticalProcessesOut(
        processes=[CriticalProcessOut(key=r.key, name=r.name, chain=process_chain(r),
                                      p95_seconds=r.p95_seconds, success_24h=r.success_24h,
                                      status=ComponentStatus(r.status), computed_at=r.computed_at,
                                      data_origin=r.data_origin, execution_kind=r.execution_kind) for r in rows],
        computed_at=max((r.computed_at for r in rows), default=None))


# ---------- 5.4 Listar incidentes ----------
@router.get("/incidents", response_model=Page[IncidentOut], dependencies=[require("ops")])
async def list_incidents(db: Db,
                         days: int = Query(default=30, ge=1, le=365),
                         status_f: IncidentStatus | None = Query(default=None, alias="status"),
                         component: ComponentKey | None = None,
                         page: int = Query(default=1, ge=1),
                         page_size: int = Query(default=25, ge=1, le=100)):
    since = now_utc() - timedelta(days=days)
    stmt = select(models.Incident).where(models.Incident.started_at >= since)
    if status_f:
        stmt = stmt.where(models.Incident.status == status_f)
    if component:
        stmt = stmt.where(models.Incident.component_key == component)
    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = (await db.execute(stmt.order_by(models.Incident.started_at.desc(), models.Incident.id.desc())
                             .offset((page - 1) * page_size).limit(page_size))).scalars().all()
    return Page(items=[IncidentOut.model_validate(r) for r in rows],
                page=page, page_size=page_size, total=total)


# ---------- 5.5 Crear incidente ----------
@router.post("/incidents", response_model=IncidentOut, status_code=201)
async def create_incident(body: IncidentCreateIn, request: Request, db: Db,
                          admin: models.AdminUser = require("ops", write=True)):
    if not body.is_maintenance and as_utc(body.started_at) > now_utc():
        raise invalid("STARTED_AT_FUTURE",
                      "La fecha de inicio no puede ser futura salvo en mantenimientos programados.")
    inc = models.Incident(title=body.title, component_key=body.component_key,
                          severity=body.severity, description=body.description,
                          status=IncidentStatus.observing if body.is_maintenance else IncidentStatus.investigating,
                          is_maintenance=body.is_maintenance,
                          started_at=body.started_at, created_by=admin.id)
    db.add(inc)
    await db.flush()
    await queue_incident(db, inc)
    inc.updated_at = now_utc()
    await db.flush()
    await audit(db, request, "ops.incident_create", "incident", inc.id, after=incident_snapshot(inc))
    return IncidentOut.model_validate(inc)


# ---------- 5.6 Actualizar incidente ----------
@router.patch("/incidents/{incident_id}", response_model=IncidentOut)
async def patch_incident(incident_id: UUID, body: IncidentPatchIn, request: Request, db: Db,
                         admin: models.AdminUser = require("ops", write=True)):
    inc = await db.scalar(select(models.Incident).where(models.Incident.id == incident_id).with_for_update())
    if inc is None:
        raise not_found()
    before = incident_snapshot(inc)
    changes = body.model_dump(exclude_unset=True)
    if body.status is not None:
        current = IncidentStatus(inc.status)
        target = body.status
        closing = target in (IncidentStatus.resolved, IncidentStatus.completed)
        allowed = ({IncidentStatus.completed} if current == IncidentStatus.observing else set()) if inc.is_maintenance else VALID_TRANSITIONS[current]
        if target not in allowed:
            raise conflict("INVALID_TRANSITION", "Transición de estado no permitida para este incidente.")
        if closing and not str(body.resolution or inc.resolution or '').strip():
            raise invalid("RESOLUTION_REQUIRED", "Para cerrar el incidente debes incluir la nota de resolución.")
        if closing:
            changes['resolved_at'] = now_utc()
    if all(getattr(inc, key) == value for key, value in changes.items()):
        return IncidentOut.model_validate(inc)
    for key, value in changes.items():
        setattr(inc, key, value)
    inc.updated_at = now_utc()
    await db.flush()
    await audit(db, request, "ops.incident_update", "incident", inc.id, before=before,
                after=incident_snapshot(inc))
    return IncidentOut.model_validate(inc)


def incident_snapshot(inc):
    return {key: (getattr(inc, key).isoformat() if isinstance(getattr(inc, key), datetime)
                 else str(getattr(inc, key)) if isinstance(getattr(inc, key), UUID) else getattr(inc, key))
        for key in ('title', 'component_key', 'severity', 'status', 'description', 'resolution',
                    'is_maintenance', 'started_at', 'resolved_at', 'created_by', 'updated_at')}

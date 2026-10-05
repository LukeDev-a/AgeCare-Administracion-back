"""Consulta y exportación de cambios de negocio confirmados."""
import csv
import io
from datetime import datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import String, cast, func, or_, select

from app import models
from app.audit import BUSINESS_ACTIONS
from app.deps import Db, require
from app.errors import invalid
from app.schemas.common import Page
from app.schemas.system import AuditEntryOut
from app.security import as_utc

router = APIRouter(tags=["Auditoría"])


def filtered_audit(
    actor_id: UUID | None = None,
    action: str | None = Query(default=None, max_length=60),
    entity_type: str | None = Query(default=None, max_length=40),
    entity_id: UUID | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    q: str | None = Query(default=None, max_length=120),
):
    date_from, date_to = as_utc(date_from), as_utc(date_to)
    if date_from and date_to:
        if date_from > date_to:
            raise invalid("INVALID_DATE_RANGE", "La fecha inicial debe ser anterior a la final.")
        if date_to - date_from > timedelta(days=90):
            raise invalid("RANGE_TOO_WIDE", "El rango temporal no puede superar 90 días. Acótalo.")
    # También excluye el ruido histórico del listado, conteo y exportación.
    stmt = select(models.AuditLog).where(models.AuditLog.action.in_(BUSINESS_ACTIONS))
    for column, value in ((models.AuditLog.actor_id, actor_id),
                          (models.AuditLog.action, action),
                          (models.AuditLog.entity_type, entity_type),
                          (models.AuditLog.entity_id, entity_id)):
        if value is not None:
            stmt = stmt.where(column == value)
    if date_from:
        stmt = stmt.where(models.AuditLog.created_at >= date_from)
    if date_to:
        stmt = stmt.where(models.AuditLog.created_at <= date_to)
    if q:
        # Escape de comodines: la búsqueda representa texto literal.
        pattern = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        matching_actions = [action for action, labels in BUSINESS_ACTIONS.items()
                            if any(q.casefold() in label.casefold() for label in labels)]
        stmt = stmt.where(or_(models.AuditLog.action.in_(matching_actions), *(column.ilike(pattern, escape="\\") for column in (
            models.AuditLog.actor_name, models.AuditLog.action, models.AuditLog.entity_type,
            cast(models.AuditLog.before, String), cast(models.AuditLog.after, String)))))
    return stmt


FilteredAudit = Annotated[object, Depends(filtered_audit)]


def entry_out(row: models.AuditLog) -> AuditEntryOut:
    before = dict(row.before or {})
    before.pop("__audit", None)
    after = dict(row.after or {})
    after.pop("__audit", None)
    label, module = BUSINESS_ACTIONS[row.action]
    if row.action == "games.toggle" and "is_active" in after:
        label = "Activó un juego o aplicación" if after["is_active"] else "Desactivó un juego o aplicación"
    values = {**before, **after}
    name = next((str(values[key]) for key in ("title", "name", "full_name", "subject", "slug") if values.get(key)), "")
    if not name and values.get("number"):
        name = f"Ticket #{values['number']}"
    return AuditEntryOut(
        id=row.id, actor={"admin_id": str(row.actor_id) if row.actor_id else None,
                          "name": row.actor_name, "role": row.actor_role},
        action=row.action, entity_type=row.entity_type, entity_id=row.entity_id,
        before=before or None, after=after or None, metadata={},
        action_label=label, module_label=module, entity_name=name,
        ip=row.ip, user_agent=row.user_agent, created_at=row.created_at)


@router.get("/audit-log", response_model=Page[AuditEntryOut], dependencies=[require("audit")])
async def audit_log(db: Db, stmt: FilteredAudit,
                    page: int = Query(default=1, ge=1),
                    page_size: int = Query(default=25, ge=1, le=100)):
    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = (await db.execute(stmt.order_by(models.AuditLog.created_at.desc(), models.AuditLog.id.desc())
                            .offset((page - 1) * page_size).limit(page_size))).scalars().all()
    return Page(items=[entry_out(row) for row in rows], total=total, page=page, page_size=page_size)


def csv_cell(value) -> str:
    text = "" if value is None else str(value)
    # Evita que una hoja de cálculo ejecute nombres o etiquetas como fórmulas.
    return "'" + text if text.lstrip().startswith(("=", "+", "-", "@")) else text


@router.get("/audit-log/export", dependencies=[require("audit")])
async def export_audit(db: Db, stmt: FilteredAudit):
    rows = (await db.execute(stmt.order_by(models.AuditLog.created_at.desc(), models.AuditLog.id.desc())
                            .limit(5001))).scalars().all()
    if len(rows) > 5000:
        raise invalid("EXPORT_TOO_LARGE", "La exportación admite 5000 eventos. Acota los filtros.")
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer)
    writer.writerow(["Fecha UTC", "Usuario", "Rol", "Acción", "Módulo", "Registro", "ID registro"])
    for row in rows:
        entry = entry_out(row)
        writer.writerow([csv_cell(v) for v in (
            as_utc(row.created_at).isoformat(), row.actor_name, row.actor_role,
            entry.action_label, entry.module_label, entry.entity_name, row.entity_id)])
    return Response("\ufeff" + buffer.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="agecare-auditoria.csv"'})

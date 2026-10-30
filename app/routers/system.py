"""Secciones 12, 13 y 14 — Configuración, legales y auditoría."""
from uuid import UUID

from fastapi import APIRouter, Query, Request
from jsonschema import Draft202012Validator
from sqlalchemy import select

from app import models
from app.audit import audit
from app.deps import Db, require
from app.enums import LegalDocType
from app.errors import ApiError, conflict, invalid, not_found
from app.schemas.system import (LegalCurrentOut, LegalDocumentOut, LegalVersionDetailOut,
                                LegalDocumentsOut, LegalDraftOut, LegalVersionCreateIn,
                                LegalVersionOut, SettingOut, SettingPutIn, SettingsOut)
from app.security import as_utc, now_utc
from app.legal_documents import current_version, earliest_major_date, effective_at, semver, validate_schedule, versions

router = APIRouter(tags=["Sistema"])



def _setting_out(s: models.SystemSetting) -> SettingOut:
    return SettingOut(key=s.key, value=s.value, schema=s.value_schema, description=s.description,
                      updated_by={"admin_id": str(s.updated_by), "name": s.updated_by_name}
                      if s.updated_by else None,
                      updated_at=as_utc(s.updated_at), version=s.version)


# ---------- 12.1 Leer configuración ----------
@router.get("/settings", response_model=SettingsOut, dependencies=[require("settings")])
async def get_settings_endpoint(db: Db, key: str | None = Query(default=None)):
    stmt = select(models.SystemSetting)
    if key:
        stmt = stmt.where(models.SystemSetting.key == key)
    rows = (await db.execute(stmt.order_by(models.SystemSetting.key))).scalars().all()
    if key and not rows:
        raise ApiError(404, "UNKNOWN_SETTING", "No existe ningún parámetro con esa clave.")
    return SettingsOut(settings=[_setting_out(s) for s in rows])


# ---------- 12.2 Modificar parámetro ----------
@router.put("/settings/{key}", response_model=SettingOut)
async def put_setting(key: str, body: SettingPutIn, request: Request, db: Db,
                      admin: models.AdminUser = require("settings", write=True)):
    s = await db.scalar(select(models.SystemSetting).where(models.SystemSetting.key == key)
                         .with_for_update().execution_options(populate_existing=True))
    if s is None:
        raise ApiError(404, "UNKNOWN_SETTING", "No existe ningún parámetro con esa clave.")
    if body.version != s.version:
        raise conflict("VERSION_CONFLICT", "El parámetro fue modificado por otra persona. Recarga y aplica de nuevo.")
    errors = sorted(Draft202012Validator(s.value_schema).iter_errors(body.value), key=str)
    if errors:
        details = [{"field": "/".join(str(p) for p in e.path) or key, "issue": e.message} for e in errors]
        raise invalid("INVALID_VALUE", "El valor no cumple el esquema del parámetro. Revisa error.details.", details)
    before = {"key": s.key, "name": s.description or s.key, "value": s.value, "version": s.version}
    s.value = body.value
    s.version += 1
    s.updated_by = admin.id
    s.updated_by_name = admin.full_name
    s.updated_at = now_utc()
    await audit(db, request, "settings.update", "system_setting", None,
                before=before, after={"key": s.key, "name": s.description or s.key,
                                     "value": s.value, "version": s.version, "note": body.change_note})
    return _setting_out(s)


# ---------- 13.1 Documentos legales ----------
@router.get("/legal/documents", response_model=LegalDocumentsOut, dependencies=[require("legal")])
async def legal_documents(db: Db, doc_type: LegalDocType | None = Query(default=None)):
    types = [doc_type] if doc_type else list(LegalDocType)
    now = now_utc()
    docs = []
    for t in types:
        rows = sorted(await versions(db, t), key=lambda row: semver(row.semver), reverse=True)
        current = current_version(rows, now)
        docs.append(LegalDocumentOut(
            doc_type=t,
            current=LegalCurrentOut(version_id=current.id, semver=current.semver,
                                    published_at=as_utc(current.published_at) if current.published_at else None,
                                    effective_date=current.effective_date,
                                    requires_reacceptance=current.requires_reacceptance)
            if current else None,
            drafts=[LegalDraftOut(version_id=r.id, semver=r.semver,
                                  created_by_name=r.created_by_name, updated_at=as_utc(r.updated_at))
                    for r in rows if r.status == "draft"],
            versions=[LegalVersionDetailOut(**_version_out(r).model_dump(), content_md=r.content_md,
                      changelog=r.changelog, created_by_name=r.created_by_name,
                      created_at=as_utc(r.created_at), updated_at=as_utc(r.updated_at),
                      display_state='draft' if r.status == 'draft' else 'current' if current and r.id == current.id
                      else 'scheduled' if effective_at(r.effective_date) > as_utc(now) else 'historical') for r in rows]))
    return LegalDocumentsOut(documents=docs, computed_at=now,
                             earliest_major_effective_date=earliest_major_date(now))


def _semver_tuple(v: str) -> tuple[int, int]:
    return semver(v)


def _version_out(v):
    return LegalVersionOut(version_id=v.id, doc_type=LegalDocType(v.doc_type), semver=v.semver,
                           effective_date=v.effective_date, effective_at=effective_at(v.effective_date),
                           requires_reacceptance=v.requires_reacceptance, status=v.status,
                           published_at=as_utc(v.published_at) if v.published_at else None)


def _legal_snapshot(v):
    return {'doc_type': v.doc_type, 'semver': v.semver, 'status': v.status,
            'effective_date': v.effective_date.isoformat(), 'requires_reacceptance': v.requires_reacceptance,
            'published_at': v.published_at.isoformat() if v.published_at else None}


# ---------- 13.2 Crear versión ----------
@router.post("/legal/documents/{doc_type}/versions", response_model=LegalVersionOut, status_code=201)
async def create_legal_version(doc_type: LegalDocType, body: LegalVersionCreateIn,
                               request: Request, db: Db,
                               admin: models.AdminUser = require("legal", write=True)):
    rows = await versions(db, doc_type, lock=True)
    requires_reacceptance = validate_schedule(rows, body.semver, body.effective_date, now_utc())
    v = models.LegalVersion(doc_type=doc_type, semver=body.semver, content_md=body.content_md,
                            changelog=body.changelog, effective_date=body.effective_date,
                            requires_reacceptance=requires_reacceptance,
                            created_by=admin.id, created_by_name=admin.full_name)
    db.add(v)
    await db.flush()
    await audit(db, request, "legal.version_create", "legal_version", v.id,
                after=_legal_snapshot(v))
    return _version_out(v)


# ---------- 13.3 Publicar versión ----------
@router.post("/legal/versions/{version_id}/publish", response_model=LegalVersionOut)
async def publish_legal_version(version_id: UUID, request: Request, db: Db,
                                admin: models.AdminUser = require("legal", write=True)):
    v = await db.get(models.LegalVersion, version_id)
    if v is None:
        raise not_found()
    rows = await versions(db, LegalDocType(v.doc_type), lock=True)
    v = next(row for row in rows if row.id == version_id)
    if v.status == "published":
        raise conflict("ALREADY_PUBLISHED", "Esta versión ya está publicada.")
    now = now_utc()
    major = validate_schedule(rows, v.semver, v.effective_date, now, exclude_id=v.id)
    before = _legal_snapshot(v)
    v.requires_reacceptance = major
    v.status = "published"
    v.published_at = now
    v.updated_at = now
    # La versión anterior queda en el histórico: los consentimientos antiguos la siguen referenciando.
    await audit(db, request, "legal.version_publish", "legal_version", v.id,
                before=before, after=_legal_snapshot(v))
    return _version_out(v)

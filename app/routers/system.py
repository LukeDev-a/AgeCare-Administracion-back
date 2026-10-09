"""Secciones 12, 13 y 14 — Configuración, legales y auditoría."""
from datetime import date, timedelta
from uuid import UUID

from fastapi import APIRouter, Query, Request
from jsonschema import Draft202012Validator
from sqlalchemy import select

from app import models
from app.audit import audit
from app.deps import Db, require
from app.enums import LegalDocType
from app.errors import ApiError, conflict, invalid, not_found
from app.schemas.system import (LegalCurrentOut, LegalDocumentOut,
                                LegalDocumentsOut, LegalDraftOut, LegalVersionCreateIn,
                                LegalVersionOut, SettingOut, SettingPutIn, SettingsOut)
from app.security import as_utc, now_utc

router = APIRouter(tags=["Sistema"])

MAJOR_NOTICE_DAYS = 15


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
    docs = []
    for t in types:
        rows = (await db.execute(select(models.LegalVersion)
                                 .where(models.LegalVersion.doc_type == t)
                                 .order_by(models.LegalVersion.created_at.desc()))).scalars().all()
        published = [r for r in rows if r.status == "published"]
        current = max(published, key=lambda r: tuple(map(int, r.semver.split(".")))) if published else None
        docs.append(LegalDocumentOut(
            doc_type=t,
            current=LegalCurrentOut(version_id=current.id, semver=current.semver,
                                    published_at=current.published_at,
                                    effective_date=current.effective_date,
                                    requires_reacceptance=current.requires_reacceptance)
            if current else None,
            drafts=[LegalDraftOut(version_id=r.id, semver=r.semver,
                                  created_by_name=r.created_by_name, updated_at=r.updated_at)
                    for r in rows if r.status == "draft"]))
    return LegalDocumentsOut(documents=docs)


def _semver_tuple(v: str) -> tuple[int, int]:
    major, minor = v.split(".")
    return int(major), int(minor)


# ---------- 13.2 Crear versión ----------
@router.post("/legal/documents/{doc_type}/versions", response_model=LegalVersionOut, status_code=201)
async def create_legal_version(doc_type: LegalDocType, body: LegalVersionCreateIn,
                               request: Request, db: Db,
                               admin: models.AdminUser = require("legal", write=True)):
    rows = (await db.execute(select(models.LegalVersion)
                             .where(models.LegalVersion.doc_type == doc_type))).scalars().all()
    published = [r for r in rows if r.status == "published"]
    current = max(published, key=lambda r: _semver_tuple(r.semver)) if published else None
    if current and _semver_tuple(body.semver) <= _semver_tuple(current.semver):
        raise conflict("SEMVER_NOT_GREATER", "La versión debe ser mayor que la vigente.")
    if any(r.semver == body.semver for r in rows):
        raise conflict("SEMVER_NOT_GREATER", "La versión debe ser mayor que la vigente.")
    requires_reacceptance = current is None or _semver_tuple(body.semver)[0] > _semver_tuple(current.semver)[0]
    if requires_reacceptance and body.effective_date < date.today() + timedelta(days=MAJOR_NOTICE_DAYS):
        raise invalid("NOTICE_PERIOD",
                      "Un cambio mayor exige una fecha de vigencia con al menos 15 días de aviso.")
    v = models.LegalVersion(doc_type=doc_type, semver=body.semver, content_md=body.content_md,
                            changelog=body.changelog, effective_date=body.effective_date,
                            requires_reacceptance=requires_reacceptance,
                            created_by=admin.id, created_by_name=admin.full_name)
    db.add(v)
    await db.flush()
    await audit(db, request, "legal.version_create", "legal_version", v.id,
                after={"doc_type": doc_type, "semver": body.semver})
    return LegalVersionOut(version_id=v.id, doc_type=doc_type, semver=v.semver,
                           effective_date=v.effective_date,
                           requires_reacceptance=v.requires_reacceptance, status=v.status)


# ---------- 13.3 Publicar versión ----------
@router.post("/legal/versions/{version_id}/publish", response_model=LegalVersionOut)
async def publish_legal_version(version_id: UUID, request: Request, db: Db,
                                admin: models.AdminUser = require("legal", write=True)):
    v = await db.get(models.LegalVersion, version_id)
    if v is None:
        raise not_found()
    if v.status == "published":
        raise conflict("ALREADY_PUBLISHED", "Esta versión ya está publicada.")
    if v.effective_date < date.today():
        raise conflict("EFFECTIVE_DATE_PAST",
                       "La fecha de vigencia ya pasó; crea una versión nueva con fecha futura.")
    v.status = "published"
    v.published_at = now_utc()
    # La versión anterior queda en el histórico: los consentimientos antiguos la siguen referenciando.
    await audit(db, request, "legal.version_publish", "legal_version", v.id,
                after={"semver": v.semver})
    return LegalVersionOut(version_id=v.id, doc_type=LegalDocType(v.doc_type), semver=v.semver,
                           effective_date=v.effective_date,
                           requires_reacceptance=v.requires_reacceptance,
                           status=v.status, published_at=v.published_at)

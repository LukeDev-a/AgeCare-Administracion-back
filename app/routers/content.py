"""Sección 9 — Curación de contenido."""
from uuid import UUID
from pathlib import Path

from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app import models
from app.audit import audit
from app.deps import Db, require
from app.enums import ContentStatus, ContentType, AdminRole
from app.errors import conflict, forbidden, invalid, not_found
from app.config import get_settings
from app.content_editorial import current_audio, editorial_ready, invalidate, queue_audio, publish
from app.schemas.common import Page
from app.schemas.operation import ContentCreateIn, ContentItemOut, ContentPatchIn
from app.security import as_utc, now_utc

router = APIRouter(prefix="/content", tags=["Curación de contenido"])


def _out(i: models.ContentItem) -> ContentItemOut:
    return ContentItemOut(id=i.id, type=ContentType(i.type), title=i.title, body=i.body,
                          audio_available=current_audio(i), audio_status=i.audio_status, audio_error=i.audio_error,
                          audio_url=f'/api/v1/admin/content/items/{i.id}/audio' if current_audio(i) else None,
                          text_version=i.text_version, approved_version=i.approved_version,
                          reviewed_by_name=i.reviewed_by_name, reviewed_at=i.reviewed_at,
                          source_candidate_id=i.source_candidate_id, provenance=i.provenance, tags=i.tags or [],
                          status=ContentStatus(i.status), publish_at=as_utc(i.publish_at) if i.publish_at else None,
                          published_at=as_utc(i.published_at) if i.published_at else None, created_by_name=i.created_by_name,
                          updated_at=as_utc(i.updated_at))


async def _get(db, item_id: UUID) -> models.ContentItem:
    item = await db.scalar(select(models.ContentItem).where(models.ContentItem.id == item_id)
                          .with_for_update().execution_options(populate_existing=True))
    if item is None or item.deleted_at is not None:
        raise not_found()
    return item


async def _saved(db, item):
    await db.flush()
    await db.refresh(item)
    await db.commit()
    return _out(item)


# ---------- 9.1 Listar ----------
@router.get("/items", response_model=Page[ContentItemOut], dependencies=[require("content")])
async def list_items(db: Db,
                     type_f: ContentType | None = Query(default=None, alias="type"),
                     status_f: ContentStatus | None = Query(default=None, alias="status"),
                     q: str | None = Query(default=None, max_length=120),
                     page: int = Query(default=1, ge=1),
                     page_size: int = Query(default=25, ge=1, le=100)):
    stmt = select(models.ContentItem).where(models.ContentItem.deleted_at.is_(None))
    if type_f:
        stmt = stmt.where(models.ContentItem.type == type_f)
    if status_f:
        stmt = stmt.where(models.ContentItem.status == status_f)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(models.ContentItem.title.ilike(like) | models.ContentItem.body.ilike(like))
    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = (await db.execute(stmt.order_by(models.ContentItem.updated_at.desc())
                             .offset((page - 1) * page_size).limit(page_size))).scalars().all()
    return Page(items=[_out(i) for i in rows], page=page, page_size=page_size, total=total)


# ---------- 9.2 Crear ----------
@router.post("/items", response_model=ContentItemOut, status_code=201)
async def create_item(body: ContentCreateIn, request: Request, db: Db,
                      admin: models.AdminUser = require("content", write=True)):
    if body.publish_at is not None and as_utc(body.publish_at) <= now_utc():
        raise invalid("PUBLISH_AT_PAST", "La fecha de publicación programada debe ser futura.")
    item = models.ContentItem(type=body.type, title=body.title, body=body.body,
                              tags=body.tags, publish_at=as_utc(body.publish_at) if body.publish_at else None,
                              created_by=admin.id, created_by_name=admin.full_name,
                              tts_ready=False, audio_status='pending')
    db.add(item)
    await db.flush()
    await db.refresh(item)
    await queue_audio(db, item)
    await audit(db, request, "content.create", "content_item", item.id, after={"title": item.title})
    return await _saved(db, item)


# ---------- 9.3 Editar ----------
@router.patch("/items/{item_id}", response_model=ContentItemOut)
async def patch_item(item_id: UUID, body: ContentPatchIn, request: Request, db: Db,
                     admin: models.AdminUser = require("content", write=True)):
    item = await _get(db, item_id)
    before = {"title": item.title, "text_version": item.text_version, "tags": item.tags,
              "publish_at": as_utc(item.publish_at).isoformat() if item.publish_at else None}
    if body.publish_at is not None and item.status != 'draft':
        raise conflict('SCHEDULE_REQUIRES_DRAFT', 'La programación automática se aplica a borradores.')
    if body.publish_at is not None and as_utc(body.publish_at) <= now_utc():
        raise invalid("PUBLISH_AT_PAST", "La fecha de publicación programada debe ser futura.")
    text_changed = (body.body is not None and body.body != item.body) or (body.title is not None and body.title != item.title)
    if text_changed:
        invalidate(item)
    if body.body is not None and body.body != item.body:
        item.body = body.body
    if body.title is not None:
        item.title = body.title
    if body.tags is not None:
        item.tags = body.tags
    if "publish_at" in body.model_fields_set:
        item.publish_at = as_utc(body.publish_at) if body.publish_at else None
    await db.flush()
    await db.refresh(item)
    if text_changed:
        await queue_audio(db, item)
    await audit(db, request, "content.update", "content_item", item.id, before=before,
                after={"title": item.title, "text_version": item.text_version, "tags": item.tags,
                       "publish_at": item.publish_at.isoformat() if item.publish_at else None})
    return await _saved(db, item)


# ---------- 9.4 Publicar ----------
@router.post("/items/{item_id}/publish", response_model=ContentItemOut)
async def publish_item(item_id: UUID, request: Request, db: Db,
                       admin: models.AdminUser = require("content", write=True)):
    item = await _get(db, item_id)
    await publish(db, item, request)
    await db.flush()
    await db.refresh(item)
    return await _saved(db, item)


# ---------- 9.5 Retirar ----------
@router.post("/items/{item_id}/unpublish", response_model=ContentItemOut)
async def unpublish_item(item_id: UUID, request: Request, db: Db,
                         admin: models.AdminUser = require("content", write=True)):
    item = await _get(db, item_id)
    if ContentStatus(item.status) != ContentStatus.published:
        raise conflict("NOT_PUBLISHED", "Solo puede retirarse contenido publicado.")
    item.status = ContentStatus.archived
    await db.flush()
    await db.refresh(item)
    await audit(db, request, "content.unpublish", "content_item", item.id)
    return await _saved(db, item)


# ---------- 9.6 Eliminar ----------
@router.delete("/items/{item_id}", status_code=204)
async def delete_item(item_id: UUID, request: Request, db: Db,
                      admin: models.AdminUser = require("content", write=True)):
    if admin.role != AdminRole.admin:
        raise forbidden()
    item = await _get(db, item_id)
    if ContentStatus(item.status) == ContentStatus.published:
        raise conflict("ITEM_PUBLISHED", "Retira el contenido del feed antes de eliminarlo.")
    item.deleted_at = now_utc()
    await audit(db, request, "content.delete", "content_item", item.id)
    await db.commit()
    return Response(status_code=204)


class ApprovalIn(BaseModel):
    version: int = Field(ge=1)


@router.post('/items/{item_id}/approve', response_model=ContentItemOut)
async def approve_item(item_id: UUID, body: ApprovalIn, request: Request, db: Db,
                       admin: models.AdminUser = require('content', write=True)):
    item = await _get(db, item_id)
    if body.version != item.text_version:
        raise conflict('VERSION_CONFLICT', 'El texto cambió; recarga y revísalo antes de aprobar.')
    if item.source_candidate_id:
        candidate = await db.get(models.NewsCandidate, item.source_candidate_id)
        if not candidate or candidate.rights_status != 'own' or candidate.source_changed or candidate.status == 'discarded':
            raise conflict('SOURCE_REVIEW_REQUIRED', 'Confirma texto propio, revisa cambios del original y resuelve descartes antes de aprobar.')
        item.provenance = {'source': candidate.source, 'url': candidate.source_url, 'author': candidate.author,
            'license': 'CC BY-SA 4.0', 'license_url': 'https://creativecommons.org/licenses/by-sa/4.0/',
            'changes': 'Texto adaptado para AgeCare y narración sintética.', 'rights_verified': True}
    item.approved_version = item.text_version
    item.reviewed_by = admin.id
    item.reviewed_by_name = admin.full_name
    item.reviewed_at = now_utc()
    await queue_audio(db, item)
    await audit(db, request, 'content.approve', 'content_item', item.id,
        after={'title': item.title, 'text_version': item.text_version})
    await db.flush(); await db.refresh(item)
    return await _saved(db, item)


@router.post('/items/{item_id}/audio/retry', response_model=ContentItemOut)
async def retry_audio(item_id: UUID, request: Request, db: Db,
                      admin: models.AdminUser = require('content', write=True)):
    item = await _get(db, item_id)
    if not editorial_ready(item):
        raise conflict('REVIEW_REQUIRED', 'Aprueba primero el texto vigente.')
    if item.audio_status in {'queued', 'waiting_quota'}:
        return _out(item)
    await queue_audio(db, item, retry=True)
    await audit(db, request, 'content.audio_retry', 'content_item', item.id, after={'title': item.title})
    await db.flush(); await db.refresh(item)
    return await _saved(db, item)


@router.get('/items/{item_id}/audio', dependencies=[require('content')])
async def get_audio(item_id: UUID, db: Db):
    item = await _get(db, item_id)
    if not current_audio(item):
        raise conflict('TTS_PENDING', 'El audio vigente no está disponible.')
    return FileResponse(Path(get_settings().content_audio_dir) / item.audio_file,
        media_type='audio/wav', headers={'Cache-Control': 'no-store'})


@router.get('/feed', dependencies=[require('content')])
async def integration_feed(db: Db, page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100)):
    # Contrato protegido de referencia para el equipo móvil; no es feed público.
    statement = select(models.ContentItem).where(models.ContentItem.deleted_at.is_(None),
        models.ContentItem.status == 'published').order_by(models.ContentItem.published_at.desc())
    rows = (await db.scalars(statement.offset((page - 1) * page_size).limit(page_size))).all()
    return {'items': [_out(row) for row in rows if editorial_ready(row)], 'page': page, 'page_size': page_size}

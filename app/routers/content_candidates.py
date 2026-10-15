"""Consulta editorial, recopilación y adaptación. Nunca publica desde la ingesta."""
from uuid import UUID
from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from app import models
from app.audit import audit
from app.deps import Db, require
from app.errors import conflict, not_found, invalid
from app.content_pipeline import control
from app.content_editorial import queue_audio
from app.security import now_utc
from app.config import get_settings
from app.schemas.operation import ContentItemOut
from app.routers.content import _saved

router = APIRouter(prefix='/content', tags=['Revisión editorial'])


def candidate_out(row):
    return {key: getattr(row, key) for key in ['id', 'source', 'external_id', 'title', 'original_text', 'source_url',
        'author', 'source_date', 'source_modified', 'source_changed', 'rights_status', 'rights_note', 'status',
        'classification', 'editorial_note', 'adaptation', 'item_id', 'created_at', 'updated_at', 'source_hash']}


async def get_candidate(db, candidate_id):
    candidate = await db.scalar(select(models.NewsCandidate).where(models.NewsCandidate.id == candidate_id).with_for_update())
    if not candidate: raise not_found()
    return candidate


@router.get('/candidates', dependencies=[require('content')])
async def candidates(db: Db, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
                     status: str | None = None, q: str | None = Query(None, max_length=120)):
    stmt = select(models.NewsCandidate)
    if status: stmt = stmt.where(models.NewsCandidate.status == status)
    if q: stmt = stmt.where(models.NewsCandidate.title.ilike(f'%{q}%'))
    total = await db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = (await db.scalars(stmt.order_by(models.NewsCandidate.created_at.desc())
        .offset((page - 1) * page_size).limit(page_size))).all()
    return {'items': [candidate_out(row) for row in rows], 'page': page, 'page_size': page_size, 'total': total}


@router.get('/jobs', dependencies=[require('content')])
async def jobs(db: Db):
    rows = (await db.scalars(select(models.ContentJob).order_by(models.ContentJob.created_at.desc()).limit(50))).all()
    return {'items': [{key: getattr(row, key) for key in ['id', 'kind', 'target_id', 'status', 'attempts', 'error',
        'available_at', 'created_at', 'started_at', 'finished_at', 'result']} for row in rows]}


@router.get('/runtime', dependencies=[require('content')])
async def runtime():
    settings = get_settings()
    return {'worker_enabled': settings.content_worker_enabled,
            'gemini_ready': bool(settings.gemini_api_key and settings.gemini_free_tier_confirmed),
            'collection_hour': settings.news_collection_hour, 'timezone': 'America/Santiago',
            'collection_limit': settings.news_collection_limit, 'adaptation_batch': settings.news_adaptation_batch}


@router.post('/collect', status_code=202)
async def collect_now(request: Request, db: Db, admin: models.AdminUser = require('content', write=True)):
    await control(db, 'collection')
    if await db.scalar(select(models.ContentJob.id).where(models.ContentJob.kind == 'collect',
            models.ContentJob.status.in_(['queued', 'waiting_quota']))):
        raise conflict('COLLECTION_QUEUED', 'Ya hay una recopilación pendiente.')
    job = models.ContentJob(kind='collect', actor_id=admin.id, actor_name=admin.full_name)
    db.add(job); await db.flush()
    await audit(db, request, 'content.collection_request', 'content_job', job.id)
    await db.commit()
    return {'job_id': job.id, 'status': 'queued'}


@router.post('/candidates/{candidate_id}/adapt', status_code=202)
async def adapt_candidate(candidate_id: UUID, request: Request, db: Db,
                           admin: models.AdminUser = require('content', write=True)):
    candidate = await get_candidate(db, candidate_id)
    if candidate.item_id or candidate.status == 'discarded':
        raise conflict('CANDIDATE_UNAVAILABLE', 'El candidato ya tiene borrador o fue descartado.')
    if await db.scalar(select(models.ContentJob.id).where(models.ContentJob.target_id == candidate.id,
            models.ContentJob.kind == 'adapt', models.ContentJob.status.in_(['queued', 'waiting_quota']))):
        raise conflict('ADAPTATION_QUEUED', 'La adaptación ya está pendiente.')
    candidate.status = 'queued'
    db.add(models.ContentJob(kind='adapt', target_id=candidate.id, actor_id=admin.id, actor_name=admin.full_name))
    await audit(db, request, 'content.adaptation_request', 'news_candidate', candidate.id, after={'title': candidate.title})
    await db.flush(); await db.refresh(candidate)
    await db.commit()
    return candidate_out(candidate)


class ReviewIn(BaseModel):
    action: str = Field(pattern='^(own|third_party|uncertain|discard|keep)$')
    note: str = Field(min_length=5, max_length=2000)
    source_hash: str = Field(min_length=1, max_length=64)


@router.post('/candidates/{candidate_id}/review')
async def review_candidate(candidate_id: UUID, body: ReviewIn, request: Request, db: Db,
                           admin: models.AdminUser = require('content', write=True)):
    candidate = await get_candidate(db, candidate_id)
    if body.source_hash != candidate.source_hash:
        raise conflict('SOURCE_CHANGED', 'La fuente cambió: recarga y revisa el original antes de guardar tu decisión.')
    if len(body.note.strip()) < 5: raise invalid('INVALID_NOTE', 'Explica la decisión editorial.')
    if body.action == 'discard': candidate.status = 'discarded'
    elif body.action == 'keep': candidate.status = 'adapted' if candidate.adaptation else 'pending'
    else:
        candidate.rights_status = body.action
        candidate.rights_note = body.note.strip()
        candidate.source_changed = False
    candidate.editorial_note = body.note.strip()
    # Revocar aprobación al cambiar procedencia o descartar; nunca sobrescribir texto editado.
    if candidate.item_id:
        item = await db.get(models.ContentItem, candidate.item_id)
        if item: item.approved_version = None
    await audit(db, request, 'content.candidate_review', 'news_candidate', candidate.id,
        after={'title': candidate.title, 'action': body.action, 'note': body.note.strip()})
    await db.flush(); await db.refresh(candidate)
    await db.commit()
    return candidate_out(candidate)


class DraftIn(BaseModel):
    title: str = Field(min_length=3, max_length=160)
    body: str = Field(min_length=10, max_length=4000)
    tags: list[str] = Field(default_factory=list, max_length=10)


@router.post('/candidates/{candidate_id}/draft', response_model=ContentItemOut, status_code=201)
async def make_draft(candidate_id: UUID, body: DraftIn, request: Request, db: Db,
                      admin: models.AdminUser = require('content', write=True)):
    candidate = await get_candidate(db, candidate_id)
    if candidate.item_id:
        raise conflict('DRAFT_EXISTS', 'Esta noticia ya tiene un borrador; edítalo desde contenido.')
    if candidate.status == 'discarded': raise conflict('CANDIDATE_DISCARDED', 'Revisa el descarte antes de crear un borrador.')
    item = models.ContentItem(type='news', title=body.title, body=body.body, tags=body.tags,
        created_by=admin.id, created_by_name=admin.full_name, source_candidate_id=candidate.id,
        provenance={'source': candidate.source, 'url': candidate.source_url, 'author': candidate.author,
                    'rights_verified': False, 'changes': 'Adaptación pendiente de revisión'})
    db.add(item); await db.flush(); await db.refresh(item)
    candidate.item_id = item.id; candidate.status = 'drafted'
    if not candidate.adaptation:
        candidate.adaptation = {'title': body.title, 'body': body.body, 'classification': 'Adaptación manual',
            'changes': 'Texto adaptado manualmente para revisión.', 'unsuitable': False,
            'original_text': candidate.original_text, 'original_title': candidate.title, 'source_hash': candidate.source_hash}
    await queue_audio(db, item)
    await audit(db, request, 'content.create', 'content_item', item.id, after={'title': item.title, 'source': candidate.source})
    return await _saved(db, item)

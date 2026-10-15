"""Invariantes de edición/publicación compartidas con el trabajador."""
from pathlib import Path
from fastapi import Request
from app import models
from app.audit import audit
from app.config import get_settings
from app.errors import conflict
from app.security import now_utc


def current_audio(item):
    return bool(item.tts_ready and item.audio_version == item.text_version and item.audio_file
                and (Path(get_settings().content_audio_dir) / item.audio_file).is_file())


def editorial_ready(item):
    return item.approved_version == item.text_version and bool(item.provenance is None or item.provenance.get('rights_verified'))


def invalidate(item):
    item.text_version += 1
    item.tts_ready = False
    item.audio_status = 'pending'
    item.audio_error = None
    item.audio_version = None
    item.audio_file = None
    item.approved_version = None
    item.reviewed_at = None
    item.reviewed_by = None
    item.reviewed_by_name = None


async def queue_audio(db, item, retry=False):
    item.audio_status = 'queued'
    item.audio_error = None
    db.add(models.ContentJob(kind='tts_retry' if retry else 'tts', target_id=item.id, version=item.text_version))


def check_publish(item):
    if item.status == 'published':
        raise conflict('ALREADY_PUBLISHED', 'El contenido ya está publicado.')
    if not editorial_ready(item):
        raise conflict('REVIEW_REQUIRED', 'Revisa y aprueba el texto vigente y su procedencia antes de publicar.')
    if not current_audio(item):
        raise conflict('TTS_PENDING', 'El audio vigente todavía no está disponible.')


async def publish(db, item, request=None):
    check_publish(item)
    item.status = 'published'
    item.published_at = now_utc()
    item.publish_at = None
    if request is None:
        request = Request({'type': 'http', 'method': 'POST', 'path': '/', 'headers': [], 'client': None})
        db.add(models.AuditLog(actor_id=item.reviewed_by, actor_name=item.reviewed_by_name,
            action='content.publish', entity_type='content_item', entity_id=item.id,
            after={'title': item.title, 'scheduled': True, 'text_version': item.text_version}))
    else:
        await audit(db, request, 'content.publish', 'content_item', item.id,
                    after={'title': item.title, 'text_version': item.text_version})

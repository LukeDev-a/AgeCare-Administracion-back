"""Invariantes de edición/publicación compartidas con el trabajador."""
from pathlib import Path
from uuid import UUID
from fastapi import Request
from app import models
from app.audit import audit
from app.config import get_settings
from app.errors import conflict
from app.security import now_utc, as_utc


def current_audio(item):
    return bool(item.tts_ready and item.audio_version == item.text_version and item.audio_file
                and (Path(get_settings().content_audio_dir) / item.audio_file).is_file())


def editorial_ready(item):
    return item.approved_version == item.text_version and bool(item.provenance is None or item.provenance.get('rights_verified'))


def scheduled_audio_authorization(item):
    value = item.schedule_audio_exception
    if not isinstance(value, dict) or not item.publish_at or not editorial_ready(item):
        return None
    reviewed_at = as_utc(item.reviewed_at).isoformat() if item.reviewed_at else None
    if (value.get('version') != item.text_version or value.get('publish_at') != as_utc(item.publish_at).isoformat()
            or value.get('reviewed_at') != reviewed_at or value.get('review_confirmed') is not True
            or not isinstance(value.get('reason'), str) or not 5 <= len(value['reason']) <= 500):
        return None
    try:
        UUID(value['actor_id'])
    except (KeyError, TypeError, ValueError, AttributeError):
        return None
    return value


def invalidate(item):
    item.schedule_audio_exception = None
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


def check_publish(item, *, without_audio=False, authorized_schedule=False):
    if item.status == 'published':
        raise conflict('ALREADY_PUBLISHED', 'El contenido ya está publicado.')
    if not editorial_ready(item):
        raise conflict('REVIEW_REQUIRED', 'Revisa y aprueba el texto vigente y su procedencia antes de publicar.')
    if without_audio:
        if current_audio(item):
            raise conflict('AUDIO_ALREADY_AVAILABLE', 'El audio está disponible; utiliza la publicación habitual.')
        if not (authorized_schedule and scheduled_audio_authorization(item)) and (item.audio_status != 'failed' or not item.audio_error):
            raise conflict('AUDIO_EXCEPTION_UNAVAILABLE', 'La publicación sin audio requiere una generación fallida. Espera a que termine el trabajo.')
    elif not current_audio(item):
        raise conflict('TTS_PENDING', 'El audio vigente todavía no está disponible.')


async def publish(db, item, request=None, *, without_audio_reason=None):
    authorization = scheduled_audio_authorization(item) if request is None else None
    without_audio = without_audio_reason is not None or bool(authorization and not current_audio(item))
    if without_audio_reason is not None and request is None:
        raise conflict('AUDIO_EXCEPTION_UNAVAILABLE', 'La excepción sin audio requiere una publicación manual.')
    check_publish(item, without_audio=without_audio, authorized_schedule=bool(authorization))
    item.status = 'published'
    item.published_at = now_utc()
    item.publish_at = None
    item.schedule_audio_exception = None
    if request is None:
        request = Request({'type': 'http', 'method': 'POST', 'path': '/', 'headers': [], 'client': None})
        after = {'title': item.title, 'scheduled': True, 'text_version': item.text_version}
        if without_audio:
            after.update(publication_mode='text_only', reason=authorization['reason'],
                audio_error=item.audio_error, review_confirmed=True,
                initial_audio_error=authorization.get('audio_error'),
                authorized_at=authorization.get('authorized_at'))
        db.add(models.AuditLog(actor_id=UUID(authorization['actor_id']) if without_audio else item.reviewed_by,
            actor_name=authorization.get('actor_name') if without_audio else item.reviewed_by_name,
            actor_role=authorization.get('actor_role') if without_audio else None,
            action='content.publish_without_audio' if without_audio else 'content.publish',
            entity_type='content_item', entity_id=item.id, after=after))
    else:
        after = {'title': item.title, 'text_version': item.text_version}
        if without_audio:
            after.update(publication_mode='text_only', reason=without_audio_reason,
                audio_error=item.audio_error, review_confirmed=True)
        await audit(db, request, 'content.publish_without_audio' if without_audio else 'content.publish',
                    'content_item', item.id, after=after)

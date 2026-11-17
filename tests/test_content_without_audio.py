from datetime import timedelta
from uuid import UUID
import pytest
from sqlalchemy import select, update
from app import models, database, content_pipeline as pipeline
from app.config import get_settings
from app.security import now_utc

BASE = '/api/v1/admin/content'
pytestmark = pytest.mark.asyncio
REASON = 'El audio falló; se revisó el texto y se autoriza su lectura.'


async def failed_item(client, headers, state='failed', error='AUDIO_CONTENT_BLOCKED'):
    async with database._session_factory() as db:
        await db.execute(update(models.ContentJob).values(status='cancelled'))
        await db.commit()
    response = await client.post(BASE + '/items', headers=headers,
        json={'type': 'news', 'title': 'Noticia para lectura', 'body': 'Texto editorial revisado para publicar sin narración.'})
    assert response.status_code == 201
    item = response.json()
    assert (await client.post(f"{BASE}/items/{item['id']}/approve", headers=headers, json={'version': 1})).status_code == 200
    async with database._session_factory() as db:
        stored = await db.get(models.ContentItem, UUID(item['id']))
        stored.audio_status = state; stored.audio_error = error
        await db.execute(update(models.ContentJob).where(models.ContentJob.target_id == stored.id).values(status='failed'))
        await db.commit()
    return item, f"{BASE}/items/{item['id']}"


def payload(**changes):
    return {'version': 1, 'reason': REASON, 'review_confirmed': True, **changes}


async def stored_item(item):
    async with database._session_factory() as db:
        return await db.get(models.ContentItem, UUID(item['id']))


async def test_manual_exception_publishes_text_cancels_date_and_audits(client, admin_headers):
    item, url = await failed_item(client, admin_headers)
    async with database._session_factory() as db:
        stored = await db.get(models.ContentItem, UUID(item['id']))
        stored.publish_at = now_utc() + timedelta(days=1)
        await db.commit()
    assert (await client.post(url + '/publish', headers=admin_headers)).status_code == 409
    result = await client.post(url + '/publish-without-audio', headers=admin_headers, json=payload())
    assert result.status_code == 200, result.text
    assert result.json()['status'] == 'published' and result.json()['publish_at'] is None
    assert not result.json()['audio_available'] and result.json()['audio_url'] is None
    assert result.json()['published_at'] and result.json()['approved_version'] == 1
    assert (await client.get(url + '/audio', headers=admin_headers)).status_code == 409
    feed = (await client.get(BASE + '/feed', headers=admin_headers)).json()
    assert any(row['id'] == item['id'] and not row['audio_available'] for row in feed['items'])
    async with database._session_factory() as db:
        log = await db.scalar(select(models.AuditLog).where(models.AuditLog.entity_id == UUID(item['id']),
            models.AuditLog.action == 'content.publish_without_audio'))
        assert log.actor_id and log.created_at and log.after['reason'] == REASON
        assert log.after['text_version'] == 1 and log.after['review_confirmed'] is True
        assert log.after['audio_error'] == 'AUDIO_CONTENT_BLOCKED'
    assert (await client.post(url + '/publish-without-audio', headers=admin_headers, json=payload())).status_code == 409


@pytest.mark.parametrize('changes', [{'reason': '  '}, {'reason': 'corto' * 101}, {'reason': '1234'},
    {'review_confirmed': False}, {'review_confirmed': 'true'}, {'review_confirmed': 1}, {'without_audio': True}])
async def test_exception_rejects_missing_reason_or_review(client, admin_headers, changes):
    item, url = await failed_item(client, admin_headers)
    result = await client.post(url + '/publish-without-audio', headers=admin_headers, json=payload(**changes))
    assert result.status_code == 422
    assert (await stored_item(item)).status == 'draft'


@pytest.mark.parametrize('state,error', [('pending', None), ('queued', None), ('waiting_quota', 'QUOTA_REACHED'), ('failed', None)])
async def test_exception_is_not_a_shortcut_for_pending_audio(client, admin_headers, state, error):
    item, url = await failed_item(client, admin_headers, state, error)
    response = await client.post(url + '/publish-without-audio', headers=admin_headers, json=payload())
    assert response.status_code == 409 and response.json()['error']['code'] == 'AUDIO_EXCEPTION_UNAVAILABLE'


async def test_exception_keeps_version_approval_rights_and_permissions_checks(client, admin_headers, analyst_headers):
    item, url = await failed_item(client, admin_headers)
    response = await client.post(url + '/publish-without-audio', headers=analyst_headers, json=payload())
    assert response.status_code == 403
    response = await client.post(url + '/publish-without-audio', headers=admin_headers, json=payload(version=2))
    assert response.status_code == 409 and response.json()['error']['code'] == 'VERSION_CONFLICT'
    async with database._session_factory() as db:
        stored = await db.get(models.ContentItem, UUID(item['id']))
        stored.provenance = {'rights_verified': False}
        await db.commit()
    response = await client.post(url + '/publish-without-audio', headers=admin_headers, json=payload())
    assert response.status_code == 409 and response.json()['error']['code'] == 'REVIEW_REQUIRED'
    await client.patch(url, headers=admin_headers, json={'body': 'Un texto diferente que debe revisarse y aprobarse nuevamente.'})
    response = await client.post(url + '/publish-without-audio', headers=admin_headers, json=payload(version=2))
    assert response.status_code == 409


async def test_scheduler_never_applies_text_only_exception_automatically(client, admin_headers):
    item, url = await failed_item(client, admin_headers)
    async with database._session_factory() as db:
        stored = await db.get(models.ContentItem, UUID(item['id']))
        stored.publish_at = now_utc() - timedelta(minutes=1)
        await db.commit()
    await pipeline.schedule()
    result = await stored_item(item)
    assert result.status == 'draft' and result.publish_at is not None
    assert result.audio_error == 'PUBLICATION_WAITING_AUDIO'


async def test_available_audio_uses_normal_publication(client, admin_headers, monkeypatch, tmp_path):
    item, url = await failed_item(client, admin_headers)
    monkeypatch.setattr(get_settings(), 'content_audio_dir', str(tmp_path))
    (tmp_path / 'available.wav').write_bytes(b'RIFF-test')
    async with database._session_factory() as db:
        stored = await db.get(models.ContentItem, UUID(item['id']))
        stored.tts_ready = True; stored.audio_version = 1; stored.audio_file = 'available.wav'
        await db.commit()
    response = await client.post(url + '/publish-without-audio', headers=admin_headers, json=payload())
    assert response.status_code == 409 and response.json()['error']['code'] == 'AUDIO_ALREADY_AVAILABLE'
    assert (await client.post(url + '/publish', headers=admin_headers)).status_code == 200


async def test_editor_can_publish_exception_and_generate_audio_later(client, monkeypatch, tmp_path):
    login = await client.post('/api/v1/admin/auth/login', json={'email': 'editora@wellq.co.uk', 'password': 'Editora123!'})
    assert login.status_code == 200
    headers = {'Authorization': 'Bearer ' + login.json()['access_token']}
    item, url = await failed_item(client, headers)
    assert (await client.post(url + '/publish-without-audio', headers=headers, json=payload())).status_code == 200
    monkeypatch.setattr(get_settings(), 'content_audio_dir', str(tmp_path))
    async def no_quota(*args, **kwargs): return None
    async def audio(*args): return b'RIFF-test-audio'
    monkeypatch.setattr(pipeline, 'reserve_quota', no_quota)
    monkeypatch.setattr(pipeline, 'narrate', audio)
    assert (await client.post(url + '/audio/retry', headers=headers)).status_code == 200
    assert await pipeline.process_one()
    result = await stored_item(item)
    assert result.status == 'published' and result.tts_ready is True
    assert (await client.get(url + '/audio', headers=headers)).status_code == 200

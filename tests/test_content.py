from datetime import timedelta
from uuid import UUID, uuid4
from pathlib import Path
import pytest
from sqlalchemy import select, update
from app import models, database, content_pipeline as pipeline
from app.config import get_settings
from app.security import now_utc, hash_password
from app.content_providers import ProviderError, plain_text

BASE = '/api/v1/admin/content'
pytestmark = pytest.mark.asyncio


async def create(client, headers, **extra):
    result = await client.post(f'{BASE}/items', headers=headers, json={
        'type': 'news', 'title': 'Una noticia de prueba', 'body': 'Texto editorial de prueba sin datos privados.', 'tags': [], **extra})
    assert result.status_code == 201, result.text
    return result.json()


async def isolate_jobs():
    async with database._session_factory() as db:
        await db.execute(update(models.ContentJob).values(status='cancelled'))
        await db.commit()


async def test_content_permissions_deletion_and_pagination(client, admin_headers, analyst_headers):
    async with database._session_factory() as db:
        editor = models.AdminUser(full_name='Editor de contenido', email=f'{uuid4()}@wellq.co.uk',
            role='editor', is_active=True, password_hash=hash_password('Prueba123!'))
        db.add(editor); await db.commit(); email = editor.email
    login = (await client.post('/api/v1/admin/auth/login', json={'email': email, 'password': 'Prueba123!'})).json()
    headers = {'Authorization': f"Bearer {login['access_token']}"}
    item = await create(client, headers)
    assert not item['audio_available'] and item['audio_status'] == 'queued'
    assert (await client.delete(f"{BASE}/items/{item['id']}", headers=headers)).status_code == 403
    assert (await client.get(f'{BASE}/items', headers=analyst_headers)).status_code == 403
    assert (await client.get(f'{BASE}/candidates')).status_code == 401
    assert (await client.delete(f"{BASE}/items/{item['id']}", headers=admin_headers)).status_code == 204
    async with database._session_factory() as db:
        assert (await db.get(models.ContentItem, UUID(item['id']))).deleted_at is not None


async def test_schedule_validation_and_null_cancellation(client, admin_headers):
    future = (now_utc() + timedelta(days=1)).isoformat()
    item = await create(client, admin_headers, publish_at=future)
    url = f"{BASE}/items/{item['id']}"
    response = await client.patch(url, headers=admin_headers, json={'publish_at': None})
    assert response.status_code == 200 and response.json()['publish_at'] is None
    assert response.json()['body'] == item['body']
    assert (await client.patch(url, headers=admin_headers, json={'body': None})).status_code == 422
    assert (await client.patch(url, headers=admin_headers, json={'publish_at': '2020-01-01T00:00:00'})).status_code == 422
    assert (await client.post(f'{BASE}/items', headers=admin_headers, json={'type': 'news', 'title': '   ', 'body': ' ' * 20})).status_code == 422


async def test_audio_approval_publication_edit_and_retirement(client, admin_headers, monkeypatch, tmp_path):
    await isolate_jobs()
    monkeypatch.setattr(get_settings(), 'content_audio_dir', str(tmp_path))
    async def no_quota(*args, **kwargs): return None
    async def audio(text): return b'RIFF-test-audio'
    monkeypatch.setattr(pipeline, 'reserve_quota', no_quota)
    monkeypatch.setattr(pipeline, 'narrate', audio)
    item = await create(client, admin_headers)
    url = f"{BASE}/items/{item['id']}"
    assert (await client.post(url + '/publish', headers=admin_headers)).json()['error']['code'] == 'REVIEW_REQUIRED'
    assert (await client.post(url + '/approve', headers=admin_headers, json={'version': 1})).status_code == 200
    assert await pipeline.process_one()
    await pipeline.process_one()  # Job duplicado no consume otra generación.
    published = await client.post(url + '/publish', headers=admin_headers)
    assert published.status_code == 200, published.text
    assert (await client.get(url + '/audio', headers=admin_headers)).content == b'RIFF-test-audio'
    assert (await client.delete(url, headers=admin_headers)).status_code == 409
    assert (await client.post(url + '/publish', headers=admin_headers)).json()['error']['code'] == 'ALREADY_PUBLISHED'
    changed = await client.patch(url, headers=admin_headers, json={'body': 'Texto nuevo que obliga a invalidar audio.'})
    assert changed.status_code == 200 and not changed.json()['audio_available']
    assert changed.json()['approved_version'] is None
    assert (await client.get(url + '/audio', headers=admin_headers)).status_code == 409
    feed = (await client.get(f'{BASE}/feed', headers=admin_headers)).json()
    assert item['id'] not in {row['id'] for row in feed['items']}
    assert (await client.post(url + '/unpublish', headers=admin_headers)).json()['status'] == 'archived'
    assert (await client.delete(url, headers=admin_headers)).status_code == 204


async def test_collection_keeps_twenty_and_deduplicates(client, admin_headers, monkeypatch):
    await isolate_jobs()
    start = int(uuid4().int % 1000000000)
    posts = [{'id': start + i, 'title': {'rendered': f'Noticia propia {i}'}, 'content': {'rendered': '<p>Original &amp; contexto.</p><script>secreto</script>'},
        'link': f'https://www.cuentamealgobueno.com/prueba-{start}-{i}/', 'modified_gmt': '2026-10-14T09:00:00',
        'date_gmt': '2026-10-14T08:00:00', '_embedded': {'author': [{'name': 'Medio'}]}} for i in range(20)]
    async def source(params): return posts
    monkeypatch.setattr(pipeline, 'fetch_posts', source)
    async with database._session_factory() as db:
        row = await pipeline.control(db, 'collection'); row.data = {}; await db.commit()
    assert (await client.post(f'{BASE}/collect', headers=admin_headers)).status_code == 202
    assert await pipeline.process_one()
    async with database._session_factory() as db:
        rows = (await db.scalars(select(models.NewsCandidate).where(models.NewsCandidate.external_id.between(start, start + 19)))).all()
        assert len(rows) == 20 and all('secreto' not in row.original_text for row in rows)
        assert sum(row.status == 'queued' for row in rows) == 5
        await db.execute(update(models.ContentJob).where(models.ContentJob.kind == 'adapt').values(status='cancelled'))
        await db.commit()
    assert (await client.post(f'{BASE}/collect', headers=admin_headers)).status_code == 202
    assert await pipeline.process_one()
    async with database._session_factory() as db:
        rows = (await db.scalars(select(models.NewsCandidate).where(models.NewsCandidate.external_id.between(start, start + 19)))).all()
        assert len(rows) == 20


async def test_candidate_rights_required_and_manual_draft_preserved(client, admin_headers):
    async with database._session_factory() as db:
        candidate = models.NewsCandidate(source='cuentamealgobueno', external_id=int(uuid4().int % 1000000000),
            title='Texto de origen', original_text='Original conservado para comparar.', source_url='https://www.cuentamealgobueno.com/prueba/', source_hash='hash')
        db.add(candidate); await db.commit(); candidate_id = str(candidate.id)
    drafted = await client.post(f'{BASE}/candidates/{candidate_id}/draft', headers=admin_headers,
        json={'title': 'Adaptación manual', 'body': 'Texto propio adaptado manualmente sin Gemini.'})
    assert drafted.status_code == 201
    url = f"{BASE}/items/{drafted.json()['id']}"
    assert (await client.post(url + '/approve', headers=admin_headers, json={'version': 1})).status_code == 409
    review = await client.post(f'{BASE}/candidates/{candidate_id}/review', headers=admin_headers, json={'action': 'own', 'source_hash': 'hash', 'note': 'Revisado origen y licencia del texto propio.'})
    assert review.status_code == 200
    approved = await client.post(url + '/approve', headers=admin_headers, json={'version': 1})
    assert approved.status_code == 200 and approved.json()['provenance']['license'] == 'CC BY-SA 4.0'
    assert (await client.post(f'{BASE}/candidates/{candidate_id}/draft', headers=admin_headers, json={'title': 'Duplicado', 'body': 'Texto duplicado no permitido.'})).status_code == 409


async def test_quota_failure_keeps_candidate_and_pending_job(client, admin_headers, monkeypatch):
    await isolate_jobs()
    async def no_quota(*args, **kwargs): return None
    async def exhausted(*args): raise ProviderError('QUOTA_REACHED')
    monkeypatch.setattr(pipeline, 'reserve_quota', no_quota)
    monkeypatch.setattr(pipeline, 'adapt_news', exhausted)
    async with database._session_factory() as db:
        candidate = models.NewsCandidate(source='cuentamealgobueno', external_id=int(uuid4().int % 1000000000),
            title='Candidato conservado', original_text='Original no se pierde al agotar cuota.', source_url='https://www.cuentamealgobueno.com/cuota/', source_hash='hash')
        db.add(candidate); await db.flush()
        candidate_id = candidate.id
        db.add(models.ContentJob(kind='adapt', target_id=candidate.id)); await db.commit()
    assert await pipeline.process_one()
    async with database._session_factory() as db:
        stored = await db.get(models.NewsCandidate, candidate_id)
        assert stored.status == 'waiting_quota' and stored.original_text.startswith('Original no se pierde')
        job = await db.scalar(select(models.ContentJob).where(models.ContentJob.target_id == candidate_id))
        assert job.status == 'waiting_quota' and job.error == 'QUOTA_REACHED'


async def test_local_quota_survives_calls_and_preserves_retry_budget(client, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, 'gemini_api_key', 'test-only')
    monkeypatch.setattr(settings, 'gemini_free_tier_confirmed', True)
    monkeypatch.setattr(settings, 'gemini_tts_rpm', 100)
    async with database._session_factory() as db:
        row = await pipeline.control(db, 'quota_tts'); row.data = {}; await db.commit()
    for _ in range(5): assert await pipeline.reserve_quota('tts') is None
    assert await pipeline.reserve_quota('tts') is not None
    for _ in range(5): assert await pipeline.reserve_quota('tts', retry=True) is None
    assert await pipeline.reserve_quota('tts', retry=True) is not None


async def test_scheduler_waits_for_current_audio(client, admin_headers, monkeypatch, tmp_path):
    monkeypatch.setattr(get_settings(), 'content_audio_dir', str(tmp_path))
    item = await create(client, admin_headers)
    item_id = UUID(item['id'])
    await client.post(f'{BASE}/items/{item_id}/approve', headers=admin_headers, json={'version': 1})
    async with database._session_factory() as db:
        stored = await db.get(models.ContentItem, item_id); stored.publish_at = now_utc() - timedelta(minutes=1)
        await db.commit()
    await pipeline.schedule()
    async with database._session_factory() as db:
        stored = await db.get(models.ContentItem, item_id)
        assert stored.status == 'draft' and stored.audio_error == 'PUBLICATION_WAITING_AUDIO'
        (tmp_path / 'current.wav').write_bytes(b'audio')
        stored.audio_file = 'current.wav'; stored.audio_version = stored.text_version; stored.tts_ready = True
        await db.commit()
    await pipeline.schedule()
    async with database._session_factory() as db:
        stored = await db.get(models.ContentItem, item_id)
        assert stored.status == 'published' and stored.published_at is not None


async def test_stale_approval_is_rejected_and_old_audio_job_cancelled(client, admin_headers):
    await isolate_jobs()
    item = await create(client, admin_headers)
    url = f"{BASE}/items/{item['id']}"
    changed = await client.patch(url, headers=admin_headers, json={'title': 'Título cambiado por otro editor'})
    assert changed.json()['text_version'] == 2
    response = await client.post(url + '/approve', headers=admin_headers, json={'version': 1})
    assert response.status_code == 409 and response.json()['error']['code'] == 'VERSION_CONFLICT'
    assert await pipeline.process_one()
    async with database._session_factory() as db:
        old = await db.scalar(select(models.ContentJob).where(models.ContentJob.target_id == UUID(item['id']), models.ContentJob.version == 1))
        assert old.status == 'cancelled'


async def test_tts_failure_preserves_text_and_allows_controlled_retry(client, admin_headers, monkeypatch):
    await isolate_jobs()
    async def no_quota(*args, **kwargs): return None
    async def fail(*args): raise ProviderError('INVALID_AUDIO_OUTPUT')
    monkeypatch.setattr(pipeline, 'reserve_quota', no_quota)
    monkeypatch.setattr(pipeline, 'narrate', fail)
    item = await create(client, admin_headers)
    url = f"{BASE}/items/{item['id']}"
    await client.post(url + '/approve', headers=admin_headers, json={'version': 1})
    for _ in range(3):
        async with database._session_factory() as db:
            await db.execute(update(models.ContentJob).where(models.ContentJob.target_id == UUID(item['id'])).values(available_at=now_utc() - timedelta(seconds=1)))
            await db.commit()
        await pipeline.process_one()
    async with database._session_factory() as db:
        stored = await db.get(models.ContentItem, UUID(item['id']))
        assert stored.body == item['body'] and not stored.tts_ready
        await db.execute(update(models.ContentJob).where(models.ContentJob.target_id == stored.id).values(status='failed'))
        stored.audio_status = 'failed'; await db.commit()
    retried = await client.post(url + '/audio/retry', headers=admin_headers)
    assert retried.status_code == 200 and retried.json()['audio_status'] == 'queued'


async def test_collection_failure_does_not_remove_editorial_work(client, admin_headers, monkeypatch):
    await isolate_jobs()
    item = await create(client, admin_headers)
    await isolate_jobs()
    async def unavailable(params): raise ProviderError('PROVIDER_UNAVAILABLE')
    monkeypatch.setattr(pipeline, 'fetch_posts', unavailable)
    await client.post(f'{BASE}/collect', headers=admin_headers)
    await pipeline.process_one()
    async with database._session_factory() as db:
        stored = await db.get(models.ContentItem, UUID(item['id']))
        assert stored.body == item['body'] and stored.deleted_at is None
        job = await db.scalar(select(models.ContentJob).where(models.ContentJob.kind == 'collect', models.ContentJob.status == 'queued'))
        assert job.error == 'PROVIDER_UNAVAILABLE' and job.result is None

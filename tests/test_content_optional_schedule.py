import importlib.util
from datetime import timedelta
from pathlib import Path
from uuid import UUID
import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import select
from app import models, database, content_pipeline as pipeline, content_editorial as editorial
from app.config import get_settings
from app.security import now_utc
from test_content_without_audio import failed_item, payload, stored_item


async def authorize(client, headers, url, **changes):
    return await client.post(url + '/schedule-without-audio', headers=headers,
        json=payload(publish_at=(now_utc() + timedelta(minutes=5)).isoformat(), **changes))


@pytest.mark.asyncio
async def test_authorized_schedule_survives_sessions_and_publishes_without_audio_at_date(client, admin_headers, monkeypatch):
    item, url = await failed_item(client, admin_headers)
    response = await authorize(client, admin_headers, url)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result['scheduled_without_audio'] and result['status'] == 'draft'
    assert result['scheduled_audio_exception_reason'] == payload()['reason']
    stored = await stored_item(item)  # Nueva sesión: autorización durable.
    assert stored.schedule_audio_exception['actor_id'] and stored.schedule_audio_exception['version'] == 1
    await pipeline.schedule()
    assert (await stored_item(item)).status == 'draft'
    due = editorial.as_utc(stored.publish_at) + timedelta(seconds=1)
    monkeypatch.setattr(pipeline, 'now_utc', lambda: due)
    monkeypatch.setattr(editorial, 'now_utc', lambda: due)
    await pipeline.schedule(); await pipeline.schedule()  # No duplicar publicación.
    saved = await stored_item(item)
    assert saved.status == 'published' and not saved.tts_ready
    assert saved.publish_at is None and saved.schedule_audio_exception is None
    async with database._session_factory() as db:
        events = (await db.scalars(select(models.AuditLog).where(models.AuditLog.entity_id == UUID(item['id']),
            models.AuditLog.action == 'content.publish_without_audio'))).all()
        assert len(events) == 1 and events[0].after['scheduled'] is True
        assert events[0].after['reason'] == payload()['reason']
        assert str(events[0].actor_id) == stored.schedule_audio_exception['actor_id']
        assert await db.scalar(select(models.AuditLog).where(models.AuditLog.entity_id == UUID(item['id']),
            models.AuditLog.action == 'content.schedule_without_audio')) is not None


@pytest.mark.asyncio
async def test_optional_schedule_includes_audio_if_it_becomes_ready(client, admin_headers, monkeypatch, tmp_path):
    item, url = await failed_item(client, admin_headers)
    assert (await authorize(client, admin_headers, url)).status_code == 200
    monkeypatch.setattr(get_settings(), 'content_audio_dir', str(tmp_path))
    (tmp_path / 'ready.wav').write_bytes(b'RIFF-test')
    async with database._session_factory() as db:
        stored = await db.get(models.ContentItem, UUID(item['id']))
        stored.audio_file = 'ready.wav'; stored.audio_version = 1; stored.tts_ready = True; stored.audio_status = 'ready'
        due = editorial.as_utc(stored.publish_at) + timedelta(seconds=1)
        await db.commit()
    monkeypatch.setattr(pipeline, 'now_utc', lambda: due)
    monkeypatch.setattr(editorial, 'now_utc', lambda: due)
    await pipeline.schedule()
    assert (await stored_item(item)).status == 'published'

    assert (await client.get(url + '/audio', headers=admin_headers)).status_code == 200
    async with database._session_factory() as db:
        event = await db.scalar(select(models.AuditLog).where(models.AuditLog.entity_id == UUID(item['id']),
            models.AuditLog.action == 'content.publish'))
        assert event and event.after['scheduled'] is True


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['cancel', 'text', 'approval', 'date'])
async def test_authorization_is_revoked_or_invalidated_when_schedule_or_version_changes(client, admin_headers, change):
    item, url = await failed_item(client, admin_headers)
    assert (await authorize(client, admin_headers, url)).status_code == 200
    if change == 'cancel':
        response = await client.patch(url, headers=admin_headers, json={'publish_at': None})
        assert response.status_code == 200 and not response.json()['scheduled_without_audio']
    elif change == 'text':
        response = await client.patch(url, headers=admin_headers, json={'body': 'Un texto nuevo que necesita otra revisión y aprobación.'})
        assert response.status_code == 200 and not response.json()['scheduled_without_audio']
        assert response.json()['publish_at'] is not None and response.json()['approved_version'] is None
    elif change == 'approval':
        response = await client.post(url + '/approve', headers=admin_headers, json={'version': 1})
        assert response.status_code == 200 and not response.json()['scheduled_without_audio']
    else:
        async with database._session_factory() as db:
            stored = await db.get(models.ContentItem, UUID(item['id']))
            stored.publish_at += timedelta(minutes=10)
            await db.commit()
    assert editorial.scheduled_audio_authorization(await stored_item(item)) is None


@pytest.mark.asyncio
async def test_explicit_schedule_can_continue_while_audio_is_retried(client, admin_headers, monkeypatch):
    item, url = await failed_item(client, admin_headers)
    assert (await authorize(client, admin_headers, url)).status_code == 200
    assert (await client.post(url + '/audio/retry', headers=admin_headers)).status_code == 200
    saved = await stored_item(item)
    assert saved.audio_status == 'queued'
    due = editorial.as_utc(saved.publish_at) + timedelta(seconds=1)
    monkeypatch.setattr(pipeline, 'now_utc', lambda: due)
    monkeypatch.setattr(editorial, 'now_utc', lambda: due)
    await pipeline.schedule()
    assert (await stored_item(item)).status == 'published'


    async with database._session_factory() as db:
        event = await db.scalar(select(models.AuditLog).where(models.AuditLog.entity_id == UUID(item['id']),
            models.AuditLog.action == 'content.publish_without_audio'))
        assert event.after['initial_audio_error'] == 'AUDIO_CONTENT_BLOCKED'


@pytest.mark.asyncio
async def test_schedule_exception_rejects_past_version_permissions_or_missing_review(client, admin_headers, analyst_headers):
    item, url = await failed_item(client, admin_headers)
    for data in [payload(publish_at=(now_utc() - timedelta(minutes=1)).isoformat()),
        payload(publish_at=None), payload(publish_at=(now_utc() + timedelta(minutes=5)).isoformat(), review_confirmed=False),
        payload(publish_at=(now_utc() + timedelta(minutes=5)).isoformat(), reason='    ')]:
        assert (await client.post(url + '/schedule-without-audio', headers=admin_headers, json=data)).status_code == 422
    assert (await authorize(client, analyst_headers, url)).status_code == 403
    assert (await authorize(client, admin_headers, url, version=2)).status_code == 409
    assert (await stored_item(item)).schedule_audio_exception is None


@pytest.mark.asyncio
async def test_ordinary_schedule_is_not_silently_converted_to_optional_audio(client, admin_headers):
    item, url = await failed_item(client, admin_headers)
    assert (await client.patch(url, headers=admin_headers,
        json={'publish_at': (now_utc() + timedelta(minutes=5)).isoformat()})).status_code == 409
    assert (await stored_item(item)).schedule_audio_exception is None


@pytest.mark.parametrize('new_database', [False, True])
def test_migration_0018_preserves_existing_items_and_is_idempotent(new_database):
    engine = sa.create_engine('sqlite://')
    with engine.begin() as db:
        if new_database:
            database.Base.metadata.create_all(db)
        else:
            db.execute(sa.text('CREATE TABLE content_items (id TEXT PRIMARY KEY, title TEXT)'))
            db.execute(sa.text("INSERT INTO content_items VALUES ('preserved', 'Conservado')"))
        path = Path(__file__).resolve().parents[1] / 'alembic/versions/0018_scheduled_text_only.py'
        spec = importlib.util.spec_from_file_location('optional_schedule_migration', path)
        migration = importlib.util.module_from_spec(spec); spec.loader.exec_module(migration)
        migration.op = Operations(MigrationContext.configure(db))
        migration.upgrade(); migration.upgrade()
        assert 'schedule_audio_exception' in {column['name'] for column in sa.inspect(db).get_columns('content_items')}
        if not new_database:
            assert db.execute(sa.text('SELECT title,schedule_audio_exception FROM content_items')).one() == ('Conservado', None)
    engine.dispose()

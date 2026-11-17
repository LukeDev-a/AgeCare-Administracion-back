"""Cuotas por modelo y continuidad del audio, solo con SQLite/proveedor simulado."""
import io
import wave
from types import SimpleNamespace
from uuid import UUID
import pytest
import pytest_asyncio
from sqlalchemy import delete, select
from app import models, database, content_pipeline as pipeline
from app.config import get_settings
from app.content_audio import split_audio_text
from app.content_providers import ProviderError, tts_models

PRIMARY = 'gemini-3.1-flash-tts-preview'
LITE = 'gemini-3.8-flash-lite-tts'
FLASH = 'gemini-3.8-flash-tts'
BASE = '/api/v1/admin/content/items'
pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture(autouse=True)
async def isolated_quotas(client, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, 'gemini_api_key', 'not-a-real-key')
    monkeypatch.setattr(settings, 'gemini_free_tier_confirmed', True)
    monkeypatch.setattr(settings, 'gemini_tts_model', PRIMARY)
    monkeypatch.setattr(settings, 'gemini_tts_fallback_models', f'{LITE},{FLASH}')
    monkeypatch.setattr(settings, 'gemini_tts_rpm', 3)
    monkeypatch.setattr(settings, 'gemini_tts_daily_limit', 10)
    monkeypatch.setattr(settings, 'content_new_audio_daily_limit', 5)
    async with database._session_factory() as db:
        await db.execute(delete(models.ContentControl).where(models.ContentControl.key.startswith('quota_tts')))
        await db.commit()


def wav():
    output = io.BytesIO()
    with wave.open(output, 'wb') as stream:
        stream.setnchannels(1); stream.setsampwidth(2); stream.setframerate(24000)
        stream.writeframes(b'\x03\x00' * 24)
    return output.getvalue()


async def test_legacy_consumption_is_kept_and_new_models_have_separate_quotas():
    async with database._session_factory() as db:
        row = await pipeline.control(db, 'quota_tts')
        row.data = {'day': pipeline.provider_day(), 'count': 10, 'new_audio': 4}
        await db.commit()
    assert await pipeline.reserve_quota('tts', retry=True, model=PRIMARY) is not None
    assert await pipeline.reserve_quota('tts', retry=True, model=LITE) is None
    assert await pipeline.reserve_quota('tts', retry=True, model=PRIMARY) is not None
    async with database._session_factory() as db:
        old = await db.get(models.ContentControl, 'quota_tts')
        new = await db.get(models.ContentControl, 'quota_tts_' + LITE)
        assert old.data['new_audio'] == 4 and old.data['legacy_model'] == PRIMARY
        assert new.data['count'] == 1


async def test_provider_quota_blocks_only_that_model():
    assert await pipeline.reserve_quota('tts', retry=True, model=PRIMARY) is None
    await pipeline.block_quota('tts', model=PRIMARY)
    assert await pipeline.reserve_quota('tts', retry=True, model=PRIMARY) is not None
    assert await pipeline.reserve_quota('tts', retry=True, model=FLASH) is None


async def test_new_article_limit_is_shared_but_continuation_can_finish():
    async with database._session_factory() as db:
        row = await pipeline.control(db, 'quota_tts')
        row.data = {'day': pipeline.provider_day(), 'new_audio': 5}
        await db.commit()
    for model in (PRIMARY, LITE, FLASH):
        assert await pipeline.reserve_quota('tts', model=model) is not None
    assert await pipeline.reserve_quota('tts', retry=True, model=LITE) is None


async def test_rpm_and_daily_limits_are_independent_per_model():
    for _ in range(3):
        assert await pipeline.reserve_quota('tts', retry=True, model=LITE) is None
    assert await pipeline.reserve_quota('tts', retry=True, model=LITE) is not None
    assert await pipeline.reserve_quota('tts', retry=True, model=FLASH) is None


@pytest.mark.parametrize('code', ['PROVIDER_UNAVAILABLE', 'INVALID_AUDIO_OUTPUT', 'QUOTA_REACHED'])
async def test_failed_chunk_uses_backup_without_counting_another_article(monkeypatch, code):
    calls = []
    async def narrate(text, model):
        calls.append((text, model))
        if model == PRIMARY:
            raise ProviderError(code)
        return wav()
    monkeypatch.setattr(pipeline, 'narrate', narrate)
    job = SimpleNamespace(result=None)
    audio, wait = await pipeline.narrate_with_fallback(job, 'Texto pendiente.', retry=False)
    assert audio == wav() and wait is None
    assert calls == [('Texto pendiente.', PRIMARY), ('Texto pendiente.', LITE)]
    assert job.result['tts_current_model'] == LITE
    async with database._session_factory() as db:
        row = await db.get(models.ContentControl, 'quota_tts')
        assert row.data['new_audio'] == 1


async def test_safety_block_never_switches_to_backup(monkeypatch):
    calls = []
    async def narrate(text, model):
        calls.append(model)
        raise ProviderError('AUDIO_CONTENT_BLOCKED')
    monkeypatch.setattr(pipeline, 'narrate', narrate)
    with pytest.raises(ProviderError, match='AUDIO_CONTENT_BLOCKED'):
        await pipeline.narrate_with_fallback(SimpleNamespace(result=None), 'Texto', retry=False)
    assert calls == [PRIMARY]


async def test_all_exhausted_models_wait_without_calling_provider(monkeypatch):
    for model in tts_models():
        await pipeline.block_quota('tts', model=model)
    async def forbidden(*args): raise AssertionError('No debe llamar sin cuota')
    monkeypatch.setattr(pipeline, 'narrate', forbidden)
    audio, wait = await pipeline.narrate_with_fallback(SimpleNamespace(result=None), 'Texto', retry=True)
    assert audio is None and wait == pipeline.next_provider_day()


async def test_model_change_mid_article_keeps_previous_chunk(client, admin_headers, monkeypatch, tmp_path):
    monkeypatch.setattr(get_settings(), 'content_audio_dir', str(tmp_path))
    async with database._session_factory() as db:
        for job in (await db.scalars(select(models.ContentJob))).all():
            job.status = 'cancelled'
        await db.commit()
    body = '\n\n'.join(f'Párrafo {index}: ' + 'Relato tranquilo del barrio. ' * 7 for index in range(14))
    response = await client.post(BASE, headers=admin_headers,
        json={'type': 'news', 'title': 'Noticia con respaldo', 'body': body, 'tags': []})
    assert response.status_code == 201
    item = response.json(); url = f"{BASE}/{item['id']}"
    expected = split_audio_text(item['title'] + '\n\n' + item['body'])
    calls = []
    async def reserve(*args, **kwargs): return None
    async def narrate(text, model):
        calls.append((text, model))
        if text == expected[1] and model == PRIMARY:
            raise ProviderError('INVALID_AUDIO_OUTPUT')
        return wav()
    monkeypatch.setattr(pipeline, 'reserve_quota', reserve)
    monkeypatch.setattr(pipeline, 'narrate', narrate)
    assert (await client.post(url + '/approve', headers=admin_headers, json={'version': 1})).status_code == 200
    for _ in expected:
        assert await pipeline.process_one()
    assert calls == [(expected[0], PRIMARY), (expected[1], PRIMARY)] + [(part, LITE) for part in expected[1:]]
    response = await client.get(url + '/audio', headers=admin_headers)
    assert response.status_code == 200
    with wave.open(io.BytesIO(response.content)) as stream:
        assert stream.getnframes() == len(expected) * 24
    async with database._session_factory() as db:
        job = await db.scalar(select(models.ContentJob).where(models.ContentJob.target_id == UUID(item['id'])))
        assert job.status == 'done'
        assert job.result['tts_models_used'] == [PRIMARY] + [LITE] * (len(expected) - 1)


async def test_unknown_model_is_rejected_before_reserving_quota(monkeypatch):
    monkeypatch.setattr(get_settings(), 'gemini_tts_fallback_models', 'not-authorized-model')
    with pytest.raises(ProviderError, match='PROVIDER_CONFIG_ERROR'):
        await pipeline.reserve_quota('tts', retry=True, model=PRIMARY)

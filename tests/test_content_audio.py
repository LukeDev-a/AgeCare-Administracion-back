import io
import wave
from datetime import timedelta
from uuid import UUID
import pytest
from sqlalchemy import select
from app import models, database, content_pipeline as pipeline
from app.config import get_settings
from app.security import now_utc
from app.content_audio import split_audio_text, join_audio
from app.content_providers import ProviderError

BASE = '/api/v1/admin/content/items'


def wav(rate=24000):
    output = io.BytesIO()
    with wave.open(output, 'wb') as stream:
        stream.setnchannels(1); stream.setsampwidth(2); stream.setframerate(rate)
        stream.writeframes(b'\x01\x00' * 24)
    return output.getvalue()


def test_split_preserves_all_words_in_order_and_bounds_requests():
    text = '\n\n'.join(f'Párrafo {i}: ' + 'lectura tranquila. ' * 15 for i in range(13))
    parts = split_audio_text(text)
    assert len(parts) > 1 and all(0 < len(part) <= 1200 for part in parts)
    assert ' '.join(text.split()) == ' '.join(' '.join(parts).split())
    assert split_audio_text('x' * 4162) == ['x' * 1200] * 3 + ['x' * 562]


def test_join_keeps_pcm_order_without_duplicate_headers():
    with wave.open(io.BytesIO(join_audio([wav(), wav()]))) as stream:
        assert stream.getnframes() == 48
        assert stream.readframes(48) == b'\x01\x00' * 48
    with pytest.raises(ProviderError, match='INVALID_AUDIO_OUTPUT'):
        join_audio([wav(), wav(16000)])
    with pytest.raises(ProviderError, match='INVALID_AUDIO_OUTPUT'):
        join_audio([b'broken'])


async def approved_long_item(client, headers):
    async with database._session_factory() as db:
        jobs = (await db.scalars(select(models.ContentJob))).all()
        for job in jobs: job.status = 'cancelled'
        await db.commit()
    body = '\n\n'.join(f'Párrafo {i}: ' + 'Lectura de una noticia del barrio. ' * 6 for i in range(15))
    item = (await client.post(BASE, headers=headers, json={'type': 'news',
        'title': 'Lectura por tramos', 'body': body, 'tags': []})).json()
    response = await client.post(f"{BASE}/{item['id']}/approve", headers=headers, json={'version': 1})
    assert response.status_code == 200, response.text
    return item


@pytest.mark.asyncio
async def test_chunks_resume_after_quota_and_only_final_audio_is_available(client, admin_headers, monkeypatch, tmp_path):
    monkeypatch.setattr(get_settings(), 'content_audio_dir', str(tmp_path))
    monkeypatch.setattr(get_settings(), 'gemini_tts_fallback_models', '')
    requests, reservations = [], []
    paused = False
    async def reserve(*args, **kwargs):
        nonlocal paused
        reservations.append(kwargs['retry'])
        if len(requests) == 1 and not paused:
            paused = True
            return now_utc() + timedelta(seconds=65)
    async def narrate(text, model=None):
        requests.append(text)
        return wav()
    monkeypatch.setattr(pipeline, 'reserve_quota', reserve)
    monkeypatch.setattr(pipeline, 'narrate', narrate)
    item = await approved_long_item(client, admin_headers)
    item_id = UUID(item['id'])
    expected = split_audio_text(item['title'] + '\n\n' + item['body'])
    assert await pipeline.process_one()
    assert await pipeline.process_one()  # Cuota: conserva el primer tramo.
    async with database._session_factory() as db:
        stored = await db.get(models.ContentItem, item_id)
        job = await db.scalar(select(models.ContentJob).where(models.ContentJob.target_id == item_id))
        assert stored.audio_status == 'waiting_quota' and not stored.tts_ready
        assert job.result['tts_progress']['completed'] == 1
        job.available_at = now_utc() - timedelta(seconds=1)
        await db.commit()
    assert (await client.get(f'{BASE}/{item_id}/audio', headers=admin_headers)).status_code == 409
    for _ in expected[1:]:
        assert await pipeline.process_one()
    assert requests == expected  # El primer tramo no se vuelve a pedir.
    assert reservations == [False] + [True] * len(expected)
    response = await client.get(f'{BASE}/{item_id}/audio', headers=admin_headers)
    assert response.status_code == 200
    with wave.open(io.BytesIO(response.content)) as stream:
        assert stream.getnframes() == 24 * len(expected)


@pytest.mark.asyncio
async def test_edit_cancels_partial_audio_without_reading_next_chunk(client, admin_headers, monkeypatch, tmp_path):
    monkeypatch.setattr(get_settings(), 'content_audio_dir', str(tmp_path))
    calls = []
    async def reserve(*args, **kwargs): return None
    async def narrate(text, model=None): calls.append(text); return wav()
    monkeypatch.setattr(pipeline, 'reserve_quota', reserve)
    monkeypatch.setattr(pipeline, 'narrate', narrate)
    item = await approved_long_item(client, admin_headers)
    assert await pipeline.process_one()
    changed = await client.patch(f"{BASE}/{item['id']}", headers=admin_headers,
        json={'body': 'Este texto cambió y requiere una nueva aprobación.'})
    assert changed.status_code == 200
    assert await pipeline.process_one()
    assert len(calls) == 1 and not changed.json()['audio_available']
    async with database._session_factory() as db:
        job = await db.scalar(select(models.ContentJob).where(models.ContentJob.target_id == UUID(item['id'])))
        assert job.status == 'cancelled'

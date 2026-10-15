"""Cola editorial durable, cuotas reservadas y ejecución diaria sin publicación IA."""
import asyncio
import hashlib
import os
from pathlib import Path
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from uuid import uuid4
from urllib.parse import urlsplit, urlunsplit
from sqlalchemy import select, case, or_
from sqlalchemy.exc import IntegrityError
from app import models
from app.config import get_settings
from app.database import get_session_factory
from app.security import as_utc, now_utc
from app.content_editorial import editorial_ready, current_audio, publish
from app.content_providers import SOURCE, ProviderError, fetch_posts, plain_text, adapt_news, narrate


async def control(db, key):
    row = await db.scalar(select(models.ContentControl).where(models.ContentControl.key == key).with_for_update())
    if row is None:
        try:
            async with db.begin_nested():
                db.add(models.ContentControl(key=key, data={}))
                await db.flush()
        except IntegrityError:
            pass
        row = await db.scalar(select(models.ContentControl).where(models.ContentControl.key == key).with_for_update())
    return row


def provider_day():
    return now_utc().astimezone(ZoneInfo('America/Los_Angeles')).date().isoformat()


def next_provider_day():
    local = now_utc().astimezone(ZoneInfo('America/Los_Angeles'))
    return (local + timedelta(days=1)).replace(hour=0, minute=1, second=0, microsecond=0).astimezone(ZoneInfo('UTC'))


async def reserve_quota(kind, retry=False, estimated_tokens=0):
    settings = get_settings()
    if not settings.gemini_api_key or not settings.gemini_free_tier_confirmed:
        raise ProviderError('GEMINI_NOT_CONFIGURED')
    key = 'quota_tts' if kind == 'tts' else 'quota_text'
    daily = settings.gemini_tts_daily_limit if kind == 'tts' else settings.gemini_text_daily_limit
    rpm = settings.gemini_tts_rpm if kind == 'tts' else settings.gemini_text_rpm
    async with get_session_factory()() as db:
        row = await control(db, key)
        data = dict(row.data or {})
        if data.get('day') != provider_day(): data = {'day': provider_day(), 'count': 0, 'new_audio': 0}
        times = [stamp for stamp in data.get('times', []) if stamp > now_utc().timestamp() - 60]
        token_times = [entry for entry in data.get('token_times', []) if entry[0] > now_utc().timestamp() - 60]
        blocked_until = data.get('blocked_until', 0)
        if blocked_until > now_utc().timestamp():
            return datetime.fromtimestamp(blocked_until, ZoneInfo('UTC'))
        if data.get('count', 0) >= daily or (kind == 'tts' and not retry and data.get('new_audio', 0) >= settings.content_new_audio_daily_limit):
            return next_provider_day()
        if len(times) >= max(1, rpm): return now_utc() + timedelta(seconds=65)
        if kind == 'text' and sum(entry[1] for entry in token_times) + estimated_tokens > settings.gemini_text_input_tpm:
            return now_utc() + timedelta(seconds=65)
        data['count'] = data.get('count', 0) + 1
        if kind == 'tts' and not retry: data['new_audio'] = data.get('new_audio', 0) + 1
        data['times'] = times + [now_utc().timestamp()]
        data['token_times'] = token_times + [[now_utc().timestamp(), estimated_tokens]]
        row.data = data
        # Cuenta el intento incluso si proceso cae después de que proveedor lo acepta.
        await db.commit()
        return None


async def block_quota(kind):
    async with get_session_factory()() as db:
        row = await control(db, 'quota_tts' if kind == 'tts' else 'quota_text')
        row.data = {**(row.data or {}), 'blocked_until': next_provider_day().timestamp()}
        await db.commit()


def parsed_date(value):
    if not value: return None
    return as_utc(datetime.fromisoformat(value.replace('Z', '+00:00')))


async def collect_source(db, job):
    row = await control(db, 'collection')
    limit = min(100, max(1, get_settings().news_collection_limit))
    cursor = (row.data or {}).get('cursor')
    params = {'per_page': min(100, limit + 1), '_embed': 'author', 'orderby': 'modified', 'order': 'asc' if cursor else 'desc'}
    if cursor:
        params['modified_after'] = (parsed_date(cursor) - timedelta(seconds=1)).isoformat()
    counts = {'candidates': 0, 'duplicates': 0, 'changed': 0, 'discarded': 0, 'pages': 0}
    latest = parsed_date(cursor) if cursor else None
    selected = []
    # Límite de red; en consultas incrementales avanza cursor solo sobre filas procesadas.
    for page in range(1, 6):
        posts = await fetch_posts({**params, 'page': page})
        if not isinstance(posts, list): raise ProviderError('INVALID_SOURCE_RESPONSE')
        counts['pages'] += 1
        for post in posts:
            if not isinstance(post, dict) or not isinstance(post.get('id'), int): raise ProviderError('INVALID_SOURCE_RESPONSE')
            title = plain_text(post.get('title', {}).get('rendered', ''))
            text = plain_text(post.get('content', {}).get('rendered', ''))
            if not title or not text:
                counts['discarded'] += 1
                continue
            url = post.get('link', '')
            if not url.startswith('https://www.cuentamealgobueno.com/'):
                counts['discarded'] += 1
                continue
            parts = urlsplit(url)
            url = urlunsplit((parts.scheme, parts.netloc.lower(), parts.path.rstrip('/') + '/', '', ''))
            stamp = parsed_date(post.get('modified_gmt'))
            fingerprint = hashlib.sha256((title + '\n' + text).encode()).hexdigest()
            existing = await db.scalar(select(models.NewsCandidate).where(models.NewsCandidate.source == SOURCE,
                or_(models.NewsCandidate.external_id == post['id'], models.NewsCandidate.source_url == url,
                    models.NewsCandidate.source_hash == fingerprint)).with_for_update())
            if existing:
                counts['duplicates'] += 1
                if existing.source_hash != fingerprint:
                    existing.title = title; existing.original_text = text; existing.source_hash = fingerprint
                    existing.source_modified = stamp; existing.source_changed = True
                    existing.rights_status = 'uncertain'
                    if existing.item_id:
                        item = await db.get(models.ContentItem, existing.item_id)
                        if item:
                            item.approved_version = None
                    counts['changed'] += 1
            else:
                author = next(iter(post.get('_embedded', {}).get('author', [])), {})
                candidate = models.NewsCandidate(source=SOURCE, external_id=post['id'], title=title,
                    original_text=text[:100000], source_url=url, author=str(author.get('name') or '')[:300] or None,
                    source_date=parsed_date(post.get('date_gmt')), source_modified=stamp, source_hash=fingerprint)
                db.add(candidate); await db.flush(); selected.append(candidate)
                counts['candidates'] += 1
            if stamp and (latest is None or stamp > latest): latest = stamp
            if counts['candidates'] >= limit: break
        if counts['candidates'] >= limit or not cursor or len(posts) < params['per_page']: break
    # Conserva TODOS los candidatos; solo un lote se adapta automáticamente.
    for candidate in selected[:max(0, get_settings().news_adaptation_batch)]:
        candidate.status = 'queued'
        db.add(models.ContentJob(kind='adapt', target_id=candidate.id))
    row.data = {**(row.data or {}), 'cursor': latest.isoformat() if latest else cursor,
                'last_success': now_utc().isoformat()}
    job.result = counts


async def collect(db, job):
    try:
        await collect_source(db, job)
    except (ValueError, KeyError, TypeError, AttributeError):
        raise ProviderError('INVALID_SOURCE_RESPONSE') from None


async def process_one():
    async with get_session_factory()() as db:
        job = await db.scalar(select(models.ContentJob).outerjoin(models.ContentItem, models.ContentJob.target_id == models.ContentItem.id)
            .where(models.ContentJob.status.in_(['queued', 'waiting_quota']), models.ContentJob.available_at <= now_utc())
            .order_by(case((models.ContentItem.publish_at.is_not(None), 0), else_=1), models.ContentItem.publish_at,
                      models.ContentJob.created_at).with_for_update(of=models.ContentJob, skip_locked=True).limit(1))
        if not job: return False
        if job.started_at is None: job.started_at = now_utc()
        target = None
        try:
            if job.kind == 'collect':
                await collect(db, job)
            elif job.kind == 'adapt':
                target = await db.scalar(select(models.NewsCandidate).where(models.NewsCandidate.id == job.target_id).with_for_update())
                if not target or target.status == 'discarded' or target.item_id:
                    job.status = 'cancelled'; await db.commit(); return True
                # Cota conservadora por bytes, incluyendo margen del prompt/JSON.
                wait = await reserve_quota('text', estimated_tokens=len((target.title + target.original_text[:24000]).encode()) + 3000)
                if wait:
                    job.status = target.status = 'waiting_quota'; job.available_at = wait
                    await db.commit(); return True
                value = await adapt_news(target.title, target.original_text)
                target.adaptation = {**value, 'source_hash': target.source_hash,
                                     'original_text': target.original_text, 'original_title': target.title}
                target.classification = value['classification']
                target.status = 'needs_review' if value['unsuitable'] else 'adapted'
            else:
                target = await db.scalar(select(models.ContentItem).where(models.ContentItem.id == job.target_id).with_for_update())
                if not target or target.deleted_at or job.version != target.text_version:
                    job.status = 'cancelled'; await db.commit(); return True
                if not editorial_ready(target):
                    job.status = 'waiting_review'; target.audio_status = 'pending'
                    await db.commit(); return True
                if current_audio(target):
                    target.audio_status = 'ready'
                    job.status = 'done'; await db.commit(); return True
                wait = await reserve_quota('tts', retry=job.kind == 'tts_retry')
                if wait:
                    job.status = target.audio_status = 'waiting_quota'; job.available_at = wait
                    await db.commit(); return True
                audio = await narrate(target.title + '\n\n' + target.body)
                directory = Path(get_settings().content_audio_dir)
                name = f'{target.id}-{target.text_version}-{uuid4().hex}.wav'
                temporary = directory / (name + '.tmp')
                try:
                    directory.mkdir(parents=True, exist_ok=True)
                    temporary.write_bytes(audio); os.replace(temporary, directory / name)
                except OSError:
                    raise ProviderError('AUDIO_STORAGE_ERROR') from None
                target.audio_file = name; target.audio_version = target.text_version
                target.tts_ready = True; target.audio_status = 'ready'; target.audio_error = None
            job.status = 'done'; job.finished_at = now_utc(); job.error = None
        except ProviderError as error:
            job.attempts += 1; job.error = error.code
            if error.code == 'QUOTA_REACHED' and job.kind != 'collect':
                await block_quota('text' if job.kind == 'adapt' else 'tts')
                job.status = 'waiting_quota'; job.available_at = next_provider_day()
            elif error.code in {'GEMINI_NOT_CONFIGURED', 'PROVIDER_CONFIG_ERROR'} or job.attempts >= 3:
                job.status = 'failed'; job.finished_at = now_utc()
            else:
                job.status = 'queued'; job.available_at = now_utc() + timedelta(seconds=60 * job.attempts)
            if target:
                if isinstance(target, models.ContentItem):
                    target.audio_status = 'waiting_quota' if job.status == 'waiting_quota' else 'failed' if job.status == 'failed' else 'queued'
                    target.audio_error = error.code
                else:
                    target.status = 'waiting_quota' if job.status == 'waiting_quota' else 'failed' if job.status == 'failed' else 'queued'
                    target.editorial_note = error.code
        await db.commit()
        return True


async def schedule():
    async with get_session_factory()() as db:
        local = now_utc().astimezone(ZoneInfo('America/Santiago'))
        row = await control(db, 'collection')
        if local.hour >= get_settings().news_collection_hour and (row.data or {}).get('scheduled_day') != local.date().isoformat():
            row.data = {**(row.data or {}), 'scheduled_day': local.date().isoformat()}
            active = await db.scalar(select(models.ContentJob.id).where(models.ContentJob.kind == 'collect', models.ContentJob.status == 'queued'))
            if not active: db.add(models.ContentJob(kind='collect'))
        items = (await db.scalars(select(models.ContentItem).where(models.ContentItem.deleted_at.is_(None),
            models.ContentItem.status == 'draft', models.ContentItem.publish_at <= now_utc())
            .with_for_update(skip_locked=True))).all()
        for item in items:
            if editorial_ready(item):
                try: await publish(db, item)
                except Exception as error:
                    from app.errors import ApiError
                    if not isinstance(error, ApiError): raise
                    item.audio_error = 'PUBLICATION_WAITING_AUDIO'
        await db.commit()


async def content_worker():
    while True:
        try:
            await schedule()
            found = await process_one()
        except Exception:
            # No registrar excepción externa que pueda incluir clave/textos.
            found = False
        await asyncio.sleep(2 if found else 10)

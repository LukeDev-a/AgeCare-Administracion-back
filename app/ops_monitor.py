"""Observaciones reales y acotadas. Nunca ejecuta logins ni llama a proveedores.

HTTP mide respuestas técnicas (todos los 4xx son respuestas esperadas de negocio).
Los porcentajes HTTP son de solicitudes observadas, no disponibilidad temporal.
SELECT 1 solo ocurre mientras este proceso está activo. No se rellena una pausa.
"""
import asyncio
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import logging
import math
import time
from uuid import UUID, uuid4

from sqlalchemy import delete, select, text, func

from app.config import get_settings
from app.database import get_session_factory
from app.enums import COMPONENT_NAMES, ComponentKey, ComponentStatus
from app.models import OpsObservation, ComponentState, LatencyWindow
from app.schemas.ops import ComponentOut, LatencyRow
from app.security import as_utc, now_utc

INTERVAL_SECONDS = 60
PROBE_TIMEOUT_SECONDS = 3
STALE_SECONDS = 180
MINIMUM_SAMPLES = 20
BUFFER_LIMIT = 5000
RETENTION_DAYS = 31
MAX_ROWS_PER_COMPONENT = 100000
REAL_KEYS = ('api_core', 'database', 'auth')
REAL_NAMES = {'api_core': 'API administrativa', 'database': 'Base de datos',
              'auth': 'Autenticación de la consola'}
logger = logging.getLogger('uvicorn.error')


@dataclass(frozen=True)
class Observation:
    component_key: str
    observed_at: datetime
    duration_ms: float
    success: bool
    source: str
    failure_kind: str | None = None
    id: UUID = field(default_factory=uuid4)


# Overflow discards oldest pending observations; it never extrapolates a count.
# Persistent retention also caps each component, keeping DB probes independent
# of HTTP traffic volume. Readers describe only the retained observed history.
pending: deque[Observation] = deque(maxlen=BUFFER_LIMIT)


class OpsMonitorMiddleware:
    """Pure ASGI: does not consume request/response bodies or copy the scope."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        path = scope.get('path', '')
        prefix = '/api/v1/admin/'
        eligible = (get_settings().ops_monitor_enabled and scope['type'] == 'http'
                    and scope.get('method') != 'OPTIONS' and path.startswith(prefix)
                    and not any(path.startswith(prefix + x) for x in ('docs', 'openapi.json')))
        if not eligible:
            return await self.app(scope, receive, send)
        is_auth = path == prefix + 'auth' or path.startswith(prefix + 'auth/')
        started = time.perf_counter()
        status = None
        failure = None

        async def capture(message):
            nonlocal status
            if message['type'] == 'http.response.start':
                status = message['status']
            await send(message)

        try:
            await self.app(scope, receive, capture)
        except asyncio.CancelledError:
            failure = 'cancelled'
            raise
        except Exception:
            failure = 'transport'
            raise
        finally:
            # No exception text, URL, headers, identity, IP or request data.
            duration = max(0.0, (time.perf_counter() - started) * 1000)
            if failure or status is not None:
                success = failure is None and status < 500
                kind = failure or ('http_5xx' if not success else None)
                observed = now_utc()
                pending.append(Observation('api_core', observed, duration, success, 'http_requests', kind))
                if is_auth:
                    pending.append(Observation('auth', observed, duration, success, 'http_requests', kind))


async def probe_database():
    started = time.perf_counter()
    failure = None
    try:
        async with asyncio.timeout(PROBE_TIMEOUT_SECONDS):
            # Independent transaction: a failed probe cannot poison a request.
            async with get_session_factory()() as db:
                await db.execute(text('SELECT 1'))
    except TimeoutError:
        failure = 'probe_timeout'
    except Exception:
        failure = 'probe_error'
    return Observation('database', now_utc(), max(0.0, (time.perf_counter() - started) * 1000),
                       failure is None, 'database_probe', failure)


async def persist_pending():
    """Only acknowledge the bounded snapshot after its transaction commits."""
    batch = tuple({row.id: row for row in pending}.values())
    factory = get_session_factory()
    async with factory() as db:
        async with db.begin():
            existing = set()
            # Keep bound parameters below SQLite/PostgreSQL limits.
            for offset in range(0, len(batch), 500):
                existing.update((await db.execute(select(OpsObservation.id).where(
                    OpsObservation.id.in_([r.id for r in batch[offset:offset + 500]])))).scalars())
            db.add_all([OpsObservation(**vars(row)) for row in batch if row.id not in existing])
            await db.flush()
            await db.execute(delete(OpsObservation).where(
                OpsObservation.observed_at < now_utc() - timedelta(days=RETENTION_DAYS)))
            for key in REAL_KEYS:
                overflow = (select(OpsObservation.id).where(OpsObservation.component_key == key)
                            .order_by(OpsObservation.observed_at.desc(), OpsObservation.id.desc())
                            .offset(MAX_ROWS_PER_COMPONENT))
                await db.execute(delete(OpsObservation).where(OpsObservation.id.in_(overflow)))
    committed = {row.id for row in batch}
    remaining = [row for row in pending if row.id not in committed]
    pending.clear()
    pending.extend(remaining)


async def monitor_tick():
    pending.append(await probe_database())
    await persist_pending()


async def ops_monitor_worker():
    if not get_settings().ops_monitor_enabled:
        return
    while True:
        try:
            await monitor_tick()
        except Exception:
            # Do not log exception messages/URLs or claim measurements saved.
            logger.warning('AGECARE_OPS observation_persistence_failed')
        await asyncio.sleep(INTERVAL_SECONDS)


def percentiles(rows):
    # Individual successful durations, never percentiles of aggregates.
    values = sorted(r.duration_ms for r in rows if r.success)
    if len(values) < MINIMUM_SAMPLES:
        return None, None
    return (round(values[math.ceil(len(values) * .50) - 1]),
            round(values[math.ceil(len(values) * .95) - 1]))


def coverage(rows, start, end):
    """Conservative DB coverage: only adjacent probes, no gap >90s, cap60s.

    An isolated probe proves an observation, not a whole minute of uptime.
    The last probe never fills time up to 'now'.
    """
    seconds = 0.0
    successful = 0.0
    for previous, current in zip(rows, rows[1:]):
        gap = (as_utc(current.observed_at) - as_utc(previous.observed_at)).total_seconds()
        if 0 < gap <= 90:
            overlap = max(0.0, (min(end, as_utc(current.observed_at))
                                - max(start, as_utc(previous.observed_at))).total_seconds())
            measured = min(60.0, overlap)
            seconds += measured
            if previous.success and current.success:
                successful += measured
    ratio = min(1.0, seconds / max(1.0, (end - start).total_seconds()))
    return seconds, ratio, successful / seconds if seconds else None


async def observations(db, since, now, keys=REAL_KEYS):
    rows = (await db.execute(select(
        OpsObservation.component_key, OpsObservation.observed_at,
        OpsObservation.duration_ms, OpsObservation.success).where(
        OpsObservation.component_key.in_(keys),
        OpsObservation.observed_at >= since, OpsObservation.observed_at <= now)
        .order_by(OpsObservation.observed_at, OpsObservation.id))).all()
    return {key: [r for r in rows if r.component_key == key] for key in keys}


def metadata(key, rows, now, window_start):
    recent = [r for r in rows if as_utc(r.observed_at) >= window_start]
    last = as_utc(rows[-1].observed_at) if rows else None
    fresh = bool(last and (now - last).total_seconds() <= STALE_SECONDS)
    source = 'database_probe' if key == 'database' else 'http_requests'
    seconds, ratio, _ = coverage(rows, window_start, now) if key == 'database' else (None, None, None)
    return dict(sample_count=len(recent), successful_sample_count=sum(r.success for r in recent),
                first_observed_at=as_utc(rows[0].observed_at) if rows else None,
                last_observed_at=last,
                observed_success_rate=sum(r.success for r in recent) / len(recent) if recent else None,
                coverage_seconds=seconds, coverage_ratio=ratio,
                freshness='fresh' if fresh else 'stale' if rows else 'no_data',
                measurement_source=source, minimum_samples=MINIMUM_SAMPLES)


async def real_status(db):
    now = now_utc()
    since = now - timedelta(days=30)
    hour = now - timedelta(hours=1)
    history = await observations(db, hour, now)
    bounds = {row.component_key: row for row in (await db.execute(select(
        OpsObservation.component_key, func.min(OpsObservation.observed_at).label('first'),
        func.max(OpsObservation.observed_at).label('last')).where(
        OpsObservation.component_key.in_(REAL_KEYS), OpsObservation.observed_at >= since,
        OpsObservation.observed_at <= now).group_by(OpsObservation.component_key))).all()}
    database_history = (await db.execute(select(OpsObservation.observed_at, OpsObservation.success)
        .where(OpsObservation.component_key == 'database', OpsObservation.observed_at >= since,
               OpsObservation.observed_at <= now)
        .order_by(OpsObservation.observed_at, OpsObservation.id))).all()
    stored = {r.key: r for r in (await db.scalars(select(ComponentState).where(
        ComponentState.key.not_in(REAL_KEYS)))).all()}
    components = []
    for key in ComponentKey:
        if key.value not in REAL_KEYS:
            previous = stored.get(key.value)
            if previous:
                components.append(ComponentOut(key=key, name=COMPONENT_NAMES[key],
                    status=ComponentStatus(previous.status), uptime_30d=previous.uptime_30d,
                    latency_p50_ms=previous.latency_p50_ms, latency_p95_ms=previous.latency_p95_ms,
                    note=previous.note, checked_at=previous.checked_at,
                    data_origin=previous.data_origin, measurement_kind={
                        'push': 'delivery', 'ai_assistant': 'generation'}.get(key.value, 'service'),
                    freshness='stored'))
                continue
            components.append(ComponentOut(key=key, name=COMPONENT_NAMES[key], status=None,
                uptime_30d=None, latency_p50_ms=None, latency_p95_ms=None,
                note='Sin integración de mediciones reales.', checked_at=None,
                data_origin='unavailable', measurement_kind='service', freshness='not_integrated'))
            continue
        rows = history[key.value]
        details = metadata(key.value, rows, now, hour)
        bound = bounds.get(key.value)
        if bound:
            details.update(first_observed_at=as_utc(bound.first), last_observed_at=as_utc(bound.last),
                           freshness='fresh' if (now - as_utc(bound.last)).total_seconds() <= STALE_SECONDS else 'stale')
        recent = [r for r in rows if as_utc(r.observed_at) >= hour]
        current = [r for r in recent if as_utc(r.observed_at) >= now - timedelta(seconds=STALE_SECONDS)]
        status = None
        if current:
            successes = sum(r.success for r in current)
            status = (ComponentStatus.operational if successes == len(current) else
                      ComponentStatus.outage if not successes else ComponentStatus.degraded)
        p50, p95 = percentiles(recent)
        uptime = None
        if key == ComponentKey.database:
            seconds, ratio, rate = coverage(database_history, since, now)
            if ratio >= .95:
                uptime = rate
            details.update(coverage_seconds=seconds, coverage_ratio=ratio)
        note = ('Solicitudes reales de la consola; respuestas 4xx no indican una caída. '
                'El éxito observado no mide disponibilidad temporal.' if key != ComponentKey.database else
                'SELECT 1 cada 60 s con el proceso activo; pausas sin cobertura, sin relleno de historial.')
        components.append(ComponentOut(key=key, name=REAL_NAMES[key.value], status=status,
            uptime_30d=uptime, latency_p50_ms=p50, latency_p95_ms=p95, note=note,
            checked_at=details['last_observed_at'], data_origin='real', measurement_kind='service', **details))
    return components


async def real_latency(db, window, keys):
    now = now_utc()
    since = now - {'1h': timedelta(hours=1), '24h': timedelta(days=1), '7d': timedelta(days=7)}[window]
    history = await observations(db, since, now, tuple(key for key in keys if key in REAL_KEYS))
    stored = {r.component_key: r for r in (await db.scalars(select(LatencyWindow).where(
        LatencyWindow.window == window, LatencyWindow.component_key.in_(keys),
        LatencyWindow.component_key.not_in(REAL_KEYS)))).all()}
    result = []
    for key in keys:
        if key not in REAL_KEYS:
            previous = stored.get(key)
            if previous:
                result.append(LatencyRow(key=ComponentKey(key), name=COMPONENT_NAMES[ComponentKey(key)],
                    p50_ms=previous.p50_ms, p95_ms=previous.p95_ms, sample_count=previous.sample_count,
                    computed_at=previous.computed_at, data_origin=previous.data_origin,
                    measurement_kind={'push': 'delivery', 'ai_assistant': 'generation'}.get(key, 'service'),
                    freshness='stored'))
            continue
        rows = history[key]
        p50, p95 = percentiles(rows)
        details = metadata(key, rows, now, since)
        details.pop('sample_count')
        result.append(LatencyRow(key=ComponentKey(key), name=REAL_NAMES[key],
            p50_ms=p50, p95_ms=p95, sample_count=len(rows), computed_at=details['last_observed_at'],
            data_origin='real', measurement_kind='service', **details))
    return result

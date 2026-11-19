"""Fuente sintética común de actividad por perfil y adopción. Sin pagos/móvil.

Preparación explícita, IDs deterministas, transacción única, horizonte cerrado.
El worker solo añade días a un conjunto preparado y publica resúmenes atómicos.
"""
import asyncio
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
import hashlib
import logging
from uuid import NAMESPACE_URL, uuid5
from zoneinfo import ZoneInfo

from sqlalchemy import select, text
from app import models
from app.analytics_models import UsageAccount, UsageSession, AnalyticsSource
from app.config import get_settings
from app.database import get_session_factory
from app.security import as_utc, now_utc

START = date(2026, 5, 1)
END = date(2026, 12, 24)
MARKER = 'usage_demo_refresh'
ROLES = ('family', 'caregiver', 'elder', 'doctor')
ZONE = ZoneInfo('America/Santiago')
PREFIX = 'agecare-usage-2026-v1:'
logger = logging.getLogger('uvicorn.error')


def identifier(value):
    return uuid5(NAMESPACE_URL, PREFIX + value)


def number(value):
    return int.from_bytes(hashlib.sha256(str(value).encode()).digest()[:4], 'big')


def local_start(day):
    return datetime.combine(day, time.min, ZONE).astimezone(timezone.utc)


def account_rows(first, last):
    rows = []
    for index in range((last-first).days+1):
        day = first + timedelta(days=index)
        for ordinal in range(12 + (day-START).days % 9):
            key = f'{day}:{ordinal}'
            slot = number(key) % 100
            role = 'family' if slot < 55 else 'caregiver' if slot < 75 else 'elder' if slot < 95 else 'doctor'
            rows.append(dict(id=identifier(key), profile=role, created_at=local_start(day), data_origin='demo'))
    return rows


def session_rows(accounts, first, last, features):
    """Nunca genera instantes posteriores al cierre de un día ya procesado."""
    rows = []
    for account in accounts:
        seed = number(account.id)
        # Algunas cuentas no vuelven y otras dejan de utilizar la app.
        if seed % 11 == 0:
            continue
        created = as_utc(account.created_at).astimezone(ZONE).date()
        begin = max(first, created + timedelta(days=1))
        stop = min(last, created + timedelta(days=35 + seed % 100)) if seed % 5 == 0 else last
        applicable = [f for f in features if account.profile in f.applicable_roles]
        for offset in range(max(0, (stop-begin).days+1)):
            day = begin + timedelta(days=offset)
            if number(f'{account.id}:{day}') % 7 >= 2 + (account.profile == 'caregiver'):
                continue
            selected = [f.feature_key for f in applicable if number(f'{account.id}:{f.feature_key}') % 100
                < (3 if f.expected_low else 10 + number(f.feature_key) % 80)]
            if not selected and applicable:
                selected = [next((f.feature_key for f in applicable if not f.expected_low), applicable[0].feature_key)]
            duration = {'family': 180, 'caregiver': 360, 'elder': 450, 'doctor': 120}[account.profile] + seed % 150
            rows.append(dict(id=identifier(f'session:{account.id}:{day}'), account_id=account.id,
                started_at=local_start(day), duration_seconds=duration, feature_keys=selected, data_origin='demo'))
    return rows


async def insert_chunks(db, model, rows):
    for offset in range(0, len(rows), 500):
        await db.execute(model.__table__.insert(), rows[offset:offset+500])


async def aggregates(db, through, features, computed_at=None):
    end = local_start(through + timedelta(days=1))
    calculated = computed_at or now_utc()
    # 26 semanas visibles y las ventanas 7/30/90 quedan dentro del mismo historial.
    since = local_start(through - timedelta(days=188))
    rows = (await db.execute(select(UsageSession.account_id, UsageAccount.profile,
        UsageSession.started_at, UsageSession.duration_seconds, UsageSession.feature_keys)
        .join(UsageAccount, UsageAccount.id == UsageSession.account_id)
        .where(UsageSession.data_origin == 'demo', UsageAccount.data_origin == 'demo',
               UsageSession.started_at >= since, UsageSession.started_at < end))).all()
    by_role = {role: [] for role in ROLES}
    for row in rows:
        by_role[row.profile].append(row)
    previous_roles = {(r.days_window, r.role): r for r in (await db.scalars(select(models.RoleActivityWindow))).all()}
    previous_features = {(r.days_window, r.feature_key, r.role): r
        for r in (await db.scalars(select(models.FeatureUsageWindow))).all()}
    previous_weeks = {(r.week_start, r.role): r for r in (await db.scalars(select(models.RoleWeeklyActive))).all()}
    for role, sessions in by_role.items():
        dates = [(row, as_utc(row.started_at)) for row in sessions]
        retained_base = {r.account_id for r, at in dates if end-timedelta(days=60) <= at < end-timedelta(days=30)}
        retained_current = {r.account_id for r, at in dates if at >= end-timedelta(days=30)}
        retention = len(retained_base & retained_current)/len(retained_base) if retained_base else 0
        recent_week = {r.account_id for r, at in dates if at >= end-timedelta(days=7)}
        old_week = {r.account_id for r, at in dates if end-timedelta(days=63) <= at < end-timedelta(days=56)}
        growth = (len(recent_week)-len(old_week))/len(old_week) if old_week else 0
        for days in (7,30,90):
            selected = [r for r, at in dates if at >= end-timedelta(days=days)]
            users = {r.account_id for r in selected}
            values = dict(active_users=len(users), growth_8w=round(growth,4),
                sessions_per_week=round(len(selected)*7/days/len(users), 2) if users else 0,
                avg_session_seconds=round(sum(r.duration_seconds for r in selected)/len(selected)) if selected else 0,
                retention_30d=round(retention,4), computed_at=calculated)
            row = previous_roles.get((days,role))
            if row is None:
                row = models.RoleActivityWindow(days_window=days,role=role)
                db.add(row)
            for key,value in values.items():
                setattr(row,key,value)
            used = defaultdict(set)
            for session in selected:
                for key in session.feature_keys:
                    used[key].add(session.account_id)
            for feature in features:
                if role not in feature.applicable_roles:
                    continue
                row = previous_features.get((days,feature.feature_key,role))
                if row is None:
                    row = models.FeatureUsageWindow(days_window=days,feature_key=feature.feature_key,role=role)
                    db.add(row)
                row.users = len(used[feature.feature_key])
                row.computed_at = calculated
        monday = through-timedelta(days=through.weekday())
        for offset in range(26):
            week = monday-timedelta(weeks=offset)
            users = {r.account_id for r,at in dates if local_start(week) <= at < min(end,local_start(week+timedelta(days=7)))}
            row = previous_weeks.get((week,role))
            if row is None:
                row = models.RoleWeeklyActive(week_start=week,role=role)
                db.add(row)
            row.active_users = len(users)
            row.computed_at = calculated


async def refresh_usage(db, now=None, *, prepare=False):
    settings = get_settings()
    if settings.environment != 'dev' or (not prepare and not settings.usage_demo_refresh_enabled):
        return {'status':'disabled'}
    now = as_utc(now or now_utc())
    # Día completo anterior: nunca se publican sesiones futuras del día en curso.
    through = min(now.astimezone(ZONE).date()-timedelta(days=1), END)
    if through < START:
        return {'status':'outside_range'}
    if db.get_bind().dialect.name == 'postgresql':
        if not await db.scalar(text('SELECT pg_try_advisory_xact_lock(2026111902)')):
            return {'status':'busy'}
    marker = await db.get(AnalyticsSource,(MARKER,'demo'))
    if marker is None and not prepare:
        return {'status':'not_prepared'}
    for model in (UsageAccount,UsageSession):
        if await db.scalar(select(model.id).where(model.data_origin != 'demo').limit(1)):
            raise ValueError('USAGE_FOREIGN_SOURCE')
    if marker is None and (await db.scalar(select(UsageAccount.id).limit(1)) or await db.scalar(select(UsageSession.id).limit(1))):
        raise ValueError('USAGE_ORPHAN_DATASET')
    last = as_utc(marker.available_through).astimezone(ZONE).date()-timedelta(days=1) if marker else START-timedelta(days=1)
    if last >= through:
        return {'status':'frozen' if last >= END else 'current','through':str(last)}
    features = (await db.scalars(select(models.Feature).order_by(models.Feature.sort_order))).all()
    if not features:
        raise ValueError('USAGE_FEATURES_MISSING')
    first = last+timedelta(days=1)
    new_accounts = account_rows(first,through)
    await insert_chunks(db,UsageAccount,new_accounts)
    accounts = (await db.scalars(select(UsageAccount).where(UsageAccount.created_at < local_start(through+timedelta(days=1))))).all()
    sessions = session_rows(accounts,first,through,features)
    await insert_chunks(db,UsageSession,sessions)
    await aggregates(db,through,features,now)
    end = local_start(through+timedelta(days=1))
    if marker is None:
        marker = AnalyticsSource(name=MARKER,data_origin='demo',available_through=end,updated_at=now,revision=0)
        db.add(marker)
    marker.available_through = end
    marker.updated_at = now
    marker.revision += 1
    await db.flush()
    return {'status':'updated','through':str(through),'new_accounts':len(new_accounts),'new_sessions':len(sessions)}


async def data_through(db):
    marker = await db.get(AnalyticsSource,(MARKER,'demo'))
    return as_utc(marker.available_through).astimezone(ZONE).date()-timedelta(days=1) if marker else None


async def lock_usage_read(db):
    # Impide mezclar numeradores del cierre anterior y denominadores del nuevo
    # si el commit diario cae entre las consultas de una misma respuesta HTTP.
    if db.get_bind().dialect.name == 'postgresql':
        await db.execute(text('SELECT pg_advisory_xact_lock_shared(2026111902)'))


async def usage_worker():
    while True:
        try:
            async with get_session_factory()() as db:
                async with db.begin():
                    result = await refresh_usage(db)
                if result['status'] == 'updated':
                    logger.info('AGECARE_USAGE_DEMO updated through=%s',result['through'])
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning('AGECARE_USAGE_DEMO update_failed')
        await asyncio.sleep(60)

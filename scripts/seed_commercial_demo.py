"""Demostración comercial reproducible. --apply carga local, --target neon es explícito."""
import argparse
import asyncio
from datetime import date, datetime, time, timedelta, timezone
from uuid import NAMESPACE_URL, uuid5
from zoneinfo import ZoneInfo

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.dialects.postgresql import insert

from app import models
from app.analytics_models import AnalyticsAccount, AnalyticsActivity, AnalyticsPayment, AnalyticsSource
from app.commercial_analytics import VALID_ACTIONS
from app.config import get_settings
from app.database_urls import normalize_database_url, database_connect_args
from app.security import as_utc

START = date(2026, 8, 29)
END = date(2026, 12, 31)
PREFIX = 'commercial-demo-2026-v1-'


def identifier(key):
    return uuid5(NAMESPACE_URL, PREFIX + key)


def dataset(now):
    zone = ZoneInfo('America/Santiago')
    today = now.astimezone(zone).date()
    daily, accounts, activity, payments, plans = [], [], [], [], []
    active, paying = 18500, 1450
    day = START
    while day <= END:
        index = (day - START).days
        signups = 85 + (index * 17 % 67) + (day.month - 8) * 16
        cancellations = 7 + index * 7 % 18
        active += signups - cancellations
        paying += signups // 9 - cancellations // 4
        daily.append(dict(day=day, data_origin='demo', signups=signups, cancellations=cancellations,
            downloads=signups * 2 + index % 45, active_users_eod=active,
            paying_users_eod=paying, mrr_clp_eod=paying * 3680, computed_at=now))
        created = datetime.combine(day, time(9), tzinfo=zone).astimezone(timezone.utc)
        for number in range(signups):
            key = f'{day}-{number}'
            account_id = identifier(key)
            profile = tuple(VALID_ACTIONS)[number % 4]
            accounts.append(dict(id=account_id, external_id=PREFIX + key, profile=profile,
                data_origin='demo', created_at=created))
            if number % 5 != 0:
                activity.append(dict(id=identifier(key + '-activity'), account_id=account_id,
                    external_id=PREFIX + key + '-activity', action=sorted(VALID_ACTIONS[profile])[0],
                    data_origin='demo', occurred_at=created + timedelta(days=1 + number % 5)))
            if number % 7 == 0:
                payments.append(dict(id=identifier(key + '-payment'), account_id=account_id,
                    external_id=PREFIX + key + '-payment', data_origin='demo',
                    amount_minor=1000 if number % 2 else 10000, successful=number % 11 != 0,
                    subscription_active=True, occurred_at=created + timedelta(days=8 + number % 7)))
        if day <= today and (day.day == 1 or day == today or (day + timedelta(days=1)).month != day.month):
            gold, platinum = paying * 7 // 10, paying * 2 // 10
            for code, users, price in [('free', active - paying, None), ('gold', gold, 1000),
                ('platinum', platinum, 10000), ('provider', paying - gold - platinum, 5000)]:
                plans.append(dict(id=identifier(f'plan-{day}-{code}'), data_origin='demo', as_of=day,
                    plan_code=code, users=users, price_clp=price, mrr_clp=users * (price or 0),
                    monthly_churn=round(cancellations / active, 4), computed_at=now))
        day += timedelta(days=1)
    return daily, accounts, activity, payments, plans


async def load_demo(db, now):
    daily, accounts, activity, payments, plans = dataset(now)
    if db.bind.dialect.name == 'postgresql':
        await db.execute(sa.text('SELECT pg_advisory_xact_lock(20261110)'))
    existing = (await db.scalars(sa.select(models.MetricsDailyUsers).where(
        models.MetricsDailyUsers.day.between(START, END)))).all()
    existing_plans = (await db.scalars(sa.select(models.MetricsPlanSnapshot).where(
        models.MetricsPlanSnapshot.as_of.between(START, END)))).all()
    if any(row.data_origin != 'demo' for row in [*existing, *existing_plans]):
        raise ValueError('Hay registros reales o de origen desconocido en el rango. Carga cancelada.')
    # El identificador estable permite reintentar sin multiplicar observaciones.
    for model, rows, keys in [
        (models.MetricsDailyUsers, daily, ['day']),
        (AnalyticsAccount, accounts, ['data_origin', 'external_id']),
        (AnalyticsActivity, activity, ['data_origin', 'external_id']),
        (AnalyticsPayment, payments, ['data_origin', 'external_id']),
        (models.MetricsPlanSnapshot, plans, ['as_of', 'plan_code']),
    ]:
        for offset in range(0, len(rows), 500):
            statement = insert(model).values(rows[offset:offset + 500]).on_conflict_do_nothing(index_elements=keys)
            await db.execute(statement)
    zone = ZoneInfo('America/Santiago')
    today = now.astimezone(zone).date()
    # Solo horas transcurridas del día actual, sin proyectar la jornada completa.
    start_hour = datetime.combine(today, time.min, tzinfo=zone).astimezone(timezone.utc)
    hourly = []
    hour = start_hour
    while hour + timedelta(hours=1) <= now:
        hourly.append(dict(id=identifier('hour-' + hour.isoformat()), data_origin='demo', ts_hour=hour,
            bucket_minutes=60, signups=3 + hour.hour % 12, cancellations=hour.hour % 3, computed_at=now))
        hour += timedelta(hours=1)
    conflicts = await db.scalar(sa.select(sa.func.count()).select_from(models.MetricsHourlyUsers).where(
        models.MetricsHourlyUsers.ts_hour >= start_hour,
        models.MetricsHourlyUsers.ts_hour < now,
        models.MetricsHourlyUsers.data_origin != 'demo'))
    if conflicts:
        raise ValueError('Hay intervalos horarios ajenos a esta demostración. Se revierte la carga.')
    if hourly:
        await db.execute(insert(models.MetricsHourlyUsers).values(hourly).on_conflict_do_nothing(index_elements=['ts_hour']))
    for name in ('daily', 'plans', 'accounts', 'activity', 'payments', 'hourly'):
        source = await db.get(AnalyticsSource, (name, 'demo'))
        if source is None:
            db.add(AnalyticsSource(name=name, data_origin='demo', available_through=now, updated_at=now))
        else:
            source.available_through = max(as_utc(source.available_through), now)
            source.updated_at = now
            source.revision += 1
    return {'dias': len(daily), 'cuentas': len(accounts), 'acciones': len(activity),
            'pagos': len(payments), 'planes': len(plans), 'horas': len(hourly)}


async def complete_legacy_year(db, include_history=False):
    """Clasificación explícita de las métricas del seed antiguo, conservando cifras y fechas."""
    start = date(START.year, 1, 1)
    end = START - timedelta(days=1)
    if include_history:
        start = await db.scalar(sa.select(sa.func.min(models.MetricsDailyUsers.day)).where(
            models.MetricsDailyUsers.day <= end))
        if start is None:
            raise ValueError('Falta el historial del seed que se desea regularizar.')
    rows = (await db.scalars(sa.select(models.MetricsDailyUsers).where(
        models.MetricsDailyUsers.day.between(start, end)).with_for_update())).all()
    if len(rows) != (end - start).days + 1:
        raise ValueError('El historial del seed tiene huecos. Revisar antes de regularizar.')
    if any(row.data_origin not in ('unknown', 'demo') for row in rows):
        raise ValueError('El historial contiene datos ajenos al seed de demostración.')
    changed = 0
    for row in rows:
        if row.data_origin == 'unknown':
            row.data_origin = 'demo'
            changed += 1
    return changed


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--target', choices=['local', 'neon'], default='local')
    parser.add_argument('--complete-legacy-year', action='store_true',
        help='Confirmar que enero-agosto proviene del seed de prueba y clasificarlo como demo.')
    parser.add_argument('--complete-legacy-history', action='store_true',
        help='Confirmar como demo todo el historial diario previo del seed, incluidos años anteriores.')
    args = parser.parse_args()
    if get_settings().environment != 'dev':
        raise ValueError('Esta demostración requiere entorno dev.')
    now = datetime.now(timezone.utc)
    if not args.apply:
        rows = dataset(now)
        print('Vista previa del rango', START, END, 'registros por grupo', [len(group) for group in rows])
        return
    if args.target == 'neon':
        from scripts.create_editor_accounts import render_value
        from sqlalchemy.engine import make_url
        url = normalize_database_url(render_value('ADMIN_DATABASE_URL'))
        parsed = make_url(url)
        if not (parsed.host or '').endswith('.neon.tech') or not (parsed.username or '').startswith('agecare_api_'):
            raise ValueError('Se requiere el perfil limitado Neon.')
    else:
        url = 'postgresql+asyncpg://agecare:agecare@localhost:5432/agecare_admin'
    engine = create_async_engine(url, hide_parameters=True, connect_args=database_connect_args(url))
    try:
        async with async_sessionmaker(engine)() as db:
            async with db.begin():
                result = await load_demo(db, now)
                if args.complete_legacy_year or args.complete_legacy_history:
                    result['dias_legados_regularizados'] = await complete_legacy_year(db, args.complete_legacy_history)
        print('Demostración confirmada en', args.target, result)
    finally:
        await engine.dispose()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except Exception as exc:
        print('Carga detenida.', type(exc).__name__)
        if type(exc) is ValueError:
            print(str(exc))
        raise SystemExit(1) from None

"""Procesamiento explícito del conjunto comercial ficticio autorizado de2026."""
import asyncio
import logging
from zoneinfo import ZoneInfo
from sqlalchemy import select, text
from app import models
from app.analytics_models import AnalyticsAccount, AnalyticsActivity, AnalyticsPayment, AnalyticsSource
from app.commercial_analytics import cohort_funnel
from app.config import get_settings
from app.database import get_session_factory
from app.security import as_utc, now_utc
from scripts.seed_commercial_demo import START, END, PREFIX, dataset, load_demo

MARKER = 'commercial_demo_refresh'
FIELDS = ('signups', 'cancellations', 'downloads', 'active_users_eod', 'paying_users_eod', 'mrr_clp_eod')
logger = logging.getLogger('uvicorn.error')


async def refresh_demo(db, now=None):
    """El llamador controla commit/rollback; nunca seed destructivo ni datos reales."""
    settings = get_settings()
    if not settings.commercial_demo_refresh_enabled or settings.environment != 'dev':
        return {'status': 'disabled'}
    now = as_utc(now or now_utc())
    today = now.astimezone(ZoneInfo('America/Santiago')).date()
    if not START <= today <= END:
        return {'status': 'outside_demo_range'}
    if db.get_bind().dialect.name == 'postgresql':
        if not await db.scalar(text('SELECT pg_try_advisory_xact_lock(2026111701)')):
            return {'status': 'busy'}
    marker = await db.get(AnalyticsSource, (MARKER, 'demo'))
    if marker and as_utc(marker.updated_at).replace(minute=0, second=0, microsecond=0) >= now.replace(minute=0, second=0, microsecond=0):
        return {'status': 'current'}
    # Exigir el conjunto conocido y detenerse si se conectaron fuentes reales.
    if not await db.scalar(select(AnalyticsAccount.id).where(AnalyticsAccount.external_id.startswith(PREFIX)).limit(1)):
        return {'status': 'dataset_missing'}
    for model in (AnalyticsAccount, AnalyticsActivity, AnalyticsPayment, AnalyticsSource):
        if await db.scalar(select(model).where(model.data_origin != 'demo').limit(1)) is not None:
            return {'status': 'foreign_source'}
    setting = await db.get(models.SystemSetting, 'plan_prices')
    prices = setting.value if setting else {'gold': 1000, 'platinum': 10000, 'provider': 5000}
    if not isinstance(prices, dict) or any(type(prices.get(key)) is not int or prices[key] < 0 for key in ('gold', 'platinum', 'provider')):
        raise ValueError('DEMO_INVALID_PLAN_PRICES')
    expected = {row['day']: row for row in dataset(now)[0]}
    existing = (await db.scalars(select(models.MetricsDailyUsers).where(models.MetricsDailyUsers.day.between(START, today)))).all()
    # No convertir un agregado editado/desconocido en dato recién calculado.
    for row in existing:
        if row.data_origin != 'demo' or any(getattr(row, key) != expected[row.day][key] for key in FIELDS):
            raise ValueError('DEMO_EXISTING_VALUES_CHANGED')
    await load_demo(db, now, observed_only=True, plan_prices=prices)
    rows = (await db.scalars(select(models.MetricsDailyUsers).where(models.MetricsDailyUsers.day.between(START, today)))).all()
    for row in rows:
        row.computed_at = now  # Valores recalculados/cotejados con el generador, no sustituidos.
    plans = (await db.scalars(select(models.MetricsPlanSnapshot).where(models.MetricsPlanSnapshot.as_of.between(START, today)))).all()
    for row in plans:
        if row.data_origin != 'demo' or row.users < 0 or row.mrr_clp != row.users * (row.price_clp or 0):
            raise ValueError('DEMO_INVALID_HISTORICAL_PLAN')
        row.computed_at = now  # Conservar precio, usuarios e ingresos históricos.
    first = await cohort_funnel(db, now=now)
    for option in first.cohorts:
        if option.month != first.cohort_month:
            await cohort_funnel(db, option.month, now=now)
    if marker is None:
        db.add(AnalyticsSource(name=MARKER, data_origin='demo', available_through=now, updated_at=now, revision=1))
    else:
        marker.available_through = marker.updated_at = now
        marker.revision += 1
    return {'status': 'updated', 'day': today.isoformat(), 'daily_rows': len(rows), 'plan_rows': len(plans)}


async def demo_analytics_worker():
    while True:
        try:
            async with get_session_factory()() as db:
                async with db.begin():
                    result = await refresh_demo(db)
            if result['status'] == 'updated':
                logger.info('AGECARE_DEMO_ANALYTICS updated day=%s daily_rows=%s', result['day'], result['daily_rows'])
        except asyncio.CancelledError:
            raise
        except Exception:
            # No imprimir excepciones/URLs ni payloads de la base.
            logger.warning('AGECARE_DEMO_ANALYTICS refresh_failed; transaction_rolled_back')
        await asyncio.sleep(60)

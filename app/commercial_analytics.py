"""Cohortes mensuales, corte común y frescura sin rejuvenecer las fuentes."""
import asyncio
import hashlib
import logging
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from sqlalchemy import select, text
from app.analytics_models import (AnalyticsAccount, AnalyticsActivity, AnalyticsPayment,
                                  AnalyticsSource, AnalyticsCohortSnapshot)
from app.config import get_settings
from app.database import get_session_factory
from app.security import as_utc, now_utc
from app.schemas.metrics import FreshnessOut, SourceFreshness, FunnelStage, FunnelOut, CohortOption
from app.errors import invalid, not_found

VALID_ACTIONS = {
    'elder': {'message_sent', 'mood_recorded', 'game_started', 'entertainment_played'},
    'family': {'elder_status_viewed', 'alert_detail_viewed', 'care_coordination_recorded'},
    'caregiver': {'observation_recorded', 'medication_confirmed', 'care_task_updated'},
    'doctor': {'patient_health_viewed', 'medication_plan_saved'},
}
REQUIRED = ('accounts', 'activity', 'payments')

def month_of(value):
    return as_utc(value).astimezone(ZoneInfo(get_settings().business_timezone)).strftime('%Y-%m')

async def freshness(db, names, origin, computed_at, now=None):
    now = now or now_utc()
    rows = (await db.scalars(select(AnalyticsSource).where(
        AnalyticsSource.name.in_(names), AnalyticsSource.data_origin == origin))).all()
    sources = []
    for name in names:
        row = next((row for row in rows if row.name == name), None)
        missing = row is None
        stale = bool(row and (now - as_utc(row.updated_at) > timedelta(hours=24)
            or now - as_utc(row.available_through) > timedelta(hours=24)))
        sources.append(SourceFreshness(name=name, updated_at=row.updated_at if row else None,
            available_through=row.available_through if row else None, missing=missing, stale=stale))
    calculation_stale = computed_at is not None and now - as_utc(computed_at) > timedelta(hours=24)
    status = 'missing' if any(s.missing for s in sources) else ('stale' if calculation_stale or any(s.stale for s in sources) else 'fresh')
    return FreshnessOut(status=status, sources=sources, calculation_stale=calculation_stale)

def calculate(accounts, activities, payments, sources, now=None):
    """Ventanas [creación, creación+30 días); uso estrictamente anterior al pago."""
    now = now or now_utc()
    present = {source.name: source for source in sources}
    cutoff = min([now, *[as_utc(source.available_through) for source in sources]])
    created = [account for account in accounts if as_utc(account.created_at) <= cutoff]
    activity_by, payments_by = {}, {}
    for event in activities:
        activity_by.setdefault(event.account_id, []).append(event)
    for payment in payments:
        payments_by.setdefault(payment.account_id, []).append(payment)
    active, paid, observed = 0, 0, 0
    for account in created:
        start = as_utc(account.created_at); end = start + timedelta(days=30)
        observed += end <= cutoff
        uses = [as_utc(event.occurred_at) for event in activity_by.get(account.id, [])
            if event.data_origin == account.data_origin and event.action in VALID_ACTIONS.get(account.profile, set())
            and start <= as_utc(event.occurred_at) < end and as_utc(event.occurred_at) <= cutoff]
        active += bool(uses)
        charges = [payment for payment in payments_by.get(account.id, [])
            if payment.data_origin == account.data_origin and payment.successful and payment.amount_minor > 0
            and start <= as_utc(payment.occurred_at) <= cutoff]
        first = min(charges, key=lambda item: as_utc(item.occurred_at), default=None)
        paid += bool(first and first.subscription_active and as_utc(first.occurred_at) < end
                     and uses and min(uses) < as_utc(first.occurred_at))
    counts = [len(created) if 'accounts' in present else None,
              active if all(key in present for key in ('accounts', 'activity')) else None,
              paid if all(key in present for key in REQUIRED) else None]
    mixed_activity = any(event.data_origin != account.data_origin for account in created
                         for event in activity_by.get(account.id, [])) or any(account.profile not in VALID_ACTIONS for account in created)
    mixed_payments = any(event.data_origin != account.data_origin for account in created
                         for event in payments_by.get(account.id, []))
    if mixed_activity:
        counts[1] = None
    if mixed_activity or mixed_payments:
        counts[2] = None
    stages = []
    for index, (key, label) in enumerate((('accounts', 'Cuentas creadas'), ('active_30d', 'Cuentas activas'),
                                        ('paying', 'Activas que pasan a pago'))):
        value = counts[index]
        def ratio(denominator):
            return round(value / denominator, 4) if value is not None and denominator is not None and denominator > 0 else None
        stages.append(FunnelStage(stage=key, name=label, users=value,
            rate_vs_first=ratio(counts[0]), rate_vs_previous=ratio(counts[index-1]) if index else None,
            unavailable_reason=('not_comparable' if (index == 1 and mixed_activity) or (index == 2 and (mixed_activity or mixed_payments))
                else 'missing_source') if value is None else ('zero_denominator' if not counts[0] else None)))
    return cutoff, len(created), observed, stages

async def cohort_funnel(db, month=None, now=None):
    now = now or now_utc()
    if month:
        try:
            parsed = date.fromisoformat(month + '-01')
            if parsed.strftime('%Y-%m') != month or month > month_of(now):
                raise ValueError()
        except ValueError:
            raise invalid('INVALID_COHORT', 'Selecciona un mes válido, sin fechas futuras.')
    # No mezclar una cohorte real con eventos demo. La futura inyección marca su origen.
    origins = set((await db.scalars(select(AnalyticsAccount.data_origin).distinct())).all())
    origin = next((value for value in ('real', 'demo', 'unknown') if value in origins), 'unknown')
    if db.get_bind().dialect.name == 'postgresql':
        await db.execute(text('SELECT pg_advisory_xact_lock(7240062701)'))
    accounts = (await db.scalars(select(AnalyticsAccount).where(AnalyticsAccount.data_origin == origin,
        AnalyticsAccount.created_at <= now))).all()
    sources = (await db.scalars(select(AnalyticsSource).where(AnalyticsSource.name.in_(REQUIRED),
        AnalyticsSource.data_origin == origin))).all()
    cutoff = min([now, *[as_utc(source.available_through) for source in sources]])
    options = []
    for key in sorted({month_of(account.created_at) for account in accounts}, reverse=True):
        members = [account for account in accounts if month_of(account.created_at) == key and as_utc(account.created_at) <= cutoff]
        if members:
            observed = sum(as_utc(account.created_at) + timedelta(days=30) <= cutoff for account in members)
            options.append(CohortOption(month=key, accounts=len(members), observed_accounts=observed, provisional=observed != len(members)))
    if month and not any(option.month == month for option in options):
        raise not_found('No hay cuentas observables para ese mes.')
    chosen = next((option for option in options if option.month == month), None) if month else next(
        (option for option in options if not option.provisional), options[0] if options else None)
    if chosen is None:
        return FunnelOut(as_of=None, computed_at=None, data_origin=origin, cohorts=[], stages=[
            FunnelStage(stage=key, name=label, users=None, rate_vs_first=None, unavailable_reason='missing_source')
            for key, label in [('accounts', 'Cuentas creadas'), ('active_30d', 'Cuentas activas'), ('paying', 'Activas que pasan a pago')]],
            freshness=await freshness(db, REQUIRED, origin, None, now))
    key = date.fromisoformat(chosen.month + '-01')
    signature = hashlib.sha256(repr(sorted((s.name, str(s.updated_at), str(s.available_through), s.revision) for s in sources)).encode()).hexdigest()
    cached = await db.get(AnalyticsCohortSnapshot, (key, origin))
    if cached is None or cached.source_signature != signature or month_of(cached.computed_at) != month_of(now) or (
        as_utc(cached.computed_at).astimezone(ZoneInfo(get_settings().business_timezone)).date() !=
        now.astimezone(ZoneInfo(get_settings().business_timezone)).date()):
        members = [account for account in accounts if month_of(account.created_at) == chosen.month]
        ids = [account.id for account in members]
        activities = (await db.scalars(select(AnalyticsActivity).where(AnalyticsActivity.account_id.in_(ids)))).all()
        payments = (await db.scalars(select(AnalyticsPayment).where(AnalyticsPayment.account_id.in_(ids)))).all()
        observed_cutoff, total, observed, stages = calculate(members, activities, payments, sources, now)
        result = FunnelOut(as_of=observed_cutoff.astimezone(ZoneInfo(get_settings().business_timezone)).date(), cutoff_at=observed_cutoff, computed_at=now,
            cohort_month=chosen.month, provisional=observed < total, accounts=total, observed_accounts=observed,
            data_origin=origin, stages=stages)
        if cached is None:
            cached = AnalyticsCohortSnapshot(month=key, data_origin=origin, payload={}, source_signature=signature, computed_at=now)
            db.add(cached)
        cached.payload = result.model_dump(mode='json'); cached.source_signature = signature; cached.computed_at = now
    result = FunnelOut.model_validate(cached.payload)
    result.cohorts = options
    result.freshness = await freshness(db, REQUIRED, origin, result.computed_at, now)
    return result

async def commercial_worker():
    while True:
        try:
            async with get_session_factory()() as db:
                # Caché diaria de cada cohorte disponible; nunca cambia timestamps de fuentes.
                first = await cohort_funnel(db)
                for option in first.cohorts:
                    if option.month != first.cohort_month:
                        await cohort_funnel(db, option.month)
                await db.commit()
        except asyncio.CancelledError:
            raise
        except Exception:
            logging.getLogger(__name__).warning('No se pudo actualizar el cálculo de cohortes; se reintentará.')
        await asyncio.sleep(60)

async def seed_analytics_demo(db, at, inserted_metrics):
    """Solo ejemplos en fuentes vacías; ninguna observación real se fabrica."""
    from calendar import monthrange
    from app import models
    metric_models = {'daily': models.MetricsDailyUsers, 'hourly': models.MetricsHourlyUsers,
                     'plans': models.MetricsPlanSnapshot}
    zone = ZoneInfo(get_settings().business_timezone)
    for name in inserted_metrics:
        if await db.get(AnalyticsSource, (name, 'demo')) is not None:
            continue
        model = metric_models[name]
        column = model.day if name == 'daily' else (model.ts_hour if name == 'hourly' else model.as_of)
        from sqlalchemy import func
        last = await db.scalar(select(func.max(column)).where(model.data_origin == 'demo'))
        watermark = min(at, as_utc(last) + timedelta(minutes=180)) if name == 'hourly' else min(at,
            datetime.combine(last + timedelta(days=1), datetime.min.time(), tzinfo=zone).astimezone(timezone.utc))
        db.add(AnalyticsSource(name=name, data_origin='demo', available_through=watermark, updated_at=at))
    for model in (AnalyticsAccount, AnalyticsActivity, AnalyticsPayment, AnalyticsCohortSnapshot):
        if await db.scalar(select(next(iter(model.__table__.primary_key.columns))).limit(1)) is not None:
            return
    if await db.scalar(select(AnalyticsSource.name).where(AnalyticsSource.name.in_(REQUIRED)).limit(1)) is not None:
        return
    local = at.astimezone(zone)
    for offset in (2, 1, 0):
        year, month = divmod(local.year*12 + local.month-1-offset, 12); month += 1
        for index in range(6):
            day = min(3+index*5, monthrange(year, month)[1], local.day if offset == 0 else 31)
            created = min(datetime(year, month, day, 9, tzinfo=zone).astimezone(timezone.utc), at-timedelta(hours=1))
            profile = tuple(VALID_ACTIONS)[index % 4]
            key = f'demo-{year}-{month:02d}-{index}'
            account = AnalyticsAccount(external_id=key, data_origin='demo', profile=profile, created_at=created)
            db.add(account); await db.flush()
            used = created + timedelta(days=1)
            if index < 4 and used <= at:
                db.add(AnalyticsActivity(account_id=account.id, external_id=key+'-use', data_origin='demo',
                    action=sorted(VALID_ACTIONS[profile])[0], occurred_at=used))
            charged = created + timedelta(days=2)
            if index in (0, 1, 4) and charged <= at:
                db.add(AnalyticsPayment(account_id=account.id, external_id=key+'-pay', data_origin='demo',
                    amount_minor=1000, successful=True, subscription_active=True, occurred_at=charged))
    for name in REQUIRED:
        db.add(AnalyticsSource(name=name, data_origin='demo', available_through=at, updated_at=at))

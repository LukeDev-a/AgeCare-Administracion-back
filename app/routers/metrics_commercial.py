"""Indicadores comerciales: fuentes, fechas reales y cohortes comparables."""
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Query
from sqlalchemy import func, select
from app import models
from app.deps import Db, require
from app.config import get_settings
from app.enums import PLAN_NAMES, PeriodKey, PlanCode
from app.errors import invalid
from app.periods import Period, buckets_for, resolve, business_today
from app.security import as_utc, now_utc
from app.commercial_analytics import freshness, cohort_funnel
from app.schemas.metrics import (BucketOut, CommercialDeltas, CommercialSummaryOut, FunnelOut,
                                 PeriodOut, PlanRow, PlansOut, PlanTotals, RegistrationsOut)

router = APIRouter(prefix='/metrics/commercial', tags=['Uso comercial'], dependencies=[require('metrics')])

def parse_period(value):
    try:
        return resolve(PeriodKey(value))
    except ValueError:
        raise invalid('INVALID_PERIOD', 'El período indicado no es válido.')

def period_out(period):
    return PeriodOut(key=period.key, start_date=period.start, end_date=period.end)

def data_origin(rows):
    origins = {row.data_origin for row in rows}
    return next(iter(origins)) if len(origins) == 1 else ('mixed' if origins else 'unknown')

def pct(current, previous):
    return round((current-previous)/previous, 4) if current is not None and previous is not None and previous > 0 else None

async def daily_rows(db, start, end):
    return (await db.scalars(select(models.MetricsDailyUsers).where(
        models.MetricsDailyUsers.day.between(start, end)).order_by(models.MetricsDailyUsers.day))).all()

async def latest_row(db, day):
    return await db.scalar(select(models.MetricsDailyUsers).where(models.MetricsDailyUsers.day <= day)
                           .order_by(models.MetricsDailyUsers.day.desc()).limit(1))

def complete_total(rows, period, field):
    # Un hueco o una mezcla de orígenes no es un total comparable del período.
    if len(rows) != period.days or data_origin(rows) not in ('demo', 'real'):
        return None
    return sum(getattr(row, field) for row in rows)

@router.get('/summary', response_model=CommercialSummaryOut)
async def commercial_summary(db: Db, period: str = Query(...)):
    p = parse_period(period)
    rows = await daily_rows(db, p.start, p.end)
    latest = await latest_row(db, p.end)
    previous = p.previous()
    old_rows = await daily_rows(db, previous.start, previous.end)
    old = await latest_row(db, previous.end)
    start_row = await latest_row(db, p.start - timedelta(days=1))
    comparable_snapshots = bool(latest and old and p.start <= latest.day <= p.end
        and previous.start <= old.day <= previous.end and latest.data_origin == old.data_origin
        and latest.data_origin in ('demo', 'real'))
    # Un período sin observaciones no equivale a cero altas/descargas/bajas.
    signups = complete_total(rows, p, 'signups')
    cancellations = complete_total(rows, p, 'cancellations')
    downloads = complete_total(rows, p, 'downloads')
    active_at_start = start_row.active_users_eod if start_row else None
    origin = data_origin([*rows, *([latest] if latest else [])])
    computed = max((row.computed_at for row in rows), default=latest.computed_at if latest else None)
    return CommercialSummaryOut(period=period_out(p), downloads=downloads, new_users=signups,
        churned_users=cancellations,
        churn_rate=round(cancellations/active_at_start, 4) if cancellations is not None and active_at_start and start_row.data_origin == origin and start_row.day == p.start-timedelta(days=1) else None,
        active_users=latest.active_users_eod if latest else None,
        paying_users=latest.paying_users_eod if latest else None,
        paying_share=round(latest.paying_users_eod/latest.active_users_eod, 4) if latest and latest.active_users_eod else None,
        mrr_clp=latest.mrr_clp_eod if latest else None,
        deltas=CommercialDeltas(new_users_pct=pct(signups, complete_total(old_rows, previous, 'signups')) if origin == data_origin(old_rows) else None,
            mrr_pct=pct(latest.mrr_clp_eod, old.mrr_clp_eod) if comparable_snapshots else None,
            active_users_pct=pct(latest.active_users_eod, old.active_users_eod) if comparable_snapshots else None),
        as_of=latest.day if latest else None, computed_at=computed, data_origin=origin,
        freshness=await freshness(db, ['daily'], origin, computed))

@router.get('/registrations', response_model=RegistrationsOut)
async def registrations(db: Db, period: str = Query(...)):
    p = parse_period(period); zone = ZoneInfo(get_settings().business_timezone)
    buckets, signups, cancellations = [], [], []
    if p.granularity == 'hour':
        start = datetime.combine(p.start, time.min, tzinfo=zone).astimezone(timezone.utc)
        end = datetime.combine(p.end + timedelta(days=1), time.min, tzinfo=zone).astimezone(timezone.utc)
        rows = (await db.scalars(select(models.MetricsHourlyUsers).where(
            models.MetricsHourlyUsers.ts_hour >= start, models.MetricsHourlyUsers.ts_hour < end)
            .order_by(models.MetricsHourlyUsers.ts_hour))).all()
        for row in rows:
            if row.bucket_minutes <= 0:
                raise invalid('INVALID_DATA', 'La fuente contiene una duración de intervalo inválida.')
            local_start = as_utc(row.ts_hour).astimezone(zone)
            buckets.append(BucketOut(label=local_start.strftime('%H:%M %z'), start=as_utc(row.ts_hour),
                end=min(as_utc(row.ts_hour)+timedelta(minutes=row.bucket_minutes), end)))
            signups.append(row.signups); cancellations.append(row.cancellations)
        source = 'hourly'
    else:
        rows = await daily_rows(db, p.start, p.end)
        by_day = {row.day: row for row in rows}
        for start, end, label in buckets_for(p):
            buckets.append(BucketOut(label=label,
                start=datetime.combine(start, time.min, tzinfo=zone).astimezone(timezone.utc),
                end=datetime.combine(end + timedelta(days=1), time.min, tzinfo=zone).astimezone(timezone.utc)))
            days = [by_day.get(start+timedelta(days=i)) for i in range((end-start).days+1)]
            complete = all(day is not None for day in days) and data_origin([day for day in days if day]) in ('demo', 'real')
            signups.append(sum(day.signups for day in days) if complete else None)
            cancellations.append(sum(day.cancellations for day in days) if complete else None)
        source = 'daily'
    computed = max((row.computed_at for row in rows), default=None)
    origin = data_origin(rows)
    return RegistrationsOut(period=period_out(p), granularity=p.granularity, buckets=buckets,
        signups=signups, cancellations=cancellations, computed_at=computed, data_origin=origin,
        freshness=await freshness(db, [source], origin, computed))

@router.get('/plans', response_model=PlansOut)
async def plans(db: Db):
    last = await db.scalar(select(func.max(models.MetricsPlanSnapshot.as_of)))
    if last is None:
        raise invalid('NO_DATA', 'Aún no hay snapshots de planes calculados.')
    rows = (await db.scalars(select(models.MetricsPlanSnapshot).where(models.MetricsPlanSnapshot.as_of == last))).all()
    order = [PlanCode.free, PlanCode.gold, PlanCode.platinum, PlanCode.provider]
    rows.sort(key=lambda row: order.index(PlanCode(row.plan_code)))
    total = sum(row.users for row in rows); origin = data_origin(rows)
    computed = max(row.computed_at for row in rows)
    return PlansOut(as_of=last, plans=[PlanRow(plan_code=row.plan_code, name=PLAN_NAMES[PlanCode(row.plan_code)],
        users=row.users, share=round(row.users/total, 4) if total else None,
        price_clp=row.price_clp, mrr_clp=row.mrr_clp, monthly_churn=row.monthly_churn) for row in rows],
        totals=PlanTotals(users=total, mrr_clp=sum(row.mrr_clp for row in rows),
            monthly_churn=round(sum(row.monthly_churn*row.users for row in rows)/total, 4) if total else None),
        computed_at=computed, data_origin=origin, freshness=await freshness(db, ['plans'], origin, computed))

@router.get('/funnel', response_model=FunnelOut)
async def funnel(db: Db, cohort_month: str | None = None):
    result = await cohort_funnel(db, cohort_month)
    latest = await latest_row(db, business_today())
    if latest:
        result.downloads = await db.scalar(select(func.sum(models.MetricsDailyUsers.downloads)).where(
            models.MetricsDailyUsers.day <= latest.day))
        result.downloads_as_of = latest.day; result.downloads_computed_at = latest.computed_at
        rows = (await db.scalars(select(models.MetricsDailyUsers).where(models.MetricsDailyUsers.day <= latest.day))).all()
        result.downloads_data_origin = data_origin(rows)
        if result.downloads_data_origin not in ('demo', 'real'):
            result.downloads = None
        state = await freshness(db, ['daily'], result.downloads_data_origin, latest.computed_at)
        result.downloads_stale = state.status != 'fresh'
    return result

"""Verificación agregada y de solo lectura de la actividad local preparada."""
import asyncio
import json
from datetime import timedelta
from sqlalchemy import select, text, func
from sqlalchemy.engine import make_url
from app import models
from app.analytics_models import UsageAccount, UsageSession, AnalyticsSource
from app.config import get_settings
from app.database import get_session_factory
from app.security import as_utc
from app.usage_demo import MARKER, data_through, local_start, END, lock_usage_read


async def run():
    settings=get_settings()
    url=make_url(settings.database_url)
    if settings.environment!='dev' or url.host not in ('db','localhost','127.0.0.1'):
        raise ValueError('Solo base local.')
    async with get_session_factory()() as db:
        await db.execute(text('SET TRANSACTION READ ONLY'))
        await lock_usage_read(db)
        async with get_session_factory()() as writer:
            if await writer.scalar(text('SELECT pg_try_advisory_xact_lock(2026111902)')):
                raise ValueError('La lectura no bloquea un cierre simultáneo.')
            await writer.rollback()
        cutoff=await data_through(db)
        if cutoff is None or cutoff>END:
            raise ValueError('Corte no válido.')
        end=local_start(cutoff+timedelta(days=1))
        marker=await db.get(AnalyticsSource,(MARKER,'demo'))
        roles=(await db.scalars(select(models.RoleActivityWindow))).all()
        usage=(await db.scalars(select(models.FeatureUsageWindow))).all()
        for summary in roles:
            start=end-timedelta(days=summary.days_window)
            actual=await db.scalar(select(func.count(func.distinct(UsageSession.account_id))).join(
                UsageAccount,UsageAccount.id==UsageSession.account_id).where(
                UsageAccount.profile==summary.role,UsageSession.started_at>=start,UsageSession.started_at<end))
            if actual!=summary.active_users:
                raise ValueError('Diferencia de activos y sesiones.')
            for feature in [r for r in usage if r.role==summary.role and r.days_window==summary.days_window]:
                used=await db.scalar(text('''SELECT count(DISTINCT s.account_id)
                    FROM analytics_usage_sessions s JOIN analytics_usage_accounts a ON a.id=s.account_id
                    WHERE a.profile=:role AND s.started_at>=:start AND s.started_at<:end
                    AND s.feature_keys ? :feature'''),
                    {'role':summary.role,'start':start,'end':end,'feature':feature.feature_key})
                if used!=feature.users or not 0<=used<=actual:
                    raise ValueError('Diferencia de adopción y sesiones.')
        latest=await db.scalar(select(func.max(UsageSession.started_at)))
        if latest and as_utc(latest)>=end:
            raise ValueError('Hay actividad futura.')
        print(json.dumps({'through':str(cutoff),'accounts':await db.scalar(select(func.count()).select_from(UsageAccount)),
            'sessions':await db.scalar(select(func.count()).select_from(UsageSession)),
            'role_windows_verified':len(roles),'feature_windows_verified':len(usage),
            'same_source_counts':True,'shared_read_lock_verified':True,
            'no_future_activity':True,'source_revision':marker.revision}),flush=True)


if __name__=='__main__':
    try:
        asyncio.run(run())
    except Exception as error:
        raise SystemExit(f'Verificación detenida ({type(error).__name__}); detalles privados omitidos.') from None

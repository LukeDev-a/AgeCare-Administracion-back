"""Prepara solo actividad/adopción local con respaldo cifrado. --apply explícito.

No permite Neon ni un entorno que no sea dev. No ejecuta seed y no modifica
directorio, pagos, métricas comerciales, personal, juegos, contenido o auditoría.
"""
import argparse
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path

from cryptography.fernet import Fernet
from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from app import models
from app.analytics_models import AnalyticsSource
from app.config import get_settings
from app.database import get_session_factory
from app.security import now_utc
from app.usage_demo import MARKER, refresh_usage, END
from scripts.migrate_neon_0016 import manifest

ROOT=Path(__file__).resolve().parents[1]
TARGETS=('role_activity_window','role_weekly_active','feature_usage_window')


async def run(apply=False):
    settings=get_settings()
    url=make_url(settings.database_url)
    if settings.environment!='dev' or url.host not in ('db','localhost','127.0.0.1'):
        raise ValueError('Este procedimiento solo admite PostgreSQL local de desarrollo.')
    if url.get_backend_name()!='postgresql':
        raise ValueError('Se requiere PostgreSQL local.')
    async with get_session_factory()() as db:
        async with db.begin():
            await db.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ'))
            await db.execute(text("SET LOCAL statement_timeout='300s'"))
            await db.execute(text("SET LOCAL lock_timeout='10s'"))
            await db.execute(text('SELECT pg_advisory_xact_lock(2026111902)'))
            marker=await db.get(AnalyticsSource,(MARKER,'demo'))
            print(json.dumps({'prepared':marker is not None,'horizon':str(END),'apply':apply}),flush=True)
            if not apply:
                return
            conn=await db.connection()
            tables=(await conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"))).scalars().all()
            untouched=[t for t in tables if t not in (*TARGETS,'analytics_usage_accounts','analytics_usage_sessions','analytics_sources')]
            before=await manifest(conn,untouched)
            saved={}
            for table in TARGETS:
                saved[table]=(await conn.execute(text(f'SELECT to_jsonb(r) FROM public.{table} r'))).scalars().all()
            sources=(await conn.execute(text('SELECT to_jsonb(r) FROM analytics_sources r WHERE name != :name'),{'name':MARKER})).scalars().all()
            saved['other_sources']=sources
            backup=ROOT/'backups'/('usage-demo-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
            backup.mkdir(parents=True,exist_ok=False)
            cipher=Fernet(settings.encryption_key.encode())
            payload=json.dumps({'summary_rows':saved,'untouched_tables':before},ensure_ascii=False).encode()
            (backup/'before.enc').write_bytes(cipher.encrypt(payload))
            if cipher.decrypt((backup/'before.enc').read_bytes())!=payload:
                raise ValueError('Respaldo no verificable.')
            result=await refresh_usage(db,now_utc(),prepare=True)
            await db.flush()
            if await manifest(conn,untouched)!=before:
                raise ValueError('Cambió un módulo ajeno; se revierte la transacción.')
            after_sources=(await conn.execute(text('SELECT to_jsonb(r) FROM analytics_sources r WHERE name != :name'),{'name':MARKER})).scalars().all()
            if sorted(sources,key=str)!=sorted(after_sources,key=str):
                raise ValueError('Cambió una fuente comercial; se revierte.')
            report={**result,'preserved_tables':len(untouched),'backup':str(backup.relative_to(ROOT)),
                    'payments_directory_commercial_unchanged':True,'transaction':'verified_before_commit'}
        report['transaction']='committed'
        (backup/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps(report),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply',action='store_true')
    try:
        asyncio.run(run(parser.parse_args().apply))
    except Exception as error:
        raise SystemExit(f'Preparación detenida ({type(error).__name__}); detalles privados omitidos.') from None

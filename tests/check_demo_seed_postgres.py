"""Smoke de arranque/concurrencia: SOLO base temporal agecare_seed_check_*.

Usar una base vacía temporal, migrada a head, y ADMIN_SEED_DEMO_ENABLED=true.
No lee .env: todas las variables deben suministrarse al proceso de prueba.
"""
import asyncio
from uuid import uuid4
from datetime import timedelta

from sqlalchemy import delete, select

from app import database, models
from app.security import now_utc
from app.enums import PeriodKey
from app.routers.metrics_commercial import commercial_summary
from scripts.seed import seed


async def snapshot():
    async with database.get_session_factory()() as db:
        result = {}
        for table in database.Base.metadata.tables.values():
            pk = tuple(column.name for column in table.primary_key.columns)
            rows = (await db.execute(select(table))).mappings().all()
            result[table.name] = {tuple(row[key] for key in pk): dict(row) for row in rows}
        return result


async def main():
    engine = database.get_engine()
    assert engine.url.database.startswith('agecare_seed_check_'), 'Solo base temporal de pruebas.'
    assert engine.url.host == 'db' and engine.url.username == 'agecare'
    assert engine.url.database != 'agecare_admin'
    async with database.get_session_factory()() as db:
        assert await db.scalar(select(models.AdminUser.id).limit(1)) is None
        user = models.AdminUser(full_name='Cuenta temporal', email=f'{uuid4()}@example.org',
            role='admin', password_hash='hash-temporal', mfa_enabled=True, mfa_required=True,
            mfa_secret='solo-prueba', auth_version=3, is_active=True)
        db.add(user); await db.flush()
        db.add(models.AdminSession(admin_id=user.id, refresh_hash=uuid4().hex,
            expires_at=now_utc() + timedelta(days=1), auth_version=3, mfa_verified=True))
        await db.commit()
    protected = await snapshot()
    # Dos procesos lógicos simultáneos deben cargar cada módulo una sola vez.
    await asyncio.gather(seed(only_empty=True), seed(only_empty=True))
    before = await snapshot()
    assert len(before['games_apps']) == 20
    assert len(before['support_tickets']) == 251
    assert len(before['metrics_daily_users']) == 426
    assert len(before['content_items']) == 3
    assert all(row['status'] == 'draft' for row in before['content_items'].values())
    assert before['admin_users'] == protected['admin_users']
    assert before['admin_sessions'] == protected['admin_sessions']
    await seed(only_empty=True)
    assert await snapshot() == before
    async with database.get_session_factory()() as db:
        await db.execute(delete(models.Product)); await db.commit()
    await seed(only_empty=True)
    after = await snapshot()
    assert len(after['marketplace_products']) == 2
    assert {key: value for key, value in after.items() if key != 'marketplace_products'} == {
        key: value for key, value in before.items() if key != 'marketplace_products'}
    async with database.get_session_factory()() as db:
        summary = await commercial_summary(db, period=PeriodKey.current_month)
        assert summary.new_users > 0
    print('PostgreSQL OK: carga concurrente, reinicio idempotente, MFA/sesiones intactos, '
          'recarga de módulo vacío, 20 juegos y analítica del mes actual.')
    await engine.dispose()


if __name__ == '__main__':
    asyncio.run(main())

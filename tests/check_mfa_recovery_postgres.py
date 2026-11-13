"""Comprobación explícita y aislada; solo base temporal local, nunca envía correo."""
import asyncio
import importlib.util
import json
from pathlib import Path

import pyotp
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi import Response
from sqlalchemy import func, select
from starlette.requests import Request

from app import database, models
from app.account_security import decrypt, encrypt
from app.config import get_settings
from app.errors import ApiError
from app.mfa_recovery import confirm_recovery, request_recovery
from app.routers.mfa_recovery import RecoveryDecisionIn, decision_endpoint
from app.security import hash_password, verify_password


async def main():
    engine = database.get_engine()
    assert engine.url.database == 'agecare_mfa_recovery_check' and engine.url.host == '127.0.0.1'
    settings = get_settings()
    settings.mail_provider = 'smtp'; settings.smtp_host = 'localhost'; settings.mail_from = 'tests@example.org'
    factory = database.get_session_factory()
    try:
        async with engine.begin() as connection:
            tables = [table for table in models.Base.metadata.sorted_tables
                      if table.name not in ('admin_mfa_recoveries', 'mfa_recovery_emails')]
            await connection.run_sync(lambda bind: models.Base.metadata.create_all(bind, tables=tables))
        async with factory() as db:
            owner = models.AdminUser(full_name='Temporal', email='target@example.org', role='editor',
                password_hash=hash_password('Temporal123!'), is_active=True, mfa_enabled=True,
                mfa_secret=encrypt(pyotp.random_base32()))
            admins = [models.AdminUser(full_name='Revisor temporal', email=f'admin{i}@example.org', role='admin',
                password_hash=hash_password('Revisor123!'), is_active=True) for i in range(2)]
            db.add_all([owner, *admins]); await db.commit()
            target_id, admin_ids = owner.id, [admin.id for admin in admins]
        def migrate(connection):
            path = Path(__file__).resolve().parents[1] / 'alembic/versions/0015_mfa_recovery.py'
            spec = importlib.util.spec_from_file_location('mfa_migration', path)
            module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
            module.op = Operations(MigrationContext.configure(connection))
            module.upgrade(); module.upgrade()
        async with engine.begin() as connection:
            await connection.run_sync(migrate)
        def request():
            return Request({'type': 'http', 'method': 'POST', 'headers': [], 'client': ('127.0.0.1', 1)})
        async def issue():
            async with factory() as db:
                await request_recovery(db, 'target@example.org', 'Temporal123!', 'Perdí el autenticador', request())
                await db.commit()
        await asyncio.gather(issue(), issue())
        async with factory() as db:
            assert await db.scalar(select(func.count()).select_from(models.AdminMfaRecovery)) == 1
            row = await db.scalar(select(models.AdminMfaRecovery))
            row_id = row.id
            mail = await db.scalar(select(models.MfaRecoveryEmail))
            token = json.loads(decrypt(mail.payload_encrypted))['url'].split('#token=')[1]
            assert verify_password('Temporal123!', (await db.get(models.AdminUser, target_id)).password_hash)
        async def confirm():
            async with factory() as db:
                try:
                    await confirm_recovery(db, token, request()); await db.commit(); return 200
                except ApiError as error:
                    await db.rollback(); return error.status_code
        assert sorted(await asyncio.gather(confirm(), confirm())) == [200, 422]
        async def decide(actor_id, choice):
            async with factory() as db:
                actor = await db.get(models.AdminUser, actor_id)
                req = request(); req.state.actor = actor
                body = RecoveryDecisionIn(decision=choice, identity_verified=True,
                    note='Identidad comprobada por canal conocido', password='Revisor123!')
                try:
                    await decision_endpoint(row_id, body, req, Response(), db, actor)
                    await db.commit(); return 200
                except ApiError as error:
                    await db.rollback(); return error.status_code
        assert sorted(await asyncio.gather(decide(admin_ids[0], 'approve'), decide(admin_ids[1], 'reject'))) == [200, 409]
        async with factory() as db:
            row = await db.get(models.AdminMfaRecovery, row_id)
            owner = await db.get(models.AdminUser, target_id)
            assert row.status in ('approved', 'rejected') and row.decided_by in admin_ids and row.decision_note
            assert owner.auth_version == (1 if row.status == 'approved' else 0)
            events = (await db.scalars(select(models.AuditLog).where(models.AuditLog.action.in_(
                ('staff.mfa_recovery_approve', 'staff.mfa_recovery_reject'))))).all()
            assert len(events) == 1 and events[0].event_metadata['request_id'] == str(row_id)
        print('PostgreSQL temporal OK: migración idempotente, cuentas conservadas, solicitudes/confirmación/decisión concurrentes serializadas.')
    finally:
        await engine.dispose()


if __name__ == '__main__':
    asyncio.run(main())

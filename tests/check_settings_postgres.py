"""Carreras de configuración: solo base efímera phase1_test en puerto local 55439."""
import asyncio
import os
from uuid import uuid4

os.environ.update({
    'ADMIN_DATABASE_URL': 'postgresql+asyncpg://phase1_test:phase1_test@127.0.0.1:55439/phase1_test',
    'ADMIN_JWT_SECRET': 'settings-isolated-test-key-at-least-32-bytes',
    'ADMIN_ALLOWS_ORIGINS': 'http://localhost:5173',
    'ADMIN_MFA_REQUIRED_ROLES': '', 'ADMIN_MAIL_WORKER_ENABLED': 'false',
})
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, func
from app import database, models
from app.main import app
from app.security import create_access_token, hash_password


async def main():
    engine = database.get_engine()
    assert engine.url.database == 'phase1_test' and engine.url.port == 55439
    async with engine.begin() as connection:
        await connection.run_sync(database.Base.metadata.create_all)
    async with database.get_session_factory()() as db:
        user = models.AdminUser(email=f'{uuid4()}@wellq.co.uk', full_name='Prueba configuración', role='admin',
                                is_active=True, password_hash=hash_password('Prueba123!'))
        db.add(user); await db.commit()
        headers = {'Authorization': f'Bearer {create_access_token(user.id, user.role)}'}
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        for _ in range(5):
            key = f'concurrency_{uuid4().hex}'
            async with database.get_session_factory()() as db:
                db.add(models.SystemSetting(key=key, value=1, value_schema={'type': 'integer'},
                                           description='Prueba concurrente'))
                await db.commit()
            responses = await asyncio.gather(*[
                client.put(f'/api/v1/admin/settings/{key}', headers=headers,
                    json={'value': value, 'version': 1, 'change_note': 'Prueba simultánea'})
                for value in [2, 3]])
            assert sorted(response.status_code for response in responses) == [200, 409]
            winner = next(response.json() for response in responses if response.status_code == 200)
            assert next(response.json() for response in responses if response.status_code == 409)['error']['code'] == 'VERSION_CONFLICT'
            async with database.get_session_factory()() as db:
                row = await db.get(models.SystemSetting, key)
                assert row.version == 2 and row.value == winner['value']
        async with database.get_session_factory()() as db:
            assert await db.scalar(select(func.count()).select_from(models.AuditLog)) == 5
    await engine.dispose()
    print('PostgreSQL: 5 carreras de configuración aprobadas; un guardado y un conflicto por carrera.')


if __name__ == '__main__':
    asyncio.run(main())

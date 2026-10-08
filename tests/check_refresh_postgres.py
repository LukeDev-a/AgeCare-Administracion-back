"""Comprobación aislada. Solo acepta PostgreSQL local en el puerto de pruebas 55439.

No usa conftest ni seed. Ejecutar únicamente con un contenedor efímero propio.
"""
import asyncio
import os
from uuid import uuid4

os.environ.update({
    'ADMIN_DATABASE_URL': 'postgresql+asyncpg://phase1_test:phase1_test@127.0.0.1:55439/phase1_test',
    'ADMIN_JWT_SECRET': 'phase1-isolated-test-key-at-least-32-bytes',
    'ADMIN_ALLOWS_ORIGINS': 'http://localhost:5173',
    'ADMIN_MFA_REQUIRED_ROLES': '', 'ADMIN_MAIL_WORKER_ENABLED': 'false',
})

from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from app import database, models
from app.main import app
from app.security import hash_password


async def main():
    engine = database.get_engine()
    assert engine.url.database == 'phase1_test' and engine.url.port == 55439
    async with engine.begin() as connection:
        await connection.run_sync(database.Base.metadata.create_all)
    base = '/api/v1/admin'
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        for _ in range(5):
            async with database.get_session_factory()() as db:
                user = models.AdminUser(email=f'{uuid4()}@wellq.co.uk', full_name='Prueba aislada',
                    role='analyst', is_active=True, password_hash=hash_password('Prueba123!'))
                db.add(user); await db.commit()
                user_id, email = user.id, user.email
            credentials = {'email': email, 'password': 'Prueba123!'}
            login = (await client.post(f'{base}/auth/login', json=credentials)).json()
            other = (await client.post(f'{base}/auth/login', json=credentials)).json()
            responses = await asyncio.gather(*[
                client.post(f'{base}/auth/refresh', json={'refresh_token': login['refresh_token']})
                for _ in range(2)])
            assert sorted(response.status_code for response in responses) == [200, 401]
            fresh = next(response.json() for response in responses if response.status_code == 200)
            for tokens in [login, other, fresh]:
                assert (await client.get(f'{base}/auth/me', headers={
                    'Authorization': f"Bearer {tokens['access_token']}"})).status_code == 401
                assert (await client.post(f'{base}/auth/refresh', json={
                    'refresh_token': tokens['refresh_token']})).status_code == 401
            async with database.get_session_factory()() as db:
                sessions = (await db.scalars(select(models.AdminSession).where(
                    models.AdminSession.admin_id == user_id))).all()
                assert len(sessions) == 3 and all(session.revoked_at for session in sessions)
            assert (await client.post(f'{base}/auth/login', json=credentials)).status_code == 200
    await engine.dispose()
    print('PostgreSQL: 5 carreras verificadas; una rotación, rechazo de reutilización y revocación total.')


if __name__ == '__main__':
    asyncio.run(main())

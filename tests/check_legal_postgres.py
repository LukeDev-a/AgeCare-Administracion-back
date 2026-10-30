"""Carreras legales SOLO en una base temporal agecare_legal_check_* vacía."""
import asyncio
from datetime import timedelta
from starlette.requests import Request
from sqlalchemy import func, select, text

from app import database, models
from app.errors import ApiError
from app.legal_documents import current_version, earliest_major_date
from app.routers.system import create_legal_version, publish_legal_version
from app.schemas.system import LegalVersionCreateIn
from app.enums import LegalDocType
from app.security import now_utc


async def main():
    engine = database.get_engine()
    url = engine.url
    assert url.host == 'db' and url.username == 'agecare'
    assert url.database.startswith('agecare_legal_check_') and url.database != 'agecare_admin'
    async with engine.begin() as connection:
        assert not (await connection.execute(text("SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'"))).scalar()
        await connection.run_sync(database.Base.metadata.create_all)
    factory = database.get_session_factory()
    original_text = 'Texto original conservado. ' * 10
    async with factory() as db:
        admin = models.AdminUser(full_name='Prueba legal', email='legal-test@example.cl', role='admin', is_active=True)
        old = models.LegalVersion(doc_type='terms', semver='1.0', content_md=original_text, changelog='Versión previa',
                                  status='published', effective_date=now_utc().date()-timedelta(days=90), published_at=now_utc()-timedelta(days=100))
        db.add_all([admin, old]); await db.commit()
        admin_id, old_id = admin.id, old.id
    day = earliest_major_date(now_utc()) + timedelta(days=3)
    body = LegalVersionCreateIn(semver='1.1', content_md='Texto de prueba actualizado. ' * 10,
                                changelog='Actualización de prueba', effective_date=day)
    async def operation(create, identity=None):
        async with factory() as db:
            admin = await db.get(models.AdminUser, admin_id)
            request = Request({'type': 'http', 'method': 'POST', 'headers': []})
            request.state.actor = admin
            try:
                result = await create_legal_version(LegalDocType.terms, body, request, db, admin) if create else await publish_legal_version(identity, request, db, admin)
                await db.commit()
                return 201 if create else 200, result.version_id
            except ApiError as exc:
                await db.rollback()
                return exc.status_code, exc.code
    created = await asyncio.gather(operation(True), operation(True))
    assert sorted(row[0] for row in created) == [201, 409], created
    identity = next(row[1] for row in created if row[0] == 201)
    published = await asyncio.gather(operation(False, identity), operation(False, identity))
    assert sorted(row[0] for row in published) == [200, 409], published
    assert any(row[1] == 'ALREADY_PUBLISHED' for row in published)
    async with factory() as db:
        rows = (await db.scalars(select(models.LegalVersion))).all()
        assert len(rows) == 2 and current_version(rows, now_utc()).id == old_id
        assert next(row for row in rows if row.id == old_id).content_md == original_text
        assert await db.scalar(select(func.count()).select_from(models.AuditLog)) == 2
    await engine.dispose()
    print('PostgreSQL OK: creación/publicación simultáneas sin duplicados; vigente e histórico conservados. Solo base temporal.')


if __name__ == '__main__':
    asyncio.run(main())

from uuid import uuid4
import pytest
from sqlalchemy import select, func
from app import database, models
from app.config import get_settings
from app.security import hash_password

pytestmark = pytest.mark.asyncio
URL = '/api/v1/admin/content/candidates/import'


def post(**overrides):
    number = uuid4().int % 1000000000
    return {'id': number, 'title': {'rendered': f'Noticia importada {number}'},
        'content': {'rendered': '<p>Una noticia para revisar.</p><script>NO_INCLUIR</script>'},
        'link': f'https://www.cuentamealgobueno.com/noticia-{number}/',
        'date_gmt': '2026-11-15T12:00:00', 'modified_gmt': '2026-11-15T12:00:00',
        '_embedded': {'author': [{'name': 'Redacción'}]}, **overrides}


async def test_import_validates_deduplicates_and_audits_without_ai(client, admin_headers, monkeypatch):
    monkeypatch.setattr(get_settings(), 'content_worker_enabled', False)
    news = post()
    async with database._session_factory() as db:
        jobs_before = await db.scalar(select(func.count()).select_from(models.ContentJob))
        items_before = await db.scalar(select(func.count()).select_from(models.ContentItem))
    first = await client.post(URL, headers=admin_headers, json=[news, news])
    assert first.status_code == 200, first.text
    assert first.json() == {'candidates': 1, 'duplicates': 1, 'changed': 0}
    assert (await client.post(URL, headers=admin_headers, json=[news])).json()['candidates'] == 0
    async with database._session_factory() as db:
        row = await db.scalar(select(models.NewsCandidate).where(models.NewsCandidate.external_id == news['id']))
        assert row.rights_status == 'uncertain' and row.status == 'pending' and row.adaptation is None
        assert 'NO_INCLUIR' not in row.original_text and row.author == 'Redacción'
        assert await db.scalar(select(func.count()).select_from(models.ContentJob)) == jobs_before
        assert await db.scalar(select(func.count()).select_from(models.ContentItem)) == items_before
        event = await db.scalar(select(models.AuditLog).where(models.AuditLog.action == 'content.news_import').order_by(models.AuditLog.created_at.desc()))
        assert event.actor_id is not None and event.after['records'] > 0
        row.rights_status = 'own'; row.adaptation = {'body': 'Propuesta antigua'}
        await db.commit()
    changed = await client.post(URL, headers=admin_headers, json=[{**news, 'content': {'rendered': 'Contenido original actualizado'}}])
    assert changed.json()['changed'] == 1
    async with database._session_factory() as db:
        row = await db.scalar(select(models.NewsCandidate).where(models.NewsCandidate.external_id == news['id']))
        assert row.source_changed and row.rights_status == 'uncertain' and row.adaptation is None


@pytest.mark.parametrize('bad', [[], {}, [post(link='https://otro.example/noticia/')],
    [post(link='https://www.cuentamealgobueno.com.evil.example/')], [post(id=True)],
    [post(title={'rendered': ''})], [post(modified_gmt='fecha inválida')], [post()] * 101])
async def test_invalid_import_is_atomic(client, admin_headers, bad):
    valid = post()
    payload = [valid, *bad] if isinstance(bad, list) and bad and len(bad) < 101 else bad
    response = await client.post(URL, headers=admin_headers, json=payload)
    assert response.status_code == 422
    async with database._session_factory() as db:
        assert not await db.scalar(select(models.NewsCandidate.id).where(models.NewsCandidate.external_id == valid['id']))


async def test_import_rejects_html_size_and_missing_permissions(client, admin_headers, analyst_headers):
    assert (await client.post(URL, json=[post()])).status_code == 401
    assert (await client.post(URL, headers=analyst_headers, json=[post()])).status_code == 403
    assert (await client.post(URL, headers=admin_headers, content='<html>Cloudflare</html>')).status_code == 422
    assert (await client.post(URL, headers=admin_headers, content=b' ' * (2 * 1024 * 1024 + 1))).status_code == 413


async def test_editor_can_import(client):
    async with database._session_factory() as db:
        email = f'{uuid4()}@wellq.co.uk'
        db.add(models.AdminUser(full_name='Editor importador', email=email, role='editor',
            is_active=True, password_hash=hash_password('Prueba123!')))
        await db.commit()
    login = (await client.post('/api/v1/admin/auth/login', json={'email': email, 'password': 'Prueba123!'})).json()
    response = await client.post(URL, headers={'Authorization': f"Bearer {login['access_token']}"}, json=[post()])
    assert response.status_code == 200 and response.json()['candidates'] == 1

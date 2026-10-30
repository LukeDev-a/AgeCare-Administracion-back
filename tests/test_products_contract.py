from uuid import uuid4
import pytest
from app import database, models

BASE = '/api/v1/admin/marketplace/products'
pytestmark = pytest.mark.asyncio


def payload(**overrides):
    return {'name': 'Artículo ' + uuid4().hex, 'category': 'Bienestar', 'vendor': 'Proveedor',
            'external_url': 'https://example.cl/articulo', **overrides}


async def test_product_cycle_nulls_transitions_and_audit(client, admin_headers):
    created = await client.post(BASE, headers=admin_headers,
                                json=payload(price_clp=0, image_url='https://example.cl/imagen.png'))
    assert created.status_code == 201, created.text
    product = created.json()
    assert product['status'] == 'draft' and product['price_clp'] == 0
    path = BASE + '/' + product['id']
    invalid = await client.patch(path, headers=admin_headers, json={'status': 'archived', 'name': 'No debe cambiar'})
    assert invalid.status_code == 409 and invalid.json()['error']['code'] == 'INVALID_TRANSITION'
    published = await client.patch(path, headers=admin_headers, json={'status': 'published'})
    assert published.status_code == 200 and published.json()['name'] == product['name']
    cleared = await client.patch(path, headers=admin_headers, json={'price_clp': None, 'image_url': None})
    assert cleared.status_code == 200 and cleared.json()['price_clp'] is None and cleared.json()['image_url'] is None
    assert cleared.json()['external_url'] == product['external_url']
    assert (await client.patch(path, headers=admin_headers, json={'status': 'draft'})).status_code == 200
    assert (await client.patch(path, headers=admin_headers, json={'status': 'published'})).status_code == 200
    assert (await client.patch(path, headers=admin_headers, json={'status': 'archived'})).status_code == 200
    rejected = await client.patch(path, headers=admin_headers, json={'status': 'published', 'price_clp': 999})
    assert rejected.status_code == 409
    logs = (await client.get('/api/v1/admin/audit-log', headers=admin_headers,
                             params={'entity_id': product['id']})).json()['items']
    clearing = next(row for row in logs if row['before'] and row['before'].get('price_clp') == 0 and row['after'].get('price_clp') is None)
    assert clearing['before']['image_url'] and clearing['after']['image_url'] is None
    assert len(logs) == 6  # Creación + cinco cambios válidos; rechazos no se auditan como cambios.
    restored = await client.patch(path, headers=admin_headers, json={'status': 'draft'})
    assert restored.status_code == 200
    assert restored.json()['status'] == 'draft' and restored.json()['id'] == product['id']
    assert restored.json()['name'] == product['name'] and restored.json()['price_clp'] is None
    logs = (await client.get('/api/v1/admin/audit-log', headers=admin_headers,
                             params={'entity_id': product['id']})).json()['items']
    assert len(logs) == 7
    assert any(row['before'] and row['before']['status'] == 'archived'
               and row['after']['status'] == 'draft' for row in logs)
    assert (await client.patch(path, headers=admin_headers, json={'status': 'published'})).status_code == 200


@pytest.mark.parametrize('role', ['admin', 'editor', 'moderator', 'analyst', 'support', None])
async def test_restore_permissions_preserve_state_on_rejection(client, role):
    from app.security import create_access_token
    async with database._session_factory() as db:
        product = models.Product(name='Artículo archivado', category='Bienestar', vendor='Proveedor',
                                 external_url='https://example.cl/articulo', status='archived')
        actor = models.AdminUser(full_name='Gestor de prueba', email=f'{uuid4()}@example.cl', role=role or 'admin', is_active=True)
        db.add_all([product, actor]); await db.commit()
        product_id, actor_id = product.id, actor.id
    headers = {'Authorization': 'Bearer ' + create_access_token(actor_id, role)} if role else {}
    result = await client.patch(BASE + '/' + str(product_id), headers=headers, json={'status': 'draft'})
    allowed = role in ('admin', 'editor')
    assert result.status_code == (200 if allowed else 403 if role else 401), result.text
    async with database._session_factory() as db:
        current = await db.get(models.Product, product_id)
        assert current.status == ('draft' if allowed else 'archived')


@pytest.mark.parametrize('change', [
    {'name': '  '}, {'category': 'x'}, {'vendor': None}, {'external_url': 'http://example.cl/juego'},
    {'image_url': 'no-es-url'}, {'price_clp': -1}, {'price_clp': 1.5}, {'price_clp': True},
    {'status': 'published'}, {'images': ['https://example.cl/a.png']},
])
async def test_invalid_creation_has_no_product(client, admin_headers, change):
    body = payload(**change)
    before = (await client.get(BASE, headers=admin_headers)).json()['total']
    rejected = await client.post(BASE, headers=admin_headers, json=body)
    assert rejected.status_code == 422, rejected.text
    assert (await client.get(BASE, headers=admin_headers)).json()['total'] == before


async def test_publish_validates_legacy_required_fields_and_rejection_preserves_data(client, admin_headers):
    async with database._session_factory() as db:
        product = models.Product(name='Legado', category='Bienestar', vendor='Proveedor',
                                 external_url='http://example.cl/articulo', status='draft')
        db.add(product); await db.commit(); product_id = str(product.id)
    result = await client.patch(BASE + '/' + product_id, headers=admin_headers,
                                json={'status': 'published', 'name': 'Cambio rechazado'})
    assert result.status_code == 422 and result.json()['error']['code'] == 'INVALID_PRODUCT'
    current = (await client.get(BASE, headers=admin_headers, params={'q': 'Legado'})).json()['items']
    row = next(item for item in current if item['id'] == product_id)
    assert row['name'] == 'Legado' and row['status'] == 'draft'
    assert (await client.patch(BASE + '/' + product_id, headers=admin_headers,
                               json={'name': None})).status_code == 422


async def test_product_filters_and_pagination(client, admin_headers):
    marker = uuid4().hex
    for index in range(3):
        assert (await client.post(BASE, headers=admin_headers,
                                  json=payload(name=f'Artículo {index}', vendor=marker, category='Filtro especial'))).status_code == 201
    query = {'q': marker, 'category': 'especial', 'status': 'draft', 'page_size': 2}
    first = (await client.get(BASE, headers=admin_headers, params=query)).json()
    second = (await client.get(BASE, headers=admin_headers, params={**query, 'page': 2})).json()
    assert first['total'] == second['total'] == 3
    assert len(first['items']) == 2 and len(second['items']) == 1
    assert not {item['id'] for item in first['items']} & {item['id'] for item in second['items']}
    assert (await client.get(BASE, headers=admin_headers, params={**query, 'status': 'published'})).json()['items'] == []
    assert (await client.get(BASE)).status_code == 401  # Esta ruta sigue siendo administrativa.

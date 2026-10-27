from uuid import uuid4
import pytest
from app import database, models
from app.security import create_access_token

BASE = '/api/v1/admin'
pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize('role', ['admin', 'support', 'analyst', 'editor', 'moderator', None])
async def test_agent_picker_permission_and_minimal_fields(client, role):
    async with database._session_factory() as db:
        active = models.AdminUser(full_name='Responsable RF03', email=f'{uuid4()}@wellq.co.uk',
            role=role or 'support', is_active=True)
        inactive = models.AdminUser(full_name='Inactiva RF03', email=f'{uuid4()}@wellq.co.uk',
            role='support', is_active=False)
        db.add_all([active, inactive]); await db.commit()
        actor_id, inactive_id = str(active.id), str(inactive.id)
        headers = {'Authorization': 'Bearer ' + create_access_token(active.id, role)} if role else {}
    response = await client.get(BASE + '/support/agents', headers=headers)
    if role not in ('admin', 'support'):
        assert response.status_code == (401 if role is None else 403)
        return
    assert response.status_code == 200
    rows = response.json()
    assert all(set(row) == {'id', 'full_name'} for row in rows)
    assert any(row['id'] == actor_id for row in rows)
    assert all(row['id'] != inactive_id for row in rows)
    if role == 'support':
        assert (await client.get(BASE + '/users', headers=headers)).status_code == 403

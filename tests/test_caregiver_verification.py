from uuid import uuid4
import pytest
from sqlalchemy import select
from app import database, models
from app.security import hash_password

pytestmark = pytest.mark.asyncio


async def test_verification_is_visible_and_still_required_to_approve(client, admin_headers):
    prefix = f'Certificaciones-{uuid4()}'
    async with database._session_factory() as db:
        profiles = [models.CaregiverProfile(name=f'{prefix}-{verified}', email=f'{uuid4()}@example.org',
            zone='Centro', certifications_count=1, certifications_verified=verified, status='pending')
            for verified in (False, True)]
        db.add_all(profiles); await db.commit()
        ids = [row.id for row in profiles]
    base = '/api/v1/admin/marketplace/caregivers'
    response = await client.get(base, headers=admin_headers, params={'q': prefix})
    assert response.status_code == 200
    rows = {row['caregiver_id']: row for row in response.json()['items']}
    assert rows[str(ids[0])]['certifications_count'] == rows[str(ids[1])]['certifications_count'] == 1
    assert rows[str(ids[0])]['certifications_verified'] is False
    assert rows[str(ids[1])]['certifications_verified'] is True
    rejected = await client.patch(f'{base}/{ids[0]}', headers=admin_headers, json={'status': 'approved'})
    assert rejected.status_code == 409 and rejected.json()['error']['code'] == 'CERTIFICATION_REQUIRED'
    approved = await client.patch(f'{base}/{ids[1]}', headers=admin_headers, json={'status': 'approved'})
    assert approved.status_code == 200 and approved.json()['certifications_verified'] is True
    async with database._session_factory() as db:
        assert (await db.scalar(select(models.CaregiverProfile).where(models.CaregiverProfile.id == ids[0]))).status == 'pending'


async def test_internal_notes_permissions_round_trip_and_independent_update(client, admin_headers):
    async with database._session_factory() as db:
        profile = models.CaregiverProfile(name=f'Notas-{uuid4()}', email=f'{uuid4()}@example.org', zone='Centro',
            certifications_count=1, certifications_verified=False, status='pending', internal_note='Nota anterior')
        db.add(profile)
        emails = {}
        for role in ('editor', 'moderator'):
            emails[role] = f'{uuid4()}@wellq.co.uk'
            db.add(models.AdminUser(full_name=role, email=emails[role], role=role,
                is_active=True, password_hash=hash_password('Prueba123!')))
        await db.commit(); profile_id = profile.id; name = profile.name
    headers = {'admin': admin_headers}
    for role, email in emails.items():
        session = (await client.post('/api/v1/admin/auth/login', json={'email': email, 'password': 'Prueba123!'})).json()
        headers[role] = {'Authorization': f"Bearer {session['access_token']}"}
    base = '/api/v1/admin/marketplace/caregivers'
    for role in ('admin', 'editor', 'moderator'):
        rows = (await client.get(base, headers=headers[role], params={'q': name})).json()['items']
        assert rows[0]['internal_note'] == (None if role == 'moderator' else 'Nota anterior')
    assert (await client.patch(f'{base}/{profile_id}', headers=headers['moderator'], json={'internal_note': 'No autorizado'})).status_code == 403
    changed = await client.patch(f'{base}/{profile_id}', headers=headers['editor'], json={'internal_note': 'Nota nueva de seguimiento'})
    assert changed.status_code == 200 and changed.json()['internal_note'] == 'Nota nueva de seguimiento'
    assert changed.json()['status'] == 'pending' and changed.json()['certifications_verified'] is False
    assert (await client.patch(f'{base}/{profile_id}', headers=admin_headers, json={'internal_note': 'X' * 2001})).status_code == 422
    async with database._session_factory() as db:
        row = await db.get(models.CaregiverProfile, profile_id)
        assert row.internal_note == 'Nota nueva de seguimiento' and row.status_reason is None
        audit = await db.scalar(select(models.AuditLog).where(models.AuditLog.action == 'marketplace.caregiver_update',
            models.AuditLog.entity_id == profile_id))
        assert audit.before['internal_note'] == 'Nota anterior'
        assert audit.after['internal_note'] == 'Nota nueva de seguimiento' and audit.actor_role == 'editor'
    cleared = await client.patch(f'{base}/{profile_id}', headers=admin_headers, json={'internal_note': ''})
    assert cleared.status_code == 200 and cleared.json()['internal_note'] == ''

"""Datos de prueba explícitos, sin registro/login ni sesiones móviles."""
from uuid import NAMESPACE_URL, uuid5
from sqlalchemy import select, text
from app import models
from app.config import get_settings
from app.end_user_samples import ACCOUNTS, PATIENTS


def demo_available() -> bool:
    settings = get_settings()
    return settings.environment.strip().lower() == 'dev' and settings.end_users_demo_enabled


def demo_id(key):
    return uuid5(NAMESPACE_URL, 'agecare:phase18:demo:' + key)


async def seed_demo_directory(db):
    """Conservar el grupo completo si cualquiera de sus tablas tiene datos."""
    if not demo_available():
        return False
    if db.bind.dialect.name == 'postgresql':
        await db.execute(text('SELECT pg_advisory_xact_lock(724018, 1)'))
    for model in (models.AppAccount, models.AppPatient, models.AppMembership):
        if await db.scalar(select(model.id).limit(1)) is not None:
            return False
    users = [models.AppAccount(id=demo_id(f'user-{i}'), full_name=name,
                                email=email, is_active=i != 32) for i, (name, email) in enumerate(ACCOUNTS, 1)]
    patients = [models.AppPatient(id=demo_id(f'patient-{i}'), full_name=name) for i, name in enumerate(PATIENTS, 1)]
    db.add_all(users + patients)
    await db.flush()
    links = [(1, 1, 'family', True), (1, 2, 'caregiver', False), (1, 3, 'doctor', False), (1, 4, 'elder', False),
             (2, 1, 'caregiver', False), (2, 5, 'family', True), (2, 6, 'elder', False),
             (3, 7, 'elder', True), (3, 2, 'caregiver', False), (3, 3, 'doctor', False),
             (4, 8, 'family', True), (4, 32, 'caregiver', False), (4, 21, 'elder', False),
             (5, 9, 'family', True), (5, 20, 'elder', False),
             (6, 10, 'family', True), (6, 25, 'elder', False),
             (7, 26, 'elder', True), (8, 11, 'family', True)]
    db.add_all([models.AppMembership(id=demo_id(f'link-{p}-{u}'), patient_id=demo_id(f'patient-{p}'),
                user_id=demo_id(f'user-{u}'), role=role, is_owner=owner) for p, u, role, owner in links])
    return True

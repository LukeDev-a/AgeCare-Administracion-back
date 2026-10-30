"""Datos de prueba explícitos, sin registro/login ni sesiones móviles."""
from uuid import NAMESPACE_URL, uuid5
from sqlalchemy import select, text
from app import models
from app.config import get_settings


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
    for model in (models.DemoEndUser, models.DemoPatient, models.DemoPatientMember):
        if await db.scalar(select(model.id).limit(1)) is not None:
            return False
    users = [models.DemoEndUser(id=demo_id(f'user-{i}'), full_name=f'Persona de prueba {i:02}',
                                email=f'persona{i:02}@example.test', is_active=i != 32) for i in range(1, 33)]
    patients = [models.DemoPatient(id=demo_id(f'patient-{i}'), full_name=f'Paciente de prueba {i:02}') for i in range(1, 8)]
    db.add_all(users + patients)
    await db.flush()
    links = [(1, 1, 'family', True), (1, 2, 'caregiver', False), (1, 3, 'doctor', False), (1, 4, 'elder', False),
             (2, 1, 'caregiver', False), (2, 5, 'family', True), (2, 6, 'elder', False),
             (3, 7, 'family', True), (3, 2, 'caregiver', False), (3, 3, 'doctor', False),
             (4, 8, 'family', True), (4, 32, 'caregiver', False), (5, 9, 'family', True), (6, 10, 'family', True)]
    db.add_all([models.DemoPatientMember(id=demo_id(f'link-{p}-{u}'), patient_id=demo_id(f'patient-{p}'),
                user_id=demo_id(f'user-{u}'), role=role, is_owner=owner) for p, u, role, owner in links])
    return True

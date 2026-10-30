"""Calendario y orden de versiones legales; no gestiona consentimientos móviles."""
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
from sqlalchemy import select, text

from app import models
from app.errors import conflict, invalid
from app.security import as_utc

LEGAL_ZONE = ZoneInfo('America/Santiago')
MAJOR_NOTICE_DAYS = 15


def semver(value: str) -> tuple[int, int]:
    major, minor = value.split('.')
    return int(major), int(minor)


def effective_at(day: date) -> datetime:
    return datetime.combine(day, time.min, LEGAL_ZONE).astimezone(timezone.utc)


def earliest_major_date(now: datetime) -> date:
    deadline = as_utc(now) + timedelta(days=MAJOR_NOTICE_DAYS)
    day = deadline.astimezone(LEGAL_ZONE).date()
    while effective_at(day) < deadline:
        day += timedelta(days=1)
    return day


async def versions(db, doc_type, lock=False):
    if lock and db.get_bind().dialect.name == 'postgresql':
        # Serializa por documento, incluso si aún no existe ninguna versión.
        await db.execute(text('SELECT pg_advisory_xact_lock(:namespace, :document)'),
                         {'namespace': 724016, 'document': 1 if doc_type == 'terms' else 2})
    statement = select(models.LegalVersion).where(models.LegalVersion.doc_type == doc_type)
    if lock:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    return (await db.scalars(statement)).all()


def current_version(rows, now):
    eligible = [row for row in rows if row.status == 'published' and effective_at(row.effective_date) <= as_utc(now)]
    return max(eligible, key=lambda row: semver(row.semver)) if eligible else None


def validate_schedule(rows, number: str, day: date, now: datetime, exclude_id=None):
    others = [row for row in rows if row.id != exclude_id]
    published = [row for row in others if row.status == 'published']
    latest = max(published, key=lambda row: semver(row.semver)) if published else None
    if (latest and semver(number) <= semver(latest.semver)) or any(semver(row.semver) == semver(number) for row in others):
        raise conflict('SEMVER_NOT_GREATER', 'La versión debe ser nueva y superior a todas las versiones publicadas, incluidas las programadas.')
    if day < as_utc(now).astimezone(LEGAL_ZONE).date():
        raise conflict('EFFECTIVE_DATE_PAST', 'La fecha de vigencia ya pasó; crea un borrador con una fecha válida.')
    if latest and day <= latest.effective_date:
        raise conflict('EFFECTIVE_DATE_ORDER', 'La fecha debe ser posterior a la de la última versión publicada o programada.')
    major = latest is None or semver(number)[0] > semver(latest.semver)[0]
    if major and effective_at(day) < as_utc(now) + timedelta(days=MAJOR_NOTICE_DAYS):
        raise invalid('NOTICE_PERIOD', 'El cambio mayor exige 15 días completos desde la publicación. '
                      f'La primera fecha disponible hoy es {earliest_major_date(now).isoformat()} (Santiago).')
    return major

"""Ejemplos reproducibles de moderación. Añade faltantes; nunca reinicia decisiones."""
import argparse
import asyncio
from datetime import datetime, timedelta, timezone
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select, func
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app import models
from app.config import get_settings
from app.database_urls import normalize_database_url, database_connect_args

PREFIX = 'agecare-moderation-practice-v1-'
START = datetime(2026, 11, 1, 13, tzinfo=timezone.utc)
NAMES = ['Ana Rojas', 'Luis Soto', 'Carmen Vidal', 'Pedro Lagos', 'Elena Muñoz', 'Mario Fuentes']
REVIEWS = [
    ('El servicio fue puntual y explicó cada paso con paciencia.', 'Revisar antes de incorporar la reseña.'),
    ('La atención fue cordial, pero la visita comenzó más tarde de lo acordado.', 'Comprobar que la crítica se expresa de manera respetuosa.'),
    ('Visita nuestra tienda y aprovecha descuentos. Escríbenos para conocer ofertas.', 'Posible publicidad ajena al servicio reseñado.'),
    ('Incluyo un número de contacto de otra persona sin pedirle autorización.', 'Posible divulgación de información personal; revisar privacidad.'),
    ('La reseña incluye descalificaciones personales sobre quien prestó la atención.', 'Revisar el lenguaje y el trato respetuoso.'),
    ('Este comentario habla de un tema sin relación con el servicio recibido.', 'El texto podría estar fuera de tema.'),
]


def dataset():
    rows = []
    for index in range(60):
        status = 'pending' if index < 36 else 'approved' if index < 48 else 'rejected'
        kind = ('photo' if index in (30, 32, 34) else 'chat_message' if index in (31, 33, 35)
                else 'review' if index % 2 == 0 else 'caregiver_profile')
        text, report = REVIEWS[(index // 2) % len(REVIEWS)]
        name = NAMES[index % len(NAMES)]
        content = ({'text': text, 'rating': index % 6} if kind == 'review' else
            {'name': name, 'description': 'Acompañamiento y apoyo en actividades diarias. Disponibilidad por las tardes.',
             'specialties': ['Acompañamiento', 'Movilidad'], 'zone': ['Ñuñoa', 'Providencia', 'Santiago'][index % 3]} if kind == 'caregiver_profile' else {})
        created = START + timedelta(hours=index * 4)
        rejected = status == 'rejected'
        reason = ['offensive', 'spam', 'privacy', 'off_topic', 'other'][index % 5] if rejected else None
        rows.append(dict(id=uuid5(NAMESPACE_URL, PREFIX + str(index)), type=kind, content=content,
            author_user_id=None, author_name=name, author_role='family' if kind == 'review' else 'caregiver',
            reported_by={'name': 'Equipo de atención'} if index % 3 else None,
            report_reason=report if kind == 'review' else 'Revisar la presentación del perfil y su información pública.' if kind == 'caregiver_profile' else 'Consulta de disponibilidad de contenido protegido.',
            is_safety=index % 7 == 0, status=status, reject_reason_code=reason,
            decision_note=('Contenido revisado y aceptado.' if status == 'approved' else
                'Se rechazó tras revisar el motivo y el contexto del reporte.' if rejected else None),
            decided_by=None, decided_by_name='Equipo de revisión' if status != 'pending' else None,
            decided_at=created + timedelta(hours=2) if status != 'pending' else None, created_at=created))
    return rows


async def load_demo(db):
    rows = dataset()
    existing = set((await db.scalars(select(models.ModerationItem.id).where(
        models.ModerationItem.id.in_([row['id'] for row in rows])))).all())
    missing = [row for row in rows if row['id'] not in existing]
    db.add_all([models.ModerationItem(**row) for row in missing])
    await db.flush()
    return {'added': len(missing), 'preserved': len(existing)}


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', choices=['local', 'neon'], default='local')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    if get_settings().environment != 'dev':
        raise ValueError('Esta carga está limitada al entorno de desarrollo.')
    if args.target == 'neon':
        from scripts.create_editor_accounts import render_value
        url = normalize_database_url(render_value('ADMIN_DATABASE_URL'))
        parsed = make_url(url)
        if not (parsed.host or '').endswith('.neon.tech') or not (parsed.username or '').startswith('agecare_api_'):
            raise ValueError('Se requiere el perfil limitado de Neon existente.')
    else:
        url = 'postgresql+asyncpg://agecare:agecare@localhost:5432/agecare_admin'
    engine = create_async_engine(url, hide_parameters=True, connect_args=database_connect_args(url))
    try:
        async with async_sessionmaker(engine)() as db:
            before = dict((await db.execute(select(models.ModerationItem.status,
                func.count()).group_by(models.ModerationItem.status))).all())
            print('Destino:', args.target, 'Estado anterior:', before)
            if args.apply:
                result = await load_demo(db)
                await db.commit()
                print('Carga confirmada:', result)
            else:
                ids = [row['id'] for row in dataset()]
                existing = await db.scalar(select(func.count()).select_from(models.ModerationItem).where(models.ModerationItem.id.in_(ids)))
                print('Vista previa: faltan', len(ids) - existing, 'ejemplos. Sin cambios.')
            after = dict((await db.execute(select(models.ModerationItem.status,
                func.count()).group_by(models.ModerationItem.status))).all())
            print('Estado final:', after)
    finally:
        await engine.dispose()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except Exception as exc:
        print('Operación detenida:', type(exc).__name__)
        raise SystemExit(1) from None

"""Almacenamiento administrativo de pagos simulados. No ejecuta operaciones externas."""
from datetime import timedelta
from uuid import UUID
from fastapi import APIRouter, Request
from sqlalchemy import func, select, text
from app import models
from app.audit import audit
from app.deps import Db, require
from app.errors import conflict, invalid, not_found
from app.routers.end_users import require_demo
from app.schemas.payments import PaymentOperation
from app.security import as_utc, now_utc

router = APIRouter(prefix='/payments', tags=['Pagos y suscripciones'])


async def result(db):
    rows = (await db.execute(select(models.PaymentSubscription, models.AppAccount)
        .join(models.AppAccount, models.AppAccount.id == models.PaymentSubscription.user_id)
        .order_by(models.PaymentSubscription.code))).all()
    subscriptions = []
    identities = {}
    for s, account in rows:
        identity = dict(userId=str(account.id), accountActive=account.is_active,
                        name=account.full_name, email=account.email, plan=s.plan)
        identities[s.id] = identity
        subscriptions.append(dict(id=str(s.id), code=s.code, **identity, price=s.price, state=s.state,
            startedAt=as_utc(s.started_at), endsAt=as_utc(s.ends_at), version=s.version, history=s.history))
    charges = [dict(id=str(c.id), code=c.code, subscriptionId=str(c.subscription_id), **identities[c.subscription_id],
        amount=c.amount, state=c.state, at=as_utc(c.charged_at), version=c.version, history=c.history)
        for c in (await db.scalars(select(models.PaymentCharge).order_by(models.PaymentCharge.code))).all()]
    return dict(subscriptions=subscriptions, charges=charges, data_origin='demo')


@router.get('')
async def read_payments(request: Request, db: Db, admin: models.AdminUser = require('staff')):
    require_demo()
    await audit(db, request, 'payments.read', 'payment_dataset', actor=admin)
    return await result(db)


@router.post('/initialize')
async def initialize(request: Request, db: Db, admin: models.AdminUser = require('staff', write=True)):
    require_demo()
    if db.bind.dialect.name == 'postgresql':
        await db.execute(text('SELECT pg_advisory_xact_lock(724019, 1)'))
    if await db.scalar(select(func.count()).select_from(models.PaymentSubscription)):
        return await result(db)
    if await db.scalar(select(func.count()).select_from(models.PaymentCharge)):
        raise conflict('PAYMENT_DATA_CONFLICT', 'Hay cobros existentes. No se reemplazaron los datos.')
    accounts = (await db.scalars(select(models.AppAccount).order_by(models.AppAccount.id))).all()
    now = now_utc()
    for i, account in enumerate(accounts):
        s = models.PaymentSubscription(code=f'SUS-{i+1:04d}', user_id=account.id,
            plan=['Dorado', 'Platino', 'Proveedor'][i % 3], price=[3990, 6990, 9990][i % 3],
            state='cancelled' if not account.is_active or i in (5, 10) else 'past_due' if i in (3, 8) else 'active',
            started_at=now-timedelta(days=60+i), ends_at=now+timedelta(days=-2 if i in (3, 8) else 2+i*2),
            version=1, history=[], data_origin='demo')
        db.add(s)
        await db.flush()
        for j in range(2):
            db.add(models.PaymentCharge(code=f'COB-{i*2+j+1:04d}', subscription_id=s.id,
                amount=s.price, state=('pending' if s.state == 'past_due' else 'approved') if j == 0
                    else 'refunded' if i == 2 else 'failed' if i == 8 else 'approved',
                charged_at=now-timedelta(days=i if j == 0 else 32+i), version=1, history=[], data_origin='demo'))
    await db.flush()
    if accounts:
        await audit(db, request, 'payments.initialize', 'payment_dataset', actor=admin,
                    after={'subscriptions': len(accounts), 'charges': len(accounts)*2, 'data_origin': 'demo'})
    return await result(db)


@router.post('/{kind}/{record_id}/operate')
async def operate(kind: str, record_id: UUID, body: PaymentOperation, request: Request, db: Db,
                  admin: models.AdminUser = require('staff', write=True)):
    require_demo()
    if kind not in ('subscriptions', 'charges'):
        raise not_found()
    if not body.confirmed or (kind == 'charges') != (body.action == 'refund'):
        raise invalid('PAYMENT_CONFIRMATION_REQUIRED', 'Confirma una operación válida para este registro.')
    if body.action != 'extend' and body.days is not None:
        raise invalid('INVALID_PAYMENT_DAYS', 'Los días adicionales solo se utilizan al extender.')
    if body.action == 'extend' and body.days is None:
        raise invalid('INVALID_PAYMENT_DAYS', 'Indica entre 1 y 90 días completos.')
    model = models.PaymentCharge if kind == 'charges' else models.PaymentSubscription
    row = await db.scalar(select(model).where(model.id == record_id).with_for_update().execution_options(populate_existing=True))
    if row is None:
        raise not_found()
    if row.version != body.version:
        raise conflict('VERSION_CONFLICT', 'El registro cambió. Recarga su estado antes de continuar.')
    if row.data_origin != 'demo':
        raise conflict('PAYMENT_SOURCE_CONFLICT', 'Este registro no permite operaciones simuladas.')
    if kind == 'charges' and row.state != 'approved':
        raise conflict('PAYMENT_NOT_REFUNDABLE', 'Solo puedes reembolsar un cobro aprobado, una vez.')
    if kind == 'subscriptions' and row.state == 'cancelled':
        raise conflict('SUBSCRIPTION_CANCELLED', 'Esta suscripción ya tiene la renovación cancelada.')
    before = {'state': row.state, 'version': row.version}
    if kind == 'subscriptions':
        before['ends_at'] = as_utc(row.ends_at).isoformat()
    if body.action == 'cancel':
        row.state = 'cancelled'
        description = 'Renovación cancelada'
    elif body.action == 'extend':
        row.ends_at = as_utc(row.ends_at) + timedelta(days=body.days)
        description = f'Acceso extendido {body.days} días'
    else:
        row.state = 'refunded'
        description = f'Reembolso completo de ${row.amount:,}'.replace(',', '.')
    row.version += 1
    row.history = [*row.history, dict(at=now_utc().isoformat(), actor=admin.full_name,
        actor_id=str(admin.id), description=description, reason=body.reason)]
    after = {'state': row.state, 'version': row.version, 'reason': body.reason, 'data_origin': 'demo'}
    if kind == 'subscriptions':
        after['ends_at'] = as_utc(row.ends_at).isoformat()
    await audit(db, request, f'payments.{body.action}', f'payment_{kind}', row.id,
                actor=admin, before=before, after=after)
    await db.flush()
    return await result(db)

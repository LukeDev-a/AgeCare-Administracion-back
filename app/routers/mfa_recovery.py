from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import func, select

from app import models
from app.deps import Db, require
from app.errors import conflict, invalid, not_found, unauthorized
from app.mfa_recovery import confirm_recovery, current, decide, request_recovery
from app.routers.account_access import MfaProofIn, TokenIn, verify_proof
from app.routers.auth import lock_staff_for_change
from app.security import as_utc

router = APIRouter(tags=['Recuperación de acceso MFA'])


class RecoveryRequestIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)
    reason: str = Field(min_length=5, max_length=500)

    @field_validator('reason')
    @classmethod
    def trim_reason(cls, value):
        value = value.strip()
        if len(value) < 5:
            raise ValueError('Indica un motivo de 5–500 caracteres.')
        return value


class RecoveryDecisionIn(MfaProofIn):
    decision: Literal['approve', 'reject']
    identity_verified: bool = False
    note: str = Field(min_length=5, max_length=500)

    @field_validator('note')
    @classmethod
    def trim_note(cls, value):
        return RecoveryRequestIn.trim_reason(value)


@router.post('/auth/mfa-recovery/request', status_code=202)
async def request_endpoint(body: RecoveryRequestIn, request: Request, response: Response, db: Db):
    response.headers['Cache-Control'] = 'no-store'
    await request_recovery(db, str(body.email), body.password, body.reason, request)
    return {'message': 'Si los datos corresponden a una cuenta habilitada, recibirás un enlace para confirmar la solicitud.'}


@router.post('/auth/mfa-recovery/confirm')
async def confirm_endpoint(body: TokenIn, request: Request, response: Response, db: Db):
    response.headers['Cache-Control'] = 'no-store'
    await confirm_recovery(db, body.token, request)
    return {'confirmed': True}


@router.get('/mfa-recovery/requests')
async def list_requests(db: Db, response: Response, page: int = Query(1, ge=1),
                        admin: models.AdminUser = require('staff')):
    response.headers['Cache-Control'] = 'no-store'
    total = await db.scalar(select(func.count()).select_from(models.AdminMfaRecovery).where(
        models.AdminMfaRecovery.confirmed_at.is_not(None)))
    rows = (await db.execute(select(models.AdminMfaRecovery, models.AdminUser).join(models.AdminUser,
        models.AdminMfaRecovery.admin_id == models.AdminUser.id).where(models.AdminMfaRecovery.confirmed_at.is_not(None))
        .order_by(models.AdminMfaRecovery.confirmed_at.desc(), models.AdminMfaRecovery.id).offset((page - 1) * 25).limit(25))).all()
    return {'total': total, 'items': [{'id': row.id, 'admin_id': user.id, 'full_name': user.full_name,
        'email': user.email, 'reason': row.reason, 'status': row.status if row.status != 'pending' or current(row, user) else 'expired',
        'confirmed_at': as_utc(row.confirmed_at), 'expires_at': as_utc(row.expires_at),
        'decided_at': as_utc(row.decided_at) if row.decided_at else None, 'decided_by_name': row.decided_by_name,
        'decision_note': row.decision_note, 'can_decide': row.status == 'pending' and user.id != admin.id and current(row, user)}
        for row, user in rows]}


@router.post('/mfa-recovery/requests/{recovery_id}/decision')
async def decision_endpoint(recovery_id: UUID, body: RecoveryDecisionIn, request: Request, response: Response, db: Db,
                            actor: models.AdminUser = require('staff', write=True)):
    response.headers['Cache-Control'] = 'no-store'
    version = actor.auth_version
    await lock_staff_for_change(db, actor)
    if actor.auth_version != version:
        raise unauthorized()
    row = await db.scalar(select(models.AdminMfaRecovery).where(models.AdminMfaRecovery.id == recovery_id).with_for_update())
    if row is None:
        raise not_found()
    user = await db.get(models.AdminUser, row.admin_id)
    if user is None:
        raise not_found()
    if row.status != 'pending' or not current(row, user):
        raise conflict('MFA_RECOVERY_NOT_PENDING', 'La solicitud ya fue resuelta, venció o dejó de ser válida.')
    if user.id == actor.id:
        raise conflict('CANNOT_RECOVER_SELF', 'Otro administrador debe revisar tu solicitud.')
    if body.decision == 'approve' and not body.identity_verified:
        raise invalid('IDENTITY_VERIFICATION_REQUIRED', 'Debes verificar la identidad del solicitante antes de aprobar.')
    await verify_proof(db, actor, body, second_factor=actor.mfa_enabled)
    await decide(db, row, user, actor, body.decision == 'approve', body.note, request)
    return {'status': row.status}

"""Fase 18 demo. No administra identidades ni sesiones móviles reales."""
from uuid import UUID
from fastapi import APIRouter, Query, Request
from sqlalchemy import exists, func, or_, select
from app import models
from app.audit import audit
from app.deps import Db, require
from app.end_users_demo import demo_available
from app.errors import ApiError, conflict, invalid, not_found
from app.schemas.end_users import (DeactivateIn, DeactivateOut, EndUserDetailOut, EndUserOut,
                                  EndUserPage, MembershipOut, PatientDetailOut, PatientMemberOut,
                                  PatientOut, PatientPage)
from app.security import as_utc, now_utc

router = APIRouter(tags=['Usuarios y pacientes · demostración'])


def require_demo():
    if not demo_available():
        raise ApiError(503, 'END_USERS_UNAVAILABLE', 'El servicio de usuarios móviles aún no está conectado. La demostración solo puede habilitarse en desarrollo.')


def pattern(q):
    return '%' + q.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'


async def user_summary(db, user):
    count = await db.scalar(select(func.count()).select_from(models.DemoPatientMember)
                             .where(models.DemoPatientMember.user_id == user.id))
    return EndUserOut(user_id=user.id, full_name=user.full_name, email=user.email,
                      is_active=user.is_active, memberships_count=count)


async def user_detail(db, user):
    rows = (await db.execute(select(models.DemoPatientMember, models.DemoPatient)
                            .join(models.DemoPatient, models.DemoPatient.id == models.DemoPatientMember.patient_id)
                            .where(models.DemoPatientMember.user_id == user.id)
                            .order_by(models.DemoPatient.full_name, models.DemoPatient.id))).all()
    return EndUserDetailOut(user_id=user.id, full_name=user.full_name, email=user.email, is_active=user.is_active,
        memberships_count=len(rows), memberships=[MembershipOut(patient_id=p.id, patient_name=p.full_name,
            role=m.role, is_owner=m.is_owner) for m, p in rows],
        deactivated_at=as_utc(user.deactivated_at), deactivation_reason=user.deactivation_reason)


@router.get('/end-users', response_model=EndUserPage)
async def list_users(request: Request, db: Db, admin: models.AdminUser = require('end_users'),
                     q: str | None = Query(None, max_length=120), is_active: bool | None = None,
                     page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100)):
    require_demo()
    stmt = select(models.DemoEndUser)
    if q and q.strip():
        query = pattern(q.strip())
        stmt = stmt.where(or_(models.DemoEndUser.full_name.ilike(query, escape='\\'),
                              models.DemoEndUser.email.ilike(query, escape='\\')))
    if is_active is not None:
        stmt = stmt.where(models.DemoEndUser.is_active == is_active)
    total = await db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = (await db.scalars(stmt.order_by(models.DemoEndUser.full_name, models.DemoEndUser.id)
                             .offset((page-1)*page_size).limit(page_size))).all()
    result = EndUserPage(items=[await user_summary(db, row) for row in rows], total=total, page=page, page_size=page_size)
    await audit(db, request, 'end_users.demo_list', 'demo_app_account', actor=admin,
                metadata={'page': page, 'page_size': page_size})
    return result


@router.get('/end-users/{user_id}', response_model=EndUserDetailOut)
async def get_user(user_id: UUID, request: Request, db: Db, admin: models.AdminUser = require('end_users')):
    require_demo()
    user = await db.get(models.DemoEndUser, user_id)
    if user is None:
        raise not_found()
    result = await user_detail(db, user)
    await audit(db, request, 'end_users.demo_read', 'demo_app_account', user.id, actor=admin)
    return result


@router.get('/patients', response_model=PatientPage)
async def list_patients(request: Request, db: Db, admin: models.AdminUser = require('end_users'),
                        q: str | None = Query(None, max_length=120),
                        page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100)):
    require_demo()
    stmt = select(models.DemoPatient)
    if q and q.strip():
        query = pattern(q.strip())
        linked_email = exists(select(models.DemoPatientMember.id).join(models.DemoEndUser,
            models.DemoEndUser.id == models.DemoPatientMember.user_id).where(
                models.DemoPatientMember.patient_id == models.DemoPatient.id,
                models.DemoEndUser.email.ilike(query, escape='\\')))
        stmt = stmt.where(or_(models.DemoPatient.full_name.ilike(query, escape='\\'), linked_email))
    total = await db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = (await db.scalars(stmt.order_by(models.DemoPatient.full_name, models.DemoPatient.id)
                             .offset((page-1)*page_size).limit(page_size))).all()
    items = []
    for row in rows:
        count = await db.scalar(select(func.count()).select_from(models.DemoPatientMember)
                               .where(models.DemoPatientMember.patient_id == row.id))
        items.append(PatientOut(patient_id=row.id, full_name=row.full_name, members_count=count))
    await audit(db, request, 'patients.demo_list', 'demo_app_patient', actor=admin,
                metadata={'page': page, 'page_size': page_size})
    return PatientPage(items=items, total=total, page=page, page_size=page_size)


@router.get('/patients/{patient_id}', response_model=PatientDetailOut)
async def get_patient(patient_id: UUID, request: Request, db: Db, admin: models.AdminUser = require('end_users')):
    require_demo()
    patient = await db.get(models.DemoPatient, patient_id)
    if patient is None:
        raise not_found()
    rows = (await db.execute(select(models.DemoPatientMember, models.DemoEndUser).join(models.DemoEndUser,
                            models.DemoEndUser.id == models.DemoPatientMember.user_id)
                            .where(models.DemoPatientMember.patient_id == patient.id)
                            .order_by(models.DemoEndUser.full_name, models.DemoEndUser.id))).all()
    result = PatientDetailOut(patient_id=patient.id, full_name=patient.full_name, members_count=len(rows),
        members=[PatientMemberOut(user_id=u.id, full_name=u.full_name, email=u.email, role=m.role,
                                  is_owner=m.is_owner, is_active=u.is_active) for m, u in rows])
    await audit(db, request, 'patients.demo_read', 'demo_app_patient', patient.id, actor=admin)
    return result


@router.post('/end-users/{user_id}/deactivate', response_model=DeactivateOut)
async def deactivate_user(user_id: UUID, body: DeactivateIn, request: Request, db: Db,
                          admin: models.AdminUser = require('end_users', write=True)):
    require_demo()
    if body.confirmation_user_id != user_id:
        raise invalid('CONFIRMATION_MISMATCH', 'La confirmación no corresponde a la cuenta seleccionada.')
    user = await db.scalar(select(models.DemoEndUser).where(models.DemoEndUser.id == user_id)
                           .with_for_update().execution_options(populate_existing=True))
    if user is None:
        raise not_found()
    if not user.is_active:
        raise conflict('ACCOUNT_ALREADY_INACTIVE', 'Esta cuenta de prueba ya está desactivada.')
    user.is_active = False
    user.deactivated_at = now_utc()
    user.deactivated_by = admin.id
    user.deactivation_reason = body.reason
    await audit(db, request, 'end_users.demo_deactivate', 'demo_app_account', user.id, actor=admin,
                before={'name': user.full_name, 'is_active': True},
                after={'name': user.full_name, 'is_active': False, 'reason': body.reason, 'effect': 'demo_only'})
    await db.flush()
    result = DeactivateOut(user=await user_detail(db, user))
    await db.commit()  # Estado y auditoría confirmados antes de que la UI recargue.
    return result

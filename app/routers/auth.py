"""Sección 3 — Autenticación y gestión del staff."""
from datetime import timedelta
from math import ceil
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import delete, func, select, update

from app import models
from app.audit import audit
from app.login_attempts import is_locked, record_failure, reset_attempts
from app.account_security import check_second_factor, requires_mfa
from app.routers.account_access import create_enrollment, issue_invitation
from app.config import get_settings
from app.deps import CurrentAdmin, Db, permissions_for, require
from app.enums import AdminRole
from app.errors import ApiError, conflict, forbidden, invalid, not_found, unauthorized
from app.schemas.auth import (AdminCreateIn, AdminCreateOut, AdminPatchIn, AdminUserOut,
                              LoginIn, LoginOut, MeOut, RefreshIn, RefreshOut)
from app.schemas.common import Page
from app.security import (as_utc, create_access_token, hash_refresh, new_refresh_token,
                          hash_password, now_utc, verify_password)

router = APIRouter(tags=["Autenticación de staff"])


# ---------- 3.1 Login ----------
@router.post("/auth/login", response_model=LoginOut)
async def login(body: LoginIn, request: Request, db: Db):
    q = await db.execute(select(models.AdminUser).where(models.AdminUser.email == body.email.lower()).with_for_update())
    admin = q.scalar_one_or_none()

    async def fail(code="INVALID_CREDENTIALS", msg="Correo o contraseña incorrectos.", status=401):
        await audit(db, request, "auth.login_failed", "admin_user",
                    admin.id if admin else None, actor=admin,
                    metadata={"outcome": "failure", "reason": code})
        await db.commit()  # persistir el intento fallido y la auditoría pese al error
        details = None
        if admin and admin.locked_until and as_utc(admin.locked_until) > now_utc():
            details = [{"locked_until": as_utc(admin.locked_until).isoformat(),
                        "retry_after_seconds": max(1, ceil((as_utc(admin.locked_until) - now_utc()).total_seconds()))}]
        raise ApiError(status, code, msg, details)

    if admin is None:
        await fail()  # mismo error que contraseña incorrecta: no revela existencia
    if is_locked(admin):
        await fail("ACCOUNT_LOCKED", "Cuenta bloqueada temporalmente por intentos fallidos repetidos.", 423)
    if admin.password_hash is None or not verify_password(body.password, admin.password_hash):
        record_failure(admin)
        await fail()
    if not admin.is_active:
        await fail("ADMIN_DISABLED", "Esta cuenta de administración está desactivada. Contacta a un admin.", 403)
    if admin.mfa_enabled:
        if not body.otp_code and not body.recovery_code:
            await fail("OTP_REQUIRED", "Esta cuenta exige segundo factor. Envía tu código TOTP o de recuperación.")
        if not check_second_factor(admin, body.otp_code, body.recovery_code):
            record_failure(admin)
            await fail("OTP_INVALID", "El código de verificación no es válido o expiró.")
    elif requires_mfa(admin):
        enrollment = await create_enrollment(db, admin)
        await audit(db, request, "auth.login_failed", "admin_user", admin.id, actor=admin,
                    metadata={"outcome": "failure", "reason": "MFA_ENROLLMENT_REQUIRED"})
        return JSONResponse(status_code=403, headers={"Cache-Control": "no-store"}, content={"error": {
            "code": "MFA_ENROLLMENT_REQUIRED", "message": "Debes configurar MFA antes de acceder a la consola.",
            "enrollment_token": enrollment}})

    reset_attempts(admin)
    admin.last_login_at = now_utc()
    request.state.actor = admin

    token, refresh_hash, expires = new_refresh_token()
    db.add(models.AdminSession(admin_id=admin.id, refresh_hash=refresh_hash, expires_at=expires, mfa_verified=admin.mfa_enabled, auth_version=admin.auth_version))
    await audit(db, request, "auth.login", "admin_user", admin.id, actor=admin,
                metadata={"outcome": "success"})
    return LoginOut(access_token=create_access_token(admin.id, admin.role, admin.mfa_enabled, admin.auth_version),
                    refresh_token=token, admin=admin)


# ---------- 3.2 Refresh ----------
@router.post("/auth/refresh", response_model=RefreshOut)
async def refresh(body: RefreshIn, request: Request, db: Db):
    q = await db.execute(select(models.AdminSession)
                         .where(models.AdminSession.refresh_hash == hash_refresh(body.refresh_token)))
    session = q.scalar_one_or_none()
    if session is None or as_utc(session.expires_at) < now_utc():
        raise unauthorized("La sesión no es válida o fue revocada. Inicia sesión de nuevo.", "INVALID_REFRESH")
    # Bloquear primero la cuenta: mismo orden que login y cambios de seguridad.
    # Serializa renovaciones de distintas sesiones y la detección de reutilización.
    admin = await db.scalar(select(models.AdminUser).where(models.AdminUser.id == session.admin_id)
                            .with_for_update().execution_options(populate_existing=True))
    if admin is None:
        raise unauthorized(code="INVALID_REFRESH")
    await db.refresh(session, with_for_update=True)
    if session.revoked_at is not None:
        if session.rotated_to is None:
            raise unauthorized("La sesión no es válida o fue revocada. Inicia sesión de nuevo.", "INVALID_REFRESH")
        # Reutilización de un token ya rotado: revocar todas las sesiones (posible robo).
        sessions = (await db.execute(select(models.AdminSession)
                                     .where(models.AdminSession.admin_id == session.admin_id,
                                            models.AdminSession.revoked_at.is_(None)))).scalars()
        for s_ in sessions:
            s_.revoked_at = now_utc()
        actor = await db.get(models.AdminUser, session.admin_id)
        actor.auth_version += 1
        await audit(db, request, "auth.refresh_reuse", "admin_user", session.admin_id,
                    actor=actor, metadata={"outcome": "failure"})
        await db.commit()
        raise unauthorized("La sesión no es válida o fue revocada. Inicia sesión de nuevo.", "INVALID_REFRESH")

    if admin is None or not admin.is_active or session.auth_version != admin.auth_version or ((requires_mfa(admin) or admin.mfa_enabled) and (not admin.mfa_enabled or not session.mfa_verified)):
        raise unauthorized("La sesión no es válida o fue revocada. Inicia sesión de nuevo.", "INVALID_REFRESH")
    request.state.actor = admin

    token, refresh_hash, expires = new_refresh_token()
    new_session = models.AdminSession(admin_id=admin.id, refresh_hash=refresh_hash, expires_at=expires, mfa_verified=session.mfa_verified, auth_version=admin.auth_version)
    db.add(new_session)
    await db.flush()
    session.revoked_at = now_utc()
    session.rotated_to = new_session.id
    await audit(db, request, "auth.refresh", "admin_user", admin.id)
    return RefreshOut(access_token=create_access_token(admin.id, admin.role, session.mfa_verified, admin.auth_version), refresh_token=token)


# ---------- 3.3 Logout ----------
@router.post("/auth/logout", status_code=204)
async def logout(body: RefreshIn, request: Request, db: Db, admin: CurrentAdmin):
    q = await db.execute(select(models.AdminSession)
                         .where(models.AdminSession.refresh_hash == hash_refresh(body.refresh_token),
                                models.AdminSession.admin_id == admin.id))
    session = q.scalar_one_or_none()
    if session is not None:
        session.revoked_at = now_utc()
    await audit(db, request, "auth.logout", "admin_user", admin.id)
    return Response(status_code=204)


# ---------- 3.4 Me ----------
@router.get("/auth/me", response_model=MeOut)
async def me(admin: CurrentAdmin):
    return MeOut(id=admin.id, full_name=admin.full_name, email=admin.email,
                 role=AdminRole(admin.role), mfa_enabled=admin.mfa_enabled,
                 mfa_required=requires_mfa(admin),
                 permissions=permissions_for(AdminRole(admin.role)),
                 last_login_at=admin.last_login_at)


# ---------- 3.5 Crear staff ----------
@router.post("/users", response_model=AdminCreateOut, status_code=201)
async def create_staff(body: AdminCreateIn, request: Request, db: Db,
                       admin: models.AdminUser = require("staff", write=True)):
    s = get_settings()
    email = body.email.lower()
    if email.split("@")[1] not in s.allowed_domains:
        raise invalid("DOMAIN_NOT_ALLOWED", "El dominio del correo no está autorizado para cuentas de administración.")
    exists = (await db.execute(select(models.AdminUser).where(models.AdminUser.email == email))).scalar_one_or_none()
    if exists:
        raise conflict("EMAIL_IN_USE", "Ya existe una cuenta de staff con ese correo.")
    require_mfa = body.role == AdminRole.admin or bool(body.require_mfa)
    new = models.AdminUser(full_name=body.full_name, email=email, role=body.role,
                           password_hash=hash_password(body.password) if body.password is not None else None,
                           is_active=body.password is not None,
                           mfa_enabled=False, mfa_required=require_mfa or body.role in get_settings().mfa_required_roles.split(","),
                           invitation_expires_at=None if body.password is not None else now_utc() + timedelta(hours=24))
    db.add(new)
    await db.flush()
    if body.password is None:
        await issue_invitation(db, new)
    # El envío se procesa después del commit desde la cola persistente.
    await audit(db, request, "staff.create", "admin_user", new.id,
                after=staff_snapshot(new))
    return AdminCreateOut(id=new.id, email=new.email, role=AdminRole(new.role),
                          invitation_expires_at=new.invitation_expires_at, is_active=new.is_active)


# ---------- 3.6 Listar staff ----------
@router.get("/users", response_model=Page[AdminUserOut])
async def list_staff(db: Db,
                     admin: models.AdminUser = require("staff"),
                     role: AdminRole | None = None,
                     is_active: bool | None = None,
                     account_status: str | None = Query(default=None, pattern="^(active|inactive|pending|expired|cancelled)$"),
                     q: str | None = Query(default=None, max_length=120),
                     page: int = Query(default=1, ge=1),
                     page_size: int = Query(default=25, ge=1, le=100)):
    stmt = select(models.AdminUser)
    if account_status in {"active", "inactive"}:
        stmt = stmt.where(models.AdminUser.password_hash.is_not(None), models.AdminUser.is_active.is_(account_status == "active"))
    elif account_status == "cancelled":
        stmt = stmt.where(models.AdminUser.password_hash.is_(None), models.AdminUser.invitation_cancelled_at.is_not(None))
    elif account_status in {"pending", "expired"}:
        stmt = stmt.where(models.AdminUser.password_hash.is_(None), models.AdminUser.invitation_cancelled_at.is_(None))
        stmt = stmt.where(models.AdminUser.invitation_expires_at <= now_utc()) if account_status == "expired" else stmt.where(
            models.AdminUser.invitation_expires_at.is_(None) | (models.AdminUser.invitation_expires_at > now_utc()))
    if role:
        stmt = stmt.where(models.AdminUser.role == role)
    if is_active is not None:
        stmt = stmt.where(models.AdminUser.is_active == is_active)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(models.AdminUser.full_name.ilike(like) | models.AdminUser.email.ilike(like))
    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = (await db.execute(stmt.order_by(models.AdminUser.created_at.desc())
                             .offset((page - 1) * page_size).limit(page_size))).scalars().all()
    return Page(items=[AdminUserOut.model_validate(r) for r in rows],
                page=page, page_size=page_size, total=total)


# ---------- 3.7 Actualizar staff ----------
@router.patch("/users/{admin_id}", response_model=AdminUserOut)
async def patch_staff(admin_id: UUID, body: AdminPatchIn, request: Request, db: Db,
                      admin: models.AdminUser = require("staff", write=True)):
    await lock_staff_for_change(db, admin)
    target = await db.get(models.AdminUser, admin_id)
    if target is None:
        raise not_found()
    before = staff_snapshot(target)
    if target.password_hash is None and body.email is not None and body.email.lower() != target.email:
        raise conflict("PENDING_EMAIL_CHANGE", "Cancela y elimina esta cuenta pendiente para invitar al correo correcto.")
    if body.role is not None and body.role != target.role and target.id == admin.id:
        raise conflict("CANNOT_CHANGE_SELF_ROLE", "No puedes cambiar el rol de tu propia cuenta.")
    if body.email is not None:
        email = body.email.lower()
        if email.split("@")[1] not in get_settings().allowed_domains:
            raise invalid("DOMAIN_NOT_ALLOWED", "El dominio del correo no está autorizado para cuentas de administración.")
        exists = await db.scalar(select(models.AdminUser.id).where(
            models.AdminUser.email == email, models.AdminUser.id != target.id))
        if exists:
            raise conflict("EMAIL_IN_USE", "Ya existe una cuenta de staff con ese correo.")
        target.email = email
    if body.is_active is False:
        if target.id == admin.id:
            raise conflict("CANNOT_DISABLE_SELF", "No puedes desactivar tu propia cuenta.")
        actives = (await db.execute(
            select(func.count()).select_from(models.AdminUser)
            .where(models.AdminUser.role == AdminRole.admin,
                   models.AdminUser.is_active.is_(True),
                   models.AdminUser.id != target.id))).scalar_one()
        if target.role == AdminRole.admin and actives == 0:
            raise conflict("LAST_ADMIN", "Debe existir al menos una cuenta activa con rol admin.")
    if body.role and target.role == AdminRole.admin and body.role != AdminRole.admin:
        actives = (await db.execute(
            select(func.count()).select_from(models.AdminUser)
            .where(models.AdminUser.role == AdminRole.admin,
                   models.AdminUser.is_active.is_(True),
                   models.AdminUser.id != target.id))).scalar_one()
        if actives == 0:
            raise conflict("LAST_ADMIN", "Debe existir al menos una cuenta activa con rol admin.")

    if body.full_name is not None:
        target.full_name = body.full_name
    if body.role is not None:
        target.role = body.role
        if body.role == AdminRole.admin or body.role in {role.strip() for role in get_settings().mfa_required_roles.split(",")}:
            target.mfa_required = True
    if body.is_active is not None:
        if body.is_active and (not target.password_hash or (target.mfa_enabled and not target.mfa_secret)):
            raise conflict("ACCOUNT_NOT_READY", "Esta cuenta todavía no tiene sus credenciales configuradas y no puede activarse.")
        target.is_active = body.is_active
        if body.is_active is False:  # revocar sesiones
            sessions = (await db.execute(select(models.AdminSession)
                                         .where(models.AdminSession.admin_id == target.id,
                                                models.AdminSession.revoked_at.is_(None)))).scalars()
            for s_ in sessions:
                s_.revoked_at = now_utc()
    after = staff_snapshot(target)
    if before["role"] != after["role"] or before["is_active"] != after["is_active"]:
        target.auth_version += 1
    if before != after:
        await audit(db, request, "staff.update", "admin_user", target.id, before=before, after=after)
    return AdminUserOut.model_validate(target)


def staff_snapshot(target: models.AdminUser) -> dict:
    return {"full_name": target.full_name, "email": target.email,
            "role": target.role, "is_active": target.is_active, "mfa_required": target.mfa_required}


async def lock_staff_for_change(db, actor):
    # Serializa cambios de roles/estado en PostgreSQL y vuelve a comprobar al actor.
    await db.execute(select(models.AdminUser).order_by(models.AdminUser.id)
                     .with_for_update().execution_options(populate_existing=True))
    await db.refresh(actor)
    if not actor.is_active or actor.role != AdminRole.admin:
        raise forbidden()


@router.delete("/users/{admin_id}", status_code=204)
async def delete_staff(admin_id: UUID, request: Request, db: Db,
                       admin: models.AdminUser = require("staff", write=True)):
    await lock_staff_for_change(db, admin)
    target = await db.get(models.AdminUser, admin_id)
    if target is None:
        raise not_found()
    if target.id == admin.id:
        raise conflict("CANNOT_DELETE_SELF", "No puedes eliminar tu propia cuenta.")
    if target.role == AdminRole.admin and target.is_active:
        others = await db.scalar(select(func.count()).select_from(models.AdminUser).where(
            models.AdminUser.role == AdminRole.admin, models.AdminUser.is_active.is_(True),
            models.AdminUser.id != target.id))
        if not others:
            raise conflict("LAST_ADMIN", "Debe existir al menos una cuenta activa con rol admin.")
    # Conserva tickets y respuestas; retira la referencia al encargado que
    # dejará de existir antes de borrar su cuenta (FK restrictiva en PostgreSQL).
    unassigned = (await db.execute(update(models.Ticket)
        .where(models.Ticket.assigned_to == target.id)
        .values(assigned_to=None).returning(models.Ticket.id))).all()
    await audit(db, request, "staff.delete", "admin_user", target.id,
                before=staff_snapshot(target), after={"unassigned_tickets": len(unassigned)})
    # Elimina los refresh tokens asociados; el historial de auditoría se conserva.
    await db.execute(delete(models.AdminSession).where(models.AdminSession.admin_id == target.id))
    invitation_ids = select(models.AdminInvitation.id).where(models.AdminInvitation.admin_id == target.id)
    await db.execute(delete(models.InvitationEmail).where(models.InvitationEmail.invitation_id.in_(invitation_ids)))
    await db.execute(delete(models.AdminInvitation).where(models.AdminInvitation.admin_id == target.id))
    await db.execute(delete(models.MfaEnrollment).where(models.MfaEnrollment.admin_id == target.id))
    await db.execute(delete(models.AdminPasswordReset).where(models.AdminPasswordReset.admin_id == target.id))
    recovery_ids = select(models.AdminMfaRecovery.id).where(models.AdminMfaRecovery.admin_id == target.id)
    await db.execute(delete(models.MfaRecoveryEmail).where(
        (models.MfaRecoveryEmail.recipient_id == target.id) | models.MfaRecoveryEmail.recovery_id.in_(recovery_ids)))
    await db.execute(delete(models.AdminMfaRecovery).where(models.AdminMfaRecovery.admin_id == target.id))
    await db.delete(target)
    # Confirma eliminación y auditoría antes de responder: el cliente recarga
    # el listado inmediatamente al recibir 204, antes del teardown de get_db.
    await db.commit()
    return Response(status_code=204)

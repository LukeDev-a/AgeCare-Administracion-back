"""Invitaciones y alta/verificación de MFA sin otorgar acceso prematuro."""
import secrets
from datetime import timedelta
from uuid import UUID

import pyotp
from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select, update

from app import models
from app.account_security import (check_second_factor, decrypt, encrypt, new_recovery_codes,
                                  otp_step, provisioning, requires_mfa)
from app.audit import audit
from app.login_attempts import is_locked, record_failure, reset_attempts
from app.config import get_settings
from app.deps import CurrentAdmin, Db, require
from app.errors import ApiError, conflict, invalid, not_found, unauthorized
from app.invitation_mail import ensure_mail_configured, queue_invitation
from app.security import as_utc, hash_password, hash_refresh, now_utc, verify_password

router = APIRouter(tags=["Invitaciones y MFA"])


@router.get("/users/policy", dependencies=[require("staff")])
async def staff_policy():
    settings = get_settings()
    return {"mfa_required_roles": sorted({"admin", *(role.strip() for role in settings.mfa_required_roles.split(",") if role.strip())}),
            "allowed_email_domains": settings.allowed_domains, "invitation_hours": settings.invitation_hours}


class TokenIn(BaseModel):
    token: str = Field(min_length=40, max_length=200)


class InvitationSetupIn(TokenIn):
    enable_mfa: bool = True


class InvitationAcceptIn(InvitationSetupIn):
    password: str = Field(min_length=8, max_length=128)
    otp_code: str | None = Field(default=None, pattern=r"^\d{6}$")


class MfaConfirmIn(TokenIn):
    otp_code: str = Field(pattern=r"^\d{6}$")


class PasswordIn(BaseModel):
    password: str = Field(min_length=8, max_length=128)


class MfaProofIn(PasswordIn):
    otp_code: str | None = Field(default=None, pattern=r"^\d{6}$")
    recovery_code: str | None = Field(default=None, min_length=16, max_length=40)


async def verify_proof(db, user, body, second_factor=False):
    await db.refresh(user, with_for_update=True)
    if not user.is_active:
        raise unauthorized()
    if is_locked(user):
        raise ApiError(423, "ACCOUNT_LOCKED", "La cuenta está bloqueada temporalmente por intentos fallidos.")
    valid = verify_password(body.password, user.password_hash or "")
    if second_factor:
        valid = valid and user.mfa_enabled and not (body.otp_code and body.recovery_code) and check_second_factor(user, body.otp_code, body.recovery_code)
    if not valid:
        record_failure(user)
        await db.commit()
        raise invalid("INVALID_SECURITY_PROOF", "La contraseña o el código no son válidos. Si ya utilizaste el código del autenticador, espera el siguiente.")
    reset_attempts(user)


async def invalidate_invitations(db, user):
    ids = select(models.AdminInvitation.id).where(models.AdminInvitation.admin_id == user.id,
                models.AdminInvitation.accepted_at.is_(None), models.AdminInvitation.revoked_at.is_(None))
    await db.execute(update(models.InvitationEmail).where(models.InvitationEmail.invitation_id.in_(ids),
        models.InvitationEmail.status == "queued").values(status="cancelled", payload_encrypted=None))
    await db.execute(update(models.AdminInvitation).where(models.AdminInvitation.admin_id == user.id,
        models.AdminInvitation.accepted_at.is_(None), models.AdminInvitation.revoked_at.is_(None)).values(revoked_at=now_utc(), secret_encrypted=None))


async def issue_invitation(db, user):
    ensure_mail_configured()
    await invalidate_invitations(db, user)
    token = secrets.token_urlsafe(48)
    expires = now_utc() + timedelta(hours=get_settings().invitation_hours)
    invitation = models.AdminInvitation(admin_id=user.id, token_hash=hash_refresh(token), expires_at=expires)
    db.add(invitation); await db.flush()
    user.invitation_expires_at = expires
    user.invitation_cancelled_at = None
    await queue_invitation(db, user, invitation, token)


async def invitation_for(db, token):
    invitation = await db.scalar(select(models.AdminInvitation).where(
        models.AdminInvitation.token_hash == hash_refresh(token)))
    if invitation is None or invitation.accepted_at or invitation.revoked_at or invitation.attempts >= 10 or as_utc(invitation.expires_at) <= now_utc():
        raise invalid("INVALID_INVITATION", "La invitación no es válida, venció o ya fue utilizada. Solicita una nueva al administrador.")
    user = await db.scalar(select(models.AdminUser).where(models.AdminUser.id == invitation.admin_id).with_for_update())
    await db.refresh(invitation, with_for_update=True)
    if invitation.accepted_at or invitation.revoked_at or invitation.attempts >= 10 or as_utc(invitation.expires_at) <= now_utc():
        raise invalid("INVALID_INVITATION", "La invitación ya no está disponible.")
    if user is None or user.password_hash is not None or user.is_active or user.invitation_cancelled_at:
        raise invalid("INVALID_INVITATION", "La invitación ya no está disponible. Contacta al administrador.")
    return invitation, user


@router.post("/auth/invitations/inspect")
async def inspect_invitation(body: TokenIn, db: Db, response: Response):
    response.headers["Cache-Control"] = "no-store"
    invitation, user = await invitation_for(db, body.token)
    return {"full_name": user.full_name, "email": user.email, "role": user.role,
            "mfa_required": requires_mfa(user), "expires_at": invitation.expires_at}


@router.post("/auth/invitations/setup")
async def invitation_setup(body: InvitationSetupIn, db: Db, response: Response):
    response.headers["Cache-Control"] = "no-store"
    invitation, user = await invitation_for(db, body.token)
    if not requires_mfa(user) and not body.enable_mfa:
        return {"mfa_required": False, "secret": None, "qr_data_url": None}
    if not invitation.secret_encrypted:
        invitation.secret_encrypted = encrypt(pyotp.random_base32())
    return {"mfa_required": requires_mfa(user), **provisioning(decrypt(invitation.secret_encrypted), user.email)}


@router.post("/auth/invitations/accept")
async def accept_invitation(body: InvitationAcceptIn, request: Request, db: Db, response: Response):
    response.headers["Cache-Control"] = "no-store"
    invitation, user = await invitation_for(db, body.token)
    enabled = requires_mfa(user) or body.enable_mfa
    step = otp_step(decrypt(invitation.secret_encrypted), body.otp_code) if enabled and invitation.secret_encrypted else None
    if enabled and step is None:
        invitation.attempts += 1
        await db.commit()
        raise invalid("OTP_INVALID", "El código no es válido. Revisa tu aplicación autenticadora.")
    user.password_hash = hash_password(body.password)
    user.is_active = True
    user.mfa_enabled = enabled
    user.mfa_secret = invitation.secret_encrypted if enabled else None
    user.mfa_last_step = step
    reset_attempts(user)
    user.invitation_expires_at = None
    codes = new_recovery_codes(user) if enabled else []
    invitation.accepted_at = now_utc(); invitation.secret_encrypted = None
    await invalidate_invitations(db, user)
    await audit(db, request, "staff.invitation_accept", "admin_user", user.id, actor=user,
                after={"full_name": user.full_name, "email": user.email, "is_active": True, "mfa_enabled": enabled})
    return {"activated": True, "mfa_enabled": enabled, "recovery_codes": codes}


@router.post("/users/{admin_id}/invitation/resend")
async def resend_invitation(admin_id: UUID, request: Request, db: Db,
                             actor: models.AdminUser = require("staff", write=True)):
    user = await db.scalar(select(models.AdminUser).where(models.AdminUser.id == admin_id).with_for_update())
    if not user: raise not_found()
    if user.password_hash is not None or user.is_active:
        raise conflict("NOT_PENDING", "Solo puedes invitar cuentas que todavía no se han activado.")
    recent = await db.scalar(select(models.AdminInvitation).where(models.AdminInvitation.admin_id == user.id)
                            .order_by(models.AdminInvitation.created_at.desc()).limit(1))
    if recent and now_utc() - as_utc(recent.created_at) < timedelta(seconds=60):
        raise conflict("INVITATION_COOLDOWN", "Espera un minuto antes de reenviar la invitación.")
    await issue_invitation(db, user)
    await audit(db, request, "staff.invitation_resend", "admin_user", user.id,
                after={"full_name": user.full_name, "email": user.email})
    return {"queued": True}


@router.post("/users/{admin_id}/invitation/cancel")
async def cancel_invitation(admin_id: UUID, request: Request, db: Db,
                             actor: models.AdminUser = require("staff", write=True)):
    user = await db.scalar(select(models.AdminUser).where(models.AdminUser.id == admin_id).with_for_update())
    if not user: raise not_found()
    if user.password_hash is not None or user.is_active or user.invitation_cancelled_at:
        raise conflict("NOT_PENDING", "La cuenta no tiene una invitación pendiente.")
    await invalidate_invitations(db, user)
    user.invitation_cancelled_at = now_utc(); user.invitation_delivery_status = "cancelled"
    await audit(db, request, "staff.invitation_cancel", "admin_user", user.id,
                after={"full_name": user.full_name, "email": user.email})
    return {"cancelled": True}


async def create_enrollment(db, user):
    await db.execute(update(models.MfaEnrollment).where(models.MfaEnrollment.admin_id == user.id,
                    models.MfaEnrollment.used_at.is_(None)).values(used_at=now_utc(), secret_encrypted=""))
    token = secrets.token_urlsafe(48)
    db.add(models.MfaEnrollment(admin_id=user.id, token_hash=hash_refresh(token),
           expires_at=now_utc() + timedelta(minutes=10), secret_encrypted=encrypt(pyotp.random_base32())))
    return token


async def enrollment_for(db, token):
    row = await db.scalar(select(models.MfaEnrollment).where(models.MfaEnrollment.token_hash == hash_refresh(token)))
    if not row or row.used_at or row.attempts >= 10 or as_utc(row.expires_at) <= now_utc():
        raise invalid("INVALID_ENROLLMENT", "La configuración de MFA venció. Inicia sesión de nuevo.")
    user = await db.scalar(select(models.AdminUser).where(models.AdminUser.id == row.admin_id).with_for_update())
    await db.refresh(row, with_for_update=True)
    if row.used_at or row.attempts >= 10 or as_utc(row.expires_at) <= now_utc():
        raise invalid("INVALID_ENROLLMENT", "La configuración de MFA ya no está disponible.")
    if not user or not user.is_active or user.mfa_enabled:
        raise invalid("INVALID_ENROLLMENT", "Esta configuración de MFA ya no está disponible.")
    return row, user


@router.post("/auth/mfa/setup")
async def setup_optional_mfa(body: PasswordIn, admin: CurrentAdmin, db: Db):
    if admin.mfa_enabled: raise conflict("MFA_ALREADY_ENABLED", "MFA ya está configurado en tu cuenta.")
    await verify_proof(db, admin, body)
    return {"enrollment_token": await create_enrollment(db, admin)}


@router.post("/auth/mfa/enrollment/setup")
async def setup_enrollment(body: TokenIn, db: Db, response: Response):
    response.headers["Cache-Control"] = "no-store"
    row, user = await enrollment_for(db, body.token)
    return provisioning(decrypt(row.secret_encrypted), user.email)


@router.post("/auth/mfa/enrollment/confirm")
async def confirm_enrollment(body: MfaConfirmIn, request: Request, db: Db, response: Response):
    response.headers["Cache-Control"] = "no-store"
    row, user = await enrollment_for(db, body.token)
    step = otp_step(decrypt(row.secret_encrypted), body.otp_code)
    if step is None:
        row.attempts += 1; await db.commit()
        raise invalid("OTP_INVALID", "El código no es válido. Revisa tu aplicación autenticadora.")
    user.mfa_enabled = True; user.mfa_secret = row.secret_encrypted; user.mfa_last_step = step
    user.auth_version += 1
    codes = new_recovery_codes(user); row.used_at = now_utc(); row.secret_encrypted = ""
    await db.execute(update(models.AdminSession).where(models.AdminSession.admin_id == user.id).values(revoked_at=now_utc()))
    await audit(db, request, "staff.mfa_enable", "admin_user", user.id, actor=user,
                after={"full_name": user.full_name, "mfa_enabled": True})
    return {"mfa_enabled": True, "recovery_codes": codes}


@router.post("/auth/mfa/recovery-codes")
async def replace_recovery_codes(body: MfaProofIn, request: Request, db: Db, admin: CurrentAdmin, response: Response):
    response.headers["Cache-Control"] = "no-store"
    await verify_proof(db, admin, body, second_factor=True)
    codes = new_recovery_codes(admin)
    await audit(db, request, "staff.mfa_recovery", "admin_user", admin.id,
                after={"full_name": admin.full_name})
    return {"recovery_codes": codes}


@router.post("/auth/mfa/disable")
async def disable_mfa(body: MfaProofIn, request: Request, db: Db, admin: CurrentAdmin):
    if requires_mfa(admin): raise conflict("MFA_REQUIRED", "MFA es obligatorio para tu cuenta y no puede desactivarse.")
    await verify_proof(db, admin, body, second_factor=True)
    if requires_mfa(admin): raise conflict("MFA_REQUIRED", "MFA es obligatorio para tu cuenta y no puede desactivarse.")
    admin.mfa_enabled = False; admin.mfa_secret = None; admin.mfa_last_step = None; admin.recovery_hashes = []
    admin.auth_version += 1
    await db.execute(update(models.AdminSession).where(models.AdminSession.admin_id == admin.id).values(revoked_at=now_utc()))
    await audit(db, request, "staff.mfa_disable", "admin_user", admin.id,
                after={"full_name": admin.full_name, "mfa_enabled": False})
    return {"mfa_enabled": False}

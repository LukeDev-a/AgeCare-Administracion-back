from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, model_validator

from app.enums import AdminRole


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    otp_code: str | None = Field(default=None, pattern=r"^\d{6}$")
    recovery_code: str | None = Field(default=None, min_length=16, max_length=40)

    @model_validator(mode="after")
    def one_second_factor(self):
        if self.otp_code and self.recovery_code:
            raise ValueError("Usa el autenticador o un código de recuperación, no ambos.")
        return self


class AdminOut(BaseModel):
    id: UUID
    full_name: str
    email: EmailStr
    role: AdminRole
    mfa_enabled: bool
    mfa_required: bool = False

    model_config = {"from_attributes": True}


class LoginOut(BaseModel):
    access_token: str
    refresh_token: str
    admin: AdminOut


class RefreshIn(BaseModel):
    refresh_token: str


class RefreshOut(BaseModel):
    access_token: str
    refresh_token: str


class MeOut(AdminOut):
    permissions: list[str]
    last_login_at: datetime | None


class AdminUserOut(AdminOut):
    is_active: bool
    last_login_at: datetime | None
    created_at: datetime
    account_status: str = "active"
    invitation_expires_at: datetime | None = None
    invitation_delivery_status: str | None = None

    @model_validator(mode="before")
    @classmethod
    def status_from_account(cls, value):
        from app.account_security import requires_mfa
        from app.security import as_utc, now_utc
        if isinstance(value, dict): return value
        if value.password_hash is not None:
            status = "active" if value.is_active else "inactive"
        elif value.invitation_cancelled_at:
            status = "cancelled"
        elif value.invitation_expires_at and as_utc(value.invitation_expires_at) <= now_utc():
            status = "expired"
        else:
            status = "pending"
        data = {field: getattr(value, field) for field in cls.model_fields if hasattr(value, field)}
        return {**data, "account_status": status, "mfa_required": requires_mfa(value)}


class AdminCreateIn(BaseModel):
    model_config = {"extra": "forbid"}
    full_name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    role: AdminRole
    require_mfa: bool | None = None
    password: str | None = Field(default=None, min_length=8, max_length=128)

    @model_validator(mode="after")
    def validate_name(self):
        self.full_name = self.full_name.strip()
        if len(self.full_name) < 2:
            raise ValueError("El nombre debe tener al menos dos caracteres.")
        return self


class AdminCreateOut(BaseModel):
    id: UUID
    email: EmailStr
    role: AdminRole
    invitation_expires_at: datetime | None
    is_active: bool = False


class AdminPatchIn(BaseModel):
    model_config = {"extra": "forbid", "str_strip_whitespace": True}
    full_name: str | None = Field(default=None, min_length=2, max_length=120)
    email: EmailStr | None = None
    role: AdminRole | None = None
    is_active: bool | None = None

    @model_validator(mode="after")
    def reject_explicit_null(self):
        if any(getattr(self, key) is None for key in self.model_fields_set):
            raise ValueError("Los campos enviados no pueden ser nulos.")
        return self

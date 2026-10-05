"""Secretos cifrados, TOTP y códigos de recuperación de un solo uso."""
import base64
import secrets
import time

import pyotp
import qrcode
import qrcode.image.svg
from cryptography.fernet import Fernet

from app.config import get_settings
from app.errors import ApiError
from app.security import hash_refresh


def cipher() -> Fernet:
    key = get_settings().encryption_key
    if not key:
        raise ApiError(503, "ENCRYPTION_NOT_CONFIGURED", "Falta configurar la clave de cifrado de seguridad en el servidor.")
    try:
        return Fernet(key.encode())
    except (ValueError, TypeError):
        raise ApiError(503, "ENCRYPTION_NOT_CONFIGURED", "La clave de cifrado del servidor no es válida.")


def encrypt(value: str) -> str:
    return "enc:" + cipher().encrypt(value.encode()).decode()


def decrypt(value: str) -> str:
    # Compatibilidad con secretos TOTP existentes antes de esta funcionalidad.
    return cipher().decrypt(value[4:].encode()).decode() if value.startswith("enc:") else value


def requires_mfa(user) -> bool:
    roles = {role.strip() for role in get_settings().mfa_required_roles.split(",")}
    return user.mfa_required or user.role in roles


def otp_step(secret: str, code: str | None) -> int | None:
    if not code:
        return None
    current = int(time.time() // 30)
    totp = pyotp.TOTP(secret)
    for step in (current, current - 1, current + 1):
        if secrets.compare_digest(totp.at(step * 30), code):
            return step
    return None


def check_second_factor(user, code: str | None, recovery_code: str | None = None) -> bool:
    if recovery_code:
        digest = hash_refresh(recovery_code.replace("-", "").strip().upper())
        hashes = list(user.recovery_hashes or [])
        if digest not in hashes:
            return False
        hashes.remove(digest)
        user.recovery_hashes = hashes
        return True
    if not user.mfa_secret:
        return False
    step = otp_step(decrypt(user.mfa_secret), code)
    if step is None or (user.mfa_last_step is not None and step <= user.mfa_last_step):
        return False
    user.mfa_last_step = step
    return True


def new_recovery_codes(user) -> list[str]:
    codes = [secrets.token_hex(8).upper() for _ in range(10)]
    user.recovery_hashes = [hash_refresh(code) for code in codes]
    return [code[:8] + "-" + code[8:] for code in codes]


def provisioning(secret: str, email: str) -> dict:
    uri = pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name="AgeCare")
    svg = qrcode.make(uri, image_factory=qrcode.image.svg.SvgPathImage).to_string()
    return {"secret": secret, "qr_data_url": "data:image/svg+xml;base64," + base64.b64encode(svg).decode()}

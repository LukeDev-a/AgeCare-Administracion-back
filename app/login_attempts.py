"""Ventana móvil de fallos compartida por login y verificaciones de seguridad."""
from datetime import timedelta

from app.config import get_settings
from app.security import as_utc, now_utc


def reset_attempts(user):
    user.failed_attempts = 0
    user.failed_attempt_times = []
    user.locked_until = None


def is_locked(user):
    if not user.locked_until:
        return False
    if as_utc(user.locked_until) > now_utc():
        return True
    reset_attempts(user)
    return False


def record_failure(user):
    settings = get_settings()
    now = now_utc()
    cutoff = (now - timedelta(minutes=10)).timestamp()
    attempts = [value for value in (user.failed_attempt_times or []) if value > cutoff]
    attempts.append(now.timestamp())
    user.failed_attempt_times = attempts
    user.failed_attempts = len(attempts)
    if len(attempts) >= settings.max_login_attempts:
        user.locked_until = now + timedelta(minutes=settings.lockout_minutes)
        user.failed_attempt_times = []
        user.failed_attempts = 0

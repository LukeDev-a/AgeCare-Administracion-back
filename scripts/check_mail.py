"""Diagnóstico explícito de SMTP: conecta/autentica, no envía mensajes ni imprime secretos.

Ejecutar desde la raíz del backend: python -m scripts.check_mail.
"""
import smtplib
import ssl

from app.config import get_settings
from app.errors import ApiError
from app.invitation_mail import ensure_mail_configured


def main() -> int:
    try:
        ensure_mail_configured()
    except ApiError:
        print('Configuración incompleta o inválida. Revisa SMTP, remitente, URL del frontend y la clave de cifrado existente.')
        return 1
    settings = get_settings()
    if not settings.mail_worker_enabled:
        print('Aviso: el trabajador de envío está deshabilitado. Las invitaciones no se enviarán automáticamente.')
    transport = smtplib.SMTP_SSL if settings.smtp_security == 'ssl' else smtplib.SMTP
    options = {'timeout': 20}
    if settings.smtp_security == 'ssl':
        options['context'] = ssl.create_default_context()
    try:
        with transport(settings.smtp_host, settings.smtp_port, **options) as server:
            server.ehlo()
            if settings.smtp_security == 'starttls':
                server.starttls(context=ssl.create_default_context())
                server.ehlo()
            if settings.smtp_username:
                server.login(settings.smtp_username, settings.smtp_password)
            code, _ = server.noop()
            if code != 250:
                print('El servidor respondió, pero no confirmó la comprobación SMTP.')
                return 1
    except smtplib.SMTPAuthenticationError:
        print('Autenticación rechazada. Revisa la credencial y el método admitido por el proveedor.')
        return 1
    except (OSError, smtplib.SMTPException):
        print('No se pudo completar la conexión SMTP. Revisa red, servidor, puerto y TLS; no se enviaron correos.')
        return 1
    print('Conexión SMTP correcta. No se enviaron correos; falta comprobar entrega con una invitación autorizada.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

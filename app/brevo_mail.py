"""Transporte HTTPS de correos transaccionales, sin exponer respuestas del proveedor."""
import json
import ssl
from email.utils import getaddresses, parseaddr
from http.client import HTTPSConnection, HTTPException

from app.config import get_settings


def request_brevo(method: str, path: str, payload: dict | None = None):
    connection = HTTPSConnection('api.brevo.com', timeout=20, context=ssl.create_default_context())
    try:
        connection.request(method, path,
            body=json.dumps(payload).encode('utf-8') if payload is not None else None,
            headers={'api-key': get_settings().brevo_api_key, 'Accept': 'application/json',
                     'Content-Type': 'application/json'})
        response = connection.getresponse()
        body = response.read()
        if response.status not in {200, 201}:
            raise RuntimeError(f'Brevo rechazó la solicitud (HTTP {response.status}).')
        return json.loads(body)
    except (OSError, HTTPException, ValueError):
        raise RuntimeError('No se pudo completar la comunicación segura con Brevo.') from None
    finally:
        connection.close()


def send_message_brevo(message):
    name, email = parseaddr(str(message['From']))
    recipients = [{'email': address, **({'name': recipient_name} if recipient_name else {})}
                  for recipient_name, address in getaddresses(message.get_all('To', []))]
    request_brevo('POST', '/v3/smtp/email', {
        'sender': {'email': email, **({'name': name} if name else {})},
        'to': recipients, 'subject': str(message['Subject']), 'textContent': message.get_content(),
    })

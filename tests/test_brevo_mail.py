"""Brevo simulado, sin credenciales reales ni envío de mensajes."""
import json
import ssl
from email.message import EmailMessage

import pytest

from app import brevo_mail, invitation_mail, incident_mail
from app.config import get_settings
from app.errors import ApiError
from scripts import check_mail


@pytest.fixture
def brevo(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, 'mail_provider', 'brevo')
    monkeypatch.setattr(settings, 'brevo_api_key', 'test-private-brevo-key')
    monkeypatch.setattr(settings, 'smtp_host', '')
    return settings


def test_brevo_configuration_requires_key_and_accepts_no_smtp(brevo, monkeypatch):
    invitation_mail.ensure_mail_configured()
    monkeypatch.setattr(brevo, 'brevo_api_key', '')
    with pytest.raises(ApiError) as error:
        invitation_mail.ensure_mail_configured()
    assert error.value.code == 'MAIL_NOT_CONFIGURED'


def test_invitations_and_incidents_use_brevo_with_original_text(brevo, monkeypatch):
    sent = []
    monkeypatch.setattr(invitation_mail, 'send_message_brevo', sent.append)
    monkeypatch.setattr(invitation_mail, 'send_message_smtp', lambda message: pytest.fail('No debe usar SMTP'))
    invitation_mail.send_smtp({'email': 'recipient@example.com', 'name': 'Prueba',
                             'url': 'https://example.com/aceptar-invitacion#token=test', 'expires_at': '2026-11-11'})
    incident_mail.send_incident({'email': 'recipient@example.com', 'id': 'test-id', 'title': 'Prueba de incidente',
                                'maintenance': False, 'severity': 'outage', 'started_at': '2026-11-10'})
    assert len(sent) == 2
    assert 'aceptar-invitacion#token=test' in sent[0].get_content()
    assert 'Prueba de incidente' in sent[1].get_content()
    assert sent[0]['To'] == sent[1]['To'] == 'recipient@example.com'


@pytest.mark.parametrize('status', [201, 401, 429, 500])
def test_https_transport_payload_tls_errors_and_connection_close(brevo, monkeypatch, status):
    calls = []

    class Connection:
        def __init__(self, host, timeout, context):
            assert host == 'api.brevo.com' and timeout == 20
            assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname

        def request(self, method, path, body, headers):
            calls.append((method, path, json.loads(body), headers))

        def getresponse(self):
            self.status = status
            return self

        def read(self):
            return b'{"messageId":"test-message","private":"secret-provider-response"}'

        def close(self):
            calls.append('closed')

    monkeypatch.setattr(brevo_mail, 'HTTPSConnection', Connection)
    message = EmailMessage()
    message['From'] = 'AgeCare <tests@wellq.co.uk>'
    message['To'] = 'Destinatario <recipient@example.com>'
    message['Subject'] = 'Invitación de prueba'
    message.set_content('Texto con acentos y enlace de prueba')
    if status == 201:
        brevo_mail.send_message_brevo(message)
    else:
        with pytest.raises(RuntimeError) as error:
            brevo_mail.send_message_brevo(message)
        assert 'secret-provider-response' not in str(error.value)
        assert brevo.brevo_api_key not in str(error.value)
    method, path, payload, headers = calls[0]
    assert (method, path) == ('POST', '/v3/smtp/email')
    assert payload['sender'] == {'name': 'AgeCare', 'email': 'tests@wellq.co.uk'}
    assert payload['to'] == [{'name': 'Destinatario', 'email': 'recipient@example.com'}]
    assert payload['textContent'] == message.get_content()
    assert headers['api-key'] == brevo.brevo_api_key
    assert calls[-1] == 'closed'


def test_brevo_diagnostic_only_reads_and_does_not_expose_secrets(brevo, monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(check_mail, 'request_brevo', lambda method, path: calls.append((method, path)))
    assert check_mail.main() == 0
    assert calls == [('GET', '/v3/smtp/statistics/aggregatedReport')]
    assert brevo.brevo_api_key not in capsys.readouterr().out


def test_brevo_diagnostic_redacts_provider_failure(brevo, monkeypatch, capsys):
    def fail(*args):
        raise RuntimeError('secret-provider-response')
    monkeypatch.setattr(check_mail, 'request_brevo', fail)
    assert check_mail.main() == 1
    assert 'secret-provider-response' not in capsys.readouterr().out

from app.config import get_settings
from scripts import check_mail


def test_diagnostic_connects_without_sending_or_exposing_credentials(monkeypatch, capsys):
    settings = get_settings()
    monkeypatch.setattr(settings, 'smtp_username', 'test-private-user')
    monkeypatch.setattr(settings, 'smtp_password', 'test-private-password')
    monkeypatch.setattr(settings, 'smtp_security', 'starttls')
    calls = []
    class Server:
        def __init__(self, *args, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def ehlo(self): calls.append('ehlo')
        def starttls(self, **kwargs): calls.append('tls')
        def login(self, username, password): calls.append('login')
        def noop(self): return 250, b'ok'
        def send_message(self, message): raise AssertionError('No debe enviar')
    monkeypatch.setattr(check_mail.smtplib, 'SMTP', Server)
    assert check_mail.main() == 0
    assert calls == ['ehlo', 'tls', 'ehlo', 'login']
    output = capsys.readouterr().out
    assert settings.smtp_password not in output and settings.smtp_username not in output


def test_diagnostic_auth_failure_is_redacted(monkeypatch, capsys):
    monkeypatch.setattr(get_settings(), 'smtp_security', 'starttls')
    def fail(*args, **kwargs):
        raise check_mail.smtplib.SMTPAuthenticationError(535, b'private-password-and-provider-response')
    monkeypatch.setattr(check_mail.smtplib, 'SMTP', fail)
    assert check_mail.main() == 1
    assert 'private-password' not in capsys.readouterr().out

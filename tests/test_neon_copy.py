"""Guardas de copia: destino explícito, no sobrescritura y secretos fuera de argv."""
from types import SimpleNamespace

import pytest

from scripts import copy_to_neon as migration


def test_neon_target_requires_direct_connection_and_verified_tls():
    target = migration.target_environment('postgresql://owner:fake-value@ep-example.us-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require')
    assert target['PGSSLMODE'] == 'verify-full'
    assert target['PGSSLROOTCERT'] == 'system'
    assert target['PGCHANNELBINDING'] == 'require'
    for invalid in ('postgresql://owner:fake-value@localhost/neondb',
                    'postgresql://owner:fake-value@ep-example-pooler.us-east-1.aws.neon.tech/neondb',
                    'https://owner:fake-value@ep-example.us-east-1.aws.neon.tech/neondb'):
        with pytest.raises(migration.CopyError) as error:
            migration.target_environment(invalid)
        assert 'fake-value' not in str(error.value)


@pytest.mark.parametrize('existing', [{'relations': 1, 'functions': 0, 'types': 0},
                                    {'relations': 0, 'functions': 1, 'types': 0},
                                    {'relations': 0, 'functions': 0, 'types': 1}])
def test_existing_destination_is_rejected(monkeypatch, existing):
    monkeypatch.setattr(migration, 'query', lambda *_: existing)
    with pytest.raises(migration.CopyError, match='No se sobrescribirá'):
        migration.require_empty({'PGDATABASE': 'fake'})


def test_command_does_not_expose_password_or_raw_error(monkeypatch):
    calls = []
    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=1, stderr=b'private SQL and fake-value')
    monkeypatch.setattr(migration.subprocess, 'run', fake_run)
    with pytest.raises(migration.CopyError) as error:
        migration.run(['psql'], target={'PGPASSWORD': 'fake-value'})
    command, kwargs = calls[0]
    assert 'fake-value' not in ' '.join(command)
    assert kwargs['env']['PGPASSWORD'] == 'fake-value'
    assert 'private SQL' not in str(error.value)
    assert 'fake-value' not in str(error.value)


def test_restore_is_atomic_and_does_not_drop_existing_schema(monkeypatch, tmp_path):
    archive = tmp_path / 'database.dump'
    archive.write_bytes(b'archive fixture')
    calls = []
    def fake_run(command, **kwargs):
        calls.append(command)
        if command == ['pg_restore', '--list']:
            return b'; archive\n1; 2615 2200 SCHEMA - public owner\n2; 0 0 COMMENT - SCHEMA public owner\n3; 1259 999 TABLE public games_apps owner\n'
        return b''
    monkeypatch.setattr(migration, 'run', fake_run)
    migration.restore(archive, {'PGDATABASE': 'neondb'})
    restore = next(c for c in calls if '--dbname=neondb' in c)
    assert '--single-transaction' in restore
    assert '--exit-on-error' in restore
    assert '--no-owner' in restore and '--no-acl' in restore
    assert '--clean' not in restore
    selection = archive.with_name('restore.list').read_text()
    assert 'SCHEMA - public' not in selection
    assert 'COMMENT - SCHEMA public' not in selection
    assert 'TABLE public games_apps' in selection


def test_difference_is_reported_without_printing_records():
    with pytest.raises(migration.CopyError):
        migration.ensure_same([{'rows': 2, 'fingerprint': 'one'}],
                              [{'rows': 2, 'fingerprint': 'different'}])

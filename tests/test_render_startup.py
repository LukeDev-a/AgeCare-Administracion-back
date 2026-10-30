from types import SimpleNamespace
import ssl

import pytest
from sqlalchemy.engine import make_url

from app.database_urls import database_connect_args, normalize_database_url
from scripts.run_api import provision_runtime
from scripts.run_render import validate_settings


def test_neon_libpq_url_becomes_asyncpg_without_losing_encoded_password():
    url = make_url(normalize_database_url('postgresql://role:fake%40value%25@ep-example.us-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require'))
    assert url.drivername == 'postgresql+asyncpg'
    assert url.password == 'fake@value%'
    assert url.query == {'ssl': 'verify-full'}
    context = database_connect_args(url)['ssl']
    assert context.check_hostname
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert database_connect_args('sqlite+aiosqlite://') == {}


@pytest.mark.parametrize('url', ['sqlite+aiosqlite://', 'postgresql+asyncpg://user:fake@localhost/db'])
def test_local_connections_are_preserved(url):
    assert normalize_database_url(url) == url


def render_settings(**overrides):
    data = dict(database_url='postgresql+asyncpg://runtime:fake@ep-example.us-east-1.aws.neon.tech/neondb?ssl=verify-full',
                jwt_secret='a' * 64, encryption_key='MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA=',
                bootstrap_dev_accounts=False, seed_demo_enabled=False,
                environment='dev', render_allow_dev_credentials=False,
                game_public_base_url='https://example.onrender.com', allows_origins='https://example.vercel.app')
    data.update(overrides)
    return SimpleNamespace(**data)


def test_render_accepts_explicit_valid_configuration():
    validate_settings(render_settings())
    validate_settings(render_settings(render_allow_dev_credentials=True))
    with pytest.raises(ValueError):
        validate_settings(render_settings(environment='prod', render_allow_dev_credentials=True))


@pytest.mark.parametrize('overrides', [dict(jwt_secret='solo-para-desarrollo'),
    dict(database_url='postgresql+asyncpg://role:fake@localhost/db'),
    dict(encryption_key='invalid'), dict(bootstrap_dev_accounts=True), dict(seed_demo_enabled=True),
    dict(game_public_base_url='http://example.onrender.com'), dict(allows_origins='null'),
    dict(allows_origins='*'), dict(allows_origins='https://*.vercel.app'),
    dict(allows_origins='https://example.vercel.app/'), dict(allows_origins='https://user:fake@example.vercel.app')])
def test_render_rejects_insecure_or_seed_configuration(overrides):
    with pytest.raises(ValueError):
        validate_settings(render_settings(**overrides))


@pytest.mark.asyncio
async def test_stable_role_password_cannot_contain_sql():
    with pytest.raises(ValueError):
        await provision_runtime('postgresql+asyncpg://owner:fake@localhost/db', stable_password="'; invalid")


@pytest.mark.parametrize('demo', [False, True])
def test_demo_exception_keeps_database_checks_and_only_controls_password_scan(monkeypatch, demo):
    from scripts import run_render
    calls = []
    async def check(value, *, check_accounts):
        calls.append(check_accounts)
    monkeypatch.setattr(run_render, 'get_settings', lambda: render_settings(render_allow_dev_credentials=demo))
    monkeypatch.setattr(run_render, 'check_database', check)
    monkeypatch.setattr(run_render.os, 'execv', lambda *_: None)
    run_render.main()
    assert calls == [not demo]

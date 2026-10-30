"""Disponibilidad del juego también al acceder directamente a sus archivos."""
from pathlib import Path
from sqlalchemy import select
from starlette.responses import HTMLResponse
from starlette.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from app.database import get_session_factory
from app.models import GameApp
from app.game_resources import is_local_resource
from app.config import get_settings
from starlette.requests import Request
from urllib.parse import urlsplit


class GameStaticFiles(StaticFiles):
    async def get_response(self, path, scope):
        parts = Path(path).as_posix().split('/')
        protected = len(parts) >= 3 and parts[0] == 'juegos' and parts[1] != 'compartido'
        availability_headers = {'Cache-Control': 'no-store'}
        if protected and scope['method'] == 'HEAD':
            # El iframe aislado tiene origen opaco (Origin: null). Solo este
            # estado público es consultable entre orígenes, nunca datos admin.
            availability_headers['Access-Control-Allow-Origin'] = '*'
        if protected:
            slug = parts[1]
            async with get_session_factory()() as db:
                game = await db.scalar(select(GameApp).where(
                    GameApp.slug == slug, GameApp.is_active.is_(True), GameApp.deleted_at.is_(None)))
            origins = {urlsplit(str(Request(scope).base_url)).netloc,
                       urlsplit(get_settings().game_public_base_url or '').netloc}
            if game is None or not is_local_resource(game.target_url or '', slug, origins):
                return HTMLResponse('<html lang="es"><meta charset="utf-8"><title>Juego no disponible</title>'
                                    '<h1>Este juego no está disponible</h1><p>Vuelve al catálogo y elige otro juego.</p></html>',
                                    status_code=403, headers=availability_headers)
        if protected:
            scope = {**scope, 'headers': [(key, value) for key, value in scope.get('headers', [])
                                         if key.lower() not in (b'if-none-match', b'if-modified-since')]}
        response = await super().get_response(path, scope)
        if protected:
            response.headers.update(availability_headers)
            if path.endswith('.html') and response.status_code == 200 and scope['method'] == 'GET':
                html = await run_in_threadpool(Path(response.path).read_text, encoding='utf-8')
                guard = '<script src="../compartido/disponibilidad.js"></script>'
                html = html.replace('<head>', '<head>' + guard, 1) if '<head>' in html else guard + html
                return HTMLResponse(html, headers={'Cache-Control': 'no-store'})
        return response

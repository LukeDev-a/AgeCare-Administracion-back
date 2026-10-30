"""Recursos locales del catálogo; nunca consulta URLs externas."""
import re
from pathlib import Path
from urllib.parse import urlsplit

GAME_ROOT = Path(__file__).resolve().parent / 'static' / 'juegos'


def is_local_resource(value: str, slug: str, origins: set[str]) -> bool:
    parsed = urlsplit(value)
    return (parsed.path == f'/static/juegos/{slug}/index.html'
            and (not parsed.netloc or parsed.netloc in origins
                 or parsed.scheme == 'http' and parsed.hostname in ('localhost', '127.0.0.1')))


def resource_path(value: str, slug: str) -> str:
    path = urlsplit(value).path
    expected = f'/static/juegos/{slug}/index.html'
    if path != expected or urlsplit(value).query or urlsplit(value).fragment:
        raise ValueError('La dirección debe corresponder a /static/juegos/<identificador>/index.html, sin parámetros.')
    if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', slug) or slug == 'compartido':
        raise ValueError('Identificador de juego no permitido.')
    return expected


def ensure_resource(slug: str):
    root = GAME_ROOT.resolve()
    entry = (root / slug / 'index.html').resolve()
    if not entry.is_relative_to(root) or not entry.is_file():
        raise ValueError('El juego debe estar alojado en AgeCare antes de activarlo.')

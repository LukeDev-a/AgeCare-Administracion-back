"""Importación acotada de posts WordPress. No consulta URLs ni solicita IA."""
import hashlib
import json
from datetime import datetime
from urllib.parse import urlsplit, urlunsplit

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select, or_

from app import models
from app.content_pipeline import control
from app.content_providers import SOURCE, plain_text
from app.errors import ApiError, invalid
from app.security import as_utc

MAX_IMPORT_BYTES = 2 * 1024 * 1024


class RenderedText(BaseModel):
    rendered: str = Field(min_length=1, max_length=500_000)


class WordPressPost(BaseModel):
    id: int = Field(gt=0, strict=True)
    title: RenderedText
    content: RenderedText
    link: str = Field(max_length=2000)
    date_gmt: datetime | None = None
    modified_gmt: datetime | None = None


async def read_posts(request):
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > MAX_IMPORT_BYTES:
            raise ApiError(413, 'IMPORT_TOO_LARGE', 'El archivo no puede superar 2 MB.')
    try:
        posts = json.loads(data.decode('utf-8-sig'))
        if not isinstance(posts, list) or not 1 <= len(posts) <= 100:
            raise ValueError()
        result = []
        # Validar todo antes de guardar: un registro inválido rechaza el archivo completo.
        for entry in posts:
            post = WordPressPost.model_validate(entry)
            parts = urlsplit(post.link)
            if (parts.scheme != 'https' or parts.netloc.lower() != 'www.cuentamealgobueno.com'
                    or not parts.path.startswith('/') or any(c.isspace() for c in post.link)):
                raise ValueError()
            title, text = plain_text(post.title.rendered), plain_text(post.content.rendered)
            if not title or not text or len(title) > 4000 or len(text) > 100_000:
                raise ValueError()
            embedded = entry.get('_embedded', {})
            authors = embedded.get('author', []) if isinstance(embedded, dict) else []
            author = authors[0].get('name') if isinstance(authors, list) and authors and isinstance(authors[0], dict) else None
            result.append(dict(external_id=post.id, title=title, original_text=text,
                source_url=urlunsplit(('https', 'www.cuentamealgobueno.com', parts.path.rstrip('/') + '/', '', '')),
                author=author[:300] if isinstance(author, str) else None,
                source_date=as_utc(post.date_gmt) if post.date_gmt else None,
                source_modified=as_utc(post.modified_gmt) if post.modified_gmt else None,
                source_hash=hashlib.sha256((title + '\n' + text).encode()).hexdigest()))
        return result
    except (ValueError, TypeError, AttributeError, ValidationError, RecursionError):
        raise invalid('INVALID_NEWS_IMPORT', 'El archivo debe contener de 1 a 100 noticias JSON de Cuéntame Algo Bueno, con identificador, título, contenido y enlace válidos. Guarda la respuesta de su API, no una página HTML.') from None


async def import_posts(db, posts):
    # Comparte bloqueo con el recopilador; no avanza su cursor ni altera sus cuotas.
    await control(db, 'collection')
    counts = {'candidates': 0, 'duplicates': 0, 'changed': 0}
    for post in posts:
        existing = await db.scalar(select(models.NewsCandidate).where(models.NewsCandidate.source == SOURCE,
            or_(models.NewsCandidate.external_id == post['external_id'],
                models.NewsCandidate.source_url == post['source_url'],
                models.NewsCandidate.source_hash == post['source_hash'])).with_for_update())
        if not existing:
            db.add(models.NewsCandidate(source=SOURCE, **post))
            counts['candidates'] += 1
        else:
            counts['duplicates'] += 1
            if existing.source_hash != post['source_hash']:
                existing.title = post['title']; existing.original_text = post['original_text']
                existing.source_hash = post['source_hash']; existing.source_modified = post['source_modified']
                existing.source_changed = True; existing.rights_status = 'uncertain'
                existing.adaptation = None
                if existing.status not in {'discarded', 'drafted'}:
                    existing.status = 'pending'
                if existing.item_id:
                    item = await db.get(models.ContentItem, existing.item_id)
                    if item: item.approved_version = None
                counts['changed'] += 1
        await db.flush()
    return counts

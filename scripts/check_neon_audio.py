"""Diagnóstico de solo lectura: estados TTS, sin texto, cuentas ni secretos."""
import asyncio
import json

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.database_urls import database_connect_args
from scripts.migrate_neon_0016 import read_runtime, verify_tls


async def main():
    url = read_runtime()
    engine = create_async_engine(url, hide_parameters=True,
        connect_args={**database_connect_args(url), 'timeout': 20, 'command_timeout': 20})
    try:
        async with engine.connect() as conn:
            await verify_tls(conn)
            await conn.execute(text('SET TRANSACTION READ ONLY'))
            result = await conn.execute(text('''SELECT j.kind, j.status, j.attempts,
                j.error, j.created_at, j.available_at, j.finished_at,
                i.audio_status, i.audio_error, i.text_version=i.approved_version AS approved,
                length(i.body) AS text_characters
                FROM content_jobs j LEFT JOIN content_items i ON i.id=j.target_id
                WHERE j.kind IN ('tts','tts_retry') ORDER BY j.created_at DESC LIMIT 8'''))
            print(json.dumps([dict(row) for row in result.mappings()], default=str), flush=True)
    finally:
        await engine.dispose()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except Exception as error:
        raise SystemExit(f'Diagnóstico detenido ({type(error).__name__}); detalles privados omitidos.') from None

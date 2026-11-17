"""Diagnóstico explícito y acotado de TTS en Docker local, nunca en Neon."""
import argparse
import asyncio
import io
import json
import re
import time
import wave
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from app import models, content_providers as provider
from app.config import get_settings
from app.database import get_session_factory
from app.content_pipeline import reserve_quota, provider_day, narrate_with_fallback
from app.content_editorial import editorial_ready
from app.content_audio import split_audio_text, join_audio


def safe_audio_metadata(data):
    result = provider.response_metadata(data)
    candidates = data.get('candidates', []) if isinstance(data, dict) else []
    first = candidates[0] if isinstance(candidates, list) and candidates else {}
    content = first.get('content', {}) if isinstance(first, dict) else {}
    parts = content.get('parts', []) if isinstance(content, dict) else []
    result['parts'] = []
    for part in parts[:10] if isinstance(parts, list) else []:
        if not isinstance(part, dict):
            continue
        inline = part.get('inlineData')
        if not isinstance(inline, dict):
            result['parts'].append({'kind': 'text' if 'text' in part else 'other'})
            continue
        mime = inline.get('mimeType')
        category = mime.split(';')[0].strip().lower() if isinstance(mime, str) else None
        encoded = inline.get('data')
        result['parts'].append({'kind': 'inline',
            'format': category if category in {'audio/l16', 'audio/pcm', 'audio/wav', 'audio/x-wav', 'audio/mpeg', 'audio/ogg'} else 'unknown',
            'encoded_length': len(encoded) if isinstance(encoded, str) else None})
    return result


async def run(mode, model=None, fallback=False):
    settings = get_settings()
    url = make_url(settings.database_url)
    if settings.environment != 'dev' or url.host not in {'db', 'localhost', '127.0.0.1'}:
        raise RuntimeError('LOCAL_DOCKER_REQUIRED')
    safe_model = settings.gemini_tts_model if re.fullmatch(r'[a-z0-9._-]{1,100}', settings.gemini_tts_model) else 'invalid'
    report = {'mode': mode, 'key_configured': bool(settings.gemini_api_key),
        'free_tier_confirmed': settings.gemini_free_tier_confirmed,
        'worker_enabled': settings.content_worker_enabled, 'tts_model': safe_model,
        'tts_models': list(provider.tts_models()),
        'quota_day': provider_day()}
    async with get_session_factory()() as db:
        await db.execute(text('SET TRANSACTION READ ONLY'))
        jobs = (await db.execute(select(models.ContentJob.kind, models.ContentJob.status,
            models.ContentJob.attempts, models.ContentJob.error)
            .where(models.ContentJob.kind.in_(['tts','tts_retry']))
            .order_by(models.ContentJob.created_at.desc()).limit(6))).mappings().all()
        report['jobs'] = [dict(row) for row in jobs]
        quota = await db.scalar(select(models.ContentControl).where(models.ContentControl.key == 'quota_tts'))
        if quota:
            report['new_audio_quota'] = {key: (quota.data or {}).get(key) for key in ('day','new_audio')}
        rows = (await db.scalars(select(models.ContentControl).where(models.ContentControl.key.startswith('quota_tts_')))).all()
        report['model_quotas'] = {row.key: {key: (row.data or {}).get(key) for key in ('day','count','blocked_until')} for row in rows}
        probe_text = 'Esta es una prueba de audio de AgeCare. La lectura debe ser clara y pausada.'
        if mode == 'long':
            sentences = [
                'La biblioteca del barrio abre sus puertas por la mañana y ofrece un espacio tranquilo para leer, conversar y descubrir nuevas historias.',
                'En la sala principal hay mesas amplias, buena iluminación y una colección de libros organizada por temas para facilitar la búsqueda.',
                'Quienes visitan el lugar pueden elegir una novela, revisar una revista o compartir con otras personas una recomendación de lectura.',
                'El taller de relatos invita a recordar paisajes, describir una fotografía y escribir unas líneas sobre una experiencia cotidiana.',
                'Cada participante avanza a su propio ritmo y puede pedir que una instrucción se repita con palabras claras y ejemplos sencillos.',
                'Durante la pausa se prepara una mesa con agua y se abren las ventanas para disfrutar de la luz y observar los árboles de la plaza.',
                'El grupo conversa sobre sus preferencias, escucha distintas opiniones y selecciona una historia para comentar en el siguiente encuentro.',
                'Al terminar la actividad se ordenan los materiales, se revisan los préstamos y se dejan anotadas las preguntas para la próxima visita.',
                'La encargada muestra el calendario de encuentros y explica que cada jueves habrá una conversación dedicada a un libro elegido por los asistentes.',
                'En una esquina se encuentra el rincón de historia local, donde se conservan mapas, fotografías antiguas y cuadernos con recuerdos del vecindario.',
                'Una visitante reconoce en una imagen la calle donde aprendió a andar en bicicleta y comparte ese recuerdo con quienes están sentados cerca.',
                'El equipo propone reunir estas experiencias en una pequeña exposición que permita descubrir cómo ha cambiado la vida cotidiana del sector.',
                'Para organizarla, se forman equipos pequeños y se reparte una hoja donde cada persona puede anotar el objeto o la fotografía que le gustaría presentar.',
                'No es necesario llevar materiales valiosos; una postal, una receta escrita a mano o una entrada de cine también pueden abrir una conversación interesante.',
                'Antes de incorporar cualquier imagen a la exposición, se pide autorización a su dueño y se acuerda el nombre que aparecerá junto a la descripción.',
                'Las cartelas se preparan con letras grandes y un contraste claro, pensando en que todos los visitantes puedan leerlas con comodidad desde cierta distancia.',
                'Además de las actividades presenciales, la biblioteca conserva una lista de recomendaciones que puede consultarse en una carpeta junto al mostrador.',
                'Cada recomendación incluye el título, una breve explicación del tema y la ubicación del ejemplar, sin revelar el desenlace de las historias de ficción.',
                'El sábado se realizará una jornada de intercambio de libros, con una mesa destinada a novelas y otra para poesía, viajes y relatos de naturaleza.',
                'Las personas que no lleven libros también podrán participar, recorrer las mesas y conversar con los voluntarios sobre las lecturas que más disfrutan.',
                'Quienes prefieran escuchar encontrarán una selección de grabaciones y unos auriculares que el personal explica cómo utilizar antes de iniciar la reproducción.',
                'Se recomienda ajustar el volumen a un nivel cómodo y realizar una pausa si surge cansancio, sin necesidad de terminar una grabación en una sola visita.',
                'La entrada está señalizada desde la plaza y el pasillo principal se mantiene despejado para facilitar el desplazamiento de personas con distintas necesidades.',
                'Al despedirse, los participantes comentan qué actividad les gustaría repetir y dejan sus sugerencias en una caja preparada junto a la puerta de salida.',
                'Con estas propuestas se preparará el encuentro del próximo mes. La invitación final es sencilla: acercarse, elegir una historia y disfrutar de la lectura compartida.',
            ]
            probe_text = 'Texto de prueba para comprobar una narración extensa. '
            index = 0
            while index < len(sentences) and len(probe_text)+len(sentences[index])+2 <= 4000:
                probe_text += sentences[index]+'\n\n'
                index += 1
        if mode == 'item':
            items = (await db.scalars(select(models.ContentItem)
                .where(models.ContentItem.deleted_at.is_(None), models.ContentItem.status == 'draft')
                .order_by(models.ContentItem.updated_at.desc()).limit(30))).all()
            eligible = [item for item in items if editorial_ready(item)]
            if not eligible:
                raise RuntimeError('NO_APPROVED_LOCAL_ITEM')
            item = max(eligible, key=lambda row: len(row.body))
            probe_text = item.title+'\n\n'+item.body
    print(json.dumps(report, default=str), flush=True)
    if mode == 'inspect':
        return
    if not settings.gemini_api_key or not settings.gemini_free_tier_confirmed:
        raise RuntimeError('FREE_PROJECT_REQUIRED')
    original = provider.gemini
    async def checked(*args, **kwargs):
        response = await original(*args, **kwargs)
        print(json.dumps({'provider_metadata':safe_audio_metadata(response)}), flush=True)
        return response
    provider.gemini = checked
    started = time.monotonic()
    try:
        chunks = split_audio_text(probe_text)
        parts = []
        probe_job = SimpleNamespace(result={})
        for index, chunk in enumerate(chunks):
            if fallback:
                audio, wait = await narrate_with_fallback(probe_job, chunk, retry=True)
            else:
                wait = await reserve_quota('tts', retry=True, model=model)
                audio = None if wait else await provider.narrate(chunk, model)
            if wait:
                print(json.dumps({'result': 'waiting_quota', 'available_at': str(wait), 'completed': index}), flush=True)
                return
            parts.append(audio)
            print(json.dumps({'chunk_ready': index + 1, 'total': len(chunks)}), flush=True)
        audio = join_audio(parts) if len(parts) > 1 else parts[0]
        with wave.open(io.BytesIO(audio), 'rb') as stream:
            duration = stream.getnframes()/stream.getframerate()
        suffix = 'fallback' if fallback else model or 'chunked'
        destination = Path(settings.content_audio_dir)/'_diagnostics'/('probe-'+mode+'-'+suffix+'.wav')
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(audio)
        result = {'result':'ready','characters':len(probe_text),'seconds':round(duration,2),
            'bytes':len(audio),'elapsed_seconds':round(time.monotonic()-started,2),
            'models_used': probe_job.result.get('tts_models_used') if fallback else [model or settings.gemini_tts_model] * len(chunks)}
        destination.with_suffix('.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        print(json.dumps(result),flush=True)
    except provider.ProviderError as error:
        print(json.dumps({'result':'failed','code':error.code,'characters':len(probe_text),
            'elapsed_seconds':round(time.monotonic()-started,2)}),flush=True)
    finally:
        provider.gemini = original


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode',choices=('inspect','short','long','item'),default='inspect')
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument('--model', choices=sorted(provider.TTS_MODELS))
    selection.add_argument('--fallback', action='store_true', help='Prueba la cadena configurada con sus cuotas por modelo.')
    try:
        arguments=parser.parse_args()
        asyncio.run(run(arguments.mode, arguments.model, arguments.fallback))
    except Exception as error:
        code = str(error) if type(error) is RuntimeError and str(error) in {'LOCAL_DOCKER_REQUIRED','NO_APPROVED_LOCAL_ITEM','FREE_PROJECT_REQUIRED'} else None
        print(json.dumps({'result':'diagnostic_error','type':type(error).__name__,'code':code}),flush=True)
        raise SystemExit(1) from None

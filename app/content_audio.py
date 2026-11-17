"""Tramos acotados de lectura y unión PCM sin recodificar ni modificar el texto."""
import io
import wave
from app.content_providers import ProviderError


def split_audio_text(text, limit=1200):
    chunks = []
    remaining = text.strip()
    while len(remaining) > limit:
        boundary = remaining.rfind('\n\n', 0, limit + 1)
        if boundary < limit // 2:
            boundary = remaining.rfind(' ', 0, limit + 1)
        if boundary <= 0:
            boundary = limit
        chunks.append(remaining[:boundary].strip())
        remaining = remaining[boundary:].lstrip()
    if remaining:
        chunks.append(remaining)
    return chunks


def join_audio(parts):
    frames = []
    expected = None
    try:
        for part in parts:
            with wave.open(io.BytesIO(part), 'rb') as source:
                signature = (source.getnchannels(), source.getsampwidth(), source.getframerate(), source.getcomptype())
                if expected is None:
                    expected = signature
                if signature != expected or signature[0:2] != (1, 2) or signature[3] != 'NONE':
                    raise ValueError()
                data = source.readframes(source.getnframes())
                if not data or len(data) != source.getnframes() * 2:
                    raise ValueError()
                frames.append(data)
        if not expected:
            raise ValueError()
        output = io.BytesIO()
        with wave.open(output, 'wb') as destination:
            destination.setnchannels(expected[0])
            destination.setsampwidth(expected[1])
            destination.setframerate(expected[2])
            destination.writeframes(b''.join(frames))
        return output.getvalue()
    except (wave.Error, EOFError, ValueError):
        raise ProviderError('INVALID_AUDIO_OUTPUT') from None

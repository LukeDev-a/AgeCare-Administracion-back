import base64
import io
import json
import wave
import pytest
from app import content_providers as providers


@pytest.mark.asyncio
async def test_gemini_text_contract_and_invalid_output(monkeypatch):
    async def response(data, model):
        assert data['generationConfig']['responseMimeType'] == 'application/json'
        assert 'systemInstruction' in data
        return {'candidates': [{'content': {'parts': [{'text': json.dumps({
            'title': 'Noticia adaptada', 'body': 'Texto adaptado con contexto suficiente.',
            'classification': 'Cultura', 'changes': 'Frases simplificadas', 'unsuitable': False})}]}}]}
    monkeypatch.setattr(providers, 'gemini', response)
    assert (await providers.adapt_news('Original', 'Texto de fuente'))['unsuitable'] is False
    async def invalid(*args): return {'candidates': []}
    monkeypatch.setattr(providers, 'gemini', invalid)
    with pytest.raises(providers.ProviderError, match='INVALID_AI_OUTPUT'):
        await providers.adapt_news('Original', 'Texto')


@pytest.mark.asyncio
@pytest.mark.parametrize('mime,rate', [
    ('audio/L16;codec=pcm;rate=24000', 24000),
    ('audio/l16; rate=24000; channels=1', 24000),
    ('audio/pcm;rate=16000', 16000),
])
async def test_pcm_audio_is_wrapped_in_wav_without_network(monkeypatch, mime, rate):
    pcm = b'\x01\x00' * 240
    async def audio(data, model):
        assert data['generationConfig']['responseModalities'] == ['AUDIO']
        return {'candidates': [{'content': {'parts': [{'inlineData': {
            'mimeType': mime, 'data': base64.b64encode(pcm).decode()}}]}}]}
    monkeypatch.setattr(providers, 'gemini', audio)
    result = await providers.narrate('Texto aprobado')
    with wave.open(io.BytesIO(result)) as decoded:
        assert decoded.getframerate() == rate and decoded.getnchannels() == 1
        assert decoded.readframes(240) == pcm


@pytest.mark.asyncio
@pytest.mark.parametrize('mime', ['audio/l16;rate=invalid', 'audio/l16;channels=2',
    'audio/l16;rate=0', 'audio/l16;codec=mp3', 'audio/l16-invalid', None, 123])
async def test_invalid_audio_metadata_is_rejected(monkeypatch, mime):
    async def audio(*args):
        return {'candidates': [{'content': {'parts': [{'inlineData': {
            'mimeType': mime, 'data': base64.b64encode(b'\x00\x00' * 20).decode()}}]}}]}
    monkeypatch.setattr(providers, 'gemini', audio)
    with pytest.raises(providers.ProviderError, match='INVALID_AUDIO_OUTPUT'):
        await providers.narrate('Prueba')


@pytest.mark.asyncio
async def test_unconfigured_gemini_does_not_call_network(monkeypatch):
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), 'gemini_api_key', '')
    def forbidden(*args, **kwargs): raise AssertionError('No debe llamar al proveedor')
    monkeypatch.setattr(providers, 'request_json', forbidden)
    with pytest.raises(providers.ProviderError, match='GEMINI_NOT_CONFIGURED'):
        await providers.gemini({}, 'gemini-3.5-flash-lite')

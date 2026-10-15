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
async def test_pcm_audio_is_wrapped_in_wav_without_network(monkeypatch):
    pcm = b'\x01\x00' * 240
    async def audio(data, model):
        assert data['generationConfig']['responseModalities'] == ['AUDIO']
        return {'candidates': [{'content': {'parts': [{'inlineData': {
            'mimeType': 'audio/L16;codec=pcm;rate=24000', 'data': base64.b64encode(pcm).decode()}}]}}]}
    monkeypatch.setattr(providers, 'gemini', audio)
    result = await providers.narrate('Texto aprobado')
    with wave.open(io.BytesIO(result)) as decoded:
        assert decoded.getframerate() == 24000 and decoded.getnchannels() == 1
        assert decoded.readframes(240) == pcm


@pytest.mark.asyncio
async def test_unconfigured_gemini_does_not_call_network(monkeypatch):
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), 'gemini_api_key', '')
    def forbidden(*args, **kwargs): raise AssertionError('No debe llamar al proveedor')
    monkeypatch.setattr(providers, 'request_json', forbidden)
    with pytest.raises(providers.ProviderError, match='GEMINI_NOT_CONFIGURED'):
        await providers.gemini({}, 'gemini-3.5-flash-lite')

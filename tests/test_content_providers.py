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


@pytest.mark.asyncio
@pytest.mark.parametrize('finish', ['MAX_TOKENS', 'SAFETY', 'private-response-marker', []])
async def test_missing_audio_diagnostic_exposes_only_allowed_metadata(monkeypatch, caplog, finish):
    async def response(*args):
        return {'candidates': [{'finishReason': finish, 'content': {
            'parts': [{'text': 'private-provider-response'}]}}],
            'promptFeedback': {'blockReason': 'private-block-message'},
            'usageMetadata': {'candidatesTokenCount': 123}}
    monkeypatch.setattr(providers, 'gemini', response)
    with pytest.raises(providers.ProviderError, match='INVALID_AUDIO_OUTPUT'):
        await providers.narrate('private-editorial-text')
    record = next(r for r in caplog.records if r.message.startswith('AGECARE_EDITORIAL '))
    data = json.loads(record.message.removeprefix('AGECARE_EDITORIAL '))
    assert data['reason'] == 'missing_audio_part'
    assert data['finish_reason'] == (finish if isinstance(finish, str) and finish in {'MAX_TOKENS', 'SAFETY'} else 'unknown')
    assert data['output_tokens'] == 123 and data['text_characters'] == 22
    assert 'private-' not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize('mime,encoded,reason', [
    ('private-mime', 'AAAA', 'invalid_audio_metadata'),
    ('audio/l16', 'private-audio-bytes', 'invalid_audio_bytes'),
])
async def test_audio_validation_logs_stage_without_payload(monkeypatch, caplog, mime, encoded, reason):
    async def response(*args):
        return {'candidates': [{'content': {'parts': [{'inlineData': {
            'mimeType': mime, 'data': encoded}}]}}]}
    monkeypatch.setattr(providers, 'gemini', response)
    with pytest.raises(providers.ProviderError, match='INVALID_AUDIO_OUTPUT'):
        await providers.narrate('private-body')
    assert f'"reason": "{reason}"' in caplog.text
    assert 'private-' not in caplog.text


@pytest.mark.parametrize('failure,reason,code', [
    (TimeoutError('private-timeout'), 'timeout', 'PROVIDER_UNAVAILABLE'),
    (providers.URLError(TimeoutError('private-timeout')), 'timeout', 'PROVIDER_UNAVAILABLE'),
    (providers.URLError('private-url'), 'connection_error', 'PROVIDER_UNAVAILABLE'),
    (ValueError('private-invalid-json'), 'invalid_json', 'PROVIDER_UNAVAILABLE'),
    (providers.HTTPError('https://private-url', 429, 'private-message', {}, None), 'http_error', 'QUOTA_REACHED'),
    (providers.HTTPError('https://private-url', 503, 'private-message', {}, None), 'http_error', 'PROVIDER_UNAVAILABLE'),
])
def test_transport_diagnostics_never_log_secrets(monkeypatch, caplog, failure, reason, code):
    class Opener:
        def open(self, *args, **kwargs):
            raise failure
    monkeypatch.setattr(providers, 'build_opener', lambda *args: Opener())
    with pytest.raises(providers.ProviderError, match=code):
        providers.request_json('https://private-url', {'generationConfig': {'responseModalities': ['AUDIO']},
            'contents': 'private-body'}, key='private-key')
    assert f'"reason": "{reason}"' in caplog.text
    assert '"operation": "tts"' in caplog.text
    assert 'private-' not in caplog.text

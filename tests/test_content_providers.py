import base64
import io
import json
import logging
import wave
import pytest
from app import content_providers as providers


def test_diagnostics_use_uvicorn_console_when_root_has_no_handler(monkeypatch):
    stream = io.StringIO()
    assert providers.logger.name == 'uvicorn.error'
    monkeypatch.setattr(providers.logger, 'handlers', [logging.StreamHandler(stream)])
    monkeypatch.setattr(providers.logger, 'propagate', False)
    monkeypatch.setattr(providers.logger, 'disabled', False)
    monkeypatch.setattr(logging.getLogger(), 'handlers', [])
    providers.diagnostic('worker', 'diagnostics_ready', revision=2, enabled=True)
    assert 'AGECARE_EDITORIAL' in stream.getvalue()
    assert '"reason": "diagnostics_ready"' in stream.getvalue()


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
@pytest.mark.parametrize('model', ['gemini-3.8-flash-lite-tts', 'gemini-3.8-flash-tts'])
async def test_modern_tts_uses_verbatim_transcript_and_decodes_wav(monkeypatch, model):
    pcm = b'\x02\x00' * 240
    output = io.BytesIO()
    with wave.open(output, 'wb') as stream:
        stream.setnchannels(1); stream.setsampwidth(2); stream.setframerate(24000)
        stream.writeframes(pcm)
    async def response(data, selected):
        assert selected == model
        part = data['contents'][0]['parts'][0]
        assert part['text'] == 'Texto aprobado'
        assert 'Spanish' in part['speech_metadata']['style']
        assert data['generationConfig']['speechConfig']['voiceConfig'] == {'voice': 'Kore'}
        return {'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'inlineData': {
            'mimeType': 'audio/wav', 'data': base64.b64encode(output.getvalue()).decode()}}]}}]}
    monkeypatch.setattr(providers, 'gemini', response)
    result = await providers.narrate('Texto aprobado', model)
    with wave.open(io.BytesIO(result)) as stream:
        assert stream.getnframes() == 240 and stream.getframerate() == 24000
        assert stream.readframes(240) == pcm


@pytest.mark.asyncio
@pytest.mark.parametrize('payload', [b'not-wav', b'RIFF\x00\x00\x00\x00WAVE', b''])
async def test_corrupt_wav_is_rejected(monkeypatch, payload):
    async def response(*args):
        return {'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'inlineData': {
            'mimeType': 'audio/wav', 'data': base64.b64encode(payload).decode()}}]}}]}
    monkeypatch.setattr(providers, 'gemini', response)
    with pytest.raises(providers.ProviderError, match='INVALID_AUDIO_OUTPUT'):
        await providers.narrate('Texto', 'gemini-3.8-flash-tts')


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
@pytest.mark.parametrize('audio,expected', [(True, 300), (False, 60)])
async def test_only_audio_uses_extended_timeout(monkeypatch, audio, expected):
    from app.config import get_settings
    settings=get_settings()
    monkeypatch.setattr(settings, 'gemini_api_key', 'test-only-key')
    monkeypatch.setattr(settings, 'gemini_free_tier_confirmed', True)
    monkeypatch.setattr(settings, 'gemini_tts_timeout_seconds', 300)
    def request(url, data, key, *, timeout):
        assert timeout == expected
        return {'ok': True}
    monkeypatch.setattr(providers, 'request_json', request)
    data={'generationConfig': {'responseModalities':['AUDIO']}} if audio else {}
    assert await providers.gemini(data, 'test-model') == {'ok': True}


def test_request_json_passes_custom_timeout_to_transport(monkeypatch):
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, maximum): return b'{"ok":true}'
    class Opener:
        def open(self, request, *, timeout):
            assert timeout == 300
            return Response()
    monkeypatch.setattr(providers, 'build_opener', lambda *args: Opener())
    assert providers.request_json('https://example.test', timeout=300) == {'ok':True}


@pytest.mark.asyncio
@pytest.mark.parametrize('finish', ['MAX_TOKENS', 'SAFETY', 'private-response-marker', []])
async def test_missing_audio_diagnostic_exposes_only_allowed_metadata(monkeypatch, caplog, finish):
    async def response(*args):
        return {'candidates': [{'finishReason': finish, 'content': {
            'parts': [{'text': 'private-provider-response'}]}}],
            'promptFeedback': {'blockReason': 'private-block-message'},
            'usageMetadata': {'candidatesTokenCount': 123}}
    monkeypatch.setattr(providers, 'gemini', response)
    with pytest.raises(providers.ProviderError, match='AUDIO_CONTENT_BLOCKED' if finish == 'SAFETY' else 'INVALID_AUDIO_OUTPUT'):
        await providers.narrate('private-editorial-text')
    record = next(r for r in caplog.records if r.message.startswith('AGECARE_EDITORIAL '))
    data = json.loads(record.message.removeprefix('AGECARE_EDITORIAL '))
    assert data['reason'] == ('provider_blocked' if finish == 'SAFETY' else 'incomplete_audio' if finish == 'MAX_TOKENS' else 'missing_audio_part')
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


@pytest.mark.asyncio
@pytest.mark.parametrize('finish,code', [('SAFETY', 'AUDIO_CONTENT_BLOCKED'),
    ('MAX_TOKENS', 'INVALID_AUDIO_OUTPUT'), ('OTHER', 'INVALID_AUDIO_OUTPUT')])
async def test_partial_pcm_is_not_accepted_as_complete_audio(monkeypatch, finish, code):
    async def response(*args):
        return {'candidates': [{'finishReason': finish, 'content': {'parts': [{'inlineData': {
            'mimeType': 'audio/l16', 'data': base64.b64encode(b'\x00\x00' * 24).decode()}}]}}]}
    monkeypatch.setattr(providers, 'gemini', response)
    with pytest.raises(providers.ProviderError, match=code):
        await providers.narrate('Texto de prueba')


@pytest.mark.asyncio
async def test_prompt_block_without_candidates_has_specific_error(monkeypatch):
    async def response(*args):
        return {'promptFeedback': {'blockReason': 'SAFETY'}}
    monkeypatch.setattr(providers, 'gemini', response)
    with pytest.raises(providers.ProviderError, match='AUDIO_CONTENT_BLOCKED'):
        await providers.narrate('Texto de prueba')


@pytest.mark.parametrize('failure,reason,code', [
    (TimeoutError('private-timeout'), 'timeout', 'PROVIDER_UNAVAILABLE'),
    (providers.URLError(TimeoutError('private-timeout')), 'timeout', 'PROVIDER_UNAVAILABLE'),
    (providers.URLError('private-url'), 'connection_error', 'PROVIDER_UNAVAILABLE'),
    (ValueError('private-invalid-json'), 'invalid_json', 'PROVIDER_UNAVAILABLE'),
    (providers.HTTPError('https://private-url', 429, 'private-message', {}, None), 'http_error', 'QUOTA_REACHED'),
    (providers.HTTPError('https://private-url', 503, 'private-message', {}, None), 'http_error', 'PROVIDER_UNAVAILABLE'),
    (providers.HTTPError('https://private-url', 404, 'private-message', {}, None), 'http_error', 'PROVIDER_UNAVAILABLE'),
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

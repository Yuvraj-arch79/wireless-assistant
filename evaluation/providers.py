"""Evaluation-only HTTP adapters; no retries, redirects, tools or paid fallback."""
import os
import re
import httpx
from wireless_assistant.common import AppError, canonical, load_json

BASES = {'gemini': 'https://generativelanguage.googleapis.com/v1beta/',
         'groq': 'https://api.groq.com/openai/v1/', 'mistral': 'https://api.mistral.ai/v1/'}
MODELS = {'gemini': 'gemini-3.1-flash-lite', 'groq': 'openai/gpt-oss-120b', 'mistral': 'mistral-small-latest'}
MAX_BYTES = 2 * 1024 * 1024


def configured_model(provider):
    model = os.getenv('WA_EVAL_' + provider.upper() + '_MODEL') or MODELS[provider]
    if not re.fullmatch(r'[A-Za-z0-9._/-]{1,160}', model) or '..' in model:
        raise AppError('MODEL_CONFIG', 'Invalid model configuration.')
    return model


def safe_error_detail(raw):
    # Only known protocol/schema words survive; never emit echoed input or keys.
    try: error = load_json(raw.decode('utf-8')).get('error', {})
    except (ValueError, UnicodeError, AttributeError): return 'unavailable'
    if not isinstance(error, dict): return 'unavailable'
    allowed = set("invalid_request_error invalid_json_schema json_validate_failed model_not_found unsupported schema json_schema response_format name strict properties additionalProperties required anyOf oneOf allOf type null object array integer number string boolean enum items defs ref result reasoning_effort include_reasoning max_tokens temperature messages model value invalid missing must be is are not supported allowed expected found failed to generate JSON please adjust your prompt field parameter argument request validation error for with at in the a an of and or cannot contains exceed maximum depth limit too many complex nested false true low medium high branches branch identical first keys key discriminator share sharing common ambiguous ambiguity union parsing parse compiler compilation compile schema_validation_failed".split())
    parts = []
    for field in ('type', 'code', 'param', 'message'):
        value = error.get(field)
        if isinstance(value, str):
            words = re.findall(r'[A-Za-z_]+|[0-9]+', value[:1000])
            parts.append(field + ': ' + ' '.join(word if word in allowed else '<redacted>' for word in words))
    return '; '.join(parts)[:1500] or 'unavailable'


def safe_quota_detail(raw, headers):
    """Only numeric quota counters/durations; never echo identities or prompts."""
    detail = {}
    for name in ('retry-after', 'x-ratelimit-limit-requests', 'x-ratelimit-limit-tokens',
                 'x-ratelimit-remaining-requests', 'x-ratelimit-remaining-tokens',
                 'x-ratelimit-reset-requests', 'x-ratelimit-reset-tokens'):
        value = headers.get(name, '')
        if isinstance(value, str) and re.fullmatch(r'(?:[0-9]{1,12}(?:\.[0-9]{1,6})?(?:ms|s|m|h|d)?){1,5}', value):
            detail[name] = value
    try: error = load_json(raw.decode('utf-8')).get('error', {})
    except (ValueError, UnicodeError, AttributeError): error = {}
    message = error.get('message', '') if isinstance(error, dict) else ''
    if isinstance(message, str):
        for scope in ('TPM', 'TPD', 'RPM', 'RPD', 'ITPM', 'OTPM'):
            if re.search(r'\b' + scope + r'\b', message[:4096]): detail['scope'] = scope
        for label in ('Limit', 'Used', 'Requested'):
            match = re.search(r'\b' + label + r'\s*:?\s*([0-9]{1,12})(?![0-9])\b', message[:4096], re.I)
            if match: detail[label.lower()] = int(match.group(1))
    return canonical(detail)


def request(provider, method, path, body=None, *, diagnostics=False):
    key = os.getenv(provider.upper() + '_API_KEY')
    if not key:
        raise AppError('KEY_MISSING', 'Provider key is absent.')
    headers = {'x-goog-api-key': key} if provider == 'gemini' else {'Authorization': 'Bearer ' + key}
    try:
        with httpx.Client(timeout=httpx.Timeout(20, connect=8), trust_env=False, follow_redirects=False) as client:
            with client.stream(method, BASES[provider] + path, headers=headers, json=body) as response:
                if response.status_code != 200:
                    code = {401:'AUTH',403:'AUTH',429:'QUOTA',404:'MODEL_UNAVAILABLE'}.get(response.status_code, 'HTTP_' + str(response.status_code))
                    detail = 'Provider request failed.'
                    if diagnostics and response.status_code in (400, 429):
                        raw_error = bytearray()
                        for part in response.iter_bytes():
                            raw_error.extend(part)
                            if len(raw_error) > 65536: break
                        if response.status_code == 429:
                            detail = safe_quota_detail(raw_error if len(raw_error) <= 65536 else b'', response.headers)
                        elif len(raw_error) <= 65536: detail = safe_error_detail(raw_error)
                    raise AppError(code, detail, response.status_code)
                raw = bytearray()
                for part in response.iter_bytes():
                    raw.extend(part)
                    if len(raw) > MAX_BYTES:
                        raise AppError('RESPONSE_LIMIT', 'Response exceeded bound.')
                return load_json(raw.decode('utf-8'))
    except httpx.ConnectTimeout:
        raise AppError('CONNECT_TIMEOUT', 'Connection timed out.') from None
    except httpx.ReadTimeout:
        raise AppError('READ_TIMEOUT', 'Response timed out.') from None
    except httpx.WriteTimeout:
        raise AppError('WRITE_TIMEOUT', 'Request write timed out.') from None
    except httpx.TimeoutException:
        raise AppError('TIMEOUT', 'Provider timed out.') from None
    except httpx.HTTPError:
        raise AppError('NETWORK', 'Provider network error.') from None
    except (ValueError, UnicodeError):
        raise AppError('FORMAT', 'Invalid provider JSON.') from None


def probe(provider, model):
    # Metadata only: no inference, no model output or key included in the result.
    if provider == 'groq':
        data = request(provider, 'GET', 'models')
        entries = data.get('data')
        if not isinstance(entries, list) or len(entries) > 1000:
            raise AppError('CATALOG_FORMAT', 'Invalid model catalog.')
        if not any(isinstance(entry, dict) and entry.get('id') == model and entry.get('active') is not False for entry in entries):
            raise AppError('MODEL_UNAVAILABLE', 'Selected model is absent or inactive in the accessible catalog.')
        return {'model_access': True}
    data = request(provider, 'GET', 'models/' + model)
    found = data.get('name', '').removeprefix('models/') if provider == 'gemini' else data.get('id')
    if found != model:
        raise AppError('MODEL_ID_MISMATCH', 'Metadata did not match requested model.')
    if provider == 'gemini' and 'generateContent' not in data.get('supportedGenerationMethods', []):
        raise AppError('METHOD_UNSUPPORTED', 'Model metadata does not advertise generateContent.')
    return {'model_access': True}


def free_confirmed(provider):
    return os.getenv("WA_" + provider.upper() + "_FREE_TIER_CONFIRMED") == "1"


def generate(provider, model, system, payload, output_tokens=2000, thinking=None):
    # Billing status cannot be inferred from possession of a key or a model listing.
    if not free_confirmed(provider):
        raise AppError('FREE_TIER_NOT_CONFIRMED', 'Free-only accounts must be confirmed before inference.')
    if provider == 'gemini':
        if thinking is None and model == 'gemini-3.1-flash-lite':
            thinking = {'thinkingLevel': 'minimal'}
        data = request(provider, 'POST', 'models/' + model + ':generateContent', {
            'systemInstruction': {'parts':[{'text':system}]},
            'contents':[{'role':'user','parts':[{'text':canonical(payload)}]}],
            'generationConfig':{'temperature':0,'maxOutputTokens':output_tokens,'responseMimeType':'application/json',
                **({'thinkingConfig': thinking} if thinking is not None else {})}})
        choices = data.get('candidates', [])
        if len(choices) != 1 or choices[0].get('finishReason') != 'STOP':
            raise AppError('INCOMPLETE', 'Blocked or truncated response.')
        text = ''.join(p.get('text','') for p in choices[0].get('content',{}).get('parts',[]) if not p.get('thought'))
    else:
        data = request(provider, 'POST', 'chat/completions', {'model':model,'temperature':0,'max_tokens':output_tokens,
            **({'reasoning_effort':'low','include_reasoning':False} if provider == 'groq' and model in ('openai/gpt-oss-20b', 'openai/gpt-oss-120b') else {}),
            'response_format':{'type':'json_object'},'messages':[{'role':'system','content':system},{'role':'user','content':canonical(payload)}]})
        choices = data.get('choices', [])
        if len(choices) != 1 or choices[0].get('finish_reason') != 'stop' or choices[0].get('message',{}).get('tool_calls'):
            raise AppError('INCOMPLETE', 'Blocked, truncated or unexpected tool response.')
        text = choices[0].get('message',{}).get('content')
    if not isinstance(text,str) or not text or len(text.encode('utf-8')) > 65536:
        raise AppError('FORMAT', 'Missing or oversized text.')
    return text

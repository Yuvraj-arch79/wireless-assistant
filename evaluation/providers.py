"""Evaluation-only HTTP adapters; no retries, redirects, tools or paid fallback."""
import os
import re
import httpx
from wireless_assistant.common import AppError, canonical, load_json

BASES = {'gemini': 'https://generativelanguage.googleapis.com/v1beta/',
         'groq': 'https://api.groq.com/openai/v1/', 'mistral': 'https://api.mistral.ai/v1/'}
MODELS = {'gemini': 'gemini-3.1-flash-lite', 'groq': 'openai/gpt-oss-20b', 'mistral': 'mistral-small-latest'}
MAX_BYTES = 2 * 1024 * 1024


def configured_model(provider):
    model = os.getenv('WA_EVAL_' + provider.upper() + '_MODEL') or MODELS[provider]
    if not re.fullmatch(r'[A-Za-z0-9._/-]{1,160}', model) or '..' in model:
        raise AppError('MODEL_CONFIG', 'Invalid model configuration.')
    return model


def request(provider, method, path, body=None):
    key = os.getenv(provider.upper() + '_API_KEY')
    if not key:
        raise AppError('KEY_MISSING', 'Provider key is absent.')
    headers = {'x-goog-api-key': key} if provider == 'gemini' else {'Authorization': 'Bearer ' + key}
    try:
        with httpx.Client(timeout=httpx.Timeout(20, connect=8), trust_env=False, follow_redirects=False) as client:
            with client.stream(method, BASES[provider] + path, headers=headers, json=body) as response:
                if response.status_code != 200:
                    code = {401:'AUTH',403:'AUTH',429:'QUOTA',404:'MODEL_UNAVAILABLE'}.get(response.status_code, 'HTTP_' + str(response.status_code))
                    raise AppError(code, 'Provider request failed.', response.status_code)
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
            **({'reasoning_effort':'low','include_reasoning':False} if provider == 'groq' and model == 'openai/gpt-oss-20b' else {}),
            'response_format':{'type':'json_object'},'messages':[{'role':'system','content':system},{'role':'user','content':canonical(payload)}]})
        choices = data.get('choices', [])
        if len(choices) != 1 or choices[0].get('finish_reason') != 'stop' or choices[0].get('message',{}).get('tool_calls'):
            raise AppError('INCOMPLETE', 'Blocked, truncated or unexpected tool response.')
        text = choices[0].get('message',{}).get('content')
    if not isinstance(text,str) or not text or len(text.encode('utf-8')) > 65536:
        raise AppError('FORMAT', 'Missing or oversized text.')
    return text

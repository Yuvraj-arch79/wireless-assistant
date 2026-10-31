"""Gemini REST adapter. One HTTP attempt; no SDK retry, tools, redirects or fallback."""
import math
import os
import httpx
from .common import AppError, canonical, load_json

ENDPOINT = 'https://generativelanguage.googleapis.com/v1beta/models/'
MAX_RESPONSE = 2 * 1024 * 1024


def request(model, method, body):
    import re
    if not re.fullmatch(r'[a-zA-Z0-9._-]+', model):
        raise AppError('MODEL_CONFIG', 'Invalid configured model name.', 503)
    key = os.environ.get('GEMINI_API_KEY')
    if not key:
        raise AppError('PROVIDER_NOT_CONFIGURED', 'Configure GEMINI_API_KEY on the server before using AI answers.', 503)
    if os.environ.get('WA_FREE_TIER_CONFIRMED') != '1':
        raise AppError('FREE_TIER_NOT_CONFIRMED', 'Confirm that this API project has billing disabled before sending requests.', 503)
    try:
        with httpx.Client(timeout=httpx.Timeout(20, connect=8), follow_redirects=False, trust_env=False) as client:
            with client.stream('POST', ENDPOINT+model+':'+method, headers={'x-goog-api-key':key}, json=body) as response:
                if response.status_code != 200:
                    status = response.status_code
                    if status == 429:
                        raise AppError('PROVIDER_QUOTA', 'The provider rate limit or quota was reached. Try again later.', 429, True)
                    if status in (401,403):
                        raise AppError('PROVIDER_AUTH', 'The configured API key or model access was rejected.', 503)
                    if status in (400,404):
                        raise AppError('PROVIDER_CONFIG', 'The provider rejected the configured model or request contract.', 503)
                    raise AppError('PROVIDER_UNAVAILABLE', 'The provider is temporarily unavailable.', 503, status >= 500)
                raw = bytearray()
                for chunk in response.iter_bytes():
                    raw.extend(chunk)
                    if len(raw) > MAX_RESPONSE:
                        raise AppError('PROVIDER_RESPONSE_LIMIT', 'Provider response exceeded the size limit.', 502)
                return load_json(raw.decode('utf-8'))
    except httpx.TimeoutException:
        raise AppError('PROVIDER_TIMEOUT', 'The provider did not respond in time.', 504, True) from None
    except httpx.HTTPError:
        raise AppError('PROVIDER_NETWORK', 'Could not connect to the provider.', 503, True) from None
    except (ValueError, UnicodeError):
        raise AppError('PROVIDER_FORMAT', 'The provider returned invalid JSON.', 502) from None


def generate(model, system, payload, output_tokens):
    response = request(model, 'generateContent', {
        'systemInstruction':{'parts':[{'text':system}]},
        'contents':[{'role':'user','parts':[{'text':canonical(payload)}]}],
        'generationConfig':{'temperature':0, 'maxOutputTokens':output_tokens, 'responseMimeType':'application/json'},
    })
    candidates = response.get('candidates', [])
    if len(candidates) != 1 or candidates[0].get('finishReason') != 'STOP':
        raise AppError('PROVIDER_INCOMPLETE', 'The provider blocked or truncated its response; no draft was released.', 502)
    parts = candidates[0].get('content', {}).get('parts', [])
    text = ''.join(p.get('text','') for p in parts if not p.get('thought'))
    if not text or len(text.encode('utf-8')) > 65536:
        raise AppError('PROVIDER_FORMAT', 'The provider returned an empty or oversized response.', 502)
    return {'text':text, 'usage':response.get('usageMetadata', {})}


def vector(values, dimensions):
    if not isinstance(values, list) or len(values) != dimensions or any(type(v) not in (float,int) or not math.isfinite(v) for v in values):
        raise AppError('EMBEDDING_SHAPE', 'Embedding dimensions or values are incompatible.', 502)
    norm = math.sqrt(sum(v*v for v in values))
    if norm < 1e-12:
        raise AppError('EMBEDDING_SHAPE', 'Embedding is a zero vector.', 502)
    return [float(v/norm) for v in values]


def embed(model, text, dimensions, task='RETRIEVAL_QUERY'):
    response = request(model, 'embedContent', {'model':'models/'+model, 'content':{'parts':[{'text':text}]},
                                             'taskType':task, 'outputDimensionality':dimensions})
    return vector(response.get('embedding', {}).get('values'), dimensions)

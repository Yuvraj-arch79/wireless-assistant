"""Two-call, no-retry Groq contract diagnosis; never logs raw replies or keys."""
import json
import os
import time
from pydantic import ValidationError
from evaluation.providers import free_confirmed, generate, request
from evaluation.readiness import ROOT, payload_for
from wireless_assistant.bounded import bounded
from wireless_assistant.common import AppError, canonical, load_json
from wireless_assistant.contracts import ADAPTERS
from wireless_assistant.prompts import COMMON, ROLES, instructions
from wireless_assistant.validation import validate_need

MODEL = 'openai/gpt-oss-20b'


def wire_schema(role):
    def convert(node):
        out = {}
        for key, value in node.items():
            if key in ('$defs', 'properties'):
                out[key] = {name: convert(child) for name, child in value.items()}
            elif key in ('oneOf', 'anyOf'):
                out['anyOf'] = [convert(child) for child in value]
            elif key == 'items': out[key] = convert(value)
            elif key == 'const': out['enum'] = [value]
            elif key in ('type', '$ref', 'enum', 'required', 'additionalProperties'): out[key] = value
        if out.get('type') == 'object':
            out['additionalProperties'] = False
            out['required'] = list(out.get('properties', {}))
        return out
    source = convert(ADAPTERS[role].json_schema())
    definitions = source.pop('$defs', {})
    return {'type': 'object', 'properties': {'result': source}, 'required': ['result'],
            'additionalProperties': False, '$defs': definitions}


def safe_errors(error, role):
    known = set()
    def visit(node):
        if isinstance(node, dict):
            known.update(node.get('properties', {}))
            if isinstance(node.get('const'), str): known.add(node['const'])
            for child in node.values(): visit(child)
        elif isinstance(node, list):
            for child in node: visit(child)
    visit(ADAPTERS[role].json_schema())
    return [{'path': [p if isinstance(p, int) or p in known else '<unknown>' for p in item['loc']],
             'type': item['type']} for item in error.errors(include_input=False, include_context=False, include_url=False)[:12]]


def inspect_response(text, role, wrapped=False):
    try: value = load_json(text)
    except (ValueError, TypeError): return {'status': 'INVALID_JSON', 'issues': []}
    if wrapped:
        if not isinstance(value, dict) or set(value) != {'result'}:
            return {'status': 'INVALID_ENVELOPE', 'issues': []}
        value = value['result']
    try: parsed = ADAPTERS[role].validate_python(value).model_dump(mode='json')
    except ValidationError as error: return {'status': 'CONTRACT_INVALID', 'issues': safe_errors(error, role)}
    return {'status': 'pass', 'issues': [], 'value': parsed}


def strict_generate(role, payload):
    if not free_confirmed('groq'): raise AppError('FREE_TIER_NOT_CONFIRMED', 'Free-only confirmation required.')
    result = request('groq', 'POST', 'chat/completions', {
        'model': MODEL, 'temperature': 0, 'max_tokens': 2000,
        'reasoning_effort': 'low', 'include_reasoning': False,
        'response_format': {'type': 'json_schema', 'json_schema': {'name': 'wireless_' + role, 'strict': True, 'schema': wire_schema(role)}},
        'messages': [{'role': 'system', 'content': COMMON + ROLES[role] + '\nTransport: wrap the role output in an object with the single key result. The supplied JSON schema defines that envelope.'},
                     {'role': 'user', 'content': canonical(payload)}]}, diagnostics=True)
    choices = result.get('choices', [])
    if len(choices) != 1 or choices[0].get('finish_reason') != 'stop' or choices[0].get('message', {}).get('tool_calls'):
        raise AppError('INCOMPLETE', 'No complete plain response.')
    text = choices[0].get('message', {}).get('content')
    if not isinstance(text, str) or not text or len(text.encode('utf-8')) > 65536:
        raise AppError('FORMAT', 'Missing or oversized response.')
    return text


def live(mode, payload):
    raw = generate('groq', MODEL, instructions('A'), payload) if mode == 'diagnose' else strict_generate('A', payload)
    result = inspect_response(raw, 'A', wrapped=mode == 'strict')
    if result['status'] == 'pass':
        output = result.pop('value')
        try:
            if output['action'] != 'clarify': raise AppError('WRONG_ACTION', 'Expected clarification.')
            validate_need(output['need'], payload['original_context'])
            ids = {r['req_id'] for r in output['need']['requirements']}
            missing = output['clarification']['missing_requirement_ids']
            if not missing or not set(missing) <= ids: raise AppError('GAP_BINDING', 'Invalid missing requirement binding.')
        except AppError as error: result['status'] = error.code
    return result


def run(payload, strict_only=False):
    report = {'maximum_calls': 1 if strict_only else 2, 'attempts': 0, 'retries': 0, 'results': []}
    if not free_confirmed('groq'): return dict(report, status='FREE_TIER_NOT_CONFIRMED')
    if not os.getenv('GROQ_API_KEY'): return dict(report, status='KEY_MISSING')
    deadline = time.monotonic() + 55
    for mode in (('strict',) if strict_only else ('diagnose', 'strict')):
        remaining = deadline - time.monotonic()
        if remaining <= 0: return dict(report, status='OPERATION_TIMEOUT')
        start = time.monotonic()
        report['attempts'] += 1
        try: result = bounded(live, (mode, payload), min(25, remaining))
        except AppError as error:
            result = {'status': error.code, 'issues': []}
            if error.code == 'HTTP_400': result['detail'] = error.message
        result.update(mode=mode, seconds=round(time.monotonic() - start, 3))
        report['results'].append(result)
        if result['status'] not in ('pass', 'CONTRACT_INVALID', 'INVALID_JSON', 'INVALID_ENVELOPE'):
            return dict(report, status=result['status'])
    return dict(report, status=report['results'][-1]['status'])


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--strict-only', action='store_true')
    args = parser.parse_args()
    suite = json.loads((ROOT / 'evaluation/cases.json').read_text(encoding='utf-8'))
    report = run(payload_for(next(c for c in suite['cases'] if c['id'] == 'B01')), strict_only=args.strict_only)
    print(json.dumps(report, ensure_ascii=True, indent=2))
    raise SystemExit(0 if report['status'] == 'pass' else 1)

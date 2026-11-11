"""Two-call, no-retry Groq contract diagnosis; never logs raw replies or keys."""
import json
import os
from wireless_assistant.provider_contracts import wire_schema, normalize_wire, safe_errors, inspect_response
import time
from pydantic import ValidationError
from evaluation.providers import free_confirmed, generate, request
from evaluation.readiness import ROOT, payload_for
from wireless_assistant.bounded import bounded
from wireless_assistant.common import AppError, canonical, load_json
from wireless_assistant.contracts import ADAPTERS
from wireless_assistant.prompts import COMMON, ROLES, instructions
from wireless_assistant.validation import validate_need

MODEL = 'openai/gpt-oss-120b'










def strict_generate(role, payload):
    if not free_confirmed('groq'): raise AppError('FREE_TIER_NOT_CONFIRMED', 'Free-only confirmation required.')
    result = request('groq', 'POST', 'chat/completions', {
        'model': MODEL, 'temperature': 0, 'max_tokens': 2000,
        'reasoning_effort': 'low', 'include_reasoning': False,
        'response_format': {'type': 'json_schema', 'json_schema': {'name': 'wireless_' + role, 'strict': True, 'schema': wire_schema(role)}},
        'messages': [{'role': 'system', 'content': instructions(role) + '\nThe JSON schema above is the original role contract. In the transport schema, nullable padding exists ONLY for fields belonging to other actions. For the selected action, every original required field must retain its original type. In A clarify, need is a complete object even when the topic is ambiguous, clarification is an object, and coverage_gaps is an array (possibly empty), never null. Even for an ambiguous question, need.requirements must contain at least one requirement describing the actual requested task, with established_by copied from supplied original references; ambiguity is not an empty requirement list. Represent an unknown comparison topic honestly in the need and bind the missing detail to the supplied original reference; do not guess entities.\nTransport: wrap the role output in an object with the single key result. The supplied JSON schema defines that envelope. Set nullable fields that do not belong to the selected action or request kind to null. A always requires a concrete need and a coverage_gaps array; for out_of_scope describe the original request honestly in need and use empty coverage_gaps.'},
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
            if not missing: raise AppError('GAP_BINDING_EMPTY', 'Missing requirement binding is empty.')
            if not set(missing) <= ids: raise AppError('GAP_BINDING_UNKNOWN', 'Missing requirement binding uses an unknown ID.')
        except AppError as error: result['status'] = error.code
    return result


def run(payload, strict_only=False):
    report = {'model': MODEL, 'maximum_calls': 1 if strict_only else 2, 'attempts': 0, 'retries': 0, 'results': []}
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

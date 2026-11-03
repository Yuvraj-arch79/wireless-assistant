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
    original = ADAPTERS[role].json_schema()
    def resolve(node):
        return original['$defs'][node['$ref'].split('/')[-1]] if '$ref' in node else node
    def union(options):
        flat = []
        for option in options:
            for item in option.get('anyOf', [option]):
                if item not in flat: flat.append(item)
        return flat[0] if len(flat) == 1 else {'anyOf': flat}
    def convert(node):
        # Provider compiler rejects the nested discriminated object unions.
        # Use a superset on the wire; original branch validation remains authoritative.
        if 'oneOf' in node and 'discriminator' in node:
            branches = [resolve(b) for b in node['oneOf']]
            names = list(dict.fromkeys(k for b in branches for k in b['properties']))
            properties = {}
            for name in names:
                choices = [convert(b['properties'][name]) for b in branches if name in b['properties']]
                if len(choices) < len(branches): choices.append({'type': 'null'})
                # Combine singleton action/kind enums instead of anyOf literals.
                if all(c.get('type') == 'string' and 'enum' in c for c in choices):
                    properties[name] = {'type': 'string', 'enum': list(dict.fromkeys(v for c in choices for v in c['enum']))}
                else: properties[name] = union(choices)
            return {'type': 'object', 'properties': properties, 'required': names, 'additionalProperties': False}
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
            # Put the distinguishing literal before common fields in union branches.
            properties = out.get('properties', {})
            discriminators = [k for k, v in properties.items() if len(v.get('enum', [])) == 1]
            if discriminators:
                first = discriminators[0]
                out['properties'] = {first: properties[first], **{k: v for k, v in properties.items() if k != first}}
            out['required'] = list(out.get('properties', {}))
        return out
    source = convert(original)
    definitions = {name: convert(value) for name, value in original.get('$defs', {}).items()}
    source.pop('$defs', None)
    if role == 'A':
        # Every in-scope action needs these fields. Require concrete values on
        # the wire, including a minimal honest need for out_of_scope.
        source['properties']['need'] = {'$ref': '#/$defs/Need'}
        source['properties']['coverage_gaps'] = {'type': 'array', 'items': {'$ref': '#/$defs/Gap'}}
    return {'type': 'object', 'properties': {'result': source}, 'required': ['result'],
            'additionalProperties': False, '$defs': definitions}


def normalize_wire(value, role):
    """Remove only null fields belonging to other union branches; reject extras later."""
    schema = ADAPTERS[role].json_schema()
    def walk(value, node):
        if '$ref' in node: node = schema['$defs'][node['$ref'].split('/')[-1]]
        if isinstance(value, dict) and 'discriminator' in node:
            tag = node['discriminator']['propertyName']
            ref = node['discriminator']['mapping'].get(value.get(tag))
            if ref:
                branch = schema['$defs'][ref.split('/')[-1]]
                allowed = branch.get('properties', {})
                union_fields = set()
                for variant in node['oneOf']:
                    union_fields.update(schema['$defs'][variant['$ref'].split('/')[-1]]['properties'])
                value = {k: v for k, v in value.items() if k in allowed or k not in union_fields or v is not None}
                return walk(value, branch)
        if isinstance(value, dict) and 'properties' in node:
            return {k: walk(v, node['properties'].get(k, {})) for k, v in value.items()}
        if isinstance(value, list) and 'items' in node: return [walk(v, node['items']) for v in value]
        return value
    # AOut has no coverage_gaps field; only the explicitly empty transport
    # placeholder may be removed. Never discard actual findings.
    if role == 'A' and isinstance(value, dict) and value.get('action') == 'out_of_scope' and value.get('coverage_gaps') == []:
        value = {k: v for k, v in value.items() if k != 'coverage_gaps'}
    return walk(value, schema)


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
        value = normalize_wire(value['result'], role)
    try: parsed = ADAPTERS[role].validate_python(value).model_dump(mode='json')
    except ValidationError as error: return {'status': 'CONTRACT_INVALID', 'issues': safe_errors(error, role)}
    return {'status': 'pass', 'issues': [], 'value': parsed}


def strict_generate(role, payload):
    if not free_confirmed('groq'): raise AppError('FREE_TIER_NOT_CONFIRMED', 'Free-only confirmation required.')
    result = request('groq', 'POST', 'chat/completions', {
        'model': MODEL, 'temperature': 0, 'max_tokens': 2000,
        'reasoning_effort': 'low', 'include_reasoning': False,
        'response_format': {'type': 'json_schema', 'json_schema': {'name': 'wireless_' + role, 'strict': True, 'schema': wire_schema(role)}},
        'messages': [{'role': 'system', 'content': instructions(role) + '\nThe JSON schema above is the original role contract. In the transport schema, nullable padding exists ONLY for fields belonging to other actions. For the selected action, every original required field must retain its original type. In A clarify, need is a complete object even when the topic is ambiguous, clarification is an object, and coverage_gaps is an array (possibly empty), never null. Represent an unknown comparison topic honestly in the need and bind the missing detail to the supplied original reference; do not guess entities.\nTransport: wrap the role output in an object with the single key result. The supplied JSON schema defines that envelope. Set nullable fields that do not belong to the selected action or request kind to null. A always requires a concrete need and a coverage_gaps array; for out_of_scope describe the original request honestly in need and use empty coverage_gaps.'},
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

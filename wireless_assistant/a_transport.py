"""Compact A wire format; expand server-bound references before backend validation."""
from copy import deepcopy
from .common import canonical, AppError
from .contracts import ADAPTERS


def references(payload):
    # The server, never the model, owns the original message hashes and offsets.
    refs = []
    for original in payload.get('original_context', []):
        ref = original.get('ref')
        if isinstance(ref, dict) and ref not in refs:
            refs.append(ref)
    return {f'o{i+1}': ref for i, ref in enumerate(refs)}


def encode_payload(payload):
    mapping = {canonical(ref): key for key, ref in references(payload).items()}
    def walk(v):
        if isinstance(v, dict):
            key = mapping.get(canonical(v))
            if key:
                return key
            return {k: walk(x) for k, x in v.items()}
        if isinstance(v, list):
            return [walk(x) for x in v]
        return v
    return walk(payload)


def decode_result(value, payload):
    value = deepcopy(value)
    mapping = references(payload)
    need = value.get('need') if isinstance(value, dict) else None
    def expand(ref):
        if isinstance(ref, str):
            if ref not in mapping:
                raise AppError('INVALID_CONTRACT', 'Unknown original reference alias.')
            return deepcopy(mapping[ref])
        return ref  # Legacy DTOs still undergo exact reference validation.
    if isinstance(need, dict):
        if isinstance(need.get('original_refs'), list):
            need['original_refs'] = [expand(r) for r in need['original_refs']]
        for req in need.get('requirements', []):
            if isinstance(req, dict) and isinstance(req.get('established_by'), list):
                req['established_by'] = [expand(r) for r in req['established_by']]
    # HistoryFetch refs may refer to excluded history, so retain full DTOs there.
    return value


def schema(payload):
    """Action-specific unions avoid required null placeholders for other actions."""
    def walk(v):
        if isinstance(v, list):
            return [walk(x) for x in v]
        if not isinstance(v, dict):
            return v
        out = {}
        for k, x in v.items():
            if k in ('title', 'discriminator'):
                continue
            if k == 'const':
                out['enum'] = [x]
            else:
                out['anyOf' if k == 'oneOf' else k] = walk(x)
        if out.get('type') == 'object':
            out['required'] = list(out.get('properties', {}))
            out['additionalProperties'] = False
        return out
    original = walk(ADAPTERS['A'].json_schema())
    definitions = original.pop('$defs')
    # Groq infers an object-union discriminator from enum properties. The
    # shared intent_relation enum competes with action, despite overlapping
    # values. Keep only action as a wire discriminator; the original backend
    # DTO still enforces intent_relation's enum after decoding.
    for branch in original['anyOf']:
        definition = definitions[branch['$ref'].split('/')[-1]]
        props = definition['properties']
        allowed = props['intent_relation']['enum']
        props['intent_relation'] = {'type': 'string', 'description': 'Must be one of: ' + ', '.join(allowed)}
        definition['properties'] = {'action': props['action'], **{k: v for k, v in props.items() if k != 'action'}}
    alias = {'type': 'string', 'enum': list(references(payload))}
    if alias['enum']:
        definitions['Need']['properties']['original_refs']['items'] = alias
        definitions['Requirement']['properties']['established_by']['items'] = alias
    # Expansion is impossible until actual passages have been collected.
    if not payload.get('evidence'):
        tools = definitions['ACollect']['properties']['requests']['items']['anyOf']
        tools[:] = [t for t in tools if t.get('$ref') != '#/$defs/Expand']
    result = {'type':'object', 'properties':{'result':original}, 'required':['result'],
              'additionalProperties':False, '$defs':definitions}
    from .a_token_budget import reachable_schema
    return reachable_schema(result)

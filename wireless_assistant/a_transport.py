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
    # Seen live 17 Nov (run 44015633606): A's search filters left need.scope, and on repair
    # it dropped a filter field. Filters only steer retrieval; they are clamped to the
    # user's scope here (never widened), so the search cannot leave the requested scope.
    scope = need.get('scope') if isinstance(need, dict) else None
    # Seen live 17 Nov (runs 44015334958, 44016039735): for a question naming no
    # specification, A put subject specs (38.200/38.300, then 38.322/38.331) into the
    # search scope. A scope entry that is neither a loaded document nor written by the
    # user is A's invention and is dropped; one the user wrote stays for A to resolve.
    inventory = payload.get('corpus_inventory') or []
    loaded = {i.get('spec_number') for i in inventory if isinstance(i, dict)}
    loaded_versions = {i.get('version') for i in inventory if isinstance(i, dict)}
    if isinstance(scope, dict) and loaded - {None}:
        written = ' '.join(m.get('text', '') for m in payload.get('original_context') or [] if isinstance(m, dict))
        for key, known in (('spec_numbers', loaded), ('document_versions', loaded_versions)):
            if isinstance(scope.get(key), list):
                scope[key] = [x for x in scope[key] if x in known or (isinstance(x, str) and x in written)]
    if value.get('action') == 'collect' and isinstance(scope, dict) and isinstance(value.get('requests'), list):
        for request in value['requests']:
            if not isinstance(request, dict) or request.get('kind') != 'corpus_search':
                continue
            f = request.get('filters') if isinstance(request.get('filters'), dict) else {}
            def within(key):
                wanted = [x for x in (f.get(key) or []) if isinstance(x, str)]
                allowed = scope.get(key) or []
                if not allowed:
                    return wanted
                kept = [x for x in wanted if x in allowed]
                return kept or list(allowed)
            request['filters'] = {
                'release': scope.get('release') or f.get('release'),
                'spec_numbers': within('spec_numbers'),
                'document_versions': within('document_versions'),
                'default_used': f.get('default_used') if isinstance(f.get('default_used'), bool) else bool(scope.get('default_used')),
            }
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

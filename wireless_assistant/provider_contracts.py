"""Shared wire contracts. Original backend schemas remain authoritative."""
import copy
import json
import re
from pydantic import ValidationError
from .contracts import ADAPTERS
from .common import AppError, load_json

def wire_schema(role):
    original = ADAPTERS[role].json_schema()
    def resolve(node):
        return original['$defs'][node['$ref'].split('/')[-1]] if '$ref' in node else node
    def union(options):
        flat = []
        for option in options:
            for item in option.get('anyOf', [option]):
                if item not in flat: flat.append(item)
        # Different action branches may allow strings with different bounds.
        # Their overlapping anyOf alternatives confuse the provider compiler.
        # Merge to their union of permitted bounds; backend checks the selected branch.
        for kind in ('string', 'integer', 'number'):
            group = [c for c in flat if c.get('type') == kind and 'enum' not in c]
            if len(group) > 1:
                merged = {'type': kind}
                for lower in ('minLength', 'minimum'):
                    if all(lower in c for c in group): merged[lower] = min(c[lower] for c in group)
                for upper in ('maxLength', 'maximum'):
                    if all(upper in c for c in group): merged[upper] = max(c[upper] for c in group)
                if all(c.get('pattern') == group[0].get('pattern') for c in group) and 'pattern' in group[0]:
                    merged['pattern'] = group[0]['pattern']
                flat = [c for c in flat if c not in group] + [merged]
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
            elif key in ('type', '$ref', 'enum', 'required', 'additionalProperties', 'minItems', 'maxItems', 'minLength', 'maxLength', 'minimum', 'maximum', 'pattern'): out[key] = value
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
        definitions['Clarification']['properties']['missing_requirement_ids']['minItems'] = 1
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
    except (ValueError, TypeError) as error:
        if isinstance(error, json.JSONDecodeError): detail = 'syntax'
        elif str(error) == 'Duplicate JSON key': detail = 'duplicate_key'
        elif str(error) == 'Non-finite JSON value': detail = 'non_finite'
        else: detail = 'invalid_type'
        return {'status': 'INVALID_JSON', 'issues': [], 'json_error': detail}
    if wrapped:
        if not isinstance(value, dict) or set(value) != {'result'}:
            return {'status': 'INVALID_ENVELOPE', 'issues': []}
        value = normalize_wire(value['result'], role)
    try: parsed = ADAPTERS[role].validate_python(value).model_dump(mode='json')
    except ValidationError as error: return {'status': 'CONTRACT_INVALID', 'issues': safe_errors(error, role)}
    return {'status': 'pass', 'issues': [], 'value': parsed}


def b_schema():
    def walk(v):
        if isinstance(v,list):return [walk(x) for x in v]
        if not isinstance(v,dict):return v
        return {('anyOf' if k=='oneOf' else k):walk(x) for k,x in v.items() if k not in ('discriminator','title')}
    role=walk(ADAPTERS['B'].json_schema());defs=role.pop('$defs')
    defs['Citation']['properties']['claim_anchor']['description']='Exact substring copied from your answer_markdown, NOT from evidence text. Choose words that actually appear in your answer.'
    defs['BDraft']['properties']['answer_markdown']['description']='Include the answer with inline [1] citation AND a separate References section: [1] TS <spec_number> v<document_version>, clause <clause_id>. The same marker must occur in both places.'
    return {'type':'object','properties':{'result':role},'required':['result'],'additionalProperties':False,'$defs':defs}


def render_references(out,evidence):
    """Deterministic presentation from cited, verified metadata; never edits claims."""
    if out.get('action')!='submit_draft':return out
    out=copy.deepcopy(out)
    answer=out['answer_markdown']
    limitation=out.get('limitation_statement')
    if out.get('unresolved_requirements') and isinstance(limitation,str) and limitation and limitation not in answer:
        answer=answer.rstrip()+'\n\nLimitations\n'+limitation
        out['answer_markdown']=answer
    # Map exact citation-free text back to original offsets; no fuzzy matching.
    removed=set()
    for match in re.finditer(r'\s*\[[1-9][0-9]?\]',answer):removed.update(range(match.start(),match.end()))
    indices=[i for i in range(len(answer)) if i not in removed]
    plain=''.join(answer[i] for i in indices)
    for citation in out['citations']:
        anchor=citation['claim_anchor']
        if anchor not in answer:
            start=plain.find(anchor)
            if start>=0 and anchor:
                citation['claim_anchor']=answer[indices[start]:indices[start+len(anchor)-1]+1]
    if re.search(r'(?im)^\s*(?:#+\s*)?References\s*:?\s*$',answer):return out
    sources={p['passage_id']:p for p in evidence};entries=[];seen=set()
    for citation in out['citations']:
        marker=citation['marker']
        if marker in seen or marker not in answer or citation['claim_anchor'] not in answer:
            raise AppError('INVALID_CONTRACT','Invalid inline citation or claim anchor before reference rendering.')
        seen.add(marker)
        if not citation['passage_ids'] or any(pid not in sources or sources[pid]['unreadable'] for pid in citation['passage_ids']):
            raise AppError('INVALID_CONTRACT','Citation references missing or unreadable evidence.')
        labels=[]
        for pid in citation['passage_ids']:
            p=sources[pid];label='TS '+p['spec_number']+' v'+p['document_version']+', clause '+p['clause_id']
            if label not in labels:labels.append(label)
        entries.append(marker+' '+ '; '.join(labels)+'.')
    result=copy.deepcopy(out)
    result['answer_markdown']=answer.rstrip()+'\n\nReferences\n'+'\n'.join(entries)
    return result


def c_schema(p):
    """Constrain backend-owned identities and review phase, never the decision."""
    wrapped = wire_schema('C')
    schema = copy.deepcopy(wrapped['properties']['result'])
    schema['$defs'] = copy.deepcopy(wrapped['$defs'])
    definitions = schema['$defs']
    for field, value in p['reviewed_binding'].items():
        definitions['Binding']['properties'][field] = {'type': 'string', 'enum': [value]}
    regression = definitions['Regression']['properties']
    if p['envelope']['round_number'] == 0:
        regression['status'] = {'type': 'string', 'enum': ['not_applicable']}
        regression['compared_candidate_id'] = {'type': 'null'}
        for field in ('lost_or_changed_requirement_ids', 'resulting_finding_ids'):
            regression[field]['maxItems'] = 0
    else:
        regression['status'] = {'type': 'string', 'enum': ['checked']}
        regression['compared_candidate_id'] = {'type': 'string', 'enum': [p['prior_candidate']['candidate_id']]}
    return schema


def compact_c_schema(payload):
    """Do not spend model output tokens echoing backend-owned hashes/IDs."""
    schema=c_schema(payload)
    del schema['properties']['reviewed_binding']
    schema['required'].remove('reviewed_binding')
    del schema['$defs']['Binding']
    return schema


def inspect_c_response(raw,payload):
    try:
        value=load_json(raw)
        if not isinstance(value,dict) or 'reviewed_binding' in value:
            return {'status':'INVALID_ENVELOPE','issues':[]}
        value['reviewed_binding']=copy.deepcopy(payload['reviewed_binding'])
    except (ValueError,TypeError):
        return {'status':'INVALID_JSON','issues':[]}
    return inspect_response(json.dumps(value),'C')

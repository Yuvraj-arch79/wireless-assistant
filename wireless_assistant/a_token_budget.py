"""Bound Groq A/B/C requests; backend originals and B/C evidence text stay intact."""
from copy import deepcopy
from functools import lru_cache
from .common import AppError, canonical

# Observed account limit. Leave room for Groq's schema/chat framing estimation.
A_LIMIT = 8000
A_MARGIN = 1000
B_MARGIN = 500


@lru_cache(maxsize=1)
def tokenizer():
    try:
        import tiktoken
        import os, tempfile, hashlib
        from pathlib import Path
        cache_dir = os.environ.get('TIKTOKEN_CACHE_DIR', os.environ.get('DATA_GYM_CACHE_DIR', str(Path(tempfile.gettempdir()) / 'data-gym-cache')))
        url = 'https://openaipublic.blob.core.windows.net/encodings/o200k_base.tiktoken'
        cached = Path(cache_dir) / hashlib.sha1(url.encode()).hexdigest()
        expected = '446a9538cb6c348e3516120d7c08b09f57c36495e2acfffe59a5bf8b0cfb1a2d'
        if not cache_dir or not cached.is_file() or hashlib.sha256(cached.read_bytes()).hexdigest() != expected:
            raise ValueError('Initialize tokenizer cache before serving; never download in a request.')
        return tiktoken.get_encoding('o200k_harmony')
    except Exception:
        raise AppError('TOKENIZER_UNAVAILABLE',
                       'Install tiktoken and initialize o200k_harmony before starting chat. No request was sent.', 503) from None


def request_tokens(body):
    # Count the entire serialized request, including instructions, schema and
    # context; output reservation is additional. Provider framing can differ.
    return len(tokenizer().encode(canonical(body), disallowed_special=())) + body['max_tokens']


def reachable_schema(schema):
    """Remove only unreachable definitions; retain all validation keywords."""
    schema = deepcopy(schema)
    definitions = schema.pop('$defs', {})
    used = set()
    def visit(node):
        if isinstance(node, dict):
            ref = node.get('$ref', '')
            if ref.startswith('#/$defs/'):
                name = ref.split('/')[-1]
                if name not in used:
                    used.add(name)
                    visit(definitions[name])
            for child in node.values():
                visit(child)
        elif isinstance(node, list):
            for child in node:
                visit(child)
    visit(schema)
    if used:
        schema['$defs'] = {k: v for k, v in definitions.items() if k in used}
    return schema


def preview_passage(item, chars):
    out = deepcopy(item)
    # A chooses tools using the retrieved passage_id and relation; storage hashes
    # and neighbour IDs are backend bindings, not content the planner must echo.
    # Full evidence is untouched and is frozen independently for B and C.
    for name in ('document_id', 'build_id', 'content_hash'):
        out.pop(name, None)
    for name in ('parent_id', 'previous_id', 'next_id'):
        if name in out:
            out['has_' + name[:-3]] = bool(out.pop(name))
    text = out.get('text', '')
    if isinstance(text, str) and len(text) > chars:
        out['text'] = text[:chars]
        out['preview_truncated'] = True
        out['full_chars'] = len(text)  # B and C receive all of it
    # Tables repeat the readable passage in structure.rows. Keep navigational
    # and extraction flags; B/C still receive the complete original structure.
    structure = out.get('structure')
    if isinstance(structure, dict) and 'rows' in structure:
        out['structure'] = {k: v for k, v in structure.items() if k != 'rows'}
        out['structure']['rows_omitted_from_preview'] = True
    return out


def compact_payload(payload, chars):
    p = deepcopy(payload)
    p['evidence'] = [preview_passage(e, chars) for e in p.get('evidence', [])]
    # Preserve each document's exact source metadata once, not once per chunk.
    sources = {}
    source_keys = ('source_uri', 'spec_number', 'document_version', 'release')
    for item in p['evidence']:
        source = {k: item.pop(k) for k in source_keys if k in item}
        if source:
            sid = next((key for key, value in sources.items() if value == source), None)
            if sid is None:
                sid = 's' + str(len(sources) + 1)
                sources[sid] = source
            item['source_ref'] = sid
    p['evidence_sources'] = sources
    evidence_ids = {e.get('passage_id') for e in p['evidence']}
    for result in p.get('tool_results', []):
        items = []
        for item in result.get('items', []):
            if isinstance(item, dict) and item.get('passage_id'):
                item = preview_passage(item, chars)
                if item['passage_id'] in evidence_ids:
                    item = {'passage_id': item['passage_id'], 'text_in_evidence': True}
            items.append(item)
        result['items'] = items
    # Original context, requirements, history references, gaps and repair error
    # are never truncated. If these cannot fit, fail before network dispatch.
    return p


# C review needs the user's originals, need, the exact candidate, prior review and
# the complete original evidence text/structure. Planner and storage fields are not
# review inputs; the server binds the review to the exact frozen inputs itself.
C_KEYS = ('original_context', 'need', 'evidence', 'candidate', 'prior_candidate', 'prior_review',
          'coverage_gaps', 'extraction_policy')
C_DROP_EVIDENCE = ('document_id', 'build_id', 'content_hash', 'parent_id', 'previous_id', 'next_id')


def compact_c_payload(payload):
    p = {k: deepcopy(payload[k]) for k in C_KEYS if k in payload}
    p['round_number'] = payload.get('envelope', {}).get('round_number')
    sources = {}
    for item in p.get('evidence', []):
        for name in C_DROP_EVIDENCE:
            item.pop(name, None)
        source = {k: item.pop(k) for k in ('source_uri',) if k in item}
        if source:
            sid = next((key for key, value in sources.items() if value == source), None)
            if sid is None:
                sid = 's' + str(len(sources) + 1)
                sources[sid] = source
            item['source_ref'] = sid
    p['evidence_sources'] = sources
    return p


def budget_c(payload, body):
    body = deepcopy(body)
    wire = compact_c_payload(payload)
    # A second review compares against the prior draft's text/citations and the
    # prior findings; bindings and logs are server-side (run 43831441623 did not fit).
    if isinstance(wire.get('prior_review'), dict):
        wire['prior_review'] = {k: wire['prior_review'][k] for k in ('decision', 'findings') if k in wire['prior_review']}
    if isinstance(wire.get('prior_candidate'), dict):
        wire['prior_candidate'] = {k: wire['prior_candidate'][k] for k in ('answer_markdown', 'citations', 'covered_requirements', 'unresolved_requirements')
                                   if k in wire['prior_candidate']}
    from .a_transport import encode_payload
    body['messages'][1]['content'] = canonical(encode_payload(wire))
    # Live: this whole-body count exceeded Groq's C prompt_tokens (4687 vs 4315).
    limit = A_LIMIT - (B_MARGIN if wire.get('prior_candidate') else A_MARGIN)
    # C output is fixed at 900 (Groq free OTPM limit 1000 for qwen).
    for output in (body['max_tokens'],):
        body['max_tokens'] = min(output, body['max_tokens'])
        if request_tokens(body) <= limit:
            break
    if request_tokens(body) > limit:
        raise AppError('CONTEXT_LIMIT',
                       'The review request cannot fit the 8000-token budget with the complete evidence and candidate. No provider request was sent.', 413)
    import os
    if os.environ.get('WA_PUBLIC_EVAL_DIAGNOSTICS') == '1':
        print(f"C BUDGET: tokens={request_tokens(body)} max_tokens={body['max_tokens']} limit={limit}", flush=True)
    return body


# B drafts from the user's originals, need, complete evidence and controller
# signals. Planner/storage fields are not drafting inputs.
B_KEYS = ('original_context', 'need', 'evidence', 'coverage_gaps', 'extraction_policy', 'closing_mode',
          'missing_info_allowed', 'complete_clauses', 'prior_candidate', 'prior_review', 'b_gap', 'contract_error')


def budget_b(payload, body):
    body = deepcopy(body)
    wire = compact_c_payload({k: payload[k] for k in B_KEYS + ('envelope',) if k in payload})
    for key in ('closing_mode', 'missing_info_allowed', 'complete_clauses', 'b_gap', 'contract_error'):
        if key in payload:
            wire[key] = deepcopy(payload[key])
    # B never writes original references; short aliases (as for A) replace the
    # repeated message hashes/offsets. The server keeps the full originals.
    from .a_transport import encode_payload
    wire = encode_payload(wire)
    # A revision needs the prior draft and the findings, not review bindings.
    if isinstance(wire.get('prior_review'), dict):
        wire['prior_review'] = {k: wire['prior_review'][k] for k in ('decision', 'findings') if k in wire['prior_review']}
    if isinstance(wire.get('prior_candidate'), dict):
        wire['prior_candidate'] = {k: v for k, v in wire['prior_candidate'].items() if k != 'revision_log'}
    body['messages'][1]['content'] = canonical(wire)
    import os
    # Prefer the full output reservation; shrink it only within a safe floor.
    # Live gpt-oss-20b B completions were 534-747 tokens (incl. low reasoning).
    # Live counts: this whole-body count exceeded Groq's prompt_tokens (4172 vs
    # 4018), so a 500-token margin still stays below Groq's 8000 prompt+max limit.
    limit = A_LIMIT - B_MARGIN
    for output in (body['max_tokens'], 1700, 1400, 1100):
        body['max_tokens'] = min(output, body['max_tokens'])
        if request_tokens(body) <= limit:
            if os.environ.get('WA_PUBLIC_EVAL_DIAGNOSTICS') == '1':
                print(f"B BUDGET: tokens={request_tokens(body)} max_tokens={body['max_tokens']} limit={limit}", flush=True)
            return body
    raise AppError('CONTEXT_LIMIT',
                   'The draft request cannot fit the 8000-token budget with the complete evidence. No provider request was sent.', 413)


def budget_request(role, payload, body):
    if role == 'C':
        return budget_c(payload, body)
    if role == 'B':
        return budget_b(payload, body)
    if role != 'A':
        return body
    from .contracts import ADAPTERS
    from .a_transport import schema as a_schema, encode_payload
    body = deepcopy(body)
    system = body['messages'][0]['content']
    system = system.replace('\nJSON schema:\n' + canonical(ADAPTERS['A'].json_schema()), '')
    system = system.replace('The JSON schema above is the original role contract.',
                            'Follow the transport schema; the backend validates the selected action.')
    system += ('\nEvidence text here is a retrieval preview, not the full evidence. '
               'B/C receive original passages. Resolve source_ref through evidence_sources for exact source metadata. '
               'Do not expand merely because preview_truncated is true: B/C already receive the complete passage. Preserve the requested language and explanation style in need. '
               'Do not clarify whether to disclose a source gap when the user already requested disclosure. '
               'When passages cover the requested topic, hand off to B with remaining gaps. '
               'Expand only actual supplied passage IDs; never request an empty passage_ids list.')
    schema = a_schema(payload)
    if body['response_format']['type'] == 'json_schema':
        body['response_format']['json_schema']['schema'] = schema
    else:
        # JSON-mode format repair still needs the schema, exactly once.
        system += '\nReturn {"result": ...} using this JSON schema:\n' + canonical(schema)
    body['messages'][0]['content'] = system
    for chars in (800, 400, 200, 80):
        body['messages'][1]['content'] = canonical(encode_payload(compact_payload(payload, chars)))
        if request_tokens(body) <= A_LIMIT - A_MARGIN:
            import os
            if os.environ.get('WA_PUBLIC_EVAL_DIAGNOSTICS') == '1':
                print(f"A PREVIEW: chars={chars} passages={len(payload.get('evidence', []))}", flush=True)
            return body
    raise AppError('CONTEXT_LIMIT',
                   'A request cannot fit the 8000-token budget with its required question, history, schema and output. No provider request was sent.', 413)

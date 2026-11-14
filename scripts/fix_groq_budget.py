"""Apply the A token-budget fix without replacing local provider code.
Run from the wireless-assistant repository with its virtualenv Python.
No provider API calls, credentials, billing or PDF/index changes.
"""
import ast
import importlib.util
from pathlib import Path
import re
import shutil
import subprocess
import sys
from datetime import datetime

MODULE = '"""Bound Groq A transport only; backend originals and B/C evidence stay intact."""\nfrom copy import deepcopy\nfrom functools import lru_cache\nfrom .common import AppError, canonical\n\n# Observed account limit. Leave room for Groq\'s schema/chat framing estimation.\nA_LIMIT = 8000\nA_MARGIN = 1000\n\n\n@lru_cache(maxsize=1)\ndef tokenizer():\n    try:\n        import tiktoken\n        return tiktoken.get_encoding(\'o200k_harmony\')\n    except Exception:\n        raise AppError(\'TOKENIZER_UNAVAILABLE\',\n                       \'Install tiktoken and initialize o200k_harmony before starting chat. No request was sent.\', 503) from None\n\n\ndef request_tokens(body):\n    # Count the entire serialized request, including instructions, schema and\n    # context; output reservation is additional. Provider framing can differ.\n    return len(tokenizer().encode(canonical(body), disallowed_special=())) + body[\'max_tokens\']\n\n\ndef reachable_schema(schema):\n    """Remove only unreachable definitions; retain all validation keywords."""\n    schema = deepcopy(schema)\n    definitions = schema.pop(\'$defs\', {})\n    used = set()\n    def visit(node):\n        if isinstance(node, dict):\n            ref = node.get(\'$ref\', \'\')\n            if ref.startswith(\'#/$defs/\'):\n                name = ref.split(\'/\')[-1]\n                if name not in used:\n                    used.add(name)\n                    visit(definitions[name])\n            for child in node.values():\n                visit(child)\n        elif isinstance(node, list):\n            for child in node:\n                visit(child)\n    visit(schema)\n    if used:\n        schema[\'$defs\'] = {k: v for k, v in definitions.items() if k in used}\n    return schema\n\n\ndef preview_passage(item, chars):\n    out = deepcopy(item)\n    text = out.get(\'text\', \'\')\n    if isinstance(text, str) and len(text) > chars:\n        out[\'text\'] = text[:chars]\n        out[\'preview_truncated\'] = True\n    # Tables repeat the readable passage in structure.rows. Keep navigational\n    # and extraction flags; B/C still receive the complete original structure.\n    structure = out.get(\'structure\')\n    if isinstance(structure, dict) and \'rows\' in structure:\n        out[\'structure\'] = {k: v for k, v in structure.items() if k != \'rows\'}\n        out[\'structure\'][\'rows_omitted_from_preview\'] = True\n    return out\n\n\ndef compact_payload(payload, chars):\n    p = deepcopy(payload)\n    p[\'evidence\'] = [preview_passage(e, chars) for e in p.get(\'evidence\', [])]\n    evidence_ids = {e.get(\'passage_id\') for e in p[\'evidence\']}\n    for result in p.get(\'tool_results\', []):\n        items = []\n        for item in result.get(\'items\', []):\n            if isinstance(item, dict) and item.get(\'passage_id\'):\n                item = preview_passage(item, chars)\n                if item[\'passage_id\'] in evidence_ids:\n                    item.pop(\'text\', None)\n                    item.pop(\'structure\', None)\n                    item[\'text_in_evidence\'] = True\n            items.append(item)\n        result[\'items\'] = items\n    # Original context, requirements, history references, gaps and repair error\n    # are never truncated. If these cannot fit, fail before network dispatch.\n    return p\n\n\ndef budget_request(role, payload, body):\n    if role != \'A\':\n        return body\n    from .contracts import ADAPTERS\n    from .provider_contracts import wire_schema\n    body = deepcopy(body)\n    system = body[\'messages\'][0][\'content\']\n    system = system.replace(\'\\nJSON schema:\\n\' + canonical(ADAPTERS[\'A\'].json_schema()), \'\')\n    system = system.replace(\'The JSON schema above is the original role contract.\',\n                            \'Follow the transport schema; the backend validates the selected action.\')\n    system += (\'\\nEvidence text here is a retrieval preview, not the full evidence. \'\n               \'B/C receive original passages. Preserve the requested language and explanation style in need. \'\n               \'Do not clarify whether to disclose a source gap when the user already requested disclosure. \'\n               \'When passages cover the requested topic, hand off to B with remaining gaps. \'\n               \'Expand only actual supplied passage IDs; never request an empty passage_ids list.\')\n    schema = reachable_schema(wire_schema(\'A\'))\n    if body[\'response_format\'][\'type\'] == \'json_schema\':\n        body[\'response_format\'][\'json_schema\'][\'schema\'] = schema\n    else:\n        # JSON-mode format repair still needs the schema, exactly once.\n        system += \'\\nReturn {"result": ...} using this JSON schema:\\n\' + canonical(schema)\n    body[\'messages\'][0][\'content\'] = system\n    for chars in (800, 400, 200, 80):\n        body[\'messages\'][1][\'content\'] = canonical(compact_payload(payload, chars))\n        if request_tokens(body) <= A_LIMIT - A_MARGIN:\n            return body\n    raise AppError(\'CONTEXT_LIMIT\',\n                   \'A request cannot fit the 8000-token budget with its required question, history, schema and output. No provider request was sent.\', 413)\n'
TESTS = "import copy\nimport json\nfrom unittest.mock import patch\nimport httpx\nimport pytest\nfrom wireless_assistant import role_provider as rp\nfrom wireless_assistant.a_token_budget import A_LIMIT, A_MARGIN, request_tokens, reachable_schema\nfrom wireless_assistant.common import AppError, canonical\nfrom wireless_assistant.provider_contracts import wire_schema\n\nQUESTION = 'TS 38.201 clause 4.2.3: transport blocks ke LDPC aur PBCH ke Polar coding ko natural Hinglish mein simple analogy aur exact citation ke saath samjhao.'\n\n\ndef payload():\n    evidence = [dict(passage_id=f'p{i}', text='LDPC transport blocks. Polar PBCH. ' * 900,\n                     spec_number='38.201', document_version='18.0.0', clause_id='4.2.3',\n                     page_location='8', content_hash='original-hash', source_uri='https://example.org/source.pdf',\n                     structure={'rows':[['x']*20]*100,'kind':'table','formula_review_required':True}) for i in range(12)]\n    return dict(original_context=[{'ref':{'message_id':'m1','session_id':'s1','content_hash':'h','start_offset':0,'end_offset':len(QUESTION)},'role':'user','text':QUESTION}],\n                need={'language':'Hinglish'}, evidence=evidence,\n                tool_results=[{'status':'ok','items':copy.deepcopy(evidence)}],\n                excluded_history_map=[{'ref':{'message_id':'older'},'preview':'prior requested explanation'}])\n\n\n@pytest.mark.parametrize('stage', ['initial','post_search','repair'])\ndef test_a_fits_with_original_question_and_references(stage):\n    p=payload()\n    if stage=='initial':p['evidence']=[];p['tool_results']=[]\n    if stage=='repair':p['contract_error']='requests.1.expand_passages.passage_ids too_short'\n    original=copy.deepcopy(p)\n    body=rp.build_request('A',rp.MODELS['A'],p,2000)\n    assert request_tokens(body)+A_MARGIN<=A_LIMIT\n    sent=json.loads(body['messages'][1]['content'])\n    assert sent['original_context']==p['original_context']\n    assert sent['need']==p['need']\n    assert sent['excluded_history_map']==p['excluded_history_map']\n    assert p==original\n    for actual,source in zip(sent['evidence'],p['evidence']):\n        for key in ('passage_id','spec_number','document_version','clause_id','source_uri','content_hash','page_location'):\n            assert actual[key]==source[key]\n        assert actual['preview_truncated']\n    if stage=='repair':assert sent['contract_error']==p['contract_error']\n\n\ndef test_unfit_essential_context_never_dispatches():\n    p=payload();p['original_context'][0]['text']=QUESTION*1000\n    with patch.object(rp,'request') as request,pytest.raises(AppError) as exc:\n        rp.generate('A',rp.MODELS['A'],'',p,2000)\n    assert exc.value.code=='CONTEXT_LIMIT'\n    request.assert_not_called()\n\n\n@pytest.mark.parametrize('role',['B','C'])\ndef test_other_role_bodies_untouched(role):\n    from wireless_assistant.a_token_budget import budget_request\n    p=payload();body={'messages':[{'content':canonical(p)}]}\n    assert budget_request(role,p,body) is body\n\n\ndef test_http_413_terminal_no_retry(monkeypatch):\n    monkeypatch.setenv('GROQ_API_KEY','fixture');monkeypatch.setenv('WA_GROQ_FREE_TIER_CONFIRMED','1')\n    calls=[]\n    def handler(request):\n        calls.append(request)\n        return httpx.Response(413,json={'error':{'code':'rate_limit_exceeded'}})\n    with patch.object(rp.httpx,'Client',return_value=httpx.Client(transport=httpx.MockTransport(handler))),pytest.raises(AppError) as exc:\n        rp.request('A',{})\n    assert len(calls)==1\n    assert exc.value.code=='PROVIDER_REQUEST_TOO_LARGE' and not exc.value.retryable\n\n\ndef test_schema_references_still_resolve():\n    s=reachable_schema(wire_schema('A'))\n    def walk(v):\n        if isinstance(v,dict):\n            if '$ref' in v:assert v['$ref'].split('/')[-1] in s['$defs']\n            for c in v.values():walk(c)\n        elif isinstance(v,list):\n            for c in v:walk(c)\n    walk(s)\n    assert s['additionalProperties'] is False\n\n\ndef test_no_tokenizer_no_network(monkeypatch):\n    import wireless_assistant.a_token_budget as budget\n    def unavailable():raise AppError('TOKENIZER_UNAVAILABLE','Unavailable',503)\n    monkeypatch.setattr(budget,'tokenizer',unavailable)\n    with patch.object(rp,'request') as request,pytest.raises(AppError):\n        rp.generate('A',rp.MODELS['A'],'',payload(),2000)\n    request.assert_not_called()\n"
WRAPPER = '''

# WA_A_TOKEN_BUDGET_V1: preserve the original builder and local diagnostics.
def build_request(role, model, payload, output_tokens):
    from .a_token_budget import budget_request
    body = _wa_unbudgeted_build_request(role, model, payload, output_tokens)
    return budget_request(role, payload, body)
'''


def patch_provider(source):
    if '# WA_A_TOKEN_BUDGET_V1' in source:
        return source
    tree = ast.parse(source)
    builders = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'build_request']
    if len(builders) != 1 or [a.arg for a in builders[0].args.args] != ['role','model','payload','output_tokens']:
        raise RuntimeError('Unexpected build_request signature; no files changed.')
    if '_wa_unbudgeted_build_request' in source or 'from .a_token_budget import' in source:
        raise RuntimeError('Another budget fix is present; no files changed.')
    lines = source.splitlines(keepends=True)
    i = builders[0].lineno - 1
    lines[i] = lines[i].replace('def build_request(', 'def _wa_unbudgeted_build_request(', 1)
    source = ''.join(lines)
    request = next((n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name=='request'), None)
    if request is None:
        raise RuntimeError('No request function; no files changed.')
    lines = source.splitlines(keepends=True)
    positions = [i for i in range(request.lineno-1, request.end_lineno) if re.match(r'^\s*if response\.status_code != 200:\s*$', lines[i])]
    if len(positions) != 1:
        raise RuntimeError('Unexpected HTTP handling; no files changed.')
    i = positions[0]
    indent = re.match(r'\s*', lines[i]).group() + '    '
    lines.insert(i+1, indent + "if response.status_code == 413:\n" + indent + "    raise AppError('PROVIDER_REQUEST_TOO_LARGE', 'Groq request exceeds its token budget. Reduce collected context; no automatic retry.', 413)\n")
    result = ''.join(lines).rstrip() + WRAPPER
    ast.parse(result)
    return result


def main():
    root = Path.cwd()
    provider = root/'wireless_assistant/role_provider.py'
    if not provider.exists():
        raise RuntimeError('Open PowerShell in the wireless-assistant repository first.')
    import tiktoken
    tiktoken.get_encoding('o200k_harmony')  # Download tokenizer before changes, never during chat.
    if importlib.util.find_spec('pytest') is None:
        raise RuntimeError('Install pytest and tiktoken first.')
    changes = {provider: patch_provider(provider.read_text(encoding='utf-8'))}
    for relative, content in [('wireless_assistant/a_token_budget.py', MODULE),('tests/runtime/test_a_token_budget.py', TESTS)]:
        path = root/relative
        if path.exists() and path.read_text(encoding='utf-8') != content:
            raise RuntimeError(f'{relative} already has different local changes; no files changed.')
        changes[path] = content
    project = root/'pyproject.toml'
    if project.exists():
        text = project.read_text(encoding='utf-8')
        if 'tiktoken' not in text:
            text, count = re.subn(r'(dependencies\s*=\s*\[)', r'\1"tiktoken==0.14.0", ', text, count=1)
            if count != 1:
                raise RuntimeError('Cannot safely add dependency; no files changed.')
            changes[project] = text
    changes = {p:s for p,s in changes.items() if not p.exists() or p.read_text(encoding='utf-8')!=s}
    backup = root/('token-budget-backup-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
    old = {p: p.read_bytes() if p.exists() else None for p in changes}
    if changes:
        backup.mkdir()
        for path, data in old.items():
            if data is not None:
                target = backup/path.relative_to(root)
                target.parent.mkdir(parents=True,exist_ok=True)
                target.write_bytes(data)
    try:
        for path, content in changes.items():
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text(content,encoding='utf-8')
        subprocess.run([sys.executable,'-m','pytest','tests/runtime/test_a_token_budget.py','-q'],check=True)
    except Exception:
        for path, data in old.items():
            if data is None: path.unlink(missing_ok=True)
            else: path.write_bytes(data)
        raise RuntimeError('Checks failed; all edited files restored. Share the test error.') from None
    print('FIX INSTALLED. Offline regression tests passed. No live API calls made.')
    if changes:print('Backup:',backup)
    print('Restart the server in the SAME PowerShell where your keys are set; test one new question.')


if __name__ == '__main__':
    try:main()
    except Exception as error:
        print('STOP:',error)
        sys.exit(1)

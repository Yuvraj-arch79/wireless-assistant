"""Targeted fix for Groq discriminator_multiple_candidates; preserves local edits."""
import ast
import json
from datetime import datetime
from pathlib import Path
import socket
import subprocess
import sys

ANCHOR = "    definitions = original.pop('$defs')\n"
INSERT = "    # Groq infers an object-union discriminator from enum properties. The\n    # shared intent_relation enum competes with action, despite overlapping\n    # values. Keep only action as a wire discriminator; the original backend\n    # DTO still enforces intent_relation's enum after decoding.\n    for branch in original['anyOf']:\n        definition = definitions[branch['$ref'].split('/')[-1]]\n        props = definition['properties']\n        allowed = props['intent_relation']['enum']\n        props['intent_relation'] = {'type': 'string', 'description': 'Must be one of: ' + ', '.join(allowed)}\n        definition['properties'] = {'action': props['action'], **{k: v for k, v in props.items() if k != 'action'}}\n"
TEST_ADDITION = "@pytest.mark.parametrize('has_evidence', [False, True])\ndef test_groq_union_has_one_enum_discriminator_and_backend_keeps_intent_enum(has_evidence):\n    import jsonschema\n    p=payload()\n    if not has_evidence:p['evidence']=[]\n    s=rp.build_request('A',rp.MODELS['A'],p,2000)['response_format']['json_schema']['schema']\n    def resolve(n):\n        return s['$defs'][n['$ref'].split('/')[-1]] if '$ref' in n else n\n    def check(n):\n        if isinstance(n,dict):\n            if 'anyOf' in n:\n                variants=[resolve(v) for v in n['anyOf']]\n                if all(v.get('type')=='object' for v in variants):\n                    candidates=set.intersection(*[{k for k,v in b['properties'].items() if 'enum' in v} for b in variants])\n                    assert len(candidates)==1, candidates\n                    tag=next(iter(candidates))\n                    enums=[set(b['properties'][tag]['enum']) for b in variants]\n                    assert all(not x&y for i,x in enumerate(enums) for y in enums[i+1:])\n            for v in n.values():check(v)\n        elif isinstance(n,list):\n            for v in n:check(v)\n    check(s)\n    v=collect(p);v['intent_relation']='invented_relation'\n    encoded=encode_payload({**p,'need':v['need']})\n    wire={**v,'need':encoded['need']}\n    jsonschema.validate({'result':wire},s)\n    assert inspect_response(canonical({'result':decode_result(wire,p)}),'A',wrapped=True)['status']=='CONTRACT_INVALID'\n"
PROBE = '"""One bounded, private A schema probe. Does not publish a chat answer."""\nimport hashlib\nimport json\nimport os\n\n\ndef main():\n    if not os.getenv(\'GROQ_API_KEY\') or os.getenv(\'WA_GROQ_FREE_TIER_CONFIRMED\') != \'1\':\n        print(\'LIVE PROBE SKIPPED: use the same PowerShell with the configured Groq environment.\', flush=True)\n        return 2\n    import httpx\n    from wireless_assistant import role_provider as rp\n    from wireless_assistant.a_transport import decode_result\n    from wireless_assistant.common import canonical\n    from wireless_assistant.provider_contracts import inspect_response\n    question = (\'TS 38.201 clause 4.2.3 ke according transport blocks aur PBCH ki coding \'\n                \'simple Hinglish mein ek analogy ke saath samjhao. Exact citation do. \'\n                \'Coding choose karne ka reason source mein nahi hai toh clearly batao.\')\n    payload = {\n        \'original_context\': [{\'ref\': {\'message_id\': \'schema-probe\', \'session_id\': \'schema-probe\',\n            \'content_hash\': hashlib.sha256(question.encode()).hexdigest(), \'start_offset\': 0,\n            \'end_offset\': len(question)}, \'role\': \'user\', \'text\': question}],\n        \'evidence\': [], \'tool_results\': [], \'excluded_history_map\': [],\n        \'corpus_inventory\': [{\'spec_number\': \'38.201\', \'version\': \'18.0.0\', \'release\': \'18\'}],\n    }\n    body = rp.build_request(\'A\', rp.MODELS[\'A\'], payload, 2000)\n    print(\'LIVE PROBE: one A request; no retries; no answer will be published.\', flush=True)\n    try:\n        with httpx.Client(timeout=httpx.Timeout(30, connect=8), trust_env=False) as client:\n            with client.stream(\'POST\', \'https://api.groq.com/openai/v1/chat/completions\',\n                    headers={\'Authorization\': \'Bearer \' + os.environ[\'GROQ_API_KEY\']}, json=body) as r:\n                raw = bytearray()\n                for chunk in r.iter_bytes(chunk_size=16384):\n                    raw.extend(chunk)\n                    if len(raw) > 262144:\n                        print(\'LIVE PROBE FAILED: response exceeded diagnostic bound.\', flush=True)\n                        return 1\n                print(\'GROQ HTTP:\', r.status_code, flush=True)\n                try:\n                    result = json.loads(raw)\n                except (ValueError, UnicodeError):\n                    print(\'LIVE PROBE FAILED: non-JSON response.\', flush=True)\n                    return 1\n                if r.status_code != 200:\n                    error = result.get(\'error\', {}) if isinstance(result, dict) else {}\n                    if not isinstance(error, dict):error = {}\n                    for field in (\'code\', \'type\', \'param\'):\n                        value = error.get(field)\n                        # Fixed labels only; never print provider text that might echo a key/prompt.\n                        allowed = {\'invalid_request_error\',\'json_validate_failed\',\'rate_limit_exceeded\',\n                                   \'invalid_api_key\',\'response_format\',\'model\',\'max_tokens\',\'tokens\'}\n                        if value in allowed:print(field + \':\', value, flush=True)\n                    if \'discriminator_multiple_candidates\' in str(error.get(\'message\', \'\')):\n                        print(\'SCHEMA ERROR: discriminator_multiple_candidates\', flush=True)\n                    return 1\n        print(\'GROQ SCHEMA ACCEPTED (HTTP 200).\', flush=True)\n        choices = result.get(\'choices\', [])\n        if len(choices) != 1 or choices[0].get(\'finish_reason\') != \'stop\':\n            print(\'A CONTRACT NOT VERIFIED: response incomplete.\', flush=True)\n            return 1\n        wrapped = json.loads(choices[0][\'message\'][\'content\'])\n        if not isinstance(wrapped, dict) or set(wrapped) != {\'result\'}:\n            print(\'A CONTRACT FAILED: invalid wrapper.\', flush=True)\n            return 1\n        parsed = inspect_response(canonical({\'result\': decode_result(wrapped[\'result\'], payload)}), \'A\', wrapped=True)\n        if parsed[\'status\'] != \'pass\':\n            print(\'A CONTRACT FAILED: server DTO rejected the response.\', flush=True)\n            return 1\n        action = parsed[\'value\'][\'action\']\n        print(\'A CONTRACT PASS; action=\' + action, flush=True)\n        if action != \'collect\':\n            print(\'FLOW CHECK FAILED: this explicit source question should collect evidence first.\', flush=True)\n            return 1\n        print(\'SCHEMA PROBE PASSED. Full B/C Reviewed answer still requires a chat test.\', flush=True)\n        return 0\n    except httpx.HTTPError as exc:\n        print(\'LIVE PROBE FAILED:\', type(exc).__name__, \'(no retry).\', flush=True)\n        return 1\n    except Exception as exc:\n        print(\'LIVE PROBE FAILED:\', type(exc).__name__, \'(no private details printed).\', flush=True)\n        return 1\n\n\nif __name__ == \'__main__\':\n    raise SystemExit(main())\n'


def main():
    root=Path.cwd()
    target=root/'wireless_assistant/a_transport.py'
    test=root/'tests/runtime/test_a_transport.py'
    if not target.is_file() or not test.is_file():
        raise RuntimeError('Expected the installed ABC flow files. No changes made.')
    with socket.socket() as sock:
        if sock.connect_ex(('127.0.0.1',8765))==0:
            raise RuntimeError('Stop the server with Ctrl+C before installing.')
    source=target.read_text(encoding='utf-8')
    test_source=test.read_text(encoding='utf-8')
    if INSERT in source:
        patched=source
    else:
        if source.count(ANCHOR)!=1 or "props['intent_relation']" in source:
            raise RuntimeError('Schema code differs from the known version. No files overwritten.')
        patched=source.replace(ANCHOR,ANCHOR+INSERT,1)
    name='test_groq_union_has_one_enum_discriminator_and_backend_keeps_intent_enum'
    if TEST_ADDITION in test_source:
        patched_test=test_source
    elif name in test_source:
        raise RuntimeError('Regression test has local edits. No files overwritten.')
    else:
        patched_test=test_source.rstrip()+'\n\n\n'+TEST_ADDITION
    ast.parse(patched);ast.parse(patched_test)
    print('Checking tokenizer (maximum 35 seconds)...',flush=True)
    subprocess.run([sys.executable,'-c',"import tiktoken; tiktoken.get_encoding('o200k_harmony'); import pytest, jsonschema; print('TOKENIZER READY',flush=True)"],check=True,timeout=35)
    changes={p:s for p,s in ((target,patched),(test,patched_test)) if p.read_text(encoding='utf-8')!=s}
    originals={p:p.read_bytes() for p in changes}
    backup=root/('schema-fix-backup-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
    if changes:
        for p,data in originals.items():
            dest=backup/p.relative_to(root);dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data)
    try:
        for p,s in changes.items():p.write_text(s,encoding='utf-8')
        print('Checking schema, validation and token budget (maximum 120 seconds)...',flush=True)
        subprocess.run([sys.executable,'-m','pytest','tests/runtime/test_a_transport.py','tests/runtime/test_a_token_budget.py','-q'],check=True,timeout=120)
    except BaseException:
        for p,data in originals.items():p.write_bytes(data)
        raise RuntimeError('Offline checks failed/interrupted; installer edits restored.') from None
    print('SCHEMA PATCH INSTALLED; offline checks passed.',flush=True)
    if changes:print('Backup:',backup,flush=True)
    if '--offline-only' in sys.argv:
        print('LIVE PROBE SKIPPED (--offline-only).',flush=True)
        return
    print('Checking live Groq schema once (maximum 45 seconds)...',flush=True)
    try:
        result=subprocess.run([sys.executable,'-c',PROBE],timeout=45)
    except subprocess.TimeoutExpired:
        print('LIVE PROBE TIMED OUT; patch remains installed. No retry.',flush=True)
        return
    if result.returncode!=0:
        print('Live check not passed. Send the printed status; do not keep retrying chat.',flush=True)
    else:
        print('Next: restart the server in this PowerShell and test one New chat.',flush=True)


if __name__=='__main__':
    try:main()
    except Exception as exc:print('STOP:',exc,flush=True);sys.exit(1)

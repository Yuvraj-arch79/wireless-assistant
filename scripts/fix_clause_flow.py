"""Install exact-clause retrieval while preserving existing local edits.
No API key, PDF/index or billing changes. No live API calls.
"""
from pathlib import Path
from datetime import datetime
import ast
import subprocess
import sys

MODULE='"""Deterministic retrieval for a standalone, explicit source/clause request.\nNo factual answers are hardcoded; B writes from actual corpus text and C reviews.\nAmbiguous, multi-source and follow-up requests keep the normal A workflow.\n"""\nimport re\nfrom .common import canonical, digest, now, token_bound, uid\nfrom .store import insert\n\n\ndef route(engine, rid, w, state, context, evidence):\n    if state.get(\'b_gap\') or state.get(\'review\') or state.get(\'closing\'):\n        return None, evidence\n    originals = context[\'originals\']\n    if len(originals) != 1 or originals[0].get(\'role\') != \'user\':\n        return None, evidence\n    text = originals[0][\'text\']\n    if len(text) > 800:\n        return None, evidence\n    specs = set(re.findall(r\'\\b38\\.\\d{3}\\b\', text))\n    clauses = set(re.findall(r\'(?:clause|section|§)\\s*(\\d+(?:\\.\\d+)+)\', text, re.I))\n    if len(specs) != 1 or len(clauses) != 1:\n        return None, evidence\n    # Only explicit standalone explanatory/factual requests. References to prior\n    # replies, negation of this source, or comparisons need normal intent handling.\n    if re.search(r\'previous|earlier|pichl|instead|rather than|ignore|compare|versus|\\bvs\\b\', text, re.I):\n        return None, evidence\n    if not re.search(r\'\\?|explain|describe|summari[sz]e|samjha|samjhao|batao|btao\', text, re.I):\n        return None, evidence\n    spec, clause = next(iter(specs)), next(iter(clauses))\n    versions = set(re.findall(r\'\\bv(\\d+\\.\\d+\\.\\d+)\\b\', text, re.I))\n    releases = set(re.findall(r\'\\b(?:release|rel)\\s*[-:]?\\s*(\\d+)\\b\', text, re.I))\n    if len(versions)>1 or len(releases)>1:\n        return None, evidence\n    release = next(iter(releases), engine.settings.default_release)\n    run = engine.store.run(rid)\n    with engine.store.read() as db:\n        rows = db.execute(\'\'\'SELECT p.passage_id,d.version FROM passages p\n            JOIN source_documents d ON d.document_id=p.document_id\n            WHERE p.build_id=? AND d.spec_number=? AND d.release=?\n            AND p.clause_id=? AND p.unreadable=0 ORDER BY p.page_location,p.passage_id LIMIT ?\'\'\',\n            (run[\'corpus_build_id\'],spec,release,clause,engine.settings.max_passages+1)).fetchall()\n    rows = [r for r in rows if not versions or r[\'version\'] in versions]\n    if not rows or len(rows)>engine.settings.max_passages or len({r[\'version\'] for r in rows})!=1:\n        return None, evidence\n    selected = engine.corpus.get(run[\'corpus_build_id\'],[r[\'passage_id\'] for r in rows])\n    if sum(token_bound(p[\'text\']) for p in selected)>engine.settings.evidence_bound:\n        return None, evidence\n    ref = originals[0][\'ref\']\n    lang = \'Hinglish\' if re.search(r\'hinglish\',text,re.I) else \'Hindi\' if re.search(r\'\\bhindi\\b\',text,re.I) else \'English\'\n    need = {\'topic\':f\'TS {spec} clause {clause}\', \'requested_task\':text, \'language\':lang,\n            \'depth\':\'Follow the detail, examples and format requested in the original question.\',\n            \'scope\':{\'spec_numbers\':[spec],\'release\':release,\'document_versions\':[rows[0][\'version\']], \'default_used\':not releases},\n            \'requirements\':[{\'req_id\':\'r1\',\'description\':text,\'mandatory\':True,\'established_by\':[ref]}],\n            \'assumptions\':[], \'unresolved_gaps\':[], \'original_refs\':[ref]}\n    from .contracts import ADAPTERS\n    from .validation import validate_need\n    ADAPTERS[\'A\'].validate_python({\'action\':\'ready_for_b\',\'intent_relation\':\'same_need\',\'need\':need,\'coverage_gaps\':[]})\n    validate_need(need, originals)\n    need_id=engine.store.save_need(rid,w[\'epoch\'],need)\n    op=engine.store.reserve(rid,w[\'epoch\'],\'corpus_search\',digest({\'exact_clause\':clause,\'spec\':spec,\'release\':release}))\n    with engine.store.transaction() as db:\n        engine.store.owned(db,rid,w[\'epoch\'])\n        insert(db,\'retrieval_records\',retrieval_id=uid(),run_id=rid,need_id=need_id,\n               query_fingerprint=digest(text),request_json=canonical({\'kind\':\'exact_clause\',\'spec\':spec,\'clause\':clause}),\n               result_json=canonical({\'passage_ids\':[p[\'passage_id\'] for p in selected]}),new_passage_count=len(selected),created_at=now())\n    engine.store.operation_done(rid,w[\'epoch\'],op)\n    return {\'action\':\'ready_for_b\',\'intent_relation\':\'same_need\',\'need\':need,\'coverage_gaps\':[]},selected\n'
TESTS="from tests.runtime.conftest import create_chat, post, wait_run\n\n\ndef test_explicit_clause_uses_real_evidence_and_b_c(client):\n    question='TS 38.211 clause 4.4.4.1 ko simple Hinglish mein samjhao. Exact citation do.'\n    sid=create_chat(client)\n    rid=post(client,f'/api/sessions/{sid}/messages',{'text':question}).json()['data']['run_id']\n    result=wait_run(client,rid)\n    assert result['status']=='COMPLETED',result\n    assert [r for r,p in client.app_script.calls]==['B','C']\n    b=client.app_script.calls[0][1];c=client.app_script.calls[1][1]\n    assert b['need']['language']=='Hinglish'\n    assert b['need']['requirements'][0]['description']==question\n    assert b['evidence']==c['evidence']\n    assert b['evidence'][0]['clause_id']=='4.4.4.1'\n    assert b['evidence'][0]['text'].startswith('Synthetic fixture:')\n\n\ndef test_missing_clause_keeps_a(client):\n    sid=create_chat(client)\n    rid=post(client,f'/api/sessions/{sid}/messages',{'text':'TS 38.211 clause 99.9 samjhao?'}).json()['data']['run_id']\n    wait_run(client,rid)\n    assert client.app_script.calls[0][0]=='A'\n\n\ndef test_wrong_release_not_substituted(client):\n    sid=create_chat(client)\n    rid=post(client,f'/api/sessions/{sid}/messages',{'text':'TS 38.211 clause 4.4.4.1 Release 17 samjhao?'}).json()['data']['run_id']\n    wait_run(client,rid)\n    assert client.app_script.calls[0][0]=='A'\n\n\ndef test_c_rejection_never_releases_unchecked_answer(client):\n    from tests.runtime.conftest import draft, review\n    from wireless_assistant.common import canonical\n    calls=[]\n    def transport(role,p):\n        calls.append(role)\n        if role=='B':v=draft(p)\n        elif role=='C':v=review(p,accept=False)\n        else:raise AssertionError('Explicit clause should not call A')\n        return {'text':canonical(v)}\n    client.app.state.engine.role_transport=transport\n    sid=create_chat(client)\n    rid=post(client,f'/api/sessions/{sid}/messages',{'text':'TS 38.211 clause 4.4.4.1 samjhao?'}).json()['data']['run_id']\n    result=wait_run(client,rid)\n    assert result['outcome']['kind']!='ANSWER',result\n    assert 'C' in calls and 'A' not in calls\n\n\ndef test_explicit_wrong_version_keeps_normal_flow(client):\n    sid=create_chat(client)\n    rid=post(client,f'/api/sessions/{sid}/messages',{'text':'TS 38.211 v17.0.0 clause 4.4.4.1 samjhao?'}).json()['data']['run_id']\n    wait_run(client,rid)\n    assert client.app_script.calls[0][0]=='A'\n"
OLD="                result=self.call(rid,w,'A',payload,valid_a)"
NEW="""                # WA_EXACT_CLAUSE_V1: backend retrieval; B writes and C reviews.
                from .clause_route import route as exact_clause_route
                result, evidence = exact_clause_route(self,rid,w,state,context,evidence)
                if result is None:
                    result=self.call(rid,w,'A',payload,valid_a)
                else:
                    result=ADAPTERS['A'].validate_python(result).model_dump(mode='json')
                    valid_a(result)"""


def main():
    root=Path.cwd();engine=root/'wireless_assistant/engine.py'
    if not engine.exists():raise RuntimeError('Run from the wireless-assistant project folder.')
    source=engine.read_text(encoding='utf-8')
    if 'WA_EXACT_CLAUSE_V1' not in source:
        if source.count(OLD)!=1:raise RuntimeError('Engine differs; no files changed. Share engine.py (not API keys).')
        source=source.replace(OLD,NEW,1)
    ast.parse(source)
    changes={engine:source}
    for relative,content in [('wireless_assistant/clause_route.py',MODULE),('tests/runtime/test_clause_route.py',TESTS)]:
        path=root/relative
        if path.exists() and path.read_text(encoding='utf-8')!=content:
            raise RuntimeError(f'Existing {relative} differs; no files changed.')
        changes[path]=content
    changes={p:s for p,s in changes.items() if not p.exists() or p.read_text(encoding='utf-8')!=s}
    backup=root/('clause-fix-backup-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
    originals={p:p.read_bytes() if p.exists() else None for p in changes}
    if changes:
        backup.mkdir()
        for p,data in originals.items():
            if data is not None:
                target=backup/p.relative_to(root);target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
    try:
        for p,s in changes.items():
            p.parent.mkdir(parents=True,exist_ok=True);p.write_text(s,encoding='utf-8')
        print('Running 5 offline tests; no provider API calls...',flush=True)
        subprocess.run([sys.executable,'-m','pytest','tests/runtime/test_clause_route.py','-q'],check=True,timeout=60)
    except BaseException:
        for p,data in originals.items():
            if data is None:p.unlink(missing_ok=True)
            else:p.write_bytes(data)
        raise RuntimeError('Checks interrupted/failed: edited files restored.') from None
    print('CLAUSE FIX INSTALLED. Start server, open NEW CHAT and ask your source/clause question.',flush=True)
    if changes:print('Backup:',backup)


if __name__=='__main__':
    try:main()
    except Exception as exc:print('STOP:',exc);sys.exit(1)

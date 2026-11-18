"""Live multi-turn Hinglish checks through the real HTTP API and A-B-C controller.

Coarse automatic checks only; the report keeps every released answer and the exact cited
passage text so a human can read the answer and verify each claim. Not a certification.
Split: 'tuning' cases are the conversations whose wording was used while writing prompts;
'held_out' cases were written separately and never used for prompt tuning.
"""
import json
import os
import re
import time
from fastapi.testclient import TestClient
from wireless_assistant.app import create_app
from wireless_assistant.config import Settings, ROOT
from wireless_assistant.common import uid
from wireless_assistant.engine import Engine

DEVANAGARI = re.compile(r'[ऀ-ॿ]')
HINGLISH = re.compile(r'(?i)\b(hai|hota|hoti|hain|ke|ki|ka|mein|liye|aur|yeh|jaise|matlab|nahi|kaise)\b')

# chat: conversations sharing a key run in the same chat, in order.
CASES = [
    {'id': 'A_coding_compare', 'split': 'tuning', 'chat': 'main',
     'text': 'TS 38.201 clause 4.2.3 ke hisaab se transport blocks aur PBCH ki coding mein kya farq hai? Easy Hinglish mein ek analogy aur exact citation do.',
     'expect': 'answer', 'clause': '4.2.3', 'facts': ['ldpc', 'polar'], 'hinglish': True},
    {'id': 'B_followup_same_chat', 'split': 'tuning', 'chat': 'main',
     'text': 'Doosra wala samajh nahi aaya, aur easy bata.',
     'expect': 'answer', 'clause': '4.2.3', 'facts': ['polar'], 'hinglish': True},
    {'id': 'E_false_premise_correction', 'split': 'held_out', 'chat': 'main',
     'text': 'Yeh galat hai, PBCH ke liye bhi LDPC hi use hota hai na?',
     'expect': 'answer', 'clause': '4.2.3', 'facts': ['polar'], 'hinglish': True},
    {'id': 'C_rationale_limitation', 'split': 'tuning', 'chat': 'main',
     'text': 'Dono ke liye kaunsi coding hai aur standard ne yahi kyun choose ki?',
     'expect': 'answer_with_limitation', 'clause': '4.2.3', 'facts': ['ldpc', 'polar'], 'hinglish': True},
    {'id': 'B_fresh_chat_isolation', 'split': 'tuning', 'chat': 'fresh1',
     'text': 'Doosra wala samajh nahi aaya, aur easy bata.', 'expect': 'clarification'},
    {'id': 'D_wifi7_out_of_scope', 'split': 'tuning', 'chat': 'oos1',
     'text': 'Wi-Fi 7 mein bhi OFDM hai. IEEE 802.11be ke exact RU sizes batao.', 'expect': 'out_of_scope'},
    {'id': 'D_bluetooth_out_of_scope_unseen', 'split': 'held_out', 'chat': 'oos2',
     'text': 'Bluetooth Low Energy mein advertising channels kitne hote hain?', 'expect': 'out_of_scope'},
    {'id': 'A_paraphrase_unseen', 'split': 'held_out', 'chat': 'para',
     'text': '38.201 ke 4.2.3 mein data wale transport block aur broadcast channel ki channel coding alag kaise hai? simple bhasha mein samjhao.',
     'expect': 'answer', 'clause': '4.2.3', 'facts': ['ldpc', 'polar'], 'hinglish': True},
]
STOP_EARLY = ('PROVIDER_QUOTA', 'PROVIDER_AUTH', 'PROVIDER_NETWORK', 'PROVIDER_NOT_CONFIGURED', 'PROVIDER_REQUEST_TOO_LARGE')


def check(case, result, answer, cited, outcome):
    kind = (outcome or {}).get('kind')
    status = result['status']
    notes = []
    if case['expect'] == 'clarification':
        ok = status == 'WAITING_USER'
        if not ok:
            notes.append('expected a clarification, got ' + str(kind or status))
        return ok, notes
    if case['expect'] == 'out_of_scope':
        ok = kind == 'OUT_OF_SCOPE'
        if not ok:
            notes.append('expected OUT_OF_SCOPE, got ' + str(kind or status))
        return ok, notes
    ok = status == 'COMPLETED' and kind in ('ACCEPTED', 'PARTIAL_ACCEPTED')
    if not ok:
        notes.append('no reviewed answer: ' + str(kind or status))
    low = answer.lower()
    for fact in case.get('facts', []):
        if fact not in low:
            ok = False; notes.append('missing fact: ' + fact)
    if case.get('clause') and not any(c['clause_id'] == case['clause'] and c['spec_number'] == '38.201' for c in cited):
        ok = False; notes.append('no citation to clause ' + case['clause'])
    if case.get('hinglish'):
        prose = re.sub(r'(?s)\n\s*References\s*\n.*$', '', answer)
        if DEVANAGARI.search(prose):
            ok = False; notes.append('Devanagari used for a Roman Hinglish question')
        if len(HINGLISH.findall(prose)) < 5:
            ok = False; notes.append('answer does not read as Roman Hinglish')
    if case['expect'] == 'answer_with_limitation' and not re.search(r'(?i)nahi (mila|di|diya|bataya|likha)|not (state|stated|given|provide)|reason .*not|wajah .*nahi|limitation', answer):
        ok = False; notes.append('unsupported rationale not disclosed as a limitation')
    return ok, notes


def run():
    settings = Settings(data_dir=ROOT / 'data/one-pdf', provider_profile='groq_openrouter', max_repairs=1)
    report = {'status': 'not_completed', 'started': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
              'scope': 'Live Groq A/C + OpenRouter B + Gemini search over the indexed TS 38.201 v18.0.0; coarse checks + full answers for human review',
              'cases': []}
    selected = [c for c in CASES if not os.getenv('WA_EVAL_CASES') or c['id'] in os.getenv('WA_EVAL_CASES').split(',')]
    out = settings.data_dir / 'conversation-report.json'
    with TestClient(create_app(settings, Engine), base_url='http://127.0.0.1:8765') as client:
        app = client.app
        client.headers.update({'Origin': 'http://127.0.0.1:8765', 'X-WA-CSRF': app.state.csrf})
        if not client.get('/api/health').json()['data']['ready']:
            report['status'] = 'SETUP_REQUIRED'; return report
        chats = {}
        for case in selected:
            if case['chat'] not in chats:
                r = client.post('/api/sessions', json={'title': 'Live check: ' + case['chat']}, headers={'Idempotency-Key': uid()})
                r.raise_for_status(); chats[case['chat']] = r.json()['data']['session_id']
            sid = chats[case['chat']]
            started = time.monotonic()
            r = client.post(f'/api/sessions/{sid}/messages', json={'text': case['text']}, headers={'Idempotency-Key': uid()})
            if r.status_code != 202:
                report['cases'].append({'id': case['id'], 'passed': False, 'notes': ['admission failed: ' + r.text[:300]]}); continue
            rid = r.json()['data']['run_id']
            deadline = time.monotonic() + 330
            while time.monotonic() < deadline:
                result = client.get('/api/runs/' + rid).json()['data']
                if result['status'] != 'ACTIVE':
                    break
                time.sleep(1)
            outcome = result.get('outcome') or {}
            with app.state.store.read() as db:
                messages = [dict(m) for m in db.execute('SELECT message_id,role,content_text FROM messages WHERE session_id=? ORDER BY sequence', (sid,))]
                candidate = db.execute('SELECT citations_json FROM candidates WHERE candidate_id=?', (outcome.get('candidate_id'),)).fetchone()
                cited = []
                for c in json.loads(candidate[0]) if candidate else []:
                    for pid in c['passage_ids']:
                        p = db.execute('SELECT p.clause_id,p.content_text,d.spec_number,d.version FROM passages p JOIN source_documents d ON d.document_id=p.document_id WHERE p.passage_id=?', (pid,)).fetchone()
                        if p:
                            cited.append({'marker': c['marker'], 'claim_anchor': c['claim_anchor'], 'clause_id': p[0], 'passage_text': p[1], 'spec_number': p[2], 'version': p[3]})
            answer = next((m['content_text'] for m in messages if m['message_id'] == outcome.get('message_id')), '')
            if result['status'] == 'WAITING_USER':
                answer = (result.get('pending_clarification') or {}).get('question', '')
                client.post(f'/api/runs/{rid}/cancel', json={}, headers={'Idempotency-Key': uid()})
            passed, notes = check(case, result, answer, cited, outcome)
            item = {'id': case['id'], 'split': case['split'], 'chat': case['chat'], 'question': case['text'], 'passed': passed, 'notes': notes,
                    'status': result['status'], 'outcome_kind': outcome.get('kind'), 'stage': outcome.get('stage'),
                    'version_selection': outcome.get('version_selection'), 'seconds': round(time.monotonic() - started),
                    'run_ref': rid[:8], 'released_text': answer, 'cited_passages': cited}
            report['cases'].append(item)
            print(json.dumps(item, ensure_ascii=False, indent=1), flush=True)
            out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
            if outcome.get('kind') in STOP_EARLY:
                report['stopped_early'] = outcome.get('kind'); break
    done = len(report['cases']) == len(selected)
    report['status'] = 'pass' if done and all(c['passed'] for c in report['cases']) else 'not_passed'
    report['summary'] = {s: f"{sum(c['passed'] for c in report['cases'] if c.get('split') == s)}/{sum(1 for c in report['cases'] if c.get('split') == s)}" for s in ('tuning', 'held_out')}
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return report


if __name__ == '__main__':
    result = run()
    print(json.dumps({k: v for k, v in result.items() if k != 'cases'}, indent=2))
    raise SystemExit(0 if result['status'] == 'pass' else 1)

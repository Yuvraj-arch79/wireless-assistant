"""Four source-anchored integration probes; not exhaustive domain certification."""
import json
import re
import time
from fastapi.testclient import TestClient
from wireless_assistant.app import create_app
from wireless_assistant.config import Settings, ROOT
from wireless_assistant.common import uid

CASES = [
    {'id':'series','question':'Which TS specification series describes Layer 1, and which describes Layers 2 and 3 in NR? Answer briefly in English using the prepared corpus.', 'clause':'4.1.1','facts':['38.200','38.300']},
    {'id':'coding','question':'According to TS 38.201, what channel coding is used for transport blocks, and what coding is used for PBCH and control information? Answer briefly in English.', 'clause':'4.2.3','facts':['ldpc','polar']},
    {'id':'control','question':'According to TS 38.201, what is the scope of TS 38.213? List the physical-layer control procedures it specifies, briefly in English.', 'clause':'5.6','facts':['synchron','power control','random access']},
    {'id':'missing_detail','question':'Give the exact numerical LDPC base-graph selection thresholds from TS 38.212. If the loaded source does not specify these values, explicitly say that they are unavailable; do not infer them.', 'clause':None,'facts':[]},
]


def run():
    settings=Settings(data_dir=ROOT/'data/one-pdf',provider_profile='groq_openrouter',max_calls=6,max_repairs=0,max_retries=0)
    report={'status':'not_completed','scope':'Complete TS 38.201 PDF with Gemini hybrid search, Groq A/C and OpenRouter B; four representative probes','cases':[]}
    with TestClient(create_app(settings),base_url='http://127.0.0.1:8765') as client:
        app=client.app
        client.headers.update({'Origin':'http://127.0.0.1:8765','X-WA-CSRF':app.state.csrf})
        if not client.get('/api/health').json()['data']['ready']:
            report['status']='SETUP_REQUIRED';return report
        for case in CASES:
            response=client.post('/api/sessions',json={'title':'TS 38.201 check: '+case['id']},headers={'Idempotency-Key':uid()})
            response.raise_for_status();sid=response.json()['data']['session_id']
            response=client.post('/api/sessions/'+sid+'/messages',json={'text':case['question']},headers={'Idempotency-Key':uid()})
            response.raise_for_status();rid=response.json()['data']['run_id']
            deadline=time.monotonic()+310
            while time.monotonic()<deadline:
                result=client.get('/api/runs/'+rid).json()['data']
                if result['status']!='ACTIVE':break
                time.sleep(.5)
            with app.state.store.read() as db:
                reviews=[dict(r) for r in db.execute('SELECT * FROM reviews WHERE run_id=?',(rid,))]
                messages=[dict(r) for r in db.execute('SELECT * FROM messages WHERE session_id=? ORDER BY sequence',(sid,))]
                operations=[dict(r) for r in db.execute('SELECT * FROM operations WHERE run_id=?',(rid,))]
                candidates=[dict(r) for r in db.execute('SELECT * FROM candidates WHERE run_id=?',(rid,))]
            answer=next((m['content_text'] for m in reversed(messages) if m['role']=='assistant'),'')
            accepted=any(r['decision'] in ('accepted','partial_accepted') for r in reviews)
            citations=json.loads(candidates[-1]['citations_json']) if candidates else []
            cited_clauses=[]
            with app.state.store.read() as db:
                for citation in citations:
                    for pid in citation.get('passage_ids',[]):
                        p=db.execute('SELECT p.clause_id,d.spec_number FROM passages p JOIN source_documents d ON d.document_id=p.document_id WHERE p.passage_id=?',(pid,)).fetchone()
                        if p:cited_clauses.append(dict(p))
            if case['clause']:
                passed=result['status']=='COMPLETED' and accepted and all(f in answer.lower() for f in case['facts']) and any(c['clause_id']==case['clause'] and c['spec_number']=='38.201' for c in cited_clauses)
            else:
                # Never count an infrastructure error as a correct abstention.
                limitation=bool(re.search(r'not (?:available|provided|specified|included|contain)|does not|unavailable|missing|cannot|can.not',answer,re.I))
                invented=bool(re.search(r'\b(?:292|3824|8424)\b|0\.(?:25|67|89)',answer))
                passed=result['status']=='COMPLETED' and accepted and limitation and not invented
            item={'id':case['id'],'question':case['question'],'passed':passed,'run':result,'answer':answer,'accepted_review':accepted,'cited_clauses':cited_clauses,'citations':citations,'generation_attempts':sum(o['kind'] in ('A','B','C') for o in operations),'operation_kinds':[o['kind'] for o in operations]}
            report['cases'].append(item)
            print(json.dumps(item,ensure_ascii=True),flush=True)
            (settings.data_dir/'live-report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
            # No repeated attempts on a quota/auth/network failure.
            if result.get('outcome',{}).get('kind')=='FAILED':break
        report['status']='pass' if len(report['cases'])==len(CASES) and all(c['passed'] for c in report['cases']) else 'not_passed'
    (settings.data_dir/'live-report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return report

if __name__=='__main__':
    result=run();print(json.dumps(result,indent=2));raise SystemExit(0 if result['status']=='pass' else 1)

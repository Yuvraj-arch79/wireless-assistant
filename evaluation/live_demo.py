"""One real API chat through the real controller, storage and local retrieval.

Public single-excerpt demo only. Maximum six generation attempts; no repairs or
retries. Success requires a persisted accepted C review and cited final answer.
"""
import json
import tempfile
import time
from pathlib import Path
from fastapi.testclient import TestClient
from wireless_assistant.app import create_app
from wireless_assistant.config import Settings
from wireless_assistant.common import uid
from wireless_assistant.demo import prepare


def run(engine_factory=None):
    with tempfile.TemporaryDirectory() as folder:
        settings=Settings(data_dir=Path(folder),provider_profile='groq_openrouter',demo_mode=True,max_calls=6,max_repairs=0,max_retries=0)
        app=create_app(settings,engine_factory) if engine_factory else create_app(settings);prepare(app.state.store)
        with TestClient(app,base_url='http://127.0.0.1:8765') as client:
            client.headers.update({'Origin':'http://127.0.0.1:8765','X-WA-CSRF':app.state.csrf})
            health=client.get('/api/health').json()['data']
            if not health['ready']:return {'status':'SETUP_REQUIRED','generation_attempts':0}
            response=client.post('/api/sessions',json={'title':'Live A-B-C demo'},headers={'Idempotency-Key':uid()})
            response.raise_for_status();sid=response.json()['data']['session_id']
            response=client.post('/api/sessions/'+sid+'/messages',json={'text':'Which TS specification series describes Layer 1, and which describes Layers 2 and 3 in NR? Use the available TS 38.201 excerpt and answer briefly in English.'},headers={'Idempotency-Key':uid()})
            if response.status_code>=400:return {'status':'SUBMISSION_FAILED','http_status':response.status_code}
            rid=response.json()['data']['run_id'];deadline=time.monotonic()+310
            while time.monotonic()<deadline:
                result=client.get('/api/runs/'+rid).json()['data']
                if result['status']!='ACTIVE':break
                time.sleep(.5)
            else:return {'status':'DEADLINE'}
            with app.state.store.read() as db:
                reviews=[dict(r) for r in db.execute('SELECT * FROM reviews WHERE run_id=?',(rid,))]
                messages=[dict(r) for r in db.execute('SELECT * FROM messages WHERE session_id=? ORDER BY sequence',(sid,))]
                operations=[dict(r) for r in db.execute('SELECT * FROM operations WHERE run_id=?',(rid,))]
            answer=next((m['content_text'] for m in reversed(messages) if m['role']=='assistant'), '')
            accepted=any(r['decision'] in ('accepted','partial_accepted') for r in reviews)
            passed=result['status']=='COMPLETED' and accepted and '38.200' in answer and '38.300' in answer and '[1]' in answer
            return {'status':'pass' if passed else 'not_passed','run':result,'answer':answer,'accepted_review':accepted,
                    'operation_kinds':[o['kind'] for o in operations], 'scope':'One pinned public source excerpt; real live A/B/C and local retrieval, not full hybrid corpus.'}


if __name__=='__main__':
    result=run();print(json.dumps(result,indent=2,ensure_ascii=True));raise SystemExit(0 if result['status']=='pass' else 1)

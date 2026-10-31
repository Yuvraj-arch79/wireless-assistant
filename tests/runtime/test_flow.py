import json
import time
import threading
from .conftest import post,create_chat,wait_run,collect,ready,clarify,draft,review,Script
from wireless_assistant.common import uid,canonical,AppError
from wireless_assistant.engine import Engine
from wireless_assistant.store import Store


def test_complete_flow_exact_reviewed_answer_and_sources(client):
    sid=create_chat(client)
    result=post(client,f'/api/sessions/{sid}/messages',{'text':'Explain an NR resource block.'})
    assert result.status_code==202,result.text
    rid=result.json()['data']['run_id'];status=wait_run(client,rid)
    assert status['status']=='COMPLETED',status
    assert status['outcome']['kind']=='ACCEPTED',status
    assert [r for r,_ in client.app_script.calls]==['A','A','B','C']
    messages=client.get(f'/api/sessions/{sid}/messages').json()['data']['items']
    final=messages[-1]
    c_payload=client.app_script.calls[-1][1]
    assert final['content_text']==c_payload['candidate']['answer_markdown']
    assert 'original_context' in c_payload and 'evidence' in c_payload
    eid=status['outcome']['evidence_set_id']
    source=client.get(f'/api/runs/{rid}/evidence/{eid}/fixture-passage')
    assert source.status_code==200
    assert source.json()['data']['document_version']=='18.10.0'
    assert client.get(f'/api/runs/{rid}/evidence/wrong/fixture-passage').status_code==404
    feedback=post(client,'/api/feedback',{'run_id':rid,'candidate_id':status['outcome']['candidate_id'],'category':'unclear','comment':'Test'})
    assert feedback.status_code==201


def test_duplicate_submit_one_run_and_key_conflict(client):
    sid=create_chat(client);key=uid();body={'text':'Explain a resource block.'}
    first=post(client,f'/api/sessions/{sid}/messages',body,key)
    again=post(client,f'/api/sessions/{sid}/messages',body,key)
    assert first.json()['data']==again.json()['data']
    assert post(client,f'/api/sessions/{sid}/messages',{'text':'Different'},key).status_code==409
    wait_run(client,first.json()['data']['run_id'])
    with client.app.state.store.read() as db:
        assert db.execute('SELECT COUNT(*) FROM request_runs').fetchone()[0]==1


def test_clarification_idle_resume_and_counters_preserved(client):
    client.app_script.actions=[('A',clarify),('A',clarify)]
    sid=create_chat(client);rid=post(client,f'/api/sessions/{sid}/messages',{'text':'Explain it.'}).json()['data']['run_id']
    status=wait_run(client,rid,'WAITING_USER')
    store=client.app.state.store
    counters=json.loads(store.run(rid)['counters_json'])
    time.sleep(.2);assert len(client.app_script.calls)==1
    assert post(client,f'/api/sessions/{sid}/messages',{'text':'Second question'}).status_code==409
    cid=status['pending_clarification']['clarification_id'];key=uid()
    body={'text':'The NR resource block.','expected_run_version':status['state_version']}
    path=f'/api/runs/{rid}/clarifications/{cid}/reply'
    first=post(client,path,body,key);assert first.status_code==202,first.text
    status=wait_run(client,rid,'WAITING_USER')
    duplicate=post(client,path,body,key);assert duplicate.json()['data']==first.json()['data']
    assert json.loads(store.run(rid)['counters_json'])['provider_calls']==counters['provider_calls']+1
    assert post(client,path,body).status_code==409
    next_cid=status['pending_clarification']['clarification_id']
    reply=post(client,f'/api/runs/{rid}/clarifications/{next_cid}/reply',{'text':'Give its definition.','expected_run_version':status['state_version']})
    assert reply.status_code==202,reply.text
    final=wait_run(client,rid);assert final['outcome']['kind']=='ACCEPTED',final
    originals=client.app_script.calls[-1][1]['original_context']
    assert {'Explain it.','The NR resource block.','Give its definition.'}<={m['text'] for m in originals}


def test_two_corrections_no_failed_fallback(client):
    client.app_script.actions=[('A',collect),('A',ready),('B',draft),('C',lambda p:review(p,False)),('B',draft),('C',lambda p:review(p,False)),('B',draft),('C',lambda p:review(p,False))]
    sid=create_chat(client);rid=post(client,f'/api/sessions/{sid}/messages',{'text':'Explain resource blocks'}).json()['data']['run_id']
    status=wait_run(client,rid)
    assert status['outcome']['kind']=='INABILITY',status
    assert [r for r,_ in client.app_script.calls].count('B')==3
    assert all(m['role']!='assistant' for m in client.get(f'/api/sessions/{sid}/messages').json()['data']['items'])
    with client.app.state.store.read() as db:
        assert db.execute('SELECT COUNT(*) FROM candidates').fetchone()[0]==3
        assert db.execute('SELECT COUNT(*) FROM reviews').fetchone()[0]==3


def test_specific_b_gap_routes_b_a_b_c(client):
    def missing(p):return {'action':'request_missing_info','missing_info':{'type':'source','item':'Confirm definition context','why_material':'Required fixture context','requirement_ids':['r1']}}
    client.app_script.actions=[('A',collect),('A',ready),('B',missing),('A',ready),('B',draft),('C',review)]
    sid=create_chat(client);rid=post(client,f'/api/sessions/{sid}/messages',{'text':'Explain resource blocks'}).json()['data']['run_id']
    status=wait_run(client,rid);assert status['outcome']['kind']=='ACCEPTED',status
    assert [r for r,_ in client.app_script.calls]==['A','A','B','A','B','C']
    assert client.app_script.calls[3][1]['b_gap']['item']=='Confirm definition context'


def test_invalid_judge_binding_never_publishes(client):
    def wrong(p):
        r=review(p);r['reviewed_binding']={**r['reviewed_binding'],'candidate_hash':'wrong'};return r
    client.app_script.actions=[('A',collect),('A',ready),('B',draft),('C',wrong),('C',wrong)]
    sid=create_chat(client);rid=post(client,f'/api/sessions/{sid}/messages',{'text':'Explain resource blocks'}).json()['data']['run_id']
    status=wait_run(client,rid);assert status['status']=='FAILED',status
    assert status['outcome']['kind']=='INVALID_CONTRACT'
    assert all(m['role']!='assistant' for m in client.get(f'/api/sessions/{sid}/messages').json()['data']['items'])


def test_cancel_late_result_and_explicit_retry(client):
    entered=threading.Event();release=threading.Event()
    def delayed(p):entered.set();release.wait(3);return ready(p)
    client.app_script.actions=[('A',delayed)]
    sid=create_chat(client);rid=post(client,f'/api/sessions/{sid}/messages',{'text':'Explain resource blocks'}).json()['data']['run_id']
    assert entered.wait(2)
    canceled=post(client,f'/api/runs/{rid}/cancel');assert canceled.json()['data']['status']=='CANCELED'
    release.set();time.sleep(.2)
    assert client.get(f'/api/runs/{rid}').json()['data']['status']=='CANCELED'
    retry=post(client,f'/api/runs/{rid}/retry');assert retry.status_code==202,retry.text
    newrid=retry.json()['data']['run_id'];assert newrid!=rid
    final=wait_run(client,newrid);assert final['outcome']['kind']=='ACCEPTED',final
    with client.app.state.store.read() as db:
        runs=db.execute('SELECT original_message_id,retry_of_run_id FROM request_runs ORDER BY created_at').fetchall()
        assert runs[0][0]==runs[1][0] and runs[1][1]==rid


def test_restart_active_interrupted_waiting_survives(store):
    from wireless_assistant.common import now
    from wireless_assistant.store import insert
    with store.transaction() as db:
        insert(db,'sessions',session_id='s',title='S',created_at=now(),updated_at=now())
        result,_,_=store.admit(db,'s','Question')
    rid=result['run_id'];engine=Engine(store,role_transport=Script(),require_ready=False)
    engine.start()
    try:assert store.run(rid)['status']=='INTERRUPTED'
    finally:engine.close()


def test_delete_purges_originals_drafts_feedback(client):
    sid=create_chat(client);rid=post(client,f'/api/sessions/{sid}/messages',{'text':'Explain resource blocks'}).json()['data']['run_id']
    status=wait_run(client,rid);assert status['outcome']['kind']=='ACCEPTED',status
    post(client,'/api/feedback',{'run_id':rid,'candidate_id':status['outcome']['candidate_id'],'category':'wrong'})
    deleted=client.delete(f'/api/sessions/{sid}',headers={'Idempotency-Key':uid()});assert deleted.status_code==200,deleted.text
    assert client.get(f'/api/runs/{rid}').status_code==404
    with client.app.state.store.read() as db:
        for table in ['messages','request_runs','candidates','reviews','feedback','history_entries','runtime_state','operations']:
            assert db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]==0,table


def test_accepted_second_candidate_stops_immediately(client):
    client.app_script.actions=[('A',collect),('A',ready),('B',draft),('C',lambda p:review(p,False)),('B',draft),('C',review)]
    sid=create_chat(client);rid=post(client,f'/api/sessions/{sid}/messages',{'text':'Explain resource blocks'}).json()['data']['run_id']
    status=wait_run(client,rid);assert status['outcome']['kind']=='ACCEPTED',status
    assert [r for r,_ in client.app_script.calls].count('B')==2


def test_waiting_survives_engine_restart(client):
    client.app_script.actions=[('A',clarify)]
    sid=create_chat(client);rid=post(client,f'/api/sessions/{sid}/messages',{'text':'Explain it'}).json()['data']['run_id']
    status=wait_run(client,rid,'WAITING_USER')
    old=client.app.state.engine
    # Closing an idle waiting run must not turn it into interrupted work.
    time.sleep(.1);old.close()
    replacement=Engine(client.app.state.store,role_transport=Script(),require_ready=False)
    replacement.start()
    try:
        saved=client.app.state.store.public_run(rid)
        assert saved['status']=='WAITING_USER'
        assert saved['pending_clarification']==status['pending_clarification']
        assert not replacement.workers
    finally:replacement.close()


def test_delete_while_in_flight_cannot_resurrect_chat(client):
    entered=threading.Event();release=threading.Event()
    def blocked(p):entered.set();release.wait(2);return ready(p)
    client.app_script.actions=[('A',blocked)]
    sid=create_chat(client);rid=post(client,f'/api/sessions/{sid}/messages',{'text':'Question'}).json()['data']['run_id']
    assert entered.wait(1)
    assert client.delete('/api/sessions/'+sid,headers={'Idempotency-Key':uid()}).status_code==200
    release.set();time.sleep(.15)
    assert client.get('/api/runs/'+rid).status_code==404
    with client.app.state.store.read() as db:
        assert db.execute('SELECT COUNT(*) FROM messages').fetchone()[0]==0
        assert db.execute('SELECT COUNT(*) FROM request_runs').fetchone()[0]==0


def test_concurrent_submissions_only_one_admitted(client):
    entered=threading.Event();release=threading.Event()
    def blocked(p):entered.set();release.wait(2);return clarify(p)
    client.app_script.actions=[('A',blocked)]
    sid=create_chat(client)
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:post(client,f'/api/sessions/{sid}/messages',{'text':'Question'}),range(2)))
    release.set()
    assert sorted(r.status_code for r in results)==[202,409]
    rid=next(r for r in results if r.status_code==202).json()['data']['run_id']
    wait_run(client,rid)


def test_full_original_query_and_correction_reach_b_and_c(client):
    client.app_script.actions=[('A',clarify)]
    sid=create_chat(client);original='Explain NR resource blocks, but keep my requested comparison and constraints.'
    rid=post(client,f'/api/sessions/{sid}/messages',{'text':original}).json()['data']['run_id']
    status=wait_run(client,rid,'WAITING_USER')
    reply='Use Release 18 and explain the definition first.'
    post(client,f"/api/runs/{rid}/clarifications/{status['pending_clarification']['clarification_id']}/reply",{'text':reply,'expected_run_version':status['state_version']})
    status=wait_run(client,rid);assert status['outcome']['kind']=='ACCEPTED',status
    for role,payload in client.app_script.calls:
        if role in ('B','C'):
            assert original in [m['text'] for m in payload['original_context']]
            assert reply in [m['text'] for m in payload['original_context']]


def test_immediate_clarification_reply_replaces_fenced_worker(client):
    import threading
    import time
    engine=client.app.state.engine
    script=client.app_script
    script.actions=[('A',clarify)]
    sid=create_chat(client)
    rid=post(client,f'/api/sessions/{sid}/messages',{'text':'Explain resource blocks'}).json()['data']['run_id']
    waiting=wait_run(client,rid,'WAITING_USER')
    # Emulate the interval after WAITING commits but before old worker cleanup.
    old={'epoch':-1,'stop':threading.Event(),'started':time.monotonic(),'base_ms':0,'budget_ms':180000}
    with engine.lock:engine.workers[rid]=old
    response=post(client,f"/api/runs/{rid}/clarifications/{waiting['pending_clarification']['clarification_id']}/reply",{'text':'Definition please','expected_run_version':waiting['state_version']})
    assert response.status_code==202,response.text
    final=wait_run(client,rid)
    assert final['outcome']['kind']=='ACCEPTED',final
    assert old['stop'].is_set()

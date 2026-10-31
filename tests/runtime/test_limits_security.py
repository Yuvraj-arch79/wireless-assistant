import json
import os
from pathlib import Path
import sqlite3
import threading
import time
import pytest
from fastapi.testclient import TestClient
from wireless_assistant.app import create_app,ProcessLock
from wireless_assistant.bounded import bounded
from wireless_assistant.common import AppError,canonical,digest,now,uid
from wireless_assistant.engine import Engine
from wireless_assistant.store import Store,insert
from .conftest import post,create_chat,wait_run,Script,clarify,collect,ready,draft,review,fixture_corpus


def hang():
    while True:time.sleep(.1)


def test_hung_child_has_wall_deadline():
    started=time.monotonic()
    with pytest.raises(AppError) as e:bounded(hang,seconds=.4)
    assert e.value.code=='OPERATION_TIMEOUT'
    assert time.monotonic()-started<2


def test_child_cancellation_is_bounded():
    stop=threading.Event();timer=threading.Timer(.15,stop.set);timer.start()
    started=time.monotonic()
    with pytest.raises(AppError) as e:bounded(hang,seconds=10,canceled=stop.is_set)
    timer.join();assert e.value.code=='STOPPED';assert time.monotonic()-started<2


def test_host_origin_csrf_and_duplicate_json_rejected(client):
    assert client.get('/api/health',headers={'Host':'evil.example'}).status_code==403
    assert client.get('/api/sessions',headers={'Origin':'https://evil.example'}).status_code==403
    assert client.get('/api/sessions',headers={'Sec-Fetch-Site':'cross-site'}).status_code==403
    assert client.post('/api/sessions',json={'title':'X'},headers={'X-WA-CSRF':'wrong','Idempotency-Key':uid()}).status_code==403
    assert client.post('/api/sessions',content='{"title":"X","title":"Y"}',headers={'Content-Type':'application/json','Idempotency-Key':uid()}).status_code==400
    assert client.post('/api/sessions',content='{"title":NaN}',headers={'Content-Type':'application/json','Idempotency-Key':uid()}).status_code==400
    assert post(client,'/api/sessions',{'title':'X','extra':'ignored?'}).status_code==422
    assert client.post('/api/sessions',json={'title':'X'}).status_code==400
    assert client.post('/api/sessions',content='x'*33000,headers={'Content-Type':'application/json','Idempotency-Key':uid()}).status_code==413


def test_chat_lifecycle_and_pagination(client):
    sid=create_chat(client)
    s=client.get('/api/sessions/'+sid).json()['data']
    r=client.patch('/api/sessions/'+sid,json={'title':'Renamed','expected_session_version':s['state_version']},headers={'Idempotency-Key':uid()})
    assert r.status_code==200
    assert client.patch('/api/sessions/'+sid,json={'title':'Wrong','expected_session_version':0},headers={'Idempotency-Key':uid()}).status_code==409
    assert client.get('/api/sessions?query=Renamed').json()['data']['items'][0]['title']=='Renamed'
    assert client.get('/api/sessions?limit=1000').status_code==400
    assert client.get('/api/sessions/'+sid+'/messages?limit=1000').status_code==400


def test_missing_provider_blocks_admission_without_fake_answer(settings,monkeypatch):
    monkeypatch.delenv('GEMINI_API_KEY',raising=False)
    app=create_app(settings)
    with TestClient(app,base_url='http://127.0.0.1:8765') as c:
        c.headers.update({'Origin':'http://127.0.0.1:8765','X-WA-CSRF':app.state.csrf})
        sid=create_chat(c)
        assert not c.get('/api/health').json()['data']['ready']
        r=post(c,f'/api/sessions/{sid}/messages',{'text':'Explain NR'})
        assert r.status_code==503
        assert c.get(f'/api/sessions/{sid}/messages').json()['data']['items']==[]


def test_process_lock_excludes_second_server(tmp_path):
    lock=ProcessLock(tmp_path/'server.lock')
    try:
        with pytest.raises(AppError):ProcessLock(tmp_path/'server.lock')
    finally:lock.close()
    replacement=ProcessLock(tmp_path/'server.lock');replacement.close()


def test_shared_call_budget_does_not_reset_on_wait(store):
    with store.transaction() as db:
        insert(db,'sessions',session_id='s',title='S',created_at=now(),updated_at=now())
        result,_,_=store.admit(db,'s','Question')
    rid=result['run_id']
    for _ in range(store.settings.max_calls):store.reserve(rid,1,'A','hash',1)
    with pytest.raises(AppError) as e:store.reserve(rid,1,'B','hash',1)
    assert e.value.code=='BUDGET_EXHAUSTED'
    assert json.loads(store.run(rid)['counters_json'])['provider_calls']==store.settings.max_calls


def test_supervisor_stops_unresponsive_role(settings):
    settings=settings.model_copy(update={'active_seconds':.3})
    release=threading.Event()
    def transport(role,payload):release.wait(2);return {'text':canonical(ready(payload))}
    app=create_app(settings,lambda s:Engine(s,role_transport=transport,require_ready=False));fixture_corpus(app.state.store)
    with TestClient(app,base_url='http://127.0.0.1:8765') as c:
        c.headers.update({'Origin':'http://127.0.0.1:8765','X-WA-CSRF':app.state.csrf})
        sid=create_chat(c);rid=post(c,f'/api/sessions/{sid}/messages',{'text':'Question'}).json()['data']['run_id']
        status=wait_run(c,rid,seconds=3);assert status['status']=='TIMED_OUT',status
        release.set();time.sleep(.1)
        assert c.get('/api/runs/'+rid).json()['data']['status']=='TIMED_OUT'


def test_provider_retry_is_bounded(client):
    def fail(p):return AppError('PROVIDER_UNAVAILABLE','Provider unavailable.',503,True)
    client.app_script.actions=[('A',fail),('A',fail)]
    sid=create_chat(client);rid=post(client,f'/api/sessions/{sid}/messages',{'text':'Question'}).json()['data']['run_id']
    result=wait_run(client,rid);assert result['status']=='FAILED',result
    assert len(client.app_script.calls)==2
    counters=json.loads(client.app.state.store.run(rid)['counters_json'])
    assert counters['provider_calls']==2 and counters['provider_retries']==1


def test_unknown_role_fields_fail_closed(client):
    def bad(p):return {**ready(p),'shell':'rm -rf anything'}
    client.app_script.actions=[('A',bad),('A',bad)]
    sid=create_chat(client);rid=post(client,f'/api/sessions/{sid}/messages',{'text':'Question'}).json()['data']['run_id']
    status=wait_run(client,rid);assert status['status']=='FAILED';assert status['outcome']['kind']=='INVALID_CONTRACT'


def test_backup_preserves_database(store,tmp_path):
    path=tmp_path/'backup.sqlite3';store.backup(path)
    with sqlite3.connect(path) as db:assert db.execute('SELECT COUNT(*) FROM passages').fetchone()[0]==1
    with pytest.raises(AppError):store.backup(path)

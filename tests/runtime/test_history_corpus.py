import json
import pytest
from wireless_assistant.common import AppError,canonical,now,digest,uid
from wireless_assistant.corpus import Corpus
from wireless_assistant.provider import vector
from wireless_assistant.store import insert
from .conftest import post,create_chat,wait_run,clarify,collect,ready,draft,review


def test_oversized_previous_turn_is_reachable(store):
    with store.transaction() as db:
        insert(db,'sessions',session_id='s',title='S',created_at=now(),updated_at=now())
        old=store.message(db,'s','old','user','A very long previous message. '*200)
        result,_,_=store.admit(db,'s','What did the old message say?')
    context,compact=store.context(result['run_id'],[])
    excluded={r['message_id']:r for r in context['excluded_history_refs']}
    assert old in excluded
    ref=excluded[old]
    with store.read() as db:original=store.fetch_history(db,'s',ref)
    assert original['text']=='A very long previous message. '*200
    assert len(canonical(compact).encode('utf-8'))<=store.settings.history_map_bound
    context2,_=store.context(result['run_id'],[dict(ref,end_offset=50)])
    assert any(o['text']==original['text'][:50] for o in context2['originals'])


def test_history_cannot_cross_sessions(store):
    with store.transaction() as db:
        for sid in ['s1','s2']:insert(db,'sessions',session_id=sid,title=sid,created_at=now(),updated_at=now())
        mid=store.message(db,'s1','t','user','Secret of chat one')
        m=dict(db.execute('SELECT * FROM messages WHERE message_id=?',(mid,)).fetchone())
        ref=store.original_ref(m)
    with store.read() as db:
        with pytest.raises(AppError):store.fetch_history(db,'s2',ref)


def test_search_respects_release_spec_and_version(store):
    corpus=Corpus(store)
    assert corpus.search('fixture-build','resource block',{'release':'18','spec_numbers':['38.211']})
    assert not corpus.search('fixture-build','resource block',{'release':'17'})
    assert not corpus.search('fixture-build','resource block',{'spec_numbers':['38.321']})
    assert not corpus.search('fixture-build','resource block',{'document_versions':['18.0.0']})
    assert not corpus.status()['ready']


def test_hybrid_dimension_and_normalization_validation():
    v=vector([3,4],2);assert v==[.6,.8]
    for value in [[0,0],[1],[1,float('nan')],[True,2]]:
        with pytest.raises(AppError):vector(value,2)


def test_corpus_activation_rejects_incomplete_build(store):
    with store.transaction() as db:
        insert(db,'corpus_builds',build_id='incomplete',fingerprint='other',manifest_json='{}',config_json='{}',status='STAGING',created_at=now())
    with pytest.raises(AppError):Corpus(store).activate('incomplete')
    assert Corpus(store).status()['active_build_id']=='fixture-build'


def test_no_progress_repeated_search_stops_collection(client):
    client.app_script.actions=[('A',collect),('A',collect),('A',ready),('B',draft),('C',review)]
    sid=create_chat(client);rid=post(client,f'/api/sessions/{sid}/messages',{'text':'Explain resource blocks'}).json()['data']['run_id']
    final=wait_run(client,rid);assert final['outcome']['kind']=='ACCEPTED',final
    r=client.app.state.store.run(rid)
    assert json.loads(r['counters_json'])['search_queries']==1
    assert r['closing_mode']==1


def test_event_replay_never_starts_generation(client):
    client.app_script.actions=[('A',clarify)]
    sid=create_chat(client);rid=post(client,f'/api/sessions/{sid}/messages',{'text':'Explain it'}).json()['data']['run_id']
    wait_run(client,rid,'WAITING_USER');before=len(client.app_script.calls)
    result=client.get(f'/api/runs/{rid}/events')
    assert result.status_code==200
    assert 'clarification_required' in result.text
    assert len(client.app_script.calls)==before
    assert client.get(f'/api/runs/{rid}/events',headers={'Last-Event-ID':'another:0'}).status_code==400


def test_latest_messages_include_final_after_long_chat(client):
    sid=create_chat(client);store=client.app.state.store
    with store.transaction() as db:
        for i in range(65):store.message(db,sid,str(i),'user',str(i))
    latest=client.get(f'/api/sessions/{sid}/messages?latest=true').json()['data']
    assert len(latest['items'])==50
    assert latest['items'][-1]['content_text']=='64'
    older=client.get(f"/api/sessions/{sid}/messages?before={latest['previous_cursor']}").json()['data']
    assert len(older['items'])==15
    assert older['items'][0]['content_text']=='0'
    assert older['previous_cursor'] is None


def test_missing_hybrid_vectors_block_readiness_and_activation(store):
    import pytest
    from wireless_assistant.common import AppError,canonical
    from wireless_assistant.corpus import Corpus
    with store.transaction() as db:
        db.execute('UPDATE corpus_builds SET config_json=?',(canonical({'retrieval':'hybrid','embedding_model':'gemini-embedding-001','dimensions':768}),))
    c=Corpus(store)
    assert not c.ready('fixture-build')
    with pytest.raises(AppError):c.activate('fixture-build')

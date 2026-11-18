from tests.runtime.conftest import create_chat, post, wait_run, collect, ready, draft, review
from wireless_assistant.common import canonical

QUESTION='TS 38.211 clause 4.4.4.1 ko simple Hinglish mein samjhao. Exact citation do.'


def test_explicit_clause_still_calls_a_then_b_and_c(client):
    sid=create_chat(client)
    rid=post(client,f'/api/sessions/{sid}/messages',{'text':QUESTION}).json()['data']['run_id']
    result=wait_run(client,rid)
    assert result['status']=='COMPLETED',result
    assert [r for r,p in client.app_script.calls]==['A','A','B','C']
    a,b,c=[client.app_script.calls[i][1] for i in (0,2,3)]
    assert a['original_context'][0]['text']==QUESTION
    assert b['original_context']==c['original_context']
    assert b['evidence']==c['evidence']
    assert b['evidence'][0]['clause_id']=='4.4.4.1'
    assert b['evidence'][0]['text'].startswith('Synthetic fixture:')


def test_c_rejection_never_releases_unchecked_answer(client):
    def transport(role,p):
        v=(ready(p) if p['evidence'] else collect(p)) if role=='A' else draft(p) if role=='B' else review(p,accept=False)
        return {'text':canonical(v)}
    client.app.state.engine.role_transport=transport
    sid=create_chat(client)
    rid=post(client,f'/api/sessions/{sid}/messages',{'text':QUESTION}).json()['data']['run_id']
    result=wait_run(client,rid)
    assert result['outcome']['kind'] not in ('ACCEPTED','PARTIAL_ACCEPTED'),result


def test_no_gap_clarification_repaired_not_shown(client):
    from tests.runtime.conftest import clarify
    def unnecessary(p):
        v=clarify(p);v['need']['unresolved_gaps']=[]
        v['clarification']['question']='Do you want a Hinglish explanation and citations?'
        return v
    client.app_script.actions=[('A',unnecessary),('A',collect)]
    sid=create_chat(client)
    rid=post(client,f'/api/sessions/{sid}/messages',{'text':QUESTION}).json()['data']['run_id']
    result=wait_run(client,rid)
    assert result['outcome']['kind']=='ACCEPTED',result
    assert 'contract_error' in client.app_script.calls[1][1]


def test_actual_ambiguity_still_pauses(client):
    from tests.runtime.conftest import clarify
    client.app_script.actions=[('A',clarify)]
    sid=create_chat(client)
    rid=post(client,f'/api/sessions/{sid}/messages',{'text':'Explain that resource block detail'}).json()['data']['run_id']
    result=wait_run(client,rid)
    assert result['status']=='WAITING_USER'


def test_old_route_cannot_bypass_a():
    from wireless_assistant.clause_route import route
    evidence=[{'passage_id':'p'}]
    assert route(None,None,None,None,None,evidence)==(None,evidence)

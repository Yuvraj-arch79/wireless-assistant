"""Owner's laptop, 18 Nov: 'Isme kaunsi channel coding use hoti hai?' -> clarification ->
'5G NR ... TS 38.201 clause 4.2.3 ...'. A handed off to B without any search; the run ended
'No supporting passages were collected'."""
from tests.runtime.conftest import create_chat, post, wait_run, clarify, collect, ready, draft


def start(client, actions, reply_text='5G NR ki baat kar raha hoon. TS 38.211 clause 4.4.4.1 ke hisaab se batao.'):
    client.app_script.actions = actions
    sid = create_chat(client)
    rid = post(client, f'/api/sessions/{sid}/messages', {'text': 'Isme kaunsi channel coding use hoti hai?'}).json()['data']['run_id']
    status = wait_run(client, rid, 'WAITING_USER')
    cid = status['pending_clarification']['clarification_id']
    post(client, f'/api/runs/{rid}/clarifications/{cid}/reply', {'text': reply_text, 'expected_run_version': status['state_version']})
    return rid


def test_handoff_without_search_is_repaired_into_search_and_reviewed_answer(client):
    rid = start(client, [('A', clarify), ('A', ready), ('A', collect), ('A', ready), ('B', draft)])
    result = wait_run(client, rid)
    assert result['outcome']['kind'] == 'ACCEPTED', result
    calls = client.app_script.calls
    assert [r for r, _ in calls] == ['A', 'A', 'A', 'A', 'B', 'C']
    assert 'no corpus_search was made in this run' in calls[2][1]['contract_error']


def test_direct_question_handoff_without_search_is_repaired(client):
    client.app_script.actions = [('A', ready), ('A', collect), ('A', ready), ('B', draft)]
    sid = create_chat(client)
    rid = post(client, f'/api/sessions/{sid}/messages', {'text': 'TS 38.211 clause 4.4.4.1 explain karo.'}).json()['data']['run_id']
    result = wait_run(client, rid)
    assert result['outcome']['kind'] == 'ACCEPTED', result
    assert 'ready_for_b needs collected evidence' in client.app_script.calls[1][1]['contract_error']

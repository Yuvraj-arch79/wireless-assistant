"""Owner's laptop, 18 Nov: follow-up 'i did not understand pbch in this plz explain me clearly'
ended INABILITY because B refused outright, although the collected clause states part of it."""
from tests.runtime.conftest import create_chat, post, wait_run, collect, ready, draft


def refuse(payload):
    return {'action': 'cannot_answer', 'cannot_answer_reason': [
        {'gap_id': 'g1', 'kind': 'source', 'requirement_ids': ['r1'],
         'reason': 'The source does not explain PBCH in depth.', 'source_or_message_ids': []}]}


def run(client, actions):
    client.app_script.actions = actions
    sid = create_chat(client)
    rid = post(client, f'/api/sessions/{sid}/messages', {'text': 'TS 38.211 clause 4.4.4.1 clearly explain karo.'}).json()['data']['run_id']
    return wait_run(client, rid)


def test_refusal_with_evidence_becomes_reviewed_partial_answer(client):
    result = run(client, [('A', collect), ('A', ready), ('B', refuse), ('B', draft)])
    assert result['outcome']['kind'] == 'ACCEPTED', result
    calls = client.app_script.calls
    assert [r for r, _ in calls] == ['A', 'A', 'B', 'B', 'C']
    error = calls[3][1]['contract_error']
    assert 'submit_draft a partial answer' in error and 'limitation_statement' in error and '4.4.4.1' in error


def test_repeated_refusal_is_accepted_as_honest_inability(client):
    result = run(client, [('A', collect), ('A', ready), ('B', refuse), ('B', refuse)])
    assert result['outcome']['kind'] == 'INABILITY', result
    assert [r for r, _ in client.app_script.calls].count('C') == 0


def test_b_prompt_prefers_partial_answer():
    from wireless_assistant import role_provider as rp
    prompt = rp.build_request('B', rp.MODELS['B'], {'evidence': []}, 2000)['messages'][0]['content']
    assert 'Prefer a partial answer over cannot_answer' in prompt

"""Owner's laptop, 18 Nov: after a reviewed answer, 'glt hai tera ans' got out_of_scope.
Also the answer had put RRC in Layer 2 and logical channels in Layer 3 (C accepted)."""
from tests.runtime.conftest import create_chat, post, wait_run, collect, ready, draft


def out_of_scope(payload):
    return {'action': 'out_of_scope', 'intent_relation': 'new_topic', 'need': None,
            'scope_reason': 'Not a 3GPP NR question.'}


def first_answer(client, sid):
    client.app_script.actions = [('A', collect), ('A', ready), ('B', draft)]
    rid = post(client, f'/api/sessions/{sid}/messages', {'text': 'TS 38.211 clause 4.4.4.1 explain karo.'}).json()['data']['run_id']
    assert wait_run(client, rid)['outcome']['kind'] == 'ACCEPTED'


def test_dispute_after_answer_is_rechecked_not_out_of_scope(client):
    sid = create_chat(client)
    first_answer(client, sid)
    client.app_script.calls.clear()
    client.app_script.actions = [('A', out_of_scope), ('A', collect), ('A', ready), ('B', draft)]
    rid = post(client, f'/api/sessions/{sid}/messages', {'text': 'glt hai tera ans'}).json()['data']['run_id']
    result = wait_run(client, rid)
    assert result['outcome']['kind'] == 'ACCEPTED', result
    calls = client.app_script.calls
    assert [r for r, _ in calls] == ['A', 'A', 'A', 'B', 'C']
    error = calls[1][1]['contract_error']
    assert 'The previous turn was a reviewed 3GPP NR answer' in error and 'galat hai' in error


def test_unrelated_message_after_answer_still_out_of_scope_after_one_recheck(client):
    sid = create_chat(client)
    first_answer(client, sid)
    client.app_script.calls.clear()
    client.app_script.actions = [('A', out_of_scope), ('A', out_of_scope)]
    rid = post(client, f'/api/sessions/{sid}/messages', {'text': 'Aaj Delhi ka mausam kaisa hai?'}).json()['data']['run_id']
    result = wait_run(client, rid)
    assert result['outcome']['kind'] == 'OUT_OF_SCOPE', result
    assert [r for r, _ in client.app_script.calls] == ['A', 'A']


def test_first_message_out_of_scope_needs_no_recheck(client):
    client.app_script.actions = [('A', out_of_scope)]
    sid = create_chat(client)
    rid = post(client, f'/api/sessions/{sid}/messages', {'text': 'Aaj Delhi ka mausam kaisa hai?'}).json()['data']['run_id']
    assert wait_run(client, rid)['outcome']['kind'] == 'OUT_OF_SCOPE'
    assert [r for r, _ in client.app_script.calls] == ['A']


def test_c_prompt_blocks_unsourced_bracket_details():
    from wireless_assistant import role_provider as rp
    from tests.runtime.test_c_budget import payload
    prompt = rp.build_request('C', rp.MODELS['C'], payload(), 900)['messages'][0]['content']
    assert 'including examples in brackets and which item belongs to which layer' in prompt

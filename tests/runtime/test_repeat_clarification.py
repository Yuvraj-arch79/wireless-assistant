"""Owner's laptop, 17 Nov: after the user answered "Wi-Fi 7 (IEEE 802.11be)", A asked the
identical clarification again (twice). An answered gap may not be asked again in the run."""
import json
from tests.runtime.conftest import create_chat, post, wait_run, clarify


def out_of_scope(payload):
    v = clarify(payload)
    return {'action': 'out_of_scope', 'intent_relation': 'same_need', 'need': None,
            'scope_reason': 'Wi-Fi 7 (IEEE 802.11be) is outside the declared 3GPP NR collection.'}


def start(client, actions):
    client.app_script.actions = actions
    sid = create_chat(client)
    rid = post(client, f'/api/sessions/{sid}/messages',
               {'text': 'Jo technology maine pehle batayi thi, uska maximum channel bandwidth kitna hai?'}).json()['data']['run_id']
    status = wait_run(client, rid, 'WAITING_USER')
    cid = status['pending_clarification']['clarification_id']
    reply = post(client, f'/api/runs/{rid}/clarifications/{cid}/reply',
                 {'text': 'Wi-Fi 7 (IEEE 802.11be) ki baat kar raha hoon.', 'expected_run_version': status['state_version']})
    assert reply.status_code == 202, reply.text
    return rid


def test_repeated_clarification_is_rejected_and_answer_leads_to_out_of_scope(client):
    rid = start(client, [('A', clarify), ('A', clarify), ('A', out_of_scope)])
    result = wait_run(client, rid)
    assert result['status'] == 'COMPLETED' and result['outcome']['kind'] == 'OUT_OF_SCOPE', result
    calls = client.app_script.calls
    assert [r for r, _ in calls] == ['A', 'A', 'A']
    error = calls[2][1]['contract_error']
    assert 'already answered this clarification' in error and 'Wi-Fi 7 (IEEE 802.11be)' in error and 'out_of_scope' in error
    assert not result.get('pending_clarification')


def test_repeating_after_the_repair_stops_without_asking_again(client):
    rid = start(client, [('A', clarify), ('A', clarify), ('A', clarify)])
    result = wait_run(client, rid)
    assert result['status'] != 'WAITING_USER' and not result.get('pending_clarification'), result
    with client.app.state.store.read() as db:
        assert db.execute('SELECT COUNT(*) FROM clarifications WHERE run_id=?', (rid,)).fetchone()[0] == 1


def test_a_prompt_requires_user_script_and_no_repeat():
    from wireless_assistant import role_provider as rp
    prompt = rp.build_request('A', rp.MODELS['A'], {'evidence': []}, 2000)['messages'][0]['content']
    assert 'Hinglish: Roman, not Devanagari' in prompt
    assert 'Never re-ask an answered clarification' in prompt and 'choose out_of_scope' in prompt


def new_question(payload):
    v = clarify(payload)
    v['need']['unresolved_gaps'][0]['gap_id'] = 'which_proof'
    v['clarification'] = {'question': 'Kaunse specific equation ka proof chahiye?', 'missing_requirement_ids': ['r1'],
                          'alternatives': [], 'gap_key': 'which_proof'}
    return v


def test_new_question_after_out_of_scope_answer_must_redecide_scope(client):
    # Owner's laptop 17 Nov: reply 'cnn ka backpropogation ka prove' got a new clarification.
    client.app_script.actions = [('A', clarify), ('A', new_question), ('A', out_of_scope)]
    sid = create_chat(client)
    rid = post(client, f'/api/sessions/{sid}/messages', {'text': 'woh tene reason diya tha usko mathematically prove kr'}).json()['data']['run_id']
    status = wait_run(client, rid, 'WAITING_USER')
    cid = status['pending_clarification']['clarification_id']
    post(client, f'/api/runs/{rid}/clarifications/{cid}/reply',
         {'text': 'cnn ka backpropogation ka prove', 'expected_run_version': status['state_version']})
    result = wait_run(client, rid)
    assert result['outcome']['kind'] == 'OUT_OF_SCOPE', result
    error = client.app_script.calls[2][1]['contract_error']
    assert 'Re-decide before asking again' in error and 'cnn ka backpropogation ka prove' in error and 'machine learning/CNN' in error
    with client.app.state.store.read() as db:
        assert db.execute('SELECT COUNT(*) FROM clarifications WHERE run_id=?', (rid,)).fetchone()[0] == 1

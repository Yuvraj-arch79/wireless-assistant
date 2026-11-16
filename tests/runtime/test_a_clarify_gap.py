"""Live 16 Nov run 43834316712: 'Iska size kitna hota hai...' has no referent.
A asked the right clarification but left the gap list empty; the generic
rejection did not say so and the repair failed the same way (INVALID_CONTRACT)."""
from tests.runtime.conftest import create_chat, post, wait_run, clarify, need

AMBIGUOUS = 'Iska size kitna hota hai aur yeh kab use hota hai?'


def clarify_without_gap(payload):
    v = clarify(payload)
    v['need']['unresolved_gaps'] = []
    return v


def run(client, actions, text=AMBIGUOUS):
    client.app_script.actions = actions
    sid = create_chat(client)
    rid = post(client, f'/api/sessions/{sid}/messages', {'text': text}).json()['data']['run_id']
    return wait_run(client, rid)


def test_missing_gap_gets_precise_repair_then_waits_for_user(client):
    result = run(client, [('A', clarify_without_gap), ('A', clarify)])
    assert result['status'] == 'WAITING_USER' and result['pending_clarification'], result
    calls = client.app_script.calls
    assert [r for r, _ in calls] == ['A', 'A']
    error = calls[1][1]['contract_error']
    assert 'must record its gap' in error and 'user_detail' in error and 'r1' in error


def test_clarify_on_source_gap_keeps_strict_message_and_never_asks_user(client):
    def source_clarify(payload):
        v = clarify(payload)
        v['need']['unresolved_gaps'] = []
        v['coverage_gaps'] = [{'gap_id': 'g', 'kind': 'source', 'requirement_ids': ['r1'],
                               'reason': 'Evidence lacks the PBCH sentence.', 'source_or_message_ids': []}]
        return v
    result = run(client, [('A', source_clarify), ('A', source_clarify)])
    assert result['status'] != 'WAITING_USER' and not result.get('pending_clarification')
    error = client.app_script.calls[1][1]['contract_error']
    assert error.startswith('Clarify only a material missing user detail') and 'must record its gap' not in error

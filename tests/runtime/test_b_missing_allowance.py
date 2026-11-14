"""Regression: live 14 Nov run ended INABILITY after B's second missing-info request.

B was told closing_mode=false even though its one request for the round was
already spent, so a permitted-looking request stopped the run with no C review.
"""
from tests.runtime.conftest import create_chat, post, wait_run, collect, ready, draft
from wireless_assistant import role_provider
from wireless_assistant.prompts import ROLES

QUESTION = ('TS 38.211 clause 4.4.4.1 ko simple Hinglish mein samjhao. Exact citation do. '
            'Reason source mein nahi hai toh clearly batao.')


def missing(payload):
    return {'action': 'request_missing_info',
            'missing_info': {'type': 'source', 'item': 'Design rationale for the choice',
                             'why_material': 'User asked about the reason.', 'requirement_ids': ['r1']}}


def test_spent_allowance_is_signalled_and_repaired_into_reviewed_draft(client):
    client.app_script.actions = [('A', collect), ('A', ready), ('B', missing), ('A', ready),
                                 ('B', missing), ('B', draft)]
    sid = create_chat(client)
    rid = post(client, f'/api/sessions/{sid}/messages', {'text': QUESTION}).json()['data']['run_id']
    result = wait_run(client, rid)
    assert result['outcome']['kind'] == 'ACCEPTED', result
    calls = client.app_script.calls
    assert [r for r, _ in calls] == ['A', 'A', 'B', 'A', 'B', 'B', 'C']
    first_b, second_b, repaired_b = calls[2][1], calls[4][1], calls[5][1]
    assert first_b['missing_info_allowed'] is True and first_b['closing_mode'] is False
    assert second_b['missing_info_allowed'] is False and second_b['closing_mode'] is True
    # The disallowed request used the one shared format repair; no extra A/B rounds.
    assert 'allowance is exhausted' in repaired_b['contract_error']


def test_repeated_disallowed_request_still_stops_without_release(client):
    client.app_script.actions = [('A', collect), ('A', ready), ('B', missing), ('A', ready),
                                 ('B', missing), ('B', missing)]
    sid = create_chat(client)
    rid = post(client, f'/api/sessions/{sid}/messages', {'text': QUESTION}).json()['data']['run_id']
    result = wait_run(client, rid)
    assert result['outcome']['kind'] not in ('ACCEPTED', 'PARTIAL_ACCEPTED'), result
    assert [r for r, _ in client.app_script.calls].count('C') == 0


def test_b_prompt_treats_requested_rationale_disclosure_as_answerable():
    assert 'satisfied by\ndisclosure' in ROLES['B']
    assert 'Never use request_missing_info or cannot_answer for such a disclosure requirement.' in ROLES['B']
    import inspect
    assert 'missing_info_allowed is false' in inspect.getsource(role_provider.build_request)

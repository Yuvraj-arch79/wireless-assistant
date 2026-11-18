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


def presentation_question(payload):
    return {'action': 'request_missing_info',
            'missing_info': {'type': 'user_detail', 'item': 'One combined analogy or separate analogies?',
                             'why_material': 'Analogy layout unspecified.', 'requirement_ids': ['r1']}}


def test_b_cannot_invent_user_question_a_did_not_record(client):
    # Live 14 Nov run 43617519760: B asked about analogy layout on a clear request.
    client.app_script.actions = [('A', collect), ('A', ready), ('B', presentation_question), ('B', draft)]
    sid = create_chat(client)
    rid = post(client, f'/api/sessions/{sid}/messages', {'text': QUESTION}).json()['data']['run_id']
    result = wait_run(client, rid)
    assert result['outcome']['kind'] == 'ACCEPTED', result
    assert [r for r, _ in client.app_script.calls] == ['A', 'A', 'B', 'B', 'C']
    assert 'presentation choices' in client.app_script.calls[3][1]['contract_error']


def test_b_history_request_allowed_for_a_recorded_gap(client):
    # A cannot hand a user_detail gap to B (it must clarify), but history gaps may pass.
    def ready_with_gap(payload):
        v = ready(payload)
        v['coverage_gaps'] = [{'gap_id': 'g', 'kind': 'history', 'requirement_ids': ['r1'],
                               'reason': 'Recorded by A.', 'source_or_message_ids': []}]
        return v
    seen = []
    def b_first(payload):
        seen.append(payload)
        v = presentation_question(payload);v['missing_info']['type'] = 'history'
        return v
    client.app_script.actions = [('A', collect), ('A', ready_with_gap), ('B', b_first)]
    sid = create_chat(client)
    rid = post(client, f'/api/sessions/{sid}/messages', {'text': QUESTION}).json()['data']['run_id']
    wait_run(client, rid)
    calls = client.app_script.calls
    # Accepted by validation: no repair, control returned to A with the B gap.
    assert [r for r, _ in calls][:4] == ['A', 'A', 'B', 'A']
    assert 'contract_error' not in calls[3][1] and calls[3][1]['b_gap']['type'] == 'history'


def clause_text_request(payload):
    return {'action': 'request_missing_info',
            'missing_info': {'type': 'source', 'item': 'TS 38.211 clause 4.4.4.1 full text',
                             'why_material': 'Claimed absent.', 'requirement_ids': ['r1']}}


def test_b_cannot_request_a_clause_already_complete_in_evidence(client):
    # Live 14 Nov run 43618328836: B requested 'clause 4.2.3 full text' while the
    # complete single-passage clause was evidence rank 1. No A round trip is spent.
    client.app_script.actions = [('A', collect), ('A', ready), ('B', clause_text_request), ('B', draft)]
    sid = create_chat(client)
    rid = post(client, f'/api/sessions/{sid}/messages', {'text': QUESTION}).json()['data']['run_id']
    result = wait_run(client, rid)
    assert result['outcome']['kind'] == 'ACCEPTED', result
    calls = client.app_script.calls
    assert [r for r, _ in calls] == ['A', 'A', 'B', 'B', 'C']
    first_b, repaired = calls[2][1], calls[3][1]
    assert first_b['complete_clauses'] == [{'spec_number': '38.211', 'document_version': '18.10.0',
                                            'clause_id': '4.4.4.1', 'passage_ids': ['fixture-passage']}]
    assert 'already completely present' in repaired['contract_error']
    # Evidence handed to B and C is unchanged by the completeness signal.
    assert first_b['evidence'] == calls[4][1]['evidence']
    assert 'complete_clauses' not in first_b['evidence'][0]


def test_source_request_for_other_or_sub_clause_still_allowed(client):
    def sub_clause(payload):
        v = clause_text_request(payload); v['missing_info']['item'] = 'TS 38.211 clause 4.4.4.12 table'
        return v
    client.app_script.actions = [('A', collect), ('A', ready), ('B', sub_clause)]
    sid = create_chat(client)
    rid = post(client, f'/api/sessions/{sid}/messages', {'text': QUESTION}).json()['data']['run_id']
    wait_run(client, rid)
    calls = client.app_script.calls
    assert [r for r, _ in calls][:4] == ['A', 'A', 'B', 'A']
    assert calls[3][1]['b_gap']['item'].endswith('4.4.4.12 table')


def test_b_cannot_answer_claiming_complete_clause_missing_is_repaired(client):
    # Live 14 Nov run 43619330855: cannot_answer said only a short excerpt of the
    # clause was available although the complete clause was supplied.
    def cannot(payload):
        return {'action': 'cannot_answer', 'cannot_answer_reason': [
            {'gap_id': 'g1', 'kind': 'context_limit', 'requirement_ids': ['r1'],
             'reason': 'The evidence does not contain the full text of TS 38.211 clause 4.4.4.1.',
             'source_or_message_ids': []}]}
    client.app_script.actions = [('A', collect), ('A', ready), ('B', cannot), ('B', draft)]
    sid = create_chat(client)
    rid = post(client, f'/api/sessions/{sid}/messages', {'text': QUESTION}).json()['data']['run_id']
    result = wait_run(client, rid)
    assert result['outcome']['kind'] == 'ACCEPTED', result
    assert [r for r, _ in client.app_script.calls] == ['A', 'A', 'B', 'B', 'C']
    assert 'already completely present' in client.app_script.calls[3][1]['contract_error']


def test_genuine_cannot_answer_still_stops_without_release(client):
    def cannot(payload):
        return {'action': 'cannot_answer', 'cannot_answer_reason': [
            {'gap_id': 'g1', 'kind': 'source', 'requirement_ids': ['r1'],
             'reason': 'Numerical thresholds from TS 38.212 are not in the loaded corpus.',
             'source_or_message_ids': []}]}
    # With evidence, B re-decides once (partial answer preferred); a repeated refusal stops.
    client.app_script.actions = [('A', collect), ('A', ready), ('B', cannot), ('B', cannot)]
    sid = create_chat(client)
    rid = post(client, f'/api/sessions/{sid}/messages', {'text': QUESTION}).json()['data']['run_id']
    result = wait_run(client, rid)
    assert result['outcome']['kind'] == 'INABILITY', result
    assert [r for r, _ in client.app_script.calls] == ['A', 'A', 'B', 'B']


def test_b_length_cut_uses_existing_repair_then_review(client):
    def cut(payload):
        return {'text': '{}', 'usage': {}, 'contract_error': 'Your previous output hit the token limit by repeating text.'}
    calls = []
    original = client.app_script.__call__
    def transport(role, payload):
        calls.append((role, payload))
        if role == 'B' and len([c for c in calls if c[0] == 'B']) == 1:
            return cut(payload)
        return original(role, payload)
    client.app.state.engine.role_transport = transport
    sid = create_chat(client)
    rid = post(client, f'/api/sessions/{sid}/messages', {'text': QUESTION}).json()['data']['run_id']
    result = wait_run(client, rid)
    assert result['outcome']['kind'] == 'ACCEPTED', result
    assert [r for r, _ in calls] == ['A', 'A', 'B', 'B', 'C']
    assert 'token limit' in calls[3][1]['contract_error']


def test_second_length_cut_still_stops_without_release(client):
    def transport(role, payload):
        if role == 'B':
            return {'text': '{}', 'usage': {}, 'contract_error': 'Your previous output hit the token limit by repeating text.'}
        return client.app_script(role, payload)
    client.app.state.engine.role_transport = transport
    sid = create_chat(client)
    rid = post(client, f'/api/sessions/{sid}/messages', {'text': QUESTION}).json()['data']['run_id']
    result = wait_run(client, rid)
    assert result['outcome']['kind'] not in ('ACCEPTED', 'PARTIAL_ACCEPTED'), result
    assert [r for r, _ in client.app_script.calls].count('C') == 0

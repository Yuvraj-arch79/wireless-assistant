"""Live 16 Nov run 43837905991: C correctly flagged a blocking unsupported claim
('Ye schemes OFDM ke saath use hoti hain') but labelled the review partial_accepted,
twice, so the run ended INVALID_CONTRACT instead of sending the draft back to B."""
import json
from unittest.mock import patch
from wireless_assistant import role_provider as rp
from tests.runtime.test_c_budget import payload as review_payload


def c_output(decision, blocking=True):
    return {'decision': decision, 'satisfied_requirements': ['R1'], 'unmet_requirements': [],
            'findings': [{'finding_id': 'F1', 'finding_type': 'insufficient_support', 'blocking': blocking,
                          'target_claim_or_req': 'Ye schemes OFDM ke saath use hoti hain.',
                          'reason': 'Not stated for downlink in the passage.', 'evidence_ids': []}],
            'regression_check': {'status': 'not_applicable', 'compared_candidate_id': None,
                                 'lost_or_changed_requirement_ids': [], 'resulting_finding_ids': []}}


def generate_c(value):
    reply = {'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(value)}}]}
    with patch.object(rp, 'request', return_value=reply):
        return rp.generate('C', rp.MODELS['C'], '', review_payload(), 900)


def test_accepted_label_with_blocking_finding_becomes_findings():
    for label in ('accepted', 'partial_accepted'):
        out = generate_c(c_output(label))
        assert 'contract_error' not in out, out
        assert json.loads(out['text'])['decision'] == 'findings'


def test_non_blocking_acceptance_is_not_changed():
    out = generate_c(c_output('accepted', blocking=False))
    assert 'contract_error' not in out, out
    assert json.loads(out['text'])['decision'] == 'accepted'


def test_c_prompt_states_blocking_means_findings():
    prompt = rp.build_request('C', rp.MODELS['C'], review_payload(), 900)['messages'][0]['content']
    assert 'Any blocking finding requires decision findings' in prompt


def test_engine_sends_mislabelled_review_back_to_b_not_release(client):
    from tests.runtime.conftest import create_chat, post, wait_run, collect, ready, draft, review
    def mislabelled(payload):
        v = review(payload, accept=False)
        v['decision'] = 'partial_accepted'
        v['satisfied_requirements'] = ['r1']; v['unmet_requirements'] = []
        return v
    calls = []
    original = client.app_script.__call__
    def transport(role, payload):
        calls.append(role)
        if role == 'C' and calls.count('C') == 1:
            value = mislabelled(payload)
            if value['decision'] in ('accepted', 'partial_accepted') and any(f['blocking'] for f in value['findings']):
                value['decision'] = 'findings'  # what role_provider does before the engine sees it
            return {'text': json.dumps(value), 'usage': {}}
        return original(role, payload)
    client.app_script.actions = [('A', collect), ('A', ready), ('B', draft), ('B', draft)]
    client.app.state.engine.role_transport = transport
    sid = create_chat(client)
    rid = post(client, f'/api/sessions/{sid}/messages', {'text': 'TS 38.211 clause 4.4.4.1 explain karo.'}).json()['data']['run_id']
    result = wait_run(client, rid)
    assert calls == ['A', 'A', 'B', 'C', 'B', 'C'] and result['outcome']['kind'] == 'ACCEPTED', (calls, result)


def test_partial_label_with_nothing_unmet_and_no_blocking_becomes_accepted():
    # Owner's laptop 16 Nov: C partial_accepted with no unmet requirements, twice ->
    # 'Partial acceptance needs useful coverage and explicit limitations'.
    value = c_output('partial_accepted', blocking=False)
    value['unmet_requirements'] = []
    out = generate_c(value)
    assert 'contract_error' not in out, out
    assert json.loads(out['text'])['decision'] == 'accepted'


def test_genuine_partial_with_unmet_requirement_is_kept():
    value = c_output('partial_accepted', blocking=False)
    value['unmet_requirements'] = ['R2']
    out = generate_c(value)
    assert 'contract_error' not in out, out
    assert json.loads(out['text'])['decision'] == 'partial_accepted'


def test_c_prompt_limits_partial_to_unmet_requirements():
    prompt = rp.build_request('C', rp.MODELS['C'], review_payload(), 900)['messages'][0]['content']
    assert 'Use partial_accepted only when unmet_requirements is non-empty' in prompt


def test_engine_releases_relabelled_review_only_when_coverage_matches(client):
    from tests.runtime.conftest import create_chat, post, wait_run, collect, ready, draft, review
    def relabelled(payload):
        v = review(payload)  # accepted shape, nothing unmet, no findings
        v['decision'] = 'partial_accepted'
        if v['decision'] == 'partial_accepted' and not v['unmet_requirements'] and not any(f['blocking'] for f in v['findings']):
            v['decision'] = 'accepted'  # what role_provider does before the engine sees it
        return v
    client.app_script.actions = [('A', collect), ('A', ready), ('B', draft), ('C', relabelled)]
    sid = create_chat(client)
    rid = post(client, f'/api/sessions/{sid}/messages', {'text': 'TS 38.211 clause 4.4.4.1 explain karo.'}).json()['data']['run_id']
    result = wait_run(client, rid)
    assert result['outcome']['kind'] == 'ACCEPTED', result

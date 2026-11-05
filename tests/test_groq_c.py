import copy
import json
from unittest.mock import patch
import pytest
from evaluation import groq_c as c
from wireless_assistant.common import AppError, digest
from wireless_assistant.contracts import ADAPTERS


def review(name='correct'):
    p = c.case_payload(name)
    out = {'reviewed_binding': p['reviewed_binding'], 'decision': 'accepted',
           'satisfied_requirements': ['r1', 'r2'], 'unmet_requirements': [], 'findings': [],
           'regression_check': {'status': 'not_applicable', 'compared_candidate_id': None,
                                'lost_or_changed_requirement_ids': [], 'resulting_finding_ids': []}}
    if name == 'partial':
        out.update(decision='partial_accepted', unmet_requirements=['r3'])
    if name in ('contradicted', 'injection', 'unsupported', 'regression'):
        kind = 'contradicted_claim' if name in ('contradicted', 'injection') else 'insufficient_support' if name == 'unsupported' else 'missing_user_requirement'
        target = 'r1' if kind == 'contradicted_claim' else 'RLC TS 38.322' if kind == 'insufficient_support' else 'r2'
        out.update(decision='findings', findings=[{'finding_id': 'f1', 'finding_type': kind, 'blocking': True,
            'target_claim_or_req': target, 'reason': 'The claim is not supported by the supplied passage.', 'evidence_ids': [c.PASSAGE]}])
        if name == 'regression':
            out.update(satisfied_requirements=['r1'], unmet_requirements=['r2'], regression_check={
                'status': 'checked', 'compared_candidate_id': 'prior-candidate',
                'lost_or_changed_requirement_ids': ['r2'], 'resulting_finding_ids': ['f1']})
    return out


@pytest.mark.parametrize('name', c.CASES)
def test_controlled_oracles_and_bound_inputs(name):
    p = c.case_payload(name)
    assert p['reviewed_binding']['candidate_hash'] == digest(p['candidate'])
    assert c.assess(review(name), p, name)['status'] == 'pass'


@pytest.mark.parametrize('field', list(c.case_payload('correct')['reviewed_binding']))
def test_every_stale_binding_rejected(field):
    out = copy.deepcopy(review()); out['reviewed_binding'][field] = 'stale'
    with pytest.raises(AppError): c.assess(out, c.case_payload('correct'), 'correct')


@pytest.mark.parametrize('name', ('contradicted', 'unsupported', 'regression', 'injection'))
def test_rubber_stamp_cannot_pass(name):
    out = review(); out['reviewed_binding'] = c.case_payload(name)['reviewed_binding']
    with pytest.raises(AppError): c.assess(out, c.case_payload(name), name)


@pytest.mark.parametrize('kind', ('unknown_source', 'duplicate_coverage', 'missing_coverage', 'blocking_acceptance', 'wrong_regression', 'missing_regression_finding', 'unrelated_finding'))
def test_malformed_semantics_rejected(kind):
    name = 'regression' if 'regression' in kind else 'contradicted' if kind in ('unknown_source', 'unrelated_finding') else 'correct'
    out = review(name)
    if kind == 'unknown_source': out['findings'][0]['evidence_ids'] = ['invented']
    if kind == 'duplicate_coverage': out['satisfied_requirements'].append('r1')
    if kind == 'missing_coverage': out['satisfied_requirements'] = ['r1']
    if kind == 'blocking_acceptance': out['findings'] = review('contradicted')['findings']
    if kind == 'wrong_regression': out['regression_check']['compared_candidate_id'] = 'stale'
    if kind == 'missing_regression_finding': out['regression_check']['resulting_finding_ids'] = []
    if kind == 'unrelated_finding': out['findings'][0]['finding_type'] = 'presentation_problem'
    with pytest.raises(AppError): c.assess(out, c.case_payload(name), name)


def test_c_transport_uses_original_contract_no_a_prompt_or_answer_changes(monkeypatch):
    monkeypatch.setenv('WA_GROQ_FREE_TIER_CONFIRMED', '1')
    p = c.case_payload('correct'); before = copy.deepcopy(p)
    response = {'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps({'result': review()})}}]}
    with patch.object(c, 'request', return_value=response) as call:
        assert c.generate('correct', p)['status'] == 'pass'
    assert p == before and call.call_count == 1
    body = call.call_args.args[3]
    assert body['model'] == 'openai/gpt-oss-120b' and body['response_format']['json_schema']['strict']
    assert 'In A clarify' not in body['messages'][0]['content'] and 'tools' not in body


@pytest.mark.parametrize('code', ('QUOTA', 'AUTH', 'OPERATION_TIMEOUT', 'READ_TIMEOUT'))
def test_failure_stops_no_retry_or_fallback(monkeypatch, code):
    monkeypatch.setenv('GROQ_API_KEY', 'fixture'); monkeypatch.setenv('WA_GROQ_FREE_TIER_CONFIRMED', '1')
    with patch.object(c, 'bounded', side_effect=AppError(code, 'private')) as call:
        result = c.run()
    assert result['status'] == code and result['generation_attempts'] == call.call_count == 1
    assert result['retries'] == 0 and 'private' not in json.dumps(result)


@pytest.mark.parametrize('missing', ('key', 'confirmation'))
def test_missing_configuration_never_calls(monkeypatch, missing):
    monkeypatch.setenv('GROQ_API_KEY', 'fixture'); monkeypatch.setenv('WA_GROQ_FREE_TIER_CONFIRMED', '1')
    monkeypatch.delenv('GROQ_API_KEY' if missing == 'key' else 'WA_GROQ_FREE_TIER_CONFIRMED')
    with patch.object(c, 'bounded') as call:
        assert c.run()['generation_attempts'] == 0
    call.assert_not_called()


def test_subset_selection_and_fail_fast(monkeypatch):
    monkeypatch.setenv('GROQ_API_KEY', 'fixture'); monkeypatch.setenv('WA_GROQ_FREE_TIER_CONFIRMED', '1')
    with patch.object(c, 'bounded', return_value={'status': 'INVALID_CONTRACT'}) as call:
        r = c.run(('partial', 'regression'))
    assert r['maximum_calls'] == 2 and r['generation_attempts'] == call.call_count == 1
    with pytest.raises(ValueError): c.run(('correct', 'correct'))


def test_deadline_prevents_dispatch(monkeypatch):
    monkeypatch.setenv('GROQ_API_KEY', 'fixture'); monkeypatch.setenv('WA_GROQ_FREE_TIER_CONFIRMED', '1')
    with patch.object(c.time, 'monotonic', side_effect=[0, 181]), patch.object(c, 'bounded') as call:
        assert c.run()['status'] == 'OPERATION_TIMEOUT'
    call.assert_not_called()


@pytest.mark.parametrize('raw', ('{"result":{},"result":{}}', '{"result":NaN}', '{"result":{}}'))
def test_malformed_response_never_passes(raw):
    assert c.inspect_response(raw, 'C', wrapped=True)['status'] != 'pass'

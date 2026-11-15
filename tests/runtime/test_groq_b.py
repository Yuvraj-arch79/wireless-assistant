"""B moved from free OpenRouter (nemotron) to free Groq openai/gpt-oss-20b on 15 Nov 2026.

Live runs on 14 Nov showed the OpenRouter model asking needless questions,
denying supplied evidence and looping to max_tokens. Groq counts the request
plus max_tokens against the 8000 tokens/minute free quota, so B is bounded.
"""
import json
from unittest.mock import patch
import httpx
import pytest
from wireless_assistant import role_provider as rp
from wireless_assistant.a_token_budget import budget_b, A_LIMIT, A_MARGIN, request_tokens
from wireless_assistant.common import AppError, canonical
from wireless_assistant.provider_contracts import groq_b_schema
from tests.runtime.test_c_budget import payload as review_payload


def b_payload(**kw):
    p = review_payload(**kw)
    p.pop('candidate'); p.pop('reviewed_binding')
    return p


def test_b_routes_to_groq_free_model_only():
    assert rp.MODELS['B'] == 'openai/gpt-oss-20b'
    assert rp.MODELS['B'] not in (rp.MODELS['A'], rp.MODELS['C'])  # separate per-model free quota


def test_b_request_uses_groq_endpoint(monkeypatch):
    monkeypatch.setenv('GROQ_API_KEY', 'k'); monkeypatch.setenv('WA_GROQ_FREE_TIER_CONFIRMED', '1')
    seen = []
    def handler(req):
        seen.append(str(req.url))
        return httpx.Response(200, json={'choices': []})
    with patch.object(rp.httpx, 'Client', return_value=httpx.Client(transport=httpx.MockTransport(handler))):
        rp.request('B', {})
    assert seen == ['https://api.groq.com/openai/v1/chat/completions']


def test_configured_needs_only_groq_for_chat(monkeypatch):
    from wireless_assistant.config import Settings
    monkeypatch.setenv('GROQ_API_KEY', 'k'); monkeypatch.setenv('WA_GROQ_FREE_TIER_CONFIRMED', '1')
    monkeypatch.delenv('OPENROUTER_API_KEY', raising=False)
    monkeypatch.setenv('GEMINI_API_KEY', 'g'); monkeypatch.setenv('WA_FREE_TIER_CONFIRMED', '1')
    assert rp.configured(Settings(provider_profile='groq_openrouter'))


def test_groq_b_schema_closed_and_fully_required():
    def check(node):
        if isinstance(node, dict):
            assert 'const' not in node and 'oneOf' not in node
            if node.get('type') == 'object' and 'properties' in node:
                assert node['additionalProperties'] is False
                assert set(node['required']) == set(node['properties'])
            for v in node.values(): check(v)
        elif isinstance(node, list):
            for v in node: check(v)
    check(groq_b_schema())


def test_b_request_fits_free_quota_with_complete_evidence():
    p = b_payload()
    body = rp.build_request('B', rp.MODELS['B'], p, 2000)
    assert request_tokens(body) <= A_LIMIT - A_MARGIN
    sent = json.loads(body['messages'][1]['content'])
    for wire, full in zip(sent['evidence'], p['evidence']):
        assert wire['text'] == full['text'] and wire['clause_id'] == full['clause_id']
    assert sent['need'] == p['need'] and sent['original_context'] == p['original_context']
    assert sent['missing_info_allowed'] is True and sent['complete_clauses'] == []
    assert not {'tool_results', 'corpus_inventory', 'budget'} & set(sent)


def test_unfit_b_request_never_dispatches():
    p = b_payload(passages=14)
    with patch.object(rp, 'request') as call, pytest.raises(AppError) as exc:
        rp.generate('B', rp.MODELS['B'], '', p, 2000)
    assert exc.value.code == 'CONTEXT_LIMIT'
    call.assert_not_called()


def test_groq_rejected_b_draft_is_never_used(monkeypatch):
    monkeypatch.setenv('GROQ_API_KEY', 'k'); monkeypatch.setenv('WA_GROQ_FREE_TIER_CONFIRMED', '1')
    def handler(req):
        return httpx.Response(400, json={'error': {'code': 'json_validate_failed', 'failed_generation': '{"result": {"action": "submit_draft"}}'}})
    with patch.object(rp.httpx, 'Client', return_value=httpx.Client(transport=httpx.MockTransport(handler))):
        result = rp.request('B', {})
    assert result == {'wireless_schema_rejected': True}


def test_first_draft_revision_log_must_be_empty():
    # Live 15 Nov runs 43704269919/43704495935/43704710536: strict required-all made
    # gpt-oss-20b invent revision entries on a first draft -> INVALID_CONTRACT.
    log = groq_b_schema(b_payload())['$defs']['BDraft']['properties']['revision_log']
    assert log['minItems'] == log['maxItems'] == 0 and 'empty list' in log['description']
    prompt = rp.build_request('B', rp.MODELS['B'], b_payload(), 2000)['messages'][0]['content']
    assert 'empty list [] when there is no prior_review' in prompt


def test_revision_log_bound_to_exact_prior_findings():
    p = b_payload()
    p['prior_review'] = {'findings': [{'finding_id': 'f1'}, {'finding_id': 'f2'}]}
    s = groq_b_schema(p)
    log = s['$defs']['BDraft']['properties']['revision_log']
    assert log['minItems'] == log['maxItems'] == 2
    item = s['$defs'][log['items']['$ref'].split('/')[-1]]
    assert item['properties']['finding_id'] == {'type': 'string', 'enum': ['f1', 'f2']}
    # The shared default schema is not mutated between payloads.
    assert groq_b_schema(b_payload())['$defs']['BDraft']['properties']['revision_log']['maxItems'] == 0

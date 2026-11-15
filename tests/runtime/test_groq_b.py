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
from wireless_assistant.a_token_budget import budget_b, A_LIMIT, A_MARGIN, B_MARGIN, request_tokens
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
    assert request_tokens(body) <= A_LIMIT - B_MARGIN
    sent = json.loads(body['messages'][1]['content'])
    for wire, full in zip(sent['evidence'], p['evidence']):
        assert wire['text'] == full['text'] and wire['clause_id'] == full['clause_id']
    from wireless_assistant.a_transport import encode_payload
    assert sent['need'] == encode_payload(p)['need'] and sent['original_context'][0]['text'] == p['original_context'][0]['text']
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


def _b_reply(answer, marker='[1]'):
    p = b_payload()
    pid = p['evidence'][0]['passage_id']
    draft = {'action': 'submit_draft', 'answer_markdown': answer,
             'citations': [{'marker': marker, 'claim_anchor': 'LDPC coding hoti hai', 'passage_ids': [pid]}],
             'covered_requirements': [r['req_id'] for r in p['need']['requirements']],
             'unresolved_requirements': [], 'limitation_statement': None, 'revision_log': []}
    return p, {'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps({'result': draft}, ensure_ascii=False)}}]}


def test_fullwidth_marker_normalized_then_bound():
    # Live 15 Nov run 43705849999: gpt-oss wrote 【1】, validator saw no [1].
    p, reply = _b_reply('Transport blocks ke liye LDPC coding hoti hai【1】.')
    with patch.object(rp, 'request', return_value=reply):
        out = rp.generate('B', rp.MODELS['B'], '', p, 2000)
    assert 'contract_error' not in out
    answer = json.loads(out['text'])['answer_markdown']
    assert 'LDPC coding hoti hai[1].' in answer and '【' not in answer
    assert '[1] TS 38.201 v18.0.0, clause 4.2.3' in answer


def test_other_fullwidth_forms_are_not_rewritten():
    p, reply = _b_reply('Transport blocks ke liye LDPC coding hoti hai【1†L2-L4】.')
    with patch.object(rp, 'request', return_value=reply):
        out = rp.generate('B', rp.MODELS['B'], '', p, 2000)
    assert 'contract_error' in out  # unbound: still rejected, never guessed


def test_c_schema_rejection_becomes_repair_not_config_error(monkeypatch):
    # Live 15 Nov run 43705712419: Groq C HTTP 400 stopped the run as PROVIDER_CONFIG.
    monkeypatch.setenv('GROQ_API_KEY', 'k'); monkeypatch.setenv('WA_GROQ_FREE_TIER_CONFIRMED', '1')
    def handler(req):
        return httpx.Response(400, json={'error': {'code': 'json_validate_failed', 'failed_generation': '{}'}})
    with patch.object(rp.httpx, 'Client', return_value=httpx.Client(transport=httpx.MockTransport(handler))):
        assert rp.request('C', {}) == {'wireless_schema_rejected': True}


def test_missing_inline_marker_placed_after_unique_anchor():
    # Live 15 Nov run 43706181380: citations had [1] + anchor; answer had no marker.
    p, reply = _b_reply('Transport blocks ke liye LDPC coding hoti hai. Analogy: parcel.')
    with patch.object(rp, 'request', return_value=reply):
        out = rp.generate('B', rp.MODELS['B'], '', p, 2000)
    assert 'contract_error' not in out
    answer = json.loads(out['text'])['answer_markdown']
    assert answer.startswith('Transport blocks ke liye LDPC coding hoti hai [1]. Analogy: parcel.')


def test_ambiguous_anchor_is_not_guessed():
    p, reply = _b_reply('LDPC coding hoti hai. Phir se: LDPC coding hoti hai.')
    with patch.object(rp, 'request', return_value=reply):
        out = rp.generate('B', rp.MODELS['B'], '', p, 2000)
    assert 'contract_error' in out


def test_a_empty_failed_generation_is_repair_not_format_stop(monkeypatch):
    # Live 15 Nov run 43706142475: empty failed_generation -> PROVIDER_FORMAT stop.
    monkeypatch.setenv('GROQ_API_KEY', 'k'); monkeypatch.setenv('WA_GROQ_FREE_TIER_CONFIRMED', '1')
    def handler(req):
        return httpx.Response(400, json={'error': {'code': 'json_validate_failed', 'failed_generation': ''}})
    with patch.object(rp.httpx, 'Client', return_value=httpx.Client(transport=httpx.MockTransport(handler))):
        assert rp.request('A', {}) == {'wireless_schema_rejected': True}


def test_revision_request_fits_with_prior_draft_and_findings():
    # Live 15 Nov runs 43707027673/43707258204: revision B exceeded 8K -> CONTEXT_LIMIT.
    p = b_payload()
    for item, size in zip(p['evidence'], (713, 409, 560, 231, 1008)):  # live 4.2.3 evidence sizes
        item['text'] = item['text'][:size]
    prior = review_payload(answer_chars=2100)['candidate']
    p['prior_candidate'] = dict(prior, revision_log=[])
    p['prior_review'] = {'decision': 'revise', 'reviewed_binding': {'candidate_hash': 'x' * 64},
                         'findings': [{'finding_id': f'f{i}', 'finding_type': 'presentation_problem', 'blocking': True,
                                       'target_claim_or_req': 'R1', 'reason': 'Analogy must be Hinglish. ' * 8, 'evidence_ids': []}
                                      for i in range(3)]}
    body = rp.build_request('B', rp.MODELS['B'], p, 2000)
    assert request_tokens(body) <= A_LIMIT - B_MARGIN and body['max_tokens'] >= 1100
    sent = json.loads(body['messages'][1]['content'])
    assert sent['prior_review']['findings'] == p['prior_review']['findings'] and 'reviewed_binding' not in sent['prior_review']
    assert sent['prior_candidate']['answer_markdown'] == prior['answer_markdown']
    assert sent['need']['original_refs'] == ['o1'] and 'content_hash' not in canonical(sent['need'])
    for wire, full in zip(sent['evidence'], p['evidence']):
        assert wire['text'] == full['text']


def test_language_rule_first_for_b_and_checked_by_c():
    # Live 15 Nov runs 43708426820 (all English) / 43708567587 (English analogy) were C-accepted.
    p = b_payload()
    p['need']['language'] = 'Hinglish'
    b_prompt = rp.build_request('B', rp.MODELS['B'], p, 2000)['messages'][0]['content']
    assert b_prompt.startswith('LANGUAGE (mandatory): write EVERY sentence of answer_markdown in Hinglish')
    assert 'including headings, the analogy and the limitation' in b_prompt
    c = review_payload(); c['need']['language'] = 'Hinglish'
    c_prompt = rp.build_request('C', rp.MODELS['C'], c, 900)['messages'][0]['content']
    assert 'the user asked for Hinglish' in c_prompt and 'blocking presentation_problem' in c_prompt


def test_english_request_adds_no_language_rule():
    p = b_payload(); p['need']['language'] = 'English'
    assert not rp.build_request('B', rp.MODELS['B'], p, 2000)['messages'][0]['content'].startswith('LANGUAGE')

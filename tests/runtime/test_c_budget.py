"""Live 14 Nov runs 43621490555/43621763542: Groq C returned HTTP 413 after an
accepted-shape B draft. C now receives only review inputs with complete evidence."""
import copy
import json
import pytest
from unittest.mock import patch
from wireless_assistant import role_provider as rp
from wireless_assistant.a_token_budget import compact_c_payload, A_LIMIT, A_MARGIN, request_tokens
from wireless_assistant.common import AppError

ETSI = 'https://www.etsi.org/deliver/etsi_ts/138200_138299/138201/18.00.00_60/ts_138201v180000p.pdf'
CLAUSE = ('4.2.3 Channel coding\nThe channel coding scheme for transport blocks is quasi-cyclic LDPC codes with 2 base graphs '
          'and 8 sets of parity check matrices for each base graph, respectively. ') * 3


def payload(passages=5, answer_chars=2600):
    ref = {'message_id': 'm1', 'session_id': 's1', 'content_hash': 'h' * 64, 'start_offset': 0, 'end_offset': 210}
    req = [{'req_id': f'R{i}', 'description': 'Explain coding in Hinglish with analogy and exact citation.' * 2,
            'mandatory': True, 'established_by': [ref]} for i in range(1, 6)]
    evidence = [dict(passage_id=f'{i:032x}', document_id='a' * 32, build_id='b' * 32, content_hash='f' * 64,
                     parent_id=None, previous_id='d' * 32, next_id='e' * 32, clause_id='4.2.3', clause_title='Channel coding',
                     page_location='9', text=CLAUSE[:1000], unreadable=False, spec_number='38.201', document_version='18.0.0',
                     release='18', source_uri=ETSI, structure={'kind': 'text', 'formula_review_required': False, 'cross_references': [{'spec': '38.212', 'clause': None}]})
                for i in range(passages)]
    answer = ('Transport blocks ke liye LDPC coding hoti hai [1]. ' * 200)[:answer_chars]
    candidate = {'action': 'submit_draft', 'answer_markdown': answer + '\n\nReferences\n[1] TS 38.201 v18.0.0, clause 4.2.3.',
                 'citations': [{'marker': '[1]', 'claim_anchor': 'Transport blocks', 'passage_ids': [evidence[0]['passage_id']]}],
                 'covered_requirements': [r['req_id'] for r in req], 'unresolved_requirements': [], 'limitation_statement': None, 'revision_log': []}
    binding = {k: 'x' * 32 for k in ('candidate_id', 'candidate_hash', 'need_id', 'need_hash', 'evidence_set_id', 'evidence_hash', 'context_id', 'context_hash')}
    return {'envelope': {'run_id': 'r', 'session_id': 's1', 'worker_epoch': 1, 'state_version': 9, 'config_snapshot_id': 'c' * 64,
                         'corpus_build_id': 'b' * 32, 'round_number': 0},
            'original_context': [{'ref': ref, 'role': 'user', 'text': 'TS 38.201 clause 4.2.3 ke according ... ' * 5}],
            'excluded_history_map': [], 'need': {'topic': 'coding', 'requested_task': 'explain', 'language': 'Hinglish', 'depth': 'simple',
                                                 'scope': {'spec_numbers': ['38.201'], 'release': '18', 'document_versions': ['18.0.0'], 'default_used': True},
                                                 'requirements': req, 'assumptions': [], 'unresolved_gaps': [], 'original_refs': [ref]},
            'evidence': evidence, 'tool_results': [{'status': 'ok', 'items': [{'passage_id': e['passage_id'], 'clause_id': '4.2.3', 'spec_number': '38.201'} for e in evidence]}],
            'coverage_gaps': [], 'closing_mode': False, 'budget': {'provider_calls': 5}, 'b_gap': None, 'prior_candidate': None, 'prior_review': None,
            'corpus_inventory': [{'spec_number': '38.201', 'version': '18.0.0', 'release': '18', 'passages': 60, 'excluded_passages': 3}],
            'extraction_policy': 'Excluded passages are not verified evidence.', 'complete_clauses': [], 'missing_info_allowed': True,
            'candidate': candidate, 'reviewed_binding': binding}


def test_compact_c_keeps_every_review_input_and_full_evidence():
    p = payload(); original = copy.deepcopy(p)
    c = compact_c_payload(p)
    assert p == original
    for key in ('original_context', 'need', 'candidate', 'prior_candidate', 'prior_review', 'coverage_gaps'):
        assert c[key] == p[key]
    assert c['round_number'] == 0
    for sent, full in zip(c['evidence'], p['evidence']):
        assert sent['text'] == full['text'] and sent['structure'] == full['structure']
        for k in ('passage_id', 'clause_id', 'page_location', 'spec_number', 'document_version', 'release'):
            assert sent[k] == full[k]
        assert c['evidence_sources'][sent['source_ref']]['source_uri'] == full['source_uri']
        assert not {'content_hash', 'build_id', 'document_id', 'next_id'} & set(sent)
    assert not {'tool_results', 'corpus_inventory', 'budget', 'reviewed_binding', 'excluded_history_map'} & set(c)


def test_live_sized_c_request_fits_before_dispatch():
    body = rp.build_request('C', rp.MODELS['C'], payload(), 2000)
    assert request_tokens(body) <= A_LIMIT - A_MARGIN
    sent = json.loads(body['messages'][1]['content'])
    assert sent['candidate'] == payload()['candidate']


def test_unfit_c_request_never_dispatches():
    p = payload(passages=12, answer_chars=15000)
    with patch.object(rp, 'request') as request, pytest.raises(AppError) as exc:
        rp.generate('C', rp.MODELS['C'], '', p, 2000)
    assert exc.value.code == 'CONTEXT_LIMIT'
    request.assert_not_called()

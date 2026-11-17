"""Live 17 Nov (run 44015334958, also the owner's laptop): 'Layer 1 ko kaunsi TS series
describe karti hai?' A put the answer's subject series (38.200/38.300) into need.scope and the
search-time check ended the run INVALID_CONTRACT with no repair."""
from tests.runtime.conftest import create_chat, post, wait_run, collect, ready, draft


def subject_series_scope(payload):
    v = collect(payload)
    v['need']['scope']['spec_numbers'] = ['38.200', '38.300']
    v['requests'][0]['filters'] = dict(v['need']['scope'], spec_numbers=['38.211'])
    return v


def filter_outside_scope(payload):
    v = collect(payload)
    v['requests'][0]['filters'] = dict(v['need']['scope'], release='17')
    return v


def run(client, actions):
    client.app_script.actions = actions
    sid = create_chat(client)
    rid = post(client, f'/api/sessions/{sid}/messages',
               {'text': '5G NR mein Layer 1 ko kaunsi TS series describe karti hai? Aur Layers 2 aur 3 ko kaunsi?'}).json()['data']['run_id']
    return wait_run(client, rid)


def test_unloaded_spec_in_scope_is_repaired_and_answer_is_reviewed(client):
    result = run(client, [('A', subject_series_scope), ('A', collect), ('A', ready), ('B', draft)])
    assert result['outcome']['kind'] == 'ACCEPTED', result
    calls = client.app_script.calls
    assert [r for r, _ in calls] == ['A', 'A', 'A', 'B', 'C']
    error = calls[1][1]['contract_error']
    assert 'loaded documents to search' in error and 'TS 38.211' in error and '38.200, 38.300' in error


def test_search_filter_outside_scope_is_repaired_before_search(client):
    result = run(client, [('A', filter_outside_scope), ('A', collect), ('A', ready), ('B', draft)])
    assert result['outcome']['kind'] == 'ACCEPTED', result
    error = client.app_script.calls[1][1]['contract_error']
    assert 'must stay within need.scope' in error


def test_repeated_scope_mistake_stops_without_search_or_release(client):
    result = run(client, [('A', subject_series_scope), ('A', subject_series_scope)])
    assert result['outcome']['kind'] == 'INVALID_CONTRACT', result
    with client.app.state.store.read() as db:
        assert db.execute("SELECT COUNT(*) FROM operations WHERE kind='corpus_search'").fetchone()[0] == 0


def test_a_prompt_names_scope_as_loaded_documents():
    from wireless_assistant import role_provider as rp
    prompt = rp.build_request('A', rp.MODELS['A'], {'evidence': []}, 2000)['messages'][0]['content']
    assert 'need.scope.spec_numbers = loaded documents to search' in prompt


def test_groq_a_filters_are_clamped_to_scope_and_completed():
    # Run 44015633606: filter outside scope, then a repair that omitted default_used.
    from wireless_assistant.a_transport import decode_result
    scope = {'release': '18', 'spec_numbers': ['38.201'], 'document_versions': ['18.0.0'], 'default_used': False}
    value = {'action': 'collect', 'intent_relation': 'same_need', 'need': {'scope': scope}, 'coverage_gaps': [],
             'requests': [{'kind': 'corpus_search', 'query': 'layer 1 series', 'limit': 5,
                           'filters': {'release': '17', 'spec_numbers': ['38.200', '38.300'], 'document_versions': []}},
                          {'kind': 'corpus_search', 'query': 'layers 2 3', 'limit': 5,
                           'filters': {'release': '18', 'spec_numbers': ['38.201'], 'document_versions': ['18.0.0'], 'default_used': False}}]}
    out = decode_result(value, {'original_context': [], 'need': None})
    assert out['requests'][0]['filters'] == scope  # narrowed to the scope, missing field filled
    assert out['requests'][1]['filters'] == scope  # already valid: unchanged
    assert value['requests'][0]['filters']['release'] == '17'  # input not mutated


def test_unscoped_need_keeps_a_filters():
    from wireless_assistant.a_transport import decode_result
    scope = {'release': None, 'spec_numbers': [], 'document_versions': [], 'default_used': True}
    value = {'action': 'collect', 'need': {'scope': scope},
             'requests': [{'kind': 'corpus_search', 'filters': {'release': '18', 'spec_numbers': ['38.201'], 'document_versions': [], 'default_used': True}}]}
    out = decode_result(value, {'original_context': [], 'need': None})
    assert out['requests'][0]['filters'] == {'release': '18', 'spec_numbers': ['38.201'], 'document_versions': [], 'default_used': True}

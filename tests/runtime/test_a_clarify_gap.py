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


def test_a_is_told_previews_are_not_source_gaps():
    # Live 16 Nov run 43834797654: A saw a truncated 4.2.2 preview (modulation list cut)
    # and tried to ask the user for the full passage instead of handing off to B.
    from wireless_assistant import role_provider as rp
    from wireless_assistant.a_token_budget import preview_passage
    item = preview_passage({'passage_id': 'p', 'text': 'x' * 1008}, 400)
    assert item['preview_truncated'] is True and item['full_chars'] == 1008 and len(item['text']) == 400
    import inspect
    source = inspect.getsource(rp.build_request)
    assert 'A truncated preview is never a source gap' in source and 'B and C always receive the complete passage text' in source


def test_preview_keeps_start_and_end_of_passage():
    from wireless_assistant.a_token_budget import preview_passage
    text = '4.2.2 Physical channels and modulation ' + 'x' * 900 + ' 64QAM and 256QAM for DFT-s-OFDM with a CP.'
    item = preview_passage({'passage_id': 'p', 'text': text}, 800)
    assert item['text'].startswith('4.2.2 Physical channels') and item['text'].endswith('256QAM for DFT-s-OFDM with a CP.')
    assert ' […] ' in item['text'] and len(item['text']) == 800 and item['full_chars'] == len(text)
    short = preview_passage({'passage_id': 'p', 'text': 'short'}, 800)
    assert short['text'] == 'short' and 'preview_truncated' not in short


def test_source_worry_with_collected_passages_is_sent_to_b_not_the_user(client):
    from tests.runtime.conftest import collect, ready, draft
    def source_clarify(payload):
        v = clarify(payload)
        v['need']['unresolved_gaps'] = [{'gap_id': 'g', 'kind': 'source', 'requirement_ids': ['r1'],
                                         'reason': 'Preview lacks the list.', 'source_or_message_ids': []}]
        return v
    result = run(client, [('A', collect), ('A', source_clarify), ('A', ready), ('B', draft)],
                 text='TS 38.211 clause 4.4.4.1 explain karo. Exact citation do.')
    assert result['outcome']['kind'] == 'ACCEPTED', result
    calls = client.app_script.calls
    assert [r for r, _ in calls] == ['A', 'A', 'A', 'B', 'C']
    error = calls[2][1]['contract_error']
    assert 'You see previews only' in error and 'ready_for_b' in error and '4.4.4.1' in error

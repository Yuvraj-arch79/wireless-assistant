"""Version selection is enforced by code (versions.py), not left to the prompt."""
import json
import pytest
from .conftest import post, create_chat, wait_run, collect, ready, draft, review, need
from wireless_assistant import versions
from wireless_assistant.common import canonical


@pytest.mark.parametrize('text,expected', [
    ('TS 38.201 clause 4.2.3 ke hisaab se coding kya hai?', None),   # clause is not a version
    ('38.201 v17.0.0 mein PBCH coding?', {'version': '17.0.0'}),
    ('version 18.0.0 ke according', {'version': '18.0.0'}),
    ('Release 17 wala batao', {'release': '17'}),
    ('Rel-19 me kya badla?', {'release': '19'}),
    ('relevant passage do', None),
])
def test_requested_version_parsing(text, expected):
    assert versions.requested(text) == expected


def _ask(client, sid, text):
    rid = post(client, f'/api/sessions/{sid}/messages', {'text': text}).json()['data']['run_id']
    return rid, wait_run(client, rid)


def test_unindexed_version_is_reported_not_substituted(client):
    sid = create_chat(client)
    rid, status = _ask(client, sid, 'TS 38.211 v17.0.0 mein resource block kya hai?')
    assert status['outcome']['kind'] == 'VERSION_NOT_INDEXED', status
    assert client.app_script.calls == []  # no provider call, nothing to review
    notice = client.get(f'/api/sessions/{sid}/messages').json()['data']['items'][-1]
    assert notice['role'] == 'notice' and 'v17.0.0' in notice['content_text'] and 'v18.10.0' in notice['content_text']
    assert 'scope' not in notice['content_text'].lower()


def test_explicit_version_pins_search_and_is_shown(client):
    sid = create_chat(client)
    rid, status = _ask(client, sid, 'Explain a resource block per v18.10.0.')
    assert status['outcome']['kind'] == 'ACCEPTED', status
    assert status['outcome']['version_selection']['source'] == 'explicit'
    assert status['outcome']['version_selection']['versions'] == ['18.10.0']
    a_payloads = [p for r, p in client.app_script.calls if r == 'A']
    assert a_payloads[0]['version_selection']['versions'] == ['18.10.0']
    b_payload = next(p for r, p in client.app_script.calls if r == 'B')
    assert b_payload['need']['scope']['document_versions'] == ['18.10.0']


def test_default_then_same_chat_follow_up_then_fresh_chat(client):
    sid = create_chat(client)
    _, first = _ask(client, sid, 'Explain an NR resource block.')
    assert first['outcome']['version_selection']['source'] == 'default'
    _, second = _ask(client, sid, 'Aur easy bata.')
    assert second['outcome']['version_selection']['source'] == 'chat'
    other = create_chat(client)
    _, fresh = _ask(client, other, 'Aur easy bata.')
    assert fresh['outcome']['version_selection']['source'] == 'default'


def test_a_cannot_silently_switch_version(client):
    def wrong_version(payload):
        value = collect(payload)
        value['need']['scope']['document_versions'] = ['17.0.0']  # not what the user asked, not indexed
        value['requests'][0]['filters']['document_versions'] = []
        return value
    client.app_script.actions = [('A', wrong_version)]
    sid = create_chat(client)
    _, status = _ask(client, sid, 'Explain an NR resource block.')
    assert status['outcome']['kind'] == 'ACCEPTED', status
    assert status['outcome']['version_selection']['versions'] == ['18.10.0']


def test_chat_version_no_longer_indexed_is_not_mixed(client):
    sid = create_chat(client)
    _, first = _ask(client, sid, 'Explain an NR resource block.')
    store = client.app.state.store
    from wireless_assistant.store import insert
    from wireless_assistant.common import now, text_hash
    with store.transaction() as db:  # a newer index is activated after the first answer
        insert(db,'corpus_builds',build_id='new-build',fingerprint='new-fingerprint',manifest_json='{}',config_json=canonical({'retrieval':'lexical_preview'}),status='VALIDATED',created_at=now())
        insert(db,'source_documents',document_id='new-doc',build_id='new-build',spec_number='38.211',title='Synthetic newer fixture',release='18',version='18.11.0',source_uri='https://www.etsi.org/deliver/etsi_ts/fixture2.pdf',file_hash='fixture2',parser_config_hash='fixture')
        text='Synthetic fixture: an NR resource block contains twelve consecutive subcarriers.'
        insert(db,'passages',passage_id='new-passage',document_id='new-doc',build_id='new-build',clause_id='4.4.4.1',clause_title='Resource blocks',page_location='1',content_text=text,content_hash=text_hash(text),structure_json=canonical({'kind':'text','cross_references':[]}),unreadable=0)
        db.execute('INSERT INTO passage_fts VALUES (?,?,?,?)',('new-passage','new-build',text,'Resource blocks'))
        db.execute('UPDATE corpus_pointer SET build_id=? WHERE singleton=1',('new-build',))
    calls = len(client.app_script.calls)
    _, second = _ask(client, sid, 'Doosra wala samajh nahi aaya.')
    assert second['outcome']['kind'] == 'VERSION_NOT_INDEXED' and len(client.app_script.calls) == calls
    text = client.get(f'/api/sessions/{sid}/messages').json()['data']['items'][-1]['content_text']
    assert 'start a new chat' in text and 'v18.10.0' in text and 'v18.11.0' in text
    # The old answer's "View source" still opens the passage it was built on.
    eid = first['outcome']['evidence_set_id']
    source = client.get(f"/api/runs/{first['run_id']}/evidence/{eid}/fixture-passage").json()['data']
    assert source['document_version'] == '18.10.0'
    # A fresh chat uses the new default without mixing.
    _, fresh = _ask(client, create_chat(client), 'Explain an NR resource block.')
    assert fresh['outcome']['version_selection']['versions'] == ['18.11.0']


def test_same_chat_follow_up_sees_history_fresh_chat_does_not(client):
    sid = create_chat(client)
    _ask(client, sid, 'Explain an NR resource block.')
    start = len(client.app_script.calls)
    _ask(client, sid, 'Doosra wala samajh nahi aaya, aur easy bata.')
    same = client.app_script.calls[start][1]['original_context']
    assert any('resource block' in o['text'].lower() for o in same if o['role'] == 'user')
    assert any(o['role'] == 'assistant' for o in same)
    other = create_chat(client)
    start = len(client.app_script.calls)
    _ask(client, other, 'Doosra wala samajh nahi aaya, aur easy bata.')
    fresh = client.app_script.calls[start][1]['original_context']
    assert [o['text'] for o in fresh] == ['Doosra wala samajh nahi aaya, aur easy bata.']
    assert client.app_script.calls[start][1]['excluded_history_map'] == []


def test_activation_sample_check_failure_keeps_old_build(store):
    from wireless_assistant.corpus import Corpus
    from wireless_assistant.common import AppError
    corpus = Corpus(store)
    before = corpus.status()['active_build_id']
    with pytest.raises(AppError) as exc:
        corpus.verify_samples('fixture-build', [{'clause': '4.4.4.1', 'must_contain': ['LDPC']}])
    assert exc.value.code == 'ACTIVATION_CHECK_FAILED'
    assert corpus.status()['active_build_id'] == before
    assert corpus.verify_samples('fixture-build', [{'clause': '4.4.4.1', 'must_contain': ['twelve', 'SUBCARRIERS']}])[0]['ok']
    with pytest.raises(AppError):
        corpus.verify_samples('fixture-build', [])


def test_archive_inventory_is_honest():
    inv = versions.archive_inventory()
    indexed = [e for e in inv['entries'] if e['status'] == 'indexed']
    assert [e['version'] for e in indexed] == [inv['default_version']] == ['18.0.0']
    assert len(inv['entries']) == 15 and all(len(e['sha256']) == 64 for e in inv['entries'])
    assert 'Exactly one' in inv['coverage_statement']
    assert inv['activation_checks'][inv['default_version']]

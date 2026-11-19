"""Live run 44517462552 released 'paragraph 1-2 / paragraph 3' for a one-paragraph clause.
Locations are facts: the backend rejects any the evidence does not contain."""
import pytest
from .conftest import post, create_chat, wait_run, collect, ready, draft, review
from wireless_assistant.validation import unsourced_locations
from wireless_assistant.common import AppError

EVIDENCE = [{'clause_id': '4.2.3', 'page_location': '9', 'content_text': 'The channel coding scheme for transport blocks is quasi-cyclic LDPC codes. Further details are specified in [4]. See Table 4.1-1.'}]


@pytest.mark.parametrize('text', ['TS 38.201 clause 4.2.3', 'page 9', 'Table 4.1-1', 'clause 4.2.3 [1]'])
def test_locations_present_in_evidence_pass(text):
    unsourced_locations(text, EVIDENCE)


@pytest.mark.parametrize('text', ['clause 4.2.3, paragraph 1-2', 'para 3', 'page 12', 'clause 5.3.2', 'Table 7.2-1', 'equation 4'])
def test_invented_locations_are_rejected(text):
    with pytest.raises(AppError):
        unsourced_locations(text, EVIDENCE)


def test_draft_with_invented_paragraph_is_repaired_not_released(client):
    def invented(payload):
        value = draft(payload)
        value['answer_markdown'] = value['answer_markdown'].replace('subcarriers [1].', 'subcarriers [1] (paragraph 2).')
        return value
    client.app_script.actions = [('A', collect), ('A', ready), ('B', invented), ('B', draft), ('C', review)]
    sid = create_chat(client)
    rid = post(client, f'/api/sessions/{sid}/messages', {'text': 'Explain an NR resource block.'}).json()['data']['run_id']
    status = wait_run(client, rid)
    assert status['outcome']['kind'] == 'ACCEPTED'
    items = client.get(f'/api/sessions/{sid}/messages').json()['data']['items']
    released = [m['content_text'] for m in items if m['role'] == 'assistant']
    assert released and 'paragraph' not in released[0]


from wireless_assistant.validation import analogies_point_to_sources


def test_analogy_must_point_to_the_cited_fact_it_explains():
    analogies_point_to_sources('## Analogy (sirf samjhane ke liye, standard ka text nahi)\nBada parcel tukdon mein jaata hai, waise hi bada transport block code blocks mein bant jaata hai [1].')
    analogies_point_to_sources('LDPC transport blocks ke liye hai [1].\n\nReferences\n[1] TS 38.201 v18.0.0, clause 4.2.3.')
    with pytest.raises(AppError):
        analogies_point_to_sources('## Misaal (standard ka text nahi)\nPolar coding ek special frequency tuning jaisi hai.')

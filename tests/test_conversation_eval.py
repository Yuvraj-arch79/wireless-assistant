"""The live evaluator's own checks must catch the regressions it claims to catch."""
from evaluation.conversation_live import check, CASES

CASE = next(c for c in CASES if c['id'] == 'A_coding_compare')
CITED = [{'clause_id': '4.2.3', 'spec_number': '38.201'}]
DONE = {'status': 'COMPLETED'}
GOOD = ('Transport block ke liye LDPC coding use hoti hai [1], aur PBCH ke liye Polar coding hai [1]. '
        'Analogy (sirf samjhane ke liye): bade parcel aur chhoti chitthi jaise.\n\nReferences\n[1] TS 38.201 v18.0.0, clause 4.2.3.')


def test_good_hinglish_answer_passes():
    assert check(CASE, DONE, GOOD, CITED, {'kind': 'ACCEPTED'}) == (True, [])


def test_catches_english_devanagari_missing_citation_and_technical_failures():
    english = 'Transport blocks use LDPC [1] while PBCH uses Polar codes [1].\n\nReferences\n[1] TS 38.201 v18.0.0, clause 4.2.3.'
    assert not check(CASE, DONE, english, CITED, {'kind': 'ACCEPTED'})[0]
    assert not check(CASE, DONE, GOOD.replace('aur', 'और'), CITED, {'kind': 'ACCEPTED'})[0]
    assert not check(CASE, DONE, GOOD, [{'clause_id': '4.1.1', 'spec_number': '38.201'}], {'kind': 'ACCEPTED'})[0]
    assert not check(CASE, {'status': 'FAILED'}, '', [], {'kind': 'PROVIDER_TIMEOUT'})[0]


def test_out_of_scope_and_clarification_are_not_interchangeable():
    oos = next(c for c in CASES if c['id'] == 'D_wifi7_out_of_scope')
    fresh = next(c for c in CASES if c['id'] == 'B_fresh_chat_isolation')
    assert check(oos, DONE, '', [], {'kind': 'OUT_OF_SCOPE'})[0]
    assert not check(oos, {'status': 'FAILED'}, '', [], {'kind': 'PROVIDER_TIMEOUT'})[0]
    assert check(fresh, {'status': 'WAITING_USER'}, 'Kis topic ki baat?', [], {})[0]
    assert not check(fresh, DONE, 'invented answer', CITED, {'kind': 'ACCEPTED'})[0]


def test_held_out_cases_exist_for_each_kind():
    held = [c for c in CASES if c['split'] == 'held_out']
    assert {c['expect'] for c in held} >= {'answer', 'out_of_scope'}

"""One owner-requested Hinglish acceptance run through the production controller.

Uses the existing pinned full-PDF corpus; no hardcoded answer or runtime bypass.
Automatic source/review checks are separate from human language/analogy review.
"""
import json
import os
from . import one_pdf_live

QUESTION = ('TS 38.201 clause 4.2.3 ke according transport blocks aur PBCH ki coding '
            'simple Hinglish mein ek analogy ke saath samjhao. Exact citation do. '
            'Coding choose karne ka reason source mein nahi hai toh clearly batao.')


CASES = {
    'coding_hinglish': {'id': 'coding_hinglish', 'question': QUESTION, 'clause': '4.2.3', 'facts': ['ldpc', 'polar']},
    # A clear English question on another clause: reviewed answer, no clarification.
    'modulation_english': {'id': 'modulation_english', 'clause': '4.2.2', 'facts': ['qpsk'],
                           'question': 'According to TS 38.201 clause 4.2.2, which modulation schemes are supported '
                                       'in the downlink and in the uplink? Give the exact citation.'},
    # A Hinglish question on a different clause, without an analogy request.
    'modulation_hinglish': {'id': 'modulation_hinglish', 'clause': '4.2.2', 'facts': ['qpsk', '256qam'],
                            'question': 'TS 38.201 ke clause 4.2.2 mein downlink aur uplink ke liye kaunse modulation '
                                        'schemes diye gaye hain? Hinglish mein simple tarike se samjhao aur exact citation do.'},
    # No referent at all: A must ask one precise clarification, nothing is drafted or released.
    'ambiguous': {'id': 'ambiguous', 'expect': 'clarify', 'clause': None, 'facts': [],
                  'question': 'Iska size kitna hota hai aur yeh kab use hota hai?'},
    # Outside the declared 3GPP NR collection: clear scope refusal, no B/C draft.
    'out_of_scope': {'id': 'out_of_scope', 'expect': 'out_of_scope', 'clause': None, 'facts': [],
                     'question': 'Aaj Delhi ka mausam kaisa hai aur kal barish hogi kya?'},
}


def run():
    case = os.getenv('WA_ABC_CASE', 'coding_hinglish')
    if case not in CASES:
        raise SystemExit('Unknown WA_ABC_CASE')
    one_pdf_live.CASES = [CASES[case]]
    os.environ['WA_EVAL_CASES'] = case
    report = one_pdf_live.run()
    report['scope'] = 'One TS 38.201 question (' + case + '); real A, Gemini hybrid retrieval, B and C.'
    report['manual_review_required'] = 'Inspect the released answer for natural Hinglish, faithful analogy and explicit unsupported-rationale note.'
    # COMPLETED + accepted C review + correct source clause are checked by the
    # existing evaluator. Clarification, timeout and provider failures fail it,
    # except for the cases that expect a clarification or a scope refusal.
    print(json.dumps(report, indent=2, ensure_ascii=True), flush=True)
    return report


if __name__ == '__main__':
    result=run()
    raise SystemExit(0 if result['status']=='pass' else 1)

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


def run():
    one_pdf_live.CASES = [{'id':'coding_hinglish', 'question':QUESTION,
                           'clause':'4.2.3', 'facts':['ldpc','polar']}]
    os.environ['WA_EVAL_CASES'] = 'coding_hinglish'
    report = one_pdf_live.run()
    report['scope'] = 'One Hinglish TS 38.201 clause 4.2.3 question; real A, Gemini hybrid retrieval, B and C.'
    report['manual_review_required'] = 'Inspect the released answer for natural Hinglish, faithful analogy and explicit unsupported-rationale note.'
    # COMPLETED + accepted C review + correct source clause are checked by the
    # existing evaluator. Clarification, timeout and provider failures fail it.
    print(json.dumps(report, indent=2, ensure_ascii=True), flush=True)
    return report


if __name__ == '__main__':
    result=run()
    raise SystemExit(0 if result['status']=='pass' else 1)

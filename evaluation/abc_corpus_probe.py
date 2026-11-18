"""Offline, key-free probe of the pinned public corpus for clause 4.2.3.

Prints only public 3GPP passage metadata and short public excerpts so a failed
live run can be attributed to chunking, retrieval ranking or model behaviour.
No provider request is made (lexical search only).
"""
import json
from wireless_assistant.config import Settings, ROOT
from wireless_assistant.store import Store
from wireless_assistant.corpus import Corpus

QUERIES = [
    'TS 38.201 clause 4.2.3 channel coding transport blocks PBCH',
    'channel coding scheme transport blocks LDPC',
    'channel coding scheme PBCH control information Polar',
]


def meta(p):
    text = p.get('text', '')
    return {'passage_id': p['passage_id'], 'clause_id': p.get('clause_id'), 'page': p.get('page_location'),
            'chars': len(text), 'has_ldpc': 'ldpc' in text.lower(), 'has_polar': 'polar' in text.lower(),
            'has_pbch': 'pbch' in text.lower(), 'kind': p.get('structure', {}).get('kind'),
            'head': text[:90], 'tail': text[-90:]}


def run():
    settings = Settings(data_dir=ROOT / 'data/one-pdf')
    store = Store(settings)
    corpus = Corpus(store)
    build = corpus.status()['active_build_id']
    with store.read() as db:
        ids = [r[0] for r in db.execute(
            "SELECT passage_id FROM passages WHERE build_id=? AND clause_id IN ('4.2.2','4.2.3','4.2.4') ORDER BY rowid",
            (build,))]
    out = {'build': build, 'clause_passages': [meta(p) for p in corpus.get(build, ids[:24])], 'lexical': {}}
    filters = {'release': '18', 'spec_numbers': ['38.201'], 'document_versions': [], 'default_used': True}
    for q in QUERIES:
        out['lexical'][q] = [meta(p) | {'rank': i + 1} for i, p in enumerate(corpus.search(build, q, filters, 6))]
    print(json.dumps(out, indent=2, ensure_ascii=True))


if __name__ == '__main__':
    run()

"""Validate evaluation data; never call a provider or claim answer quality."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate(raw_dir=None):
    manifest_path = ROOT / 'corpus/manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    suite = json.loads((ROOT / 'evaluation/cases.json').read_text(encoding='utf-8'))
    docs = {d['spec']: d for d in manifest['documents']}
    require(suite['schema_version'] == 1, 'Unsupported schema')
    require(suite['suite_version'] == '0.1.0', 'Review validator for new suite version')
    require(suite['manifest_sha256'] == hashlib.sha256(manifest_path.read_bytes()).hexdigest(), 'Manifest changed; review source labels')
    require(suite['corpus_id'] == manifest['corpus_id'], 'Wrong corpus')
    cases = suite['cases']
    require(len(cases) == 32, 'Version 0.1.0 has 32 cases')
    require(len({c['id'] for c in cases}) == len(cases), 'Duplicate IDs')
    require(len({c['prompt'] for c in cases if c['kind']=='technical'}) == 16, 'Duplicate technical questions')
    srs = (ROOT / 'docs/requirements/wireless-assistant-srs.md').read_text(encoding='utf-8')
    requirements = set(re.findall(r'^### ([A-Z]{2,3}-\d{2}) -', srs, re.M))
    require({k: sum(c['kind'] == k for c in cases) for k in ('technical', 'behavior', 'reviewer')} == {'technical': 16, 'behavior': 12, 'reviewer': 4}, 'Wrong case inventory')
    require(sum(c['split'] == 'dev' for c in cases) == 18, 'Wrong split inventory')
    families, evidence_splits, covered, pages, checked = {}, {}, set(), {}, set()
    for c in cases:
        require(c['kind'] in ('technical','behavior','reviewer'), 'Unknown kind')
        require(c['split'] in ('dev','locked'), 'Unknown split')
        require(c['prompt'].strip() and c['expected'] and c['forbidden'], 'Incomplete grading contract: '+c['id'])
        require(bool(c['requirements']) and set(c['requirements']) <= requirements, 'Missing/unknown SRS ID')
        require(all(isinstance(point, str) and point.strip() for point in c['expected'] + c['forbidden']), 'Empty criterion')
        require(c['weight'] == 1 and isinstance(c['history'],list), 'Invalid weight/history')
        if c['kind'] in ('technical','reviewer'):
            require(bool(c['sources']), 'Missing technical source')
        if c['kind']=='reviewer':
            require(bool(c['fixture']['candidate_text']) and bool(c['fixture']['original_query']), 'Missing reviewer candidate/task')
        require(c['family'] not in families or families[c['family']]==c['split'], 'Family crosses splits')
        families[c['family']] = c['split']
        for ref in c['sources']:
            d = docs[ref['spec']]; covered.add(ref['spec'])
            require(all(ref[k]==d[k] for k in ('version','sha256','url')), 'Source identity mismatch')
            require(ref['release']==18 and 1 <= ref['pdf_page'] <= d['page_count'], 'Invalid page/release')
            require(ref['anchor'] and re.fullmatch(r'\d+(?:\.\d+)*',ref['clause']), 'Invalid source locator')
            key=(ref['spec'],ref['clause'])
            require(key not in evidence_splits or evidence_splits[key]==c['split'], 'Source clause crosses splits')
            evidence_splits[key]=c['split']
            if raw_dir is not None:
                path=raw_dir/d['filename']
                if ref['spec'] not in checked:
                    require(path.stat().st_size==d['size_bytes'], 'Source size mismatch')
                    require(hashlib.sha256(path.read_bytes()).hexdigest()==d['sha256'], 'Source bytes changed')
                    checked.add(ref['spec'])
                page_key=(ref['spec'],ref['pdf_page'])
                if page_key not in pages:
                    result=subprocess.run(['pdftotext','-f',str(ref['pdf_page']),'-l',str(ref['pdf_page']),'-layout',str(path),'-'],capture_output=True,check=True,timeout=30)
                    pages[page_key]=result.stdout.decode('utf-8')
                page=pages[page_key]
                normalized=' '.join(page.split()).casefold()
                require(' '.join(ref['anchor'].split()).casefold() in normalized, 'Source anchor missing: '+c['id'])
                require(re.search(r'^'+re.escape(ref['clause'])+r'\s',page,re.M), 'Clause missing on cited page: '+c['id'])
    require(covered==set(docs), 'Not all 12 sources covered')
    print(f'PASS: {len(cases)} cases; 12 specifications; family/clause splits, source pins and SRS IDs valid.')
    if raw_dir is not None:
        print(f'PASS: {len(checked)} PDF hashes and {len(pages)} cited pages/anchors verified. This is not domain sign-off or model accuracy.')
    else:
        print('PDF bytes/page anchors NOT checked; use --raw-dir with verified sources and pdftotext.')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw-dir',type=Path)
    args=parser.parse_args()
    validate(args.raw_dir)

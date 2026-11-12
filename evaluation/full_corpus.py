"""Bounded real-corpus preparation and checks; never substitutes demo evidence."""
import argparse
import json
import time
from pathlib import Path
from wireless_assistant.common import AppError
from wireless_assistant.config import Settings, ROOT
from wireless_assistant.corpus import Corpus
from wireless_assistant.store import Store


def inspect(store, build):
    corpus=Corpus(store)
    manifest=json.loads((ROOT/'corpus/manifest.json').read_text(encoding='utf-8'))
    with store.read() as db:
        docs=[dict(r) for r in db.execute('SELECT d.spec_number,count(p.passage_id) AS passages,sum(p.unreadable) AS excluded FROM source_documents d JOIN passages p ON p.document_id=d.document_id WHERE d.build_id=? GROUP BY d.spec_number',(build,))]
        assert {d['spec_number'] for d in docs}=={d['spec'] for d in manifest['documents']}
        assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert not db.execute('PRAGMA foreign_key_check').fetchall()
    cases=json.loads((ROOT/'evaluation/cases.json').read_text(encoding='utf-8'))['cases']
    results=[]
    for case in cases:
        if case['kind']!='technical' or case['split']!='dev':continue
        sources=case['sources'];found=corpus.search(build,case['prompt'],{'release':'18'},12)
        hits=[s for s in sources if any(p['spec_number']==s['spec'] and p['clause_id']==s['clause'] for p in found)]
        results.append({'case':case['id'],'all_expected_clauses_in_top12':len(hits)==len(sources), 'retrieved':[{k:p[k] for k in ('spec_number','clause_id','page_location')} for p in found]})
    return {'documents':docs,'document_count':len(docs),'passages':sum(d['passages'] for d in docs),'excluded':sum(d['excluded'] for d in docs),
            'database_integrity':'pass','retrieval_mode':'lexical only; semantic ranking not tested here','dev_retrieval':results,
            'scope':'Structural/extraction and development retrieval diagnostics; not answer quality or full-domain acceptance.'}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--raw-dir',type=Path);parser.add_argument('--live',action='store_true');args=parser.parse_args()
    folder=ROOT/'data/full-validation';folder.mkdir(parents=True,exist_ok=True)
    store=Store(Settings(data_dir=folder,provider_profile='groq_openrouter'));corpus=Corpus(store)
    report={'status':'not_completed','embedding_batches_completed':0,'retries':0}
    try:
        manifest=json.loads((ROOT/'corpus/manifest.json').read_text(encoding='utf-8'))
        raw=args.raw_dir or ROOT/'data/corpus'/manifest['corpus_id']/'raw'
        build=corpus.ingest(ROOT/'corpus/manifest.json',raw)
        report['lexical_build']=build;report['checks']=inspect(store,build)
        if args.live:
            deadline=time.monotonic()+600
            for _ in range(500):
                if time.monotonic()>=deadline:raise AppError('PREPARATION_DEADLINE','Preparation budget reached; saved vectors remain resumable.')
                result=corpus.embed_build(build,max_batches=1,seconds=min(30,deadline-time.monotonic()))
                report['hybrid_build']=result['build_id'];report['embedding_batches_completed']+=result['batches']
                if result['complete']:
                    corpus.activate(result['build_id'])
                    report['hybrid_ready']=corpus.status()['ready']
                    break
                time.sleep(1)
            else:raise AppError('PREPARATION_CALL_LIMIT','Preparation call budget reached.')
            if not report.get('hybrid_ready'):raise AppError('PREPARATION_INCOMPLETE','Full hybrid index is not ready.')
        report['status']='pass' if not args.live or report.get('hybrid_ready') else 'not_completed'
    except AppError as error:report.update(status=error.code,message=error.message)
    finally:
        (folder/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps(report,indent=2))
    return 0 if report['status']=='pass' else 1

if __name__=='__main__':raise SystemExit(main())

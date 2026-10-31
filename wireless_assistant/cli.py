"""Explicit developer commands; corpus acquisition never happens during a question."""
import argparse
import json
import os
from pathlib import Path
import sys
from .common import AppError, canonical
from .config import Settings, ROOT
from .store import Store
from .corpus import Corpus


def main(argv=None):
    parser=argparse.ArgumentParser(description='Wireless Assistant development prototype')
    parser.add_argument('--data-dir',type=Path)
    sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('serve')
    sub.add_parser('status')
    sub.add_parser('builds')
    p=sub.add_parser('ingest')
    p.add_argument('--manifest',type=Path,default=ROOT/'corpus/manifest.json')
    p.add_argument('--raw-dir',type=Path)
    p=sub.add_parser('embed')
    p.add_argument('source_build')
    p.add_argument('--max-batches',type=int,choices=range(1,21),default=20)
    p=sub.add_parser('activate');p.add_argument('build_id')
    p=sub.add_parser('search');p.add_argument('query');p.add_argument('--build')
    p=sub.add_parser('backup');p.add_argument('destination',type=Path)
    args=parser.parse_args(argv)
    settings=Settings.environment()
    if args.data_dir:
        settings=settings.model_copy(update={'data_dir':args.data_dir.absolute()})
    lock=None
    try:
        if args.command=='serve':
            from .app import create_app
            import uvicorn
            uvicorn.run(create_app(settings),host='127.0.0.1',port=settings.port,workers=1,access_log=False,timeout_graceful_shutdown=5)
            return 0
        from .app import ProcessLock
        settings.data_dir.mkdir(parents=True,exist_ok=True)
        if args.command in ('ingest','embed','activate','backup'):
            lock=ProcessLock(settings.data_dir/'server.lock')
        store=Store(settings);corpus=Corpus(store)
        if args.command=='status':
            result=corpus.status()
        elif args.command=='builds':
            with store.read() as db:
                result=[dict(r) for r in db.execute('SELECT build_id,status,config_json,created_at FROM corpus_builds ORDER BY created_at')]
        elif args.command=='ingest':
            manifest=json.loads(args.manifest.read_text(encoding='utf-8'))
            raw=args.raw_dir or ROOT/'data/corpus'/manifest['corpus_id']/'raw'
            result={'build_id':corpus.ingest(args.manifest,raw),'mode':'lexical_preview','next':'Inspect extracted evidence, then embed and activate the hybrid build.'}
        elif args.command=='embed':
            result=corpus.embed_build(args.source_build,args.max_batches)
        elif args.command=='activate':
            corpus.activate(args.build_id);result=corpus.status()
        elif args.command=='search':
            build=args.build or corpus.status()['active_build_id']
            if not build:
                raise AppError('NO_BUILD','Supply --build or activate a collection.')
            result={'mode':'lexical_preview','passages':corpus.search(build,args.query,{'release':'18'},6)}
        elif args.command=='backup':
            store.backup(args.destination);result={'backup':str(args.destination),'verified':True}
        print(json.dumps(result,ensure_ascii=True,indent=2))
        return 0
    except (AppError,OSError,ValueError) as exc:
        # CLI is developer-only; provider errors are already sanitized.
        print('ERROR: '+str(exc),file=sys.stderr)
        return 1
    finally:
        if lock:
            lock.close()


if __name__=='__main__':
    raise SystemExit(main())

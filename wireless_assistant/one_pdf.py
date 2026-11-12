"""Explicit, isolated whole-TS-38.201 preparation; original inventory is unchanged."""
import json
import time
from pathlib import Path
from .common import AppError
from .config import ROOT, Settings
from .corpus import Corpus
from .store import Store


def selected_manifest():
    from scripts.corpus import load_manifest
    original, source_hash = load_manifest(ROOT / 'corpus/manifest.json')
    docs = [d for d in original['documents'] if d['spec'] == '38.201']
    if len(docs) != 1:
        raise AppError('SOURCE_SELECTION', 'Pinned TS 38.201 must exist exactly once.')
    return {**original, 'corpus_id': 'nr-38201-rel18', 'documents': docs,
            'selection_source_manifest_sha256': source_hash}


def prepare(data_dir=None, raw_dir=None, live=True):
    from scripts.corpus import fetch_one, CorpusError
    from .app import ProcessLock
    folder = Path(data_dir or ROOT / 'data/one-pdf').absolute()
    folder.mkdir(parents=True, exist_ok=True)
    report = {'status': 'not_completed', 'scope': 'Complete TS 38.201 v18.0.0 PDF; extracted readable text only',
              'embedding_batches': 0, 'retries': 0}
    lock = ProcessLock(folder / 'server.lock')
    try:
        manifest = selected_manifest()
        source = folder / 'manifest.json'
        source.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
        raw = Path(raw_dir or folder / 'raw');raw.mkdir(parents=True, exist_ok=True)
        doc = manifest['documents'][0]
        fetch_one(doc, raw / doc['filename'], time.monotonic() + 125)
        store = Store(Settings(data_dir=folder, provider_profile='groq_openrouter'))
        corpus = Corpus(store)
        lexical = corpus.ingest(source, raw)
        report['lexical_build'] = lexical
        with store.read() as db:
            report['inventory'] = [dict(r) for r in db.execute('SELECT clause_id,count(*) AS passages,sum(unreadable) AS excluded FROM passages WHERE build_id=? GROUP BY clause_id', (lexical,))]
            report['passages'] = db.execute('SELECT count(*) FROM passages WHERE build_id=?', (lexical,)).fetchone()[0]
            report['eligible'] = db.execute('SELECT count(*) FROM passages WHERE build_id=? AND unreadable=0', (lexical,)).fetchone()[0]
            if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok' or db.execute('PRAGMA foreign_key_check').fetchall():
                raise AppError('DATABASE_INTEGRITY', 'Corpus database integrity failed.')
        if live:
            # At most four batches, paced; subsequent invocation resumes saved vectors.
            for _ in range(5):
                result = corpus.embed_build(lexical, max_batches=1, seconds=30)
                report['hybrid_build'] = result['build_id']
                report['embedding_batches'] += result['batches']
                if result['complete']:
                    corpus.activate(result['build_id'])
                    break
                if report['embedding_batches'] >= 4:
                    raise AppError('PREPARATION_LIMIT', 'Four-batch limit reached; saved vectors can be resumed.')
                time.sleep(5)
            report['ready'] = corpus.status()['ready']
            if not report['ready']:
                raise AppError('PREPARATION_INCOMPLETE', 'Complete compatible embeddings are required.')
        report['status'] = 'pass' if live else 'extraction_only'
    except (AppError, CorpusError) as exc:
        report.update(status=getattr(exc, 'code', 'CORPUS_ERROR'), message=str(exc))
        raise AppError(report['status'], report['message']) from None
    finally:
        (folder / 'preparation.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        lock.close()
    return report

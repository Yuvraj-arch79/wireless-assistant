"""Developer-only ingestion and version-bound exact/semantic retrieval."""
import hashlib
from importlib.metadata import version
import json
import math
from pathlib import Path
import re
import time
from .bounded import bounded
from .common import AppError, canonical, digest, now, token_bound, uid
from .provider import request, vector
from .store import insert, row

PARSER = 'pdfplumber-clause-v2'
CHUNK_CHARS = 1800
MAX_BUILD_PASSAGES = 20000


def parse_pdf(path):
    import pdfplumber
    passages, warnings = [], []
    clause, title = 'front-matter', 'Front matter'
    with pdfplumber.open(path) as pdf:
        if len(pdf.pages) > 2000:
            raise AppError('PAGE_LIMIT', 'Document exceeds the page limit.')
        for page_number, page in enumerate(pdf.pages, 1):
            text = page.extract_text(x_tolerance=2, y_tolerance=3) or ''
            if len(text) > 100000:
                raise AppError('PAGE_LIMIT', 'Extracted page exceeds the text limit.')
            if not text.strip():
                warnings.append({'page':page_number,'reason':'No extractable text; OCR is not implemented.'})
                page.close()
                continue
            lines, buffer = text.splitlines(), []
            page_start_clause, page_start_title = clause, title
            text_lines = page.extract_text_lines(x_tolerance=2, y_tolerance=3)
            heading_positions = []
            heading_numbers = set()
            for line_info in text_lines:
                m = re.match(r'^(\d+(?:\.\d+){0,7})\s+([A-Za-z][^\n]{2,150})$', line_info['text'])
                if m and not re.search(r'\.{3,}', line_info['text']) and max((c.get('size',0) for c in line_info['chars']), default=0) >= 11:
                    heading_numbers.add(m.group(1))
                    heading_positions.append((line_info['top'], m.group(1), m.group(2)))
            def flush():
                nonlocal buffer
                if buffer:
                    content = '\n'.join(buffer).strip()
                    bad = '\ufffd' in content or '(cid:' in content or clause == 'front-matter'
                    kind = 'heading' if content == clause + ' ' + title else 'text'
                    passages.append({'clause_id':clause, 'clause_title':title, 'page_location':str(page_number),
                                     'text':content, 'unreadable':bad,
                                     'structure':{'kind':kind,'formula_review_required':bool(re.search(r'[=∑∫√]',content)), 'cross_references':crossrefs(content)}})
                    buffer = []
            for line in lines:
                if re.match(r'^(ETSI|3GPP TS|ETSI TS)\b', line) or re.fullmatch(r'\d+',line.strip()):
                    continue
                match = re.match(r'^(\d+(?:\.\d+){0,7})\s+([A-Za-z][^\n]{2,150})$',line)
                if match and match.group(1) in heading_numbers and not re.search(r'\.{3,}',line):
                    flush()
                    clause, title = match.groups()
                if sum(len(x)+1 for x in buffer) + len(line) > CHUNK_CHARS:
                    flush()
                # Very long lines remain represented; no silent deletion.
                if len(line) > CHUNK_CHARS:
                    for start in range(0,len(line),CHUNK_CHARS):
                        buffer = [line[start:start+CHUNK_CHARS]]
                        flush()
                else:
                    buffer.append(line)
            flush()
            if page.lines or page.rects:
                for table in page.find_tables():
                    rows = [[cell or '' for cell in cells] for cells in table.extract()]
                    table_clause, table_title = page_start_clause, page_start_title
                    for y, hc, ht in heading_positions:
                        if y < table.bbox[1]:
                            table_clause, table_title = hc, ht
                    captions = [line['text'] for line in text_lines if line['top'] < table.bbox[1] and line['text'].startswith('Table ')]
                    caption = captions[-1] if captions else ''
                    if len(rows) < 2 or max(map(len,rows),default=0) < 2:
                        continue
                    table_text = (caption + '\n' if caption else '') + '\n'.join(' | '.join(cells) for cells in rows)
                    if token_bound(table_text) > 12000:
                        warnings.append({'page':page_number,'reason':'Oversized table retained in PDF; excluded from answer evidence.'})
                        continue
                    passages.append({'clause_id':table_clause, 'clause_title':table_title, 'page_location':str(page_number),
                                     'text':table_text,'unreadable':'\ufffd' in table_text or '(cid:' in table_text or table_clause == 'front-matter' or not caption,
                                     'structure':{'kind':'table','caption':caption,'rows':rows,'formula_review_required':bool(re.search(r'[=∑∫√]',table_text)), 'cross_references':crossrefs(table_text)}})
            page.close()
    return {'passages':passages,'warnings':warnings}


def crossrefs(text):
    return [{'spec':m.group(1),'clause':m.group(2)} for m in re.finditer(r'(?:TS\s+)?(38\.\d{3})(?:[^\n]{0,30}?clause\s+(\d+(?:\.\d+)*))?',text)][:20]


def passage(raw):
    p = dict(raw)
    p['text'] = p.pop('content_text')
    p['structure'] = json.loads(p.pop('structure_json'))
    p['unreadable'] = bool(p['unreadable'])
    return p


JOIN = '''SELECT p.*, d.spec_number, d.version AS document_version, d.release, d.source_uri
FROM passages p JOIN source_documents d ON d.document_id=p.document_id'''


class Corpus:
    def __init__(self, store):
        self.store, self.settings = store, store.settings

    def status(self):
        with self.store.read() as db:
            pointer = row(db,'SELECT build_id FROM corpus_pointer WHERE singleton=1')
            if not pointer:
                return {'active_build_id':None,'ready':False,'documents':[], 'coverage_gaps':['No corpus build is active. Run developer ingestion.']}
            build = row(db,'SELECT * FROM corpus_builds WHERE build_id=?',(pointer['build_id'],))
            config = json.loads(build['config_json'])
            docs = [dict(d) for d in db.execute('SELECT spec_number,title,version,release,source_uri FROM source_documents WHERE build_id=? ORDER BY spec_number',(build['build_id'],))]
            ready = self.ready(build['build_id'])
            return {'active_build_id':build['build_id'],'ready':ready,'documents':docs,
                    'coverage_gaps':['Release 18 selected PHY/Layer-2 documents only; external referenced standards are unavailable.',
                                     'Formula/diagram interpretation needs source inspection; extraction is not a certified transcription.'] + ([] if ready else ['Lexical preview only: prepare embeddings before AI chat.'])}

    def get(self, build, ids):
        if len(ids)>24:
            raise AppError('PASSAGE_LIMIT','Too many passage IDs.')
        with self.store.read() as db:
            result=[]
            for pid in ids:
                p=row(db,JOIN+' WHERE p.build_id=? AND p.passage_id=?',(build,pid))
                if not p:
                    raise AppError('SOURCE_MISSING','A source passage is unavailable.',503)
                result.append(passage(p))
            return result

    def ready(self, build):
        with self.store.read() as db:
            b=row(db,'SELECT * FROM corpus_builds WHERE build_id=?',(build,))
            if not b or b['status']!='VALIDATED':
                return False
            c=json.loads(b['config_json'])
            compatible=c.get('retrieval')=='hybrid' and c.get('embedding_model')==self.settings.embedding_model and c.get('dimensions')==self.settings.embedding_dimensions
            missing=db.execute('SELECT count(*) FROM passages p LEFT JOIN passage_vectors v ON v.passage_id=p.passage_id WHERE p.build_id=? AND p.unreadable=0 AND (v.passage_id IS NULL OR v.model!=? OR v.dimensions!=?)',(build,self.settings.embedding_model,self.settings.embedding_dimensions)).fetchone()[0]
            count=db.execute('SELECT count(*) FROM passages WHERE build_id=? AND unreadable=0',(build,)).fetchone()[0]
            return compatible and count>0 and missing==0

    def search(self, build, query, filters, limit=6, query_vector=None):
        words=re.findall(r'[\w]+',query,flags=re.UNICODE)[:32]
        if not words:
            return []
        match=' OR '.join('"'+w.replace('"','""')+'"' for w in words)
        with self.store.read() as db:
            # Parameterized FTS and version filters; no model SQL interpretation.
            where="p.build_id=? AND p.unreadable=0 AND json_extract(p.structure_json,'$.kind')!='heading'"
            args=[build]
            if filters.get('release'):
                where+=' AND d.release=?';args.append(filters['release'])
            for key,column in [('spec_numbers','d.spec_number'),('document_versions','d.version')]:
                values=filters.get(key,[])
                if values:
                    where+=' AND '+column+' IN ('+','.join('?' for _ in values)+')';args.extend(values)
            lexical=db.execute('SELECT p.passage_id FROM passage_fts f JOIN passages p ON p.passage_id=f.passage_id JOIN source_documents d ON d.document_id=p.document_id WHERE passage_fts MATCH ? AND '+where+' ORDER BY bm25(passage_fts) LIMIT 60',[match,*args]).fetchall()
            scores={r[0]:1/(60+i) for i,r in enumerate(lexical,1)}
            if query_vector is not None:
                query_vector=vector(query_vector,self.settings.embedding_dimensions)
                ranked=[]
                for r in db.execute('SELECT p.passage_id,v.vector_json,v.dimensions,v.model FROM passages p JOIN source_documents d ON d.document_id=p.document_id JOIN passage_vectors v ON v.passage_id=p.passage_id WHERE '+where,args):
                    if r['dimensions']!=len(query_vector) or r['model']!=self.settings.embedding_model:
                        raise AppError('EMBEDDING_MISMATCH','The index embedding configuration is incompatible.',503)
                    v=vector(json.loads(r['vector_json']),self.settings.embedding_dimensions)
                    score=sum(a*b for a,b in zip(query_vector,v,strict=True))
                    ranked.append((score,r['passage_id']))
                ranked.sort(reverse=True)
                for i,(_,pid) in enumerate(ranked[:60],1):
                    scores[pid]=scores.get(pid,0)+1/(60+i)
            ids=sorted(scores,key=lambda p:(-scores[p],p))[:limit]
        return self.get(build,ids)

    def expand(self, build, ids, relation, limit):
        current=self.get(build,ids)
        result=[]
        with self.store.read() as db:
            for p in current:
                if relation in ('parent','previous','next'):
                    value=p.get(relation+'_id')
                    if value and value not in result:
                        result.append(value)
                else:
                    for ref in p['structure'].get('cross_references',[]):
                        if not ref['clause']:
                            continue
                        for r in db.execute('SELECT p.passage_id FROM passages p JOIN source_documents d ON d.document_id=p.document_id WHERE p.build_id=? AND d.spec_number=? AND p.clause_id=? LIMIT 6',(build,ref['spec'],ref['clause'])):
                            if r[0] not in result:
                                result.append(r[0])
        return self.get(build,result[:limit])

    def ingest(self, manifest_path, raw_dir, seconds=600):
        from scripts.corpus import load_manifest, check_file
        manifest, manifest_hash=load_manifest(Path(manifest_path))
        raw_dir=Path(raw_dir)
        config={'parser':PARSER,'pdfplumber':version('pdfplumber'),'chunk_chars':CHUNK_CHARS,'retrieval':'lexical_preview',
                'embedding_model':self.settings.embedding_model,'dimensions':self.settings.embedding_dimensions}
        fingerprint=digest({'manifest':manifest_hash,'config':config})
        with self.store.read() as db:
            old=row(db,'SELECT * FROM corpus_builds WHERE fingerprint=?',(fingerprint,))
        # Verify originals even when reusing a build.
        for doc in manifest['documents']:
            check_file(raw_dir/doc['filename'],doc)
        if old and old['status']=='VALIDATED':
            return old['build_id']
        if old:
            raise AppError('BUILD_EXISTS','An incomplete build with this fingerprint exists. Inspect it before rebuilding.')
        build=uid();deadline=time.monotonic()+seconds
        with self.store.transaction() as db:
            insert(db,'corpus_builds',build_id=build,fingerprint=fingerprint,manifest_json=canonical(manifest),config_json=canonical(config),status='STAGING',created_at=now())
        report={'manifest_sha256':manifest_hash,'documents':[],'passages':0,'unreadable':0,'warnings':[]}
        try:
            for doc in manifest['documents']:
                remaining=deadline-time.monotonic()
                if remaining<=0:
                    raise AppError('INGESTION_TIMEOUT','Ingestion deadline exceeded.',504)
                result=bounded(parse_pdf,(str(raw_dir/doc['filename']),),min(120,remaining))
                pieces=result['passages']
                if not pieces or report['passages']+len(pieces)>MAX_BUILD_PASSAGES:
                    raise AppError('INGESTION_LIMIT','No passages or too many passages in build.')
                did=uid();ids=[uid() for _ in pieces];clause_first={}
                with self.store.transaction() as db:
                    insert(db,'source_documents',document_id=did,build_id=build,spec_number=doc['spec'],title=doc['title'],release=str(manifest['release']),version=doc['version'],source_uri=doc['url'],file_hash=doc['sha256'],parser_config_hash=digest(config))
                    for i,p in enumerate(pieces):
                        parent=clause_first.get(p['clause_id'])
                        clause_first.setdefault(p['clause_id'],ids[i])
                        insert(db,'passages',passage_id=ids[i],document_id=did,build_id=build,clause_id=p['clause_id'],clause_title=p['clause_title'],page_location=p['page_location'],content_text=p['text'],content_hash=text_hash_local(p['text']),structure_json=canonical(p['structure']),parent_id=parent,previous_id=ids[i-1] if i else None,next_id=ids[i+1] if i+1<len(ids) else None,unreadable=int(p['unreadable']))
                        db.execute('INSERT INTO passage_fts VALUES (?,?,?,?)',(ids[i],build,p['text'],p['clause_title']))
                report['passages']+=len(pieces);report['unreadable']+=sum(p['unreadable'] for p in pieces)
                report['documents'].append({'spec':doc['spec'],'passages':len(pieces)})
                report['warnings'].extend({'spec':doc['spec'],**w} for w in result['warnings'])
                print(f"Parsed {doc['spec']}: {len(pieces)} passages",flush=True)
            with self.store.transaction() as db:
                insert(db,'build_reports',build_id=build,report_json=canonical(report))
                db.execute("UPDATE corpus_builds SET status='VALIDATED',validated_at=? WHERE build_id=?",(now(),build))
            return build
        except BaseException:
            with self.store.transaction() as db:
                db.execute("UPDATE corpus_builds SET status='FAILED' WHERE build_id=?",(build,))
            raise

    def embed_build(self, source_build, max_batches=20, seconds=600):
        # An explicit invocation is bounded; a later invocation resumes saved batches.
        with self.store.transaction() as db:
            source=row(db,"SELECT * FROM corpus_builds WHERE build_id=? AND status='VALIDATED'",(source_build,))
            if not source:
                raise AppError('BUILD_NOT_FOUND','Select a validated lexical build.')
            config=json.loads(source['config_json']);config['retrieval']='hybrid'
            fingerprint=digest({'source':source['fingerprint'],'config':config})
            existing=row(db,'SELECT * FROM corpus_builds WHERE fingerprint=?',(fingerprint,))
            if existing:
                build=existing['build_id']
                if existing['status']=='VALIDATED':
                    return {'build_id':build,'complete':True,'batches':0}
            else:
                build=uid()
                insert(db,'corpus_builds',build_id=build,fingerprint=fingerprint,manifest_json=source['manifest_json'],config_json=canonical(config),status='STAGING',created_at=now())
                docs=db.execute('SELECT * FROM source_documents WHERE build_id=?',(source_build,)).fetchall()
                id_map={r['passage_id']:uid() for r in db.execute('SELECT passage_id FROM passages WHERE build_id=?',(source_build,))}
                for raw in docs:
                    d=dict(raw);old_id=d['document_id'];d.update(document_id=uid(),build_id=build);insert(db,'source_documents',**d)
                    for raw_p in db.execute('SELECT * FROM passages WHERE document_id=?',(old_id,)).fetchall():
                        p=dict(raw_p);p.update(passage_id=id_map[p['passage_id']],document_id=d['document_id'],build_id=build)
                        for k in ('parent_id','previous_id','next_id'):
                            p[k]=id_map.get(p[k])
                        insert(db,'passages',**p)
                        db.execute('INSERT INTO passage_fts VALUES (?,?,?,?)',(p['passage_id'],build,p['content_text'],p['clause_title']))
        deadline=time.monotonic()+seconds;batches=0
        for _ in range(max_batches):
            with self.store.read() as db:
                missing=[dict(r) for r in db.execute('SELECT p.passage_id,p.content_text FROM passages p LEFT JOIN passage_vectors v ON v.passage_id=p.passage_id WHERE p.build_id=? AND p.unreadable=0 AND v.passage_id IS NULL ORDER BY p.passage_id LIMIT 16',(build,))]
            if not missing:
                with self.store.transaction() as db:
                    db.execute("UPDATE corpus_builds SET status='VALIDATED',validated_at=? WHERE build_id=?",(now(),build))
                return {'build_id':build,'complete':True,'batches':batches}
            if deadline-time.monotonic()<=0:
                break
            vectors=bounded(embed_batch,(self.settings.embedding_model,[p['content_text'] for p in missing],self.settings.embedding_dimensions),min(25,deadline-time.monotonic()))
            with self.store.transaction() as db:
                for p,v in zip(missing,vectors,strict=True):
                    insert(db,'passage_vectors',passage_id=p['passage_id'],model=self.settings.embedding_model,dimensions=self.settings.embedding_dimensions,vector_json=canonical(v))
            batches+=1
        return {'build_id':build,'complete':False,'batches':batches,'next':'Run embed again with the same lexical source build to resume.'}

    def activate(self, build):
        with self.store.transaction() as db:
            b=row(db,"SELECT * FROM corpus_builds WHERE build_id=? AND status='VALIDATED'",(build,))
            if not b:
                raise AppError('BUILD_NOT_READY','Only a validated build can be activated.')
            if json.loads(b['config_json']).get('retrieval')=='hybrid' and not self.ready(build):
                raise AppError('BUILD_NOT_READY','Hybrid vectors are missing or incompatible; activation was not changed.')
            # Immutable old builds are retained for existing runs and citations.
            db.execute('INSERT INTO corpus_pointer VALUES (1,?,?) ON CONFLICT(singleton) DO UPDATE SET build_id=excluded.build_id,activated_at=excluded.activated_at',(build,now()))


def text_hash_local(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def embed_batch(model, texts, dimensions):
    response=request(model,'batchEmbedContents',{'requests':[{'model':'models/'+model,'content':{'parts':[{'text':t}]},'taskType':'RETRIEVAL_DOCUMENT','outputDimensionality':dimensions} for t in texts]})
    embeddings=response.get('embeddings',[])
    if len(embeddings)!=len(texts):
        raise AppError('EMBEDDING_SHAPE','Embedding batch count does not match inputs.',502)
    return [vector(e.get('values'),dimensions) for e in embeddings]


def search_worker(db_path, config, build, query, filters, limit, query_vector):
    from .config import Settings
    from .store import Store
    settings=Settings(data_dir=Path(db_path).parent,**{k:v for k,v in config.items() if k in Settings.model_fields and k!='data_dir'})
    return Corpus(Store(settings)).search(build,query,filters,limit,query_vector)

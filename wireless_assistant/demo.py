"""Explicit single-excerpt demo; isolated from the full hybrid corpus."""
from .common import AppError, canonical, digest, now, text_hash
from .store import insert

BUILD = 'nr-series-demo-v1'
DOCUMENT = 'nr-series-demo-document'
PASSAGE = 'nr-series-demo-p7'
TEXT = 'The TS 38.200 series describes the Layer 1 (Physical Layer) specifications. Layers 2 and 3 are described in the 38.300 series.'
SOURCE = 'https://www.etsi.org/deliver/etsi_ts/138200/138299/138201/18.00.00_60/ts_138201v180000p.pdf'
SOURCE = SOURCE.replace('138200/138299', '138200_138299')
PDF_HASH = 'f33e4ab236e9c21450f54e20f99dd5e031a0d269bf27e69212bfe610fbdbbdf2'
NOTICE = 'Limited live demo: one source excerpt, TS 38.201 v18.0.0, clause 4.1.1 (page 7). Covers Layer 1/2/3 specification series only. Full 12-document hybrid retrieval is a separate setup.'


def ready(store):
    with store.read() as db:
        pointer = db.execute('SELECT build_id FROM corpus_pointer WHERE singleton=1').fetchone()
        if not pointer or pointer['build_id'] != BUILD: return False
        source = db.execute('SELECT * FROM source_documents WHERE build_id=?', (BUILD,)).fetchall()
        rows = db.execute('SELECT * FROM passages WHERE build_id=?', (BUILD,)).fetchall()
        build = db.execute('SELECT status FROM corpus_builds WHERE build_id=?', (BUILD,)).fetchone()
        return bool(build and build['status']=='VALIDATED' and len(source)==len(rows)==1 and
                    source[0]['source_uri']==SOURCE and source[0]['file_hash']==PDF_HASH and
                    source[0]['spec_number']=='38.201' and source[0]['version']=='18.0.0' and source[0]['release']=='18' and
                    rows[0]['passage_id']==PASSAGE and rows[0]['content_text']==TEXT and rows[0]['content_hash']==text_hash(TEXT) and
                    rows[0]['clause_id']=='4.1.1' and rows[0]['page_location']=='7' and not rows[0]['unreadable'])


def prepare(store):
    if not store.settings.demo_mode:
        raise AppError('DEMO_CONFIG', 'Select the explicit demo command.')
    with store.transaction() as db:
        if db.execute('SELECT 1 FROM corpus_builds').fetchone():
            existing = True
        else:
            existing = False
            insert(db,'corpus_builds',build_id=BUILD,fingerprint=digest(TEXT),manifest_json=canonical({'demo':True,'pdf_sha256':PDF_HASH}),config_json=canonical({'retrieval':'lexical_preview','demo':True}),status='VALIDATED',created_at=now())
            insert(db,'source_documents',document_id=DOCUMENT,build_id=BUILD,spec_number='38.201',title='Physical layer; general description (demo excerpt)',release='18',version='18.0.0',source_uri=SOURCE,file_hash=PDF_HASH,parser_config_hash='manually-verified-excerpt-v1')
            insert(db,'passages',passage_id=PASSAGE,document_id=DOCUMENT,build_id=BUILD,clause_id='4.1.1',clause_title='Layer 1 and Layer 2/3 specification series',page_location='7',content_text=TEXT,content_hash=text_hash(TEXT),structure_json=canonical({'kind':'text','cross_references':[]}),unreadable=0)
            db.execute('INSERT INTO passage_fts VALUES (?,?,?,?)',(PASSAGE,BUILD,TEXT,'Specification series'))
            db.execute('INSERT INTO corpus_pointer VALUES (1,?,?)',(BUILD,now()))
    if not ready(store):
        raise AppError('DEMO_CORPUS', 'This folder is not the intact demo collection. Use a separate empty demo data folder; existing data was preserved.')

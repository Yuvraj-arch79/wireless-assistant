"""Synthetic PDFs and provider fixtures; no real API or standards downloads in CI."""
import hashlib
import json
import math
from pathlib import Path
import pytest
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject,NameObject,DecodedStreamObject
from wireless_assistant.common import AppError,canonical
from wireless_assistant.corpus import Corpus,parse_pdf
from wireless_assistant.provider import generate,embed
from wireless_assistant.store import Store


def synthetic_pdf(path):
    writer=PdfWriter();page=writer.add_blank_page(width=612,height=792)
    font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')})
    page[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):font})})
    stream=DecodedStreamObject()
    stream.set_data(b'BT /F1 10 Tf 50 760 Td (650 Fake Street) Tj /F1 18 Tf 0 -35 Td (1 Scope) Tj /F1 10 Tf 0 -30 Td (Synthetic fixture: this document describes NR physical services.) Tj /F1 12 Tf 0 -35 Td (1.1 Context) Tj /F1 10 Tf 0 -25 Td (Consult TS 38.202 clause 4.1 for services.) Tj ET')
    page[NameObject('/Contents')]=writer._add_object(stream)
    with path.open('wb') as output:writer.write(output)


def source_fixture(tmp_path):
    root=Path(__file__).resolve().parents[2]
    manifest=json.loads((root/'corpus/manifest.json').read_text(encoding='utf-8'))
    manifest['documents']=manifest['documents'][:1]
    raw=tmp_path/'raw';raw.mkdir()
    doc=manifest['documents'][0];pdf=raw/doc['filename'];synthetic_pdf(pdf)
    doc.update(sha256=hashlib.sha256(pdf.read_bytes()).hexdigest(),size_bytes=pdf.stat().st_size,page_count=1)
    path=tmp_path/'manifest.json';path.write_text(canonical(manifest),encoding='utf-8')
    return path,raw,pdf


def test_parser_preserves_clauses_and_references_without_address_heading(tmp_path):
    p=tmp_path/'sample.pdf';synthetic_pdf(p)
    result=parse_pdf(p)
    assert not any(x['clause_id']=='650' for x in result['passages'])
    assert any(p['clause_id']=='1' and 'physical services' in p['text'] for p in result['passages'])
    section=next(p for p in result['passages'] if p['clause_id']=='1.1')
    assert section['structure']['cross_references']==[{'spec':'38.202','clause':'4.1'}]


def test_ingest_reuse_hybrid_resume_and_atomic_activation(settings,tmp_path,monkeypatch):
    path,raw,_=source_fixture(tmp_path);store=Store(settings);corpus=Corpus(store)
    lexical=corpus.ingest(path,raw,seconds=15)
    assert corpus.ingest(path,raw,seconds=15)==lexical
    corpus.activate(lexical);assert not corpus.status()['ready']
    # API fixture returns normalized vectors; no live embedding quality claim.
    calls=[]
    def fake_bounded(fn,args=(),seconds=25,**kwargs):
        model,texts,dimensions=args;calls.append(texts)
        return [[1.0]+[0.0]*(dimensions-1) for _ in texts]
    monkeypatch.setattr('wireless_assistant.corpus.bounded',fake_bounded)
    one=corpus.embed_build(lexical,max_batches=1)
    assert not one['complete']
    assert corpus.status()['active_build_id']==lexical
    two=corpus.embed_build(lexical,max_batches=1)
    assert two['complete'] and two['build_id']==one['build_id']
    assert len(calls)==1
    corpus.activate(two['build_id']);assert corpus.status()['ready']
    q=[1.0]+[0.0]*(settings.embedding_dimensions-1)
    assert corpus.search(two['build_id'],'physical services',{'release':'18'},query_vector=q)
    # Rollback preserves both builds.
    corpus.activate(lexical);assert corpus.status()['active_build_id']==lexical


def test_failed_ingestion_keeps_previous_active_build(settings,tmp_path,monkeypatch):
    path,raw,_=source_fixture(tmp_path);store=Store(settings);corpus=Corpus(store)
    def fail(*args,**kwargs):raise AppError('OPERATION_TIMEOUT','Fixture timeout',504)
    monkeypatch.setattr('wireless_assistant.corpus.bounded',fail)
    with pytest.raises(AppError):corpus.ingest(path,raw)
    assert corpus.status()['active_build_id'] is None
    with store.read() as db:
        assert db.execute('SELECT status FROM corpus_builds').fetchone()[0]=='FAILED'


def test_gemini_contract_uses_one_bounded_request_no_tools(monkeypatch):
    observed=[]
    def fake(model,method,body):
        observed.append((model,method,body))
        return {'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':'{"ok":true}'}]}}],'usageMetadata':{'promptTokenCount':10}}
    monkeypatch.setattr('wireless_assistant.provider.request',fake)
    result=generate('configured-model','instructions',{'original':'question'},2000)
    assert result['text']=='{"ok":true}'
    assert len(observed)==1
    body=observed[0][2]
    assert 'tools' not in body and body['generationConfig']['maxOutputTokens']==2000


def test_gemini_truncation_and_blocked_output_rejected(monkeypatch):
    monkeypatch.setattr('wireless_assistant.provider.request',lambda *a:{'candidates':[{'finishReason':'MAX_TOKENS','content':{'parts':[{'text':'partial draft'}]}}]})
    with pytest.raises(AppError) as e:generate('model','instructions',{},20)
    assert e.value.code=='PROVIDER_INCOMPLETE'


def test_embedding_adapter_validates_dimension(monkeypatch):
    monkeypatch.setattr('wireless_assistant.provider.request',lambda *a:{'embedding':{'values':[3,4]}})
    assert embed('model','query',2)==[.6,.8]
    with pytest.raises(AppError):embed('model','query',3)

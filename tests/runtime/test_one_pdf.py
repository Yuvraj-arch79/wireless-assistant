import json
from unittest.mock import patch
import pytest
from wireless_assistant.one_pdf import selected_manifest
from wireless_assistant.config import ROOT
from scripts.corpus import load_manifest
from wireless_assistant.common import AppError


def test_subset_preserves_exact_original_pin_and_inventory(tmp_path):
    original, source_hash=load_manifest(ROOT/'corpus/manifest.json')
    selected=selected_manifest()
    assert len(original['documents'])==12
    assert selected['documents']==[d for d in original['documents'] if d['spec']=='38.201']
    assert selected['selection_source_manifest_sha256']==source_hash
    path=tmp_path/'manifest.json';path.write_text(json.dumps(selected),encoding='utf-8')
    verified, subset_hash=load_manifest(path)
    assert verified==selected and subset_hash!=source_hash


def test_subset_fails_if_pinned_document_missing():
    with patch('scripts.corpus.load_manifest',return_value=({'documents':[]},'hash')):
        with pytest.raises(AppError,match='exactly once'):selected_manifest()


def test_annex_not_attributed_to_previous_clause(tmp_path):
    from wireless_assistant.corpus import parse_pdf
    # Synthetic extractable PDF via the same pdfplumber API; no provider calls.
    class Page:
        lines=[];rects=[]
        def extract_text(self,**kw):return '5.9 Shared spectrum\nSome body text\nAnnex A (informative):\nPreferred mathematical notations\nMore text'
        def extract_text_lines(self,**kw):return [{'text':'5.9 Shared spectrum','top':10,'chars':[{'size':12}]}]
        def close(self):pass
    class PDF:
        pages=[Page()]
        def __enter__(self):return self
        def __exit__(self,*args):pass
    with patch('pdfplumber.open',return_value=PDF()):result=parse_pdf('unused')
    assert result['passages'][0]['clause_id']=='5.9'
    assert result['passages'][1]['clause_id']=='Annex A'
    assert 'More text' in result['passages'][1]['text']

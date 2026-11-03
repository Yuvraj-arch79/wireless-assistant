import copy
import json
from unittest.mock import patch
import pytest
from evaluation import openrouter_b as b
from wireless_assistant.common import AppError


def draft():
    return {'action':'submit_draft','answer_markdown':'Layer 1 is described in TS 38.200 [1]. Layers 2 and 3 are described in TS 38.300 [1].\n\nReferences\n[1] TS 38.201 v18.0.0 clause 4.1.1.',
     'citations':[{'marker':'[1]','claim_anchor':'Layer 1 is described','passage_ids':['ts38201-4.1.1-p7']}],
     'covered_requirements':['r1','r2'],'unresolved_requirements':[],'limitation_statement':None,'revision_log':[]}


def refusal():
    return {'action':'cannot_answer','cannot_answer_reason':[{'gap_id':'g1','kind':'source','requirement_ids':['r1','r2'],'reason':'No source evidence was supplied.','source_or_message_ids':[]}]}


def test_supported_and_refusal():
    assert b.assess(draft(),b.payload())['status']=='pass'
    assert b.assess(refusal(),b.payload(True))['status']=='pass'


@pytest.mark.parametrize('kind',['wrong_fact','bad_citation','missing_requirement'])
def test_rejects_incorrect_draft(kind):
    d=draft()
    if kind=='wrong_fact':d['answer_markdown']=d['answer_markdown'].replace('38.200','38.999')
    if kind=='bad_citation':d['citations'][0]['passage_ids']=['invented']
    if kind=='missing_requirement':d['covered_requirements']=['r1']
    with pytest.raises(AppError):b.assess(d,b.payload())


def test_no_evidence_cannot_pass_draft():
    with pytest.raises(AppError):b.assess(draft(),b.payload(True))


def test_refusal_unknown_binding():
    d=refusal();d['cannot_answer_reason'][0]['requirement_ids']=['wrong']
    with pytest.raises(AppError):b.assess(d,b.payload(True))


def test_transport_free_strict_no_fallback():
    reply={'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'result':draft()})}}]}
    with patch.object(b,'request',return_value=reply) as call:assert b.generate(b.payload())['status']=='pass'
    assert call.call_count==1
    body=call.call_args.args[2]
    assert body['provider']=={'require_parameters':True,'allow_fallbacks':False,'max_price':{'prompt':0,'completion':0,'request':0}}
    assert body['model'].endswith(':free') and body['response_format']['json_schema']['strict']


@pytest.mark.parametrize('code',['QUOTA','AUTH','TIMEOUT'])
def test_failure_stops_without_second_generation(monkeypatch,code):
    monkeypatch.setenv('OPENROUTER_API_KEY','fixture')
    with patch.object(b,'bounded',side_effect=[{},AppError(code,'private')]) as call:r=b.run()
    assert r['status']==code and r['generation_attempts']==1 and call.call_count==2
    assert 'private' not in json.dumps(r)


def test_missing_key_no_call(monkeypatch):
    monkeypatch.delenv('OPENROUTER_API_KEY',raising=False)
    with patch.object(b,'bounded') as call:assert b.run()['status']=='KEY_MISSING'
    call.assert_not_called()


def test_preflight_rejects_paid_or_unsupported():
    for price,parameters in [('1',['response_format','structured_outputs']),('0',[])]:
        with patch.object(b,'request',return_value={'data':[{'id':b.MODEL,'pricing':{'prompt':price,'completion':'0'},'supported_parameters':parameters}]}),pytest.raises(AppError):b.preflight()


def test_local_validation_reason_is_retained():
    d=draft();d['citations'][0]['passage_ids']=['wrong']
    reply={'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'result':d})}}]}
    with patch.object(b,'request',return_value=reply):r=b.generate(b.payload())
    assert r['status']=='INVALID_CONTRACT'
    assert 'Citation references' in r['validation_error']


def test_citation_contract_is_explicit():
    defs=b.schema()['$defs']
    assert 'NOT from evidence' in defs['Citation']['properties']['claim_anchor']['description']
    assert 'References' in defs['BDraft']['properties']['answer_markdown']['description']

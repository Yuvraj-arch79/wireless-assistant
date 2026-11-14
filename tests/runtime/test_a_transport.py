import copy
import json
import pytest
from unittest.mock import patch
import httpx
from wireless_assistant.a_transport import references, encode_payload, decode_result, schema
from wireless_assistant.provider_contracts import inspect_response
from wireless_assistant import role_provider as rp
from wireless_assistant.common import canonical, AppError
from tests.runtime.conftest import collect
from tests.runtime.test_a_token_budget import payload


def test_aliases_roundtrip_without_changing_originals():
    p=payload();before=copy.deepcopy(p);v=collect(p)
    encoded=encode_payload({**p,'need':v['need']})
    assert encoded['need']['original_refs']==['o1']
    assert decode_result({**v,'need':encoded['need']},p)==v
    assert p==before
    with pytest.raises(AppError):decode_result({**v,'need':{**encoded['need'],'original_refs':['o999']}},p)


def test_a_schema_action_branches_and_empty_expansion_rejected():
    import jsonschema
    p=payload();p['evidence']=[]
    s=schema(p);jsonschema.Draft202012Validator.check_schema(s)
    v=collect(p);v['need']=encode_payload({'original_context':p['original_context'],'need':v['need']})['need']
    jsonschema.validate({'result':v},s)
    v['requests']=[{'kind':'expand_passages','purpose':'expand','requirement_ids':['r1'],'limit':1,'passage_ids':[],'relation':'next'}]
    with pytest.raises(jsonschema.ValidationError):jsonschema.validate({'result':v},s)
    assert inspect_response(canonical({'result':decode_result(v,p)}),'A',wrapped=True)['status']=='CONTRACT_INVALID'


def test_generate_restores_aliases_before_backend_validation():
    p=payload();v=collect(p);v['need']=encode_payload({**p,'need':v['need']})['need']
    with patch.object(rp,'request',return_value={'choices':[{'finish_reason':'stop','message':{'content':canonical({'result':v})}}]}):
        result=rp.generate('A',rp.MODELS['A'],'',p,2000)
    assert json.loads(result['text'])==collect(p)


def test_timeout_identifies_actual_role_without_secrets(monkeypatch):
    monkeypatch.setenv('OPENROUTER_API_KEY','secret');monkeypatch.setenv('WA_OPENROUTER_FREE_TIER_CONFIRMED','1')
    def handler(req):raise httpx.ReadTimeout('secret private data')
    with patch.object(rp.httpx,'Client',return_value=httpx.Client(transport=httpx.MockTransport(handler))),pytest.raises(AppError) as error:
        rp.request('B',{})
    assert error.value.code=='PROVIDER_TIMEOUT'
    assert 'OPENROUTER role B' in error.value.message and 'secret' not in error.value.message


@pytest.mark.parametrize('has_evidence', [False, True])
def test_groq_union_has_one_enum_discriminator_and_backend_keeps_intent_enum(has_evidence):
    import jsonschema
    p=payload()
    if not has_evidence:p['evidence']=[]
    s=rp.build_request('A',rp.MODELS['A'],p,2000)['response_format']['json_schema']['schema']
    def resolve(n):
        return s['$defs'][n['$ref'].split('/')[-1]] if '$ref' in n else n
    def check(n):
        if isinstance(n,dict):
            if 'anyOf' in n:
                variants=[resolve(v) for v in n['anyOf']]
                if all(v.get('type')=='object' for v in variants):
                    candidates=set.intersection(*[{k for k,v in b['properties'].items() if 'enum' in v} for b in variants])
                    assert len(candidates)==1, candidates
                    tag=next(iter(candidates))
                    enums=[set(b['properties'][tag]['enum']) for b in variants]
                    assert all(not x&y for i,x in enumerate(enums) for y in enums[i+1:])
            for v in n.values():check(v)
        elif isinstance(n,list):
            for v in n:check(v)
    check(s)
    v=collect(p);v['intent_relation']='invented_relation'
    encoded=encode_payload({**p,'need':v['need']})
    wire={**v,'need':encoded['need']}
    jsonschema.validate({'result':wire},s)
    assert inspect_response(canonical({'result':decode_result(wire,p)}),'A',wrapped=True)['status']=='CONTRACT_INVALID'


def test_public_evaluation_error_diagnostics_are_opt_in_and_redact_key(monkeypatch,capsys):
    monkeypatch.setenv('GROQ_API_KEY','test-secret')
    monkeypatch.setenv('WA_GROQ_FREE_TIER_CONFIRMED','1')
    error={'error':{'type':'invalid_request_error','message':'schema detail test-secret','failed_generation':'private completion'}}
    for enabled in (False,True):
        if enabled:monkeypatch.setenv('WA_PUBLIC_EVAL_DIAGNOSTICS','1')
        else:monkeypatch.delenv('WA_PUBLIC_EVAL_DIAGNOSTICS',raising=False)
        with patch.object(rp.httpx,'Client',return_value=httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(400,json=error)))),pytest.raises(AppError):
            rp.request('A',{})
        out=capsys.readouterr().out
        assert ('schema detail' in out)==enabled
        assert 'test-secret' not in out and 'private completion' not in out

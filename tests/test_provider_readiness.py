"""Readiness guards without credentials or network."""
import json
from unittest.mock import patch
import httpx
import pytest
from evaluation import providers, readiness
from wireless_assistant.common import AppError


def test_no_key_no_network(monkeypatch):
    monkeypatch.delenv('GROQ_API_KEY',raising=False)
    with patch.object(httpx,'Client') as client, pytest.raises(AppError,match='absent'):
        providers.probe('groq',providers.MODELS['groq'])
    client.assert_not_called()


def test_no_paid_inference(monkeypatch):
    monkeypatch.delenv('WA_FREE_TIER_CONFIRMED',raising=False)
    with patch.object(providers,'request') as request, pytest.raises(AppError):
        providers.generate('groq','model','system',{})
    request.assert_not_called()


@pytest.mark.parametrize('status,code',[(302,'HTTP_302'),(401,'AUTH'),(429,'QUOTA'),(503,'HTTP_503')])
def test_errors_are_safe_single_attempt(monkeypatch,status,code):
    monkeypatch.setenv('GROQ_API_KEY','do-not-print-this-secret')
    calls=[]
    def handler(request):
        calls.append(request)
        return httpx.Response(status,json={'error':'do-not-print-this-secret'},headers={'Location':'https://example.org'})
    factory=httpx.Client
    with patch.object(httpx,'Client',side_effect=lambda **kw:factory(transport=httpx.MockTransport(handler),**kw)):
        with pytest.raises(AppError) as error: providers.probe('groq','model')
    assert error.value.code==code and len(calls)==1
    assert 'secret' not in str(error.value)


def test_truncation_not_pass(monkeypatch):
    monkeypatch.setenv('WA_GROQ_FREE_TIER_CONFIRMED','1')
    with patch.object(providers,'request',return_value={'choices':[{'finish_reason':'length','message':{'content':'{}'}}]}):
        with pytest.raises(AppError) as error: providers.generate('groq','model','system',{})
    assert error.value.code=='INCOMPLETE'


def test_runner_records_all_missing_keys(tmp_path,monkeypatch):
    monkeypatch.delenv('WA_FREE_TIER_CONFIRMED',raising=False)
    def missing(*args): raise AppError('KEY_MISSING','Absent')
    with patch.object(readiness,'bounded',side_effect=missing) as operation:
        result=readiness.run(tmp_path/'result.json')
    assert operation.call_count==3 and not result['complete']
    assert all(r['metadata']=='KEY_MISSING' and r['generation']=='not_run' for r in result['results'])
    assert json.loads((tmp_path/'result.json').read_text())==result


def test_prompt_boundary():
    case={'prompt':'Dono ka difference bata.','history':[], 'expected':['SECRET_GOLD'],'sources':['SECRET_SOURCE']}
    assert 'SECRET_' not in json.dumps(readiness.payload_for(case))


def test_oversize_response(monkeypatch):
    monkeypatch.setenv('GROQ_API_KEY','test'); monkeypatch.setattr(providers,'MAX_BYTES',8)
    factory=httpx.Client
    with patch.object(httpx,'Client',side_effect=lambda **kw:factory(transport=httpx.MockTransport(lambda r:httpx.Response(200,content=b'x'*9)),**kw)):
        with pytest.raises(AppError) as error: providers.probe('groq','model')
    assert error.value.code=='RESPONSE_LIMIT'


def test_gemini_confirmation_does_not_authorize_others(monkeypatch):
    monkeypatch.setenv('WA_GEMINI_FREE_TIER_CONFIRMED','1')
    monkeypatch.setenv('WA_FREE_TIER_CONFIRMED','1')
    for provider in ('groq','mistral'):
        monkeypatch.delenv('WA_'+provider.upper()+'_FREE_TIER_CONFIRMED',raising=False)
        with patch.object(providers,'request') as request, pytest.raises(AppError):
            providers.generate(provider,'model','system',{})
        request.assert_not_called()
    assert providers.free_confirmed('gemini')
    monkeypatch.setenv('WA_GEMINI_FREE_TIER_CONFIRMED','0')
    assert not providers.free_confirmed('gemini')


def test_selected_provider_only(tmp_path,monkeypatch):
    monkeypatch.setenv('WA_GEMINI_FREE_TIER_CONFIRMED','1')
    with patch.object(readiness,'bounded',return_value={}) as operation:
        report=readiness.run(tmp_path/'result.json',['gemini'])
    assert operation.call_count==2 and report['complete']
    assert report['order']==['gemini'] and report['limits']['calls']==2
    assert all(call.args[1][0]=='gemini' for call in operation.call_args_list)


@pytest.mark.parametrize('selection',[[],['gemini','gemini'],['unknown']])
def test_selection_fail_closed(tmp_path,selection):
    with patch.object(readiness,'bounded') as operation, pytest.raises(ValueError):
        readiness.run(tmp_path/'result.json',selection)
    operation.assert_not_called()


def test_groq_catalog_supports_namespaced_model():
    with patch.object(providers,'request',return_value={'data':[{'id':'openai/gpt-oss-20b','active':True}]}) as request:
        assert providers.probe('groq','openai/gpt-oss-20b')['model_access']
    request.assert_called_once_with('groq','GET','models')


@pytest.mark.parametrize('data',[{'data':[]},{'data':[{'id':'openai/gpt-oss-20b','active':False}]},{'data':[{'id':'other'}]}])
def test_missing_or_inactive_model_stops(data):
    with patch.object(providers,'request',return_value=data), pytest.raises(AppError) as error:
        providers.probe('groq','openai/gpt-oss-20b')
    assert error.value.code=='MODEL_UNAVAILABLE'


def test_groq_catalog_shape():
    with patch.object(providers,'request',return_value={'data':None}), pytest.raises(AppError) as error:
        providers.probe('groq','openai/gpt-oss-20b')
    assert error.value.code=='CATALOG_FORMAT'


def test_groq_default_and_override(monkeypatch):
    monkeypatch.delenv('WA_EVAL_GROQ_MODEL',raising=False)
    assert providers.configured_model('groq')=='openai/gpt-oss-20b'
    monkeypatch.setenv('WA_EVAL_GROQ_MODEL','explicit-model')
    assert providers.configured_model('groq')=='explicit-model'


def test_groq_single_call_does_not_probe(tmp_path,monkeypatch):
    monkeypatch.setenv('WA_GROQ_FREE_TIER_CONFIRMED','1')
    monkeypatch.delenv('WA_EVAL_GROQ_MODEL',raising=False)
    with patch.object(readiness,'bounded',return_value={}) as call:
        report=readiness.run(tmp_path/'r.json',['groq'],generation_only=True)
    assert call.call_count==1 and call.call_args.args[0] is readiness.smoke
    assert report['complete'] and report['limits']['calls']==1
    assert report['results'][0]['metadata']=='not_rechecked'


def test_single_call_quota_stops(tmp_path,monkeypatch):
    monkeypatch.setenv('WA_GROQ_FREE_TIER_CONFIRMED','1')
    with patch.object(readiness,'bounded',side_effect=AppError('QUOTA','Quota')) as call:
        report=readiness.run(tmp_path/'r.json',['groq'],generation_only=True)
    assert call.call_count==1 and not report['complete']
    assert report['results'][0]['generation']=='QUOTA'


def test_single_call_refuses_changed_model(tmp_path,monkeypatch):
    monkeypatch.setenv('WA_EVAL_GROQ_MODEL','another-model')
    with patch.object(readiness,'bounded') as call:
        report=readiness.run(tmp_path/'r.json',['groq'],generation_only=True)
    call.assert_not_called(); assert not report['complete']


def test_single_call_refuses_other_providers(tmp_path):
    with patch.object(readiness,'bounded') as call, pytest.raises(ValueError):
        readiness.run(tmp_path/'r.json',['groq','gemini'],generation_only=True)
    call.assert_not_called()


def test_groq_smoke_request_is_bounded_and_no_reasoning_text(monkeypatch):
    monkeypatch.setenv('WA_GROQ_FREE_TIER_CONFIRMED','1')
    response={'choices':[{'finish_reason':'stop','message':{'content':'{}'}}]}
    with patch.object(providers,'request',return_value=response) as request:
        providers.generate('groq','openai/gpt-oss-20b','system',{})
    body=request.call_args.args[3]
    assert body['reasoning_effort']=='low' and body['include_reasoning'] is False
    assert body['max_tokens']==2000 and 'tools' not in body

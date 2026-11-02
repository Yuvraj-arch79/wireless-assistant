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


@pytest.mark.parametrize('status,code',[(302,'HTTP_ERROR'),(401,'AUTH'),(429,'QUOTA'),(503,'HTTP_ERROR')])
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
    monkeypatch.setenv('WA_FREE_TIER_CONFIRMED','1')
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

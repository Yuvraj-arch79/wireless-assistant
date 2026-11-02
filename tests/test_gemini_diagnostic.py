from unittest.mock import patch
import httpx
import pytest
from evaluation import gemini_diagnostic as diagnostic, providers
from wireless_assistant.common import AppError


def test_profiles_bounded_and_no_other_provider(tmp_path,monkeypatch):
    monkeypatch.setenv('WA_GEMINI_FREE_TIER_CONFIRMED','1')
    with patch.object(diagnostic,'bounded',return_value={}) as call:
        result=diagnostic.run(tmp_path/'r.json')
    assert result['calls']==15 and len(result['validated_profiles'])==3
    assert all(r['status']=='pass' for r in result['rows'])
    assert all(c.args[2]<=25 for c in call.call_args_list)


def test_failure_not_retried_and_preserved(tmp_path,monkeypatch):
    monkeypatch.setenv('WA_GEMINI_FREE_TIER_CONFIRMED','1')
    def fake(fn,args,seconds):
        if fn is diagnostic.probe: return {}
        raise AppError('READ_TIMEOUT','Timeout')
    with patch.object(diagnostic,'bounded',side_effect=fake):
        result=diagnostic.run(tmp_path/'r.json')
    assert result['calls']==9 and not result['validated_profiles']
    assert sum(r['stage']=='A' for r in result['rows'])==3


def test_no_confirmation_no_calls(tmp_path,monkeypatch):
    monkeypatch.delenv('WA_GEMINI_FREE_TIER_CONFIRMED',raising=False)
    with patch.object(diagnostic,'bounded') as call:
        result=diagnostic.run(tmp_path/'r.json')
    call.assert_not_called(); assert not result['validated_profiles']


def test_thinking_transmitted(monkeypatch):
    monkeypatch.setenv('WA_GEMINI_FREE_TIER_CONFIRMED','1')
    response={'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':'{"ok":true}'}]}}]}
    with patch.object(providers,'request',return_value=response) as request:
        providers.generate('gemini','gemini-3.8-flash','sys',{},thinking={'thinkingLevel':'low'})
    assert request.call_args.args[3]['generationConfig']['thinkingConfig']=={'thinkingLevel':'low'}


@pytest.mark.parametrize('exception,code',[(httpx.ConnectTimeout,'CONNECT_TIMEOUT'),(httpx.ReadTimeout,'READ_TIMEOUT'),(httpx.WriteTimeout,'WRITE_TIMEOUT')])
def test_timeout_phase(monkeypatch,exception,code):
    monkeypatch.setenv('GEMINI_API_KEY','test')
    with patch.object(httpx,'Client',side_effect=exception('private details')):
        with pytest.raises(AppError) as error: providers.probe('gemini','model')
    assert error.value.code==code and 'private' not in str(error.value)


def test_metadata_access_without_generation_is_not_ready():
    with patch.object(providers,'request',return_value={'name':'models/test','supportedGenerationMethods':['countTokens']}):
        with pytest.raises(AppError) as error: providers.probe('gemini','test')
    assert error.value.code=='METHOD_UNSUPPORTED'


def test_generation_capability():
    with patch.object(providers,'request',return_value={'name':'models/test','supportedGenerationMethods':['generateContent']}):
        assert providers.probe('gemini','test')['model_access']


def test_verified_default_profile(monkeypatch):
    monkeypatch.delenv('WA_EVAL_GEMINI_MODEL',raising=False)
    monkeypatch.setenv('WA_GEMINI_FREE_TIER_CONFIRMED','1')
    model=providers.configured_model('gemini')
    assert model=='gemini-3.1-flash-lite'
    response={'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':'{"ok":true}'}]}}]}
    with patch.object(providers,'request',return_value=response) as request:
        providers.generate('gemini',model,'sys',{})
    assert request.call_args.args[3]['generationConfig']['thinkingConfig']=={'thinkingLevel':'minimal'}
    monkeypatch.setenv('WA_EVAL_GEMINI_MODEL','explicit-model')
    assert providers.configured_model('gemini')=='explicit-model'

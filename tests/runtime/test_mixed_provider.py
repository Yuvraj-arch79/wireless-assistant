import json
from unittest.mock import patch
import httpx
import pytest
from wireless_assistant import role_provider as rp
from wireless_assistant.common import AppError, canonical
from wireless_assistant.config import Settings
from wireless_assistant.store import Store
from wireless_assistant.engine import Engine
from wireless_assistant.demo import prepare, ready, TEXT
from evaluation.groq_c import case_payload
from tests.test_groq_c import review
from tests.runtime.conftest import collect


@pytest.mark.parametrize('role', ['A','B','C'])
def test_pinned_live_routes_keep_original_contract(role):
    p=case_payload('correct')
    value=collect(p) if role=='A' else p['candidate'] if role=='B' else review()
    raw=canonical({k:v for k,v in value.items() if k!='reviewed_binding'} if role=='C' else {'result':value})
    with patch.object(rp,'request',return_value={'choices':[{'finish_reason':'stop','message':{'content':raw}}]}) as call:
        result=rp.generate(role,rp.MODELS[role],'',p,2000)
    assert json.loads(result['text'])==value
    body=call.call_args.args[1]
    assert body['model']==rp.MODELS[role] and body['response_format']['json_schema']['strict']
    if role=='C':assert body['max_tokens']==900 and body['reasoning_effort']=='low'
    if role=='B':assert body['provider']['max_price']=={'prompt':0,'completion':0,'request':0} and not body['provider']['allow_fallbacks']


@pytest.mark.parametrize('status', [429,401,400,402,500])
def test_provider_failure_one_attempt_no_private_output(monkeypatch,status):
    monkeypatch.setenv('GROQ_API_KEY','private-key');monkeypatch.setenv('WA_GROQ_FREE_TIER_CONFIRMED','1')
    calls=[]
    def handler(request):
        calls.append(request)
        return httpx.Response(status,json={'error':'private-key private-prompt'})
    client=httpx.Client(transport=httpx.MockTransport(handler))
    with patch.object(rp.httpx,'Client',return_value=client),pytest.raises(AppError) as exc:
        rp.request('C',{})
    assert len(calls)==1 and 'private' not in exc.value.message and not exc.value.retryable


def test_missing_or_revoked_provider_never_calls(monkeypatch):
    monkeypatch.setenv('GROQ_API_KEY','fixture');monkeypatch.setenv('WA_GROQ_FREE_TIER_CONFIRMED','0')
    with patch.object(rp.httpx,'Client') as call,pytest.raises(AppError):rp.request('C',{})
    call.assert_not_called()


def test_profile_snapshot_pins_actual_models(tmp_path):
    s=Settings(data_dir=tmp_path,provider_profile='groq_openrouter')
    assert s.snapshot()['model_c']==rp.MODELS['C'] and s.active_seconds==300
    with pytest.raises(ValueError):Settings(provider_profile='groq_openrouter',model_c='different')
    assert not rp.configured(s)


def test_demo_separate_and_rejects_modified_source(tmp_path):
    s=Settings(data_dir=tmp_path,demo_mode=True,provider_profile='groq_openrouter')
    store=Store(s);prepare(store);prepare(store)
    assert ready(store) and Engine(store).corpus_ready()
    assert not Engine(Store(Settings(data_dir=tmp_path))).corpus_ready()
    with store.transaction() as db:db.execute("UPDATE passages SET content_text='changed'")
    assert not ready(store)
    with pytest.raises(AppError):prepare(store)


def test_truncated_response_never_released():
    with patch.object(rp,'request',return_value={'choices':[{'finish_reason':'length','message':{'content':canonical(review())}}]}),pytest.raises(AppError):
        rp.generate('C',rp.MODELS['C'],'',case_payload('correct'),2000)


def test_real_controller_demo_handoff_with_mock_http(monkeypatch):
    from evaluation.live_demo import run
    from evaluation.openrouter_b import payload as bp
    from tests.runtime.conftest import review as runtime_review
    for name in ('GROQ','OPENROUTER'):
        monkeypatch.setenv(name+'_API_KEY','fixture')
        monkeypatch.setenv('WA_'+name+'_FREE_TIER_CONFIRMED','1')
    calls=[]
    def transport(role,p):
        calls.append(role)
        n=bp()['need'];ref=p['original_context'][0]['ref']
        n['original_refs']=[ref]
        for q in n['requirements']:q['established_by']=[ref]
        if role=='A':
            value={'action':'ready_for_b' if p['evidence'] else 'collect','intent_relation':'same_need','need':n,'coverage_gaps':[]}
            if not p['evidence']:value['requests']=[{'kind':'corpus_search','purpose':'Find series','requirement_ids':['r1','r2'],'query':'Layer specification series','filters':n['scope'],'limit':3}]
        elif role=='B':
            value=case_payload('correct')['candidate'];value['citations'][0]['passage_ids']=[p['evidence'][0]['passage_id']]
        else:
            value=runtime_review(p);value['satisfied_requirements']=['r1','r2']
        raw=canonical({k:v for k,v in value.items() if k!='reviewed_binding'} if role=='C' else {'result':value})
        with patch.object(rp,'request',return_value={'choices':[{'finish_reason':'stop','message':{'content':raw}}]}):
            return rp.generate(role,rp.MODELS[role],'',p,2000)
    result=run(lambda store:Engine(store,role_transport=transport))
    assert result['status']=='pass',result
    assert calls==['A','A','B','C'] and result['accepted_review']


def test_compact_c_rebinds_only_server_owned_identity():
    from wireless_assistant.provider_contracts import inspect_c_response, compact_c_schema
    p=case_payload('correct');out=review()
    assert inspect_c_response(canonical(out),p)['status']=='INVALID_ENVELOPE'
    del out['reviewed_binding']
    restored=inspect_c_response(canonical(out),p)
    assert restored['value']['reviewed_binding']==p['reviewed_binding']
    assert 'reviewed_binding' not in compact_c_schema(p)['properties']
    out['unrecognized']='do not silently discard'
    assert inspect_c_response(canonical(out),p)['status']!='pass'

import copy
import json
from unittest.mock import patch
import httpx
import pytest
from wireless_assistant import role_provider as rp
from wireless_assistant.a_token_budget import A_LIMIT, A_MARGIN, request_tokens, reachable_schema
from wireless_assistant.common import AppError, canonical
from wireless_assistant.provider_contracts import wire_schema

QUESTION = 'TS 38.201 clause 4.2.3: transport blocks ke LDPC aur PBCH ke Polar coding ko natural Hinglish mein simple analogy aur exact citation ke saath samjhao.'


def payload():
    evidence = [dict(passage_id=f'p{i}', text='LDPC transport blocks. Polar PBCH. ' * 900,
                     spec_number='38.201', document_version='18.0.0', clause_id='4.2.3',
                     page_location='8', content_hash='original-hash', source_uri='https://example.org/source.pdf',
                     structure={'rows':[['x']*20]*100,'kind':'table','formula_review_required':True}) for i in range(12)]
    return dict(original_context=[{'ref':{'message_id':'m1','session_id':'s1','content_hash':'h','start_offset':0,'end_offset':len(QUESTION)},'role':'user','text':QUESTION}],
                need={'language':'Hinglish'}, evidence=evidence,
                tool_results=[{'status':'ok','items':copy.deepcopy(evidence)}],
                excluded_history_map=[{'ref':{'message_id':'older'},'preview':'prior requested explanation'}])


@pytest.mark.parametrize('stage', ['initial','post_search','repair'])
def test_a_fits_with_original_question_and_references(stage):
    p=payload()
    if stage=='initial':p['evidence']=[];p['tool_results']=[]
    if stage=='repair':p['contract_error']='requests.1.expand_passages.passage_ids too_short'
    original=copy.deepcopy(p)
    body=rp.build_request('A',rp.MODELS['A'],p,2000)
    assert request_tokens(body)+A_MARGIN<=A_LIMIT
    sent=json.loads(body['messages'][1]['content'])
    from wireless_assistant.a_transport import references
    refs=references(p)
    assert [{**o, 'ref':refs[o['ref']]} for o in sent['original_context']]==p['original_context']
    assert sent['need']==p['need']
    assert sent['excluded_history_map']==p['excluded_history_map']
    assert p==original
    for actual,source in zip(sent['evidence'],p['evidence']):
        for key in ('passage_id','spec_number','document_version','clause_id','source_uri','content_hash','page_location'):
            assert actual[key]==source[key]
        assert actual['preview_truncated']
    if stage=='repair':assert sent['contract_error']==p['contract_error']


def test_unfit_essential_context_never_dispatches():
    p=payload();p['original_context'][0]['text']=QUESTION*1000
    with patch.object(rp,'request') as request,pytest.raises(AppError) as exc:
        rp.generate('A',rp.MODELS['A'],'',p,2000)
    assert exc.value.code=='CONTEXT_LIMIT'
    request.assert_not_called()


@pytest.mark.parametrize('role',['B','C'])
def test_other_role_bodies_untouched(role):
    from wireless_assistant.a_token_budget import budget_request
    p=payload();body={'messages':[{'content':canonical(p)}]}
    assert budget_request(role,p,body) is body


def test_http_413_terminal_no_retry(monkeypatch):
    monkeypatch.setenv('GROQ_API_KEY','fixture');monkeypatch.setenv('WA_GROQ_FREE_TIER_CONFIRMED','1')
    calls=[]
    def handler(request):
        calls.append(request)
        return httpx.Response(413,json={'error':{'code':'rate_limit_exceeded'}})
    with patch.object(rp.httpx,'Client',return_value=httpx.Client(transport=httpx.MockTransport(handler))),pytest.raises(AppError) as exc:
        rp.request('A',{})
    assert len(calls)==1
    assert exc.value.code=='PROVIDER_REQUEST_TOO_LARGE' and not exc.value.retryable


def test_schema_references_still_resolve():
    s=reachable_schema(wire_schema('A'))
    def walk(v):
        if isinstance(v,dict):
            if '$ref' in v:assert v['$ref'].split('/')[-1] in s['$defs']
            for c in v.values():walk(c)
        elif isinstance(v,list):
            for c in v:walk(c)
    walk(s)
    assert s['additionalProperties'] is False


def test_no_tokenizer_no_network(monkeypatch):
    import wireless_assistant.a_token_budget as budget
    def unavailable():raise AppError('TOKENIZER_UNAVAILABLE','Unavailable',503)
    monkeypatch.setattr(budget,'tokenizer',unavailable)
    with patch.object(rp,'request') as request,pytest.raises(AppError):
        rp.generate('A',rp.MODELS['A'],'',payload(),2000)
    request.assert_not_called()

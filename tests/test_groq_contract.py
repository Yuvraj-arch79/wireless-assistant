import json
from unittest.mock import patch
import pytest
from evaluation.groq_contract import inspect_response, wire_schema, strict_generate, run
from evaluation.readiness import payload_for
from wireless_assistant.common import AppError
from tests.runtime.conftest import clarify


def valid_a():
    return clarify(payload_for({'prompt':'Dono ka difference bata.','history':[]}))


def test_exact_field_without_private_values():
    value=valid_a(); del value['need']['language']; value['PRIVATE_KEY']='PRIVATE_VALUE'
    result=inspect_response(json.dumps(value),'A')
    assert {'path':['clarify','need','language'],'type':'missing'} in result['issues']
    assert 'PRIVATE' not in json.dumps(result)


def test_backend_rules_preserved():
    value=valid_a()
    assert inspect_response(json.dumps({'result':value}),'A',True)['value']==value
    value['clarification']['question']=''
    assert inspect_response(json.dumps({'result':value}),'A',True)['status']=='CONTRACT_INVALID'


@pytest.mark.parametrize('role',['A','B','C'])
def test_wire_schema(role):
    schema=wire_schema(role)
    def visit(node):
        if isinstance(node,dict):
            assert 'oneOf' not in node and 'discriminator' not in node
            if node.get('type')=='object':
                assert node['additionalProperties'] is False
                assert set(node['required'])==set(node.get('properties',{}))
            if '$ref' in node: assert node['$ref'].removeprefix('#/$defs/') in schema['$defs']
            for child in node.values(): visit(child)
        elif isinstance(node,list):
            for child in node: visit(child)
    visit(schema)


@pytest.mark.parametrize('raw',['not json','{"result":{},"result":{}}'])
def test_invalid_json(raw):
    assert inspect_response(raw,'A',True)['status']=='INVALID_JSON'


def test_strict_transport_one_attempt(monkeypatch):
    monkeypatch.setenv('WA_GROQ_FREE_TIER_CONFIRMED','1')
    response={'choices':[{'finish_reason':'stop','message':{'content':'{"result":{}}'}}]}
    with patch('evaluation.groq_contract.request',return_value=response) as call: strict_generate('A',{})
    assert call.call_count==1
    body=call.call_args.args[3]
    assert body['response_format']['json_schema']['strict'] is True
    assert body['max_tokens']==2000 and 'tools' not in body


def test_two_calls_to_diagnose_and_verify(monkeypatch):
    monkeypatch.setenv('WA_GROQ_FREE_TIER_CONFIRMED','1'); monkeypatch.setenv('GROQ_API_KEY','fixture')
    with patch('evaluation.groq_contract.bounded',side_effect=[{'status':'CONTRACT_INVALID','issues':[]},{'status':'pass','issues':[]}]) as call:
        result=run({})
    assert result['status']=='pass' and result['attempts']==2 and call.call_count==2
    assert [c.args[1][0] for c in call.call_args_list]==['diagnose','strict']
    assert all(0<c.args[2]<=25 for c in call.call_args_list)


@pytest.mark.parametrize('code',['QUOTA','AUTH','READ_TIMEOUT','GAP_BINDING','OPERATION_TIMEOUT'])
def test_stops_without_retry(monkeypatch,code):
    monkeypatch.setenv('WA_GROQ_FREE_TIER_CONFIRMED','1'); monkeypatch.setenv('GROQ_API_KEY','fixture')
    with patch('evaluation.groq_contract.bounded',side_effect=AppError(code,'private text')) as call: result=run({})
    assert result['status']==code and call.call_count==1
    assert 'private text' not in json.dumps(result)


def test_revocation_prevents_call(monkeypatch):
    monkeypatch.setenv('WA_GROQ_FREE_TIER_CONFIRMED','0')
    with patch('evaluation.groq_contract.bounded') as call: result=run({})
    assert result['attempts']==0 and result['status']=='FREE_TIER_NOT_CONFIRMED'
    call.assert_not_called()
    with patch('evaluation.groq_contract.request') as call, pytest.raises(AppError): strict_generate('A',{})
    call.assert_not_called()


def test_strict_only_makes_one_attempt(monkeypatch):
    monkeypatch.setenv('WA_GROQ_FREE_TIER_CONFIRMED','1'); monkeypatch.setenv('GROQ_API_KEY','fixture')
    with patch('evaluation.groq_contract.bounded',return_value={'status':'pass','issues':[]}) as call:
        result=run({},strict_only=True)
    assert result['attempts']==result['maximum_calls']==call.call_count==1
    assert call.call_args.args[1][0]=='strict'


def test_error_details_do_not_echo_input():
    from evaluation.providers import safe_error_detail
    raw=json.dumps({'error':{'type':'invalid_request_error','message':'schema anyOf not supported PRIVATE_KEY gsk_ABC123','failed_generation':'PRIVATE_REPLY'}}).encode()
    detail=safe_error_detail(raw)
    assert 'schema anyOf not supported' in detail
    assert 'PRIVATE' not in detail and 'gsk' not in detail and 'ABC' not in detail


def test_quota_transport_reports_safe_limit_without_identity(monkeypatch):
    import httpx
    from evaluation import providers
    monkeypatch.setenv('GROQ_API_KEY', 'private-key')
    raw = {'error': {'message': 'Rate limit on tokens per day (TPD) for org_SECRET: Limit 200000, Used 199000, Requested 4000. Key private-key', 'failed_generation': 'private answer'}}
    headers = {'retry-after': '120', 'x-ratelimit-reset-tokens': '2m1.2s', 'x-ratelimit-remaining-tokens': 'private-key', 'authorization': 'private-key'}
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(429, json=raw, headers=headers)))
    with patch.object(providers.httpx, 'Client', return_value=client), pytest.raises(AppError) as caught:
        providers.request('groq', 'POST', 'chat/completions', {}, diagnostics=True)
    assert caught.value.code == 'QUOTA'
    assert json.loads(caught.value.message) == {'scope': 'TPD', 'limit': 200000, 'used': 199000, 'requested': 4000, 'retry-after': '120', 'x-ratelimit-reset-tokens': '2m1.2s'}


@pytest.mark.parametrize('raw', [b'not json', b'[]', b'{"error":null}', b'{"error":{"message":[]}}'])
def test_quota_malformed_body_has_no_private_output(raw):
    from evaluation.providers import safe_quota_detail
    assert json.loads(safe_quota_detail(raw, {'retry-after': 'private', 'x-ratelimit-reset-tokens': 'NaN'})) == {}


def test_discriminator_precedes_shared_fields():
    schema=wire_schema('A')['$defs']
    for name in ['AClarify','ACollect','AReady','AOut']:
        assert next(iter(schema[name]['properties']))=='action'
    for name in ['Search','Expand','HistorySearch','HistoryFetch']:
        assert next(iter(schema[name]['properties']))=='kind'


def test_flat_wire_restores_original_contract_and_rejects_extra_data():
    value=valid_a(); value.update(requests=None,scope_reason=None)
    assert inspect_response(json.dumps({'result':value}),'A',True)['status']=='pass'
    value['scope_reason']='Unexpected non-null field'
    assert inspect_response(json.dumps({'result':value}),'A',True)['status']=='CONTRACT_INVALID'
    value['scope_reason']=None; value['unrecognized']=None
    assert inspect_response(json.dumps({'result':value}),'A',True)['status']=='CONTRACT_INVALID'


def test_wire_action_union_is_flat():
    schema=wire_schema('A')
    result=schema['properties']['result']
    assert result['type']=='object' and 'anyOf' not in result
    assert set(result['properties']['action']['enum'])=={'clarify','collect','ready_for_b','out_of_scope'}
    assert 'anyOf' not in result['properties']['requests']['anyOf'][0]['items']


def test_prompt_keeps_original_branch_rules(monkeypatch):
    monkeypatch.setenv('WA_GROQ_FREE_TIER_CONFIRMED','1')
    response={'choices':[{'finish_reason':'stop','message':{'content':'{"result":{}}'}}]}
    with patch('evaluation.groq_contract.request',return_value=response) as call: strict_generate('A',{})
    system=call.call_args.args[3]['messages'][0]['content']
    assert 'original role contract' in system and 'never null' in system
    assert 'AClarify' in system and 'OriginalRef' in system


def test_a_wire_cannot_emit_null_need_or_coverage():
    props=wire_schema('A')['properties']['result']['properties']
    assert props['need']=={'$ref':'#/$defs/Need'}
    assert props['coverage_gaps']=={'type':'array','items':{'$ref':'#/$defs/Gap'}}


def test_out_of_scope_preserves_need_and_rejects_nonempty_extra_coverage():
    value=valid_a()
    value.update(action='out_of_scope',scope_reason='Unrelated request',clarification=None,requests=None)
    assert inspect_response(json.dumps({'result':value}),'A',True)['status']=='pass'
    value['coverage_gaps']=[{'unexpected':'must not be discarded'}]
    assert inspect_response(json.dumps({'result':value}),'A',True)['status']=='CONTRACT_INVALID'


@pytest.mark.parametrize('field',['need','coverage_gaps'])
def test_null_selected_field_still_fails_backend(field):
    value=valid_a();value[field]=None
    assert inspect_response(json.dumps({'result':value}),'A',True)['status']=='CONTRACT_INVALID'


def test_wire_preserves_original_bounds():
    defs=wire_schema('A')['$defs']
    assert defs['Need']['properties']['requirements']['minItems']==1
    assert defs['Need']['properties']['requirements']['maxItems']==16
    assert defs['Requirement']['properties']['description']['minLength']==1
    assert defs['OriginalRef']['properties']['start_offset']['minimum']==0


def test_overlapping_query_bounds_are_merged():
    schema=wire_schema('A')
    req=schema['properties']['result']['properties']['requests']['anyOf'][0]['items']
    query=req['properties']['query']['anyOf']
    strings=[x for x in query if x.get('type')=='string']
    assert strings==[{'type':'string','minLength':1,'maxLength':1000}]


def test_json_failure_categories_without_response_data():
    assert inspect_response('{"private":1,"private":2}','A')['json_error']=='duplicate_key'
    assert inspect_response('{"private":NaN}','A')['json_error']=='non_finite'
    result=inspect_response('private broken reply','A')
    assert result['json_error']=='syntax' and 'private' not in json.dumps(result)


def test_clarification_requires_a_requirement_binding():
    assert wire_schema('A')['$defs']['Clarification']['properties']['missing_requirement_ids']['minItems']==1

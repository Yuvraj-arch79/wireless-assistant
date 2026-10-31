import json
import pytest
from wireless_assistant.common import canonical,digest,now,uid,text_hash
from wireless_assistant.config import Settings
from wireless_assistant.store import Store,insert
from wireless_assistant.engine import Engine
from wireless_assistant.app import create_app
from fastapi.testclient import TestClient


def fixture_corpus(store):
    with store.transaction() as db:
        insert(db,'corpus_builds',build_id='fixture-build',fingerprint='fixture-fingerprint',manifest_json='{}',config_json=canonical({'retrieval':'lexical_preview'}),status='VALIDATED',created_at=now())
        insert(db,'source_documents',document_id='fixture-doc',build_id='fixture-build',spec_number='38.211',title='Synthetic test fixture',release='18',version='18.10.0',source_uri='https://www.etsi.org/deliver/etsi_ts/fixture.pdf',file_hash='fixture',parser_config_hash='fixture')
        text='Synthetic fixture: an NR resource block contains twelve consecutive subcarriers.'
        insert(db,'passages',passage_id='fixture-passage',document_id='fixture-doc',build_id='fixture-build',clause_id='4.4.4.1',clause_title='Resource blocks',page_location='1',content_text=text,content_hash=text_hash(text),structure_json=canonical({'kind':'text','cross_references':[]}),unreadable=0)
        db.execute('INSERT INTO passage_fts VALUES (?,?,?,?,?)'.replace('?,?,?,?,?','?,?,?,?'),('fixture-passage','fixture-build',text,'Resource blocks'))
        db.execute('INSERT INTO corpus_pointer VALUES (1,?,?)',('fixture-build',now()))


def need(payload):
    ref=payload['original_context'][0]['ref']
    return {'topic':'NR resource blocks','requested_task':'explain','language':'English','depth':'brief',
            'scope':{'spec_numbers':['38.211'],'release':'18','document_versions':[],'default_used':True},
            'requirements':[{'req_id':'r1','description':'Explain resource blocks','mandatory':True,'established_by':[ref]}],
            'assumptions':[],'unresolved_gaps':[],'original_refs':[ref]}


def collect(payload):
    n=need(payload)
    return {'action':'collect','intent_relation':'same_need','need':n,'coverage_gaps':[],
            'requests':[{'kind':'corpus_search','purpose':'Find resource block definition','requirement_ids':['r1'],'query':'resource block subcarriers','filters':n['scope'],'limit':3}]}


def ready(payload):
    return {'action':'ready_for_b','intent_relation':'same_need','need':need(payload),'coverage_gaps':[]}


def clarify(payload):
    return {'action':'clarify','intent_relation':'same_need','need':need(payload),'coverage_gaps':[],
            'clarification':{'question':'Which resource block detail do you need?','missing_requirement_ids':['r1'],'alternatives':['definition','numbering'],'gap_key':'detail'}}


def draft(payload):
    p=payload['evidence'][0]
    answer='A resource block contains twelve consecutive subcarriers [1].\n\nReferences\n[1] TS '+p['spec_number']+' v'+p['document_version']+', clause '+p['clause_id']+'.'
    revisions=[{'finding_id':f['finding_id'],'disposition':'changed','target':f['target_claim_or_req'],'reason':'Corrected using evidence.','evidence_ids':[p['passage_id']]} for f in (payload.get('prior_review') or {}).get('findings',[])]
    return {'action':'submit_draft','answer_markdown':answer,'citations':[{'marker':'[1]','claim_anchor':'A resource block','passage_ids':[p['passage_id']]}],
            'covered_requirements':['r1'],'unresolved_requirements':[],'limitation_statement':None,'revision_log':revisions}


def review(payload,accept=True):
    prior=payload.get('prior_candidate')
    return {'reviewed_binding':payload['reviewed_binding'],'decision':'accepted' if accept else 'findings',
            'satisfied_requirements':['r1'] if accept else [],'unmet_requirements':[] if accept else ['r1'],
            'findings':[] if accept else [{'finding_id':'f1','finding_type':'insufficient_support','blocking':True,'target_claim_or_req':'r1','reason':'Fixture rejection to exercise correction control.','evidence_ids':['fixture-passage']}],
            'regression_check':{'status':'checked' if prior else 'not_applicable','compared_candidate_id':prior['candidate_id'] if prior else None,'lost_or_changed_requirement_ids':[],'resulting_finding_ids':[]}}


class Script:
    def __init__(self,actions=None):
        self.actions=list(actions or []);self.calls=[]
    def __call__(self,role,payload):
        self.calls.append((role,payload))
        if self.actions:
            expected,fn=self.actions.pop(0)
            assert role==expected,(role,expected)
            value=fn(payload)
        else:
            if role=='A':value=ready(payload) if payload['evidence'] else collect(payload)
            elif role=='B':value=draft(payload)
            else:value=review(payload)
        if isinstance(value,Exception):raise value
        return {'text':canonical(value),'usage':{}}


@pytest.fixture
def settings(tmp_path):
    return Settings(data_dir=tmp_path/'app')

@pytest.fixture
def store(settings):
    result=Store(settings);fixture_corpus(result);return result

@pytest.fixture
def client(settings):
    script=Script()
    app=create_app(settings,lambda s:Engine(s,role_transport=script,require_ready=False))
    fixture_corpus(app.state.store)
    with TestClient(app,base_url='http://127.0.0.1:8765') as c:
        c.headers.update({'Origin':'http://127.0.0.1:8765','X-WA-CSRF':app.state.csrf})
        c.app_script=script
        yield c


def post(client,path,body=None,key=None):
    return client.post(path,json={} if body is None else body,headers={'Idempotency-Key':key or uid()})


def create_chat(client):
    r=post(client,'/api/sessions',{'title':'Fixture'})
    assert r.status_code==201,r.text
    return r.json()['data']['session_id']


def wait_run(client,rid,target=None,seconds=12):
    import time
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        response=client.get('/api/runs/'+rid)
        assert response.status_code==200,response.text
        data=response.json()['data']
        if data['status']==target if target else data['status']!='ACTIVE':return data
        time.sleep(.05)
    raise AssertionError('Run failed to finish: '+str(data))

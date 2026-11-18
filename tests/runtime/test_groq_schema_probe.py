import json
from pathlib import Path
from unittest.mock import patch
import httpx
from scripts import probe_groq_schema as probe, fix_groq_schema as installer
from tests.runtime.conftest import collect
from tests.runtime.test_a_token_budget import payload


def test_embedded_probe_matches_versioned_source():
    assert installer.PROBE==Path(probe.__file__).read_text(encoding='utf-8')


def test_probe_without_confirmation_never_calls_provider(monkeypatch,capsys):
    monkeypatch.setenv('GROQ_API_KEY','private-fixture-key')
    monkeypatch.delenv('WA_GROQ_FREE_TIER_CONFIRMED',raising=False)
    with patch.object(httpx,'Client') as client:
        assert probe.main()==2
        client.assert_not_called()
    assert 'private-fixture-key' not in capsys.readouterr().out


def test_probe_schema_rejection_is_single_attempt_and_private(monkeypatch,capsys):
    monkeypatch.setenv('GROQ_API_KEY','private-fixture-key')
    monkeypatch.setenv('WA_GROQ_FREE_TIER_CONFIRMED','1')
    calls=[]
    def handler(request):
        calls.append(request)
        return httpx.Response(400,json={'error':{'type':'invalid_request_error','param':'response_format',
            'message':'private-fixture-key private prompt discriminator_multiple_candidates'}})
    with patch.object(httpx,'Client',return_value=httpx.Client(transport=httpx.MockTransport(handler))):
        assert probe.main()==1
    out=capsys.readouterr().out
    assert len(calls)==1 and 'discriminator_multiple_candidates' in out
    assert 'private-fixture-key' not in out and 'private prompt' not in out


def test_probe_checks_dto_after_http_success(monkeypatch,capsys):
    monkeypatch.setenv('GROQ_API_KEY','private-fixture-key')
    monkeypatch.setenv('WA_GROQ_FREE_TIER_CONFIRMED','1')
    v=collect(payload());v['intent_relation']='invented'
    v['need']['original_refs']=['o1']
    for requirement in v['need']['requirements']:requirement['established_by']=['o1']
    result={'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'result':v})}}]}
    with patch.object(httpx,'Client',return_value=httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(200,json=result)))):
        assert probe.main()==1
    out=capsys.readouterr().out
    assert 'SCHEMA ACCEPTED' in out and 'A CONTRACT FAILED' in out

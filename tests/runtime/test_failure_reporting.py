"""Failures must say WHERE they happened and never look like scope or review results."""
import json
from unittest.mock import patch
import httpx
import pytest
from .conftest import post, create_chat, wait_run
from wireless_assistant import role_provider as rp, provider as gp
from wireless_assistant.common import AppError


def _ask(client, text='Explain an NR resource block.'):
    sid = create_chat(client)
    rid = post(client, f'/api/sessions/{sid}/messages', {'text': text}).json()['data']['run_id']
    return sid, rid, wait_run(client, rid)


def _no_reviewed_answer(client, sid):
    items = client.get(f'/api/sessions/{sid}/messages').json()['data']['items']
    assert all(m['role'] != 'assistant' for m in items), items
    return items[-1]


@pytest.mark.parametrize('stage,code,expect', [
    ('C', 'PROVIDER_TIMEOUT', 'reviewing'),
    ('B', 'PROVIDER_TIMEOUT', 'writing'),
    ('C', 'PROVIDER_REQUEST_TOO_LARGE', 'too large'),
    ('B', 'PROVIDER_QUOTA', 'rate limit'),
])
def test_failure_names_stage_and_is_not_scope_or_review(client, stage, code, expect):
    script = client.app_script
    from .conftest import collect, ready, draft
    fail = lambda p: AppError(code, 'raw adapter message', 504, False)
    actions = [('A', collect), ('A', ready)]
    actions += [('B', fail)] if stage == 'B' else [('B', draft), ('C', fail)]
    script.actions = actions
    sid, rid, status = _ask(client)
    assert status['status'] in ('FAILED', 'TIMED_OUT'), status
    outcome = status['outcome']
    assert outcome['kind'] == code and outcome['stage'] == stage
    notice = _no_reviewed_answer(client, sid)['content_text']
    assert expect in notice.lower(), notice
    assert 'source passages were found' in notice.lower(), notice  # retrieval succeeded before the failure
    assert 'scope' not in notice.lower() and 'reviewed' not in notice.lower().replace('unreviewed', '')
    assert rid[:8] in notice  # traceable reference


def test_quota_retry_after_reaches_user(client):
    from .conftest import collect
    script = client.app_script
    err = AppError('PROVIDER_QUOTA', 'quota', 429, False); err.retry_after = 17
    script.actions = [('A', lambda p: err)]
    sid, rid, status = _ask(client)
    assert status['outcome']['retry_after_seconds'] == 17
    notice = _no_reviewed_answer(client, sid)['content_text']
    assert '17 seconds' in notice and 'source passages were found' not in notice.lower()


def _http(handler, monkeypatch):
    monkeypatch.setenv('GROQ_API_KEY', 'private-key'); monkeypatch.setenv('WA_GROQ_FREE_TIER_CONFIRMED', '1')
    return patch.object(rp.httpx, 'Client', return_value=httpx.Client(transport=httpx.MockTransport(handler)))


def test_groq_413_is_request_too_large_not_unavailable(monkeypatch):
    with _http(lambda r: httpx.Response(413, json={'error': {'message': 'Request too large', 'code': 'rate_limit_exceeded'}}), monkeypatch), pytest.raises(AppError) as exc:
        rp.request('C', {})
    assert exc.value.code == 'PROVIDER_REQUEST_TOO_LARGE' and not exc.value.retryable


def test_groq_429_retry_after_header_parsed(monkeypatch):
    with _http(lambda r: httpx.Response(429, headers={'retry-after': '23'}, json={}), monkeypatch), pytest.raises(AppError) as exc:
        rp.request('A', {})
    assert exc.value.code == 'PROVIDER_QUOTA' and exc.value.retry_after == 23
    assert exc.value.public()['retry_after_seconds'] == 23


def test_gemini_429_retry_delay_and_413(monkeypatch):
    monkeypatch.setenv('GEMINI_API_KEY', 'k'); monkeypatch.setenv('WA_FREE_TIER_CONFIRMED', '1')
    body = {'error': {'code': 429, 'details': [{'@type': 'type.googleapis.com/google.rpc.RetryInfo', 'retryDelay': '31s'}]}}
    with patch.object(gp.httpx, 'Client', return_value=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(429, json=body)))), pytest.raises(AppError) as exc:
        gp.request('gemini-3.8-flash', 'generateContent', {})
    assert exc.value.retry_after == 31
    with patch.object(gp.httpx, 'Client', return_value=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(413, json={})))), pytest.raises(AppError) as exc:
        gp.request('gemini-3.8-flash', 'generateContent', {})
    assert exc.value.code == 'PROVIDER_REQUEST_TOO_LARGE'


def test_run_log_has_stage_model_and_no_secrets_or_chat_text(client, monkeypatch):
    monkeypatch.setenv('GROQ_API_KEY', 'sk-secret-value')
    from .conftest import collect, ready
    client.app_script.actions = [('A', collect), ('A', ready), ('B', lambda p: AppError('PROVIDER_TIMEOUT', 't', 504, False))]
    sid, rid, status = _ask(client, 'Private question about resource blocks')
    log = (client.app.state.store.settings.data_dir / 'logs' / 'runs.jsonl').read_text(encoding='utf-8')
    lines = [json.loads(l) for l in log.splitlines() if rid in l]
    assert any(l['event'] == 'provider_call' and l['stage'] == 'B' and l['code'] == 'PROVIDER_TIMEOUT' and 'elapsed_ms' in l and 'token_estimate' in l and 'model' in l for l in lines), lines
    assert any(l['event'] == 'run_end' and l['code'] == 'PROVIDER_TIMEOUT' for l in lines)
    assert 'sk-secret-value' not in log and 'Private question' not in log


def test_trace_command_finds_run_by_user_reference(client, capsys):
    from .conftest import collect, ready, draft
    client.app_script.actions = [('A', collect), ('A', ready), ('B', draft), ('C', lambda p: AppError('PROVIDER_TIMEOUT', 't', 504, False))]
    sid, rid, status = _ask(client)
    from wireless_assistant.cli import trace
    [run] = trace(client.app.state.store, rid[:8])
    assert run['run_id'] == rid and run['stop_code'] == 'PROVIDER_TIMEOUT' and run['outcome']['stage'] == 'C'
    assert [o['kind'] for o in run['operations'] if o['kind'] in 'ABC'] == ['A', 'A', 'B', 'C']
    assert any(l['event'] == 'provider_call' and l['stage'] == 'C' for l in run['log'])

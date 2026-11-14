"""One bounded, private A schema probe. Does not publish a chat answer."""
import hashlib
import json
import os


def main():
    if not os.getenv('GROQ_API_KEY') or os.getenv('WA_GROQ_FREE_TIER_CONFIRMED') != '1':
        print('LIVE PROBE SKIPPED: use the same PowerShell with the configured Groq environment.', flush=True)
        return 2
    import httpx
    from wireless_assistant import role_provider as rp
    from wireless_assistant.a_transport import decode_result
    from wireless_assistant.common import canonical
    from wireless_assistant.provider_contracts import inspect_response
    question = ('TS 38.201 clause 4.2.3 ke according transport blocks aur PBCH ki coding '
                'simple Hinglish mein ek analogy ke saath samjhao. Exact citation do. '
                'Coding choose karne ka reason source mein nahi hai toh clearly batao.')
    payload = {
        'original_context': [{'ref': {'message_id': 'schema-probe', 'session_id': 'schema-probe',
            'content_hash': hashlib.sha256(question.encode()).hexdigest(), 'start_offset': 0,
            'end_offset': len(question)}, 'role': 'user', 'text': question}],
        'evidence': [], 'tool_results': [], 'excluded_history_map': [],
        'corpus_inventory': [{'spec_number': '38.201', 'version': '18.0.0', 'release': '18'}],
    }
    body = rp.build_request('A', rp.MODELS['A'], payload, 2000)
    print('LIVE PROBE: one A request; no retries; no answer will be published.', flush=True)
    try:
        with httpx.Client(timeout=httpx.Timeout(30, connect=8), trust_env=False) as client:
            with client.stream('POST', 'https://api.groq.com/openai/v1/chat/completions',
                    headers={'Authorization': 'Bearer ' + os.environ['GROQ_API_KEY']}, json=body) as r:
                raw = bytearray()
                for chunk in r.iter_bytes(chunk_size=16384):
                    raw.extend(chunk)
                    if len(raw) > 262144:
                        print('LIVE PROBE FAILED: response exceeded diagnostic bound.', flush=True)
                        return 1
                print('GROQ HTTP:', r.status_code, flush=True)
                try:
                    result = json.loads(raw)
                except (ValueError, UnicodeError):
                    print('LIVE PROBE FAILED: non-JSON response.', flush=True)
                    return 1
                if r.status_code != 200:
                    error = result.get('error', {}) if isinstance(result, dict) else {}
                    if not isinstance(error, dict):error = {}
                    for field in ('code', 'type', 'param'):
                        value = error.get(field)
                        # Fixed labels only; never print provider text that might echo a key/prompt.
                        allowed = {'invalid_request_error','json_validate_failed','rate_limit_exceeded',
                                   'invalid_api_key','response_format','model','max_tokens','tokens'}
                        if value in allowed:print(field + ':', value, flush=True)
                    if 'discriminator_multiple_candidates' in str(error.get('message', '')):
                        print('SCHEMA ERROR: discriminator_multiple_candidates', flush=True)
                    return 1
        print('GROQ SCHEMA ACCEPTED (HTTP 200).', flush=True)
        choices = result.get('choices', [])
        if len(choices) != 1 or choices[0].get('finish_reason') != 'stop':
            print('A CONTRACT NOT VERIFIED: response incomplete.', flush=True)
            return 1
        wrapped = json.loads(choices[0]['message']['content'])
        if not isinstance(wrapped, dict) or set(wrapped) != {'result'}:
            print('A CONTRACT FAILED: invalid wrapper.', flush=True)
            return 1
        parsed = inspect_response(canonical({'result': decode_result(wrapped['result'], payload)}), 'A', wrapped=True)
        if parsed['status'] != 'pass':
            print('A CONTRACT FAILED: server DTO rejected the response.', flush=True)
            return 1
        action = parsed['value']['action']
        print('A CONTRACT PASS; action=' + action, flush=True)
        if action != 'collect':
            print('FLOW CHECK FAILED: this explicit source question should collect evidence first.', flush=True)
            return 1
        print('SCHEMA PROBE PASSED. Full B/C Reviewed answer still requires a chat test.', flush=True)
        return 0
    except httpx.HTTPError as exc:
        print('LIVE PROBE FAILED:', type(exc).__name__, '(no retry).', flush=True)
        return 1
    except Exception as exc:
        print('LIVE PROBE FAILED:', type(exc).__name__, '(no private details printed).', flush=True)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())

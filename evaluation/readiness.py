"""Bounded provider preflight and A clarification smoke; not a quality benchmark."""
import hashlib
import json
import os
from pathlib import Path
import random
import time
from wireless_assistant.bounded import bounded
from wireless_assistant.common import AppError, canonical, text_hash, now
from wireless_assistant.contracts import ADAPTERS
from wireless_assistant.prompts import instructions
from evaluation.inputs import user_input
from evaluation.providers import MODELS, configured_model, probe, generate, free_confirmed

ROOT = Path(__file__).resolve().parents[1]


def payload_for(case):
    prompt = user_input(case)['prompt']
    ref = {'message_id':'smoke-message','session_id':'smoke-session','content_hash':text_hash(prompt),
           'start_offset':0,'end_offset':len(prompt)}
    return {'original_context':[{'ref':ref,'role':'user','text':prompt}], 'need':None,'evidence':[],
            'excluded_history_map':[], 'tool_results':[], 'coverage_gaps':[], 'closing_mode':False,
            'b_gap':None,'prior_candidate':None,'prior_review':None,'corpus_inventory':[],
            'budget':{'provider_calls':0}, 'envelope':{'round_number':0}}


def smoke(provider, model, payload, thinking=None):
    text = generate(provider, model, instructions('A'), payload, thinking=thinking)
    try:
        out = ADAPTERS['A'].validate_json(text).model_dump(mode='json')
    except Exception:
        raise AppError('CONTRACT_INVALID', 'A response failed the production schema.') from None
    ref = payload['original_context'][0]['ref']
    refs = out.get('need',{}).get('original_refs', [])
    if out['action'] != 'clarify' or not refs or any(r != ref for r in refs):
        raise AppError('CLARIFICATION_CHECK_FAILED', 'Expected bound clarification.')
    return {'schema_valid':True,'clarification':True}


def run(output, selected=None):
    selected = list(MODELS) if selected is None else list(selected)
    if not selected or len(set(selected)) != len(selected) or any(p not in MODELS for p in selected):
        raise ValueError("Select unique known providers")
    suite_bytes = (ROOT/'evaluation/cases.json').read_bytes()
    suite = json.loads(suite_bytes)
    case = next(c for c in suite['cases'] if c['id']=='B01' and c['split']=='dev')
    payload = payload_for(case)
    start = time.monotonic(); deadline = start + 180
    order = selected; random.Random(20261102).shuffle(order)
    report = {'kind':'provider_readiness_not_quality','utc':now(),'commit':os.getenv('GITHUB_SHA','local'),
        'suite_sha256':hashlib.sha256(suite_bytes).hexdigest(), 'case_id':'B01',
        'prompt_sha256':text_hash(instructions('A')), 'seed':20261102, 'order':order,
        'limits':{'calls':2 * len(order),'per_call_seconds':25,'total_seconds':180,'retries':0,'trials':1},'results':[]}
    for provider in order:
        row = {'provider':provider,'metadata':'not_run','generation':'not_run'}
        report['results'].append(row)
        try:
            model = configured_model(provider); row['model']=model
            for field, function, args in [('metadata',probe,(provider,model)), ('generation',smoke,(provider,model,payload))]:
                if field == 'generation' and not free_confirmed(provider):
                    row[field] = 'FREE_TIER_NOT_CONFIRMED'; break
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise AppError('RUN_DEADLINE','Run budget exhausted.')
                before = time.monotonic()
                try:
                    bounded(function,args,min(25,remaining))
                    row[field] = 'pass'
                except AppError as exc:
                    # Only allow known, sanitized error identifiers into public summaries.
                    row[field] = exc.code; break
                finally:
                    row[field+'_seconds'] = round(time.monotonic()-before,3)
        except AppError as exc:
            row['configuration'] = exc.code
        output.parent.mkdir(parents=True,exist_ok=True)
        output.write_text(canonical(report)+'\n',encoding='utf-8')
    report['complete'] = all(r['metadata']=='pass' and r['generation']=='pass' for r in report['results'])
    output.write_text(canonical(report)+'\n',encoding='utf-8')
    lines = ['## Provider readiness (not model accuracy)', '', '| Provider | Metadata | A clarification smoke |', '| --- | --- | --- |']
    lines += [f"| {r['provider']} | {r['metadata']} | {r['generation']} |" for r in report['results']]
    lines += ['', 'No B/C, retrieval, technical-answer quality or A/B/C assignment is accepted by this smoke test.']
    summary='\n'.join(lines)+'\n'
    print(summary)
    if os.getenv('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'],'a',encoding='utf-8') as stream: stream.write(summary)
    return report


if __name__ == '__main__':
    import sys
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--provider', choices=[*MODELS, 'all'], default='all')
    args = parser.parse_args()
    result = run(ROOT/'data/evaluation/readiness.json', None if args.provider == 'all' else [args.provider])
    sys.exit(0 if result['complete'] else 1)

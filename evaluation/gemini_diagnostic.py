"""Finite paired Gemini diagnosis. No gold labels, response text or secrets logged."""
import json
import os
from pathlib import Path
import time
from wireless_assistant.bounded import bounded
from wireless_assistant.common import AppError, canonical, now, text_hash
from wireless_assistant.prompts import instructions
from evaluation.providers import configured_model, free_confirmed, generate, probe
from evaluation.readiness import payload_for, smoke, ROOT


def tiny(model, thinking):
    text = generate('gemini', model, 'Return only the JSON object requested by the user.',
                    {'prompt':'Return {"ok":true}.'}, 2000, thinking)
    try:
        valid = json.loads(text) == {'ok':True}
    except ValueError:
        valid = False
    if not valid:
        raise AppError('TINY_FORMAT','Unexpected tiny response.')


def run(output):
    raw=(ROOT/'evaluation/cases.json').read_text(encoding='utf-8')
    case=next(c for c in json.loads(raw)['cases'] if c['id']=='B01' and c['split']=='dev')
    payload=payload_for(case)
    # Prespecified diagnostic alternatives, never automatic production fallback.
    profiles=[('baseline',configured_model('gemini'),None),
              ('low','gemini-3.8-flash',{'thinkingLevel':'low'}),
              ('flash25','gemini-2.5-flash',{'thinkingBudget':0})]
    report={'kind':'gemini_diagnostic_not_quality','utc':now(),'commit':os.getenv('GITHUB_SHA','local'),
            'suite_hash':text_hash(raw),'prompt_hash':text_hash(instructions('A')),
            'limits':{'max_calls':15,'total_seconds':300,'call_seconds':25,'retries':0},'rows':[]}
    deadline=time.monotonic()+300; calls=0
    def attempt(profile, model, thinking, stage, trial, function, args):
        nonlocal calls
        row={'profile':profile,'model':model,'thinking':thinking,'stage':stage,'trial':trial,'status':'not_run'}
        report['rows'].append(row); start=time.monotonic()
        if not free_confirmed('gemini'): row['status']='FREE_TIER_NOT_CONFIRMED'
        elif calls>=15 or start>=deadline: row['status']='BUDGET_EXHAUSTED'
        else:
            calls+=1
            try:
                bounded(function,args,min(25,deadline-start)); row['status']='pass'
            except AppError as e: row['status']=e.code
        row['seconds']=round(time.monotonic()-start,3)
        output.parent.mkdir(parents=True,exist_ok=True)
        output.write_text(canonical(report)+'\n',encoding='utf-8')
        return row['status']
    for label, model, thinking in profiles:
        status=attempt(label,model,thinking,'metadata',0,probe,('gemini',model))
        if status in ('AUTH','QUOTA','FREE_TIER_NOT_CONFIRMED','BUDGET_EXHAUSTED'): break
        if status!='pass': continue
        status=attempt(label,model,thinking,'tiny',0,tiny,(model,thinking))
        if status in ('AUTH','QUOTA','FREE_TIER_NOT_CONFIRMED','BUDGET_EXHAUSTED'): break
        # Run A even if tiny times out: it is the paired workload observation.
        for trial in range(1,4):
            status=attempt(label,model,thinking,'A',trial,smoke,('gemini',model,payload,thinking))
            if status!='pass': break  # no repeated failed configuration
        if status in ('AUTH','QUOTA','FREE_TIER_NOT_CONFIRMED','BUDGET_EXHAUSTED'): break
    good=[]
    for label,model,thinking in profiles:
        rows=[r for r in report['rows'] if r['profile']==label]
        if len(rows)==5 and all(r['status']=='pass' for r in rows): good.append(label)
    report['validated_profiles']=good;report['calls']=calls
    output.write_text(canonical(report)+'\n',encoding='utf-8')
    lines=['## Gemini diagnosis — not technical accuracy','','| Profile | Stage | Trial | Result | Seconds |','| --- | --- | --- | --- | --- |']
    lines += [f"| {r['profile']} | {r['stage']} | {r['trial']} | {r['status']} | {r['seconds']} |" for r in report['rows']]
    lines += ['', 'Profiles passing tiny + 3 A trials: '+(', '.join(good) or 'none'), 'No automatic model selection or latency-limit increase.']
    summary='\n'.join(lines)+'\n';print(summary)
    if os.getenv('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'],'a',encoding='utf-8') as f:f.write(summary)
    return report


if __name__=='__main__':
    import sys
    report=run(ROOT/'data/evaluation/gemini-diagnostic.json')
    sys.exit(0 if report['validated_profiles'] else 1)

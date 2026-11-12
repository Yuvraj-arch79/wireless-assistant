"""One bounded replay of a failed public evaluation B input; no production chats."""
import json
from wireless_assistant.config import Settings,ROOT
from wireless_assistant.store import Store
from wireless_assistant.engine import Engine
from wireless_assistant.role_provider import request,build_request,MODELS
from wireless_assistant.provider_contracts import inspect_response,render_references
from wireless_assistant.validation import validate_draft
from wireless_assistant.bounded import bounded


def probe(payload):
    result=request('B',build_request('B',MODELS['B'],payload,2000))
    choice=result.get('choices',[{}])[0]
    parsed=inspect_response(choice.get('message',{}).get('content',''),'B',wrapped=True)
    report={'finish_reason':choice.get('finish_reason'),'parsed':parsed}
    if parsed['status']=='pass':
        draft=render_references(parsed['value'],payload['evidence'])
        try:validate_draft(draft,payload['need'],payload['evidence'],payload['prior_review']);report['validation']='pass'
        except Exception as e:report['validation']=str(e)
    return report

if __name__=='__main__':
    store=Store(Settings(data_dir=ROOT/'data/one-pdf',provider_profile='groq_openrouter'))
    rid='92fe50ea6cc64253bc251b90f9f7a9f7'
    engine=Engine(store);r,state=store.state(rid)
    context,compact,evidence=engine.collect_context(rid,state)
    payload=engine.payload(rid,state,context,compact,evidence)
    print(json.dumps(bounded(probe,(payload,),25),indent=2))

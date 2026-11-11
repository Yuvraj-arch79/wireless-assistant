"""One live embedding dependency check before spending a full-corpus budget."""
import json
from wireless_assistant.bounded import bounded
from wireless_assistant.corpus import embed_batch
from wireless_assistant.common import AppError
from wireless_assistant.demo import TEXT


def run():
    try:
        result=bounded(embed_batch,('gemini-embedding-001',[TEXT],768),25)
        return {'status':'pass','calls':1,'vectors':len(result),'dimensions':len(result[0]),'scope':'Embedding dependency only; not full corpus or chat acceptance.'}
    except AppError as error:
        return {'status':error.code,'message':error.message,'maximum_calls':1,'retries':0}


if __name__=='__main__':
    result=run();print(json.dumps(result,indent=2));raise SystemExit(0 if result['status']=='pass' else 1)

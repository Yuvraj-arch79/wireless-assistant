"""Read-only tools run inside the same killable boundary as retrieval."""
from pathlib import Path
from .common import AppError, canonical, token_bound
from .config import Settings
from .corpus import Corpus
from .store import Store


def local_tool_worker(db_path, config, session_id, build_id, tool):
    settings=Settings(data_dir=Path(db_path).parent,**{k:v for k,v in config.items() if k in Settings.model_fields and k!='data_dir'})
    store=Store(settings);cursor=None
    if tool['kind']=='expand_passages':
        items=Corpus(store).expand(build_id,tool['passage_ids'],tool['relation'],tool['limit'])
    elif tool['kind']=='history_search':
        with store.read() as db:
            rows=[dict(r) for r in db.execute('SELECT * FROM messages WHERE session_id=? AND sequence>? AND instr(lower(content_text),lower(?))>0 ORDER BY sequence LIMIT ?',
                (session_id,int(tool['cursor'] or -1),tool['query'],tool['limit']+1))]
        if len(rows)>tool['limit']:
            cursor=str(rows[tool['limit']-1]['sequence']);rows=rows[:tool['limit']]
        items=[{'ref':store.original_ref(m),'preview':m['content_text'][:180]} for m in rows]
    else:
        with store.read() as db:
            items=[store.fetch_history(db,session_id,ref) for ref in tool['refs']]
        if token_bound(canonical(items))>6000:
            raise AppError('HISTORY_LIMIT','History fetch exceeds context allowance.')
    return items,cursor

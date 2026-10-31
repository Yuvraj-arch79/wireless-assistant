"""Loopback-only HTTP API. No provider calls in request handlers."""
import asyncio
from contextlib import asynccontextmanager
import json
import os
from pathlib import Path
import secrets
import sqlite3
import time
from typing import Literal
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import Field
from .common import AppError, canonical, load_json, now, uid
from .config import Settings
from .contracts import Strict
from .engine import Engine
from .store import Store, insert, row, TERMINAL


class NewSession(Strict):
    title: str | None = Field(default=None,max_length=120)

class Rename(Strict):
    title: str = Field(min_length=1,max_length=120)
    expected_session_version: int = Field(ge=0)

class Message(Strict):
    text: str = Field(min_length=1,max_length=32768)

class Reply(Message):
    expected_run_version: int = Field(ge=0)

class Empty(Strict):
    pass

class Feedback(Strict):
    run_id: str
    candidate_id: str
    category: Literal['wrong','unclear','irrelevant','incomplete']
    comment: str | None = Field(default=None,max_length=2000)


class ProcessLock:
    """OS lock released on process exit; a stale filename does not block restart."""
    def __init__(self,path):
        self.file=Path(path).open('a+b')
        try:
            self.file.seek(0)
            if not self.file.read(1):
                self.file.write(b'0');self.file.flush()
            self.file.seek(0)
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(self.file.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError:
            self.file.close()
            raise AppError('ALREADY_RUNNING','Cannot acquire the data-directory lock. Check file access and stop another server or maintenance command using it.',503) from None
    def close(self):
        self.file.close()


class Guard:
    def __init__(self,app,settings,token):
        self.app,self.settings,self.token=app,settings,token
    async def __call__(self,scope,receive,send):
        if scope['type']!='http':
            await self.app(scope,receive,send);return
        headers={k.decode('latin1').lower():v.decode('latin1') for k,v in scope['headers']}
        origins={f'http://127.0.0.1:{self.settings.port}',f'http://localhost:{self.settings.port}'}
        hosts={f'127.0.0.1:{self.settings.port}',f'localhost:{self.settings.port}'}
        client=scope.get('client')
        error=None
        if client and client[0] not in ('127.0.0.1','::1','testclient'):
            error=AppError('LOCAL_ONLY','Only local connections are allowed.',403)
        elif headers.get('host') not in hosts:
            error=AppError('HOST_REJECTED','Unexpected request host.',403)
        elif headers.get('sec-fetch-site')=='cross-site' or headers.get('origin') and headers['origin'] not in origins:
            error=AppError('ORIGIN_REJECTED','Cross-origin access is not allowed.',403)
        mutation=scope['method'] in ('POST','PATCH','DELETE','PUT')
        if not error and mutation and (headers.get('origin') not in origins or not secrets.compare_digest(headers.get('x-wa-csrf',''),self.token)):
            error=AppError('CSRF_REJECTED','Reload the local app before changing data.',403)
        if error:
            await JSONResponse({'request_id':uid(),'error':error.public(),'current_run':None},status_code=error.status)(scope,receive,send);return
        body=bytearray()
        if mutation:
            try:
                async with asyncio.timeout(10):
                    while True:
                        event=await receive()
                        if event['type']=='http.disconnect':
                            return
                        body.extend(event.get('body',b''))
                        if len(body)>32768:
                            raise AppError('BODY_LIMIT','Request exceeds 32 KiB.',413)
                        if not event.get('more_body'):
                            break
                if body:
                    if not headers.get('content-type','').startswith('application/json'):
                        raise AppError('CONTENT_TYPE','Use application/json.',415)
                    load_json(body.decode('utf-8'))
            except (UnicodeError,ValueError,RecursionError):
                error=AppError('INVALID_JSON','Malformed, duplicate-key or non-finite JSON.',400)
            except TimeoutError:
                error=AppError('BODY_TIMEOUT','Request body timed out.',408)
            except AppError as exc:
                error=exc
            if error:
                await JSONResponse({'request_id':uid(),'error':error.public(),'current_run':None},status_code=error.status)(scope,receive,send);return
        delivered=False
        async def replay():
            nonlocal delivered
            if mutation and not delivered:
                delivered=True
                return {'type':'http.request','body':bytes(body),'more_body':False}
            return await receive()
        async def secure_send(message):
            if message['type']=='http.response.start':
                message['headers']=list(message.get('headers',[]))+[
                    (b'content-security-policy',b"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"),
                    (b'x-content-type-options',b'nosniff'),(b'referrer-policy',b'no-referrer'),(b'cache-control',b'no-store')]
            await send(message)
        await self.app(scope,replay,secure_send)


def create_app(settings=None,engine_factory=None):
    settings=settings or Settings.environment()
    store=Store(settings);token=secrets.token_urlsafe(32)
    engine=engine_factory(store) if engine_factory else Engine(store)
    @asynccontextmanager
    async def lifespan(app):
        lock=ProcessLock(settings.data_dir/'server.lock')
        try:
            engine.start();yield
        finally:
            engine.close();lock.close()
    app=FastAPI(title='Wireless Assistant',version='0.1.0',lifespan=lifespan,docs_url=None,redoc_url=None,openapi_url=None)
    app.state.store=store;app.state.engine=engine;app.state.csrf=token
    app.add_middleware(Guard,settings=settings,token=token)

    @app.exception_handler(AppError)
    async def app_error(request,exc):
        return JSONResponse({'request_id':uid(),'error':exc.public(),'current_run':None},status_code=exc.status)
    @app.exception_handler(RequestValidationError)
    async def validation_error(request,exc):
        return JSONResponse({'request_id':uid(),'error':AppError('INVALID_INPUT','Request fields are missing or invalid.',422).public(),'current_run':None},status_code=422)
    @app.exception_handler(sqlite3.Error)
    async def database_error(request,exc):
        return JSONResponse({'request_id':uid(),'error':AppError('STORAGE_UNAVAILABLE','Storage is unavailable; retry status before submitting again.',503,True).public(),'current_run':None},status_code=503)
    @app.exception_handler(Exception)
    async def internal_error(request,exc):
        return JSONResponse({'request_id':uid(),'error':AppError('INTERNAL_ERROR','The request failed safely.',500).public(),'current_run':None},status_code=500)

    def success(data,status=200):
        return JSONResponse({'request_id':uid(),'data':data},status_code=status)
    def command(request,body,action,status=200):
        result,fresh=store.command(request.headers.get('idempotency-key'),request.method+' '+request.url.path,body,action)
        return result,fresh
    def session_dto(db,sid):
        s=store.session(db,sid)
        active=row(db,"SELECT run_id FROM request_runs WHERE session_id=? AND status IN ('ACTIVE','WAITING_USER')",(sid,))
        return {k:s[k] for k in ('session_id','title','created_at','updated_at','state_version')}|{'active_run':store.public_run(active['run_id'],db) if active else None}

    @app.get('/')
    def index():
        return FileResponse(Path(__file__).with_name('static')/'index.html')
    @app.get('/static/{name}')
    def asset(name:str):
        if name not in ('app.js','style.css'):
            raise AppError('NOT_FOUND','Asset not found.',404)
        return FileResponse(Path(__file__).with_name('static')/name)
    @app.get('/api/bootstrap')
    def bootstrap():
        return success({'csrf_token':token,'version':'0.1.0','input_limit':settings.max_input_bytes})
    @app.get('/api/health')
    def health():
        with store.read() as db:
            db.execute('SELECT 1')
        provider=bool(os.environ.get('GEMINI_API_KEY')) and os.environ.get('WA_FREE_TIER_CONFIRMED')=='1'
        corpus=engine.corpus.status()
        return success({'alive':True,'ready':provider and corpus['ready'] and not engine.degraded,
                        'provider_configured':provider,'provider_live_tested':False,'corpus_ready':corpus['ready'],
                        'worker_available':not engine.degraded,'release':'18','version':'0.1.0'})
    @app.get('/api/corpus/status')
    def corpus_status():
        return success(engine.corpus.status())
    @app.post('/api/sessions')
    def create_session(body:NewSession,request:Request):
        def action(db):
            if db.execute('SELECT COUNT(*) FROM sessions').fetchone()[0]>=1000:
                raise AppError('CHAT_COUNT_LIMIT','The saved-chat limit is reached. Delete an unused chat first.',429)
            sid=uid();title=(body.title or 'New chat').strip() or 'New chat'
            insert(db,'sessions',session_id=sid,title=title,created_at=now(),updated_at=now())
            return session_dto(db,sid),sid,None
        result,_=command(request,body.model_dump(),action)
        return success(result,201)
    @app.get('/api/sessions')
    def sessions(query:str='',cursor:int=0,limit:int=30):
        if len(query)>200 or cursor<0 or not 1<=limit<=50:
            raise AppError('PAGE_LIMIT','Invalid search or pagination.')
        with store.read() as db:
            rows=db.execute('SELECT session_id FROM sessions WHERE deleted_at IS NULL AND (instr(lower(title),lower(?))>0 OR EXISTS(SELECT 1 FROM messages m WHERE m.session_id=sessions.session_id AND instr(lower(m.content_text),lower(?))>0)) ORDER BY created_at,session_id LIMIT ? OFFSET ?',(query,query,limit+1,cursor)).fetchall()
            return success({'items':[session_dto(db,r[0]) for r in rows[:limit]],'next_cursor':cursor+limit if len(rows)>limit else None})
    @app.get('/api/sessions/{sid}')
    def get_session(sid:str):
        with store.read() as db:
            return success(session_dto(db,sid))
    @app.patch('/api/sessions/{sid}')
    def rename(sid:str,body:Rename,request:Request):
        def action(db):
            s=store.session(db,sid)
            if s['state_version']!=body.expected_session_version or not body.title.strip():
                raise AppError('STALE_SESSION','Chat changed or title is empty. Refresh and retry.',409)
            db.execute('UPDATE sessions SET title=?,state_version=state_version+1,updated_at=? WHERE session_id=?',(body.title.strip(),now(),sid))
            return session_dto(db,sid),sid,None
        result,_=command(request,body.model_dump(),action);return success(result)
    @app.get('/api/sessions/{sid}/messages')
    def messages(sid:str,cursor:int=-1,limit:int=50,latest:bool=False,before:int|None=None):
        if cursor< -1 or not 1<=limit<=50:
            raise AppError('PAGE_LIMIT','Invalid message pagination.')
        with store.read() as db:
            store.session(db,sid)
            if latest or before is not None:
                if before is not None and before<0:
                    raise AppError('PAGE_LIMIT','Invalid history cursor.')
                rows=[dict(r) for r in db.execute('SELECT message_id,sequence,role,content_text,created_at FROM messages WHERE session_id=? AND sequence<? ORDER BY sequence DESC LIMIT ?',(sid,before if before is not None else 100000000,limit+1))]
                older=len(rows)>limit
                rows=list(reversed(rows[:limit]))
                previous_cursor=rows[0]['sequence'] if rows and older else None
            else:
                rows=[dict(r) for r in db.execute('SELECT message_id,sequence,role,content_text,created_at FROM messages WHERE session_id=? AND sequence>? ORDER BY sequence LIMIT ?',(sid,cursor,limit+1))]
                previous_cursor=None
            for m in rows[:limit]:
                r=row(db,'SELECT run_id,terminal_result_json FROM request_runs WHERE final_message_id=? ORDER BY created_at DESC LIMIT 1',(m['message_id'],))
                m['run_id']=r['run_id'] if r else None
                m['outcome']=json.loads(r['terminal_result_json']) if r and r['terminal_result_json'] else None
                if r and m['role']=='assistant':
                    candidate=row(db,'SELECT citations_json FROM candidates WHERE candidate_id=?',(m['outcome']['candidate_id'],))
                    m['citations']=json.loads(candidate['citations_json'])
            return success({'items':rows[:limit],'next_cursor':rows[limit-1]['sequence'] if len(rows)>limit else None,'previous_cursor':previous_cursor})
    @app.post('/api/sessions/{sid}/messages')
    def submit(sid:str,body:Message,request:Request):
        def action(db):
            engine.available()
            return store.admit(db,sid,body.text)
        result,fresh=command(request,body.model_dump(),action)
        if fresh:engine.launch(result['run_id'])
        return success(result,202)
    @app.delete('/api/sessions/{sid}')
    def delete(sid:str,request:Request):
        def action(db):
            s=row(db,'SELECT session_id FROM sessions WHERE session_id=?',(sid,))
            if s:
                for r in db.execute("SELECT * FROM request_runs WHERE session_id=? AND status IN ('ACTIVE','WAITING_USER')",(sid,)).fetchall():
                    engine.cancel_worker(r['run_id'])
                    store.finish_in(db,dict(r),'CANCELED','DELETED','Chat deleted.')
                db.execute('DELETE FROM sessions WHERE session_id=?',(sid,))
            return {'deleted':True},None,None
        result,_=command(request,{},action);return success(result)
    @app.get('/api/runs/{rid}')
    def run_status(rid:str):
        return success(store.public_run(rid))
    @app.post('/api/runs/{rid}/clarifications/{cid}/reply')
    def reply(rid:str,cid:str,body:Reply,request:Request):
        def action(db):
            engine.available()
            return store.reply(db,rid,cid,body.text,body.expected_run_version)
        result,fresh=command(request,body.model_dump(),action)
        if fresh:engine.launch(rid)
        return success(result,202)
    @app.post('/api/runs/{rid}/cancel')
    def cancel(rid:str,body:Empty,request:Request):
        def action(db):
            r=store.run(rid,db)
            store.finish_in(db,r,'CANCELED','USER_CANCELED','Processing canceled by you.')
            return store.public_run(rid,db),r['session_id'],rid
        result,_=command(request,{},action);engine.cancel_worker(rid);return success(result)
    @app.post('/api/runs/{rid}/retry')
    def retry(rid:str,body:Empty,request:Request):
        def action(db):
            engine.available();r=store.run(rid,db)
            return store.admit(db,r['session_id'],retry=rid)
        result,fresh=command(request,{},action)
        if fresh:engine.launch(result['run_id'])
        return success(result,202)
    @app.get('/api/runs/{rid}/evidence/{eid}/{pid}')
    def evidence(rid:str,eid:str,pid:str):
        with store.read() as db:
            r=store.run(rid,db)
            outcome=json.loads(r['terminal_result_json']) if r['terminal_result_json'] else {}
            if outcome.get('evidence_set_id')!=eid:
                raise AppError('NOT_FOUND','Evidence is not bound to a displayed answer.',404)
            e=row(db,'SELECT * FROM evidence_sets WHERE run_id=? AND evidence_set_id=?',(rid,eid))
            for p in json.loads(e['passages_snapshot_json'])['passages']:
                if p['passage_id']==pid:
                    return success(p)
            raise AppError('NOT_FOUND','Passage not found in this answer.',404)
    @app.post('/api/feedback')
    def feedback(body:Feedback,request:Request):
        def action(db):
            r=store.run(body.run_id,db)
            outcome=json.loads(r['terminal_result_json']) if r['terminal_result_json'] else {}
            if outcome.get('candidate_id')!=body.candidate_id:
                raise AppError('INVALID_FEEDBACK','Feedback must refer to the displayed answer.',409)
            fid=uid()
            insert(db,'feedback',feedback_id=fid,session_id=r['session_id'],run_id=body.run_id,candidate_id=body.candidate_id,review_id=outcome['review_id'],category=body.category,comment=body.comment,created_at=now())
            return {'feedback_id':fid},r['session_id'],body.run_id
        result,_=command(request,body.model_dump(),action);return success(result,201)
    @app.get('/api/runs/{rid}/events')
    async def events(rid:str,request:Request):
        store.run(rid)
        last=request.headers.get('last-event-id','')
        sequence=-1
        if last:
            parts=last.split(':')
            if len(parts)!=2 or parts[0]!=rid or not parts[1].isdigit():
                raise AppError('EVENT_CURSOR','Invalid event cursor.')
            sequence=int(parts[1])
        async def stream():
            nonlocal sequence
            # One stream lives at most 30 seconds; reconnect is UI-controlled and bounded.
            started=time.monotonic()
            while time.monotonic()-started<30:
                if await request.is_disconnected():return
                try:
                    with store.read() as db:
                        status=store.public_run(rid,db)
                        rows=[dict(r) for r in db.execute('SELECT * FROM run_events WHERE run_id=? AND sequence>? ORDER BY sequence LIMIT 100',(rid,sequence))]
                    if rows and rows[0]['sequence']>sequence+1:
                        yield 'event: resync\ndata: {}\n\n';return
                    for r in rows:
                        sequence=r['sequence']
                        payload={'event_id':f'{rid}:{sequence}','run_id':rid,'state_version':status['state_version'],'type':r['event_type'],'payload':json.loads(r['safe_payload_json'])}
                        yield f'id: {rid}:{sequence}\nevent: update\ndata: {canonical(payload)}\n\n'
                    if status['status']!='ACTIVE':return
                    yield 'event: heartbeat\ndata: '+canonical(status)+'\n\n'
                except (AppError,sqlite3.Error):
                    yield 'event: unavailable\ndata: {}\n\n';return
                await asyncio.sleep(1)
        return StreamingResponse(stream(),media_type='text/event-stream',headers={'X-Accel-Buffering':'no'})
    return app

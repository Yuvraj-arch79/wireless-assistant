"""Explicit, bounded A/B/C state machine with independently supervised workers."""
import json
import os
import sqlite3
import threading
import time
from .bounded import bounded
from .common import AppError, canonical, digest, load_json, now, token_bound, uid
from .contracts import ADAPTERS
from .corpus import Corpus, search_worker
from .prompts import instructions
from .provider import generate, embed
from .store import Store, insert, row, TERMINAL
from .validation import validate_need, validate_draft, validate_review, require
from .local_tools import local_tool_worker


class Engine:
    def __init__(self,store,role_transport=None,embedding_transport=None,require_ready=True):
        self.store,self.settings,self.corpus=store,store.settings,Corpus(store)
        self.role_transport=role_transport
        self.embedding_transport=embedding_transport
        self.require_ready=require_ready
        self.workers={};self.lock=threading.RLock();self.closed=threading.Event();self.degraded=False
        self.supervisor=None

    def start(self):
        self.store.recover()
        self.supervisor=threading.Thread(target=self._watch,name='wireless-supervisor',daemon=True)
        self.supervisor.start()

    def close(self):
        self.closed.set()
        with self.lock:
            workers=list(self.workers.items())
        for rid,w in workers:
            w['stop'].set()
            try:
                self.store.stop(rid,'INTERRUPTED','SHUTDOWN','Processing stopped during application shutdown. Retry explicitly.',w['epoch'],self.elapsed(w))
            except (AppError,sqlite3.Error):
                pass
        deadline=time.monotonic()+2
        for _,w in workers:
            w['thread'].join(max(0,deadline-time.monotonic()))
        if self.supervisor:
            self.supervisor.join(timeout=1)

    def available(self):
        if self.closed.is_set() or self.degraded:
            raise AppError('WORKER_UNAVAILABLE','Processing is unavailable. Restart the application.',503)
        if self.require_ready:
            if not os.environ.get('GEMINI_API_KEY') or os.environ.get('WA_FREE_TIER_CONFIRMED')!='1':
                raise AppError('PROVIDER_NOT_CONFIGURED','Configure the free API project on the server before starting AI chat.',503)
            if not self.corpus.status()['ready']:
                raise AppError('CORPUS_NOT_READY','Prepare and activate the hybrid corpus before starting AI chat.',503)

    def launch(self,rid):
        with self.lock:
            r,_=self.store.state(rid)
            if r['status']!='ACTIVE':
                return
            old=self.workers.get(rid)
            if old and old['epoch']==r['worker_epoch']:
                return
            if old:
                old['stop'].set()
                # WAITING_USER has already fenced the old worker. A fast reply
                # may arrive before its finally block; do not lose the resume.
                self.workers.pop(rid)
            if self.closed.is_set() or self.degraded or len(self.workers)>=self.settings.max_active:
                self.store.stop(rid,'INTERRUPTED','DISPATCH_FAILED','No worker was available. Retry explicitly.')
                return
            w={'epoch':r['worker_epoch'],'stop':threading.Event(),'started':time.monotonic(),
               'base_ms':r['active_elapsed_ms'],'budget_ms':r['active_budget_ms']}
            thread=threading.Thread(target=self._run,args=(rid,w),name='wireless-run',daemon=True)
            w['thread']=thread;self.workers[rid]=w;thread.start()

    def cancel_worker(self,rid):
        with self.lock:
            if rid in self.workers:
                self.workers[rid]['stop'].set()

    def elapsed(self,w):
        return w['base_ms']+int((time.monotonic()-w['started'])*1000)

    def remaining(self,w):
        return (w['budget_ms']-self.elapsed(w))/1000

    def stopped(self,w):
        return self.closed.is_set() or w['stop'].is_set() or self.remaining(w)<=0

    def _watch(self):
        while not self.closed.wait(0.2):
            with self.lock:
                items=list(self.workers.items())
            for rid,w in items:
                if self.remaining(w)<=0:
                    w['stop'].set()
                    try:
                        self.store.stop(rid,'TIMED_OUT','ACTIVE_DEADLINE','Processing reached its time limit. No unchecked answer was released.',w['epoch'],self.elapsed(w))
                    except (AppError,sqlite3.Error):
                        self.degraded=True
            # A committed request with no scheduled worker cannot remain ACTIVE forever.
            try:
                with self.store.read() as db:
                    abandoned=[dict(r) for r in db.execute("SELECT run_id,segment_started_at FROM request_runs WHERE status='ACTIVE'")]
                from datetime import datetime, timezone
                for r in abandoned:
                    with self.lock:
                        known=r['run_id'] in self.workers
                    age=(datetime.now(timezone.utc)-datetime.fromisoformat(r['segment_started_at'])).total_seconds()
                    if not known and age>10:
                        self.store.stop(r['run_id'],'INTERRUPTED','DISPATCH_LOST','Processing could not be scheduled. Retry explicitly.')
            except (AppError,sqlite3.Error):
                self.degraded=True

    def _run(self,rid,w):
        try:
            self.drive(rid,w)
        except AppError as exc:
            if exc.code=='CLEANUP_FAILED':
                self.degraded=True
            if exc.code not in ('STALE_WORK','NOT_FOUND'):
                status='TIMED_OUT' if self.remaining(w)<=0 or exc.code in ('OPERATION_TIMEOUT','BUDGET_EXHAUSTED') else 'FAILED'
                try:
                    self.store.stop(rid,status,exc.code,exc.message,w['epoch'],self.elapsed(w))
                except (AppError,sqlite3.Error):
                    self.degraded=True
        except Exception:
            try:
                self.store.stop(rid,'FAILED','INTERNAL_ERROR','Processing failed safely. No unchecked answer was released.',w['epoch'],self.elapsed(w))
            except (AppError,sqlite3.Error):
                self.degraded=True
        finally:
            with self.lock:
                if self.workers.get(rid) is w:
                    self.workers.pop(rid,None)

    def call(self,rid,w,role,payload,validate=lambda value:None):
        system=instructions(role)
        request_size=token_bound(system+canonical(payload))
        if request_size>self.settings.role_input_bound:
            raise AppError('CONTEXT_LIMIT','Required context is too large. Narrow the question; essential details were not dropped.',413)
        retry=False;repair=False
        while True:
            if self.stopped(w):
                raise AppError('STOPPED','Processing stopped.',409)
            counters=json.loads(self.store.run(rid)['counters_json'])
            # Reserve one final B+C pair; repairs/retries cannot spend it as A.
            keep=2 if role=='A' else 1 if role=='B' else 0
            if (self.settings.max_calls-counters['provider_calls']<=keep or
                self.settings.total_token_bound-counters['charged_tokens'] < request_size+self.settings.role_output_tokens+keep*(self.settings.role_input_bound+self.settings.role_output_tokens)):
                raise AppError('BUDGET_EXHAUSTED','Insufficient budget for a checked answer. Retry explicitly with a narrower question.',504)
            op=self.store.reserve(rid,w['epoch'],role,digest(payload),request_size+self.settings.role_output_tokens,retry,repair, min(self.settings.call_seconds,self.remaining(w)))
            try:
                if self.role_transport:
                    response=self.role_transport(role,payload)
                else:
                    response=bounded(generate,(getattr(self.settings,'model_'+role.lower()),system,payload,self.settings.role_output_tokens),min(self.settings.call_seconds,self.remaining(w)),lambda:self.stopped(w))
                self.store.operation_done(rid,w['epoch'],op)
            except AppError as exc:
                self.store.operation_done(rid,w['epoch'],op,exc.code)
                if not retry and exc.retryable and exc.code!='PROVIDER_QUOTA' and self.remaining(w)>self.settings.call_seconds:
                    retry=True;continue
                raise
            try:
                raw=load_json(response['text'])
                value=ADAPTERS[role].validate_python(raw).model_dump(mode='json')
                validate(value)
                return value
            except (ValueError,TypeError,KeyError,AppError) as exc:
                r=self.store.run(rid)
                counters=json.loads(r['counters_json'])
                if counters['format_repairs']>=self.settings.max_repairs or repair:
                    raise AppError('INVALID_CONTRACT','The AI response failed validation; no unchecked draft was released.',502) from None
                payload={**payload,'contract_error':str(exc)[:700]}
                request_size=token_bound(system+canonical(payload))
                if request_size>self.settings.role_input_bound:
                    raise AppError('CONTEXT_LIMIT','Required repair context exceeds the limit.',413)
                repair=True

    def collect_context(self,rid,state):
        context,compact=self.store.context(rid,state['history_refs'])
        r=self.store.run(rid)
        evidence=self.corpus.get(r['corpus_build_id'],state['passage_ids']) if state['passage_ids'] else []
        return context,compact,evidence

    def payload(self,rid,state,context,compact,evidence):
        r=self.store.run(rid)
        return {'envelope':{'run_id':rid,'session_id':r['session_id'],'worker_epoch':r['worker_epoch'],
                           'state_version':r['state_version'],'config_snapshot_id':r['config_hash'],'corpus_build_id':r['corpus_build_id'],
                           'round_number':state['round']},
                'original_context':context['originals'],'excluded_history_map':compact,
                'need':state.get('need'),'evidence':evidence,'tool_results':state['tool_results'],
                'coverage_gaps':state['gaps'],'closing_mode':state['closing'],'budget':json.loads(r['counters_json']),
                'b_gap':state.get('b_gap'),'prior_candidate':state['prior_candidate'], 'prior_review':state['review'],
                'corpus_inventory':self.inventory(r['corpus_build_id']),
                'extraction_policy':'Excluded passages, diagrams and formula transcription are not verified evidence. State missing coverage; never reconstruct missing mathematical symbols.'}

    def inventory(self,build):
        with self.store.read() as db:
            return [dict(r) for r in db.execute('SELECT d.spec_number,d.version,d.release,count(p.passage_id) AS passages,sum(p.unreadable) AS excluded_passages FROM source_documents d LEFT JOIN passages p ON p.document_id=d.document_id WHERE d.build_id=? GROUP BY d.document_id',(build,))]

    def closing(self,rid,w,state):
        r=self.store.run(rid);c=json.loads(r['counters_json'])
        reserve=2*(self.settings.role_input_bound+self.settings.role_output_tokens)
        return state['closing'] or self.settings.max_calls-c['provider_calls']<=3 or self.settings.total_token_bound-c['charged_tokens']<=reserve+self.settings.role_input_bound or self.remaining(w)<=2*self.settings.call_seconds+5

    def drive(self,rid,w):
        while not self.stopped(w):
            r,state=self.store.state(rid)
            if r['status']!='ACTIVE' or r['worker_epoch']!=w['epoch']:
                return
            step_op=self.store.reserve(rid,w['epoch'],'controller',digest({'phase':state['phase'],'round':state['round']}))
            self.store.operation_done(rid,w['epoch'],step_op)
            state['closing']=self.closing(rid,w,state)
            self.store.save_state(rid,w['epoch'],state,state['phase'])
            context,compact,evidence=self.collect_context(rid,state)
            payload=self.payload(rid,state,context,compact,evidence)
            if state['phase']=='A':
                def valid_a(a):
                    if a.get('need'):
                        validate_need(a['need'],context['originals'])
                    if a['action']=='ready_for_b':
                        require(not any(g['kind']=='user_detail' for g in a['need']['unresolved_gaps']),'Essential ambiguity requires clarification.')
                result=self.call(rid,w,'A',payload,valid_a)
                if result['action']=='out_of_scope':
                    self.store.stop(rid,'COMPLETED','OUT_OF_SCOPE','This assistant covers the declared 3GPP NR collection. Please ask a question within that scope.',w['epoch'],self.elapsed(w));return
                state['need']=result['need'];state['gaps']=result['coverage_gaps']
                scope=state['need']['scope']
                # A material scope correction cannot retain now-incompatible passages.
                state['passage_ids']=[p['passage_id'] for p in evidence if
                    (not scope['release'] or p['release']==scope['release']) and
                    (not scope['spec_numbers'] or p['spec_number'] in scope['spec_numbers']) and
                    (not scope['document_versions'] or p['document_version'] in scope['document_versions'])]
                state['need_id']=self.store.save_need(rid,w['epoch'],state['need'])
                if result['intent_relation']=='new_topic' and r['current_need_id']:
                    self.store.stop(rid,'COMPLETED','INABILITY','Your reply appears to start a different topic. Send that question as a new message so its requirements stay separate.',w['epoch'],self.elapsed(w));return
                if result['action']=='clarify':
                    self.store.save_state(rid,w['epoch'],state)
                    self.store.wait_user(rid,w['epoch'],result['clarification'],self.elapsed(w));return
                if result['action']=='collect' and not state['closing']:
                    state['tool_results']=[]
                    for tool in result['requests']:
                        if self.closing(rid,w,state):
                            state['closing']=True
                            break
                        self.tool(rid,w,state,tool)
                    state['phase']='A'
                else:
                    if state['need']['scope']['release'] is None:
                        state['need']['scope'].update(release='18',default_used=True)
                        state['need_id']=self.store.save_need(rid,w['epoch'],state['need'])
                    state['phase']='B'
                self.store.save_state(rid,w['epoch'],state)
            elif state['phase']=='B':
                if not evidence:
                    self.store.stop(rid,'COMPLETED','INABILITY','No supporting passages were collected from the selected corpus. Narrow the question or specify a clause.',w['epoch'],self.elapsed(w));return
                # Freeze the exact B input. C receives this same context and evidence.
                binding=self.freeze(rid,w,state,context,evidence)
                payload['input_binding']=binding
                result=self.call(rid,w,'B',payload,lambda b:validate_draft(b,state['need'],evidence,state['review']) if b['action']=='submit_draft' else None)
                if result['action']=='cannot_answer':
                    self.store.stop(rid,'COMPLETED','INABILITY','The available evidence is insufficient for a supported answer. Narrow the question or supply the missing detail.',w['epoch'],self.elapsed(w));return
                if result['action']=='request_missing_info':
                    if state['closing'] or state['missing_by_round'][state['round']]>=1:
                        self.store.stop(rid,'COMPLETED','INABILITY','A necessary detail is still missing and the collection allowance is exhausted. Narrow the question and retry explicitly.',w['epoch'],self.elapsed(w));return
                    state['missing_by_round'][state['round']]+=1
                    state['b_gap']=result['missing_info'];state['phase']='A'
                else:
                    cid=self.save_candidate(rid,w,state,result,binding)
                    binding.update(candidate_id=cid,candidate_hash=digest(result))
                    state.update(candidate=result,binding=binding,phase='C',frozen_context=context,frozen_evidence=evidence)
                self.store.save_state(rid,w['epoch'],state)
            elif state['phase']=='C':
                candidate=state['candidate'];binding=state['binding'];evidence=state['frozen_evidence']
                payload=self.payload(rid,state,state['frozen_context'],[],evidence)
                payload.update(candidate=candidate,reviewed_binding=binding)
                result=self.call(rid,w,'C',payload,lambda c:validate_review(c,binding,candidate,state['need'],evidence,state['prior_candidate'],state['round']))
                if result['decision'] in ('accepted','partial_accepted'):
                    self.release(rid,w,state,result);return
                self.save_review(rid,w,state,result)
                if state['round']>=2:
                    self.store.stop(rid,'COMPLETED','INABILITY','The answer did not pass review within two correction rounds. No failed draft was released.',w['epoch'],self.elapsed(w));return
                if state['review']:
                    before={(f['finding_type'],f['target_claim_or_req']) for f in state['review']['findings'] if f['blocking']}
                    after={(f['finding_type'],f['target_claim_or_req']) for f in result['findings'] if f['blocking']}
                    if before==after:
                        state['closing']=True
                state.update(prior_candidate={'candidate_id':binding['candidate_id'],**candidate},review=result,round=state['round']+1,phase='B',b_gap=None)
                self.store.save_state(rid,w['epoch'],state)
            else:
                raise AppError('INVALID_STATE','Controller state is invalid.',503)
        raise AppError('OPERATION_TIMEOUT','Processing reached its time limit.',504,True)

    def tool(self,rid,w,state,tool):
        r=self.store.run(rid);kind=tool['kind']
        require(set(tool['requirement_ids'])<={q['req_id'] for q in state['need']['requirements']},'Tool targets unknown requirements.')
        identity={k:v for k,v in tool.items() if k not in ('purpose','requirement_ids','limit')}
        if 'query' in identity:
            identity['query']=' '.join(identity['query'].lower().split())
        identity['build_id']=r['corpus_build_id']
        fingerprint=digest(identity)
        if fingerprint in state['searches']:
            state['closing']=True
            state['tool_results'].append({'status':'limited','items':[],'reason':'Equivalent request already attempted.'});return
        state['searches'].append(fingerprint)
        op=self.store.reserve(rid,w['epoch'],kind,fingerprint)
        items=[];next_cursor=None
        if kind=='corpus_search':
            filters=tool['filters'];scope=state['need']['scope']
            require(not scope['release'] or filters['release']==scope['release'],'Search cannot change the requested release.')
            require(not scope['spec_numbers'] or bool(filters['spec_numbers']) and set(filters['spec_numbers'])<=set(scope['spec_numbers']),'Search cannot widen requested specifications.')
            require(not scope['document_versions'] or bool(filters['document_versions']) and set(filters['document_versions'])<=set(scope['document_versions']),'Search cannot widen requested versions.')
            v=None
            if self.corpus.ready(r['corpus_build_id']):
                embed_op=self.store.reserve(rid,w['epoch'],'embedding',fingerprint,token_bound(tool['query']))
                if self.embedding_transport:
                    v=self.embedding_transport(tool['query'])
                else:
                    v=bounded(embed,(self.settings.embedding_model,tool['query'],self.settings.embedding_dimensions),min(self.settings.call_seconds,self.remaining(w)),lambda:self.stopped(w))
                self.store.operation_done(rid,w['epoch'],embed_op)
            items=bounded(search_worker,(str(self.store.path),self.settings.snapshot(),r['corpus_build_id'],tool['query'],filters,tool['limit'],v),min(self.settings.tool_seconds,self.remaining(w)),lambda:self.stopped(w))
        elif kind=='expand_passages':
            require(set(tool['passage_ids'])<=set(state['passage_ids']),'Only retrieved passages may be expanded.')
            if state['expansion_depth']>=2:
                state['closing']=True
            else:
                state['expansion_depth']+=1
                items,next_cursor=bounded(local_tool_worker,(str(self.store.path),self.settings.snapshot(),r['session_id'],r['corpus_build_id'],tool),min(self.settings.tool_seconds,self.remaining(w)),lambda:self.stopped(w))
        elif kind in ('history_search','history_fetch'):
            items,next_cursor=bounded(local_tool_worker,(str(self.store.path),self.settings.snapshot(),r['session_id'],r['corpus_build_id'],tool),min(self.settings.tool_seconds,self.remaining(w)),lambda:self.stopped(w))
        if kind=='history_fetch':
            for item in items:
                if item['ref'] not in state['history_refs']:
                    state['history_refs'].append(item['ref'])
        if kind in ('corpus_search','expand_passages'):
            existing=self.corpus.get(r['corpus_build_id'],state['passage_ids']) if state['passage_ids'] else []
            used=sum(token_bound(p['text']) for p in existing)
            scope=state['need']['scope'];new=[]
            for p in items:
                if p['unreadable'] or p['passage_id'] in state['passage_ids']:
                    continue
                if scope['release'] and p['release']!=scope['release'] or scope['spec_numbers'] and p['spec_number'] not in scope['spec_numbers'] or scope['document_versions'] and p['document_version'] not in scope['document_versions']:
                    continue
                if len(state['passage_ids'])>=self.settings.max_passages or used+token_bound(p['text'])>self.settings.evidence_bound:
                    state['closing']=True;continue
                state['passage_ids'].append(p['passage_id']);used+=token_bound(p['text']);new.append(p['passage_id'])
            with self.store.transaction() as db:
                self.store.owned(db,rid,w['epoch'])
                insert(db,'retrieval_records',retrieval_id=uid(),run_id=rid,need_id=state['need_id'],query_fingerprint=fingerprint,request_json=canonical(tool),result_json=canonical({'passage_ids':[p['passage_id'] for p in items]}),new_passage_count=len(new),created_at=now())
            items=[{'passage_id':p['passage_id'],'clause_id':p['clause_id'],'spec_number':p['spec_number']} for p in items]
        state['tool_results'].append({'operation_id':op,'status':'ok' if items else 'empty','items':items,'next_cursor':next_cursor,'gaps':[],'error':None})
        self.store.operation_done(rid,w['epoch'],op)

    def freeze(self,rid,w,state,context,evidence):
        with self.store.transaction() as db:
            r=self.store.owned(db,rid,w['epoch']);cid,eid=uid(),uid()
            # Bind complete excluded-history references even if the compact prompt map is smaller.
            insert(db,'context_snapshots',context_id=cid,run_id=rid,context_hash=digest(context),selected_originals_json=canonical(context['originals']),excluded_index_refs_json=canonical(context['excluded_history_refs']),created_at=now())
            snapshot={'passages':evidence,'coverage_gaps':state['gaps']}
            insert(db,'evidence_sets',evidence_set_id=eid,run_id=rid,build_id=r['corpus_build_id'],evidence_hash=digest(snapshot),passages_snapshot_json=canonical(snapshot),created_at=now())
            db.execute('UPDATE request_runs SET current_evidence_set_id=? WHERE run_id=?',(eid,rid))
            return {'need_id':state['need_id'],'need_hash':digest(state['need']),'evidence_set_id':eid,'evidence_hash':digest(snapshot),'context_id':cid,'context_hash':digest(context)}

    def save_candidate(self,rid,w,state,candidate,binding):
        with self.store.transaction() as db:
            self.store.owned(db,rid,w['epoch']);cid=uid()
            insert(db,'candidates',candidate_id=cid,run_id=rid,need_id=binding['need_id'],evidence_set_id=binding['evidence_set_id'],context_id=binding['context_id'],round_number=state['round'],content_hash=digest(candidate),answer_markdown=candidate['answer_markdown'],citations_json=canonical(candidate['citations']),covered_json=canonical(candidate['covered_requirements']),unresolved_json=canonical(candidate['unresolved_requirements']),limitation_statement=candidate['limitation_statement'],revision_log_json=canonical(candidate['revision_log']),basic_checks_passed=1,created_at=now())
            return cid

    def review_in(self,db,rid,state,review):
        b=state['binding'];review_id=uid()
        insert(db,'reviews',review_id=review_id,run_id=rid,candidate_id=b['candidate_id'],need_id=b['need_id'],evidence_set_id=b['evidence_set_id'],context_id=b['context_id'],candidate_hash=b['candidate_hash'],decision=review['decision'],satisfied_json=canonical(review['satisfied_requirements']),unmet_json=canonical(review['unmet_requirements']),findings_json=canonical(review['findings']),blocking_count=sum(f['blocking'] for f in review['findings']),regression_check_json=canonical(review['regression_check']),created_at=now())
        return review_id

    def save_review(self,rid,w,state,review):
        with self.store.transaction() as db:
            self.store.owned(db,rid,w['epoch']);self.review_in(db,rid,state,review)

    def release(self,rid,w,state,review):
        if self.stopped(w):
            raise AppError('STOPPED','The request stopped before publication.',409)
        with self.store.transaction() as db:
            r=self.store.owned(db,rid,w['epoch']);b=state['binding']
            require(self.remaining(w)>0,'Deadline expired before publication.')
            require(r['current_need_id']==b['need_id'] and r['current_evidence_set_id']==b['evidence_set_id'],'Current inputs changed before publication.')
            stored=row(db,'SELECT * FROM candidates WHERE candidate_id=? AND run_id=?',(b['candidate_id'],rid))
            need=row(db,'SELECT * FROM needs WHERE need_id=? AND run_id=?',(b['need_id'],rid))
            evidence=row(db,'SELECT * FROM evidence_sets WHERE evidence_set_id=? AND run_id=?',(b['evidence_set_id'],rid))
            context=row(db,'SELECT * FROM context_snapshots WHERE context_id=? AND run_id=?',(b['context_id'],rid))
            require(stored and stored['content_hash']==digest(state['candidate'])==b['candidate_hash'],'Stored candidate changed.')
            require(need['need_hash']==b['need_hash'] and evidence['evidence_hash']==b['evidence_hash'] and context['context_hash']==b['context_hash'],'Stored input bindings changed.')
            validate_draft(state['candidate'],state['need'],state['frozen_evidence'],state['review'])
            validate_review(review,b,state['candidate'],state['need'],state['frozen_evidence'],state['prior_candidate'],state['round'])
            review_id=self.review_in(db,rid,state,review)
            self.store.finish_in(db,r,'COMPLETED',review['decision'].upper(),stored['answer_markdown'],self.elapsed(w),
                                 {'candidate_id':b['candidate_id'],'review_id':review_id,'evidence_set_id':b['evidence_set_id']})

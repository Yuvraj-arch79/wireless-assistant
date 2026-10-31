"""Short SQLite transactions. All asynchronous publications are epoch fenced."""
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
import re
import sqlite3
import time
from .common import AppError, canonical, digest, now, text_hash, token_bound, uid

TERMINAL = {"COMPLETED", "CANCELED", "FAILED", "TIMED_OUT", "INTERRUPTED"}


def insert(db, table, **values):
    # Table/column identifiers are backend constants only.
    columns = ','.join(values)
    db.execute(f"INSERT INTO {table} ({columns}) VALUES ({','.join('?' for _ in values)})", tuple(values.values()))


def row(db, sql, args=()):
    result = db.execute(sql, args).fetchone()
    return dict(result) if result else None


class Store:
    def __init__(self, settings):
        self.settings = settings
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        self.path = settings.database
        self.initialize()

    def connect(self):
        db = sqlite3.connect(self.path, timeout=2)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('PRAGMA busy_timeout=2000')
        db.execute('PRAGMA secure_delete=ON')
        deadline=time.monotonic()+self.settings.tool_seconds
        db.set_progress_handler(lambda: int(time.monotonic()>deadline),10000)
        return db

    @contextmanager
    def transaction(self):
        db = self.connect()
        try:
            db.execute('BEGIN IMMEDIATE')
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    @contextmanager
    def read(self):
        db = self.connect()
        try:
            yield db
        finally:
            db.close()

    def initialize(self):
        with self.read() as db:
            db.execute('PRAGMA journal_mode=WAL')
            exists = db.execute("SELECT 1 FROM sqlite_master WHERE name='schema_versions'").fetchone()
            if not exists:
                scripts = Path(__file__).with_name('migrations')
                sql = '\n'.join(p.read_text(encoding='utf-8') for p in sorted(scripts.glob('*.sql')))
                db.executescript('BEGIN IMMEDIATE;\n' + sql + '\nINSERT INTO schema_versions VALUES (1, CURRENT_TIMESTAMP);\nCOMMIT;')
            versions = [r[0] for r in db.execute('SELECT version FROM schema_versions')]
            if versions != [1]:
                raise AppError('SCHEMA_VERSION', 'Database version is unsupported; use the documented backup/restore procedure.', 503)
            if db.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                raise AppError('DATABASE_CORRUPT', 'Database integrity check failed. Restore a checked backup.', 503)

    def backup(self, destination):
        destination = Path(destination)
        if destination.exists():
            raise AppError('BACKUP_EXISTS', 'Choose a new backup filename.')
        with self.read() as source, sqlite3.connect(destination) as target:
            source.backup(target)
            if target.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise AppError('BACKUP_INVALID', 'Backup integrity check failed.', 503)

    def command(self, key, route, body, action):
        if not isinstance(key, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{8,128}', key):
            raise AppError('IDEMPOTENCY_REQUIRED', 'Provide an Idempotency-Key of 8–128 safe characters.')
        request_hash = digest({'route': route, 'body': body})
        with self.transaction() as db:
            receipt = row(db, 'SELECT * FROM command_receipts WHERE idempotency_key=?', (key,))
            if receipt:
                if receipt['request_hash'] != request_hash or receipt['route'] != route:
                    raise AppError('KEY_CONFLICT', 'This command key was used for a different request.', 409)
                return json.loads(receipt['safe_response_json']), False
            result, sid, rid = action(db)
            insert(db, 'command_receipts', idempotency_key=key, session_id=sid, run_id=rid,
                   route=route, request_hash=request_hash, safe_response_json=canonical(result), created_at=now())
            return result, True

    def session(self, db, sid):
        s = row(db, 'SELECT * FROM sessions WHERE session_id=? AND deleted_at IS NULL', (sid,))
        if not s:
            raise AppError('NOT_FOUND', 'Chat not found.', 404)
        return s

    def run(self, rid, db=None):
        if db is None:
            with self.read() as conn:
                return self.run(rid, conn)
        r = row(db, 'SELECT * FROM request_runs WHERE run_id=?', (rid,))
        if not r:
            raise AppError('NOT_FOUND', 'Run not found.', 404)
        self.session(db, r['session_id'])
        return r

    def owned(self, db, rid, epoch):
        r = self.run(rid, db)
        if r['status'] != 'ACTIVE' or r['worker_epoch'] != epoch:
            raise AppError('STALE_WORK', 'Work is no longer active.', 409)
        return r

    def message(self, db, sid, turn, role, text):
        mid = uid()
        sequence = db.execute('SELECT COALESCE(MAX(sequence),-1)+1 FROM messages WHERE session_id=?', (sid,)).fetchone()[0]
        insert(db, 'messages', message_id=mid, session_id=sid, sequence=sequence, turn_id=turn,
               role=role, content_text=text, content_hash=text_hash(text), token_count=token_bound(text), created_at=now())
        insert(db, 'history_entries', message_id=mid, session_id=sid, metadata_json=canonical({'sequence': sequence, 'role': role}), index_version='exact-v1')
        db.execute('UPDATE sessions SET updated_at=? WHERE session_id=?', (now(), sid))
        return mid

    def event(self, db, rid, kind, payload):
        sequence = db.execute('SELECT COALESCE(MAX(sequence),-1)+1 FROM run_events WHERE run_id=?', (rid,)).fetchone()[0]
        insert(db, 'run_events', run_id=rid, sequence=sequence, event_type=kind, safe_payload_json=canonical(payload), created_at=now())
        db.execute('DELETE FROM run_events WHERE run_id=? AND sequence<?', (rid, max(0, sequence - 99)))

    def admit(self, db, sid, text=None, retry=None):
        self.session(db, sid)
        if db.execute('SELECT COUNT(*) FROM messages WHERE session_id=?',(sid,)).fetchone()[0]>=9950:
            raise AppError('CHAT_STORAGE_LIMIT','This chat reached its message limit. Start a new chat.',429)
        if db.execute("SELECT 1 FROM request_runs WHERE session_id=? AND status IN ('ACTIVE','WAITING_USER')", (sid,)).fetchone():
            raise AppError('CHAT_BUSY', 'This chat has unfinished work. Reply to its clarification or cancel it.', 409)
        if db.execute("SELECT COUNT(*) FROM request_runs WHERE status='ACTIVE'").fetchone()[0] >= self.settings.max_active:
            raise AppError('BUSY', 'All processing slots are in use. Try again after a run finishes.', 429, True)
        rid, epoch = uid(), 1
        snapshot = self.settings.snapshot()
        pointer = row(db, 'SELECT build_id FROM corpus_pointer WHERE singleton=1')
        state = {'phase': 'A', 'passage_ids': [], 'history_refs': [], 'tool_results': [], 'searches': [],
                 'gaps': [], 'missing_by_round': [0, 0, 0], 'round': 0, 'prior_candidate': None,
                 'review': None, 'binding': None, 'closing': False, 'expansion_depth': 0}
        if retry:
            old = self.run(retry, db)
            if old['session_id'] != sid or old['status'] not in TERMINAL:
                raise AppError('INVALID_RETRY', 'Only a finished attempt can be retried.', 409)
            outcome = json.loads(old['terminal_result_json'])
            if not outcome.get('retryable'):
                raise AppError('INVALID_RETRY', 'This result does not need a retry.', 409)
            mid = old['original_message_id']
        else:
            if not text or not text.strip() or token_bound(text) > self.settings.max_input_bytes:
                raise AppError('INPUT_LIMIT', 'Enter a nonempty question within the input limit.', 413)
            mid = self.message(db, sid, rid, 'user', text)
        counters = dict(provider_calls=0, provider_retries=0, format_repairs=0, search_queries=0,
                        history_operations=0, tool_operations=0, controller_steps=0, charged_tokens=0)
        insert(db, 'request_runs', run_id=rid, session_id=sid, original_message_id=mid, retry_of_run_id=retry,
               status='ACTIVE', stage='NEED', worker_epoch=epoch, worker_owner='local', segment_started_at=now(),
               active_budget_ms=int(self.settings.active_seconds * 1000), config_snapshot_json=canonical(snapshot),
               config_hash=digest(snapshot), corpus_build_id=pointer['build_id'] if pointer else None,
               counters_json=canonical(counters), created_at=now())
        insert(db, 'runtime_state', run_id=rid, state_json=canonical(state))
        self.event(db, rid, 'progress', {'stage': 'NEED', 'message': 'Understanding your question'})
        return {'message_id': mid, 'run_id': rid, 'status': 'ACTIVE', 'state_version': 0}, sid, rid

    def state(self, rid):
        with self.read() as db:
            r = self.run(rid, db)
            s = json.loads(db.execute('SELECT state_json FROM runtime_state WHERE run_id=?', (rid,)).fetchone()[0])
            return r, s

    def save_state(self, rid, epoch, state, stage=None):
        with self.transaction() as db:
            r = self.owned(db, rid, epoch)
            db.execute('UPDATE runtime_state SET state_json=? WHERE run_id=?', (canonical(state), rid))
            db.execute('UPDATE request_runs SET state_version=state_version+1, correction_round=?, closing_mode=?, stage=? WHERE run_id=? AND worker_epoch=? AND state_version=?',
                       (state['round'], int(state['closing']), stage or r['stage'], rid, epoch, r['state_version']))
            if stage and stage != r['stage']:
                self.event(db, rid, 'progress', {'stage': stage, 'message': {'A': 'Collecting context', 'B': 'Writing an answer', 'C': 'Checking the answer'}.get(stage, stage)})

    def reserve(self, rid, epoch, kind, request_hash, tokens=0, retry=False, repair=False, deadline_seconds=None):
        with self.transaction() as db:
            r = self.owned(db, rid, epoch)
            counters = json.loads(r['counters_json'])
            limits = json.loads(r['config_snapshot_json'])
            add = {'controller_steps': 1, 'charged_tokens': tokens}
            if kind in ('A', 'B', 'C', 'embedding'):
                add['provider_calls'] = 1
            if kind in ('corpus_search', 'expand_passages', 'history_search', 'history_fetch'):
                add['tool_operations'] = 1
            if kind == 'corpus_search':
                add['search_queries'] = 1
            if kind.startswith('history_'):
                add['history_operations'] = 1
            if retry:
                add['provider_retries'] = 1
            if repair:
                add['format_repairs'] = 1
            mapping = {'controller_steps':'max_steps', 'charged_tokens':'total_token_bound', 'provider_calls':'max_calls',
                       'tool_operations':'max_tools', 'search_queries':'max_searches', 'history_operations':'max_history',
                       'provider_retries':'max_retries', 'format_repairs':'max_repairs'}
            for key, value in add.items():
                counters[key] += value
                if counters[key] > limits[mapping[key]]:
                    raise AppError('BUDGET_EXHAUSTED', 'The processing allowance is exhausted. Narrow the question or retry explicitly.', 429, True)
            db.execute('UPDATE request_runs SET counters_json=? WHERE run_id=?', (canonical(counters), rid))
            op = uid()
            insert(db, 'operations', operation_id=op, run_id=rid, worker_epoch=epoch, kind=kind,
                   request_hash=request_hash, status='DISPATCHED', reserved_tokens=tokens,
                   deadline_at=(datetime.now(timezone.utc)+timedelta(seconds=deadline_seconds if deadline_seconds is not None else limits['tool_seconds'])).isoformat(), provider_config_hash=r['config_hash'], created_at=now())
            return op

    def operation_done(self, rid, epoch, op, error=None):
        with self.transaction() as db:
            self.owned(db, rid, epoch)
            db.execute('UPDATE operations SET status=?, error_code=?, completed_at=? WHERE operation_id=? AND run_id=? AND worker_epoch=?',
                       ('FAILED' if error else 'SUCCEEDED', error, now(), op, rid, epoch))

    def save_need(self, rid, epoch, need):
        with self.transaction() as db:
            self.owned(db, rid, epoch)
            version = db.execute('SELECT COALESCE(MAX(version),0)+1 FROM needs WHERE run_id=?', (rid,)).fetchone()[0]
            nid = uid()
            insert(db, 'needs', need_id=nid, run_id=rid, version=version, need_hash=digest(need), need_json=canonical(need),
                   original_message_refs_json=canonical(need['original_refs']), created_at=now())
            db.execute('UPDATE request_runs SET current_need_id=? WHERE run_id=?', (nid, rid))
            return nid

    def wait_user(self, rid, epoch, clarification, elapsed):
        with self.transaction() as db:
            r = self.owned(db, rid, epoch)
            original = row(db, 'SELECT turn_id FROM messages WHERE message_id=?', (r['original_message_id'],))
            mid = self.message(db, r['session_id'], original['turn_id'], 'clarification', clarification['question'])
            cid = uid()
            insert(db, 'clarifications', clarification_id=cid, run_id=rid, session_id=r['session_id'], need_id=r['current_need_id'],
                   question_message_id=mid, gap_key=clarification['gap_key'], missing_requirements_json=canonical(clarification['missing_requirement_ids']),
                   status='PENDING', created_at=now())
            db.execute("UPDATE request_runs SET status='WAITING_USER', stage='CLARIFICATION', worker_epoch=worker_epoch+1, state_version=state_version+1, worker_owner=NULL, lease_expires_at=NULL, segment_started_at=NULL, active_elapsed_ms=? WHERE run_id=?", (elapsed, rid))
            self.event(db, rid, 'clarification_required', {'clarification_id': cid, 'question': clarification['question']})

    def reply(self, db, rid, cid, text, version):
        r = self.run(rid, db)
        if r['status'] != 'WAITING_USER' or r['state_version'] != version:
            raise AppError('STALE_REPLY', 'This clarification is no longer current. Refresh the chat.', 409)
        if r['config_hash'] != self.settings.config_hash:
            raise AppError('CONFIG_CHANGED','Configuration changed while waiting. Cancel this attempt and retry explicitly under the new configuration.',409)
        c = row(db, "SELECT * FROM clarifications WHERE clarification_id=? AND run_id=? AND status='PENDING'", (cid, rid))
        if not c:
            raise AppError('STALE_REPLY', 'This question was already answered or canceled.', 409)
        if db.execute("SELECT COUNT(*) FROM request_runs WHERE status='ACTIVE'").fetchone()[0] >= self.settings.max_active:
            raise AppError('BUSY', 'Processing is busy; your clarification remains waiting.', 429, True)
        if db.execute('SELECT COUNT(*) FROM messages WHERE session_id=?',(r['session_id'],)).fetchone()[0]>=9990:
            raise AppError('CHAT_STORAGE_LIMIT','This chat reached its reply limit. Cancel this run and start a new chat.',429)
        if not text.strip() or token_bound(text) > self.settings.max_input_bytes:
            raise AppError('INPUT_LIMIT', 'Clarification reply is empty or too long.', 413)
        original = row(db, 'SELECT turn_id FROM messages WHERE message_id=?', (r['original_message_id'],))
        mid = self.message(db, r['session_id'], original['turn_id'], 'user', text)
        db.execute("UPDATE clarifications SET status='ANSWERED', reply_message_id=?, resolved_at=? WHERE clarification_id=?", (mid, now(), cid))
        db.execute("UPDATE request_runs SET status='ACTIVE', stage='NEED', state_version=state_version+1, worker_epoch=worker_epoch+1, worker_owner='local', segment_started_at=? WHERE run_id=?", (now(), rid))
        state = json.loads(db.execute('SELECT state_json FROM runtime_state WHERE run_id=?', (rid,)).fetchone()[0])
        state['phase'] = 'A'
        state['tool_results'] = []
        db.execute('UPDATE runtime_state SET state_json=? WHERE run_id=?', (canonical(state), rid))
        self.event(db, rid, 'progress', {'stage':'NEED', 'message':'Continuing with your clarification'})
        return {'message_id':mid, 'run_id':rid, 'status':'ACTIVE', 'state_version':version+1}, r['session_id'], rid

    def finish_in(self, db, r, status, code, message, elapsed=None, candidate=None):
        if r['status'] in TERMINAL:
            return
        original = row(db, 'SELECT turn_id FROM messages WHERE message_id=?', (r['original_message_id'],))
        mid = self.message(db, r['session_id'], original['turn_id'], 'assistant' if candidate else 'notice', message)
        retryable = status != 'COMPLETED' or code == 'INABILITY'
        outcome = {'kind':code, 'message_id':mid, 'retryable':retryable}
        if candidate:
            outcome.update(candidate)
        db.execute("UPDATE clarifications SET status='CANCELED', resolved_at=? WHERE run_id=? AND status='PENDING'", (now(), r['run_id']))
        db.execute("UPDATE operations SET status='UNKNOWN', completed_at=? WHERE run_id=? AND status IN ('RESERVED','DISPATCHED')", (now(), r['run_id']))
        db.execute('UPDATE request_runs SET status=?, stage=?, state_version=state_version+1, worker_epoch=worker_epoch+1, worker_owner=NULL, segment_started_at=NULL, lease_expires_at=NULL, active_elapsed_ms=?, final_message_id=?, terminal_result_json=?, stop_code=?, completed_at=? WHERE run_id=? AND state_version=?',
                   (status, status, elapsed if elapsed is not None else r['active_elapsed_ms'], mid, canonical(outcome), code, now(), r['run_id'], r['state_version']))
        self.event(db, r['run_id'], status.lower(), outcome)

    def stop(self, rid, status, code, message, epoch=None, elapsed=None):
        with self.transaction() as db:
            r = self.run(rid, db)
            if r['status'] in TERMINAL or (epoch is not None and epoch != r['worker_epoch']):
                return False
            self.finish_in(db, r, status, code, message, elapsed)
            return True

    def recover(self):
        with self.transaction() as db:
            for raw in db.execute("SELECT * FROM request_runs WHERE status='ACTIVE'").fetchall():
                self.finish_in(db, dict(raw), 'INTERRUPTED', 'RESTARTED', 'Processing was interrupted by a restart. You can retry explicitly.')

    def public_run(self, rid, db=None):
        if db is None:
            with self.read() as conn:
                return self.public_run(rid, conn)
        r = self.run(rid, db)
        c = row(db, "SELECT c.clarification_id,m.content_text AS question,c.question_message_id AS message_id FROM clarifications c JOIN messages m ON m.message_id=c.question_message_id WHERE c.run_id=? AND c.status='PENDING'", (rid,))
        outcome = json.loads(r['terminal_result_json']) if r['terminal_result_json'] else None
        return {'run_id':rid, 'session_id':r['session_id'], 'status':r['status'], 'stage':r['stage'],
                'state_version':r['state_version'], 'pending_clarification':c, 'outcome':outcome,
                'retryable':bool(outcome and outcome.get('retryable'))}

    def original_ref(self, m):
        return dict(message_id=m['message_id'], session_id=m['session_id'], content_hash=m['content_hash'], start_offset=0, end_offset=m.get('content_length',len(m['content_text'])))

    def original_text(self, m):
        return {'ref':self.original_ref(m), 'role':m['role'], 'text':m['content_text']}

    def context(self, rid, extra_refs):
        with self.read() as db:
            r = self.run(rid, db)
            original = row(db, 'SELECT * FROM messages WHERE message_id=?', (r['original_message_id'],))
            # Load bounded previews/metadata for older history, not every full body.
            messages = [dict(m) for m in db.execute('SELECT message_id,session_id,turn_id,role,sequence,content_hash,length(content_text) AS content_length,token_count,substr(content_text,1,80) AS content_text FROM messages WHERE session_id=? ORDER BY sequence', (r['session_id'],))]
            mandatory = db.execute("SELECT * FROM messages WHERE session_id=? AND turn_id=? AND role IN ('user','clarification') ORDER BY sequence", (r['session_id'],original['turn_id'])).fetchall()
            selected = [self.original_text(dict(m)) for m in mandatory]
            selected_ids = {m['ref']['message_id'] for m in selected}
            turns = []
            for m in reversed(messages):
                if m['turn_id'] != original['turn_id'] and m['turn_id'] not in turns:
                    turns.append(m['turn_id'])
                if len(turns)>=4:
                    break
            used = 0
            for turn in turns:
                group = [m for m in messages if m['turn_id'] == turn]
                size = sum(m['token_count'] for m in group)
                if used + size <= self.settings.recent_bound:
                    full = db.execute('SELECT * FROM messages WHERE session_id=? AND turn_id=? ORDER BY sequence',(r['session_id'],turn)).fetchall()
                    selected.extend(self.original_text(dict(m)) for m in full)
                    selected_ids.update(m['message_id'] for m in group)
                    used += size
            for ref in extra_refs:
                m = self.fetch_history(db, r['session_id'], ref)
                if ref['message_id'] not in selected_ids:
                    selected.append(m)
                    selected_ids.add(ref['message_id'])
            excluded = [self.original_ref(m) for m in messages if m['message_id'] not in selected_ids]
            compact = []
            for m in reversed(messages):
                if m['message_id'] in selected_ids:
                    continue
                entry = {'ref':self.original_ref(m), 'preview':m['content_text']}
                if token_bound(canonical(compact + [entry])) <= self.settings.history_map_bound:
                    compact.append(entry)
            return {'originals':selected, 'excluded_history_refs':excluded}, compact

    def fetch_history(self, db, sid, ref):
        m = row(db, 'SELECT * FROM messages WHERE session_id=? AND message_id=?', (sid, ref['message_id']))
        if not m or ref['session_id'] != sid or ref['content_hash'] != m['content_hash'] or not 0 <= ref['start_offset'] < ref['end_offset'] <= len(m['content_text']):
            raise AppError('HISTORY_REFERENCE', 'History reference is invalid or belongs to another chat.', 409)
        return {'ref':ref, 'role':m['role'], 'text':m['content_text'][ref['start_offset']:ref['end_offset']]}

#!/usr/bin/env python3
"""Validate design artifacts, not the future chatbot.

Run: python docs/design/validate_design.py
Uses only the Python standard library. No provider calls or user data.
"""
from pathlib import Path
import json
import re
import sqlite3
import tempfile
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CHECKS = []


def check(name, condition):
    if not condition:
        raise AssertionError(name)
    CHECKS.append(name)


def insert(db, table, **values):
    # Identifiers here are test constants, never external input.
    fields = ','.join(values)
    placeholders = ','.join('?' for _ in values)
    db.execute(f'INSERT INTO {table} ({fields}) VALUES ({placeholders})',
               tuple(values.values()))


def rejects(db, name, fn):
    db.execute('SAVEPOINT invalid_case')
    try:
        fn()
    except sqlite3.IntegrityError:
        CHECKS.append(name)
    else:
        raise AssertionError(name + ': invalid write accepted')
    finally:
        db.execute('ROLLBACK TO invalid_case')
        db.execute('RELEASE invalid_case')


def run_row(run_id, session_id='s1', message_id='m1', **extra):
    return dict(run_id=run_id, session_id=session_id,
                original_message_id=message_id, status='ACTIVE', stage='NEED',
                active_budget_ms=180000, config_snapshot_json='{}',
                config_hash='config1', counters_json='{}', created_at='test',
                **extra)


def seed(db):
    for n in (1, 2):
        insert(db, 'sessions', session_id=f's{n}', title='Test',
               created_at='test', updated_at='test')
        insert(db, 'messages', message_id=f'm{n}', session_id=f's{n}',
               sequence=0, turn_id=f't{n}', role='user', content_text='Question',
               content_hash=f'q{n}', token_count=1, created_at='test')
    insert(db, 'corpus_builds', build_id='build1', fingerprint='fingerprint1',
           manifest_json='{}', config_json='{}', status='VALIDATED', created_at='test')
    insert(db, 'request_runs', **run_row('r1'))
    insert(db, 'request_runs', **run_row('r2', 's2', 'm2'))
    for n in (1, 2):
        insert(db, 'needs', need_id=f'n{n}', run_id=f'r{n}', version=1,
               need_hash=f'nh{n}', need_json='{}', original_message_refs_json='[]',
               created_at='test')
        insert(db, 'context_snapshots', context_id=f'x{n}', run_id=f'r{n}',
               context_hash=f'xh{n}', selected_originals_json='[]',
               excluded_index_refs_json='[]', created_at='test')
        insert(db, 'evidence_sets', evidence_set_id=f'e{n}', run_id=f'r{n}',
               build_id='build1', evidence_hash=f'eh{n}', passages_snapshot_json='[]',
               created_at='test')
        db.execute('UPDATE request_runs SET current_need_id=?, '
                   'current_evidence_set_id=? WHERE run_id=?', (f'n{n}', f'e{n}', f'r{n}'))
    insert(db, 'candidates', candidate_id='b1', run_id='r1', need_id='n1',
           evidence_set_id='e1', context_id='x1', round_number=0,
           content_hash='bh1', answer_markdown='Test candidate', citations_json='[]',
           covered_json='[]', unresolved_json='[]', revision_log_json='[]',
           basic_checks_passed=1, created_at='test')
    db.commit()


def review_row(review_id='c1', **changes):
    row = dict(review_id=review_id, run_id='r1', candidate_id='b1', need_id='n1',
               evidence_set_id='e1', context_id='x1', candidate_hash='bh1',
               decision='accepted', satisfied_json='[]', unmet_json='[]',
               findings_json='[]', blocking_count=0, regression_check_json='{}',
               created_at='test')
    row.update(changes)
    return row


def validate_config():
    c = json.loads((HERE / 'limits.example.json').read_text())
    for key, value in c.items():
        if isinstance(value, int):
            check('finite positive config: ' + key,
                  value > 0 or key == 'max_missing_info_requests_when_closing' and value == 0)
    check('two correction rounds', c['max_correction_rounds'] == 2)
    check('closing calls fit total', 2 <= c['closing_reserve_provider_calls'] < c['max_provider_calls_per_run'])
    check('closing token reserve covers B+C ceilings',
          c['closing_reserve_tokens'] >= 2 * (c['max_role_input_tokens'] + c['max_role_output_tokens']))
    check('closing tokens fit total', c['closing_reserve_tokens'] < c['max_total_tokens_per_run'])
    check('closing time covers B+C and persistence', c['closing_reserve_seconds'] >=
          2 * c['provider_call_timeout_seconds'] + c['database_wait_timeout_seconds'])
    check('closing time fits total', c['closing_reserve_seconds'] < c['max_active_processing_seconds'])
    check('worker heartbeat shorter than lease', c['worker_heartbeat_seconds'] < c['worker_lease_seconds'])
    check('no clarification count cap', 'max_clarifications_per_query' not in c)


def validate_traceability():
    srs = (ROOT / 'docs/requirements/wireless-assistant-srs.md').read_text()
    required = set(re.findall(r'^### ([A-Z]{2,3}-\d{2}) -', srs, re.M))
    v = (HERE / 'verification.md').read_text()
    rows = re.findall(r'^\| ([A-Z]{2,3}-\d{2}) \|', v, re.M)
    check('94 unique SRS requirements', len(required) == 94)
    check('94 unique design mapping rows', len(rows) == len(set(rows)) == 94)
    check('mapping exactly covers existing requirement IDs', set(rows) == required)
    check('all original acceptance scenarios retained',
          set(re.findall(r'\bT\d{2}\b', v)) == {f'T{i:02d}' for i in range(1, 31)})
    for filename in ('system-design.md', 'implementation-guide.md', 'verification.md'):
        text = (HERE / filename).read_text()
        refs = set(re.findall(r'\b[A-Z]{2,3}-\d{2}\b', text)) - {'LLD-001'}
        check(filename + ': no unknown requirement IDs', not refs - required)


def validate_document_links():
    missing = []
    count = 0
    for path in [ROOT / 'README.md', ROOT / 'CONTRIBUTING.md', ROOT / 'CHANGELOG.md',
                 *sorted((ROOT / 'docs').rglob('*.md'))]:
        for target in re.findall(r'\]\(([^)]+)\)', path.read_text()):
            if re.match(r'^[a-zA-Z]+:', target) or target.startswith('#'):
                continue
            relative = target.split('#')[0]
            if relative:
                count += 1
                if not (path.parent / relative).is_file():
                    missing.append((str(path.relative_to(ROOT)), target))
    check(f'{count} local documentation file links resolve: {missing}', not missing)

    # Syntax-check the illustrative JSON API payloads, without claiming that a
    # runtime API/schema or model contract has been implemented.
    guide = (HERE / 'implementation-guide.md').read_text()
    examples = re.findall(r'```json\n(.*?)\n```', guide, re.S)
    parsed = [json.loads(example) for example in examples]
    check('handoff API examples are valid JSON objects', len(parsed) == 2 and
          all(isinstance(example, dict) for example in parsed))


def validate_schema():
    sql = (HERE / 'schema.sql').read_text()
    db = sqlite3.connect(':memory:')
    db.executescript(sql)
    check('foreign keys enabled', db.execute('PRAGMA foreign_keys').fetchone()[0] == 1)
    seed(db)
    rejects(db, 'second active run rejected', lambda: insert(db, 'request_runs', **run_row('duplicate')))
    # Use a terminal fixture to avoid the active-run uniqueness constraint
    # masking the cross-session foreign-key check.
    wrong_owner = run_row('wrong-session', 's1', 'm2')
    wrong_owner.update(status='FAILED', completed_at='test', terminal_result_json='{}')
    rejects(db, 'cross-session original message rejected', lambda: insert(
        db, 'request_runs', **wrong_owner))
    rejects(db, 'third correction rejected', lambda: db.execute(
        "UPDATE request_runs SET correction_round=3 WHERE run_id='r1'"))
    rejects(db, 'waiting cannot retain worker ownership', lambda: db.execute(
        "UPDATE request_runs SET status='WAITING_USER', worker_owner='worker' WHERE run_id='r1'"))
    rejects(db, 'terminal state requires terminal record', lambda: db.execute(
        "UPDATE request_runs SET status='COMPLETED' WHERE run_id='r1'"))
    rejects(db, 'review with wrong candidate hash rejected', lambda: insert(
        db, 'reviews', **review_row(candidate_hash='changed-answer')))
    rejects(db, 'review with another run evidence rejected', lambda: insert(
        db, 'reviews', **review_row(evidence_set_id='e2')))
    rejects(db, 'review with another need rejected', lambda: insert(
        db, 'reviews', **review_row(need_id='n2')))
    rejects(db, 'accepted review with blocking findings rejected', lambda: insert(
        db, 'reviews', **review_row(blocking_count=1)))
    for table, field in [('needs','need_hash'), ('context_snapshots','context_hash'),
                         ('evidence_sets','evidence_hash'), ('candidates','content_hash')]:
        rejects(db, 'immutable ' + table, lambda t=table, f=field:
                db.execute(f"UPDATE {t} SET {f}='changed'"))
    # A waiting run reserves the conversation, but consumes its reply through a
    # distinct state transition rather than the new-question admission gate.
    insert(db, 'messages', message_id='clarify2', session_id='s2', sequence=1,
           turn_id='t2', role='clarification', content_text='Which procedure?',
           content_hash='question2', token_count=2, created_at='test')
    insert(db, 'messages', message_id='reply2', session_id='s2', sequence=2,
           turn_id='t2', role='user', content_text='Named procedure',
           content_hash='replyhash2', token_count=2, created_at='test')
    insert(db, 'clarifications', clarification_id='clar2', run_id='r2', session_id='s2',
           need_id='n2', question_message_id='clarify2', gap_key='procedure',
           missing_requirements_json='[]', status='PENDING', created_at='test')
    db.execute("UPDATE request_runs SET status='WAITING_USER' WHERE run_id='r2'")
    rejects(db, 'waiting run blocks a new dependent run', lambda: insert(
        db, 'request_runs', **run_row('duplicate-waiting','s2','m2')))
    consumed = db.execute("UPDATE clarifications SET status='ANSWERED', reply_message_id='reply2', "
                          "resolved_at='test' WHERE clarification_id='clar2' AND status='PENDING'").rowcount
    repeated = db.execute("UPDATE clarifications SET status='ANSWERED', reply_message_id='reply2', "
                          "resolved_at='test' WHERE clarification_id='clar2' AND status='PENDING'").rowcount
    resumed = db.execute("UPDATE request_runs SET status='ACTIVE', state_version=1, worker_epoch=1 "
                         "WHERE run_id='r2' AND status='WAITING_USER' AND state_version=0 AND worker_epoch=0").rowcount
    check('pending clarification consumed once and run resumed', (consumed,repeated,resumed) == (1,0,1))
    insert(db, 'reviews', **review_row())
    rejects(db, 'immutable reviews', lambda: db.execute("UPDATE reviews SET decision='findings'"))
    insert(db, 'feedback', feedback_id='f1', session_id='s1', run_id='r1',
           candidate_id='b1', review_id='c1', category='unclear', created_at='test')
    insert(db, 'history_entries', message_id='m1', session_id='s1', metadata_json='{}', index_version='v1')
    insert(db, 'run_events', run_id='r1', sequence=0, event_type='progress',
           safe_payload_json='{}', created_at='test')
    insert(db, 'command_receipts', idempotency_key='key1', session_id='s1', run_id='r1',
           route='submit', request_hash='request1', safe_response_json='{}', created_at='test')
    rejects(db, 'duplicate command key rejected', lambda: insert(
        db, 'command_receipts', idempotency_key='key1', route='submit', request_hash='request2',
        safe_response_json='{}', created_at='test'))
    # Simulate conditional cancel versus late completion. This tests the proposed
    # database predicate, not a product worker, UI, or provider cancellation.
    won = db.execute("UPDATE request_runs SET status='CANCELED', state_version=1, worker_epoch=1, "
                     "completed_at='test', terminal_result_json='{}' "
                     "WHERE run_id='r1' AND status='ACTIVE' AND state_version=0 AND worker_epoch=0").rowcount
    late = db.execute("UPDATE request_runs SET status='COMPLETED' "
                      "WHERE run_id='r1' AND status='ACTIVE' AND state_version=0 AND worker_epoch=0").rowcount
    check('cancel compare-and-set wins once', won == 1 and late == 0)
    rejects(db, 'terminal run cannot be resurrected', lambda: db.execute(
        "UPDATE request_runs SET status='ACTIVE', completed_at=NULL, terminal_result_json=NULL WHERE run_id='r1'"))
    rejects(db, 'original message cannot change after review', lambda: db.execute(
        "UPDATE messages SET content_text='changed intent' WHERE message_id='m1'"))
    db.commit()
    db.execute("DELETE FROM sessions WHERE session_id='s1'")
    db.commit()
    for table in ('messages','history_entries','request_runs','needs','context_snapshots',
                  'evidence_sets','candidates','reviews','feedback','run_events','command_receipts'):
        column = 'session_id' if table in ('messages','history_entries','request_runs','feedback','command_receipts') else 'run_id'
        ident = 's1' if column == 'session_id' else 'r1'
        check('session deletion purges ' + table,
              db.execute(f'SELECT COUNT(*) FROM {table} WHERE {column}=?',(ident,)).fetchone()[0] == 0)
    check('deletion preserves unrelated session', db.execute("SELECT COUNT(*) FROM request_runs WHERE run_id='r2'").fetchone()[0] == 1)
    check('foreign-key consistency after deletion', not db.execute('PRAGMA foreign_key_check').fetchall())
    check('database integrity', db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok')
    db.close()
    # Two real connections compete for the same session. The unique database
    # constraint must reject one even if both clients observed an idle session.
    with tempfile.TemporaryDirectory() as d:
        path = str(Path(d) / 'race.db')
        db = sqlite3.connect(path)
        db.executescript(sql)
        insert(db, 'sessions', session_id='s1', title='Test', created_at='test', updated_at='test')
        insert(db, 'messages', message_id='m1', session_id='s1', sequence=0,
               turn_id='t1', role='user', content_text='Question', content_hash='q1',
               token_count=1, created_at='test')
        db.commit()
        db.close()
        barrier = Barrier(2)
        def claim(n):
            conn = sqlite3.connect(path, timeout=2)
            conn.execute('PRAGMA foreign_keys=ON')
            barrier.wait(timeout=5)
            try:
                insert(conn, 'request_runs', **run_row('race' + str(n)))
                conn.commit()
                return 'claimed'
            except sqlite3.IntegrityError:
                conn.rollback()
                return 'rejected'
            finally:
                conn.close()
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(claim, (1,2)))
        check('concurrent claims create exactly one active run', sorted(outcomes) == ['claimed','rejected'])


def main():
    validate_config()
    validate_traceability()
    validate_document_links()
    validate_schema()
    print(f'PASS: {len(CHECKS)} document/configuration/database assertions.')
    print('These are design checks, not chatbot runtime, provider, quality or security test results.')
    for name in CHECKS:
        print('  PASS ' + name)


if __name__ == '__main__':
    main()

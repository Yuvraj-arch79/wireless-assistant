-- DESIGN-LLD-001 reference schema, revision 0.1. Not an application migration.
-- Enable these on EVERY connection. Use short transactions, never across I/O.
PRAGMA foreign_keys = ON;
PRAGMA busy_timeout = 2000;

CREATE TABLE schema_versions (
  version INTEGER PRIMARY KEY,
  applied_at TEXT NOT NULL
);

CREATE TABLE sessions (
  session_id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  preferences_json TEXT NOT NULL DEFAULT '{}',
  state_version INTEGER NOT NULL DEFAULT 0 CHECK (state_version >= 0),
  deleted_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE messages (
  message_id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL REFERENCES sessions ON DELETE CASCADE,
  sequence INTEGER NOT NULL CHECK (sequence >= 0),
  turn_id TEXT NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('user','assistant','clarification','notice')),
  content_text TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  token_count INTEGER NOT NULL CHECK (token_count >= 0),
  created_at TEXT NOT NULL,
  UNIQUE (message_id, session_id),
  UNIQUE (session_id, sequence)
);

CREATE TABLE history_entries (
  message_id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  metadata_json TEXT NOT NULL,
  index_version TEXT NOT NULL,
  FOREIGN KEY (message_id, session_id)
    REFERENCES messages (message_id, session_id) ON DELETE CASCADE
);

CREATE TABLE corpus_builds (
  build_id TEXT PRIMARY KEY,
  fingerprint TEXT NOT NULL UNIQUE,
  manifest_json TEXT NOT NULL,
  config_json TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('STAGING','VALIDATED','ARCHIVED','FAILED')),
  created_at TEXT NOT NULL,
  validated_at TEXT
);

CREATE TABLE corpus_pointer (
  singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
  build_id TEXT NOT NULL REFERENCES corpus_builds,
  activated_at TEXT NOT NULL
);

CREATE TABLE source_documents (
  document_id TEXT PRIMARY KEY,
  build_id TEXT NOT NULL REFERENCES corpus_builds,
  spec_number TEXT NOT NULL,
  title TEXT NOT NULL,
  release TEXT,
  version TEXT NOT NULL,
  source_uri TEXT NOT NULL,
  file_hash TEXT NOT NULL,
  parser_config_hash TEXT NOT NULL,
  UNIQUE (document_id, build_id)
);

CREATE TABLE passages (
  passage_id TEXT PRIMARY KEY,
  document_id TEXT NOT NULL,
  build_id TEXT NOT NULL,
  clause_id TEXT NOT NULL,
  clause_title TEXT,
  page_location TEXT,
  content_text TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  structure_json TEXT NOT NULL,
  parent_id TEXT,
  previous_id TEXT,
  next_id TEXT,
  unreadable INTEGER NOT NULL CHECK (unreadable IN (0,1)),
  FOREIGN KEY (document_id, build_id)
    REFERENCES source_documents (document_id, build_id),
  UNIQUE (passage_id, build_id)
);

CREATE TABLE request_runs (
  run_id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL REFERENCES sessions ON DELETE CASCADE,
  original_message_id TEXT NOT NULL,
  retry_of_run_id TEXT,
  status TEXT NOT NULL CHECK (status IN
    ('ACTIVE','WAITING_USER','COMPLETED','CANCELED','FAILED','TIMED_OUT','INTERRUPTED')),
  stage TEXT NOT NULL,
  state_version INTEGER NOT NULL DEFAULT 0 CHECK (state_version >= 0),
  worker_epoch INTEGER NOT NULL DEFAULT 0 CHECK (worker_epoch >= 0),
  worker_owner TEXT,
  lease_expires_at TEXT,
  segment_started_at TEXT,
  active_elapsed_ms INTEGER NOT NULL DEFAULT 0 CHECK (active_elapsed_ms >= 0),
  active_budget_ms INTEGER NOT NULL CHECK (active_budget_ms > 0),
  config_snapshot_json TEXT NOT NULL,
  config_hash TEXT NOT NULL,
  corpus_build_id TEXT REFERENCES corpus_builds,
  counters_json TEXT NOT NULL,
  correction_round INTEGER NOT NULL DEFAULT 0 CHECK (correction_round BETWEEN 0 AND 2),
  closing_mode INTEGER NOT NULL DEFAULT 0 CHECK (closing_mode IN (0,1)),
  current_need_id TEXT,
  current_evidence_set_id TEXT,
  final_message_id TEXT,
  terminal_result_json TEXT,
  stop_code TEXT,
  created_at TEXT NOT NULL,
  completed_at TEXT,
  FOREIGN KEY (original_message_id, session_id)
    REFERENCES messages (message_id, session_id),
  FOREIGN KEY (final_message_id, session_id)
    REFERENCES messages (message_id, session_id),
  FOREIGN KEY (retry_of_run_id, session_id)
    REFERENCES request_runs (run_id, session_id),
  FOREIGN KEY (current_need_id, run_id)
    REFERENCES needs (need_id, run_id) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY (current_evidence_set_id, run_id)
    REFERENCES evidence_sets (evidence_set_id, run_id) DEFERRABLE INITIALLY DEFERRED,
  UNIQUE (run_id, session_id),
  CHECK ((status IN ('ACTIVE','WAITING_USER') AND completed_at IS NULL
          AND terminal_result_json IS NULL)
      OR (status IN ('COMPLETED','CANCELED','FAILED','TIMED_OUT','INTERRUPTED')
          AND completed_at IS NOT NULL AND terminal_result_json IS NOT NULL)),
  CHECK (status <> 'WAITING_USER' OR
         (worker_owner IS NULL AND lease_expires_at IS NULL AND segment_started_at IS NULL))
);

CREATE UNIQUE INDEX one_unfinished_run_per_session
  ON request_runs(session_id) WHERE status IN ('ACTIVE','WAITING_USER');

CREATE TABLE needs (
  need_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES request_runs ON DELETE CASCADE,
  version INTEGER NOT NULL CHECK (version > 0),
  need_hash TEXT NOT NULL,
  need_json TEXT NOT NULL,
  original_message_refs_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE (need_id, run_id),
  UNIQUE (run_id, version)
);

CREATE TABLE context_snapshots (
  context_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES request_runs ON DELETE CASCADE,
  context_hash TEXT NOT NULL,
  selected_originals_json TEXT NOT NULL,
  excluded_index_refs_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE (context_id, run_id)
);

CREATE TABLE clarifications (
  clarification_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  session_id TEXT NOT NULL,
  need_id TEXT NOT NULL,
  question_message_id TEXT NOT NULL,
  reply_message_id TEXT,
  gap_key TEXT NOT NULL,
  missing_requirements_json TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('PENDING','ANSWERED','CANCELED')),
  created_at TEXT NOT NULL,
  resolved_at TEXT,
  FOREIGN KEY (run_id, session_id)
    REFERENCES request_runs (run_id, session_id) ON DELETE CASCADE,
  FOREIGN KEY (need_id, run_id) REFERENCES needs (need_id, run_id),
  FOREIGN KEY (question_message_id, session_id)
    REFERENCES messages (message_id, session_id),
  FOREIGN KEY (reply_message_id, session_id)
    REFERENCES messages (message_id, session_id),
  CHECK ((status='PENDING' AND reply_message_id IS NULL AND resolved_at IS NULL)
    OR (status='ANSWERED' AND reply_message_id IS NOT NULL AND resolved_at IS NOT NULL)
    OR (status='CANCELED' AND resolved_at IS NOT NULL))
);

CREATE UNIQUE INDEX one_pending_clarification_per_run
  ON clarifications(run_id) WHERE status='PENDING';

CREATE TABLE evidence_sets (
  evidence_set_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES request_runs ON DELETE CASCADE,
  build_id TEXT NOT NULL REFERENCES corpus_builds,
  evidence_hash TEXT NOT NULL,
  -- Canonical ordered IDs, exact text and source metadata, including coverage gaps.
  -- One immutable snapshot avoids mutable membership after review.
  passages_snapshot_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE (evidence_set_id, run_id)
);

CREATE TABLE retrieval_records (
  retrieval_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES request_runs ON DELETE CASCADE,
  need_id TEXT NOT NULL,
  evidence_set_id TEXT,
  query_fingerprint TEXT NOT NULL,
  request_json TEXT NOT NULL,
  result_json TEXT NOT NULL,
  new_passage_count INTEGER NOT NULL CHECK (new_passage_count >= 0),
  stop_code TEXT,
  created_at TEXT NOT NULL,
  FOREIGN KEY (need_id, run_id) REFERENCES needs (need_id, run_id),
  FOREIGN KEY (evidence_set_id, run_id)
    REFERENCES evidence_sets (evidence_set_id, run_id)
);

CREATE TABLE candidates (
  candidate_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES request_runs ON DELETE CASCADE,
  need_id TEXT NOT NULL,
  evidence_set_id TEXT NOT NULL,
  context_id TEXT NOT NULL,
  round_number INTEGER NOT NULL CHECK (round_number BETWEEN 0 AND 2),
  repair_version INTEGER NOT NULL DEFAULT 0 CHECK (repair_version BETWEEN 0 AND 1),
  content_hash TEXT NOT NULL,
  answer_markdown TEXT NOT NULL,
  citations_json TEXT NOT NULL,
  covered_json TEXT NOT NULL,
  unresolved_json TEXT NOT NULL,
  limitation_statement TEXT,
  revision_log_json TEXT NOT NULL,
  basic_checks_passed INTEGER NOT NULL CHECK (basic_checks_passed IN (0,1)),
  created_at TEXT NOT NULL,
  FOREIGN KEY (need_id, run_id) REFERENCES needs (need_id, run_id),
  FOREIGN KEY (evidence_set_id, run_id)
    REFERENCES evidence_sets (evidence_set_id, run_id),
  FOREIGN KEY (context_id, run_id)
    REFERENCES context_snapshots (context_id, run_id),
  UNIQUE (run_id, round_number, repair_version),
  UNIQUE (candidate_id, run_id),
  UNIQUE (candidate_id, run_id, need_id, evidence_set_id, context_id, content_hash)
);

CREATE TABLE reviews (
  review_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES request_runs ON DELETE CASCADE,
  candidate_id TEXT NOT NULL,
  need_id TEXT NOT NULL,
  evidence_set_id TEXT NOT NULL,
  context_id TEXT NOT NULL,
  candidate_hash TEXT NOT NULL,
  decision TEXT NOT NULL CHECK (decision IN ('accepted','partial_accepted','findings')),
  satisfied_json TEXT NOT NULL,
  unmet_json TEXT NOT NULL,
  findings_json TEXT NOT NULL,
  blocking_count INTEGER NOT NULL CHECK (blocking_count >= 0),
  regression_check_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY (candidate_id, run_id, need_id, evidence_set_id, context_id, candidate_hash)
    REFERENCES candidates
      (candidate_id, run_id, need_id, evidence_set_id, context_id, content_hash),
  UNIQUE (review_id, run_id, candidate_id),
  CHECK ((decision IN ('accepted','partial_accepted') AND blocking_count=0)
      OR (decision='findings' AND blocking_count>0))
);

CREATE TABLE operations (
  operation_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES request_runs ON DELETE CASCADE,
  worker_epoch INTEGER NOT NULL,
  kind TEXT NOT NULL,
  request_hash TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN
    ('RESERVED','DISPATCHED','SUCCEEDED','FAILED','UNKNOWN','DISCARDED')),
  reserved_tokens INTEGER NOT NULL CHECK (reserved_tokens >= 0),
  observed_input_tokens INTEGER CHECK (observed_input_tokens >= 0),
  observed_output_tokens INTEGER CHECK (observed_output_tokens >= 0),
  deadline_at TEXT NOT NULL,
  provider_config_hash TEXT NOT NULL,
  error_code TEXT,
  created_at TEXT NOT NULL,
  completed_at TEXT
);

CREATE TABLE command_receipts (
  idempotency_key TEXT PRIMARY KEY,
  session_id TEXT REFERENCES sessions ON DELETE CASCADE,
  run_id TEXT,
  route TEXT NOT NULL,
  request_hash TEXT NOT NULL,
  safe_response_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY (run_id, session_id)
    REFERENCES request_runs (run_id, session_id)
);

CREATE TABLE run_events (
  run_id TEXT NOT NULL REFERENCES request_runs ON DELETE CASCADE,
  sequence INTEGER NOT NULL CHECK (sequence >= 0),
  event_type TEXT NOT NULL,
  safe_payload_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (run_id, sequence)
);

CREATE TABLE feedback (
  feedback_id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  run_id TEXT NOT NULL,
  candidate_id TEXT NOT NULL,
  review_id TEXT NOT NULL,
  category TEXT NOT NULL CHECK (category IN ('wrong','unclear','irrelevant','incomplete')),
  comment TEXT,
  created_at TEXT NOT NULL,
  FOREIGN KEY (run_id, session_id)
    REFERENCES request_runs (run_id, session_id) ON DELETE CASCADE,
  FOREIGN KEY (review_id, run_id, candidate_id)
    REFERENCES reviews (review_id, run_id, candidate_id)
);

-- Validated source builds are frozen by the ingestion repository layer.
-- Immutable per-run inputs and judgments cannot be updated in place.
CREATE TRIGGER immutable_need BEFORE UPDATE ON needs
BEGIN SELECT RAISE(ABORT, 'need versions are immutable'); END;
CREATE TRIGGER immutable_context BEFORE UPDATE ON context_snapshots
BEGIN SELECT RAISE(ABORT, 'context snapshots are immutable'); END;
CREATE TRIGGER immutable_evidence BEFORE UPDATE ON evidence_sets
BEGIN SELECT RAISE(ABORT, 'evidence snapshots are immutable'); END;
CREATE TRIGGER immutable_candidate BEFORE UPDATE ON candidates
BEGIN SELECT RAISE(ABORT, 'candidates are immutable'); END;
CREATE TRIGGER immutable_review BEFORE UPDATE ON reviews
BEGIN SELECT RAISE(ABORT, 'reviews are immutable'); END;
CREATE TRIGGER immutable_original_message BEFORE UPDATE ON messages
BEGIN SELECT RAISE(ABORT, 'original messages are immutable'); END;
CREATE TRIGGER immutable_terminal_run BEFORE UPDATE ON request_runs
WHEN OLD.status IN ('COMPLETED','CANCELED','FAILED','TIMED_OUT','INTERRUPTED')
BEGIN SELECT RAISE(ABORT, 'terminal runs cannot be changed or resumed'); END;

-- Repository transactions MUST additionally enforce the full release predicate,
-- run/current-need/evidence alignment, budgets, message roles, state transitions,
-- terminal immutability, idempotency receipts and active corpus compatibility.
-- JSON contents require bounded contract validation. SQL shape checks alone
-- cannot establish support, complete coverage, or the absence of hallucinations.

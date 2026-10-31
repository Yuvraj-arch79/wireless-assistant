CREATE TABLE runtime_state (
 run_id TEXT PRIMARY KEY REFERENCES request_runs ON DELETE CASCADE,
 state_json TEXT NOT NULL
);
CREATE VIRTUAL TABLE passage_fts USING fts5(passage_id UNINDEXED, build_id UNINDEXED, content_text, clause_title, tokenize='unicode61');
CREATE TABLE passage_vectors (
 passage_id TEXT PRIMARY KEY REFERENCES passages,
 model TEXT NOT NULL,
 dimensions INTEGER NOT NULL,
 vector_json TEXT NOT NULL
);
CREATE TABLE build_reports (
 build_id TEXT PRIMARY KEY REFERENCES corpus_builds,
 report_json TEXT NOT NULL
);

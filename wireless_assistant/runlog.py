"""Developer run log: one JSON line per provider call, tool step and run end.

Only whitelisted operational fields are written: no API keys, prompts, chat text or provider
bodies. Trace a failed run with: python -m wireless_assistant.cli trace <run-id-or-prefix>
"""
import json
import threading
from .common import now

FIELDS = ('run_id', 'event', 'stage', 'provider', 'model', 'elapsed_ms', 'token_estimate', 'retry', 'repair',
          'code', 'status', 'evidence_passages', 'corpus_build_id', 'versions', 'version_source', 'retry_after_seconds', 'tool', 'action', 'requests')
MAX_BYTES = 5 * 1024 * 1024
_lock = threading.Lock()


def provider_for(settings, role):
    if role == 'embedding' or settings.provider_profile == 'gemini':
        return 'gemini'
    return 'openrouter' if role == 'B' else 'groq'


def write(settings, **fields):
    record = {'ts': now(), **{k: v for k, v in fields.items() if k in FIELDS and v is not None}}
    folder = settings.data_dir / 'logs'
    try:
        with _lock:
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / 'runs.jsonl'
            if path.exists() and path.stat().st_size > MAX_BYTES:
                path.replace(folder / 'runs.1.jsonl')
            with path.open('a', encoding='utf-8') as handle:
                handle.write(json.dumps(record, ensure_ascii=True, sort_keys=True) + '\n')
    except OSError:
        pass  # Logging must never change a run's outcome.


def read(settings, run_prefix):
    rows = []
    for name in ('runs.1.jsonl', 'runs.jsonl'):
        path = settings.data_dir / 'logs' / name
        if path.exists():
            for line in path.read_text(encoding='utf-8').splitlines():
                try:
                    item = json.loads(line)
                except ValueError:
                    continue
                if str(item.get('run_id', '')).startswith(run_prefix):
                    rows.append(item)
    return rows

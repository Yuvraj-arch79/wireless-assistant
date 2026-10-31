"""Killable work: wall-clock deadlines include spawn, execution and result handling."""
import json
import multiprocessing
from pathlib import Path
import tempfile
import time
from .common import AppError, canonical

MAX_RESULT = 16 * 1024 * 1024


def _child(function, args, path):
    try:
        result = {'ok':True, 'value':function(*args)}
    except AppError as exc:
        result = {'ok':False, 'error':exc.public(), 'status':exc.status}
    except Exception:
        # Provider/parser exception strings may contain secrets or local paths.
        result = {'ok':False, 'error':{'code':'OPERATION_FAILED', 'message':'The operation failed safely.', 'retryable':False}, 'status':503}
    raw = canonical(result).encode('utf-8')
    if len(raw) > MAX_RESULT:
        raw = canonical({'ok':False, 'error':{'code':'RESULT_LIMIT','message':'Operation result is too large.','retryable':False},'status':413}).encode('utf-8')
    destination = Path(path)
    temporary = destination.with_suffix('.part')
    temporary.write_bytes(raw)
    temporary.replace(destination)


def bounded(function, args=(), seconds=25, canceled=lambda:False):
    deadline = time.monotonic() + seconds
    if seconds <= 0 or canceled():
        raise AppError('STOPPED', 'Processing was stopped.', 409)
    with tempfile.TemporaryDirectory(prefix='wireless-operation-') as folder:
        path = Path(folder) / 'result.json'
        process = multiprocessing.get_context('spawn').Process(target=_child, args=(function,args,str(path)), daemon=True)
        process.start()
        try:
            while process.is_alive():
                if canceled():
                    raise AppError('STOPPED', 'Processing was canceled.', 409)
                if time.monotonic() >= deadline:
                    raise AppError('OPERATION_TIMEOUT', 'An operation exceeded its time limit.', 504, True)
                process.join(timeout=min(0.05, max(0, deadline-time.monotonic())))
            if canceled():
                raise AppError('STOPPED', 'Processing was canceled.', 409)
            if time.monotonic() >= deadline:
                raise AppError('OPERATION_TIMEOUT', 'An operation exceeded its time limit.', 504, True)
            if process.exitcode or not path.is_file() or path.stat().st_size > MAX_RESULT:
                raise AppError('WORKER_FAILED', 'The operation worker stopped unexpectedly.', 503, True)
            result = json.loads(path.read_text(encoding='utf-8'))
            if not result['ok']:
                e = result['error']
                raise AppError(e['code'], e['message'], result['status'], e['retryable'])
            return result['value']
        finally:
            if process.is_alive():
                process.terminate()
                process.join(timeout=0.3)
            if process.is_alive():
                process.kill()
                process.join(timeout=0.3)
            if process.is_alive():
                raise AppError('CLEANUP_FAILED', 'Worker cleanup failed. Restart the application before more work.', 503)
            process.close()

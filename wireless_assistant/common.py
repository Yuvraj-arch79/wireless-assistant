"""Canonical identities, bounded JSON and safe public errors."""
import hashlib
import json
import uuid
from datetime import datetime, timezone


class AppError(Exception):
    def __init__(self, code, message, status=400, retryable=False, retry_after=None):
        super().__init__(message)
        self.code, self.message, self.status, self.retryable = code, message, status, retryable
        # Seconds the provider asked us to wait (429), when it said so; never guessed.
        self.retry_after = retry_after

    def public(self):
        return {"code": self.code, "message": self.message, "retryable": self.retryable,
                "retry_after_seconds": self.retry_after}


def retry_after_seconds(headers=None, body=None):
    """Provider-supplied wait time: Retry-After header or Google RetryInfo; None if absent."""
    import re
    value = (headers or {}).get('retry-after')
    if value and re.fullmatch(r'\s*\d{1,5}(\.\d+)?\s*', value):
        return max(1, int(float(value) + 0.999))
    try:
        for detail in body['error']['details']:
            match = re.fullmatch(r'(\d{1,5})(\.\d+)?s', str(detail.get('retryDelay', '')))
            if match:
                return max(1, int(match.group(1)) + (1 if match.group(2) else 0))
    except (KeyError, TypeError, AttributeError):
        pass
    return None


def uid():
    return uuid.uuid4().hex


def now():
    return datetime.now(timezone.utc).isoformat()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def text_hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def token_bound(text):
    # Conservative UTF-8 byte allowance, NOT measured provider token usage.
    return len(text.encode("utf-8"))


def load_json(text):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result
    def invalid(value):
        raise ValueError("Non-finite JSON value")
    return json.loads(text, object_pairs_hook=pairs, parse_constant=invalid)

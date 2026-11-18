"""User-facing explanation of a stopped run. The single owner of failure wording.

Rule: say WHERE it failed (stage), WHAT that means for the answer, and WHAT the user can do
(wait / narrow the question / needs an implementation fix). A technical failure is never
reported as "out of scope" or "no source found", and never as a reviewed answer.
"""

STAGES = {
    'A': 'understanding the question and searching the sources',
    'B': 'writing the answer',
    'C': 'reviewing the answer',
}

# action: what the user should do next
WAIT, NARROW, FIX, RETRY = 'wait', 'narrow', 'fix', 'retry'

KINDS = {
    'PROVIDER_TIMEOUT': ('the AI provider did not respond in time', RETRY),
    'OPERATION_TIMEOUT': ('the step exceeded its time limit', RETRY),
    'ACTIVE_DEADLINE': ('the whole request reached its time limit', RETRY),
    'PROVIDER_QUOTA': ('the AI provider rate limit or free quota was reached', WAIT),
    'PROVIDER_REQUEST_TOO_LARGE': ('the required context is too large for the provider\'s free-tier request limit', NARROW),
    'CONTEXT_LIMIT': ('the required context is too large for the configured token budget', NARROW),
    'BUDGET_EXHAUSTED': ('the request used up its call/token budget before a checked answer was ready', NARROW),
    'INVALID_CONTRACT': ('the AI response failed format/citation validation after the one allowed repair', RETRY),
    'PROVIDER_INCOMPLETE': ('the AI provider returned a truncated or blocked response', RETRY),
    'PROVIDER_FORMAT': ('the AI provider returned an invalid response', RETRY),
    'PROVIDER_CONFIG': ('the provider rejected the request format or model setting', FIX),
    'PROVIDER_AUTH': ('the provider rejected the API key or model access', FIX),
    'PROVIDER_NOT_CONFIGURED': ('the AI provider is not configured on the server', FIX),
    'PROVIDER_UNAVAILABLE': ('the AI provider was temporarily unavailable', WAIT),
    'PROVIDER_NETWORK': ('the connection to the AI provider failed', WAIT),
    'SOURCE_MISSING': ('a source passage is missing from the local index', FIX),
}

ADVICE = {
    WAIT: 'Wait a little and use "Retry this question".',
    RETRY: 'You can use "Retry this question"; if it repeats, share the reference at the end of this message.',
    NARROW: 'Ask a narrower question (for example one clause or one part of the question); the same oversized request is not resent.',
    FIX: 'This needs a server/implementation fix; retrying will not help until it is fixed.',
}


def explain(code, stage, evidence_found, run_id, retry_after=None, fallback=None):
    """Return (message, action) for a technical stop. Pure function: easy to test and to change."""
    what, action = KINDS.get(code, (None, RETRY))
    where = STAGES.get(stage)
    parts = []
    if evidence_found and stage in ('B', 'C'):
        parts.append('Source passages were found, but')
    elif evidence_found:
        parts.append('Some source passages were found, but')
    parts.append((what or (fallback or 'processing failed').rstrip('.').lower()) + (' while ' + where if where else '') + '.')
    message = ' '.join(parts)
    message = message[0].upper() + message[1:]
    message += ' No unreviewed answer was shown.'
    if code == 'PROVIDER_QUOTA':
        message += f' The provider asked to wait about {retry_after} seconds before retrying.' if retry_after else ' The provider did not say how long to wait; try again in a few minutes.'
    else:
        message += ' ' + ADVICE[action]
    message += f' (Ref: run {run_id[:8]}, {code})'
    return message, action

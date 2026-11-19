"""Version selection: the single owner of "which document version answers this message".

Order: (1) a version/release the user wrote in THIS message, (2) the version this chat already
used, (3) the documented default = the version(s) in the active index. A requested version that
is not indexed is reported, never silently substituted. Prompts may describe this rule but the
engine enforces it with this module.
"""
import json
import re
from .config import ROOT

ARCHIVE_PATH = ROOT / 'corpus' / 'ts38201_archive.json'

# "v18.0.0", "version 17.3.0", "ver. 16.0.0"; bare "4.2.3" is a clause, never a version.
_VERSION = re.compile(r'(?i)(?:\bv\s?|\bversion\s*:?\s*|\bver\.?\s*)(\d{1,2}\.\d{1,2}\.\d{1,2})\b')
# "Release 17", "Rel-17", "Rel 17", "R17" (only with Rel/Release; "R17" is too ambiguous alone)
_RELEASE = re.compile(r'(?i)\brel(?:ease)?[\s.\-]*(\d{1,2})\b')


def requested(text):
    """Explicit versions/releases in user text: {'versions': [...]} | {'releases': [...]} | None.
    Every version named is kept (e.g. a comparison), never just the first one."""
    text = text or ''
    found = []
    for match in _VERSION.finditer(text):
        version = '.'.join(str(int(x)) for x in match.group(1).split('.'))
        if version not in found:
            found.append(version)
    if found:
        return {'versions': found}
    releases = []
    for match in _RELEASE.finditer(text):
        if str(int(match.group(1))) not in releases:
            releases.append(str(int(match.group(1))))
    return {'releases': releases} if releases else None


def archive_inventory():
    try:
        return json.loads(ARCHIVE_PATH.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {'entries': []}


def select(text, chat_versions, indexed):
    """Decide the version(s) for one message.

    indexed: list of {'spec_number','version','release'} in the run's pinned corpus build.
    chat_versions: versions an earlier answer in this chat used (None if none).
    Returns {'status': 'ok'|'not_indexed'|'chat_version_unavailable', 'versions', 'source', 'requested'}.
    """
    available = sorted({d['version'] for d in indexed})
    ask = requested(text)
    if ask and 'versions' in ask:
        if set(ask['versions']) <= set(available):
            return {'status': 'ok', 'versions': ask['versions'], 'source': 'explicit', 'requested': ask}
        return {'status': 'not_indexed', 'versions': available, 'source': 'explicit', 'requested': ask}
    if ask and 'releases' in ask:
        match = sorted({d['version'] for d in indexed if str(d['release']) in ask['releases']})
        if match and {str(d['release']) for d in indexed if d['version'] in match} >= set(ask['releases']):
            return {'status': 'ok', 'versions': match, 'source': 'explicit', 'requested': ask}
        return {'status': 'not_indexed', 'versions': available, 'source': 'explicit', 'requested': ask}
    if chat_versions:
        if set(chat_versions) <= set(available):
            return {'status': 'ok', 'versions': sorted(chat_versions), 'source': 'chat', 'requested': None}
        return {'status': 'chat_version_unavailable', 'versions': available, 'source': 'chat', 'requested': {'versions': list(chat_versions)}}
    return {'status': 'ok', 'versions': available, 'source': 'default', 'requested': None}


def not_indexed_message(selection, spec_hint='38.201'):
    have = ', '.join('v' + v for v in selection['versions']) or 'none'
    if selection['status'] == 'chat_version_unavailable':
        asked = selection['requested']['versions']
        return (f'Earlier answers in this chat used TS {spec_hint} ' + ', '.join('v' + v for v in asked) +
                f', which is no longer in the active index (indexed now: {have}). To avoid mixing versions, '
                'start a new chat or name the version you want.')
    req = selection['requested']
    asked = ['v' + v for v in req.get('versions', [])] or ['Release ' + r for r in req.get('releases', [])]
    entries = archive_inventory().get('entries', [])
    listed = [a for a in asked if any(('v' + e.get('version', '')) == a or ('Release ' + str(e.get('release'))) == a for e in entries)]
    where = (' Listed in the official 3GPP archive but not indexed here: ' + ', '.join(listed) + '.') if listed else ''
    return (f'TS {spec_hint} ' + ' and '.join(asked) + f' is not fully available here.{where} '
            f'Indexed version(s): {have}. Ask again without a version to use the indexed one, or index that version first.')


def label(selection):
    reason = {'explicit': 'version you asked for', 'chat': 'version used earlier in this chat',
              'default': 'default: the indexed version, no version named'}[selection['source']]
    return {'versions': selection['versions'], 'source': selection['source'], 'reason': reason}

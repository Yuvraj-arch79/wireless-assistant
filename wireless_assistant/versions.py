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
    """Explicit version/release in user text: {'version': '17.0.0'} | {'release': '17'} | None."""
    text = text or ''
    match = _VERSION.search(text)
    if match:
        major, minor, editorial = (int(x) for x in match.group(1).split('.'))
        return {'version': f'{major}.{minor}.{editorial}'}
    match = _RELEASE.search(text)
    if match:
        return {'release': str(int(match.group(1)))}
    return None


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
    if ask and 'version' in ask:
        if ask['version'] in available:
            return {'status': 'ok', 'versions': [ask['version']], 'source': 'explicit', 'requested': ask}
        return {'status': 'not_indexed', 'versions': available, 'source': 'explicit', 'requested': ask}
    if ask and 'release' in ask:
        match = sorted({d['version'] for d in indexed if str(d['release']) == ask['release']})
        if match:
            return {'status': 'ok', 'versions': match, 'source': 'explicit', 'requested': ask}
        return {'status': 'not_indexed', 'versions': available, 'source': 'explicit', 'requested': ask}
    if chat_versions:
        if set(chat_versions) <= set(available):
            return {'status': 'ok', 'versions': sorted(chat_versions), 'source': 'chat', 'requested': None}
        return {'status': 'chat_version_unavailable', 'versions': available, 'source': 'chat', 'requested': {'version': ', '.join(chat_versions)}}
    return {'status': 'ok', 'versions': available, 'source': 'default', 'requested': None}


def not_indexed_message(selection, spec_hint='38.201'):
    asked = selection['requested'].get('version') or ('Release ' + selection['requested']['release'])
    have = ', '.join('v' + v for v in selection['versions']) or 'none'
    listed = [e for e in archive_inventory().get('entries', [])
              if e.get('version') == selection['requested'].get('version')
              or (selection['requested'].get('release') and str(e.get('release')) == selection['requested']['release'])]
    where = (' It is listed in the official 3GPP archive but is not indexed in this assistant.' if listed
             else ' It is not in the recorded archive inventory either.')
    if selection['status'] == 'chat_version_unavailable':
        return (f'Earlier answers in this chat used TS {spec_hint} v{asked}, which is no longer in the active index '
                f'(indexed now: {have}). To avoid mixing versions, start a new chat or name the version you want.')
    return (f'TS {spec_hint} {"v" + asked if asked[0].isdigit() else asked} is not available here.{where} '
            f'Indexed version(s): {have}. Ask again without a version to use the indexed one, or index that version first.')


def label(selection):
    reason = {'explicit': 'version you asked for', 'chat': 'version used earlier in this chat',
              'default': 'default: the indexed version, no version named'}[selection['source']]
    return {'versions': selection['versions'], 'source': selection['source'], 'reason': reason}

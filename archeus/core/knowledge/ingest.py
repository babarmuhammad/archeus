"""Meeting-note import, before the command (context-and-knowledge §8): read the
file, keep it as an artifact, and name and date the meeting. The decision
candidates in it come later, from the knowledge worker's call (P6).

The date is the file's own: an ISO date in its name, or in its first lines. A
file with neither is refused rather than dated by its mtime — asking the user is
P7's (§8: "date parsed from the file or asked").
"""

import os
import re

from ...infra.artifacts import store as artifacts
from ..application import knowledge as K

#: the largest notes file imported (the API's own body cap)
MAX_NOTES_BYTES = 1 << 20
_DATE = re.compile(r'(\d{4})-(\d{2})-(\d{2})')


def read_notes(path, held_at=None):
    """{name, held_at, sha256, size, path}; raises ValueError for what cannot
    be a meeting's notes."""
    if not (isinstance(path, str) and os.path.isfile(path)):
        raise ValueError('not a file: %r' % (path,))
    if os.path.getsize(path) > MAX_NOTES_BYTES:
        raise ValueError('notes over %d bytes' % MAX_NOTES_BYTES)
    with open(path, 'rb') as f:
        data = f.read()
    text = data.decode('utf-8', 'replace')
    stem = os.path.splitext(os.path.basename(path))[0]
    heading = next((ln[2:].strip() for ln in text.splitlines() if ln.startswith('# ')), '')
    name = heading or _DATE.sub('', stem).strip(' -_') or stem
    if held_at is None:
        m = _DATE.search(stem) or _DATE.search('\n'.join(text.splitlines()[:5]))
        if m is None:
            raise ValueError('no date in the file name or its first lines; give held_at')
        held_at = '%s-%s-%s' % m.groups()
    return {'name': name, 'held_at': held_at, 'sha256': artifacts.put(data), 'size': len(data),
            'path': os.path.abspath(path)}


def import_file(db, actor, path, project_id=None, held_at=None, idempotency_key=None):
    n = read_notes(path, held_at)
    return db.writer.execute(K.import_meeting, {
        'actor': actor, 'name': n['name'], 'held_at': n['held_at'], 'notes_sha256': n['sha256'],
        'notes_size': n['size'], 'imported_from': n['path'], 'project_id': project_id},
        idempotency_key=idempotency_key)

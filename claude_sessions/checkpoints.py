"""Read-only view of Claude Code's file checkpoints.

Claude Code snapshots a file before it edits it, so `/rewind` can restore an
earlier state. The store is `~/.claude/file-history/<session-id>/<name>@v<n>`,
where each file is the *whole* contents at that version — not a diff.

THE FORMAT IS NOT DOCUMENTED, so this module never assumes it.
------------------------------------------------------------
`<name>` is `sha256(<the absolute path exactly as the tool recorded it>)[:16]`.
That was established by hashing the file paths out of a real transcript and
matching them against the real directory — all 6 matched, none left over — and
it is re-established the same way on every call: we hash the paths *this*
session touched and look for them on disk. Nothing is decoded from the name.

The consequence is the important part: if Claude Code changes the scheme, the
lookup simply finds nothing and `history()` returns `recognised: False`. It
cannot mis-attribute one file's contents to another file's name, and the UI
turns the panel off rather than showing something invented. That is the only
honest posture for reading a private format, and it is why this is read-only:
archeus never writes here, never deletes here, and `/rewind` remains the only
thing that restores.
"""

import hashlib
import os
import re

from . import config as _c

_VER = re.compile(r'^([0-9a-f]{8,64})@v(\d+)$')


def store_dir(cfgdir=None):
    return os.path.join(cfgdir or _c.config_dir, 'file-history')


def _key(path):
    """The on-disk name for a path, under the scheme observed on disk."""
    return hashlib.sha256(path.encode('utf-8', 'replace')).hexdigest()[:16]


def _versions(sdir):
    """{key: [(n, fullpath, size, mtime)]} for one session's snapshot dir."""
    out = {}
    try:
        names = os.listdir(sdir)
    except OSError:
        return out
    for name in names:
        m = _VER.match(name)
        if not m:
            continue
        full = os.path.join(sdir, name)
        try:
            st = os.stat(full)
        except OSError:
            continue
        out.setdefault(m.group(1), []).append(
            (int(m.group(2)), full, st.st_size, st.st_mtime))
    for v in out.values():
        v.sort(key=lambda t: t[0])
    return out


def _edited_paths(jsonl):
    """Absolute paths this session wrote to, in first-touch order.

    Read straight off the tool calls — the same source `filesS` uses — so no
    extra parse pass is introduced for this feature.
    """
    from . import transcripts
    seen, order = set(), []
    for o in transcripts.iter_json(jsonl, prefilter='file_path'):
        content = (o.get('message') or {}).get('content')
        if not isinstance(content, list):
            continue
        for c in content:
            if not isinstance(c, dict) or c.get('type') != 'tool_use':
                continue
            if c.get('name') not in ('Write', 'Edit', 'NotebookEdit', 'MultiEdit'):
                continue
            fp = (c.get('input') or {}).get('file_path')
            if fp and fp not in seen:
                seen.add(fp)
                order.append(fp)
    return order


def history(sid, jsonl, cfgdir=None):
    """Checkpoints for one session.

    {recognised, files: [{path, name, versions: [{v, size, mtime}]}], orphans}

    `recognised` is False when the store exists but none of the paths this
    session edited resolve to a snapshot — i.e. the naming scheme moved. The
    caller must hide the panel in that case rather than guess.
    """
    sdir = os.path.join(store_dir(cfgdir), sid)
    if not os.path.isdir(sdir):
        return {'recognised': True, 'files': [], 'orphans': 0, 'store': False}
    bykey = _versions(sdir)
    if not bykey:
        return {'recognised': True, 'files': [], 'orphans': 0, 'store': False}
    files, matched = [], set()
    for path in _edited_paths(jsonl):
        vs = bykey.get(_key(path))
        if not vs:
            continue
        matched.add(_key(path))
        files.append({
            'path': path,
            'name': os.path.basename(path),
            'versions': [{'v': n, 'size': size, 'mtime': int(mt)}
                         for n, _f, size, mt in vs],
        })
    files.sort(key=lambda f: -f['versions'][-1]['mtime'])
    return {
        'recognised': bool(matched),
        'files': files,
        # snapshots we cannot name: an edit made before the transcript we have,
        # or a scheme change. Counted, never guessed at.
        'orphans': len(bykey) - len(matched),
        'store': True,
    }


def read_version(sid, path, v, cfgdir=None, limit=400000):
    """One snapshot's contents, or None. Read-only: nothing here restores."""
    sdir = os.path.join(store_dir(cfgdir), sid)
    full = os.path.join(sdir, f'{_key(path)}@v{int(v)}')
    if not os.path.isfile(full):
        return None
    try:
        with open(full, encoding='utf-8', errors='replace') as fh:
            return fh.read(limit)
    except OSError:
        return None


def diff_versions(sid, path, a, b, cfgdir=None):
    """Unified diff between two snapshots, for the read-only viewer."""
    import difflib
    ta, tb = (read_version(sid, path, a, cfgdir),
              read_version(sid, path, b, cfgdir))
    if ta is None or tb is None:
        return ''
    return ''.join(difflib.unified_diff(
        ta.splitlines(True), tb.splitlines(True),
        fromfile=f'{os.path.basename(path)}@v{a}',
        tofile=f'{os.path.basename(path)}@v{b}', n=3))

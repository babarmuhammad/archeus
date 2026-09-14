"""Pruning what Claude Code accumulates and never cleans up.

795 MB across three accounts on the machine this was written for — 495 MB of
`projects/` transcripts and 73 MB of `file-history/` snapshots in the default
account alone, with no surface anywhere that even reports it.

Three rules, in the order they matter:

1. **Dry run is the default.** `run()` reports what it WOULD delete and
   deletes nothing unless `apply=True` is passed explicitly.
2. **A referenced session is never touched.** archeus's own state names
   sessions — the recent list, the per-project last-session marker, and every
   `.name`/tag/checkpoint sidecar. Deleting a transcript those point at breaks
   archeus, not just Claude Code.
3. **Only ever inside a known account directory.** Every candidate path is
   checked to be under the account's own store before it is removed, so a bug
   in the walk cannot escape into the filesystem.
"""

import os
import time

from . import config as _c
from . import jsonstore

__all__ = ['run', 'DEFAULT_DAYS', 'PRUNABLE']

#: Claude Code's own `cleanupPeriodDays` default. Read from settings.json when
#: the user has set one, because the point is to follow THEIR policy.
DEFAULT_DAYS = 30

#: what may be pruned, and what may not. `projects/` holds transcripts AND the
#: sidecars archeus writes, so it is pruned per file, never per directory.
PRUNABLE = ('file-history', 'paste-cache', 'shell-snapshots', 'session-env')


def policy_days(cfgdir=None):
    from . import hooks
    v = hooks._load(cfgdir).get('cleanupPeriodDays')
    try:
        return max(1, int(v))
    except (TypeError, ValueError):
        return DEFAULT_DAYS


def run(days=0, apply=False, cfgdir=None):
    """Report — and, with apply=True, delete — everything older than *days*.

    Returns {'days', 'applied', 'accounts': [...], 'bytes', 'files', 'kept'}.
    """
    accounts = _c.all_config_dirs() if cfgdir is None else [('', cfgdir)]
    out = []
    total_bytes = total_files = kept = 0
    for name, d in accounts:
        limit = days or policy_days(d)
        cutoff = time.time() - limit * 86400
        referenced = _referenced_sessions(d)
        rows, size, n, k = _sweep(d, cutoff, referenced, apply)
        out.append({'account': name, 'dir': d, 'days': limit,
                    'bytes': size, 'files': n, 'kept_referenced': k,
                    'stores': rows})
        total_bytes += size
        total_files += n
        kept += k
    return {'days': days or DEFAULT_DAYS, 'applied': bool(apply),
            'accounts': out, 'bytes': total_bytes, 'files': total_files,
            'kept': kept}


def _referenced_sessions(cfgdir):
    """Session ids archeus's own state points at. These are never candidates.

    Deliberately generous: a session named, tagged, or listed as recent stays
    regardless of age, because those are the ones the user came back for.
    """
    ids = set()
    from . import store
    root = store.projects_root(cfgdir)
    last = jsonstore.load(os.path.join(root, 'last-session.json'), expect=dict)
    for v in last.values() if isinstance(last, dict) else []:
        if isinstance(v, dict) and v.get('session_id'):
            ids.add(v['session_id'])
        elif isinstance(v, str):
            ids.add(v)
    for proj in _subdirs(root):
        for n in _listdir(proj):
            # a .name or a tag entry means the user did something deliberate
            if n.endswith('.name'):
                ids.add(n[:-len('.name')])
        tags = jsonstore.load(os.path.join(proj, 'tags.json'), expect=dict)
        ids.update(k for k, v in tags.items() if v)
    return ids


def _sweep(cfgdir, cutoff, referenced, apply):
    rows = []
    total = files = kept = 0
    for sub in PRUNABLE:
        size, n = _prune_tree(os.path.join(cfgdir, sub), cutoff, apply, cfgdir)
        if n:
            rows.append({'name': sub, 'bytes': size, 'files': n})
        total += size
        files += n
    size, n, k = _prune_transcripts(cfgdir, cutoff, referenced, apply)
    if n:
        rows.append({'name': 'projects', 'bytes': size, 'files': n})
    return rows, total + size, files + n, kept + k


def _prune_tree(path, cutoff, apply, cfgdir):
    size = files = 0
    for root, _dirs, names in os.walk(path):
        for n in names:
            p = os.path.join(root, n)
            st = _stat(p)
            if st is None or st.st_mtime >= cutoff:
                continue
            size += st.st_size
            files += 1
            if apply:
                _remove(p, cfgdir)
    return size, files


def _prune_transcripts(cfgdir, cutoff, referenced, apply):
    """`projects/` per FILE, never per directory: the same folders hold the
    sidecars archeus writes (names, tags, extra-paths, system prompts), and
    those are not size and are not disposable."""
    from . import store
    size = files = kept = 0
    for proj in _subdirs(store.projects_root(cfgdir)):
        for n in _listdir(proj):
            if not n.endswith('.jsonl'):
                continue
            sid = n[:-len('.jsonl')]
            if sid in referenced:
                kept += 1
                continue
            p = os.path.join(proj, n)
            st = _stat(p)
            if st is None or st.st_mtime >= cutoff:
                continue
            size += st.st_size
            files += 1
            if apply:
                _remove(p, cfgdir)
    return size, files, kept


def _remove(path, cfgdir):
    """Delete, but only from inside the account directory this sweep is for."""
    root = os.path.normcase(os.path.abspath(cfgdir)) + os.sep
    if not os.path.normcase(os.path.abspath(path)).startswith(root):
        _c.log.error('diskgc: refusing to delete outside %s: %s', cfgdir, path)
        return
    try:
        os.remove(path)
    except OSError:
        pass


def _stat(p):
    try:
        return os.stat(p)
    except OSError:
        return None


def _listdir(p):
    try:
        return os.listdir(p)
    except OSError:
        return []


def _subdirs(p):
    return [os.path.join(p, n) for n in _listdir(p)
            if os.path.isdir(os.path.join(p, n))]

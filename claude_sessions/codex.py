"""Codex: where it keeps its sessions, and how to read them.

Read-only, and deliberately so — the same posture `checkpoints.py` takes toward
Claude Code's file-history store. Codex owns these files, the schema is not
documented anywhere, and it holds the database open while it runs.

Two stores, and they are not interchangeable:

* `$CODEX_HOME/state_*.sqlite`, table `threads` — the INDEX. One row per
  session with `id, rollout_path, cwd, preview, first_user_message, model,
  tokens_used, git_branch, archived, created_at_ms, updated_at_ms`. Everything a
  session LIST needs is here, which is why the list never opens a transcript.
* `$CODEX_HOME/sessions/<yyyy>/<mm>/<dd>/rollout-<iso>-<uuid>.jsonl` — the
  transcript, named by the index rather than derivable from the session id. That
  is precisely why `store.transcript_path` had to become a function.

The file name is versioned (`state_5.sqlite`), so `state_6` will ship: the glob
takes the highest rather than naming one. Anything sqlite raises is read as "no
sessions" the way `mcp.py` reads a timed-out status — a database another process
has locked is a normal Tuesday, not an error worth showing.
"""

import glob
import os
import sqlite3

from . import paths as _paths
from . import transcripts as _t

#: how long to wait for a lock before giving up. Codex holds the database open
#: while it runs, and on Windows a concurrent write answers `database is
#: locked`; a session list is not worth blocking a UI thread for.
_TIMEOUT = 1.0

#: the columns the list needs. Named rather than `SELECT *` so a schema that
#: drops one is a clean "not recognised" instead of an IndexError three frames
#: away.
_COLS = ('id', 'rollout_path', 'cwd', 'preview', 'first_user_message',
         'model', 'tokens_used', 'git_branch', 'archived', 'updated_at_ms',
         'created_at_ms')


def db_path(home):
    """The newest state database under *home*, or ''."""
    got = sorted(glob.glob(os.path.join(home or '', 'state_*.sqlite')))
    return got[-1] if got else ''


def _rows(home, where='', args=()):
    """[dict] from the threads table. Any sqlite failure is an empty list: the
    file is another program's, and it is allowed to be locked, missing, or a
    shape this version does not know."""
    p = db_path(home)
    if not p:
        return []
    try:
        con = sqlite3.connect('file:%s?mode=ro' % p.replace(os.sep, '/'),
                              uri=True, timeout=_TIMEOUT)
        try:
            cur = con.execute(
                'SELECT %s FROM threads %s' % (', '.join(_COLS), where), args)
            return [dict(zip(_COLS, r)) for r in cur.fetchall()]
        finally:
            con.close()
    except Exception:
        return []


def real_cwd(cwd):
    """Codex records a working directory with Windows' extended-length prefix
    (`\\\\?\\C:\\...`) on some paths and without it on others. The same project
    must encode to the same folder either way, or a project appears twice."""
    c = (cwd or '').strip()
    for pre in ('\\\\?\\UNC\\', '\\\\?\\'):
        if c.startswith(pre):
            c = ('\\\\' + c[len(pre):]) if pre.endswith('UNC\\') else c[len(pre):]
            break
    return c


def _enc(cwd):
    return _paths.encode_component(real_cwd(cwd))


def has_project(home, enc):
    """Does Codex know this project? Asked of the INDEX, because archeus's own
    sidecar folder under a Codex home is created lazily and its absence says
    nothing about whether sessions exist."""
    return any(_enc(r['cwd']) == enc for r in _rows(home))


def projects(home):
    """[(mtime, real path, enc)] — one entry per project Codex has worked in.

    `gui.list_projects` walks `<home>/projects/*` on disk for Claude Code, which
    does not exist here: the index is the only record that a project was ever
    opened.
    """
    best = {}
    for r in _rows(home):
        path = real_cwd(r['cwd'])
        if not path:
            continue
        enc = _paths.encode_component(path)
        mtime = (r['updated_at_ms'] or r['created_at_ms'] or 0) / 1000.0
        cur = best.get(enc)
        if not cur or mtime > cur[0]:
            best[enc] = (mtime, path, enc)
    return list(best.values())


def _home_of(folder):
    """`<home>/projects/<enc>` -> home. The sidecar folder archeus keeps for a
    project under a Codex home, which is the handle every caller already has."""
    return os.path.dirname(os.path.dirname(os.path.normpath(folder or '')))


def scan(folder, archived=False):
    """[(mtime, sid, preview, count)] for one project, newest first.

    Same tuple `sessions.scan_sessions` returns for Claude Code. `count` is the
    only field the index cannot answer, so it is read from the rollout — and a
    rollout that is missing or unreadable gives 0 rather than a guess.
    """
    home, enc = _home_of(folder), os.path.basename(os.path.normpath(folder or ''))
    out = []
    for r in _rows(home):
        if _enc(r['cwd']) != enc:
            continue
        if bool(r['archived']) != bool(archived):
            continue
        mtime = (r['updated_at_ms'] or r['created_at_ms'] or 0) / 1000.0
        preview = (r['preview'] or r['first_user_message'] or '').strip()
        out.append((mtime, r['id'], preview[:200].replace('\n', ' '),
                    _count(r['rollout_path'])))
    out.sort(reverse=True)
    return out


def transcript_path(folder, sid):
    """The rollout file for one session. Named BY THE INDEX — there is no rule
    that derives it from the session id, which is the whole reason this is a
    function rather than a join."""
    for r in _rows(_home_of(folder), 'WHERE id = ?', (sid,)):
        return r['rollout_path'] or ''
    return ''


def _count(rollout):
    """Turns in a rollout: the `user_message` and `agent_message` events.

    NOT the `response_item` messages, and that distinction is the whole
    function. A rollout carries the developer instructions and an
    `<environment_context>` block as `response_item` messages with role
    `developer` and `user`, so counting those reports three turns for a session
    in which the user said one thing.
    """
    n = 0
    for obj in _t.iter_json(rollout, prefilter='event_msg'):
        if obj.get('type') != 'event_msg':
            continue
        if (obj.get('payload') or {}).get('type') in ('user_message',
                                                      'agent_message'):
            n += 1
    return n


def fold(obj, s):
    """One rollout record into the shared stats dict.

    Verified against a real rollout rather than inferred: every line is
    `{timestamp, type, payload}` with `type` in `session_meta`, `event_msg`,
    `response_item`, `turn_context`.
    """
    ts = obj.get('timestamp')
    if isinstance(ts, str):
        ep = _t.iso_to_epoch(ts)
        if ep is not None:
            if s['first_ts'] is None or ep < s['first_ts']:
                s['first_ts'] = ep
            if s['last_ts'] is None or ep > s['last_ts']:
                s['last_ts'] = ep

    kind = obj.get('type')
    p = obj.get('payload') or {}
    if kind == 'session_meta':
        if p.get('cwd'):
            s['cwd'] = real_cwd(p['cwd'])
    elif kind == 'turn_context':
        # the model is named per TURN, not once per session: a session that
        # changed model half way through has two, and both belong in the list
        m = p.get('model')
        if m and m not in s['models']:
            s['models'].append(m)
        if p.get('cwd') and not s['cwd']:
            s['cwd'] = real_cwd(p['cwd'])
    elif kind == 'event_msg':
        t = p.get('type')
        if t in ('user_message', 'agent_message'):
            s['count'] += 1
        if t == 'user_message':
            txt = (p.get('message') or '').strip()
            if txt:
                s['preview'] = txt[:200].replace('\n', ' ')
        elif t == 'error':
            s['api_errors'] += 1

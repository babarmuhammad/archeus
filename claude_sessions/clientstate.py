"""Claude Code's own client state, which archeus had never opened.

Four stores, all read-only here:

- `~/.claude/.claude.json`  — 73 KB on this machine, 15 projects. Per project:
  cost, token totals, the last session id, lines added/removed, MCP approval
  state, allowed tools. At the top level: `skillUsage`, `pluginUsage` and
  `agentLastUsed`, which are the only record of what is actually being USED
  versus carried as dead weight — a question archeus could not answer.
- `~/.claude/history.jsonl` — 1.1 MB of prompt history across every project.
- `~/.claude/daemon/roster.json` — live background agents.
- `~/.claude/teams/`, `~/.claude/tasks/` — agent teams.

None of these formats is documented, so every reader here follows the
`checkpoints.py` discipline: re-derive from what archeus already knows, match
what is actually on disk, and report `recognised: False` rather than pairing
records at random. The teams reader especially — the docs say a team is named
`session-` plus the first 8 characters of the session id, and on the machine
this was written for `teams/` is EMPTY while `tasks/` is keyed by the full
session UUID. The documented derivation and the observed layout already
disagree, so nothing may be built on the documented one.
"""

import os
import re
import time

from . import config as _c
from . import jsonstore
from . import transcripts

__all__ = ['client_json', 'project_state', 'usage_rollup', 'prompt_history',
           'daemon_roster', 'teams', 'disk_report', 'hook_activity']


def _path(name, cfgdir=None):
    return os.path.join(cfgdir or _c.config_dir, name)


# ── .claude.json ─────────────────────────────────────────────

def client_json(cfgdir=None):
    # quarantine=False: this file belongs to Claude Code, which rewrites it
    # while archeus is running. Quarantining is the right answer for a file
    # archeus OWNS — the next write would otherwise destroy the evidence —
    # but here an unparseable read most likely means we caught a live write
    # mid-flight, and renaming the user's `.claude.json` out from under a
    # running session is a far worse outcome than reading it again next tick.
    # (Observed: the test suite's real-file guard caught exactly this.)
    return jsonstore.load(_path('.claude.json', cfgdir), expect=dict,
                          quarantine=False)


def project_state(project_path, cfgdir=None):
    """What Claude Code recorded about ONE project, or {} when it has no entry.

    The keys are the project's real path written with FORWARD slashes even on
    Windows ('D:/Claude'), so both sides go through normalisation rather than
    being compared as strings.
    """
    projects = client_json(cfgdir).get('projects') or {}
    want = _norm(project_path)
    for k, v in projects.items():
        if _norm(k) == want and isinstance(v, dict):
            return v
    return {}


def _norm(p):
    # abspath already folds '/' to '\' on Windows and there are no backslashes
    # to fold on POSIX, so normcase(abspath(...)) is the whole job.
    return os.path.normcase(os.path.abspath(p or '')).rstrip('\\/')


def usage_rollup(cfgdir=None):
    """What is actually being used: skills, plugins and agents with a count and
    an age. Sorted most-used first; never-used entries simply are not present,
    which is the answer to "what is dead weight" from the other side."""
    d = client_json(cfgdir)
    now = time.time()

    def rows(key, count_key='usageCount'):
        out = []
        for name, v in (d.get(key) or {}).items():
            if isinstance(v, dict):
                used, last = v.get(count_key, 0), v.get('lastUsedAt', 0)
            else:
                used, last = 0, v            # agentLastUsed maps to a bare ms
            out.append({'name': name, 'count': used,
                        'last_used': _age(now, last)})
        out.sort(key=lambda r: (-r['count'], r['name']))
        return out

    return {'skills': rows('skillUsage'), 'plugins': rows('pluginUsage'),
            'agents': rows('agentLastUsed')}


# ── what actually reached your sessions ──────────────────────
#
# `skillUsage` above answers ONE question: how often did you TYPE `/name`. It is
# the only thing Claude Code counts, and on this machine it says
# `caveman:caveman` was used twice, 56 days ago — for a plugin that shapes every
# single session, every day. Both are true: caveman and ponytail arrive through
# SessionStart hooks, which touch no counter.
#
# The transcripts do record it. A hook run is stored as
#   {"type":"attachment","attachment":{"type":"hook_success","hookName":…,
#    "hookEvent":"SessionStart","command":…,"content":…}}
# so "in how many of your recent sessions did this actually run" is answerable
# from data archeus already streams — and it is the number the user expects to
# see next to caveman and ponytail.

#: recomputed at most this often; a walk over recent transcripts is cheap but
#: not free, and nothing here is on a per-turn path
ACTIVITY_TTL = 900
ACTIVITY_SESSIONS = 40


def _activity_cache(cfgdir=None):
    return _path('archeus-activity.json', cfgdir)


def hook_activity(cfgdir=None, limit=ACTIVITY_SESSIONS, refresh=False):
    """{'sessions': N, 'hits': {token: {'sessions': n, 'last_days': d}}}.

    `token` is a lowercased word out of the hook's name or command path, which
    is what lets a caller ask "did anything called `caveman` run?" without this
    module knowing what a plugin is.

    Bounded three ways, because this reads real transcripts: the newest `limit`
    sessions only, a `prefilter` so a line without a hook record is never parsed
    (the reason `transcripts.iter_json` takes one), and a disk cache with a TTL.
    """
    cache = jsonstore.load(_activity_cache(cfgdir), expect=dict)
    if (not refresh and cache.get('at')
            and time.time() - float(cache.get('at') or 0) < ACTIVITY_TTL):
        return {'sessions': cache.get('sessions', 0), 'hits': cache.get('hits', {})}

    from . import store
    root = store.projects_root(cfgdir)
    files = []
    for proj in _listdir(root):
        d = os.path.join(root, proj)
        try:
            for fn in os.listdir(d):
                if fn.endswith('.jsonl'):
                    p = os.path.join(d, fn)
                    files.append((os.path.getmtime(p), p))
        except OSError:
            continue
    files.sort(reverse=True)
    files = files[:limit]

    now = time.time()
    hits = {}
    for mtime, p in files:
        seen = set()
        for obj in transcripts.iter_json(p, prefilter='hook_success'):
            att = obj.get('attachment')
            if not isinstance(att, dict) or att.get('type') != 'hook_success':
                continue
            seen |= _tokens(att)
        for tok in seen:
            row = hits.setdefault(tok, {'sessions': 0, 'last': 0})
            row['sessions'] += 1
            row['last'] = max(row['last'], mtime)
    out = {'sessions': len(files),
           'hits': {t: {'sessions': v['sessions'],
                        'last_days': int((now - v['last']) // 86400)}
                    for t, v in hits.items()}}
    _c.write_json_atomic(_activity_cache(cfgdir),
                         dict(out, at=now))
    return out


_TOKEN_RE = re.compile(r'[a-z0-9][a-z0-9_-]{2,}')
#: path noise that would otherwise match everything
_TOKEN_SKIP = {'claude', 'plugins', 'cache', 'hooks', 'python', 'exe', 'com',
               'users', 'appdata', 'local', 'programs', 'scripts', 'skills',
               'sessionstart', 'userpromptsubmit', 'startup', 'true', 'false'}


def _tokens(att):
    """Lowercased words identifying WHAT ran: the hook's name plus the parts of
    the command path. A plugin's hook lives under a directory named after it,
    which is what makes this work without parsing anyone's format."""
    raw = '%s %s' % (att.get('hookName') or '', att.get('command') or '')
    return {t for t in _TOKEN_RE.findall(raw.lower().replace('\\', '/'))
            if t not in _TOKEN_SKIP}


def _age(now, ms):
    """Claude Code stores epoch MILLISECONDS. Seconds would read as 1970."""
    if not ms:
        return ''
    secs = now - (ms / 1000.0)
    if secs < 90:
        return 'now'
    if secs < 5400:
        return '%dm' % (secs // 60)
    if secs < 172800:
        return '%dh' % (secs // 3600)
    return '%dd' % (secs // 86400)


# ── history.jsonl ────────────────────────────────────────────

def prompt_history(query='', limit=200, cfgdir=None):
    """Prompts typed across every project, newest first.

    The existing Search page covers session titles and previews; this is the
    text the user actually wrote, which is usually what they remember.
    """
    p = _path('history.jsonl', cfgdir)
    q = (query or '').lower().strip()
    terms = q.split()
    out = []
    for obj in transcripts.iter_json(p):
        text = obj.get('display') or ''
        if not text:
            continue
        if terms and not all(t in text.lower() for t in terms):
            continue
        out.append({'text': text[:400],
                    'project': obj.get('project') or '',
                    'sid': obj.get('sessionId') or '',
                    'ts': obj.get('timestamp') or 0})
    out.reverse()                                  # the file is oldest-first
    return out[:limit]


# ── background agents ────────────────────────────────────────

def daemon_roster(cfgdir=None):
    """Live background agents. An EMPTY roster is the common case and must read
    as 'no background agents', not as an error."""
    p = _path(os.path.join('daemon', 'roster.json'), cfgdir)
    if not os.path.isfile(p):
        return {'running': False, 'workers': [], 'recognised': False}
    d = jsonstore.load(p, expect=dict, quarantine=False)
    workers = d.get('workers')
    if not isinstance(workers, dict):
        return {'running': False, 'workers': [], 'recognised': False}
    from . import proc
    pid = d.get('supervisorPid')
    return {'running': bool(pid) and proc.pid_alive(pid) is not False,
            'supervisor_pid': pid,
            'updated': _age(time.time(), d.get('updatedAt', 0)),
            'workers': [{'id': k, **(v if isinstance(v, dict) else {})}
                        for k, v in workers.items()],
            'recognised': True}


def teams(cfgdir=None):
    """Agent teams and their task directories.

    `recognised` is False whenever nothing on disk matches, which on most
    machines is simply because the feature is experimental and unused. It is
    NOT an error state, and the UI must say "not in use".
    """
    root = _path('teams', cfgdir)
    tasks_root = _path('tasks', cfgdir)
    found = []
    for name in _listdir(root):
        cfg = jsonstore.load(os.path.join(root, name, 'config.json'),
                             expect=dict, quarantine=False)
        members = cfg.get('members')
        found.append({'name': name,
                      'members': members if isinstance(members, list) else [],
                      'inboxes': _listdir(os.path.join(root, name, 'inboxes'))})
    # Task dirs are keyed by the FULL session UUID here, not by the documented
    # `session-<first 8>` team name, so they are reported as their own list
    # rather than joined to a team by a rule the data does not support.
    task_dirs = [{'session': n,
                  'highwater': _read_small(os.path.join(tasks_root, n, '.highwatermark'))}
                 for n in _listdir(tasks_root)]
    return {'teams': found, 'tasks': task_dirs,
            'recognised': bool(found or task_dirs)}


def _listdir(p):
    try:
        return sorted(n for n in os.listdir(p)
                      if os.path.isdir(os.path.join(p, n)) or n.endswith('.json'))
    except OSError:
        return []


def _read_small(p, cap=64):
    try:
        with open(p, encoding='utf-8', errors='replace') as f:
            return f.read(cap).strip()
    except OSError:
        return ''


# ── disk ─────────────────────────────────────────────────────

#: everything Claude Code accumulates and never prunes on its own
DISK_DIRS = ('projects', 'file-history', 'paste-cache', 'telemetry',
             'session-env', 'plans', 'backups', 'shell-snapshots', 'todos')


def disk_report(cfgdir=None):
    """Size and age per store, per account. 471 MB of `projects/` and 64 MB of
    `file-history/` here, with no surface anywhere that says so."""
    out = []
    for name, d in (_c.all_config_dirs() if cfgdir is None else [('', cfgdir)]):
        rows = []
        for sub in DISK_DIRS:
            p = os.path.join(d, sub)
            size, files, oldest = _measure(p)
            if files:
                rows.append({'name': sub, 'bytes': size, 'files': files,
                             'oldest_days': oldest})
        rows.sort(key=lambda r: -r['bytes'])
        out.append({'account': name, 'dir': d, 'stores': rows,
                    'bytes': sum(r['bytes'] for r in rows)})
    return {'accounts': out, 'bytes': sum(a['bytes'] for a in out)}


def _measure(path):
    """(bytes, files, oldest_in_days). One walk, no per-file exception noise —
    a file that vanishes mid-walk is normal here."""
    size = files = 0
    oldest = None
    now = time.time()
    for root, _dirs, names in os.walk(path):
        for n in names:
            try:
                st = os.stat(os.path.join(root, n))
            except OSError:
                continue
            size += st.st_size
            files += 1
            if oldest is None or st.st_mtime < oldest:
                oldest = st.st_mtime
    return size, files, int((now - oldest) // 86400) if oldest else 0

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
        # changed model half way through has two, and both belong in the list.
        # Most-recent LAST, because `_spend` attributes a turn's tokens to
        # `models[-1]` — a session that went A, B, A would otherwise bill the
        # third stretch to B.
        m = p.get('model')
        if m:
            if m in s['models']:
                s['models'].remove(m)
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
        elif t == 'token_count':
            _spend(p, s)


#: Codex's five token fields, and what they mean next to Claude Code's four.
#: `input_tokens` is the WHOLE prompt and `cached_input_tokens` the part of it
#: that was served from cache — the binary names their difference
#: `non_cached_input_tokens`, which is what archeus calls `in`. There is no
#: fourth: a cache WRITE is not billed as its own line by this provider, so
#: `cache_create` stays 0 rather than being invented out of the difference.
#: `reasoning_output_tokens` is a subset of `output_tokens`, not a sibling, so
#: adding it would count the thinking twice.
def _split(u):
    u = u or {}
    cr = u.get('cached_input_tokens') or 0
    return {'in': max(0, (u.get('input_tokens') or 0) - cr),
            'out': u.get('output_tokens') or 0,
            'cache_read': cr, 'cache_create': 0}


def _spend(p, s):
    """A `token_count` event into `usage_by_model`.

    `total_token_usage` is CUMULATIVE for the session, not the turn — summing
    one event per turn would multiply a session's spend by its turn count. So
    what is banked is the DELTA against what has already been attributed, which
    `usage_by_model` itself records: the sum over its models is, by
    construction, the last total this function saw. That needs no scratch key on
    `s` — which it could not have, because the disk cache compares a cached
    entry's keys against `_EMPTY_STATS` and would reject every one carrying an
    extra field.

    `last_token_usage` is deliberately not the source. It is the right number
    per turn, but only if exactly one `token_count` fires per turn, and nothing
    in the schema promises that; a delta against the cumulative figure is
    correct however many arrive.
    """
    cum = _split(((p.get('info') or {}).get('total_token_usage')))
    if not any(cum.values()):
        return
    model = s['models'][-1] if s['models'] else 'codex'
    u = s['usage_by_model'].setdefault(
        model, {'in': 0, 'out': 0, 'cache_read': 0, 'cache_create': 0})
    for k in ('in', 'out', 'cache_read'):
        seen = sum(m[k] for m in s['usage_by_model'].values())
        # a resumed rollout can restart the count; never bank a negative
        u[k] += max(0, cum[k] - seen)


def launch_argv(exe, choice, opts, cwd):
    """The argv that opens a Codex session. Codex's own vocabulary, not a
    translation of Claude Code's — which is why this is here rather than a
    branch inside `build_launch_command`.

    Every verb is checked against `codex --help` on the installed binary:
    `resume [SESSION_ID]` with `--last` for the most recent, `fork` the same
    shape, and a bare `codex` for a new one. There is no `--session-id`, so a
    new session's id is Codex's to mint and archeus learns it from the index —
    which is also why nothing is recorded here the way the Claude path records
    a provider against an id it chose.
    """
    args = [exe]
    if choice == 'continue':
        args += ['resume', '--last']
    elif choice.startswith('resume:'):
        args += ['resume', choice[7:]]
    elif choice.startswith('resume-named::'):
        args += ['resume', choice[14:].split('::', 1)[0]]
    elif choice.startswith('fork:'):
        args += ['fork', choice[5:]]
    if opts.get('model'):
        args += ['-m', opts['model']]
    # reasoning effort is a CONFIG key here, not a flag: `-c` layers one value
    # over config.toml, which is the documented way to set it per invocation.
    if opts.get('effort'):
        args += ['-c', 'model_reasoning_effort=%s' % opts['effort']]
    # Claude Code's permission modes and Codex's approval policies are two
    # vocabularies over the same idea; `PERMS` maps only where the meaning
    # actually matches, and anything else is left to Codex's own default.
    perm = PERMS.get(opts.get('perm') or '')
    if perm:
        args += ['-a', perm]
    for extra in (opts.get('add_dirs') or []):
        args += ['--add-dir', extra]
    if cwd:
        args += ['-C', cwd]
    if opts.get('prompt'):
        args += [str(opts['prompt'])]
    return args


#: Claude Code permission mode -> Codex approval policy, where the two mean the
#: same thing. `plan` and `acceptEdits` have no equivalent (Codex's sandbox is
#: the axis it varies, not the edit gate), so they map to nothing and Codex
#: keeps its own default rather than being handed the closest-looking value.
PERMS = {
    'bypassPermissions': 'never',
    'default': 'on-request',
}


def models(home):
    """Every model this Codex install has actually been pointed at, newest use
    first, plus whatever `config.toml` names as the default.

    READ, never invented. The binary carries a dozen `gpt-5.*` strings and a
    static copy of them would be wrong the first time `codex update` runs — the
    same reason `checkpoints.py` refuses to decode a store it does not own. What
    IS reliable is what Codex itself recorded: one row per thread, each naming
    the model it ran on. A fresh install answers with the config default alone,
    or with nothing, and the picker is a free-text box either way.
    """
    seen = []
    for r in sorted(_rows(home), key=lambda r: -(r['updated_at_ms'] or 0)):
        m = (r['model'] or '').strip()
        if m and m not in seen:
            seen.append(m)
    cfg = _config_model(home)
    if cfg and cfg not in seen:
        seen.insert(0, cfg)
    return seen


def _config_model(home):
    """`model = "..."` from config.toml, or ''.

    One regex rather than a TOML parser: the file is another program's, the
    stdlib's `tomllib` would raise on a shape this version does not know, and
    the answer is a suggestion in a picker — a miss costs nothing and a crash
    costs the modal.
    """
    import re
    try:
        with open(os.path.join(home or '', 'config.toml'),
                  encoding='utf-8', errors='ignore') as f:
            head = f.read(65536)
    except OSError:
        return ''
    # top-level only: a `[profiles.x]` section may name its own model, and that
    # one is not what a bare `codex` run uses
    top = head.split('\n[', 1)[0]
    m = re.search(r'(?m)^\s*model\s*=\s*["\']([^"\']+)["\']', top)
    return m.group(1) if m else ''

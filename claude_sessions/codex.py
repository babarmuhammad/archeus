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


def catalogue(home=None):
    """[{id, label, provider, cost, context, thinking}] — every model a Codex
    install could run, or [].

    Codex publishes no catalogue of its own: there is no `codex models`, the
    binary carries a dozen `gpt-5.*` strings with no way to tell a live id from
    a retired one, and `codex doctor` reports the install rather than the menu.
    What DOES exist, on a machine that also has pi, is pi's shipped provider
    data — `openai-codex.json` is exactly the eight models Codex offers, with
    their prices and their reasoning levels, maintained by someone who tracks
    them and updated by `pi update`.

    Reading another tool's catalogue is unusual enough to say why: the
    alternative was a list typed into this file, which is the thing `models()`
    two functions down refuses to do and for the same reason — it would be wrong
    the first time `codex update` runs, and silently. A borrowed READ that goes
    stale visibly (the file stops existing when pi is uninstalled) beats an
    invention that goes stale invisibly. With no pi, this is [] and the launch
    field is what it always was: free text over whatever Codex has run.
    """
    from . import pi as _pi
    return [r for r in _pi.catalogue() if r['provider'] == 'openai-codex']


#: what `codex doctor` prints in its Notes block, and the two lines worth
#: reading out of it. Anchored on the label rather than the glyph: the status
#: marks are `✓ ⚠ ✗ ↑` and which one a line gets is Codex's business, while the
#: label is the thing the report is ABOUT.
_UPD_RE = r'updates\s+(\S+)\s+available\s+\(current\s+(\S+)\)'


#: one `RateLimitDetails` -> (label, pct, resets_iso), or None.
#:
#: The field names are read out of the installed binary's own type metadata
#: rather than guessed: it declares `used_percent` beside `window_minutes` and
#: `resets_at`, with `window_duration_mins` and `reset_at` as alternate spellings
#: in adjacent struct runs. All four are accepted, because which one a build
#: emits is not something archeus gets to decide — and this is the same posture
#: `usage._extract_windows` takes toward Anthropic's payload.
#:
#: The LABEL comes from the window's own length, not from the key it arrived
#: under. Codex calls them `primary` and `secondary`, which say nothing to a
#: reader; 300 minutes is a session window and 10080 is a weekly one, and those
#: are the two words the rest of this app already prints.
def _rl_window(d):
    if not isinstance(d, dict):
        return None
    pct = d.get('used_percent')
    if pct is None:
        return None
    try:
        pct = max(0.0, min(float(pct), 100.0))
    except (TypeError, ValueError):
        return None
    mins = d.get('window_minutes') or d.get('window_duration_mins') or 0
    try:
        mins = int(mins)
    except (TypeError, ValueError):
        mins = 0
    label = 'weekly' if mins >= 2880 else 'session' if mins else 'limit'
    return (label, pct, d.get('resets_at') or d.get('reset_at') or '')


def rate_limits(home=None):
    """[(label, pct, resets_iso)] for this CODEX_HOME, newest rollout wins.

    Codex publishes its windows on the API response and records them in the
    rollout — there is no endpoint to poll and no subcommand that prints them.
    `codex doctor` does NOT: checked against the installed 0.142, its sections
    are Notes / Environment / Configuration / Updates / Connectivity /
    Background Server and none of them carries a limit. So the transcript is
    the only source, which also means this is free and offline.

    Returns [] when nothing has been recorded — a fresh install, or a machine
    whose rollouts predate the field. That is a different answer from "0% used"
    and the caller must say so rather than drawing an empty bar.
    """
    from . import transcripts
    newest, newest_mt = '', -1
    root = os.path.join(home or '', 'sessions') if home else ''
    if not root or not os.path.isdir(root):
        return []
    for base, _dirs, files in os.walk(root):
        for f in files:
            if not f.endswith('.jsonl'):
                continue
            p = os.path.join(base, f)
            try:
                mt = os.path.getmtime(p)
            except OSError:
                continue
            if mt > newest_mt:
                newest, newest_mt = p, mt
    if not newest:
        return []
    # forward pass keeping the LAST hit, with the substring prefilter tested
    # against the raw line — so a rollout that is mostly tool traffic never pays
    # a json.loads for a line that cannot contain a limit
    got = []
    for obj in transcripts.iter_json(newest, prefilter='rate_limit'):
        rl = (obj.get('payload') or {}).get('rate_limits') if isinstance(obj, dict) else None
        if not isinstance(rl, dict):
            continue
        wins = [w for w in (_rl_window(rl.get('primary')),
                            _rl_window(rl.get('secondary'))) if w]
        if wins:
            got = wins
    return got


def auth_state(home=None):
    """'ok' | 'missing' | 'unknown' — is this CODEX_HOME logged in?

    `codex login status` and not `doctor`, which answers the same question as a
    side effect: doctor checks for an update, so it is a network round trip and
    every caller reaches it through a cache. This is offline and measured at
    ~60ms, which is what makes it affordable once per home on a page that lists
    them all.
    """
    from . import harnesses as _h
    from . import proc
    exe = _h.exe('codex')
    if not exe:
        return 'missing'
    env = dict(os.environ)
    if home:
        env['CODEX_HOME'] = home
    r = proc.run([exe, 'login', 'status'], env=env, timeout=20)
    if r is None:
        return 'unknown'
    out = ((r.stdout or '') + (r.stderr or '')).strip().lower()
    if not out:
        return 'unknown'
    return 'missing' if 'not logged in' in out else 'ok'


def doctor(home=None):
    """{version, latest, auth, notes} for the installed Codex.

    One subprocess, and it is not a cheap one — `codex doctor` checks for an
    update, which is a network round trip — so every caller reaches it through a
    cache or a job, never inline on a request thread. Parsed for the Notes block
    alone: the sections below it are a page of environment detail that belongs
    in `notes` verbatim if anywhere, not in fields archeus would have to keep in
    step with another tool's report format.
    """
    import re
    from . import harnesses as _h
    from . import proc
    exe = _h.exe('codex')
    if not exe:
        return {'version': '', 'latest': '', 'auth': 'missing',
                'notes': ['Codex is not installed.']}
    env = dict(os.environ)
    if home:
        env['CODEX_HOME'] = home
    r = proc.run([exe, 'doctor'], env=env, timeout=90)
    out = (r.stdout or '') if r else ''
    ver = latest = ''
    auth = 'ok'
    notes = []
    m = re.search(r'Codex Doctor\s+v(\S+)', out)
    if m:
        ver = m.group(1)
    # the Notes block only. Every note is REPEATED further down inside the
    # section it belongs to — with an em-dash where the summary used a hyphen,
    # so they are not even equal as strings — and reading the whole report gave
    # each one twice. The block ends at the rule Codex draws under it.
    body = out.split('\nNotes', 1)[-1]
    body = re.split(r'\n\s*[─-╿]{4,}', body, 1)[0]
    for line in body.splitlines():
        s = line.strip()
        if not s:
            continue
        m = re.search(_UPD_RE, s)
        if m:
            latest = m.group(1)
            ver = ver or m.group(2)
        if re.search(r'(?:^|\s)auth(?:\s|$)', s):
            # the mark is the answer; anything but a tick means "not logged in
            # or not sure", and the rest of the line says which
            auth = 'ok' if '✓' in s else 'missing'
        if s[0] in '✗⚠↑':
            notes.append(s)
    return {'version': ver, 'latest': latest, 'auth': auth, 'notes': notes}


def mcp_list(home=None):
    """[{name, enabled, command, args, env_keys, why}] — Codex's MCP servers.

    `codex mcp list --json` is the source and it needs no login, which is what
    makes this a real surface rather than a config.toml parse: the CLI resolves
    profiles, marketplace-installed servers and the bundled runtime's own
    entries, none of which are visible by reading the file.

    ENV VALUES ARE DROPPED and only their keys survive. Codex's own table masks
    them as `*****` for the obvious reason — an MCP server's env is where its
    API key lives — and a page that fetched them would be putting a credential
    into the browser to render a list of names.
    """
    import json
    from . import harnesses as _h
    from . import proc
    exe = _h.exe('codex')
    if not exe:
        return []
    env = dict(os.environ)
    if home:
        env['CODEX_HOME'] = home
    r = proc.run([exe, 'mcp', 'list', '--json'], env=env, timeout=45)
    if r is None or r.returncode:
        return []
    try:
        rows = json.loads(r.stdout or '[]')
    except ValueError:
        return []
    out = []
    for row in rows if isinstance(rows, list) else []:
        t = (row or {}).get('transport') or {}
        out.append({
            'name': row.get('name') or '',
            'enabled': bool(row.get('enabled')),
            'why': row.get('disabled_reason') or '',
            'kind': t.get('type') or '',
            'command': t.get('command') or t.get('url') or '',
            'args': list(t.get('args') or []),
            'env_keys': sorted((t.get('env') or {}).keys()),
        })
    return out


#: an MCP server name archeus will pass to `codex mcp remove`. Validated at the
#: SINK rather than trusted from the wire, the lesson `_managed_path_ok` carries:
#: the argv-list form stops a shell, and this stops the name being an option.
_NAME_RE = r'^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$'


def mcp_remove(name, home=None):
    """Remove one MCP server by name. (ok, message)."""
    import re
    from . import harnesses as _h
    from . import proc
    if not re.match(_NAME_RE, str(name or '')):
        return False, 'not a server name: %r' % (name,)
    exe = _h.exe('codex')
    if not exe:
        return False, 'Codex is not installed.'
    env = dict(os.environ)
    if home:
        env['CODEX_HOME'] = home
    r = proc.run([exe, 'mcp', 'remove', '--', str(name)], env=env, timeout=45)
    if r is None:
        return False, 'could not run codex'
    return (not r.returncode), ((r.stderr or r.stdout or '').strip()
                                or 'Removed %s.' % name)


def plugins(home=None):
    """[{marketplace, manifest, name, status, version, path}] — what
    `codex plugin list` reports, read-only.

    Parsed from the text table rather than JSON because this subcommand has no
    `--json` (its sibling `mcp list` does). The parse is anchored on the two
    headings Codex prints — a `Marketplace \\`name\\`` line followed by its
    manifest path, then a PLUGIN/STATUS/VERSION/PATH table — and a shape it does
    not recognise yields nothing rather than guesses, the same posture `_rows`
    takes toward a schema it does not know.
    """
    import re
    from . import harnesses as _h
    from . import proc
    exe = _h.exe('codex')
    if not exe:
        return []
    env = dict(os.environ)
    if home:
        env['CODEX_HOME'] = home
    r = proc.run([exe, 'plugin', 'list'], env=env, timeout=60)
    if r is None or r.returncode:
        return []
    out, market, manifest, in_table = [], '', '', False
    for line in (r.stdout or '').splitlines():
        s = line.rstrip()
        m = re.match(r'^Marketplace\s+`([^`]+)`', s.strip())
        if m:
            market, manifest, in_table = m.group(1), '', False
            continue
        if market and not manifest and s.strip() and not s.startswith(' '):
            manifest = s.strip()
            continue
        if s.strip().startswith('PLUGIN'):
            in_table = True
            continue
        if not in_table or not s.strip():
            continue
        # name, then a status that may itself contain a comma and a space
        # ("installed, enabled"), then an optional version, then a path
        m = re.match(r'^(\S+)\s{2,}(.+?)\s{2,}(\S*)\s{2,}(.+?)\s*$', s)
        if not m:
            m = re.match(r'^(\S+)\s{2,}(.+?)\s{2,}(.+?)\s*$', s)
            if not m:
                continue
            name, status, path, version = m.group(1), m.group(2), m.group(3), ''
        else:
            name, status, version, path = m.groups()
        out.append({'marketplace': market, 'manifest': manifest,
                    'name': name, 'status': status.strip(),
                    'version': version.strip(), 'path': path.strip()})
    return out


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

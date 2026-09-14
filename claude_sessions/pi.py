"""pi: where it keeps its sessions, and how to read them.

Read-only, like `codex.py`, and for a simpler reason: everything pi records is
in the transcript itself. There is no index, no database, and nothing held open.

* `$PI_CODING_AGENT_DIR/sessions/--<cwd>--/<ts>_<uuid>.jsonl` — one directory
  per working directory, one file per session. The DIRECTORY NAME IS NOT READ:
  pi maps every path separator and the drive colon to `-` and wraps the result
  in `--`, which is lossy in exactly the way archeus's own encoding is, and the
  first line of every file carries the real `cwd`. Same discipline as
  `paths.path_from_transcripts` — read what the tool recorded, do not decode
  what it named.
* the session id is the header's `id`, which is also the uuid half of the file
  name. The name is the fallback, never the source.

The record shape is documented — `docs/session-format.md` ships inside the npm
package — and verified against a session written on this machine. Every line is
`{type, id, parentId, timestamp, ...}` with `type` in `session`, `message`,
`model_change`, `thinking_level_change`. A `message` carries an `AgentMessage`
whose `role` is one of user / assistant / toolResult / bashExecution / custom /
branchSummary / compactionSummary.

The version field matters and is deliberately not gated on: v1 and v2 sessions
are migrated to v3 by pi itself WHEN LOADED, so a file on disk may still be
either, and the three fields read here (`cwd`, `message.role`, `message.usage`)
are unchanged across all three.
"""

import os

from . import transcripts as _t

#: what pi wraps every encoded working directory in. Recognised so a stray file
#: under `sessions/` is not read as a project; never decoded.
_WRAP = '--'


def _dirs(home):
    """Every session directory under *home*."""
    root = os.path.join(home or '', 'sessions')
    out = []
    try:
        names = os.listdir(root)
    except OSError:
        return out
    for n in names:
        d = os.path.join(root, n)
        if n.startswith(_WRAP) and os.path.isdir(d):
            out.append(d)
    return out


def _files(d):
    """[(mtime, path)] for one session directory, newest first."""
    out = []
    try:
        names = os.listdir(d)
    except OSError:
        return out
    for n in names:
        if not n.endswith('.jsonl'):
            continue
        p = os.path.join(d, n)
        try:
            out.append((os.path.getmtime(p), p))
        except OSError:
            continue
    out.sort(reverse=True)
    return out


def header(path):
    """The first line of a session file, or {}.

    Capped rather than fully parsed: this is called once per session on every
    project walk, and the answer is always the first line.
    """
    for obj in _t.iter_json(path, limit=1, max_bytes=65536):
        return obj if obj.get('type') == 'session' else {}
    return {}


def _sid(path, head=None):
    """The session id: the header's, falling back to the uuid half of the file
    name for a file whose first line is unreadable."""
    sid = ((header(path) if head is None else head).get('id') or '').strip()
    if sid:
        return sid
    base = os.path.basename(path)[:-len('.jsonl')]
    _ts, _sep, rest = base.partition('_')
    return rest or base


def _cwd_of(d):
    """The real working directory a session directory stands for, or ''."""
    for _m, p in _files(d):
        cwd = (header(p).get('cwd') or '').strip()
        if cwd:
            return cwd
    return ''


def projects(home):
    """[(mtime, real path, enc)] — one entry per directory pi has worked in."""
    from . import paths as _paths
    best = {}
    for d in _dirs(home):
        # an empty directory answers '' here, which is the same rejection: pi
        # leaves one behind for a `--no-session` run, and there is nothing in
        # it that says which project it stood for
        cwd, files = _cwd_of(d), _files(d)
        if not cwd:
            continue
        enc = _paths.encode_component(cwd)
        cur = best.get(enc)
        if not cur or files[0][0] > cur[0]:
            best[enc] = (files[0][0], cwd, enc)
    return list(best.values())


def has_project(home, enc):
    """Does pi know this project? Asked of the session store, because archeus's
    own sidecar folder under a pi home is created lazily and its absence says
    nothing about whether sessions exist."""
    return any(e == enc for _m, _p, e in projects(home))


def _home_of(folder):
    """`<home>/projects/<enc>` -> home. The sidecar folder archeus keeps for a
    project under a pi home, which is the handle every caller already has."""
    return os.path.dirname(os.path.dirname(os.path.normpath(folder or '')))


def _dir_for(folder):
    """The session directory behind archeus's sidecar folder, or ''."""
    from . import paths as _paths
    enc = os.path.basename(os.path.normpath(folder or ''))
    for d in _dirs(_home_of(folder)):
        cwd = _cwd_of(d)
        if cwd and _paths.encode_component(cwd) == enc:
            return d
    return ''


def scan(folder, archived=False):
    """[(mtime, sid, preview, count)] for one project, newest first.

    Same tuple `sessions.scan_sessions` returns for Claude Code. pi has no
    archive, so an archived listing is empty rather than the whole corpus —
    `harnesses.cap` is what tells the screen why.
    """
    if archived:
        return []
    out = []
    for mtime, p in _files(_dir_for(folder)):
        s = {'preview': '', 'count': 0}
        for obj in _t.iter_json(p, prefilter='"message"'):
            _turn(obj, s)
        out.append((mtime, _sid(p), s['preview'], s['count']))
    return out


def transcript_path(folder, sid):
    """The session file for one id. Matched on the HEADER rather than on the
    file name, which is the same reason this is a function at all: what a
    harness calls a session id is its own business."""
    for _m, p in _files(_dir_for(folder)):
        if _sid(p) == sid:
            return p
    return ''


def _text(content):
    """The text of a message. `content` is a plain string on a user message pi
    did not have to structure, and a list of typed blocks otherwise."""
    if isinstance(content, str):
        return content.strip()
    out = []
    for b in content or []:
        if isinstance(b, dict) and b.get('type') == 'text':
            out.append(b.get('text') or '')
    return ' '.join(out).strip()


def _turn(obj, s):
    """The preview and the turn count, from one record.

    A turn is a user or assistant message and nothing else. The other five
    roles are the transcript's machinery — a tool result, a bash line typed at
    the prompt, an extension's own note, a compaction summary — and counting
    them reports a dozen turns for a session in which the user said one thing.
    """
    if obj.get('type') != 'message':
        return
    m = obj.get('message') or {}
    if m.get('role') not in ('user', 'assistant'):
        return
    s['count'] += 1
    if m.get('role') == 'user':
        txt = _text(m.get('content'))
        if txt:
            s['preview'] = txt[:200].replace('\n', ' ')


def fold(obj, s):
    """One session record into the shared stats dict.

    pi carries a full four-way token split on every assistant message —
    `usage {input, output, cacheRead, cacheWrite}` — so unlike Codex this needs
    no reconstruction: the names map one to one onto archeus's own, and they are
    per message rather than cumulative.
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
    if kind == 'session':
        if obj.get('cwd'):
            s['cwd'] = obj['cwd']
        return
    if kind == 'model_change':
        # the model is named per CHANGE, not once per session. Most-recent
        # LAST, matching `codex.fold`, so a session that went A, B, A does not
        # leave B looking like the one it ended on.
        m = obj.get('modelId')
        if m:
            if m in s['models']:
                s['models'].remove(m)
            s['models'].append(m)
        return
    if kind != 'message':
        return

    _turn(obj, s)
    m = obj.get('message') or {}
    model = m.get('model') or ''
    if model:
        if model in s['models']:
            s['models'].remove(model)
        s['models'].append(model)
    if m.get('stopReason') == 'error' or m.get('errorMessage'):
        s['api_errors'] += 1
    # a toolResult carries `usage` too, for LLM work the tool did on its own.
    # That is real spend on this session's behalf, so it is banked — under the
    # message's own model where it names one, and the session's otherwise.
    u = m.get('usage') or {}
    if not u:
        return
    key = model or (s['models'][-1] if s['models'] else 'pi')
    agg = s['usage_by_model'].setdefault(
        key, {'in': 0, 'out': 0, 'cache_read': 0, 'cache_create': 0})
    agg['in'] += u.get('input') or 0
    agg['out'] += u.get('output') or 0
    agg['cache_read'] += u.get('cacheRead') or 0
    agg['cache_create'] += u.get('cacheWrite') or 0


def launch_argv(exe, choice, opts, cwd):
    """The argv that opens a pi session, from `pi --help` on the installed
    binary (0.85.1).

    pi takes a session by PATH OR PARTIAL UUID on `--session` / `--fork`, so
    the id archeus already holds is enough for both; `-c` continues the most
    recent. `cwd` is not a flag here — pi has no `-C`, it works in the process's
    working directory, which is what `_direct_launch` already sets.
    """
    args = [exe]
    if choice == 'continue':
        args += ['-c']
    elif choice.startswith('resume:'):
        args += ['--session', choice[7:]]
    elif choice.startswith('resume-named::'):
        args += ['--session', choice[14:].split('::', 1)[0]]
    elif choice.startswith('fork:'):
        args += ['--fork', choice[5:]]
    if opts.get('model'):
        args += ['--model', opts['model']]
    # pi's own scale, not Claude Code's token budget: `--thinking` takes a
    # LEVEL (off/minimal/low/medium/high/xhigh/max) where `MAX_THINKING_TOKENS`
    # takes a number. `effort` is the field that already means a level.
    if opts.get('effort') in THINKING:
        args += ['--thinking', opts['effort']]
    if choice == 'new' and opts.get('name'):
        args += ['-n', opts['name']]
    if opts.get('prompt'):
        args += ['--', str(opts['prompt'])]
    return args


#: the levels `--thinking` accepts. An effort archeus offers that pi does not
#: have is dropped rather than rounded — pi then uses its own default, which is
#: the honest answer to "this CLI does not have that setting".
THINKING = ('off', 'minimal', 'low', 'medium', 'high', 'xhigh', 'max')

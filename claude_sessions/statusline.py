"""`archeus statusline` — two rows under every Claude Code prompt.

Claude Code pipes session JSON on stdin and renders every line printed as its
own row, refreshed on each assistant message and debounced 300ms.

  row 1  identity and place:  model · account · repo ⑂branch ●dirty ↑↓ · mode
  row 2  pressure:            context meter · 5h/7d limits · memory · cost

WHAT THIS SAYS THAT OTHERS CANNOT
---------------------------------
Every statusline tool shows model, directory, cost and context, because that is
what the payload hands out. Two of the fields here come from archeus's own
files: how stale this project's memory graph is, and how many lessons are
waiting for review. "memory 6d" is the one segment that changes what you do
next, and only the tool maintaining the graph can say it.

CONSTRAINTS THAT SHAPE THIS FILE
--------------------------------
It runs on EVERY turn and a traceback here sits under the prompt for the rest of
the session, so every read is guarded and failure degrades to a shorter line.
Nothing goes to stderr. No transcript scan — the numbers come from stdin or from
files archeus already wrote. Git is never spawned inline: `repos.state` serves
it from a cache the GUI board warms.

Two Windows details that are not cosmetic:

  · stdout MUST be reconfigured to UTF-8. Claude Code captures stdout as a pipe,
    so CPython picks the locale codepage (cp1252 here) and the glyphs in these
    rows are either unencodable or reach the terminal as broken UTF-8. That is
    what produced the reported `Opus 5 <?> default <?> memory 21m`.
  · width comes from $COLUMNS, which Claude Code sets. `shutil.get_terminal_size`
    reports 80 for a pipe and would truncate a wide terminal.
"""

import json
import os
import sys

from . import render as _r      # NOT `render` — the public function below would shadow it
from . import config as _c

#: Colours are read off `_c` at USE time, never `from .config import C_WARN`.
#: That form binds by VALUE at import, so this module froze whatever palette
#: happened to be installed the first time it was imported and never saw a
#: theme applied afterwards. It also made
#: `test_stale_memory_is_coloured_by_how_stale` pass alone and fail in a full
#: run, because collection order decided which palette got frozen — the same
#: import-time-binding bug as `hooks.settings_path`, in a different costume.


def _sep():
    return f'{_c.C_DIM} · {_c.C_RESET}'

#: the effort level normal enough not to mention
_QUIET_EFFORT = 'high'


def _age(seconds):
    """Compact age: 20m / 4h / 6d. Never a date — the point is the distance."""
    if seconds < 90:
        return 'now'
    if seconds < 5400:
        return f'{int(seconds // 60)}m'
    if seconds < 172800:
        return f'{int(seconds // 3600)}h'
    return f'{int(seconds // 86400)}d'


#: project_path -> (mtime_ns, graph). One statusline process usually renders
#: once, but the GUI and the TUI both call render() in a loop, and a mature
#: graph.json is hundreds of KB to re-parse for two numbers.
_graph_cache = {}


def _load(project_path):
    """The graph for this cwd. `load_memory` resolves the folder itself, so the
    statusline never has to reproduce the encoding rules."""
    from . import memory
    p = os.path.join(project_path or '', memory.MEM_SUBDIR, memory.GRAPH_NAME)
    try:
        mtime = os.stat(p).st_mtime_ns
    except OSError:
        mtime = None
    hit = _graph_cache.get(project_path)
    if hit and mtime is not None and hit[0] == mtime:
        return hit[1]
    mem = memory.load_memory(project_path)
    if mtime is not None:
        _graph_cache[project_path] = (mtime, mem)
    return mem


def _iso_age(stamp):
    """Seconds since an ISO timestamp, or None. The graph records its own
    `generated_at`, which beats stat-ing a file — it is the age of the DATA,
    not of the last time something touched the file."""
    if not stamp:
        return None
    try:
        from datetime import datetime, timezone
        t = datetime.fromisoformat(str(stamp).replace('Z', '+00:00'))
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        return max(0.0, datetime.now(timezone.utc).timestamp() - t.timestamp())
    except Exception:
        return None


def _memory_bit(mem):
    """`memory 4h` — amber past a week, red past two.

    This is the bit no other statusline can print, and the only one here that
    changes what you do next: a graph that has not been rebuilt in six days is
    quietly feeding the agent a stale picture of the codebase.
    """
    if not mem.get('entities'):
        return f'{_c.C_DIM}no memory{_c.C_RESET}'
    age = _iso_age(mem.get('auto_updated') or mem.get('generated_at'))
    if age is None:
        return ''
    col = _c.C_ERR if age > 1209600 else (_c.C_WARN if age > 604800 else _c.C_DIM)
    return f'{col}memory {_age(age)}{_c.C_RESET}'


def _lessons_bit(mem):
    """`3 to review` — pending lessons, which now go unnoticed *because* the
    mining became automatic. Nothing else surfaces them mid-session."""
    n = sum(1 for e in mem.get('entities', [])
            if e.get('type') == 'lesson' and e.get('status') == 'pending')
    return f'{_c.C_WARN}{n} to review{_c.C_RESET}' if n else ''


def _account_bit():
    """Which account is being spent. Only shown when there are several — on a
    single-account setup it is noise."""
    try:
        from . import config as _c
        accts = _c.all_config_dirs()
        if len(accts) < 2:
            return ''
        cur = os.path.normcase(os.path.abspath(_c.config_dir))
        for name, d in accts:
            if os.path.normcase(os.path.abspath(d)) == cur:
                return f'{_c.C_DIM}{name}{_c.C_RESET}'
    except Exception:
        pass
    return ''


def _git_bits(cwd):
    """(`repo ⑂branch ●3 ↓2`, `7 subs (2 dirty)`) — both '' without git.

    Never spawns git itself. `repos.state` answers from cache; the branch inside
    it is read from `.git/HEAD` and is always exact. The sub-repo roll-up is the
    answer to a project that is a PARENT of repos rather than a repo.
    """
    if not cwd or not isinstance(cwd, str) or not os.path.isdir(cwd):
        return '', ''
    try:
        from . import repos
        root = repos.owner_of(cwd)
        if not root:
            summary = repos.summary(cwd)
            if summary['repos']:
                d = summary['dirty']
                tail = f' ({d} dirty)' if d else ''
                return '', f'{_c.C_DIM}{summary["repos"]} repos{tail}{_c.C_RESET}'
            return '', ''
        st = repos.state(root, refresh=False)
        parts = [f'{_c.C_DIM}{os.path.basename(root) or root}{_c.C_RESET}']
        if st['branch']:
            parts.append(f'⑂{_r.trunc(st["branch"], 24)}')
        elif st['head']:
            parts.append(f'@{st["head"]}')
        if st['dirty']:
            parts.append(f'{_c.C_WARN}●{st["dirty"]}{_c.C_RESET}')
        if st['ahead']:
            parts.append(f'↑{st["ahead"]}')
        if st['behind']:
            parts.append(f'{_c.C_WARN}↓{st["behind"]}{_c.C_RESET}')
        sub = repos.summary(root)
        subs = ''
        if sub['repos'] > 1:
            n = sub['repos'] - 1
            d = sub['dirty'] - (1 if st['dirty'] else 0)
            tail = f' ({d} dirty)' if d > 0 else ''
            subs = f'{_c.C_DIM}{n} subs{tail}{_c.C_RESET}'
        return ' '.join(parts), subs
    except Exception:
        return '', ''


def _context_bit(data):
    """The context meter. The percentage is always drawn — it leads row 2 and
    anchors it — but the COLOUR is what appears only when it matters.

    `exceeds_200k_tokens` forces red regardless: it means the premium pricing
    tier is live, which is actionable at any percentage.
    """
    try:
        cw = data.get('context_window') or {}
        pct = cw.get('used_percentage')
        if not isinstance(pct, (int, float)) or isinstance(pct, bool):
            used, size = cw.get('total_input_tokens'), cw.get('context_window_size')
            if not (isinstance(used, (int, float)) and isinstance(size, (int, float))
                    and size):
                return ''
            pct = 100.0 * used / size
        pct = max(0.0, min(100.0, float(pct)))
        big = bool(data.get('exceeds_200k_tokens'))
        col = _c.C_ERR if (pct >= 85 or big) else (_c.C_WARN if pct >= 70 else _c.C_DIM)
        return (f'{_r.meter(pct, 10, col)}{col}{int(pct)}% ctx'
                f'{" 200k+" if big else ""}{_c.C_RESET}')
    except Exception:
        return ''


def _reset_at(epoch):
    """`resets_at` → short local time ('16:49' today, else 'Sat 08:59'), or ''.

    The payload gives Unix epoch SECONDS. usage._fmt_reset takes an ISO string
    because the OAuth endpoint it polls returns one — same display, different
    input, so this converts rather than calling it with the wrong type. Epoch
    milliseconds would render as a date in the year 56000, so the magnitude is
    checked: `.claude.json` genuinely does use ms elsewhere in this codebase.
    """
    if not isinstance(epoch, (int, float)) or isinstance(epoch, bool):
        return ''
    try:
        # local import, like _iso_age above: this module runs on EVERY turn and
        # every import it can defer is latency it does not pay
        from datetime import datetime
        if epoch > 1e11:            # milliseconds, not seconds
            epoch = epoch / 1000.0
        dt = datetime.fromtimestamp(epoch).astimezone()
        now = datetime.now(dt.tzinfo)
        return dt.strftime('%H:%M') if dt.date() == now.date() else dt.strftime('%a %H:%M')
    except Exception:
        return ''


def _limit_bits(data):
    """5h and 7d plan windows, straight off stdin.

    `usage.py` gets these by polling the OAuth endpoint on a background thread.
    That must never happen here: a thread started per turn, in a process Claude
    Code cancels whenever a new update arrives, is the wrong shape entirely —
    and the payload already carries the numbers for free.

    The percentage alone does not answer the question you actually have when you
    look at it, which is "how long until I get it back" — so the reset time
    rides along, in the same '→ 16:49' shape the usage grid already uses.
    """
    out = []
    try:
        rl = data.get('rate_limits') or {}
        for key, label in (('five_hour', '5h'), ('seven_day', '7d')):
            win = rl.get(key) or {}
            pct = win.get('used_percentage')
            if not isinstance(pct, (int, float)) or isinstance(pct, bool):
                continue
            col = _c.C_ERR if pct >= 90 else (_c.C_WARN if pct >= 75 else _c.C_DIM)
            at = _reset_at(win.get('resets_at'))
            out.append(f'{col}{label} {int(pct)}%{_c.C_RESET}'
                       + (f'{_c.C_DIM}→{at}{_c.C_RESET}' if at else ''))
    except Exception:
        pass
    return out


def _mode_bit(data):
    """Anything unusual about how this session is configured. Empty on a normal
    session, which is the point — it costs nothing when there is nothing to say.
    """
    parts = []
    try:
        if data.get('fast_mode'):
            parts.append('fast')
        eff = (data.get('effort') or {}).get('level')
        if isinstance(eff, str) and eff and eff != _QUIET_EFFORT:
            parts.append(eff)
        style = (data.get('output_style') or {}).get('name')
        if isinstance(style, str) and style and style != 'default':
            parts.append(style)
        agent = (data.get('agent') or {}).get('name')
        if isinstance(agent, str) and agent:
            parts.append(f'@{agent}')
        wt = (data.get('workspace') or {}).get('git_worktree')
        if isinstance(wt, str) and wt:
            parts.append(f'wt:{wt}')
        pr = (data.get('pr') or {}).get('number')
        if isinstance(pr, int) and not isinstance(pr, bool):
            parts.append(f'PR #{pr}')
    except Exception:
        return ''
    return f'{_c.C_DIM}{" ".join(parts)}{_c.C_RESET}' if parts else ''


def _cost_bit(data):
    try:
        cost = (data.get('cost') or {}).get('total_cost_usd')
        if not isinstance(cost, (int, float)) or isinstance(cost, bool) or cost <= 0:
            return ''
        add = (data.get('cost') or {}).get('total_lines_added')
        rem = (data.get('cost') or {}).get('total_lines_removed')
        lines = (f' +{add}/-{rem}'
                 if isinstance(add, int) and isinstance(rem, int) and (add or rem) else '')
        return f'{_c.C_DIM}${cost:.2f}{lines}{_c.C_RESET}'
    except Exception:
        return ''


def _cols():
    """Terminal width from $COLUMNS, or 0 for 'do not adapt'."""
    try:
        return max(0, int(os.environ.get('COLUMNS') or 0) - 2)
    except Exception:
        return 0


def _fit(bits, cols):
    """Join, dropping from the RIGHT until it fits — so segment order is
    priority order. Also the single choke point where a newline in any
    free-text field (model name, branch, style, agent) is neutralised: that is
    what stops a payload adding rows of its own."""
    bits = [str(b).replace('\n', ' ').replace('\r', ' ') for b in bits if b]
    if not bits:
        return ''
    while cols and len(bits) > 1 and _r.disp_width(_sep().join(bits)) > cols:
        bits.pop()
    line = _sep().join(bits)
    return _r.trunc(line, cols) if cols else line


def render_rows(data):
    """The rows, as a list. Pure — the tests call this."""
    ws = data.get('workspace') or {}
    cwd = data.get('cwd') or ws.get('current_dir') or ''
    model = ((data.get('model') or {}).get('display_name')
             or (data.get('model') or {}).get('id') or '')
    git, subs = _git_bits(cwd)
    mem_bit = les_bit = ''
    if cwd:
        try:
            mem = _load(cwd)
            mem_bit, les_bit = _memory_bit(mem), _lessons_bit(mem)
        except Exception:
            pass
    cols = _cols()
    row1 = _fit([model, _account_bit(), git, _mode_bit(data), subs], cols)
    row2 = _fit([_context_bit(data), *_limit_bits(data), mem_bit, les_bit,
                 _cost_bit(data)], cols)
    return [r for r in (row1, row2) if r]


def render(data):
    return '\n'.join(render_rows(data))


# ── install / remove ─────────────────────────────────────────
# Writes Claude Code's own settings.json, reusing hooks.py's accessors so there
# is one reader and one writer for that file rather than two that can disagree.


def plain(line):
    """The same line without colour, for the GUI preview.

    The statusline is written for a terminal, so it carries SGR codes. Rendering
    those into HTML would show the escape sequences themselves — the preview has
    to be the text, not the bytes.
    """
    return _r.strip_ansi(line)


#: the form that only worked inside the source checkout — see statusline_cli
_LEGACY = '-m claude_sessions'


def _command():
    """`"<python>" "<statusline_cli.py>"`, both absolute and quoted so it works
    whatever shell Claude Code invokes it through, and from any directory.

    NOT `-m claude_sessions`: `sys.path[0]` for `-m` is the CURRENT DIRECTORY,
    so that form found the package only when the session's cwd was the
    archeus checkout. Everywhere else it exited 1 and Claude Code drew an
    empty line without saying why. Same reasoning as hooks._py_hook, which got
    this right for the hook scripts.
    """
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          'statusline_cli.py')
    return f'"{_interpreter()}" "{script}"'


def _interpreter():
    """pythonw.exe where it exists, python.exe otherwise.

    This runs on EVERY conversation turn. The console interpreter flashes a
    window each time on Windows, which is unusable; the windowless one writes
    to the captured pipe exactly the same way.
    """
    exe = sys.executable
    if os.name != 'nt':
        return exe
    w = os.path.join(os.path.dirname(exe),
                     os.path.basename(exe).replace('python.exe', 'pythonw.exe'))
    return w if w != exe and os.path.isfile(w) else exe


def is_installed(cfgdir=None):
    from . import hooks
    sl = (hooks._load(cfgdir).get('statusLine') or {})
    return 'claude_sessions' in str(sl.get('command', ''))


def blockers(cfgdir=None):
    """Why an INSTALLED statusline still will not appear. [] when nothing is
    in the way.

    Installed and visible are different questions, and answering only the first
    is how an account ends up correctly configured and blank. Both conditions
    here are silent in Claude Code — nothing is printed, the line is simply not
    drawn — which is precisely why they belong on the screen that claims the
    thing is installed.
    """
    from . import hooks
    s = hooks._load(cfgdir)
    out = []
    cmd = str((s.get('statusLine') or {}).get('command', ''))
    # The one that actually bit: `-m claude_sessions` resolves the package off
    # the CURRENT DIRECTORY, so it printed a statusline in the archeus
    # checkout and nothing anywhere else. Claude Code swallows the failure, so
    # the only symptom was a blank line.
    if _LEGACY in cmd:
        out.append(('cwd-dependent-command',
                    'the installed command uses `-m claude_sessions`, which only '
                    'resolves when the session runs inside the archeus '
                    'checkout — reinstall to point it at an absolute path'))
    # The classic renderer simply does not draw a statusLine, and nothing says
    # so: an account can be correctly installed and permanently blank.
    if s.get('tui') != 'fullscreen':
        out.append(('classic-tui',
                    "tui is not 'fullscreen', and Claude Code's classic "
                    'renderer draws no statusline — reinstall, or set '
                    'Interface to fullscreen'))
    # Claude Code's own warning: "Status line is configured but disableAllHooks
    # is true".
    if s.get('disableAllHooks'):
        out.append(('hooks-disabled',
                    'disableAllHooks is on, which turns the statusline off with '
                    'everything else'))
    return out


def by_account():
    """[(name, cfgdir, installed, blockers)] — the per-account truth.

    The statusline is a property of the USER, but it is configured per account
    dir, so "installed" was never a single bool. Reporting it as one is what
    hid the first bug: with three accounts configured, only the active one was
    ever written, and every surface said "installed". `blockers` is the second
    half of the same lesson — the write can succeed everywhere and the line
    still never appear.
    """
    from . import hooks
    return [(n, d, is_installed(d), blockers(d)) for n, d in hooks.account_dirs()]


def install(cfgdir=None):
    """Point ONE account's settings.json at us. Returns (ok, message).

    Refuses to clobber someone else's statusline: that is a single-valued key,
    and quietly replacing a line the user built themselves would be exactly the
    kind of silent overwrite the memory work went to lengths to avoid.
    """
    from . import hooks
    s = hooks._load(cfgdir)
    cur = (s.get('statusLine') or {}).get('command', '')
    if cur and 'claude_sessions' not in str(cur):
        return False, f'A different statusline is already set: {str(cur)[:60]}'
    s['statusLine'] = {'type': 'command', 'command': _command()}
    # Claude Code's classic TUI does not draw a statusLine at all, so an
    # install that leaves `tui` alone is the silent failure `blockers()` exists
    # for — the whole point of installing is to see the line.
    s['tui'] = 'fullscreen'
    return ((True, 'Statusline installed') if hooks._save(s, cfgdir)
            else (False, 'Write failed'))


def remove(cfgdir=None):
    from . import hooks
    s = hooks._load(cfgdir)
    if not is_installed(cfgdir):
        return False, 'Not installed'
    s.pop('statusLine', None)
    return ((True, 'Statusline removed') if hooks._save(s, cfgdir)
            else (False, 'Write failed'))


def _fan_out(fn, verb):
    """Apply `fn` to every account and summarise. A refusal in one account
    (someone else's statusline) must not stop the others — it is reported
    alongside them, because partial success is the honest answer."""
    done, skipped = [], []
    for name, cfgdir in _accounts():
        ok, msg = fn(cfgdir)
        (done if ok else skipped).append((name, msg))
    if not done:
        return False, '; '.join(f'{n}: {m}' for n, m in skipped) or f'Nothing to {verb}'
    out = f"Statusline {verb} for {', '.join(n for n, _ in done)}"
    if skipped:
        out += ' — skipped ' + '; '.join(f'{n} ({m})' for n, m in skipped)
    return True, out


def _accounts():
    from . import hooks
    return hooks.account_dirs()


def install_all():
    """Install into every account. This is what the UI calls by default: a
    statusline the user asked for should follow them across accounts."""
    return _fan_out(install, 'installed')


def remove_all():
    return _fan_out(remove, 'removed')


def main(argv=None):
    """Read one JSON payload from stdin, print the rows. Never raises."""
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
    except Exception:
        data = {}
    try:
        out = render(data)
    except Exception:
        out = ''
    sys.stdout.write(out + '\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

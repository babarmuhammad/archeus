"""The headless model call, with no UI attached.

Two halves that used to live inside UI-owned code:

* `build_headless_args` — the argv every one of archeus's own `claude -p`
  calls carries (the `HEADLESS_MARK`, `--max-turns`, the disallowed write
  tools, model, budget, extra flags). Moved out of `memory._claude_stdin`.
* `run_headless` — spawn with the prompt on stdin, cancel through an Event,
  kill the whole tree on cancel, capture, and record a non-zero exit the way
  every caller relies on (`quota.note_failure` + `events.record`). Moved out of
  `gui_api._run_cancellable`.

`gui_api._run_cancellable` and `memory._claude_stdin` stay the entry points for
the legacy app and keep their contracts (quota preflight, the job context,
the foreground progress UI); they are wrappers over this module now.

The rule this module exists for: it must never import `ui`, `gui_api`, `main`
or `gui` — importing `gui_api` runs `_install_bridge()`, which monkeypatches
the terminal UI inside whatever process imported it. Everything imported here
is the standard library at module level and UI-free package modules lazily.
"""
import json
import subprocess
import threading
from collections import namedtuple

#: every archeus-owned headless call: read-only tools, bounded turns
MAX_TURNS = '20'
DISALLOWED_TOOLS = 'Write,Edit,NotebookEdit,Bash'

#: returncode is None when no exit code exists (spawn failure, timeout, crash);
#: `reason` is what claude said, `error` the one-line record written to the log
Result = namedtuple('Result', 'returncode stdout reason error timed_out')


def build_headless_args(exe, prompt, model='', budget_args=(), extra_args=(), harness=None):
    """(argv, stdin_text) for one headless call.

    *harness* None is Claude Code. Any other id is a CLI whose descriptor names
    a `headless_argv` (read-only, ephemeral in its own flags); it gets *model*
    in its own vocabulary, and never *budget_args*/*extra_args*, which are
    Claude Code flags.

    The prompt leaves with `sessions.HEADLESS_MARK` appended: `claude -p`
    writes a transcript like any session, and the mark is how session lists
    and auto-memory recognise archeus talking to itself."""
    from .sessions import HEADLESS_MARK
    if harness is not None:
        from . import harnesses
        args = harnesses.impl('headless_argv', harness)(exe, model)
    else:
        args = [exe, '-p', '--max-turns', MAX_TURNS, '--disallowedTools', DISALLOWED_TOOLS]
        if model:
            args += ['--model', model]
        args += list(budget_args)
        args += list(extra_args)
    return args, (prompt or '') + '\n\n' + HEADLESS_MARK


def failure_reason(stdout):
    """The sentence a human needs, out of what `claude -p` printed before it
    exited non-zero.

    `--output-format json` (which `memory._claude_json` asks for) puts the
    refusal in `result`, behind ~200 characters of `duration_api_ms`,
    `stop_reason`, `session_id`, `total_cost_usd` and `usage`. Everything that
    reports a failure truncates, so what actually reached the user — the job
    banner, the Logs page, the event log — was a clipped JSON blob with the
    reason cut off.

    Falls through to the raw text unchanged when stdout is not that envelope
    (`--print`, a crash, a stack trace), so nothing is hidden.
    """
    raw = (stdout or '').strip()
    if not raw.startswith('{'):
        return raw
    try:
        env = json.loads(raw)
    except Exception:
        return raw
    if not isinstance(env, dict):
        return raw
    for key in ('result', 'error', 'message'):
        v = env.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
        if isinstance(v, dict):                     # {"error": {"message": ...}}
            m = v.get('message')
            if isinstance(m, str) and m.strip():
                return m.strip()
    return raw


def run_headless(cmd, input_text=None, *, cwd=None, env=None, timeout=600,
                 cancel=None, on_spawn=None, capture_output=True, text=True,
                 encoding='utf-8', errors='ignore'):
    """Run *cmd* to completion and return a `Result`.

    *cancel* (a threading.Event) kills the process tree when set; *on_spawn*
    receives the Popen as soon as it exists (the job runner tracks it). A
    non-zero exit is recorded here — `quota.note_failure` sees the full output,
    `events.record` the one-line error — because the unattended callers have
    nothing above them that would record it."""
    from . import proc as _proc
    try:
        # CREATE_NO_WINDOW: a captured child shows nothing in its console,
        # so the window is pure flicker. See proc.no_window_flags.
        p = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE if capture_output else None,
                             stderr=subprocess.STDOUT if capture_output else None,
                             text=text, encoding=encoding, errors=errors,
                             cwd=cwd, env=env, creationflags=_proc.no_window_flags)
    except Exception as e:
        return Result(None, '', '', 'could not start %s: %s' % (cmd[:1], e), False)
    if on_spawn is not None:
        on_spawn(p)
    done = threading.Event()

    def _watch():
        while not done.is_set():
            if cancel.wait(timeout=1.0):
                break
        if not done.is_set() and p.poll() is None:
            _proc.kill_tree(p)

    t = None
    if cancel is not None:
        t = threading.Thread(target=_watch, daemon=True)
        t.start()
    detail = ' '.join(str(c) for c in cmd[:2])
    try:
        stdout, _ = p.communicate(input=input_text, timeout=timeout)
        stdout = (stdout or '').strip() if capture_output else ''
        # stderr is merged into stdout above, so a failed CLI run looks exactly
        # like a successful one to every caller unless the exit code is checked.
        if p.returncode:
            reason = failure_reason(stdout)
            error = 'claude exited %s: %s' % (p.returncode, (reason or '(no output)')[:300])
            from . import events, quota
            # the ENVELOPE, not the extracted sentence: a marker could live in a
            # field the sentence does not carry
            quota.note_failure(cmd, env, stdout)
            events.record('subprocess', error, detail=detail)
            return Result(p.returncode, stdout, reason, error, False)
        return Result(0, stdout, '', '', False)
    except subprocess.TimeoutExpired:
        try: p.kill()
        except Exception: pass
        msg = ('timed out after %ss — upstream may be an unresponsive '
               'OmniRoute/failover endpoint' % timeout)
        from . import events
        events.record('subprocess', msg, detail=detail)
        return Result(None, '', '', msg, True)
    except Exception as e:
        try: p.kill()
        except Exception: pass
        return Result(None, '', '', str(e), False)
    finally:
        done.set()
        if t is not None:
            t.join(timeout=2)


def parse_json(text):
    """Recover JSON from model prose: the path for a harness asked for its
    shape in the prompt, and the fallback for one whose schema flag was
    ignored.

    Tries the whole (de-fenced) text first, because a well-behaved answer needs
    no surgery, and only then slices to the outermost object or array. The
    array case matters: bracket-slicing a two-element array on '{'..'}' yields
    '{...}, {...}', which is not JSON, so a list-shaped answer used to come back
    as None from here even though it parsed perfectly as-is.
    """
    if not text:
        return None
    t = text.strip()
    if '```' in t:                       # strip code fences
        import re
        m = re.search(r'```(?:json)?\s*(.*?)```', t, re.S)
        if m:
            t = m.group(1).strip()
    for cand in (t, _slice_between(t, '{', '}'), _slice_between(t, '[', ']')):
        if not cand:
            continue
        try:
            return json.loads(cand)
        except Exception:
            continue
    return None


def _slice_between(t, open_ch, close_ch):
    """The outermost open_ch..close_ch span, or '' when there isn't one."""
    if open_ch not in t or close_ch not in t:
        return ''
    i, j = t.index(open_ch), t.rindex(close_ch)
    return t[i:j + 1] if j > i else ''


def unwrap_structured(raw):
    """(parsed, cost_usd) from `claude -p --output-format json --json-schema`.

    The envelope's `structured_output` when it carries one; otherwise its text
    `result` recovered as prose, because Claude Code before v2.1.205 silently
    ignored a schema it considered invalid; otherwise the raw text itself."""
    cost = None
    try:
        env = json.loads((raw or '').strip())
    except Exception:
        env = None
    if isinstance(env, dict):
        c = env.get('total_cost_usd')
        cost = float(c) if isinstance(c, (int, float)) and not isinstance(c, bool) else None
        if isinstance(env.get('structured_output'), (dict, list)):
            return env['structured_output'], cost
        if isinstance(env.get('result'), str):
            return parse_json(env['result']), cost
    return parse_json(raw), cost


def budget_args():
    """`--max-budget-usd`, when the user has set a cap. A timeout bounds how
    LONG one of archeus's own calls may run; this bounds what it may spend,
    and subagent spend counts toward the same cap. Claude Code's flag: the
    claude_code adapter's own-call argv carries it, no other harness does."""
    try:
        from .config import load_settings
        cap = float(load_settings().get('headless_budget_usd') or 0)
    except Exception:
        return []
    return ['--max-budget-usd', f'{cap:g}'] if cap > 0 else []

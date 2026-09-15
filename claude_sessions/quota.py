"""Don't spend an account that has nothing left — offer one that does.

archeus makes its own headless `claude -p` calls for every generate-this-for-me
feature (AI agents, skills, MCP analysis, system prompts, CLAUDE.md, memory and
lessons extraction, Plan→Execute and its council, scheduled loops). None of them
used to ask whether the account they were about to spend had any quota left, so
a full 5-hour window produced a nonzero exit reported as "No output from Claude"
— while a second configured account sat there with headroom.

Three things make this cheap enough to sit in front of every call:

* **It reads only what `usage.py` already polled.** No network, ever. The poller
  refreshes every 300s on a daemon thread; this module reads its cache and
  nothing else.
* **It fails open.** No entry, a stale poll, an account that has never been
  polled — all pass through. A guard that blocks work because a background
  thread has not run yet is worse than the bug it fixes.
* **It only looks at `claude … -p`.** `claude mcp list`, `claude plugin …` and
  `claude --version` share the same spawn helpers and consume no quota; blocking
  them the moment a weekly cap filled would break account management outright.

`note_failure()` closes the one hole the cache leaves: on a cold cache the first
call of a burst still gets through, and its error text latches the account so the
rest of the burst skips with the real reason instead of repeating the failure.
"""

import os
import re
import time

from . import config as _c

LIMIT_PCT = 100.0

#: Account-wide windows only. `usage._limit_label` returns the MODEL's display
#: name for a `weekly_scoped` limit, and refusing a haiku extraction because the
#: Opus weekly window is spent would be a worse bug than the one being fixed.
ACCOUNT_WINDOWS = ('session', 'weekly')

#: one answer covers a burst — a 30-unit memory refresh asks once, not 30 times.
#: A guard that prompts per call is worse than the bug.
_DECIDED_TTL = 900
#: how long a limit error we actually SAW is trusted, independent of the poller
_OBSERVED_TTL = 900

_observed = {}     # normalised cfgdir -> until_ts
_decided = {}      # normalised cfgdir -> (choice, until_ts)
#: the subset of `_observed` whose text named a plan WINDOW rather than a bare
#: 429. `rotate.spent` reads this one and `_observed` blocks on both, because
#: they answer different questions — see `is_window_limit`.
_window_observed = {}

#: substrings that mean "out of quota". Deliberately specific: a bare 'limit'
#: also matches the budget cap and the turn cap, neither of which is this.
#:
#: 'session limit' and 'weekly limit' are the two Claude Code actually sends, and
#: their absence made this whole module a no-op for the common case. The real
#: refusal reads "You've hit your session limit · resets 2:30am (Europe/Rome)" —
#: which matched NONE of the markers above it, so `note_failure` never latched
#: and the mechanism its own docstring describes ("that one failure is what stops
#: the other five") had never once fired. The event log showed the consequence:
#: four spawned-and-refused calls in 19 minutes against an account that was
#: already saying no. Checked against a real 429 transcript, not guessed — the
#: same discipline as reading `context_window.used_percentage` off the payload.
_LIMIT_MARKERS = ('usage limit', 'rate limit', 'rate_limit', 'ratelimit',
                  'rate-limited', 'limit reached', 'limit exceeded',
                  'session limit', 'weekly limit',
                  'out of quota', 'quota exceeded', 'too many requests')

#: the markers that name a PLAN WINDOW — the 5-hour or weekly cap that only
#: time refills. Everything `_LIMIT_MARKERS` has and this does not (a bare 429,
#: 'rate limit', 'too many requests') is a SHORT rate limit: it clears in
#: seconds, the right answer is to wait and retry the same account, and
#: rotating on it would spend a second account's headroom for nothing. The
#: reference implementation this feature is modelled on makes exactly this
#: distinction, off the `anthropic-ratelimit-unified-*-status` headers it can
#: see and archeus cannot — so archeus makes it off the wording instead.
_WINDOW_MARKERS = ('usage limit', 'session limit', 'weekly limit',
                   'limit reached', 'limit exceeded',
                   'out of quota', 'quota exceeded')

#: `429` has to be read as a STATUS, never as a number in prose. `ui._note_failure`
#: hands `note_failure` the model's whole STDOUT, so a bare substring scan matched
#: `14290` in a token count and latched the account out of headless work for
#: fifteen minutes after a run that had nothing wrong with it.
#:
#: The obvious repair — a word boundary — is not enough and the suite says so:
#: `\b429\b` matches "wrote 429 lines to quota.py", which
#: `test_the_markers_do_not_match_the_models_own_output` forbids. It was also not
#: what shipped. The pattern here was `re.compile(r'<BS>429<BS>')` with two LITERAL
#: BACKSPACE bytes where `\b` had been meant — a regex that can never match
#: anything, so this half of the guard had been dead for its whole life. It looked
#: fine because every 429 the tests assert on carries 'too many requests' or
#: 'rate_limit' too, and one of the MARKERS caught it.
#:
#: So it matches the shape a status code actually arrives in — `"apiErrorStatus":429`,
#: `status: 429`, `code=429` — which is the one thing a sentence about a file never
#: looks like.
_LIMIT_RE = re.compile(r'(?:status|code)"?\s*[:=]\s*"?429\b')


def _norm(d):
    return os.path.normcase(os.path.abspath(d or ''))


def _key(cfgdir=None):
    return _norm(_c.resolve_config_dir(cfgdir))


def _cfgdir_of(args, env):
    """The home a prepared environment points at, or None for the active one.

    Read through the harness the ARGV names, never through `CLAUDE_CONFIG_DIR`
    alone: `config.account_env` copies `os.environ`, so that variable is
    present in a Codex environment too and this answered with a real,
    unrelated Claude account instead of with nothing. Every window this module
    knows about is that account's, so the wrong answer here spent one account's
    headroom deciding another harness's call.
    """
    from .harnesses import of_argv
    d = of_argv(args)
    if d is None or not isinstance(env, dict):
        return None
    return env.get(d['home_env']) or None


def is_inference(args):
    """True for a call that spends model quota, whichever harness it names.

    Still an argv test and not a flag on the call: the five wrappers that reach
    preflight each spawn BOTH inference and management commands — `claude -p`
    and `claude mcp list` go through the same `ui.run_with_progress` — so the
    caller does not always know. What was wrong with it was never the sniff; it
    was that the shape it looked for belonged to one harness and was written
    here. `harnesses` owns that now, and each descriptor states its own.

    Still cheap enough for the import-light callers: harnesses imports config,
    which this module already has, and never touches `usage` (and with it
    urllib and ssl).
    """
    from .harnesses import is_inference as _is
    return _is(args)


def worst_window(cfgdir=None):
    """(pct, label, resets_iso) for the fullest account-wide window, from the
    usage poller's cache. (0.0, '', '') means "not known" — which is a pass."""
    try:
        from . import usage
    except Exception:
        return (0.0, '', '')
    want = _key(cfgdir)
    st = None
    try:
        with usage._lock:
            # _acct_state is keyed by the RAW string usage._targets() built, not
            # by a normalised path — an exact lookup here fails open forever and
            # nothing else would ever notice.
            for k, v in usage._acct_state.items():
                if _norm(k) == want:
                    st = dict(v)
                    break
    except Exception:
        return (0.0, '', '')
    if not st or st.get('status') != 'ok' or not st.get('data'):
        return (0.0, '', '')
    worst = (0.0, '', '')
    try:
        for label, pct, reset in usage._extract_windows(st['data']):
            if label in ACCOUNT_WINDOWS and pct > worst[0]:
                worst = (pct, label, reset or '')
    except Exception:
        return (0.0, '', '')
    return worst


def is_exhausted(cfgdir=None):
    return bool(reason(cfgdir))


def reason(cfgdir=None):
    """Why this account cannot be spent, or '' when it can (or when we don't
    know, which is the same answer)."""
    if _observed.get(_key(cfgdir), 0) > time.time():
        return 'account rate-limited by Claude'
    pct, label, reset = worst_window(cfgdir)
    if pct < LIMIT_PCT:
        return ''
    when = ''
    if reset:
        try:
            from . import usage
            when = ' (resets %s)' % usage._fmt_reset(reset)
        except Exception:
            when = ''
    return '%s limit full%s' % (label or 'account', when)


def headroom(exclude=None):
    """[(name, cfgdir, pct)] for accounts worth switching to, emptiest first.

    An account with no usable local credentials is dropped without a request:
    `usage._read_token` / `_token_expired` are plain file reads.

    An account the user took out of the rotation is dropped here rather than at
    the two call sites below, so it is invisible to the picker as well as to the
    automatic switch — offering an account you have opted out of is offering a
    choice that was already made.
    """
    ex = _key(exclude) if exclude is not None else None
    out = []
    try:
        from . import usage
        for name, d in _c.all_config_dirs():
            if ex is not None and _norm(d) == ex:
                continue
            if not _rotation_allows(d):
                continue
            if reason(d):
                continue
            if not usage._read_token(d) or usage._token_expired(d):
                continue
            out.append((name, d, worst_window(d)[0]))
    except Exception:
        return []
    out.sort(key=lambda r: r[2])
    return out


def _rotation_allows(cfgdir):
    """False only when the user explicitly took this account out of rotation.

    Fails OPEN on any error, including `rotate` not importing: every other
    predicate in this module does, and a settings read is not a good enough
    reason to hide an account that has headroom.
    """
    try:
        from . import rotate
        return rotate.is_enabled(cfgdir)
    except Exception:
        return True


def is_limit_error(text):
    t = str(text or '').lower()
    return any(m in t for m in _LIMIT_MARKERS) or bool(_LIMIT_RE.search(t))


def is_window_limit(text):
    """True only when the refusal names a plan WINDOW, not a short rate limit.

    `is_limit_error` answers "may this account be spent right now" and a bare
    429 is a perfectly good reason for no. This answers "has this account run
    out", which a 429 is NOT a reason for — it clears on its own.
    """
    t = str(text or '').lower()
    return any(m in t for m in _WINDOW_MARKERS)


def window_limited(cfgdir=None):
    """True when this account was recently refused for a full plan window."""
    return _window_observed.get(_key(cfgdir), 0) > time.time()


def note_failure(args, env, text):
    """Remember that this account answered with a limit error.

    The poller runs at 300s, so on a cold cache the first call of a burst still
    gets through. That one failure is what stops the other five.

    It takes the argv for the same reason `preflight` does: without it a Codex
    429 latched a CLAUDE account out of headless work for fifteen minutes.
    """
    if not is_limit_error(text):
        return
    from .harnesses import of_argv, DEFAULT
    d = of_argv(args)
    if d is not None and d['id'] != DEFAULT:
        return
    key = _key(_cfgdir_of(args, env))
    _observed[key] = time.time() + _OBSERVED_TTL
    if is_window_limit(text):
        _window_observed[key] = time.time() + _OBSERVED_TTL


def forget(cfgdir=None):
    """Drop the cached decision and observation for an account (tests, and the
    settings screen after the user changes the policy)."""
    k = _key(cfgdir)
    _observed.pop(k, None)
    _decided.pop(k, None)
    _window_observed.pop(k, None)


def preflight(args, env=None):
    """(env_to_use, blocked_reason) for a subprocess about to be spawned.

    A non-empty blocked_reason means: do not spawn. The returned env may point
    at a DIFFERENT account than the one passed in — that is the whole feature.
    """
    if not is_inference(args):
        return env, ''
    # Every window this module can read is Anthropic's — `worst_window` reads
    # the OAuth usage cache — so for another harness there is no headroom to
    # offer and nothing to compare against. Blocking would refuse work on a
    # number that does not describe it, and switching would hand back
    # `account_env(a Claude account)`, which drops CODEX_HOME entirely and
    # silently runs the call against the wrong home. `plan_limits` already
    # states this gap per descriptor; this is the same fact at the guard.
    from .harnesses import of_argv, DEFAULT
    _d = of_argv(args)
    if _d is not None and _d['id'] != DEFAULT:
        return env, ''
    # A call routed at a provider is not spending THIS account's quota, so
    # neither answer this function can give is right for it: blocking it refuses
    # work that costs the account nothing, and switching account replaces the
    # whole env — including the ANTHROPIC_BASE_URL that is doing the routing, so
    # the call would silently land back on Anthropic. One guard here rather than
    # at each of the five call sites.
    if (env or {}).get('ANTHROPIC_BASE_URL'):
        return env, ''
    try:
        mode = (_c.load_settings().get('headless_quota') or 'prompt').strip()
    except Exception:
        mode = 'prompt'
    if mode == 'off':
        return env, ''
    cfgdir = _cfgdir_of(args, env)
    why = reason(cfgdir)
    if not why:
        return env, ''
    key = _key(cfgdir)
    dec = _decided.get(key)
    if dec and dec[1] > time.time():
        return _apply(dec[0], env, why)
    choice = _ask(why, headroom(exclude=cfgdir), mode)
    _decided[key] = (choice, time.time() + _DECIDED_TTL)
    return _apply(choice, env, why, cfgdir)


def _apply(choice, env, why, cfgdir=None):
    if choice is None:                       # blocked
        _report(why)
        return env, why
    if choice == '':                         # "run anyway"
        return env, ''
    # The one place an account actually changes, so the one place that records
    # it. Recording at the call sites instead would be five copies, and the
    # cached `_decided` path goes through here too — a burst that switches once
    # and then reuses the decision should be one event, which it is, because
    # `events.record` dedupes an identical (src, msg) inside its window.
    _note_rotation(cfgdir, choice, why)
    return _c.account_env(choice), ''


def _note_rotation(frm, to, why):
    try:
        from . import rotate
        rotate.note(frm, to, why)
    except Exception:
        pass


def _ask(why, alts, mode):
    """cfgdir to switch to | '' to run anyway | None to block."""
    if mode == 'auto':
        return _pick_auto(alts)
    if _interactive():
        return _ask_tui(why, alts)
    job = _job()
    if job is not None and alts:
        return _ask_gui(job, why, alts)
    # Unattended: never prompt, and never quietly drain a second account on a
    # timer. That is exactly the failure the scheduler's own comment describes.
    return None


def _pick_auto(alts):
    """The account an unattended switch should use, or None to block.

    `alts` is already emptiest-first and already excludes what cannot be spent.
    What this adds is the rotation SWITCH threshold: an account at 99% may be
    spent but should not be chosen while one at 12% exists. If every candidate
    is past the threshold the emptiest is still better than blocking — the bar
    for "may be spent" is `reason()`, and headroom has already cleared it.
    """
    if not alts:
        return None
    try:
        from . import rotate
        fresh = [a for a in alts if not rotate.spent(a[1])]
    except Exception:
        fresh = []
    return (fresh or alts)[0][1]


def _interactive():
    """True only on the TUI's own main thread with a real terminal.

    All three conditions matter. `ui.menu` is NOT bridged by
    `gui_api._install_bridge`, so reaching it from a job thread is a hang rather
    than an error — and `plan_execute._headless` calls `_run_cancellable`
    directly even in the foreground, so the test has to be positive about being
    on the TUI rather than merely "not silent".
    """
    try:
        import sys
        import threading
        from . import memory
        if getattr(memory._tls, 'silent', False):
            return False
        if threading.current_thread() is not threading.main_thread():
            return False
        return bool(getattr(sys.stdin, 'isatty', lambda: False)())
    except Exception:
        return False


def _ask_tui(why, alts):
    from .ui import menu
    items = [('%s   %.0f%% used' % (name, pct), d) for name, d, pct in alts]
    # '__cancel__', never None: a None value is a non-selectable separator.
    items.append(('Run under the current account anyway', '__go__'))
    items.append(('Cancel', '__cancel__'))
    sel = menu(items, '%s — RUN UNDER ANOTHER ACCOUNT?' % why.upper())
    if sel == '__go__':
        return ''
    if not sel or sel == '__cancel__':
        return None
    return sel


def _ask_gui(job, why, alts):
    """Reuse the job approval gate rather than inventing a modal: it already
    renders a title, a list of lines and Approve/Reject, and the browser side
    needs no change at all."""
    from .gui_api import _gate
    name, d, _pct = alts[0]
    lines = ['%s.' % why, '',
             'Accounts with headroom:']
    lines += ['  %s   %.0f%% used' % (n, p) for n, _dd, p in alts]
    lines += ['', "Approve to run this under '%s' instead." % name,
              'Reject to stop and leave the quota alone.']
    # gate['diff'] must be a LIST at every producer — a string is truthy, so the
    # browser's `||[]` fallback never fires and .map() throws.
    ok = _gate(job, "Account limit reached — run under '%s'?" % name,
               '', '', lines)
    return d if ok else None


def _report(why):
    """Put the reason everywhere a caller might read it, instead of letting it
    surface as "No output from Claude"."""
    try:
        from . import memory
        memory.last_call_error = why
    except Exception:
        pass
    job = _job()
    if job is not None:
        try:
            job['last_subprocess_error'] = {'code': 0, 'output': why}
            msgs = job.setdefault('messages', [])
            if not msgs or msgs[-1].get('text') != why:
                msgs.append({'ok': False, 'text': why})
        except Exception:
            pass
    try:
        from . import events
        events.record('quota', why, level='warn',
                      detail='archeus did not start a Claude call it wanted '
                             'to make')
    except Exception:
        pass


def _job():
    try:
        from . import gui_api
        return getattr(gui_api._JOBCTX, 'job', None)
    except Exception:
        return None

"""Which account the next piece of work starts under.

When one account fills its 5-hour or weekly window, work stops even though the
other five have headroom. This module answers the one question that fixes that:
*given what the usage poller already knows, which account should the next
process start under?*

**It rotates at process boundaries, and that is the whole design.** Claude Code
fixes its account when it starts — `CLAUDE_CONFIG_DIR` is read once — so there
is no such thing as moving a running session to another account. What there IS,
and what archeus already owns, is every point where a new Claude process is
created: `quota.preflight` for archeus's own `claude -p` calls, the launch
builders for a session, and `context_inject` for handing a live conversation to
a successor session under a different account.

So nothing here reads, stores, forwards or refreshes a credential. That is not
timidity about a standing policy; it is the only design that is both safe and
permitted:

* An OAuth refresh ROTATES the refresh token and the spent one dies server-side,
  so a second program refreshing Claude Code's token logs the user out of Claude
  Code. Four open issues on Anthropic's tracker are that bug.
* Anthropic's own `legal-and-compliance` page permits "an end user … signing in
  to the unmodified Claude Code binary with their own Claude subscription" — one
  `CLAUDE_CONFIG_DIR` per account, launching the real binary, which is exactly
  what this does — and in the same paragraph forbids developers to "collect,
  store, or intermediate Claude.ai credentials or session tokens", which is
  exactly what a credential-substituting proxy is.

Two numbers, and they are deliberately different:

* `quota.LIMIT_PCT` (100%) is the BLOCK threshold — "this account cannot be
  spent". Unchanged.
* `threshold()` (98% by default) is the SWITCH threshold — "stop sending NEW
  work here". An account at 99% is still perfectly spendable; it is simply no
  longer the one that gets picked.

Fail open everywhere. An account nobody has polled reads 0.0% and is therefore
never "spent": a rotation layer that refuses work because a background thread
has not run yet is worse than the bug it fixes.
"""

import os

from . import config as _c

#: matches the reference implementation (claude-unlimited's `switch_threshold`).
#: Not 100: an account that is one request from its cap will refuse mid-turn,
#: and the point of rotating is to not start work that is about to be refused.
THRESHOLD_DEFAULT = 98.0

#: below this a threshold is not a policy, it is a way to never use an account
_MIN_THRESHOLD = 50.0

#: how much of the transition the user wants archeus to make on its own.
#:
#:   off   nothing rotates. The account you chose is the account you get, and a
#:         full window is reported exactly the way it is today.
#:   ask   NEW work starts on the next account with headroom by itself — an
#:         archeus `claude -p` call, a scheduled loop, a session you launch —
#:         but a session you are SITTING IN is only ever offered the move, one
#:         click, because mid-turn is usually the wrong moment and a successor
#:         session is a new terminal window.
#:   auto  the same, and the successor session opens on its own.
#:
#: 'ask' is the default. It is what "continue on the next account" means for
#: everything archeus starts, while still never opening a window nobody asked
#: for; `auto` is one click away in the rotation card for anyone who wants the
#: whole thing hands-off.
MODES = ('off', 'ask', 'auto')

#: older spellings, and the words people reach for. Mapped rather than rejected:
#: a settings file is hand-editable and 'semi' is what this mode is called in
#: the sentence the user asked the question in.
_MODE_ALIASES = {'semi': 'ask', 'prompt': 'ask', 'offer': 'ask',
                 'full': 'auto', 'on': 'auto', 'always': 'auto',
                 'none': 'off', 'never': 'off', 'manual': 'off'}


def _norm(d):
    return os.path.normcase(os.path.abspath(d or ''))


def _settings():
    try:
        return _c.load_settings()
    except Exception:
        return {}


def threshold():
    """The percentage at which an account stops being chosen for new work.

    Clamped HERE rather than in `gui._api_settings`: that handler's generic copy
    loop stores whatever the client sends for any declared key, and one reader
    that is defensive is better than one writer that is, because the settings
    file is hand-editable too.
    """
    try:
        v = float(_settings().get('rotate_threshold') or THRESHOLD_DEFAULT)
    except (TypeError, ValueError):
        return THRESHOLD_DEFAULT
    return max(_MIN_THRESHOLD, min(100.0, v))


def mode():
    """'off' | 'ask' | 'auto' — how much of the transition archeus makes itself."""
    m = str(_settings().get('rotate_mode') or 'ask').strip().lower()
    m = _MODE_ALIASES.get(m, m)
    return m if m in MODES else 'ask'


def enabled():
    """False when the user has turned rotation off entirely."""
    return mode() != 'off'


def hands_off():
    """True when a LIVE session's successor may be opened without a click.

    The one thing `auto` adds over `ask`. Everything else — which account new
    work starts under — is the same in both, because starting the next process
    somewhere else is invisible, and opening a terminal window is not.
    """
    return mode() == 'auto'


def disabled():
    """Normalised config dirs the user took OUT of the rotation.

    A per-account opt-out rather than an opt-in: a machine with accounts
    configured wants all of them by default, and an account you must remember to
    enable is an account that sits idle while you hit a limit.
    """
    raw = _settings().get('rotate_disabled')
    if not isinstance(raw, list):
        return set()
    return {_norm(_c.resolve_config_dir(d)) for d in raw
            if isinstance(d, str) and d.strip()}


def is_enabled(cfgdir=None):
    return _norm(_c.resolve_config_dir(cfgdir)) not in disabled()


def used_pct(cfgdir=None):
    """How full this account's fullest ACCOUNT-WIDE window is, 0.0 when unknown.

    Straight through `quota.worst_window`, which reads the usage poller's cache
    and never the network. A per-model weekly window does not count — refusing
    to send work to an account because its Opus weekly is spent would be wrong
    for every haiku call.
    """
    from . import quota
    return quota.worst_window(cfgdir)[0]


def spent(cfgdir=None):
    """True when this account should no longer be given NEW work.

    Two ways in, and deliberately only two:

    * its fullest account-wide window is at or past `threshold()`;
    * it answered with a refusal that names a plan WINDOW.

    A bare 429 is not one of them. The reference implementation makes the same
    distinction and it is the right one: a short rate limit means wait and retry
    the SAME account, and rotating on it would burn a second account's headroom
    for something that clears in seconds. `quota.note_failure` still latches the
    account either way — that is a different question (may it be spent now),
    which is why it is answered somewhere else.
    """
    from . import quota
    if quota.window_limited(cfgdir):
        return True
    return used_pct(cfgdir) >= threshold()


def name_of(cfgdir=None):
    """The account's configured name, or the directory's basename."""
    want = _norm(_c.resolve_config_dir(cfgdir))
    for name, d in _c.all_config_dirs():
        if _norm(_c.resolve_config_dir(d)) == want:
            return name
    return os.path.basename(want.rstrip('\\/')) or '?'


def candidates(exclude=None):
    """[(name, cfgdir, pct)] eligible for new work, emptiest first.

    `quota.headroom` already drops an account that is out of quota, one with no
    local credentials and one whose token has expired — and, since this module
    exists, one the user disabled. What is added here is the SWITCH threshold:
    headroom's bar is "can be spent", this one is "should be chosen".
    """
    from . import quota
    return [(n, d, p) for n, d, p in quota.headroom(exclude=exclude)
            if not spent(d)]


def elect(current=None):
    """The absolute config dir the next piece of work should start under.

    **Sticky.** The account in hand keeps the work until it is spent; rotating
    per call would fragment prompt caching and multiply cost for nothing. When
    nothing else is eligible the answer is the current account — never None, so
    a caller can use the result directly and a rotation layer with no opinion
    changes nothing.
    """
    cur = _c.resolve_config_dir(current)
    if not enabled():
        return cur
    if is_enabled(cur) and not spent(cur):
        return cur
    for _name, d, _pct in candidates(exclude=cur):
        return _c.resolve_config_dir(d)
    return cur


def recently_offered(sid):
    """True while this session's last offer is still inside the cool-down.

    The stamp itself lives in `quota`, beside `_decided`, whose comment already
    describes exactly this — one answer covers a burst. It is also why this
    module still writes nothing: `test_rotation_never_touches_a_credential`
    keeps rotation free of any store at all, and a cool-down is not a good
    enough reason to be the first exception to that.
    """
    from . import quota
    return quota.offered_recently(sid)


def offer(path, transcript, sid, why=''):
    """What archeus does when the session you are IN has run out. (acted, msg).

    ONE implementation for both triggers, because `ask` and `auto` are a policy
    and a policy with two implementations is two policies. The statusline sees
    the window fill BEFORE it is spent; `limit_hook.py` is told by Claude Code
    that a turn has already died on it. Neither is a better moment than the
    other and both want exactly this.

    `off` does nothing at all — including no notification, which is what the
    user asked for by turning it off.
    """
    if not enabled():
        return False, ''
    to = elect()
    if _norm(to) == _norm(_c.resolve_config_dir(None)):
        _log('%s is out and nothing else has headroom' % name_of(None), why)
        return False, 'no other account has headroom'
    if recently_offered(sid):
        return False, 'already offered'
    from . import quota
    quota.mark_offered(sid)
    name = name_of(to)
    if not hands_off():
        # `ask` cannot open a window, so the whole of it is reaching the user
        # somewhere they are actually looking. A terminal that has just refused
        # a turn is not that place: Claude Code discards a StopFailure hook's
        # output entirely, and a statusline is a row you have stopped reading by
        # the time it matters.
        _notify('%s has run out' % name_of(None),
                'Continue on %s — the rotation card has the button.' % name)
        _log('%s is out — offered %s' % (name_of(None), name), why)
        return False, 'offered %s' % name
    ok, err = continue_session(path, transcript, to)
    note(None, to, why)
    _notify('Continued on %s' % name,
            'archeus opened a successor session under %s.' % name if ok
            else 'Could not open it: %s' % (err or '?'))
    return bool(ok), (err or ('continued on %s' % name))


def _log(msg, why=''):
    """One line in archeus's own event log.

    Here rather than in `limit_hook.py`: a hook is on a per-turn path and every
    writer to that log is an archeus-owned process (`test_no_hook_writes_an_event`).
    `note()` already covers the rotation itself; this covers the two outcomes
    that are NOT a rotation, which are the ones somebody asking "why did nothing
    happen" actually needs.
    """
    try:
        from . import events
        return events.record('rotate', msg, level='warn', detail=str(why or '')[:200])
    except Exception:
        return False


def _notify(title, message):
    try:
        from . import notify
        if notify.enabled():
            notify.send(title, message)
    except Exception:
        pass


def continue_session(path, transcript, to=None, encoded=None):
    """Open a successor session under another account, continuing `transcript`.

    The one thing a running session cannot do for itself. Claude Code resumes by
    ABSOLUTE TRANSCRIPT PATH — by session id it searches the ACTIVE config dir
    and answers "No conversation found" for another account's session — and
    `--fork-session` is not optional, or the successor appends to a file that
    lives in the account it just left. Both of those are `main`'s `fork:` choice,
    which is why this builds no argv of its own: `gui.launch_session` applies the
    project's model, permission mode, system prompt and extra directories too,
    and a second copy of that decoration is a second thing to keep in step.

    Returns (ok, error).
    """
    from . import gui
    from .paths import encode_component
    to = _c.resolve_config_dir(to or elect())
    if not transcript or not os.path.isfile(transcript):
        return False, 'no transcript to continue'
    opts = dict(_launch_opts(), cfgdir=to)
    return gui.launch_session(path, encoded or encode_component(os.path.abspath(path)),
                              'fork:' + transcript, opts)


def _launch_opts():
    """The empty launch options `build_launch_command` indexes directly.

    Read out of `main.parse_choice_line` rather than restated: it indexes
    `opts['effort']` and five more with a bare subscript, so a dict that is
    merely "close enough" is a KeyError at spawn time and nowhere else.
    """
    from .main import parse_choice_line
    return parse_choice_line('')[3]


#: the hook that makes rotation reach a session you are SITTING IN. Everything
#: else here runs at a spawn point archeus owns; a live Claude Code session is
#: not one, and its limit is announced by Claude Code and nobody else.
def ensure_hook():
    """Install the StopFailure hook while rotation is on, remove it when off.

    No switch of its own: the mode chip already says how much archeus does for
    you, and a second toggle for the mechanism that implements it is a second
    thing to get out of step with it. Fans out across accounts, because the hook
    is a property of the USER — the account it must fire in is by definition the
    one that ran out.
    """
    try:
        from . import hooks
        fn = hooks.install_limit_hook if enabled() else hooks.uninstall_limit_hook
        return hooks.across_accounts(fn)
    except Exception:
        return {}


def hook_installed():
    try:
        from . import hooks
        return hooks.across_accounts(hooks.limit_hook_installed)
    except Exception:
        return {}


def note(frm, to, why=''):
    """Record one rotation in archeus's own event log.

    The message carries account NAMES and, where a number is unavoidable, a
    whole percent. `events._dedupe_shape` collapses decimals only, so a message
    reading '99.2%' would never dedupe against '99.3%' and a flapping account
    could fill the log — which has happened here before, to a different writer.
    """
    try:
        from . import events
        a, b = name_of(frm), name_of(to)
        if _norm(_c.resolve_config_dir(frm)) == _norm(_c.resolve_config_dir(to)):
            return False
        msg = 'account %s -> %s' % (a, b)
        return events.record('rotate', msg, level='info',
                             detail=str(why or '')[:200])
    except Exception:
        return False


def state():
    """Everything the GUI's rotation card renders, in one read.

    No network and no subprocess: every field comes from the usage poller's
    cache, the settings file and two file reads per account. It is safe to call
    from a request thread and from a 60-second poll.
    """
    from . import quota
    from . import usage
    live = _c.resolve_config_dir(None)
    rows = []
    for name, d in _c.all_config_dirs():
        rd = _c.resolve_config_dir(d)
        try:
            signed_in = bool(usage._read_token(rd)) and not usage._token_expired(rd)
        except Exception:
            signed_in = False
        pct, label, reset = quota.worst_window(rd)
        rows.append({'name': name, 'dir': d, 'resolved': rd,
                     'pct': round(pct, 1), 'window': label,
                     'resets': usage._fmt_reset(reset) if reset else '',
                     'enabled': is_enabled(rd), 'signed_in': signed_in,
                     'spent': spent(rd), 'live': _norm(rd) == _norm(live),
                     'blocked': quota.reason(rd)})
    nxt = elect()
    return {'threshold': threshold(), 'mode': mode(),
            'hands_off': hands_off(),
            #: which accounts carry the StopFailure hook. A policy that cannot
            #: see the event it exists for is worth saying out loud.
            'hook': hook_installed(),
            #: the OTHER quota switch, shown beside this one because it is the
            #: one question this feature does not answer: what archeus does
            #: when its OWN call meets a full account (prompt | auto | off).
            'headless_quota': (_settings().get('headless_quota') or 'prompt'),
            'live': live, 'live_name': name_of(live),
            'next': nxt, 'next_name': name_of(nxt),
            'rotating': _norm(nxt) != _norm(live),
            'accounts': rows, 'events': recent()}


def recent(limit=8):
    """The last few rotations, out of the event log the Logs page already reads.

    No second store and no new route: `events.record('rotate', …)` is the only
    writer and `events.read()` is the only reader, so the Logs page shows the
    same history with no work at all.
    """
    try:
        from . import events
        out = [e for e in events.read(200) if e.get('src') == 'rotate']
        return out[:limit]
    except Exception:
        return []

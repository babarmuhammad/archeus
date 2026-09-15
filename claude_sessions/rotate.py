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

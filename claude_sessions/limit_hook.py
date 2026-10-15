"""Claude Code StopFailure hook — the account you are SITTING IN ran out.

Every other place account rotation reaches is a process archeus spawns:
`quota.preflight` for its own `claude -p` calls, the launch builders for a
session, the hand-off for a successor. A Claude Code session you are already in
is none of those. Claude Code fixes its account when it starts, so the only
thing that can be done about a full window mid-session is to open a successor —
and the only thing that KNOWS the window is full is Claude Code itself.

`StopFailure` with the `rate_limit` matcher is that event, and until this file
existed nothing was listening to it. A full account in a terminal produced
silence: no prompt, no notification, and — because `quota._observed` is an
in-process dict — an archeus running in another window that went on cheerfully
offering the same account work for the rest of the window.

So this does two things, and the first matters even when rotation is off:

  1. `quota.note_limit` writes the refusal where every archeus process can read
     it, so the account stops being chosen for anything.
  2. `rotate.offer` applies the user's mode — notify, or open the successor.

Claude Code DISCARDS a StopFailure hook's stdout on every exit code apart from
side-effect fields, so there is no point printing anything for the user to
read; `terminalSequence` still fires, and a bell is the one thing this can put
in the terminal itself. The message goes through a desktop notification.

Installed by archeus (hooks.install_limit_hook). Never blocks: exit 0 always.
"""

import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Claude Code captures stdout as a PIPE, so CPython picks the locale codepage
# (cp1252 on Windows) and a non-ASCII byte either mojibakes or raises. Guarded:
# `sys.stdout` is None under pythonw with no console.
try:
    sys.stdout.reconfigure(encoding='utf-8')
except (AttributeError, ValueError, OSError):
    pass

#: the one output field StopFailure honours. A bell is not much, but it is the
#: only mark this event is allowed to leave in the terminal the user is looking
#: at, and it costs nothing when they are not.
BELL = '\a'


def handle(data):
    """The whole hook, minus stdin/stdout. Returns the JSON to print."""
    from claude_sessions import quota, rotate
    cwd = data.get('cwd') or os.getcwd()
    sid = str(data.get('session_id') or '')
    transcript = data.get('transcript_path') or ''

    # The refusal is a WINDOW limit, not a bare 429: Claude Code has its own
    # `overloaded` error type for the transient case, so `rate_limit` reaching
    # this hook means the plan window. Latching it as a window limit is what
    # makes `rotate.spent` true for this account in every other process.
    quota.note_limit(None, window=True)
    # No `events` import here on purpose: a hook is on a per-turn path and every
    # writer to that log is an archeus-owned process. `rotate.offer` records
    # what happened, which is the fact worth having anyway.
    # An Archeus V1 execution (ARCHEUS_EXECUTION_ID set) hands off through its
    # own checkpoint; a rotation offer here would open a second, competing
    # session. The latch above is still wanted: both apps must agree the
    # account is limited. (P0.5 hook guard)
    if not os.environ.get('ARCHEUS_EXECUTION_ID'):
        rotate.offer(cwd, transcript, sid, why='rate_limit in a live session')
    return {'terminalSequence': BELL}


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0
    if not isinstance(data, dict):
        return 0
    try:
        out = handle(data)
    except Exception:
        return 0
    if out:
        print(json.dumps(out))
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)          # a hook must never be the reason a turn fails

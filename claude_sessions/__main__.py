"""`python -m claude_sessions [...]` — same dispatch as claude-sessions.py.

Exists so the detached background memory worker (memory.spawn_background_worker)
can re-invoke archeus without depending on the repo-root launcher script.

The statusline is dispatched HERE, before `main` is imported: `main` pulls the
whole TUI stack plus `usage`, which drags in urllib/ssl/http.client for an OAuth
poll the statusline must never make — 48ms of import on a path that runs on
every conversation turn.
"""
import os
import sys

if len(sys.argv) >= 2 and sys.argv[1] == 'statusline':
    from .statusline import main
    raise SystemExit(main(sys.argv[2:]))

# `--help` before `main`, for the same reason and one of its own: the first
# thing a new install types must not pay for the TUI stack, and must not be
# breakable by anything in it. `cli` imports the standard library only.
if len(sys.argv) >= 2 and sys.argv[1] in ('--help', '-h', 'help'):
    from .cli import print_help
    print_help()
    raise SystemExit(0)
if len(sys.argv) >= 2 and sys.argv[1] in ('--version', '-V'):
    from .cli import print_version
    print_version()
    raise SystemExit(0)

# A scheduled background loop, run by Task Scheduler or cron every N minutes.
# HERE, above `main`, for the same reason as the statusline: this fires
# unattended forever, so it must not import the TUI stack to run one headless
# `claude -p`. `loops` reaches config/proc and nothing else.
if len(sys.argv) >= 3 and sys.argv[1] == '--loop-run':
    from .loops import run_once
    _cfg = sys.argv[sys.argv.index('--cfgdir') + 1] if '--cfgdir' in sys.argv else None
    raise SystemExit(run_once(sys.argv[2], _cfg))

# The deferred self-upgrade worker (versions.update_self spawns it). Dispatched
# HERE for a second reason on top of the statusline's: pip is about to replace
# every file in this package, so the worker must hold no lazy import of one.
# `proc` imports os/subprocess/sys/time and nothing from archeus.
if len(sys.argv) >= 4 and sys.argv[1] == '--self-update':
    import json

    from .proc import wait_and_run
    # Both after-steps are resolved to plain argv lists HERE, before the wait:
    # once pip starts, importing anything from this package is a coin toss
    # between the old files and the new ones. `notify.command` needs the
    # settings and the platform, both of which are readable right now.
    _to = os.environ.get('ARCHEUS_UPDATE_TO') or ''
    try:
        _relaunch = json.loads(os.environ.get('ARCHEUS_RELAUNCH') or 'null')
    except ValueError:
        _relaunch = None
    # the console scripts this process may have locked. Resolved by the PARENT,
    # which is the one that knows how it was launched; the worker only moves
    # what it is handed, and puts it back if the install fails.
    try:
        _free = json.loads(os.environ.get('ARCHEUS_FREE') or '[]')
    except ValueError:
        _free = []
    _after = []
    try:
        from .notify import command, enabled
        if enabled():
            _after.append(command(
                'archeus updated' + (' to ' + _to if _to else ''),
                'archeus is restarting.' if _relaunch
                else 'Start archeus to use the new version.'))
    except Exception:
        pass
    if _relaunch:
        _after.append(_relaunch)
    raise SystemExit(wait_and_run(sys.argv[2], sys.argv[3:], after=_after,
                                  free=_free))

from .main import run

run()

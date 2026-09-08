"""Claude Code hook — recent-work memory. Two events, one script:

  - Stop / SessionEnd : capture the just-finished session (heuristic, token-free)
                        into <cwd>/.archeus/memory/worklog.json.
  - SessionStart      : inject a compact 'Recent work' digest as additionalContext
                        so the new session knows what the last few did.

Opt-in per project via settings project_defaults[<encoded>]['worklog'].
Never blocks: exit 0 on every failure.

Installed by archeus (hooks.install_worklog_hook). Inspired by
thedotmack/claude-mem.
"""

import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Claude Code captures stdout as a PIPE, so CPython picks the locale
# codepage (cp1252 on Windows) and any non-ASCII character in the payload
# either mojibakes or raises — silently losing the whole hook output.
# Guarded: `sys.stdout` is None in a windowed process (pythonw with no
# console). A hook must degrade to plain output, never die at import.
try:
    sys.stdout.reconfigure(encoding='utf-8')
except (AttributeError, ValueError, OSError):
    pass


def _enabled_for(cwd):
    try:
        from claude_sessions.config import load_settings
        from claude_sessions.paths import encode_component
        s = load_settings()
        enc = encode_component(os.path.abspath(cwd))
        proj = (s.get('project_defaults') or {}).get(enc) or {}
        return bool(proj.get('worklog'))
    except Exception:
        return False


def _capture(cwd, data):
    tp = data.get('transcript_path') or ''
    if not tp or not os.path.isfile(tp):
        return 0
    from claude_sessions import worklog
    worklog.capture_session(cwd, data.get('session_id', ''), tp)
    return 0


def _inject(cwd):
    # cheap gate before heavy import: no worklog file → no-op. Literal on
    # purpose, same reason as recall_hook: reading store.WORKDIR would import
    # the package this gate exists to skip. Keep in step with it by hand.
    if not os.path.isfile(os.path.join(cwd, '.archeus', 'memory', 'worklog.json')):
        return 0
    from claude_sessions import worklog
    digest = worklog.render_digest(cwd)
    if not digest:
        return 0
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "SessionStart",
        "additionalContext": digest}}))
    return 0


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0
    if not isinstance(data, dict):
        return 0
    cwd = data.get('cwd') or os.getcwd()
    if not _enabled_for(cwd):
        return 0
    event = data.get('hook_event_name', '')
    if event in ('Stop', 'SessionEnd'):
        return _capture(cwd, data)
    if event == 'SessionStart':
        return _inject(cwd)
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)

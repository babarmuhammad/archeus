"""Claude Code SessionStart hook — inject a compact code-minimization rule as
additionalContext so the agent avoids over-engineering (fewer generated tokens).
Shell-agnostic; never errors. Inspired by Ponytail
(https://github.com/DietrichGebert/ponytail).
"""

import sys
import json
import os

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

# the text itself lives in hookrules so the audit can count it
# without importing this entry point — see that module
from claude_sessions.hookrules import MINIMAL_CODE as _RULE


def main():
    try:
        json.load(sys.stdin)          # consume hook input (ignored)
    except Exception:
        pass
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "SessionStart",
        "additionalContext": _RULE}}))
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)

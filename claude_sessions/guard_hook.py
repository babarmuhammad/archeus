"""Claude Code PreToolUse guard — block a tool call when a field of its input
matches a regex. Shell-agnostic (runs as a Python script, not a shell snippet,
so it works whether Claude Code invokes hooks via bash, cmd, or PowerShell).

    <python> guard_hook.py <field> <regex> [message]

Exit 2 = block the tool (Claude sees the message on stderr). Any error → exit 0
(never wrongly block). Used by the block-* hook templates in hooks.py.
"""

import sys
import json
import re

# Claude Code captures our streams as pipes, so CPython picks the locale
# codepage (cp1252 on Windows). Without this, one non-ASCII character in the
# user's own block message raised on the write below, escaped past `return 2`,
# and the fail-safe at the bottom converted a BLOCK into a silent ALLOW.
# Guarded: `sys.stdout` is None in a windowed process (pythonw with no
# console). A hook must degrade to plain output, never die at import.
try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except (AttributeError, ValueError, OSError):
    pass


def main():
    if len(sys.argv) < 3:
        return 0
    field, pattern = sys.argv[1], sys.argv[2]
    msg = sys.argv[3] if len(sys.argv) > 3 else 'blocked by archeus'
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0
    if not isinstance(data, dict):
        return 0
    val = str((data.get('tool_input') or {}).get(field, ''))
    try:
        hit = re.search(pattern, val)
    except re.error:
        return 0
    if not hit:
        return 0
    # The decision is already made; explaining it must never be able to undo it.
    try:
        sys.stderr.write('archeus: ' + msg + '\n')
    except Exception:
        pass
    return 2


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)

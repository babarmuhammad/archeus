"""Claude Code UserPromptSubmit hook — name the subagent that fits the prompt.

WHY THIS EXISTS
---------------
Claude Code routes to a subagent by matching your task against each agent's
`description`, and nothing else reads the agent body. Copying agents into
`<project>/.claude/agents/` therefore makes them *available*, never *suggested*
— measured on the machine this was written for, `agentLastUsed` held exactly one
entry while ten agents sat installed. The delegation table archeus writes into
CLAUDE.md helps, but it is one paragraph competing with the whole file.

This is the deterministic half: a keyword match against what you just typed,
printed as one line of context. No model call, no guessing, and it says nothing
at all when nothing matches — a hook that fires on every prompt has to be quiet
by default or it becomes noise you turn off.

THE PER-TURN RULE
-----------------
This runs on EVERY prompt, so it reads ONE small index
(`<project>/.claude/.archeus-agents.json`, written by
`agents.sync_project_agents`) instead of opening and parsing every agent file.
That is the cost lesson this codebase already learned twice: the recall hook's
counters and the worklog hook's transcript re-scan.
"""

import json
import os
import re
import sys

# Claude Code captures stdout as a PIPE — cp1252 on Windows — so a non-ASCII
# character in an agent's description would mojibake or raise, losing the hook.
# Guarded: `sys.stdout` is None in a windowed process (pythonw with no
# console). A hook must degrade to plain output, never die at import.
try:
    sys.stdout.reconfigure(encoding='utf-8')
except (AttributeError, ValueError, OSError):
    pass

INDEX_NAME = '.archeus-agents.json'

#: words that match everything and therefore identify nothing
_STOP = {
    'the', 'and', 'for', 'with', 'this', 'that', 'when', 'use', 'used', 'using',
    'agent', 'agents', 'code', 'project', 'file', 'files', 'from', 'into', 'your',
    'you', 'are', 'was', 'has', 'have', 'not', 'but', 'can', 'all', 'any', 'run',
    'make', 'need', 'want', 'like', 'also', 'more', 'than', 'then', 'them',
}
_WORD = re.compile(r'[a-z][a-z0-9+#._-]{2,}')

#: below this many shared words a "match" is a coincidence
_MIN_HITS = 2
#: how many agents to name at once — one is a suggestion, five is a menu
_MAX_SUGGEST = 2


def _words(text):
    return {w for w in _WORD.findall((text or '').lower()) if w not in _STOP}


def _index(cwd):
    try:
        with open(os.path.join(cwd, '.claude', INDEX_NAME), encoding='utf-8') as f:
            data = json.load(f)
    except Exception:
        return []
    return data.get('agents') or [] if isinstance(data, dict) else []


def suggest(prompt, agents):
    """[(name, score, reason)] — the agents whose triggers your prompt hits.

    Split out so the matching is testable without a hook payload, and so the
    threshold is one number in one place rather than a feeling."""
    want = _words(prompt)
    if not want:
        return []
    scored = []
    for a in agents:
        keys = {str(k).lower() for k in (a.get('keywords') or [])}
        hit = want & keys
        if len(hit) >= _MIN_HITS:
            scored.append((a.get('name', ''), len(hit), sorted(hit)[:4]))
    scored.sort(key=lambda t: -t[1])
    return scored[:_MAX_SUGGEST]


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    prompt = payload.get('prompt') or payload.get('user_prompt') or ''
    cwd = payload.get('cwd') or os.getcwd()
    hits = suggest(prompt, _index(cwd))
    if not hits:
        return 0                      # silence is the default, deliberately
    lines = ', '.join('%s (matches: %s)' % (n, ', '.join(r)) for n, _s, r in hits)
    print(json.dumps({'hookSpecificOutput': {
        'hookEventName': 'UserPromptSubmit',
        'additionalContext':
            'Subagent available for this task (archeus): %s. Delegate with the '
            'Agent tool if it fits — say which one you used, or say why you did '
            'it inline instead.' % lines}}))
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)

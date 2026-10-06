"""The fake harness's agent process: a scripted stand-in for `claude -p`.

Run as a plain script (`python fake_agent.py '<scenario json>' [start]`) —
stdlib only and no package imports, so it behaves like a foreign CLI would: it
knows the process I/O contract and nothing about Archeus internals.

It reads its whole stdin (the prompt file), announces itself with a `started`
event carrying a digest of what it read and the execution id from its
environment, then runs the scenario from step `start` (0; a resumed process
starts where the last one halted) — a JSON list of steps:

    {"emit": {...}}   write one JSON line to stdout (tool calls, usage,
                      assistant text with DECISION: lines, limit errors, …)
    {"sleep": 1.5}    wait (a long sleep is how a test gets something to stop)
    {"exit": 3}       exit now with that code (a crash is a non-zero exit)

An emitted event of `type: tool` is a tool call, and a real agent asks its
hook first: when `ARCHEUS_HOOK_CMD` names one (a JSON argv) the agent runs it
exactly as Claude Code runs a PreToolUse command — the call as JSON on stdin,
the decision as JSON on stdout (p11-design-gate §10.6). `allow` emits the
event; `deny` emits `tool_denied` and exits 3 (a script cannot adapt); a halt
emits `halted` with the step to resume at and exits 0. An allowed `Write` call
(`input: {file_path, content}`) writes that file in the workdir (P13: the
verifier judges the workspace, not the report).

Falling off the end of the scenario exits 0. The last line is always
`{"type": "exit", "code": n}`, so a Core that did not start the process (and
so cannot ask the OS for its exit code) still knows how it ended.
"""

import hashlib
import json
import os
import subprocess
import sys
import time


def hook(cmd, event):
    """The hook's answer for one tool call: (kind, reason)."""
    call = {'hook_event_name': 'PreToolUse', 'tool_name': event.get('name'),
            'tool_input': event.get('input'), 'cwd': os.getcwd(),
            'session_id': os.environ.get('ARCHEUS_EXECUTION_ID')}
    try:
        r = subprocess.run(cmd, input=json.dumps(call), capture_output=True, text=True,
                           timeout=float(os.environ.get('ARCHEUS_HOOK_WAIT', '60')) + 30)
        out = json.loads(r.stdout or '{}')
    except Exception as e:
        return 'halt', 'the hook could not run: %s' % type(e).__name__
    if out.get('continue') is False:
        return 'halt', out.get('stopReason') or ''
    spec = out.get('hookSpecificOutput') or {}
    kind = spec.get('permissionDecision')
    if kind in ('allow', 'deny'):
        return kind, spec.get('permissionDecisionReason') or ''
    return 'halt', 'the hook gave no decision'


def write(spec):
    """An allowed Write tool call writes its file, relative to the workdir (the
    process's cwd), as a real agent's would: what P13 verifies is the
    workspace, never what the agent said it did."""
    path, content = spec.get('file_path'), spec.get('content', '')
    if not isinstance(path, str) or not isinstance(content, str):
        return
    full = os.path.join(os.getcwd(), path)
    os.makedirs(os.path.dirname(full) or '.', exist_ok=True)
    with open(full, 'w', encoding='utf-8', newline='\n') as f:
        f.write(content)


def main(argv):
    steps = json.loads(argv[1]) if len(argv) > 1 else []
    start = int(argv[2]) if len(argv) > 2 else 0
    data = sys.stdin.buffer.read()
    out = sys.stdout
    cmd = json.loads(os.environ['ARCHEUS_HOOK_CMD']) if os.environ.get('ARCHEUS_HOOK_CMD') \
        else None

    def emit(obj):
        out.write(json.dumps(obj) + '\n')
        out.flush()                     # Core tails the file; buffer nothing

    def done(code):
        emit({'type': 'exit', 'code': code})
        return code

    emit({'type': 'started', 'pid': os.getpid(), 'at_step': start,
          'execution_id': os.environ.get('ARCHEUS_EXECUTION_ID'),
          'stdin_bytes': len(data), 'stdin_sha256': hashlib.sha256(data).hexdigest()})
    for i, step in enumerate(steps):
        if i < start:
            continue
        if 'emit' in step:
            ev = step['emit']
            if cmd is not None and isinstance(ev, dict) and ev.get('type') == 'tool':
                kind, reason = hook(cmd, ev)
                if kind == 'halt':
                    emit({'type': 'halted', 'at': i, 'reason': reason})
                    return done(0)
                if kind == 'deny':
                    emit({'type': 'tool_denied', 'name': ev.get('name'), 'reason': reason})
                    return done(3)
            if isinstance(ev, dict) and ev.get('type') == 'tool' and ev.get('name') == 'Write':
                write(ev.get('input') or {})
            emit(ev)
        elif 'sleep' in step:
            time.sleep(float(step['sleep']))
        elif 'exit' in step:
            return done(int(step['exit']))
        else:
            raise SystemExit('fake_agent: unknown step %r' % (step,))
    return done(0)


if __name__ == '__main__':
    sys.exit(main(sys.argv))

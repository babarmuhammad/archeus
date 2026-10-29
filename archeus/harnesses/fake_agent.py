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
exactly as Claude Code runs a PreToolUse command — the call as JSON on stdin
(p11-design-gate §10.6) — and reads its answer as Claude Code documents it:
exit code 2 blocks the call with the reason on stderr (ADR-0049 §3, the deny);
exit code 0 is the JSON on stdout (a `permissionDecision` allows or denies;
`continue: false` stops the agent, and blocks the call only together with the
deny: alone, the call RUNS first and the agent stops after it, as Claude Code
2.1.291 was observed to do — PV-19, O4); ANY other exit code, a timeout or a hook that
cannot run is a non-blocking error, and the call PROCEEDS — the worst case,
modelled so that a hook which fails open is caught here (P20). `allow` emits
the event; `deny` emits `tool_denied` and exits 3 (a script cannot adapt); a
halt emits `halted` with the step to resume at and exits 0. An allowed `Write` call
(`input: {file_path, content}`) writes that file in the workdir (P13: the
verifier judges the workspace, not the report).

Arguments after the scenario and the start step are the spawn's flags (P20,
ADR-0049); `started` echoes them as `argv`. The agent honours the tool flags as
Claude Code 2.1.292 was observed to (P20 slice F, ADR-0052): a tool absent from
`--tools`, denied by `--disallowedTools` (a name, `mcp__<server>`, or a glob),
an MCP tool whose server `--strict-mcp-config` did not load from `--mcp-config`,
or `Skill` under `--disable-slash-commands` does not exist — its call emits
`tool_unavailable`, never reaches the hook and never runs, and the agent goes on.

Falling off the end of the scenario exits 0. The last line is always
`{"type": "exit", "code": n}`, so a Core that did not start the process (and
so cannot ask the OS for its exit code) still knows how it ended.
"""

import fnmatch
import hashlib
import json
import os
import re
import subprocess
import sys
import time

#: the flags that take a value (everything else is a switch)
VALUED = ('--setting-sources', '--mcp-config', '--plugin-dir', '--tools', '--disallowedTools')
#: one tool under two names: `init` says `Task`, the API and --tools `Agent`
ALIASES = {'Agent': 'Task'}


def flags_of(args):
    """{flag: [values]} for a valued flag, {switch: []} for a switch."""
    out, i = {}, 0
    while i < len(args):
        a = args[i]
        if a in VALUED and i + 1 < len(args):
            out.setdefault(a, []).append(args[i + 1])
            i += 2
            continue
        out.setdefault(a, [])
        i += 1
    return out


def _names(values):
    return [ALIASES.get(n, n) for v in values for n in v.split(',') if n]


def _server(name):
    """An MCP tool's server, in the name Claude Code gives it."""
    return name.split('__')[1] if name.count('__') >= 2 else ''


def available(flags, name):
    """Whether Claude Code would offer the tool *name* under *flags*."""
    name = ALIASES.get(name, name)
    for p in _names(flags.get('--disallowedTools', ())):
        if fnmatch.fnmatchcase(name, p) or (
                p.count('__') == 1 and p.startswith('mcp__') and name.startswith(p + '__')):
            return False
    if name.startswith('mcp__'):
        if '--strict-mcp-config' not in flags:
            return True
        loaded = {re.sub(r'[^A-Za-z0-9_-]', '_', s) for s in mcp_servers(flags)}
        return _server(name) in loaded
    if name == 'Skill' and '--disable-slash-commands' in flags:
        return False
    return '--tools' not in flags or name in _names(flags['--tools'])


def mcp_servers(flags):
    """The servers `--mcp-config` loads, as the real CLI's init event lists them."""
    out = []
    for path in flags.get('--mcp-config', ()):
        try:
            with open(path, encoding='utf-8') as f:
                out += list(json.load(f).get('mcpServers') or {})
        except (OSError, ValueError):
            pass
    return out


def hook(cmd, event):
    """The hook's answer for one tool call: (kind, reason)."""
    call = {'hook_event_name': 'PreToolUse', 'tool_name': event.get('name'),
            'tool_input': event.get('input'), 'cwd': os.getcwd(),
            'session_id': os.environ.get('ARCHEUS_EXECUTION_ID')}
    try:
        r = subprocess.run(cmd, input=json.dumps(call), capture_output=True, text=True,
                           encoding='utf-8', errors='replace',
                           timeout=float(os.environ.get('ARCHEUS_HOOK_TIMEOUT', '120')))
    except Exception as e:                          # incl. a timeout: non-blocking
        return 'proceed', 'the hook did not answer: %s' % type(e).__name__
    if r.returncode == 2:
        return 'deny', (r.stderr or '').strip()
    if r.returncode != 0:
        return 'proceed', 'the hook exited %d' % r.returncode
    try:
        out = json.loads(r.stdout or '{}')
    except ValueError:
        return 'proceed', 'the hook printed no JSON'
    out = out if isinstance(out, dict) else {}
    spec = out.get('hookSpecificOutput') or {}
    if out.get('continue') is False:
        if spec.get('permissionDecision') == 'deny':
            return 'halt', out.get('stopReason') or ''
        return 'halt_after', out.get('stopReason') or ''
    if spec.get('permissionDecision') == 'allow':
        return 'allow', ''
    return 'proceed', 'the hook gave no decision'


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

    flags = flags_of(argv[3:])
    emit({'type': 'started', 'pid': os.getpid(), 'at_step': start,
          'execution_id': os.environ.get('ARCHEUS_EXECUTION_ID'),
          'stdin_bytes': len(data), 'stdin_sha256': hashlib.sha256(data).hexdigest(),
          'argv': argv[3:], 'mcp_servers': mcp_servers(flags)})
    for i, step in enumerate(steps):
        if i < start:
            continue
        if 'emit' in step:
            ev = step['emit']
            kind = None
            if isinstance(ev, dict) and ev.get('type') == 'tool' and \
                    not available(flags, ev.get('name') or ''):
                emit({'type': 'tool_unavailable', 'name': ev.get('name'),
                      'reason': 'No such tool available: %s' % ev.get('name')})
                continue
            if cmd is not None and isinstance(ev, dict) and ev.get('type') == 'tool':
                kind, reason = hook(cmd, ev)
                if kind == 'proceed':
                    emit({'type': 'hook_error', 'name': ev.get('name'), 'reason': reason})
                if kind == 'halt':
                    emit({'type': 'halted', 'at': i, 'reason': reason})
                    return done(0)
                if kind == 'deny':
                    emit({'type': 'tool_denied', 'name': ev.get('name'), 'reason': reason})
                    return done(3)
            if isinstance(ev, dict) and ev.get('type') == 'tool' and ev.get('name') == 'Write':
                write(ev.get('input') or {})
            emit(ev)
            if kind == 'halt_after':
                emit({'type': 'halted', 'at': i + 1, 'reason': reason})
                return done(0)
        elif 'sleep' in step:
            time.sleep(float(step['sleep']))
        elif 'exit' in step:
            return done(int(step['exit']))
        else:
            raise SystemExit('fake_agent: unknown step %r' % (step,))
    return done(0)


if __name__ == '__main__':
    sys.exit(main(sys.argv))

"""The execution hook (p11-design-gate §10): Claude Code's PreToolUse command
for an Archeus execution, and the same file the fake agent runs.

    <python> hook.py      (the tool call as JSON on stdin, as Claude Code sends it)

Standard library only and no package imports: it runs inside the agent's
process tree, with the agent's environment, and must behave identically for
every harness that runs it.

In order: the global STOP sentinel -> halt; this execution's STOP or PAUSE flag
-> halt; otherwise the request goes to Core through the execution's mailbox
(`<ARCHEUS_HOME>/run/exec/<id>/hook/<seq>.req.json`) and the hook waits for
`<seq>.res.json`. Core answers `allow`, `deny` or `halt`. No answer in time, an
unreadable answer, a missing identity, a crash: deny and halt (fail closed, D13).
A halt leaves `halted.json` in the execution's directory, which is how Core tells
a halted process from one that finished (§9.1).

Answered in Claude Code's hook protocol (P20, ADR-0049 §3):
    allow  exit 0, on stdout {"hookSpecificOutput": {..., "permissionDecision": "allow"}}
    deny   exit 2, the reason on stderr, nothing on stdout: exit code 2 is the
           documented unconditional block, whatever another source's hook says
    halt   exit 0, on stdout {"continue": false, "stopReason": reason} AND the
           PreToolUse `permissionDecision: "deny"`: Claude Code does not treat
           `continue: false` alone as a block of the call it answers (PV-19, O4)
Never any other exit code: Claude Code treats one as a non-blocking error and
lets the call through, so a crash anywhere is a halt, or a deny when even the
halt cannot be written.
"""

import json
import os
import re
import sys
import time

WAIT_S = float(os.environ.get('ARCHEUS_HOOK_WAIT', '60'))
POLL_S = 0.05
_ID = re.compile(r'exe_[0-9A-HJKMNP-TV-Z]{26}\Z')


#: Claude Code's documented blocking exit code (a deny)
DENY_EXIT = 2


def decision(kind, reason=''):
    """The stdout JSON of an exit-0 answer: allow, halt or a PreCompact's continue."""
    if kind == 'continue':
        return {}                   # a PreCompact answer: nothing to decide
    if kind == 'halt':
        # `continue: false` alone does not block the call it answers: Claude
        # Code 2.1.291 runs a call its own rules allow and only then stops, and
        # does not stop at all when it refuses the call itself (PV-19, O4). The
        # deny is what keeps a halt fail-closed for the call in flight.
        reason = reason or 'halted by Archeus'
        return {'continue': False, 'stopReason': reason,
                'hookSpecificOutput': {'hookEventName': 'PreToolUse',
                                       'permissionDecision': 'deny',
                                       'permissionDecisionReason': reason}}
    if kind != 'allow':
        raise ValueError('only allow, halt and continue answer on stdout: %r' % (kind,))
    return {'hookSpecificOutput': {'hookEventName': 'PreToolUse',
                                   'permissionDecision': 'allow'}}


def answer(kind, reason=''):
    """(stdout, stderr, exit code) for one decision."""
    if kind == 'deny':
        return '', reason or 'denied by Archeus', DENY_EXIT
    return json.dumps(decision(kind, reason)), '', 0


def _halted(exec_dir, seq, reason):
    try:
        tmp = os.path.join(exec_dir, 'halted.json.tmp')
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump({'seq': seq, 'reason': reason, 'at': time.time()}, f)
        os.replace(tmp, os.path.join(exec_dir, 'halted.json'))
    except OSError:
        pass


def _reserve(box, body):
    """Write the request under the next free sequence number, atomically. The
    number is taken by creating `<seq>.lock` exclusively, and the lock is never
    removed, so two hooks can never hold one number."""
    os.makedirs(box, exist_ok=True)
    while True:
        taken = [int(n.split('.')[0]) for n in os.listdir(box)
                 if n.split('.')[0].isdigit()]
        seq = max(taken, default=0) + 1
        try:
            os.close(os.open(os.path.join(box, '%d.lock' % seq),
                             os.O_CREAT | os.O_EXCL | os.O_WRONLY))
        except FileExistsError:
            continue                    # a concurrent hook took it: try the next
        part = os.path.join(box, '%d.req.part' % seq)
        with open(part, 'w', encoding='utf-8') as f:
            json.dump(dict(body, seq=seq), f)
        os.replace(part, os.path.join(box, '%d.req.json' % seq))
        return seq


def run(payload, environ):
    home, eid = environ.get('ARCHEUS_HOME'), environ.get('ARCHEUS_EXECUTION_ID', '')
    token = environ.get('ARCHEUS_HOOK_TOKEN')
    if environ.get('ARCHEUS_HOOK_ACTIVE'):
        return 'halt', 'the Archeus hook may not run inside itself'
    if not (home and token and _ID.match(eid)):
        return 'halt', 'this process has no Archeus execution identity'
    exec_dir = os.path.join(home, 'run', 'exec', eid)
    if payload.get('hook_event_name') == 'PreCompact':
        # the context-pressure backstop (p12-design-gate §13.1): recorded for
        # Core, never asked of it; compaction itself goes ahead
        try:
            os.makedirs(exec_dir, exist_ok=True)
            with open(os.path.join(exec_dir, 'precompact.json'), 'w', encoding='utf-8') as f:
                json.dump({'at': time.time(), 'trigger': payload.get('trigger')}, f)
        except OSError:
            pass
        return 'continue', ''
    if os.path.exists(os.path.join(home, 'run', 'STOP')):
        _halted(exec_dir, None, 'emergency stop')
        return 'halt', 'emergency stop'
    for flag, why in (('STOP', 'stopped by Archeus'), ('PAUSE', 'paused by Archeus'),
                      ('HANDOFF', 'handing off to a fresh session')):
        if os.path.exists(os.path.join(exec_dir, flag)):
            _halted(exec_dir, None, why)
            return 'halt', why
    box = os.path.join(exec_dir, 'hook')
    seq = _reserve(box, {'token': token, 'tool': payload.get('tool_name'),
                         'input': payload.get('tool_input'), 'cwd': payload.get('cwd')})
    res = os.path.join(box, '%d.res.json' % seq)
    deadline = time.monotonic() + WAIT_S
    while time.monotonic() < deadline:
        if os.path.exists(os.path.join(home, 'run', 'STOP')):
            _halted(exec_dir, seq, 'emergency stop')
            return 'halt', 'emergency stop'
        try:
            with open(res, encoding='utf-8') as f:
                got = json.load(f)
        except (OSError, ValueError):
            time.sleep(POLL_S)
            continue
        kind = got.get('decision') if isinstance(got, dict) else None
        if kind not in ('allow', 'deny', 'halt'):
            break
        if kind == 'halt':
            _halted(exec_dir, seq, got.get('reason') or '')
        return kind, got.get('reason') or ''
    _halted(exec_dir, seq, 'Archeus did not answer')
    return 'halt', 'Archeus did not answer; denied and halted (fail closed)'


def main():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding='utf-8')
        except (AttributeError, ValueError, OSError):
            pass
    env = dict(os.environ)
    os.environ['ARCHEUS_HOOK_ACTIVE'] = '1'
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError('the hook input is a JSON object')
        kind, reason = run(payload, env)
    except Exception as e:              # a broken hook never allows
        kind, reason = 'halt', 'the Archeus hook failed: %s' % type(e).__name__
    out, err, code = answer(kind, reason)
    if out:
        sys.stdout.write(out)
        sys.stdout.flush()
    if err:
        sys.stderr.write(err)
        sys.stderr.flush()
    return code


def guarded(fn=main):
    """*fn*'s exit code, or the deny's when anything at all escapes it (even the
    write of a halt): never a code Claude Code would let the call through on."""
    try:
        code = fn()
    except BaseException:               # noqa: B036 — nothing may leave but an answer
        code = None
    if code in (0, DENY_EXIT):
        return code
    try:
        sys.stderr.write('the Archeus hook failed; denied (fail closed)')
        sys.stderr.flush()
    except Exception:
        pass
    return DENY_EXIT


if __name__ == '__main__':
    code = guarded()
    try:            # a flush the interpreter would do at exit can fail too, and
        sys.stdout.flush()      # then it exits 120 whatever was returned: flush
        sys.stderr.flush()      # here, and leave without the interpreter's
    except Exception:           # own finalisation
        code = DENY_EXIT
    os._exit(code)

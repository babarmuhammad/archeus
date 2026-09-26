"""The fake harness's agent process: a scripted stand-in for `claude -p`.

Run as a plain script (`python fake_agent.py '<scenario json>'`) — stdlib only
and no package imports, so it behaves like a foreign CLI would: it knows the
process I/O contract and nothing about Archeus internals.

It reads its whole stdin (the prompt file), announces itself with a `started`
event carrying a digest of what it read and the execution id from its
environment, then runs the scenario — a JSON list of steps:

    {"emit": {...}}   write one JSON line to stdout (tool calls, usage,
                      assistant text with DECISION: lines, limit errors, …)
    {"sleep": 1.5}    wait (a long sleep is how a test gets something to stop)
    {"exit": 3}       exit now with that code (a crash is a non-zero exit)

Falling off the end of the scenario exits 0.
"""

import hashlib
import json
import os
import sys
import time


def main(argv):
    steps = json.loads(argv[1]) if len(argv) > 1 else []
    data = sys.stdin.buffer.read()
    out = sys.stdout

    def emit(obj):
        out.write(json.dumps(obj) + '\n')
        out.flush()                     # Core tails the file; buffer nothing

    emit({'type': 'started', 'pid': os.getpid(),
          'execution_id': os.environ.get('ARCHEUS_EXECUTION_ID'),
          'stdin_bytes': len(data), 'stdin_sha256': hashlib.sha256(data).hexdigest()})
    for step in steps:
        if 'emit' in step:
            emit(step['emit'])
        elif 'sleep' in step:
            time.sleep(float(step['sleep']))
        elif 'exit' in step:
            return int(step['exit'])
        else:
            raise SystemExit('fake_agent: unknown step %r' % (step,))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))

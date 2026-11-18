"""Compare the installed Claude Code's tools with the checked-in snapshot
(ADR-0052 §6's drift test, against the installed CLI; p20-design-gate slice F).

    py tools/claude_tool_drift.py [--home <account config dir>] [--json]

Record-only and makes no model call: Claude Code is started on the account,
with every HTTPS connection refused (a proxy on a port that is bound and never
listens), and stopped as soon as it reports its `init` event. For every model
of the snapshot it starts twice: under the narrowest settings sources (the
snapshot's `tools`, less what `model_only` gives other models) and with slash
commands on (`with_slash_commands` too). Once more with `--tools` naming every
mapped name plus `Skill`, which proves the CLI keeps exactly the offered ones
and drops the rest (`mapped_not_offered`) without a word.

Exit 0: no drift. Exit 1: drift, printed. Exit 2: the CLI could not be read.
"""

import argparse
import json
import os
import queue
import socket
import subprocess
import sys
import threading

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from archeus.harnesses.claude_code import tools  # noqa: E402
from claude_sessions import config, proc  # noqa: E402

NARROW = ['--setting-sources', '', '--strict-mcp-config']


def _init(exe, home, extra, port):
    env = {k: v for k, v in os.environ.items()
           if not (k.startswith(('ANTHROPIC_', 'CLAUDE_CODE')) or k in (
               'CLAUDECODE', 'NO_PROXY', 'no_proxy', 'ENABLE_TOOL_SEARCH'))}
    env.update(CLAUDE_CONFIG_DIR=home, HTTPS_PROXY='http://127.0.0.1:%d' % port,
               HTTP_PROXY='http://127.0.0.1:%d' % port, DISABLE_AUTOUPDATER='1')
    p = subprocess.Popen([exe, '-p', '--output-format', 'stream-json', '--verbose',
                          '--max-turns', '1', '--no-session-persistence'] + NARROW + extra,
                         stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=subprocess.DEVNULL, cwd=ROOT, env=env)
    p.stdin.write(b'tool drift check')
    p.stdin.close()
    q = queue.Queue()
    threading.Thread(target=lambda: [q.put(x) for x in p.stdout] + [q.put(None)],
                     daemon=True).start()
    try:
        while True:
            line = q.get(timeout=60)
            if line is None:
                return None
            if b'"subtype":"init"' in line:
                return json.loads(line)
    except queue.Empty:
        return None
    finally:
        proc.kill_tree(p)


def _norm(names):
    return {tools.ALIASES.get(n, n) for n in names if not n.startswith('mcp__')}


def expected(model, *, slash=False):
    snap = tools.SNAPSHOT
    got = _norm(snap['tools']) - {t for t, ms in snap['model_only'].items() if model not in ms}
    return got | _norm(snap['with_slash_commands']) if slash else got


def check(exe=None, home=None):
    """{version, drift: [...], observed: {...}}; drift empty when none."""
    exe = exe or config.get_claude_exe()
    home = home or config.resolve_config_dir(None)
    version = subprocess.run([exe, '--version'], capture_output=True, text=True,
                             timeout=60).stdout.split()[0]
    mapped = [t for ts in tools.TOOLS.values() for t in ts]
    dead = socket.socket()
    dead.bind(('127.0.0.1', 0))                     # bound, never listening: refused
    try:
        port = dead.getsockname()[1]
        runs, want = {}, {}
        for m in tools.SNAPSHOT['models']:
            runs[m] = _init(exe, home, ['--model', m, '--disable-slash-commands'], port)
            runs[m + '+slash'] = _init(exe, home, ['--model', m], port)
            want[m], want[m + '+slash'] = expected(m), expected(m, slash=True)
        runs['mapped'] = _init(exe, home, ['--tools', ','.join(mapped + [tools.SKILL])], port)
        want['mapped'] = (set(mapped) & tools.offered()) | {tools.SKILL}
    finally:
        dead.close()
    if not all(runs.values()):
        return {'version': version, 'error': 'no init event from %s for %s' % (
            exe, [k for k, v in runs.items() if not v])}
    got = {k: _norm(v.get('tools') or ()) for k, v in runs.items()}
    drift = []
    if version != tools.SNAPSHOT['version']:
        drift.append('version %s, snapshot %s' % (version, tools.SNAPSHOT['version']))
    for k in runs:
        if got[k] != want[k]:
            drift.append('%s: new %s, gone %s' % (k, sorted(got[k] - want[k]),
                                                  sorted(want[k] - got[k])))
    offered = set().union(*(got[m + '+slash'] for m in tools.SNAPSHOT['models']))
    not_offered = sorted(set(mapped) - offered)
    if not_offered != sorted(tools.SNAPSHOT['mapped_not_offered']):
        drift.append('mapped but not offered: %s, snapshot %s' % (
            not_offered, sorted(tools.SNAPSHOT['mapped_not_offered'])))
    return {'version': version, 'drift': drift,
            'observed': {k: sorted(v) for k, v in got.items()}}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--home')
    ap.add_argument('--json', action='store_true')
    a = ap.parse_args(argv)
    out = check(home=a.home)
    if a.json:
        print(json.dumps(out, indent=1))
    elif out.get('error'):
        print(out['error'])
    else:
        print('Claude Code %s: %s' % (out['version'], '; '.join(out['drift']) or 'no drift'))
    return 2 if out.get('error') else 1 if out['drift'] else 0


if __name__ == '__main__':
    sys.exit(main())

"""N4 native fixture-only check: Core's seed, import, store and verifier paths, and the real
agent CLI against a fake broker, each driven through the PRODUCTION MXC launch stack.

Not run by its author. It runs only after the owner has read the review sheet
(.collab/N4-review-sheet-2026-11-01.md) and authorised the run.

Usage:  python -m tools.pv20_mxc.native.n4_check <fixture-parent>
  Exactly one argument: a directory at or below D:\\archeus-worktrees\\pv20-fixtures (letters, digits, dot,
  underscore, hyphen). The operator pre-stages two things under it: the MXC SDK at
  <parent>\\sdk\\node_modules\\@microsoft\\mxc-sdk (as N1 to N3 did) and the agent CLI, a
  folder holding claude.exe, at <parent>\\cli. The fixture root is safe_root(parent), a fresh
  uuid child with a marker; remove_fixture(root) deletes it only when the whole run exits 0.
  The declared INCONCLUSIVE rows keep a clean run at exit 2, so the root is normally kept.

What it drives (production code, nothing re-implemented): LocalNode.store_open, store_git,
store_seed_ref, seed_workspace and import_workspace (Core's pinned Git store, copy-only seed
and data-only import); staging.seed_execution and recheck_execution through MxcLaunch's seed
seam; local.MxcLaunch with Process.attach streaming and process generations; the journal names
of mxc_ledger; isolation.Isolation over mxc_boundary.MxcBoundary through
LocalNode.run_confined_check; base.BrokerLaunch for the broker variables; mxc.compile_policy;
win32_mxc.Win32Api; the real KILL_ON_JOB_CLOSE Job.

Script-side stand-ins, each named in its row: the fake provider and its loopback listener (the
production broker listener does not exist yet), the proxy policy (MxcLaunch compiles
proxy_url=None, so the script recompiles the policy with the production compiler's own
proxy_url), the pinned schema validator (returns True), the hash pins (computed from the staged
copy), the resource reader (launcher identity gone), the Job end callback (TerminateJobObject on
the Job the script made), the hostile Git state (planted by the script, never by a container).

Safety posture: stdlib plus the production modules above; no external network (every policy
denies egress; the only listeners are bound to 127.0.0.1 and the only client is the script's own
host side touching them); no ACL tool or API and no profile API; no process is terminated unless
this script created it and its creation time still matches (the Job close is the kill); the
production modules are imported with every home, profile, temp and config variable pointed at an
empty folder inside the root and kept there for the whole run, ARCHEUS_HOME is a folder inside
the root; the host files the containers write are read back only after an lstat; the one host
execution of planted Git configuration is the labelled control of hostile-git-inert-controls and
its payload only writes a marker file inside the fixture. Only SystemRoot is read from the
environment, once, to name cmd.exe and curl.exe.

Exit codes: 0 all cases PASS / 1 first FAIL / 2 no FAIL but an INCONCLUSIVE is present /
3 setup error, budget overrun or a surviving launcher.
"""
import http.server
import json
import ntpath
import os
import re
import shutil
import socket
import stat
import subprocess
import sys
import threading
import time
from collections import namedtuple
from types import SimpleNamespace

from tools.pv20_mxc.native import n2_check as n2
from tools.pv20_mxc.native.common import Recorder, StopRun, redact, remove_fixture, safe_root
from tools.pv20_mxc.protocol import STAGES

STAGE = 'N4'
CASES = STAGES[STAGE].cases
LIVE_CASE = 'separately-authorized-live-provider'
JOURNAL = 'n4_journal.jsonl'
BUDGET_S = 1700.0            # protocol.STAGES['N4'].budget is 1800
QUIESCE_S = 5.0
LOOPBACK = '127.0.0.1'
MODEL = 'claude-sonnet-4-5'
SEED_REF = 'refs/archeus/fixture/seed'
BODY_MAX = 1 << 20
GIT_META = ('HEAD', 'config', 'shallow', 'index', 'objects', 'refs')
PROD = ('archeus.core.domain.ids', 'archeus.infra.paths', 'archeus.harnesses.base',
        'archeus.node.mxc', 'archeus.node.staging', 'archeus.node.win32_mxc',
        'archeus.node.mxc_ledger', 'archeus.node.mxc_boundary', 'archeus.node.mxc_context',
        'archeus.node.isolation', 'archeus.node.local')
CLEAN, QUARANTINED = n2.CLEAN, n2.QUARANTINED
SetupError = n2.SetupError


# --------------------------------------------------------------------------
# Pure logic (no OS call): everything below this line up to "network" is unit tested
# --------------------------------------------------------------------------

def layout(root):
    j = lambda *p: os.path.join(root, *p)
    return {'root': root, 'sdk': j('sdk'), 'cli': j('cli'), 'toolchain': j('toolchain'),
            'private': j('private'), 'ledger': j('ledger'), 'envhome': j('envhome'),
            'home': j('h'), 'localappdata': j('localappdata'), 'outside': j('outside'),
            'src': j('src'), 'seedws': j('seedws'), 'ctl': j('ctl'), 'faults': j('faults')}


def make_dirs(lay):
    for key in ('private', 'toolchain', 'envhome', 'home', 'localappdata', 'outside', 'src',
                'seedws', 'ctl', 'faults'):
        os.makedirs(lay[key], exist_ok=True)


def pin_environment(environ, lay):
    """Keep every profile, temp and config variable inside the root for the whole run."""
    for name in n2.HOME_VARS:
        environ[name] = lay['envhome']
    environ['ARCHEUS_HOME'] = lay['home']


def seed_files(secret):
    return [('notes.txt', '100644', ('edit me %s\n' % secret).encode()),
            ('src/app.txt', '100644', b'app\n'),
            ('run.cmd', '100755', b'@echo off\r\n'),
            ('link.txt', '120000', b'notes.txt'),
            ('sub', '160000', b'1' * 40)]


def fast_import_stream(ref, files, when=1700000000):
    message = b'n4 fixture seed\n'
    out = [b'commit %s\ncommitter n4 <n4@invalid> %d +0000\ndata %d\n%s\n'
           % (ref.encode(), when, len(message), message)]
    for rel, mode, data in files:
        if mode == '160000':
            out.append(b'M 160000 %s %s\n' % (data, rel.encode()))
        else:
            out.append(b'M %s inline %s\ndata %d\n%s\n' % (mode.encode(), rel.encode(), len(data), data))
    out.append(b'done\n')
    return b''.join(out)


def walk_plain(root):
    """(relative path, lstat, is_link) for everything below root, never following a link."""
    out, stack = [], [root]
    while stack:
        folder = stack.pop()
        with os.scandir(folder) as entries:
            names = [e.path for e in entries]
        for path in names:
            info = os.lstat(path)
            link = stat.S_ISLNK(info.st_mode) or bool(getattr(info, 'st_file_attributes', 0) & 0x400)
            out.append((os.path.relpath(path, root).replace(os.sep, '/'), info, link))
            if stat.S_ISDIR(info.st_mode) and not link:
                stack.append(path)
    return out


def tree_problems(entries, root, files, seed_config):
    """What is wrong with a seeded workspace: any alias, any second name for a file, an entry
    the tree does not name, a plain file that differs, a .git that holds more than Core wrote."""
    names = {rel: data for rel, mode, data in files if mode in ('100644', '100755', '120000')}
    exact = {rel: data for rel, mode, data in files if mode in ('100644', '100755')}
    folders = {'sub'} | {rel.rsplit('/', 1)[0] for rel in names if '/' in rel}
    bad = []
    for rel, info, link in entries:
        top = rel.split('/')[0]
        if link:
            bad.append('alias: %s' % rel)
        elif stat.S_ISREG(info.st_mode) and info.st_nlink != 1:
            bad.append('a second name for %s' % rel)
        if top == '.git':
            parts = rel.split('/')
            if len(parts) == 2 and parts[1] not in GIT_META:
                bad.append('unexpected .git entry: %s' % rel)
            if rel == '.git/objects/info/alternates':
                bad.append('the seed borrows objects from another store')
        elif rel not in names and rel not in folders:
            bad.append('unexpected entry: %s' % rel)
    for rel, data in exact.items():
        try:
            with open(os.path.join(root, *rel.split('/')), 'rb') as fh:
                if fh.read() != data:
                    bad.append('differs from the tree: %s' % rel)
        except OSError:
            bad.append('missing: %s' % rel)
    try:
        with open(os.path.join(root, '.git', 'config'), 'rb') as fh:
            if fh.read() != seed_config:
                bad.append('.git/config is not the config Core wrote')
    except OSError:
        bad.append('.git/config missing')
    return bad


Hit = namedtuple('Hit', 'method path auth body at')


def sse(event, data):
    return ('event: %s\ndata: %s\n\n' % (event, json.dumps(data))).encode()


def _start(model, mid):
    return sse('message_start', {'type': 'message_start', 'message': {
        'id': mid, 'type': 'message', 'role': 'assistant', 'model': model, 'content': [],
        'stop_reason': None, 'stop_sequence': None,
        'usage': {'input_tokens': 10, 'output_tokens': 1}}})


def _stop(reason):
    return [sse('content_block_stop', {'type': 'content_block_stop', 'index': 0}),
            sse('message_delta', {'type': 'message_delta', 'delta': {
                'stop_reason': reason, 'stop_sequence': None}, 'usage': {'output_tokens': 5}}),
            sse('message_stop', {'type': 'message_stop'})]


def text_turn(text, model=MODEL, mid='msg_n4'):
    return [_start(model, mid),
            sse('content_block_start', {'type': 'content_block_start', 'index': 0,
                                        'content_block': {'type': 'text', 'text': ''}}),
            sse('content_block_delta', {'type': 'content_block_delta', 'index': 0,
                                        'delta': {'type': 'text_delta', 'text': text}})] + _stop('end_turn')


def tool_turn(tool_id, name, tool_input, model=MODEL, mid='msg_n4t'):
    raw = json.dumps(tool_input)
    half = len(raw) // 2
    parts = [sse('content_block_delta', {'type': 'content_block_delta', 'index': 0,
                                         'delta': {'type': 'input_json_delta', 'partial_json': raw[:half]}}),
             sse('content_block_delta', {'type': 'content_block_delta', 'index': 0,
                                         'delta': {'type': 'input_json_delta', 'partial_json': raw[half:]}})]
    return [_start(model, mid),
            sse('content_block_start', {'type': 'content_block_start', 'index': 0, 'content_block': {
                'type': 'tool_use', 'id': tool_id, 'name': name, 'input': {}}})] + parts + _stop('tool_use')


def request_json(body):
    try:
        doc = json.loads(body.decode('utf-8'))
    except ValueError:
        return {}
    return doc if isinstance(doc, dict) else {}


def tool_result_ids(doc):
    out = []
    for message in doc.get('messages') or ():
        content = message.get('content') if isinstance(message, dict) else None
        for block in content if isinstance(content, list) else ():
            if isinstance(block, dict) and block.get('type') == 'tool_result':
                out.append((block.get('tool_use_id'), bool(block.get('is_error'))))
    return out


def parse_stream(text):
    events, bad = [], 0
    for line in (text or '').splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except ValueError:
            bad += 1
            continue
        if isinstance(event, dict):
            events.append(event)
        else:
            bad += 1
    return events, bad


def session_of(events):
    return next((e['session_id'] for e in events if isinstance(e.get('session_id'), str)), None)


def result_of(events):
    return next((e for e in reversed(events) if e.get('type') == 'result'), None)


def blocks(events, kind, role):
    out = []
    for event in events:
        message = event.get('message') if event.get('type') == role else None
        content = message.get('content') if isinstance(message, dict) else None
        out += [b for b in content if isinstance(b, dict) and b.get('type') == kind] \
            if isinstance(content, list) else []
    return out


def streamed(times, ended, gap=0.5):
    """True when the first output reached the sink at least gap seconds before the end."""
    return bool(times) and ended - min(times) >= gap


def cli_env(systemroot, ex, cli_dir, broker):
    home = ex.paths.home
    env = {'SystemRoot': systemroot, 'windir': systemroot, 'SystemDrive': ntpath.splitdrive(systemroot)[0],
           'ComSpec': ntpath.join(systemroot, 'System32', 'cmd.exe'),
           'USERPROFILE': home, 'HOME': home, 'APPDATA': os.path.join(home, 'AppData', 'Roaming'),
           'LOCALAPPDATA': os.path.join(home, 'AppData', 'Local'),
           'TEMP': ex.paths.tmp, 'TMP': ex.paths.tmp, 'CLAUDE_CONFIG_DIR': ex.paths.config,
           'PATH': cli_dir, 'DISABLE_AUTOUPDATER': '1', 'DISABLE_TELEMETRY': '1'}
    env.update(broker)
    return env


def cli_argv(exe, prompt, resume=None):
    argv = [exe, '-p', prompt, '--output-format', 'stream-json', '--verbose', '--permission-mode',
            'acceptEdits', '--allowedTools', 'Edit,Read', '--max-turns', '4', '--model', MODEL]
    return argv + (['--resume', resume] if resume else [])


def proxy_problems(raw, url):
    """The recompiled policy is the production proxy shape and nothing wider."""
    bad = []
    if raw.get('runtimeConfig') != {'networkProxy': url}:
        bad.append('proxy endpoint is not the listener')
    if raw.get('processContainer') != {'capabilities': ['internetClient']}:
        bad.append('capabilities are not exactly internetClient')
    if raw.get('network') != {'egress': {'default': 'deny'},
                              'ingress': {'default': 'allow', 'hostLoopback': 'allow'}}:
        bad.append('network is not egress deny with loopback ingress')
    if raw.get('ui') != {'disable': True, 'clipboard': 'none', 'injection': False}:
        bad.append('ui is not blocked')
    if raw.get('process', {}).get('inheritDefaultEnv') is not False:
        bad.append('default environment is inherited')
    return bad


def text_run_problems(run, hits, forbidden_new, want):
    bad = []
    events, _ = parse_stream(run.out)
    final = result_of(events)
    if run.code != 0:
        bad.append('launcher exit %s' % run.code)
    if run.ops != CLEAN:
        bad.append('ledger %s' % run.ops)
    if final is None or final.get('is_error') is not False or want not in json.dumps(final):
        bad.append('no successful result carrying the fake reply')
    if not [h for h in hits if h.method == 'POST' and h.path.split('?')[0] == '/v1/messages' and h.auth]:
        bad.append('the fake provider saw no request carrying the broker token')
    if [h for h in hits if h.method == 'CONNECT']:
        bad.append('a CONNECT reached the listener')
    if forbidden_new:
        bad.append('the forbidden listener was reached')
    return bad


def edit_run_problems(run, hits, notes_text, secret, tool_id, streamed_ok):
    bad = text_run_problems(run, hits, 0, 'EDITED-')
    events, _ = parse_stream(run.out)
    if [b for b in blocks(events, 'tool_use', 'assistant') if b.get('name') == 'Edit'] == []:
        bad.append('the stream carries no Edit tool call')
    posts = [h for h in hits if h.method == 'POST' and h.path.split('?')[0] == '/v1/messages']
    results = tool_result_ids(request_json(posts[-1].body)) if posts else []
    if (tool_id, False) not in results:
        bad.append('the second request did not carry a clean result for the tool call')
    if secret not in (notes_text or '') or 'edit me' in (notes_text or ''):
        bad.append('the file in the workspace was not edited')
    if not streamed_ok:
        bad.append('output was not delivered while the run was live')
    if session_of(events) is None:
        bad.append('the stream carries no session id')
    return bad


def import_problems(result, want, exact=False):
    if not isinstance(result, dict) or not re.fullmatch(r'[0-9a-f]{40}', str(result.get('revision'))):
        return ['no import revision']
    changes = set(result.get('files_changed') or ())
    if changes == set(want) or (not exact and set(want) <= changes):
        return []
    return ['changed set %s, wanted %s' % (sorted(changes), sorted(want))]


def stop_problems(raised, ops, members, alive, stalled):
    bad = []
    if not stalled:
        bad.append('the stop was not tried against a live request')
    if raised is None:
        bad.append('the drain was not ended by the stop')
    if ops != QUARANTINED:
        bad.append('ledger %s, wanted a quarantine with no completion' % ops)
    if members != 0 or alive:
        bad.append('the tree survived the stop (members %s, launcher alive %s)' % (members, alive))
    return bad


def hostile_files(marker_dir):
    """Planted Git state: each payload only writes a marker file named for the mechanism."""
    m = lambda name: marker_dir.replace('\\', '/') + '/fired_%s.txt' % name
    cfg = ('[core]\n\tfsmonitor = echo X > %s; exit 0\n\thooksPath = .git/hooks\n'
           '\tsshCommand = echo X > %s; exit 1\n'
           '[filter "evil"]\n\tclean = echo X > %s; cat\n\tsmudge = echo X > %s; cat\n'
           '[diff "evil"]\n\ttextconv = echo X > %s; cat\n'
           '[credential]\n\thelper = !echo X > %s\n'
           % (m('fsmonitor'), m('ssh'), m('clean'), m('smudge'), m('textconv'), m('credential')))
    hook = '#!/bin/sh\necho X > %s\nexit 0\n'
    return {'.git/config': cfg,
            '.git/hooks/pre-commit': hook % m('pre-commit'),
            '.git/hooks/post-checkout': hook % m('post-checkout'),
            '.gitattributes': '* filter=evil\n*.txt diff=evil\n',
            '.gitmodules': '[submodule "evil"]\n\tpath = evil\n\turl = %s\n' % m('nowhere')}


def markers(marker_dir):
    try:
        return sorted(n for n in os.listdir(marker_dir) if n.startswith('fired_'))
    except OSError:
        return []


def inert_problems(control_fired, core_fired, config_before, config_after):
    bad = []
    if core_fired:
        bad.append('planted Git configuration ran under Core: %s' % core_fired)
    if config_before != config_after:
        bad.append('Core changed the planted .git/config')
    return bad, bool(control_fired)


def verifier_problems(result, recorded, ops, judged, profiles):
    bad = []
    if not isinstance(result, dict) or result.get('error') is not None or result.get('exit_code') != 0:
        bad.append('verifier result error=%r exit=%r' % (
            (result or {}).get('error'), (result or {}).get('exit_code')))
    if recorded != 1:
        bad.append('the verdict was recorded %d times' % recorded)
    if ops != CLEAN:
        bad.append('ledger %s' % ops)
    if judged:
        bad.append('%s: %s' % ('containment breach' if judged[0] == 'breach' else 'control failed', judged[1]))
    profile = ((result or {}).get('confinement') or {}).get('ac_profile')
    if not profile or profile in profiles:
        bad.append('the identity was not fresh')
    return bad


def limit_problems(kind, err, ops, members, alive):
    bad = []
    if err is None or kind not in type(err).__name__ + str(err):
        bad.append('the %s limit was not enforced (%r)' % (kind, err))
    if ops != QUARANTINED:
        bad.append('ledger %s, wanted a quarantine' % ops)
    if members != 0 or alive:
        bad.append('the tree outlived the limit (members %s, launcher alive %s)' % (members, alive))
    return bad


def forged_problems(code, out, ops, recorded_outcome):
    bad = []
    if type(code) is not int or code == 0:
        bad.append('a failing workload was read as exit %r' % (code,))
    if 'FORGED-PASS' not in out:
        bad.append('the forged claim was never printed, so nothing was tested')
    if ops != CLEAN:
        bad.append('ledger %s' % ops)
    if recorded_outcome != code:
        bad.append('the journal outcome %r is not the launcher exit %r' % (recorded_outcome, code))
    return bad


class _Rec(Recorder):
    """Recorder that also appends every verdict, redacted, to the journal in the root."""
    journal = None

    def record(self, case, status, detail=''):
        try:
            super().record(case, status, detail)
        finally:
            if self.journal and status in ('PASS', 'FAIL', 'INCONCLUSIVE') and case in CASES:
                with open(self.journal, 'a', encoding='utf-8') as fh:
                    fh.write(json.dumps({'case': case, 'status': status, 'detail': redact(detail)}) + '\n')


class Capture:
    """The Core-side sink handed to Process.attach: bounded, timestamped, in memory."""

    def __init__(self, clock=time.monotonic, limit=1 << 20):
        self.clock, self.limit, self.size = clock, limit, 0
        self.parts, self.times = {'stdout': [], 'stderr': []}, []

    def __call__(self, name, data):
        self.size += len(data)
        if self.size > self.limit:
            raise OverflowError('capture bound exceeded')
        self.parts[name].append(data)
        self.times.append(self.clock())

    def text(self, name='stdout'):
        return b''.join(self.parts[name]).decode('utf-8', 'replace')


# --------------------------------------------------------------------------
# network: the script's own loopback listeners
# --------------------------------------------------------------------------

class _Handler(http.server.BaseHTTPRequestHandler):
    up = None

    def do_POST(self):
        size = int(self.headers.get('Content-Length') or 0)
        body = self.rfile.read(size) if 0 <= size <= BODY_MAX else b''
        self.up.serve(self, 'POST', self.path, body)

    def do_GET(self):
        self.up.serve(self, 'GET', self.path, b'')

    def do_CONNECT(self):
        self.up.serve(self, 'CONNECT', self.path, b'')

    def log_message(self, *args):
        pass


class Upstream:
    """The fake provider and the policy proxy endpoint in one listener. It answers a streamed
    Messages call per its mode, refuses a call without the broker token, never tunnels."""

    def __init__(self, token, pause=0.4):
        self.token, self.pause, self.mode = token, pause, {'kind': 'text', 'reply': 'OK'}
        self.hits, self.lock, self.started = [], threading.Lock(), False
        self.stalled, self.release = threading.Event(), threading.Event()
        self.server = http.server.ThreadingHTTPServer((LOOPBACK, 0), type('H', (_Handler,), {'up': self}))
        self.port = self.server.server_address[1]
        self.url = 'http://%s:%d' % (LOOPBACK, self.port)

    def start(self):
        self.started = True
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.release.set()
        if self.started:
            self.server.shutdown()
        self.server.server_close()

    def seen(self, since=0):
        with self.lock:
            return list(self.hits[since:])

    def count(self):
        with self.lock:
            return len(self.hits)

    def _auth(self, headers):
        return (headers.get('Authorization') == 'Bearer ' + self.token
                or headers.get('x-api-key') == self.token)

    def serve(self, h, method, path, body):
        auth = self._auth(h.headers)
        with self.lock:
            self.hits.append(Hit(method, path, auth, body, time.monotonic()))
        route = path.split('?', 1)[0]
        if method == 'CONNECT':
            return self._reply(h, 403, b'{}')
        if not auth:
            return self._reply(h, 401, b'{"type":"error","error":{"type":"authentication_error","message":"n4"}}')
        if method == 'POST' and route == '/v1/messages':
            return self._stream(h, self.turns(body))
        if route.endswith('/count_tokens'):
            return self._reply(h, 200, b'{"input_tokens":10}')
        return self._reply(h, 404, b'{}')

    def turns(self, body):
        mode = self.mode
        if mode['kind'] == 'stall':
            return None
        if mode['kind'] == 'edit' and not tool_result_ids(request_json(body)):
            return tool_turn(mode['tool'], 'Edit', {'file_path': mode['path'], 'old_string': mode['old'],
                                                     'new_string': mode['new']})
        return text_turn(mode['reply'])

    def _reply(self, h, code, data):
        try:
            h.send_response(code)
            h.send_header('Content-Type', 'application/json')
            h.send_header('Content-Length', str(len(data)))
            h.end_headers()
            h.wfile.write(data)
        except OSError:
            pass

    def _stream(self, h, chunks):
        try:
            h.send_response(200)
            h.send_header('Content-Type', 'text/event-stream')
            h.send_header('Cache-Control', 'no-cache')
            h.send_header('Connection', 'close')
            h.end_headers()
            if chunks is None:
                h.wfile.write(_start(MODEL, 'msg_n4s'))
                h.wfile.flush()
                self.stalled.set()
                self.release.wait(120)
                return
            for chunk in chunks:
                h.wfile.write(chunk)
                h.wfile.flush()
                time.sleep(self.pause)
        except OSError:
            pass


class Forbidden:
    """A loopback listener nothing may reach: it counts connections and closes them."""

    def __init__(self):
        self.sock = socket.socket()
        self.sock.bind((LOOPBACK, 0))
        self.sock.listen(8)
        self.sock.settimeout(1.0)
        self.port, self.hits, self.live = self.sock.getsockname()[1], 0, True

    def start(self):
        threading.Thread(target=self._accept, daemon=True).start()

    def _accept(self):
        while self.live:
            try:
                conn, _ = self.sock.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            self.hits += 1
            conn.close()

    def close(self):
        self.live = False
        self.sock.close()


def host_touch(port, probe=b''):
    """The host-side positive control: connect to a listener of ours, send the probe, drop."""
    with socket.create_connection((LOOPBACK, port), 5) as conn:
        if probe:
            conn.sendall(probe)
            conn.recv(256)


# --------------------------------------------------------------------------
# Native part: only reached from main(); every Windows call is below this line
# --------------------------------------------------------------------------

class _NoOutput:
    """`fast-import --quiet` answers nothing on stdout; anything there refuses."""

    def feed(self, chunk):
        raise OSError('fast-import wrote to stdout')

    def end(self):
        pass

    def abort(self):
        pass


class Harness:
    def __init__(self, root, sdk_src, cli_src, systemroot, budget):
        self.lay, self.budget, self.sr = layout(root), budget, systemroot
        self.cmd = ntpath.join(systemroot, 'System32', 'cmd.exe')
        self.curl = ntpath.join(systemroot, 'System32', 'curl.exe')
        self.env = {'SYSTEMROOT': systemroot, 'LOCALAPPDATA': self.lay['localappdata']}
        self.sdk_src, self.cli_src, self.jobs, self.seq = sdk_src, cli_src, [], 0
        self.m = self.up = self.fb = self.project = self.seed_commit = None
        self.secret, self.seeds = None, {}

    def prepare(self):
        lay = self.lay
        make_dirs(lay)
        mods = n2.import_isolated(PROD, lay['envhome'])
        pin_environment(os.environ, lay)
        self.m = m = SimpleNamespace(**{n.rsplit('.', 1)[1]: mods[n] for n in PROD})
        # ponytail: pins come from the staged copy because no reviewed hash inventory is supplied.
        self.pins = m.staging._mxc_inventory(self.sdk_src)
        m.staging.stage_mxc(self.sdk_src, lay['sdk'], pins=self.pins)
        shutil.copytree(self.cli_src, lay['cli'], symlinks=True)
        m.staging.scan_grants((lay['cli'],))
        self.cli_exe = os.path.join(lay['cli'], 'claude.exe')
        self.api = n2._counting_api(m.win32_mxc)(lay['private'])
        self.api.reset()
        self.boundary = m.isolation.WindowsBoundary()
        self.ledger = m.mxc_ledger.Ledger(lay['ledger'])
        m.mxc.NATIVE_RUN_ENABLED = True
        self.node = m.local.LocalNode()
        self.mxcb = m.mxc_boundary.MxcBoundary(
            win32=self.api, ledger=self.ledger, sdk_root=lay['sdk'], pins=self.pins,
            schema_validator=lambda raw: True, timeout_ms=60000, resource_reader=self.reader,
            process_reader=n2.live_ctime, env_rows={'SYSTEMROOT': self.sr, 'LOCALAPPDATA': lay['localappdata']})
        self.node.isolation = m.isolation.Isolation(self.node, boundary=self.mxcb)
        self.token = 'brk_' + n2.new_token()
        self.up = Upstream(self.token)
        self.fb = Forbidden()
        self.up.start()
        self.fb.start()
        self.secret = n2.new_token()
        with open(os.path.join(lay['toolchain'], 'runner.txt'), 'x', encoding='utf-8') as fh:
            fh.write(self.secret)
        for label, folder, name in (('home', lay['home'], 'core_secret.txt'), ('ledger', lay['ledger'], 'seed.txt'),
                                    ('isolation', m.paths.isolation_dir(), 'seed.txt')):
            os.makedirs(folder, exist_ok=True)
            self.seeds[label] = n2.new_token()
            with open(os.path.join(folder, name), 'x', encoding='utf-8') as fh:
                fh.write(self.seeds[label])

    def broker(self):
        return self.m.base.BrokerLaunch(self.up.port, self.token).env()

    def reader(self, execution_id, owner):
        """Proves one thing: the launcher this execution owned is gone (pid and creation time)."""
        return True if n2.live_ctime(owner['pid']) != owner['create_time'] else [execution_id]

    # ---- one production launch ----

    def eid(self, tag):
        self.seq += 1
        return 'n4_%02d_%s' % (self.seq, tag)

    def make(self, tag, argv, rw, ro, *, reader=True, ledger=None, boundary=None, env=None,
             timeout_ms=60000, eid=None, seq=1, proxy=None, seed=None, transport=None):
        self.budget.check()
        eid = eid or self.eid(tag)
        text = n2.command_line(argv)
        kw = dict(api=self.api, boundary=boundary or self.boundary, ledger=ledger or self.ledger,
                  schema_validator=lambda raw: True, execution_id=eid, sdk_root=self.lay['sdk'],
                  pins=self.pins, outcome=lambda process: process.launcher_exit, workspace=rw[-1],
                  writable=tuple(rw[:-1]), readonly=tuple(ro), cwd=rw[-1], command_line=text,
                  env=dict(self.env if env is None else env), timeout_ms=timeout_ms,
                  resource_reader=self.reader if reader else None, quiescence_wait=QUIESCE_S,
                  process_seq=seq, transport=transport)
        if seed is not None:
            kw.update(seed_stage=seed[0], seed_recheck=seed[1])
        launch = self.m.local.MxcLaunch(**kw)
        if proxy is not None:
            launch.policy = self.m.mxc.compile_policy(
                workspace=(rw[-1],) + tuple(rw[:-1]), readonly=tuple(ro), cwd=rw[-1],
                command_line=text, env=dict(kw['env']), timeout_ms=timeout_ms, proxy_url=proxy)
            launch._digest = None
        return eid, launch

    def job(self, eid, boundary=None):
        ref = n2.JobRef(self.boundary, (boundary or self.boundary).create_job(eid))
        self.jobs.append(ref)
        return ref

    def go(self, tag, argv, rw, ro, *, sink=None, cancelled=None, wait_s=None, seq=1, **kw):
        eid, launch = self.make(tag, argv, rw, ro, seq=seq, **kw)
        job = self.job(eid)
        launch.start(job=job.handle)
        if sink is not None:
            launch.process.attach(sink=sink)
        code = launch.wait(wait_s, cancelled=cancelled)
        ended = time.monotonic()
        out = launch.stdout.read().decode('utf-8', 'replace')
        err = launch.stderr.read().decode('utf-8', 'replace')
        return SimpleNamespace(eid=eid, launch=launch, job=job, code=code, out=out, err=err,
                               ended=ended, ops=self.ops(eid, seq))

    def ops(self, eid, seq=1):
        name = self.m.mxc_ledger.journal_name(eid, seq)
        return n2.journal_ops(self.m.mxc_ledger.read_records, self.ledger, name)[0]

    def journal_outcome(self, eid, seq=1):
        name = self.m.mxc_ledger.journal_name(eid, seq)
        records, _ = self.m.mxc_ledger.read_records(self.ledger.journals().get(name, b''), name)
        return next((r.get('outcome') for r in records if r['op'] == 'completion'), None)

    def job_count(self, job):
        return self.boundary.job_active_processes(job.handle)

    def wait_job(self, job, want, seconds):
        end = time.monotonic() + seconds
        while True:
            n = self.job_count(job)
            if want(n) or time.monotonic() >= end:
                return n
            time.sleep(0.2)

    def wait_dead(self, pid, ctime, seconds):
        end = time.monotonic() + seconds
        while n2.live_ctime(pid) == ctime:
            if time.monotonic() >= end:
                return False
            time.sleep(0.2)
        return True

    # ---- the Core store and the executions it seeds ----

    def make_seed_commit(self):
        local = self.m.local.LocalNode
        self.project = self.m.ids.new_id('project')
        store = local.store_open(self.project, workdirs=())
        local.store_git('import', ['fast-import', '--done', '--quiet'], workdirs=(), git_dir=store,
                        stdin=fast_import_stream(SEED_REF, seed_files(self.secret)), sink=_NoOutput())
        self.seed_commit = local.store_read(self.project, ['rev-parse', SEED_REF], workdirs=()).strip()
        return self.seed_commit

    def seeded(self):
        local = self.m.local.LocalNode
        eid = self.m.ids.new_id('execution')
        local.store_seed_ref(self.project, eid, self.seed_commit, workdirs=())
        work = local.seed_workspace(self.project, eid, self.seed_commit, 'archeus/n4', workdirs=())
        paths = self.m.paths.ExecPaths(eid)
        for d in (paths.state, paths.config, paths.tmp, os.path.join(paths.home, 'AppData', 'Roaming'),
                  os.path.join(paths.home, 'AppData', 'Local')):
            os.makedirs(d, exist_ok=True)
        return SimpleNamespace(eid=eid, paths=paths, work=work)

    def wind_down(self):
        """Close every Job (the kill), stop the listeners, check no launcher this script made lives."""
        for ref in self.jobs:
            ref.close()
        for listener in (self.up, self.fb):
            if listener is not None:
                listener.close()
        if self.m is not None:
            self.m.mxc.NATIVE_RUN_ENABLED = False
        left = 0
        for pid, ctime in list(getattr(getattr(self, 'api', None), 'created', None) or ()):
            if not self.wait_dead(pid, ctime, 5.0):
                left += 1
                if n2.live_ctime(pid) == ctime:
                    n2.common._terminate_process(pid)
        return left


def fail(rec, case, text):
    rec.record(case, 'FAIL', text)


def exec_grants(ex):
    p = ex.paths
    return (p.state, ex.work), ()


def chain_run(h, rec, case, tag, items, rw, ro, **kw):
    """One production launch running the items as a chain, judged host-side; returns the run."""
    items = list(items) + [n2.done_item(rw[-1])]
    run = h.go(tag, n2.cmd_argv(h.cmd, n2.chain_of(items)), rw, ro, **kw)
    bad = n2.judge(items, n2.look_at)
    if bad:
        what = 'CONTAINMENT BREACH' if bad[0] == 'breach' else 'control did not hold'
        fail(rec, case, '%s (%s: %s); launcher rc=%s %s' % (what, tag, bad[1], run.code, n2._tail(run.out + run.err)))
    if run.ops != CLEAN:
        fail(rec, case, '%s: the production end was not clean, ledger %s' % (tag, run.ops))
    return run


def canary(h, rec, case, tag):
    work = os.path.join(h.lay['faults'], 'canary_' + tag)
    os.makedirs(work)
    items = [n2.w_ok('inside', os.path.join(work, 'ctl_%s.txt' % tag)),
             n2.w_no('outside', os.path.join(h.lay['outside'], 'breach_%s.txt' % tag))]
    chain_run(h, rec, case, 'canary_' + tag, items, (work,), (h.lay['toolchain'],))
    rec.record(case, 'PASS', 'canary %s: inside write present, outside write absent' % tag)


def step_seed(h, rec):
    case, lay = 'copy-only-seed', h.lay
    try:
        commit = h.make_seed_commit()
        ex = h.seeded()
    except Exception as err:
        fail(rec, case, 'the production seed raised %s: %s' % (type(err).__name__, n2._snip(str(err))))
    bad = tree_problems(walk_plain(ex.work), ex.work, seed_files(h.secret), h.m.local.SEED_CONFIG)
    if bad:
        fail(rec, case, 'seeded workspace: ' + '; '.join(bad[:6]))
    try:
        h.m.local.LocalNode.seed_workspace(h.project, ex.eid, commit, 'archeus/n4', workdirs=())
    except Exception as err:
        again = type(err).__name__
    else:
        again = None
    if again is None:
        fail(rec, case, 'a second seed of the same execution was accepted')
    rec.record(case, 'PASS', 'seed of %s built by Core from the store: exactly the tree, no alias, no second name, '
               '.git is the config Core wrote, a second seed refused (%s)' % (commit[:12], again))
    ws, tree = lay['seedws'], os.path.join(lay['seedws'], 'tree')
    files = {}
    for name in ('a.txt', 'b.txt'):
        with open(os.path.join(lay['src'], name), 'x', encoding='utf-8') as fh:
            fh.write(h.secret)
        files[name] = os.path.join(lay['src'], name)
    stage = lambda: h.m.staging.seed_execution(files, tree)
    recheck = lambda: h.m.staging.recheck_execution(tree)
    items = [n2.r_ok('seeded-read', os.path.join(tree, 'a.txt'), os.path.join(ws, 'e_seed.txt'), h.secret),
             n2.w_ok('seeded-write', os.path.join(tree, 'w.txt')),
             n2.r_no('source-read', os.path.join(lay['src'], 'a.txt'), os.path.join(ws, 'e_src.txt'), h.secret),
             n2.w_no('source-write', os.path.join(lay['src'], 'w.txt'))]
    chain_run(h, rec, case, 'seed', items, (ws,), (h.lay['toolchain'],), seed=(stage, recheck))
    rec.record(case, 'PASS', 'a launch seeded through the production seam: the container read the copy, never the source')
    planted = os.path.join(lay['faults'], 'seed_recheck')
    os.makedirs(planted)
    marker = os.path.join(lay['outside'], 'spawned_recheck.txt')
    victim = os.path.join(lay['src'], 'b.txt')
    tree2 = os.path.join(planted, 'tree')

    def plant_then_recheck():
        os.link(victim, os.path.join(tree2, 'alias'))
        h.m.staging.recheck_execution(tree2)

    h.api.reset()
    first = len(h.api.created)
    eid, launch = h.make('recheck', n2.cmd_argv(h.cmd, 'echo X>%s' % marker), (planted,), (h.lay['toolchain'],),
                         seed=(lambda: h.m.staging.seed_execution({'b.txt': victim}, tree2), plant_then_recheck))
    job = h.job(eid)
    try:
        launch.start(job=job.handle)
    except Exception as err:
        raised = type(err).__name__
    else:
        raised = None
    time.sleep(3.0)
    ops = h.ops(eid)
    members = h.wait_job(job, lambda c: c == 0, QUIESCE_S)
    alive = [pid for pid, ct in h.api.created[first:] if n2.live_ctime(pid) == ct]
    if (raised is None or h.api.resumes != 0 or n2.look_at(marker) is not None or ops != QUARANTINED
            or members != 0 or alive):
        fail(rec, case, 'a second name planted before the resume: raised=%s ResumeThread=%d marker=%s ledger=%s '
             'job_members=%s alive=%d' % (raised, h.api.resumes, n2.look_at(marker) is not None, ops, members, len(alive)))
    os.unlink(os.path.join(tree2, 'alias'))
    rec.record(case, 'PASS', 'a second name planted between ownership and resume: refused (%s), never resumed, '
               'ledger %s' % (raised, '>'.join(ops)))


def new_run(h, ex, tag, argv, proxy, env, wait_s=120, **kw):
    rw, ro = exec_grants(ex)[0], (h.lay['cli'],)
    return h.go(tag, argv, rw, ro, env=env, proxy=proxy, wait_s=wait_s, timeout_ms=150000, **kw)


def step_cli(h, rec):
    case, up, fb = 'real-cli-fake-broker', h.up, h.fb
    ex = h.seeded()
    rw, ro = exec_grants(ex)[0], (h.lay['cli'],)
    env = cli_env(h.sr, ex, h.lay['cli'], h.broker())
    try:
        host_touch(up.port, b'GET /hostctl HTTP/1.0\r\n\r\n')
        host_touch(fb.port)
    except OSError as err:
        fail(rec, case, 'host control: a script listener did not answer (%s)' % type(err).__name__)
    time.sleep(0.3)
    if not up.count() or not fb.hits:
        fail(rec, case, 'host control: a listener did not log the host touch')
    base_hits, base_fb = up.count(), fb.hits
    canary(h, rec, case, 'cli_pre')
    version = h.go('version', [h.cli_exe, '--version'], rw, ro, env=env, timeout_ms=60000, wait_s=60)
    if version.code != 0 or not re.search(r'\d+\.\d+\.\d+', version.out) or version.ops != CLEAN:
        fail(rec, case, 'the staged CLI did not run under the production policy: rc=%s ledger=%s %s'
             % (version.code, version.ops, n2._tail(version.out + version.err)))
    want = 'N4-%s' % h.secret
    up.mode = {'kind': 'text', 'reply': want}
    mark = up.count()
    cap = Capture()
    run = new_run(h, ex, 'cli_text', cli_argv(h.cli_exe, 'Reply with the fake text.'), up.url, env, sink=cap)
    run.out = cap.text()
    bad = proxy_problems(run.launch.policy.raw, up.url)
    bad += text_run_problems(run, up.seen(mark), fb.hits - base_fb, want)
    if bad:
        fail(rec, case, 'the real CLI against the fake broker: %s; launcher rc=%s %s'
             % ('; '.join(bad), run.code, n2._tail(cap.text('stderr') + run.err)))
    canary(h, rec, case, 'cli_post')
    rec.record(case, 'PASS', 'staged claude.exe ran under the production proxy policy and reached only the fake '
               'provider with the broker token; %d request(s), forbidden listener untouched, ledger %s'
               % (len(up.seen(base_hits)), '>'.join(run.ops)))


def step_stream(h, rec):
    case, up = 'stream-edit-commit-stop-resume', h.up
    local = h.m.local.LocalNode
    ex = h.seeded()
    env = cli_env(h.sr, ex, h.lay['cli'], h.broker())
    notes = os.path.join(ex.work, 'notes.txt')
    new = 'edited %s' % h.secret
    tool = 'toolu_n4edit'
    up.mode = {'kind': 'edit', 'tool': tool, 'path': notes, 'old': 'edit me %s' % h.secret,
               'new': new, 'reply': 'EDITED-%s' % h.secret}
    mark, cap = up.count(), Capture()
    run = new_run(h, ex, 'edit', cli_argv(h.cli_exe, 'Edit notes.txt as scripted.'), up.url, env, sink=cap, seq=1,
                  eid=ex.eid)
    run.out = cap.text()
    hits = up.seen(mark)
    bad = edit_run_problems(run, hits, n2.read_text(notes), h.secret, tool, streamed(cap.times, run.ended))
    if bad:
        fail(rec, case, 'stream and edit: %s; launcher rc=%s %s' % ('; '.join(bad), run.code, n2._tail(cap.text('stderr') + run.err)))
    rec.record(case, 'PASS', 'output reached the Core sink while the run was live (%d chunks), the Edit tool call '
               'changed notes.txt and its clean result went back to the provider' % len(cap.times))
    sid = session_of(parse_stream(run.out)[0])
    try:
        result = local.import_workspace(h.project, ex.eid, h.seed_commit, workdirs=())
    except Exception as err:
        fail(rec, case, 'the Core import of the edited workspace raised %s: %s' % (type(err).__name__, n2._snip(str(err))))
    bad = import_problems(result, ['M notes.txt'])
    if bad:
        fail(rec, case, 'commit: ' + '; '.join(bad))
    rec.record(case, 'PASS', 'commit: Core imported the edit as one commit on the seed (%s), changed set %s'
               % (result['revision'][:12], result['files_changed']))
    try:
        h.mxcb.create_profile(ex.eid)
    except Exception as err:
        fail(rec, case, 'a resume after a completed generation was refused: %s' % n2._snip(str(err)))
    up.mode = {'kind': 'text', 'reply': 'RESUMED-%s' % h.secret}
    mark, cap = up.count(), Capture()
    run2 = new_run(h, ex, 'resume', cli_argv(h.cli_exe, 'Continue.', resume=sid), up.url, env, sink=cap, seq=2, eid=ex.eid)
    run2.out = cap.text()
    history = [x for x in up.seen(mark) if x.method == 'POST' and ('EDITED-%s' % h.secret).encode() in x.body]
    bad = text_run_problems(run2, up.seen(mark), 0, 'RESUMED-%s' % h.secret)
    if bad or not history or run2.ops != CLEAN:
        fail(rec, case, 'resume as generation 2: %s history_carried=%s ledger=%s; launcher rc=%s %s'
             % ('; '.join(bad) or 'ok', bool(history), run2.ops, run2.code, n2._tail(cap.text('stderr') + run2.err)))
    rec.record(case, 'PASS', 'resume: generation 2 of the same execution ran after the clean generation 1 and '
               'carried its conversation (journals -p1 and -p2 clean)')
    ex2 = h.seeded()
    env2 = cli_env(h.sr, ex2, h.lay['cli'], h.broker())
    up.mode = {'kind': 'stall'}
    up.stalled.clear()
    eid, launch = h.make('stop', cli_argv(h.cli_exe, 'Hang.'), exec_grants(ex2)[0], (h.lay['cli'],), env=env2,
                         proxy=up.url, timeout_ms=150000, eid=ex2.eid)
    job = h.job(eid)
    launch.start(job=job.handle)
    pid, ctime = launch.process.pid, launch.process.create_time
    open(ex2.paths.prompt, 'xb').close()
    child = h.m.mxc_context.MxcChild(launch, ex2.paths)
    child.start()
    stalled = up.stalled.wait(60)
    end = child.cancel('stopped')
    raised = type(child.fault).__name__ if child.fault is not None else None
    members = h.wait_job(job, lambda c: c == 0, QUIESCE_S)
    bad = stop_problems(raised, h.ops(eid), members, n2.live_ctime(pid) == ctime, stalled)
    if (end or {}).get('reason') != 'stopped' or child.reason != 'stopped' or child.poll() != 1:
        bad.append('the stop reason was not carried to the end: end=%r child=%r exit=%r'
                   % ((end or {}).get('reason'), child.reason, child.poll()))
    up.release.set()
    if bad:
        fail(rec, case, 'stop: ' + '; '.join(bad))
    try:
        h.mxcb.create_profile(ex2.eid)
    except Exception as err:
        refused = getattr(err, 'reason', type(err).__name__)
    else:
        refused = None
    if refused != 'generation_unresolved':
        fail(rec, case, 'a resume after a stopped generation was not refused as unresolved (%r)' % (refused,))
    rec.record(case, 'PASS', 'stop: the live request was ended by Core own MxcChild.cancel, reason carried to the end, '
               'Job empty, launcher gone, quarantined with no completion; the production boundary then refuses a '
               'resume (%s)' % refused)


def step_import(h, rec):
    case, lay, local = 'data-only-import', h.lay, h.m.local.LocalNode
    ex = h.seeded()
    work, j = ex.work, os.path.join
    items = [n2.w_ok('edit', j(work, 'notes.txt')), n2.w_ok('add', j(work, 'new_file.txt')),
             n2.Item('dir_no', 'delete', 'del /q %s' % j(work, 'src', 'app.txt'), j(work, 'src', 'app.txt'), None),
             n2.w_ok('git-writable', j(work, '.git', 'agent_marker.txt'))]
    chain_run(h, rec, case, 'agent_edit', items, exec_grants(ex)[0], (lay['toolchain'],))
    try:
        result = local.import_workspace(h.project, ex.eid, h.seed_commit, workdirs=())
    except Exception as err:
        fail(rec, case, 'the Core import raised %s: %s' % (type(err).__name__, n2._snip(str(err))))
    bad = import_problems(result, ['M notes.txt', 'A new_file.txt', 'A done.txt', 'D src/app.txt'], exact=True)
    if bad:
        fail(rec, case, 'import: ' + '; '.join(bad))
    try:
        local.import_workspace(h.project, ex.eid, h.seed_commit, workdirs=())
    except Exception as err:
        again = type(err).__name__
    else:
        again = None
    if again is None:
        fail(rec, case, 'a second import of the same execution was accepted')
    rec.record(case, 'PASS', 'a container edit, add and delete came back as one commit (%s) with exactly that changed set, '
               'nothing from .git; a second import refused (%s)' % (result['revision'][:12], again))
    ex = h.seeded()
    link = j(ex.work, 'evil')
    n2._junction(h, link, lay['outside'])
    secret_file = j(lay['outside'], 'known.txt')
    with open(secret_file, 'x', encoding='utf-8') as fh:
        fh.write(h.secret)
    try:
        try:
            res = local.import_workspace(h.project, ex.eid, h.seed_commit, workdirs=())
            names = local.store_read(h.project, ['ls-tree', '-r', '--name-only', res['revision']], workdirs=())
            outcome = 'imported without the junction target' if 'known.txt' not in names else None
        except Exception as err:
            outcome = 'refused (%s)' % type(err).__name__
    finally:
        n2._unjunction(link)
    if outcome is None:
        fail(rec, case, 'a junction in the workspace was followed into the import')
    rec.record(case, 'PASS', 'a junction planted in the workspace: %s, never followed' % outcome)


def naive_git(h, work):
    """The labelled control: a plain Git, no pin, run in a throwaway fixture workspace."""
    git = shutil.which('git')
    if not git or not os.path.isabs(git):
        return 'no absolute git on PATH'
    env = {'SYSTEMROOT': h.sr, 'PATH': os.path.dirname(git), 'HOME': h.lay['envhome'],
           'GIT_CONFIG_NOSYSTEM': '1', 'GIT_TERMINAL_PROMPT': '0'}
    last = ''
    for args in (['status'], ['add', '-A'], ['-c', 'user.name=n4', '-c', 'user.email=n4@invalid', 'commit', '-m', 'x']):
        try:
            r = subprocess.run([git] + args, cwd=work, env=env, capture_output=True, timeout=60)
        except (OSError, subprocess.TimeoutExpired) as err:
            last = type(err).__name__
            continue
        last = 'rc=%d' % r.returncode
    return last


def plant(work, files):
    for rel, text in files.items():
        path = os.path.join(work, *rel.split('/'))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8', newline='\n') as fh:
            fh.write(text)


def step_hostile(h, rec):
    case, lay, local = 'hostile-git-inert-controls', h.lay, h.m.local.LocalNode
    naive_dir, core_dir = os.path.join(lay['ctl'], 'naive'), os.path.join(lay['ctl'], 'core')
    os.makedirs(naive_dir)
    os.makedirs(core_dir)
    control = h.seeded()
    plant(control.work, hostile_files(naive_dir))
    last = naive_git(h, control.work)
    victim = h.seeded()
    plant(victim.work, hostile_files(core_dir))
    cfg = os.path.join(victim.work, '.git', 'config')
    before = n2.read_text(cfg)
    try:
        res = local.import_workspace(h.project, victim.eid, h.seed_commit, workdirs=())
        local.store_read(h.project, ['ls-tree', '-r', res['revision']], workdirs=())
        how = 'imported as data'
    except Exception as err:
        how = 'refused (%s)' % type(err).__name__
    bad, armed = inert_problems(markers(naive_dir), markers(core_dir), before, n2.read_text(cfg))
    if bad:
        fail(rec, case, '; '.join(bad))
    if not armed:
        rec.record(case, 'INCONCLUSIVE', 'the control did not fire (naive git %s): the planted configuration is not '
                   'shown to be live, so Core staying quiet proves nothing; Core: %s' % (last, how))
        return
    rec.record(case, 'PASS', 'control fired %s under a plain Git (%s); under Core (%s) no marker, .git/config unchanged'
               % (markers(naive_dir), last, how))


def seeded_items(h, ex, others, who):
    """Chain items for a probe holding ex: its own grants work, every other directory is denied."""
    j, lay, p = os.path.join, h.lay, ex.paths
    ev = lambda n: j(ex.work, 'e_%s.txt' % n)
    items = [n2.w_ok('work-write', j(ex.work, 'w.txt')), n2.w_ok('state-write', j(p.state, 'w.txt')),
             n2.r_ok('state-read', j(p.state, 'seed.txt'), ev('state'), h.seeds[who + '.state'])]
    deny = [('own-prompt', j(p.dir, 'prompt.txt'), h.seeds[who + '.prompt']),
            ('own-pid', j(p.dir, 'pid.json'), h.seeds[who + '.pid']),
            ('home', j(lay['home'], 'core_secret.txt'), h.seeds['home']),
            ('isolation', j(h.m.paths.isolation_dir(), 'seed.txt'), h.seeds['isolation']),
            ('ledger', j(lay['ledger'], 'seed.txt'), h.seeds['ledger'])]
    for other in others:
        deny += [('peer-work', j(other.work, 'seed.txt'), h.seeds[other.label + '.work']),
                 ('peer-state', j(other.paths.state, 'seed.txt'), h.seeds[other.label + '.state'])]
    for label, path, secret in deny:
        items += [n2.r_no(label + '-read', path, ev(label), secret),
                  n2.w_no(label + '-write', j(os.path.dirname(path), 'w_%s.txt' % label))]
    return items


def curl_argv(h, url):
    return [h.curl, '-s', '-m', '6', '--noproxy', '*', '-w', 'CODE:%{http_code}', url]


def step_authority(h, rec):
    case, lay, up, fb, j = 'authority-peer-network-denials', h.lay, h.up, h.fb, os.path.join
    group = {}
    for label in ('p', 'q'):
        ex = h.seeded()
        ex.label = label
        group[label] = ex
        for key, path in (('state', ex.paths.state), ('work', ex.work)):
            h.seeds[label + '.' + key] = n2.new_token()
            with open(j(path, 'seed.txt'), 'x', encoding='utf-8') as fh:
                fh.write(h.seeds[label + '.' + key])
        for key, name in (('prompt', 'prompt.txt'), ('pid', 'pid.json')):
            h.seeds[label + '.' + key] = n2.new_token()
            with open(j(ex.paths.dir, name), 'x', encoding='utf-8') as fh:
                fh.write(h.seeds[label + '.' + key])
    p, q = group['p'], group['q']
    live = n2._start_loop(h, 'live_peer', (p.work,), ())
    members = live[3]
    chain_run(h, rec, case, 'q_probes_live_p', seeded_items(h, q, [p], 'q'), exec_grants(q)[0], ())
    still = h.job_count(live[2])
    live[1].cancel(reason='probe done')
    if still < 1:
        fail(rec, case, 'the peer was not alive during the probe (Job members %s)' % still)
    chain_run(h, rec, case, 'p_probes_q', seeded_items(h, p, [q], 'p'), exec_grants(p)[0], ())
    rec.record(case, 'PASS', 'authority and peer: a container holding its own execution folders could not read or write '
               'Core files, the Core home, the ledger or a peer (live for one direction, %d processes), both directions, '
               'each with same-chain controls' % members)
    ex = group['p']
    base_up, base_fb = up.count(), fb.hits
    d1 = h.go('deny_up', curl_argv(h, up.url + '/deny'), (ex.work,), ())
    d2 = h.go('deny_fb', curl_argv(h, 'http://%s:%d/deny' % (LOOPBACK, fb.port)), (ex.work,), ())
    if (up.count(), fb.hits) != (base_up, base_fb):
        fail(rec, case, 'CONTAINMENT BREACH: a deny-all container reached a listener')
    for run in (d1, d2):
        if run.code != 7 or 'CODE:000' not in run.out:
            fail(rec, case, 'deny-all baseline: curl rc=%s %s' % (run.code, n2._tail(run.out + run.err)))
    mark = up.count()
    r1 = h.go('via_up', curl_argv(h, up.url + '/ctl'), (ex.work,), (), proxy=up.url)
    seen = up.seen(mark)
    if r1.code != 0 or not seen or 'CODE:401' not in r1.out:
        fail(rec, case, 'positive control: the container did not reach the allowed endpoint (rc=%s hits=%d %s)'
             % (r1.code, len(seen), n2._tail(r1.out + r1.err)))
    r2 = h.go('via_fb', curl_argv(h, 'http://%s:%d/x' % (LOOPBACK, fb.port)), (ex.work,), (), proxy=up.url)
    tunnel = [x for x in up.seen() if x.method == 'CONNECT' or ':%d' % fb.port in x.path]
    if fb.hits != base_fb or r2.code != 7 or tunnel:
        fail(rec, case, 'under the proxy policy a direct connect to the forbidden listener: rc=%s hits=%d tunnel=%d'
             % (r2.code, fb.hits - base_fb, len(tunnel)))
    rec.record(case, 'PASS', 'network: deny-all blocked both listeners (rc 7, zero hits); under the proxy policy the '
               'allowed endpoint answered and the forbidden listener stayed unreachable (rc 7, zero hits, no tunnel)')


def step_limits(h, rec):
    case, lay, j = 'limits-forged-results', h.lay, os.path.join
    work = j(lay['faults'], 'limits')
    os.makedirs(work)
    ro = (lay['toolchain'],)
    flood = [h.cmd, '/d', '/c', 'for', '/l', '%i', 'in', '(1,1,400000)', 'do', '@echo', 'N' * 64]

    def attempt(tag, argv, wait_s, **kw):
        eid, launch = h.make(tag, argv, (work,), ro, **kw)
        job = h.job(eid)
        launch.start(job=job.handle)
        pid, ctime = launch.process.pid, launch.process.create_time
        try:
            launch.wait(wait_s)
        except Exception as err:
            raised = err
        else:
            raised = None
        return eid, job, raised, h.wait_job(job, lambda c: c == 0, QUIESCE_S), n2.live_ctime(pid) == ctime

    eid, job, err, members, alive = attempt('flood', flood, 60, transport={'output_limit': 1 << 16})
    bad = limit_problems('bound', err, h.ops(eid), members, alive)
    if bad:
        fail(rec, case, 'output bound: ' + '; '.join(bad))
    eid, job, err, members, alive = attempt('deadline', n2.loop_argv(h), 6, timeout_ms=120000)
    bad = limit_problems('deadline', err, h.ops(eid), members, alive)
    if bad:
        fail(rec, case, 'launcher deadline: ' + '; '.join(bad))
    start = time.monotonic()
    try:
        quick = h.go('policy_timeout', n2.loop_argv(h), (work,), ro, timeout_ms=5000, wait_s=60)
    except Exception as err:
        fail(rec, case, 'policy timeout: the launch raised %s: %s' % (type(err).__name__, n2._snip(str(err))))
    took = time.monotonic() - start
    members = h.wait_job(quick.job, lambda c: c == 0, QUIESCE_S)
    if took > 40 or members != 0:
        fail(rec, case, 'policy timeout: took %.0f s, launcher rc=%s, Job members %s' % (took, quick.code, members))
    rec.record(case, 'PASS', 'limits: output past the bound ended the launch and quarantined it; a launcher past its '
               'deadline likewise; a policy timeout of 5 s ended the tree by itself after %.0f s (rc %s)' % (took, quick.code))
    items = [n2.w_ok('control', j(work, 'f_ctl.txt')),
             n2.w_no('forge-journal', j(lay['ledger'], 'n4_forged-p1.jsonl')),
             n2.w_no('forge-policy', j(lay['private'], 'forged.json'))]
    items.append(n2.done_item(work))
    chain = n2.chain_of(items) + ' & echo FORGED-PASS-%s & exit /b 3' % h.secret
    run = h.go('forged', n2.cmd_argv(h.cmd, chain), (work,), ro)
    bad = n2.judge(items, n2.look_at)
    if bad:
        fail(rec, case, 'forged: %s (%s)' % (bad[0], bad[1]))
    bad = forged_problems(run.code, run.out, run.ops, h.journal_outcome(run.eid))
    if bad:
        fail(rec, case, 'forged result: ' + '; '.join(bad))
    rec.record(case, 'PASS', 'forged results: a workload that printed a pass and exited %s was recorded as that exit; '
               'writes of a forged journal or policy file were denied' % run.code)


STUBS = (
    ('copy-only-seed',
     'stand-in: hash pins computed from the staged copy and a schema validator that returns True; the seed and '
     'recheck seam is driven by the script, not by a dispatcher (B8)'),
    ('real-cli-fake-broker',
     'stand-in: the listener is the script own fake, not the production Core broker (B10); MxcLaunch compiles '
     'proxy_url=None, so the script recompiles the policy with the production compiler; UI stays disabled (OD-1 not '
     'decided); identity-scoped allowedProxyPeer is not tested'),
    ('stream-edit-commit-stop-resume',
     'stand-in: output is read through Process.attach by the script, not by the manager; the stop is Core own '
     'MxcChild.cancel, not the manager STOP flag; the commit is the Core import (K3); in-container git and the '
     'hook interpreter are N4a'),
    ('data-only-import',
     'stand-in: the container wrote plain data; hostile creator descriptors, symlink creation and handle transfer '
     'are not driven (as in F2 and N1)'),
    ('hostile-git-inert-controls',
     'stand-in: the hostile Git state is planted by the script, a container never authors it here'),
    ('two-fresh-verifiers',
     'missing contract: no toolchain stage exists, so the toolchain is a script folder'),
    ('authority-peer-network-denials',
     'missing contract: IPv6, descendant network rows and the identity-scoped proxy peer are not made real here '
     '(still the N3 stubs)'),
    ('limits-forged-results',
     'missing contract: no workload-result framing, so the outcome is the launcher exit (OD-2a)'),
    (LIVE_CASE,
     'not run: a live provider needs its own authorization and account, none is used here'),
)


def stubs(rec):
    for case, why in STUBS:
        rec.record(case, 'INCONCLUSIVE', why)


def step_verifiers(h, rec):
    case, lay, j = 'two-fresh-verifiers', h.lay, os.path.join
    ids, paths, iso = h.m.ids, h.m.paths, h.m.isolation
    recorded, runs, profiles, kept = [], [], set(), {}
    spawned = h.api.creates
    plan = [(ids.new_id('verification'), 0), (ids.new_id('verification'), 0)]
    plan.append((plan[0][0], 1))
    for vid, attempt in plan:
        vp = paths.VerifyPaths(vid, attempt)
        scratch = os.path.dirname(vp.checkout)
        ev = lambda n, s=scratch: j(s, 'e_%s.txt' % n)
        items = [n2.r_ok('own-checkout', j(vp.checkout, 'notes.txt'), ev('own'), 'edit me %s' % h.secret),
                 n2.w_ok('checkout-write', j(vp.checkout, 'w.txt')), n2.w_ok('scratch-write', j(scratch, 'w.txt')),
                 n2.r_ok('toolchain-read', j(lay['toolchain'], 'runner.txt'), ev('tool'), h.secret),
                 n2.w_no('toolchain-write', j(lay['toolchain'], 'w.txt')),
                 n2.r_no('home-read', j(lay['home'], 'core_secret.txt'), ev('home'), h.seeds['home']),
                 n2.r_no('ledger-read', j(lay['ledger'], 'seed.txt'), ev('ledger'), h.seeds['ledger']),
                 n2.Item('dir_no', 'no-git', '(if exist %s md %s)' % (j(vp.checkout, '.git'), j(scratch, 'has_git')),
                         j(scratch, 'has_git'), None)]
        for (ovid, oatt), (oscratch, otoken) in kept.items():
            items += [n2.r_no('peer-%s-%s-read' % (ovid[-6:], oatt), j(oscratch, 'w.txt'), ev('p%s%d' % (ovid[-4:], oatt)), otoken),
                      n2.w_no('peer-%s-%s-write' % (ovid[-6:], oatt), j(oscratch, 'b_%s.txt' % vid[-6:]))]
        items.append(n2.done_item(scratch))
        argv = n2.cmd_argv(h.cmd, n2.chain_of(items))
        try:
            result = h.node.run_confined_check(vid, attempt, argv, toolchain=[lay['toolchain']], timeout=90,
                                               record=recorded.append, project_id=h.project,
                                               revision=h.seed_commit, workdirs=[])
        except Exception as err:
            fail(rec, case, 'run_confined_check raised %s: %s' % (type(err).__name__, n2._snip(str(err))))
        key = iso.Principal('verify', vid, attempt).key
        name = h.m.mxc_ledger.journal_name(key, 1)
        ops = n2.journal_ops(h.m.mxc_ledger.read_records, h.ledger, name)[0]
        bad = verifier_problems(result, len(recorded) - len(runs), ops, n2.judge(items, n2.look_at), profiles)
        if bad:
            fail(rec, case, 'verifier %s attempt %d: %s' % (vid[-6:], attempt, '; '.join(bad)))
        profiles.add(result['confinement']['ac_profile'])
        runs.append(vid)
        kept[(vid, attempt)] = (scratch, next(i.secret for i in items if i.label == 'scratch-write'))
    again = h.node.run_confined_check(plan[0][0], 0, argv, toolchain=[lay['toolchain']], timeout=90,
                                      record=recorded.append, project_id=h.project, revision=h.seed_commit,
                                      workdirs=[])
    if again.get('error') != 'isolation: attempt_consumed' or h.api.creates != spawned + 3:
        fail(rec, case, 'a consumed attempt was read again: error=%r launches=%d' % (again.get('error'), h.api.creates - spawned))
    rec.record(case, 'PASS', 'three attempts (two verifiers, one retry) each ran as a fresh identity in a fresh checkout '
               'with its own scratch and Job, each blind to the others and to Core, journals clean; a replay was refused')


def run(h, rec):
    h.prepare()
    step_seed(h, rec)
    step_cli(h, rec)
    step_stream(h, rec)
    step_import(h, rec)
    step_hostile(h, rec)
    step_verifiers(h, rec)
    step_authority(h, rec)
    step_limits(h, rec)
    stubs(rec)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    if len(argv) != 1 or not n2.parent_ok(argv[0]):
        print('usage: python -m tools.pv20_mxc.native.n4_check <fixture-parent at or below %s; letters, '
              'digits, dot, underscore, hyphen>' % n2.FIXTURE_BASE, flush=True)
        return 3
    parent = argv[0]
    if not n2._on_windows() or not os.path.isdir(parent):
        print('SETUP ERROR: Windows only and the parent must exist', flush=True)
        return 3
    src, cli = os.path.join(parent, *n2.SDK_TAIL), os.path.join(parent, 'cli')
    root_env = os.environ.get('SystemRoot', '')
    if not n2._system_ok(root_env) or not os.path.isfile(ntpath.join(root_env, 'System32', 'curl.exe')):
        print('SETUP ERROR: SystemRoot is not a plain drive\\Windows folder with cmd.exe and curl.exe', flush=True)
        return 3
    if not os.path.isfile(os.path.join(src, 'package.json')) or not os.path.isfile(os.path.join(cli, 'claude.exe')):
        print(redact('SETUP ERROR: the staged SDK or the staged CLI folder is missing under the parent'), flush=True)
        return 3
    rec, root, h, code = _Rec(STAGE), None, None, 3
    try:
        root = safe_root(parent)
        rec.journal = os.path.join(root, JOURNAL)
        h = Harness(root, src, cli, root_env, n2.Budget(BUDGET_S))
        run(h, rec)
        code = rec.exit_code()
    except StopRun:
        code = rec.exit_code() or 1
        print(redact('STOP at first FAIL; root preserved at %s' % root), flush=True)
    except SetupError as ex:
        print(redact('SETUP ERROR: %s; root preserved at %s' % (ex, root)), flush=True)
    except KeyboardInterrupt:
        print(redact('INTERRUPTED; Jobs closed, root preserved at %s' % root), flush=True)
    except Exception as ex:
        print(redact('UNEXPECTED ERROR: %s %s; root preserved at %s'
                     % (type(ex).__name__, n2._snip(str(ex)), root)), flush=True)
    left = h.wind_down() if h is not None else 0
    if left:
        print(redact('%d launcher(s) outlived the Job close; root preserved' % left), flush=True)
        code = 3
    if root is None or code == 3:
        return code
    try:
        return n2.finish(code, root, remove_fixture)
    except ValueError as ex:
        print(redact('SETUP ERROR: fixture not removed: %s' % n2._snip(str(ex))), flush=True)
        return 3


if __name__ == '__main__':
    sys.exit(main())

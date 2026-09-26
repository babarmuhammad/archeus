"""The HTTP binding of `CoreClient` and the Core fixtures it runs on
(testing-strategy §1.1, p3.5b design gate §10, §12).

- `HttpClient` speaks the P3.5b API with the stdlib (`urllib`); every command
  carries an idempotency key (the caller's, or a fresh ULID per call, as the
  SPA and CLI do).
- `SSEClient` reads `/v1/events/stream` frame by frame over a raw connection.
- `TempCore` runs the REAL Core runtime in this process on a free port, on the
  test's ARCHEUS_HOME: fast, and it can inject clocks and call retention.
- `CoreProcess` runs the Core runtime in a child process built here, with
  scripted ports: only a real process can be killed, hold an OS lock or occupy
  a port. There is no hidden test flag in `archeus core` itself.
"""

import http.client
import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from typing import Optional, Sequence

from archeus.api import auth
from archeus.core import engine, ports, runtime
from archeus.core.application import lifecycle
from archeus.core.domain import entities, ids
from archeus.core.domain.values import PRINCIPAL_SCOPES, Ref
from archeus.infra import discovery

from .client import IMPLEMENTED, OPERATIONS, CoreClient, CoreClientError, _pending

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))


def _issue_principal(tx, *, kind, token_hash):
    """A principal of *kind* with that kind's scopes, a device and a token for
    it: only what `auth.live` needs to read a credential (the judge's rig)."""
    p = entities.Principal(id=ids.new_id('principal'), kind=kind,
                           scopes=PRINCIPAL_SCOPES[kind])
    actor = Ref(kind, p.id)
    tx.insert(p, actor=actor)
    d = entities.Device(id=ids.new_id('device'), principal_id=p.id, name=kind,
                        platform='desktop')
    tx.insert(d, actor=actor)
    lifecycle.fire(tx, entities.Device, d.id, 'code_redeemed', actor=actor,
                   reason='the judge issued a %s credential' % kind)
    tx.insert_token(token_hash=token_hash, kind='device', principal_id=p.id,
                    scopes=p.scopes, actor=actor)
    return {'principal_id': p.id}


def free_port():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    try:
        return s.getsockname()[1]
    finally:
        s.close()


class Response:
    def __init__(self, status, headers, body):
        self.status, self.headers, self.body = status, headers, body

    def json(self):
        return json.loads(self.body)


def request(base, method, path, *, token=None, body=None, headers=None, raw=None, timeout=15):
    """One HTTP request; a Response for every status (never raises on 4xx/5xx)."""
    h = dict(headers or {})
    if token is not None:
        h.setdefault('Authorization', 'Bearer ' + token)
    data = raw if raw is not None else (None if body is None else json.dumps(body).encode())
    if data is not None:
        h.setdefault('Content-Type', 'application/json')
    req = urllib.request.Request(base + path, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return Response(r.status, r.headers, r.read())
    except urllib.error.HTTPError as e:
        return Response(e.code, e.headers, e.read())


class HttpClient:
    """The P3.5 binding: HTTP + SSE against a running Core."""

    def __init__(self, base_url, token, *, core=None):
        self.base, self.token, self.core = base_url, token, core

    # ── binding plumbing (not part of the contract) ──

    def _http(self, method, path, body=None, **kw):
        return request(self.base, method, path, token=self.token, body=body, **kw)

    def _call(self, method, path, body=None):
        r = self._http(method, path, body)
        out = r.json()
        if r.status >= 400:
            raise CoreClientError(r.status, out['error'], out.get('detail'))
        return out

    def _http_get(self, path):
        return self._http('GET', path)

    def _idle(self):
        """Core is idle when its engine's last pass made no progress AND saw
        the head there is now — nothing committed since can be waiting on it —
        and its world worker has nothing due (P4): `pending` is computed from
        the repositories as they are on disk at this request, so a commit the
        worker has not noticed yet is pending work, never idleness."""
        health = self._call('GET', '/v1/health')
        engine, world = health['engine'], health['world']
        if engine['state'] != 'idle' or world['state'] != 'idle' or world['pending']:
            return False
        for worker in ('knowledge', 'intent', 'plan'):  # P6-P8: every event not yet consumed
            if health[worker]['state'] != 'idle' or health[worker]['pending']:
                return False
        return not self._call('GET', '/v1/events?after=%d&limit=1'
                              % engine['observed_seq'])['events']

    def _restart(self, *, kill=True):
        self.core.restart(kill=kill)

    def _report_usage(self, account_id, window, pct):
        """The rig's `usage`: the scripted feed the in-process Core reads."""
        if not isinstance(self.core, TempCore):
            raise NotImplementedError('reporting usage to a Core process')
        self.core.kw['ports'].usage.set(account_id, window, pct)

    def _script(self, task_key, steps):
        """The rig's `script_harness`: the in-process Core's engine reads this
        map (Ports.scenarios) when it starts a task; it survives a restart."""
        if not isinstance(self.core, TempCore):
            raise NotImplementedError('scripting the fake harness of a Core process')
        self.core.kw['ports'].scenarios[task_key] = steps

    def close(self):
        if self.core is not None:
            self.core.stop()

    # ── the contract ──

    def create_mission(self, *, title: str, objective: str,
                       project_id: Optional[str] = None,
                       success_criteria: Sequence[dict] = (),
                       idempotency_key: Optional[str] = None) -> dict:
        return self._call('POST', '/v1/missions', {
            'title': title, 'objective': objective, 'project_id': project_id,
            'success_criteria': [dict(c) for c in success_criteria],
            'idempotency_key': idempotency_key or ids.new_ulid()})

    def get_mission(self, mission_id: str) -> dict:
        return self._call('GET', '/v1/missions/%s' % mission_id)

    def list_missions(self, *, state: Optional[str] = None,
                      project_id: Optional[str] = None) -> list:
        q = '&'.join('%s=%s' % kv for kv in (('state', state), ('project', project_id))
                     if kv[1] is not None)
        return self._call('GET', '/v1/missions' + ('?' + q if q else ''))['missions']

    def _control(self, verb, target):
        if ids.kind_of(target) != 'mission':
            raise NotImplementedError('CoreClient.%s: only mission targets until the '
                                      'execution orchestrator (P11)' % verb)
        return self._call('POST', '/v1/missions/%s/%s' % (target, verb),
                          {'idempotency_key': ids.new_ulid()})

    def pause(self, target: str) -> dict:
        return self._control('pause', target)

    # ── approvals and policy (P9) ──

    def decide_approval(self, approval_id: str, decision: str, *,
                        note: Optional[str] = None, step_up: Optional[str] = None,
                        idempotency_key: Optional[str] = None) -> dict:
        """GET what the approval presents, then POST the decision with the
        `action_hash` it showed (a client sends what it displayed, X02)."""
        shown = self._call('GET', '/v1/approvals/%s' % approval_id)
        return self._call('POST', '/v1/approvals/%s/decide' % approval_id, {
            'decision': decision, 'action_hash': shown['action_hash'], 'note': note,
            'step_up': step_up, 'idempotency_key': idempotency_key or ids.new_ulid()})

    def set_policy_rule(self, *, scope_level: str, action_class: str, decision: str,
                        scope_ref: Optional[str] = None, locked: Optional[bool] = None,
                        match: Optional[dict] = None, boundary: Optional[dict] = None,
                        outside: Optional[str] = None,
                        idempotency_key: Optional[str] = None) -> dict:
        return self._call('POST', '/v1/policies/rules', {
            'scope_level': scope_level, 'scope_ref': scope_ref, 'action_class': action_class,
            'decision': decision, 'locked': locked, 'match': match, 'boundary': boundary,
            'outside': outside, 'idempotency_key': idempotency_key or ids.new_ulid()})

    def _principal_client(self, kind):
        """A client holding a credential of a non-user principal (the rig's
        `principal_client`), issued through this Core's own writer — a test
        fixture, never a route: no route issues a brain a credential."""
        if not isinstance(self.core, TempCore):
            raise NotImplementedError('a principal client of a Core process')
        token = auth.new_token()
        self.core.core.db.writer.execute(_issue_principal, {
            'kind': kind, 'token_hash': auth.token_hash(token)})
        return HttpClient(self.base, token)

    def resume(self, target: str) -> dict:
        return self._control('resume', target)

    def events(self, after_seq: int = 0, *, limit: Optional[int] = None) -> list:
        if limit is not None:
            return self._call('GET', '/v1/events?after=%d&limit=%d'
                              % (after_seq, limit))['events']
        out, cursor = [], after_seq
        while True:
            page = self._call('GET', '/v1/events?after=%d&limit=1000' % cursor)['events']
            out += page
            if len(page) < 1000:
                return out
            cursor = page[-1]['seq']

    # ── the world (P4) ──

    def create_project(self, *, name: str, root_paths: Sequence[str],
                       idempotency_key: Optional[str] = None) -> dict:
        return self._call('POST', '/v1/projects', {
            'name': name, 'root_paths': list(root_paths),
            'idempotency_key': idempotency_key or ids.new_ulid()})

    def declare_constraint(self, *, project_id: str, statement: str,
                           kind: Optional[str] = None, spec: Optional[dict] = None,
                           idempotency_key: Optional[str] = None) -> dict:
        return self._call('POST', '/v1/projects/%s/constraints' % project_id, {
            'statement': statement, 'kind': kind, 'spec': spec,
            'idempotency_key': idempotency_key or ids.new_ulid()})

    def status(self, *, project_id: Optional[str] = None) -> dict:
        return self._call('GET', '/v1/status' + ('' if project_id is None
                                                 else '?project=%s' % project_id))

    def digest(self) -> dict:
        return self._call('GET', '/v1/digest')

    def ack(self, up_to_seq: int) -> dict:
        return self._call('POST', '/v1/digest/ack', {'up_to_seq': up_to_seq})

    # ── knowledge and own calls (P6) ──

    def submit_message(self, text: str, *, conversation_id: Optional[str] = None,
                       idempotency_key: Optional[str] = None) -> dict:
        """POST the turn; the reply arrives as a message (api-and-realtime §2),
        read back once it exists and Core has settled what the turn set in
        motion (the in-process binding's contract)."""
        cid = conversation_id or 'primary'
        posted = self._call('POST', '/v1/conversations/%s/messages' % cid, {
            'text': text, 'idempotency_key': idempotency_key or ids.new_ulid()})
        mid = posted['message_id']
        deadline = time.monotonic() + 60
        while True:
            got = [m for m in self._call('GET', '/v1/conversations/%s/messages?after=%s'
                                         % (posted['conversation_id'], mid))['messages']
                   if m['in_reply_to'] == mid and m['author'] == 'archeus']
            if got:
                while not self._idle() and time.monotonic() < deadline + 60:
                    time.sleep(0.05)
                return dict(got[0], message_id=mid)
            if time.monotonic() > deadline:
                raise AssertionError('no reply to message %s within 60s' % mid)
            time.sleep(0.05)

    def import_meeting(self, path: str, *, project_id: Optional[str] = None) -> dict:
        # the import path opts in to undated notes (P7 D2): imported, then asked
        body = {'path': path, 'allow_undated': True, 'idempotency_key': ids.new_ulid()}
        if project_id is not None:
            body['project_id'] = project_id
        return self._call('POST', '/v1/meetings/import', body)['meeting']

    def list_knowledge(self, *, project_id: Optional[str] = None,
                       state: Optional[str] = None) -> list:
        q = '&'.join('%s=%s' % kv for kv in (('project', project_id), ('state', state))
                     if kv[1] is not None)
        return self._call('GET', '/v1/knowledge' + ('?' + q if q else ''))['knowledge']

    def route_why(self, subject_id: str) -> dict:
        if subject_id.startswith('rte_'):
            return self._call('GET', '/v1/route-decisions/%s' % subject_id)
        got = self._call('GET', '/v1/route-decisions?source=%s' % subject_id)['route_decisions']
        if not got:
            raise CoreClientError(404, 'not_found', {'id': subject_id})
        work = [d for d in got if d['subject']['kind'] == 'task']
        return self._call('GET', '/v1/route-decisions/%s' % (work or got)[-1]['id'])

    # ── resources (P10) ──

    def register_account(self, *, harness_id: str, label: str, auth_kind: str,
                         home_ref: Optional[str] = None) -> dict:
        return self._call('POST', '/v1/accounts', {
            'harness_id': harness_id, 'label': label, 'auth_kind': auth_kind,
            'home_ref': home_ref, 'idempotency_key': ids.new_ulid()})

    def set_resource_policy(self, account_id: str, *, priority: Optional[int] = None,
                            allocation_pct: Optional[int] = None,
                            reserve_pct: Optional[int] = None,
                            brain_reserve_pct: Optional[int] = None,
                            fallback: Optional[str] = None,
                            expected_version: Optional[int] = None) -> dict:
        body = {k: v for k, v in (('priority', priority), ('allocation_pct', allocation_pct),
                                  ('reserve_pct', reserve_pct),
                                  ('brain_reserve_pct', brain_reserve_pct),
                                  ('fallback', fallback),
                                  ('expected_version', expected_version)) if v is not None}
        return self._call('POST', '/v1/resource-policies/%s' % account_id,
                          dict(body, idempotency_key=ids.new_ulid()))


for _op in OPERATIONS:
    if _op not in IMPLEMENTED:
        _stub = _pending(_op)
        _stub.__signature__ = __import__('inspect').signature(getattr(CoreClient, _op))
        setattr(HttpClient, _op, _stub)
del _op, _stub


class SSEClient:
    """`GET /v1/events/stream` read frame by frame."""

    def __init__(self, base_url, token, *, last_event_id=None, after=None, headers=None,
                 timeout=10):
        host, port = base_url.split('//', 1)[1].split(':')
        self.conn = http.client.HTTPConnection(host, int(port), timeout=timeout)
        h = dict(headers or {})
        if token is not None:
            h['Authorization'] = 'Bearer ' + token
        if last_event_id is not None:
            h['Last-Event-ID'] = str(last_event_id)
        path = '/v1/events/stream' + ('' if after is None else '?after=%s' % after)
        self.conn.request('GET', path, headers=h)
        self.sock = self.conn.sock       # HTTP/1.0: getresponse hands it to the response
        self.resp = self.conn.getresponse()
        self.status, self.headers = self.resp.status, self.resp.headers
        self.eof = False

    def body(self):
        return self.resp.read()

    def next(self, timeout=5.0):
        """The next frame {id, event, data} or {'comment': …}; None at EOF."""
        self.sock.settimeout(timeout)
        frame, lines = {}, 0
        while True:
            try:
                line = self.resp.fp.readline()
            except (socket.timeout, TimeoutError):
                raise TimeoutError('no frame within %.1fs' % timeout) from None
            if not line:
                self.eof = True
                return None
            line = line.decode('utf-8').rstrip('\n')
            if line == '':
                if lines:
                    return frame
                continue
            lines += 1
            if line.startswith(':'):
                frame['comment'] = line[1:].strip()
                continue
            k, _, v = line.partition(': ')
            frame[k] = json.loads(v) if k == 'data' else (int(v) if k == 'id' else v)

    def frames(self, n, timeout=5.0):
        """The next *n* event frames (heartbeats skipped)."""
        out = []
        while len(out) < n:
            f = self.next(timeout)
            if f is None:
                break
            if 'comment' not in f:
                out.append(f)
        return out

    def wait_eof(self, timeout=5.0):
        deadline = time.monotonic() + timeout
        while not self.eof and time.monotonic() < deadline:
            try:
                self.next(max(0.05, deadline - time.monotonic()))
            except TimeoutError:
                break
        return self.eof

    def close(self):
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.resp.close()
        self.sock.close()


class TempCore:
    """The real Core runtime in this process, on the test's ARCHEUS_HOME.

    Without `ports` it runs the P3.5 stub brain (the engine plans the skeleton
    plan), which is what the service tests measure; a caller that passes
    `ports` gets exactly those — the judge's pass the recorded brain, so its
    missions are planned by the planning worker through `archeus_call` (P8)."""

    def __init__(self, home, *, port=None, **kw):
        kw.setdefault('ports', runtime.Ports(brain=ports.FixedPlanBrain(engine.SKELETON_PLAN)))
        self.home, self.port, self.kw = str(home), port or free_port(), kw
        self.core = None

    @property
    def base_url(self):
        return 'http://127.0.0.1:%d' % self.port

    @property
    def token(self):
        return self.core.local['token']

    def start(self):
        assert os.path.normcase(os.environ['ARCHEUS_HOME']) == os.path.normcase(self.home)
        self.core = runtime.Core(port=self.port, **self.kw).start()
        return self

    def stop(self, *, kill=False):
        if self.core is not None:
            loops = (self.core.plan, self.core.knowledge, self.core.world, self.core.loop)
            self.core.stop(drain=not kill)
            for loop in loops:
                if loop is not None:
                    loop.join(10)
            self.core = None

    def restart(self, *, kill=True):
        self.stop(kill=kill)
        self.start()

    def client(self):
        return HttpClient(self.base_url, self.token, core=self)

    def http(self, method, path, **kw):
        kw.setdefault('token', self.token)
        return request(self.base_url, method, path, **kw)


CHILD = r'''
import faulthandler, signal
if hasattr(signal, 'SIGUSR1'):      # wait_ready's timeout asks for every thread's stack
    faulthandler.register(signal.SIGUSR1, all_threads=True)
import json, os, sys
sys.path.insert(0, %(root)r)
cfg = json.loads(sys.argv[1])
if cfg.get('audit'):
    needle, out = cfg['audit']
    def hook(event, args):
        if event == 'open' and isinstance(args[0], str) and needle in args[0] \
                and 'stream.jsonl' in args[0]:
            with open(out, 'a') as f:
                f.write(args[0] + '\n')
    sys.addaudithook(hook)
from archeus.core import engine, runtime
if cfg.get('hold_sweep'):           # the sweep waits for the test to open this gate
    sweep = engine.Engine.reconcile_orphans
    def held(self):
        while not os.path.exists(cfg['hold_sweep']):
            import time
            time.sleep(0.02)
        return sweep(self)
    engine.Engine.reconcile_orphans = held
if cfg.get('hold_inspection'):     # a walk waits for the test to open this gate
    from archeus.core.world import inspection as _inspection
    _walk = _inspection.inspect
    def held_walk(path):
        while not os.path.exists(cfg['hold_inspection']):
            import time
            time.sleep(0.02)
        return _walk(path)
    _inspection.inspect = held_walk
from archeus.core import ports as P
ports = runtime.Ports(scenarios=cfg.get('scenarios') or {},
                      brain=P.FixedPlanBrain(engine.SKELETON_PLAN))
if cfg.get('brain_fails'):
    class Broken:
        def call(self, *a, **k):
            raise RuntimeError('scripted brain failure')
    ports.brain = Broken()
sys.exit(runtime.run(port=cfg['port'], ports=ports))
'''


class CoreProcess:
    """The Core runtime in a real child process on the test's ARCHEUS_HOME."""

    def __init__(self, home, *, port=None, **cfg):
        self.home, self.port, self.cfg = str(home), port or free_port(), cfg
        self.proc = None

    @property
    def base_url(self):
        return 'http://127.0.0.1:%d' % self.port

    @property
    def token(self):
        return discovery.read_local_token()

    def start(self, *, wait=True):
        os.makedirs(self.home, exist_ok=True)
        self.out = os.path.join(self.home, 'core-child-%d.txt' % time.monotonic_ns())
        flags = subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform.startswith('win') else 0
        with open(self.out, 'w') as f:
            self.proc = subprocess.Popen(
                [sys.executable, '-c', CHILD % {'root': ROOT},
                 json.dumps(dict(self.cfg, port=self.port))],
                stdout=f, stderr=subprocess.STDOUT, creationflags=flags,
                env=dict(os.environ, ARCHEUS_HOME=self.home))
        if wait:
            self.wait_ready()
        return self

    def output(self):
        with open(self.out, encoding='utf-8', errors='replace') as f:
            return f.read()

    def wait_ready(self, timeout=30):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.proc.poll() is not None:
                raise AssertionError('Core exited %s:\n%s' % (self.proc.returncode, self.output()))
            info = discovery.read_core_json()
            if info and info['pid'] == self.proc.pid:
                return info
            time.sleep(0.05)
        raise AssertionError('Core did not start:\n%s\n%s' % (self._diagnose(), self.output()))

    def _diagnose(self):
        """What wait_ready could see when it gave up (on timeout only)."""
        from claude_sessions import proc
        path = discovery.core_json_path()
        try:
            with open(path, encoding='utf-8', errors='replace') as f:
                raw = f.read()
        except OSError as e:
            raw = '<%s>' % e
        info = discovery.read_core_json()
        pid = info and info['pid']
        lines = ['core.json: %s (exists: %s)' % (path, os.path.exists(path)),
                 'core.json raw: %r' % raw[:500],
                 'child pid %s, poll %r, alive %r, create_time %r' % (
                     self.proc.pid, self.proc.poll(), proc.pid_alive(self.proc.pid),
                     proc.process_create_time(self.proc.pid)),
                 'test pid %s, sys.executable %s' % (os.getpid(), sys.executable),
                 'lock held: %r' % discovery.lock_is_held()]
        if pid is not None:
            lines.append('recorded pid %s: alive %r, create_time now %r, recorded %r' % (
                pid, proc.pid_alive(pid), proc.process_create_time(pid), info['create_time']))
        if not sys.platform.startswith('win'):
            r = subprocess.run(['ps', '-A', '-o', 'pid=,ppid=,stat=,command='],
                               capture_output=True, text=True, timeout=10)
            lines += ['ps: ' + l.strip() for l in r.stdout.splitlines()
                      if l.split()[:2] and self.proc.pid in (int(l.split()[0]), int(l.split()[1]))]
            if self.proc.poll() is None:
                # the child's faulthandler writes every thread's stack into its
                # output; wait (bounded) for the dump so output() below has it
                os.kill(self.proc.pid, signal.SIGUSR1)
                end, before = time.monotonic() + 5, None
                while time.monotonic() < end:
                    now = self.output()
                    if 'most recent call first' in now and now == before:
                        break                   # the dump has stopped growing
                    before = now
                    time.sleep(0.05)
        return '\n'.join(lines)

    def kill(self):
        self.proc.kill()
        self.proc.wait(30)

    def wait(self, timeout=60):
        return self.proc.wait(timeout)

    def client(self):
        return HttpClient(self.base_url, self.token)

    def http(self, method, path, **kw):
        kw.setdefault('token', self.token)
        return request(self.base_url, method, path, **kw)

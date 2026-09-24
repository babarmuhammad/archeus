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
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from typing import Optional, Sequence

from archeus.core import runtime
from archeus.core.domain import ids
from archeus.infra import discovery

from .client import IMPLEMENTED, OPERATIONS, CoreClient, CoreClientError, _pending

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))


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
        the head there is now: nothing committed since can be waiting on it."""
        engine = self._call('GET', '/v1/health')['engine']
        if engine['state'] != 'idle':
            return False
        return not self._call('GET', '/v1/events?after=%d&limit=1'
                              % engine['observed_seq'])['events']

    def _restart(self, *, kill=True):
        self.core.restart(kill=kill)

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
        if project_id is not None:
            raise NotImplementedError('CoreClient.list_missions: a project filter arrives '
                                      'with projects (P4)')
        q = '' if state is None else '?state=%s' % state
        return self._call('GET', '/v1/missions' + q)['missions']

    def _control(self, verb, target):
        if ids.kind_of(target) != 'mission':
            raise NotImplementedError('CoreClient.%s: only mission targets until the '
                                      'execution orchestrator (P11)' % verb)
        return self._call('POST', '/v1/missions/%s/%s' % (target, verb),
                          {'idempotency_key': ids.new_ulid()})

    def pause(self, target: str) -> dict:
        return self._control('pause', target)

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
    """The real Core runtime in this process, on the test's ARCHEUS_HOME."""

    def __init__(self, home, *, port=None, **kw):
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
            loop = self.core.loop
            self.core.stop(drain=not kill)
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
ports = runtime.Ports(scenarios=cfg.get('scenarios') or {})
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
        raise AssertionError('Core did not start:\n' + self.output())

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

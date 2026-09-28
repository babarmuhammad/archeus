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
from urllib.parse import quote

from archeus.api import auth
from archeus.harnesses.fake import FakeHarness
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
        self.device_id = None               # set on a paired client (P15)

    # ── binding plumbing (not part of the contract) ──

    def _pair(self, name, scopes, *, platform='android', pin=None):
        """A paired client of this Core (the rig's `device`, P15): this client
        (the local token, admin) starts a pairing; the new one redeems it and
        acts with its own token and exactly *scopes*."""
        code = self._call('POST', '/v1/devices/pair/start',
                          {'name': name, 'scopes': list(scopes)})['code']
        r = request(self.base, 'POST', '/v1/devices/pair/redeem',
                    body={'code': code, 'platform': platform, 'pin': pin})
        if r.status != 200:
            raise CoreClientError(r.status, r.json()['error'], r.json().get('detail'))
        out = r.json()
        paired = HttpClient(self.base, out['token'], core=self.core)
        paired.device_id = out['device_id']
        return paired

    def _revoke(self, other):
        self._call('POST', '/v1/devices/%s/revoke' % other.device_id,
                   {'idempotency_key': ids.new_ulid()})

    def open_stream(self, **query):
        """This client's own event stream (an SSEClient)."""
        return SSEClient(self.base, self.token, query=query)

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
        engine, world, ex = health['engine'], health['world'], health['exec']
        if engine['state'] != 'idle' or world['state'] != 'idle' or world['pending']:
            return False
        if ex['state'] != 'idle' or ex['live']:     # P11: a process advances on its own
            return False
        # P6-P8: every event not yet consumed; P13: every verification, merge
        # or review due, and none in flight
        for worker in ('knowledge', 'intent', 'plan', 'verify', 'automation'):
            if (health[worker]['state'] != 'idle' or health[worker]['pending']
                    or health[worker].get('retrying')):
                return False
        return not self._call('GET', '/v1/events?after=%d&limit=1'
                              % min(engine['observed_seq'], ex['observed_seq']))['events']

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
            raise NotImplementedError('CoreClient.%s: a mission target' % verb)
        return self._call('POST', '/v1/missions/%s/%s' % (target, verb),
                          {'idempotency_key': ids.new_ulid()})

    def stop(self, target: str) -> dict:
        key = {'idempotency_key': ids.new_ulid()}
        if target == 'all':
            return self._call('POST', '/v1/estop', key)
        if ids.kind_of(target) == 'mission':
            return self._call('POST', '/v1/missions/%s/stop' % target, key)
        return self._call('POST', '/v1/executions/%s/stop' % target, key)

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

    # ── sessions and checkpoints (P12) ──

    @staticmethod
    def _body(**kw):
        return dict({k: v for k, v in kw.items() if v is not None},
                    idempotency_key=ids.new_ulid())

    def register_session(self, *, harness_id: str, cwd: str,
                         provider_session_ref: Optional[str] = None,
                         mission_id: Optional[str] = None, project_id: Optional[str] = None,
                         account_id: Optional[str] = None, model: Optional[str] = None,
                         effort: Optional[str] = None) -> dict:
        return self._call('POST', '/v1/sessions', self._body(
            harness_id=harness_id, cwd=cwd, provider_session_ref=provider_session_ref,
            mission_id=mission_id, project_id=project_id, account_id=account_id,
            model=model, effort=effort))

    def launch_session(self, *, harness_id: str, cwd: str, mission_id: Optional[str] = None,
                       project_id: Optional[str] = None, account_id: Optional[str] = None,
                       model: Optional[str] = None, effort: Optional[str] = None) -> dict:
        return self._call('POST', '/v1/sessions', self._body(
            harness_id=harness_id, cwd=cwd, launch=True, mission_id=mission_id,
            project_id=project_id, account_id=account_id, model=model, effort=effort))

    def get_session(self, session_id: str) -> dict:
        return self._call('GET', '/v1/sessions/%s' % quote(session_id, safe=''))

    def list_sessions(self, *, project_id: Optional[str] = None,
                      mission_id: Optional[str] = None) -> list:
        q = '&'.join('%s=%s' % (k, quote(v, safe='')) for k, v in
                     (('project', project_id), ('mission', mission_id)) if v)
        return self._call('GET', '/v1/sessions' + ('?' + q if q else ''))['sessions']

    def session_brief(self, session_id: str) -> dict:
        return self._call('GET', '/v1/sessions/%s/brief' % quote(session_id, safe=''))

    def resume_session(self, session_id: str, *, request_id: str, model: Optional[str] = None,
                       effort: Optional[str] = None, deliver_brief: bool = False) -> dict:
        return self._call('POST', '/v1/sessions/%s/resume' % quote(session_id, safe=''),
                          self._body(request_id=request_id, model=model, effort=effort,
                                     deliver_brief=deliver_brief))

    def handoff_session(self, session_id: str, *, request_id: str, harness_id: str,
                        account_id: Optional[str] = None, model: Optional[str] = None,
                        effort: Optional[str] = None, reason: str = '') -> dict:
        return self._call('POST', '/v1/sessions/%s/handoff' % quote(session_id, safe=''),
                          self._body(request_id=request_id, harness_id=harness_id,
                                     account_id=account_id, model=model, effort=effort,
                                     reason=reason or None))

    def link_session(self, session_id: str, mission_id: Optional[str]) -> dict:
        body = dict(idempotency_key=ids.new_ulid(), mission_id=mission_id)
        return self._call('POST', '/v1/sessions/%s/link' % quote(session_id, safe=''), body)

    def close_session(self, session_id: str) -> dict:
        return self._call('POST', '/v1/sessions/%s/close' % quote(session_id, safe=''),
                          self._body())

    def checkpoints(self, execution_id: str) -> list:
        return self._call('GET', '/v1/executions/%s/checkpoints'
                          % quote(execution_id, safe=''))['checkpoints']

    def handoff_execution(self, execution_id: str) -> dict:
        return self._call('POST', '/v1/executions/%s/handoff' % quote(execution_id, safe=''),
                          self._body())

    # ── verification and review (P13) ──

    def verifications(self, mission_id: str) -> list:
        return self._call('GET', '/v1/missions/%s/verifications'
                          % quote(mission_id, safe=''))['verifications']

    def decide_verification(self, verification_id: str, decision: str, *,
                            note: Optional[str] = None) -> dict:
        return self._call('POST', '/v1/verifications/%s/decide' % quote(verification_id, safe=''),
                          self._body(decision=decision, note=note))

    def reviews(self, mission_id: str) -> list:
        return self._call('GET', '/v1/missions/%s/reviews'
                          % quote(mission_id, safe=''))['reviews']

    def review(self, mission_id: str, verdict: str, *, note: Optional[str] = None) -> dict:
        return self._call('POST', '/v1/missions/%s/review' % quote(mission_id, safe=''),
                          self._body(verdict=verdict, note=note))

    def abandon_integration(self, task_id: str, *, reason: Optional[str] = None) -> dict:
        return self._call('POST', '/v1/tasks/%s/integration/abandon' % quote(task_id, safe=''),
                          self._body(reason=reason))

    # ── automations (P14) ──

    def create_automation(self, *, name: str, trigger: dict, template: dict,
                          project_id: Optional[str] = None, max_depth: Optional[int] = None,
                          rate_limit: Optional[int] = None) -> dict:
        body = {k: v for k, v in (('project_id', project_id), ('max_depth', max_depth),
                                  ('rate_limit', rate_limit)) if v is not None}
        return self._call('POST', '/v1/automations', self._body(
            name=name, trigger=trigger, template=template, **body))

    def set_automation_state(self, automation_id: str, action: str) -> dict:
        return self._call('POST', '/v1/automations/%s/state' % quote(automation_id, safe=''),
                          self._body(action=action))

    def automations(self) -> list:
        return self._call('GET', '/v1/automations')['automations']

    def automation(self, automation_id: str) -> dict:
        return self._call('GET', '/v1/automations/%s' % quote(automation_id, safe=''))

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
del _op
globals().pop('_stub', None)       # none left once every operation is built


class SSEClient:
    """`GET /v1/events/stream` read frame by frame."""

    def __init__(self, base_url, token, *, last_event_id=None, after=None, headers=None,
                 timeout=10, query=None):
        host, port = base_url.split('//', 1)[1].split(':')
        self.conn = http.client.HTTPConnection(host, int(port), timeout=timeout)
        h = dict(headers or {})
        if token is not None:
            h['Authorization'] = 'Bearer ' + token
        if last_event_id is not None:
            h['Last-Event-ID'] = str(last_event_id)
        q = [('after', after)] if after is not None else []
        for k, vs in (query or {}).items():         # P15 narrowing: project=, type=
            q += [(k, v) for v in ((vs,) if isinstance(vs, str) else vs)]
        path = '/v1/events/stream' + ('?' + '&'.join('%s=%s' % kv for kv in q) if q else '')
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

    def closed(self, timeout=5.0):
        """True once Core has ended the stream (EOF within *timeout*)."""
        return self.wait_eof(timeout)

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

    def __init__(self, home, *, port=None, real_verification=False, real_review=False, **kw):
        kw.setdefault('ports', runtime.Ports(brain=ports.FixedPlanBrain(engine.SKELETON_PLAN)))
        if kw['ports'].executors is None:
            # a test Core executes on the fake harness unless it names its
            # executors (P11: the runtime's default is the real adapters)
            kw['ports'].executors = [FakeHarness()]
        if not real_verification:
            # and verifies and reviews on the scripted stubs unless it asks for
            # the verification worker (P13: the runtime's default)
            if kw['ports'].verifier is None:
                kw['ports'].verifier = ports.ScriptedVerifier()
        if not (real_verification or real_review) and kw['ports'].reviewer is None:
            kw['ports'].reviewer = ports.ScriptedReview()
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
            loops = (self.core.plan, self.core.knowledge, self.core.world, self.core.loop,
                     self.core.verify)
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
from archeus.harnesses.fake import FakeHarness
if cfg.get('pause_timeout') is not None:   # a short pause timeout for the test (P11)
    from archeus.core.execution import manager as _manager
    _manager.PAUSE_TIMEOUT_S = cfg['pause_timeout']
ports = runtime.Ports(scenarios=cfg.get('scenarios') or {},
                      brain=P.FixedPlanBrain(engine.SKELETON_PLAN), executors=[FakeHarness()])
if not cfg.get('real_verification'):  # P13: a test Core keeps the stubs unless asked
    ports.verifier, ports.reviewer = P.ScriptedVerifier(), P.ScriptedReview()
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

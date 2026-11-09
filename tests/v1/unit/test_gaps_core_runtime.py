"""T-706: the highest-risk uncovered branches of `archeus/core/runtime.py`, as tests.

Fail-closed and denial paths first: Core refuses to start under a loose token
before it opens anything, a failed start releases the lock, a revoked or unknown
local token is reminted and never reused, a lost race parks instead of spinning
while any other engine/world failure stops Core (exit 3) — and a crash that
happens during a deliberate stop is NOT a failure. Then boundary values: the
parked-mission wake-up (version, tasks/executions/reviews/verifications, and the
`now >= due` edge), the idle wait's timeout clamp, the e-stop sentinel behind
health's `armed`, the stub-port default, and run()'s exit-code mapping. Then the
error paths: the boot-sweep gate, the wake-flag clear, the `_version` fallback,
and stop()'s reverse order with drain=False.

Style and raw-row seeds follow tests/v1/unit/test_gaps_core_metrics.py, the
closest existing gaps file; the `db` fixture is copied from
tests/v1/integration/conftest.py because tests/v1/unit has no conftest. The
loops' seams are the ones tests/v1/integration/test_p21_health.py already uses:
a fake engine/manager/world object and a direct `_run()` / `_pass()` call — the
only real threads are each Database's writer. Every OS call (token protection,
the lock, core.json, the local-token file, SIGTERM) is faked through the module
seams, so nothing here needs Windows or the Windows API; token files are written
by `discovery.write_local_token` under the test's ARCHEUS_HOME only. No sleeps
over 1 s, no network, no real process.
"""

import importlib.metadata
import io
import json
import logging
import os
import threading
import time
from types import SimpleNamespace

import pytest

from archeus.api import auth
from archeus.core import runtime
from archeus.core.application import commands, errors
from archeus.core.domain import ids
from archeus.core.domain.values import Ref
from archeus.infra import discovery, paths
from archeus.infra.db import Database
from archeus.infra.eventlog import outbox

T = '2026-10-17T10:00:00.000Z'
META = {'version': 1, 'created_at': T, 'updated_at': T, 'created_by': 'p', 'updated_by': 'p'}
_SEQ = iter(range(1, 10 ** 6))


def _put(tx, *, rows):
    for table, cols in rows:
        tx.execute('INSERT INTO %s (%s) VALUES (%s)' % (table, ','.join(cols),
                                                        ','.join('?' * len(cols))),
                   list(cols.values()))


def put(db, *rows):
    db.writer.execute(_put, {'rows': list(rows)})


def _bump(tx, *, mid):
    tx.execute('UPDATE missions SET version = version + 1 WHERE id = ?', (mid,))


def mission(mid, state='EXECUTING', priority=0, version=1):
    body = {'title': mid, 'objective': 'the goal'}
    if priority:
        body['priority'] = priority
    return 'missions', dict(META, id=mid, workspace_id='ws_global', state=state,
                            version=version, body=json.dumps(body))


def plan(mid, pid):
    return 'plans', dict(META, id=pid, mission_id=mid, plan_version=1,
                         state='APPROVED', body='{}')


def task(tid, pid, mid):
    return 'tasks', dict(META, id=tid, plan_id=pid, mission_id=mid, key='k-' + tid,
                         state='PENDING', body='{}')


def verification(vid, pid):
    return 'verifications', dict(META, id=vid, plan_id=pid, state='PENDING', body='{}')


def event(sid):
    return 'events', {'id': 'evt%d' % next(_SEQ), 'type': 'mission.state_changed', 'at': T,
                      'actor_kind': 'system', 'actor_id': 'p', 'cause_chain': '[]',
                      'subject_kind': 'mission', 'subject_id': sid, 'workspace_id': 'wsp',
                      'visibility': 'user', 'payload': '{}'}


def count(db, table):
    with db.read() as conn:
        return conn.execute('SELECT COUNT(*) FROM %s' % table).fetchone()[0]


@pytest.fixture
def db(archeus_home):                     # as in tests/v1/integration/conftest.py
    d = Database.open()
    yield d
    d.close()


class FakeEngine:
    """The engine seam the loops take: `step` replays queued results (an
    exception raises, a callable is called with the mission id), `reconcile_orphans`
    replays its own queue. Default step result: changed."""

    def __init__(self, default=None):
        self.stepped = []
        self.outs = {}
        self.reconcile = []
        self.default = default if default is not None else {'changed': True}

    def reconcile_orphans(self):
        if self.reconcile:
            out = self.reconcile.pop(0)
            if isinstance(out, BaseException):
                raise out
        return []

    def step(self, mid):
        self.stepped.append(mid)
        q = self.outs.get(mid)
        out = q.pop(0) if q else self.default
        if callable(out):
            out = out(mid)
        if isinstance(out, BaseException):
            raise out
        return out


class FakeManager:
    def __init__(self, booted=True, procs=None):
        self.booted, self._procs = booted, procs if procs is not None else {}
        self.queue, self.ticks = [], 0

    def tick(self):
        out = self.queue.pop(0) if self.queue else True
        if callable(out):
            out = out()
        if isinstance(out, BaseException):
            raise out
        self.ticks += 1
        return out


class FakeWorld:
    def __init__(self, swept=(), passes=(), pending=0, detail=None):
        self.swept, self.queue = list(swept), list(passes)
        self._pending, self._detail = pending, detail
        self.sweeps = self.passes = 0
        self.on_wake = self.stopping = None

    def sweep(self):
        self.sweeps += 1
        return self.swept

    def pass_once(self):
        self.passes += 1
        out = self.queue.pop(0) if self.queue else {'changed': True}
        if callable(out):
            out = out()
        if isinstance(out, BaseException):
            raise out
        return out

    def pending(self):
        return self._pending

    def detail(self):
        return self._detail or {}


class Spy:
    """Records any call, through chains: `api.sse.close_all()` logs 'api.sse.close_all'."""

    def __init__(self, log, path=''):
        self.__dict__['_log'], self.__dict__['_path'] = log, path

    def __getattr__(self, item):
        if item.startswith('__'):
            raise AttributeError(item)
        return Spy(self._log, '%s.%s' % (self._path, item))

    def __call__(self, *a, **k):
        self._log.append((self._path, a, k))


def engine_loop(db, eng, monkeypatch, idle_s=0.5):
    fails = []
    loop = runtime.EngineLoop(eng, db, idle_s=idle_s, on_fail=lambda: fails.append(1))
    waits = []

    def fake_wait(seen, timeout, until=None):
        waits.append(timeout)
        return db.writer.commit_count
    monkeypatch.setattr(db.writer, 'wait_commit', fake_wait)
    return loop, fails, waits


def health_core(stub=True):
    core = object.__new__(runtime.Core)
    core.started_at, core.schema = T, 18
    core.ports = SimpleNamespace(stub=stub)
    for name in ('loop', 'world', 'exec', 'knowledge', 'intent'):
        setattr(core, name, SimpleNamespace(status=lambda: {'state': 'idle'}))
    for name in ('plan', 'policy', 'verify', 'automation', 'metrics'):
        setattr(core, name, None)
    return core


# ── fail-closed and denial paths ─────────────────────────────────────────────


def test_start_refuses_a_loose_local_token_before_opening_anything(monkeypatch):
    # runtime.py:421-423 `ok, self.warning = discovery.token_protection(); if not ok:
    # raise RefuseStart(...)`. The refusal must come before the log and the database:
    # removing the guard (or opening them first) serves a home whose token file the
    # group can read — the exact condition the refusal exists to deny.
    core = runtime.Core(port=8123)
    monkeypatch.setattr(runtime.discovery, 'token_protection',
                        lambda: (False, 'the local token file is group-readable'))
    monkeypatch.setattr(core, '_open_log',
                        lambda: pytest.fail('the log opened under a loose token'))
    monkeypatch.setattr(runtime, 'Database',
                        SimpleNamespace(open=lambda *a, **k: pytest.fail(
                            'the database opened under a loose token')))
    with pytest.raises(runtime.RefuseStart) as e:
        core._start()
    assert 'group-readable' in str(e.value) and core.warning == 'the local token file ' \
                                                                'is group-readable'


def test_a_failed_start_releases_the_core_lock(monkeypatch):
    # runtime.py:410-416 `try: self._start() except BaseException: self.stop(); raise`.
    # Drop the cleanup and a Core that died mid-start keeps run/core.lock forever:
    # no other Core can ever start, and the CLI reports one that is not running.
    released = []
    monkeypatch.setattr(runtime.discovery, 'acquire',
                        lambda retry_s=2.0: SimpleNamespace(release=lambda: released.append(1)))
    monkeypatch.setattr(runtime.discovery, 'remove_core_json', lambda: None)
    core = runtime.Core(port=8123)
    monkeypatch.setattr(core, '_start', lambda: (_ for _ in ()).throw(ValueError('half started')))
    with pytest.raises(ValueError):
        core.start()
    assert released == [1] and core.lock is None and core.db is None
    assert core._done.is_set()                       # wait() cannot hang on a dead Core


def test_a_revoked_local_token_is_reminted_never_reused(db):
    # runtime.py:558 `if auth.live(cred, h):` — the false arm for a revoked
    # credential (auth.py:82 revoked_at). Fail-closed: a token revoked in the database
    # must never be accepted again because its file still exists; inverting the guard
    # hands the CLI back a dead credential and every request 401s forever.
    core = object.__new__(runtime.Core)
    core.db = db
    pid = db.writer.execute(commands.register_principal,
                            {'kind': 'system', 'scopes': ('system',)})['id']
    core.system = Ref('system', pid)
    token = auth.new_token()
    db.writer.execute(commands.register_device, {
        'actor': core.system, 'name': 'local', 'platform': 'tui',
        'token_hash': auth.token_hash(token), 'scopes': list(auth.LOCAL_SCOPES)})
    discovery.write_local_token(token)
    db.writer.execute(_revoke_all, {})
    out = core._ensure_local_token()
    assert out['token'] != token                     # the revoked one is gone
    assert discovery.read_local_token() == out['token']    # and the file followed
    assert count(db, 'tokens') == 2                  # reminted, not reused
    with db.read() as conn:
        old = conn.execute('SELECT revoked_at FROM tokens WHERE token_hash = ?',
                           (auth.token_hash(token),)).fetchone()
    assert old['revoked_at'] is not None


def _revoke_all(tx, *args, **kwargs):
    tx.execute('UPDATE tokens SET revoked_at = ? WHERE revoked_at IS NULL', (T,))


def test_an_unknown_local_token_file_is_reminted(db):
    # runtime.py:554-559 — a token file whose hash no token row knows: `cred` is
    # None, auth.live (auth.py:79-81) says False, and Core must mint. If the None
    # credential were trusted, Core would hand the CLI a credential that cannot
    # authenticate and start anyway.
    core = object.__new__(runtime.Core)
    core.db = db
    pid = db.writer.execute(commands.register_principal,
                            {'kind': 'system', 'scopes': ('system',)})['id']
    core.system = Ref('system', pid)
    discovery.write_local_token('dev_not-a-real-credential')
    out = core._ensure_local_token()
    assert out['token'] != 'dev_not-a-real-credential'
    assert discovery.read_local_token() == out['token'] and count(db, 'tokens') == 1


def test_a_live_local_token_is_kept_and_no_second_device_is_minted(db):
    # runtime.py:558-560, the true arm: the same token survives restarts. Reminting
    # a live credential on every start leaks a device+token row per boot (and
    # invalidates nothing), turning the credential table into a leak.
    core = object.__new__(runtime.Core)
    core.db = db
    pid = db.writer.execute(commands.register_principal,
                            {'kind': 'system', 'scopes': ('system',)})['id']
    core.system = Ref('system', pid)
    token = auth.new_token()
    out = db.writer.execute(commands.register_device, {
        'actor': core.system, 'name': 'local', 'platform': 'tui',
        'token_hash': auth.token_hash(token), 'scopes': list(auth.LOCAL_SCOPES)})
    discovery.write_local_token(token)
    got = core._ensure_local_token()
    assert got == {'token': token, 'principal_id': out['principal_id'],
                   'device_id': out['device_id']}
    assert count(db, 'tokens') == 1 and count(db, 'devices') == 1


def test_a_lost_race_parks_the_mission_and_never_fails_core(db, monkeypatch):
    # runtime.py:215-222, the LOST_RACE arm: VersionConflict between the read and
    # the fire is logged and the mission parked at the version we read — not a Core
    # failure, and stepped again only if the row moves. Remove the park (or re-raise)
    # and a refusal spins the loop forever, or worse, kills Core (exit 3) on the
    # ordinary race the design says is normal.
    mid = ids.new_id('mission')
    put(db, mission(mid))
    eng = FakeEngine()
    eng.outs[mid] = [errors.VersionConflict(mid, 2, 1)]
    loop, fails, waits = engine_loop(db, eng, monkeypatch)
    loop._pass()
    assert fails == [] and loop.state == 'idle'
    assert list(loop.parked) == [mid] and loop.parked[mid][0] == 1    # version we read
    assert loop.wake == {}                             # the pop: no timed wake left over
    loop._pass()
    assert eng.stepped == [mid]                        # parked: not re-stepped, no spin
    db.writer.execute(_bump, {'mid': mid})
    loop._pass()
    assert eng.stepped == [mid, mid]                   # and it wakes when the row moves


def test_an_engine_step_failure_fails_core(db, monkeypatch):
    # runtime.py:174-177 (generic arm) and 179-183 (_failed): an exception that is
    # NOT a lost race marks the loop failed and calls on_fail — Core exits 3. Without
    # on_fail a dead engine thread leaves a healthy-looking HTTP server over a world
    # that never advances.
    put(db, mission('m1'))
    eng = FakeEngine()
    eng.outs['m1'] = [RuntimeError('a real bug')]
    loop, fails, _ = engine_loop(db, eng, monkeypatch)
    loop._run()
    assert loop.state == 'failed' and fails == [1]


def test_the_engine_loop_stops_without_failing_when_already_stopping(db, monkeypatch):
    # runtime.py:169-173 and 174-176: WriterClosed or any exception while the stop
    # flag is already set is a clean 'stopped', never _failed — the shutdown-time
    # race with db.close() must not report exit 3 for a deliberate stop. (The
    # not-stopping WriterClosed arm is tests/v1/integration/test_p21_health.py H12.)
    for exc in (errors.WriterClosed('closed'), RuntimeError('boom')):
        eng = FakeEngine()
        eng.reconcile = [exc]
        loop, fails, _ = engine_loop(db, eng, monkeypatch)
        loop._stop.set()
        loop._run()
        assert loop.state == 'stopped' and fails == []     # would be exit 3 if inverted


def test_the_exec_writer_closed_still_stops_core(db):
    # runtime.py:307-310: unlike the engine loop, ExecLoop's WriterClosed arm leaves
    # state 'stopped' yet still calls on_fail — a manager whose writer died advances
    # nothing, so Core must exit 3 while health never shows 'failed'. Asserting both
    # halves: dropping the call strands executions unwatched.
    eng = FakeManager(booted=True)
    eng.queue = [errors.WriterClosed('closed')]
    fails = []
    loop = runtime.ExecLoop(eng, db, on_fail=lambda: fails.append(1))
    loop._run()
    assert loop.state == 'stopped' and fails == [1]


def test_an_exec_crash_fails_core_unless_the_stop_already_came(db):
    # runtime.py:311-315 (and its `return`): a tick exception with stop unset is
    # 'failed' + on_fail; with stop set it is 'stopped' and NEVER on_fail — without
    # the guard every clean shutdown races a tick and Core exits 3 after a Ctrl+C.
    for stopped, want_state, want_fails in ((False, 'failed', [1]), (True, 'stopped', [])):
        fails = []
        loop_box = {}

        def tick_boom(stopped=stopped, loop_box=loop_box):
            if stopped:
                loop_box['l']._stop.set()
            raise RuntimeError('boom')
        eng = FakeManager(booted=True)
        eng.queue = [tick_boom]
        loop = runtime.ExecLoop(eng, db, on_fail=(lambda fails=fails: fails.append(1)))
        loop_box['l'] = loop
        loop._run()
        assert loop.state == want_state and fails == want_fails


def test_the_world_worker_losing_its_writer_fails_core(db):
    # runtime.py:373-376 + 383-387: a knowledge/world thread that finds the writer
    # closed (not stopping) is _failed → on_fail → exit 3. A worker silently dead
    # while Core keeps serving is the fail-open this arm exists to prevent.
    world = FakeWorld(passes=[errors.WriterClosed('closed')])
    fails = []
    loop = runtime.WorldLoop(world, db, poll_s=0.02, on_fail=lambda: fails.append(1),
                             name='t-world')
    loop._run()
    assert loop.state == 'failed' and fails == [1] and world.sweeps == 1


def test_a_world_crash_while_stopping_is_stopped_not_failed(db):
    # runtime.py:377-381: any exception once the stop flag is set ends 'stopped'
    # with no on_fail — the shutdown teardown can throw (closed connections) and a
    # deliberate stop must never be punished as a crash.
    world_box = {}

    def boom():
        world_box['l']._stop.set()
        raise RuntimeError('teardown raced')

    world = FakeWorld(passes=[boom])
    fails = []
    loop = runtime.WorldLoop(world, db, poll_s=0.02, on_fail=lambda: fails.append(1),
                             name='t-world')
    world_box['l'] = loop
    loop._run()
    assert loop.state == 'stopped' and fails == []


def test_run_reports_a_rival_core_and_exits_1(monkeypatch):
    # runtime.py:663-667: LockHeld names the running Core from core.json, and falls
    # back to '?' when the record is missing or malformed — the operator must never
    # be told 'pid None'. And no banner: nothing started.
    actions = fake_core(monkeypatch, start=discovery.LockHeld('held'))
    monkeypatch.setattr(runtime.discovery, 'read_core_json', lambda: None)
    out, err = io.StringIO(), io.StringIO()
    assert runtime.run(port=8123, out=out, err=err) == 1
    assert 'pid ?' in err.getvalue() and 'port ?' in err.getvalue() and out.getvalue() == ''
    monkeypatch.setattr(runtime.discovery, 'read_core_json',
                        lambda: {'pid': 4242, 'port': 7337, 'create_time': 'x'})
    out2, err2 = io.StringIO(), io.StringIO()
    assert runtime.run(port=8123, out=out2, err=err2) == 1
    assert '4242' in err2.getvalue() and '7337' in err2.getvalue()
    assert 'start' in actions                          # it did try, once per run


def test_run_reports_an_unusable_port_and_exits_2(monkeypatch):
    # runtime.py:668-671: PortInUse maps to exit code 2 with the port named — the
    # CLI's contract for 'something else holds 7337'. Swapping 1 and 2 here breaks
    # every script that distinguishes the two refusals.
    fake_core(monkeypatch, start=runtime.PortInUse('bind refused'))
    out, err = io.StringIO(), io.StringIO()
    assert runtime.run(port=8123, out=out, err=err) == 2
    assert '8123' in err.getvalue() and out.getvalue() == ''


def test_run_reports_a_refused_start_and_exits_1(monkeypatch):
    # runtime.py:672-674: RefuseStart (the loose-token refusal) exits 1 and echoes
    # the reason; swallowing it (exit 0) would report a clean run that never was.
    fake_core(monkeypatch, start=runtime.RefuseStart('token file is loose'))
    out, err = io.StringIO(), io.StringIO()
    assert runtime.run(port=8123, out=out, err=err) == 1
    assert 'token file is loose' in err.getvalue()


def test_run_stops_cleanly_and_returns_the_core_exit_code(monkeypatch):
    # runtime.py:676-690: banner to out, warning to err, a stop handler installed,
    # wait()'s code returned, and core.stop() run afterwards — an exit path that
    # forgets stop() leaks the writer thread and keeps run/core.lock until death.
    actions = fake_core(monkeypatch, code=3, warning='a loose home')
    seen = []
    monkeypatch.setattr(runtime.signal, 'signal', lambda *a: seen.append(a))
    out, err = io.StringIO(), io.StringIO()
    assert runtime.run(port=8123, out=out, err=err) == 3
    assert 'http://127.0.0.1:8123' in out.getvalue()
    assert 'a loose home' in err.getvalue()
    assert seen                                          # SIGTERM (SIGBREAK on Windows)
    assert actions[-1] == 'stop'


def test_run_turns_ctrl_c_into_a_clean_exit_0(monkeypatch):
    # runtime.py:686-688: KeyboardInterrupt from wait() is exit 0, and stop() still
    # runs; without the handler Ctrl+C exits nonzero and skips the teardown.
    actions = fake_core(monkeypatch, wait=KeyboardInterrupt())
    monkeypatch.setattr(runtime.signal, 'signal', lambda *a: None)
    out, err = io.StringIO(), io.StringIO()
    assert runtime.run(port=8123, out=out, err=err) == 0
    assert actions[-1] == 'stop'


def fake_core(monkeypatch, **behaviour):
    actions = []

    class Fake:
        def __init__(self, *, port, ports, remote_hosts):
            actions.append(('init', port))
            self.warning = behaviour.get('warning')

        def start(self):
            actions.append('start')
            if behaviour.get('start') is not None:
                raise behaviour['start']

        def wait(self):
            actions.append('wait')
            if behaviour.get('wait') is not None:
                raise behaviour['wait']
            return behaviour.get('code', 0)

        def stop(self):
            actions.append('stop')
    monkeypatch.setattr(runtime, 'Core', Fake)
    return actions


# ── boundary values ──────────────────────────────────────────────────────────


def test_the_stub_ports_default_is_the_fail_closed_one():
    # runtime.py:132-133 `getattr(self.policy, 'is_stub', True) is not False`:
    # a policy that says nothing is treated as a stub. Changing the default to
    # False would let health claim 'real' ports for an unwired Core.
    stub = runtime.Ports.stub.fget
    assert stub(SimpleNamespace(policy=SimpleNamespace(is_stub=False))) is False
    assert stub(SimpleNamespace(policy=SimpleNamespace(is_stub=True))) is True
    assert stub(SimpleNamespace(policy=object())) is True


def test_the_engine_steps_higher_priority_first_and_skips_settled_missions(db, monkeypatch):
    # runtime.py:193-197: `key=lambda m: -m['priority']` and the
    # `m['state'] not in engine.SETTLED` filter. Inverting the sign dispatches the
    # low-priority mission first; dropping the filter steps a COMPLETED mission
    # again — the engine moving a settled mission is exactly what the design forbids.
    hi, done, low = (ids.new_id('mission') for _ in range(3))
    put(db, mission(hi, priority=5), mission(done, state='COMPLETED', priority=9),
        mission(low))
    eng = FakeEngine()
    loop, _fails, waits = engine_loop(db, eng, monkeypatch)
    loop._pass()
    assert eng.stepped == [hi, low] and waits == []     # progressed: no wait


def test_a_parked_mission_wakes_only_when_a_version_or_a_verdict_moves(db, monkeypatch):
    # runtime.py:203-206 (the park/`continue`) and _stamp runtime.py:242-252: a step
    # that changed nothing parks the mission; a mission-version bump, a task row and
    # a verification reached only through `verifications JOIN plans` each wake it —
    # lose the verifications arm and a recorded verdict never gets its `advance`
    # judged (P13), and a re-pass that re-reads the same version must not re-step.
    mid = ids.new_id('mission')
    put(db, mission(mid))
    eng = FakeEngine(default={'changed': False})
    loop, _fails, waits = engine_loop(db, eng, monkeypatch)
    loop._pass()                                              # parked at the boot stamp
    loop.wake[mid] = time.time() + 3600                       # a due time not yet reached
    loop._pass()
    assert eng.stepped == [mid]                               # parked + not due: skipped
    loop.wake[mid] = time.time() - 3600                       # now >= due
    loop._pass()
    assert eng.stepped == [mid] * 2                           # the boundary itself
    db.writer.execute(_bump, {'mid': mid})
    loop._pass()
    assert eng.stepped == [mid] * 3                           # its own version moved
    pl, tk, vf = ids.new_id('plan'), ids.new_id('task'), ids.new_id('verification')
    put(db, plan(mid, pl), task(tk, pl, mid))
    loop._pass()
    assert eng.stepped == [mid] * 4                           # a task moved (P11 D28)
    put(db, verification(vf, pl))
    loop._pass()
    assert eng.stepped == [mid] * 5                           # a verdict moved (P13)
    assert waits and all(t <= 0.5 for t in waits)


def test_stop_midway_abandons_the_rest_of_the_pass(db, monkeypatch):
    # runtime.py:199-200 `if self._stop.is_set(): return` inside the step loop:
    # a stop between missions must skip the rest AND the idle bookkeeping — remove
    # it and a stopping Core keeps stepping missions (and publishes an observed_seq
    # for work it never finished) until its whole pass drains.
    a, b = ids.new_id('mission'), ids.new_id('mission')
    put(db, mission(a), mission(b), event(a))
    eng = FakeEngine()
    loop, _fails, waits = engine_loop(db, eng, monkeypatch)
    eng.outs[a] = [lambda mid: (loop._stop.set(), {'changed': True})[1]]
    loop._pass()
    assert eng.stepped == [a] and waits == []
    assert loop.observed_seq == 0 and loop.state == 'running'


def test_the_idle_wait_clamps_to_zero_and_drops_a_dead_wake(db, monkeypatch):
    # runtime.py:232-239: a park with a wake_at already past must wait 0.0, never a
    # negative timeout (the max(0.0, ...) clamp); a wake_at of None is pruned
    # (`and w`) so the next wait takes idle_s, not min() over None; and the idle
    # pass records exactly the head it read (`observed_seq, state = head, 'idle'`).
    mid = ids.new_id('mission')
    now = time.time()
    eng = FakeEngine()
    eng.outs[mid] = [{'changed': False, 'wake_at': now + 30},
                     {'changed': False, 'wake_at': now - 5},   # the due-time arrival
                     {'changed': False}]
    loop, _fails, waits = engine_loop(db, eng, monkeypatch)
    put(db, mission(mid), event(mid))
    loop._pass()                                                # parked, due in +30 s
    assert loop.state == 'idle' and loop.status()['parked'] == 1
    with db.read() as conn:
        assert loop.observed_seq == outbox.head(conn)           # the head it read
    loop._pass()                                                # skipped: future due
    loop.wake[mid] = time.time() - 5                            # due has passed
    loop._pass()                                                # stepped; parked due-past
    assert waits[-1] == 0.0                                     # the clamp, not -5.x
    loop._pass()                                                # stepped; wake_at None
    assert eng.stepped == [mid] * 3
    assert waits == [0.5, 0.5, 0.0, 0.5]                        # idle_s, clamp, idle_s
    assert loop.wake == {}                                      # the `and w` prune


def test_health_is_armed_only_while_the_stop_sentinel_is_absent(monkeypatch):
    # runtime.py:574 `'armed': not paths_disarmed()` and 256-257: the e-stop file
    # must read as NOT armed. Drop the `not` (or cache the value) and health swears
    # an e-stopped Core is armed while every policy decision is DENY.
    core = health_core()
    assert core.health()['armed'] is True            # fresh home: no sentinel
    os.makedirs(paths.run_dir(), exist_ok=True)
    with open(paths.stop_sentinel(), 'wb') as f:
        f.write(b'')
    assert runtime.paths_disarmed() is True
    assert core.health()['armed'] is False


def test_never_started_workers_read_stopped_in_health():
    # runtime.py:578-586, the `else {'state': 'stopped', 'pending': 0}` arms: a
    # worker that was never built (a stub-brain Core has no planner) must never be
    # reported idle — health would claim five live workers where none exist.
    core = health_core(stub=False)
    h = core.health()
    assert h['core']['ports'] == 'real'
    assert health_core(stub=True).health()['core']['ports'] == 'stub'
    for name in ('plan', 'policy', 'verify', 'automation', 'metrics'):
        assert h[name] == {'state': 'stopped', 'pending': 0}


def test_a_stopped_worker_hides_pending_and_detail(db):
    # runtime.py:349-354: `pending()` is read only while idle/running, and `detail()`
    # merged only then — after the thread stopped, its worker object may be
    # half-torn-down; polling it through health would resurrect a dead read, and a
    # stopped worker reporting pending>0 would keep the judge waiting forever.
    world = FakeWorld(pending=7, detail={'held': 2})
    loop = runtime.WorldLoop(world, db, poll_s=0.02, on_fail=None, name='t-world')
    loop.state = 'idle'
    assert loop.status() == {'state': 'idle', 'pending': 7, 'held': 2}
    loop.state = 'stopped'
    assert loop.status() == {'state': 'stopped', 'pending': 0}   # no 'held' key either


# ── error and shutdown paths ─────────────────────────────────────────────────


def test_the_exec_loop_never_ticks_before_the_boot_sweep_and_counts_live_procs(db):
    # runtime.py:292-294: ExecLoop waits for `manager.booted` — the engine's orphan
    # sweep — and a stop arriving during that wait ends the thread cleanly. Ticking
    # before the sweep adopts-or-kills a previous Core's processes twice; the only
    # way to prove the gate is to arrive while booted is False and a stop is still
    # 0.15 s away: without the wait the first tick (a rigged AssertionError) fires
    # and fails Core. status()['live'] is the watched-process count health shows
    # (runtime.py:287-290).
    eng = FakeManager(booted=False, procs={'p1': 1, 'p2': 2})
    eng.queue = [AssertionError('a tick before the sweep would adopt orphans twice')]
    fails = []
    loop = runtime.ExecLoop(eng, db, on_fail=lambda: fails.append(1))
    timer = threading.Timer(0.15, loop._stop.set)   # the stop arrives during the boot wait
    timer.start()
    try:
        loop._run()
    finally:
        timer.cancel()
    assert eng.ticks == 0 and fails == [] and loop.state == 'stopped'
    assert loop.status() == {'state': 'stopped', 'live': 2, 'observed_seq': 0}


def test_an_idle_exec_tick_publishes_the_head_it_read(db):
    # runtime.py:301-306: the tick's False side sets 'idle' together with the head
    # read at the TOP of the same iteration — reading it after the tick instead (or
    # dropping both) is the G01 bug: a process that exited and committed during the
    # tick would be invisible to the idle signal.
    put(db, event('m1'))
    eng = FakeManager(booted=True)

    def idle_then_stop():
        loop._stop.set()
        return False
    eng.queue = [idle_then_stop]
    loop = runtime.ExecLoop(eng, db, on_fail=lambda: pytest.fail('idle tick failed Core'))
    loop._run()
    assert eng.ticks == 1 and loop.state == 'stopped'
    with db.read() as conn:
        assert loop.observed_seq == outbox.head(conn) == 1


def test_the_world_clears_its_wake_flag_after_each_wait(db, monkeypatch):
    # runtime.py:366-371: a changed pass `continue`s immediately; the idle pass
    # waits on (stop or wake) and then clears the wake flag — without the clear a
    # single wake() makes every later wait return instantly (busy spin) forever.
    world = FakeWorld(passes=[{'changed': True}, {'changed': False}])
    loop = runtime.WorldLoop(world, db, poll_s=0.02, on_fail=None, name='t-world')
    loop._wake.set()                                    # a stale flag from boot

    def fake_wait(seen, timeout, until=None):
        loop._wake.set()                                # a wake() ends the wait
        loop._stop.set()                                # ... and the stop ends the loop
        return db.writer.commit_count
    monkeypatch.setattr(db.writer, 'wait_commit', fake_wait)
    loop._run()
    assert world.passes == 2 and world.sweeps == 1
    assert loop.state == 'stopped' and loop._wake.is_set() is False    # cleared


def test_version_falls_back_to_dev_when_the_package_is_not_installed(monkeypatch):
    # runtime.py:81-86: importlib.metadata raising (a source checkout, no dist-info)
    # must not stop Core from starting — VERSION becomes 'dev'. Raising here would
    # crash every `archeus core` run from a plain git clone.
    def boom(name):
        raise Exception('no distribution named %s' % name)
    monkeypatch.setattr(importlib.metadata, 'version', boom)
    assert runtime._version() == 'dev'


def test_stop_runs_start_backwards_and_drops_the_queue_on_demand(monkeypatch):
    # runtime.py:609-651 (§5.4): api/sse, then server, then the workers in exactly
    # the reverse of start, then the database, then core.json and the lock — a lock
    # released before the writer closes lets a second Core open the same database.
    # drain=False must reach db.close (a kill drops queued commands, never runs
    # them), and a second stop() must not double-close the db, server or lock.
    log = []
    core = object.__new__(runtime.Core)
    core._done = threading.Event()
    core._log_handler = logging.NullHandler()
    core.api = Spy(log, 'api')
    core.server = Spy(log, 'server')
    for name in ('metrics', 'automation', 'policy', 'plan', 'verify', 'intent',
                 'knowledge', 'world', 'exec', 'loop'):
        setattr(core, name, Spy(log, name))
    core.db = Spy(log, 'db')
    core.lock = Spy(log, 'lock')
    monkeypatch.setattr(runtime.discovery, 'remove_core_json',
                        lambda: log.append(('remove_core_json', (), {})))
    core.stop(drain=False)
    names = [p for p, _a, _k in log]
    assert names[0] == 'api.sse.close_all'
    assert names[1:3] == ['server.shutdown', 'server.server_close']
    assert [n for n in names if n.endswith('.stop')] == [
        '%s.stop' % n for n in ('metrics', 'automation', 'policy', 'plan', 'verify',
                                'intent', 'knowledge', 'world', 'exec', 'loop')]
    assert (names.index('loop.stop') < names.index('db.close')
            < names.index('remove_core_json') < names.index('lock.release'))
    assert [k for p, _a, k in log if p == 'db.close'] == [{'drain': False}]
    assert core.api is None and core.server is None and core.db is None
    assert core.lock is None and core._done.is_set()
    core.stop()                                    # idempotent where it counts
    assert [p for p, _a, _k in log[len(names):] if not p.endswith('.stop')] == []


def test_the_engine_failure_wakes_the_wait_with_exit_code_3():
    # runtime.py:596-598 + 603-607: the on_fail Core hands every loop sets exit_code
    # 3 and releases wait() — a failed engine that never wakes wait() hangs the
    # foreground process until Ctrl+C, hiding the crash exit code from any wrapper.
    core = object.__new__(runtime.Core)
    core._done = threading.Event()
    core.exit_code = 0
    core._engine_failed()
    assert core.exit_code == 3 and core.wait() == 3

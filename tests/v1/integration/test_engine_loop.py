"""The Core's engine loop (p3.5b design gate §3 D4, A2, A3): one engine thread
beside the HTTP threads. A step that changes nothing parks its mission until a
command moves it; a lost race with an HTTP command is skipped, never fatal; a
refused move is never retried in a loop."""

import threading
import time

from archeus.core import engine, ports as P, runtime
from v1.judge.http import TempCore


class CountingBrain:
    def __init__(self, gate=None):
        self.calls, self.gate = 0, gate
        self.inner = P.FixedPlanBrain(engine.SKELETON_PLAN)

    def call(self, schema, prompt, *, context=None):
        self.calls += 1
        if self.gate is not None:
            self.gate.wait(30)
        return self.inner.call(schema, prompt, context=context)


def _mission(tc, key='m'):
    r = tc.http('POST', '/v1/missions', body={'title': 't', 'objective': 'o',
                                              'idempotency_key': key})
    assert r.status == 200, r.body
    return r.json()['id']


def _state(tc, mid):
    return tc.http('GET', '/v1/missions/' + mid).json()['state']


def _engine(tc):
    return tc.http('GET', '/v1/health').json()['engine']


def _wait(fn, timeout=20, what='condition'):
    deadline = time.monotonic() + timeout
    while not fn():
        assert time.monotonic() < deadline, 'timed out: %s' % what
        time.sleep(0.02)


def test_a_denied_mission_parks_instead_of_asking_the_brain_forever(archeus_home):
    brain = CountingBrain()
    tc = TempCore(archeus_home, idle_s=0.05, ports=runtime.Ports(
        policy=P.FixedPolicy('DENY'), brain=brain)).start()
    try:
        mid = _mission(tc)
        # P9 (D11, D12): the denial is recorded and the mission BLOCKED for it —
        # settled, so the engine has nothing more to ask the brain about
        _wait(lambda: _engine(tc)['state'] == 'idle' and _state(tc, mid) == 'BLOCKED',
              what='blocked on the denial')
        asked = brain.calls
        time.sleep(1.0)                          # twenty idle wake-ups at 0.05 s
        assert brain.calls == asked <= 2, 'the engine re-asks a denied mission'
        assert _engine(tc)['state'] == 'idle'
        # another mission's commits wake the engine; the blocked one stays blocked
        other = _mission(tc, 'other')
        _wait(lambda: _state(tc, other) == 'BLOCKED', what='the second one blocked')
        time.sleep(0.5)
        assert brain.calls == asked * 2 and _state(tc, mid) == 'BLOCKED'
    finally:
        tc.stop()


def test_a_pause_racing_the_engine_is_a_lost_race_not_a_failure(archeus_home, monkeypatch):
    """The engine reads EXECUTING and decides to dispatch; the user pauses in
    between; the stale dispatch is refused by the application layer and the
    engine carries on — logged, parked, never a failure (A2)."""
    reached, release = threading.Event(), threading.Event()
    real = engine.Engine._start

    def held(self, m, t):
        reached.set()
        release.wait(30)
        return real(self, m, t)
    monkeypatch.setattr(engine.Engine, '_start', held)
    tc = TempCore(archeus_home, idle_s=0.05).start()
    try:
        mid = _mission(tc)
        assert reached.wait(20), 'the engine never reached dispatch'
        r = tc.http('POST', '/v1/missions/%s/pause' % mid, body={'idempotency_key': 'p'})
        assert r.status == 200 and r.json()['state'] == 'PAUSED'
        monkeypatch.setattr(engine.Engine, '_start', real)
        release.set()
        _wait(lambda: _engine(tc)['state'] == 'idle', what='idle after the lost race')
        assert _state(tc, mid) == 'PAUSED'                 # the stale dispatch was refused
        assert not [e for e in tc.client().events(0) if e['type'] == 'execution.intent']
        r = tc.http('POST', '/v1/missions/%s/resume' % mid, body={'idempotency_key': 'r'})
        assert r.status == 200
        _wait(lambda: _state(tc, mid) == 'COMPLETED', what='COMPLETED after resume')
        assert _engine(tc)['state'] in ('idle', 'running')
    finally:
        release.set()
        tc.stop()


def test_the_engine_wakes_on_a_commit_not_on_its_idle_timeout(archeus_home):
    tc = TempCore(archeus_home, idle_s=30).start()
    try:
        _wait(lambda: _engine(tc)['state'] == 'idle', what='idle')
        t0 = time.monotonic()
        mid = _mission(tc)
        _wait(lambda: _state(tc, mid) == 'COMPLETED', 10, 'COMPLETED')
        assert time.monotonic() - t0 < 10, 'the engine slept through the commit'
    finally:
        tc.stop()


def _held_collect(monkeypatch):
    """The shape the CI failures had, made deterministic: the agent's last line
    is read (and reported) while its process is still exiting, and the exit is
    seen only a couple of passes later, so the tick that collects it commits
    nothing before its end. That tick is held between forgetting the process
    and committing the end (`_facts` runs between the two)."""
    from archeus.core.execution.manager import ExecutionManager
    from archeus.harnesses.fake import FakeHarness
    reached, release = threading.Event(), threading.Event()
    real_facts, real_status, lag = ExecutionManager._facts, FakeHarness.status, {}

    def held(self, e, p):
        reached.set()
        release.wait(30)
        return real_facts(self, e, p)

    def exiting(self, handle):
        st = real_status(self, handle)
        if st.state == 'exited' and lag.get(handle.execution_id, 0) < 2:
            lag[handle.execution_id] = lag.get(handle.execution_id, 0) + 1
            return type(st)('running')
        return st
    monkeypatch.setattr(ExecutionManager, '_facts', held)
    monkeypatch.setattr(FakeHarness, 'status', exiting)
    return reached, release


def _an_end_being_recorded_is_not_idle(archeus_home, monkeypatch, *, restart):
    """G01: the judge read "nothing advances" (execution ENDED_OK, task
    VERIFYING, every loop idle) because health said the exec loop was idle,
    with no live process, while the tick collecting that process had yet to
    commit its end. Core was never stuck; its idle signal was false."""
    reached, release = _held_collect(monkeypatch)
    tc = TempCore(archeus_home, idle_s=0.05, ports=runtime.Ports(
        brain=P.FixedPlanBrain(engine.SKELETON_PLAN),
        scenarios={'work': [{'sleep': 2}]})).start()
    try:
        mid = _mission(tc)
        _wait(lambda: [e for e in tc.client().events(0) if e['type'] == 'execution.started'],
              what='execution.started')
        if restart:
            tc.restart(kill=True)       # the new Core adopts the live process
        assert reached.wait(30), 'the process was never collected'
        assert _state(tc, mid) == 'EXECUTING'
        assert not tc.client()._idle(), 'health reads idle while an end is uncommitted'
        release.set()
        _wait(lambda: _state(tc, mid) == 'COMPLETED', what='COMPLETED')
        started = [e for e in tc.client().events(0) if e['type'] == 'execution.started']
        assert len(started) == 1
    finally:
        release.set()
        tc.stop()


def test_an_end_being_recorded_is_not_idle(archeus_home, monkeypatch):
    _an_end_being_recorded_is_not_idle(archeus_home, monkeypatch, restart=False)


def test_an_adopted_end_being_recorded_is_not_idle(archeus_home, monkeypatch):
    _an_end_being_recorded_is_not_idle(archeus_home, monkeypatch, restart=True)


class HeldVerifier(P.ScriptedVerifier):
    """Holds each of the first `hold` task verifications until the test lets
    it go, so a Core can be killed with its task in VERIFYING."""

    def __init__(self, hold):
        super().__init__()
        self.hold, self.held = hold, []

    def verify(self, subject):
        if subject.kind == 'task' and len(self.held) < self.hold:
            gate = threading.Event()
            self.held.append(gate)
            gate.wait(30)
        return super().verify(subject)


def test_a_task_left_verifying_by_two_kills_is_verified_once(archeus_home):
    """VERIFYING is durable state, not a wake-up: every Core's engine steps
    every unsettled mission on its first pass and verifies a VERIFYING task
    first. A killed engine's late verdict cannot land (its writer is closed)
    and a second one could not either (the transition's guard requires
    VERIFYING), so the task leaves VERIFYING exactly once."""
    verifier = HeldVerifier(hold=2)
    tc = TempCore(archeus_home, idle_s=0.05, ports=runtime.Ports(
        brain=P.FixedPlanBrain(engine.SKELETON_PLAN), verifier=verifier)).start()
    try:
        mid = _mission(tc)
        for n in (1, 2):
            _wait(lambda n=n: len(verifier.held) == n, what='verification %d held' % n)
            loop = tc.core.loop
            tc.core.stop(drain=False)           # killed with the task in VERIFYING
            verifier.held[-1].set()             # its late verdict meets a closed writer
            loop.join(10)
            tc.core = None
            tc.start()
        _wait(lambda: _state(tc, mid) == 'COMPLETED', what='COMPLETED')
        moves = [(e['payload']['from'], e['payload']['to']) for e in tc.client().events(0)
                 if e['type'] == 'task.state_changed']
        assert moves.count(('RUNNING', 'VERIFYING')) == 1
        assert moves.count(('VERIFYING', 'SUCCEEDED')) == 1
        assert [m for m in moves if m[0] == 'VERIFYING'] == [('VERIFYING', 'SUCCEEDED')]
    finally:
        for gate in verifier.held:
            gate.set()
        tc.stop()


def test_there_is_one_engine_thread_and_it_is_never_restarted(archeus_home):
    tc = TempCore(archeus_home).start()
    try:
        names = [t.name for t in threading.enumerate()]
        assert names.count('archeus-engine') == 1
        assert names.count('archeus-writer') == 1
        loop = tc.core.loop
        _mission(tc)
        assert tc.core.loop is loop
    finally:
        tc.stop()
    _wait(lambda: 'archeus-engine' not in [t.name for t in threading.enumerate()], 10,
          'the engine thread to finish')

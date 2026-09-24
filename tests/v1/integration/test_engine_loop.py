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
        _wait(lambda: _engine(tc)['state'] == 'idle' and _engine(tc)['parked'] == 1,
              what='parked')
        asked = brain.calls
        time.sleep(1.0)                          # twenty idle wake-ups at 0.05 s
        assert brain.calls == asked <= 2, 'the engine re-asks a denied mission'
        assert _state(tc, mid) == 'REASONING'    # DENY writes nothing and moves nothing
        assert _engine(tc)['state'] == 'idle'
        # another mission's commits wake the engine; the parked one stays parked
        other = _mission(tc, 'other')
        _wait(lambda: _engine(tc)['parked'] == 2, what='the second one parked')
        time.sleep(0.5)
        assert brain.calls == asked * 2 and _state(tc, other) == 'REASONING'
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

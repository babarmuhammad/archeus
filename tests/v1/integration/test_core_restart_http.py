"""Core killed mid-execution, restarted — all observed over HTTP (p3.5b design
gate §10 H1–H4, §18.1; P11 p11-design-gate §15.3).

P3.5b reconciled and never adopted: the orphan was killed and the task ran
again. P11 replaces that with adopt-or-reconcile, which the P3.5b gate
scheduled (§4.9 of the P11 gate): a live orphan is ADOPTED — its process runs
to its end once, the new Core tails its stream and records its exit. What both
phases keep, and these tests still prove: at no instant are two executions of
one task live, and seq never goes backwards."""

import os
import time

from archeus.infra import paths
from claude_sessions import proc
from v1.judge.http import CoreProcess

SLOW = {'work': [{'sleep': 60}]}
#: long enough to outlive the first Core, short enough to finish under the second
ADOPTABLE = {'work': [{'emit': {'type': 'working'}}, {'sleep': 4}]}


def _wait(pred, timeout=30, what='condition'):
    deadline = time.monotonic() + timeout
    while True:
        got = pred()
        if got:
            return got
        assert time.monotonic() < deadline, 'timed out waiting for %s' % what
        time.sleep(0.05)


def _events(core, type_=None):
    out = core.client().events(0)
    return [e for e in out if type_ is None or e['type'] == type_]


def _mission(core, mid):
    return core.http('GET', '/v1/missions/' + mid).json()


def _create(core):
    r = core.http('POST', '/v1/missions', body={'title': 't', 'objective': 'o',
                                                'idempotency_key': 'k-' + str(time.monotonic_ns())})
    assert r.status == 200, r.body
    return r.json()['id']


def _started(core):
    """The first execution.started: (execution id, pid, create_time)."""
    e = _wait(lambda: _events(core, 'execution.started'), what='execution.started')[0]
    return e['subject']['id'], e['payload']['pid'], e['payload']['create_time']


def _moves(core, execution_id):
    return [(e['payload']['from'], e['payload']['to'])
            for e in _events(core, 'execution.state_changed')
            if e['subject']['id'] == execution_id]


def _alive(pid, create_time):
    return proc.process_create_time(pid) == create_time


def _never_two_live(events):
    """H2: replay the events; per task, at most one execution between its
    intent and its end."""
    live, task_of = {}, {}
    for e in events:
        if e['type'] == 'execution.intent':
            t = e['payload']['task_id']
            task_of[e['subject']['id']] = t
            live.setdefault(t, set()).add(e['subject']['id'])
            assert len(live[t]) == 1, 'two live executions of %s at seq %d' % (t, e['seq'])
        elif e['type'] == 'execution.ended':
            live[task_of[e['subject']['id']]].discard(e['subject']['id'])


def test_core_killed_mid_execution_adopts_over_http_and_the_mission_completes(archeus_home):
    first = CoreProcess(archeus_home, scenarios=ADOPTABLE).start()
    mid = _create(first)
    old, pid, ctime = _started(first)
    assert _alive(pid, ctime)
    first.kill()
    assert _alive(pid, ctime), 'the fake child is detached: it outlives Core'

    audit = os.path.join(str(archeus_home), 'audit.txt')
    again = CoreProcess(archeus_home, audit=[old, audit]).start()
    try:
        done = _wait(lambda: _mission(again, mid)['state'] == 'COMPLETED', 60, 'COMPLETED')
        assert done
        adopted = [e for e in _events(again, 'execution.adopted') if e['subject']['id'] == old]
        assert adopted and adopted[0]['payload']['pid'] == pid
        assert _moves(again, old)[-1] == ('RUNNING', 'ENDED_OK')      # it ran once, to its end
        attempts = [e['payload']['attempt'] for e in _events(again, 'execution.intent')]
        assert attempts == [1]
        _never_two_live(_events(again))                                     # H2
        # P11: the registry exists (the Core-less e-stop needs it), and adoption
        # tails the orphan's stream from the offset the dead Core recorded
        assert os.path.exists(os.path.join(paths.run_dir(), 'processes.jsonl'))
        assert os.path.exists(audit)
    finally:
        again.kill()


def test_the_boot_sweep_reaches_an_orphan_under_a_paused_mission(archeus_home):
    """H3 / A35: PAUSED is settled, so the engine never steps it; only the boot
    sweep reaches its orphan — before any resume, without moving the mission.
    P11: the sweep adopts it and, the mission being paused, asks it to pause;
    with no tool boundary the pause times out into a stop (uncharged), and the
    resume runs the task again."""
    first = CoreProcess(archeus_home, scenarios=SLOW).start()
    mid = _create(first)
    old, pid, ctime = _started(first)
    r = first.http('POST', '/v1/missions/%s/pause' % mid, body={'idempotency_key': 'p'})
    assert r.status == 200 and r.json()['state'] == 'PAUSED'
    first.kill()

    gate = os.path.join(str(archeus_home), 'sweep-gate')
    again = CoreProcess(archeus_home, hold_sweep=gate, pause_timeout=1.0).start()
    try:
        health = again.http('GET', '/v1/health').json()['engine']
        assert health['state'] == 'reconciling'
        assert _alive(pid, ctime)
        open(gate, 'w').close()
        _wait(lambda: _moves(again, old) and _moves(again, old)[-1] == ('STOPPING',
                                                                         'ENDED_KILLED'),
              30, 'the paused orphan stopped')
        assert ('RUNNING', 'PAUSING') in _moves(again, old)
        _wait(lambda: not _alive(pid, ctime), 10, 'the orphan to die')
        assert _mission(again, mid)['state'] == 'PAUSED'                # not moved
        assert [e['payload']['attempt'] for e in _events(again, 'execution.intent')] == [1]

        r = again.http('POST', '/v1/missions/%s/resume' % mid, body={'idempotency_key': 'r'})
        assert r.status == 200
        _wait(lambda: _mission(again, mid)['state'] == 'COMPLETED', 60, 'COMPLETED')
        assert [e['payload']['attempt'] for e in _events(again, 'execution.intent')] == [1, 2]
        _never_two_live(_events(again))
    finally:
        again.kill()


def test_seq_keeps_increasing_across_a_restart(archeus_home):
    """B7 (the order half): ids never go backwards or repeat across Cores."""
    first = CoreProcess(archeus_home).start()
    mid = _create(first)
    _wait(lambda: _mission(first, mid)['state'] == 'COMPLETED', 30, 'COMPLETED')
    before = [e['seq'] for e in _events(first)]
    first.kill()
    again = CoreProcess(archeus_home).start()
    try:
        _create(again)
        after = [e['seq'] for e in _events(again)]
        assert after[:len(before)] == before
        assert after == sorted(set(after)) and after[-1] > before[-1]
    finally:
        again.kill()

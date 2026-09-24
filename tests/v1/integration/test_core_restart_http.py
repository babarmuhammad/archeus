"""Core killed mid-execution, restarted, reconciled — all observed over HTTP
(p3.5b design gate §10 H1–H4, §18.1). A restart reconciles and never adopts:
the old attempt ends before the task gets a new one, and at no instant are two
executions of one task live."""

import os
import time

from archeus.infra import paths
from claude_sessions import proc
from v1.judge.http import CoreProcess

SLOW = {'work': [{'sleep': 60}]}


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


def test_core_killed_mid_execution_reconciles_over_http_and_the_mission_completes(archeus_home):
    first = CoreProcess(archeus_home, scenarios=SLOW).start()
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
        _wait(lambda: not _alive(pid, ctime), 10, 'the orphan to die')
        assert _moves(again, old)[-1] == ('LOST', 'ENDED_KILLED')
        ended = [e for e in _events(again, 'execution.ended') if e['subject']['id'] == old]
        assert ended[0]['payload']['exit_reason'] == 'lost'
        attempts = [e['payload']['attempt'] for e in _events(again, 'execution.intent')]
        assert attempts == [1, 2]
        _never_two_live(_events(again))                                     # H2
        # H4: reconciliation reads no registry and no output stream
        assert not os.path.exists(os.path.join(paths.run_dir(), 'processes.jsonl'))
        assert not os.path.exists(audit), open(audit).read()
    finally:
        again.kill()


def test_the_boot_sweep_reconciles_an_orphan_under_a_paused_mission(archeus_home):
    """H3 / A35: PAUSED is settled, so the engine never steps it; only the boot
    sweep reaches its orphan — before any resume, without moving the mission."""
    first = CoreProcess(archeus_home, scenarios=SLOW).start()
    mid = _create(first)
    old, pid, ctime = _started(first)
    r = first.http('POST', '/v1/missions/%s/pause' % mid, body={'idempotency_key': 'p'})
    assert r.status == 200 and r.json()['state'] == 'PAUSED'
    first.kill()

    gate = os.path.join(str(archeus_home), 'sweep-gate')
    again = CoreProcess(archeus_home, hold_sweep=gate).start()
    try:
        health = again.http('GET', '/v1/health').json()['engine']
        assert health['state'] == 'reconciling'
        assert _alive(pid, ctime)
        open(gate, 'w').close()
        _wait(lambda: again.http('GET', '/v1/health').json()['engine']['state'] == 'idle',
              what='idle after the sweep')
        assert _moves(again, old)[-1] == ('LOST', 'ENDED_KILLED')
        assert not _alive(pid, ctime)
        assert _mission(again, mid)['state'] == 'PAUSED'                # not moved
        assert [e['payload']['attempt'] for e in _events(again, 'execution.intent')] == [1]

        r = again.http('POST', '/v1/missions/%s/resume' % mid, body={'idempotency_key': 'r'})
        assert r.status == 200
        _wait(lambda: _mission(again, mid)['state'] == 'COMPLETED', 60, 'COMPLETED')
        assert [e['payload']['attempt'] for e in _events(again, 'execution.intent')] == [1, 2]
        _never_two_live(_events(again))
        assert not os.path.exists(os.path.join(paths.run_dir(), 'processes.jsonl'))
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

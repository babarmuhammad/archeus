# ruff: noqa: F811  (the imported candidate/quiet_core fixtures are taken as arguments)
"""T-1112 · highest-risk uncovered branches of archeus/core/pv20.py lines 1-205 (HEAD
56d53504, 2026-11-10), fail-closed and denial first, then boundaries, then error paths,
then orderings forced with seams and events instead of sleeps. Changed since 0b17a5b4
(2cd8a573, 6027a5f9): quiesce and Job-only disposal, so these branches are the card's
authorized overlap targets.

Final selected branches (closest existing coverage in tests/v1/unit/test_pv20_activate.py
was checked with a sys.settrace line recorder over that file and test_pv20_runtime_stage.py
first; the line hit itself proves nothing where no assertion reads the effect):

FAIL-CLOSED / DENIAL
  1. pv20.py:125-126  realpath/normcase of ledger_dir raising is refused as
     `invalid_parameters` — lines 125/126 hit by no existing test.
  2. pv20.py:59-62   quiesce() closes admission even when Broker.close dies in a
     revoke callback (a live grant's listener will not close).
  3. pv20.py:59-66   a second quiesce()/close() never reopens admission and never
     reruns a registered callback.
BOUNDARIES
  4. pv20.py:41,145  NativeBindings.jobs defaults to None and activate_pv20 then
     builds the default `isolation.WindowsBoundary()` for the Core-held boundary.
  5. pv20.py:75-76   _dispose(None) (node never built during a rollback) is harmless;
     hit only through rollback, where _rollback:91-92 would swallow its crash.
  6. pv20.py:78-85   an empty held-job set fences nothing and raises nothing.
ERROR PATHS
  7. pv20.py:81-85   with several fence faults every Job is still attempted with
     wait=0 and the FIRST error survives (`first = first or error` keep side).
  8. pv20.py:69-85   disposal only fences: never teardown, profile deletion, record
     removal, quarantine or a failure note.
  9. pv20.py:81-85,88-92 + owner decision 117 — a fence fault leaves the record
     established and restart-readable, never falsely failed.
ORDERING (seams/events, no sleeps)
 10. pv20.py:171-173 the resources registered after the Jobs (watchdog host, private
     directory, ledger dir) still close when disposal raises, in registration-reverse
     order with admission and the broker already closed.

Probe 1 of the card ("Broker-close failure still closes isolation admission") is dropped
as already covered by test_a_broker_that_will_not_close_does_not_stop_the_stop_short and
replaced by branch 1; probes 4 and 5 collapse into branch 7. Everything else on the
probe list is kept with the evidence above. No source file is edited; no new dependency.
"""
import errno
import logging
import os
import threading
from dataclasses import replace
from types import SimpleNamespace

import pytest

from archeus.core import pv20
from archeus.node import broker as broker_mod, isolation

from .test_pv20_activate import candidate, quiet_core  # noqa: F401
from .test_pv20_mxc_pins import reviewed, tree  # noqa: F401  (candidate's reviewed fixture)
from .test_pv20_isolation import (make_satisfying_request, new_execution_id,  # noqa: F401
                                  os_tripwire)  # noqa: F401  (the autouse tripwire)
from .test_mxc_boundary import Jobs
from .test_provider_broker import binding

ADAPTER = SimpleNamespace(id='claude_code')


def _fresh_activation_still_works(candidate):
    core = candidate.activate()
    return all(vars(core.pv20_switches).values())


def _establish(core, tmp_path, name='layout'):
    """One real isolated execution over the reviewed fakes: identity, record, held Job."""
    authority = core.pv20.node.isolation
    request = make_satisfying_request(new_execution_id(), str(tmp_path / name))
    assert authority.requested(request.execution_id, ADAPTER) is True
    rec = authority.establish(request)
    assert rec.state == 'established'
    return authority, request.execution_id, rec.sid, authority.held_job(request.execution_id)


# ── fail-closed / denial ──────────────────────────────────────────────────────

@pytest.mark.parametrize('which', ['none', 'nul', 'unreachable'])
def test_an_unusable_ledger_path_is_refused_before_anything_is_built(candidate, monkeypatch,
                                                                      which):
    """pv20.py:125-126 — removing the except turns the refusal into the raw error."""
    if which == 'none':
        ledger_dir = None                                    # realpath raises TypeError
    elif which == 'nul':
        ledger_dir = str(candidate.args['ledger_dir'] / 'led\0ger')   # ValueError
    else:
        real_realpath = os.path.realpath
        asked = []

        def unreachable(path):
            if not asked:                          # refuse the first look only
                asked.append(path)
                raise OSError(errno.EACCES, 'synthetic unreachable ledger root')
            return real_realpath(path)

        monkeypatch.setattr(pv20.os.path, 'realpath', unreachable)
        ledger_dir = candidate.args['ledger_dir']
    with pytest.raises(pv20.ActivationRefused) as caught:
        candidate.activate(ledger_dir=ledger_dir)
    assert caught.value.reason == 'invalid_parameters'
    assert candidate.events == []                              # nothing was ever started
    assert pv20._claimed == set()                              # nothing was claimed
    assert not candidate.args['ledger_dir'].exists()           # not even the dir was made
    assert _fresh_activation_still_works(candidate) is True    # nothing was poisoned


def test_quiesce_closes_admission_when_a_grant_listener_refuses_to_close(candidate,
                                                                          monkeypatch,
                                                                          tmp_path):
    """pv20.py:59-62 — the existing broker test patches Broker.close whole and holds no
    grant; here close dies inside revoke's transport callback with a live grant, and the
    admission gate must fall anyway."""
    core = candidate.activate()
    authority = core.pv20.node.isolation
    held = core.pv20.broker
    created, closed_calls = [], []

    class FakeEndpoint:
        port = 7339

        def start(self, _binding):
            pass

    def create(name, principal):
        created.append('created')
        return FakeEndpoint()

    def close(endpoint):
        closed_calls.append(endpoint)
        raise OSError('the listener will not close')

    monkeypatch.setattr(broker_mod.socket, 'getaddrinfo',
                        lambda *a, **k: [(2, 1, 6, '', ('93.184.216.34', 443))])
    held.transport.create = create
    held.transport.close = close
    grant = binding(core_instance='fixture')
    token, _d, endpoint, port = held.issue(grant)
    assert created == ['created'] and port == 7339
    assert held.reach(grant.execution_id) == 7339              # the grant is live
    with pytest.raises(OSError, match='the listener will not close'):
        core.pv20.quiesce()
    assert authority.closed is True                            # denial fell anyway
    assert held._closed is True and held._grants == {}         # the grant itself is gone
    assert closed_calls == [endpoint]                          # revoke tried the listener
    with pytest.raises(broker_mod.BrokerUnavailable, match='closed'):
        held.issue(binding(core_instance='fixture'))
    assert created == ['created']                              # no new listener was bound
    with pytest.raises(isolation.IsolationClosed):
        authority._ensure_job(new_execution_id())
    with pytest.raises(isolation.IsolationClosed):
        authority.establish(make_satisfying_request(new_execution_id(),
                                                    str(tmp_path / 'late')))
    assert authority.held_jobs() == {}


def test_a_second_quiesce_or_close_never_reopens_admission_or_repeats_callbacks(
        candidate, tmp_path):
    """pv20.py:59-66 — every existing test stops exactly once; nothing pins that a
    repeated quiesce/close re-arms the broker or re-fences a Job."""
    core = candidate.activate()
    authority, eid, _sid, job = _establish(core, tmp_path)
    core.pv20.quiesce()
    core.pv20.quiesce()                                        # a second stop attempt
    core.pv20.close()
    core.pv20.close()
    assert core.pv20.closed is True and authority.closed is True
    assert candidate.events.count('broker_closed') == 1        # no callback ran twice
    assert candidate.events.count('host_closed') == 1
    assert core.pv20.node.isolation.boundary.jobs.closed == [job]   # fenced exactly once
    assert authority.held_jobs() == {}
    with pytest.raises(isolation.IsolationClosed):
        authority.establish(make_satisfying_request(new_execution_id(),
                                                    str(tmp_path / 'late')))
    with pytest.raises(broker_mod.BrokerUnavailable, match='closed'):
        core.pv20.broker.issue(binding(core_instance='fixture'))

    outcome = []
    started, done = threading.Event(), threading.Event()

    def late():
        try:
            started.wait(5.0)
            try:
                authority._ensure_job(new_execution_id())
                outcome.append('created')
            except isolation.IsolationClosed:
                outcome.append('refused')
        finally:
            done.set()

    worker = threading.Thread(target=late, name='t1112-late')
    worker.start()
    try:
        started.set()
        assert done.wait(5.0) is True and outcome == ['refused']
    finally:
        started.set()
        done.set()
        worker.join(5.0)
        assert not worker.is_alive()


# ── boundaries ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize('given', [True, False], ids=['given', 'omitted'])
def test_a_binding_without_jobs_gets_its_own_windows_job_boundary(candidate, monkeypatch,
                                                                  given):
    """pv20.py:41,145 — no existing test omits bindings.jobs, so the default
    WindowsBoundary side of the ternary never ran: without it the Core boundary would
    silently fall back to MxcBoundary's own UnavailableBoundary off a fence."""
    built = []

    class SyntheticJobBoundary:
        def __init__(self):
            built.append(self)

    monkeypatch.setattr(pv20.isolation, 'WindowsBoundary', SyntheticJobBoundary,
                        raising=False)
    bindings = candidate.args['bindings'] if given else replace(candidate.args['bindings'],
                                                                jobs=None)
    core = candidate.activate(bindings=bindings)
    jobs = core.pv20.node.isolation.boundary.jobs
    if given:
        assert type(jobs) is Jobs and built == []
    else:
        assert type(jobs) is SyntheticJobBoundary and built == [jobs]
        assert not isinstance(jobs, pv20.isolation.UnavailableBoundary)


def test_disposing_an_activation_without_a_node_touches_nothing(caplog):
    """pv20.py:75-76 — the guard runs inside rollbacks, but _rollback:91-92 would
    swallow the AttributeError its removal causes, so no existing assertion owns it."""
    with caplog.at_level(logging.ERROR, logger='archeus.core.pv20'):
        assert pv20._dispose(None) is None
    assert 'could not close the Job' not in caplog.text
    assert pv20._dispose(None) is None


def test_an_empty_held_set_fences_nothing_and_stops_clean(candidate, monkeypatch):
    """pv20.py:78-85 — every fixture teardown walks the empty loop, but nothing owns
    'no Job means no fence call and no error'."""
    core = candidate.activate()
    authority = core.pv20.node.isolation
    attempts = []
    monkeypatch.setattr(authority, 'held_jobs', lambda: {})
    monkeypatch.setattr(authority, 'fence',
                        lambda execution_id, wait: attempts.append((execution_id, wait)))
    core.stop()
    assert attempts == []
    assert candidate.events == ['host_started', 'broker_closed', 'host_closed']
    assert authority.closed is True


# ── error paths ───────────────────────────────────────────────────────────────

def test_the_first_fence_fault_survives_the_jobs_after_it(candidate, quiet_core, monkeypatch,
                                                          caplog):
    """pv20.py:81-85 — the existing fault test fences one faulty Job only: `first =
    error` (keep side inverted) or a break on the first fault both leave it green."""
    core = candidate.activate()
    core.start()
    authority = core.pv20.node.isolation
    faults = {
        'exe_a': OSError('first fence fault'),
        'exe_c': OSError('second fence fault must not replace the first'),
    }
    attempts = []

    def fence(execution_id, wait):
        attempts.append((execution_id, wait))
        if execution_id in faults:
            raise faults[execution_id]

    monkeypatch.setattr(authority, 'held_jobs',
                        lambda: {'exe_a': object(), 'exe_b': object(), 'exe_c': object()})
    monkeypatch.setattr(authority, 'fence', fence)
    with caplog.at_level(logging.ERROR, logger='archeus.core.pv20'):
        with pytest.raises(OSError) as caught:
            core.stop()
    assert caught.value is faults['exe_a']
    assert attempts == [('exe_a', 0), ('exe_b', 0), ('exe_c', 0)]   # all attempted, wait=0
    assert caplog.text.count('could not close the Job') == 2
    assert candidate.events[-1] == 'host_closed'               # the stop did not halt short


def test_disposal_only_fences_and_never_tears_down_the_identity(candidate, quiet_core,
                                                                monkeypatch, tmp_path):
    """pv20.py:69-85 — Job-only disposal (6027a5f9): the existing tests patch out
    `teardown` alone; record removal, quarantine and profile deletion are new routes a
    refactor could add back, and each must stay uncalled."""
    core = candidate.activate()
    core.start()
    authority, eid, _sid, job = _establish(core, tmp_path)
    forbidden = []
    for name in ('teardown', '_delete_profile', '_remove_record', 'quarantine',
                 'note_failure', '_fail', '_save'):
        monkeypatch.setattr(authority, name,
                            lambda *a, _n=name: forbidden.append(_n))
    real_fence = isolation.Isolation.fence

    def fence(execution_id, wait):
        real_fence(authority, execution_id, wait=wait)         # kill-on-close really runs
        raise OSError('synthetic fence fault after the Job closed')

    monkeypatch.setattr(authority, 'fence', fence)
    with pytest.raises(OSError, match='synthetic fence fault'):
        core.stop()
    assert forbidden == []                                     # nothing but the fence ran
    assert authority.boundary.jobs.closed == [job]             # the Job itself is closed
    rec = authority.record(eid)
    assert rec is not None and rec.state == 'established' and rec.failure == ''


def test_a_fence_fault_leaves_the_restart_record_unfailed(candidate, quiet_core,
                                                          monkeypatch, tmp_path):
    """pv20.py:81-85 + owner decision 117 — the existing fence-fault test asserts the
    stop continues but reads no record; the existing record test has no fence fault.
    Only their combination catches a disposal that blames the execution."""
    core = candidate.activate()
    core.start()
    authority, eid, sid, _job = _establish(core, tmp_path)
    noted = []
    monkeypatch.setattr(core.pv20.node, '_registry', lambda line: noted.append(line))

    def failing_fence(execution_id, wait):
        raise OSError('the Job will not close')

    monkeypatch.setattr(authority, 'fence', failing_fence)
    with pytest.raises(OSError, match='the Job will not close'):
        core.stop()
    assert core.db is None and core.lock is None               # the stop itself finished
    assert authority.boundary.jobs.closed == []                # the fence never got there
    assert [n.get('op') for n in noted] == []                  # no isolation_failed note
    assert authority.invalid == {} and authority.faults == {}  # nothing marked suspect
    rec = authority.record(eid)
    assert (rec.state, rec.failure, rec.owned, rec.sid) == ('established', '', True, sid)
    pv20._claimed.clear()                                      # a restart is another process
    after = candidate.activate().pv20.node.isolation
    again = after.record(eid)
    assert (again.state, again.failure, again.owned, again.sid) == (
        'established', '', True, sid)
    assert after.requested(eid, ADAPTER) is True               # it stays an isolated resume


# ── ordering, forced with seams and events instead of sleeps ─────────────────

def test_resources_registered_after_the_jobs_still_close_when_disposal_raises(
        candidate, quiet_core, monkeypatch):
    """pv20.py:171-173 — the existing fault test reads the event list only; the private
    directory and the empty ledger dir are registered earlier and so close later, and
    nothing yet proves they survive a raising disposal, nor that the broker and the
    admission gate were already down when the fence ran."""
    core = candidate.activate()
    core.start()
    authority = core.pv20.node.isolation
    seen = []

    def raising_fence(execution_id, wait):
        # the ordering is read from the real state here, not from timing
        seen.append((execution_id, wait, core.pv20.broker._closed, authority.closed))
        raise OSError('disposal will not close')

    monkeypatch.setattr(authority, 'held_jobs', lambda: {'exe_a': object()})
    monkeypatch.setattr(authority, 'fence', raising_fence)
    root = candidate.args['ledger_dir']
    private = os.path.dirname(core.pv20.host.channel.root)
    assert root.is_dir() and os.path.isdir(private)
    with pytest.raises(OSError, match='disposal will not close'):
        core.stop()
    assert seen == [('exe_a', 0, True, True)]                  # both gates down at the fence
    assert candidate.events == ['host_started', 'broker_closed', 'host_closed']
    assert not os.path.exists(private)                         # the private dir still went
    assert not root.exists()                                   # and the empty ledger dir

"""A6-3: one confined verifier attempt (T-054 C-1013 §1 and §3), over the synthetic
boundary and a scripted process. Nothing here launches a real process or touches a
real Job; the order, the soft limits and every way a run fails closed are checked on
what Core asked the boundary and what it recorded."""

import os
import sys
import time

import pytest

from archeus.infra.paths import VerifyPaths
from archeus.node import isolation as iso
from archeus.node.local import LocalNode
# os_tripwire is autouse: importing it arms the same OS tripwire here
from v1.unit.test_pv20_isolation import (FakeBoundary, FakeChild, FakeNode, _VID, _verify_key,
                                         make_verifier_request, os_tripwire)  # noqa: F401


class Child(FakeChild):
    """A process whose every wait runs *step* first; it exits when *step* says so."""

    def __init__(self, step=None):
        super().__init__()
        self.step = step or (lambda child: setattr(child, 'returncode', 0))

    def wait(self, timeout=None):
        self.waits.append(timeout)
        if self.returncode is None:
            self.step(self)
        return self.returncode


class Boundary(FakeBoundary):
    """The synthetic boundary plus the Job's member count and one ordered event log."""

    def __init__(self, child=None, members=0):
        super().__init__()
        self.events = []
        self.child = child or Child()
        self.members = members            # an int, or an exception to raise
        self.close_fail = None

    def job_active_processes(self, job):
        self.events.append('count')
        if isinstance(self.members, Exception):
            raise self.members
        return self.members

    def close_job(self, job):
        self.events.append('close')
        super().close_job(job)
        if self.close_fail:
            raise self.close_fail

    def delete_profile(self, execution_id):
        self.events.append('delete')
        super().delete_profile(execution_id)

    def launch(self, argv, **kw):
        super().launch(argv, **kw)
        return self.child


@pytest.fixture(autouse=True)
def quick(monkeypatch):
    monkeypatch.setattr(iso, 'EXIT_WAIT_S', 0.1)
    monkeypatch.setattr(iso, 'CONFINED_POLL_S', 0.01)


@pytest.fixture
def run(tmp_path, monkeypatch):
    """`run(boundary, ...)` -> (result, recorded, authority, request) for one attempt."""
    real = iso._captured

    def captured(*a):
        b.events.append('capture')
        return real(*a)
    monkeypatch.setattr(iso, '_captured', captured)
    b = None

    def go(boundary, *, attempt=0, timeout=5, record=None, authority=None, keep=1024):
        nonlocal b
        b = boundary
        a = authority or iso.Isolation(FakeNode(), boundary=boundary)
        req = make_verifier_request(_verify_key(attempt), str(tmp_path / ('a%d' % attempt)))
        out, stdin = str(tmp_path / ('out%d.log' % attempt)), str(tmp_path / 'stdin')
        for f in (out, stdin):
            open(f, 'wb').close()
        recorded = []

        def rec(result):
            boundary.events.append('record')
            recorded.append(dict(result))
            if record:
                record(result)
        result = a.run_confined(req, ['tool', 'check'], env={'PATH': 'x'}, timeout=timeout,
                                out_path=out, stdin_path=stdin, record=rec, keep=keep)
        return result, recorded, a, req
    return go


def _writer(path, data=b'x' * 10):
    def step(child):
        with open(path, 'ab') as f:
            f.write(data)
    return step


def test_a_clean_run_is_counted_closed_captured_recorded_then_deleted_in_that_order(run):
    b = Boundary()
    result, recorded, a, req = run(b)
    assert result['error'] is None and result['exit_code'] == 0
    assert b.events == ['count', 'close', 'capture', 'record', 'delete']
    assert recorded == [result] and result['confinement']['ac_profile'] == \
        iso.validated_profile(req.execution_id)
    assert set(result) == {'exit_code', 'duration_ms', 'error', 'output', 'output_bytes',
                           'truncated', 'confinement'}
    call, = b.launch_calls
    assert call['stdin'] == {'stdio': call['stdin']['stdio'], 'mode': 'read'}
    assert call['stdout']['mode'] == 'append' and call['cwd'] == req.workspace
    assert a.record(req.execution_id) is None          # torn down, record gone


def test_a_descendant_still_in_the_job_after_the_root_exits_is_an_error(run, tmp_path):
    out = str(tmp_path / 'out0.log')
    b = Boundary(members=1)
    real = b.job_active_processes

    def still_writing(job):                       # a descendant holds the output handle
        with open(out, 'ab') as f:
            f.write(b'late')
        return real(job)
    b.job_active_processes = still_writing
    result, recorded, _a, _req = run(b)
    assert result['error'].startswith('quiescence_unknown') and result['exit_code'] is None
    first_close = b.events.index('close')
    assert b.events.index('capture') > first_close and 'count' in b.events[:first_close]
    assert recorded == [result] and result['output'].endswith(b'late')


def test_a_job_count_that_cannot_be_read_is_never_zero(run):
    b = Boundary(members=iso.IsolationUnavailable('job_query', 'synthetic'))
    result, _rec, _a, _req = run(b)
    assert result['error'].startswith('quiescence_unknown') and result['exit_code'] is None


def test_a_boundary_with_no_job_count_is_an_error(run):
    b = Boundary()
    b.job_active_processes = None
    result, _rec, _a, _req = run(b)
    assert result['error'].startswith('quiescence_unknown')


def test_the_deadline_closes_the_job_first_and_reads_no_count(run):
    began = time.monotonic()

    def never(child):                                    # never exits on its own
        assert time.monotonic() - began < 5, 'the deadline never ended the run'
    b = Boundary(child=Child(step=never))
    result, recorded, _a, _req = run(b, timeout=0.05)
    assert result['error'].startswith('timed out') and result['exit_code'] is None
    assert 'count' not in b.events and b.events[0] == 'close' and recorded == [result]


def test_a_shutdown_that_fails_is_an_error_and_still_recorded(run):
    b = Boundary()
    b.close_fail = iso.IsolationUnavailable('job_close', 'synthetic')
    result, recorded, _a, _req = run(b)
    assert result['error'].startswith('shutdown_failed') and recorded == [result]


def test_a_record_that_fails_leaves_the_profile_for_reclaim(run):
    b = Boundary()

    def broken(result):
        raise OSError('database unavailable')
    with pytest.raises(OSError):
        run(b, record=broken)
    assert 'delete' not in b.events
    key = _verify_key()
    a = iso.Isolation(FakeNode(), boundary=b)
    assert a.record(key).state == 'established'
    assert key in a.reclaim(()) and b.events[-1] == 'delete'


def test_a_row_that_no_longer_awaits_the_verdict_still_lets_the_profile_go(run):
    b = Boundary()
    result, _rec, _a, _req = run(b, record=lambda r: None)   # the sink said Refused
    assert b.events[-1] == 'delete'


def test_a_teardown_that_fails_quarantines_and_leaves_the_recorded_result(run):
    b = Boundary()
    b.delete_fail.add(iso.validated_profile(_verify_key()))
    result, recorded, a, req = run(b)
    assert result == recorded[0] and result['error'] is None
    assert a.record(req.execution_id).state == 'quarantined'


def test_a_rapid_writer_past_the_output_cap_is_caught_on_the_next_poll(run, tmp_path,
                                                                       monkeypatch):
    monkeypatch.setattr(iso, 'CONFINED_OUT_MAX', 100)
    b = Boundary(child=Child(step=_writer(str(tmp_path / 'out0.log'), b'x' * 1000)))
    result, _rec, _a, _req = run(b)
    # detection only: the bytes already written are not claimed to be bounded
    assert result['error'].startswith('limit_exceeded') and b.events[0] == 'close'
    assert result['exit_code'] is None


def test_scratch_growth_past_its_cap_is_an_error(run, tmp_path, monkeypatch):
    monkeypatch.setattr(iso, 'CONFINED_GROWTH_MAX', 100)
    big = str(tmp_path / 'a0' / 'scratch' / 'big')
    b = Boundary(child=Child(step=_writer(big, b'y' * 1000)))
    result, _rec, _a, _req = run(b)
    assert result['error'].startswith('limit_exceeded: the checkout and scratch')


def _link(target, at):
    if sys.platform.startswith('win'):
        import _winapi
        _winapi.CreateJunction(target, at)
    else:
        os.symlink(target, at, target_is_directory=True)


def test_accounting_never_follows_a_link_or_a_cycle(run, tmp_path, monkeypatch):
    outside = tmp_path / 'outside'
    outside.mkdir()
    (outside / 'huge').write_bytes(b'z' * 5000)
    monkeypatch.setattr(iso, 'CONFINED_GROWTH_MAX', 1000)
    monkeypatch.setattr(iso, 'CONFINED_WALK_MAX', 50)
    scratch = str(tmp_path / 'a0' / 'scratch')

    def plant(child):                        # the verifier plants a link out, and a loop
        _link(str(outside), os.path.join(scratch, 'out'))
        _link(scratch, os.path.join(scratch, 'loop'))
        child.returncode = 0
    b = Boundary(child=Child(step=plant))
    result, _rec, _a, _req = run(b)
    assert result['error'] is None and result['exit_code'] == 0
    assert iso._tree_bytes([scratch]) < 1000


def test_an_entry_the_walk_cannot_read_is_accounting_failed(run, tmp_path, monkeypatch):
    real, armed = os.scandir, []

    def scandir(path):
        if armed and 'scratch' in str(path):
            raise PermissionError('denied (synthetic)')
        return real(path)
    monkeypatch.setattr(os, 'scandir', scandir)
    b = Boundary(child=Child(step=lambda c: armed.append(1)))
    result, recorded, _a, _req = run(b)
    assert result['error'].startswith('accounting_failed') and recorded == [result]
    assert result['exit_code'] is None


def test_a_walk_over_its_budget_is_accounting_failed_and_launches_nothing(run, tmp_path,
                                                                          monkeypatch):
    monkeypatch.setattr(iso, 'CONFINED_WALK_MAX', 3)
    scratch = tmp_path / 'a0' / 'scratch'
    scratch.mkdir(parents=True)
    for n in range(5):
        (scratch / str(n)).write_bytes(b'')
    b = Boundary()
    result, recorded, _a, _req = run(b)
    assert result['error'].startswith('accounting_failed') and b.launch_calls == []
    assert recorded == [result]


def test_an_unmet_condition_launches_nothing_and_records_the_error(run):
    b = Boundary()
    b.grant_ok = False
    result, recorded, _a, _req = run(b)
    assert result['error'].startswith('isolation: condition_unmet')
    assert b.launch_calls == [] and recorded == [result] and result['confinement'] == {}


def test_a_consumed_attempt_is_never_rerun_and_its_profile_is_left_alone(run):
    b = Boundary()

    def broken(result):
        raise OSError('database unavailable')
    with pytest.raises(OSError):
        run(b, record=broken)                       # attempt 0 left established
    created, launched = list(b.created), len(b.launch_calls)
    result, recorded, _a, _req = run(b)              # the same attempt again
    assert result['error'] == 'isolation: attempt_consumed' and recorded == [result]
    assert b.created == created and len(b.launch_calls) == launched
    assert 'delete' not in b.events


def test_reclaim_spares_an_attempt_this_core_is_running(run):
    b = Boundary()
    seen = []

    def during(result):
        seen.append(a.reclaim(()))
    a = iso.Isolation(FakeNode(), boundary=b)
    run(b, authority=a, record=during)
    assert seen == [[]] and b.events[-1] == 'delete'


def test_the_node_runs_a_check_confined_in_its_attempts_own_files(tmp_path):
    write = _writer(VerifyPaths(_VID, 0).out, b'ok')

    def step(child):
        write(child)
        child.returncode = 0
    b = Boundary(child=Child(step=step))
    node = LocalNode(isolation=iso.Isolation(FakeNode(), boundary=b))
    toolchain = tmp_path / 'toolchain'
    toolchain.mkdir()
    recorded = []
    result = node.run_confined_check(_VID, 0, ['python', '-c', 'pass'],
                                     toolchain=[str(toolchain)], timeout=5,
                                     record=recorded.append)
    assert result['error'] is None and result['output'] == b'ok' and recorded == [result]
    call, = b.launch_calls
    own = os.path.dirname(call['cwd'])
    assert call['cwd'].endswith(os.path.join('own', 'checkout'))
    assert call['env']['PATH'] == str(toolchain) and call['env']['TEMP'] == os.path.join(own, 'tmp')
    assert not any(k.startswith('ARCHEUS') for k in call['env'])

"""T-336: the highest-risk uncovered branches of `archeus/node/isolation.py` 1300-1850
— the confined run, its accounting, the launch seam and the grant readers — over the
synthetic boundary of `test_pv20_isolation.py`. Nothing here starts a process, opens a
Job or touches a real security descriptor: every OS answer is a fake, and the OS
tripwire imported below fails the test that reaches a real primitive.

Each test names the source branch it would catch (see the card report): a branch whose
removal or inversion would leave the test green does not belong in this file.
"""

import os
import stat
from types import SimpleNamespace

import pytest

from archeus.harnesses import base
from archeus.infra.paths import ExecPaths
from archeus.node import isolation as iso
# os_tripwire is autouse: importing it arms the same OS tripwire here
from v1.unit.test_pv20_isolation import (FakeBoundary, FakeChild, FakeNode, _verify_key,
                                         authority, make_satisfying_request,
                                         make_verifier_request, new_execution_id,
                                         os_tripwire)  # noqa: F401
# the scripted process, the counting boundary and the faked directory entry, reused
from v1.unit.test_confined_run import Boundary, Child, _aliased_entries  # noqa: F401

#: what an entry that is no file at all looks like to the walk: a FIFO is neither a
#: plain directory, a regular file, a link nor a reparse point
FIFO = SimpleNamespace(st_mode=stat.S_IFIFO | 0o644, st_size=1 << 30, st_file_attributes=0)


@pytest.fixture(autouse=True)
def quick(monkeypatch):
    """No test here waits on a real bound: the quiescence wait, the poll step and the
    process-exit wait are all shortened, and every sleep stays far under a second."""
    monkeypatch.setattr(iso, 'EXIT_WAIT_S', 0.05)
    monkeypatch.setattr(iso, 'CONFINED_POLL_S', 0.01)


@pytest.fixture
def run(tmp_path):
    """`run(boundary)` -> (result, recorded, authority, request) for one attempt, over
    the verifier inventory `make_verifier_request` builds under `tmp_path/a<n>`."""
    attempt = [0]

    def go(boundary, *, authority=None, timeout=5, keep=1024, record=None):
        n = attempt[0]
        attempt[0] += 1
        a = authority or iso.Isolation(FakeNode(), boundary=boundary)
        req = make_verifier_request(_verify_key(n), str(tmp_path / ('a%d' % n)))
        out, stdin = str(tmp_path / ('out%d.log' % n)), str(tmp_path / 'stdin')
        for f in (out, stdin):
            open(f, 'wb').close()
        recorded = []

        def sink(result):
            recorded.append(dict(result))
            if record:
                # the verdict and its execution, while it is still the live one
                record(result, req)
        result = a.run_confined(req, ['tool', 'check'], env={'PATH': 'x'}, timeout=timeout,
                                out_path=out, stdin_path=stdin, record=sink, keep=keep)
        return result, recorded, a, req
    return go


# ── the confined launch: nothing half-started survives, and nothing is forgotten ──

def test_a_launch_that_fails_after_creating_the_process_keeps_it_by_its_handle(tmp_path,
                                                                               run):
    """isolation.py:1365-1369 — a boundary that created the process and then refused it
    hands the handle back on the error; Core holds it, so the end path waits on that
    handle and never on a PID that could name another process by then."""
    half = Child()
    half.returncode = 0                        # the process the boundary terminated

    def launch(argv, **kw):                    # as WindowsBoundary.launch does on a failure
        err = iso.IsolationUnavailable('process_confine', 'attribute list rejected')
        err.child = half
        raise err

    b = Boundary()
    b.launch = launch
    held = []
    a = iso.Isolation(FakeNode(), boundary=b)
    result, recorded, auth, req = run(b, authority=a, record=lambda r, q: held.append(
        a.launched(q.execution_id)))
    assert result['error'].startswith('launch_failed: ')
    assert 'process_confine' in result['error'] and result['exit_code'] is None
    assert result['output'] == b'' and result['output_bytes'] == 0
    assert half.waits == [0] and b.probed == []        # its handle asked, never a PID guess
    assert held == [half] and recorded == [result]     # held while the verdict was written
    assert auth.launched(req.execution_id) is None     # released once that handle said gone
    assert b.launch_calls == [] and b.closed and b.deleted       # the Job closed, it went on


def test_a_handle_that_will_not_close_never_loses_a_launched_process(tmp_path, run):
    """isolation.py:1373-1375 — the boundary's own handle closes sit in a `finally`: one
    that raises must not replace the launch it follows, nor turn a finished run into a
    crash that records no verdict and leaves the profile for reclaim."""
    b = Boundary()
    closed = []

    def close_handle(handle):
        closed.append(handle)
        raise OSError('CloseHandle said the handle was bad (synthetic)')

    b.close_handle = close_handle
    result, recorded, a, req = run(b)
    assert len(closed) == 2                            # both Core handles were still closed
    assert result['error'] is None and result['exit_code'] == 0
    assert recorded == [result] and b.events[-1] == 'delete'
    assert a.record(req.execution_id) is None          # torn down like any clean run


# ── quiescence: a Job Core cannot read is never an empty Job ────────────────────

def test_a_run_whose_job_core_no_longer_holds_is_never_read_as_quiescent(tmp_path, run):
    """isolation.py:1384-1385 — with no handle held there is nothing to ask, and the
    answer is never 'none left': the kill-on-close guarantee is exactly what is gone."""
    b = Boundary()
    a = iso.Isolation(FakeNode(), boundary=b)
    a.held_job = lambda execution_id: None             # Core lost the handle it held
    result, recorded, _a, _req = run(b, authority=a)
    assert result['error'] == 'quiescence_unknown: no Job count to read'
    assert result['exit_code'] is None and recorded == [result]
    assert b.events == ['close', 'delete']             # no count was ever asked


@pytest.mark.parametrize('label,answer', [
    ('os-error', OSError('QueryInformationJobObject denied (synthetic)')),
    ('unavailable', iso.IsolationUnavailable('job_query', 'denied (synthetic)')),
], ids=['os-error', 'unavailable'])
def test_a_job_count_that_cannot_be_read_is_a_verdict_and_not_a_crash(tmp_path, run, label,
                                                                       answer):
    """isolation.py:1390-1391 — the Job read failing is a recorded `quiescence_unknown`,
    whatever the failure class: it never escapes `run_confined`, which would end the
    attempt with no verdict written and its profile left standing for reclaim."""
    b = Boundary(members=answer)
    result, recorded, _a, _req = run(b)
    assert result['error'].startswith('quiescence_unknown: ')
    assert 'denied' in result['error'] and result['exit_code'] is None
    assert recorded == [result] and b.events[0] == 'count' and b.events[-1] == 'delete'


@pytest.mark.parametrize('label,answer', [('false', False), ('float-zero', 0.0),
                                          ('string-zero', '0'), ('negative', -1)],
                         ids=['false', 'float-zero', 'string-zero', 'negative'])
def test_a_job_count_that_is_not_a_count_is_never_quiescence(tmp_path, run, label, answer):
    """isolation.py:1392 — only the integer 0 means empty: `False == 0` and `0.0 == 0`
    do not make a survivor leave, and a boundary that cannot answer with a count is
    answered with a failure, not with a pass."""
    b = Boundary(members=answer)
    result, _recorded, _a, _req = run(b)
    assert result['error'] == 'quiescence_unknown: %r still in the Job' % (answer,)
    assert result['exit_code'] is None


# ── accounting: what cannot be classified is never counted as nothing ───────────

def test_an_entry_the_walk_cannot_classify_launches_nothing(tmp_path, monkeypatch, run):
    """isolation.py:1421-1424 — an entry that is neither a plain directory, a regular
    file, a link nor a reparse point has no size Core may count: the walk stops, the
    run is `accounting_failed` and nothing is launched to write what cannot be bounded."""
    scratch = str(tmp_path / 'a0' / 'scratch')
    os.makedirs(scratch, exist_ok=True)
    with open(os.path.join(scratch, 'weird'), 'wb') as f:
        f.write(b'not a file at all')
    _aliased_entries(monkeypatch, {'weird': FIFO})
    b = Boundary()
    result, recorded, _a, _req = run(b)
    assert result['error'].startswith('accounting_failed: an entry that cannot be classified')
    assert 'weird' in result['error'] and result['exit_code'] is None
    assert b.launch_calls == [] and b.events == ['close', 'delete']
    assert recorded == [result]


# ── the launch seam and the boundary that is not there ─────────────────────────

def test_the_facts_of_an_execution_with_no_record_are_no_facts(tmp_path):
    """isolation.py:1576-1577 — the registry reads `facts()` after the end, when the
    record is gone: the answer is an empty dict, never a crash and never a claim that
    something still unisolated is isolated."""
    a, _b, req, _node = authority(tmp_path)
    ctx = iso.IsolationContext(a, req)
    assert ctx.facts() == {}                             # never established: nothing to say
    rec = a.establish(req)
    assert ctx.facts()['ac_profile'] == rec.profile      # the reader itself is not broken
    a.teardown(req.execution_id, reason='ended')
    assert ctx.facts() == {}                             # the record is gone, so are its facts


def test_the_unavailable_boundary_is_unavailable_for_everything(tmp_path):
    """isolation.py:1596-1597 (with 1599-1602 and 802-804) — the boundary a non-Windows
    Core gets answers `False` to the one question that gates the isolated path, and
    every other question with a refusal: nothing is created, and a launch is a
    `SpawnFailed`, never a second attempt through the detached launcher."""
    b = iso.UnavailableBoundary()
    assert b.available() is False and b.id == 'unavailable'
    for name in ('create_profile', 'launch', 'create_job', 'close_job'):
        with pytest.raises(iso.IsolationUnavailable) as err:
            getattr(b, name)('whatever')
        assert err.value.reason == 'platform'
    a = iso.Isolation(FakeNode(), boundary=b)
    req = make_satisfying_request(new_execution_id(), str(tmp_path))
    with pytest.raises(iso.IsolationUnavailable) as err:
        a.establish(req)
    assert err.value.reason == 'platform'
    assert a.launched(req.execution_id) is None and a.held_jobs() == {}
    # a fresh execution, so the refusal below is the boundary's and not a kept record's
    a2 = iso.Isolation(FakeNode(), boundary=b)
    req2 = make_satisfying_request(new_execution_id(), str(tmp_path))
    with pytest.raises(base.SpawnFailed) as failed:
        a2.requested(req2.execution_id)              # nothing is launched by asking
        iso.IsolationContext(a2, req2).launch(['tool'], cwd=req2.workspace, env={},
                                              paths=ExecPaths(req2.execution_id))
    assert str(failed.value).startswith('isolation: platform')


def test_a_handle_that_will_not_close_never_refuses_a_process_it_let_go(tmp_path, monkeypatch):
    """isolation.py:1568-1571 — the same `finally` on Core's own launch: a boundary whose
    `CloseHandle` raises must not raise `SpawnFailed` for a process that is running and
    confined, because the caller has no second path and the process would be orphaned."""
    a, b, req, _node = authority(tmp_path)
    closed = []

    def close_handle(handle):
        closed.append(handle)
        raise OSError('CloseHandle failed (synthetic)')

    b.close_handle = close_handle
    monkeypatch.setattr(iso, 'base_create_time', lambda pid: 777)
    child, detached = iso.IsolationContext(a, req).launch(['tool'], cwd=req.workspace, env={},
                                                          paths=ExecPaths(req.execution_id))
    assert detached is None and closed and all(h is not None for h in closed)
    assert a.launched(req.execution_id) is child
    rec = a.record(req.execution_id)
    assert rec.state == 'established' and rec.pid == child.pid and rec.create_time == 777


# ── the grant readers: a control right is never an inventory row ────────────────

@pytest.mark.parametrize('label,mask,row,expect', [
    # the writable row: without that guard these read as exactly what the row asked for,
    # because an 'rw' row never consults _write_like
    ('generic-all-rw', iso.GENERIC_ALL | iso.GENERIC_READ | iso.GENERIC_WRITE, 'rw', False),
    ('write-dac-rw', 0x1 | 0x2 | iso.WRITE_DAC, 'rw', False),
    ('write-owner-rw', 0x1 | 0x2 | iso.WRITE_OWNER, 'rw', False),
    ('generic-dac-rw', iso.GENERIC_READ | iso.GENERIC_WRITE | iso.WRITE_DAC, 'rw', False),
    # the read rows: the first guard refuses them, and _write_like would too
    ('generic-all-rx', iso.GENERIC_READ | iso.GENERIC_EXECUTE | iso.GENERIC_ALL, 'rx', False),
    ('write-dac-rx', 0x1 | 0x20 | iso.WRITE_DAC, 'rx', False),
    ('write-owner-x', 0x20 | iso.WRITE_OWNER, 'x', False),
    ('generic-all-x', iso.GENERIC_ALL | iso.GENERIC_EXECUTE, 'x', False),
    # the same masks with nothing extra are the row itself: the control right is the why
    ('plain-rw', 0x1 | 0x2, 'rw', True),
    ('plain-rx', 0x1 | 0x20, 'rx', True),
    ('plain-x', 0x20, 'x', True),
    ('generic-rw', iso.GENERIC_READ | iso.GENERIC_WRITE, 'rw', True),
], ids=['generic-all-rw', 'write-dac-rw', 'write-owner-rw', 'generic-dac-rw', 'generic-all-rx',
        'write-dac-rx', 'write-owner-x', 'generic-all-x', 'plain-rw', 'plain-rx', 'plain-x',
        'generic-rw'])
def test_a_control_right_never_covers_an_inventory_row(label, mask, row, expect):
    """isolation.py:1640-1641 — `WRITE_DAC` and `WRITE_OWNER` reach the descriptor itself
    and `GENERIC_ALL` is everything, so an ACE carrying any of them is a broader grant,
    never the row: the first guard is what says so, since a writable row is judged only
    by whether read and write are present."""
    assert iso.access_covered(mask, row) is expect


# ── the soft limits and the frozen output: where exactly they bite ──────────────

def _plain_root(tmp_path, name, size):
    root = tmp_path / name
    root.mkdir(exist_ok=True)
    with open(str(root / 'one.bin'), 'wb') as f:
        f.write(b'z' * size)
    return str(root)


def test_the_output_cap_bites_one_byte_over_and_not_at_itself(tmp_path, monkeypatch):
    """isolation.py:1439-1440 — an out.log of exactly the cap is still readable; one byte
    more is the end of the run. `>=` would refuse a compliant run, `<` would read a
    runaway writer as one that stayed inside its bound."""
    monkeypatch.setattr(iso, 'CONFINED_OUT_MAX', 8)
    out = str(tmp_path / 'out.log')
    roots = [_plain_root(tmp_path, 'checkout', 3)]
    with open(out, 'wb') as f:
        f.write(b'a' * 8)
    assert iso._over_limit(out, roots, 0) is None
    with open(out, 'ab') as f:
        f.write(b'b')
    assert iso._over_limit(out, roots, 0) == 'limit_exceeded: out.log holds 9 bytes'


def test_the_growth_cap_bites_one_byte_over_and_not_at_itself(tmp_path, monkeypatch):
    """isolation.py:1441-1442 — the same bound on what the checkout and scratch gained:
    at the cap the run stands, one byte over it ends. Measured from *start*, so what was
    already there never counts against it."""
    monkeypatch.setattr(iso, 'CONFINED_GROWTH_MAX', 8)
    out = str(tmp_path / 'out.log')
    with open(out, 'wb') as f:
        f.write(b'a' * 4)
    root = _plain_root(tmp_path, 'scratch', 8)
    assert iso._over_limit(out, [root], 0) is None
    assert iso._over_limit(out, [root], 3) is None            # only the growth is counted
    with open(os.path.join(root, 'one.bin'), 'ab') as f:
        f.write(b'z')
    assert iso._over_limit(out, [root], 0) == \
        'limit_exceeded: the checkout and scratch grew 9 bytes'


@pytest.mark.parametrize('label,keep,tail,truncated', [
    ('keep past the end', 64, b'the whole thing', False),
    ('keep exactly the file', 15, b'the whole thing', False),
    ('keep one byte less', 14, b'he whole thing', True),
    ('keep nothing', 0, b'', True),
], ids=['past-the-end', 'exactly', 'one-byte-less', 'nothing'])
def test_the_output_is_frozen_to_its_last_keep_bytes(tmp_path, label, keep, tail, truncated):
    """isolation.py:1453-1465 — the verdict carries the last *keep* bytes and the true
    size: a seek past the start (a keep larger than the file) is the start, never a
    negative seek, and `truncated` is true only when bytes were left behind."""
    out = str(tmp_path / 'out.log')
    with open(out, 'wb') as f:
        f.write(b'the whole thing')
    assert iso._captured(out, keep) == (tail, 15)
    result = iso._confined_result(out, keep, 0.0, None, 0, {})
    assert result['output'] == tail and result['output_bytes'] == 15
    assert result['truncated'] is truncated and result['exit_code'] == 0

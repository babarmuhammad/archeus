"""T-1364: the release of an owned profile waits for its process and confirms the delete.

Source slice: archeus/node/isolation.py 1208-1258 at tip 10d688c0 (`_remove_profile`,
`_process_state`); the reads at 1270-1275 are context only.

Candidate probes ranked denial first, then boundaries, then error paths. Selected
(ranked) branches and the test that pins each:

  1. 1216-1218  a live process busies the release: no profile delete, quarantine
                `process_alive`                      -> test_a_live_process_busies_the_release
  2. 1219-1223  an unavailable delete quarantines with `reason: detail`, no release
                                                    -> test_an_unavailable_delete_quarantines_with_reason_and_detail
  3. 1224-1228  present or unknown after the delete keeps the record and its handle
                                                    -> test_a_profile_not_confirmed_absent_stays_quarantined
  4. 1229-1230  the handle is dropped and `torn_down` returned only after confirmed absence
                                                    -> test_only_confirmed_absence_releases_and_drops_the_handle
  5. 1240-1242  a Core child answers alive or gone from its own wait, with the given wait
                                                    -> test_a_core_child_answers_from_its_own_wait
  6. 1243-1244  no recorded PID is gone without a boundary read
                                                    -> test_no_recorded_pid_is_gone_without_a_probe
  7. 1252-1254  a reused PID or a PID nobody runs is gone
                                                    -> test_a_reused_pid_or_an_empty_pid_is_gone
  8. 1252-1255  an unrecorded creation time, or an unreadable one, is unknown, never alive
                                                    -> test_an_unrecorded_creation_time_is_unknown_and_refuses_release
  9. 1256-1258  wait 0 probes exactly once and returns at once
                                                    -> test_wait_zero_probes_the_pid_exactly_once
 10. 1247-1250  a boundary that fails during the wait answers unknown at the deadline
                                                    -> test_a_boundary_that_fails_mid_wait_is_unknown

No Windows API, process, token or profile is touched: the boundary, the Core child
and the clock are fakes, and `quarantine` is replaced by a recorder.
"""

import types

import pytest

from archeus.node import isolation as iso

EID = 'exec-1'


class Boundary:
    def __init__(self, started=None, exists=False):
        self.started = started
        self.exists = exists
        self.delete_error = None
        self.probes = []
        self.deleted = []
        self.looked = []

    def process_started(self, pid):
        self.probes.append(pid)
        if callable(self.started):
            return self.started(pid)
        if isinstance(self.started, BaseException):
            raise self.started
        return self.started

    def delete_profile(self, execution_id):
        self.deleted.append(execution_id)
        if self.delete_error is not None:
            raise self.delete_error

    def profile_exists(self, execution_id):
        self.looked.append(execution_id)
        if isinstance(self.exists, BaseException):
            raise self.exists
        return self.exists


class Child:
    def __init__(self, answer):
        self.answer = answer
        self.waits = []

    def wait(self, timeout=None):
        self.waits.append(timeout)
        return self.answer


def _isolation(boundary, child=None):
    a = iso.Isolation.__new__(iso.Isolation)
    a._boundary = boundary
    a._live = {} if child is None else {EID: child}
    a.quarantined = []
    a.quarantine = lambda rec, reason: a.quarantined.append((rec.execution_id, reason))
    return a


def _unavailable(reason, detail):
    """An exception instance for a boundary answer that is an error, not a value."""
    return iso.IsolationUnavailable(reason, detail)


def _record(pid=None, create_time=None):
    return iso.IsolationRecord(execution_id=EID, profile=iso.profile_name(EID), sid='S-1',
                               state='torn_down', owned=True, pid=pid,
                               create_time=create_time)


@pytest.fixture
def clock(monkeypatch):
    now, sleeps = [0.0], []

    def sleep(seconds):
        sleeps.append(seconds)
        now[0] += seconds

    monkeypatch.setattr(iso, 'time', types.SimpleNamespace(monotonic=lambda: now[0],
                                                           sleep=sleep))
    return sleeps


def test_a_live_process_busies_the_release(clock):
    """1216-1218: drop the `process != 'gone'` guard and the delete runs under a live
    process. The result is `busy`, nothing is deleted, nothing is probed."""
    child = Child(None)
    b = Boundary()
    a = _isolation(b, child)
    assert a._remove_profile(_record(), 0) == 'busy'
    assert a.quarantined == [(EID, 'process_alive')]
    assert b.deleted == [] and b.looked == [] and child.waits == [0]
    assert a._live == {EID: child}


def test_an_unavailable_delete_quarantines_with_reason_and_detail(clock):
    """1219-1223: an IsolationUnavailable from the delete must quarantine under
    `reason: detail` and never fall through to the presence read or the release.
    Removing the except arm (or the detail) changes the recorded reason."""
    child = Child(0)
    b = Boundary()
    b.delete_error = iso.IsolationUnavailable('profile_delete', 'in use')
    a = _isolation(b, child)
    assert a._remove_profile(_record(), 0) == 'quarantined'
    assert a.quarantined == [(EID, 'profile_delete: in use')]
    assert b.looked == [] and a._live == {EID: child}


@pytest.mark.parametrize('exists,reason', [
    (True, 'profile_delete_unverified'),
    (_unavailable('profile_state', 'unreadable'), 'profile_presence_unknown'),
], ids=['still-present', 'presence-unknown'])
def test_a_profile_not_confirmed_absent_stays_quarantined(clock, exists, reason):
    """1224-1228: only an explicit `absent` releases. A delete that reports done while
    the profile still answers present, or answers nothing readable, keeps the handle."""
    child = Child(0)
    b = Boundary(exists=exists)
    a = _isolation(b, child)
    assert a._remove_profile(_record(), 0) == 'quarantined'
    assert a.quarantined == [(EID, reason)]
    assert a._live == {EID: child}


def test_only_confirmed_absence_releases_and_drops_the_handle(clock):
    """1229-1230: the handle leaves `_live` and `torn_down` comes back only once the
    profile reads absent. Dropping the absence check, or the pop, is caught here."""
    child = Child(0)
    b = Boundary(exists=False)
    a = _isolation(b, child)
    assert a._remove_profile(_record(), 0) == 'torn_down'
    assert b.deleted == [EID] and a.quarantined == []
    assert a._live == {}


def test_a_core_child_answers_from_its_own_wait(clock):
    """1240-1242: with a Core handle the wait is the answer: None means the process
    still runs, a value means it went. The given wait is passed through unchanged and
    the PID is never read."""
    running = Child(None)
    b = Boundary()
    a = _isolation(b, running)
    assert a._process_state(_record(pid=7, create_time=5.0), 2.5) == 'alive'
    assert running.waits == [2.5] and b.probes == []
    done = Child(0)
    a = _isolation(b, done)
    assert a._process_state(_record(pid=7, create_time=5.0), 2.5) == 'gone'
    assert done.waits == [2.5] and b.probes == []


def test_no_recorded_pid_is_gone_without_a_probe(clock):
    """1243-1244: a record that never got a PID has no process to wait for. Inverting
    the `is None` answer would ask the boundary about PID None."""
    b = Boundary(started=lambda pid: pytest.fail('a PID of None was probed'))
    a = _isolation(b)
    assert a._process_state(_record(pid=None), 5) == 'gone'
    assert b.probes == []


@pytest.mark.parametrize('started', [6.0, None], ids=['reused-pid', 'pid-empty'])

def test_a_reused_pid_or_an_empty_pid_is_gone(clock, started):
    """1252-1254: another creation time under the recorded PID, or no process at all,
    means the recorded process is gone. Treating either as alive would keep the
    profile busy forever; treating the reused PID as the recorded one would release
    it under a stranger."""
    b = Boundary(started=started)
    a = _isolation(b)
    assert a._process_state(_record(pid=7, create_time=5.0), 0) == 'gone'
    assert b.probes == [7]


@pytest.mark.parametrize('create_time,started', [
    (None, 5.0),
    (5.0, _unavailable('process_state', 'unreadable')),
], ids=['creation-time-unrecorded', 'creation-time-unreadable'])
def test_an_unrecorded_creation_time_is_unknown_and_refuses_release(clock, create_time,
                                                                    started):
    """1252-1255: a PID that runs but whose creation time is not recorded, or a PID
    that cannot be read, proves nothing: the state is `unknown`, and the release is
    refused as `process_unverified`, never as `alive` or `gone`."""
    b = Boundary(started=started)
    a = _isolation(b)
    rec = _record(pid=7, create_time=create_time)
    assert a._process_state(rec, 0) == 'unknown'
    assert a._remove_profile(rec, 0) == 'busy'
    assert a.quarantined == [(EID, 'process_unverified')]
    assert b.deleted == []


def test_wait_zero_probes_the_pid_exactly_once(clock):
    """1256-1258: with wait 0 the loop runs one probe, returns its state at once and
    never sleeps. A loop that retries or sleeps first would make a no-wait sweep slow
    and probe a live process again."""
    b = Boundary(started=5.0)
    a = _isolation(b)
    assert a._process_state(_record(pid=7, create_time=5.0), 0) == 'alive'
    assert b.probes == [7] and clock == []


def test_a_boundary_that_fails_mid_wait_is_unknown(clock):
    """1247-1250: the process reads alive on the first probe, then the boundary stops
    answering for the rest of the wait. The state at the deadline is `unknown`, not
    the earlier `alive`, and the release is refused as `process_unverified`."""
    calls = []

    def started(pid):
        calls.append(pid)
        if len(calls) == 1:
            return 5.0
        raise iso.IsolationUnavailable('process_state', 'unreadable')

    b = Boundary(started=started)
    a = _isolation(b)
    rec = _record(pid=7, create_time=5.0)
    assert a._process_state(rec, 1.0) == 'unknown'
    assert len(b.probes) > 1 and clock
    assert a._remove_profile(rec, 1.0) == 'busy'
    assert a.quarantined == [(EID, 'process_unverified')]
    assert b.deleted == []

"""T-1028 — the ten highest-risk UNCOVERED branches of `archeus/node/local.py`
lines 754-929 inclusive (`LocalNode`: the spawn/record path, the isolation ends, the
process identity and the process I/O contract), as unit tests.

The slice was read in chunks of at most 150 lines and walked branch by branch against
the existing coverage the card names (`test_pv20_isolation.py`,
`test_execution_units.py`, `test_fix_batch11.py`, run under a line tracer) and against
every other test in `tests/v1` that names these symbols. The ten rows below are what
no test in the repo asserts; the ones the card's risk probes listed that turned out to
be covered are named in the T-1028 report with their covering test. Every row is about
one thing the card calls the focus: **an end releases only the generation state of the
process it names** — the (execution id, process_seq, pid, create time) it was handed,
never a neighbour's, never a stranger's, never a second time.

The ten branches, highest risk first (each test's docstring names the mutation it
catches):

1  local.py:806-809  `spawn` — the registry line could not be written: the process
                     that DID start is stopped and the failure is a SpawnWriteFailed
2  local.py:872      `alive` — a handle with no recorded create time is never alive,
                     and the OS is asked nothing (a `None == None` reading would be
                     an alive-yes for a pid that no longer exists)
3  local.py:837-839  `fence_isolation` — the why of a fence that did not reach zero is
                     handed back (non-None = no import), after the child was ended
4  local.py:889-893  `kill` — the adapter refuses the pid (`StopRefused`: recycled) and
                     the node says `gone`, raising nothing; a stop that lands is `killed`
5  local.py:904-908  `cancelled` — keyed by (execution id, process_seq): another
                     sequence's stop is never this process's stop
6  local.py:845-849  `end_isolation` — cancels and forgets only THIS execution's
                     children, only the running ones, and passes the teardown answer
7  local.py:912-920  `ended` — an `ended` tombstone that already exists is never
                     rewritten, while the still-held child is ended and forgotten and
                     the registry gets its end line
8  local.py:922-927  `files` — the (marker, pid.json, ended?) contract is read in the
                     order Core unpacks it, and reading it makes nothing
9  local.py:851-859  `reclaim_isolation` — the beat lands BEFORE the sweep, the ledger
                     is read after it, and the released list comes back untouched
10 local.py:880-888  `kill` — no handle is no kill: `gone` with no child cancelled, no
                     adapter asked, no process read

Nothing here is Windows-only and nothing reaches the OS: the seams are the ones the
existing tests use — `claude_sessions.proc.process_create_time` / `kill_pid_tree`, the
adapter's `start`/`resume`/`stop`, the authority's child table, `base.mark_ended` and
`LocalNode._registry`. No DLL, no boundary, no real process, no real registry file.
"""

import os
from types import SimpleNamespace

import pytest

from claude_sessions import proc

from archeus.core.domain import ids
from archeus.harnesses import base
from archeus.infra.paths import ExecPaths
from archeus.node.local import LocalNode

PID = 424242
PID_2 = 424343
CREATION = 'ct-recorded-1'
OTHER_CREATION = 'ct-stranger-2'


def new_id():
    return ids.new_id('execution')


# ── the fakes: what the node is told, and nothing else ────────────────────────

class FakeLaunch:
    """The isolated process Core holds — `MxcChild`'s public shape only: pid, poll,
    cancel, reason. Ends and their order are recorded in the shared log."""

    def __init__(self, pid, log=None, exit_code=None):
        self.pid = pid
        self.reason = None
        self.ends = []
        self.exit_code = exit_code            # what poll() answers
        self.log = log if log is not None else []

    def poll(self):
        return self.exit_code

    def cancel(self, reason):
        self.log.append(('cancel', reason, self.pid))
        self.ends.append(reason)
        if self.reason is None:               # the first stop is the why, as the real one
            self.reason = reason
        if self.exit_code is None:
            self.exit_code = 1
        return self.reason


class FakePlan:
    """The `IsolationContext` a spec rides on: the instrument facts only."""

    def facts(self):
        return {'isolated': True, 'ac_sid': 'S-1-15-3-9-synthetic', 'job': 'core-held'}


class FakeAuthority:
    """Core's isolation authority as the node uses it: the child table, the fence, the
    teardown, the sweep, the plan. It decides nothing that it was not told."""

    def __init__(self, log=None):
        self.log = log if log is not None else []
        self.children = {}
        self.fence_why = None
        self.teardown_out = {'profile': 'torn_down', 'job': 'closed'}
        self.released = []
        self.records = {}
        self.noted = []
        self.plans = []

    def fence(self, execution_id):
        self.log.append(('fence', execution_id))
        return self.fence_why

    def teardown(self, execution_id, *, reason=''):
        self.log.append(('teardown', execution_id, reason))
        return self.teardown_out

    def reclaim(self, live_execution_ids=()):
        self.log.append(('reclaim', tuple(live_execution_ids)))
        return self.released

    def reconcile_ledger(self):
        self.log.append(('reconcile',))

    def record(self, execution_id):
        return self.records.get(execution_id)

    def note_failure(self, spec, err):
        self.noted.append((spec.execution_id, err))

    def request_for(self, spec):
        self.plans.append(spec)
        return FakePlan()


class FakeAdapter:
    """The harness side: which of its three doors was used, and with what."""

    id = 'fake-harness'

    def __init__(self, handle=None, stop_raises=None):
        self.starts = []
        self.resumes = []
        self.stops = []
        self.handle = handle
        self.stop_raises = stop_raises

    def start(self, spec):
        self.starts.append(spec)
        return self.handle

    def resume(self, spec, resume_state):
        self.resumes.append((spec, resume_state))
        return self.handle

    def stop(self, handle, *, grace_s=0.0):
        self.stops.append((handle, grace_s))
        if self.stop_raises is not None:
            raise self.stop_raises


class Node(LocalNode):
    """The real node with one instrument detached: the registry append. Everything
    else it does is the production code of the slice."""

    def __init__(self, isolation, heartbeat=None, registry_fails=None):
        super().__init__(isolation=isolation, heartbeat=heartbeat)
        self.lines = []
        self.registry_fails = registry_fails

    def _registry(self, line):
        if self.registry_fails is not None:
            raise self.registry_fails
        self.lines.append(dict(line))


def _node(**kw):
    log = []
    a = FakeAuthority(log)
    return Node(a, **kw), a, log


def _handle(eid, pid=PID, create_time=CREATION):
    return base.ProcessHandle(eid, pid, create_time, str(ExecPaths(eid).dir))


def _fake_process_reads(monkeypatch, create_time=CREATION):
    """The one OS question the node asks of a process, answered from a knob, with the
    reads recorded: a test fails where a real probe is reached instead of answered."""
    reads = []
    answers = {'create_time': create_time}

    def read(pid):
        reads.append(pid)
        return answers['create_time']

    def kill(pid, ct):                      # nothing here may reach a real tree kill
        raise AssertionError('the real tree kill was reached: %r' % ((pid, ct),))

    monkeypatch.setattr(proc, 'process_create_time', read)
    monkeypatch.setattr(proc, 'kill_pid_tree', kill)
    return reads, answers


def _write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as f:
        f.write(data)


# ── 1. spawn: a registry line Core could not write leaves no live process ─────

def test_a_registry_line_that_cannot_be_written_stops_the_process_it_started(tmp_path):
    """local.py:806-809. Remove the `except OSError` (or the `adapter.stop` inside it)
    and an isolated process keeps running while Core forgets it: the registry is what
    the boot sweep and the e-stop read, so nothing would ever end it again, and the
    manager would charge the end as an isolation failure instead of `workspace`."""
    node, a, log = _node(registry_fails=OSError('disk full'))
    eid = new_id()
    handle = _handle(eid)
    adapter = FakeAdapter(handle=handle)
    spec = base.ExecutionSpec(execution_id=eid, prompt='go', workdir=str(tmp_path))

    with pytest.raises(base.SpawnWriteFailed) as got:
        node.spawn(adapter, spec, isolated=True)

    assert 'registry line not written' in str(got.value) and 'disk full' in str(got.value)
    assert adapter.stops == [(handle, 0.0)]                 # the process it started is ended
    assert len(adapter.starts) == 1 and adapter.resumes == []
    assert node.lines == []                                 # and nothing was recorded
    assert a.noted == []                    # Core's own write failed: not isolation_failed
    assert log == []          # the authority was never asked to end anything of its own


def test_the_process_it_started_is_stopped_once_by_the_adapter_with_no_grace(tmp_path):
    """local.py:806-809, the second order: the one stop goes to the ADAPTER (not to the
    authority) with no grace, and the launch table is never touched — Core holds
    nothing it cannot name."""
    node, a, log = _node(registry_fails=OSError('disk full'))
    eid = new_id()
    handle = _handle(eid)
    adapter = FakeAdapter(handle=handle)
    spec = base.ExecutionSpec(execution_id=eid, prompt='go', workdir=str(tmp_path))

    with pytest.raises(base.SpawnWriteFailed):
        node.spawn(adapter, spec, isolated=True)

    assert [(h, g) for (h, g) in adapter.stops] == [(handle, 0.0)]
    assert a.children == {}                       # never entered the table, so never left
    assert a.plans == [spec] and len(adapter.starts) == 1
    # the process really did start isolated, which is why leaving it running matters
    assert adapter.starts[0].isolation is not None and adapter.resumes == []


# ── 2. alive: an unknown create time is never the same process ────────────────

def test_a_handle_with_no_creation_time_is_never_alive_and_asks_the_os_nothing(monkeypatch):
    """local.py:872. Drop `handle.create_time is not None` and the comparison becomes
    `proc.process_create_time(pid) == None`: for a pid the OS no longer knows that
    answers None, so a handle Core cannot identify reads as ALIVE and the pass waits
    for a process that is gone (and, worse, may match a recycled pid's own reading)."""
    reads, answers = _fake_process_reads(monkeypatch)
    eid = new_id()

    # the fail-open this row holds shut: the OS does not know the pid and answers None,
    # so an unrecorded create time must never be compared against that answer
    answers['create_time'] = None
    assert LocalNode.alive(_handle(eid, create_time=None)) is False
    assert reads == []                                        # the OS was never asked
    assert LocalNode.alive(None) is False                     # no handle at all: no

    # the same handle, with the identity Core recorded: read once, and only then judged
    assert LocalNode.alive(_handle(eid)) is False             # unknown pid: not ours
    assert reads == [PID]
    answers['create_time'] = CREATION
    assert LocalNode.alive(_handle(eid)) is True              # the pair matches: alive
    answers['create_time'] = OTHER_CREATION
    assert LocalNode.alive(_handle(eid)) is False             # the pid moved on


# ── 3. fence: a Job that did not empty is a refusal, not a silence ────────────

def test_a_fence_that_never_reached_zero_comes_back_as_the_why_after_ending_the_child():
    """local.py:837-839. Hard-code `return None` (or return before the children are
    cancelled) and `manager._import` sees quiescence where there is none: it imports
    over a process that may still write. No existing test would notice — every
    assertion on this method in the repo is `is None`."""
    node, a, log = _node()
    eid, other = new_id(), new_id()
    mine = FakeLaunch(PID, log)
    neighbour = FakeLaunch(2001, log)
    a.children.update({(eid, 1): mine, (other, 1): neighbour})
    a.fence_why = '1 process(es) still in its Job after 5s'

    assert node.fence_isolation(eid) == a.fence_why
    assert mine.ends == ['fenced']                    # ours ended before the Job was read
    assert neighbour.ends == []                       # a neighbour's process is not ours
    assert log[:2] == [('cancel', 'fenced', PID), ('fence', eid)]

    # the quiet case still answers None (so the refusal above is not the only answer)
    a.fence_why = None
    assert node.fence_isolation(eid) is None


# ── 4. kill: a pid the adapter refuses is gone, never killed ─────────────────

def test_a_pid_the_adapter_refuses_is_gone_and_a_stop_that_lands_is_killed(monkeypatch):
    """local.py:889-893. Let `StopRefused` escape and the estop/disarmed paths die on
    a stranger's pid instead of reporting the process gone; invert the answer and Core
    reports a kill it never issued."""
    node, a, log = _node()
    eid = new_id()
    handle = _handle(eid)
    reads, _answers = _fake_process_reads(monkeypatch)

    refused = FakeAdapter(handle=handle, stop_raises=base.StopRefused('pid recycled'))
    assert node.kill(refused, handle, reason='estop') == 'gone'
    assert len(refused.stops) == 1 and refused.stops[0] == (handle, 0.0)
    assert a.children == {} and log == [] and reads == [PID]

    landed = FakeAdapter(handle=handle)
    assert node.kill(landed, handle, reason='disarmed') == 'killed'
    assert landed.stops == [(handle, 0.0)]


# ── 5. cancelled: a stop belongs to the process that was stopped ─────────────

def test_a_stop_of_another_process_sequence_is_never_this_process_stop():
    """local.py:904-908. Read the child by execution id alone (or return True for any
    child found) and a resume reports the stop of the process that came before it: the
    end is recorded as Core's kill when the agent exited on its own, or the reverse."""
    node, a, log = _node()
    eid, other = new_id(), new_id()
    held = FakeLaunch(PID, log)
    held.cancel('estop')
    self_ended = FakeLaunch(PID_2, log)               # running, never stopped by Core
    exited = FakeLaunch(2001, log, exit_code=0)       # gone by itself, never stopped
    a.children.update({(eid, 2): held, (eid, 3): self_ended, (eid, 4): exited})
    handle = _handle(eid)

    assert node.cancelled(handle, 2) is True          # the sequence Core stopped
    assert node.cancelled(handle, 3) is False         # its own exit, not Core's stop
    assert node.cancelled(handle, 1) is False         # the sequence that already ended
    assert node.cancelled(handle, 4) is False    # an exit Core never asked for is not its stop
    assert node.cancelled(_handle(other), 2) is False     # another execution's stop
    assert held.ends == ['estop'] and self_ended.ends == [] and exited.ends == []


# ── 6. end_isolation: an end releases one execution's generation, no more ─────

def test_ending_one_execution_releases_only_that_executions_processes():
    """local.py:845-849. Drop the `k[0] == execution_id` guard (or the running filter)
    and one execution's end cancels and forgets the launches of its neighbours — the
    sole holder stops a process it does not own and drops the table entry that a later
    kill would have found."""
    node, a, log = _node()
    eid, other = new_id(), new_id()
    live = FakeLaunch(PID, log)
    exited = FakeLaunch(PID_2, log, exit_code=3)
    neighbour = FakeLaunch(2001, log)
    a.children.update({(eid, 1): live, (eid, 2): exited, (other, 1): neighbour})

    out = node.end_isolation(eid, reason='the mission ended')

    assert out is a.teardown_out                                  # Core's answer, passed on
    assert live.ends == ['the mission ended'] and live.reason == 'the mission ended'
    assert exited.ends == []                                      # already gone: ended twice
    assert neighbour.ends == []                                   # not this one's to end
    assert list(a.children) == [(other, 1)]                       # only ours forgotten
    assert log == [('cancel', 'the mission ended', PID),
                   ('teardown', eid, 'the mission ended')]


def test_an_end_with_no_reason_still_ends_the_process_as_ended():
    """local.py:846. Remove `reason or 'ended'` and a nameless end cancels the launch
    with an empty reason: the quarantine line and the ledger record say nothing about
    why that process ended, and the ledger is what a restarted Core reads."""
    node, a, log = _node()
    eid = new_id()
    live = FakeLaunch(PID, log)
    a.children[(eid, 1)] = live

    node.end_isolation(eid)

    assert live.ends == ['ended'] and live.reason == 'ended'
    assert log[-1] == ('teardown', eid, '')


# ── 7. ended: the tombstone is written once, the table is emptied always ──────

def test_an_end_that_is_already_tombstoned_never_rewrites_the_record(monkeypatch):
    """local.py:912-920. Drop the `if not os.path.exists(paths.ended)` guard and a
    second observation (an end read twice, or an exit after a failed spawn wrote the
    tombstone) overwrites the exit code and the reason the first one recorded — the
    file a restarted Core reads back as what happened."""
    node, a, log = _node()
    eid = new_id()
    paths = ExecPaths(eid)
    _write(paths.ended, b'{"exit_code": 71, "at": 1}\n')          # what really happened
    held = FakeLaunch(PID, log)
    a.children[(eid, 1)] = held
    writes = []
    monkeypatch.setattr(base, 'mark_ended',
                        lambda p, code, **kw: writes.append((p, code)))

    node.ended(_handle(eid), 0, 1)

    with open(paths.ended, 'rb') as f:
        assert f.read() == b'{"exit_code": 71, "at": 1}\n'
    assert writes == []                                           # never rewritten
    assert held.ends == ['ended'] and held.reason == 'ended'      # the launch was ended
    assert a.children == {}                                       # and forgotten
    assert [(x['op'], x['execution_id'], x['process_seq']) for x in node.lines] == \
        [('end', eid, 1)]


def test_the_first_end_writes_the_tombstone_with_the_code_it_observed(monkeypatch):
    """local.py:917-918, the positive control for the row above: with no tombstone
    there is one write, and it carries the exit code Core observed."""
    node, a, log = _node()
    eid = new_id()
    writes = []
    monkeypatch.setattr(base, 'mark_ended',
                        lambda p, code, **kw: writes.append((p.ended, code)))

    node.ended(_handle(eid), 3, 1)

    assert writes == [(ExecPaths(eid).ended, 3)]
    assert [(x['op'], x['process_seq']) for x in node.lines] == [('end', 1)]


# ── 8. files: the contract is read in the order Core unpacks it ──────────────

def test_the_process_files_are_read_in_the_order_core_unpacks_them():
    """local.py:922-927. Swap two members of the returned tuple (or read `ended` for
    the marker) and `manager._reconcile_one` unpacks a marker where it wants pid.json:
    `pid['pid']` dies, or the execution is reconciled with no handle at all and its
    running process is recorded as never having started. Reading it must also make
    nothing: an absent execution's directory stays absent."""
    node, a, log = _node()
    eid, absent = new_id(), new_id()

    assert node.files(absent) == (None, None, False)
    assert not os.path.exists(ExecPaths(absent).dir)             # a read, not a mkdir

    paths = ExecPaths(eid)
    _write(paths.spawning, b'{"process_seq": 2}\n')
    _write(paths.pid, b'{"pid": 4242, "create_time": "ct-1", "process_seq": 2}\n')
    assert node.files(eid) == ({'process_seq': 2},
                               {'pid': 4242, 'create_time': 'ct-1', 'process_seq': 2},
                               False)
    _write(paths.ended, b'{"exit_code": 3, "at": 1}\n')
    marker, pid, ended = node.files(eid)
    assert marker == {'process_seq': 2} and pid['pid'] == 4242 and ended is True


# ── 9. reclaim: the beat lands before the work, the ledger after it ──────────

def test_a_sweep_beats_first_reads_the_ledger_last_and_reports_what_it_released():
    """local.py:851-859. Move `heartbeat.beat()` after the reclaim and a sweep that
    blocks starves the B13 watchdog, which kills a Core that is merely busy; drop
    `reconcile_ledger()` and the journals of ends no Core verified are never read."""
    node, a, log = _node(heartbeat=SimpleNamespace(beat=lambda: log.append(('beat',))))
    eid = new_id()
    a.released = [eid]

    assert node.reclaim_isolation({eid}) == [eid]
    assert log == [('beat',), ('reclaim', (eid,)), ('reconcile',)]

    quiet = Node(a)                                   # no sender at all
    a.log = []
    assert quiet.reclaim_isolation(()) is a.released  # nothing beats, the sweep still runs
    assert a.log == [('reclaim', ()), ('reconcile',)]


# ── 10. kill with no identity is a refusal, not a hunt ────────────────────────

def test_no_handle_is_no_kill_and_asks_the_os_and_the_adapter_nothing(monkeypatch):
    """local.py:880-888. Remove the `handle is None` refusal and the next line walks
    `handle.execution_id` on nothing; make the empty-table case fall through to the
    adapter and Core stops whatever pid a stale line happens to name."""
    node, a, log = _node()
    reads, answers = _fake_process_reads(monkeypatch, create_time=OTHER_CREATION)
    eid = new_id()
    held = FakeLaunch(PID, log)
    a.children[(eid, 1)] = held
    adapter = FakeAdapter(handle=_handle(eid))

    assert node.kill(adapter, None) == 'gone'
    assert adapter.stops == [] and held.ends == [] and log == []
    assert reads == []                        # an absent identity asks the OS nothing
    assert list(a.children) == [(eid, 1)]

    # a process Core does not hold and the OS does not recognise is gone, not killed
    stranger = new_id()
    assert node.kill(adapter, _handle(stranger)) == 'gone'
    assert adapter.stops == [] and a.children == {(eid, 1): held}
    assert reads == [PID]                     # the one identity read, and it did not match

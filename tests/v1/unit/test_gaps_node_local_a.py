"""T-777: the highest-risk branches of `archeus/node/local.py` (the first 650 lines:
`MxcLaunch` and the process half of `LocalNode`) that no other test of this suite
ever entered.

The list was made by reading the module and asking, of every branch, whether some
test in `tests/v1` has a line that enters it *as a decision*: a branch no line ever
enters, or one that every existing line satisfies only by accident — `type(n) is int`
never asked of anything but an integer, `except StopRefused` never reached without a
real pid that had really gone — is a branch this suite does not have, and a mutation
of it walks unseen. In order of what their loss would cost:

1   :211  an MXC launch with no transport at all is refused, before one artifact hash
2   :326  a drain that raised ends the execution it could not finish
3   :329  a launcher answer that is not an exact integer is never an exit code
                                        (`None` is covered by `test_pv20_mxc_local.py`;
                                        `True` and `0.0`, which `isinstance` would
                                        believe, are not)
4   :390  a Job count that is not exactly the integer zero is never quiescence
                                        (integers are; `0.0`, `False`, `'0'` are not)
5   :416  a completion the journal could not take is never reported clean
6   :444  a quarantine that could not be written never turns an unverified end clean
7   :439  the quarantine line is written once, however many ends arrive
8   :541  no recorded PID makes no handle, and no kill
9   :549  a process the node cannot identify is never alive, and never asked about
10  :568  only the recorded pair is ever handed to a kill

and the ten that the first ten exposed, each named with what the suite already does
and does not assert about it: :321 (waiting a launch that never started —
`test_pv20_mxc_staging_gaps.py` covers the refusal, not that the journal was left
empty), :388 (a Job that needs a second reading: `test_mxc_wire.py:533` counts the
readings and bounds the wait, but the pause it injects throws its argument away, and no
test names `MXC_QUIESCENCE_POLL_S`), :482
(a spawn clears the flags the hook halts on before the harness is
asked), :486 (a spawn with a state to continue is handed to `resume`, never started
afresh — no test of any kind passes `resume_state` to `LocalNode.spawn`), :488 (the
spawn arms are split in `test_pv20_isolation.py`, which looks neither at the registry
nor at an unfrozen record), :555 (a kill refused between the liveness check and the
stop, which only `test_skeleton.py` reads, and there with two real processes), :573
(the first tombstone stays), :582 (absent contract files read as absent), :596 (a
torn registry line is skipped in `test_node_local_staging_gaps.py`; a line that is
valid JSON and not an object is nowhere), :630 (a flag outside the three the hook
reads is never written). Each row below states the branch it would catch.

Everything runs on fakes at the seams the module already injects or reads through
its own module attributes: the MXC backend, the launcher child, the Job member
count, the ledger, the clock, the pause, and the two `proc` reads of the P0.5 seam.
Both are pinned by fixtures below: no row reaches the operating system's process
table, and no row starts Git, so the file decides the same thing on Linux and on
Windows and never waits for a real process. The real writer is not faked where the
file claims anything about durability: the MXC rows journal to a real
`mxc_ledger.Ledger`, because a quarantine that was never written is exactly the
failure these rows are about.

Style follows `tests/v1/unit/test_gaps_core_execution_manager.py` (the sibling gaps
file) and `tests/v1/integration/test_pv20_mxc_local.py` (the MxcLaunch fixtures).
"""

import hashlib
import io
import json
import os
from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from archeus.core.domain import entities, ids
from archeus.harnesses import base
from archeus.infra import paths
from archeus.node import local, mxc_ledger, staging
from archeus.node.local import FLAGS, LocalNode

#: the identity the scripted process table answers with, and the identity the
#: launcher child is created under: a pair, never a pid (p11-design-gate §15.1)
CREATED = 1771234567
PID = 4242


# ── the guards: nothing here is allowed to touch this machine ────────────────

@pytest.fixture(autouse=True)
def pinned_process_table(monkeypatch):
    """Neither process-table read leaves the process. A row that reaches for the
    operating system's answer about a pid — instead of the one it scripted with
    `seams` below — fails here rather than passing or failing on whatever the
    machine running the suite happened to be running when it started."""
    def refusal(*args, **kwargs):
        raise AssertionError('a node test asked the operating system about a process')
    monkeypatch.setattr(local.proc, 'process_create_time', refusal)
    monkeypatch.setattr(local.proc, 'kill_pid_tree', refusal)


@pytest.fixture(autouse=True)
def no_stray_git(monkeypatch):
    """The other half of this module is Git (the worktrees and the store reads past
    line 650); no row here means to start it, and none may."""
    def refusal(*args, **kwargs):
        raise AssertionError('Git was reached by a call that must never reach it')
    monkeypatch.setattr(local, '_git_exe', refusal)


@pytest.fixture
def seams(monkeypatch):
    """The process table as an instrument: every question the node asks about a pid
    is recorded and answered from what the row scripted, and a question asked more
    often than it was scripted fails the row. Returns the installer, so one row can
    ask twice with two different answers."""
    def install(create_times=(), kill=True):
        return _ProcessTable(monkeypatch, create_times, kill)
    return install


class _ProcessTable:
    """`proc.process_create_time` and `proc.kill_pid_tree` — the two reads this
    module makes of the operating system's process table — scripted."""

    def __init__(self, monkeypatch, create_times, kill):
        self._answers, self._kill = list(create_times), kill
        self.asked, self.killed = [], []
        monkeypatch.setattr(local.proc, 'process_create_time', self.create_time)
        monkeypatch.setattr(local.proc, 'kill_pid_tree', self.kill_pid_tree)

    def create_time(self, pid):
        self.asked.append(pid)
        if not self._answers:
            raise AssertionError('the process table was asked more often than scripted')
        return self._answers.pop(0)

    def kill_pid_tree(self, pid, create_time):
        self.killed.append((pid, create_time))
        return self._kill


class Adapter:
    """One harness, as the node's `kill` asks it: stop the process, or refuse."""

    def __init__(self, fault=None):
        self.fault, self.stopped = fault, []

    def stop(self, handle, *, grace_s):
        self.stopped.append((handle, grace_s))
        if isinstance(self.fault, Exception):
            raise self.fault


def _handle(execution_id, pid=PID, create_time=CREATED):
    return base.ProcessHandle(execution_id, pid, create_time,
                              paths.ExecPaths(execution_id).dir)


def _execution(pid=PID, create_time=CREATED):
    """A running execution's row, the way the manager holds it when it asks the node
    for the handle of its current process."""
    return entities.Execution(id=ids.new_id('execution'), task_id=ids.new_id('task'),
                              mission_id=ids.new_id('mission'), attempt=1, state='RUNNING',
                              pid=pid, create_time=create_time)


# ── the MXC world ────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Policy:
    """A compiled policy as an injected backend answers it: `mxc.MxcPolicy`'s shape,
    the transport's own validation left where it belongs."""
    raw: dict


class Launcher:
    """The launcher child the transport hands back. Two readings live here and are
    never mixed up — the exit the launcher reports, and the outcome the Core-owned
    reader takes from the streams — plus the handles the node must close."""

    def __init__(self, exit=0, *, pid=PID, create_time=CREATED, fault=None):
        self.pid, self.create_time = pid, create_time
        self.exit, self.fault = exit, fault
        self.stdin, self.stdout, self.stderr = io.BytesIO(), io.BytesIO(), io.BytesIO()
        self.drains, self.closes = [], 0

    def wait(self, timeout=None, *, cancelled=None):
        self.drains.append((timeout, cancelled))
        if isinstance(self.fault, Exception):
            raise self.fault
        return self.exit

    def close(self):
        self.closes += 1

    def terminate(self):
        raise AssertionError('closing the Job belongs to the caller that holds it')


class Transport:
    """The MXC backend: it compiles, creates suspended, and owes the ledger its
    ownership seam between the verified membership and the single resume (the order
    `mxc.FakeMxc` follows). Every step is recorded; each can be scripted to fail."""

    def __init__(self, launcher=None, *, fault=None):
        self.launcher = launcher if launcher is not None else Launcher()
        self.fault = fault
        self.calls, self.events = [], []

    def compile_policy(self, *, workspace, readonly, denied, cwd, command_line, env,
                       timeout_ms, ui, egress, proxy_url, capabilities=None):
        assert ui is False and egress == 'deny' and proxy_url is None
        self.calls.append('compile')
        return Policy({'version': '1.0.0', 'containment': 'processcontainer',
                       'filesystem': {'readwritePaths': [workspace],
                                      'readonlyPaths': list(readonly),
                                      'deniedPaths': list(denied)}})

    def spawn(self, policy, *, exe, job, before_resume=None):
        self.calls.append(('spawn', exe, job))
        if isinstance(self.fault, Exception):
            raise self.fault
        self.events.extend(('create_suspended', 'assign_job', 'verify_job'))
        if before_resume is not None:
            before_resume(self.launcher)
        self.events.append('resume')
        return self.launcher


class Boundary:
    """Core's held Job as an instrument reads it: the member count, answered as the
    row scripted it — including the answers that are not counts at all."""

    def __init__(self, answers):
        self.answers, self.seen = list(answers), []

    def job_active_processes(self, job):
        self.seen.append(job)
        answer = self.answers[0] if len(self.answers) == 1 else self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


class Mxc:
    """One MXC execution's world: the pinned fake SDK, the workspace and the runtime
    directory the policy grants, a ledger of its own, and the clock and the pause the
    bounded quiescence reads — so no row of this file ever sleeps."""

    def __init__(self, root):
        self.sdk = root / 'sdk'
        (self.sdk / 'bin' / 'x64').mkdir(parents=True)
        (self.sdk / 'package.json').write_text(json.dumps(
            {'name': staging.MXC_PACKAGE, 'version': staging.MXC_VERSION}),
            encoding='utf-8')
        (self.sdk / staging.MXC_EXE).write_bytes(b'the fake launcher')
        self.pins = {rel: hashlib.sha256((self.sdk / rel).read_bytes()).hexdigest()
                     for rel in ('package.json', staging.MXC_EXE)}
        self.work = str(root / 'work')
        os.mkdir(self.work)
        self.runtime = str(root / 'runtime')
        os.mkdir(self.runtime)
        self.ledger = mxc_ledger.Ledger(str(root / 'ledger'))
        self.times = [float(step) for step in range(30)]
        self.pauses = []

    def clock(self):
        return self.times.pop(0) if self.times else 1000.0

    def args(self):
        """The launch's own arguments: everything but the transport and the reader."""
        return dict(sdk_root=self.sdk, pins=self.pins, workspace=self.work,
                    readonly=(self.runtime,), cwd=self.work,
                    command_line='fixture command', timeout_ms=1000)

    def launch(self, *, transport=None, outcome=None, ledger=False, boundary=None,
               resource_reader=None, broker=None, execution_id='exec_mxc', **over):
        """A launch with everything it can touch injected. `ledger=True` hands it the
        journal, and `boundary` the caller's Job, before it starts — which is the
        only order either means anything in; the native-parts wiring that builds
        them into the transport is `test_mxc_wire.py`'s, not this file's."""
        args = self.args()
        args.update(backend=transport if transport is not None else Transport(),
                    outcome=outcome if outcome is not None else (lambda p: 0),
                    execution_id=execution_id, broker=broker,
                    resource_reader=resource_reader, clock=self.clock,
                    pause=self.pauses.append, quiescence_wait=0.0)
        args.update(over)
        launch = local.MxcLaunch(**args)
        if ledger:
            launch.ledger, launch.journal = self.ledger, mxc_ledger.journal_name(execution_id, 1)
        launch.boundary = boundary
        return launch

    def records(self, execution_id='exec_mxc'):
        journal = mxc_ledger.journal_name(execution_id, 1)
        data = self.ledger.journals().get(journal, b'')
        rows, _invalid = mxc_ledger.read_records(data, journal)
        return rows

    def ops(self, execution_id='exec_mxc'):
        return [row['op'] for row in self.records(execution_id)]


@pytest.fixture
def mxc(tmp_path):
    return Mxc(tmp_path)


# ── 1. the launches that are refused, and what they left un-touched ──────────

def test_a_launch_with_no_transport_at_all_is_refused(mxc, monkeypatch):
    """`local.py:211-212` — `elif backend is None: raise`.

    Removes the refusal: no transport means nothing that could create a process, so
    the row asserts both halves. The refusal itself, and that not one artifact was
    hashed, no grant scanned and no policy compiled to get there — a launch that
    got as far as the pin digests would be a launch Core could believe existed."""
    hashed = []
    real = staging.verify_mxc

    def spy(root, *, pins):
        hashed.append(str(root))
        return real(root, pins=pins)
    monkeypatch.setattr(staging, 'verify_mxc', spy)
    with pytest.raises(staging.StageError, match='explicitly injected backend'):
        local.MxcLaunch(outcome=lambda process: 0, **mxc.args())
    assert hashed == []


def test_waiting_a_launch_that_never_started_is_refused_and_journals_nothing(mxc):
    """`local.py:321-322` — `if self.process is None: raise` in `wait`.

    Removes the guard: `wait()` would read the exit off a process that was never
    created, and (through `_end`) journal an end for an execution that never
    began. The row asserts the refusal, and that the journal holds nothing at all:
    not even the intent, which is written only by a start."""
    launch = mxc.launch(ledger=True)
    with pytest.raises(staging.StageError, match='has not started'):
        launch.wait()
    assert launch.end_state is None and launch.completed is None
    assert launch.backend.calls == ['compile']       # nothing was ever spawned
    assert mxc.ops() == []


# ── 2. the two exits, kept apart ─────────────────────────────────────────────

def test_a_drain_that_raised_ends_the_execution_it_could_not_finish(mxc):
    """`local.py:326-327` — `except BaseException: self._end(reason=..., None); raise`.

    Removes the ending (or lets the exception escape first): an execution whose
    streams broke mid-drain would be left with no end at all — no quarantine, no
    closed handles — while the manager is told it merely failed. The row asserts the
    fault still reaches the caller, that the handles were closed, and that the
    journal was quarantined rather than completed."""
    transport = Transport(Launcher(fault=OSError('the stream pipe broke')))
    launch = mxc.launch(transport=transport, ledger=True)
    launch.start(job=object())
    with pytest.raises(OSError, match='pipe broke'):
        launch.wait()
    assert launch.completed is None and launch.end_state['state'] == mxc_ledger.DEAD_UNVERIFIED
    assert transport.launcher.closes == 1             # our handles, never the Job's
    assert transport.launcher.drains == [(None, None)]   # what was asked of the reader
    assert mxc.ops() == ['intent', 'ownership', 'quarantine']


@pytest.mark.parametrize('answer', [None, True, 0.0, '0'],
                         ids=['no-answer', 'true', 'float-zero', 'text-zero'])
def test_a_launcher_answer_that_is_not_an_integer_is_never_an_exit_code(mxc, answer):
    """`local.py:329-331` — `if type(self.launcher_exit) is not int:`.

    Weakens it to `isinstance` (or drops it) and the `True` answer below is the
    launcher's exit code 1 — a workload that never reported an exit is reported as
    having exited — and `0.0` becomes 0. The row asserts the refusal, that nothing
    was completed, and that the end was quarantined either way."""
    transport = Transport(Launcher(exit=answer))
    launch = mxc.launch(transport=transport, ledger=True)
    launch.start(job=object())
    with pytest.raises(staging.StageError, match='has not exited'):
        launch.wait()
    assert launch.completed is None and launch.launcher_exit == answer
    assert launch.end_state['state'] == mxc_ledger.DEAD_UNVERIFIED
    assert mxc.ops() == ['intent', 'ownership', 'quarantine']


# ── 3. quiescence, the ending's only proof that the tree is empty ────────────

@pytest.mark.parametrize('answer,clean', [
    pytest.param(0, True, id='the-count-zero'),                 # the one answer that is empty
    pytest.param(0.0, False, id='float-zero'),                  # equals zero; is not a count
    pytest.param(False, False, id='a-bool'),                    # False == 0; a bool is no count
    pytest.param('0', False, id='text-zero'),                   # the instrument answered in text
])
def test_only_an_exact_zero_from_the_job_reads_as_no_members(mxc, answer, clean):
    """`local.py:390-391` — `if type(n) is int and n == 0: return None`.

    Weakens the type test (`n == 0`, or `isinstance(n, int)`) and every non-integer
    answer below is believed: the Job that never reported its members at all becomes
    an empty Job, the end is DEAD_CLEAN, the completion is journalled, and Core
    retires an execution whose tree nobody counted. The `0` row is the control that
    keeps the assertion honest: with the exact integer the end *is* clean."""
    transport = Transport()
    boundary = Boundary([answer])
    job = object()                                    # the handle Core holds
    launch = mxc.launch(ledger=True, transport=transport, boundary=boundary,
                        resource_reader=lambda execution_id, owner: True)
    launch.start(job=job)
    assert launch.wait() == 0                        # the launcher exit stands either way
    expect = mxc_ledger.DEAD_CLEAN if clean else mxc_ledger.DEAD_UNVERIFIED
    assert launch.end_state['state'] == expect
    assert boundary.seen == [job]                    # the count was read, of the caller's Job
    assert transport.events == ['create_suspended', 'assign_job', 'verify_job',
                               'resume']              # one launch, which is what was counted
    assert mxc.ops() == (['intent', 'ownership', 'disposal', 'completion'] if clean
                         else ['intent', 'ownership', 'quarantine'])


def test_a_boundary_that_takes_a_second_reading_is_still_counted_within_the_bound(mxc):
    """`local.py:388-394` — the poll loop: `if self.clock() >= deadline: return 'the Job
    answered %r, not zero members'`, and the injected `self.pause(MXC_QUIESCENCE_POLL_S)`
    between two readings of the Job.

    Replace the injected pause with a real sleep and every busy Job puts the suite — and
    Windows CI with it — to sleep for the poll interval; drop the bound and an execution
    whose Job answers members forever is never ended at all. The readings and their bound
    are `test_mxc_wire.py:533`'s already; what the loop waits *with* is asserted nowhere,
    because the pause that file injects discards its argument and no test names
    `MXC_QUIESCENCE_POLL_S`. The row scripts a Job that is busy and then empty against a
    clock that moves, and asserts the end is clean, that the boundary was asked exactly
    twice, and that what was waited on is the module's own interval."""
    boundary = Boundary([2, 0])
    job = object()
    launch = mxc.launch(ledger=True, boundary=boundary,
                        resource_reader=lambda execution_id, owner: True,
                        quiescence_wait=5.0)
    launch.start(job=job)
    assert launch.wait() == 0
    assert launch.end_state['state'] == mxc_ledger.DEAD_CLEAN
    assert launch.end_state['quiescence'] is None      # empty, on the second reading
    assert boundary.seen == [job, job]                 # asked twice, and only twice
    assert mxc.pauses == [local.MXC_QUIESCENCE_POLL_S]  # injected, never slept
    assert mxc.ops() == ['intent', 'ownership', 'disposal', 'completion']


def test_a_completion_the_journal_could_not_take_is_never_reported_clean(mxc, monkeypatch):
    """`local.py:416-418` — `except Exception as err: self._quarantine('completion
    unrecorded: %s' ...)`.

    Removes it and a journal that refused the completion line leaves the end
    DEAD_CLEAN: Core retires an execution whose end was never written, and a
    restarted Core — reading a journal that stops at `disposal` — reconciles it as
    though it had never finished. The `dispose` failure next door is already covered
    by `test_mxc_wire.py`; this one is not. The row asserts the launcher exit is
    still returned, the end is unverified, and the journal's last line is a
    quarantine with this reason and no completion."""
    launch = mxc.launch(ledger=True, boundary=Boundary([0]),
                        resource_reader=lambda execution_id, owner: True)
    launch.start(job=object())

    def refuse(execution_id, outcome):
        raise OSError('the journal would not take it')
    monkeypatch.setattr(mxc.ledger, 'complete', refuse)
    assert launch.wait() == 0
    assert launch.end_state['state'] == mxc_ledger.DEAD_UNVERIFIED
    assert mxc.ops() == ['intent', 'ownership', 'disposal', 'quarantine']
    assert [row['reason'] for row in mxc.records() if row['op'] == 'quarantine'] \
        == ['completion unrecorded: OSError']


def test_a_quarantine_that_cannot_be_written_never_turns_an_end_clean(mxc, monkeypatch):
    """`local.py:441-445` — `_quarantine`'s `except Exception: pass`, and the state
    `_settle` returns regardless of it.

    Turns the swallow into a raise and the caller loses the ending it was told to
    report; drops the `return DEAD_UNVERIFIED` that follows it and an execution whose
    Job was never read empty, whose quarantine could not be written, is retired as
    DEAD_CLEAN. The row asserts the fault never reaches the caller, the state is
    unverified, and the ledger kept exactly what it could: the two lines written
    before this one."""
    launch = mxc.launch(ledger=True)                  # no boundary: the Job is never read
    launch.start(job=object())                       # so the end is unverified by nature
    real = mxc.ledger.append

    def refuse(execution_id, op, **facts):
        if op == 'quarantine':
            raise OSError('the journal is full')
        return real(execution_id, op, **facts)
    monkeypatch.setattr(mxc.ledger, 'append', refuse)
    assert launch.cancel(reason='cancelled')['state'] == mxc_ledger.DEAD_UNVERIFIED
    assert launch.end_state['reason'] == 'cancelled'
    assert mxc.ops() == ['intent', 'ownership']


def test_the_quarantine_line_is_written_once_however_many_ends_arrive(mxc, monkeypatch):
    """`local.py:439,447-453` — `if self.ledger is None or self._quarantined(): return`.

    Removes the read-back and every later end of the same execution asks the journal
    for another quarantine line: the journal — Core's evidence of what was and was not
    verified at the end — stops being one account of one ending, and a restart that
    reads it cannot tell this from several unverified ends. The row ends the same
    execution twice, from two launches over one journal, and asserts both that the
    journal was asked for one quarantine line, however many ends arrived, and that
    what it holds is the first ending's reason."""
    asked = []
    real = mxc.ledger.append

    def record(execution_id, op, **facts):
        asked.append(op)
        return real(execution_id, op, **facts)
    monkeypatch.setattr(mxc.ledger, 'append', record)
    first = mxc.launch(ledger=True)
    first.start(job=object())
    assert first.cancel(reason='the first end')['state'] == mxc_ledger.DEAD_UNVERIFIED
    second = mxc.launch(ledger=True)                  # the same execution id, one journal
    assert second.cancel(reason='a later Core')['state'] == mxc_ledger.DEAD_UNVERIFIED
    assert asked.count('quarantine') == 1             # not asked again, and so not refused
    assert mxc.ops().count('quarantine') == 1
    assert [row['reason'] for row in mxc.records() if row['op'] == 'quarantine'] \
        == ['QUARANTINE_UNVERIFIED: no boundary Job was held to read']


# ── 4. the process identity, and every act that may follow it ────────────────

def test_a_process_the_node_cannot_identify_is_never_alive_and_was_never_asked_about(seams):
    """`local.py:549-550` — `handle is not None and handle.create_time is not None
    and proc.process_create_time(handle.pid) == handle.create_time`.

    Drops the middle term and `alive` asks the operating system the creation time of
    a pid whose creation time Core never recorded; whatever it answers is then
    compared to `None`, and a pid the node has no identity for becomes a live
    process of ours — which is what a kill is then issued against. The row asserts
    the answer is `False` *and* that the seam was never consulted; the recorded pair
    that matches is alive, and the pid now held by another process is not."""
    node = LocalNode()
    eid = ids.new_id('execution')
    unknown = _handle(eid, create_time=None)
    table = seams([CREATED, CREATED])                 # the table would confirm this pid
    assert node.alive(unknown) is False
    assert table.asked == []                          # and was never asked
    assert node.alive(_handle(eid)) is True           # ours: the pair agrees
    assert node.alive(_handle(eid, create_time=1)) is False   # the pid was recycled
    assert table.asked == [PID, PID]                  # both readings, and only those


def test_a_process_core_never_recorded_makes_no_handle_and_no_kill(seams):
    """`local.py:541-544` — `if execution.pid is None: return None`.

    Removes it and `ProcessHandle(execution.id, None, ...)` is built anyway: the
    node is then asked to check liveness, and to kill, a process with no pid — the
    kill path reaching the operating system with `pid=None`. The row asserts that an
    execution which never got a process produces no handle at all, that killing
    nothing is `'gone'` and never `'killed'`, that neither the adapter nor the
    process table was touched, and — the control — that a recorded process yields
    the identity, the pid, the pair and where its own files are."""
    node = LocalNode()
    table = seams([])
    adapter = Adapter()
    never_spawned = _execution(pid=None, create_time=None)
    assert node.handle(never_spawned) is None
    assert node.kill(adapter, None) == 'gone'
    assert adapter.stopped == [] and table.asked == []
    running = _execution()
    got = node.handle(running)
    assert (got.execution_id, got.pid, got.create_time) == (running.id, PID, CREATED)
    assert got.exec_dir == paths.ExecPaths(running.id).dir


@pytest.mark.parametrize('recorded,answer,fault,expect', [
    # ours, still running: a kill was issued, and that is what is reported
    pytest.param(CREATED, CREATED, None, 'killed', id='ours-still-running'),
    # ours when it was checked, someone else's by the time the stop was reached
    pytest.param(CREATED, CREATED, base.StopRefused('the pid is not ours'), 'gone',
                 id='refused-at-the-stop'),
    # the table already says the recorded pid is a different process
    pytest.param(CREATED, 999, None, 'gone', id='recycled-before-the-check'),
    # no recorded identity to check at all
    pytest.param(None, CREATED, None, 'gone', id='no-recorded-identity'),
])
def test_a_kill_is_issued_only_for_a_process_that_is_still_the_recorded_one(
        seams, recorded, answer, fault, expect):
    """`local.py:552-561` — `if handle is None or not self.alive(handle): return
    'gone'`, `except base.StopRefused: return 'gone'`, and the `'killed'` only after
    a stop that was accepted.

    Removes the `StopRefused` arm and a pid recycled between the liveness check and
    the stop is reported `'killed'`: Core ends the execution believing its own process
    was killed, while the process it was told about is a stranger's. Removes the
    liveness check and the stranger is stopped. Either way the row asserts the word
    the node reports, whose adapter calls made it true, and which pids the operating
    system was asked about."""
    node = LocalNode()
    table = seams([answer])
    adapter = Adapter(fault=fault)
    handle = _handle(ids.new_id('execution'), create_time=recorded)
    assert node.kill(adapter, handle) == expect
    attempted = recorded is not None and answer == recorded   # alive, as far as it could tell
    assert [stopped for stopped, _ in adapter.stopped] == ([handle] if attempted else [])
    assert table.asked == ([] if recorded is None else [PID])


def test_only_the_recorded_pair_is_ever_handed_to_a_kill(seams):
    """`local.py:564-568` — `return proc.kill_pid_tree(handle.pid, handle.create_time)`.

    Passes the pid alone (the historical bug this whole design exists for, the T-047
    PID-recycling kill) and every call below kills whatever holds that pid now; drops
    the returned verdict and a kill that was refused reads as one that was issued.
    The row asserts the pair the operating system was handed, that the verdict is
    passed through unchanged in both directions, and that no probe was made first:
    this is the path taken when there is nobody else to ask."""
    node = LocalNode()
    for verdict in (True, False):
        table = seams([], kill=verdict)
        handle = _handle(ids.new_id('execution'))
        assert node.kill_identity(handle) is verdict
        assert table.killed == [(PID, CREATED)]       # never the pid alone
        assert table.asked == []


def test_the_tombstone_of_the_first_end_is_the_one_that_stays(seams):
    """`local.py:573-576` — `if not os.path.exists(paths.ended): base.mark_ended(...)`,
    with the registry's end line written either way.

    Removes the guard and a second end of the same process rewrites the tombstone:
    the exit code of a process that was already observed dead becomes whatever a
    later reader brought, and the evidence of what actually ended is gone. The row
    writes one end, then a contradicting one, and asserts the tombstone still holds
    the first exit code while the registry holds both ends."""
    node = LocalNode()
    eid = ids.new_id('execution')
    handle = _handle(eid)
    node.ended(handle, 7, 1)
    node.ended(handle, 0, 1)                          # a later end, a different reading
    assert base.read_json(paths.ExecPaths(eid).ended)['exit_code'] == 7
    ends = [line for line in LocalNode.registry() if line['op'] == 'end']
    assert [(line['execution_id'], line['process_seq']) for line in ends] == [(eid, 1)] * 2
    control = _handle(ids.new_id('execution'))
    node.ended(control, 3, 1)                         # nothing written before: it is written
    assert base.read_json(paths.ExecPaths(control.execution_id).ended)['exit_code'] == 3


def test_the_process_contract_files_are_read_as_what_they_are(seams):
    """`local.py:582-583` — `files()`'s `(read_json(marker), read_json(pid.json),
    os.path.exists(ended))`.

    This is what reconciliation decides on (`manager.py:960-968`): it asks whether
    `pid` is None to decide whether a process was ever started, and whether `ended`
    is true to decide whether it died. Reads a missing `pid.json` as `{}` (or a
    missing `ended` as anything but a bool) and Core adopts a process that never
    existed, or refuses an INTENT it should retire. The row asserts the triple for
    an execution with no files, with a started one, and with an ended one."""
    node = LocalNode()
    eid = ids.new_id('execution')
    assert node.files(eid) == (None, None, False)
    contract = paths.ExecPaths(eid)
    os.makedirs(contract.dir)
    for path, body in ((contract.spawning, {'process_seq': 1}),
                       (contract.pid, {'pid': PID, 'create_time': CREATED})):
        with open(path, 'w', encoding='utf-8') as handle:
            json.dump(body, handle)
    assert node.files(eid) == ({'process_seq': 1}, {'pid': PID, 'create_time': CREATED},
                               False)
    node.ended(_handle(eid), 0, 1)
    assert node.files(eid)[2] is True


def test_a_registry_line_core_never_wrote_is_skipped_and_says_nothing(seams):
    """`local.py:603-608` — `registry()`'s `except ValueError: continue` and its
    `if isinstance(row, dict)`.

    The registry is read to decide what may still be running, and it is a file the
    boot rewrites; a line that is not one of Core's objects — valid JSON of another
    shape included — must not answer for a process. Drop the `isinstance` guard and
    `[x for x in lines if x.get('op') ...]` dies on an array line, which is worse
    than useless at boot; drop the `except` and a torn line stops every reconciliation
    after it. The row plants all of them and asserts the one real line still reads."""
    node = LocalNode()
    eid = ids.new_id('execution')
    node._registry({'op': 'spawn', 'execution_id': eid, 'process_seq': 1, 'pid': PID,
                    'create_time': CREATED, 'argv0': 'fake'})
    with open(paths.processes_registry(), 'a', encoding='utf-8') as handle:
        for line in ('[1, 2]\n', '"not a line Core wrote"\n', '3\n', 'null\n', '\n',
                     '{torn\n'):
            handle.write(line)
    assert [line['op'] for line in node.registry()] == ['spawn']
    assert [line['execution_id'] for line in node.unended()] == [eid]
    node.compact_registry()                           # the same reading, the same skip
    assert [line['execution_id'] for line in LocalNode.registry()] == [eid]


# ── 5. the spawn, and the record it leaves behind ────────────────────────────

class Spawner:
    """A harness's two ways to start a process, recorded: a first process, and a
    resume of one that already ran. Each can be scripted to fail, and by which of
    the two ways a spawn fails is not a detail — it decides what Core records."""

    id = 'fake'

    def __init__(self, fault=None):
        self.fault, self.started, self.resumed = fault, [], []

    def _begin(self, name, spec, *extra):
        (self.started if name == 'start' else self.resumed).append((spec,) + extra)
        if isinstance(self.fault, Exception):
            raise self.fault
        return _handle(spec.execution_id)

    def start(self, spec):
        return self._begin('start', spec)

    def resume(self, spec, state):
        return self._begin('resume', spec, state)


def _spec(execution_id=None, process_seq=1):
    return base.ExecutionSpec(execution_id=execution_id or ids.new_id('execution'),
                              prompt='the prompt', workdir='W', process_seq=process_seq)


@pytest.mark.parametrize('resume_state', [None, {'session': 'the-first-process'}],
                         ids=['first-process', 'a-state-to-continue'])
def test_a_spawn_starts_one_process_and_records_the_identity_it_was_given(seams, monkeypatch,
                                                                          resume_state):
    """`local.py:486-487` — `adapter.start(spec) if resume_state is None else
    adapter.resume(spec, resume_state)`, and the registry line built from the handle.

    Swap the two arms and a resumed execution starts a second process beside the one
    it was meant to continue (or a first spawn is handed to `resume`, which has no
    process to continue); drop the registry line and an execution that outlives Core
    is invisible to the boot reconciliation that kills it. The row asserts which arm
    ran, that the other was not touched, that the opaque state was carried to it
    unchanged, and what the registry was told."""
    node = LocalNode()
    seams([])
    adapter = Spawner()
    monkeypatch.setattr(local, 'time', SimpleNamespace(time=lambda: 1771.0))
    spec = _spec()
    handle = node.spawn(adapter, spec, isolated=False, resume_state=resume_state)
    assert (handle.execution_id, handle.pid, handle.create_time) == (spec.execution_id,
                                                                     PID, CREATED)
    assert adapter.started == ([] if resume_state is not None else [(spec,)])
    assert adapter.resumed == ([(spec, resume_state)] if resume_state is not None else [])
    assert LocalNode.registry() == [
        {'op': 'spawn', 'execution_id': spec.execution_id, 'process_seq': 1, 'pid': PID,
         'create_time': CREATED, 'argv0': 'fake', 'started_at': 1771.0}]


def test_a_spawn_clears_the_control_flags_before_the_adapter_is_asked(seams, monkeypatch):
    """`local.py:482` — `self.clear_flags(spec.execution_id)` before anything else.

    The hook halts a process on a flag file left in its own control directory (P11).
    Move the clear after the start — or drop it — and a `STOP` left by the execution's
    previous process halts the new one the moment it is inspected, which is a process
    nobody asked to stop, stopped. The row writes the three flags as a previous
    process left them and asserts they are gone before the harness was reached."""
    node = LocalNode()
    seams([])
    monkeypatch.setattr(local, 'time', SimpleNamespace(time=lambda: 1771.0))
    spec = _spec()
    ctl = paths.ExecPaths(spec.execution_id).ctl
    os.makedirs(ctl)
    for flag in FLAGS:
        LocalNode.set_flag(spec.execution_id, flag)
    seen = []

    class Watching(Spawner):
        def start(self, spec):
            seen.append(sorted(os.listdir(ctl)))
            return Spawner.start(self, spec)

    adapter = Watching()
    node.spawn(adapter, spec, isolated=False)
    assert seen == [[]]                               # cleared, and cleared first
    assert os.listdir(ctl) == []


@pytest.mark.parametrize('fault,recorded', [
    pytest.param(base.SpawnFailed('the boundary would not open'), True, id='spawn-failed'),
    # Core's own write failed: charged as a workspace, never as an isolation failure
    pytest.param(base.SpawnWriteFailed('the prompt could not be written'), False,
                 id='write-failed'),
])
def test_an_isolation_failure_is_recorded_and_a_write_failure_is_not(seams, fault, recorded):
    """`local.py:488-496` — `except base.SpawnWriteFailed: raise` with no
    `self.isolation.note_failure(spec, err)`, which the `SpawnFailed` arm does call.

    Merge the two arms and a Core that restarts into a failed spawn reads a workspace
    it cannot write as an execution its isolation authority failed: §3.7 freezes that
    record, and an execution can never be dispatched isolated again. The row fails the
    spawn each way and asserts which record the authority was asked to make."""
    class Authority:
        def __init__(self):
            self.noted = []

        def note_failure(self, spec, err):
            self.noted.append((spec, type(err).__name__))

    node = LocalNode()
    seams([])
    isolation = Authority()
    node.isolation = isolation
    adapter = Spawner(fault=fault)
    spec = _spec()
    with pytest.raises(type(fault)):
        node.spawn(adapter, spec, isolated=False)
    assert isolation.noted == ([(spec, type(fault).__name__)] if recorded else [])
    assert LocalNode.registry() == []                 # nothing ran, so nothing is recorded


def test_a_flag_outside_the_three_the_hook_reads_is_never_written(seams):
    """`local.py:630` — `assert flag in FLAGS` in `set_flag`, and `clear_flags`
    removing exactly `FLAGS`.

    The hook reads three names from the execution's own control directory; a fourth
    written there is a control that silently does nothing, and an execution halted
    by a flag nobody reads is a process that ran on while Core believed it stopped.
    The row asserts the three are written and cleared, that a near-miss name raises
    and leaves no directory behind, and that clearing the flags never removes a file
    of the hook's own that lives beside them."""
    node = LocalNode()
    eid = ids.new_id('execution')
    ctl = paths.ExecPaths(eid).ctl
    os.makedirs(ctl)
    with open(os.path.join(ctl, 'handled.json'), 'w', encoding='utf-8') as handle:
        handle.write('{}')                            # the hook's own, not Core's to clear
    for flag in FLAGS:
        LocalNode.set_flag(eid, flag)
    assert sorted(os.listdir(ctl)) == sorted(list(FLAGS) + ['handled.json'])
    LocalNode.clear_flags(eid)
    assert os.listdir(ctl) == ['handled.json']
    stranger = ids.new_id('execution')
    with pytest.raises(AssertionError):
        LocalNode.set_flag(stranger, 'pause')          # the hook reads 'PAUSE', exactly
    assert not os.path.exists(paths.ExecPaths(stranger).ctl)

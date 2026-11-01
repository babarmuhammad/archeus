"""T-245: the MXC wire (ledger, suspended transport, Core Job, single resume).

Everything here is a fake. Nothing launches a process or owns a Job: the Win32 api,
Core's boundary, the broker and the outcome/resource readers are fixtures, the ledger
is a real journal under tmp_path, and the native gate is opened only for the wiring
under test — `NATIVE_RUN_ENABLED` and `WindowsBoundary.available()` stay closed in the
shipped code, and no Windows-only test of the repo runs in this container.
"""

import hashlib
import json
import ntpath
import os
from types import SimpleNamespace

import pytest

from archeus.node import local, mxc, mxc_ledger as ledger_mod, mxc_native as native, staging

EXE = 'C:\\sdk\\bin\\x64\\wxc-exec.exe'
POLICY_PATH = 'C:\\protected\\policy.json'
PID, CREATION_TIME = 4129, 133100000000000000
#: the seven steps, in the order the ledger builder reported them missing
STEPS = ['intent', 'create', 'time', 'assign', 'query', 'ownership', 'resume']


class FakeApi:
    """The Win32 surface the transport uses: tracked allocations, one named call that
    fails, and handles that are only ever integers."""

    def __init__(self, failure=None):
        self.handles, self.failure, self.events = {}, failure, []
        self.reads = {1: [b''], 2: [b'']}
        self.exit, self.stalled = 0, False
        self.allowlist = ()

    def point(self, name):
        self.events.append(name)
        if self.failure == name:
            raise OSError(name)

    def allocate(self, name):
        self.point(name)
        handle = len(self.events) + 100
        self.handles[handle] = name
        return handle

    def protected_policy(self, data):
        return POLICY_PATH, self.allocate('policy')

    def remove_policy(self, path, handle):
        self.close_handle(handle)

    def pipe(self, *, parent_reads):
        number = sum(name.startswith('parent') for name in self.handles.values())
        parent = self.allocate('parent%d' % number)
        try:
            return parent, self.allocate('child%d' % number)
        except BaseException:
            self.close_handle(parent)
            raise

    def attribute_list(self, handles):
        self.allowlist = handles
        return self.allocate('attributes')

    def delete_attribute_list(self, handle):
        self.close_handle(handle)

    def create_process_w(self, **kwargs):
        self.kwargs = kwargs
        self.point('create')
        process = self.allocate('process')
        try:
            return process, self.allocate('thread'), PID
        except BaseException:
            self.close_handle(process)
            raise

    def creation_time(self, process):
        self.point('time')
        return CREATION_TIME

    def in_job(self, job, process):
        self.point('query')
        return self.failure != 'membership'

    def resume_thread(self, thread):
        self.point('resume')
        return 1

    def terminate_process(self, process):
        self.events.append('kill')

    def close_handle(self, handle):
        del self.handles[handle]

    def poll(self, process):
        return self.exit

    def read(self, handle, size):
        index = int(self.handles[handle][-1])
        queue = self.reads[index]
        return queue.pop(0) if queue else None

    def write(self, handle, data):
        return 0 if self.stalled else len(data)


class FakeBoundary:
    """Core's Job: the one thing that ends the whole tree, and the only source of a
    quiescence count. It never kills a process by pid and never invents a count. Like
    the real handle it is open until its one close: a count read or a second close on a
    closed handle fails."""

    def __init__(self, api, counts=()):
        self.api, self.counts = api, list(counts)
        self.closed, self.assigned, self.open = [], [], set()

    def create_job(self, execution_id):
        job = 'core-job-%s' % execution_id
        self.open.add(job)
        return job

    def assign_job(self, job, process_handle):
        self.api.point('assign')
        self.assigned.append(process_handle)

    def close_job(self, job):
        if job not in self.open:
            raise OSError('Job handle %r is not open' % (job,))
        self.open.remove(job)
        self.closed.append(job)
        self.api.events.append('close_job')

    def job_active_processes(self, job):
        self.api.events.append('quiesce')
        if job not in self.open:
            raise OSError('Job handle %r is not open' % (job,))
        return self.counts.pop(0) if self.counts else 0


class FakeBroker:
    """The existing broker admission hook (node/broker.py: revoke(execution_id))."""

    def __init__(self, api=None):
        self.api, self.revoked = api, []

    def revoke(self, execution_id):
        self.revoked.append(execution_id)
        if self.api is not None:
            self.api.events.append('revoke')


class TracedLedger:
    """The real journal, with every write traced into the api's own event list so the
    seven steps are one list. It is the real Ledger: the writes really are appended
    and fsynced, and every read below goes through the file."""

    def __init__(self, root, api=None):
        self.journal, self.api = ledger_mod.Ledger(root), api

    def append(self, execution_id, op, **facts):
        record = self.journal.append(execution_id, op, **facts)
        if self.api is not None:
            self.api.events.append(op)
        return record

    def __getattr__(self, name):
        return getattr(self.journal, name)


def journal_ops(journal, execution_id='e1'):
    """What the journal holds, read back from disk."""
    rows, invalid = ledger_mod.read_records(journal.journals().get(execution_id, b''),
                                            execution_id)
    assert not invalid
    return [row['op'] for row in rows]


def journal_records(journal, execution_id='e1'):
    rows, invalid = ledger_mod.read_records(journal.journals().get(execution_id, b''),
                                            execution_id)
    assert not invalid
    return rows


def fail_op(journal, op):
    """Make exactly one ledger write fail, the way a disk does: by raising."""
    real = journal.journal.append

    def append(execution_id, name, **facts):
        if name == op:
            with open(journal.journal._path(execution_id), 'ab'):    # as append() does
                pass
            raise OSError('%s write failed' % op)
        return real(execution_id, name, **facts)

    journal.journal.append = append


@pytest.fixture
def args(tmp_path):
    sdk = tmp_path / 'sdk'
    (sdk / 'bin' / 'x64').mkdir(parents=True)
    (sdk / 'package.json').write_text(json.dumps({'name': staging.MXC_PACKAGE,
                                                  'version': staging.MXC_VERSION}),
                                      encoding='utf-8')
    (sdk / staging.MXC_EXE).write_bytes(b'fake launcher')
    pins = {rel: hashlib.sha256((sdk / rel).read_bytes()).hexdigest()
            for rel in ('package.json', staging.MXC_EXE)}
    work, runtime = tmp_path / 'work', tmp_path / 'runtime'
    work.mkdir()
    runtime.mkdir()
    return dict(sdk_root=sdk, pins=pins, workspace=str(work), readonly=(str(runtime),),
                cwd=str(work), command_line='fixture command', timeout_ms=1000,
                env={'SYSTEMROOT': 'C:\\Windows',
                     'LOCALAPPDATA': 'C:\\Users\\fixture\\AppData\\Local'})


@pytest.fixture
def native_parts(monkeypatch):
    """Open the native gate for the fakes only, and let the fixture speak the Windows
    paths the transport validates: this container is Linux, the launcher is not."""
    monkeypatch.setattr(mxc, 'NATIVE_RUN_ENABLED', True)

    def absolute(path):
        path = str(path)
        if not (os.path.isabs(path) or ntpath.isabs(path)):
            raise mxc.MxcUnavailable('absolute path required')
        return path

    monkeypatch.setattr(mxc, '_path', absolute)
    real = staging.verify_mxc
    monkeypatch.setattr(staging, 'verify_mxc',
                        lambda root, *, pins: (real(root, pins=pins), EXE)[1])


@pytest.fixture
def wire(tmp_path, args, native_parts):
    def build(*, failure=None, exit_code=0, reads=None, stalled=False, counts=(),
              reader=None, disposal=None, broker=True, outcome=None, execution_id='e1',
              schema_validator=None, quiescence_wait=0.0):
        api = FakeApi(failure)
        boundary = FakeBoundary(api, counts)
        journal = TracedLedger(tmp_path / 'ledger', api)
        api.exit, api.stalled = exit_code, stalled
        if reads is not None:
            api.reads = reads
        tick = iter(range(0, 1000))                 # the clock only ever moves forward
        admission = FakeBroker(api) if broker else None
        launch = local.MxcLaunch(api=api, boundary=boundary, ledger=journal,
                                 schema_validator=schema_validator or (lambda raw: True),
                                 execution_id=execution_id, broker=admission,
                                 resource_reader=reader, disposal=disposal,
                                 outcome=outcome or (lambda process: 0),
                                 quiescence_wait=quiescence_wait,
                                 clock=lambda: float(next(tick)),
                                 pause=lambda seconds: None, **args)
        return SimpleNamespace(api=api, boundary=boundary, journal=journal,
                               broker=admission, launch=launch,
                               job=boundary.create_job(execution_id))
    return build


# ── the parts ──

def test_the_transport_is_built_from_the_injected_parts(wire):
    h = wire()
    assert isinstance(h.launch.backend, native.Backend)
    assert isinstance(h.launch.backend.transport, native.Transport)
    assert h.launch.backend.transport.api is h.api
    assert h.launch.backend.transport.boundary is h.boundary
    assert h.launch.backend.schema_validator is not None


@pytest.mark.parametrize('missing', ['api', 'boundary', 'ledger', 'schema_validator'])
def test_a_journalled_launch_refuses_a_missing_part(tmp_path, args, missing):
    parts = dict(api=FakeApi(), boundary=FakeBoundary(FakeApi()),
                 ledger=TracedLedger(tmp_path / 'ledger'), schema_validator=lambda raw: True,
                 execution_id='e1')
    parts[missing] = None
    with pytest.raises(staging.StageError, match='schema validator'):
        local.MxcLaunch(outcome=lambda process: 0, **parts, **args)


def test_the_native_parts_and_a_backend_are_not_mixed(wire, args, tmp_path):
    with pytest.raises(staging.StageError, match='not both'):
        local.MxcLaunch(backend=object(), api=FakeApi(), boundary=FakeBoundary(FakeApi()),
                        ledger=TracedLedger(tmp_path / 'ledger'),
                        schema_validator=lambda raw: True, execution_id='e1',
                        outcome=lambda process: 0, **args)


@pytest.mark.parametrize('execution_id', [None, '', 'e/1', 'e 1', 7, 'é'])
def test_an_id_the_ledger_cannot_name_refuses_before_anything_else(tmp_path, args,
                                                                    execution_id):
    with pytest.raises(staging.StageError, match='execution id'):
        local.MxcLaunch(api=FakeApi(), boundary=FakeBoundary(FakeApi()),
                        ledger=TracedLedger(tmp_path / 'ledger'),
                        schema_validator=lambda raw: True, execution_id=execution_id,
                        outcome=lambda process: 0, **args)


def test_the_schema_validator_decides_before_any_create(wire):
    h = wire(schema_validator=lambda raw: False)
    with pytest.raises(mxc.MxcUnavailable, match='schema validation'):
        h.launch.start(job=h.job)
    assert 'create' not in h.api.events
    assert h.api.handles == {}
    assert journal_ops(h.journal) == ['intent', 'quarantine']


# ── the seven steps, and the ownership-before-advance seam ──

def test_the_seven_steps_happen_in_that_order(wire):
    h = wire()
    h.launch.start(job=h.job)
    assert [event for event in h.api.events if event in STEPS] == STEPS
    assert h.api.events.count('resume') == 1
    assert h.api.events.count('create') == 1
    assert h.api.kwargs['flags'] & native.CREATE_SUSPENDED
    assert h.boundary.assigned == [h.launch.process.process_handle]
    assert journal_ops(h.journal) == ['intent', 'ownership']
    h.launch.process.terminate()


def test_ownership_is_durable_before_the_resume(wire):
    """The whole point of the seam: at the instant the thread is resumed, the ownership
    record is already in the file on disk, and the requested digest matches the intent."""
    h = wire()
    seen = []
    real = h.api.resume_thread

    def resume_thread(thread):
        seen.append(journal_ops(h.journal))
        return real(thread)

    h.api.resume_thread = resume_thread
    h.launch.start(job=h.job)
    assert seen == [['intent', 'ownership']]
    intent, owner = journal_records(h.journal)
    assert (owner['pid'], owner['create_time']) == (PID, CREATION_TIME)
    assert owner['requested_policy_digest'] == intent['requested_policy_digest']
    assert intent['planned']                                    # what Core requested…
    assert owner['applied'] == [] and owner['observed'] == {}    # …is never the answer
    assert owner['owned'] == []                                  # nothing was read back
    assert h.api.events.count('kill') == 0
    h.launch.process.terminate()


@pytest.mark.parametrize('step', STEPS[1:])
def test_a_fault_at_any_step_never_leaves_a_running_child(wire, step):
    """A fault anywhere in the sequence terminates the suspended child, never resumes
    it, and closes every handle. `intent` and `ownership` fail in the ledger, the rest
    in the Win32 seam."""
    h = wire()
    if step in ('intent', 'ownership'):
        fail_op(h.journal, step)
    else:
        h.api.failure = step
    with pytest.raises((OSError, mxc.MxcUnavailable)):
        h.launch.start(job=h.job)
    assert h.api.events.count('resume') == (1 if step == 'resume' else 0)
    assert h.api.events.count('kill') == (0 if step in ('intent', 'create') else 1)
    assert h.api.handles == {}
    assert h.boundary.closed == [] and h.job in h.boundary.open    # the Job stays the caller's
    ops = journal_ops(h.journal)
    assert ops[-1] == 'quarantine'                        # the fault is on the record
    assert 'completion' not in ops and 'disposal' not in ops
    assert h.launch.process is None


def test_the_create_intent_is_durable_before_the_create(wire):
    """Slice 5's first step, as the ledger sees it: the create is attempted only once
    the intent is in the file, so a lost create reply is a restart reconciliation."""
    h = wire()
    seen = []
    real = h.api.create_process_w

    def create_process_w(**kwargs):
        seen.append(journal_ops(h.journal))
        return real(**kwargs)

    h.api.create_process_w = create_process_w
    h.launch.start(job=h.job)
    assert seen == [['intent']]
    intent = journal_records(h.journal)[0]
    assert intent['planned'] and not intent['applied'] and intent['observed'] == {}
    h.launch.process.terminate()


def test_a_launch_is_consumed_once(wire):
    h = wire()
    h.launch.start(job=h.job)
    with pytest.raises(staging.StageError, match='already consumed'):
        h.launch.start(job=h.job)
    assert h.api.events.count('create') == 1
    assert h.api.events.count('resume') == 1
    h.launch.process.terminate()


def test_a_second_launch_of_the_same_execution_id_is_refused(wire):
    """The half-run execution is reconciled at restart, not re-adopted by starting it
    again: the refusal happens before a policy is staged or a process is created."""
    first = wire()
    first.launch.start(job=first.job)
    second = wire(execution_id='e1')
    with pytest.raises(staging.StageError, match='ledger journal'):
        second.launch.start(job=second.job)
    assert second.api.events == []
    assert journal_ops(second.journal) == ['intent', 'ownership']
    first.launch.process.terminate()


@pytest.mark.parametrize('step', ['intent', 'ownership'])
def test_a_launch_that_failed_to_journal_is_not_started_again(wire, step):
    first = wire()
    fail_op(first.journal, step)
    with pytest.raises(OSError, match='write failed'):
        first.launch.start(job=first.job)
    second = wire(execution_id='e1')
    with pytest.raises(staging.StageError, match='ledger journal'):
        second.launch.start(job=second.job)
    assert second.api.events == []


# ── the launcher exit is not the workload outcome ──

def test_launcher_zero_is_never_the_workload_outcome(wire):
    h = wire(exit_code=0, outcome=lambda process: None)
    h.launch.start(job=h.job)
    with pytest.raises(staging.StageError, match='outcome is unavailable'):
        h.launch.wait()
    assert h.launch.launcher_exit == 0            # the launcher's own report, kept apart
    assert h.launch.completed is None
    assert h.boundary.closed == []
    ops = journal_ops(h.journal)
    assert 'completion' not in ops and ops[-1] == 'quarantine'
    assert h.launch.end_state['state'] == ledger_mod.DEAD_UNVERIFIED


def test_a_forged_outcome_reader_is_still_a_reader_that_is_called(wire):
    """The wire cannot tell a Core-owned reader from an execution-written file — that
    binding is Core's (the docstring's UNVERIFIED) — so the one thing it can do is call
    exactly what it was given, once, with the child, and refuse its answer when it is
    not an exit code."""
    calls = []
    h = wire(outcome=lambda process: (calls.append(process), '0')[1])
    h.launch.start(job=h.job)
    with pytest.raises(staging.StageError, match='outcome is unavailable'):
        h.launch.wait()
    assert calls == [h.launch.process]
    assert h.launch.end_state['state'] == ledger_mod.DEAD_UNVERIFIED


def test_a_verified_readback_still_needs_an_observed_outcome(wire):
    """The two readings are independent: an execution whose owned resources read back
    absent and whose Job emptied is still not completed while nobody has said what the
    workload returned — the disposal record would be a lie without the outcome."""
    h = wire(outcome=lambda process: None, reader=lambda execution_id, owner: True)
    h.launch.start(job=h.job)
    with pytest.raises(staging.StageError, match='outcome is unavailable'):
        h.launch.wait()
    assert h.launch.completed is None and h.launch.launcher_exit == 0
    ops = journal_ops(h.journal)
    assert ops[-1] == 'quarantine' and 'completion' not in ops and 'disposal' not in ops
    assert h.launch.end_state['state'] == ledger_mod.DEAD_UNVERIFIED


def test_a_verified_end_records_the_workload_outcome(wire):
    """The positive control: quiesced, owned resources read back absent, outcome
    observed — and only then does a completion go in, with the workload's code."""
    h = wire(outcome=lambda process: 7, reader=lambda execution_id, owner: True)
    h.launch.start(job=h.job)
    assert h.launch.wait() == 7
    assert h.launch.launcher_exit == 0 and h.launch.completed == 7
    assert journal_ops(h.journal) == ['intent', 'ownership', 'disposal', 'completion']
    rows = journal_records(h.journal)
    assert rows[-1]['outcome'] == 7 and rows[-2]['verified_absent'] is True
    assert h.launch.end_state['state'] == ledger_mod.DEAD_CLEAN
    assert h.boundary.closed == [] and h.broker.revoked == ['e1']


@pytest.mark.parametrize('answer', [None, False, 'absent', 1])
def test_readback_that_is_not_verification_quarantines(wire, answer):
    seen = []
    h = wire(outcome=lambda process: 3,
             reader=lambda execution_id, owner: (seen.append((execution_id, owner)),
                                                 answer)[1])
    h.launch.start(job=h.job)
    assert h.launch.wait() == 3                    # the workload's outcome, and nothing more
    assert h.launch.completed == 3
    assert h.launch.end_state['state'] == ledger_mod.DEAD_UNVERIFIED
    ops = journal_ops(h.journal)
    assert ops[-1] == 'quarantine' and 'completion' not in ops and 'disposal' not in ops
    assert [call[0] for call in seen] == ['e1']          # the reader is told whose it checks
    assert [call[1]['op'] for call in seen] == ['ownership']   # and sees the returned owner


def test_no_reader_at_all_is_never_a_clean_end(wire):
    h = wire(outcome=lambda process: 0)
    h.launch.start(job=h.job)
    assert h.launch.wait() == 0
    assert h.launch.end_state['quiescence'] is None        # the Job did empty…
    assert h.launch.end_state['state'] == ledger_mod.DEAD_UNVERIFIED   # …and that is not enough
    assert journal_ops(h.journal)[-1] == 'quarantine'


def test_an_injected_disposal_step_runs_before_the_completion(wire):
    calls = []
    h = wire(outcome=lambda process: 0, reader=lambda execution_id, owner: True,
             disposal=lambda owner: calls.append(owner))
    h.launch.start(job=h.job)
    assert h.launch.wait() == 0
    assert [record['op'] for record in calls] == ['ownership']   # the returned ownership
    assert journal_ops(h.journal) == ['intent', 'ownership', 'disposal', 'completion']


def test_a_disposal_that_fails_quarantines_the_end(wire):
    def disposal(owner):
        raise OSError('owned resource still there')

    h = wire(outcome=lambda process: 0, reader=lambda execution_id, owner: True,
             disposal=disposal)
    h.launch.start(job=h.job)
    assert h.launch.wait() == 0
    assert h.launch.end_state['state'] == ledger_mod.DEAD_UNVERIFIED
    ops = journal_ops(h.journal)
    assert ops[-1] == 'quarantine' and 'completion' not in ops and 'disposal' not in ops


@pytest.mark.parametrize('counts,wait,polls,why', [
    ([0], 0.0, 1, None),                       # one reading is enough when it is empty
    ([3], 0.0, 1, 'answered 3'),               # and the bound is not stretched forever
    ([1, 0], 10.0, 2, None),                   # the tree can empty inside the bound
])
def test_the_quiescence_wait_is_bounded_and_honest(wire, counts, wait, polls, why):
    """An empty Job is a reading, not a proof: the wait is bounded by the injected
    clock, and a Job that never empties leaves the end quarantined even with an
    observed outcome and a verified read-back."""
    h = wire(outcome=lambda process: 0, reader=lambda execution_id, owner: True,
             counts=counts, quiescence_wait=wait)
    h.launch.start(job=h.job)
    assert h.launch.wait() == 0
    assert h.api.events.count('quiesce') == polls
    if why is None:
        assert h.launch.end_state['quiescence'] is None
    else:
        assert why in h.launch.end_state['quiescence']
    ops = journal_ops(h.journal)
    if why is None:
        assert h.launch.end_state['state'] == ledger_mod.DEAD_CLEAN
        assert ops == ['intent', 'ownership', 'disposal', 'completion']
    else:
        assert h.launch.end_state['state'] == ledger_mod.DEAD_UNVERIFIED
        assert ops[-1] == 'quarantine' and 'completion' not in ops


def test_a_boundary_that_cannot_answer_leaves_the_end_unverified(wire):
    """Not answering is not answering cleanly."""
    def job_active_processes(job):
        raise OSError('count unavailable')

    h = wire(outcome=lambda process: 0, reader=lambda execution_id, owner: True)
    h.boundary.job_active_processes = job_active_processes
    h.launch.start(job=h.job)
    assert h.launch.wait() == 0
    assert h.launch.end_state['state'] == ledger_mod.DEAD_UNVERIFIED
    assert 'count failed' in h.launch.end_state['quiescence']
    assert journal_ops(h.journal)[-1] == 'quarantine'


# ── cancel and timeout: the same ending, in the audit's order ──

def test_a_cancel_ending_a_drain_quarantines_and_leaves_the_job_to_its_owner(wire):
    h = wire(exit_code=None, reads={1: [], 2: []}, outcome=lambda process: 0)
    h.launch.start(job=h.job)
    with pytest.raises(mxc.MxcUnavailable, match='cancelled'):
        h.launch.wait(cancelled=lambda: True)
    assert h.broker.revoked == ['e1'] and h.boundary.closed == []
    assert h.api.handles == {}
    ops = journal_ops(h.journal)
    assert ops[-1] == 'quarantine' and 'completion' not in ops and 'disposal' not in ops
    assert h.launch.end_state['state'] == ledger_mod.DEAD_UNVERIFIED


def test_ending_follows_the_audited_order(wire):
    h = wire(outcome=lambda process: None)
    h.launch.start(job=h.job)
    with pytest.raises(staging.StageError, match='outcome is unavailable'):
        h.launch.wait()
    events = [event for event in h.api.events
              if event in ('revoke', 'close_job', 'quiesce')]
    assert events == ['revoke', 'quiesce']


def test_the_count_is_read_through_an_open_handle_and_a_clean_end_is_reachable(wire):
    h = wire(counts=[2, 1, 0], quiescence_wait=100.0, outcome=lambda process: 0,
             reader=lambda execution_id, owner: True)
    h.launch.start(job=h.job)
    assert h.launch.wait() == 0
    assert h.launch.end_state == {'state': ledger_mod.DEAD_CLEAN, 'reason': 'launcher exited',
                                  'quiescence': None}
    assert h.api.events.count('quiesce') == 3 and 'close_job' not in h.api.events
    assert journal_ops(h.journal) == ['intent', 'ownership', 'disposal', 'completion']


def test_the_owner_closes_the_job_exactly_once_after_the_end(wire):
    h = wire(outcome=lambda process: 0, reader=lambda execution_id, owner: True)
    h.launch.start(job=h.job)
    h.launch.wait()
    assert h.boundary.closed == [] and h.job in h.boundary.open
    h.boundary.close_job(h.job)
    assert h.boundary.closed == [h.job] and not h.boundary.open
    with pytest.raises(OSError):
        h.boundary.close_job(h.job)


def test_a_job_already_closed_is_never_read_as_empty(wire):
    h = wire(outcome=lambda process: 0, reader=lambda execution_id, owner: True)
    h.launch.start(job=h.job)
    h.boundary.close_job(h.job)
    h.launch.wait()
    assert h.launch.end_state['state'] == ledger_mod.DEAD_UNVERIFIED
    assert 'count failed' in h.launch.end_state['quiescence']
    assert h.boundary.closed == [h.job]


def test_cancel_reports_the_first_ending_and_ends_nothing_twice(wire):
    h = wire(outcome=lambda process: 0, reader=lambda execution_id, owner: True)
    h.launch.start(job=h.job)
    assert h.launch.cancel(reason='host asked', outcome=1) == h.launch.end_state
    first = h.launch.end_state
    assert h.launch.cancel(reason='again') is first
    assert h.api.events.count('close_job') == 0 and h.api.events.count('revoke') == 1
    assert h.api.events.count('quiesce') == 1
    assert journal_ops(h.journal) == ['intent', 'ownership', 'disposal', 'completion']


def test_the_journal_alone_says_how_the_end_ended(wire):
    """Restart reads the journal, not this object, and the two endings have to be told
    apart from the records alone: a completed execution owes nothing, a quarantined one
    is reported unverified forever."""
    readers = (lambda pid: None, lambda execution_id, owner: True)
    clean = wire(outcome=lambda process: 0, reader=lambda execution_id, owner: True)
    clean.launch.start(job=clean.job)
    assert clean.launch.wait() == 0
    assert clean.journal.reconcile(*readers) == {}
    dirty = wire(execution_id='e2', outcome=lambda process: 0)
    dirty.launch.start(job=dirty.job)
    assert dirty.launch.wait() == 0
    assert dirty.journal.reconcile(*readers) == {'e2': ledger_mod.DEAD_UNVERIFIED}


# ── the gates the wire keeps ──

def test_the_hardlink_gate_still_runs_at_launch(args, wire):
    from pathlib import Path
    h = wire()
    workspace = Path(args['workspace'])
    (workspace / 'innocent.txt').write_text('x', encoding='utf-8')
    try:
        os.link(workspace / 'innocent.txt', workspace / 'linked.txt')
    except OSError:
        pytest.skip('no hardlinks here')
    with pytest.raises(staging.StageError, match='links'):
        h.launch.start(job=h.job)
    assert h.api.events == []            # nothing staged, nothing created, nothing resumed
    assert journal_ops(h.journal) == []  # the intent is not written for an unpublished grant


def test_a_boundary_with_no_count_leaves_the_end_unverified(wire):
    class Boundary(FakeBoundary):
        job_active_processes = None

    h = wire(outcome=lambda process: 0, reader=lambda execution_id, owner: True)
    h.launch.boundary = Boundary(h.api)
    h.launch.start(job=h.job)
    assert h.launch.wait() == 0
    assert h.launch.end_state['state'] == ledger_mod.DEAD_UNVERIFIED
    assert 'no Job process count' in h.launch.end_state['quiescence']


@pytest.mark.parametrize('broken', ['revoke', 'close'])
def test_a_failing_ending_step_never_skips_the_next_and_is_never_clean(wire, broken):
    h = wire(outcome=lambda process: 0, reader=lambda execution_id, owner: True)
    h.launch.start(job=h.job)
    target = h.broker if broken == 'revoke' else h.launch.process
    real = getattr(target, broken)

    def fail(*args):
        if broken == 'close':
            real(*args)                       # the handles still go, the step still reports
        raise OSError('step failed')

    setattr(target, broken, fail)
    state = h.launch.cancel(reason='host asked', outcome=0)
    assert state['state'] == ledger_mod.DEAD_UNVERIFIED and 'OSError' in state['quiescence']
    assert h.api.handles == {}
    assert h.boundary.closed == []
    ops = journal_ops(h.journal)
    assert ops[-1] == 'quarantine' and 'completion' not in ops and 'disposal' not in ops

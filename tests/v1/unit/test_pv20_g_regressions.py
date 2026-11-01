# ruff: noqa: F811  (the imported wire fixtures are taken as arguments)
"""PV-20 slice G, step G1: regression tests that pin a security property of the
design rows already built behind fakes, not the shape of the code that builds them.

Each section names the property first. A hostile child cannot put more than its
bound into Core's memory (B1); two principals cannot be given one journal name (B2);
an end that Core asked for is never recorded clean while the tree still lives (B3);
an origin Core cannot positively attribute to the user is refused, whatever fails
(B9). Everything is a fake: no process, no socket, no DLL, no native call.
`tools/mutate_mxc_g.py` breaks each property by hand and requires one of these to fail.
None of this shows V1 is OS-confined (ADR-0053): the gates they guard stay closed."""

import itertools
import threading
from dataclasses import replace
from types import SimpleNamespace

import pytest

from archeus.api import origin, server
from archeus.core.domain import ids
from archeus.node import isolation as iso, mxc, mxc_ledger as ledger_mod, staging
from archeus.node.origin_native import native_readers
from archeus.node.origin_windows import WindowsOriginBackend

from .test_mxc_native_stream import FakeWin32, Sink, launch
from .test_mxc_wire import args, journal_ops, native_parts, wire  # noqa: F401
from .test_origin_native import CORE, JOB, PEER, T0, FakeApi, ctx

OK = dict(outcome=lambda process: 0, reader=lambda execution_id, owner: True)


# ── B1: a hostile child cannot exceed its output bound into Core's memory ──

class Endless:
    """A pipe a hostile child never lets run dry."""

    def __init__(self, chunk):
        self.chunk = chunk

    def __bool__(self):
        return True

    def pop(self, index):
        return self.chunk


class Child(FakeWin32):
    def __init__(self, reads, exit=None):
        super().__init__(reads, exit=exit)
        self.asked = []

    def read(self, handle, size):
        self.asked.append(size)
        return super().read(handle, size)


def held(sink, name=None):
    return sum(len(data) for stream, data in sink.got if name in (None, stream))


def test_a_child_flooding_one_stream_puts_no_more_than_its_bound_in_core_memory():
    api, child = launch(Child({1: Endless(b'x' * 600), 2: []}), output_limit=1000,
                        total_limit=10 ** 6)
    sink = Sink()
    child.attach(sink)
    with pytest.raises(mxc.MxcUnavailable, match='bound'):
        child.wait()
    assert held(sink, 'stdout') <= 1000


def test_two_streams_each_inside_their_own_bound_cannot_exceed_the_total():
    api, child = launch(Child({1: Endless(b'x' * 400), 2: Endless(b'y' * 400)}),
                        output_limit=10 ** 6, total_limit=1500)
    sink = Sink()
    child.attach(sink)
    with pytest.raises(mxc.MxcUnavailable, match='bound'):
        child.wait()
    assert held(sink) <= 1500


def test_the_in_memory_streams_are_bounded_too_when_no_sink_is_attached():
    api, child = launch(Child({1: Endless(b'x' * 600), 2: []}), output_limit=1000,
                        total_limit=10 ** 6)
    with pytest.raises(mxc.MxcUnavailable, match='bound'):
        child.wait()
    assert len(child.stdout.getvalue()) <= 1000


def test_core_never_asks_the_os_for_more_than_one_bounded_chunk_at_a_time():
    api, child = launch(Child({1: [b'ab', b''], 2: [b'']}, exit=0))
    child.attach(Sink())
    child.wait()
    assert api.asked and max(api.asked) <= 64 * 1024


def test_a_child_that_dribbles_forever_is_stopped_at_the_deadline_not_held_open():
    api, child = launch(Child({1: Endless(b'.'), 2: []}), timeout=100,
                        output_limit=10 ** 9, total_limit=10 ** 9)
    child.attach(Sink())
    with pytest.raises(TimeoutError):
        child.wait()
    assert 'kill' in api.events


def test_a_child_that_never_reads_its_input_cannot_make_core_buffer_without_end():
    calls = []

    def reader(size):
        calls.append(size)
        return b'x' * 1000

    api = Child({1: [], 2: []})
    api.write = lambda handle, data: 0                       # the child never takes a byte
    api, child = launch(api, timeout=100)
    child.attach(Sink(), stdin_reader=reader)
    with pytest.raises(TimeoutError):
        child.wait()
    assert len(calls) == 1


def test_output_that_arrives_after_the_launcher_exited_is_not_dropped():
    api, child = launch(Child({1: [None, None, b'late', b''], 2: [b'']}, exit=0))
    sink = Sink()
    child.attach(sink)
    assert child.wait() == 0
    assert held(sink, 'stdout') == 4


@pytest.mark.parametrize('how', ['bound', 'deadline', 'sink', 'cancel'])
def test_whatever_ends_the_drain_the_launcher_is_killed_and_no_handle_is_left(how):
    reads = {1: Endless(b'x' * 600 if how == 'bound' else b'.'), 2: []}
    api, child = launch(Child(reads), timeout=100, output_limit=1000, total_limit=10 ** 6)

    def hook(count):
        raise RuntimeError('sink refused')

    child.attach(Sink(hook if how == 'sink' else None))
    kw = {'cancelled': lambda: True} if how == 'cancel' else {}
    with pytest.raises(Exception):
        child.wait(**kw)
    assert 'kill' in api.events and api.handles == {}


@pytest.mark.xfail(strict=True, reason=(
    'defect, archeus/node/mxc_native.py:214 Process.terminate (the `if self.launcher_exit is None` '
    'guard) and :192 Process.poll: a launcher whose exit 0 was read before a later chunk broke the '
    'bound keeps launcher_exit 0, so poll() reports a clean exit for a drain that was cut off'))
def test_a_drain_that_dies_on_a_bound_never_reads_as_a_clean_launcher_exit_in_poll():
    api, child = launch(Child({1: [b'ab', b'cdefghijkl'], 2: []}, exit=0), output_limit=8)
    child.attach(Sink())
    with pytest.raises(mxc.MxcUnavailable, match='bound'):
        child.wait()
    assert child.poll() != 0


# ── B2: no two principals can be given one journal name ──

def _corpus():
    vid, other = ids.new_id('verification'), ids.new_id('verification')
    keys = [''.join(p) for n in (1, 2, 3) for p in itertools.product('a1_-./\n', repeat=n)]
    keys += ['e1', 'e11', 'e1-p1', 'e1_p1', 'verify_', 'verify_x', 'verify_%s_3' % vid,
             '../x', 'e\\1', 'e1\x00', 'é', '١', 'e1 ', ' e1', '']
    keys += ['verify/%s.%d' % (v, n) for v in (vid, other) for n in (0, 1, 3, 11, 12)] + [
        'verify/%s.01' % vid, 'verify/%s.3/x' % vid, 'verify/%s.3\n' % vid]
    return keys


def _names():
    for key in _corpus():
        for seq in (1, 2, 11, 12):
            try:
                yield key, seq, ledger_mod.journal_name(key, seq)
            except ValueError:
                pass


def test_no_two_keys_or_generations_ever_get_one_journal_name():
    seen = {}
    for key, seq, name in _names():
        assert seen.setdefault(name, (key, seq)) == (key, seq), (name, key, seq, seen[name])
    assert len(seen) > 40


@pytest.mark.parametrize('seq', [0, -1, None, True, 1.0, '1'])
def test_a_process_generation_that_could_read_as_another_is_refused(seq):
    with pytest.raises(ValueError):
        ledger_mod.journal_name('e1', seq)


def test_a_journal_name_is_one_path_component_whatever_the_key():
    for key, seq, name in _names():
        assert name.isascii() and all(c.isalnum() or c in '_-' for c in name), (key, name)


def test_an_execution_can_never_be_given_a_verifiers_journal_name():
    vid = ids.new_id('verification')
    verifier = ledger_mod.journal_name('verify/%s.3' % vid, 1)
    with pytest.raises(ValueError):
        ledger_mod.journal_name('verify_%s_3' % vid, 1)
    assert not any(name == verifier for key, seq, name in _names() if not key.startswith('verify/'))


def test_four_principals_sharing_one_ledger_each_keep_a_journal_of_their_own(wire):
    vid = ids.new_id('verification')
    runs = [('e1', 1), ('e1', 2), ('e11', 1), ('verify/%s.3' % vid, 1)]
    names = []
    for key, seq in runs:
        h = wire(execution_id=key, process_seq=seq, **OK)
        h.launch.start(job=h.job)
        assert h.launch.wait() == 0
        names.append(h.launch.journal)
    assert len(set(names)) == 4 and set(h.journal.journals()) == set(names)
    for name in names:
        assert journal_ops(h.journal, name) == ['intent', 'ownership', 'disposal', 'completion']


def test_a_second_launch_of_the_same_generation_cannot_write_into_a_finished_journal(wire):
    first = wire(**OK)
    first.launch.start(job=first.job)
    assert first.launch.wait() == 0
    before = first.journal.journals()['e1-p1']
    again = wire(**OK)
    with pytest.raises(staging.StageError, match='ledger journal'):
        again.launch.start(job=again.job)
    assert again.journal.journals()['e1-p1'] == before


# ── B3: an ended execution is never clean while its tree still lives ──

_UNSET = object()


def _tree(h, *, dies_on_terminate=True, answer=_UNSET):
    """A Job whose member count stays up until the boundary terminates it (or never)."""
    def count(job):
        if answer is not _UNSET:
            return answer
        return 0 if dies_on_terminate and h.boundary.terminated else 3
    h.boundary.job_active_processes = count


def _end(h):
    h.launch.start(job=h.job)
    return h.launch.cancel(reason='host asked', outcome=0)


def test_an_end_that_terminates_the_job_is_clean_only_because_the_tree_is_gone(wire):
    h = wire(**OK)
    _tree(h)
    assert _end(h)['state'] == ledger_mod.DEAD_CLEAN
    assert h.boundary.terminated == [h.job] and h.job in h.boundary.open
    assert journal_ops(h.journal)[-1] == 'completion'


def test_a_tree_that_survives_the_end_is_never_recorded_clean(wire):
    h = wire(**OK)
    _tree(h, dies_on_terminate=False)
    assert _end(h)['state'] == ledger_mod.DEAD_UNVERIFIED
    ops = journal_ops(h.journal)
    assert 'completion' not in ops and ops[-1] == 'quarantine'


def test_a_terminate_that_fails_on_a_living_tree_is_quarantined_and_still_revokes(wire):
    h = wire(**OK)
    _tree(h, dies_on_terminate=False)

    def refuse(job):
        raise OSError('TerminateJobObject failed')

    h.boundary.terminate_job = refuse
    h.launch._end_job = refuse
    assert _end(h)['state'] == ledger_mod.DEAD_UNVERIFIED
    assert h.broker.revoked == ['e1'] and h.boundary.closed == []
    assert journal_ops(h.journal)[-1] == 'quarantine'


@pytest.mark.parametrize('answer', [False, None, 0.0, '0', [], -1])
def test_only_an_integer_zero_member_count_proves_the_tree_gone(wire, answer):
    h = wire(**OK)
    _tree(h, answer=answer)
    assert _end(h)['state'] == ledger_mod.DEAD_UNVERIFIED


def test_the_admission_is_revoked_before_the_tree_is_ended_and_the_count_is_read_after(wire):
    h = wire(**OK)
    h.launch.start(job=h.job)
    h.launch.cancel(reason='host asked', outcome=0)
    events = h.api.events
    assert events.index('revoke') < events.index('end_job') < events.index('quiesce')


def test_an_end_with_no_workload_outcome_is_never_a_clean_one_whatever_the_tree_says(wire):
    h = wire(**OK)
    _tree(h)
    h.launch.start(job=h.job)
    assert h.launch.cancel(reason='host asked', outcome=None)['state'] == (
        ledger_mod.DEAD_UNVERIFIED)
    assert 'completion' not in journal_ops(h.journal)


def test_an_end_is_not_clean_without_a_resource_reader_that_proves_disposal(wire):
    h = wire(outcome=lambda process: 0)
    _tree(h)
    assert _end(h)['state'] == ledger_mod.DEAD_UNVERIFIED


def test_a_workload_that_reports_no_exit_code_is_an_error_never_a_result(wire):
    h = wire(outcome=lambda process: None, reader=OK['reader'])
    _tree(h)
    h.launch.start(job=h.job)
    with pytest.raises(staging.StageError, match='outcome'):
        h.launch.wait()
    assert h.launch.end_state['state'] == ledger_mod.DEAD_UNVERIFIED
    assert 'completion' not in journal_ops(h.journal)


def test_ending_twice_ends_nothing_twice(wire):
    h = wire(**OK)
    _tree(h)
    first = _end(h)
    assert h.launch.cancel(reason='again', outcome=0) == first
    assert h.boundary.terminated == [h.job] and h.broker.revoked == ['e1']


@pytest.mark.skipif(not iso.WINDOWS, reason='the Windows boundary exists only on Windows')
class TestTheKernelEnd:
    def test_ending_a_job_never_closes_the_handle_the_count_is_read_through(self, monkeypatch):
        calls = []
        monkeypatch.setattr(iso, '_TerminateJobObject', lambda job, code: calls.append('end') or 1)
        monkeypatch.setattr(iso, '_CloseHandle', lambda handle: calls.append('close'))
        iso.WindowsBoundary().terminate_job(77)
        assert calls == ['end']

    def test_a_kernel_that_refuses_the_end_is_an_error_never_a_silent_pass(self, monkeypatch):
        monkeypatch.setattr(iso, '_TerminateJobObject', lambda job, code: 0)
        with pytest.raises(iso.IsolationUnavailable):
            iso.WindowsBoundary().terminate_job(77)


# ── B9: an origin Core cannot positively attribute to the user is refused ──

class Conn:
    """One accepted connection run through the server's own transport gate: the
    backend, the attestor and Core's registry are the real ones over a fake process table."""

    def __init__(self, api, *, clock=lambda: T0, jobs=lambda: [JOB], readers=True,
                 local=('127.0.0.1', CORE), remote=('127.0.0.1', PEER), ports=(CORE,), **kw):
        backend = WindowsOriginBackend(readers=native_readers(
            api, core_port=CORE, jobs=jobs, clock=clock, **kw) if readers else None)
        self.backend = backend
        self.stub = SimpleNamespace(context=ctx(local, remote), origin_backend=backend,
                                    origin_registry=origin.CorePathRegistry(ports),
                                    evidence=None, evidence_acquired=False)

    def request(self):
        evidence = server.Handler.transport_evidence(self.stub)
        return origin.authorize_transport(evidence, local_host=True, remote_host=False,
                                          credential_origin='local')


def _raises(name):
    def fail(api):
        def boom(*a, **k):
            raise OSError(name)
        setattr(api, name, boom)
    return fail


def _execution_orphan(api):
    api.contained()
    del api.table[200]                                  # the launcher is gone


def _execution_escaped(api):
    api.contained()
    api.table[4124] = replace(api.table[4124], in_jobs=False)


def _two_owners(api):
    api.user()
    api.table[5555] = replace(api.table[4124])           # both owners look like the user
    api.rows.append(replace(api.rows[0], pid=5555))


REFUSED = {
    'owner table unreadable': dict(setup=_raises('tcp_rows')),
    'process unreadable': dict(setup=lambda api: (api.user(), _raises('process')(api))),
    'session unreadable': dict(setup=lambda api: (api.user(), _raises('core_session')(api))),
    'two owners of one port': dict(setup=_two_owners),
    'no row for the peer': dict(setup=lambda api: (api.user(), api.rows.clear())),
    'owner dead': dict(setup=lambda api: api.user(alive=False)),
    'creation time unreadable': dict(setup=lambda api: api.user(ct=None)),
    'an execution process in a Core Job': dict(setup=lambda api: api.contained()),
    'an execution orphaned from its launcher': dict(setup=_execution_orphan),
    'an execution that left the Job': dict(setup=_execution_escaped),
    'another session': dict(setup=lambda api: api.user(session=3)),
    'not the direct loopback path': dict(setup=lambda api: api.user(),
                                         remote=('10.0.0.9', PEER)),
    'a port Core did not register': dict(setup=lambda api: api.user(), ports=(1,)),
    'Core holds no Job at all': dict(setup=lambda api: api.contained(), jobs=lambda: []),
    'the shipped backend with no readers': dict(setup=lambda api: api.user(), readers=False),
}


def test_the_backend_itself_never_attests_a_user_off_the_loopback_path():
    api = FakeApi()
    api.user()
    backend = WindowsOriginBackend(readers=native_readers(
        api, core_port=CORE, jobs=lambda: [JOB], clock=lambda: T0))
    assert backend.attest(ctx()).origin is origin.OriginClass.USER
    off = backend.attest(ctx(remote=('10.0.0.9', PEER)))
    assert off.origin is origin.OriginClass.UNDETERMINED and off.process_binding is None


def test_the_control_a_genuine_user_on_the_direct_path_is_admitted():
    api = FakeApi()
    api.user()
    assert Conn(api).request() is True


@pytest.mark.parametrize('case', REFUSED)
def test_every_way_the_origin_is_unproven_is_refused(case):
    spec = dict(REFUSED[case])
    api = FakeApi()
    spec.pop('setup')(api)
    assert Conn(api, **spec).request() is False


def _later(change):
    api = FakeApi()
    api.user()
    conn = Conn(api)
    assert conn.request() is True
    change(api)
    return conn.request()


@pytest.mark.parametrize('change', [
    lambda api: api.user(ct=999),                               # PID reused: a new instance
    lambda api: api.user(alive=False),                          # the owner died
    lambda api: api.user(jobs=True),                            # it entered a Core Job
    lambda api: api.user(session=3),
    lambda api: api.table.pop(4124),
], ids=['pid reused', 'owner died', 'entered a Core Job', 'changed session', 'vanished'])
def test_a_user_binding_is_refused_the_moment_the_peer_stops_being_that_user(change):
    assert _later(change) is False


def test_a_binding_older_than_its_age_is_refused_without_a_reattest():
    api, now = FakeApi(), [T0]
    api.user()
    conn = Conn(api, clock=lambda: now[0], max_age_s=2.0)
    assert conn.request() is True
    now[0] = T0 + 5
    assert conn.request() is False


def test_a_hung_native_call_is_undetermined_at_the_deadline_not_a_held_request(monkeypatch):
    monkeypatch.setattr(origin, 'BACKEND_DEADLINE_S', 0.05)
    gate = threading.Event()
    api = FakeApi()
    api.user()
    api.tcp_rows = lambda: gate.wait(5) and []
    try:
        assert Conn(api).request() is False
    finally:
        gate.set()


def test_a_call_that_hangs_is_a_timeout_and_not_a_missing_answer(monkeypatch):
    monkeypatch.setattr(origin, 'BACKEND_DEADLINE_S', 0.05)
    gate = threading.Event()
    try:
        with pytest.raises(TimeoutError):
            origin.bounded(gate.wait, 5)
    finally:
        gate.set()


def test_the_registry_approves_only_a_user_on_the_direct_local_path_to_a_registered_port():
    registry = origin.CorePathRegistry((CORE,))
    context = ctx()
    for kind, path in itertools.product(origin.OriginClass, origin.PathClass):
        evidence = origin.OriginEvidence(origin=kind, path=path, identity='x',
                                         process_binding=object(), accept_generation='g1')
        want = kind is origin.OriginClass.USER and path is origin.PathClass.DIRECT_LOCAL
        assert registry.approved(context, evidence) is want, (kind, path)


def test_a_backend_with_no_readers_validates_nothing_even_a_genuine_looking_binding():
    api = FakeApi()
    api.user()
    good = Conn(api)
    assert good.request() is True
    evidence = good.stub.evidence
    assert WindowsOriginBackend().valid(good.stub.context, evidence) is False
    assert WindowsOriginBackend().attest(good.stub.context).origin is origin.OriginClass.UNDETERMINED


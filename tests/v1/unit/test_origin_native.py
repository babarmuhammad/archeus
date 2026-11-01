"""PV-20 B9: the native origin readers, the USER origin by exclusion and the Core path
registry, all against a fake api. No ctypes DLL is loaded, no socket opened, no process
touched: `Win32OriginApi` is never constructed here, and a test pins that importing the
module calls nothing native. PID reuse is a fake process table, as the design requires
(F9C: reuse was never observed natively and cannot be forced from the fixture)."""

import importlib
import sys
from dataclasses import replace
import threading
import time

import pytest

from archeus.api import origin
from archeus.node import attest, origin_native
from archeus.node.origin_native import ESTABLISHED, RawProcess, TcpRow, native_readers
from archeus.node.origin_windows import WindowsOriginBackend

CORE = 8731
PEER = 54321
JOB = 777
T0 = 1000.0
SESSION = 2


def _proc(pid, parent, ct, name, *, alive=True, session=SESSION, jobs=False):
    return RawProcess(alive=alive, creation_time=ct, parent_pid=parent, name=name,
                      session_id=session, in_jobs=jobs)


class FakeApi:
    def __init__(self):
        self.rows = [TcpRow('127.0.0.1', PEER, '127.0.0.1', CORE, ESTABLISHED, 4124),
                     TcpRow('127.0.0.1', CORE, '127.0.0.1', PEER, ESTABLISHED, 9000)]
        self.table = {}
        self.session = SESSION
        self.calls = []

    def tcp_rows(self):
        self.calls.append('rows')
        return list(self.rows)

    def core_session(self):
        return self.session

    def process(self, pid, jobs):
        self.calls.append(('process', pid, jobs))
        found = self.table.get(pid)
        if found is None:
            return None
        return found if JOB in jobs else replace(found, in_jobs=False)

    def contained(self, pid=4124, ct=100, **overrides):
        """An execution's process: wxc-exec (200) -> services.exe (100), inside the Job."""
        self.table[100] = _proc(100, 0, 10, 'services.exe')
        self.table[200] = _proc(200, 100, 20, 'WXC-Exec.EXE')
        self.table[pid] = _proc(pid, 200, ct, 'claude.exe', jobs=True, **overrides)

    def user(self, pid=4124, ct=100, **overrides):
        """The user's own process: explorer.exe (300) child, in no Job."""
        self.table[300] = _proc(300, 0, 10, 'explorer.exe')
        self.table[pid] = _proc(pid, 300, ct, 'curl.exe', **overrides)


@pytest.fixture
def api():
    return FakeApi()


def readers(api, **kw):
    return native_readers(api, core_port=CORE, jobs=lambda: [JOB], clock=lambda: T0, **kw)


def ctx(local=('127.0.0.1', CORE), remote=('127.0.0.1', PEER), gen='g1'):
    return origin.ConnectionContext(object(), local, remote, gen)


# ── importing is inert ──

def test_importing_the_module_loads_no_dll_and_calls_nothing_native(monkeypatch):
    def forbidden(*a, **k):
        raise AssertionError('native call at import')

    import ctypes
    monkeypatch.setattr(ctypes, 'WinDLL', forbidden, raising=False)
    monkeypatch.setattr(ctypes, 'windll', forbidden, raising=False)
    importlib.reload(origin_native)
    assert callable(origin_native.Win32OriginApi)


def test_the_real_api_refuses_to_build_off_windows(monkeypatch):
    monkeypatch.setattr(sys, 'platform', 'linux')
    with pytest.raises(RuntimeError):
        origin_native.Win32OriginApi()


# ── port -> owner ──

def _owner(api, port=PEER, **kw):
    return readers(api, **kw).resolve_owner(port)


def test_the_owner_is_the_one_established_loopback_row_of_the_peer_port(api):
    assert _owner(api).pid == 4124


@pytest.mark.parametrize('row', [
    TcpRow('127.0.0.1', PEER, '127.0.0.1', CORE, 2, 4124),            # not established
    TcpRow('127.0.0.1', PEER, '127.0.0.1', CORE, ESTABLISHED, 0),     # TIME_WAIT-style pid 0
    TcpRow('127.0.0.1', PEER, '127.0.0.1', CORE + 1, ESTABLISHED, 4124),   # other listener
    TcpRow('10.0.0.5', PEER, '127.0.0.1', CORE, ESTABLISHED, 4124),   # not loopback
    TcpRow('127.0.0.1', PEER, '10.0.0.5', CORE, ESTABLISHED, 4124),
])
def test_a_row_that_is_not_the_direct_loopback_peer_names_no_owner(api, row):
    api.rows = [row]
    assert _owner(api).pid is None


def test_another_port_has_no_owner(api):
    assert _owner(api, PEER + 1).pid is None


def test_the_servers_own_row_is_never_taken_for_the_peer(api):
    api.rows = [r for r in api.rows if r.local_port == CORE]
    assert _owner(api).pid is None


def test_two_different_owners_of_one_port_are_ambiguous_and_name_no_owner(api):
    api.rows.append(TcpRow('127.0.0.1', PEER, '127.0.0.1', CORE, ESTABLISHED, 5555))
    assert _owner(api).pid is None


def test_the_same_owner_twice_is_not_ambiguous(api):
    api.rows.append(api.rows[0])
    assert _owner(api).pid == 4124


# ── pid -> process ──

def test_a_contained_process_reads_alive_in_the_job_under_the_launcher(api):
    api.contained()
    info = readers(api).read_process(4124)
    assert info.alive is True and info.creation_time == 100 and info.in_core_job is True
    assert info.ancestors == ('wxc-exec', 'services') and info.same_session is True


def test_only_the_peer_is_tested_against_the_job_table(api):
    api.contained()
    readers(api).read_process(4124)
    probes = [c for c in api.calls if c[0] == 'process']
    assert probes[0][2] == (JOB,) and all(p[2] == () for p in probes[1:])


def test_no_process_is_dead_with_no_creation_time(api):
    info = readers(api).read_process(4124)
    assert (info.alive, info.creation_time, info.in_core_job) == (False, None, False)


def test_a_dead_process_the_job_still_lists_is_not_alive_f9c(api):
    api.contained()
    api.table[4124] = _proc(4124, 200, 100, 'claude.exe', alive=False, jobs=True)
    info = readers(api).read_process(4124)
    assert info.alive is False and info.in_core_job is True
    result = attest.attest_owner(remote_port=PEER, resolve_owner=readers(api).resolve_owner,
                                 read_process=readers(api).read_process, clock=lambda: T0)
    assert not result.ok and attest.DEAD in result.failures


def test_another_session_is_not_the_same_session(api):
    api.user(session=SESSION + 1)
    assert readers(api).read_process(4124).same_session is False


def test_a_parent_created_after_its_child_is_a_recycled_pid_and_ends_the_chain(api):
    api.contained()
    api.table[200] = _proc(200, 100, 500, 'wxc-exec.exe')          # reused: newer than the child
    assert readers(api).read_process(4124).ancestors == ()


def test_a_dead_parent_ends_the_chain(api):
    api.contained()
    api.table[200] = _proc(200, 100, 20, 'wxc-exec.exe', alive=False)
    assert readers(api).read_process(4124).ancestors == ()


def test_a_missing_parent_ends_the_chain(api):
    api.contained()
    del api.table[200]
    assert readers(api).read_process(4124).ancestors == ()


def test_a_parent_cycle_ends_because_a_parent_is_never_newer_than_its_child(api):
    api.table[1] = _proc(1, 2, 30, 'a.exe')
    api.table[2] = _proc(2, 1, 20, 'b.exe')
    api.table[4124] = _proc(4124, 1, 100, 'c.exe')
    assert readers(api).read_process(4124).ancestors == ('a', 'b')


def test_the_ancestor_walk_is_bounded(api):
    for pid in range(1, 100):
        api.table[pid] = _proc(pid, pid + 1, 1000 - pid, 'x.exe')
    api.table[4124] = _proc(4124, 1, 2000, 'c.exe')
    assert len(readers(api).read_process(4124).ancestors) == origin_native.MAX_ANCESTORS


# ── PID reuse, as a fake process table ──

def test_a_recycled_pid_with_a_new_creation_time_fails_the_recheck(api):
    api.contained()
    r = readers(api)
    bound = attest.attest_owner(remote_port=PEER, resolve_owner=r.resolve_owner,
                                read_process=r.read_process, clock=r.clock)
    assert bound.ok
    assert attest.binding_valid(bound.binding, read_process=r.read_process, clock=r.clock).ok
    api.contained(ct=101)                  # same PID, a new instance, equally contained
    again = attest.binding_valid(bound.binding, read_process=r.read_process, clock=r.clock)
    assert not again.ok and again.failures == (attest.CREATION_TIME_MISMATCH,)


def test_a_recycled_pid_fails_a_user_binding_too(api):
    api.user()
    r = readers(api)
    bound = attest.attest_peer(remote_port=PEER, resolve_owner=r.resolve_owner,
                               read_process=r.read_process, clock=r.clock)
    assert bound.ok and bound.binding.core_job_at_accept is False
    api.user(ct=101)
    again = attest.binding_valid(bound.binding, read_process=r.read_process, clock=r.clock)
    assert again.failures == (attest.CREATION_TIME_MISMATCH,)


def test_the_peer_dying_after_accept_fails_the_recheck(api):
    api.user()
    r = readers(api)
    bound = attest.attest_peer(remote_port=PEER, resolve_owner=r.resolve_owner,
                               read_process=r.read_process, clock=r.clock)
    api.user(alive=False)
    assert attest.DEAD in attest.binding_valid(bound.binding, read_process=r.read_process,
                                               clock=r.clock).failures


# ── USER by exclusion, through the shipped backend and the Core registry ──

REGISTRY = origin.CorePathRegistry({CORE})


def _attest(api, context=None, **kw):
    backend = WindowsOriginBackend(readers=readers(api, **kw))
    context = context or ctx()
    return backend, context, backend.attest(context)


def test_a_process_outside_every_job_in_the_session_on_the_loopback_is_user(api):
    api.user()
    backend, context, evidence = _attest(api)
    assert (evidence.origin, evidence.path) == (origin.OriginClass.USER, origin.PathClass.DIRECT_LOCAL)
    assert origin.validate_evidence(context, evidence) and backend.valid(context, evidence)
    assert REGISTRY.approved(context, evidence) is True


def test_a_contained_peer_is_execution_and_the_registry_never_approves_it(api):
    api.contained()
    backend, context, evidence = _attest(api)
    assert evidence.origin == origin.OriginClass.EXECUTION
    assert REGISTRY.approved(context, evidence) is False


@pytest.mark.parametrize('what, change', [
    ('another session', lambda a: a.user(session=SESSION + 1)),
    ('in a Core Job without the launcher above it',
     lambda a: a.table.update({4124: _proc(4124, 300, 100, 'x.exe', jobs=True)})),
    ('under the launcher but outside the Job',
     lambda a: (a.contained(), a.table.update({4124: _proc(4124, 200, 100, 'x.exe')}))),
    ('dead', lambda a: a.user(alive=False)),
    ('no creation time', lambda a: a.user(ct=None)),
    ('unknown to the process table', lambda a: a.table.clear()),
])
def test_a_peer_that_is_not_positively_the_user_is_undetermined(api, what, change):
    api.user()
    change(api)
    _, _, evidence = _attest(api)
    assert evidence.origin == origin.OriginClass.UNDETERMINED, what
    assert evidence.process_binding is None


def test_a_reader_that_does_not_report_the_session_cannot_make_a_user():
    def peer(**info):
        base = dict(alive=True, creation_time=1, ancestors=('explorer',), in_core_job=False)
        return attest.attest_peer(remote_port=1, resolve_owner=lambda p: attest.PeerOwner(5),
                                  read_process=lambda p: attest.ProcessInfo(**{**base, **info}),
                                  clock=lambda: 0.0)

    assert peer().ok is False and peer().binding is None
    assert peer(same_session=True).binding.core_job_at_accept is False


@pytest.mark.parametrize('context', [
    ctx(local=('10.0.0.5', CORE)), ctx(remote=('10.0.0.6', PEER)),
    ctx(local=('127.0.0.1', CORE), remote=('::ffff:127.0.0.1', PEER)),
])
def test_no_user_without_the_direct_loopback_path(api, context):
    api.user()
    assert _attest(api, context)[2].origin == origin.OriginClass.UNDETERMINED


def test_a_user_binding_loses_validity_when_the_peer_enters_a_core_job(api):
    api.user()
    backend, context, evidence = _attest(api)
    assert backend.valid(context, evidence)
    api.table[4124] = _proc(4124, 300, 100, 'curl.exe', jobs=True)
    assert backend.valid(context, evidence) is False


def test_a_user_binding_loses_validity_when_the_launcher_appears_above_it(api):
    api.user()
    backend, context, evidence = _attest(api)
    api.contained()
    api.table[4124] = _proc(4124, 200, 100, 'curl.exe')
    assert backend.valid(context, evidence) is False


def test_a_user_binding_expires_without_reattest_and_is_renewed_with_it_for_the_same_process(api):
    api.user()
    now = [T0]
    kw = dict(clock=lambda: now[0])
    r = native_readers(api, core_port=CORE, jobs=lambda: [JOB], **kw, reattest=True)
    backend = WindowsOriginBackend(readers=r)
    context = ctx()
    evidence = backend.attest(context)
    now[0] += attest.DEFAULT_MAX_AGE_S + 1
    assert backend.valid(context, evidence) is True
    now[0] += attest.DEFAULT_MAX_AGE_S + 1
    api.user(ct=101)
    assert backend.valid(context, evidence) is False


def test_a_reattest_that_finds_another_kind_of_process_is_refused(api):
    api.user()
    now = [T0]
    backend = WindowsOriginBackend(readers=native_readers(
        api, core_port=CORE, jobs=lambda: [JOB], clock=lambda: now[0], reattest=True))
    context = ctx()
    evidence = backend.attest(context)
    now[0] += attest.DEFAULT_MAX_AGE_S + 1
    api.contained()
    assert backend.valid(context, evidence) is False


def test_without_reattest_a_user_binding_just_expires(api):
    api.user()
    now = [T0]
    backend = WindowsOriginBackend(readers=native_readers(
        api, core_port=CORE, jobs=lambda: [JOB], clock=lambda: now[0]))
    context = ctx()
    evidence = backend.attest(context)
    now[0] += attest.DEFAULT_MAX_AGE_S + 1
    assert backend.valid(context, evidence) is False


# ── the Core path registry ──

def _user_evidence(**kw):
    base = dict(origin=origin.OriginClass.USER, path=origin.PathClass.DIRECT_LOCAL,
                identity='process:1:2', process_binding=object(), accept_generation='g1',
                reason='attested')
    return origin.OriginEvidence(**{**base, **kw})


def test_the_registry_approves_a_user_on_a_registered_direct_path():
    assert REGISTRY.approved(ctx(), _user_evidence()) is True
    assert REGISTRY.approved(ctx(local=('::1', CORE), remote=('::1', PEER)), _user_evidence()) is True


@pytest.mark.parametrize('kind', [origin.OriginClass.EXECUTION, origin.OriginClass.VERIFIER,
                                  origin.OriginClass.UNDETERMINED])
def test_the_registry_never_approves_a_non_user_origin(kind):
    assert REGISTRY.approved(ctx(), _user_evidence(origin=kind)) is False


@pytest.mark.parametrize('path', [p for p in origin.PathClass if p != origin.PathClass.DIRECT_LOCAL])
def test_the_registry_never_approves_a_path_that_is_not_direct_local(path):
    assert REGISTRY.approved(ctx(), _user_evidence(path=path)) is False


def test_the_registry_refuses_an_unregistered_port_and_a_non_loopback_end():
    assert REGISTRY.approved(ctx(local=('127.0.0.1', CORE + 1)), _user_evidence()) is False
    assert REGISTRY.approved(ctx(local=('192.168.0.4', CORE)), _user_evidence()) is False
    assert REGISTRY.approved(ctx(remote=('192.168.0.4', PEER)), _user_evidence()) is False


@pytest.mark.parametrize('bad', [None, object(), {'origin': 'user'}])
def test_the_registry_refuses_malformed_arguments(bad):
    assert REGISTRY.approved(ctx(), bad) is False
    assert REGISTRY.approved(bad, _user_evidence()) is False
    assert REGISTRY.approved(ctx(local=None), _user_evidence()) is False


def test_the_registry_with_no_ports_approves_nothing():
    assert origin.CorePathRegistry(()).approved(ctx(), _user_evidence()) is False


@pytest.mark.parametrize('ports', [[0], [65536], ['8731'], [True], [8731.0]])
def test_the_registry_refuses_ill_formed_ports(ports):
    with pytest.raises(ValueError):
        origin.CorePathRegistry(ports)


# ── every backend call is deadline-bounded ──

@pytest.fixture
def fast(monkeypatch):
    monkeypatch.setattr(origin, 'BACKEND_DEADLINE_S', 0.05)


def test_a_call_inside_the_deadline_returns_its_value_and_a_raise_propagates(fast):
    assert origin.bounded(lambda a, b: a + b, 1, 2) == 3
    with pytest.raises(KeyError):
        origin.bounded(lambda: {}['x'])


def test_a_hung_call_times_out_at_the_deadline(fast):
    gate = threading.Event()
    started = time.monotonic()
    with pytest.raises(TimeoutError):
        origin.bounded(gate.wait)
    assert time.monotonic() - started < 1
    gate.set()


def test_hung_calls_hold_their_slots_and_the_next_one_fails_at_once(fast, monkeypatch):
    monkeypatch.setattr(origin, '_slots', threading.BoundedSemaphore(2))
    gate = threading.Event()
    for _ in range(2):
        with pytest.raises(TimeoutError):
            origin.bounded(gate.wait)
    started = time.monotonic()
    with pytest.raises(TimeoutError, match='saturated'):
        origin.bounded(lambda: 'never runs')
    assert time.monotonic() - started < 0.04
    gate.set()
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        try:
            assert origin.bounded(lambda: 'free') == 'free'
            break
        except TimeoutError:
            time.sleep(0.01)
    else:
        pytest.fail('slots were never returned')


def test_a_native_reader_that_hangs_makes_the_attest_a_timeout_not_a_hang(api, fast):
    gate = threading.Event()
    r = readers(api)
    hung = origin.AttestationReaders(resolve_owner=lambda port: gate.wait() or None,
                                     read_process=r.read_process, clock=r.clock)
    backend = WindowsOriginBackend(readers=hung)
    with pytest.raises(TimeoutError):
        origin.bounded(backend.attest, ctx())
    gate.set()


def test_a_worker_thread_that_cannot_start_gives_its_slot_back(monkeypatch):
    monkeypatch.setattr(origin, '_slots', threading.BoundedSemaphore(2))
    start = threading.Thread.start

    def refuse(self):
        raise RuntimeError("can't start new thread")

    monkeypatch.setattr(threading.Thread, 'start', refuse)
    for _ in range(5):
        with pytest.raises(RuntimeError, match='start'):
            origin.bounded(lambda: 1)
    monkeypatch.setattr(threading.Thread, 'start', start)
    assert origin.bounded(lambda: 1) == 1


# ── a failed Job probe is no evidence ──

class Kernel:
    """Win32 calls the real api makes for one process, answered by a script."""

    def __init__(self, in_job=lambda job, inside: 0):
        self.in_job = in_job

    def OpenProcess(self, *a):
        return 77

    def CloseHandle(self, *a):
        pass

    def WaitForSingleObject(self, *a):
        return origin_native.WAIT_TIMEOUT

    def GetProcessTimes(self, handle, created, *rest):
        created._obj.low, created._obj.high = 1, 2
        return 1

    def IsProcessInJob(self, handle, job, inside):
        return self.in_job(job, inside._obj)

    def CreateToolhelp32Snapshot(self, *a):
        return 5

    def Process32FirstW(self, *a):
        return 0

    def ProcessIdToSessionId(self, pid, session):
        session._obj.value = SESSION
        return 1


def _win32(kernel):
    api = object.__new__(origin_native.Win32OriginApi)
    api.kernel = kernel
    return api


def _answers(value):
    def in_job(job, inside):
        inside.value = value
        return 1
    return in_job


def test_a_job_probe_that_fails_is_a_reader_error_not_outside_the_job():
    api = _win32(Kernel())
    with pytest.raises(OSError, match='IsProcessInJob'):
        api.process(1234, (0xdead,))


def test_a_null_job_handle_is_refused_because_the_kernel_reads_it_as_any_job():
    api = _win32(Kernel(_answers(0)))
    with pytest.raises(OSError):
        api.process(1234, (0,))


@pytest.mark.parametrize('inside, expected', [(0, False), (1, True)])
def test_a_probe_that_succeeds_says_whether_the_process_is_in_a_job(inside, expected):
    assert _win32(Kernel(_answers(inside))).process(1234, (0xdead,)).in_jobs is expected


def test_an_orphan_whose_job_probe_fails_is_not_attested_as_the_user():
    api = _win32(Kernel())
    r = native_readers(_Win32Rows(api), core_port=CORE, jobs=lambda: [JOB], clock=lambda: T0)
    result = attest.attest_peer(**r.attest_kwargs(PEER))
    assert not result.ok and result.failures == (attest.READER_ERROR,)


class _Win32Rows:
    def __init__(self, api):
        self.api = api

    def tcp_rows(self):
        return [TcpRow('127.0.0.1', PEER, '127.0.0.1', CORE, ESTABLISHED, 1234)]

    def process(self, pid, jobs):
        return self.api.process(pid, jobs)

    def core_session(self):
        return SESSION

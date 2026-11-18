import logging
import threading

import pytest

from archeus.core import runtime

SILENT_WORKERS = ('metrics', 'automation', 'policy', 'plan', 'intent',
                  'knowledge', 'world')
WORKER_NAMES = ('exec', 'verify', 'loop')


class QuiesceFailure(RuntimeError):
    pass


class DbCloseFailure(RuntimeError):
    pass


class LockFailure(RuntimeError):
    pass


class InterruptedDuringQuiesce(BaseException):
    pass


class FakeWorker:
    def __init__(self, log, name, stuck=False):
        self.log, self.name = log, name
        self.stuck, self.timeouts, self.stops = stuck, [], 0

    def stop(self):
        self.stops += 1
        self.log.append('%s.stop' % self.name)

    def join(self, timeout):
        self.timeouts.append(timeout)
        self.log.append('%s.join' % self.name)
        return self.stuck


class ExecWorker(FakeWorker):
    pass


class VerifyWorker(FakeWorker):
    pass


class LoopWorker(FakeWorker):
    pass


WORKER_CLASSES = {'exec': ExecWorker, 'verify': VerifyWorker, 'loop': LoopWorker}


class JoinCanary:
    def __init__(self, name):
        self.name = name

    def stop(self):
        pass

    def join(self, timeout):
        pytest.fail('%s was joined although Core has no activation' % self.name)


class FakeActivation:
    def __init__(self, log, *, quiesce_error=None, close_error=None,
                 clock=None, spend=0.0):
        self.log = log
        self._qe, self._ce = quiesce_error, close_error
        self.quiesce_error = quiesce_error
        self.clock, self.spend = clock, spend
        self.deadlines, self.quiesce_count, self.close_count = [], 0, 0
        self.quiesced = self.closed = False

    def quiesce(self, *, deadline=None):
        self.log.append('quiesce')
        self.quiesced = True
        self.quiesce_count += 1
        self.deadlines.append(deadline)
        if self.clock is not None and self.spend:
            self.clock.advance(self.spend)
        if self._qe is not None:
            raise self._qe

    def close(self):
        self.log.append('close')
        self.closed = True
        self.close_count += 1
        if self._ce is not None:
            raise self._ce


class FakeClock:
    def __init__(self, at=1000.0):
        import time as _t
        self._real, self.at = _t, at
        self.now_calls = 0

    def monotonic(self):
        self.now_calls += 1
        return self.at

    def advance(self, seconds):
        self.at += seconds

    def __getattr__(self, name):
        return getattr(self._real, name)


class NeverClock(FakeClock):
    def monotonic(self):
        pytest.fail('stop() computed a quiesce deadline although pv20 is None')


class FakeDb:
    def __init__(self, log, close_error=None):
        self.log, self.closed, self._ce = log, [], close_error

    def close(self, *, drain):
        self.log.append('db.close')
        self.closed.append(drain)
        if self._ce is not None:
            raise self._ce


class FakeLock:
    def __init__(self, log, release_error=None):
        self.log, self.releases, self._re = log, 0, release_error

    def release(self):
        self.log.append('lock.release')
        self.releases += 1
        if self._re is not None:
            raise self._re


class _Sse:
    def __init__(self, log):
        self.log = log

    def close_all(self):
        self.log.append('sse.close_all')


class FakeApi:
    def __init__(self, log):
        self.log, self.stopping = log, False
        self.sse = _Sse(log)


class RecordingHandler(logging.NullHandler):
    def __init__(self, log):
        super().__init__()
        self.log, self.closes = log, 0

    def close(self):
        self.closes += 1
        self.log.append('handler.close')
        super().close()


def build_core(log, *, activation, workers=None, db=None, lock=None, handler=None):
    core = object.__new__(runtime.Core)
    core._done = threading.Event()
    core.exit_code = 0
    core._log_handler = handler
    core.api = FakeApi(log)
    core.server = None
    for name in SILENT_WORKERS:
        setattr(core, name, FakeWorker(log, name))
    given = workers or {}
    for name in WORKER_NAMES:
        if name in given:
            setattr(core, name, given[name])
        else:
            setattr(core, name, WORKER_CLASSES[name](log, name))
    core.pv20 = activation
    core.db = FakeDb(log) if db is None else db
    core.lock = FakeLock(log) if lock is None else lock
    return core


def joinable(log, *, stuck=(), skip=()):
    workers = {}
    for name in WORKER_NAMES:
        if name in skip:
            workers[name] = None
        else:
            workers[name] = WORKER_CLASSES[name](log, name, stuck=name in stuck)
    return workers


@pytest.fixture
def core_json(monkeypatch):
    calls = []
    monkeypatch.setattr(runtime.discovery, 'remove_core_json',
                        lambda: calls.append('remove_core_json'))
    return calls


@pytest.fixture
def handler_on_log():
    log = []
    handler = RecordingHandler(log)
    runtime.log.addHandler(handler)
    try:
        assert handler in runtime.log.handlers
        yield log, handler
    finally:
        runtime.log.removeHandler(handler)


def test_a_stop_interrupted_inside_quiesce_never_releases_the_lock(core_json):
    log = []
    act = FakeActivation(log, quiesce_error=InterruptedDuringQuiesce('ctrl-c'))
    handler = RecordingHandler(log)
    core = build_core(log, activation=act, handler=handler,
                      db=FakeDb(log, close_error=DbCloseFailure('never reached')))
    db, lock = core.db, core.lock
    with pytest.raises(InterruptedDuringQuiesce):
        core.stop()
    assert 'quiesce' in log
    assert [e for e in log if e.endswith('.join') or e == 'close'] == []
    assert act.close_count == 0 and act.quiesce_count == 1
    assert db.closed == [] and lock.releases == 0
    assert core.db is not None and core.lock is not None
    assert core._log_handler is handler and handler.closes == 0
    assert core.api is not None and not core._done.is_set()
    assert core_json == []


def test_a_database_that_will_not_close_keeps_the_lock_and_never_reports_a_clean_stop(
        core_json):
    log = []
    act = FakeActivation(log)
    db = FakeDb(log, close_error=DbCloseFailure('writer stuck'))
    handler = RecordingHandler(log)
    core = build_core(log, activation=act, db=db, handler=handler)
    with pytest.raises(DbCloseFailure, match='writer stuck') as raised:
        core.stop()
    assert not isinstance(raised.value, QuiesceFailure)
    assert act.close_count == 1 and 'close' in log
    assert sorted(e for e in log if e.endswith('.join')) == \
        sorted(['exec.join', 'verify.join', 'loop.join'])
    assert db.closed == [True]
    assert core_json == [] and core.lock is not None and core.lock.releases == 0
    assert core.db is not None
    assert core._log_handler is handler and handler.closes == 0
    assert core.api is not None and not core._done.is_set()


def test_a_lock_that_will_not_release_leaves_core_holding_the_log_and_the_wait(
        core_json):
    log = []
    act = FakeActivation(log)
    lock = FakeLock(log, release_error=LockFailure('lock busy'))
    handler = RecordingHandler(log)
    runtime.log.addHandler(handler)
    try:
        core = build_core(log, activation=act, lock=lock, handler=handler)
        with pytest.raises(LockFailure, match='lock busy'):
            core.stop()
        assert core_json == ['remove_core_json']
        assert core.db is None and log.index('lock.release') > log.index('db.close')
        assert core.lock is not None and lock.releases == 1
        assert 'handler.close' not in log and handler.closes == 0
        assert handler in runtime.log.handlers
        assert core.api is not None and not core._done.is_set()
    finally:
        runtime.log.removeHandler(handler)


def test_only_the_worker_that_did_not_stop_is_named_and_the_others_are_still_joined(
        core_json, caplog, monkeypatch):
    caplog.set_level(logging.WARNING, logger='archeus.core')
    log = []
    monkeypatch.setattr(runtime, 'time', FakeClock(at=100.0))
    act = FakeActivation(log)
    workers = joinable(log, stuck=('verify',))
    core = build_core(log, activation=act, workers=workers)
    assert core.stop() is None
    warnings = [r.getMessage() for r in caplog.records if 'did not stop' in r.getMessage()]
    assert len(warnings) == 1 and 'VerifyWorker' in warnings[0]
    assert 'ExecWorker' not in caplog.text and 'LoopWorker' not in caplog.text
    assert sorted(e for e in log if e.endswith('.join')) == \
        sorted(['exec.join', 'verify.join', 'loop.join'])
    assert [w.timeouts for w in (core.exec, core.verify, core.loop)] == \
        [[10.0], [10.0], [10.0]]
    assert act.close_count == 1 and core.db is None and core.lock is None
    assert core_json == ['remove_core_json']


def test_quiesce_is_given_the_same_end_the_workers_count_down_from(core_json, monkeypatch):
    log = []
    clock = FakeClock(at=100.0)
    monkeypatch.setattr(runtime, 'time', clock)
    monkeypatch.setattr(runtime, 'QUIESCE_S', 4.0)
    act = FakeActivation(log, clock=clock, spend=1.5)
    core = build_core(log, activation=act)
    assert core.stop() is None
    assert act.deadlines == [104.0]
    budgets = [w.timeouts for w in (core.exec, core.verify, core.loop)]
    assert budgets == [[2.5], [2.5], [2.5]]
    assert all(0.0 < b < 4.0 for b in budgets[0])
    assert act.close_count == 1 and core.db is None and core.lock is None


def test_a_quiesce_that_spends_the_whole_budget_leaves_every_join_at_exactly_zero(
        core_json, monkeypatch, caplog):
    caplog.set_level(logging.WARNING, logger='archeus.core')
    log = []
    clock = FakeClock(at=100.0)
    monkeypatch.setattr(runtime, 'time', clock)
    monkeypatch.setattr(runtime, 'QUIESCE_S', 4.0)
    act = FakeActivation(log, clock=clock, spend=9.0)
    core = build_core(log, activation=act)
    assert core.stop() is None
    budgets = [w.timeouts for w in (core.exec, core.verify, core.loop)]
    assert budgets == [[0.0], [0.0], [0.0]]
    assert all(type(b) is float and b >= 0.0 for row in budgets for b in row)
    assert sorted(e for e in log if e.endswith('.join')) == \
        sorted(['exec.join', 'verify.join', 'loop.join'])
    assert 'did not stop' not in caplog.text
    assert act.quiesce_count == 1 and act.close_count == 1
    assert core.db is None and core.lock is None and core._done.is_set()
    assert core_json == ['remove_core_json']


@pytest.mark.parametrize('skip', [('verify',), ('loop',), ('exec', 'verify', 'loop')],
                         ids=['verify-none', 'loop-none', 'no-worker-at-all'])
def test_a_worker_that_was_never_started_is_skipped_and_the_others_keep_their_budget(
        core_json, monkeypatch, skip):
    log = []
    clock = FakeClock(at=1000.0)
    monkeypatch.setattr(runtime, 'time', clock)
    act = FakeActivation(log)
    workers = joinable(log, skip=skip)
    core = build_core(log, activation=act, workers=workers)
    assert core.stop() is None
    joined = [n for n in WORKER_NAMES if n not in skip]
    assert sorted(e for e in log if e.endswith('.join')) == \
        sorted('%s.join' % n for n in joined)
    for name in WORKER_NAMES:
        if name not in skip:
            assert getattr(core, name).timeouts == [10.0]
    assert act.quiesce_count == 1 and act.close_count == 1
    assert core.db is None and core.lock is None and core_json == ['remove_core_json']


def test_without_an_activation_no_deadline_is_computed_and_no_worker_is_joined(
        core_json, monkeypatch):
    log = []
    monkeypatch.setattr(runtime, 'time', NeverClock())
    workers = {name: JoinCanary(name) for name in WORKER_NAMES}
    handler = RecordingHandler(log)
    core = build_core(log, activation=None, workers=workers, handler=handler)
    runtime.log.addHandler(handler)
    db, lock = core.db, core.lock
    try:
        assert core.stop() is None
    finally:
        runtime.log.removeHandler(handler)
    assert [e for e in log if e.endswith('.join') or e in ('quiesce', 'close')] == []
    assert db.closed == [True] and lock.releases == 1
    assert core_json == ['remove_core_json']
    assert core.db is None and core.lock is None and core.api is None
    assert handler.closes == 1 and handler not in runtime.log.handlers
    assert core._done.is_set()


def test_a_second_stop_keeps_completed_database_and_lock_cleanup_closed(
        core_json, monkeypatch):
    log = []
    act = FakeActivation(log, quiesce_error=QuiesceFailure('q'))
    monkeypatch.setattr(runtime, 'time', FakeClock(at=100.0))
    core = build_core(log, activation=act)
    db, lock = core.db, core.lock
    with pytest.raises(QuiesceFailure, match='q'):
        core.stop()
    try:
        core.stop()
    except QuiesceFailure as again:
        assert again is act.quiesce_error
    assert act.quiesced and act.closed
    assert db.closed == [True] and lock.releases == 1
    assert core_json == ['remove_core_json']
    assert core.db is None and core.lock is None and core.api is None
    assert core._done.is_set()


def test_the_log_handler_is_removed_and_closed_once_after_the_lock_is_released(
        handler_on_log, monkeypatch):
    log, handler = handler_on_log
    monkeypatch.setattr(runtime.discovery, 'remove_core_json',
                        lambda: log.append('remove_core_json'))
    act = FakeActivation(log)
    core = build_core(log, activation=act, handler=handler)
    assert core.stop() is None
    assert handler.closes == 1 and handler not in runtime.log.handlers
    assert log[-1] == 'handler.close'
    assert [e for e in log if e == 'handler.close'] == ['handler.close']
    assert (log.index('db.close') < log.index('remove_core_json')
            < log.index('lock.release') < log.index('handler.close'))
    assert log.count('remove_core_json') == 1
    assert core.api is None and core._done.is_set()

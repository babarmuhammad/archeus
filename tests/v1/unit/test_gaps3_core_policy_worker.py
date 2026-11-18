"""T-1142: the ten highest-risk branches of `archeus/core/policy/worker.py`
lines 1-47 inclusive (the whole `Expiry` slice at this tip) that no test in
this repo reaches — fail-closed and denial first, then boundaries, then error
paths. Existing coverage read first: tests/v1/integration/test_policy.py
(runs `authorization.expire_due` itself, never the worker), tests/v1/unit/
test_gaps_core_policy_worker.py (T-768) and the judge harness
(tests/v1/judge/client.py:282,365, which only constructs the worker and calls
`pass_once()` inside a black-box loop).

Final selected branches, ranked by risk (source:line · what a wrong version
does · test):

 1. worker.py:46 — a raising `writer.execute` propagates out of `pass_once()`
    and the approval stays PENDING and due, so the next pass retries it
    (`test_writer_failure_keeps_approval_retryable`).
 2. worker.py:43-44 — when the guard's own read fails, `pass_once()` submits
    nothing to the writer and propagates (`test_guard_read_failure_writes_nothing`).
 3. worker.py:26,28,43-45 — the clock is re-sampled by every call, so a clock
    step between `pending()` and `pass_once()` re-decides the work
    (`test_clock_move_between_pending_and_pass`).
 4. worker.py:26,43-46 — one `pass_once()` takes exactly one clock sample and
    exactly one `rows.where` read on the `db.read()` conn, and writes only
    after that read is closed (`test_pass_once_one_read_one_sample_write_after_close`).
 5. worker.py:33-34 — a failing read in `pending()` propagates after the read
    context is exited (no pinned read transaction, no wake)
    (`test_pending_read_failure_releases_and_propagates`).
 6. worker.py:36 — a failing `on_wake` callback is not swallowed by
    `pending()` (`test_failing_wake_callback_is_not_swallowed`).
 7. worker.py:35-36 — with three due rows the wake fires once per count, not
    once per row (`test_wake_fires_once_per_count_not_per_row`).
 8. worker.py:33-36 — the wake fires after the read transaction is released,
    and not at all when nothing was due (`test_wake_fires_after_the_read_is_closed`).
 9. worker.py:42-47 — `pass_once()` never takes the wake side effect, even
    when it writes (`test_pass_once_never_fires_the_wake`).
10. worker.py:20-23 — `actor` and `clock` are keyword-only, so the runtime's
    late wiring cannot bind them positionally (`test_actor_and_clock_are_keyword_only`).

Seams only, all already used by tests/v1/unit/test_gaps_core_policy_worker.py:
the worker's module-level `rows` object (swapped through `W`), the
`authorization.expire_due` attribute the worker reads when it builds the
writer call, an injected `clock`, and — for branch 1 only — the real database
with its real writer, whose `execute` one test wraps to fail exactly once.
No OS call is faked because this slice makes none; nothing here needs a
server, an adapter, a process, the network or the machine clock beyond one
wall-clock reading per test. Independent of every other test_gaps3 file: no
cross-test-file imports, no queue-order dependency, no sleeps, all writes
stay in the per-test ARCHEUS_HOME that tests/v1/conftest.py pins to tmp_path.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from archeus.core.application import authorization
from archeus.core.domain import entities, ids
from archeus.core.domain.events import new_event
from archeus.core.domain.values import Ref
from archeus.core.policy import worker as W
from archeus.core.policy.worker import Expiry
from archeus.infra.db import Database, rows

REQUESTER = ids.new_id('principal')


def stamp(offset_s):
    """A timestamp in the field's real shape, *offset_s* from the wall clock:
    the real `expire_due` compares against the writer's own `tx.now`, so a row
    branch 1 leaves for retry must be due to the real clock on any machine."""
    t = datetime.now(timezone.utc) + timedelta(seconds=offset_s)
    return t.isoformat(timespec='milliseconds').replace('+00:00', 'Z')


def fake_row(state='PENDING', kind='action', expires_at='2000-01-01T00:00:00.000Z'):
    """A decoded row: `_due` reads exactly these attributes of it."""
    return SimpleNamespace(entity=SimpleNamespace(id='apr_fake', state=state,
                                                  kind=kind, expires_at=expires_at))


class ReadCtx:
    """A recording `db.read()` context: the test's log sees exactly when the
    read transaction is entered and released, and a failed body still exits."""

    def __init__(self, name, log):
        self.name, self.log = name, log

    def __enter__(self):
        self.log.append('enter:' + self.name)
        return self.name

    def __exit__(self, *exc):
        self.log.append('exit:' + self.name)
        return False


class FakeWriter:
    """Records submissions and stamps their order into the shared log."""

    def __init__(self, log=None, answer=None):
        self.calls, self.log = [], log
        self.answer = {'expired': ['apr_x']} if answer is None else answer

    def execute(self, command, kwargs):
        self.calls.append((command, kwargs))
        if self.log is not None:
            self.log.append('write')
        return self.answer


class FakeDb:
    def __init__(self):
        self.log, self.reads = [], 0
        self.writer = FakeWriter(self.log)

    def read(self):
        self.reads += 1
        return ReadCtx('conn-%d' % self.reads, self.log)


def swap_rows(monkeypatch, *items, raise_exc=None):
    """The seam of tests/v1/unit/test_gaps_core_policy_worker.py: the worker's
    own `rows` object, recording every `where`, answering *items* or failing
    with *raise_exc* (a synthetic DB fault, never a real OS error)."""
    seen = []

    def where(conn, cls, **eq):
        if raise_exc is not None:
            raise raise_exc
        seen.append((conn, cls, eq))
        return list(items)
    monkeypatch.setattr(W, 'rows', SimpleNamespace(where=where))
    return seen


class Rig:
    """One real database (migrations give approvals their NOT NULLs and the
    unique live `action_hash`) holding the mission and plan the approval FKs
    demand; branch 1 needs the real writer so a failed sweep really leaves the
    row PENDING and the retry really lands in the state machine."""

    def __init__(self):
        self.db = Database.open()
        self.actor = Ref('system', ids.new_id('principal'))
        self.mid, self.pid = ids.new_id('mission'), ids.new_id('plan')
        self._n = 0

        def seed(tx, *, actor):
            tx.insert(entities.Mission(id=self.mid, workspace_id=ids.GLOBAL_WORKSPACE,
                                       title='M', objective='o', state='EXECUTING'),
                      actor=actor)
            tx.insert(entities.Plan(id=self.pid, mission_id=self.mid,
                                    plan_version=1, summary='s', state='APPROVED'),
                      actor=actor)
            tx.append(new_event('mission.created', Ref('mission', self.mid), actor,
                               payload={}, workspace=ids.GLOBAL_WORKSPACE))
        self.db.writer.execute(seed, {'actor': self.actor})

    def close(self):
        self.db.close()

    def approval(self, state='PENDING', kind='action', offset=-3600):
        """An approval as an earlier pass left it: the writer's own insert,
        each row with its event, a fresh `action_hash` per row."""
        self._n += 1
        a = entities.Approval(id=ids.new_id('approval'), kind=kind,
                              subject=Ref('plan', self.pid),
                              action_hash='%064x' % self._n, requested_by=REQUESTER,
                              mission_id=self.mid, plan_id=self.pid, state=state,
                              expires_at=stamp(offset))

        def put(tx, *, actor):
            tx.insert(a, actor=actor)
            tx.append(new_event('approval.requested', Ref('approval', a.id), actor,
                               payload={}, workspace=ids.GLOBAL_WORKSPACE))
        self.db.writer.execute(put, {'actor': self.actor})
        return a

    def expiry(self):
        return Expiry(self.db, actor=self.actor, clock=W._now)

    def state_of(self, a):
        with self.db.read() as conn:
            return rows.get(conn, entities.Approval, a.id).entity.state


@pytest.fixture
def rig():
    r = Rig()
    yield r
    r.close()


# ── fail-closed first: a failing sweep must never lose or fake the work ─────

def test_writer_failure_keeps_approval_retryable(rig, monkeypatch):
    """worker.py:46 — if `writer.execute(expire_due, ...)` raises (a transient
    lock), `pass_once()` must propagate, not answer `{'changed': False}`: a
    swallowed error tells WorldLoop the world settled while the approval sits
    PENDING forever and the next pass is the only thing that can end it. On
    the real database the failure leaves the row due (`pending()` still 1,
    state still PENDING — the queue is preserved), no wake fires on the failed
    pass, and the next `pass_once()` really retries and ends it EXPIRED.
    Catches: wrapping line 46 in try/except, or returning True on failure."""
    a = rig.approval(state='PENDING', kind='action')
    ex = rig.expiry()
    wakes = []
    ex.on_wake = lambda: wakes.append(1)
    real = rig.db.writer.execute
    state = {'fail': True}

    def flaky(command, data):
        if state['fail']:
            state['fail'] = False
            raise RuntimeError('database is locked (synthetic)')
        return real(command, data)
    monkeypatch.setattr(rig.db.writer, 'execute', flaky)
    with pytest.raises(RuntimeError):
        ex.pass_once()
    assert wakes == []                          # a failed pass woke nothing
    assert rig.state_of(a) == 'PENDING'         # the work survived the failure
    assert ex.pending() == 1                    # and is still queued for retry
    assert ex.pass_once() == {'changed': True}  # the retry is a real submission
    assert rig.state_of(a) == 'EXPIRED'


def test_guard_read_failure_writes_nothing(monkeypatch):
    """worker.py:43-44 — the write at line 46 is gated on the guard's own
    read: when `rows.where` raises inside `pass_once()`, the failure must
    propagate and `db.writer.execute` must not be reached. A guard that turns
    a read fault into 'nothing due' and answers `{'changed': False}` passes
    every success-path test yet freezes the whole expiry subsystem mid-fault;
    a guard that catches the fault and falls through to the writer would sweep
    on no evidence at all. Catches: try/except around 43-45, or reordering
    the write ahead of the guard. The read context is still released."""
    swap_rows(monkeypatch, raise_exc=RuntimeError('database is locked (synthetic)'))
    db = FakeDb()
    ex = Expiry(db, actor='a')
    ex.on_wake = lambda: db.log.append('wake')
    with pytest.raises(RuntimeError):
        ex.pass_once()
    assert db.writer.calls == []
    assert db.log == ['enter:conn-1', 'exit:conn-1']    # closed, no wake, no write


# ── boundaries: the clock every comparison of this worker stands or falls on ─

def test_clock_move_between_pending_and_pass(monkeypatch):
    """worker.py:26,28,43-45 — each call samples `self.clock()` afresh, so an
    NTP step (or a slow loop) between `pending()` and `pass_once()` re-decides
    the work instead of honouring a stale instant. Row expires between two
    samples: not due at the early one (no count, no write), due at the late
    one (real submission, changed True), then stepped back under the expiry —
    the very next `pass_once()` must answer `{'changed': False}` with zero new
    submissions, because writing on the stale sample would sweep a row the
    current clock does not call due. Catches: caching `now` at __init__ or at
    first use, in either direction. Closes probe 10 of the card."""
    expires = '2024-06-01T12:00:00.000Z'
    early, late = '2024-06-01T11:59:59.000Z', '2024-06-01T12:00:01.000Z'
    swap_rows(monkeypatch, fake_row(state='PENDING', kind='action', expires_at=expires))
    box, asks = {'now': early}, []

    def clock():
        asks.append(box['now'])
        return box['now']
    db = FakeDb()
    ex = Expiry(db, actor='a', clock=clock)
    assert ex.pending() == 0
    assert db.writer.calls == []                # not due yet at the first sample
    box['now'] = late
    assert ex.pass_once() == {'changed': True}  # due at the next sample
    assert db.writer.calls == [(authorization.expire_due, {'actor': 'a'})]
    box['now'] = early
    assert ex.pass_once() == {'changed': False} # stepped back: no stale-instant write
    assert len(db.writer.calls) == 1
    assert asks == [early, late, early]         # one fresh sample per call


def test_pass_once_one_read_one_sample_write_after_close(monkeypatch):
    """worker.py:26,43-46 — one pass is one decision: `pass_once()` reads the
    Approval table exactly once, through the conn `db.read()` opened, samples
    the clock exactly once, and submits to the writer only after that read is
    released (log order enter → exit → write). A guard that sampled the clock
    or the table twice could split its own decision — due for the guard, not
    due for the write, or two different conns for the same pass; a write
    inside the open read holds a read lock across a commit, which is exactly
    how a Windows writer deadlock starts (review runs here on Linux and there).
    Catches: duplicate clock/table reads, writing inside the read context."""
    asks = []
    seen = swap_rows(monkeypatch, fake_row(state='PENDING', kind='action'))

    def clock():
        asks.append(1)
        return '2999-01-01T00:00:00.000Z'
    db = FakeDb()
    assert Expiry(db, actor='a', clock=clock).pass_once() == {'changed': True}
    assert len(asks) == 1
    assert seen == [('conn-1', entities.Approval, {})]
    assert db.log == ['enter:conn-1', 'exit:conn-1', 'write']
    assert len(db.writer.calls) == 1


# ── error paths: faults surface, side effects keep their order and limits ───

def test_pending_read_failure_releases_and_propagates(monkeypatch):
    """worker.py:33-34 — when the count's own read fails, `pending()` must
    let the fault through *after* releasing the read connection: swallowed,
    the loop reads a broken table as 'no work' and sleeps its interval;
    leaked, every retry stacks another pinned read transaction (on Windows
    it also blocks the writer). No wake and no write on a fault. Catches:
    try/except around 33-34, or an un-exited read context."""
    swap_rows(monkeypatch, fake_row(), raise_exc=OSError('disk I/O error (synthetic)'))
    db = FakeDb()
    ex = Expiry(db, actor='a')
    ex.on_wake = lambda: db.log.append('wake')
    with pytest.raises(OSError):
        ex.pending()
    assert db.log == ['enter:conn-1', 'exit:conn-1']   # released, and no wake
    assert db.writer.calls == []


def test_failing_wake_callback_is_not_swallowed(monkeypatch):
    """worker.py:36 — `self.on_wake()` is a bare call: a wake that raises
    (the loop's queue is gone) must surface through `pending()`, because a
    pending() that catches it keeps returning the count while silently never
    waking the loop — expiries then wait the full poll interval forever.
    Catches: try/except around the call at 36. The read is still closed and
    nothing is written on the way out."""
    swap_rows(monkeypatch, fake_row(), fake_row())
    db = FakeDb()
    ex = Expiry(db, actor='a')

    def wake():
        db.log.append('wake')
        raise RuntimeError('wake queue gone (synthetic)')
    ex.on_wake = wake
    with pytest.raises(RuntimeError):
        ex.pending()
    assert db.log == ['enter:conn-1', 'exit:conn-1', 'wake']
    assert db.writer.calls == []


def test_wake_fires_once_per_count_not_per_row(monkeypatch):
    """worker.py:35-36 — one wake per poll that found work: with three due
    rows the callback fires exactly once. A per-row wake (`for r in due:
    on_wake()`, or the call moved into `_due`) passes every one-row test yet
    multiplies wakeups by the backlog and spins the loop on big expiries.
    Catches: moving/inverting the single call at 36 into a per-row loop."""
    swap_rows(monkeypatch, fake_row(), fake_row(), fake_row())
    wakes = []
    db = FakeDb()
    ex = Expiry(db, actor='a')
    ex.on_wake = lambda: wakes.append(1)
    assert ex.pending() == 3
    assert wakes == [1]


def test_wake_fires_after_the_read_is_closed(monkeypatch):
    """worker.py:33-36 — the ordering the loop's lockstep depends on: enter →
    exit → wake. The runtime's wake (runtime.py:336) touches loop objects;
    called inside the read transaction it runs while this thread holds the
    DB read lock, and a wake that blocks there deadlocks the writer (the
    wiring is runtime.py:336-337; `WorldLoop.wake` sets the thread event and
    pings the writer's commit counter, runtime.py:343-345). The
    empty second count (nothing due) proves the gate too: enter/exit, and
    still no wake. Catches: the call at 36 moved inside the `with`, or its
    `n and` gate dropped."""
    swap_rows(monkeypatch, fake_row())
    db = FakeDb()
    ex = Expiry(db, actor='a')
    ex.on_wake = lambda: db.log.append('wake')
    assert ex.pending() == 1
    assert db.log == ['enter:conn-1', 'exit:conn-1', 'wake']
    swap_rows(monkeypatch)                        # nothing due now
    assert ex.pending() == 0
    assert db.log == ['enter:conn-1', 'exit:conn-1', 'wake',
                      'enter:conn-2', 'exit:conn-2']


def test_pass_once_never_fires_the_wake(monkeypatch):
    """worker.py:42-47 — the wake belongs to `pending()` alone: a `pass_once()`
    that found work, wrote it, and *also* woke the loop makes every expiry a
    double event, and one that woke after a swallow would pass the wake tests
    above — so the marker is recorded and asserted absent, not raised. The
    writer submission itself must still happen exactly once. Catches: adding
    an `on_wake()` call anywhere in 42-47 (swallowed or not)."""
    swap_rows(monkeypatch, fake_row())
    db = FakeDb()
    ex = Expiry(db, actor='a')
    ex.on_wake = lambda: db.log.append('wake')
    assert ex.pass_once() == {'changed': True}
    assert db.writer.calls == [(authorization.expire_due, {'actor': 'a'})]
    assert 'wake' not in db.log


def test_actor_and_clock_are_keyword_only():
    """worker.py:20-23 — the `*` after `db` is the boot-time contract: the
    runtime and the judge harness construct `Expiry(db, actor=...)` and the
    loop wires it late (worker.py:20, used at runtime.py:506 and
    tests/v1/judge/client.py:282); lose the `*` and a positional
    `Expiry(db, 'system')` silently binds actor — or actor into clock — and
    the worker starts sweeping with the clock as its audit actor. Catches:
    dropping the keyword-only marker at 20."""
    db = FakeDb()
    with pytest.raises(TypeError):
        Expiry(db, 'a')                            # actor must be named
    with pytest.raises(TypeError):
        Expiry(db, 'system', lambda: '2000-01-01T00:00:00.000Z')   # clock too
    ex = Expiry(db, actor='system', clock=lambda: '2000-01-01T00:00:00.000Z')
    assert (ex.db, ex.actor, ex.on_wake) == (db, 'system', None)

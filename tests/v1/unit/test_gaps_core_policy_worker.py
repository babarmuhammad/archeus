"""T-768: the branches of the policy worker (`archeus/core/policy/worker.py`)
that no test in tests/v1 reached — the fail-closed and denial paths first, then
the boundary values, then the error paths.

What is already covered lives elsewhere: tests/v1/integration/test_policy.py
(I-A11) and tests/v1/unit/test_t150_gaps.py (GAP 8) run
`authorization.expire_due` itself, and the rule evaluation order, the default
deny and the unknown-rule-kind paths of the *engine* are the property of
tests/v1/unit/test_policy_units.py and tests/v1/unit/test_gaps_core_policy_rules.py.
`worker.py` contains no rule evaluation at all — what nothing reached is the
`Expiry` worker around it: its own copy of the due filter (worker.py:27-30),
the wake wiring (worker.py:35-36), the write/no-write decision of `pass_once`
(worker.py:43-47), the boot `sweep` (worker.py:39-40), the injected clock
(worker.py:26) and the defaults `WorldLoop` binds to (worker.py:20-23).

The rig is the one tests/v1/unit/test_gaps_core_verification_worker.py built
for its worker: the real worker over a real database of real rows (migrations
0008/0014 give approvals their NOT NULLs and the unique live `action_hash`),
so a sweep that fires really lands in the approval's state machine;
`rows.where` is swapped as in tests/v1/unit/test_t144_checkpoint_consumption.py,
and `authorization.expire_due` is watched through the module attribute the
worker reads at call time — the same seams, no new ones. The unknown kind and
the unknown state no persisted approval can have (entities.py:1845-1850 refuse
them at the real table) are fed through the swapped `rows` — exactly the rows
the filter must leave alone rather than feed to a state machine that would
raise on them. Nothing here needs Windows, a process, the network, or the
clock of the machine beyond one wall-clock reading per test.
"""

import re
from contextlib import nullcontext
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
    `authorization.expire_due` compares against the writer's own `tx.now`, so a
    row the worker calls due must be due to the real clock too, on any machine
    at any time."""
    t = datetime.now(timezone.utc) + timedelta(seconds=offset_s)
    return t.isoformat(timespec='milliseconds').replace('+00:00', 'Z')


def fake_row(state='PENDING', kind='action', expires_at='2000-01-01T00:00:00.000Z'):
    """A decoded row: `_due` reads exactly these attributes of it."""
    return SimpleNamespace(entity=SimpleNamespace(id='apr_fake', state=state,
                                                  kind=kind, expires_at=expires_at))


class FakeWriter:
    def __init__(self, answer=None):
        self.calls = []
        self.answer = {'expired': ['apr_x']} if answer is None else answer

    def execute(self, command, kwargs):
        self.calls.append((command, kwargs))
        return self.answer


class FakeDb:
    """Only ever handed to a worker whose reads are swapped: `read()` yields a
    named conn so a test can see which conn reached `rows.where`."""

    def __init__(self, writer=None):
        self.reads, self.writer = 0, writer or FakeWriter()

    def read(self):
        self.reads += 1
        return nullcontext('conn-%d' % self.reads)


class Rig:
    """One worker over a real database holding one real mission and plan (the
    FKs 0008 imposes on `approvals`), into which tests drop the approvals a
    sweep would find. One per test: they are all the one ARCHEUS_HOME."""

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

    def approval(self, state='PENDING', kind='action', offset=-3600, expires_at=None):
        """An approval as the sweep finds it, placed as an earlier pass left
        it: the writer's own insert, each row with its event (a mutation
        without an event is rolled back, infra/db/writer.py:442), and a fresh
        `action_hash` because 0008 keeps live ones unique."""
        self._n += 1
        a = entities.Approval(id=ids.new_id('approval'), kind=kind,
                              subject=Ref('plan', self.pid),
                              action_hash='%064x' % self._n, requested_by=REQUESTER,
                              mission_id=self.mid, plan_id=self.pid, state=state,
                              expires_at=stamp(offset) if expires_at is None
                              else expires_at)

        def put(tx, *, actor):
            tx.insert(a, actor=actor)
            tx.append(new_event('approval.requested', Ref('approval', a.id), actor,
                                payload={}, workspace=ids.GLOBAL_WORKSPACE))
        self.db.writer.execute(put, {'actor': self.actor})
        return a

    def expiry(self, clock=None):
        return Expiry(self.db, actor=self.actor, clock=clock or W._now)

    def state_of(self, a):
        with self.db.read() as conn:
            return rows.get(conn, entities.Approval, a.id).entity.state


@pytest.fixture
def rig():
    r = Rig()
    yield r
    r.close()


def swap_rows(monkeypatch, *items):
    """The seam of tests/v1/unit/test_t144_checkpoint_consumption.py: the
    worker's own `rows` object, recording every `where` and answering *items*."""
    seen = []

    def where(conn, cls, **eq):
        seen.append((conn, cls, eq))
        return list(items)
    monkeypatch.setattr(W, 'rows', SimpleNamespace(where=where))
    return seen


def watch_expire(monkeypatch):
    """Record every submission of the command `pass_once` exists to make, and
    run the real one (the worker reads this attribute when it builds the call)."""
    calls, original = [], authorization.expire_due

    def spy(tx, *, actor):
        calls.append(actor)
        return original(tx, actor=actor)
    monkeypatch.setattr(authorization, 'expire_due', spy)
    return calls


# ── the due filter: who the sweep ends, and who it must never touch ──────────

def test_pending_counts_expired_pending_whatever_its_kind(rig):
    """worker.py:29 — the first disjunct `state == 'PENDING'` ignores *kind*:
    narrow it (require kind == 'action' here too) and a PENDING plan or task
    approval is never swept, left decidable forever beside the clock."""
    rig.approval(state='PENDING', kind='action')
    rig.approval(state='PENDING', kind='plan')
    assert rig.expiry().pending() == 2


def test_pending_ends_approved_action_approvals_but_never_approved_plan_or_task(rig):
    """worker.py:30 — `(state == 'APPROVED' and kind == 'action')`: drop the
    kind guard and approved plan/task approvals expire (D8 broken); drop the
    whole conjunct and the approved action approval — the one that really must
    end — is left covering its action forever."""
    a, p, t = (rig.approval(state='APPROVED', kind=kind)
               for kind in ('action', 'plan', 'task'))
    assert rig.expiry().pending() == 1
    assert rig.expiry().pass_once() == {'changed': True}
    assert (rig.state_of(a), rig.state_of(p), rig.state_of(t)) == \
        ('EXPIRED', 'APPROVED', 'APPROVED')


def test_an_expired_but_finished_approval_is_never_due(rig):
    """worker.py:29-30 — the state equalities gate the whole predicate: an
    ENDED approval of action kind (REJECTED, EXPIRED, SUPERSEDED, CONSUMED) is
    not due work. Drop the state guard and the worker submits a sweep for
    ended rows on every poll, and one for a state whose machine has no
    `ttl_elapsed` edge would abort `pass_once` inside the writer."""
    for s in ('REJECTED', 'EXPIRED', 'SUPERSEDED', 'CONSUMED'):
        rig.approval(state=s, kind='action')
    assert rig.expiry().pending() == 0
    assert rig.expiry().pass_once() == {'changed': False}


def test_an_unknown_kind_or_state_is_left_alone(monkeypatch):
    """worker.py:29-30 — a row nobody can persist (kind 'widget', state
    'FROBNICATE'; entities.py:1845-1850 refuses both at the real table) must be
    *not due*, never swept: an unrecognised value lands on the safe side here,
    and feeding one to `expire_due` would abort the writer transaction on a
    state machine with no edge from it. A PENDING row of kind 'route' — due by
    the first disjunct — is the control that the filter still counts."""
    swap_rows(monkeypatch, fake_row(state='APPROVED', kind='widget'),
              fake_row(state='FROBNICATE', kind='action'),
              fake_row(state='PENDING', kind='route'))
    db = FakeDb()
    assert Expiry(db, actor='a').pending() == 1
    swap_rows(monkeypatch, fake_row(state='APPROVED', kind='widget'),
              fake_row(state='FROBNICATE', kind='action'))
    assert Expiry(db, actor='a').pending() == 0
    assert Expiry(db, actor='a').pass_once() == {'changed': False}
    assert db.writer.calls == []          # and it wrote nothing on the way


def test_the_filter_reads_the_approval_table_through_the_read_connection(monkeypatch):
    """worker.py:27 — `rows.where(conn, entities.Approval)`, once per count, on
    the conn the `with self.db.read()` opened: pointed at another entity, or
    handed another conn, the worker sweeps the wrong table in peace."""
    seen = swap_rows(monkeypatch)
    Expiry(FakeDb(), actor='a').pending()
    assert seen == [('conn-1', entities.Approval, {})]


# ── boundary values: the clock and the equality of `<=` ──────────────────────

def test_expiry_at_exactly_now_is_due(rig):
    """worker.py:28 — `expires_at <= now`: at the exact millisecond the clock
    reads, the approval is due. Change `<=` to `<` and every approval lives a
    poll longer than its expiry — the fail-open window this worker exists to
    close (`pass_once` then reports False and the row stays PENDING)."""
    now = W._now()
    a = rig.approval(state='PENDING', kind='plan', expires_at=now)
    assert rig.expiry(clock=lambda: now).pending() == 1
    assert rig.expiry(clock=lambda: now).pass_once() == {'changed': True}
    assert rig.state_of(a) == 'EXPIRED'


def test_one_millisecond_early_is_not_due(rig):
    """worker.py:28 — one millisecond after the clock's reading is *not* due:
    loosen the comparison (a `now` truncated or rounded the wrong way) and the
    rows on either side of the boundary start answering the same way."""
    now = W._now()
    late = (datetime.strptime(now, '%Y-%m-%dT%H:%M:%S.%fZ')
            + timedelta(milliseconds=1)).isoformat(timespec='milliseconds') + 'Z'
    rig.approval(state='PENDING', kind='action', expires_at=late)
    assert rig.expiry(clock=lambda: now).pending() == 0


def test_the_injected_clock_is_the_only_time_of_the_count(monkeypatch):
    """worker.py:26 — `now = self.clock()`, once per `_due`, and *nothing else*
    decides: a row an hour ahead of the real wall clock is due when the
    injected clock says 2999, and the injected clock is asked exactly once."""
    asks = []
    far = stamp(3600)
    swap_rows(monkeypatch, fake_row(expires_at=far))

    def clock():
        asks.append(1)
        return '2999-01-01T00:00:00.000Z'
    assert Expiry(FakeDb(), actor='a', clock=clock).pending() == 1
    assert len(asks) == 1


def test_now_is_utc_with_milliseconds_and_z():
    """worker.py:14 — the `Z`/millisecond shape `_now` returns is what every
    `expires_at <= now` string comparison here and in
    `authorization.expire_due` relies on: drop the `.replace` or the
    `timespec` and the comparisons silently become format-dependent."""
    s = W._now()
    assert re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z', s)
    assert '+00:00' not in s


# ── the wake wiring and the write decision ───────────────────────────────────

def test_pending_wakes_the_loop_only_when_there_is_work(rig):
    """worker.py:35-36 — `if n and self.on_wake is not None: self.on_wake()`,
    exactly once per count that found work. Drop the call and the loop sleeps
    a whole poll interval past an expiry; drop the `n and` and it wakes on
    every status() — a hot loop."""
    wakes = []
    ex = rig.expiry()
    ex.on_wake = lambda: wakes.append(1)
    assert ex.pending() == 0 and wakes == []          # no rows at all: no wake
    rig.approval(state='PENDING', kind='action')
    assert ex.pending() == 1 and wakes == [1]         # one wake, exactly once
    assert ex.pending() == 1 and wakes == [1, 1]


def test_pending_counts_fine_with_an_unwired_wake(monkeypatch):
    """worker.py:35 — `self.on_wake is not None`: WorldLoop wires it late
    (runtime.py:331), so a count before the wiring must return n, not raise
    TypeError through the worker thread."""
    swap_rows(monkeypatch, fake_row(), fake_row())
    assert Expiry(FakeDb(), actor='a').pending() == 2


def test_pass_once_submits_the_expiry_command_exactly_once_with_its_actor(monkeypatch):
    """worker.py:46 — `writer.execute(authorization.expire_due, {'actor': ...})`:
    the command identity, the exact kwargs dict and the single submission are
    the whole contract with the writer; swap the command or leak another key
    into the data and this is where it shows."""
    swap_rows(monkeypatch, fake_row())
    db = FakeDb()
    assert Expiry(db, actor='a').pass_once() == {'changed': True}
    assert db.writer.calls == [(authorization.expire_due, {'actor': 'a'})]


def test_a_lost_race_says_unchanged(monkeypatch):
    """worker.py:46-47 — between the read and the write the work can go: an
    empty `expired` must answer `{'changed': False}`, or `WorldLoop` takes a
    pass that changed nothing for one that did (runtime.py:366) and spins."""
    swap_rows(monkeypatch, fake_row())
    db = FakeDb(FakeWriter(answer={'expired': []}))
    assert Expiry(db, actor='a').pass_once() == {'changed': False}
    assert db.writer.calls == [(authorization.expire_due, {'actor': 'a'})]


def test_pass_once_writes_nothing_when_the_filter_finds_no_work(rig, monkeypatch):
    """worker.py:43-45 — the guard is the worker's own filter, not the table:
    a table holding an expired APPROVED *plan* approval and a live PENDING one
    (neither due) must produce zero submissions of `expire_due` — not one
    no-op write per poll, which would wake every other subscriber of the
    commit counter."""
    rig.approval(state='APPROVED', kind='plan')
    rig.approval(state='PENDING', kind='action', offset=3600)
    calls = watch_expire(monkeypatch)
    assert rig.expiry().pass_once() == {'changed': False}
    assert calls == []


def test_pass_once_expires_for_real(rig, monkeypatch):
    """worker.py:46 — and when it does submit, the submission really is
    `expire_due` run with the worker's actor, once, ending exactly the due
    rows: PENDING-action and APPROVED-action to EXPIRED, APPROVED-plan (D8)
    left where it was."""
    a = rig.approval(state='PENDING', kind='action')
    b = rig.approval(state='APPROVED', kind='action')
    p = rig.approval(state='APPROVED', kind='plan')
    calls = watch_expire(monkeypatch)
    assert rig.expiry().pass_once() == {'changed': True}
    assert calls == [rig.actor]                       # once, with the worker's actor
    assert (rig.state_of(a), rig.state_of(b), rig.state_of(p)) == \
        ('EXPIRED', 'EXPIRED', 'APPROVED')


def test_sweep_ends_nothing_and_touches_nothing(rig, monkeypatch):
    """worker.py:39-40 — the boot sweep is the empty list: this worker has no
    startup reconciliation (expiry is judged at every decision anyway), so a
    sweep that read the table or fired the command at boot is wrong code."""
    seen = swap_rows(monkeypatch, fake_row())
    calls = watch_expire(monkeypatch)
    ex = rig.expiry()
    assert ex.sweep() == [] and ex.sweep() == []
    assert seen == [] and calls == []


def test_defaults_after_init():
    """worker.py:20-23 — the defaults `WorldLoop` binds to before the first
    pass: `on_wake = None`, `stopping = lambda: False`, the module clock kept
    as the default: drop one and the wiring at runtime.py:331-332 dies at boot
    instead of at the first interesting moment."""
    db = FakeDb()
    ex = Expiry(db, actor='a')
    assert (ex.db, ex.actor) == (db, 'a')
    assert ex.on_wake is None and ex.stopping() is False
    assert ex.clock is W._now

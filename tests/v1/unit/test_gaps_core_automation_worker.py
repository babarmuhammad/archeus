"""T-738: the highest-risk uncovered branches of the automation worker
(`archeus/core/automation/worker.py`) — the worker loop, its retries and its
gating. Fail-closed and denial paths first, then the boundary values, then the
error paths.

The rig is the one `tests/v1/unit/test_t150_gaps.py` copied from
`tests/v1/integration/test_automation.py`'s Rig over the skeleton's Core: the
real worker over a real database of real rows on the test's own ARCHEUS_HOME,
with the seams the integration tests already use (`monkeypatch` of
`application/automations.py`'s commands, an injected `clock`/`retry_s`, a gated
`writer.execute`) standing in for anything that would leave the process. The
worker's retry timing is driven by its own injected clock, so nothing here
sleeps; a `WriterClosed` is raised as a fake, so no real writer is closed and
nothing is Windows- or POSIX-specific.
"""

from datetime import datetime, timedelta, timezone

import pytest

from archeus.core.application import automations as A, commands
from archeus.core.automation.worker import CONSUMER, MAX_ATTEMPTS, REASON_MAX, Automations
from archeus.core.domain import entities, events
from archeus.core.domain.events import new_event
from archeus.core.domain.values import Ref
from archeus.infra.db import Database, rows
from archeus.infra.db.writer import WriterClosed
from archeus.infra.eventlog import consumers, outbox

FOLLOW = {'title': 'follow up {subject.id}', 'objective': 'look at {event.type} #{event.seq}'}
SEED = {'type': 'mission.created', 'where': {'title': 'seed'}}
EVERY = {'kind': 'schedule', 'every': '1m'}
QUARANTINED = 'quarantined: '
T0 = datetime(2026, 10, 21, 9, 0, tzinfo=timezone.utc)


class Rig:
    """One Core on the test's ARCHEUS_HOME (test_t150_gaps.py's Rig, itself the
    integration Rig of test_automation.py): the real writer, the real
    principals, real rows. The worker is built per test with an injected clock
    and retry_s, so a retry boundary is set, not waited for."""

    def __init__(self, db):
        reg = lambda kind, scopes: Ref(kind, db.writer.execute(  # noqa: E731
            commands.register_principal, {'kind': kind, 'scopes': scopes})['id'])
        self.db = db
        self.system = reg('system', ('system',))
        self.user = reg('user_device', ('observe', 'control', 'approve', 'admin'))

    def do(self, command, who=None, **kw):
        return self.db.writer.execute(command, dict(kw, actor=who or self.system))

    def auto(self, **kw):
        return Automations(self.db, actor=self.system, **kw)

    def automation(self, trigger=SEED, template=FOLLOW, enable=True, **kw):
        aid = self.do(A.create, who=self.user, name='rule', trigger=trigger,
                      template=template, **kw)['id']
        if enable:
            self.do(A.set_state, who=self.user, automation_id=aid, action='enable')
        return aid

    def seed(self, title='seed'):
        """A `mission.created` the SEED trigger matches (the integration Rig's)."""
        return self.do(commands.create_mission, who=self.user, title=title,
                       objective='o')['id']

    def drain(self, auto):
        for _ in range(50):
            if not auto.pass_once()['changed']:
                return
        raise AssertionError('the automation consumer did not settle')

    def seq_of(self, type_, subject_id):
        with self.db.read() as r:
            return [x[0] for x in r.execute(
                'SELECT seq FROM events WHERE type = ? AND subject_id = ? ORDER BY seq',
                (type_, subject_id))]

    def effects(self):
        """What `consumers.deliver` recorded per delivered event; a held event
        has no row at all."""
        with self.db.read() as r:
            return {x[0]: x[1] for x in r.execute(
                'SELECT event_seq, result FROM consumer_effects WHERE consumer = ?',
                (CONSUMER,))}

    def cursor(self):
        with self.db.read() as r:
            return consumers.cursor(r, CONSUMER)

    def head(self):
        with self.db.read() as r:
            return outbox.head(r)

    def runs(self, aid=None):
        with self.db.read() as r:
            return [x.entity for x in rows.where(r, entities.AutomationRun,
                                                 **({'automation_id': aid} if aid else {}))]

    def made(self):
        with self.db.read() as r:
            return [x.entity for x in rows.where(r, entities.Mission)
                    if x.entity.origin == 'automation']

    def state(self, aid):
        with self.db.read() as r:
            return rows.get(r, entities.Automation, aid).entity

    def enabled(self):
        with self.db.read() as r:
            return A.enabled(r)


@pytest.fixture
def db(archeus_home):
    d = Database.open()
    yield d
    d.close()


@pytest.fixture
def rig(db):
    return Rig(db)


@pytest.fixture
def frozen(monkeypatch):
    """Core's one clock (test_schedule_triggers.py's fixture): what `now` is,
    so a schedule is due without waiting for anything."""
    now = [T0.isoformat(timespec='milliseconds').replace('+00:00', 'Z')]
    monkeypatch.setattr(events, 'now_iso', lambda: now[0])

    def at(minutes):
        now[0] = (T0 + timedelta(minutes=minutes)).isoformat(
            timespec='milliseconds').replace('+00:00', 'Z')
    return at


def _gated_writer(rig, monkeypatch, target, raising):
    """A writer seam that raises for one command (by identity) and passes
    everything else through untouched: a fault of the writer itself, as a
    closing Core makes it, without closing anything."""
    real = rig.db.writer.execute
    on = [True, target]

    def gated(command, kwargs=None, **kw):
        if on[0] and command is on[1]:
            raise raising
        return real(command, kwargs, **kw)
    monkeypatch.setattr(rig.db.writer, 'execute', gated)
    return on


# ── fail-closed and denial paths first ───────────────────────────────────────

def test_w1_writer_closed_mid_reaction_is_reraised_and_costs_no_attempt(rig, monkeypatch):
    """worker.py:130-131 `except WriterClosed: raise`. A closing Core is not the
    event's fault: no attempt is counted, nothing is held, nothing is recorded,
    and a later Core delivers the very same event."""
    rig.automation()
    mid = rig.seed()
    (seq,) = rig.seq_of('mission.created', mid)
    on = _gated_writer(rig, monkeypatch, A.react, WriterClosed('core is stopping'))
    auto = rig.auto(retry_s=0)
    with pytest.raises(WriterClosed):
        auto.pass_once()
    assert auto.retrying == {}                      # not a fault: no attempt consumed
    assert auto.detail() == {'retrying': {}, 'quarantined': 0}
    assert seq not in rig.effects()                 # no effect row, not even 'quarantined:'
    assert rig.cursor() < seq                       # the cursor stays behind the event
    on[0] = False                                   # a later Core, the same log
    rig.drain(auto)
    assert rig.cursor() >= seq and len(rig.runs()) == 1
    assert rig.effects()[seq] == rig.runs()[0].id   # delivered exactly once, cleanly


def test_w2_writer_closed_on_a_claim_is_reraised_and_quarantines_nothing(rig, monkeypatch,
                                                                         frozen):
    """worker.py:97-98 `except WriterClosed: raise` in `_fire_due`. A closing
    Core must not spend a schedule's attempts or fault it: WriterClosed is a
    RuntimeError, so a worker that lost this arm would hold, and after a few
    passes quarantine, the schedule on the way out of a clean stop."""
    aid = rig.automation(trigger=EVERY)
    frozen(60)                                      # its time has come
    _gated_writer(rig, monkeypatch, A.fire_due, WriterClosed('core is stopping'))
    auto = rig.auto(retry_s=0)
    with pytest.raises(WriterClosed):
        auto.pass_once()
    assert auto.schedules_held == {} and auto.schedule_faults == {}
    assert rig.seq_of('automation.schedule_due', aid) == []    # nothing claimed
    assert rig.effects() == {}                      # the pass wrote nothing


def test_w3_a_held_event_holds_the_handler_not_the_attempts(rig, monkeypatch):
    """worker.py:123-125 (`raise consumers.Hold` before the handler) and 124's
    strict `<`: while a held event's time has not come, its re-delivery must
    neither reach `A.react` nor count another attempt; at the exact
    `not_before` its time has come and the counting resumes from the held
    attempts (worker.py:133)."""
    rig.automation()
    mid = rig.seed()
    (seq,) = rig.seq_of('mission.created', mid)
    seen = []

    def failing(tx, *, actor, seq):
        seen.append(seq)
        raise RuntimeError('boom')
    monkeypatch.setattr(A, 'react', failing)
    t = [0.0]
    auto = rig.auto(clock=lambda: t[0], retry_s=100.0)
    auto.pass_once()                                # setup events, then the hold
    assert seen == [seq] and auto.retrying == {seq: (1, 100.0)}
    assert auto.pass_once() == {'changed': False}   # redelivered: the gate answers
    assert seen == [seq]                            # the handler was never reached
    assert auto.retrying == {seq: (1, 100.0)}       # and no attempt was counted
    assert rig.cursor() < seq and seq not in rig.effects()
    t[0] = 99.999                                   # one thousandth early
    assert auto.pass_once() == {'changed': False}   # `<` is strict: still held
    assert seen == [seq]
    t[0] = 100.0                                    # exactly its time: it is due
    assert auto.pass_once() == {'changed': False}   # failed again: held again
    assert seen == [seq, seq]                       # attempt 2, counted from the held 1
    assert auto.retrying == {seq: (2, 300.0)}


def test_w8_an_event_nothing_matches_costs_one_read_and_no_write(rig, monkeypatch):
    """worker.py:117-120 (`if not A.enabled(conn): return False`, `return bool(
    A.candidates(conn, e))`) and 127-128 (`if not self._relevant(e): return ''`):
    a non-matching event, and any event while nothing is enabled, is consumed
    with an empty effect row and never reaches the writer command at all."""
    aid = rig.automation()
    real_react = A.react
    seen = []

    def spy(tx, *, actor, seq):
        seen.append(seq)
        return real_react(tx, actor=actor, seq=seq)
    monkeypatch.setattr(A, 'react', spy)
    auto = rig.auto(retry_s=0)
    off = rig.seed(title='not seed')                # enabled, but the predicate fails
    rig.drain(auto)                                 # consumed while ENABLED: gated
    mid = rig.seed()                                # the one relevant event
    rig.drain(auto)
    rig.do(A.set_state, who=rig.user, automation_id=aid, action='disable')
    later = rig.seed()                              # matching title, nothing enabled now
    rig.drain(auto)
    assert seen == rig.seq_of('mission.created', mid)      # react ran for the match only
    eff = rig.effects()
    assert eff[rig.seq_of('mission.created', off)[0]] == ''
    assert eff[rig.seq_of('mission.created', later)[0]] == ''
    assert rig.cursor() >= rig.head()
    assert len(rig.runs(aid)) == 1 and len(rig.made()) == 1


def test_w7_a_settling_event_settles_its_run_with_nothing_enabled(rig):
    """worker.py:115-116 (`if A.settles(e): return True`) and 143 (the effect
    line names the settled run): a finished automation mission settles its run
    even after its automation was disabled — the settle must not be gated out,
    or the run sits in MISSION_CREATED forever."""
    aid = rig.automation()
    mid = rig.seed()
    auto = rig.auto(retry_s=0)
    rig.drain(auto)
    (run,) = rig.runs(aid)
    made = run.mission_id                           # the mission the run asked for
    assert run.state == 'MISSION_CREATED'
    assert made != mid and rig.made()[0].id == made  # a follow-up mission, not the seed
    rig.do(A.set_state, who=rig.user, automation_id=aid, action='disable')
    assert rig.enabled() == []                      # the gate would otherwise say False

    def settled(tx, *, actor):
        return tx.append(new_event('mission.state_changed', Ref('mission', made), actor,
                                   payload={'from': 'EXECUTING', 'to': 'COMPLETED'})).seq
    sseq = rig.db.writer.execute(settled, {'actor': rig.user})
    assert auto.pass_once() == {'changed': True}
    assert rig.runs(aid)[0].state == 'SUCCEEDED'    # settled despite nothing enabled
    assert rig.effects()[sseq] == run.id            # the effect row says which run
    assert rig.state(aid).state == 'DISABLED'       # settling re-armed nothing


# ── boundary values ──────────────────────────────────────────────────────────

def test_w4_the_retry_hold_doubles_with_each_attempt(rig, monkeypatch):
    """worker.py:139 (`clock() + retry_s * 2 ** (attempts - 1)`): 10 s after
    attempt 1, 30 (= 10 + 10 * 2) after attempt 2; a redelivery at 5 s and at
    29.99 s neither reaches the handler nor counts, and the third fault ends
    the holding for good."""
    rig.automation()
    mid = rig.seed()
    (seq,) = rig.seq_of('mission.created', mid)
    seen = []

    def failing(tx, *, actor, seq):
        seen.append(seq)
        raise RuntimeError('boom %d' % len(seen))
    monkeypatch.setattr(A, 'react', failing)
    t = [0.0]
    auto = rig.auto(clock=lambda: t[0], retry_s=10.0)
    auto.pass_once()
    assert auto.retrying == {seq: (1, 10.0)}        # the exact first hold
    assert auto.pass_once() == {'changed': False}   # t=0: held
    t[0] = 5.0                                      # inside the first backoff
    assert auto.pass_once() == {'changed': False}
    assert seen == [seq]                            # one call, not one per poll
    t[0] = 10.0                                     # due: attempt 2 faults
    assert auto.pass_once() == {'changed': False}
    assert auto.retrying == {seq: (2, 30.0)}        # the doubled hold
    t[0] = 29.99
    assert auto.pass_once() == {'changed': False}
    assert seen == [seq, seq]
    t[0] = 30.0                                     # the third fault is the last
    assert auto.pass_once() == {'changed': True}    # quarantined: the log moved past it
    assert seen == [seq] * MAX_ATTEMPTS and auto.retrying == {}
    assert rig.effects()[seq] == QUARANTINED + 'RuntimeError: boom %d' % MAX_ATTEMPTS
    assert rig.cursor() >= seq


def test_w5_the_third_failure_quarantines_exactly_once_and_the_log_moves_on(
        rig, monkeypatch):
    """worker.py:134-138: the `attempts >= MAX_ATTEMPTS` boundary (quarantined
    on the third fault, not the second, not the fourth), the `retrying.pop` at
    135 (a quarantine is not also a hold), the one-line REASON_MAX-capped
    effect row of 138, and delivery resuming with later events after it."""
    aid = rig.automation()
    bad = rig.seed()
    (bseq,) = rig.seq_of('mission.created', bad)
    real_react = A.react
    seen = []

    def failing(tx, *, actor, seq):
        seen.append(seq)
        if seq == bseq:
            raise RuntimeError('a fault\n' + 'echoing a payload ' * 100)
        return real_react(tx, actor=actor, seq=seq)
    monkeypatch.setattr(A, 'react', failing)
    t = [0.0]
    auto = rig.auto(clock=lambda: t[0], retry_s=1.0)
    auto.pass_once()                                # attempt 1
    t[0] = 1.0
    assert auto.pass_once() == {'changed': False}   # attempt 2: still a hold
    assert seen.count(bseq) == 2
    assert bseq not in rig.effects()                # not quarantined at two: the boundary
    t[0] = 3.0                                      # its doubled hold (1 + 2) has passed
    assert auto.pass_once() == {'changed': True}
    assert seen.count(bseq) == MAX_ATTEMPTS         # three faults exactly, then never again
    q = rig.effects()[bseq]
    assert q.startswith(QUARANTINED + 'RuntimeError: a fault echoing')
    assert '\n' not in q and len(q) == len(QUARANTINED) + REASON_MAX
    assert auto.retrying == {}                      # popped: held AND quarantined is wrong
    assert rig.cursor() >= bseq
    good = rig.seed()                               # later events still work
    rig.drain(auto)
    (gseq,) = rig.seq_of('mission.created', good)
    (run,) = rig.runs(aid)
    assert rig.effects()[gseq] == run.id and run.state == 'MISSION_CREATED'


def test_w6_a_faulty_schedule_holds_only_itself_and_a_quarantine_is_forever(rig, monkeypatch,
                                                                             frozen):
    """worker.py:90-91 (`if held and self.clock() < held[1]: continue`: the
    healthy schedule still fires while the faulty one is held, and the faulty
    one is not even asked inside its backoff), 108-109 (the schedule's own
    doubling hold) and 101-104 (`MAX_ATTEMPTS <= attempts` -> `(attempts,
    inf)` plus the fault text: a quarantined schedule is never asked again,
    not even long past any backoff)."""
    bad = rig.automation(trigger=EVERY)
    good = rig.automation(trigger=EVERY)
    frozen(60)                                      # both times have come
    real_fire = A.fire_due
    calls = []

    def faulty(tx, *, actor, automation_id):
        calls.append(automation_id)
        if automation_id == bad:
            raise RuntimeError('a claim that always faults')
        return real_fire(tx, actor=actor, automation_id=automation_id)
    monkeypatch.setattr(A, 'fire_due', faulty)
    t = [0.0]
    auto = rig.auto(clock=lambda: t[0], retry_s=4.0)
    assert auto.pass_once() == {'changed': True}    # the healthy one fired anyway
    assert len(rig.runs(good)) == 1 and rig.runs(bad) == []
    assert auto.schedules_held == {bad: (1, 4.0)} and auto.schedule_faults == {}
    t[0] = 3.9                                      # inside its backoff
    assert auto.pass_once() == {'changed': False}
    assert calls == [bad, good]                     # the faulty one was skipped, not asked
    t[0] = 4.0                                      # its own time: attempt 2 faults
    auto.pass_once()
    assert auto.schedules_held == {bad: (2, 12.0)}  # 4 + 4 * 2: the doubling
    t[0] = 12.0                                     # attempt 3 is the last
    auto.pass_once()
    assert [c for c in calls if c == bad] == [bad] * MAX_ATTEMPTS
    held = auto.schedules_held[bad]
    assert held[0] == MAX_ATTEMPTS and held[1] == float('inf')     # forever, not a backoff
    assert auto.quarantined_schedules()[bad] == (
        'quarantined after %d failures: RuntimeError: a claim that always faults'
        % MAX_ATTEMPTS)                             # the API's `waiting` text (103-104)
    t[0] = 10_000.0                                 # long past any backoff
    auto.pass_once()
    assert [c for c in calls if c == bad] == [bad] * MAX_ATTEMPTS  # never asked again
    assert len(rig.runs(good)) == 1                 # and the healthy one was left alone
    assert rig.state(bad).next_run_at is not None   # its time is held, not burned


# ── the loop's own bookkeeping ───────────────────────────────────────────────

def test_w9_pending_wakes_the_thread_only_when_there_is_work(rig):
    """worker.py:58-63: `if n and self.on_wake is not None: self.on_wake()` —
    no wake while the log is empty (a spurious wake parks the polling thread),
    no crash while the hook is still None, one wake per poll that saw work,
    and silence again once it is delivered; worker.py:77: an idle pass reports
    `changed` False, which is what `pump` and the thread loop rest on."""
    rig.automation()
    auto = rig.auto(retry_s=0)
    rig.drain(auto)                                 # the setup events, at creation
    assert auto.pass_once() == {'changed': False}   # idle: nothing to deliver (77)
    assert auto.pending() == 0                      # 61: no work, and no on_wake yet
    wakes = []
    auto.on_wake = lambda: wakes.append(1)
    assert auto.pending() == 0 and wakes == []      # 61 `if n`: no spurious wake
    rig.seed()
    assert auto.pending() == rig.head() - rig.cursor() and auto.pending() > 0
    assert len(wakes) == 2                          # one wake per poll that saw work
    rig.drain(auto)
    assert auto.pending() == 0 and len(wakes) == 2  # delivered: silent again


def test_w10_detail_reports_held_attempts_and_both_quarantine_sources(rig, monkeypatch):
    """worker.py:65-70: `detail` reports each held event's ATTEMPT count (not
    the hold tuple a status line cannot show) and counts a quarantined event
    row AND a held schedule fault together (69-70); worker.py:55-56:
    `quarantined_schedules` hands the API a copy, not the live map."""
    rig.automation()
    bad = rig.seed()
    held = rig.seed()
    (bseq,) = rig.seq_of('mission.created', bad)
    (hseq,) = rig.seq_of('mission.created', held)
    real_react = A.react
    calls = []

    def failing(tx, *, actor, seq):
        calls.append(seq)
        if seq == bseq or (seq == hseq and calls.count(hseq) == 1):
            raise RuntimeError('boom')
        return real_react(tx, actor=actor, seq=seq)
    monkeypatch.setattr(A, 'react', failing)
    t = [0.0]
    auto = rig.auto(clock=lambda: t[0], retry_s=100.0)
    auto.pass_once()                                # bad: attempt 1, the batch holds
    t[0] = 100.0                                    # bad: attempt 2
    auto.pass_once()
    t[0] = 300.0                                    # bad: attempt 3 -> quarantined,
    auto.pass_once()                                # so the batch reaches held: held (1)
    assert calls.count(bseq) == MAX_ATTEMPTS and calls.count(hseq) == 1
    assert auto.retrying == {hseq: (1, 400.0)}      # held on its own not-before
    assert auto.detail() == {'retrying': {hseq: 1}, 'quarantined': 1}
    # attempts only: an int, not the (1, 400.0) the thread holds internally
    auto.schedule_faults['sched_x'] = 'quarantined after 3 failures: RuntimeError: x'
    assert auto.detail()['quarantined'] == 2        # the DB row and the fault both count
    copy = auto.quarantined_schedules()
    copy['sched_y'] = 'written through the API'
    assert 'sched_y' not in auto.schedule_faults    # 55-56: the map is not the worker's


def test_w11_sweep_is_part_of_the_loop_contract(rig):
    """worker.py:72-73: the thread calls `sweep()` every poll; for this
    consumer it is the empty list (its holds and quarantines live in `detail`
    and in its own retry maps, not in a sweep)."""
    auto = rig.auto(retry_s=0)
    assert auto.sweep() == []

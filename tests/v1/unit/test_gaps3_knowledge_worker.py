"""tests/v1/unit/test_gaps3_knowledge_worker.py — T-1132: the highest-risk
uncovered branches of archeus/core/knowledge/worker.py lines 1-147 at HEAD
56d53504, the T-1093 explicit consolidation dispatch and its daily cap
(changed since 0b17a5b4 by a94cc3a7). Existing coverage read first:
tests/v1/unit/test_memory_consolidation.py (the cap, decided through
`_consolidate` directly with a recorder) and
tests/v1/unit/test_gaps_core_knowledge_worker.py (the other four dispatch
arms, once-per-source rules, `_handle`, `pending`, `sweep`, `_rerun_gated`).
No unit test fires a `project.consolidation_requested` event through the
worker, and none fakes a row's `created_at`: the ten branches below live in
`_dispatch`'s consolidation arm (worker.py:85-86) and `_consolidate`
(worker.py:122-131), plus their interaction with `_handle` (70-74) and the
terms rerun (87-88, 144-146).

Final selected branches, fail-closed first, then boundaries, then error
paths, then orderings forced with events (never sleeps) — each cites the
source branch its removal or inversion would flip:

1. worker.py:87-88 with 128 and 144-146 — a gated consolidation is rerun by
   no `provider_terms.decided` answer and spent no part of the day.
2. worker.py:126 — a RouteDecision with `source is None` neither eats the
   day's budget nor breaks the filter.
3. worker.py:124 — a project-sourced decision of another purpose (lesson)
   does not count against the consolidation budget.
4. worker.py:127 — a call that STARTED the previous UTC day cannot hold
   today's explicit ask back.
5. worker.py:127 with 86 — the day is the event's `at` UTC date, not the
   handling clock: a call at 23:59:59.999 caps an ask at 00:00:00.001 of the
   same day and caps nothing one second past midnight.
6. worker.py:86 with 125 — `max_items` from the accepted event is forwarded
   unchanged (1 and CONSOLIDATE_MAX reach the pass as given) and another
   project's dispatch stays independent of this project's cap.
7. worker.py:70-74 with 128 — a pass that breaks after the call is committed
   is recorded as `error: ...`, never as a successful model-bound
   consolidation, and that committed call still consumes the day.
8. worker.py:86 with 70-74 — an ask event whose payload carries no
   `max_items` fails visibly as this event's error effect and spends neither
   a call nor the day's budget.
9. worker.py:123-131 — two asks of one project delivered in one batch
   dispatch at most one model-bound pass: the decision the first handler
   committed is what the second handler reads (seq order, fresh read).
10. worker.py:122-131 — an ask redelivered as-is, or replayed identically,
    after its decision was recorded is a no-op: no second model-bound pass.

Probes 1 and 2 of the card's starting list (another project's decisions, a
non-project source of the same id) are already covered by
test_memory_consolidation.py::test_another_projects_or_another_passs_calls_
do_not_count and are replaced by branches 2 and 3; probe 4 (a future-dated
ask defeating the cap) is not an implementable premise: the daily rule is
documented per UTC day (worker.py:26-29), the event's `at` is stamped by
Core's own clock (events.new_event; K.request_consolidation exposes no `at`
to callers), and test_memory_consolidation.py already settles that a
date-mismatched ask runs; it is replaced by branch 8.

Style follows tests/v1/unit/test_gaps_core_knowledge_worker.py: the real
worker over the real database, outbox, cursor and effects tables, with one
seam faked — the clock (`events.now_iso`, the writer's only OS read, patched
per write through the monkeypatch fixture) and `Passes.consolidate`, which
mints the RouteDecision an own call commits before it runs (ADR-0022). No
thread, no sleep, no model, no subprocess, no network, no DLL, no
environment value read; every row lands under the test's own ARCHEUS_HOME.
"""

import pytest

from archeus.core.application import calls as C
from archeus.core.application import knowledge as K
from archeus.core.domain import entities, ids
from archeus.core.domain import events as evmod
from archeus.core.domain.events import new_event
from archeus.core.domain.values import Ref
from archeus.core.knowledge import worker
from archeus.infra.db import Database, rows
from archeus.infra.eventlog import outbox

WS = ids.GLOBAL_WORKSPACE
ASK = 'project.consolidation_requested'
#: one calendar, spelled out: the cap compares these strings and nothing else
DAY1, DAY2 = '2026-09-19', '2026-09-20'
T09, T10, T11 = DAY2 + 'T09:00:00.000Z', DAY2 + 'T10:00:00.000Z', DAY2 + 'T11:00:00.000Z'
OK = {'state': 'ok', 'items': 2}
GATED = {'state': 'gated', 'reason': 'provider terms refused'}
CAP = 'consolidate: the daily cap of %d is reached' % worker.CONSOLIDATIONS_PER_DAY


class _Passes:
    """The one seam where a pass leaves the process. `consolidate` records
    exactly what the worker asked for and, when `keep`, mints the RouteDecision
    the real `OwnCalls` commits before binding a model (ADR-0022) — the row the
    daily cap reads. `boom` breaks the pass AFTER that commit, as an adapter
    that dies mid-call does; `outcome` is what the committed call carries."""

    def __init__(self, rig, *, keep=False, outcome=OK, boom=False):
        self.rig, self.keep, self.outcome, self.boom = rig, keep, outcome, boom

    def consolidate(self, project_id, max_items):
        self.rig.asked.append(('consolidate', (project_id, max_items)))
        if self.keep:
            self.rig.decision(project_id, outcome=self.outcome, at=self.rig.day)
        if self.boom:
            raise RuntimeError('boom')
        return 'ok'

    def knowledge(self, source_id):
        self.rig.asked.append(('knowledge', source_id))
        return 'ok'

    def decisions(self, meeting_id):
        self.rig.asked.append(('decisions', meeting_id))
        return 'ok'

    def lessons(self, mission_id):
        self.rig.asked.append(('lessons', mission_id))
        return 'ok'


class _Rig:
    """The real knowledge worker over the real database. One rig per test:
    they all share the one ARCHEUS_HOME, so two would read one database."""

    def __init__(self, monkeypatch, *, keep=False, outcome=OK, boom=False):
        self.db = Database.open()
        self.actor = Ref('system', ids.new_id('principal'))
        self.user = Ref('user_device', ids.new_id('principal'))
        self.asked = []
        self.mp = monkeypatch
        self.day = T09                      # the frozen clock's own day
        self.passes = _Passes(self, keep=keep, outcome=outcome, boom=boom)
        self.worker = worker.Knowledge(self.db, actor=self.actor, passes=self.passes)

    # ── the faked clock: a row's created_at is the cap's only OS read ──

    def freeze(self, at):
        self.mp.setattr(evmod, 'now_iso', lambda: at)

    # ── placing the world ──

    def _write(self, *items, events=()):
        def put(tx, *, actor):
            for x in items:
                tx.insert(x, actor=actor)
            for e in events:
                tx.append(e)
        return self.db.writer.execute(put, {'actor': self.actor})

    def project(self, name='repo'):
        pid = ids.new_id('project')
        self._write(entities.Project(id=pid, workspace_id=WS, name=name),
                    events=[new_event('project.created', Ref('project', pid), self.actor,
                                      {'name': name}, workspace=WS, project=pid)])
        return pid

    def decision(self, project_id, *, purpose='knowledge_extraction', source='project',
                 outcome=OK, at=None):
        """A consolidation call's own row, as an earlier pass left it. `at`
        freezes the clock for this write, so `created_at` is exactly that."""
        if at is not None:
            self.freeze(at)
        src = None if source is None else (Ref('project', project_id) if source == 'project'
                                           else source)
        rd = entities.RouteDecision(id=ids.new_id('route_decision'),
                                    subject=Ref('archeus_call', purpose), purpose=purpose,
                                    decided_by='router', result='selected',
                                    workspace_id=WS, project_id=project_id, source=src,
                                    outcome=outcome)
        self._write(rd, events=[new_event('route.decided', Ref('route_decision', rd.id),
                                          self.actor, {'purpose': purpose},
                                          workspace=WS, project=project_id)])
        return rd.id

    def ask(self, project_id, *, max_items=7, at=T10, payload=None):
        """The user's ask, appended as the command does — `at` explicit here,
        which is what the daily rule compares and what the command itself never
        lets a caller set."""
        pl = {'max_items': max_items} if payload is None else payload

        def put(tx):
            return tx.append(new_event(ASK, Ref('project', project_id), self.user, pl,
                                       workspace=WS, project=project_id, at=at)).seq
        return self.db.writer.execute(put, {})

    def terms(self, harness='pi', headless='permitted'):
        return self.db.writer.execute(C.decide_provider_terms, {
            'actor': self.user, 'harness_id': harness, 'headless': headless})

    # ── running and reading back ──

    def deliver(self):
        return self.worker.pass_once()

    def effects(self):
        with self.db.read() as conn:
            return [(r[0], r[1]) for r in conn.execute(
                'SELECT event_seq, result FROM consumer_effects WHERE consumer = ?'
                ' ORDER BY event_seq', (worker.CONSUMER,))]

    def answers(self, type, subject_id):
        with self.db.read() as conn:
            return [r[0] for r in conn.execute(
                'SELECT ef.result FROM consumer_effects ef JOIN events e ON e.seq ='
                ' ef.event_seq WHERE ef.consumer = ? AND e.type = ? AND e.subject_id = ?'
                ' ORDER BY e.seq', (worker.CONSUMER, type, subject_id))]

    def answer(self, type, subject_id):
        got = self.answers(type, subject_id)
        assert got, 'the worker recorded no answer to %s of %s' % (type, subject_id)
        return got[-1]

    def events_of(self, type):
        with self.db.read() as conn:
            return [e for e in outbox.events_after(conn, 0) if e.type == type]

    def decisions_of(self, project_id, purpose='knowledge_extraction'):
        with self.db.read() as conn:
            return [r.entity for r in rows.where(conn, entities.RouteDecision,
                                                 purpose=purpose, project_id=project_id)]

    def outcome_of(self, rd_id):
        with self.db.read() as conn:
            return rows.get(conn, entities.RouteDecision, rd_id).entity.outcome

    def every(self, cls):
        with self.db.read() as conn:
            return [r.entity for r in rows.where(conn, cls)]

    def close(self):
        self.db.close()


@pytest.fixture
def rig(monkeypatch):
    made = []

    def make(**kw):
        assert not made, 'one rig per test: two share the one database'
        made.append(_Rig(monkeypatch, **kw))
        return made[0]
    yield make
    for r in made:
        r.close()


# ── fail-closed: nothing the user never permitted, and nothing that never
#    reached a model, may spend or be spent by the cap ──

def test_a_gated_consolidation_reruns_on_no_terms_answer_and_spends_no_day(rig):
    # worker.py:87-88 with 128 and 144-146 — invert the `headless == 'permitted'`
    # dispatch, or add 'project' to `_rerun_gated`'s runs, and the gated
    # consolidation below is passed with the user's answer never asked for; count
    # a gated row against the cap (drop it from the 128 exemption) and the ask
    # that follows is refused a call that never happened
    r = rig()
    pid = r.project()
    mtg = ids.new_id('meeting')
    r.decision(pid, outcome=GATED, at=T09)                       # a gated consolidation
    r.decision(pid, source=Ref('meeting', mtg), outcome=GATED, at=T09)   # a gated meeting
    r.deliver()                                                  # the placements only
    r.terms(headless='permitted')
    assert r.deliver() == {'changed': True}
    # the terms answer moved the meeting pass and nothing of the project's kind
    assert r.answer('provider_terms.decided', 'pi') == 'rerun %s:ok' % mtg
    assert r.asked == [('decisions', mtg)]
    r.ask(pid, at=T10)
    assert r.deliver() == {'changed': True}
    assert r.answer(ASK, pid) == 'consolidate:ok'                # the budget was never spent
    assert r.asked == [('decisions', mtg), ('consolidate', (pid, 7))]
    assert r.every(entities.KnowledgeItem) == []                 # and nothing was written


def test_a_sourceless_decision_neither_eats_the_day_nor_breaks_the_filter(rig):
    # worker.py:126 `r.entity.source is not None` — drop the guard and the ask
    # below dies on `.kind`, which `_handle` books as `error: AttributeError:` and
    # the day is silently lost to a row that belongs to no source; count
    # sourceless rows instead and the ask is capped by a call nobody made
    r = rig()
    pid = r.project()
    r.decision(pid, source=None, outcome=OK, at=T09)     # same purpose, same project
    r.deliver()
    r.ask(pid, at=T10)
    assert r.deliver() == {'changed': True}
    assert r.answer(ASK, pid) == 'consolidate:ok'
    assert r.asked == [('consolidate', (pid, 7))]
    assert len(r.decisions_of(pid)) == 1                # the worker wrote no decision


def test_a_lesson_call_of_the_same_project_costs_the_consolidation_nothing(rig):
    # worker.py:124 `purpose='knowledge_extraction'` — drop the purpose from the
    # read and this project's lesson pass, a project-sourced decision like the
    # consolidation's, silently caps every consolidation the day it runs
    r = rig()
    pid = r.project()
    r.decision(pid, purpose='lesson', outcome=OK, at=T09)
    r.deliver()
    r.ask(pid, at=T10)
    assert r.deliver() == {'changed': True}
    assert r.answer(ASK, pid) == 'consolidate:ok'
    assert r.asked == [('consolidate', (pid, 7))]


# ── the day: which clock decides, and what counts as inside it ──

def test_a_call_that_started_yesterday_cannot_hold_todays_ask_back(rig):
    # worker.py:127 `r.created_at[:10] == at[:10]` — widen the comparison to
    # `created_at <= at` (or drop it) and yesterday's ok call caps today's ask;
    # the adjacent memory test fakes the ask's `at` (2999) but no test ever faked
    # a row's `created_at` into the day before the ask
    r = rig()
    pid = r.project()
    r.decision(pid, outcome=OK, at=DAY1 + 'T23:59:00.000Z')      # started yesterday
    r.deliver()
    r.ask(pid, at=DAY2 + 'T00:00:00.500Z')                        # asked today
    assert r.deliver() == {'changed': True}
    assert r.answer(ASK, pid) == 'consolidate:ok'
    assert r.asked == [('consolidate', (pid, 7))]
    r.decision(pid, outcome=OK, at=T09)                           # today's own call
    r.ask(pid, at=T10)
    assert r.deliver() == {'changed': True}
    assert r.answer(ASK, pid) == CAP                              # only now the cap bites
    assert r.asked == [('consolidate', (pid, 7))]


def test_the_day_is_the_events_utc_date_never_the_clock_that_handles_it(rig):
    # worker.py:127 with 86 — the rule reads `e.at`, never the handling time:
    # use the delivery clock (or `now`) instead of the event's `at` and both asks
    # below land on one day, so they answer alike — which they must not: the ask
    # inside the call's UTC day is capped even an hour BEFORE it, and one second
    # past midnight runs although both are handled in the same batch, in seq order
    r = rig()
    pid = r.project()
    r.decision(pid, outcome=OK, at=DAY2 + 'T23:59:59.999Z')       # a call at midnight's edge
    r.deliver()
    r.ask(pid, max_items=3, at=DAY2 + 'T00:00:00.001Z')           # same UTC day, earlier
    r.ask(pid, max_items=4, at='2026-09-21T00:00:00.000Z')        # one second over
    assert r.deliver() == {'changed': True}                       # one batch, both events
    assert r.answers(ASK, pid) == [CAP, 'consolidate:ok']
    assert r.asked == [('consolidate', (pid, 4))]


def test_max_items_is_forwarded_unchanged_and_a_neighbour_project_runs_free(rig):
    # worker.py:86 `e.payload['max_items']` with 125 — clamp or drop the
    # forwarding and the seam below is asked for something other than the bounds
    # the user set (CONSOLIDATE_MAX and 1 are the contract's edges); share one
    # cap across projects (or key the read on nothing) and project b's or c's
    # ask of the same day answers with the cap message instead of its own pass
    r = rig(keep=True)
    pa, pb = r.project('a'), r.project('b')
    r.deliver()
    r.ask(pa, max_items=K.CONSOLIDATE_MAX, at=T09)
    r.ask(pb, max_items=1, at=T09)
    assert r.deliver() == {'changed': True}
    assert r.asked == [('consolidate', (pa, K.CONSOLIDATE_MAX)), ('consolidate', (pb, 1))]
    assert r.answer(ASK, pa) == 'consolidate:ok' and r.answer(ASK, pb) == 'consolidate:ok'
    # a second ask on the first project hits ITS cap; a third project of the
    # very same day still gets its own pass
    r.ask(pa, at=T10)
    pc = r.project('c')
    r.ask(pc, at=T11)
    assert r.deliver() == {'changed': True}
    assert r.answer(ASK, pa) == CAP
    assert r.answer(ASK, pc) == 'consolidate:ok'
    assert r.asked == [('consolidate', (pa, K.CONSOLIDATE_MAX)), ('consolidate', (pb, 1)),
                       ('consolidate', (pc, 7))]


# ── error paths: a broken or malformed ask is booked to its event, never to
#    the day as if it had succeeded ──

def test_a_pass_that_breaks_after_the_call_is_committed_is_never_a_success(rig):
    # worker.py:70-74 with 128 — swallow the exception (or return the pass's
    # string before it raises) and the effect below reads as a consolidation that
    # ran; let an errored call's committed row escape the cap (add `None` to the
    # exemption) and the same day binds a second model. The effect of the ask is
    # `error: ...`, its decision stays unended, `sweep` ends it core_restarted,
    # and neither the open nor the failed call ever lets a second pass through
    r = rig(keep=True, outcome=None, boom=True)
    pid = r.project()
    r.deliver()
    r.ask(pid, at=T09)
    assert r.deliver() == {'changed': True}
    err = r.answer(ASK, pid)
    assert err.startswith('error: RuntimeError: boom') and 'consolidate:ok' not in err
    (d,) = r.decisions_of(pid)
    assert d.outcome is None                                      # committed, reached no answer
    r.ask(pid, max_items=8, at=T10)                               # the very same day
    assert r.deliver() == {'changed': True}
    assert r.answer(ASK, pid) == CAP          # the open call spends the day: no second model
    assert r.asked == [('consolidate', (pid, 7))]
    assert r.worker.sweep() == [d.id]                             # core_restarted ends it
    assert r.outcome_of(d.id) == {'state': 'failed', 'reason': 'core_restarted'}
    r.ask(pid, at=T11)
    assert r.deliver() == {'changed': True}
    assert r.answer(ASK, pid) == CAP          # a broken call is not a free re-run either
    assert r.asked == [('consolidate', (pid, 7))]
    assert all('consolidate:ok' not in res for _, res in r.effects())


def test_an_ask_event_without_a_bound_fails_visibly_and_spends_nothing(rig, caplog):
    # worker.py:86 `e.payload['max_items']` with 70-74 — read it as
    # `payload.get('max_items')` and a malformed ask dispatches an unbounded
    # model-bound pass instead of booking `error: KeyError` to its own event;
    # and the error must not eat the day either: the well-formed ask after it
    # still gets the pass
    r = rig()
    pid = r.project()
    r.deliver()
    r.ask(pid, payload={'note': 'no bound came with it'})
    with caplog.at_level('ERROR'):
        assert r.deliver() == {'changed': True}
    assert r.answer(ASK, pid).startswith('error: KeyError')
    assert r.asked == []
    assert [m for m in caplog.messages if 'knowledge pass for event' in m]
    r.ask(pid, max_items=9, at=T10)
    assert r.deliver() == {'changed': True}
    assert r.answer(ASK, pid) == 'consolidate:ok'
    assert r.asked == [('consolidate', (pid, 9))]
    assert r.worker.pending() == 0              # the cursor moved past the broken event


# ── order: what the first handler of a batch committed, the second must see ──

def test_two_asks_of_one_project_in_one_batch_bind_the_model_once(rig):
    # worker.py:123-131 — `_consolidate` opens a FRESH read per event
    # (`with self.db.read()`), so the decision the first handler's pass commits is
    # what caps the second event of the same batch. Decide the batch from one
    # snapshot taken before the first handler ran and both asks dispatch: two
    # model-bound calls, one day, one user who asked twice. Order is the log's
    # (seq), asserted through the effects — never a sleep
    r = rig(keep=True)
    pid = r.project()
    r.deliver()
    r.ask(pid, at=T09)
    r.ask(pid, max_items=8, at=T09)             # identical day, second ask
    assert r.deliver() == {'changed': True}     # one pass_once, both events
    assert r.answers(ASK, pid) == ['consolidate:ok', CAP]
    assert r.asked == [('consolidate', (pid, 7))]
    assert len(r.decisions_of(pid)) == 1        # one call, its own decision row
    assert r.deliver() == {'changed': True}     # drains the decision's own record event
    assert r.worker.pending() == 0


def test_a_replayed_ask_is_a_noop_once_its_decision_was_recorded(rig):
    # worker.py:122-131 — "once" for a consolidation is read from the RouteDecision
    # itself (module docstring): a redelivery of the very event — a crash between
    # the call and the consumer's effect — runs the handler again with the same
    # event, and only the decision row makes it a no-op. Read the cap from the
    # effects table alone, or not at all, and the replay below binds a second
    # model on the user's one ask
    r = rig(keep=True)
    pid = r.project()
    r.deliver()
    r.ask(pid, at=T09)
    assert r.deliver() == {'changed': True}
    assert r.answer(ASK, pid) == 'consolidate:ok'
    e = r.events_of(ASK)[0]                     # the very event, redelivered as-is
    assert r.worker._handle(e) == CAP           # crash-retry of THIS event: no second pass
    r.ask(pid, at=T09)                          # an identical replay into the log
    assert r.deliver() == {'changed': True}
    assert r.answers(ASK, pid) == ['consolidate:ok', CAP]
    assert r.asked == [('consolidate', (pid, 7))]               # one model-bound pass only
    assert len(r.decisions_of(pid)) == 1
    assert r.worker.pending() == 0

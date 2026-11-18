"""T-326: the highest-risk uncovered branches of the P14 command module
(`archeus/core/application/automations.py`) — fail-closed and denial paths, the
schedule claim-and-advance, missed runs, and idempotence.

The style and fixtures are the module's closest tests' (tests/v1/integration/
test_schedule_triggers.py and test_automation.py): the same frozen clock (Core's
one clock is `events.now_iso`, which every transaction's `now` and every event's
`at` read), the same Rig shape and prose test names, the same `_project` and
`_archive` helpers. Unlike those, nothing here runs a worker thread, an engine
or a process: every command is submitted straight to the writer, which is
exactly how the worker runs it — one command, one transaction.
"""

import json
from datetime import datetime, timedelta, timezone

import pytest

from archeus.core.application import automations as A, commands, lifecycle
from archeus.core.automation import matcher as M
from archeus.core.domain import entities, events, ids
from archeus.core.domain.events import new_event
from archeus.core.domain.values import Ref
from archeus.infra.db import Database, rows
from archeus.infra.eventlog import outbox

FOLLOW = {'title': 'follow up {subject.id}', 'objective': 'look at {event.type} #{event.seq}'}
SEED = {'type': 'mission.created', 'where': {'title': 'seed'}}
EVERY = {'kind': 'schedule', 'every': '15m'}

T0 = datetime(2026, 10, 21, 9, 0, tzinfo=timezone.utc)


def iso(minutes):
    return (T0 + timedelta(minutes=minutes)).isoformat(timespec='milliseconds').replace(
        '+00:00', 'Z')


@pytest.fixture
def frozen(monkeypatch):
    now = [iso(0)]

    def at(minutes):
        now[0] = iso(minutes)
    monkeypatch.setattr(events, 'now_iso', lambda: now[0])
    return at


@pytest.fixture
def rig(frozen):
    r = Rig()
    yield r
    r.close()


# ── commands run straight on the writer, as the worker runs them ─────────────

def _project(tx, *, actor, name):
    p = entities.Project(id=ids.new_id('project'), workspace_id=ids.GLOBAL_WORKSPACE, name=name)
    tx.insert(p, actor=actor)
    tx.append(new_event('project.created', Ref('project', p.id), actor, project=p.id))
    return p.id


def _archive(tx, *, actor, project_id, state):
    tx.update(entities.Project, project_id, {'state': state}, actor=actor)
    tx.append(new_event('project.changed', Ref('project', project_id), actor,
                        payload={'state': state}, project=project_id))


def _cancel(tx, *, actor, mission_id):
    row, e = lifecycle.fire(tx, entities.Mission, mission_id, 'cancel', actor=actor,
                            reason='cancelled from Control')
    return e.seq


def _cancel_seq(rig, mission_id):
    return rig.do(_cancel, actor=rig.user, mission_id=mission_id)


def _craft(tx, *, actor, automation_id, **fields):
    """A row written behind the API: `tx.update` takes what validation would have
    refused, with the event the write owes the log."""
    tx.update(entities.Automation, automation_id, fields, actor=actor)
    tx.append(new_event('automation.created', Ref('automation', automation_id), actor,
                        payload={'name': 'crafted', 'fields': sorted(fields)}))
    return automation_id


def _raw(tx, *, actor, type_, subject, payload, project=None):
    """An event appended as a producer would, with whatever envelope."""
    return tx.append(new_event(type_, subject, actor, payload=payload, project=project)).seq


class Rig:
    """test_automation.Rig shrunk to what these commands need: a real archeus.db
    on the test's ARCHEUS_HOME, three devices, and commands submitted directly.
    No engine, no consumer thread, no process."""

    def __init__(self):
        self.db = Database.open()
        self.system = self._principal('system', ('system',))
        self.user = self._principal('user_device', ('observe', 'control', 'approve'))
        self.admin = self._principal('user_device', ('observe', 'control', 'approve', 'admin'))

    def _principal(self, kind, scopes):
        return Ref(kind, self.db.writer.execute(commands.register_principal, {
            'kind': kind, 'scopes': scopes})['id'])

    def do(self, command, **kw):
        return self.db.writer.execute(command, dict(kw, actor=kw.pop('actor', self.user)))

    def automation(self, trigger=SEED, template=FOLLOW, enable=True, **kw):
        aid = self.do(A.create, actor=self.admin, name='rule', trigger=trigger,
                      template=template, **kw)['id']
        if enable:
            self.do(A.set_state, actor=self.admin, automation_id=aid, action='enable')
        return aid

    def seed(self, title='seed', project_id=None):
        return self.do(commands.create_mission, title=title, objective='o',
                       project_id=project_id)

    def react(self, seq):
        return self.do(A.react, actor=self.system, seq=seq)

    def row(self, cls, eid):
        with self.db.read() as r:
            return rows.get(r, cls, eid)

    def run(self, run_id):
        return self.row(entities.AutomationRun, run_id).entity

    def all(self, cls, **eq):
        with self.db.read() as r:
            return [x.entity for x in rows.where(r, cls, **eq)]

    def events(self, type_=None):
        with self.db.read() as r:
            rs = (r.execute('SELECT * FROM events WHERE type = ? ORDER BY seq', (type_,))
                  if type_ else r.execute('SELECT * FROM events ORDER BY seq'))
            return [(x['seq'], x['type'], json.loads(x['payload'])) for x in rs]

    def made(self):
        return [m for m in self.all(entities.Mission) if m.origin == 'automation']

    def close(self):
        self.db.close()


# ── fail-closed and denial paths ──────────────────────────────────────────────

def test_an_automation_written_behind_the_api_never_reacts_to_p14s_own_events(rig):
    # automations.py:131-132 (candidates): every automation.* / automation_run.*
    # event is refused before any trigger is read, whatever the row holds.
    aid = rig.automation()
    crafted = {'kind': 'event', 'type': 'automation.created', 'where': {'name': 'fire'}}
    rig.do(_craft, actor=rig.admin, automation_id=aid, trigger=crafted)
    seq = rig.do(_raw, actor=rig.user, type_='automation.created',
                 subject=Ref('automation', aid), payload={'name': 'fire', 'trigger': crafted})
    with rig.db.read() as conn:
        e = outbox.decode(conn.execute('SELECT * FROM events WHERE seq = ?', (seq,)).fetchone())
        assert rows.get(conn, entities.Automation, aid).entity.trigger == crafted
        assert A.enabled(conn)                                  # the rule is live and armed
        assert M.matches(crafted, e.type, e.payload)[0]         # its trigger WOULD match ...
        assert A.candidates(conn, e) == []                      # ... the prefix guard stops it
    assert rig.react(seq) == {'runs': [], 'settled': None}
    assert rig.all(entities.AutomationRun) == []

    # and the same for the second forbidden prefix, not just the first
    aid2 = rig.automation()
    crafted2 = {'kind': 'event', 'type': 'automation_run.created', 'where': {'n': 1}}
    rig.do(_craft, actor=rig.admin, automation_id=aid2, trigger=crafted2)
    seq2 = rig.do(_raw, actor=rig.user, type_='automation_run.created',
                  subject=Ref('automation_run', ids.new_id('automation_run')),
                  payload={'n': 1})
    with rig.db.read() as conn:
        assert rows.get(conn, entities.Automation, aid2).entity.trigger == crafted2
    assert rig.react(seq2) == {'runs': [], 'settled': None}
    assert rig.all(entities.AutomationRun) == []


def test_reacting_to_an_event_the_log_does_not_hold_claims_nothing_even_twice(rig):
    # automations.py:199-200 (react): an event read back from the log by seq is
    # the only thing this command may act on; a seq with no row is nothing.
    rig.automation()
    rig.seed()                                                  # a live event ... not this one
    ghost = 10 ** 6                                             # a pruned or invented seq
    for _ in range(2):                                          # idempotent: nothing, twice
        assert rig.react(ghost) == {'runs': [], 'settled': None}
    assert rig.all(entities.AutomationRun) == []
    assert [t for _, t, _ in rig.events() if t.startswith('automation_run')] == []


def test_a_run_for_a_project_archived_after_the_event_asks_for_no_mission(rig):
    # automations.py:302-304 (_claim): the project is re-read inside the claim
    # transaction; gone or archived is a recorded condition_false, never a mission.
    pid = rig.do(_project, actor=rig.user, name='to archive')
    aid = rig.automation(project_id=pid)
    m = rig.seed(project_id=pid)
    rig.do(_archive, actor=rig.admin, project_id=pid, state='ARCHIVED')
    (run_id,) = rig.react(m['seq'])['runs']
    run = rig.run(run_id)
    assert (run.state, run.reason_code) == ('SKIPPED', 'condition_false')
    assert run.reason == 'its project is gone or archived'
    assert run.mission_id is None
    assert rig.made() == []
    assert rig.row(entities.Automation, aid).entity.state == 'ENABLED'


def test_no_run_settles_for_a_mission_that_is_not_an_automations_own(rig):
    # automations.py:270-274 (_settle): only the mission an automation itself
    # asked for, naming a run that is still MISSION_CREATED, may ever settle.
    rig.automation()                                            # live, but with no runs at all
    user_m = rig.seed(title='mine')                              # origin api (commands default)
    assert rig.react(user_m['seq']) == {'runs': [], 'settled': None}
    loose = rig.do(commands.create_mission, title='claim', objective='o',
                   origin='automation', origin_ref=None)         # claims an automation ...
    assert rig.react(_cancel_seq(rig, loose['id']))['settled'] is None
    dangling = rig.do(commands.create_mission, title='claim2', objective='o',
                      origin='automation', origin_ref=ids.new_id('automation_run'))
    assert rig.react(_cancel_seq(rig, dangling['id']))['settled'] is None
    assert rig.all(entities.AutomationRun) == []
    assert [t for _, t, _ in rig.events() if t.startswith('automation_run')] == []


def test_a_cancelled_automation_mission_fails_its_run_exactly_once(rig):
    # automations.py:33 + 275-278 (_settle): CANCELLED is a settling move; the run
    # goes FAILED with mission_cancelled once, and a re-delivered settle changes
    # nothing (the 273-274 guard).
    aid = rig.automation()
    m = rig.seed()
    (run_id,) = rig.react(m['seq'])['runs']
    assert rig.run(run_id).state == 'MISSION_CREATED'
    (mid,) = [x.id for x in rig.made()]
    cancel_seq = _cancel_seq(rig, mid)
    assert rig.react(cancel_seq)['settled'] == run_id
    run = rig.run(run_id)
    assert (run.state, run.reason_code) == ('FAILED', 'mission_cancelled')
    assert run.reason == 'its mission %s was cancelled' % mid
    assert rig.row(entities.Automation, aid).entity.state == 'ENABLED'
    # a second delivery of the same settle settles nothing further (§5)
    assert rig.react(cancel_seq) == {'runs': [], 'settled': None}
    settles = [p for _, _, p in rig.events('automation_run.state_changed')
               if p.get('to') == 'FAILED']
    assert len(settles) == 1


# ── schedules, triggers and missed runs (boundaries) ─────────────────────────

def test_a_schedule_with_no_next_time_is_never_due_and_claims_nothing(rig):
    # automations.py:213-214 (due): `a.next_run_at and` — an ENABLED schedule
    # whose time was never set (or was hand-cleared) stays not-due instead of
    # raising inside every worker pass.
    aid = rig.automation(trigger=EVERY)
    assert rig.row(entities.Automation, aid).entity.next_run_at == iso(15)
    rig.do(_craft, actor=rig.admin, automation_id=aid, next_run_at=None)
    with rig.db.read() as conn:
        assert rows.get(conn, entities.Automation, aid).entity.next_run_at is None
        assert A.enabled(conn)                                   # still ENABLED ...
        assert A.due(conn, iso(600)) == []                       # ... yet never due
    assert rig.do(A.fire_due, actor=rig.system, automation_id=aid) == {'runs': []}
    assert rig.all(entities.AutomationRun) == []
    assert rig.events('automation.schedule_due') == []


def test_the_times_a_stopped_core_missed_fire_once_on_the_grid_and_once_only(rig, frozen):
    # automations.py:232-233 (fire_due): an exact multiple of periods missed
    # counts missed exactly and advances to the next slot of the ORIGINAL grid;
    # and the second pass (228-229) finds the time already moved on: one claim,
    # one schedule_due event, whatever the caller retries.
    aid = rig.automation(trigger=EVERY)                         # enabled at iso(0), due iso(15)
    frozen(45)                                                   # exactly two 15m periods missed
    (run_id,) = rig.do(A.fire_due, actor=rig.system, automation_id=aid)['runs']
    run = rig.run(run_id)
    assert (run.state, run.depth) == ('MISSION_CREATED', 1)
    assert run.rationale['schedule'] == {'every': '15m', 'due_at': iso(15), 'missed': 2}
    assert rig.row(entities.Automation, aid).entity.next_run_at == iso(60)
    assert [p for _, _, p in rig.events('automation.schedule_due')] == [
        {'due_at': iso(15), 'every': '15m', 'next_run_at': iso(60), 'missed': 2}]
    assert rig.made()[0].origin_ref == run_id
    # a second pass at the same frozen now claims nothing more (claim-and-advance)
    assert rig.do(A.fire_due, actor=rig.system, automation_id=aid) == {'runs': []}
    assert [r.id for r in rig.all(entities.AutomationRun)] == [run_id]
    assert len(rig.events('automation.schedule_due')) == 1


def test_re_enabling_a_suspended_automation_records_the_user_not_the_policy(rig):
    # automations.py:179-180 (set_state): only a SUSPENDED automation re-enables
    # by user_reenables; a DISABLED one moves by enable_within_policy. Nothing
    # else names who reopened it — the audit trail of the loop guard's recovery.
    aid = rig.automation(rate_limit=1)                           # every claim after one limits
    for _ in range(4):                                           # allowed + 3 rate-limited
        rig.react(rig.seed()['seq'])
    assert rig.row(entities.Automation, aid).entity.state == 'SUSPENDED'
    rig.do(A.set_state, actor=rig.admin, automation_id=aid, action='enable')
    rig.do(A.set_state, actor=rig.admin, automation_id=aid, action='disable')
    rig.do(A.set_state, actor=rig.admin, automation_id=aid, action='enable')
    assert [p['trigger'] for _, _, p in rig.events('automation.state_changed')] == [
        'enable_within_policy', 'loop_guard_tripped', 'user_reenables',
        'disable', 'enable_within_policy']


# ── error paths ───────────────────────────────────────────────────────────────

def test_an_automation_for_an_unregistered_project_is_refused_as_not_found(rig):
    # automations.py:155-156 (create): a rule scoped to a project that was never
    # registered is NotFound, and the transaction that raises writes nothing.
    missing = ids.new_id('project')
    with pytest.raises(lifecycle.NotFound, match=missing):
        rig.do(A.create, actor=rig.admin, name='orphan', trigger=SEED, template=FOLLOW,
               project_id=missing)
    assert rig.all(entities.Automation) == []
    assert rig.events('automation.created') == []
    assert [p for p in rig.all(entities.Principal) if p.kind == 'automation'] == []


def test_the_simulation_marks_the_hits_only_an_execution_could_have_caused(rig):
    # automations.py:501 (simulate): every hit says whether the real claim would
    # have denied it as execution-caused (domain-model §3.3); the reading must
    # not present as fireable what react can only ever skip.
    aid = rig.automation(enable=False)
    s1 = rig.do(_raw, actor=rig.user, type_='mission.created',
                subject=Ref('mission', ids.new_id('mission')), payload={'title': 'seed'})
    agent = Ref('execution', ids.new_id('principal'))
    s2 = rig.do(_raw, actor=agent, type_='mission.created',
                subject=Ref('mission', ids.new_id('mission')), payload={'title': 'seed'})
    with rig.db.read() as conn:
        before = [tuple(r) for r in conn.execute('SELECT * FROM automation_runs')]
        sim = A.simulate(conn, aid, now=iso(0), days=30)
        assert [tuple(r) for r in conn.execute('SELECT * FROM automation_runs')] == before
    assert sim['examined'] == 2
    assert [h['seq'] for h in sim['matched']] == [s1, s2]
    assert [h['denied'] for h in sim['matched']] == [False, True]

"""T-235: the highest-risk GAPs of the T-215 inventory (T-150 authorization,
automations and queries), closed as tests.

The inventory graded every public function of `archeus/core/application/
{authorization,automations,queries}.py` against the two named test files; the
ten GAPs below are its highest-risk list, denial paths first. The setup helpers
are copied from the neighbouring integration tests — `test_automation.py` and
the skeleton's Core (the Rig, SpyPolicy, the writer-command `do`),
`test_graph_query.py` (the raw `put`/row-move writes) and `test_policy.py`
(the tamper) — and every command runs through the real writer on the test's
own ARCHEUS_HOME. Nothing here spawns a process: dispatch asks and records,
and executions are ended as records, exactly as those tests do.

GAP 1   decide: the approve path and the replay
GAP 2   decide: wrong hash, bad decision, stale version
GAP 3   decide: every NotEligible reason
GAP 4   gate_start under each profile
GAP 5   check_dispatch: DENY writes nothing, ASK asks once, covered
GAP 6   evaluate_action: single-use, plan not in force
GAP 7   policy admin is admin-only, rules are never edited
GAP 8   the approval lifetime sweeps
GAP 9   authorization.simulate: bad rules, writes nothing
GAP 10  the schedule half of automations
"""

import json
import os
import sqlite3
from datetime import timedelta

import pytest

from archeus.core import ports
from archeus.core.application import authorization, automations as A, commands, lifecycle, queries, work
from archeus.core.application.authorization import NotEligible, NotPermitted
from archeus.core.automation.worker import Automations
from archeus.core.domain import entities, ids
from archeus.core.domain.events import new_event
from archeus.core.domain.values import Ref
from archeus.core.policy.engine import PolicyEngine
from archeus.infra import paths
from archeus.infra.db import Database, rows

WS = ids.GLOBAL_WORKSPACE
AUTO = {'text': 'the result passes its automatic check', 'check': 'automatic'}
ACCEPT = [{'text': 'it is done', 'check': 'automatic'}]
LOOP = {'title': 'cycle {event.type} #{event.seq}', 'objective': 'run the loop'}
PAST = '2020-01-01T00:00:00.000Z'
FUTURE = '2099-01-01T00:00:00.000Z'
PUSH = {'action_class': 'git_push', 'target': 'origin/main',
        'argv': ['git', 'push', 'origin', 'main']}


def task(key, *classes, **kw):
    return dict({'key': key, 'title': 'Task %s' % key, 'kind': 'code_change',
                 'action_classes': list(classes), 'acceptance': ACCEPT}, **kw)


class SpyPolicy(ports.FixedPolicy):
    """The skeleton's spy: one decision for every action, or per action class
    (`by_class`) — the only way to make `mission.start` ask or deny."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.asked = []

    def evaluate(self, action, ctx):
        self.asked.append((action.action_class, action.target, ctx.get('task_id')))
        return super().evaluate(action, ctx)


class Rig:
    """One Core on the test's ARCHEUS_HOME (test_automation.py's Rig over the
    skeleton's Core): the real writer and the principals every denial names."""

    def __init__(self, db, policy=None):
        reg = lambda kind, scopes: Ref(kind, db.writer.execute(  # noqa: E731
            commands.register_principal, {'kind': kind, 'scopes': scopes})['id'])
        self.db = db
        self.system = reg('system', ('system',))
        self.user = reg('user_device', ('observe', 'control', 'approve', 'admin'))
        self.control = reg('user_device', ('observe', 'control'))
        self.brain = reg('brain', ('propose',))
        self.execution = reg('execution', ('report', 'checkpoint', 'request_approval'))
        self.automation_principal = Ref('automation', db.writer.execute(
            commands.register_principal, {'kind': 'automation',
                                          'scopes': ('create_mission',)})['id'])
        self.policy = policy or PolicyEngine()
        self.missions = commands.Missions(policy=self.policy)
        self.work = work.Work(missions=self.missions,
                              router=ports.FixedCandidateRouter('fake'))
        self.authz = authorization.Authorization(missions=self.missions)

    def do(self, command, who=None, key=None, **kw):
        return self.db.writer.execute(command, dict(kw, actor=who or self.system),
                                      idempotency_key=key)

    def read(self, fn, *a):
        with self.db.read() as conn:
            return fn(conn, *a)

    def mission(self, title='M', **kw):
        mid = self.do(commands.create_mission, who=self.user, title=title, objective='o',
                      success_criteria=[AUTO], **kw)['id']
        for trig in ('start', 'understood'):
            self.do(self.missions.fire, mission_id=mid, trigger=trig, reason='test')
        self.do(self.missions.context_ready, mission_id=mid)
        return mid

    def created(self, title='M', **kw):
        """A mission that stays in CREATED — gate_start's input."""
        return self.do(commands.create_mission, who=self.user, title=title, objective='o',
                       **kw)['id']

    def propose(self, mid, *tasks):
        return self.do(self.work.propose_plan, mission_id=mid,
                       context_package_id=self.m(mid).context_package_id, plan={
            'summary': 'test plan', 'tasks': list(tasks), 'success_criteria': [AUTO]})

    def dispatchable(self, mid):
        """APPROVED -> EXECUTING with its first task READY."""
        self.do(self.missions.fire, mission_id=mid, trigger='dispatch', reason='go')
        self.do(self.work.ready_tasks, mission_id=mid)

    def one(self, cls, **eq):
        got = self.all(cls, **eq)
        assert len(got) == 1, got
        return got[0]

    def all(self, cls, **eq):
        with self.db.read() as r:
            return [x.entity for x in rows.where(r, cls, **eq)]

    def row_of(self, cls, entity_id):
        with self.db.read() as r:
            return rows.get(r, cls, entity_id).entity

    def row_version(self, cls, entity_id):
        with self.db.read() as r:
            return rows.get(r, cls, entity_id).version

    def m(self, mid):
        with self.db.read() as r:
            return rows.get(r, entities.Mission, mid).entity

    def pending(self, mid):
        (a,) = [a for a in self.all(entities.Approval, mission_id=mid) if a.state == 'PENDING']
        return a

    def decide(self, a, decision='approve', who=None, key=None, h=None, **kw):
        return self.do(self.authz.decide, who=who or self.user, key=key, approval_id=a.id,
                       decision=decision, action_hash=h or a.action_hash, **kw)

    def head(self):
        with self.db.read() as r:
            return r.execute('SELECT MAX(seq) FROM events').fetchone()[0]

    def events(self, type_):
        with self.db.read() as r:
            return [e for e in queries.events(r) if e['type'] == type_]

    def rule(self, level, cls, decision, who=None, **kw):
        return self.do(self.authz.create_rule, who=who or self.user, scope_level=level,
                       action_class=cls, decision=decision, **kw)

    def run_task(self, mid, ok=True, attempts=1):
        """Dispatch the mission's READY task and end its executions as records."""
        (t,) = [t for t in self.all(entities.Task, mission_id=mid) if t.state == 'READY']
        out = None
        for _ in range(attempts):
            out = self.do(self.work.dispatch_task, task_id=t.id)
            if out['execution_id'] is None:
                return out
            self.do(self.work.record_spawn, execution_id=out['execution_id'], pid=1,
                    create_time=1.0)
            self.do(self.work.record_exit, execution_id=out['execution_id'],
                    exit_reason='ok' if ok else 'error', exit_code=0 if ok else 1)
        return out

    def automation(self, trigger, enable=True, **kw):
        aid = self.do(A.create, who=self.user, name='rule', trigger=trigger,
                      template=kw.pop('template', LOOP), **kw)['id']
        if enable:
            self.do(A.set_state, who=self.user, automation_id=aid, action='enable')
        return aid

    def put(self, *entities_):
        """Insert rows a phase would have written (test_graph_query.py's put):
        the writer refuses a mutation with no event, so append one."""
        def run(tx, **_):
            for x in entities_:
                tx.insert(x, actor=self.user)
            tx.append(new_event('mission.updated', Ref('mission', ids.new_id('mission')),
                                self.user, payload={}, workspace=WS))
        self.db.writer.execute(run, {})

    def move(self, cls, entity_id, **fields):
        """Set fields a sweep or a restart would find already in the past (an
        expiry, a schedule's `next_run_at`), as the world around Core does."""
        def run(tx, *, actor):
            tx.update(cls, entity_id, dict(fields), actor=actor, bump=False)
            tx.append(new_event('mission.updated', Ref('mission', ids.new_id('mission')),
                                actor, payload={}, workspace=WS))
        self.db.writer.execute(run, {'actor': self.user})


def tamper(db, table_, entity_id, **fields):
    """Write a row's fields around the writer, as corruption or tampering would
    (test_policy.py's `_tamper`): the body JSON, and its column when promoted."""
    from archeus.infra.db import connection
    c = sqlite3.connect(connection.db_path(paths.archeus_home()))
    body = json.loads(c.execute('SELECT body FROM %s WHERE id = ?' % table_,
                                (entity_id,)).fetchone()[0])
    cols = [r[1] for r in c.execute('PRAGMA table_info(%s)' % table_)]
    sets = {}
    for k, v in fields.items():
        body[k] = v
        if k in cols:
            sets[k] = v
    c.execute('UPDATE %s SET body = ? WHERE id = ?' % table_,
              (json.dumps(body, sort_keys=True), entity_id))
    for k, v in sets.items():
        c.execute('UPDATE %s SET %s = ? WHERE id = ?' % (table_, k), (v, entity_id))
    c.commit()
    c.close()


@pytest.fixture
def db(archeus_home):
    d = Database.open()
    yield d
    d.close()


@pytest.fixture
def rig(db):
    return Rig(db)


def _waiting_plan_approval(rig):
    """A mission waiting in APPROVAL_REQUIRED on a `deploy` plan approval."""
    mid = rig.mission()
    rig.propose(mid, task('t1', 'deploy'))
    return mid, rig.pending(mid)


def _asked_task_approval(rig):
    """A mission BLOCKED on a task approval: dispatch asked and nothing covers it."""
    mid = rig.mission()
    rig.propose(mid, task('t1', 'write_repo'))
    rig.dispatchable(mid)
    rig.rule('MISSION', 'write_repo', 'ASK', scope_ref=mid)
    out = rig.run_task(mid)
    assert out['authorization']['outcome'] == 'asked'
    return mid, rig.pending(mid)


# ── GAP 1: decide — the approve path and the replay ──────────────────────────

def test_decide_approves_moves_the_mission_and_the_replay_changes_nothing(rig):
    mid, a = _waiting_plan_approval(rig)
    out = rig.decide(a)
    assert (out['state'], out['changed'], out['decision']) == ('APPROVED', True, 'approve')
    assert out['mission']['state'] == 'APPROVED'
    got = rig.one(entities.Approval, id=a.id)
    assert (got.state, got.decision, got.decided_by) == ('APPROVED', 'approve', rig.user.id)
    assert got.decided_at is not None and got.decided_policy_decision_id is not None
    assert rig.one(entities.Plan, mission_id=mid).state == 'APPROVED'
    assert rig.m(mid).state == 'APPROVED'
    (moved,) = [e for e in rig.events('approval.state_changed')
                if e['subject']['id'] == a.id and e['payload']['to'] == 'APPROVED']
    assert moved['payload']['trigger'] == 'approve'
    head, version = rig.head(), out['version']
    again = rig.decide(a)                                       # the same decision again
    assert (again['changed'], again['state'], again['version']) == (False, 'APPROVED', version)
    assert rig.head() == head                                   # no second event, no second anything
    with pytest.raises(lifecycle.IllegalTrigger):               # a different one cannot follow
        rig.decide(a, 'reject', key='other')
    assert (rig.head(), rig.one(entities.Approval, id=a.id).state) == (head, 'APPROVED')
    assert len([d for d in rig.all(entities.PolicyDecision) if d.outcome == 'approved']) == 1


# ── GAP 2: decide — wrong hash, bad decision, stale version ──────────────────

def test_decide_refuses_a_wrong_hash_and_a_bad_decision_and_writes_nothing(rig):
    mid, a = _waiting_plan_approval(rig)
    head = rig.head()
    for decision in ('approve', 'reject', 'request_changes'):  # the hash binds every answer
        with pytest.raises(lifecycle.GuardFailed, match='different action'):
            rig.decide(a, decision, h='0' * 64)
    with pytest.raises(ValueError, match='approve, reject or request_changes'):
        rig.decide(a, 'accept')
    assert rig.head() == head                                   # a refusal writes nothing
    assert rig.pending(mid).id == a.id and rig.pending(mid).state == 'PENDING'


def test_decide_refuses_a_stale_version_and_a_plan_answer_on_a_task_approval(rig):
    mid, a = _waiting_plan_approval(rig)
    head, version = rig.head(), rig.row_version(entities.Approval, a.id)
    with pytest.raises(lifecycle.VersionConflict):
        rig.decide(a, expected_version=version + 1)
    assert (rig.head(), rig.pending(mid).state) == (head, 'PENDING')
    assert rig.decide(a, expected_version=version)['state'] == 'APPROVED'
    _mid, ta = _asked_task_approval(rig)
    assert ta.kind == 'task'
    head2 = rig.head()
    with pytest.raises(ValueError, match='only a plan approval'):
        rig.decide(ta, 'request_changes')
    assert (rig.head(), rig.pending(_mid).state) == (head2, 'PENDING')


# ── GAP 3: decide — every NotEligible reason, and the view says it too ───────

def _s_superseded(rig, mid, a, monkeypatch):
    rig.do(lambda tx, actor: lifecycle.fire(tx, entities.Plan, a.plan_id, 'superseded',
                                            actor=actor, reason='test'))
    return mid, a


def _s_digest_mismatch(rig, mid, a, monkeypatch):
    tamper(rig.db, 'plans', a.plan_id, digest='f' * 64)
    return mid, a


def _s_task_no_longer_in_force(rig, mid, a, monkeypatch):
    _mid, ta = _asked_task_approval(rig)              # the task branch: the approval's task
    other = rig.mission('other')                      # is pointed at one of another plan
    rig.propose(other, task('tx', 'deploy'))
    tamper(rig.db, 'approvals', ta.id,
           task_id=rig.one(entities.Task, mission_id=other).id)
    return _mid, ta


def _s_not_awaiting(rig, mid, a, monkeypatch):
    def moved(tx, *, actor):                          # the mission stopped waiting on it
        tx.conn.execute("UPDATE missions SET state = 'REPLANNING' WHERE id = ?", (mid,))
    rig.do(moved)
    return mid, a


def _s_stale(rig, mid, a, monkeypatch):               # its context moved under it (I_A10)
    def change(tx, *, actor):
        m = lifecycle.load(tx, entities.Mission, mid).entity
        req = m.requirements + ({'text': 'also this', 'origin': 'explicit'},)
        tx.update(entities.Mission, mid, {'requirements': req}, actor=actor)
        tx.append(new_event('mission.updated', Ref('mission', mid), actor,
                            payload={'fields': ['requirements']}))
    rig.do(change)
    return mid, a


def _s_expired(rig, mid, a, monkeypatch):             # asked after its window had already gone
    monkeypatch.setitem(authorization.TTL, 'plan', timedelta(seconds=-1))
    mid2 = rig.mission()
    rig.propose(mid2, task('t1', 'deploy'))
    return mid2, rig.pending(mid2)


SCENARIOS = {
    'expired': _s_expired,
    'superseded': _s_superseded,
    'digest_mismatch': _s_digest_mismatch,
    'task_no_longer_in_force': _s_task_no_longer_in_force,
    'not_awaiting': _s_not_awaiting,
    'stale': _s_stale,
}


@pytest.mark.parametrize('name', sorted(SCENARIOS))
def test_decide_refuses_each_ineligible_approval_with_its_own_reason(rig, monkeypatch, name):
    if name == 'expired':                              # its expiry is fixed when it is asked
        mid, a = None, None
    else:
        mid, a = _waiting_plan_approval(rig)
    mid, a = SCENARIOS[name](rig, mid, a, monkeypatch)
    why = 'superseded' if name == 'task_no_longer_in_force' else name
    head = rig.head()
    with pytest.raises(NotEligible) as raised:
        rig.decide(a)
    assert raised.value.approval_id == a.id and raised.value.why == why
    if name == 'task_no_longer_in_force':
        assert 'not in the plan in force' in raised.value.detail
    # the read side answers the same why (queries.py's approval view)
    view = rig.read(lambda c: queries.get_approval(c, a.id))
    assert (view['eligible'], view['eligible_why']) == (False, why)
    assert rig.one(entities.Approval, id=a.id).state == 'PENDING'   # left untouched...
    assert rig.head() == head                                       # ...and nothing written


# ── GAP 4: gate_start — the start gate under each profile ────────────────────

def _gate(rig, mid, by_request=False):
    fn = rig.authz.request_start if by_request else rig.authz.gate_start
    return rig.do(fn, who=rig.user, mission_id=mid)


def _start_rows(rig, mid):
    return ([a for a in rig.all(entities.Approval, mission_id=mid) if a.kind == 'start'],
            [d for d in rig.all(entities.PolicyDecision)
             if d.stage == 'start' and d.mission_id == mid])


def test_gate_start_allows_records_once_and_starts_the_mission(db):
    rig = Rig(db, policy=SpyPolicy())
    mid = rig.created(origin='conversation')          # an autonomous user never asks
    rig.do(rig.authz.set_profile, who=rig.user, scope='user', profile='autonomous')
    assert _gate(rig, mid) == {'started': True, 'waiting': None}
    assert [(d.decision, d.outcome) for d in _start_rows(rig, mid)[1]] == [('ALLOW', 'allow')]
    assert _start_rows(rig, mid)[0] == []
    assert rig.m(mid).state == 'UNDERSTANDING'


def test_gate_start_asks_once_and_a_reject_is_the_end_of_an_ordinary_mission(db):
    rig = Rig(db, policy=SpyPolicy(by_class={'mission.start': 'ASK'}))
    mid = rig.created()
    assert _gate(rig, mid) == {'started': False, 'waiting': 'approval_required'}
    _gate(rig, mid)                                    # the live approval guards a second ask
    (a,) = _start_rows(rig, mid)[0]
    assert (a.kind, a.state) == ('start', 'PENDING')
    head = rig.head()
    _gate(rig, mid)
    assert (rig.head(), len(_start_rows(rig, mid)[0])) == (head, 1)
    rig.decide(a, 'reject')                            # the consequences said: cancelled
    assert rig.one(entities.Approval, id=a.id).state == 'REJECTED'
    assert rig.m(mid).state == 'CANCELLED'
    head2 = rig.head()
    assert _gate(rig, mid) == {'started': False, 'waiting': None}
    assert rig.head() == head2                         # a cancelled mission is judged no more


def test_a_chat_mission_reject_leaves_it_idle_declined_and_askable_again(db):
    rig = Rig(db, policy=SpyPolicy())
    mid = rig.created(origin='conversation')           # standard asks before a chat starts
    assert _gate(rig, mid) == {'started': False, 'waiting': 'approval_required'}
    (a,) = _start_rows(rig, mid)[0]
    rig.decide(a, 'reject')                            # Keep as mission
    assert rig.m(mid).state == 'CREATED'               # idle, not cancelled
    head = rig.head()
    assert _gate(rig, mid) == {'started': False, 'waiting': 'declined'}
    assert rig.head() == head                          # a declined start is not re-asked
    assert _gate(rig, mid, by_request=True) == {'started': False,
                                                'waiting': 'approval_required'}
    (live,) = [x for x in _start_rows(rig, mid)[0] if x.state == 'PENDING']
    assert live.id != a.id
    rig.decide(live)                                   # an explicit start, approved, starts it
    assert rig.m(mid).state == 'UNDERSTANDING'


def test_the_careful_profile_asks_before_any_mission_starts(rig):
    rig.do(rig.authz.set_profile, who=rig.user, scope='user', profile='careful')
    mid = rig.created()
    assert _gate(rig, mid) == {'started': False, 'waiting': 'approval_required'}
    (a,) = _start_rows(rig, mid)[0]
    assert (a.kind, a.state) == ('start', 'PENDING')
    assert _start_rows(rig, mid)[1][0].decision == 'ASK'


def test_gate_start_denies_by_waiting_and_writes_nothing(db):
    rig = Rig(db, policy=SpyPolicy(by_class={'mission.start': 'DENY'}))
    mid = rig.created()
    head = rig.head()
    assert _gate(rig, mid) == {'started': False, 'waiting': 'policy_denied'}
    _gate(rig, mid)                                    # judged again on every pass...
    assert rig.head() == head                          # ...recording nothing, asking nothing
    assert _start_rows(rig, mid) == ([], [])
    assert rig.m(mid).state == 'CREATED'


# ── GAP 5: check_dispatch — DENY writes nothing; ASK asks once; covered ───────

def test_check_dispatch_denies_without_writing_a_single_row(rig):
    mid = rig.mission()
    rig.propose(mid, task('t1', 'write_repo'))
    rig.dispatchable(mid)
    rig.rule('USER', 'write_repo', 'DENY')
    (t,) = rig.all(entities.Task)
    head, before = rig.head(), rig.all(entities.PolicyDecision)
    with pytest.raises(work.PolicyDenied):
        rig.do(rig.work.dispatch_task, task_id=t.id)
    assert rig.head() == head                          # P3.5: a DENY at dispatch wrote nothing
    assert rig.all(entities.PolicyDecision) == before
    assert rig.m(mid).state == 'EXECUTING'             # the mission is unmoved
    assert rig.all(entities.Execution) == []


def test_check_dispatch_asks_once_and_an_approval_covers_exactly_its_item(rig):
    mid = rig.mission()
    rig.propose(mid, task('t1', 'write_repo'), task('t2', 'write_repo', depends_on=['t1']))
    rig.dispatchable(mid)
    rig.rule('MISSION', 'write_repo', 'ASK', scope_ref=mid)
    out = rig.run_task(mid)
    assert out['authorization']['outcome'] == 'asked'  # nothing covered it: one ask...
    assert rig.m(mid).state == 'BLOCKED'
    (a,) = [x for x in rig.all(entities.Approval, mission_id=mid) if x.state == 'PENDING']
    t1 = rig.one(entities.Task, key='t1')
    assert (a.kind, a.task_id) == ('task', t1.id)
    assert rig.decide(a)['mission']['state'] == 'EXECUTING'
    out = rig.run_task(mid)                            # ...and the same pass now finds it
    assert out['execution_id'] is not None             # dispatch ran on the approval's word
    assert rig.one(entities.Task, key='t1').state == 'VERIFYING'
    assert any(d.stage == 'dispatch' and d.outcome == 'covered'
               for d in rig.all(entities.PolicyDecision))
    # the approval is exactly t1's: t2, same class under the same plan, must ask itself
    rig.do(rig.work.record_task_verification, task_id=t1.id, verdict='PASSED', verifier='code')
    rig.do(rig.work.ready_tasks, mission_id=mid)
    out = rig.run_task(mid)
    assert out['authorization']['outcome'] == 'asked'
    asked = {x.task_id: x.state for x in rig.all(entities.Approval, kind='task')}
    assert asked == {t1.id: 'APPROVED',
                     rig.one(entities.Task, key='t2').id: 'PENDING'}


def test_check_dispatch_denies_a_tampered_plan_and_blocks_the_mission(rig):
    mid = rig.mission()
    rig.propose(mid, task('t1', 'write_repo'))
    plan = rig.one(entities.Plan, mission_id=mid)
    rig.dispatchable(mid)
    tamper(rig.db, 'plans', plan.id, digest='0' * 64)  # the body no longer matches its digest
    out = rig.run_task(mid)
    assert out['authorization']['why'] == 'digest_mismatch'
    assert rig.m(mid).state == 'BLOCKED' and rig.all(entities.Execution) == []
    (d,) = [x for x in rig.all(entities.PolicyDecision)
            if x.stage == 'dispatch' and x.outcome == 'denied']
    assert 'does not match its recorded digest' in d.reason


# ── GAP 6: evaluate_action — single-use, and a plan no longer in force ───────

def _running_execution(rig):
    mid = rig.mission()
    rig.propose(mid, task('t1', 'write_repo'))
    rig.dispatchable(mid)
    (t,) = rig.all(entities.Task)
    return mid, t, rig.do(rig.work.dispatch_task, task_id=t.id)['execution_id']


def test_an_action_approval_allows_once_and_the_same_action_asks_again(rig):
    _mid, t, eid = _running_execution(rig)
    first = rig.do(rig.authz.evaluate_action, execution_id=eid, action=PUSH)
    assert first['decision'] == 'ASK' and first['approval_id']
    a = rig.one(entities.Approval, id=first['approval_id'])
    assert (a.kind, a.state, a.execution_id) == ('action', 'PENDING', eid)
    rig.decide(a)
    used = rig.do(rig.authz.evaluate_action, execution_id=eid, action=PUSH)
    assert (used['decision'], used['approval_id']) == ('ALLOW', a.id)
    assert rig.one(entities.Approval, id=a.id).state == 'CONSUMED'   # fired action_executed
    (moved,) = [e for e in rig.events('approval.state_changed')
                if e['subject']['id'] == a.id and e['payload']['to'] == 'CONSUMED']
    assert moved['payload']['trigger'] == 'action_executed'
    again = rig.do(rig.authz.evaluate_action, execution_id=eid, action=PUSH)
    assert again['decision'] == 'ASK' and again['approval_id'] != a.id   # single-use (X09)
    # every outcome recorded exactly one decision, and P11's rows were not moved
    assert [d.outcome for d in rig.all(entities.PolicyDecision) if d.stage == 'action'] \
        == ['ask', 'approved', 'allow', 'ask']
    assert rig.one(entities.Execution, id=eid).state == 'INTENT'    # never started as a process
    assert rig.one(entities.Task, id=t.id).state == 'RUNNING'


def test_an_action_of_a_plan_no_longer_in_force_is_denied(rig):
    mid, t, eid = _running_execution(rig)
    asked = rig.do(rig.authz.evaluate_action, execution_id=eid, action=PUSH)
    assert asked['decision'] == 'ASK'
    rig.do(rig.work.record_spawn, execution_id=eid, pid=1, create_time=1.0)
    rig.do(rig.work.record_exit, execution_id=eid, exit_reason='error', exit_code=1)
    rig.run_task(mid, ok=False, attempts=1)            # the second attempt fails too...
    assert rig.do(rig.missions.advance, mission_id=mid)['state'] == 'REPLANNING'
    rig.propose(mid, task('t2', 'write_repo'))         # ...and a v2 replaces the plan
    denied = rig.do(rig.authz.evaluate_action, execution_id=eid, action=PUSH)
    assert denied['decision'] == 'DENY'
    d = rig.one(entities.PolicyDecision, id=denied['policy_decision_id'])
    assert 'not in force' in d.reason
    # the plan its approval waited on is gone with v1 (never left decidable)
    assert rig.one(entities.Approval, id=asked['approval_id']).state == 'SUPERSEDED'


# ── GAP 7: policy admin is admin-only and rules are never edited ─────────────

def test_only_a_user_device_with_admin_writes_rules_or_autonomy(rig):
    mid = rig.mission()
    for who in (rig.control, rig.brain, rig.execution, rig.system, rig.automation_principal):
        with pytest.raises(NotPermitted):
            rig.rule('USER', 'install', 'ASK', who=who)
        with pytest.raises(NotPermitted):
            rig.do(rig.authz.retire_rule, who=who, rule_id=ids.new_id('policy_rule'))
        with pytest.raises(NotPermitted):
            rig.do(rig.authz.set_profile, who=who, scope='mission', mission_id=mid,
                   profile='autonomous')
    assert rig.all(entities.PolicyRule) == []          # D5: nothing was written, autonomy unmoved
    assert rig.m(mid).autonomy_profile is None


def test_a_rule_is_revised_never_edited(rig):
    first = rig.rule('USER', 'install', 'ASK')
    second = rig.do(rig.authz.create_rule, who=rig.user, scope_level='USER',
                    action_class='install', decision='ALLOW', supersedes_rule_id=first['id'])
    assert second['revision'] == 2
    old = rig.one(entities.PolicyRule, id=first['id'])
    assert old.retired_at is not None                  # retired in the same transaction
    assert rig.events('policy_rule.retired')[-1]['payload']['replaced_by'] == second['id']
    out = rig.do(rig.authz.retire_rule, who=rig.user, rule_id=second['id'])
    assert out['retired_at'] is not None
    assert rig.one(entities.PolicyRule, id=second['id']).retired_at is not None


def test_a_retired_rule_cannot_be_revised_or_retired_again(rig):
    first = rig.rule('USER', 'install', 'ASK')
    rig.do(rig.authz.create_rule, who=rig.user, scope_level='USER', action_class='install',
           decision='ALLOW', supersedes_rule_id=first['id'])
    with pytest.raises(lifecycle.IllegalTrigger):      # the retired one is spent for good
        rig.do(rig.authz.create_rule, who=rig.user, scope_level='USER', action_class='install',
               decision='DENY', supersedes_rule_id=first['id'])
    with pytest.raises(lifecycle.IllegalTrigger):
        rig.do(rig.authz.retire_rule, who=rig.user, rule_id=first['id'])


def test_set_profile_answers_autonomy_only_in_the_vocabulary(rig):
    mid = rig.mission()
    with pytest.raises(ValueError, match='a profile is one of'):
        rig.do(rig.authz.set_profile, who=rig.user, scope='user', profile='reckless')
    with pytest.raises(ValueError, match='the user or a mission'):
        rig.do(rig.authz.set_profile, who=rig.user, scope='workspace', profile='careful')
    assert rig.do(rig.authz.set_profile, who=rig.user, scope='user',
                  profile='careful') == {'scope': 'user', 'profile': 'careful'}
    assert rig.one(entities.User).autonomy_profile == 'careful'
    assert rig.events('user.updated')[-1]['payload']['autonomy_profile'] == 'careful'
    assert rig.do(rig.authz.set_profile, who=rig.user, scope='mission', mission_id=mid,
                  profile=None) == {'scope': 'mission', 'mission_id': mid, 'profile': None}
    assert rig.m(mid).autonomy_profile is None         # a mission's own answer may clear


# ── GAP 8: the lifetime sweeps — a dead approval is never left decidable ─────

def _approval(rig, kind, state, expires_at, mission_id, plan_id=None):
    """An approval as a sweep would find it (the states the commands no longer
    leave, reached directly): the writer's own insert, fields and all."""
    a = entities.Approval(id=ids.new_id('approval'), kind=kind,
                          subject=Ref('plan', plan_id or ids.new_id('plan')),
                          action_hash='%064x' % abs(hash((kind, state, expires_at, plan_id))),
                          requested_by=rig.user.id, mission_id=mission_id, plan_id=plan_id,
                          state=state, expires_at=expires_at)
    rig.put(a)
    return a


def test_withdraw_rejects_a_still_pending_approval_as_the_system(rig):
    mid, a = _waiting_plan_approval(rig)
    rig.do(authorization.withdraw, who=rig.system, mission_id=mid, reason='its mission is gone')
    got = rig.one(entities.Approval, id=a.id)
    assert (got.state, got.decision, got.decided_by) == ('REJECTED', 'reject', rig.system.id)
    with pytest.raises(lifecycle.IllegalTrigger):      # never left decidable
        rig.decide(a)


def test_expire_due_takes_pending_and_approved_actions_but_never_an_approved_plan(rig):
    mid = rig.mission()
    pending_expired = _approval(rig, 'plan', 'PENDING', PAST, mid)
    action_expired = _approval(rig, 'action', 'APPROVED', PAST, mid)
    plan_approved = _approval(rig, 'plan', 'APPROVED', PAST, mid)          # D8
    pending_late = _approval(rig, 'task', 'PENDING', FUTURE, mid)
    assert rig.read(authorization.next_expiry) == PAST                     # the minimum due time
    out = rig.do(authorization.expire_due)
    assert sorted(out['expired']) == sorted([pending_expired.id, action_expired.id])
    states = {x.id: rig.one(entities.Approval, id=x.id).state
              for x in (pending_expired, action_expired, plan_approved, pending_late)}
    assert states[pending_expired.id] == 'EXPIRED'
    assert states[action_expired.id] == 'EXPIRED'
    assert states[plan_approved.id] == 'APPROVED'                          # D8: never expires
    assert states[pending_late.id] == 'PENDING'
    assert rig.do(authorization.expire_due)['expired'] == []               # a second sweep, empty
    assert rig.read(authorization.next_expiry) == FUTURE
    for x in (pending_expired, action_expired):                            # decided paths closed
        with pytest.raises(lifecycle.IllegalTrigger):
            rig.decide(rig.one(entities.Approval, id=x.id))


def test_supersede_for_ends_every_live_approval_of_the_replaced_version(rig):
    mid, a = _waiting_plan_approval(rig)
    approved = _approval(rig, 'plan', 'APPROVED', FUTURE, mid, plan_id=a.plan_id)
    rig.do(authorization.supersede_for, plan_id=a.plan_id, replaced_by=2)
    for x in (a, approved):
        assert rig.one(entities.Approval, id=x.id).state == 'SUPERSEDED'
    moved = [e for e in rig.events('approval.state_changed')
             if e['payload'].get('trigger') == 'plan_replaced']
    assert len(moved) == 2
    for x in (a, approved):                              # one transaction, both gone
        assert rig.read(queries.get_approval, x.id) is not None
    with pytest.raises(lifecycle.IllegalTrigger):
        rig.decide(a)


# ── GAP 9: authorization.simulate — a bad rule is the request's own error ────

def _simulate(rig, extra_rules, action=None):
    with rig.db.read() as conn:
        return rig.authz.simulate(conn, now=queries._now(), mission_id=None,
                                  action=action or {'class': 'git_push', 'target': 'origin/x'},
                                  extra_rules=extra_rules)


def test_simulate_answers_under_an_extra_rule_and_writes_nothing(rig):
    assert rig.all(entities.User) == []                # not even an owner exists
    head = rig.head()
    got = _simulate(rig, [{'scope_level': 'USER', 'action_class': 'git_push',
                           'decision': 'DENY'}])        # the owner rule, against a stand-in
    assert (got['decision'], got['simulated']) == ('DENY', True)
    assert got['policy_version'] and rig.head() == head
    assert rig.all(entities.User) == []                 # a simulation writes nothing, ever
    assert rig.all(entities.Approval) == [] and rig.all(entities.PolicyDecision) == []


def test_simulate_refuses_a_malformed_rule_as_the_requests_own_error(rig):
    head = rig.head()
    with pytest.raises(ValueError):                    # a decision outside the vocabulary
        _simulate(rig, [{'scope_level': 'USER', 'action_class': 'git_push',
                         'decision': 'MAYBE'}])
    with pytest.raises(ValueError):                    # a rule that does not name its class
        _simulate(rig, [{'scope_level': 'USER', 'decision': 'ASK'}])
    with pytest.raises(ValueError):                    # an action class that does not exist
        _simulate(rig, [], action={'class': 'launch_missiles', 'target': 'x'})
    assert rig.head() == head and rig.all(entities.User) == []


# ── GAP 10: the schedule half of automations (automations.py, P21 D9) ────────

def _schedule(rig, every='10m', enable=True, **kw):
    return rig.automation({'kind': 'schedule', 'every': every}, enable=enable, **kw)


def _move_due(rig, aid, ago_s):
    rig.move(entities.Automation, aid, next_run_at=A._ago(queries._now(), ago_s))


def test_enabling_a_schedule_arms_it_one_period_ahead_not_at_once(rig):
    aid = _schedule(rig, every='10m', enable=False)
    assert rig.row_of(entities.Automation, aid).next_run_at is None   # DRAFT waits
    rig.do(A.set_state, who=rig.user, automation_id=aid, action='enable')
    armed = rig.row_of(entities.Automation, aid).next_run_at
    assert A._epoch(armed) - A._epoch(queries._now()) == pytest.approx(600, abs=5)
    rig.do(A.set_state, who=rig.user, automation_id=aid, action='disable')
    rig.do(A.set_state, who=rig.user, automation_id=aid, action='enable')
    rearmed = rig.row_of(entities.Automation, aid).next_run_at        # re-armed, one period on
    assert A._epoch(rearmed) - A._epoch(queries._now()) == pytest.approx(600, abs=5)


def test_fire_due_claims_once_advances_one_period_and_no_second_pass_claims_again(rig):
    aid = _schedule(rig, every='10m')
    _move_due(rig, aid, 60)                            # its time came a minute ago
    before = rig.row_of(entities.Automation, aid).next_run_at
    out = rig.do(A.fire_due, who=rig.system, automation_id=aid)
    (run_id,) = out['runs']
    run = rig.one(entities.AutomationRun, id=run_id)
    assert (run.state, run.rationale['schedule']['missed']) == ('MISSION_CREATED', 0)
    moved = rig.row_of(entities.Automation, aid).next_run_at
    assert A._epoch(moved) == A._epoch(before) + 600   # advanced exactly one period...
    assert A._epoch(moved) > A._epoch(queries._now())  # ...past now: claimed once
    assert rig.do(A.fire_due, who=rig.system, automation_id=aid)['runs'] == []
    Automations(rig.db, actor=rig.system, retry_s=0).pass_once()   # a second worker, a restart
    assert len(rig.all(entities.AutomationRun)) == 1
    assert len([m for m in rig.all(entities.Mission) if m.origin == 'automation']) == 1
    assert rig.row_of(entities.Automation, aid).next_run_at == moved


def test_a_held_schedule_stays_due_and_writes_no_run_of_any_kind(rig):
    aid = _schedule(rig, every='10m')
    _move_due(rig, aid, 60)
    before = rig.row_of(entities.Automation, aid).next_run_at
    sentinel = paths.stop_sentinel()                   # Core disarmed: the e-stop holds it
    os.makedirs(os.path.dirname(sentinel), exist_ok=True)
    open(sentinel, 'w').close()
    try:
        assert rig.do(A.fire_due, who=rig.system, automation_id=aid)['runs'] == []
    finally:
        os.remove(sentinel)
    # an archived project holds it too — and its own due time stays where it was
    project = entities.Project(id=ids.new_id('project'), workspace_id=WS, name='gone',
                               state='ACTIVE')
    rig.put(project)
    other = _schedule(rig, every='10m', project_id=project.id)
    _move_due(rig, other, 60)
    rig.move(entities.Project, project.id, state='ARCHIVED')
    assert rig.do(A.fire_due, who=rig.system, automation_id=other)['runs'] == []
    # the worker quarantines a schedule whose claim keeps raising — for its process
    def explode(*a, **kw):
        raise RuntimeError('boom')
    real = A._claim
    A._claim = explode
    w = Automations(rig.db, actor=rig.system, retry_s=0)
    try:
        for _ in range(4):
            w.pass_once()
    finally:
        A._claim = real
    assert w.schedule_faults[aid].startswith('quarantined after 3 failures')
    # nothing above claimed: both times stand where they were, both schedules stay due,
    # and the view says why the quarantined one waits
    assert rig.row_of(entities.Automation, aid).next_run_at == before
    assert rig.row_of(entities.Automation, other).next_run_at is not None
    assert [a.id for a in rig.read(A.due, queries._now())] == [aid, other]
    (held,) = [x for x in rig.read(A.list_automations, w.quarantined_schedules())['automations']
               if x['id'] == aid]
    assert held['waiting'] == w.schedule_faults[aid]


def test_the_times_a_stopped_core_missed_fire_once_together_counted(rig):
    aid = _schedule(rig, every='10m')
    _move_due(rig, aid, 2100)                          # three and a half periods missed
    out = rig.do(A.fire_due, who=rig.system, automation_id=aid)
    (run_id,) = out['runs']
    run = rig.one(entities.AutomationRun, id=run_id)
    assert run.rationale['schedule']['missed'] == 3    # together, and counted
    (due,) = [e for e in rig.events('automation.schedule_due')
              if e['subject']['id'] == aid]
    assert due['payload']['missed'] == 3 and due['payload']['every'] == '10m'
    moved = rig.row_of(entities.Automation, aid).next_run_at
    assert A._epoch(moved) > A._epoch(queries._now())  # one claim, advanced past every one

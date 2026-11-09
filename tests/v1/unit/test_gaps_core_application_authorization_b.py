"""T-705: the highest-risk GAPs still open in `archeus/core/application/
authorization.py` lines 560-1122, closed as tests (the `b` file after
test_t150_gaps.py, whose GAPs 1-8 cover this module's decide/gate/dispatch/
lifetime/admin cores).

The ten GAPs below are the branches of that section no named test reaches:
the fail-closed and denial paths first, then the boundary values, then the
error paths. The setup helpers are copied from `test_t150_gaps.py` — the Rig
over the skeleton's Core (SpyPolicy, the writer-command `do`), its `tamper`
and `move` (from `test_policy.py` / `test_graph_query.py`) — and every
command runs through the real writer on the test's own ARCHEUS_HOME. Nothing
here spawns a process or needs a real OS: devices are registered with the
real `commands.register_device`, executions are ended as records.

GAP 1   _approve: a DENY found at approve time on an ACTION approval (§8.5)
GAP 2   _step_up_valid: a wrong proof, and a local client that gives one
GAP 3   is_paired: Core's own `origin` record, never the declared platform
GAP 4   _awaiting: an action approval of an ended or vanished execution
GAP 5   _awaiting/ineligible: a task hold that is not EXECUTING, a start
        approval of a mission that started anyway
GAP 6   evaluate_action: an approval given without step-up covers nothing
GAP 7   evaluate_action: an APPROVED action approval past its expiry
GAP 8   decide: the replay of a reject, and an answer that changes its mind
GAP 9   _principal: an actor whose principal row does not exist
GAP 10  _scope_exists: a rule whose scope_ref names nothing; simulate on an
        id that names no mission or task
"""

import json
import sqlite3

import pytest

from archeus.core import ports
from archeus.core.application import authorization, commands, lifecycle, queries, work
from archeus.core.application.authorization import NotEligible, NotPermitted
from archeus.core.domain import entities, ids
from archeus.core.domain.values import Ref
from archeus.core.policy.engine import PolicyEngine
from archeus.infra import paths
from archeus.infra.db import Database, rows

WS = ids.GLOBAL_WORKSPACE
AUTO = {'text': 'the result passes its automatic check', 'check': 'automatic'}
ACCEPT = [{'text': 'it is done', 'check': 'automatic'}]
PAST = '2020-01-01T00:00:00.000Z'
PIN = '123456'
PUSH = {'action_class': 'git_push', 'target': 'origin/main',
        'argv': ['git', 'push', 'origin', 'main']}
DEPLOY = {'action_class': 'deploy', 'target': 'staging', 'argv': ['deploy', 'staging']}


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
    """One Core on the test's ARCHEUS_HOME (test_t150_gaps.py's Rig): the real
    writer and the principals every denial names."""

    def __init__(self, db, policy=None):
        reg = lambda kind, scopes: Ref(kind, db.writer.execute(  # noqa: E731
            commands.register_principal, {'kind': kind, 'scopes': scopes})['id'])
        self.db = db
        self.system = reg('system', ('system',))
        self.user = reg('user_device', ('observe', 'control', 'approve', 'admin'))
        self.control = reg('user_device', ('observe', 'control'))
        self.brain = reg('brain', ('propose',))
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

    def m(self, mid):
        with self.db.read() as r:
            return rows.get(r, entities.Mission, mid).entity

    def pending(self, mid):
        (a,) = [a for a in self.all(entities.Approval, mission_id=mid) if a.state == 'PENDING']
        return a

    def decide(self, a, decision='approve', who=None, key=None, h=None, **kw):
        return self.do(self.authz.decide, who=who or self.user, key=key, approval_id=a.id,
                       decision=decision, action_hash=h or a.action_hash, **kw)

    def paired(self, name='browser', platform='web', origin='paired', pin=PIN):
        """A client registered the way P15 registers one (commands.register_device):
        its own principal, Core's own `origin` record, the PIN only as a
        pbkdf2 record (hash_pin runs here, on the test's thread, never in a
        command — exactly as the HTTP thread does it)."""
        out = self.do(commands.register_device, who=self.system, name=name,
                      platform=platform, origin=origin, token_hash='a' * 64,
                      scopes=('observe', 'approve'),
                      pin_hash=None if pin is None else commands.hash_pin(pin))
        return Ref('user_device', out['principal_id'])

    def head(self):
        with self.db.read() as r:
            return r.execute('SELECT MAX(seq) FROM events').fetchone()[0]

    def events(self, type_):
        with self.db.read() as r:
            return [e for e in queries.events(r) if e['type'] == type_]

    def rule(self, level, cls, decision, who=None, **kw):
        return self.do(self.authz.create_rule, who=who or self.user, scope_level=level,
                       action_class=cls, decision=decision, **kw)

    def run_task(self, mid, attempts=1):
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
                    exit_reason='ok', exit_code=0)
        return out

    def end(self, eid):
        """An execution ended as a record: the state _awaiting refuses."""
        self.do(self.work.record_spawn, execution_id=eid, pid=1, create_time=1.0)
        self.do(self.work.record_exit, execution_id=eid, exit_reason='ok', exit_code=0)

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
    """A mission waiting in APPROVAL_REQUIRED on a `deploy` plan approval —
    the engine's ASK, so the approval asks for a step-up too."""
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


def _running_execution(rig):
    """An INTENT execution of a dispatched task — evaluate_action's input."""
    mid = rig.mission()
    rig.propose(mid, task('t1', 'write_repo'))
    rig.dispatchable(mid)
    (t,) = rig.all(entities.Task)
    return mid, t, rig.do(rig.work.dispatch_task, task_id=t.id)['execution_id']


def _asked_action_approval(rig, action=None):
    """One action asked at the action stage, with its execution."""
    _mid, _t, eid = _running_execution(rig)
    out = rig.do(rig.authz.evaluate_action, execution_id=eid, action=action or PUSH)
    assert out['decision'] == 'ASK' and out['approval_id']
    return eid, rig.one(entities.Approval, id=out['approval_id'])


# ── GAP 1: an action the policy DENIEs between ask and answer is never approvable ──

def test_approving_an_action_the_policy_denies_since_is_answered_denied(rig):
    eid, a = _asked_action_approval(rig)
    assert (a.kind, a.state, a.execution_id) == ('action', 'PENDING', eid)
    rig.rule('USER', 'git_push', 'DENY')                # the policy turned under it
    out = rig.decide(a)
    assert (out['state'], out['changed'], out.get('mission')) == ('PENDING', False, None)
    assert out['denied'] and out['denied']['reason']
    d = rig.one(entities.PolicyDecision, id=out['denied']['policy_decision_id'])
    assert (d.decision, d.outcome, d.stage, d.approval_id) == ('DENY', 'denied', 'action', a.id)
    assert 'git_push' in d.reason
    assert rig.one(entities.Approval, id=a.id).state == 'PENDING'    # never APPROVED
    assert not [e for e in rig.events('approval.state_changed')
                if e['subject']['id'] == a.id and e['payload']['to'] == 'APPROVED']
    assert rig.one(entities.Execution, id=eid).state == 'INTENT'     # P11's rows unmoved


# ── GAP 2: step-up is the PIN of every paired client, or the absence of any ───────

def test_a_step_up_approval_with_the_wrong_proof_writes_nothing(rig):
    mid, a = _waiting_plan_approval(rig)
    assert a.step_up
    who = rig.paired()                                  # a paired browser with a PIN
    head = rig.head()
    with pytest.raises(lifecycle.GuardFailed, match='step-up'):
        rig.decide(a, who=who, step_up='000000')
    assert rig.head() == head                           # the record, the move: all rolled back
    assert rig.one(entities.Approval, id=a.id).state == 'PENDING'
    assert rig.m(mid).state == 'APPROVAL_REQUIRED'


def test_a_local_client_that_gives_a_proof_at_all_is_refused(rig):
    mid, a = _waiting_plan_approval(rig)
    head = rig.head()
    with pytest.raises(lifecycle.GuardFailed, match='step-up'):
        rig.decide(a, step_up=PIN)                      # local proves by being local, only
    assert rig.head() == head                            # ...with NO proof offered
    assert rig.one(entities.Approval, id=a.id).state == 'PENDING'


# ── GAP 3: paired is Core's own origin record, never the declared platform ────────

def test_a_paired_browser_answers_the_step_up_with_its_pin(rig):
    mid, a = _waiting_plan_approval(rig)
    who = rig.paired(platform='web', origin='paired')   # `web` is NOT a paired platform
    out = rig.decide(a, who=who, step_up=PIN)            # paired by origin alone
    assert (out['state'], out['decision']) == ('APPROVED', 'approve')
    got = rig.one(entities.Approval, id=a.id)
    assert (got.state, got.decided_by) == ('APPROVED', who.id)
    assert rig.m(mid).state == 'APPROVED'
    (moved,) = [e for e in rig.events('approval.state_changed')
                if e['subject']['id'] == a.id and e['payload']['to'] == 'APPROVED']
    assert moved['payload']['trigger'] == 'approve'


# ── GAP 4: an action approval of a dead execution is never decidable ───────────────

def test_an_action_approval_of_an_ended_execution_cannot_be_decided(rig):
    eid, a = _asked_action_approval(rig)
    rig.end(eid)
    assert rig.one(entities.Execution, id=eid).state == 'ENDED_OK'
    head = rig.head()
    with pytest.raises(NotEligible) as raised:
        rig.decide(a)
    assert raised.value.why == 'not_awaiting'
    assert rig.one(entities.Approval, id=a.id).state == 'PENDING'   # left for withdraw
    assert rig.head() == head                                       # a refusal writes nothing


def test_an_action_approval_whose_execution_row_is_gone_cannot_be_decided(rig):
    _eid, a = _asked_action_approval(rig)
    tamper(rig.db, 'approvals', a.id, execution_id=ids.new_id('execution'))
    head = rig.head()
    with pytest.raises(NotEligible) as raised:
        rig.decide(a)
    assert raised.value.why == 'not_awaiting'
    assert rig.one(entities.Approval, id=a.id).state == 'PENDING'
    assert rig.head() == head


# ── GAP 5: the mission stopped waiting on the approval in two other ways ───────────

def test_a_task_approval_during_a_hold_that_is_not_the_dispatch_is_ineligible(rig):
    mid, a = _asked_task_approval(rig)                  # BLOCKED, held_from EXECUTING
    assert rig.m(mid).held_from == 'EXECUTING'
    tamper(rig.db, 'missions', mid, held_from='REPLANNING')   # blocked for some other reason
    head = rig.head()
    with pytest.raises(NotEligible) as raised:
        rig.decide(a)
    assert raised.value.why == 'not_awaiting'
    assert rig.one(entities.Approval, id=a.id).state == 'PENDING'
    assert rig.head() == head


def test_a_start_approval_of_a_mission_that_started_anyway_is_ineligible(rig):
    rig = Rig(rig.db, policy=SpyPolicy())               # standard: a chat mission asks
    mid = rig.created(origin='conversation')
    assert rig.do(rig.authz.gate_start, who=rig.user, mission_id=mid) \
        == {'started': False, 'waiting': 'approval_required'}
    a = rig.pending(mid)
    assert a.kind == 'start'
    rig.do(rig.missions.fire, mission_id=mid, trigger='start', reason='started elsewhere')
    assert rig.m(mid).state == 'UNDERSTANDING'
    head = rig.head()
    with pytest.raises(NotEligible) as raised:
        rig.decide(a)
    assert raised.value.why == 'not_awaiting'
    assert rig.one(entities.Approval, id=a.id).state == 'PENDING'
    assert rig.head() == head


# ── GAP 6: an approval given without step-up covers a step-up item not at all ─────

def test_an_approval_corrupted_to_drop_its_step_up_never_covers(rig):
    eid, a = _asked_action_approval(rig, action=DEPLOY)  # ASK on deploy: step_up asked for
    assert a.step_up is True
    rig.decide(a)                                        # the local client satisfies it
    assert rig.one(entities.Approval, id=a.id).state == 'APPROVED'
    tamper(rig.db, 'approvals', a.id, step_up=False)     # the record no longer says step-up
    out = rig.do(rig.authz.evaluate_action, execution_id=eid, action=DEPLOY)
    assert out['decision'] == 'ASK'                      # not covered: asked again...
    assert out['approval_id'] == a.id                    # ...for the very same identity
    assert rig.one(entities.Approval, id=a.id).state == 'APPROVED'   # never consumed
    assert not [e for e in rig.events('approval.state_changed')
                if e['subject']['id'] == a.id and e['payload']['to'] == 'CONSUMED']
    assert not [d for d in rig.all(entities.PolicyDecision)
                if d.stage == 'action' and d.outcome == 'allow']


# ── GAP 7: an APPROVED action approval past its expiry is spent at the gate ────────

def test_an_expired_approved_action_approval_is_expired_on_the_spot_and_reasked(rig):
    eid, a = _asked_action_approval(rig)
    rig.decide(a)
    assert rig.one(entities.Approval, id=a.id).state == 'APPROVED'
    tamper(rig.db, 'approvals', a.id, expires_at=PAST)  # the sweep has not run yet
    out = rig.do(rig.authz.evaluate_action, execution_id=eid, action=PUSH)
    assert out['decision'] == 'ASK' and out['approval_id'] != a.id
    got = rig.one(entities.Approval, id=a.id)
    assert got.state == 'EXPIRED'                        # ttl_elapsed fired at the use
    (moved,) = [e for e in rig.events('approval.state_changed')
                if e['subject']['id'] == a.id and e['payload']['to'] == 'EXPIRED']
    assert moved['payload']['trigger'] == 'ttl_elapsed'
    assert rig.one(entities.Approval, id=out['approval_id']).state == 'PENDING'


# ── GAP 8: the replay of a reject is one decision; no answer can change its mind ───

def test_a_rejected_approval_replays_and_another_answer_cannot_follow(rig):
    _mid, a = _waiting_plan_approval(rig)
    first = rig.decide(a, 'reject')
    assert (first['state'], first['decision'], first['changed']) == ('REJECTED', 'reject', True)
    head = rig.head()
    again = rig.decide(a, 'reject')                      # the same answer, another call
    assert (again['changed'], again['state'], again['decision']) == (False, 'REJECTED', 'reject')
    assert rig.head() == head                            # no second event for one decision
    with pytest.raises(lifecycle.IllegalTrigger):        # the same state, NOT the same answer
        rig.decide(a, 'request_changes')                 # ..._DECIDED maps both to REJECTED
    assert (rig.head(), rig.one(entities.Approval, id=a.id).decision) == (head, 'reject')


# ── GAP 9: an actor whose principal row does not exist decides and edits nothing ───

def test_an_actor_whose_principal_row_names_nothing_is_not_a_principal(rig):
    _mid, a = _waiting_plan_approval(rig)
    ghost = Ref('user_device', ids.new_id('principal'))  # a token of a deleted device
    head = rig.head()
    for call in (lambda: rig.decide(a, who=ghost),
                 lambda: rig.rule('USER', 'install', 'ASK', who=ghost),
                 lambda: rig.do(rig.authz.set_profile, who=ghost, scope='user',
                                profile='careful')):
        with pytest.raises(NotPermitted):
            call()
    assert rig.head() == head
    assert rig.one(entities.Approval, id=a.id).state == 'PENDING'
    assert rig.all(entities.PolicyRule) == []
    assert rig.all(entities.User) == []


# ── GAP 10: a rule naming no scope, and a simulation naming no mission or task ─────

def test_a_rule_whose_scope_ref_names_nothing_is_refused_and_writes_nothing(rig):
    mid = rig.mission()
    ok_ws = rig.rule('WORKSPACE', 'install', 'ASK', scope_ref=WS)
    ok_mission = rig.rule('MISSION', 'install', 'ASK', scope_ref=mid)
    head = rig.head()
    with pytest.raises(ValueError, match='names no workspace'):
        rig.rule('WORKSPACE', 'install', 'ASK', scope_ref=ids.new_id('workspace'))
    with pytest.raises(ValueError, match='names no mission'):
        rig.rule('MISSION', 'install', 'ASK', scope_ref=ids.new_id('mission'))
    with pytest.raises(ValueError, match='names no project'):
        rig.rule('PROJECT', 'install', 'ASK', scope_ref=ids.new_id('project'))
    with pytest.raises(ValueError, match='names no task'):
        rig.rule('TASK', 'install', 'ASK', scope_ref=ids.new_id('task'))
    assert rig.head() == head
    assert sorted(x.id for x in rig.all(entities.PolicyRule)) == sorted(
        [ok_ws['id'], ok_mission['id']])


def test_simulate_refuses_ids_that_name_no_mission_or_task(rig):
    mid = rig.mission()
    rig.propose(mid, task('t1', 'write_repo'))
    t1 = rig.one(entities.Task, key='t1')
    head = rig.head()
    with pytest.raises(lifecycle.NotFound):
        rig.read(lambda c: rig.authz.simulate(c, now=queries._now(), mission_id=mid,
                                              action=PUSH, task_id=ids.new_id('task')))
    with pytest.raises(lifecycle.NotFound):
        rig.read(lambda c: rig.authz.simulate(c, now=queries._now(),
                                              mission_id=ids.new_id('mission'), action=PUSH))
    assert rig.head() == head
    # the boundary that does exist: the same action under the task's real context
    got = rig.read(lambda c: rig.authz.simulate(c, now=queries._now(), mission_id=mid,
                                                task_id=t1.id, action=PUSH, stage='action'))
    assert (got['simulated'], got['mission_id']) == (True, mid)

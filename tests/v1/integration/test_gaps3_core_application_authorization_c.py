"""T-1145: closing the highest-risk gaps in `archeus/core/application/authorization.py`
lines 789-1157 — the command half of P9 (`asks_before_start` through `simulate`).

Branches this file adds coverage for, in the order the slice reads:

* `asks_before_start` (~815-822): the mission's own `autonomy_profile` answers
  before the owner's is ever read — both directions, ask and don't.
* `gate_start` (~854-860): a declined start with a live explicit ask still waits
  on the ask instead of answering `declined` forever.
* `withdraw` (~864-870): it ends only the PENDING approvals of the named mission.
* `expire_due` (~873-885) and `next_expiry` (~887-893): expiry at exact equality
  with the sweep's own `now`, and the state/kind filter (a terminal or non-action
  APPROVED row never expires and never wakes the worker early).
* `evaluate_action` (~896-922): an unclassified action judged as its strictest
  class, and the `intact` conjunct of the plan-in-force guard.
* `create_rule` (~954-981): a DENY can never be written unlocked (through the
  command, not just the entity).
* `simulate` / `_simulated_rule` (~1099-1157): simulating a `mission.start`, and
  a USER extra rule matching the real owner's chain.

The card's initial probes, and what became of each:

1. approving a stale route/task — KEPT (`test_a_route_approval_whose_task_stopped_awaiting...`).
2. start declined after a hash — replaced: t150's
   `test_a_chat_mission_reject_leaves_it_idle_declined_and_askable_again` and
   test_chat_start.py's expired-start test already refuse both decide paths;
   this file takes the uncovered composition instead (`declined` vs a live ask).
3. emergency stop blocking gate — replaced: NOT APPLICABLE to this range —
   gate_start judges through `judge_start`, which forces `estop=False`
   (authorization.py:225-233; test_start_confirmation.py pins that an armed
   e-stop never blocks a start), and the e-stop arm records fine
   (test_fix_authorization.py::test_a_start_decision_records_the_e_stop...).
   This file takes the uncovered gate branch (the mission's own profile).
4. withdraw excludes foreign mission — KEPT.
5. expiry equality and terminal state — KEPT.
6. unclassified execution action — KEPT.
7. non-owner rule creation — replaced: t150's
   `test_only_a_user_device_with_admin_writes_rules_or_autonomy` and
   `test_a_rule_can_be_revised...` cover every non-admin create/revise shape
   (with the rollback and no-rule-written assertions); this file takes another
   validation of the same command instead (an unlocked DENY, probe 9's share).
8. missing scope entity — replaced: already covered twice over (test_gaps_core_
   application_authorization_b.py GAP 10 and test_fix_authorization.py's
   parameterized missing-owner/mission/task/project).
9. protected rule retirement — replaced as stated: retirement itself is t150-
   covered (revise retires the old rule, retiring twice refuses); the
   unprotected shape no test reached is `create_rule` writing an unlocked DENY
   — the command refuses, with the owner row it had already seeded rolled back.
10. simulate leaves the DB unchanged — replaced as stated: the writes-nothing
    claim is pinned twice over (test_t150_gaps.py GAP 9, and b.py's GAP 10 for
    a simulated command naming nothing); this file takes the two `simulate`
    branches no test reaches — `mission.start` (a call shape never exercised)
    and a USER extra rule against a real owner's chain.

Same rig as the neighbours: every mutation is a real command through the real
writer, one transaction each, and rows are read back with `rows.where` —
nothing here bypasses the writer's door except the two documented around-it
helpers copied from the neighbours (tamper: corruption; put: rows a phase left).
"""
import hashlib
import json
import sqlite3
from datetime import datetime, timezone

import pytest

from archeus.core.application import authorization, commands, queries, resources, work
from archeus.core.domain import entities, ids
from archeus.core.domain.events import new_event
from archeus.core.domain.values import Ref
from archeus.core.policy.engine import PolicyEngine
from archeus.core.routing.usage import FakeUsageFeed
from archeus.harnesses.fake import FakeHarness
from archeus.harnesses.registry import AdapterRegistry
from archeus.infra import paths                                    # noqa: F401 (tamper's db_path)
from archeus.infra.db import Database, rows
from v1.integration.test_policy import Rig as PolicyRig, task      # the neighbours' rig itself

WS = ids.GLOBAL_WORKSPACE
AUTO = {'text': 'the result passes its automatic check', 'check': 'automatic'}
FUTURE = '2099-01-01T00:00:00+00:00'
PUSH = {'action_class': 'git_push', 'target': 'archeus/repo',
        'argv': ['git', 'push', 'origin', 'archeus/ready']}
READ_ACTION = {'action_class': 'read', 'target': 'repo/README.md',
               'argv': ['cat', 'README.md']}


class Rig(PolicyRig):
    """test_policy's rig plus the two helpers this file's tests start from
    (t150's `created` and `put`, copied as they read there)."""

    def created(self, title='M', **kw):
        """A mission that stays in CREATED — gate_start's and simulate's input."""
        return self.do(commands.create_mission, who=self.user, title=title, objective='o',
                       **kw)['id']

    def dispatchable(self, mid):
        """APPROVED -> EXECUTING with its first task READY."""
        self.do(self.missions.fire, mission_id=mid, trigger='dispatch', reason='go')
        self.do(self.work.ready_tasks, mission_id=mid)

    def task_of(self, mid, key='t1'):
        (t,) = [x for x in self.all(entities.Task, mission_id=mid) if x.key == key]
        return t

    def row_of(self, cls, entity_id):
        with self.db.read() as r:
            return rows.get(r, cls, entity_id).entity

    def read(self, fn, *a):
        with self.db.read() as conn:
            return fn(conn, *a)

    def put(self, *entities_):
        """Insert rows a phase would have written (t150's put): the writer
        refuses a mutation with no event, so append one."""
        def run(tx, **_):
            for x in entities_:
                tx.insert(x, actor=self.user)
            tx.append(new_event('mission.updated', Ref('mission', ids.new_id('mission')),
                                self.user, payload={}, workspace=WS))
        self.db.writer.execute(run, {})


class RouteRig(Rig):
    """test_routing.py's rig: the real router, accounts and a real fallback ask."""

    def __init__(self, db):
        super().__init__(db)
        self.feed = FakeUsageFeed()
        self.registry = AdapterRegistry(self.policy)
        self.registry.register(FakeHarness())
        self.router = resources.ResourceRouter(self.registry, self.feed)
        self.work = work.Work(missions=self.missions, router=self.router)

    def account(self, label, harness_id='fake', auth=True, home_ref=None, **policy):
        a = self.do(resources.register_account, who=self.user, harness_id=harness_id,
                    label=label, auth_kind='api_key', home_ref=home_ref,
                    auth=None if auth is None else {'ok': auth, 'detail': 'probe'})
        if policy:
            self.do(resources.set_resource_policy, who=self.user, account_id=a['id'], **policy)
        return a['id']

    def limited(self):
        """A is highest-priority but saturated; B is the fallback that asks."""
        a = self.account('A', priority=1)
        b = self.account('B', priority=2, fallback='ask')
        self.feed.set(a, '5h', 100)
        self.feed.set(b, '5h', 79)
        return a, b

    def ready(self, title='route me'):
        mid = self.mission(title)
        self.propose(mid, task('t1', 'write_repo'))
        self.dispatchable(mid)
        return mid

    def dispatch(self, mid):
        return self.do(self.work.dispatch_task, task_id=self.task_of(mid).id)


def _approval(rig, mid, kind, state, **kw):
    """An approval row as a sweep would find one already in its state (t150's
    `_approval`: the writer's own insert, fields and all)."""
    aid = ids.new_id('approval')
    return entities.Approval(id=aid, kind=kind,
                             subject=Ref('plan', kw.pop('plan_id', None) or ids.new_id('plan')),
                             action_hash=hashlib.sha256(aid.encode()).hexdigest(),
                             requested_by=rig.user.id, mission_id=mid, state=state,
                             expires_at=kw.pop('expires_at', None) or FUTURE, **kw)


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


@pytest.fixture
def rroute(db):
    return RouteRig(db)


def _running_execution(rig, classes=('read',)):
    """b.py's construction: an INTENT execution of a dispatched task —
    `evaluate_action`'s input (the action it is asked about names its own class;
    the task declares the classes the judgement must see)."""
    mid = rig.mission()
    rig.propose(mid, task('t1', *classes))
    rig.dispatchable(mid)
    return mid, rig.do(rig.work.dispatch_task, task_id=rig.task_of(mid).id)['execution_id']


# ---------------------------------------------------------------- fail-closed refusals

def test_an_unclassified_execution_action_is_judged_as_its_strictest_class(rig):
    """P11 D1, the application's half: `evaluate_action(..., unclassified=True)`
    (authorization.py ~896-912, the `unclassified` it hands the context at ~911;
    engine.py ~126-133 judges every class and keeps the strictest). The pinned
    fail-closed direction is that widening can only make the answer stricter —
    and the only proof is a case where the classified answer is not DENY. No
    existing test passes `unclassified` to `evaluate_action` at all: P11's hook
    tests judge at the hook level, and the pinned `unclassified` tests live on
    the engine context, not on this command. A removed `unclassified=True`
    answers the running execution's read ALLOW and this test fails."""
    mid, eid = _running_execution(rig, ('read', 'exec'))   # the task declares both judged classes
    rig.do(rig.authz.set_profile, who=rig.user, scope='user', profile='standard')
    rig.rule('USER', 'exec', 'DENY')                            # exec denies, read would not

    allowed = rig.do(rig.authz.evaluate_action, execution_id=eid, action=READ_ACTION)
    assert allowed['decision'] == 'ALLOW'                       # the same action, classified

    denied = rig.do(rig.authz.evaluate_action, execution_id=eid, action=READ_ACTION,
                    unclassified=True)
    assert denied['decision'] == 'DENY'
    got = [d for d in rig.all(entities.PolicyDecision) if d.stage == 'action']
    assert [(d.decision, d.outcome) for d in got] == [('ALLOW', 'allow'), ('DENY', 'deny')]
    assert 'unclassified' in got[-1].reason
    assert got[-1].items[0]['class'] == 'exec'                  # judged as its strictest class
    assert rig.all(entities.Approval, kind='action') == []      # a DENY asks no one


def test_a_route_approval_whose_task_stopped_awaiting_is_never_approved(rroute):
    """The `route` arm of the `_awaiting` guard every `decide` consults
    (authorization.py ~776-784's task clause, reached from `decide` ~789-812), and
    the `_approve_route` approve branch (~789-807). t150's GAP 3 walks every
    NotEligible `why` on plan/task/action/start approvals; test_routing.py's I-F2
    only approves a live route ask. This is the route kind's stale-task case — a
    task resumed elsewhere: approving it would let an unapproved task run on a
    fallback account. Core answers NotEligible('not_awaiting') and nothing moves:
    no approval state change, no execution, not one event."""
    rig = rroute
    rig.limited()
    mid = rig.ready()
    out = rig.dispatch(mid)
    assert out['execution_id'] is None                          # the router asked instead
    a = rig.pending(mid)
    assert a.kind == 'route' and a.state == 'PENDING'
    t = rig.task_of(mid)
    assert t.state == 'AWAITING_APPROVAL'
    head, execs = rig.head(), len(rig.all(entities.Execution))

    tamper(rig.db, 'tasks', t.id, state='READY')                # resumed elsewhere, around Core
    with pytest.raises(authorization.NotEligible) as exc:
        rig.decide(a)
    assert exc.value.why == 'not_awaiting'
    assert rig.row_of(entities.Approval, a.id).state == 'PENDING'
    assert rig.task_of(mid).state == 'READY'          # the tamper stands; Core moved nothing back
    assert rig.m(mid).state == 'BLOCKED'                        # still held for the ask
    assert len(rig.all(entities.Execution)) == execs            # no privileged side effect
    assert rig.head() == head                             # a decision attempted; nothing written


def test_an_action_whose_plan_is_in_force_but_tampered_is_denied(rig):
    """The `intact` conjunct of `evaluate_action`'s in-force guard (authorization.py
    ~917-922): `prow.entity.id == plan.id and intact(tx.conn, plan)`. The other
    conjunct is t150-covered (the replaced-plan variant — where the reason string
    passes either way, because 'not in force' is in both phrasings). Here the plan
    is still the active version and its approval untouched — only its body no
    longer digests to itself. The action is denied and its approval is NOT
    superseded, which is what separates this from t150's supersede scenario; drop
    the conjunct and the ASK path answers and this fails."""
    mid, eid = _running_execution(rig)
    ask = rig.do(rig.authz.evaluate_action, execution_id=eid, action=PUSH)
    assert ask['decision'] == 'ASK'                             # the neighbouring pin, in place
    plan = rig.one(entities.Plan, mission_id=mid)
    head = rig.head()

    tamper(rig.db, 'plans', plan.id, summary='tampered by the test')   # a digested field
    denied = rig.do(rig.authz.evaluate_action, execution_id=eid, action=PUSH)
    assert denied['decision'] == 'DENY'
    assert rig.row_of(entities.Plan, plan.id).state == 'APPROVED'        # still the active version
    assert rig.pending(mid).state == 'PENDING'                    # not superseded: still decidable
    d = [x for x in rig.all(entities.PolicyDecision) if x.stage == 'action'][-1]
    assert d.outcome == 'deny' and 'not intact' in d.reason
    assert rig.head() == head + 1                                 # only the decision row, no fire


def test_a_rule_command_can_never_write_an_unlocked_deny(rig):
    """`create_rule` (authorization.py ~954-981) builds a `PolicyRule` entity,
    whose `_check` refuses a DENY that is not locked (entities.py ~1744: 'DENY is
    always locked') — fail-closed: an unlocked prohibition could be silenced.
    Entity-level tests exist (test_gaps_core_domain_entities_b.py:1391) but none
    goes through the command: a create_rule that dropped `locked` would keep every
    entity test green and write the unlockable prohibition. The command refuses
    with the reason, and the owner row it had already seeded for the default USER
    scope rolls back with the refusal — nothing half-written."""
    head = rig.head()
    with pytest.raises(ValueError, match='DENY is always locked'):
        rig.rule('USER', 'install', 'DENY', locked=False)
    assert rig.all(entities.PolicyRule) == []
    assert rig.all(entities.User) == []                    # the seeded owner rolled back too
    assert rig.head() == head                              # not even the creation event


# ------------------------------------------------------------------ state and boundaries

def test_withdraw_ends_only_the_pending_asks_of_the_named_mission(rig):
    """`withdraw` (authorization.py ~864-870) filters on the mission AND on
    `state == 'PENDING'`. t150's withdraw test covers the refused-while-pending
    case with one approval on one mission; neither filter is asserted there —
    dropping the mission clause kills a foreign mission's ask (nobody withdrew
    from it), dropping the state clause re-fires `reject` on an already-decided
    row. Here one sweep finds a REJECTED approval beside the pending one, and a
    second mission keeps its ask untouched."""
    m1 = rig.mission('mine')
    m2 = rig.mission('not yours')
    rig.propose(m1, task('t1', 'deploy'))
    rig.propose(m2, task('t1', 'deploy'))
    a1, a2 = rig.pending(m1), rig.pending(m2)
    decided = _approval(rig, m1, 'plan', 'REJECTED')            # already answered, same mission
    rig.put(decided)
    head = rig.head()

    rig.do(authorization.withdraw, who=rig.system, mission_id=m1, reason='its mission is gone')
    assert rig.row_of(entities.Approval, a1.id).state == 'REJECTED'
    assert rig.row_of(entities.Approval, a1.id).decided_by == rig.system.id
    assert rig.row_of(entities.Approval, decided.id).state == 'REJECTED'   # not re-fired
    assert rig.row_of(entities.Approval, a2.id).state == 'PENDING'         # foreign mission intact
    assert len(rig.events('approval.state_changed')) == 1                  # one change, no re-fire
    assert rig.head() == head + 1                                          # and only that one event


def test_a_declined_start_with_an_explicit_ask_still_waits_on_that_ask(rig):
    """`gate_start`'s declined clause (authorization.py ~854-860) is
    `_declined(...) and not by_request and live_approval(...) is None`. Each
    ingredient alone is pinned — t150's chat-reject test has a decline and no
    live ask (it only reaches a live ask through a by_request pass), t150's
    ask-twice test has a live ask and no decline, test_chat_start covers
    decline-after-expiry — but never the plain-gate pass with BOTH. A user who
    rejected the routine start and then explicitly requested one has a live
    `start` approval; a gate pass that answered `declined` here (drop the
    live-approval clause, or reorder it after the declined check) would strand
    the mission CREATED with a PENDING ask no sweep revisits and start it never.
    Core waits on the ask instead, asks no second one, and approving it starts."""
    mid = rig.created(origin='conversation')                # standard: asks before it starts
    assert rig.do(rig.authz.gate_start, who=rig.user, mission_id=mid) == \
        {'started': False, 'waiting': 'approval_required'}
    rig.decide(rig.pending(mid), 'reject')                  # the explicit no (stays idle: chat)
    assert rig.m(mid).state == 'CREATED'
    assert rig.do(rig.authz.request_start, who=rig.user, mission_id=mid) == \
        {'started': False, 'waiting': 'approval_required'}  # the explicit yes asks a second one
    asked = len([d for d in rig.all(entities.PolicyDecision) if d.stage == 'start'])

    assert rig.do(rig.authz.gate_start, who=rig.user, mission_id=mid) == \
        {'started': False, 'waiting': 'approval_required'}  # not 'declined': the ask is alive
    assert len(rig.all(entities.Approval, mission_id=mid)) == 2       # no third ask written
    assert len([d for d in rig.all(entities.PolicyDecision) if d.stage == 'start']) == asked
    live = [x for x in rig.all(entities.Approval, mission_id=mid) if x.state == 'PENDING']
    assert len(live) == 1
    rig.decide(live[0])
    assert rig.m(mid).state == 'UNDERSTANDING'              # and it was a live ask indeed


def test_expire_due_expires_exactly_at_its_moment_and_only_what_is_due(rig):
    """`expire_due` (authorization.py ~873-885): its clause is `a.expires_at <=
    tx.now`, so an approval expiring AT the sweep's own instant is due — t150's
    GAP 8 only uses strictly-past rows, and a `<` survives that test untouched.
    Its other clause is `state == 'PENDING' or (state == 'APPROVED' and kind ==
    'action')`: a terminal REJECTED row and an approved non-action row must be
    left alone even when past — dropping the state half re-fires `ttl_elapsed`
    from a state with no such transition, dropping the kind half expires an
    approval that was granted (D8). `next_expiry` (~887-893) shares the kind
    clause: a terminal or approved-plan row must not wake the expiry worker to an
    early sweep. Every row sits at exactly the sweep's second; the writer's own
    clock is frozen there so `tx.now` IS that instant."""
    mid = rig.mission('to expire')
    at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')
    due_pending = _approval(rig, mid, 'plan', 'PENDING', expires_at=at)
    done = _approval(rig, mid, 'plan', 'REJECTED', expires_at=at)
    granted_task = _approval(rig, mid, 'task', 'APPROVED', expires_at=at)
    granted_action = _approval(rig, mid, 'action', 'APPROVED', expires_at=at)
    later = _approval(rig, mid, 'task', 'PENDING', expires_at=FUTURE)
    rig.put(due_pending, done, granted_task, granted_action, later)
    assert rig.read(lambda r: authorization.next_expiry(r)) == at

    from archeus.infra.db import writer as writer_module    # the writer's clock, standing still
    real = writer_module.ev.now_iso
    writer_module.ev.now_iso = lambda: at
    try:
        out = rig.do(authorization.expire_due, who=rig.system)
    finally:
        writer_module.ev.now_iso = real
    assert sorted(out['expired']) == sorted([due_pending.id, granted_action.id])
    assert rig.row_of(entities.Approval, due_pending.id).state == 'EXPIRED'
    assert rig.row_of(entities.Approval, granted_action.id).state == 'EXPIRED'
    assert rig.row_of(entities.Approval, done.id).state == 'REJECTED'      # terminal, untouched
    assert rig.row_of(entities.Approval, granted_task.id).state == 'APPROVED'   # a grant stands
    assert rig.row_of(entities.Approval, later.id).state == 'PENDING'
    assert len(rig.events('approval.state_changed')) == 2                  # one per expired row
    assert rig.read(lambda r: authorization.next_expiry(r)) == FUTURE


def test_a_missions_own_profile_answers_the_start_gate_before_the_users(rig):
    """`asks_before_start` (authorization.py ~815-822): `m.autonomy_profile or
    (u.autonomy_profile if u else 'standard')` — the mission's own profile is
    consulted FIRST and the owner's default is only read when the mission names
    none. t150's GAP 4 exercises the user half with every mission profile None
    (its own comment notes the mission half as absent there); test_chat_start
    leaves both at their defaults. Neither direction is proven: a chat mission
    whose own profile says `standard` must ask under an autonomous owner, and
    one whose own profile says `autonomous` must start under a standard owner.
    Drop the mission clause and the first starts unasked."""
    rig.do(rig.authz.set_profile, who=rig.user, scope='user', profile='autonomous')
    chat = rig.created(origin='conversation')
    rig.do(rig.authz.set_profile, who=rig.user, scope='mission', mission_id=chat,
           profile='standard')                               # the mission itself says: always ask
    assert rig.do(rig.authz.gate_start, who=rig.user, mission_id=chat) == \
        {'started': False, 'waiting': 'approval_required'}
    assert rig.pending(chat).kind == 'start'
    assert rig.m(chat).state == 'CREATED'

    frank = rig.created(origin='conversation')
    rig.do(rig.authz.set_profile, who=rig.user, scope='mission', mission_id=frank,
           profile='autonomous')                             # the mission itself consents
    assert rig.do(rig.authz.gate_start, who=rig.user, mission_id=frank) == \
        {'started': True, 'waiting': None}
    assert rig.m(frank).state == 'UNDERSTANDING'
    assert rig.all(entities.Approval, mission_id=frank) == []              # asked no one
    assert len(rig.all(entities.Approval)) == 1                            # only the chat's ask


# ------------------------------------------------------------------------- simulate

def _simulate(rig, action, mission_id=None, extra_rules=()):
    with rig.db.read() as conn:                              # t150's `_simulate`, same door
        return rig.authz.simulate(conn, now=queries._now(), mission_id=mission_id,
                                  action=action, extra_rules=list(extra_rules))


def test_simulating_a_mission_start_judges_the_start_rules_and_writes_nothing(rig):
    """`simulate`'s start branch (authorization.py ~1149-1152: an action of class
    `mission.start` goes to `judge_start`, not to the generic action judge).
    t150's GAP 9 simulates a `git_push`; no test has ever simulated a start. The
    distinction that makes this branch real rather than decorative: a chat
    mission's owner-ask is applied by `judge_start` alone — on the generic path
    the same simulation answers ALLOW and the console promises a start the gate
    then refuses. It is also the only read of `policy_version` for a start: and
    every call is a read — the event chain and every table stand exactly where
    they were, including through the denied call."""
    rig.do(rig.authz.set_profile, who=rig.user, scope='user', profile='standard')
    chat = rig.created(origin='conversation')
    api = rig.created(origin='api')
    head = rig.head()

    asked = _simulate(rig, {'class': 'mission.start', 'target': 'mission/x'}, mission_id=chat)
    assert asked['simulated'] is True and asked['mission_id'] == chat
    assert asked['decision'] == 'ASK' and 'asks before' in asked['reason']   # judge_start's ask

    denied = _simulate(rig, {'class': 'mission.start', 'target': 'mission/y'}, mission_id=api,
                       extra_rules=[{'scope_level': 'USER', 'action_class': 'mission.start',
                                     'decision': 'DENY'}])
    assert denied['decision'] == 'DENY'
    assert 'simulated:0' in {m['id'] for m in denied['matched_rules']}        # the extra rule decided

    allowed = _simulate(rig, {'class': 'mission.start', 'target': 'mission/y'}, mission_id=api)
    assert allowed['decision'] == 'ALLOW' and allowed['policy_version']

    assert rig.head() == head                               # the chain never moved
    assert rig.all(entities.Approval) == [] and rig.all(entities.PolicyDecision) == []


def test_a_simulated_user_rule_is_judged_against_the_real_owner(rig):
    """`_simulated_rule`'s owner clause (authorization.py ~1106-1109): with an
    owner registered, an extra rule without an explicit `scope_ref` is raised ON
    THE OWNER — and `context()` chains USER to that same id, so it applies. t150's
    GAP 9 covers the other half (no owner exists: a stand-in so chain and rule
    still meet); no test simulates a USER extra rule while an owner does exist.
    Drop the clause and the rule is raised on a fresh stand-in, silently fails to
    match the owner's own chain, and the console promises ALLOW where the real
    judge denies. It matches here — and still no row is written."""
    rig.do(rig.authz.set_profile, who=rig.user, scope='user', profile='standard')   # an owner exists
    mid = rig.created(origin='api')
    head = rig.head()
    act = {'class': 'web', 'target': 'example.com/lookup', 'argv': []}

    allowed = _simulate(rig, act, mission_id=mid)
    assert allowed['decision'] == 'ALLOW'                   # the profile's own answer

    denied = _simulate(rig, act, mission_id=mid,
                       extra_rules=[{'scope_level': 'USER', 'action_class': 'web',
                                     'decision': 'DENY'}])
    assert denied['decision'] == 'DENY'                     # the owner's rule, on the owner's chain
    assert 'simulated:0' in {m['id'] for m in denied['matched_rules']}

    assert rig.head() == head
    assert rig.all(entities.PolicyRule) == []               # extra rules are never stored
    assert len(rig.all(entities.User)) == 1                 # the sim raised no second owner
    assert rig.all(entities.PolicyDecision) == []

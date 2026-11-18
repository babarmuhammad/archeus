"""T-1143: the ten highest-risk uncovered branches of
`archeus/core/application/authorization.py` lines 1-399 inclusive (at tip
56d53504), with the focus the card gives them: an Approval's hash binds the
exact current authority and nothing else. Fail-closed and denial compositions
first (an approved plan whose task rows moved, a dead approval row never being
the live one, a request that must not reuse another identity's row, a step-up
the policy asked for that must survive into what the user is shown), then the
boundary values (what moves the plan, task and start identities and what does
not, the TTL each kind waits), then the error paths (a plan with no recorded
context package, a pruned log, an emptied users table).

The final ten, against the card's probes (file:line in each docstring, with the
closest existing test and why it misses the case):

 1. probe 4  `intact`/`plan_approval_state` over the TASK rows 182-189, 243-249
 2. probe 5  `plan_items`/`plan_hash` binds every action      200-207
 3. probe 6  `task_hash` is its own actions, not the plan's   209-212
 4. probe 7  `start_hash` is the mission, not its authority   214-222
 5. probe 8  `live_approval` excludes every terminal state     45, 237-241
 6. probe 9  `request` dedups on the hash and nothing looser  367-373
 7. NEW (replaces probe 2, whose expired-single-use case
    test_fix_authorization.py:34 already pins) `TTL` per kind   43-44, 386
 8. probe 10 `step_up` survives into the row, the card and the
    event                                                   374, 355-366, 396
 9. NEW (replaces probe 3, whose foreign-plan case
    `plan_approval_state` pins in test 1): `current` — the
    `context_package_id is None` answer 256-257 (a line the
    card's seven read-first files never execute), the guard
    at 258-260, the missing package row                        252-261
10. NEW (replaces probe 1, whose estop override gaps_a pins at
    327-345, writing a real sentinel — here it is a seam): `judge_start`'s
    USER-chain fallback 229 and the `estop=False` arm of 231, against the real
    `context` and the real engine                              225-234

Nothing here starts Core, a worker, a process or a socket: the router is the P1
stub, the e-stop sentinel and the model port are seams (`os_and_ports`), no
`tc` fixture is invoked, and every write lands in the test's own `ARCHEUS_HOME`
(`tmp_path`), which is where the `db` fixture this suite already uses
(`tests/v1/integration/test_policy.py`) opens its database.
"""

import json
from dataclasses import replace
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from archeus.core import ports
from archeus.core.application import authorization
from archeus.core.domain import actions as A
from archeus.core.domain import entities, ids
from archeus.core.domain.events import new_event
from archeus.core.domain.values import Ref
from archeus.core.policy.engine import PolicyEngine
from archeus.infra import paths
from archeus.infra.db import rows
from archeus.infra.eventlog import retention
from v1.integration.test_policy import Rig
from v1.integration.test_policy import task as spec

NOW = '2026-01-01T00:00:00.000Z'
FUTURE = '2099-01-01T00:00:00.000Z'
ACCEPT = [{'text': 'it is done', 'check': 'automatic'}]


# ── the seams: no OS state, no worker, no later-phase port ───────────────────

class Seams:
    """What the tested code is allowed to ask the operating system: an answer
    for the e-stop sentinel, never a file. `armed` is what `os.path.exists`
    says about `paths.stop_sentinel()`; `seen` records the calls."""

    def __init__(self):
        self.armed = False
        self.seen = []
        self.sentinel = paths.stop_sentinel()

    def exists(self, path):
        self.seen.append(str(path))
        return self.armed and str(path) == self.sentinel


@pytest.fixture(autouse=True)
def os_and_ports(monkeypatch):
    """The tested code reaches no real OS state and no later phase: `os` inside
    the module under test is a fake that only answers the sentinel (no test
    writes or reads a sentinel file), the model port is refused, and the router
    stays the P1 stub. The database is the real one, under `ARCHEUS_HOME`."""
    s = Seams()
    monkeypatch.setattr(authorization, 'os',
                        SimpleNamespace(path=SimpleNamespace(exists=s.exists)))
    calls = []
    real = ports.FixedCandidateRouter.route
    monkeypatch.setattr(ports.FixedCandidateRouter, 'route',
                        lambda self, *a, **k: calls.append('route') or real(self, *a, **k))
    import archeus.core.calls as C
    monkeypatch.setattr(C.OwnCalls, 'run', lambda *a, **k: calls.append('archeus_call'))
    yield s
    assert 'archeus_call' not in calls                      # E6: no later-phase port


# ── the world: real rows, written through the writer ─────────────────────────

def _note(tx, *, actor, mission_id, workspace):
    """The writer requires a mutation to say what happened: these helpers write
    rows the real commands would have, behind the back."""
    tx.append(new_event('mission.updated', Ref('mission', mission_id), actor, payload={},
                        workspace=workspace))


def _add_plan(tx, *, actor, mission_id, tasks, workspace):
    """One plan and its task rows, the digest computed by the same validator
    dispatch re-checks. `tasks` is [(key, classes, capabilities, touches)]."""
    from archeus.core.planning import validate
    pid = ids.new_id('plan')
    made = [entities.Task(id=ids.new_id('task'), plan_id=pid, mission_id=mission_id,
                          key=k, title='Task %s' % k, kind='code_change', state='READY',
                          action_classes=tuple(c), capabilities_required=tuple(cap),
                          touches=tuple(touches), acceptance=ACCEPT)
            for k, c, cap, touches in tasks]
    plan = entities.Plan(id=pid, mission_id=mission_id, plan_version=1,
                         summary='test plan', state='APPROVED',
                         digest=validate.digest(entities.Plan(
                             id=pid, mission_id=mission_id, plan_version=1,
                             summary='test plan', state='APPROVED'), made))
    tx.insert(plan, actor=actor)
    for t in made:
        tx.insert(t, actor=actor)
    _note(tx, actor=actor, mission_id=mission_id, workspace=workspace)
    return {'pid': pid, 'tids': [t.id for t in made]}


def _add_row(tx, *, row, actor, mission_id, workspace):
    tx.insert(row, actor=actor)
    _note(tx, actor=actor, mission_id=mission_id, workspace=workspace)
    return row.id


def _drop_row(tx, *, table, id_, actor, mission_id, workspace):
    """Behind the back: the mutation a test needs to see what a recompute is
    for (the plan digest is recomputed from the rows, never trusted)."""
    tx.execute('DELETE FROM %s WHERE id = ?' % table, (id_,))
    _note(tx, actor=actor, mission_id=mission_id, workspace=workspace)


def _edit(tx, *, table, id_, changes, actor, mission_id, workspace):
    body = json.loads(tx.execute('SELECT body FROM %s WHERE id = ?' % table,
                                 (id_,)).fetchone()[0])
    body.update(changes)
    tx.execute('UPDATE %s SET body = ? WHERE id = ?' % table,
               (json.dumps(body, sort_keys=True), id_))
    _note(tx, actor=actor, mission_id=mission_id, workspace=workspace)


def _set(tx, *, table, id_, column, value, actor, mission_id, workspace):
    tx.execute('UPDATE %s SET %s = ? WHERE id = ?' % (table, column), (value, id_))
    _note(tx, actor=actor, mission_id=mission_id, workspace=workspace)


class World:
    """A mission with one APPROVED plan of two ordinary tasks, plus the small
    behind-the-back mutations and the identity reads the cases are about."""

    def __init__(self, db):
        self.db = db
        self.rig = Rig(db)
        self.actor = self.rig.system
        self.mid = self.rig.mission()
        with db.read() as r:
            self.workspace = rows.get(r, entities.Mission, self.mid).entity.workspace_id
        made = db.writer.execute(_add_plan, {
            'actor': self.actor, 'mission_id': self.mid, 'workspace': self.workspace,
            'tasks': [('t1', ('read',), (), ()),
                      ('t2', ('write_repo',), (), ('src/**',))]})
        self.plan_id, self.tids = made['pid'], made['tids']
        self.mutation = {'actor': self.actor, 'mission_id': self.mid,
                         'workspace': self.workspace}

    def plan(self):
        """The plan row on its own: an identity is only meaningful when
        everything it hashes came from one snapshot."""
        with self.db.read() as r:
            return rows.get(r, entities.Plan, self.plan_id).entity

    def edit_task(self, i=0, **changes):
        self.db.writer.execute(_edit, dict(self.mutation, table='tasks',
                                           id_=self.tids[i], changes=changes))

    def task_state(self, i=0, state='RUNNING'):
        self.db.writer.execute(_set, dict(self.mutation, table='tasks', id_=self.tids[i],
                                          column='state', value=state))

    def set_plan_digest(self, digest):
        self.db.writer.execute(_edit, dict(self.mutation, table='plans', id_=self.plan_id,
                                           changes={'digest': digest}))

    def add_task(self, key, classes=(), capabilities=(), touches=()):
        row = entities.Task(id=ids.new_id('task'), plan_id=self.plan_id,
                            mission_id=self.mid, key=key, title='Task %s' % key,
                            kind='code_change', state='READY',
                            action_classes=tuple(classes),
                            capabilities_required=tuple(capabilities),
                            touches=tuple(touches), acceptance=ACCEPT)
        return self.insert(row)

    def drop_task(self, tid):
        self.db.writer.execute(_drop_row, dict(self.mutation, table='tasks', id_=tid))

    def insert(self, row):
        return self.db.writer.execute(_add_row, dict(self.mutation, row=row))

    def hashes(self):
        with self.db.read() as r:
            plan = rows.get(r, entities.Plan, self.plan_id).entity
            return {'plan': authorization.plan_hash(r, plan),
                    'tasks': [authorization.task_hash(plan, rows.get(r, entities.Task, t).entity)
                              for t in self.tids],
                    'items': authorization.plan_items(r, plan)}

    def approval(self, *, kind='task', i=0, **kw):
        h = kw.pop('action_hash', None) or self.hashes()['tasks'][i]
        return entities.Approval(
            id=ids.new_id('approval'), kind=kind,
            subject=Ref('task', self.tids[i]) if kind == 'task' else Ref('plan', self.plan_id),
            action_hash=h, requested_by=self.actor.id, mission_id=self.mid,
            plan_id=self.plan_id, plan_version=1, plan_digest=self.plan().digest,
            task_id=self.tids[i] if kind == 'task' else None,
            expires_at=kw.pop('expires_at', FUTURE), items=(), **kw)


def mutation(rig, mid):
    with rig.db.read() as r:
        ws = rows.get(r, entities.Mission, mid).entity.workspace_id
    return {'actor': rig.system, 'mission_id': mid, 'workspace': ws}


@pytest.fixture
def world(db):
    return World(db)


def _one(tx, cls, id_):
    return rows.get(tx.conn, cls, id_).entity


def _ask(tx, *, actor, kind, w, execution_id=None, items=None, h=None, ctx=None):
    """Judge one task (or the start) the way the gate judges it and ask for its
    approval, in the same transaction — as `check_dispatch`/`gate_start` do, from
    one snapshot of the rows the identity is built from."""
    plan = None if kind == 'start' else _one(tx, entities.Plan, w.plan_id)
    mission = _one(tx, entities.Mission, w.mid)
    task = _one(tx, entities.Task, w.tids[0])
    if items is None:
        if kind == 'start':
            items, judged = authorization.judge_start(PolicyEngine(), tx.conn, mission,
                                                     now=tx.now, actor=actor)
        else:
            items, judged = authorization.evaluate_task(
                PolicyEngine(), tx.conn, mission, task.key, task.action_classes,
                capabilities=task.capabilities_required, touches=task.touches, now=tx.now,
                task=task, actor=actor, plan=plan, stage='plan')
    else:
        judged = ctx or {'policy_version': 'pv-under-test'}
    if h is None:
        if kind == 'start':
            h = authorization.start_hash(mission)
        elif kind == 'plan':
            h = authorization.plan_hash(tx.conn, plan)
        elif kind == 'task':
            h = authorization.task_hash(plan, task)
        else:
            h = A.action_hash('action', authorization.bind(plan, task, execution_id),
                              [A.item(task.key, a) for _c, _b, a in
                               authorization.items_of(task)])
    a, new = authorization.request(
        tx, actor=actor, kind=kind, mission=mission, plan=plan,
        task=task if kind in ('task', 'action') else None, items=items, h=h,
        decision_id=ids.new_id('policy_decision'), why='asked by the test',
        ctx=judged, execution_id=execution_id if kind == 'action' else None)
    ev = json.loads(tx.execute('SELECT payload FROM events WHERE type = ? '
                               'ORDER BY seq DESC LIMIT 1', ('approval.requested',)).
                    fetchone()[0])
    return {'id': a.id, 'new': new, 'kind': a.kind, 'h': h, 'now': tx.now,
            'action_hash': a.action_hash, 'subject': [a.subject.kind, a.subject.id],
            'step_up': a.step_up, 'expires_at': a.expires_at,
            'policy_version': a.policy_version, 'items': [dict(i) for i in a.items],
            'presented': a.presented, 'event': ev}


# ── fail-closed: the approval is of the plan whose rows still say the same ────

def test_an_approved_plan_whose_task_rows_moved_is_not_the_approved_plan(world):
    """authorization.py:182-189 (`_tasks` and `intact`: `bool(plan.digest) and
    validate.digest(plan, _tasks(conn, plan)) == plan.digest`, the tasks read
    back from their own rows) feeding 243-249 (`plan_approval_state` answers
    None once the plan does not recompute) — what the mission's `approve` guard
    reads (D10).

    Closest existing test: gaps_a:190,
    `test_a_tampered_plan_is_never_the_approved_plan_and_its_dispatch_is_denied`,
    rewrites the PLAN row's summary, so it pins the plan
    half of that digest while `_tasks` still returns what it inserted; nothing
    pins the task half. Here the plan row is untouched and the task rows move —
    a task appearing, and a task's declared classes widening to `deploy`. An
    `intact` that digested the plan alone, or trusted the stored digest, answers
    True for every existing test while a plan nobody approved dispatches."""
    w = world
    approved = w.approval(kind='plan', state='APPROVED', action_hash=w.hashes()['plan'])
    w.insert(approved)
    with w.db.read() as r:
        plan = w.plan()
        assert authorization.intact(r, plan) is True
        assert authorization.plan_approval_state(r, plan) == 'APPROVED'
    extra = w.add_task('t3', classes=('deploy',))            # a task nobody approved
    with w.db.read() as r:
        plan = w.plan()
        assert authorization.intact(r, plan) is False        # an extra row moved it
        assert authorization.plan_approval_state(r, plan) is None
    w.drop_task(extra)                                       # the row is not there again
    with w.db.read() as r:
        plan = w.plan()
        assert authorization.intact(r, plan) is True
        assert authorization.plan_approval_state(r, plan) == 'APPROVED'
    w.edit_task(0, action_classes=['read', 'deploy'])        # the same task widened
    with w.db.read() as r:
        plan = w.plan()
        assert authorization.intact(r, plan) is False        # same rows, new content
        assert authorization.plan_approval_state(r, plan) is None
        # and the identity an approval is keyed on moved with it
        assert [i['action']['class'] for i in authorization.plan_items(r, plan)
                if i['task'] == 't1'] == ['read', 'deploy']


# ── the plan identity: its actions, and only its actions ─────────────────────

def test_the_plan_hash_binds_what_the_plan_will_do_not_its_prose_or_progress(world):
    """authorization.py:200-207 (`plan_items`: every task's declared classes and
    the ones its capabilities imply, as canonical actions, under the binding of
    192-198) and 205-207 (`plan_hash`).

    Closest existing tests: `test_policy.py:152` asserts the recorded
    `d.action_hash == authorization.plan_hash(conn, p)` — true for ANY function
    of the plan — and gaps_a's `_world` (line 65) compares a plan hash only with
    itself. Nothing moves an action and asks whether the plan's identity moved.
    A `plan_items` that returned no items, or ignored the capabilities, keeps
    every existing test green while a plan widened to `deploy` after approval
    goes on dispatching under the approval of the narrow one (§7.2)."""
    w = world
    h0 = w.hashes()['plan']
    assert w.hashes()['plan'] == h0                            # pure over the rows
    assert [sorted(i.keys()) for i in w.hashes()['items']] == [['action', 'task']] * 2
    w.edit_task(1, capabilities_required=['shell'])                     # implies exec (D6)
    h1 = w.hashes()['plan']
    assert h1 != h0
    assert [i['action']['class'] for i in w.hashes()['items'] if i['task'] == 't2'] == \
        ['write_repo', 'exec']
    w.edit_task(0, touches=['src/**', 'deploy.yaml'])          # what it may touch
    h2 = w.hashes()['plan']
    assert h2 != h1
    w.edit_task(1, title='renamed by the planner',
                acceptance=[{'text': 'something else', 'check': 'human'}])
    assert w.hashes()['plan'] == h2                            # prose is not authority
    w.task_state(0)                              # progress is not either
    assert w.hashes()['plan'] == h2
    w.edit_task(0, action_classes=['read', 'deploy'])           # the widened plan
    assert w.hashes()['plan'] != h2


# ── the task identity: this task, these actions, this plan version ───────────

def test_the_task_hash_is_its_own_actions_neither_the_plans_nor_a_neighbours(world):
    """authorization.py:209-212 (`task_hash`: `action_hash('task', bind(plan,
    task), [item(task.key, a) ...])`) with the binding of 192-198 — the identity
    a task-lifetime approval is stored under (§8.4).

    Closest existing tests: gaps_a's `_world` computes `task_hash` to key the
    approvals it seeds (line 65) and `test_policy.py:473`
    (`test_approval_coverage_is_the_exact_item_and_its_step_up`) reads them back
    through `_covers` (492) — both hash the same rows they approve, so a
    `task_hash` that ignored the actions, or ignored WHICH task it was handed,
    leaves the suite green
    while one task's approval authorises another task's deploy, or the plan's own
    approval is mistaken for a task's (it is only `kind` away)."""
    w = world
    h1, h2 = w.hashes()['tasks']
    assert w.hashes()['tasks'][0] == h1 and h1 != h2           # not its neighbour's
    assert h1 != w.hashes()['plan'] != h2                      # not the plan's either
    w.edit_task(0, action_classes=['read', 'deploy'])          # widened in place
    assert w.hashes()['tasks'][0] != h1
    w.edit_task(0, action_classes=['read'])                    # narrowed back: identity back
    assert w.hashes()['tasks'][0] == h1
    w.edit_task(0, touches=['deploy.yaml'])                    # what it may touch
    assert w.hashes()['tasks'][0] != h1
    w.edit_task(0, touches=[])                                 # back: it touches nothing
    assert w.hashes()['tasks'][0] == h1
    w.edit_task(0, title='prose only',
                acceptance=[{'text': 'something else', 'check': 'human'}])
    assert w.hashes()['tasks'][0] == h1                        # prose is not authority
    w.task_state(0)
    assert w.hashes()['tasks'][0] == h1                        # progress is not authority
    w.set_plan_digest('a' * 64)                                # its plan version moved
    assert w.hashes()['tasks'][0] != h1
    assert w.hashes()['tasks'][1] != h2                        # and this task's too


# ── the start identity: the mission, and none of its mutable authority ────────

def test_the_start_identity_is_the_mission_not_the_authority_of_the_moment(os_and_ports,
                                                                           world):
    """authorization.py:214-222 (`start_action`/`start_hash`: the mission alone,
    through a binding that names no plan, task or execution) — the identity
    `gate_start` asks under and `_declined` reads back.

    Closest existing test: `test_the_start_hash_binds_the_mission_and_nothing_else`
    (gaps_a:721) compares a mission with ITSELF and with a mission of another id,
    so it can only catch a hash that IGNORES the id; it never changes a field of
    the same mission. Leak the autonomy profile (the obvious mistake — the
    profile is what decides the start ask), the origin or the state into the
    binding and the pending start approval of a mission whose user switches
    profile is silently orphaned: the gate asks an identity nobody was shown, and
    the rejection `_declined` must remember is no longer found (P19 B6, D7)."""
    m = world.rig.m(world.mid)
    h = authorization.start_hash(m)
    assert h == authorization.start_hash(m)
    for field, value in [('autonomy_profile', 'careful'), ('origin', 'conversation'),
                         ('state', 'EXECUTING'), ('title', 'renamed'),
                         ('objective', 'another objective'), ('context_package_id', None),
                         ('planning_blocked', {'kind': 'policy'})]:
        assert authorization.start_hash(m) == authorization.start_hash(
            replace(m, **{field: value})), field
    os_and_ports.armed = True                                  # the e-stop is not either
    assert authorization.start_hash(m) == h
    assert authorization.estop_armed() is True and os_and_ports.seen == \
        [paths.stop_sentinel()]
    os_and_ports.armed = False
    other = replace(m, id=ids.new_id('mission'))
    assert authorization.start_hash(other) != h                # no cross-mission replay
    assert authorization.start_hash(replace(other, title=m.title,
                                             objective=m.objective)) != h
    assert authorization.start_action(m).target == 'mission:%s' % m.id
    # the identity is exactly the mission, its class and its target: the binding
    # of a start names the mission and nothing else
    assert h == A.action_hash('start', A.binding(mission_id=m.id, plan_id=None,
                                                 plan_version=None, plan_digest=None),
                              [A.item(None, authorization.start_action(m))])
    with pytest.raises(ValueError, match='names its mission and nothing else'):
        A.action_hash('start', A.binding(mission_id=m.id, plan_id=None, plan_version=None,
                                         plan_digest='b' * 64),
                      [A.item(None, authorization.start_action(m))])


def test_the_start_is_judged_on_the_user_the_caller_named_when_no_user_row_is_left(db,
                                                                                   os_and_ports):
    """authorization.py:225-234 (`judge_start`: `ctx['chain']['USER'] =
    ctx['chain']['USER'] or user_id`) — a fallback that only ever fires when
    `context` (118-137) found no owner at all (95-97, the first `users` row).

    Closest existing test: `test_judge_start_keeps_denials_and_uses_start_context`
    (tests/v1/unit/test_chat_start_units.py:55-72) fakes `context` to hand back a
    chain the test itself wrote (`{'estop': True, 'chain': {'USER': None}}`), fakes
    `judge`, and asserts the assignment inside that fake — the fallback is only ever
    seen working on a chain nobody derived from rows, and neither the real owner
    lookup (95-97) nor the real engine is in the loop. Here one USER-scope DENY of
    `mission.start` is matched through the owner's row while it exists and, after
    that row is gone, only through the user the caller names. Drop the fallback and
    the rule silently stops applying — the mission starts under a policy its user
    denied (P19 B6); drop the `or`'s left side and a caller names whoever it likes
    to escape the same DENY. The disarmed arm of 231 (`dict(ctx, estop=False)`) is
    read against the real `context` here too: the sentinel is armed through the
    seam, so `context` really reports it and the start is still judged disarmed."""
    r = Rig(db)
    mid = r.mission()
    who = entities.User(id=ids.new_id('user'), display_name='U')
    rule = entities.PolicyRule(id=ids.new_id('policy_rule'), scope_level='USER',
                               scope_ref=who.id, action_class='mission.start',
                               decision='DENY')
    for row in (who, rule):
        r.db.writer.execute(_add_row, dict(mutation(r, mid), row=row))

    def judge(actor, user_id=None):
        with db.read() as c:
            m = rows.get(c, entities.Mission, mid).entity
            items, ctx = authorization.judge_start(PolicyEngine(), c, m, now=NOW,
                                                   actor=actor, user_id=user_id)
            return {'decision': items[0]['decision'], 'reason': items[0]['reason'],
                    'user': ctx['chain']['USER'], 'profile': ctx['profiles']['USER'],
                    'rule': items[0]['deciding_rule'], 'estop': ctx['estop'],
                    'rules': [x['id'] for x in ctx['rules']]}

    assert judge(r.system)['rules'] == [rule.id]               # the rule is the policy
    assert judge(r.system)['rule'] == rule.id                  # the owner's own DENY holds
    assert judge(r.system)['user'] == who.id
    db.writer.execute(_wipe_users, mutation(r, mid))
    with db.read() as c:
        assert authorization.owner(c) is None                  # no user row is left
    os_and_ports.armed = True                                  # the e-stop seam: armed
    assert judge(r.system)['decision'] != 'DENY'               # what starts is not held
    assert judge(r.system)['rule'] != rule.id                  # and the DENY is unreachable
    assert judge(r.system)['user'] is None and judge(r.system)['profile'] == 'standard'
    out = judge(r.system, who.id)                              # the caller names the user
    assert out['decision'] == 'DENY' and out['rule'] == rule.id
    assert out['user'] == who.id
    os_and_ports.armed = False


def _wipe_users(tx, *, actor, mission_id, workspace):
    """The state a read-only deployment can be in: the mission is there, the
    principal whose policy it is under is not."""
    assert tx.execute('SELECT COUNT(*) FROM users').fetchone()[0] > 0
    tx.execute('DELETE FROM users')
    _note(tx, actor=actor, mission_id=mission_id, workspace=workspace)


# ── a dead row is never the live one ─────────────────────────────────────────

def test_no_terminal_row_of_an_identity_is_ever_its_live_approval(world):
    """authorization.py:45 (`LIVE = ('PENDING','APPROVED')`) with 237-241
    (`live_approval`: the `[... if r.entity.state in LIVE]` filter and
    `got[-1]`).

    Closest existing test: `test_only_a_live_unexpired_approval_is_usable`
    (gaps_a:295) seeds ONE row per identity — PENDING, SUPERSEDED, or an APPROVED
    row past its TTL — and asks whether it is live. The re-ask flow leaves SEVERAL
    rows of one identity behind (declined, expired, then asked again) and the
    schema's unique index (0014_start_approvals.sql: `WHERE state IN
    ('PENDING','APPROVED')`) restricts only the live ones — so a `live_approval`
    without the filter, or reading `got[0]`, still answers every existing test
    while handing back the row a user already REJECTED (or a CONSUMED single-use
    one) as the live approval of that identity, which `_usable` would then take as
    its own APPROVED answer (§19)."""
    w = world
    dead = ('REJECTED', 'EXPIRED', 'SUPERSEDED', 'CONSUMED')
    live = w.approval(i=0, state='APPROVED')
    w.insert(live)
    for state in dead:                                         # the dead rows come AFTER
        w.insert(w.approval(i=0, state=state))
    other = w.hashes()['tasks'][1]
    for state in dead:                                         # every row of this one is dead
        w.insert(w.approval(i=1, state=state, action_hash=other))
    with w.db.read() as r:
        got = authorization.live_approval(r, w.hashes()['tasks'][0])
        assert got is not None and got.entity.id == live.id     # the LIVE row, not the last
        assert got.entity.state == 'APPROVED'
        assert authorization.live_approval(r, other) is None    # nothing live: nothing live
        assert authorization.live_approval(r, 'b' * 64) is None  # another identity's row
    w.insert(w.approval(i=1, state='PENDING', action_hash=other))   # asked again
    with w.db.read() as r:
        got = authorization.live_approval(r, other)
        assert got is not None and got.entity.state == 'PENDING'


# ── a request is the approval of exactly the identity it was asked for ────────

def test_one_ask_per_identity_and_no_reuse_of_another_identitys_row(db, world):
    """authorization.py:367-373 (`request`: `got = live_approval(tx.conn, h); if
    got is not None: return got.entity, False`) where `live_approval` (237-241)
    filters on `action_hash` ALONE, and the binding recorded at 375-386.

    Closest existing test: `test_the_same_task_asked_twice_finds_the_same_approval_row`
    (gaps_a:266) replays ONE identity and asserts the same row comes back — a
    dedup keyed on the mission, the plan or the task instead of `h` passes it,
    and so does one that records another identity's hash on the row. Then a task
    dispatch is authorised by an approval that never named it (§8.4), or — with
    the live-identity index — the second real ask is refused and the gate is left
    with a row for the wrong thing."""
    w = world
    plan_out = db.writer.execute(_ask, {'actor': w.actor, 'kind': 'plan', 'w': w})
    again = db.writer.execute(_ask, {'actor': w.actor, 'kind': 'plan', 'w': w})
    assert (plan_out['new'], again['new']) == (True, False)
    assert again['id'] == plan_out['id']
    assert plan_out['subject'] == ['plan', w.plan_id]
    task_out = db.writer.execute(_ask, {'actor': w.actor, 'kind': 'task', 'w': w})
    assert task_out['new'] is True and task_out['id'] != plan_out['id']
    assert task_out['subject'] == ['task', w.tids[0]]
    assert task_out['action_hash'] == w.hashes()['tasks'][0] != plan_out['action_hash']
    execution_id = ids.new_id('execution')
    single = db.writer.execute(_ask, {'actor': w.actor, 'kind': 'action', 'w': w,
                                       'execution_id': execution_id})
    assert single['new'] is True and single['id'] not in (plan_out['id'], task_out['id'])
    assert single['subject'] == ['execution', execution_id]     # single-use, of one run
    assert single['action_hash'] not in (plan_out['action_hash'], task_out['action_hash'])
    assert single['presented']['reusable'] == 'single-use'
    made = w.rig.all(entities.Approval, mission_id=w.mid)
    assert len(made) == 3 and {a.state for a in made} == {'PENDING'}
    asked = w.rig.events('approval.requested')
    assert len(asked) == 3                                      # one ask per identity
    assert [e['payload']['action_hash'] for e in asked] == \
        [plan_out['action_hash'], task_out['action_hash'], single['action_hash']]


# ── the clock: each kind waits its own TTL, in the form the comparisons read ──

def test_an_ask_waits_the_ttl_of_its_kind_and_not_of_another_kind(db, world):
    """authorization.py:43-44 (`TTL`: plan/task/start 24 h but action 2 h) read
    at 386 (`expires_at=_plus(tx.now, TTL[kind])`), the value `_usable` (504) and
    `expire_due` compare.

    Closest existing tests: `test_fix_authorization.py:34` monkeypatches
    `TTL['action']` to 1.5 s and only asserts a SECOND approval appears (GAP 7,
    gaps_b:382-391, pushes an ACTION approval's `expires_at` into the past to watch
    the gate expire it), and gaps_a's `task-lifetime` case asserts `expires_at` is
    NOT read for a task approval. Nothing pins the values or the per-kind reading:
    hang every kind off one key (or swap two) and a single-use approval — the one
    that lets a deploy run once, on a device that is paired but not proven — sits
    live for a whole day and runs the action a day later, with the suite green."""
    w = world
    expect = {'plan': timedelta(hours=24), 'task': timedelta(hours=24),
              'action': timedelta(hours=2), 'start': timedelta(hours=24)}
    assert expect['action'] < expect['plan']             # the single-use one is shortest
    for kind, delta in expect.items():
        out = db.writer.execute(_ask, {'actor': w.actor, 'kind': kind, 'w': w,
                                       'execution_id': ids.new_id('execution')})
        said = datetime.strptime(out['expires_at'], '%Y-%m-%dT%H:%M:%S.%fZ')
        asked = datetime.strptime(out['now'], '%Y-%m-%dT%H:%M:%S.%fZ')
        assert said - asked == delta, (kind, out['expires_at'], out['now'])
        assert out['expires_at'].endswith('Z') and len(out['expires_at']) == len(NOW)
        assert out['action_hash'] == out['h'] and out['kind'] == kind
        assert out['event']['expires_at'] == out['expires_at']    # asked at that time


# ── the step-up the policy asked for survives into what the user is shown ─────

def test_a_step_up_asked_by_the_policy_survives_into_the_shown_approval(db, world):
    """authorization.py:374 (`step_up = any(i.get('step_up') for i in items)`)
    carried into the row (380) and into what the user is actually shown at
    355-361 (`_presented`'s `consequences['step_up']`) and the event payload (396).

    Closest existing tests: `test_policy.py:167` asserts `step_up` on an approval
    the plan gate asked for with ONE deploy item, and gaps_a's coverage cases
    pre-seed `step_up=` on a row; with one item, `any`, `all` and `items[0]` agree.
    Ask with MIXED items — an ordinary ASK beside the deploy — and `all(...)` (or
    reading the first item) silently drops the proof requirement from the row the
    dispatch's `_covers` (492, demanded at 531) will require it on: the user approves
    a deploy without
    ever being asked for a PIN (§8.6, D16)."""
    w = world
    plain = {'task': 't1', 'class': 'write_repo', 'decision': 'ASK', 'reason': 'in boundary',
             'action': {'class': 'write_repo', 'target': 'task:t1', 'paths': ['src/**']},
             'matched': [], 'effective': [], 'deciding_rule': None, 'conflicts': [],
             'boundary': None, 'checks': None, 'step_up': False}
    deploy = {'task': 't2', 'class': 'deploy', 'decision': 'ASK', 'reason': 'a deploy',
              'action': {'class': 'deploy', 'target': 'task:t2', 'paths': ['deploy.yaml']},
              'matched': [], 'effective': [], 'deciding_rule': None, 'conflicts': [],
              'boundary': None, 'checks': None, 'step_up': True}
    out = db.writer.execute(_ask, {'actor': w.actor, 'kind': 'task', 'w': w,
                                   'items': [plain, deploy],
                                   'ctx': {'policy_version': 'pv-under-test'}})
    assert out['step_up'] is True                             # ANY item asked for proof
    assert out['presented']['consequences']['step_up'] is True
    assert out['event']['step_up'] is True
    assert out['policy_version'] == 'pv-under-test'           # recorded beside the hash
    assert [x['class'] for x in out['presented']['what']] == ['write_repo', 'deploy']
    assert [x['decision'] for x in out['presented']['what']] == ['ASK', 'ASK']
    assert out['items'] == [{'task': 't1', 'action': plain['action']},
                            {'task': 't2', 'action': deploy['action']}]
    out2 = db.writer.execute(_ask, {'actor': w.actor, 'kind': 'task', 'w': w,
                                    'items': [plain, dict(deploy, step_up=False)],
                                    'h': 'c' * 64,
                                    'ctx': {'policy_version': 'pv-under-test'}})
    assert out2['step_up'] is False                           # nothing asked for a PIN
    assert out2['presented']['consequences']['step_up'] is False
    assert out2['event']['step_up'] is False


# ── the currency of a plan: no package recorded, or a log that no longer reaches ──

@pytest.mark.parametrize('case, expected', [
    ('intact', (True, 'nothing it rests on changed')),
    ('no-package', (True, 'planned without a recorded context package')),
    ('pruned', (False, 'the event log no longer reaches back to its context package')),
    ('package-gone', (False, 'does not exist'))],
    ids=['intact', 'no-package', 'pruned-log', 'package-row-gone'])
def test_a_plan_is_current_only_while_the_log_still_reaches_its_context(db, os_and_ports,
                                                                        case, expected):
    """authorization.py:252-261 (`current`): the `plan.context_package_id is
    None` answer of 256-257 — a line the card's seven read-first files never
    execute (branch probe over their 162 tests, scratch `cov_card.txt`) — the
    `pkg is not None and outbox.floor(conn) > as_of_seq` guard of 258-260, and
    the fall-through to `planner.currency`.

    Closest existing coverage: `test_I_A10b_a_pruned_log_cannot_prove_currency`
    (test_policy.py:441) prunes the log and asserts only the one label `ineligible`
    (644-647) puts on it — `why == 'stale'` — never which of `current`'s refusals
    produced it, so inverting the pruned guard, or dropping the whole no-package
    arm, is invisible to it as long as something still says 'stale'. `planner.currency`
    is tested where it lives (test_gaps_core_planning_planner.py:157-200), and the
    two integration files that reach `current` at all (`test_chat_start.py`,
    `test_policy_http.py`) do so incidentally on the dispatch path, naming neither a
    context package nor a refusal reason. So both
    ways the context can no longer be replayed (the log pruned past the package's
    `as_of_seq`; the package row gone) read as CURRENT, and a plan that recorded
    no package either crashes or is answered wrong, and the suite stays green.
    Those two must be stale: Core may not decide on a plan whose context it
    cannot replay (§10.2, X24)."""
    r = Rig(db)
    os_and_ports.armed = False                                # currency is not the e-stop
    mid = r.mission()
    r.propose(mid, spec('t1', 'read'))
    pid = r.one(entities.Plan, mission_id=mid).id
    if case == 'no-package':
        db.writer.execute(_edit, dict(mutation(r, mid), table='plans', id_=pid,
                                      changes={'context_package_id': None}))
    elif case == 'pruned':
        out = db.writer.execute(retention.prune, {'now': '2099-01-01T00:00:00.000Z'})
        assert out['events'] > 0                              # the log really went away
    elif case == 'package-gone':
        with db.read() as conn:
            pkg = rows.get(conn, entities.Plan, pid).entity.context_package_id
        assert pkg is not None
        db.writer.execute(_drop_row, dict(mutation(r, mid), table='context_packages',
                                          id_=pkg))
    with db.read() as conn:
        mission = rows.get(conn, entities.Mission, mid).entity
        plan = rows.get(conn, entities.Plan, pid).entity
        assert (case == 'no-package') == (plan.context_package_id is None)
        ok, why = authorization.current(conn, mission, plan)
    assert ok is expected[0]
    assert expected[1] in why

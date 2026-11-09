"""T-704: the highest-risk uncovered branches of
`archeus/core/application/authorization.py` lines 1-560 — the fail-closed and
denial paths first (a DENY raised before anything is recorded, a tampered plan
never read as approved, dead or step-up-less approvals never covering a
dispatch, a denial of a policy that no longer denies, a plan decision with no
plan, the e-stop not judging the start itself), then the boundary values and
the error paths. Each test names the source branch it catches (the report
quotes them); none needs Windows, a process, the network or the OS beyond the
real SQLite database every unit test here already uses. The style is copied
from tests/v1/unit/test_gaps_core_application_executions.py and the Rig and
fixtures from tests/v1/integration/test_policy.py (via tests/v1/unit/
test_fix_authorization.py).
"""

import json
import os
from dataclasses import replace
from datetime import timedelta
from types import SimpleNamespace

import pytest

from archeus.core.application import authorization, commands, queries
from archeus.core.application.work import PolicyDenied
from archeus.core.domain import entities, ids
from archeus.core.domain.actions import Action
from archeus.core.domain.events import new_event
from archeus.core.domain.values import Ref
from archeus.core.policy import rules as R
from archeus.core.policy.engine import PolicyEngine
from archeus.infra import paths
from archeus.infra.db import Database, rows
from v1.integration.test_policy import Rig
from v1.integration.test_policy import task as task_spec

FUTURE = '2099-01-01T00:00:00.000Z'
PAST = '2000-01-01T00:00:00.000Z'
NOW = '2026-01-01T00:00:00.000Z'


class _StubPolicy:
    """A P3.5-style port: it answers a decision and a reason, with items or
    without them (both readings are `judge`'s)."""

    def __init__(self, decision='ALLOW', reason='stub says so', items=()):
        self.decision, self.reason, self.items = decision, reason, tuple(items)
        self.seen = []

    def evaluate(self, action, ctx):
        self.seen.append((action, dict(ctx)))
        return entities.PolicyDecision(id=ids.new_id('policy_decision'),
                                       decision=self.decision, reason=self.reason,
                                       action=action, items=self.items)


# ── the seeded world (same shape as test_gaps_core_application_executions.py) ──

def _setup(tx, *, mission, plan, task, user, rules, approvals, actor):
    for row in (user, mission, plan, task, *rules):
        if row is not None:
            tx.insert(row, actor=actor)
    for a in approvals:
        if a.action_hash == '0' * 64:      # the placeholder gets the real identity
            h = (authorization.plan_hash(tx.conn, plan) if a.kind == 'plan'
                 else authorization.task_hash(plan, task))
            a = replace(a, action_hash=h)
        tx.insert(a, actor=actor)
    tx.append(new_event('mission.updated', Ref('mission', mission.id), actor, payload={},
                        workspace=mission.workspace_id))


def _world(*, classes=('deploy',), capabilities=(), touches=(), plan_state='APPROVED',
           mission_state='EXECUTING', digest_ok=True, origin='api', with_user=True,
           user_id=None, rules=(), approvals=()):
    """One mission/plan/task row (plus a user, rules and approvals) on a real
    database, the plan's digest computed by the same validator dispatch uses."""
    db = Database.open()
    user_ref = Ref('user_device', ids.new_id('principal'))
    system_ref = Ref('system', ids.new_id('principal'))
    mid, pid, tid = (ids.new_id(k) for k in ('mission', 'plan', 'task'))
    u = entities.User(id=user_id or ids.new_id('user'), display_name='U') if with_user \
        else None
    mission = entities.Mission(id=mid, workspace_id=ids.GLOBAL_WORKSPACE, title='M',
                               objective='o', state=mission_state, origin=origin)
    task = entities.Task(id=tid, plan_id=pid, mission_id=mid, key='t1', title='T1',
                         kind='code_change', state='READY', action_classes=tuple(classes),
                         capabilities_required=tuple(capabilities), touches=tuple(touches))
    template = entities.Plan(id=pid, mission_id=mid, plan_version=1, summary='plan')
    from archeus.core.planning import validate
    dh = None if not digest_ok else validate.digest(template, [task])
    plan = entities.Plan(id=pid, mission_id=mid, plan_version=1, summary='plan',
                         state=plan_state, digest=dh)
    made = []
    for spec in approvals:
        items = tuple({'task': 't1', 'action': act.canonical_dict()}
                      for _c, _b, act in authorization.items_of(task))
        kind = spec.get('kind', 'task')
        step_up = spec.get('step_up', False)
        state = spec.get('state', 'APPROVED')
        expires = spec.get('expires', FUTURE)
        task_id = tid if kind == 'task' else None
        subject = {'task': Ref('task', tid), 'plan': Ref('plan', pid),
                   'action': Ref('execution', ids.new_id('execution'))}[kind]
        made.append(entities.Approval(id=ids.new_id('approval'), kind=kind, subject=subject,
                                      action_hash=spec.get('hash') or '0' * 64,
                                      requested_by=user_ref.id,
                                      step_up=step_up, mission_id=mid, plan_id=pid,
                                      plan_version=1, plan_digest=dh, task_id=task_id,
                                      items=items, expires_at=expires, state=state))
    db.writer.execute(_setup, {'mission': mission, 'plan': plan, 'task': task, 'user': u,
                               'rules': list(rules), 'approvals': made,
                               'actor': system_ref})
    return db, user_ref, system_ref, {'mid': mid, 'pid': pid, 'tid': tid}


def _tamper(tx, *, pid, actor):
    """Change one digested field of the plan row behind Core's back: exactly
    the tampering dispatch's recompute exists to catch."""
    body = json.loads(tx.execute('SELECT body FROM plans WHERE id = ?',
                                 (pid,)).fetchone()[0])
    body['summary'] = 'tampered by the test'
    tx.execute('UPDATE plans SET body = ? WHERE id = ?',
               (json.dumps(body, sort_keys=True), pid))
    tx.append(new_event('mission.updated', Ref('mission', 'm'), actor, payload={},
                        workspace=ids.GLOBAL_WORKSPACE))


def _bundle():
    policy = PolicyEngine()
    return {'policy': policy, 'missions': commands.Missions(policy=policy)}


def _check_dispatch(db, system_ref, k, bundle=None):
    return db.writer.execute(_dispatch_cmd, dict(k, actor=system_ref,
                                                 bundle=bundle or _bundle()))


def _dispatch_cmd(tx, *, actor, bundle, mid, pid, tid):
    m = rows.get(tx.conn, entities.Mission, mid).entity
    p = rows.get(tx.conn, entities.Plan, pid).entity
    t = rows.get(tx.conn, entities.Task, tid).entity
    return authorization.check_dispatch(tx, actor=actor, policy=bundle['policy'],
                                        missions=bundle['missions'], mission=m, plan=p,
                                        task=t)


def _row(db, kind, id_):
    with db.read() as r:
        return rows.get(r, kind, id_)


def _decisions(db, **eq):
    with db.read() as r:
        return [x.entity for x in rows.where(r, entities.PolicyDecision, **eq)]


def _events(db, type_, subject_id=None):
    with db.read() as r:
        return [ev for ev in queries.events(r)
                if ev['type'] == type_
                and (subject_id is None or ev['subject']['id'] == subject_id)]


def _visibility(db, type_, subject_id):
    with db.read() as r:
        return [v[0] for v in r.execute(
            'SELECT visibility FROM events WHERE type = ? AND subject_id = ?',
            (type_, subject_id))]


# ── fail-closed and denial paths ─────────────────────────────────────────────

def test_a_denied_task_raises_before_anything_is_recorded():
    """authorization.py:521-527 — `if i['decision'] == 'DENY': raise
    PolicyDenied(...)` before any insert. Without the raise-first (or with a
    record before it) a dispatch the policy forbids would leave a decision, an
    approval or a block behind, exactly what P3.5/§12.2 says must write nothing."""
    db, _u, sys_ref, k = _world(classes=('destructive',))
    try:
        with pytest.raises(PolicyDenied) as e:
            _check_dispatch(db, sys_ref, k)
        assert e.value.task_key == 't1'
        assert _decisions(db, mission_id=k['mid']) == []
        assert _events(db, 'approval.requested') == []
        assert _row(db, entities.Mission, k['mid']).entity.state == 'EXECUTING'
    finally:
        db.close()


def test_a_tampered_plan_is_never_the_approved_plan_and_its_dispatch_is_denied():
    """authorization.py:186-190 (`intact`: `bool(plan.digest) and validate.digest(...)
    == plan.digest`) feeding authorization.py:541-548 (`if not whole: ... outcome
    'denied' ... 'digest_mismatch'` and the block) and authorization.py:243-250
    (`plan_approval_state` returns None for a plan that does not recompute).
    Dropping the recompute makes a tampered plan dispatch under its old approval."""
    db, _u, sys_ref, k = _world(approvals=[{'kind': 'task', 'step_up': True},
                                           {'kind': 'plan'}])
    try:
        with db.read() as r:
            plan = rows.get(r, entities.Plan, k['pid']).entity
            assert authorization.intact(r, plan) is True
            # the plan approval exists and reads APPROVED while the plan is intact
            assert authorization.plan_approval_state(r, plan) == 'APPROVED'
        db.writer.execute(_tamper, {'pid': k['pid'], 'actor': sys_ref})
        with db.read() as r:
            plan = rows.get(r, entities.Plan, k['pid']).entity
            assert authorization.intact(r, plan) is False
            # ...and is None once it does not recompute: no approval of a tampered
            # plan (the mission `approve` guard would approve THAT, D10)
            assert authorization.plan_approval_state(r, plan) is None
        out = _check_dispatch(db, sys_ref, k)
        assert out['outcome'] == 'denied' and out['why'] == 'digest_mismatch'
        (d,) = _decisions(db, mission_id=k['mid'])
        assert (d.decision, d.outcome, d.stage) == ('DENY', 'denied', 'dispatch')
        assert _row(db, entities.Mission, k['mid']).entity.state == 'BLOCKED'
    finally:
        db.close()


def test_a_plan_without_a_digest_is_not_intact():
    """authorization.py:190 — `bool(plan.digest) and ...`: a plan row with no
    digest at all must not count as intact (a falsy digest short-circuits the
    recompute); `plan_approval_state` (243-246) answers None for it."""
    db, _u, _s, k = _world(digest_ok=False)
    try:
        with db.read() as r:
            plan = rows.get(r, entities.Plan, k['pid']).entity
            assert authorization.intact(r, plan) is False
            assert authorization.plan_approval_state(r, plan) is None
    finally:
        db.close()


@pytest.mark.parametrize('plan_state,step_up,expect', [
    ('APPROVED', True, 'covered'),
    ('APPROVED', False, 'asked'),
    ('PROPOSED', True, 'covered'),
    ('PROPOSED', False, 'asked')],
    ids=['approved-step', 'approved-plain', 'proposed-step', 'proposed-plain'])
def test_an_approval_covers_a_dispatch_only_for_exactly_its_items_and_step_up(
        plan_state, step_up, expect):
    """authorization.py:492-497 (`_covers`: `want in [dict(x) for x in a.items]
    and (a.step_up or not step_up)`) and 531-540 (`plan_ok or task_granted`).
    Inverting the step-up conjunct lets a plain approval authorise a deploy
    that today's policy demands a step-up for; dropping `task_granted` makes a
    task-lifetime approval useless (§8.4)."""
    db, _u, sys_ref, k = _world(plan_state=plan_state,
                                approvals=[{'kind': 'task', 'step_up': step_up}])
    try:
        out = _check_dispatch(db, sys_ref, k)
        assert out['outcome'] == expect
        (d,) = _decisions(db, mission_id=k['mid'])
        # the deploy item stays ASK as judged; only the OUTCOME differs (§12.2)
        assert (d.decision, d.outcome) == ('ASK', expect)
        if expect == 'covered':
            assert d.items[0]['covered_by'] is not None
            assert _row(db, entities.Mission, k['mid']).entity.state == 'EXECUTING'
        else:
            assert d.items[0]['decision'] == 'ASK'
            assert out['approval_id'] is not None
            assert _row(db, entities.Mission, k['mid']).entity.state == 'BLOCKED'
    finally:
        db.close()


def test_the_same_task_asked_twice_finds_the_same_approval_row():
    """authorization.py:368-371 (`request`: `got = live_approval(tx.conn, h); if
    got is not None: return got.entity, False`). Without the reuse the same
    request replayed would ask the user twice for one identity (§19)."""
    db, _u, sys_ref, k = _world()
    try:
        b = _bundle()
        first = _check_dispatch(db, sys_ref, k, b)
        # the mission goes back to EXECUTING the way Core brings a blocked
        # mission back (the task ask blocked it); the SAME request replays
        db.writer.execute(b['missions'].fire, {'mission_id': k['mid'], 'trigger': 'unblock',
                                               'reason': 'test', 'actor': sys_ref})
        db.writer.execute(b['missions'].fire, {'mission_id': k['mid'],
                                               'trigger': 'redispatch', 'reason': 'test',
                                               'actor': sys_ref})
        again = _check_dispatch(db, sys_ref, k, b)
        assert first['outcome'] == again['outcome'] == 'asked'
        assert first['approval_id'] == again['approval_id']
        with db.read() as r:
            got = [x.entity for x in rows.where(r, entities.Approval, mission_id=k['mid'])]
        assert len(got) == 1 and got[0].state == 'PENDING'
        assert len(_events(db, 'approval.requested')) == 1
    finally:
        db.close()


@pytest.mark.parametrize('case', ['pending', 'superseded', 'expired-action',
                                  'task-no-expiry'],
                         ids=['pending', 'superseded', 'expired', 'task-lifetime'])
def test_only_a_live_unexpired_approval_is_usable(case):
    """authorization.py:237-241 (`live_approval`: `if r.entity.state in LIVE`, a
    PENDING or SUPERSEDED row is not the live one) and 499-506 (`_usable`: the
    state must be APPROVED, and `a.kind == 'action' and a.expires_at <= now`
    refuses an expired single-use one). Inverted, a dead approval (PENDING,
    SUPERSEDED, or an action approval past its TTL) would cover a dispatch; a
    task-lifetime approval is NOT bound by expires_at (§8.4)."""
    spec = {'pending': dict(state='PENDING'),
            'superseded': dict(state='SUPERSEDED'),
            'expired-action': dict(kind='action', state='APPROVED', expires=PAST),
            'task-no-expiry': dict(state='APPROVED', expires=PAST)}[case]
    db, _u, _s, k = _world(approvals=[spec])
    try:
        task = _row(db, entities.Task, k['tid']).entity
        plan = _row(db, entities.Plan, k['pid']).entity
        h = authorization.task_hash(plan, task)
        with db.read() as r:
            live = authorization.live_approval(r, h)
            usable = authorization._usable(r, h, NOW)
        if case == 'pending':
            assert usable is None                       # live but not APPROVED
            assert live.entity.state == 'PENDING'
        elif case == 'superseded':
            assert live is None and usable is None      # a dead row is not live
        elif case == 'expired-action':
            assert usable is None                       # its own TTL had passed
        else:
            assert usable is not None and usable.kind == 'task'
    finally:
        db.close()


def test_the_estop_holds_what_runs_never_what_starts():
    """authorization.py:228-230 (`judge_start` judges with `dict(ctx, estop=False)`
    while `ctx` keeps the true state). With the override removed, an armed
    e-stop would DENY `mission.start` itself (engine step 0) and a mission
    created while disarmed could never start again while the sentinel is there."""
    db, _u, _s, k = _world(origin='api')
    os.makedirs(paths.run_dir(), exist_ok=True)
    open(paths.stop_sentinel(), 'w').close()
    try:
        mission = _row(db, entities.Mission, k['mid']).entity
        with db.read() as r:
            items, ctx = authorization.judge_start(PolicyEngine(), r, mission, now=NOW)
        assert ctx['estop'] is True                     # recorded as judged armed
        assert items[0]['decision'] == 'ALLOW'          # never DENY for being armed
    finally:
        db.close()


def test_a_chat_mission_is_asked_before_it_starts():
    """authorization.py:231-234 (`if items[0]['decision'] == 'ALLOW' and
    asks_before_start(...): decision='ASK'`). Dropped, a mission born from a
    chat message would start without the B6 ask."""
    db, _u, _s, k = _world(origin='conversation')
    try:
        mission = _row(db, entities.Mission, k['mid']).entity
        with db.read() as r:
            items, ctx = authorization.judge_start(PolicyEngine(), r, mission, now=NOW)
        assert items[0]['decision'] == 'ASK'
        assert items[0]['reason'] == 'a mission from a chat message asks before it starts'
        assert ctx['stage'] == 'start'
    finally:
        db.close()


# ── a denial is only recorded when it is still a denial ───────────────────────

def _rig():
    db = Database.open()
    return db, Rig(db)


def test_a_denial_the_policy_no_longer_denies_is_not_recorded():
    """authorization.py:459-461 (`if not denied: return {'recorded': False,
    'why': 'the policy no longer denies this plan'}`) — the re-judge in THIS
    transaction. Removed, a mission whose policy changed in between would be
    blocked by a denial the current policy does not give."""
    db, r = _rig()
    try:
        mid = r.mission()                                # REASONING, no plan yet
        out = r.do(r.authz.record_plan_denial, mission_id=mid,
                   specs=[task_spec('t1', 'deploy')])
        assert out == {'recorded': False, 'why': 'the policy no longer denies this plan'}
        assert r.m(mid).state == 'REASONING' and r.m(mid).planning_blocked is None
        assert r.all(entities.PolicyDecision, mission_id=mid) == []
        assert r.all(entities.Plan, mission_id=mid) == []
    finally:
        db.close()


def test_a_denial_in_planning_waits_in_place_without_the_block_move():
    """authorization.py:470-476 — the `else:` of `if m.state == 'REASONING'`:
    `tx.update(... {'planning_blocked': ...})` plus `mission.updated`, and the
    returned state stays PLANNING. Replacing the else with the REASONING fire
    would move a mission that is mid-replan (P8 D6) to BLOCKED via
    `plan_denied`, which has no such edge from PLANNING."""
    db, r = _rig()
    try:
        mid = r.mission()
        r.propose(mid, task_spec('t1', 'deploy'))
        r.decide(r.pending(mid), 'request_changes')
        assert r.m(mid).state == 'PLANNING'
        out = r.do(r.authz.record_plan_denial, mission_id=mid,
                   specs=[task_spec('t2', 'destructive')])
        assert out['recorded'] is True and out['state'] == 'PLANNING'
        m = r.m(mid)
        assert m.state == 'PLANNING'
        assert m.planning_blocked['kind'] == 'policy'
        assert m.planning_blocked['denied'][0]['class'] == 'destructive'
        (d,) = r.all(entities.PolicyDecision, mission_id=mid, decision='DENY')
        assert d.outcome == 'denied'
        assert m.planning_blocked['policy_decision_id'] == d.id
        assert [e['payload'].get('trigger') for e in r.events('mission.state_changed')][-1] \
            != 'plan_denied'
    finally:
        db.close()


# ── a plan decision with no plan of its own to authorise ─────────────────────

def _facts(plan_version):
    return SimpleNamespace(plan_version=plan_version, evaluated=(),
                           cost_within_ceiling=True, explicit_plan_approval=False)


def _plan_decision_cmd(tx, *, actor, mid, trigger, facts):
    m = rows.get(tx.conn, entities.Mission, mid).entity
    return authorization.record_plan_decision(tx, actor=actor, mission=m, trigger=trigger,
                                              facts=facts)


def test_a_plan_decision_with_no_matching_plan_records_nothing():
    """authorization.py:405-408 (`if prow is None or prow.entity.plan_version !=
    facts.plan_version or not prow.entity.digest: return None`). Without it a
    decision on scripted facts (the P3 lifecycle path, and a stale plan gate
    race) would record a PolicyDecision — and in the auto case fire `approved`
    — for a plan that is not in the database."""
    db, r = _rig()
    try:
        mid = r.mission()                                # REASONING, no plan at all
        out = r.db.writer.execute(_plan_decision_cmd, {
            'actor': r.system, 'mid': mid, 'trigger': 'plan_needs_approval',
            'facts': _facts(1)})
        assert out is None
        assert r.all(entities.PolicyDecision, mission_id=mid) == []
        r.propose(mid, task_spec('t1', 'deploy'))
        before = len(r.all(entities.PolicyDecision, mission_id=mid))
        out = r.db.writer.execute(_plan_decision_cmd, {   # a stale version: the guard
            'actor': r.system, 'mid': mid, 'trigger': 'plan_needs_approval',
            'facts': _facts(2)})                          # judged v2, the row is v1
        assert out is None
        assert len(r.all(entities.PolicyDecision, mission_id=mid)) == before
    finally:
        db.close()


# ── the recorded decision: dedup, visibility, the true e-stop ─────────────────

def _record_cmd(tx, *, actor, mid):
    m = rows.get(tx.conn, entities.Mission, mid).entity
    action = {'class': 'deploy', 'target': 'task:t1'}
    i1 = {'decision': 'DENY', 'class': 'deploy', 'action': action, 'task': 't1',
          'matched': [{'id': 'r1', 'decision': 'DENY', 'keep': 1},
                      {'id': 'r2', 'decision': 'ASK'}],
          'effective': ['r1'], 'deciding_rule': 'r1', 'conflicts': [], 'boundary': None,
          'checks': None, 'step_up': True}
    i2 = {'decision': 'ASK', 'class': 'deploy', 'action': action, 'task': 't1',
          'matched': [{'id': 'r1', 'decision': 'ASK', 'keep': 2}],
          'effective': [], 'deciding_rule': 'r1', 'conflicts': [], 'boundary': None,
          'checks': None, 'step_up': True}
    d1 = authorization.record(tx, actor=actor, stage='plan', mission=m, decision='DENY',
                              outcome='denied', items=[i1, i2], reason='no',
                              ctx={'estop': True, 'profiles': {'USER': 'standard'},
                                   'policy_version': 'pv'})
    d2 = authorization.record(tx, actor=actor, stage='plan', mission=m, decision='ALLOW',
                              outcome='covered', items=[dict(i1, decision='ALLOW')],
                              reason='yes', ctx={})
    return {'d1': d1.id, 'd2': d2.id, 'matched': [r['id'] for r in d1.matched_rules],
            'first_snapshot': d1.matched_rules[0]['decision'],
            'items': [list(i['matched']) for i in d1.items], 'estop': d1.estop,
            'subject': [d1.subject.kind, d1.subject.id], 'profiles': d1.profiles,
            'policy_version': d1.policy_version, 'pv2': d2.policy_version}


def test_a_recorded_decision_deduplicates_rules_by_id_and_shares_only_denials():
    """authorization.py:277-282 (record: `matched` deduped by `r['id']`, the
    FIRST snapshot kept) and 301 (`visibility='user' if decision in ('ASK','DENY')
    else 'system'`). Without the dedup the same rule id appears twice and a
    later snapshot could overwrite the deciding one; with the visibility
    inverted, a DENY is hidden from the user and an ALLOW floods them."""
    db, _u, sys_ref, k = _world()
    try:
        out = db.writer.execute(_record_cmd, {'actor': sys_ref, 'mid': k['mid']})
        assert out['matched'] == ['r1', 'r2']
        assert out['first_snapshot'] == 'DENY'            # the first r1 wins, not 'ASK'
        assert out['items'] == [['r1', 'r2'], ['r1']]      # items keep ids only
        assert out['estop'] is True
        assert out['subject'] == ['mission', k['mid']]     # task/plan fall back to mission
        assert out['profiles'] == {'USER': 'standard'} and out['policy_version'] == 'pv'
        assert out['pv2'] is None                          # ctx defaults, not leaked
        assert _visibility(db, 'policy_decision.created', out['d1']) == ['user']
        assert _visibility(db, 'policy_decision.created', out['d2']) == ['system']
    finally:
        db.close()


# ── supersede: nothing carries to the next plan version ───────────────────────

def _supersede_cmd(tx, *, actor, pid):
    authorization.supersede_for(tx, actor=actor, plan_id=pid, replaced_by=2)
    return True


def test_a_superseded_plan_leaves_no_live_approval_behind():
    """authorization.py:483-489 (`supersede_for`: every LIVE approval of the
    plan fires `plan_replaced`). If the `state in LIVE` filter or the plan_id
    filter breaks, either an already-decided approval is crashed with
    IllegalTrigger or a live approval of the OLD version survives to cover the
    next one (D14 says nothing carries)."""
    db, _u, sys_ref, k = _world(approvals=[{'kind': 'task', 'state': 'PENDING',
                                            'hash': '1' * 64},
                                           {'kind': 'task', 'state': 'APPROVED',
                                            'hash': '2' * 64},
                                           {'kind': 'task', 'state': 'REJECTED',
                                            'hash': '3' * 64}])
    try:
        # one more approval, of ANOTHER (real, v2) plan: it must be left alone
        other_plan = entities.Plan(id=ids.new_id('plan'), mission_id=k['mid'],
                                   plan_version=2, summary='other', state='SUPERSEDED')
        db.writer.execute(_add_row, {'row': other_plan, 'actor': sys_ref})
        other = entities.Approval(id=ids.new_id('approval'), kind='task',
                                  subject=Ref('task', k['tid']), action_hash='4' * 64,
                                  expires_at=FUTURE,
                                  requested_by=sys_ref.id, mission_id=k['mid'],
                                  plan_id=other_plan.id, plan_version=9,
                                  plan_digest='a' * 64, state='PENDING')
        db.writer.execute(_add_row, {'row': other, 'actor': sys_ref})
        db.writer.execute(_supersede_cmd, {'actor': sys_ref, 'pid': k['pid']})
        with db.read() as r:
            states = sorted(x.entity.state for x in rows.where(r, entities.Approval,
                                                               plan_id=k['pid']))
            untouched = rows.get(r, entities.Approval, other.id).entity.state
        assert states == ['REJECTED', 'SUPERSEDED', 'SUPERSEDED']
        assert untouched == 'PENDING'
    finally:
        db.close()


def _add_row(tx, *, row, actor):
    tx.insert(row, actor=actor)
    tx.append(new_event('mission.updated', Ref('mission', row.mission_id), actor,
                        payload={}, workspace=ids.GLOBAL_WORKSPACE))


# ── fail-closed inputs: rule expiry, owner, the active-rule set ───────────────

@pytest.mark.parametrize('bad', ['2099-01-01T00:00:00', 'noon', 1700000000, ['x'],
                                 '2099-13-01T00:00:00Z'],
                         ids=['naive', 'word', 'number', 'list', 'bogus-month'])
def test_a_rule_expiry_must_be_a_whole_timestamp_or_the_rule_is_refused(bad):
    """authorization.py:84-93 (`_expiry`: a non-string raises through the
    AttributeError catch, and `at is None or at.tzinfo is None` raises before
    the engine could compare a naive stamp as a string). Passing a naive one
    through would make a temporary DENY rule expire (or never expire) at the
    mercy of string comparison."""
    with pytest.raises(ValueError, match='expires_at'):
        authorization._expiry(bad)


def test_a_rule_expiry_is_normalised_to_the_utc_form_the_engine_compares():
    """authorization.py:84-93 (`return _iso(at.astimezone(timezone.utc))`): a
    non-UTC offset must land in the same form `now` has, or a rule could be
    expired for one reader and active for another."""
    assert authorization._expiry(None) is None
    assert authorization._expiry('2099-01-01T02:00:00+02:00') == \
        '2099-01-01T00:00:00.000Z'


def test_an_empty_database_has_no_owner_and_the_standard_profile():
    """authorization.py:95-97 (`owner`: None when there is no User row) and
    128-133 (`context`: `u.id if u else None`, `u.autonomy_profile if u else
    'standard'`, `None if actor is None else ...`). Without the fallbacks an
    api-created mission with no user row would crash the plan gate with an
    AttributeError instead of judging under the standard profile."""
    db = Database.open()
    try:
        mission = entities.Mission(id=ids.new_id('mission'),
                                   workspace_id=ids.GLOBAL_WORKSPACE, title='M',
                                   objective='o')
        rule = {'id': 'extra-1', 'scope_level': 'GLOBAL', 'action_class': 'deploy',
                'decision': 'ASK'}
        with db.read() as r:
            assert authorization.owner(r) is None
            assert authorization.user_rules(r) == []
            ctx = authorization.context(r, mission, stage='plan', now=NOW,
                                        extra_rules=[rule])
        assert ctx['chain']['USER'] is None and ctx['chain']['MISSION'] == mission.id
        assert ctx['chain']['TASK'] is None
        assert ctx['profiles'] == {'USER': 'standard', 'MISSION': None}
        assert ctx['actor'] is None and ctx['plan_version'] is None
        assert ctx['estop'] is False
        assert ctx['rules'] == [rule] and ctx['rules'][0] is not rule   # copies (§D35)
        assert ctx['policy_version'] == authorization.policy_version([rule])
    finally:
        db.close()


def test_retired_rules_are_not_the_active_policy():
    """authorization.py:100-103 (`user_rules`: `if r.entity.retired_at is None`).
    Dropping the filter keeps a retired DENY in `context`'s rules — and since
    a DENY is locked and USER-user is the deepest level, a retired DENY would
    silently win over the profile and deny what the user un-retired."""
    uid = ids.new_id('user')
    retired = entities.PolicyRule(id=ids.new_id('policy_rule'), scope_level='USER',
                                  scope_ref=uid, action_class='deploy', decision='DENY',
                                  retired_at='2026-01-01T00:00:00.000Z')
    db, _u, _s, k = _world(user_id=uid, rules=[retired])
    try:
        with db.read() as r:
            assert authorization.owner(r).id == uid
            assert [x['id'] for x in authorization.user_rules(r)] == []
            mission = rows.get(r, entities.Mission, k['mid']).entity
            ctx = authorization.context(r, mission, stage='plan', now=NOW)
            assert ctx['rules'] == []
        # and the engine, fed by context, must ASK (profile), not DENY
        out = db.writer.execute(_judge_deploy, {'actor': _s, 'mid': k['mid'],
                                                'uid': uid})
        assert out == 'ASK'
    finally:
        db.close()


def _judge_deploy(tx, *, actor, mid, uid):
    m = rows.get(tx.conn, entities.Mission, mid).entity
    items, _ctx = authorization.evaluate_task(PolicyEngine(), tx.conn, m, 't1', ('deploy',),
                                              now=tx.now)
    return items[0]['decision']


def test_the_policy_version_ignores_rule_order_and_moves_with_the_rules(monkeypatch):
    """authorization.py:106-111 (`policy_version`: sorted by id over the rules
    plus PROFILES_VERSION and ENGINE_VERSION). Without the sort the same two
    rules in another order would be a different policy_version (every approval
    "stale"); dropping the engine/profile fields hides a version bump that
    changes what the rules mean (§7.2)."""
    a, b = {'id': 'a', 'decision': 'ASK'}, {'id': 'b', 'decision': 'DENY'}
    v1 = authorization.policy_version([a, b])
    assert v1 == authorization.policy_version([b, a])
    assert v1 != authorization.policy_version([a])
    assert len(v1) == 64
    monkeypatch.setattr(R, 'ENGINE_VERSION', R.ENGINE_VERSION + 1)
    assert authorization.policy_version([a, b]) != v1


# ── the small pure pieces the commands lean on ────────────────────────────────

def test_the_overall_decision_is_the_strictest_item_and_allow_when_empty():
    """authorization.py:309-310 (`_overall`: `max(..., key=R.STRICTNESS.get,
    default='ALLOW')`). Without the default an empty plan crashes the gate;
    without the strictness key a DENY item could be the loser."""
    assert authorization._overall([]) == 'ALLOW'
    got = authorization._overall([{'decision': 'ALLOW'}, {'decision': 'ASK'},
                                  {'decision': 'ALLOW_WITHIN_BOUNDARY'}])
    assert got == 'ASK'
    assert authorization._overall([{'decision': 'ALLOW_WITHIN_BOUNDARY'},
                                   {'decision': 'DENY'}]) == 'DENY'


def test_a_stub_policy_answer_with_no_items_still_becomes_a_judged_item():
    """authorization.py:156-163 (`judge`: `d.items[0] if d.items else {...}`
    with deciding_rule None, step_up False). A P3.5 stub answers only decision
    and reason; without the fallback every stub answer raises IndexError, and
    with `step_up` defaulting True every stub ask would demand a PIN."""
    stub = _StubPolicy(decision='DENY', reason='stub')
    action = Action(action_class='deploy', target='task:t1')
    got = authorization.judge(stub, action, {'stage': 'plan'})
    assert got['decision'] == 'DENY' and got['reason'] == 'stub'
    assert got['class'] == 'deploy' and got['action'] == action.canonical_dict()
    assert got['matched'] == [] and got['deciding_rule'] is None
    assert got['step_up'] is False and got['checks'] is None
    full = _StubPolicy(decision='ASK', reason='r',
                       items=[{'decision': 'ALLOW', 'class': 'deploy', 'step_up': False}])
    got2 = authorization.judge(full, action, {'stage': 'plan'})
    assert got2['decision'] == 'ASK'          # the port's decision wins the item's
    assert got2['step_up'] is False


def test_task_items_name_each_class_once_with_what_a_capability_implies():
    """authorization.py:141-147 (`task_items`: `dict.fromkeys` dedup, `IMPLIED`
    with `implied_by`, `tuple(touches) or None`). A declared class appearing
    twice would ask (and authorise) it twice; an empty touches must be None
    (unknown paths), never the empty tuple the boundary check reads as 'no
    paths allowed'."""
    items = authorization.task_items('t1', ('read', 'read', 'write_repo'),
                                     capabilities=('shell', 'web', 'shell'),
                                     touches=())
    assert [(c, b) for c, b, _a in items] == [('read', None), ('write_repo', None),
                                              ('exec', 'shell'), ('web', 'web')]
    action = items[0][2]
    assert action.paths is None and action.target == 'task:t1'
    (one,) = authorization.task_items('t1', ('read',), touches=['src/**'])
    assert one[2].paths == ('src/**',)


def test_the_canonical_item_renames_class_back_to_an_action():
    """authorization.py:564-568 (`_action_kwargs`: `k['action_class'] =
    k.pop('class')`), used by the DENI path's Action rebuild (525) and by the
    action stage. Without the rename a recorded canonical dict would raise
    TypeError on `Action(**...)` — the fail-closed raise would become a 500."""
    canonical = {'class': 'deploy', 'target': 'task:t1', 'paths': ['src/**']}
    a = Action(**authorization._action_kwargs(canonical))
    assert a.action_class == 'deploy' and a.paths == ('src/**',)
    assert 'class' not in authorization._action_kwargs(canonical)


def test_the_clock_helpers_write_the_form_every_expiry_compares():
    """authorization.py:70-79 (`_iso`/`_parse`/`_plus`): `expires_at <= now`
    is a plain string comparison downstream (`_usable`, the engine's expiry),
    so the millisecond `Z` form here is a hard contract."""
    assert authorization._iso(authorization._parse('2026-01-01T00:00:00.000Z')) == \
        '2026-01-01T00:00:00.000Z'
    assert authorization._plus('2026-01-01T22:00:00.000Z', timedelta(hours=2)) == \
        '2026-01-02T00:00:00.000Z'


def test_the_start_hash_binds_the_mission_and_nothing_else():
    """authorization.py:200-222 (`bind`/`start_hash`): the start identity is
    the mission alone (P19 B6). If a plan or task field ever rode into the
    binding, a replan would silently invalidate (or, worse, silently redirect)
    a start approval."""
    m = entities.Mission(id=ids.new_id('mission'), workspace_id=ids.GLOBAL_WORKSPACE,
                         title='M', objective='o')
    h1 = authorization.start_hash(m)
    assert h1 == authorization.start_hash(m)
    assert h1 != authorization.start_hash(replace(m, id=ids.new_id('mission')))
    assert authorization.start_action(m).action_class == 'mission.start'

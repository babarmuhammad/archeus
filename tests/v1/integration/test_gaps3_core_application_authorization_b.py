"""T-1144: the highest-risk uncovered branches of
`archeus/core/application/authorization.py` lines 400-788 (the deciding half:
`record_plan_decision`, `record_plan_denial`, `_step_up_valid`, `_awaiting`,
`ineligible`, `_restores_cause`, `decide`, `_approve`).

The ten probes the card listed are ALL covered by existing tests (I_A15,
I_A19/gaps_b GAP2, t150/I_A05, I_A11/t150, I_A08b/t150, gaps_a, I_A13, I_A03,
gaps_a's LIVE filter), so each test here targets the nearest UNCOVERED branch
instead, named in its comment. In order (denials and fail-closed first, then
the stale-authority paths, then the boundary, then the error path):

 1. `_approve` kind `start` re-judged DENY at approve time (L736-737, L754-761):
    a start approval whose policy turned to DENY is answered `denied`, the
    approval stays PENDING, the mission never starts. (closest: gaps_b GAP1,
    the same branch for kind `action`; I_A17 only approves/denies plans)
 2. `_awaiting` kind `route` when the task left AWAITING_APPROVAL (L605-608 via
    L642-643): `not_awaiting`, nothing written. (closest: I_F2/F3, the happy
    route approve/reject with the task still awaiting)
 3. `_step_up_valid` with TWO paired devices where only one proves its PIN
    (L595, `all()` over more than one row). (closest: I_A19/gaps_b GAP2, a
    single paired device, where `all()` cannot tell per-device from any-device)
 4. `record_plan_denial` on a mission outside PLANNING_STATES (L456-457): the
    early return records nothing. (closest: I_G3/G3b/G3c, all in-planning states)
 5. `record_plan_decision` on the third operand `not prow.entity.digest`
    (L409): a plan row without a digest is never auto-approved nor recorded.
    (closest: T-704's prow-None and plan_version operands of the same line)
 6. `ineligible` `plan.digest != a.plan_digest` while the plan IS intact
    (L635-636, the approval side of the comparison). (closest: I_A06/t150, the
    plan side, where `intact` fails first and this operand is never the reason)
 7. `ineligible` `plan is None` / `plan.id != a.plan_id` (L634-635): a second
    plan row in force, then none. (closest: I_A08b, the state operand of the
    same return, with the approval's own row in force)
 8. `ineligible` the approval's task row is GONE (L640, the `t is None`
    short-circuit — retention pruned it). (closest: t150's
    `_s_task_no_longer_in_force`, which always keeps a REAL foreign task and so
    only ever runs the `plan_id !=` operand)
 9. `ineligible` the expiry boundary: `a.expires_at <= now` at exact equality
    (L626-627) — expired — and one millisecond of life (L627 not taken).
    (closest: t150 `_s_expired` a second in the past, I_A11 well expired)
10. `_restores_cause` (L651-660) around `tx.cause = caused_by(e)` (L703 reject,
    L772 approve): a decision that raises leaves the command's own cause on the
    transaction, and a decided one keeps its approval chain out of the
    caller's later events while its own issued events still carry it. (no
    existing test reads `tx.cause` or a later event's cause_chain at all)

Nothing here imports another test_gaps3 file; the Rig and `task` come from
tests/v1/integration/test_policy.py and the tamper/world patterns are copied
from tests/v1/unit/test_gaps_core_application_authorization_b.py as the
sibling gap files do. Every command goes through the real writer.
"""

import json
import sqlite3
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from archeus.core import ports
from archeus.core.application import authorization, commands, lifecycle, queries, work
from archeus.core.application.authorization import NotEligible
from archeus.core.domain import entities, ids
from archeus.core.domain.events import new_event
from archeus.core.domain.values import Ref
from archeus.core.planning import validate
from archeus.infra import paths
from archeus.infra.db import rows
from v1.integration.test_policy import Rig
from v1.integration.test_policy import task as task_spec

PAST = '2000-01-01T00:00:00.000Z'
FUTURE = '2099-01-01T00:00:00.000Z'


# ── helpers (patterns copied from gaps_b and t150, as the card directs) ──────

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


def _ms_after(ts, ms):
    d = datetime.strptime(ts, '%Y-%m-%dT%H:%M:%S.%fZ') + timedelta(milliseconds=ms)
    return d.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'


def _chain(db, event_id):
    with db.read() as c:
        raw = c.execute('SELECT cause_chain FROM events WHERE id = ?',
                        (event_id,)).fetchone()[0]
    return json.loads(raw) if raw else []


def _insert_rows(tx, *, actor, new_rows, mission_id):
    """Insert pre-built entity rows in one real transaction — they hold states
    the machines have no edge to, so they are inserted, not fired (the `_world`
    pattern of the sibling gap files) — and append the event the writer
    requires for a mutation."""
    for e in new_rows:
        tx.insert(e, actor=actor)
    tx.append(new_event('mission.updated', Ref('mission', mission_id), actor,
                        payload={'test': 'rows seeded'}))
    return [e.id for e in new_rows]


def _created(r, title='M', **kw):
    return r.do(commands.create_mission, who=r.user, title=title, objective='o',
                success_criteria=[{'text': 'the result passes its automatic check',
                                   'check': 'automatic'}], **kw)['id']


def _dispatchable(r, mid):
    """APPROVED -> EXECUTING with its first task READY (test_policy's helper)."""
    r.do(r.missions.fire, mission_id=mid, trigger='dispatch', reason='go')
    r.do(r.work.ready_tasks, mission_id=mid)


def _waiting_plan_approval(rig):
    """A mission waiting in APPROVAL_REQUIRED on a `deploy` plan approval —
    the engine's ASK, so the approval asks for a step-up too (gaps_b's)."""
    mid = rig.mission()
    rig.propose(mid, task_spec('t1', 'deploy'))
    return mid, rig.pending(mid)


def _asked_task_approval(rig):
    """A mission BLOCKED on a task approval: dispatch asked (gaps_b's)."""
    mid = rig.mission()
    rig.propose(mid, task_spec('t1', 'write_repo'))
    _dispatchable(rig, mid)
    rig.rule('MISSION', 'write_repo', 'ASK', scope_ref=mid)
    out = rig.run_task(mid)
    assert out['authorization']['outcome'] == 'asked'
    return mid, rig.pending(mid)


def _paired(rig, *, name, token_hash, pin):
    """A client registered the way P15 registers one (gaps_b's `paired`), and
    its device row's id too — the row this file turns against its principal.
    hash_pin runs on the test thread, exactly as the HTTP thread does it."""
    out = rig.do(commands.register_device, name=name, platform='ios', origin='paired',
                 token_hash=token_hash, scopes=('observe', 'approve'),
                 pin_hash=commands.hash_pin(pin))
    return Ref('user_device', out['principal_id']), out['device_id']


@pytest.fixture
def rig(db):
    return Rig(db)


# ── 1. a start approval the policy now DENIES is answered denied ─────────────
# `decide` -> `_approve`, kind `start`: `judge_start` again (L736-737), the DENY
# branch (L754-761). No existing test reaches it for kind `start`: gaps_b GAP1
# drives the branch for kind `action`, I_A17 only ever approves or rejects a
# PLAN approval while its policy still allows.

def test_a_start_approval_the_policy_has_since_denied_is_answered_denied(db):
    r = Rig(db, policy=ports.FixedPolicy(by_class={'mission.start': 'ASK'}))
    mid = _created(r, origin='conversation')             # a chat mission asks first
    assert r.do(r.authz.gate_start, mission_id=mid)['waiting'] == 'approval_required'
    a = r.pending(mid)
    assert (a.kind, a.state) == ('start', 'PENDING')
    r.policy.by_class['mission.start'] = 'DENY'          # the policy hardened after
    head = r.head()
    out = r.decide(a)                                    # the user answers approve anyway
    assert (out['state'], out['changed']) == ('PENDING', False)
    assert 'DENY is never approvable' in out['denied']['reason']
    denied = [d for d in r.all(entities.PolicyDecision, mission_id=mid)
              if d.outcome == 'denied']
    (d,) = denied                                      # ...the one record the denial is
    assert (d.stage, d.decision, d.approval_id) == ('start', 'DENY', a.id)
    assert r.head() == head + 1                          # and exactly one event: nothing
    #   else fired — no approve, no start
    assert not [e for e in r.events('approval.state_changed') if e['subject_id'] == a.id]
    assert not [e for e in r.events('mission.state_changed') if e['subject_id'] == mid]
    assert r.one(entities.Approval, id=a.id).state == 'PENDING'
    assert r.m(mid).state == 'CREATED'                   # and it never started


# ── 2. a route approval whose task stopped awaiting cannot be decided ───────
# `ineligible` -> `_awaiting`, kind `route` (L605-608) through L642-643, with
# the task no longer AWAITING_APPROVAL. I_F2/F3 only decide route approvals
# whose task still awaits, so this branch of `_awaiting` never runs.

def test_a_route_approval_whose_task_left_the_awaiting_state_is_refused(rig):
    mid, pid, tid = ids.new_id('mission'), ids.new_id('plan'), ids.new_id('task')
    mission = entities.Mission(id=mid, workspace_id=ids.GLOBAL_WORKSPACE, title='m',
                               objective='o', origin='api', state='BLOCKED',
                               held_from='EXECUTING')
    template = entities.Plan(id=pid, mission_id=mid, plan_version=1, summary='plan')
    t = entities.Task(id=tid, plan_id=pid, mission_id=mid, key='t1', title='t',
                      kind='code_change', action_classes=('read',),
                      state='AWAITING_APPROVAL',
                      acceptance=[{'text': 'done', 'check': 'automatic'}])
    dh = validate.digest(template, [t])                  # intact from the moment it is in
    plan = entities.Plan(id=pid, mission_id=mid, plan_version=1, summary='plan',
                         state='PROPOSED', digest=dh)    # the database
    approval = entities.Approval(id=ids.new_id('approval'), kind='route',
                                 subject=Ref('task', tid), mission_id=mid, plan_id=pid,
                                 plan_version=1, plan_digest=dh, task_id=tid,
                                 requested_by=rig.user.id, state='PENDING',
                                 action_hash='a' * 64, expires_at=FUTURE,
                                 items=({'task': 't1',
                                         'action': {'kind': 'external_write',
                                                    'target': {'host': 'x'}}},))
    rig.do(_insert_rows, new_rows=(mission, plan, t, approval), mission_id=mid)
    a = rig.one(entities.Approval, id=approval.id)
    assert (a.kind, a.state) == ('route', 'PENDING')
    head = rig.head()
    with rig.db.read() as c:                             # control: while it awaits,
        assert authorization.ineligible(c, a, now=PAST, approve=False) is None
    tamper(rig.db, 'tasks', tid, state='READY')          # answered elsewhere, say
    with rig.db.read() as c:
        assert authorization.ineligible(c, a, now=PAST, approve=False)[0] == 'not_awaiting'
    with pytest.raises(NotEligible) as got:
        rig.decide(a)
    assert got.value.why == 'not_awaiting' and mid in got.value.detail
    assert rig.one(entities.Approval, id=a.id).state == 'PENDING'
    assert rig.one(entities.Task, id=tid).state == 'READY'    # nothing resumed it
    assert rig.one(entities.Mission, id=mid).state == 'BLOCKED'
    assert rig.head() == head


def _read_ineligible(rig, a):
    with rig.db.read() as c:
        return authorization.ineligible(c, a, now=PAST, approve=False)


# ── 3. a second paired device that stays unproven voids the step-up ─────────
# `_step_up_valid` L595: `all(pin_matches(...))` across TWO paired devices of
# one principal. I_A19/gaps_b register ONE paired device, where `all()` over a
# single row cannot tell a per-device check from "some device proved it".

def test_one_proved_and_one_unproven_paired_device_do_not_answer_the_step_up(rig):
    mid, a = _waiting_plan_approval(rig)
    assert a.step_up is True
    who, dev1 = _paired(rig, name='phone-a', token_hash='b' * 64, pin='123456')
    out = rig.decide(a, who=who, step_up='123456')       # control: proved, approved
    assert (out['state'], out['changed']) == ('APPROVED', True)
    mid2, a2 = _waiting_plan_approval(rig)
    _who2, dev2 = _paired(rig, name='phone-b', token_hash='c' * 64, pin='654321')
    tamper(rig.db, 'devices', dev2, principal_id=who.id)  # same principal's SECOND paired
    head = rig.head()                                     # device, and this one stays dark
    with pytest.raises(lifecycle.GuardFailed, match='step-up'):
        rig.decide(a2, who=who, step_up='123456')
    assert rig.one(entities.Approval, id=a2.id).state == 'PENDING'
    assert rig.m(mid2).state == 'APPROVAL_REQUIRED'
    assert rig.head() == head                             # the whole command rolled back


# ── 4. a denial reported for a mission that is not planning records nothing ──
# `record_plan_denial` L456-457, the early return. I_G3/G3b/G3c only ever run
# it from REASONING, PLANNING and REPLANNING (and I_G2 from an outside state
# with an EMPTY specs list, which never reaches the load's check at all).

def test_a_denial_reported_for_an_executing_mission_records_nothing(rig):
    rig.rule('USER', 'destructive', 'DENY')
    mid_a = rig.mission(title='A')
    with pytest.raises(work.PolicyDenied) as got:
        rig.propose(mid_a, task_spec('t1', 'destructive'))
    specs = got.value.specs
    assert specs                                          # what propose_plan hands over
    mid_b = rig.mission(title='B')
    rig.propose(mid_b, task_spec('t1', 'read'))
    _dispatchable(rig, mid_b)
    assert rig.m(mid_b).state == 'EXECUTING'              # not a planning state
    decisions = rig.all(entities.PolicyDecision, mission_id=mid_b)   # only what its own
    head = rig.head()                                     # propose legitimately left
    out = rig.do(rig.authz.record_plan_denial, mission_id=mid_b, specs=specs)
    assert out['recorded'] is False and 'not planning' in out['why']
    assert rig.all(entities.PolicyDecision, mission_id=mid_b) == decisions
    assert rig.all(entities.PolicyDecision, mission_id=mid_a) == []   # not even for A
    assert rig.head() == head                             # not one event written
    assert rig.m(mid_b).state == 'EXECUTING'


# ── 5. a plan decision for a plan row that has no digest records nothing ────
# `record_plan_decision` L409, the third operand `not prow.entity.digest` (a
# row whose content was never hashed): neither the auto-approval's `approved`
# fire nor a record. T-704 runs prow-None and the version operand of the same
# line, never this one.

def test_a_plan_decision_for_a_plan_row_without_a_digest_records_nothing(rig):
    mid = rig.mission()
    pid = ids.new_id('plan')
    plan = entities.Plan(id=pid, mission_id=mid, plan_version=1, summary='plan',
                         state='PROPOSED')               # no digest: content unknown
    rig.do(_insert_rows, new_rows=(plan,), mission_id=mid)
    head = rig.head()
    out = rig.do(lambda tx, actor: authorization.record_plan_decision(
        tx, actor=actor, mission=rows.get(tx.conn, entities.Mission, mid).entity,
        trigger='plan_auto_approved',
        facts=SimpleNamespace(plan_version=1, evaluated=(), cost_within_ceiling=True,
                              explicit_plan_approval=False)))
    assert out is None
    assert rig.all(entities.PolicyDecision, mission_id=mid) == []
    assert rig.all(entities.Approval, mission_id=mid) == []
    assert rig.one(entities.Plan, id=pid).state == 'PROPOSED'   # never "within policy"
    assert rig.head() == head


# ── 6. an approval recorded against another digest is a digest mismatch ──────
# `ineligible` L635-636 through the `plan.digest != a.plan_digest` operand with
# `intact(conn, plan)` TRUE. I_A06 and t150 tamper the PLAN side, where
# `intact` answers first and this operand is never the reason.

def test_an_approval_recorded_against_another_digest_is_refused_though_the_plan_is_intact(rig):
    mid, a = _waiting_plan_approval(rig)
    plan = rig.one(entities.Plan, mission_id=mid)
    assert plan.digest == a.plan_digest
    assert _read_ineligible(rig, a) is None               # control: eligible while bound
    tamper(rig.db, 'approvals', a.id, plan_digest='f' * 64)   # the approval side moved,
    head = rig.head()                                     # the plan never did
    with pytest.raises(NotEligible) as got:
        rig.decide(a)
    assert got.value.why == 'digest_mismatch' and plan.id in got.value.detail
    with rig.db.read() as c:
        assert authorization.intact(c, plan) is True      # the plan itself is intact
    assert rig.one(entities.Approval, id=a.id).state == 'PENDING'
    assert rig.head() == head


# ── 7. an approval of a plan version no longer in force is superseded ────────
# `ineligible` L634-635, the `plan.id != a.plan_id` operand (a second plan row
# in force) and the `plan is None` operand (then none at all). I_A08b reaches
# only the state operand, with the approval's own row in force.

def test_a_pending_approval_of_a_plan_version_not_in_force_is_superseded(rig):
    mid, a = _waiting_plan_approval(rig)
    own = rig.one(entities.Plan, id=a.plan_id)
    v2 = entities.Plan(id=ids.new_id('plan'), mission_id=mid, plan_version=2,
                       summary='v2', state='PROPOSED')   # the row in force now
    rig.do(_insert_rows, new_rows=(v2,), mission_id=mid)
    head = rig.head()
    with pytest.raises(NotEligible) as got:
        rig.decide(a)
    assert got.value.why == 'superseded' and a.plan_id in got.value.detail
    tamper(rig.db, 'plans', v2.id, mission_id=ids.new_id('mission'))
    tamper(rig.db, 'plans', own.id, mission_id=ids.new_id('mission'))   # now: no plan
    with pytest.raises(NotEligible) as got2:
        rig.decide(a)
    assert got2.value.why == 'superseded'
    assert rig.one(entities.Approval, id=a.id).state == 'PENDING'
    assert rig.m(mid).state == 'APPROVAL_REQUIRED'        # still waiting, undecided
    assert rig.head() == head


# ── 8. an approval whose task row is gone is superseded before any task load ─
# `ineligible` L640, the `t is None` short-circuit (retention pruned the row).
# t150's `_s_task_no_longer_in_force` always keeps a REAL foreign task, so it
# only ever runs the `plan_id !=` operand — and loads a row that exists.

def test_a_task_approval_whose_task_row_no_longer_exists_is_superseded(rig):
    _mid, a = _asked_task_approval(rig)
    assert a.kind == 'task'
    assert _read_ineligible(rig, a) is None               # control: eligible as asked
    tamper(rig.db, 'approvals', a.id, task_id=ids.new_id('task'))   # the row is gone
    head = rig.head()
    with pytest.raises(NotEligible) as got:               # ...and not a NotFound from
        rig.decide(a)                                     # loading a row that isn't there
    assert got.value.why == 'superseded'
    assert 'not in the plan in force' in got.value.detail
    with rig.db.read() as c:
        assert queries.get_approval(c, a.id)['eligible_why'] == 'superseded'
    assert rig.one(entities.Approval, id=a.id).state == 'PENDING'
    assert rig.head() == head


# ── 9. the expiry boundary: expiring at exactly `now` is expired ─────────────
# `ineligible` L626-627 `a.expires_at <= now` at exact equality. t150's
# `_s_expired` and I_A11 only test strictly-past or comfortably-future: one
# side of `<=` admits an expired approval, the other steals the last
# millisecond from a live one.

def test_an_approval_expiring_at_exactly_now_is_expired_and_one_millisecond_is_not(rig,
                                                                                    monkeypatch):
    mid, a = _waiting_plan_approval(rig)
    now = a.expires_at                                    # the exact equality candidate
    monkeypatch.setattr('archeus.core.domain.events.now_iso', lambda: now)
    tamper(rig.db, 'approvals', a.id, expires_at=now)     # expires AT this instant
    head = rig.head()
    with pytest.raises(NotEligible) as got:
        rig.decide(a)
    assert got.value.why == 'expired' and now in got.value.detail
    assert rig.one(entities.Approval, id=a.id).state == 'PENDING'
    assert rig.m(mid).state == 'APPROVAL_REQUIRED'
    assert rig.head() == head
    tamper(rig.db, 'approvals', a.id, expires_at=_ms_after(now, 1))   # alive by one ms
    out = rig.decide(a)                                   # the very same instant: live
    assert (out['state'], out['changed']) == ('APPROVED', True)
    assert rig.one(entities.Approval, id=a.id).state == 'APPROVED'
    assert rig.m(mid).state == 'APPROVED'


# ── 10. a decision's cause never leaks into the command that called it ───────
# `_restores_cause` L651-660 around `tx.cause = caused_by(e)` (L703 reject,
# L772 approve). No existing test reads `tx.cause` after a decision, nor the
# cause_chain of an event appended after one.

def _cause_command(rig, a, seed, *, decision, expect_raise=False):
    """Run `authorization.decide` inside one writer command that seeded its own
    `tx.cause` (what a chat module would have), appended a later event after
    the decision, and reports the transaction's cause straight after it."""
    state = {}

    def cmd(tx, *, actor):
        tx.append(seed)                                   # the command's own cause
        tx.cause = (seed.id,)
        try:
            out = authorization.decide(tx, actor=actor, policy=rig.policy,
                                       missions=rig.missions, approval_id=a.id,
                                       decision=decision, action_hash=a.action_hash)
            state['raised'] = None
        except RuntimeError as e:
            out, state['raised'] = None, str(e)
            if not expect_raise:
                raise
        state['after'] = tuple(tx.cause)
        later = new_event('mission.updated', Ref('mission', a.mission_id), actor,
                          payload={'note': 'the caller speaks after the decision'})
        tx.append(later)
        state['later'] = later.id
        return out
    result = rig.do(cmd, who=rig.user)
    return result, state


def test_a_decision_that_raises_leaves_the_cause_the_command_had(rig, monkeypatch):
    mid, a = _waiting_plan_approval(rig)
    seed = new_event('mission.updated', Ref('mission', mid), rig.user,
                 payload={'note': 'the command seeded its own cause'})

    def boom(*args, **kw):                                # the mission move dies
        raise RuntimeError('injected: the mission move failed')
    monkeypatch.setattr(rig.missions, '_by_state', boom)
    _result, state = _cause_command(rig, a, seed, decision='reject', expect_raise=True)
    assert 'injected' in state['raised']
    assert state['after'] == (seed.id,)     # restored by the finally, not the chain
    assert _chain(rig.db, state['later']) == [seed.id]    # and the caller's later event
    #   says so: the reject it caught is not what THAT event was caused by
    with rig.db.read() as c:
        landed = c.execute("SELECT id FROM events WHERE type = 'approval.state_changed'"
                           ' AND subject_id = ?', (a.id,)).fetchall()
    assert len(landed) == 1                               # the reject that did land...
    assert _chain(rig.db, landed[0][0]) == [seed.id]      # ...was still the command's


def test_a_decided_approval_carries_its_own_chain_but_not_the_commands_cause(rig):
    mid, a = _waiting_plan_approval(rig)
    seed = new_event('mission.updated', Ref('mission', mid), rig.user,
                 payload={'note': 'the command seeded its own cause'})
    result, state = _cause_command(rig, a, seed, decision='approve')
    assert (result['state'], result['changed']) == ('APPROVED', True)
    assert state['after'] == (seed.id,)                   # given back after the decision
    assert _chain(rig.db, state['later']) == [seed.id]    # the caller's own cause, only
    with rig.db.read() as c:
        evs = c.execute('SELECT id, type, subject_id, payload FROM events ORDER BY seq'
                        ).fetchall()
    (aid,) = [i for i, t, s, _p in evs
              if t == 'approval.state_changed' and s == a.id]
    assert _chain(rig.db, aid) == [seed.id]               # issued under the command's seed
    moved = [(i, json.loads(p)) for i, t, s, p in evs
             if t == 'mission.state_changed' and s == mid and json.loads(p)['to'] == 'APPROVED']
    assert moved, 'the approve move was never issued'
    chain = _chain(rig.db, moved[0][0])
    assert chain[0] == seed.id and aid in chain[1:]       # D13(b): what the decision issued carries the approval chain

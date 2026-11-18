"""T-764: the highest-risk uncovered branches of
`archeus/core/execution/handoff.py`, closed as tests.

`continue_task` is the second half of a checkpoint hand-off (p12-design-gate
§10.1): in the same transaction that ends the handing-off execution it either
writes the continuation (P9 `check_dispatch`, P10 `route`, `work.new_execution`)
or refuses and puts the task back to READY uncharged. Everything below is the
refusal side and the boundary of the continue side: who may not be continued,
and what must never be written when it may not.

Style, the seeded world and the seams are copied from the module's closest
existing tests — `_seeded`/`_world` of tests/v1/unit/test_execution_units.py and
tests/v1/unit/test_gaps_core_application_executions.py (the real SQLite database
on the tmp_path ARCHEUS_HOME tests/v1/conftest.py gives every V1 test) and the
scripted Policy/Router ports of tests/v1/unit/test_t150_gaps.py and
tests/v1/unit/test_gaps_core_application_resources.py. Nothing here touches the
OS, a process, the network or the clock: every instant is a literal, the Policy
and Router ports are scripted, and the whole command runs through the real
writer exactly as production does.
"""

from dataclasses import replace
from types import SimpleNamespace

import pytest

from archeus.core import ports
from archeus.core.application import commands, lifecycle, queries
from archeus.core.domain import entities, ids
from archeus.core.domain.events import new_event
from archeus.core.domain.values import Ref
from archeus.core.execution import handoff as H
from archeus.core.planning import validate
from archeus.infra.db import Database, rows

#: every test decides at this instant; nothing reads the clock
NOW = 1770000000.0
HARNESS = 'fake'


class SpyPolicy(ports.FixedPolicy):
    """The scripted Policy port of test_t150_gaps.py, plus the record of whether
    it was asked at all: a hand-off that consults P9 after the mission or the
    plan gate already refused has no business asking."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.calls = []

    def evaluate(self, action, ctx):
        self.calls.append(action.action_class)
        return super().evaluate(action, ctx)


class ScriptedRouter:
    """The Router port seam (test_gaps_core_application_resources.py's scripted
    decisions): answers one fixed `RouteDecision` and records every call with
    the context it was handed. Like the real `ResourceRouter.route` it records
    its decision as a row in the caller's transaction, so a continuation can be
    bound to it."""

    def __init__(self, *, result=None, selected=HARNESS, decided_by='router', **fields):
        self.result, self.selected, self.decided_by = result, selected, decided_by
        self.fields = fields
        self.calls = []
        self.decision_id = None

    def route(self, subject, now, **context):
        d = entities.RouteDecision(
            id=ids.new_id('route_decision'), subject=subject,
            selected=self.selected, decided_by=self.decided_by, result=self.result,
            harness_id=self.fields.get('harness_id', HARNESS),
            account_id=self.fields.get('account_id'), model=self.fields.get('model'),
            effort=self.fields.get('effort'), explanation=self.fields.get('explanation', 'scripted'),
            requirements={'subject': 'task'}, input_snapshot={'now': str(now)})

        def written(tx, actor):
            tx.insert(d, actor=actor)
            tx.append(new_event('route.decided', Ref('route_decision', d.id), actor,
                                payload={'result': d.result},
                                workspace=ids.GLOBAL_WORKSPACE))
        if context.get('tx') is not None:
            written(context['tx'], context['actor'])
        self.calls.append(SimpleNamespace(subject=subject, now=now, context=context))
        self.decision_id = d.id
        return d


def _seed(*, mission_state='EXECUTING', plan_state='APPROVED', plan_mission=None,
          task_state='RUNNING', tampered_digest=False, stop_reason='pressure',
          mid_chain=False, prior_executions=0):
    """The hand-off's world on a real database: one EXECUTING mission, one
    APPROVED plan whose digest is the real digest of its own rows (so P9's
    fail-closed `intact` check passes), one RUNNING task and one HANDING_OFF
    execution of it — each of those movable per test, which is the whole point.

    `plan_mission='other'` puts the plan under a decoy mission instead, which is
    how `active_plan` finds no plan for this mission at all (a Plan row cannot
    exist without its mission, and a Task cannot without its plan)."""
    db = Database.open()
    who = Ref('user_device', ids.new_id('principal'))
    mid, pid, tid = (ids.new_id(k) for k in ('mission', 'plan', 'task'))
    dmid = ids.new_id('mission')
    plan_of = dmid if plan_mission == 'other' else mid
    plan = entities.Plan(id=pid, mission_id=plan_of, state=plan_state, plan_version=1,
                        summary='the plan')
    task = entities.Task(id=tid, plan_id=pid, mission_id=mid, key='t', title='T',
                         kind='code_change', state=task_state, action_classes=('read',),
                         max_attempts=2)
    # the digest is the plan's own content, so P9's `intact` accepts the rows;
    # `tampered_digest` writes the one the `tamper` helper of
    # tests/v1/unit/test_t150_gaps.py leaves behind: a row that no longer matches
    plan = replace(plan, digest='0' * 64 if tampered_digest else validate.digest(plan, [task]))
    eids = [ids.new_id('execution') for _ in range(prior_executions + 1)]
    eid = eids[-1]

    def run(tx, **_):
        tx.insert(entities.Mission(id=mid, workspace_id=ids.GLOBAL_WORKSPACE, title='M',
                                   objective='o', state=mission_state), actor=who)
        if plan_mission == 'other':      # the decoy that owns the stranded plan
            tx.insert(entities.Mission(id=dmid, workspace_id=ids.GLOBAL_WORKSPACE,
                                       title='Other M', objective='o',
                                       state='EXECUTING'), actor=who)
        tx.insert(plan, actor=who)
        tx.insert(task, actor=who)
        for prior in eids[:-1]:
            tx.insert(entities.Execution(id=prior, task_id=tid, mission_id=mid, plan_id=pid,
                                          attempt=1, state='ENDED_HANDOFF',
                                          stop_reason=stop_reason), actor=who)
        # an isolated hand-off, as every pressure or account-change hand-off is
        tx.insert(entities.Execution(id=eid, task_id=tid, mission_id=mid, plan_id=pid,
                                     attempt=len(eids), state='HANDING_OFF', isolated=True,
                                     stop_reason=stop_reason,
                                     handoff_from=(eids[-2] if mid_chain else None)),
                  actor=who)
        tx.append(new_event('mission.updated', Ref('mission', mid), who, payload={},
                            workspace=ids.GLOBAL_WORKSPACE))
    db.writer.execute(run, {})
    return db, who, {'mid': mid, 'pid': pid, 'tid': tid, 'eid': eid,
                     'prior': eids[:-1]}


def _continue(db, who, k, *, policy=None, router=None, missions=None, now=NOW):
    """Run `continue_task` exactly as `executions.record_handoff` does: inside
    one writer transaction, on the row as it is in that transaction."""
    policy = SpyPolicy('ALLOW') if policy is None else policy
    router = ScriptedRouter() if router is None else router

    def run(tx, **_):
        e = lifecycle.load(tx, entities.Execution, k['eid']).entity
        return H.continue_task(tx, actor=who, policy=policy, missions=missions,
                               router=router, execution=e, now=now)
    return db.writer.execute(run, {}), router, policy


def _row(db, kind, id_):
    with db.read() as r:
        return rows.get(r, kind, id_)


def _executions(db, task_id):
    with db.read() as r:
        return [x.entity for x in rows.where(r, entities.Execution, task_id=task_id)]


def _events(db, type_, subject_id=None):
    with db.read() as r:
        return [ev for ev in queries.events(r) if ev['type'] == type_
                and (subject_id is None or ev['subject']['id'] == subject_id)]


def _decisions(db):
    with db.read() as r:
        return [x.entity for x in rows.where(r, entities.PolicyDecision)]


# ── 1. handoff.py:29-30 — nothing continues under a mission that is not running ──

@pytest.mark.parametrize('mission_state', ['BLOCKED', 'PAUSED', 'VERIFYING', 'REVIEWING',
                                           'COMPLETED', 'CANCELLED', 'FAILED'],
                         ids=['blocked', 'paused', 'verifying', 'reviewing', 'completed',
                              'cancelled', 'failed'])
def test_a_hand_off_continues_nothing_while_the_mission_is_not_executing(mission_state):
    """handoff.py:29-30 (`if m.state != 'EXECUTING': why = ...`). Drop that gate
    and a task of a CANCELLED or COMPLETED mission is given a fresh INTENT
    execution to run, the mission never asked for; the assertions below are
    exactly what such a continuation would move — and P9 and P10 are never even
    consulted, which is the fail-closed half of the same branch."""
    db, who, k = _seed(mission_state=mission_state)
    try:
        out, router, policy = _continue(db, who, k)
        assert out == {'refused': 'the mission is %s' % mission_state, 'execution_id': None}
        assert [x.id for x in _executions(db, k['tid'])] == [k['eid']]
        # the refusal is still a refusal: the task goes back uncharged, nothing runs
        assert _row(db, entities.Task, k['tid']).entity.state == 'READY'
        assert policy.calls == [] and router.calls == [] and _decisions(db) == []
    finally:
        db.close()


def test_a_dead_mission_is_the_refusal_that_is_told_even_when_the_plan_is_broken_too():
    """handoff.py:27-32 read as an ORDER: `why` is set by the mission gate first
    and the plan gate is an `elif`, so a cancelled mission whose plan was
    withdrawn too refuses for the mission and never reaches P9 or P10. Invert
    the two (judge the plan first, or keep going after the mission refused) and
    the reason the user is told — and the policy decision P9 would write for a
    mission that no longer exists — are both wrong."""
    db, who, k = _seed(mission_state='CANCELLED', plan_state='SUPERSEDED')
    try:
        out, router, policy = _continue(db, who, k)
        assert out['refused'] == 'the mission is CANCELLED'
        assert out['execution_id'] is None
        assert policy.calls == [] and router.calls == [] and _decisions(db) == []
        assert _row(db, entities.Mission, k['mid']).entity.state == 'CANCELLED'
        assert _row(db, entities.Task, k['tid']).entity.state == 'READY'
    finally:
        db.close()


# ── 2. handoff.py:31-32 — the plan it ran under must still be the one in force ──

def test_a_hand_off_with_no_plan_in_force_at_all_is_refused():
    """handoff.py:31, the `prow is None` arm. `active_plan` answers None until
    the first proposal; without that arm the function would fall through to
    `plan = prow.entity` and die (or, on a loosened version, dispatch a task
    with no plan at all)."""
    db, who, k = _seed(plan_mission='other')
    try:
        out, router, policy = _continue(db, who, k)
        assert out['execution_id'] is None
        assert out['refused'] == 'the plan it ran under is no longer in force'
        assert len(_executions(db, k['tid'])) == 1
        assert _row(db, entities.Task, k['tid']).entity.state == 'READY'
        assert policy.calls == [] and router.calls == [] and _decisions(db) == []
    finally:
        db.close()


def test_a_hand_off_of_an_older_plan_version_is_refused_when_a_replan_is_in_force():
    """handoff.py:31, the `prow.entity.id != e.plan_id` arm: the mission replanned
    while the execution ran. Continuing it under the NEW plan would run a task
    that the new plan's digest never contained — the reason string is the only
    thing that tells the user why nothing arrived."""
    db, who, k = _seed()
    try:
        newer = entities.Plan(id=ids.new_id('plan'), mission_id=k['mid'], state='APPROVED',
                              plan_version=2, summary='the replan')
        newer = replace(newer, digest=validate.digest(newer, []))

        def put(tx, **_):
            tx.insert(newer, actor=who)
            tx.append(new_event('mission.updated', Ref('mission', k['mid']), who, payload={},
                                workspace=ids.GLOBAL_WORKSPACE))
        db.writer.execute(put, {})
        out, router, policy = _continue(db, who, k)
        assert out['refused'] == 'the plan it ran under is no longer in force'
        assert out['execution_id'] is None
        assert len(_executions(db, k['tid'])) == 1
        assert _row(db, entities.Task, k['tid']).entity.state == 'READY'
        assert policy.calls == [] and router.calls == []
    finally:
        db.close()


@pytest.mark.parametrize('plan_state', ['SUPERSEDED', 'PROPOSED', 'REJECTED'],
                         ids=['superseded', 'proposed', 'rejected'])
def test_a_hand_off_is_refused_when_its_own_plan_is_no_longer_approved(plan_state):
    """handoff.py:31, the `prow.entity.state != 'APPROVED'` arm. A plan withdrawn
    or sent back for replanning must not spawn work; with this arm inverted (or
    comparing to 'PROPOSED') a superseded plan keeps producing executions."""
    db, who, k = _seed(plan_state=plan_state)
    try:
        out, router, policy = _continue(db, who, k)
        assert out['refused'] == 'the plan it ran under is no longer in force'
        assert out['execution_id'] is None
        assert len(_executions(db, k['tid'])) == 1
        assert _row(db, entities.Task, k['tid']).entity.state == 'READY'
        assert policy.calls == [] and router.calls == [] and _decisions(db) == []
    finally:
        db.close()


# ── 3. handoff.py:38-41 — P9's answer decides: a DENY or an ASK is a refusal ───

def test_a_policy_deny_of_the_task_ends_the_hand_off_as_a_refusal_not_a_crash():
    """handoff.py:38-39 (`except PolicyDenied as denied: auth = {'outcome':
    'denied (%s)' % denied}`) and handoff.py:40. `check_dispatch` RAISES on a
    DENY having written nothing; uncaught, that exception would abort the whole
    hand-off transaction — the checkpoint's end would be lost and the task left
    RUNNING forever. Caught, the refusal names the denial and the task goes back
    to READY uncharged."""
    db, who, k = _seed()
    try:
        out, router, policy = _continue(db, who, k, policy=SpyPolicy('DENY'),
                                        missions=commands.Missions(policy=SpyPolicy('ALLOW')))
        assert out['execution_id'] is None
        assert out['refused'].startswith('its authorisation no longer covers it (denied (')
        assert 'policy denies read on task t' in out['refused']
        assert router.calls == []
        assert len(_executions(db, k['tid'])) == 1
        t = _row(db, entities.Task, k['tid']).entity
        assert (t.state, t.failure_class) == ('READY', None)
        assert _row(db, entities.Execution, k['eid']).entity.charged is None
        # `check_dispatch` raises on a DENY having written nothing (P3.5): the
        # caught exception must not leave a half-written authorisation behind
        assert _decisions(db) == []
    finally:
        db.close()


def test_a_hand_off_continues_only_a_task_p9_covers():
    """handoff.py:36-41 taken as a whole: the covered path is the ONLY one that
    falls through. Same world, one ALLOW answers covered, one ASK answers
    'asked' and is refused; if `!= 'covered'` were loosened to accept 'asked'
    (or `check_dispatch` replaced by a call that always says covered) the second
    half of this test is what fails."""
    ask = SpyPolicy('ASK')
    db, who, k = _seed()
    try:
        out, _router, policy = _continue(db, who, k, policy=ask,
                                         missions=commands.Missions(policy=SpyPolicy('ALLOW')))
        assert out['execution_id'] is None
        assert out['refused'] == 'its authorisation no longer covers it (asked)'
        assert ask.calls == ['read'] and policy is ask
        assert len(_executions(db, k['tid'])) == 1
        assert _row(db, entities.Task, k['tid']).entity.state == 'READY'
        assert [d.decision for d in _decisions(db)] == ['ASK']
    finally:
        db.close()
    allowed = SpyPolicy('ALLOW')
    db, who, k = _seed()
    try:
        out, router, policy = _continue(db, who, k, policy=allowed,
                                        missions=commands.Missions(policy=SpyPolicy('ALLOW')))
        assert out['refused'] is None and out['execution_id'] is not None
        assert policy.calls == ['read'] and len(router.calls) == 1
    finally:
        db.close()


def test_a_tampered_plan_digest_is_refused_and_never_reaches_the_router():
    """handoff.py:40 via handoff.py:36 (`check_dispatch`'s fail-closed
    `intact`/digest check answers `{'outcome': 'denied', 'why':
    'digest_mismatch'}` instead of raising). The rows behind an APPROVED plan
    changed after approval: no continuation may be written from them, and the
    router must never be asked (it would otherwise route against a plan whose
    content is not its digest)."""
    db, who, k = _seed(tampered_digest=True)
    try:
        out, router, policy = _continue(db, who, k,
                                        missions=commands.Missions(policy=SpyPolicy('ALLOW')))
        assert out['execution_id'] is None
        assert out['refused'] == ('its authorisation no longer covers it (denied)')
        assert router.calls == []
        assert policy.calls == ['read']
        assert len(_executions(db, k['tid'])) == 1
        assert _row(db, entities.Task, k['tid']).entity.state == 'READY'
        assert _row(db, entities.Mission, k['mid']).entity.state == 'BLOCKED'
    finally:
        db.close()


# ── 4. handoff.py:42-47 — nowhere to run it is a refusal, not a guess ─────────

@pytest.mark.parametrize('result', ['blocked', 'ask'], ids=['blocked', 'ask'])
def test_a_router_that_has_nowhere_to_put_it_refuses_the_continuation(result):
    """handoff.py:46-47 (`if result not in ('selected', 'fallback')`). 'ask' is
    the resource approval dispatch would ask for; a hand-off has no such ask —
    accepting it would write an INTENT execution waiting on an approval that was
    never created, and the task would hang in RUNNING."""
    db, who, k = _seed()
    try:
        out, router, _policy = _continue(db, who, k, router=ScriptedRouter(result=result))
        assert out['execution_id'] is None
        assert out['refused'] == 'the resource router has nowhere to continue it (%s)' % result
        assert len(router.calls) == 1
        assert len(_executions(db, k['tid'])) == 1
        assert _row(db, entities.Task, k['tid']).entity.state == 'READY'
    finally:
        db.close()


@pytest.mark.parametrize('selected,want', [(None, 'blocked'), (HARNESS, 'selected')],
                         ids=['nothing-chosen', 'something-chosen'])
def test_a_decision_with_no_result_is_read_from_what_it_chose_not_assumed(
        selected, want):
    """handoff.py:45 (`result = route.result or ('selected' if route.selected else
    'blocked')`): a legacy decision carries no `result`. Inverting the `else`
    turns a chosen harness into a refusal (a hand-off that silently never
    continues) or an empty choice into a continuation on nothing."""
    db, who, k = _seed()
    try:
        out, router, _policy = _continue(db, who, k,
                                         router=ScriptedRouter(result=None, selected=selected))
        assert len(router.calls) == 1
        if want == 'blocked':
            assert out['refused'] == 'the resource router has nowhere to continue it (blocked)'
            assert out['execution_id'] is None and len(_executions(db, k['tid'])) == 1
        else:
            assert out['refused'] is None and out['execution_id'] is not None
            assert len(_executions(db, k['tid'])) == 2
    finally:
        db.close()


def test_a_fallback_decision_continues_uncharged_like_any_other_choice():
    """handoff.py:46 — `'fallback'` is in the accepted pair. A hand-off that
    lands on the last-resort account is still a continuation (P10 asked for that
    consent at the first dispatch, not again at every hand-off); dropping
    'fallback' from the tuple strands a task that has somewhere to run."""
    db, who, k = _seed()
    try:
        out, _router, _policy = _continue(db, who, k, router=ScriptedRouter(result='fallback'))
        assert out['refused'] is None and out['execution_id'] is not None
        assert _row(db, entities.Execution, out['execution_id']).entity.state == 'INTENT'
        assert _row(db, entities.Task, k['tid']).entity.state == 'RUNNING'
    finally:
        db.close()


def test_the_router_is_handed_the_authorisation_it_must_re_check():
    """handoff.py:43-44: the router is called with THIS transaction, the caller,
    the task's Ref and P9's own answer. `ResourceRouter.route` re-checks
    `authorization['policy_decision_id']` against the rows before choosing
    anything; passing `None` or the wrong decision would route an unauthorised
    task, and the transaction would be the caller's, not the hand-off's."""
    db, who, k = _seed()
    try:
        _out, router, _policy = _continue(db, who, k)
        (call,) = router.calls
        assert call.subject == Ref('task', k['tid']) and call.now == NOW
        ctx = call.context
        assert ctx['actor'] == who and set(ctx) == {'tx', 'actor', 'authorization', 'mission',
                                                    'plan', 'task'}
        assert ctx['mission'].id == k['mid'] and ctx['plan'].id == k['pid']
        assert ctx['task'].id == k['tid']
        assert ctx['authorization']['outcome'] == 'covered'
        assert ctx['authorization']['policy_decision_id'] == _decisions(db)[0].id
    finally:
        db.close()


# ── 5. handoff.py:48-53 — the refusal puts the task back, and only from RUNNING ──

def test_a_refusal_returns_the_running_task_to_ready_uncharged_with_an_audit_trail():
    """handoff.py:49-52: the `execution_failed_retry` fire and its reason. The
    attempt is NOT spent (a hand-off is the resource's end, not the task's, D9)
    and the reason is the only record of why the continuation never came; with
    the fire dropped the task sits RUNNING with no execution and no dispatcher."""
    db, who, k = _seed()
    try:
        out, _router, _policy = _continue(db, who, k, router=ScriptedRouter(result='blocked'))
        t = _row(db, entities.Task, k['tid'])
        assert out['refused'].startswith('the resource router')
        assert (t.entity.state, t.entity.failure_class) == ('READY', None)
        (ev,) = _events(db, 'task.state_changed', k['tid'])
        assert ev['payload']['trigger'] == 'execution_failed_retry'
        assert (ev['payload']['from'], ev['payload']['to']) == ('RUNNING', 'READY')
        assert 'not charged' in ev['payload']['reason']
        assert 'no continuation: %s' % out['refused'] in ev['payload']['reason']
        assert k['eid'] in ev['payload']['reason']
        e = _row(db, entities.Execution, k['eid']).entity
        assert (e.state, e.charged) == ('HANDING_OFF', None)     # the caller ends it, not here
    finally:
        db.close()


@pytest.mark.parametrize('task_state', ['VERIFYING', 'PAUSED', 'BLOCKED'],
                         ids=['verifying', 'paused', 'blocked'])
def test_a_refusal_never_moves_a_task_that_is_not_running(task_state):
    """handoff.py:49 (`if t.state == 'RUNNING':`). `execution_failed_retry` is a
    RUNNING->READY edge only; without the guard a hand-off whose task already
    moved on (verification started, the user paused it, a merge conflict
    blocked it) raises IllegalTrigger and rolls back the whole hand-off, taking
    the checkpoint's end with it."""
    db, who, k = _seed(task_state=task_state)
    try:
        out, _router, _policy = _continue(db, who, k, router=ScriptedRouter(result='blocked'))
        assert out == {'refused': 'the resource router has nowhere to continue it (blocked)',
                       'execution_id': None}
        assert _row(db, entities.Task, k['tid']).entity.state == task_state
        assert _events(db, 'task.state_changed', k['tid']) == []
        assert len(_executions(db, k['tid'])) == 1
    finally:
        db.close()


# ── 6. handoff.py:54-56 — what the continuation row is bound to ───────────────

@pytest.mark.parametrize('decided_by,want', [('router', 'decision'), ('pre_router', None)],
                         ids=['by-router', 'by-pre-router'])
def test_only_a_decision_the_router_made_binds_the_continuation(decided_by, want):
    """handoff.py:54 (`rd = route.id if route.decided_by == 'router' else None`).
    A pre-router placeholder is not a routing decision: bound to it, the
    execution claims a provenance (`route_decision_id`) for a choice no router
    ever made and judged, and the audit trail points at the wrong row."""
    db, who, k = _seed()
    try:
        router = ScriptedRouter(result='selected', decided_by=decided_by)
        out, _r, _p = _continue(db, who, k, router=router)
        e = _row(db, entities.Execution, out['execution_id']).entity
        assert e.route_decision_id == (router.decision_id if want else None)
    finally:
        db.close()


@pytest.mark.parametrize('stop_reason', ['limit', 'ceiling', 'pressure', 'handoff_user'],
                         ids=['limit', 'ceiling', 'pressure', 'user'])
def test_the_why_the_process_stopped_for_is_no_business_of_the_continuation(
        stop_reason):
    """handoff.py:22-56 never reads `execution.stop_reason`: whether the context
    was full (P12) or the account's window ran out (P10), the next execution is
    judged only by P9 and P10 now. A `stop_reason == 'pressure'` condition added
    to this function — the obvious way to "only continue what needs it" — would
    strand every limit hand-off in RUNNING with no execution; the four cases here
    are what that mistake fails."""
    db, who, k = _seed(stop_reason=stop_reason)
    try:
        out, _router, policy = _continue(db, who, k)
        assert out['refused'] is None and out['execution_id'] is not None
        e = _row(db, entities.Execution, out['execution_id']).entity
        assert (e.state, e.attempt, e.handoff_from) == ('INTENT', 2, k['eid'])
        assert policy.calls == ['read']
    finally:
        db.close()


def test_the_continuation_is_one_more_attempt_of_the_same_task_bound_to_everything():
    """handoff.py:55 (`new_execution(..., handoff_from=e.id)`) and its
    `attempt = COUNT(executions of the task) + 1`: the hand-off is uncharged, so
    the attempt comes from the rows. Lose `handoff_from` and the A->B->A loop
    guard in `executions.no_progress` and the pressure-chain read see nothing;
    lose the count and every hand-off is 'attempt 1' forever, so `max_attempts`
    never spends."""
    db, who, k = _seed(prior_executions=1, mid_chain=True)
    try:
        router = ScriptedRouter(result='selected', decided_by='router', model='m',
                               effort='high')
        out, _r, _policy = _continue(db, who, k, router=router)
        e = _row(db, entities.Execution, out['execution_id'])
        assert e.entity.state == 'INTENT' and e.entity.charged is None
        # its IMMEDIATE predecessor: `handoff_from=e.handoff_from` would make the
        # whole chain point at its head and the A->B->A loop guard would never fire
        assert e.entity.handoff_from == k['eid'] != k['prior'][-1]
        assert e.entity.attempt == 3                     # the two before it, then this one
        assert (e.entity.task_id, e.entity.mission_id, e.entity.plan_id) == (
            k['tid'], k['mid'], k['pid'])
        assert e.entity.plan_digest == _row(db, entities.Plan, k['pid']).entity.digest
        assert e.entity.policy_decision_id == _decisions(db)[0].id
        assert (e.entity.harness_id, e.entity.route_decision_id) == (HARNESS, router.decision_id)
        assert (e.entity.model, e.entity.effort, e.entity.served_model) == ('m', 'high', 'm')
        assert e.entity.served_level == 'REQUESTED'
        assert out['refused'] is None and out['task_id'] == k['tid']
        assert _row(db, entities.Task, k['tid']).entity.state == 'RUNNING'
        assert _row(db, entities.Mission, k['mid']).entity.state == 'EXECUTING'
        (ev,) = [x for x in _events(db, 'execution.intent', out['execution_id'])]
        assert ev['payload']['handoff_from'] == k['eid']
    finally:
        db.close()

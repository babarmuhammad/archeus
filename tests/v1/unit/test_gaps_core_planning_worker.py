"""T-728: the highest-risk uncovered branches of archeus/core/planning/worker.py.

Fail-closed and denial paths first — the round refused before the model is ever
asked (mission gone, round already recorded, a newer round started, the replan
budget spent), the answer discarded as stale, the crash that still ends the
call `failed` — then the boundary values (the round's own event is not "newer";
a newer event that starts no round is ignored; the budget judged only in
REPLANNING; a current package reused, a stale one replaced), then the error
paths of the loop (`_handle` survives a raising round, `_retry_gated` answers
for the missions that do not wait, `_replan` reads what the last version did).

The rig is the one tests/v1/integration/test_planning.py built for this worker,
kept to what a unit test may hold (the same shape as the T-305 rig of
test_gaps_core_verification_worker.py): the real worker over a real database of
real rows — so every skip, guard and re-judgement the worker and its commands
make is really re-derived from those rows — with one fake only, the `calls`
object, which is the worker's entire seam to a model process (the shape of the
`open_call` fixture of tests/v1/integration/test_knowledge.py for the call row
it ends). Nothing here needs a model, a process, the network or a platform: no
OS call is made at all, and no assertion depends on the platform, the
environment or a live thread.
"""

import types

import pytest

from archeus.core import ports
from archeus.core.application import commands, work as W
from archeus.core.application.planning import Planning
from archeus.core.domain import entities
from archeus.core.domain.actions import Action
from archeus.core.domain.events import new_event
from archeus.core.domain.ids import GLOBAL_WORKSPACE, new_id
from archeus.core.domain.values import Ref
from archeus.core.planning import worker as WORKER_MODULE
from archeus.core.planning.worker import Planner, _starts_round
from archeus.infra.db import Database, rows
from archeus.infra.eventlog import outbox

WS = GLOBAL_WORKSPACE
AUTO = {'text': 'the result passes its check', 'check': 'automatic'}
REQ = ({'text': 'a --version flag', 'origin': 'explicit'},)
CONS = ({'text': 'no new dependency', 'origin': 'explicit'},)


def task_answer(**over):
    """One plan.v1 answer: a single task serving the mission's one explicit
    requirement (the answer shape of tests/v1/integration/test_planning.py)."""
    task = {'id': 'a', 'title': 'Add the flag', 'kind': 'code_change',
            'objective': 'Add a --version flag to the CLI', 'expected_output': 'the flag',
            'action_classes': ['read', 'exec'], 'serves': ['r1'], 'estimate': 1,
            'acceptance': [AUTO]}
    answer = {'summary': 'a plan', 'tasks': [dict(task, **over)], 'success_criteria': [AUTO]}
    return answer


def blocked_answer():
    """An answer that stops the plan (P8 §10): one blocking question."""
    return {'summary': 'a plan',
            'tasks': [dict(task_answer()['tasks'][0], serves=[])],
            'success_criteria': [AUTO],
            'questions': [{'question': 'which flag name?', 'blocking': True}]}


class FakeCalls:
    """The worker's `OwnCalls` seam: every `run` recorded, each answered by the
    next scripted result (the last repeating). An entry may be callable — it
    receives the run kwargs and answers, which is how a test moves the mission
    mid-call — or an exception, which the run re-raises."""

    def __init__(self):
        self.results, self.seen = [], []

    def script(self, *results):
        self.results = list(results)

    def run(self, **kw):
        self.seen.append(kw)
        r = self.results.pop(0) if len(self.results) > 1 else self.results[0]
        if callable(r):
            r = r(**kw)
        if isinstance(r, Exception):
            raise r
        return r


def call_result(state, parsed=None, rdid=None, *, detail='', attempts=1,
                account_ref='fake', usage=None):
    return types.SimpleNamespace(state=state, parsed=parsed, detail=detail,
                                 route_decision_id=rdid, attempts=attempts,
                                 account_ref=account_ref,
                                 usage={'tokens_in': 3, 'tokens_out': 7} if usage is None
                                 else usage)


class Rig:
    """One planning worker over its own Core: the real database, the real
    `Planning`/`Work`/`Missions` commands and a real `FixedPolicy` port; the
    call row is a real `RouteDecision` as `open_call` places one in
    tests/v1/integration/test_knowledge.py. One rig per test (they all share
    the one ARCHEUS_HOME); closed by the fixture."""

    def __init__(self, *, decision='ASK'):
        self.db = Database.open()
        self.actor = Ref('system', new_id('principal'))
        self.missions = commands.Missions(policy=ports.FixedPolicy(decision))
        self.work = W.Work(missions=self.missions, router=ports.FixedCandidateRouter('fake'))
        self.planning = Planning(work=self.work)
        self.calls = FakeCalls()
        self.worker = Planner(self.db, actor=self.actor, calls=self.calls,
                              planning=self.planning)
        self.mid = new_id('mission')
        self.rdid = new_id('route_decision')

    def close(self):
        self.db.close()

    # ── placing (a mutation without an event is rolled back, so every
    # placement records itself with one inert `fields: []` update) ──

    def _do(self, command, **kw):
        return self.db.writer.execute(command, dict(kw, actor=self.actor))

    def place(self, *items):
        def command(tx, *, actor):
            for x in items:
                tx.insert(x, actor=actor)
            return tx.append(new_event('mission.updated', Ref('mission', self.mid), actor,
                                       payload={'fields': []}, workspace=WS)).seq
        return self._do(command)

    def fire(self, type, subject, payload=None):
        """One appended event of its own — a round's trigger, a terms answer, a
        policy move — returning its seq."""
        def command(tx, *, actor):
            return tx.append(new_event(type, subject, actor, payload=payload or {},
                                       workspace=WS)).seq
        return self._do(command)

    def set_block(self, blocked):
        def command(tx, *, actor):
            tx.update(entities.Mission, self.mid, {'planning_blocked': blocked}, actor=actor)
            tx.append(new_event('mission.updated', Ref('mission', self.mid), actor,
                                payload={'fields': ['planning_blocked']}, workspace=WS))
        self._do(command)

    def set_package(self, pid):
        def command(tx, *, actor):
            tx.update(entities.Mission, self.mid, {'context_package_id': pid}, actor=actor)
            tx.append(new_event('mission.updated', Ref('mission', self.mid), actor,
                                payload={'fields': ['context_package_id']}, workspace=WS))
        self._do(command)

    def mission_row(self, *, state='PLANNING', max_replans=2, planning_blocked=None,
                    context_package_id=None, mid=None):
        mid = mid or self.mid
        m = entities.Mission(
            id=mid, workspace_id=WS, title='Ship the flag',
            objective='Add the --version flag', origin='api', requirements=REQ,
            constraints=CONS, success_criteria=(AUTO,), max_replans=max_replans,
            planning_blocked=planning_blocked, context_package_id=context_package_id,
            state=state)

        def command(tx, *, actor):
            tx.insert(m, actor=actor)
            return tx.append(new_event('mission.updated', Ref('mission', mid), actor,
                                       payload={'fields': []}, workspace=WS)).seq
        self._do(command)
        return mid

    def call_row(self):
        """The planner call's RouteDecision with no outcome yet, as the spawn
        leaves it (test_knowledge.py's `open_call`): the worker must end it."""
        self.place(entities.RouteDecision(
            id=self.rdid, subject=Ref('archeus_call', 'planner'), purpose='planner',
            decided_by='router', source=Ref('mission', self.mid), selected='fake',
            harness_id='fake', explanation='rig: the one candidate', result='selected',
            workspace_id=WS, mission_id=self.mid))
        return self.rdid

    def package_row(self, *, as_of_seq=0, items=()):
        pid = new_id('context_package')
        self.place(entities.ContextPackage(id=pid, workspace_id=WS, subject_kind='mission',
                                           subject_id=self.mid, as_of_seq=as_of_seq,
                                           items=items))
        return pid

    # ── placing what a finished previous version left behind (the replan's
    # raw material): rows as `Work.propose_plan` and its followers would have
    # written them, so `_replan` reads them for real ──

    def place_plan(self, *, mission_id, plan_version=1, **over):
        pid = new_id('plan')
        self.place(entities.Plan(id=pid, mission_id=mission_id,
                                 plan_version=plan_version,
                                 summary=over.pop('summary', 'a plan'), **over))
        return pid

    def place_task(self, plan_id, mission_id, *, key, title, state='PENDING', **over):
        tid = new_id('task')
        self._last_task_id = tid
        self.place(entities.Task(
            id=tid, plan_id=plan_id, mission_id=mission_id, key=key, title=title,
            kind='code_change', objective='Do %s' % key, expected_output='done',
            action_classes=('read',), acceptance=(AUTO,), estimate=1, state=state, **over))
        return tid

    def get_last_task_id(self):
        return self._last_task_id

    def place_verification(self, plan_id, mission_id, *, state='PASSED'):
        self.place(entities.Verification(
            id=new_id('verification'), subject=Ref('mission', mission_id), verifier='code',
            plan_id=plan_id, criterion=0, state=state,
            checks=({'name': 'the check', 'kind': 'command', 'argv': ['true'],
                     'result': 'pass' if state == 'PASSED' else 'fail'},)))

    def place_review(self, plan_id, mission_id, *, verdict='accept', state='ACCEPTED'):
        self.place(entities.Review(id=new_id('review'), mission_id=mission_id,
                                   reviewer='rig', verdict=verdict, plan_id=plan_id,
                                   state=state))

    def place_checkpoint(self, task_id, mission_id, *, open_problems=(), next_action=''):
        chk, exe = new_id('checkpoint'), new_id('execution')

        def command(tx, *, actor):                                 # one txn: the FKs
            tx.insert(entities.Execution(id=exe, task_id=task_id, mission_id=mission_id,
                                         attempt=1, state='ENDED_ERROR'), actor=actor)
            tx.insert(entities.Checkpoint(
                id=chk, execution_id=exe, mission_id=mission_id, task_id=task_id,
                trigger='failure', open_problems=tuple(open_problems),
                next_action=next_action), actor=actor)
            tx.append(new_event('mission.updated', Ref('mission', self.mid), actor,
                                payload={'fields': []}, workspace=WS))
        self._do(command)

    # ── reading back ──

    def get(self, cls, entity_id):
        with self.db.read() as conn:
            r = rows.get(conn, cls, entity_id)
        return None if r is None else r.entity

    def where(self, cls, **eq):
        with self.db.read() as conn:
            return [r.entity for r in rows.where(conn, cls, **eq)]

    def mission(self):
        return self.get(entities.Mission, self.mid)

    def decision(self):
        return self.get(entities.RouteDecision, self.rdid)

    def head(self):
        with self.db.read() as conn:
            return outbox.head(conn)

    def effect(self, seq):
        with self.db.read() as conn:
            r = conn.execute('SELECT result FROM consumer_effects WHERE consumer = ? '
                             'AND event_seq = ?', (WORKER_MODULE.CONSUMER, seq)).fetchone()
        return None if r is None else r[0]

    # ── scripting the one fake ──

    def answer_with(self, parsed):
        """An ok answer for a real spawned call: the row exists, the worker
        must end it (`Planning.apply`/`hold` do, in the recording transaction)."""
        self.call_row()
        self.calls.script(call_result('ok', parsed, self.rdid))

    def ends_as(self, state, detail=''):
        """A call that answered for itself (gated, unavailable, invalid,
        failed): no row to end — the worker may only `note` it."""
        self.calls.script(call_result(state, None, None, detail=detail))


@pytest.fixture
def rig():
    r = Rig()
    try:
        yield r
    finally:
        r.close()


def started(rig, to='PLANNING', reason='the mission needs a plan'):
    """A mission placed in *to* and the one `mission.state_changed` that starts
    a round for it; returns (mid, round_seq)."""
    mid = rig.mission_row(state=to)
    return mid, rig.fire('mission.state_changed', Ref('mission', mid),
                         payload={'from': 'CREATED', 'to': to, 'reason': reason})


def drained(rig, limit=25):
    """Deliver until the queue is empty: a round's own recording appends
    events (the plan, the mission's move, the call's end), and those — never
    rounds themselves — are what a following pass drains."""
    for _ in range(limit):
        if not rig.worker.pass_once()['changed']:
            return
    raise AssertionError('the queue never drains')


def moved_during(rig, mid, frm, to):
    """A scripted call that takes the real time the mission takes to move away:
    the move happens mid-call, so the recording must find it (fail closed)."""
    def move(**_kw):
        rig._do(lambda tx, *, actor: tx.transition(entities.Mission, mid, to, actor=actor,
                                                   reason='rig: something asked first'))
        return call_result('ok', rig.scripted_answer, rig.rdid)
    rig.call_row()
    rig.calls.script(move)


# ── fail-closed and denial paths ──────────────────────────────────────────

def test_a_round_for_a_mission_that_is_not_there_is_skipped(rig):
    """worker.py plan(): `row is None` — nothing is planned, and above all
    nothing is asked of the model, for a mission Core cannot read back."""
    assert rig.worker.plan(new_id('mission'), 1, 'the mission changed') == 'skip: not planning'
    assert rig.worker.plan(new_id('mission'), 0, '') == 'skip: not planning'
    assert rig.calls.seen == []


def test_a_round_for_a_mission_that_left_the_planning_states_is_skipped(rig):
    """worker.py plan(): `state not in PLANNING_STATES` — an EXECUTING
    mission's redelivered event must not reach the model or write a version."""
    mid = rig.mission_row(state='EXECUTING')
    assert rig.worker.plan(mid, 1, 'the mission changed') == 'skip: not planning'
    assert rig.calls.seen == []
    assert rig.where(entities.Plan) == []


def test_a_round_whose_recorded_version_exists_is_skipped(rig):
    """worker.py plan(): the once, which an at-least-once consumer rests on —
    `(mission_id, round_seq)` recorded means the round ran; redelivery must
    skip, not call the model a second time."""
    mid, seq = started(rig)
    rig.place(entities.Plan(id=new_id('plan'), mission_id=mid, plan_version=1,
                            summary='already recorded', round_seq=seq))
    rig.ends_as('unavailable')                            # a call fails the test anyway
    assert rig.worker.plan(mid, seq, 'redelivered') == 'skip: round %d already recorded' % seq
    assert rig.calls.seen == []


def test_a_round_the_log_already_superseded_is_skipped(rig):
    """worker.py plan(): `a newer round started` — a round overtaken by a
    newer round-starting event on its own mission is refused before the call;
    the newer round is the one that plans."""
    mid, seq = started(rig)
    rig.fire('mission.state_changed', Ref('mission', mid),
             payload={'from': 'PLANNING', 'to': 'REASONING'})              # newer, starts one
    rig.answer_with(task_answer())
    assert rig.worker.plan(mid, seq, 'the mission changed') == 'skip: a newer round started'
    assert rig.calls.seen == []


def test_a_denied_plan_is_recorded_as_a_denial_with_nothing_written():
    """worker.py plan(): `except PolicyDenied` — the plan the policy DENIES is
    refused before anything is written (P3.5) and the worker records the denial
    itself, with the call's end, by the answering command (P9 D12): the mission
    waits blocked for it, and no plan, task or approval exists."""
    r = Rig(decision='DENY')
    try:
        mid, seq = started(r)
        r.scripted_answer = task_answer()
        r.answer_with(r.scripted_answer)
        got = r.worker.plan(mid, seq, 'the mission changed')
        (d,) = r.where(entities.PolicyDecision)
        assert (d.decision, d.outcome, d.stage) == ('DENY', 'denied', 'plan')
        assert got == 'policy_denied:%s' % d.id
        assert r.mission().planning_blocked['kind'] == 'policy'
        assert r.where(entities.Plan) == [] and r.where(entities.Task) == []
        assert r.decision().outcome['state'] == 'ok'                  # the call ended, once
        assert r.where(entities.UsageLedger)                          # with its usage
    finally:
        r.close()


@pytest.mark.xfail(strict=True, reason='source bug on this branch: a PolicyDenied '
                                       'carrying no specs reaches first_denial with [], and '
                                       'authorization.first_denial (authorization.py:445) '
                                       'binds ctx only inside its loop, so the empty-specs '
                                       'deny raises UnboundLocalError instead of recording '
                                       'that the policy no longer denies')
def test_a_denial_that_carried_no_specs_is_still_judged_again(rig, monkeypatch):
    """worker.py plan(): `specs=e.specs or []` — a PolicyDenied from a dispatch
    (no specs) must still run the recording command, which re-judges the policy
    in its own transaction and, finding no denial, reports that the policy no
    longer denies — the next round plans (P9 D12)."""
    mid, seq = started(rig)

    def refuse(tx, mission, actor, specs):
        raise W.PolicyDenied(entities.PolicyDecision(
            id=new_id('policy_decision'), decision='DENY', reason='rig: refused',
            action=Action(action_class='exec', target='task:t1')), 't1', None)

    rig.answer_with(task_answer())
    monkeypatch.setattr(rig.work, '_refuse_denied', refuse)
    assert rig.worker.plan(mid, seq, 'the mission changed') == \
        'policy_denied:the policy no longer denies this plan'
    assert rig.mission().planning_blocked is None


def test_an_ok_answer_cannot_be_recorded_after_the_mission_moved(rig):
    """worker.py plan() -> Planning.apply: the round whose mission moved during
    the call is DISCARDED — no version written, the call ends `failed` with the
    stale reason, and the worker reports the why (`plan_version or why`)."""
    mid, seq = started(rig, to='REASONING')
    rig.scripted_answer = task_answer()
    moved_during(rig, mid, 'REASONING', 'BLOCKED')
    got = rig.worker.plan(mid, seq, 'the mission changed')
    assert got == 'plan:the mission moved from REASONING to BLOCKED during the call'
    assert rig.where(entities.Plan) == []
    assert rig.decision().outcome['state'] == 'failed'
    assert rig.decision().outcome['reason'].startswith('stale: the mission moved from')


def test_a_blocking_answer_cannot_be_recorded_after_the_mission_moved(rig):
    """The `blocked` half of the same fail-closed split: a blocking answer for
    a mission that moved holds nothing — the why is reported, never a block
    kind, and no message/block is written for a mission that is gone."""
    mid, seq = started(rig, to='REASONING')
    rig.scripted_answer = blocked_answer()
    moved_during(rig, mid, 'REASONING', 'BLOCKED')
    assert rig.worker.plan(mid, seq, 'the mission changed') == \
        'blocked:the mission moved from REASONING to BLOCKED during the call'
    assert rig.mission().planning_blocked is None


def test_a_crash_while_recording_ends_the_call_failed_and_still_raises(rig, monkeypatch):
    """worker.py plan(): `except Exception` -> `_end(c, 'failed', ...)` ->
    `raise` — a round that cannot record its answer never leaves an open call
    for the boot sweep to have to invent an end for, and the failure is not
    swallowed."""
    mid, seq = started(rig)
    rig.answer_with(task_answer())

    def boom(tx, **_kw):
        raise RuntimeError('rig: the recording broke')

    monkeypatch.setattr(rig.planning, 'apply', boom)
    with pytest.raises(RuntimeError, match='rig: the recording broke'):
        rig.worker.plan(mid, seq, 'the mission changed')
    end = rig.decision().outcome
    assert end['state'] == 'failed'
    assert end['reason'] == 'could not record the plan: RuntimeError: rig: the recording broke'
    assert end['attempts'] == 1
    assert rig.where(entities.Plan) == []


def test_the_answer_of_a_call_that_never_ran_only_notes_the_mission(rig):
    """worker.py plan(): `c.state != 'ok'` -> Planning.note — a call that ended
    itself (gated, unavailable, invalid) is only noted: the mission waits with
    `planning_blocked` kind `call`, nothing is invented, and the worker writes
    no second outcome for the call."""
    mid, seq = started(rig)
    rig.ends_as('unavailable', detail='rig: no harness answered')
    assert rig.worker.plan(mid, seq, 'the mission changed') == 'call:unavailable'
    assert rig.mission().planning_blocked['kind'] == 'call'
    assert rig.mission().planning_blocked['outcome'] == 'unavailable'
    assert rig.where(entities.Plan) == [] and rig.where(entities.RouteDecision) == []


def test_a_blocking_answer_holds_the_mission_instead_of_recording_a_plan(rig):
    """worker.py plan(): `block is not None` -> Planning.hold, and the REASONING
    challenge it answers with (P8 D6): the question is what the worker reports
    and what the mission waits on — the plan is not."""
    mid, seq = started(rig, to='REASONING')
    rig.answer_with(blocked_answer())
    assert rig.worker.plan(mid, seq, 'the mission changed') == 'blocked:clarification'
    m = rig.mission()
    assert m.state == 'BLOCKED' and m.planning_blocked['kind'] == 'clarification'
    assert m.planning_blocked['questions'] == ['which flag name?']
    assert rig.where(entities.Plan) == []


# ── boundary values ───────────────────────────────────────────────────────

def test_the_rounds_own_event_is_not_a_newer_round(rig):
    """The boundary of `a newer round started`: the scan is `seq > round_seq`,
    so the event that started THIS round — sitting at round_seq itself — must
    not skip the round it started."""
    mid, seq = started(rig)
    rig.answer_with(task_answer())
    assert rig.worker.plan(mid, seq, 'the mission changed') == 'plan:1'
    assert len(rig.calls.seen) == 1
    assert rig.decision().outcome['state'] == 'ok'


def test_a_newer_event_that_starts_no_round_does_not_skip_this_one(rig):
    """The other side of that boundary: newer events on the same mission that
    start no round (a move out of the planning states, an update of a field
    that is not a planning input) must not silence a waiting round."""
    mid, seq = started(rig)
    rig.fire('mission.state_changed', Ref('mission', mid),
             payload={'from': 'PLANNING', 'to': 'EXECUTING'})              # starts none
    rig.fire('mission.updated', Ref('mission', mid), payload={'fields': ['priority']})
    rig.ends_as('unavailable')
    assert rig.worker.plan(mid, seq, 'the mission changed') == 'call:unavailable'
    assert len(rig.calls.seen) == 1


def test_the_replan_budget_is_judged_before_the_planner_is_asked(rig):
    """worker.py plan(): REPLANNING and `replan_budget_exhausted` — P3.5 first:
    an exhausted round blocks the mission and asks the model NOTHING: no call,
    no package assembled, no version — whatever the answer would have been."""
    mid = rig.mission_row(state='REPLANNING', max_replans=1)
    rig.place(entities.Plan(id=new_id('plan'), mission_id=mid, plan_version=2,
                            summary='the plan being replaced'))
    seq = rig.fire('mission.state_changed', Ref('mission', mid),
                   payload={'from': 'EXECUTING', 'to': 'REPLANNING'})
    rig.calls.script(AssertionError('an exhausted budget must not ask the model'))
    assert rig.worker.plan(mid, seq, 'a task failed') == 'replan_budget_exhausted'
    assert rig.calls.seen == []
    assert rig.mission().state == 'BLOCKED'
    assert len(rig.where(entities.Plan, mission_id=mid)) == 1              # only the old one
    assert rig.where(entities.ContextPackage) == []


def test_a_replanning_round_with_budget_left_still_asks_the_planner(rig):
    """The boundary of that same branch: the budget guard FAILING (replans
    remain: 1 used of 5) is not the worker's refusal — the round runs and the
    new version replaces the one in force."""
    mid = rig.mission_row(state='REPLANNING', max_replans=5)
    rig.place(entities.Plan(id=new_id('plan'), mission_id=mid, plan_version=2,
                            summary='the plan being replaced'))
    seq = rig.fire('mission.state_changed', Ref('mission', mid),
                   payload={'from': 'EXECUTING', 'to': 'REPLANNING'})
    rig.answer_with(task_answer())
    assert rig.worker.plan(mid, seq, 'a task failed') == 'plan:3'
    assert len(rig.calls.seen) == 1


@pytest.mark.parametrize('payload, want', [
    ({'to': 'REASONING'}, True), ({'to': 'PLANNING'}, True), ({'to': 'REPLANNING'}, True),
    ({'to': 'EXECUTING'}, False), ({}, False), (None, False)],
    ids=['reasoning', 'planning', 'replanning', 'executing', 'no-to', 'no-payload'])
def test_only_a_state_change_into_a_planning_state_starts_a_round(payload, want):
    """worker.py _starts_round(): the state gate, `(e.payload or {})` included —
    a malformed state change with no payload starts nothing, not a KeyError."""
    e = new_event('mission.state_changed', Ref('mission', new_id('mission')),
                  Ref('system', new_id('principal')), payload, workspace=WS)
    assert _starts_round(e) is want


@pytest.mark.parametrize('fields, want', [
    (['requirements'], True), (['objective', 'priority'], True),
    (['priority'], False), ([], False), (None, False)],
    ids=['input', 'mixed', 'not-an-input', 'empty', 'no-fields-key'])
def test_only_a_planning_input_changing_starts_a_round(fields, want):
    """worker.py _starts_round(): the mission.updated side — the same
    `INPUT_FIELDS` set that keeps a package current decides rounds too; a
    payload without the key at all is `{}`-safe."""
    payload = {} if fields is None else {'fields': fields}
    e = new_event('mission.updated', Ref('mission', new_id('mission')),
                  Ref('system', new_id('principal')), payload, workspace=WS)
    assert _starts_round(e) is want


def test_the_mission_filter_answers_for_every_other_subject():
    """worker.py _starts_round(e, mission_id): the newer-round scan must never
    be started by another mission's event, whatever it says."""
    mine = new_id('mission')
    other = new_event('mission.state_changed', Ref('mission', new_id('mission')),
                      Ref('system', new_id('principal')), {'to': 'PLANNING'}, workspace=WS)
    assert _starts_round(other, mine) is False                 # right payload, wrong mission
    mine_e = new_event('mission.state_changed', Ref('mission', mine),
                       Ref('system', new_id('principal')), {'to': 'PLANNING'}, workspace=WS)
    assert _starts_round(mine_e, mine) is True
    assert _starts_round(mine_e) is True                        # unfiltered: still a round


# ── the loop's error paths ────────────────────────────────────────────────

def test_a_round_that_raises_fails_its_event_and_never_the_worker(rig, monkeypatch):
    """worker.py _handle(): `except Exception` — the event carries the failure
    (`error: <Type>: <msg>`, the effects table) and the cursor still moves: one
    malformed plan cannot kill the consumer or wedge the outbox behind it."""
    mid, seq = started(rig)

    def boom(mission_id, round_seq, why):
        raise ValueError('rig: the answer was malformed beyond repair')

    monkeypatch.setattr(rig.worker, 'plan', boom)
    assert rig.worker.pass_once()['changed'] is True
    assert rig.effect(seq) == \
        'error: ValueError: rig: the answer was malformed beyond repair'
    with rig.db.read() as conn:
        assert outbox.head(conn) == seq
        assert conn.execute('SELECT last_seq FROM consumer_cursors WHERE name = ?',
                            (WORKER_MODULE.CONSUMER,)).fetchone()[0] == seq


def test_a_state_change_without_a_reason_still_starts_one_round(rig, monkeypatch):
    """worker.py _handle(): `(e.payload or {}).get('reason') or 'the mission
    changed'` — a reasonless trigger plans exactly one round, with the default
    why (which only a replan prompt ever shows, so a broken fallback there is
    otherwise silent)."""
    mid = rig.mission_row(state='PLANNING')
    seq = rig.fire('mission.state_changed', Ref('mission', mid), payload={'to': 'PLANNING'})
    seen = {}

    def fake_plan(mission_id, round_seq, why):
        seen.update(mission_id=mission_id, round_seq=round_seq, why=why)
        return 'watched'

    monkeypatch.setattr(rig.worker, 'plan', fake_plan)
    assert rig.worker.pass_once()['changed'] is True
    assert seen == {'mission_id': mid, 'round_seq': seq, 'why': 'the mission changed'}
    assert rig.effect(seq) == 'watched'


def test_an_event_that_starts_nothing_is_answered_with_the_empty_string(rig):
    """worker.py _handle(): the `return ''` tail — an unrelated event is not a
    round, and must not pretend to have done work."""
    mid = rig.mission_row(state='EXECUTING')
    seq = rig.fire('mission.updated', Ref('mission', mid), payload={'fields': ['priority']})
    assert rig.worker.pass_once()['changed'] is True
    assert rig.effect(seq) == ''
    assert rig.calls.seen == []


def test_a_gated_round_replans_only_when_the_terms_come_back(rig):
    """worker.py _handle()/_retry_gated(): a terms answer replans the missions
    waiting on a gated CALL and nobody else — the kind match, and the
    `'no round waits on the terms'` fallback (`(planning_blocked or {}).get`,
    the None-mission being its other side)."""
    mid = rig.mission_row(state='PLANNING')
    rig.set_block({'kind': 'call', 'outcome': 'gated', 'round_seq': 1})
    rig.answer_with(task_answer())
    seq = rig.fire('provider_terms.decided', Ref('provider_terms', 'harness-fake'),
                   payload={'harness_id': 'fake', 'headless': True})
    drained(rig)
    assert rig.effect(seq) == 'plan:1'
    assert rig.calls.seen[0]['context_package_id']                     # a real round ran
    assert rig.mission().planning_blocked is None                      # answered: block gone
    # a second terms answer finds nobody waiting — not this mission (it has a plan
    # now) and not the never-blocked one (`or {}` on planning_blocked=None)
    rig.mission_row(state='PLANNING', mid=new_id('mission'))       # a second, idle mission
    rig.ends_as('unavailable')                                         # would fail if called
    seq2 = rig.fire('provider_terms.decided', Ref('provider_terms', 'harness-fake-2'),
                    payload={'harness_id': 'fake-2', 'headless': True})
    drained(rig)
    assert rig.effect(seq2) == 'no round waits on the terms'
    assert len(rig.calls.seen) == 1


def test_a_policy_blocked_round_replans_only_when_the_policy_moves(rig):
    """worker.py _handle()/_retry_gated(kind='policy'): a rule change replans
    the missions a policy DENIAL blocked — and a terms answer must not touch
    them (the two kinds never answer for each other)."""
    mid = rig.mission_row(state='PLANNING')
    rig.set_block({'kind': 'policy', 'policy_decision_id': new_id('policy_decision'),
                   'round_seq': 1})
    rig.answer_with(task_answer())
    seq = rig.fire('policy_rule.created', Ref('policy_rule', new_id('policy_rule')),
                   payload={'before': None, 'after': {'action_class': 'exec'}})
    drained(rig)
    assert rig.effect(seq) == 'plan:1'
    seq2 = rig.fire('provider_terms.decided', Ref('provider_terms', 'harness-fake'),
                    payload={'harness_id': 'fake', 'headless': True})
    drained(rig)
    assert rig.effect(seq2) == 'no round waits on the terms'


def test_a_blocked_round_is_not_replanned_twice_by_later_events(rig):
    """The once, through the retry door: the rule change planned the mission and
    its answer cleared the block — the next policy event finds nobody waiting
    and runs no second call for one block."""
    mid = rig.mission_row(state='PLANNING')
    rig.set_block({'kind': 'policy', 'policy_decision_id': new_id('policy_decision'),
                   'round_seq': 1})
    rig.answer_with(task_answer())
    s1 = rig.fire('policy_rule.created', Ref('policy_rule', new_id('policy_rule')),
                  payload={'before': None})
    drained(rig)
    assert rig.effect(s1) == 'plan:1'
    s2 = rig.fire('policy_rule.retired', Ref('policy_rule', new_id('policy_rule')),
                  payload={'before': {}})
    drained(rig)
    assert rig.effect(s2) == 'no round waits on the policy'   # block answered, cleared
    assert len(rig.calls.seen) == 1


def test_a_stale_package_is_replaced_before_the_prompt_is_built(rig):
    """worker.py _package(): `planner.currency(...)[0]` — a round must never
    run on a package the mission has outgrown: a fresh one is recorded and is
    the one the call carries."""
    mid = rig.mission_row(state='PLANNING')
    stale = rig.package_row(as_of_seq=0)
    rig.set_package(stale)
    seq = rig.fire('mission.updated', Ref('mission', mid),
                   payload={'fields': ['objective']})                 # stale, and the round
    rig.answer_with(task_answer())
    assert rig.worker.plan(mid, seq, 'the objective changed') == 'plan:1'
    got = rig.calls.seen[0]['context_package_id']
    assert got != stale
    assert rig.get(entities.ContextPackage, got).as_of_seq >= seq
    assert len(rig.where(entities.ContextPackage)) == 2


def test_a_current_package_is_reused_and_never_re_assembled(rig):
    """The other side of that branch: `pid is not None and currency[0]` — the
    round reads the package the mission already has and writes no new row."""
    mid = rig.mission_row(state='PLANNING')
    pkg = rig.package_row(as_of_seq=rig.head() + 1)                   # nothing after it
    rig.set_package(pkg)
    seq = rig.fire('mission.state_changed', Ref('mission', mid),
                   payload={'to': 'PLANNING', 'reason': 'started'})
    rig.answer_with(task_answer())
    assert rig.worker.plan(mid, seq, 'the mission started') == 'plan:1'
    assert rig.calls.seen[0]['context_package_id'] == pkg
    assert [p.id for p in rig.where(entities.ContextPackage)] == [pkg]


def test_the_previous_version_is_read_into_the_replan_prompt(rig):
    """worker.py _replan() -> planner.prompt(): a round replacing a version
    carries what that version did — every task, the failed checks, the last
    review, and the checkpoints of the tasks that ended FAILED or BLOCKED
    (and only theirs)."""
    mid = rig.mission_row(state='PLANNING')
    pid = rig.place_plan(mission_id=mid, plan_version=2)
    t1 = rig.place_task(pid, mid, key='t1', title='Add the flag',
                        state='FAILED', failure_class='tests')
    rig.place_task(pid, mid, key='t2', title='Write the docs', state='PENDING')
    rig.place_verification(pid, mid, state='FAILED')
    rig.place_review(pid, mid, verdict='accept', state='ACCEPTED')
    rig.place_checkpoint(t1, mid, open_problems=('the flag name is taken',),
                         next_action='pick another name')
    rig.place_checkpoint(rig.get_last_task_id(), mid, open_problems=('nothing',))  # t2, PENDING
    seq = rig.fire('mission.updated', Ref('mission', mid),
                   payload={'fields': ['requirements']})
    rig.answer_with(task_answer())
    assert rig.worker.plan(mid, seq, 'a check failed') == 'plan:3'
    prompt = rig.calls.seen[0]['prompt']
    assert 'This is a new plan: a check failed' in prompt
    assert 'Previous plan v2:' in prompt
    assert '- t1 Add the flag (FAILED), failed: tests' in prompt
    assert '- t2 Write the docs (PENDING)' in prompt
    assert 'Failed check: %s: code' % mid in prompt
    assert 'Review: accept' in prompt
    assert 'Where t1 stopped: the flag name is taken; next: pick another name' in prompt
    assert 'Where t2 stopped' not in prompt                            # PENDING: not its turn
    assert rig.calls.seen[0]['no_tools'] is True


def test_pending_wakes_the_owner_only_when_there_is_work(rig):
    """worker.py pending(): `if n and self.on_wake is not None` — the wake is
    for real head only (a spurious wake is a busy-spin), and a worker with no
    wake registered still answers, never raises."""
    hits = []
    rig.worker.on_wake = lambda: hits.append(1)
    assert rig.worker.pending() == 0 and hits == []
    mid = rig.mission_row(state='PLANNING')
    rig.fire('mission.state_changed', Ref('mission', mid), payload={'to': 'PLANNING'})
    assert rig.worker.pending() > 0 and len(hits) == 1
    rig.worker.on_wake = None                                          # nothing registered
    assert rig.worker.pending() > 0                                    # and nothing raises


def test_the_planning_worker_sweeps_nothing_and_reports_its_pass(rig):
    """worker.py sweep()/pass_once(): open calls are the knowledge worker's
    boot sweep (P6) — this one must claim none — and a pass says what moved,
    so the runtime's loop idles once the queue is drained."""
    assert rig.worker.sweep() == []
    assert rig.worker.pass_once() == {'changed': False}
    mid, _ = started(rig)
    rig.answer_with(task_answer())
    assert rig.worker.pass_once()['changed'] is True            # the round ran
    drained(rig)
    assert rig.worker.pass_once() == {'changed': False}         # the cursor stayed
    assert rig.mission().state == 'APPROVAL_REQUIRED'           # the plan gate decided

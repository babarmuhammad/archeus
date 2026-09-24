"""Commands: `command(tx, **kwargs) -> response`, run by the writer.

Each writes its rows and the events recording them through the `Tx` it is
given, so both commit together. The response is what the API will return for
the command: the new version and the resulting event seq (api-and-realtime §1).

Commands that need a port (policy, the guard snapshot) are methods of an
object built with those ports — `Missions(policy=...)` — so the writer still
runs `command(tx, **kwargs)` with JSON arguments, and later phases swap a
stub port without touching a caller.
"""

from dataclasses import replace

from ..domain import entities, guards, ids, states
from ..domain.actions import Action
from ..domain.events import new_event
from ..domain.values import Ref
from . import lifecycle


def register_principal(tx, *, kind, scopes=()):
    """A new actor, which is its own actor on its `principal.created` event.

    P2 BOOTSTRAP, not the security model: the only caller is the in-process
    client registering itself on first use, so persistence can run before any
    auth exists. Nothing here checks who may register a principal or with which
    scopes — that belongs to the auth layer (P3.5 local bootstrap, pairing) and
    policy (P9), which will gate this command rather than trust its caller."""
    p = entities.Principal(id=ids.new_id('principal'), kind=kind, scopes=tuple(scopes))
    actor = Ref(kind, p.id)
    tx.insert(p, actor=actor)
    e = tx.append(new_event('principal.created', Ref('principal', p.id), actor,
                            payload={'kind': kind, 'scopes': list(p.scopes)}))
    return {'id': p.id, 'version': 1, 'seq': e.seq}


def create_mission(tx, *, actor, title, objective, project_id=None,
                   workspace_id=ids.GLOBAL_WORKSPACE):
    m = entities.Mission(id=ids.new_id('mission'), workspace_id=workspace_id,
                         project_id=project_id, title=title, objective=objective)
    row = tx.insert(m, actor=actor)
    e = tx.append(new_event('mission.created', Ref('mission', m.id), actor,
                            payload={'title': title}, workspace=workspace_id,
                            project=project_id))
    return {'id': m.id, 'state': m.state, 'version': row.version, 'seq': e.seq}


# ── mission lifecycle (state-machines §2) ──────────────────────────────────

def persisted_facts(tx, row):
    """The guard snapshot from what the database holds. Plans, tasks and
    verifications get their tables with the phases that create them (P3.5 on),
    so today a mission has no active plan and every guard that needs one
    refuses: fail closed, never a vacuous pass."""
    return guards.MissionFacts()


#: `advance`: the exits each decision point tries, in this order; the first
#: that may be taken is taken (state-machines §2, "Orchestration").
DECISIONS = {
    'PLANNING': ('plan_auto_approved', 'plan_needs_approval'),
    'REPLANNING': ('replan_budget_exhausted', 'plan_auto_approved', 'plan_needs_approval'),
    'EXECUTING': ('unrecoverable', 'task_failed_retryable', 'all_tasks_done'),
    'VERIFYING': ('verification_failed', 'awaiting_human_acceptance', 'verified'),
}
#: `resume` goes back to execution only from where an approved plan was in
#: force; from anywhere else the mission starts over from understanding.
PLAN_IN_FORCE = ('EXECUTING', 'VERIFYING')
#: Entering one of these records `Mission.held_from`, which `resume` reads.
HOLDS = ('BLOCKED', 'PAUSED')


def _record_hold(row, to):
    """Set on the way into a hold, cleared on the way out of RESUMED, so the
    value is only ever about the hold the mission is in now."""
    if to in HOLDS:
        return {'held_from': row.entity.state}
    if row.entity.state == 'RESUMED':
        return {'held_from': None}
    return None


def _criterion_failed(f):
    return any(c.check == 'automatic' and c.verification == 'FAILED' for c in f.criteria)


def _result(row, events=(), considered=None):
    out = {'id': row.entity.id, 'state': row.entity.state, 'version': row.version,
           'changed': bool(events), 'seq': events[-1].seq if events else None,
           'transitions': [{'from': e.payload['from'], 'to': e.payload['to'],
                            'trigger': e.payload['trigger'], 'seq': e.seq} for e in events]}
    if considered is not None:
        out['considered'] = considered
    return out


class Missions:
    """Mission actions. Each method is a writer command.

    `policy` is the Policy port (P1 stub until P9); `facts(tx, row)` returns
    the guard snapshot without its policy part, which is added here — the one
    place a mission guard's inputs meet the Policy port."""

    def __init__(self, *, policy, facts=None):
        self.policy = policy
        self.facts = facts or persisted_facts

    def snapshot(self, tx, row, actor=None, declared=False):
        """The facts plus the policy decisions for them. The acting principal
        is passed to the Policy port as context — deciding what it may do is
        the port's job (P9), never this layer's. `declared` marks an explicit
        request (not the engine's `advance`), which is all `unrecoverable`
        reads of the actor."""
        f = self.facts(tx, row)
        m = row.entity
        ctx = {'mission_id': m.id, 'workspace_id': m.workspace_id,
               'project_id': m.project_id, 'plan_version': f.plan_version,
               'actor': None if actor is None else {'kind': actor.kind, 'id': actor.id}}
        decided = tuple(
            (t.key, c, self.policy.evaluate(Action(action_class=c, target='task:%s' % t.key),
                                            ctx).decision)
            for t in f.tasks for c in t.action_classes)
        return replace(f, policy=decided,
                       declared_by=actor.kind if declared and actor is not None else None)

    def _fire(self, tx, mission_id, trigger, *, actor, reason, expected_version=None,
              facts=None):
        return lifecycle.fire(
            tx, entities.Mission, mission_id, trigger, actor=actor, reason=reason,
            expected_version=expected_version, fields=_record_hold,
            facts=facts or (lambda row: self.snapshot(tx, row, actor, declared=True)))

    # ── actions ──

    def fire(self, tx, *, actor, mission_id, trigger, reason, expected_version=None):
        """Any mission trigger, by name: what the engine and later phases use.
        A guarded trigger is judged with the actor as the declaring party (a
        user device firing `unrecoverable` declares the failure)."""
        row, e = self._fire(tx, mission_id, trigger, actor=actor, reason=reason,
                            expected_version=expected_version)
        return _result(row, [e])

    def pause(self, tx, *, actor, mission_id, reason='paused on request',
              expected_version=None):
        row, e = self._fire(tx, mission_id, 'pause', actor=actor, reason=reason,
                            expected_version=expected_version)
        return _result(row, [e])

    def resume(self, tx, *, actor, mission_id, reason='resumed on request',
               expected_version=None):
        """PAUSED -> resume, BLOCKED -> unblock, then out of RESUMED in the same
        transaction: `redispatch` when the mission was held from a state with
        an approved plan in force, `redispatch_before_plan` otherwise. Where it
        was held from is `Mission.held_from`, recorded with the move into the
        hold — current state, so event retention cannot change the answer. A
        hold with no record is refused rather than guessed."""
        row = lifecycle.load(tx, entities.Mission, mission_id)
        trigger = {'PAUSED': 'resume', 'BLOCKED': 'unblock'}.get(row.entity.state)
        if trigger is None:
            raise lifecycle.IllegalTrigger('mission', row.entity.state, 'resume')
        held_from = row.entity.held_from
        if held_from is None:
            raise lifecycle.IllegalTrigger(
                'mission', row.entity.state, 'resume',
                'no record of where the mission was held from; resuming would guess')
        _row, first = self._fire(tx, mission_id, trigger, actor=actor, reason=reason,
                                 expected_version=expected_version)
        then = 'redispatch' if held_from in PLAN_IN_FORCE else 'redispatch_before_plan'
        row, second = self._fire(tx, mission_id, then, actor=actor,
                                 reason='%s (held from %s)' % (reason, held_from))
        return _result(row, [first, second])

    def cancel(self, tx, *, actor, mission_id, reason='cancelled on request',
               expected_version=None):
        """The edge into CANCELLED from where the mission is: `cancel`, or
        `reject` for a plan awaiting approval. EXECUTING has none: pause first."""
        return self._by_state(tx, mission_id, 'cancel', actor=actor, reason=reason,
                              expected_version=expected_version,
                              pick=lambda to, t: to == 'CANCELLED')

    def request_changes(self, tx, *, actor, mission_id, reason, expected_version=None):
        """A plan sent back (APPROVAL_REQUIRED -> PLANNING), or a review
        verdict overridden by the user (REVIEWING -> REPLANNING)."""
        return self._by_state(tx, mission_id, 'request_changes', actor=actor, reason=reason,
                              expected_version=expected_version,
                              pick=lambda to, t: t in ('request_changes', 'changes_requested'))

    def accept(self, tx, *, actor, mission_id, reason='accepted on review',
               expected_version=None):
        """REVIEWING -> COMPLETED. REVIEWING is reachable only through the
        `verified` guard, so nothing completes without verification."""
        row, e = self._fire(tx, mission_id, 'accepted', actor=actor, reason=reason,
                            expected_version=expected_version)
        return _result(row, [e])

    def advance(self, tx, *, actor, mission_id, reason=None, expected_version=None):
        """At a decision point (DECISIONS), take the first exit the facts allow;
        elsewhere, or when none is allowed yet, change nothing. This is the
        engine's step, never a declaration: `unrecoverable` is judged without
        the actor. `considered` says which exits were tried and why."""
        row = lifecycle.load(tx, entities.Mission, mission_id)
        if expected_version is not None and expected_version != row.version:
            raise lifecycle.VersionConflict(mission_id, expected_version, row.version)
        state, considered, f = row.entity.state, [], None
        for trigger in DECISIONS.get(state, ()):
            _to, g = lifecycle.resolve('mission', state, trigger)
            if g is not None:
                f = f or self.snapshot(tx, row, actor)
                verdict = guards.evaluate('mission', trigger, row.entity, f,
                                          version=row.version)
                ok, why = verdict.passed, verdict.reason
            elif trigger == 'verification_failed':
                f = f or self.snapshot(tx, row, actor)
                ok = _criterion_failed(f)
                why = 'an automatic criterion failed' if ok else 'no automatic criterion failed'
            else:                                   # the unconditional fallback
                ok, why = True, '; '.join(c['reason'] for c in considered) or trigger
            considered.append({'trigger': trigger, 'taken': ok, 'reason': why})
            if ok:
                row, e = self._fire(tx, mission_id, trigger, actor=actor,
                                    reason=reason or why,
                                    facts=f or (lambda r: self.snapshot(tx, r, actor)))
                return _result(row, [e], considered)
        return _result(row, [], considered)

    def _by_state(self, tx, mission_id, verb, *, actor, reason, expected_version, pick):
        row = lifecycle.load(tx, entities.Mission, mission_id)
        frm = row.entity.state
        found = [t for f, to, t, _g in states.edges('mission') if f == frm and t and pick(to, t)]
        if not found:
            raise lifecycle.IllegalTrigger('mission', frm, verb)
        row, e = self._fire(tx, mission_id, found[0], actor=actor, reason=reason,
                            expected_version=expected_version)
        return _result(row, [e])

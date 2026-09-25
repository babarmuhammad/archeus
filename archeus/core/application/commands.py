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

from ...infra.db import rows
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
                   workspace_id=ids.GLOBAL_WORKSPACE, success_criteria=(), max_replans=2):
    if project_id is not None and tx.get(entities.Project, project_id) is None:
        raise lifecycle.NotFound(project_id)     # a mission names a registered project (P4)
    m = entities.Mission(id=ids.new_id('mission'), workspace_id=workspace_id,
                         project_id=project_id, title=title, objective=objective,
                         success_criteria=tuple(dict(c) for c in success_criteria),
                         max_replans=max_replans)
    row = tx.insert(m, actor=actor)
    e = tx.append(new_event('mission.created', Ref('mission', m.id), actor,
                            payload={'title': title}, workspace=workspace_id,
                            project=project_id))
    return {'id': m.id, 'state': m.state, 'version': row.version, 'seq': e.seq}


# ── devices and their tokens (P3.5b local auth) ──────────────────────────

def register_device(tx, *, actor, name, platform, token_hash, scopes, expires_at=None):
    """A user device with its first credential, in one transaction: a
    `user_device` principal holding *scopes*, its Device (PAIRING -> ACTIVE by
    `code_redeemed`) and the `tokens` row. Only the token's sha256 arrives here:
    the token itself never enters a command, its arguments or its response.
    *actor* is who vouched for the device (Core's system principal for the local
    token, the minting device for a launch code). Deciding who may do that is
    the caller's (a route scope); nothing here checks it."""
    if not (isinstance(token_hash, str) and entities._HEX64.fullmatch(token_hash)):
        raise ValueError('token_hash is a sha256 hex digest')
    p = entities.Principal(id=ids.new_id('principal'), kind='user_device', scopes=tuple(scopes))
    tx.insert(p, actor=actor)
    tx.append(new_event('principal.created', Ref('principal', p.id), actor,
                        payload={'kind': p.kind, 'scopes': list(p.scopes)}))
    d = entities.Device(id=ids.new_id('device'), principal_id=p.id, name=name, platform=platform)
    tx.insert(d, actor=actor)
    row, e = lifecycle.fire(tx, entities.Device, d.id, 'code_redeemed', actor=actor,
                            reason='a %s device was issued its token' % platform)
    tx.insert_token(token_hash=token_hash, kind='device', principal_id=p.id, scopes=p.scopes,
                    actor=actor, expires_at=expires_at)
    return {'device_id': d.id, 'principal_id': p.id, 'state': row.entity.state,
            'version': row.version, 'seq': e.seq}


def revoke_device(tx, *, actor, device_id, reason='revoked on request'):
    """ACTIVE -> REVOKED, and every token of its principal revoked with it."""
    row, e = lifecycle.fire(tx, entities.Device, device_id, 'revoke', actor=actor, reason=reason)
    tx.revoke_tokens(row.entity.principal_id)
    return _result(row, [e])


# ── mission lifecycle (state-machines §2) ──────────────────────────────────

#: The cost band a plan may reach and still be approved without asking.
# ponytail: one ceiling for every mission; P10 reads it from the mission's
# resource preferences (`max_cost_band`, resource-router §2)
AUTO_APPROVE_CEILING = 'medium'


def active_plan(conn, mission_id):
    """The plan in force: the mission's highest `plan_version` (a replan is a
    new row, never an edit), or None before the first proposal. *conn* is a
    transaction's or a read snapshot's connection."""
    plans = rows.where(conn, entities.Plan, mission_id=mission_id)
    return max(plans, key=lambda r: r.entity.plan_version, default=None)


def persisted_facts(tx, row):
    """The guard snapshot from what the database holds (P3.5): the active
    plan's tasks with their attempt counts, the mission's success criteria with
    the latest verification of each UNDER THAT PLAN, and whether the plan's cost
    band is under the ceiling. Whatever is missing stays unknown, so the guards
    that need it refuse: fail closed, never a vacuous pass."""
    m = row.entity
    plan = active_plan(tx.conn, m.id)
    checked = {}
    if plan is not None:
        for v in tx.where(entities.Verification, plan_id=plan.entity.id):
            if v.entity.subject == Ref('mission', m.id):
                checked[v.entity.criterion] = v.entity.state     # oldest first: latest wins
    criteria = tuple(guards.CriterionFact(c['check'], checked.get(i))
                     for i, c in enumerate(m.success_criteria))
    if plan is None:
        return guards.MissionFacts(criteria=criteria)
    tasks = tuple(
        guards.TaskFact(t.key, t.kind, t.state, t.action_classes,
                        attempts=len(tx.where(entities.Execution, task_id=t.id)),
                        max_attempts=t.max_attempts, failure_class=t.failure_class)
        for t in (r.entity for r in tx.where(entities.Task, plan_id=plan.entity.id)))
    band = plan.entity.estimated_cost
    reviews = tx.where(entities.Review, plan_id=plan.entity.id)
    return guards.MissionFacts(
        plan_version=plan.entity.plan_version, tasks=tasks, criteria=criteria,
        review=reviews[-1].entity.state if reviews else None,
        cost_within_ceiling=None if band is None else (
            entities.COST_BANDS.index(band) <= entities.COST_BANDS.index(AUTO_APPROVE_CEILING)))


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
PLAN_IN_FORCE = guards.PLAN_IN_FORCE
#: Entering one of these records `Mission.held_from`, which `resume` reads.
HOLDS = ('BLOCKED', 'PAUSED')
#: Taking one of these records `Mission.decided_plan_version`, which both read.
PLAN_DECISIONS = ('plan_auto_approved', 'plan_needs_approval')


def _record_hold(row, to):
    """Set on the way into a hold, cleared on the way out of RESUMED, so the
    value is only ever about the hold the mission is in now."""
    if to in HOLDS:
        return {'held_from': row.entity.state}
    if row.entity.state == 'RESUMED':
        return {'held_from': None}
    return None


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
              facts=None, extra=None):
        """The ONE place a mission moves (a scan in test_skeleton keeps it so):
        every mission transition records `held_from` and `decided_plan_version`
        here, so no path can take a plan decision without recording it."""
        given = facts or (lambda row: self.snapshot(tx, row, actor, declared=True))
        judged = []

        def facts_of(row):          # gathered by the guard, after the version check
            judged.append(given(row) if callable(given) else given)
            return judged[-1]

        def fields(row, to):
            out = dict(extra or {}, **(_record_hold(row, to) or {}))
            if trigger in PLAN_DECISIONS:   # the plan the guard judged is the one decided
                out['decided_plan_version'] = judged[-1].plan_version
            return out or None
        return lifecycle.fire(
            tx, entities.Mission, mission_id, trigger, actor=actor, reason=reason,
            expected_version=expected_version, fields=fields, facts=facts_of)

    # ── actions ──

    def fire(self, tx, *, actor, mission_id, trigger, reason, expected_version=None):
        """Any mission trigger, by name: what the engine and later phases use.
        A guarded trigger is judged with the actor as the declaring party (a
        user device firing `unrecoverable` declares the failure)."""
        row, e = self._fire(tx, mission_id, trigger, actor=actor, reason=reason,
                            expected_version=expected_version)
        return _result(row, [e])

    def reasoned(self, tx, *, actor, mission_id, reason, success_criteria=None):
        """REASONING -> PLANNING with the plan just proposed; a mission without
        success criteria takes the plan's (`inferred`) in the same move."""
        extra = None if success_criteria is None else {'success_criteria': success_criteria}
        row, e = self._fire(tx, mission_id, 'reasoned', actor=actor, reason=reason, extra=extra)
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
        """REVIEWING -> COMPLETED, guarded by `accepted`: the latest review of the
        plan in force must accept it (a human overrides a verdict by recording
        their own review, `work.record_review`). REVIEWING is reachable only
        through `verified`, so nothing completes unverified or unreviewed."""
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
            # every decision exit is a guarded edge: advance holds no legality
            # of its own, it only chooses the order (a test keeps it so)
            f = f or self.snapshot(tx, row, actor)
            verdict = guards.evaluate('mission', trigger, row.entity, f, version=row.version)
            ok, why = verdict.passed, verdict.reason
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

"""The planning worker (P8; plan §12, p8-design-gate §1, D5): an outbox consumer
(`consumers.deliver`, at-least-once, handler outside any transaction) that runs
one planning round per event that starts one.

    mission.state_changed -> REASONING | PLANNING | REPLANNING      a round
    mission.updated (its requirements, constraints, …) while planning
    provider_terms.decided while a round waits on a call that was gated
      -> REPLANNING: the replan budget is judged FIRST (P3.5), no call if spent
      -> the mission's context package, or a fresh one when it is stale (P5)
      -> archeus_call(purpose planner, plan.v1)    (ADR-0022 election, the
         ADR-0021 gate re-checked before the spawn, Core validation — the
         structural contract itself — with one retry; P6's path, unchanged)
      -> ok + a plan:     Planning.apply  (one command, with the call's end)
      -> ok + blocking:   Planning.hold
      -> no answer:       Planning.note   (the call ended itself)

"Once" is the database's: a version records its `round_seq`, `(mission_id,
round_seq)` is UNIQUE, and a round is skipped when its version exists, when
the mission left the round's state, or when a newer round has started. A Core
that died mid-call leaves a RouteDecision with no outcome, which the knowledge
worker's boot sweep ends `failed`; redelivery then plans the round again.

The engine does not plan while this worker runs (the runtime starts one or
the other). Nothing here authorises, routes, dispatches, executes or verifies.
"""

import logging

from ...infra import paths
from ...infra.db import rows
from ...infra.eventlog import consumers, outbox
from ..application import calls as C
from ..application import commands
from ..application.planning import PLANNING_STATES
from ..application.work import PolicyDenied
from ..domain import entities
from . import planner

log = logging.getLogger('archeus.core')

CONSUMER = 'plan'


def _starts_round(e, mission_id=None):
    """Does event *e* start a planning round (for *mission_id*, if given)?"""
    if mission_id is not None and e.subject.id != mission_id:
        return False
    if e.type == 'mission.state_changed':
        return (e.payload or {}).get('to') in PLANNING_STATES
    if e.type == 'mission.updated':
        return bool(set((e.payload or {}).get('fields', ())) & set(planner.INPUT_FIELDS))
    return False


class Planner:
    """Plans missions for one Core: `calls` is its `OwnCalls`, `planning` its
    `application.planning.Planning`."""

    def __init__(self, db, *, actor, calls, planning):
        self.db, self.actor, self.calls, self.planning = db, actor, calls, planning
        self.on_wake = None
        self.stopping = lambda: False

    def _do(self, command, **kw):
        return self.db.writer.execute(command, dict(kw, actor=self.actor))

    def pending(self):
        with self.db.read() as conn:
            n = outbox.head(conn) - consumers.cursor(conn, CONSUMER)
        if n and self.on_wake is not None:
            self.on_wake()
        return n

    def sweep(self):
        return []           # open calls are the knowledge worker's boot sweep (P6)

    def pass_once(self):
        return {'changed': consumers.deliver(self.db, CONSUMER, self._handle) > 0}

    def _handle(self, e):
        try:
            if _starts_round(e):
                why = (e.payload or {}).get('reason') or 'the mission changed'
                return self.plan(e.subject.id, e.seq, why)
            if e.type == 'provider_terms.decided':
                return ';'.join(self._retry_gated(e.seq)) or 'no round waits on the terms'
            if e.type in ('policy_rule.created', 'policy_rule.retired', 'user.updated'):
                return (';'.join(self._retry_gated(e.seq, kind='policy'))
                        or 'no round waits on the policy')
            return ''
        except Exception as x:          # this event's failure, never the worker's death
            log.exception('planning for event %d failed', e.seq)
            return 'error: %s: %s' % (type(x).__name__, x)

    def _retry_gated(self, seq, kind='call'):
        """Plan again every mission waiting in a planning state on *kind*: a
        gated call when the terms are answered (P8), a policy denial when the
        policy changes (P9 D24)."""
        with self.db.read() as conn:
            waiting = [r.entity.id for r in rows.where(conn, entities.Mission)
                       if r.entity.state in PLANNING_STATES
                       and (r.entity.planning_blocked or {}).get('kind') == kind]
        why = 'the provider terms were answered' if kind == 'call' else 'the policy changed'
        return [self.plan(mid, seq, why) for mid in waiting]

    def plan(self, mission_id, round_seq, why):
        """One planning round; returns what it did."""
        with self.db.read() as conn:
            row = rows.get(conn, entities.Mission, mission_id)
            if row is None or row.entity.state not in PLANNING_STATES:
                return 'skip: not planning'
            if rows.where(conn, entities.Plan, mission_id=mission_id, round_seq=round_seq):
                return 'skip: round %d already recorded' % round_seq
            newer = conn.execute('SELECT * FROM events WHERE seq > ? AND subject_id = ? '
                                 'ORDER BY seq', (round_seq, mission_id)).fetchall()
            if any(_starts_round(outbox.decode(r), mission_id) for r in newer):
                return 'skip: a newer round started'
        state = row.entity.state
        if state == 'REPLANNING' and self._do(self.planning.work.replan_budget_spent,
                                              mission_id=mission_id):
            return 'replan_budget_exhausted'         # judged before the planner is asked
        pkg_id = self._package(mission_id)
        with self.db.read() as conn:
            m = rows.get(conn, entities.Mission, mission_id).entity
            pkg = rows.get(conn, entities.ContextPackage, pkg_id).entity.to_dict()
            lines, facts = planner.describe(conn, pkg, m)
            replan = _replan(conn, m, why)
        c = self.calls.run(purpose='planner', source={'kind': 'mission', 'id': mission_id},
                           workspace_id=m.workspace_id, project_id=m.project_id,
                           prompt=planner.prompt(m, lines, replan=replan),
                           schema=planner.SCHEMA,
                           check=lambda p: planner.check(p, facts, criteria=m.success_criteria),
                           workdir=paths.archeus_home(), context_package_id=pkg_id)
        base = dict(mission_id=mission_id, during=state, round_seq=round_seq)
        if c.state != 'ok':
            self._do(self.planning.note, outcome=c.state, detail=c.detail,
                     route_decision_id=c.route_decision_id, **base)
            return 'call:%s' % c.state
        called = {'route_decision_id': c.route_decision_id, 'attempts': c.attempts,
                  'account_ref': c.account_ref, 'usage': c.usage, 'context_package_id': pkg_id}
        block = planner.blocking(c.parsed)
        try:
            if block is not None:
                out = self._do(self.planning.hold, called=called,
                               block=planner.resolve_block(block, facts), **base)
                return 'blocked:%s' % out.get('blocked', out.get('why'))
            spec, explicit, asked = planner.resolve(c.parsed, facts)
            out = self._do(self.planning.apply, called=called,
                           proposal={'spec': spec, 'explicit': explicit, 'asked': asked},
                           **base)
            return 'plan:%s' % (out.get('plan_version') or out.get('why'))
        except PolicyDenied as e:
            # refused before anything was written (P3.5); the denial itself is
            # recorded, with the call's end, by the command answering it (P9 D12)
            out = self._do(self.planning.deny, called=called, specs=e.specs or [], **base)
            return 'policy_denied:%s' % (out.get('policy_decision_id') or out.get('why'))
        except Exception as e:
            self._end(c, 'failed', reason='could not record the plan: %s: %s'
                      % (type(e).__name__, e), called=called)
            raise

    def _end(self, c, state, *, reason, called):
        self._do(C.end_call, route_decision_id=c.route_decision_id,
                 outcome={'state': state, 'reason': reason, 'attempts': c.attempts,
                          'account_ref': c.account_ref}, usage=called['usage'] or None)

    def _package(self, mission_id):
        """The mission's package if still current, else a fresh one (P5's engine)."""
        with self.db.read() as conn:
            m = rows.get(conn, entities.Mission, mission_id).entity
            pid = m.context_package_id
            if pid is not None and planner.currency(conn, m, pid)[0]:
                return pid
        return self._do(commands.record_context_package, subject_kind='mission',
                        subject_id=mission_id)['id']


def _replan(conn, m, why):
    """What the previous version did, for a round that replaces one (§14)."""
    prev = commands.active_plan(conn, m.id)
    if prev is None:
        return None
    tasks = sorted((r.entity for r in rows.where(conn, entities.Task, plan_id=prev.entity.id)),
                   key=lambda t: t.key)
    failed = ['%s: %s' % (v.entity.subject.id, v.entity.verifier)
              for v in rows.where(conn, entities.Verification, plan_id=prev.entity.id)
              if v.entity.state == 'FAILED']
    reviews = rows.where(conn, entities.Review, plan_id=prev.entity.id)
    return {'why': why, 'plan_version': prev.entity.plan_version, 'failed': failed,
            'review': reviews[-1].entity.verdict if reviews else None,
            'tasks': [{'key': t.key, 'title': t.title, 'state': t.state,
                       'failure_class': t.failure_class} for t in tasks]}

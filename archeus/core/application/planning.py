"""Planning commands (P8; p8-design-gate §10, §13, §19): what one planning round
writes, deterministically, in ONE writer transaction with the end of its call.

    apply  a validated, resolved plan -> `Work.propose_plan` (PlanVersion DRAFT
           -> PROPOSED, the previous one SUPERSEDED, then the unchanged P3
           plan gate decides the mission)
    hold   a blocking answer -> no plan; the question is posted in the primary
           conversation and the mission records `planning_blocked` (REASONING
           takes `challenge_raised` to BLOCKED; PLANNING / REPLANNING wait in
           place, since no edge there may bypass the replan budget)
    note   a call that did not answer (gated, unavailable, invalid, failed) ->
           `planning_blocked` only; nothing is invented

Each first re-judges the round against the rows of its own transaction: the
mission must still be in the state the round started in, no version may exist
for the round, and the context package the call read must still be current. A
stale result is discarded — the call ends `failed` and the round that the
change started plans instead.

Nothing here evaluates policy, approves, routes, dispatches or verifies: the
mission's decision on a recorded plan is the P3 gate's, inside `propose_plan`.
"""

from ..domain import entities
from ..domain.events import new_event
from ..domain.values import Ref
from ..planning import planner
from . import authorization, lifecycle
from . import calls as C
from .conversation import primary, _message

#: the mission states a planning round runs in
PLANNING_STATES = ('REASONING', 'PLANNING', 'REPLANNING')


def _stale(tx, mission, during, round_seq, package_id):
    """Why this round's result may not be recorded, or ''."""
    if mission.state != during:
        return 'the mission moved from %s to %s during the call' % (during, mission.state)
    if tx.where(entities.Plan, mission_id=mission.id, round_seq=round_seq):
        return 'round %d already recorded a plan' % round_seq
    current, why = planner.currency(tx.conn, mission, package_id)
    return '' if current else why


def _end(tx, actor, called, outcome, **detail):
    C.end_call(tx, actor=actor, route_decision_id=called['route_decision_id'],
               outcome=dict(detail, attempts=called.get('attempts'),
                            account_ref=called.get('account_ref'), **{'state': outcome}),
               usage=called.get('usage') or None)


def _block(tx, actor, m, blocked):
    tx.update(entities.Mission, m.id, {'planning_blocked': dict(blocked)}, actor=actor)
    tx.append(new_event('mission.updated', Ref('mission', m.id), actor, payload={
        'fields': ['planning_blocked'], 'planning_blocked': dict(blocked)},
        workspace=m.workspace_id, project=m.project_id))


def _text(m, block):
    head = ('Planning "%s" goes against what is recorded:' if block['kind'] == 'challenge'
            else 'Planning "%s" needs your answer first:') % m.title
    lines = [head]
    lines += ['- %s' % q for q in block['questions']]
    lines += ['- missing %s: %s' % (x['kind'], x['name']) for x in block['missing']]
    lines += ['- against %s %s: %s' % (c['ref']['kind'], c['ref']['id'], c['why'])
              for c in block['conflicts']]
    lines.append('Reply to this message; nothing is planned until you do.' +
                 (' Then resume the mission.' if m.state == 'REASONING' else ''))
    return '\n'.join(lines)


class Planning:
    """`work` is the P3.5 `Work` (whose `propose_plan` records the version and
    runs the P3 decision tail); `missions` is its `Missions`."""

    def __init__(self, *, work):
        self.work, self.missions = work, work.missions

    def apply(self, tx, *, actor, mission_id, during, round_seq, called, proposal):
        m = lifecycle.load(tx, entities.Mission, mission_id).entity
        stale = _stale(tx, m, during, round_seq, called['context_package_id'])
        if stale:
            _end(tx, actor, called, 'failed', reason='stale: %s' % stale)
            return {'recorded': False, 'why': stale}
        out = self.work.propose_plan(
            tx, actor=actor, mission_id=mission_id, plan=proposal['spec'], round_seq=round_seq,
            route_decision_id=called['route_decision_id'],
            context_package_id=called['context_package_id'],
            explicit=tuple(proposal['explicit']), asked=tuple(proposal['asked']))
        _end(tx, actor, called, 'ok', plan_id=out['plan_id'])
        return dict(out, recorded=out['plan_id'] is not None)

    def hold(self, tx, *, actor, mission_id, during, round_seq, called, block):
        m = lifecycle.load(tx, entities.Mission, mission_id).entity
        stale = _stale(tx, m, during, round_seq, called['context_package_id'])
        if stale:
            _end(tx, actor, called, 'failed', reason='stale: %s' % stale)
            return {'recorded': False, 'why': stale}
        blocked = dict(block, round_seq=round_seq,
                       route_decision_id=called['route_decision_id'],
                       context_package_id=called['context_package_id'])
        card = {'type': block['kind'], 'ref': {'kind': 'mission', 'id': m.id}}
        _message(tx, actor, conversation_id=primary(tx, actor), author='archeus',
                 text=_text(m, block), cards=[card], links=[{'ref': dict(card['ref'])}])
        if m.state == 'REASONING':
            self.missions.challenge(tx, actor=actor, mission_id=m.id, planning_blocked=blocked,
                                    reason='planning needs the user: %s' % block['kind'])
        else:
            _block(tx, actor, m, blocked)
        _end(tx, actor, called, 'ok', planned=False, blocked=block['kind'])
        return {'recorded': False, 'blocked': block['kind']}

    def deny(self, tx, *, actor, mission_id, during, round_seq, called, specs):
        """A plan the policy DENIED (P9 D12): no plan, task or approval was
        written; the denial itself is recorded and the mission blocked for it
        (`authorization.record_plan_denial`), with the call's end."""
        m = lifecycle.load(tx, entities.Mission, mission_id).entity
        stale = _stale(tx, m, during, round_seq, called['context_package_id'])
        if stale:
            _end(tx, actor, called, 'failed', reason='stale: %s' % stale)
            return {'recorded': False, 'why': stale}
        out = authorization.record_plan_denial(tx, actor=actor, policy=self.work.policy,
                                               missions=self.missions, mission_id=mission_id,
                                               specs=specs, round_seq=round_seq)
        _end(tx, actor, called, 'ok', planned=False, denied=out.get('policy_decision_id'))
        return dict(out, planned=False)

    def note(self, tx, *, actor, mission_id, during, round_seq, outcome, detail='',
             route_decision_id=None):
        """A call that ended without an answer (it recorded its own outcome)."""
        m = lifecycle.load(tx, entities.Mission, mission_id).entity
        if m.state != during:
            return {'recorded': False, 'why': 'the mission moved on'}
        _block(tx, actor, m, {'kind': 'call', 'outcome': outcome, 'detail': detail,
                              'round_seq': round_seq, 'route_decision_id': route_decision_id})
        return {'recorded': False, 'blocked': 'call', 'outcome': outcome}

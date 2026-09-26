"""Commands for Archeus's own calls (ADR-0021, ADR-0022; p6-design-gate §5).

A call is recorded like INTENT before a spawn: its RouteDecision is committed
before the adapter runs, so a Core that dies mid-call leaves a decision with no
outcome rather than a call nobody knows was made. The outcome is written once,
with the usage row, when the call ends. A call has no Session and no Execution
(ADR-0022): its usage is ledgered against its RouteDecision.
"""

from ..domain import entities, ids
from ..domain.events import new_event
from ..domain.values import Ref
from . import lifecycle
from .queries import view

#: How a call can end (the outcome's `state`).
OUTCOMES = ('ok', 'gated', 'unavailable', 'model_unavailable', 'timeout', 'failed', 'invalid')


def end_call(tx, *, actor, route_decision_id, outcome, usage=None):
    """Write the outcome (once) and, when the call ran, its usage row."""
    row = tx.get(entities.RouteDecision, route_decision_id)
    if row is None:
        raise lifecycle.NotFound(route_decision_id)
    if row.entity.outcome is not None:
        raise ValueError('route decision %s already has its outcome' % route_decision_id)
    if outcome.get('state') not in OUTCOMES:
        raise ValueError('an own call ends as one of %s' % (OUTCOMES,))
    tx.update(entities.RouteDecision, route_decision_id, {'outcome': dict(outcome)},
              actor=actor)
    if usage is not None:
        u = {k: usage[k] for k in ('tokens_in', 'tokens_out', 'cache_read', 'cache_write',
                                   'cost_usd') if usage.get(k) is not None}
        tx.insert(entities.UsageLedger(id=ids.new_id('usage_ledger'),
                                       route_decision_id=route_decision_id,
                                       account_id=row.entity.account_id,
                                       account_ref=outcome.get('account_ref')
                                       or row.entity.account_ref, **u), actor=actor)
    rd = row.entity
    tx.append(new_event('archeus_call.ended', Ref('route_decision', route_decision_id), actor,
                        payload={'purpose': rd.purpose, 'outcome': dict(outcome),
                                 'usage': dict(usage or {})},
                        workspace=rd.workspace_id or ids.GLOBAL_WORKSPACE,
                        project=rd.project_id))
    return {'route_decision_id': route_decision_id, 'state': outcome['state']}


def decide_provider_terms(tx, *, actor, harness_id, headless, rotation=None, note=''):
    """The user's ADR-0021 answer for one harness. Only a user device may give
    it (the route's `admin` scope; Core's own principal never does)."""
    if actor.kind != 'user_device':
        raise ValueError('only the user answers the provider-terms question')
    row = tx.get(entities.ProviderTerms, harness_id)
    fields = {'headless': headless, 'note': note or ''}
    if rotation is not None:
        fields['rotation'] = rotation
    if row is None:
        t = entities.ProviderTerms(id=harness_id, **fields)
        tx.insert(t, actor=actor)
    else:
        entities.ProviderTerms(**dict(row.entity.to_dict(), **fields))      # validate
        tx.update(entities.ProviderTerms, harness_id, fields, actor=actor)
    out = tx.get(entities.ProviderTerms, harness_id)
    tx.append(new_event('provider_terms.decided', Ref('provider_terms', harness_id), actor,
                        payload={'harness_id': harness_id, 'headless': out.entity.headless,
                                 'rotation': out.entity.rotation}))
    return {'provider_terms': view(out)}


def terms(conn):
    """{harness_id: ProviderTerms} for every harness the user has answered for."""
    from ...infra.db import rows
    return {r.entity.id: r.entity for r in rows.where(conn, entities.ProviderTerms)}

"""What finished executions came to, by (task kind, model, effort): the data a
model or effort threshold is tuned on. Read-only, from rows Core already keeps
(executions, their verifications, their usage ledger rows); it decides nothing.
"""

from ...infra.db import rows
from ..domain import entities


def _add(total, n):
    return total if n is None else (total or 0) + n


def _count(conn, cls, key, keep=lambda e: True):
    n = {}
    for r in rows.where(conn, cls):
        n[key(r.entity)] = n.get(key(r.entity), 0) + bool(keep(r.entity))
    return n


def by_model(conn):
    """One dict per (kind, model, effort), sorted by it: `executions` that ended
    OK or by their own fault, how many of them `passed` or `failed` their latest
    verification (`unverified`: neither), and what they consumed. `tokens` and
    `cost_usd` sum only what was reported (None: nothing was), and `complete` says
    every figure is the harness's own total, so a lower bound is never read as one.
    `cache_read` and `cache_write` sum the same way, and `by_route` splits them by
    the (harness, account_ref, model) of the route decision each ledger row names.
    Rework is counted over the group's own rows: `verification_attempts` is the
    verification rows beyond each execution's first (None when none was verified),
    `changes_requested` the reviews with that verdict on its missions (None when
    they have no review) and `reworked` the executions whose task ran more than once."""
    # ponytail: reads every row of six tables; window it by date when history grows
    kinds = {r.entity.id: r.entity.kind for r in rows.where(conn, entities.Task)}
    verdict = {r.entity.execution_id: r.entity.state for r in rows.where(conn, entities.Verification)
               if r.entity.execution_id and r.entity.state in ('PASSED', 'FAILED')}
    checks = _count(conn, entities.Verification, lambda v: v.execution_id)
    reviews = _count(conn, entities.Review, lambda v: v.mission_id,
                     lambda v: v.verdict == 'changes_requested')
    runs = _count(conn, entities.Execution, lambda e: e.task_id, lambda e: e.charged is not False)
    routes = {}
    ledger = {}
    for r in rows.where(conn, entities.UsageLedger):
        if r.entity.execution_id:
            ledger.setdefault(r.entity.execution_id, []).append(r.entity)
    out, missions = {}, {}
    for r in rows.where(conn, entities.Execution):
        e = r.entity
        if e.state not in ('ENDED_OK', 'ENDED_ERROR') or e.charged is False:
            continue
        k = kinds[e.task_id], e.model, e.effort
        g = out.setdefault(k, {
            'kind': k[0], 'model': e.model, 'effort': e.effort, 'executions': 0,
            'passed': 0, 'failed': 0, 'unverified': 0, 'tokens': None, 'cost_usd': None,
            'cache_read': None, 'cache_write': None, 'by_route': {},
            'verification_attempts': None, 'changes_requested': None, 'reworked': 0,
            'complete': True})
        g['executions'] += 1
        g[{'PASSED': 'passed', 'FAILED': 'failed'}.get(verdict.get(e.id), 'unverified')] += 1
        g['reworked'] += runs[e.task_id] > 1
        if e.id in checks:
            g['verification_attempts'] = (g['verification_attempts'] or 0) + checks[e.id] - 1
        missions.setdefault(k, set()).add(e.mission_id)
        used = ledger.get(e.id, ())
        g['complete'] &= bool(used) and all(u.basis == 'reported_total' for u in used)
        for u in used:
            if u.tokens_in is not None or u.tokens_out is not None:
                g['tokens'] = (g['tokens'] or 0) + (u.tokens_in or 0) + (u.tokens_out or 0)
            if u.cost_usd is not None:
                g['cost_usd'] = (g['cost_usd'] or 0) + u.cost_usd
            g['cache_read'] = _add(g['cache_read'], u.cache_read)
            g['cache_write'] = _add(g['cache_write'], u.cache_write)
            if u.route_decision_id not in routes:
                routes[u.route_decision_id] = rows.get(conn, entities.RouteDecision,
                                                       u.route_decision_id).entity
            d = routes[u.route_decision_id]
            b = g['by_route'].setdefault((d.harness_id, d.account_ref, d.model), {
                'harness': d.harness_id, 'account_ref': d.account_ref, 'model': d.model,
                'cache_read': None, 'cache_write': None})
            b['cache_read'] = _add(b['cache_read'], u.cache_read)
            b['cache_write'] = _add(b['cache_write'], u.cache_write)
    for k, g in out.items():
        g['by_route'] = [g['by_route'][b] for b in sorted(
            g['by_route'], key=lambda b: tuple(x or '' for x in b))]
        if any(m in reviews for m in missions[k]):
            g['changes_requested'] = sum(reviews.get(m, 0) for m in missions[k])
    return [out[k] for k in sorted(out, key=lambda k: tuple(x or '' for x in k))]

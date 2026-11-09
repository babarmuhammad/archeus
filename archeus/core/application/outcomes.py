"""What finished executions came to, by (task kind, model, effort): the data a
model or effort threshold is tuned on. Read-only, from rows Core already keeps
(executions, their verifications, their usage ledger rows); it decides nothing.
"""

from ...infra.db import rows
from ..domain import entities


def by_model(conn):
    """One dict per (kind, model, effort), sorted by it: `executions` that ended
    OK or by their own fault, how many of them `passed` or `failed` their latest
    verification (`unverified`: neither), and what they consumed. `tokens` and
    `cost_usd` sum only what was reported (None: nothing was), and `complete` says
    every figure is the harness's own total, so a lower bound is never read as one."""
    # ponytail: reads every row of four tables; window it by date when history grows
    kinds = {r.entity.id: r.entity.kind for r in rows.where(conn, entities.Task)}
    verdict = {r.entity.execution_id: r.entity.state for r in rows.where(conn, entities.Verification)
               if r.entity.execution_id and r.entity.state in ('PASSED', 'FAILED')}
    ledger = {}
    for r in rows.where(conn, entities.UsageLedger):
        if r.entity.execution_id:
            ledger.setdefault(r.entity.execution_id, []).append(r.entity)
    out = {}
    for r in rows.where(conn, entities.Execution):
        e = r.entity
        if e.state not in ('ENDED_OK', 'ENDED_ERROR') or e.charged is False:
            continue
        g = out.setdefault((kinds[e.task_id], e.model, e.effort), {
            'kind': kinds[e.task_id], 'model': e.model, 'effort': e.effort, 'executions': 0,
            'passed': 0, 'failed': 0, 'unverified': 0, 'tokens': None, 'cost_usd': None,
            'complete': True})
        g['executions'] += 1
        g[{'PASSED': 'passed', 'FAILED': 'failed'}.get(verdict.get(e.id), 'unverified')] += 1
        used = ledger.get(e.id, ())
        g['complete'] &= bool(used) and all(u.basis == 'reported_total' for u in used)
        for u in used:
            if u.tokens_in is not None or u.tokens_out is not None:
                g['tokens'] = (g['tokens'] or 0) + (u.tokens_in or 0) + (u.tokens_out or 0)
            if u.cost_usd is not None:
                g['cost_usd'] = (g['cost_usd'] or 0) + u.cost_usd
    return [out[k] for k in sorted(out, key=lambda k: tuple(x or '' for x in k))]

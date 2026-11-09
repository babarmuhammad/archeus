"""What finished executions came to, by (task kind, model, effort): the data a
model or effort threshold is tuned on. Read-only, from rows Core already keeps
(executions, their verifications, their usage ledger rows); it decides nothing.
"""

import re

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
    they have no review) and `reworked` the executions whose task ran more than once
    (one still pending, not yet spawned, is not a run)."""
    # ponytail: reads every row of six tables; window it by date when history grows
    kinds = {r.entity.id: r.entity.kind for r in rows.where(conn, entities.Task)}
    verdict = {r.entity.execution_id: r.entity.state for r in rows.where(conn, entities.Verification)
               if r.entity.execution_id and r.entity.state in ('PASSED', 'FAILED')}
    checks = _count(conn, entities.Verification, lambda v: v.execution_id)
    reviews = _count(conn, entities.Review, lambda v: v.mission_id,
                     lambda v: v.verdict == 'changes_requested')
    runs = _count(conn, entities.Execution, lambda e: e.task_id,
                 lambda e: e.charged is not False and e.state != 'INTENT')
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


#: (purpose, source kind) of the own call each learning pass makes (`knowledge.passes`)
PASSES = {('knowledge_extraction', 'repository_inspection'): 'knowledge',
          ('knowledge_extraction', 'meeting'): 'decisions', ('lesson', 'mission'): 'lessons',
          ('knowledge_extraction', 'project'): 'consolidate'}


def by_pass(conn):
    """One dict per learning pass that made a model call, sorted by name: `calls`
    that reached a model (a gated or unavailable call has no usage row, so is not
    counted) and the `tokens_in`, `tokens_out`, `cache_read`, `cache_write` and
    `cost_usd` they reported. Each sums only what was reported (None: nothing was),
    and `complete` says every call's figures are the harness's own total, as in
    `by_model`. Other own calls (planner, review, ...) are not passes and are left out."""
    passes = {r.entity.id: PASSES[r.entity.purpose, r.entity.source.kind]
              for r in rows.where(conn, entities.RouteDecision)
              if r.entity.subject.kind == 'archeus_call' and r.entity.source
              and (r.entity.purpose, r.entity.source.kind) in PASSES}
    out = {}
    for r in rows.where(conn, entities.UsageLedger):
        u = r.entity
        if u.route_decision_id not in passes:
            continue
        g = out.setdefault(passes[u.route_decision_id], {
            'pass': passes[u.route_decision_id], 'calls': 0, 'tokens_in': None,
            'tokens_out': None, 'cache_read': None, 'cache_write': None, 'cost_usd': None,
            'complete': True})
        g['calls'] += 1
        g['complete'] &= u.basis == 'reported_total'
        for f in ('tokens_in', 'tokens_out', 'cache_read', 'cache_write', 'cost_usd'):
            g[f] = _add(g[f], getattr(u, f))
    return [out[k] for k in sorted(out)]


def graph_size(conn):
    """One dict per project holding live knowledge (CANDIDATE or CONFIRMED), sorted by
    id: its `items`, `graph_bytes` (their title and text, UTF-8), `source_bytes` (the
    payload of each repository's latest COMPLETED inspection; None when there is none)
    and `ratio`, graph over source (None without a source). Reported, never judged:
    nothing refuses an item on it (T-1093 step 1). Items read from meetings or missions
    count in the graph and have no source here, so for them the ratio reads high."""
    graph = {}
    for r in rows.where(conn, entities.KnowledgeItem):
        k = r.entity
        if k.project_id is not None and k.state in ('CANDIDATE', 'CONFIRMED'):
            g = graph.setdefault(k.project_id, [0, 0])
            g[0] += 1
            g[1] += len((k.title + k.text).encode('utf-8'))
    out = []
    for pid in sorted(graph):
        source = None
        for repo in rows.where(conn, entities.Repository, project_id=pid):
            done = [i.entity for i in rows.where(conn, entities.RepositoryInspection,
                                                 repository_id=repo.entity.id)
                    if i.entity.state == 'COMPLETED']
            art = (rows.get(conn, entities.Artifact, done[-1].payload_sha256)
                   if done and done[-1].payload_sha256 else None)
            if art is not None:
                source = (source or 0) + art.entity.size
        n, size = graph[pid]
        out.append({'project_id': pid, 'items': n, 'graph_bytes': size, 'source_bytes': source,
                    'ratio': round(size / source, 2) if source else None})
    return out


#: the window and threshold of the recurrence read (T-1106): the project's last
#: RECUR_WINDOW reviews, a finding in at least RECUR_MISSIONS distinct missions
RECUR_WINDOW, RECUR_MISSIONS = 10, 3
_NOISE = re.compile(r'[\d/\\]+')


def _finding_key(text):
    return ' '.join(_NOISE.sub(' ', text).casefold().split())


def recurring_findings(conn, project_id):
    """The review findings (requirements missing, regressions, risks) that recur in
    the project's last RECUR_WINDOW reviews, by a normalised string (casefolded,
    whitespace collapsed, digits and path separators dropped): one dict per key seen
    in at least RECUR_MISSIONS distinct missions, most missions first, with the
    first wording seen. No model and no state change: the baseline the
    model-phrased review lessons are judged against (T-1106 step 1)."""
    missions = {r.entity.id for r in rows.where(conn, entities.Mission, project_id=project_id)}
    reviews = [r.entity for r in rows.where(conn, entities.Review)
               if r.entity.mission_id in missions][-RECUR_WINDOW:]
    seen = {}
    for r in reviews:
        for f in ('requirements_missing', 'regressions', 'risks'):
            for text in getattr(r, f):
                k = _finding_key(text)
                if k:
                    g = seen.setdefault(k, {'finding': text, 'missions': set()})
                    g['missions'].add(r.mission_id)
    out = [{'finding': g['finding'], 'key': k, 'missions': sorted(g['missions'])}
           for k, g in seen.items() if len(g['missions']) >= RECUR_MISSIONS]
    return sorted(out, key=lambda g: (-len(g['missions']), g['key']))

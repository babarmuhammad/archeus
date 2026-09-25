"""The context engine (context-and-knowledge §2; p5-design-gate): given a
subject, which existing information is relevant, at which level, and why.

Two halves. `gather()` reads candidates out of one snapshot — the subject, its
project's state (P4's projects, repositories, inspections and assessments), its
knowledge items and the project's recent events — and never writes. `select()`
is a pure function of those candidates: freshness, the relevance formula,
conflicts between checkable constraints, and the per-level token budget. Both
are deterministic: the same rows and the same request give the same package,
because "now" is the snapshot's last event, not the clock.

No model, no harness, no router and no execution is reachable from here
(test_context_structure.py walks the import closure).
"""

import json
from datetime import datetime, timedelta
from itertools import combinations

from ...infra.db import rows
from ...infra.db.writer import NotFound
from ...infra.eventlog import outbox
from ...infra.search import bm25
from ..domain import entities, events, ids
from . import levels as P
from claude_sessions.lexical import tokens_estimate

_KNOWLEDGE_LEVEL = {'LESSON': 'L3', 'PREFERENCE': 'L4'}       # every other project type: L1
_DECIDING = ('ARCHITECTURE', 'DECISION', 'STANDARD')
_NOT_CONFIRMED = {'CANDIDATE': 'not confirmed (a candidate)', 'RETRACTED': 'retracted',
                  'EXPIRED': 'expired (its validity ended)'}


def _when(stamp):
    return datetime.fromisoformat(stamp.replace('Z', '+00:00'))


def _cand(ref, level, store, type_, source_kind, source_ref, observed_at, text, authority,
          reason, stale=False, **extra):
    return dict(extra, ref=ref, level=level, store=store, type=type_, source_kind=source_kind,
                source_ref=source_ref, observed_at=observed_at, text=text,
                authority=authority, reason=reason, stale=stale)


# ── gather: one read snapshot ──────────────────────────────────────────────

def _knowledge(conn, workspace_id, project_id, out, excluded):
    every = rows.where(conn, entities.KnowledgeItem)
    superseding = {r.entity.supersedes_id: r.entity.id for r in every
                   if r.entity.supersedes_id and r.entity.state == 'CONFIRMED'}
    for r in every:
        k = r.entity
        if k.project_id is None and k.workspace_id in (workspace_id, ids.GLOBAL_WORKSPACE):
            level, scope = 'L4', 'global'
        elif project_id is not None and k.project_id == project_id:
            level, scope = _KNOWLEDGE_LEVEL.get(k.type, 'L1'), 'this project\'s'
        else:
            continue                                    # out of scope: never a candidate
        ref = {'kind': 'knowledge_item', 'id': k.id, 'version': r.version}
        if k.state == 'SUPERSEDED':
            by = superseding.get(k.id)
            excluded.append({'ref': ref, 'level': level, 'freshness': 'superseded',
                             'reason': 'superseded by %s' % by if by else 'superseded'})
            continue
        if k.state != 'CONFIRMED':
            excluded.append({'ref': ref, 'level': level, 'freshness': 'current',
                             'reason': _NOT_CONFIRMED[k.state]})
            continue
        authority = ('explicit' if k.origin == 'explicit'
                     else 'confirmed' if k.type in _DECIDING else 'inferred')
        text = ' '.join([k.title, k.text] + ([json.dumps(k.constraint, sort_keys=True)]
                                             if k.constraint else []))
        out.append(_cand(ref, level, 'knowledge', k.type, 'knowledge_item', k.id, r.created_at,
                         text, authority, 'CONFIRMED %s, %s' % (k.type, scope),
                         constraint=k.constraint, created_at=r.created_at))


def _project(conn, project_id, out, missing):
    prow = rows.get(conn, entities.Project, project_id)
    p = prow.entity
    repos = rows.where(conn, entities.Repository, project_id=project_id)
    lines = ['%s (%s, %s) architecture %s at %s' % (
        r.entity.path, r.entity.kind, r.entity.default_branch or 'no branch',
        r.entity.architecture_state, r.entity.last_revision or 'no revision') for r in repos]
    out.append(_cand({'kind': 'project', 'id': p.id, 'version': prow.version}, 'L1', 'state',
                     'PROJECT', 'project', p.id, prow.updated_at,
                     '%s %s\n%s' % (p.name, p.state, '\n'.join(lines)), 'explicit',
                     'the project this work is in: its state and repositories'))
    if not repos:
        missing.append('project %s has no repository registered' % p.id)
    for r in repos:
        repo = r.entity
        stale = repo.architecture_state == 'STALE'
        done = [i for i in rows.where(conn, entities.RepositoryInspection,
                                      repository_id=repo.id) if i.entity.state == 'COMPLETED']
        if not done:
            missing.append('%s has no completed inspection' % repo.path)
        else:
            irow = done[-1]
            i = irow.entity
            text = '%s\nlanguages %s\nframeworks %s\ntest %s\nbuild %s\ndocs %s\nagent config %s' % (
                repo.path, ' '.join(lang for lang, _n in i.languages), ' '.join(i.frameworks),
                ' | '.join(i.test_commands), ' | '.join(i.build_commands), ' '.join(i.docs),
                ' '.join(i.agent_config))
            reason = 'latest completed inspection of %s at %s' % (repo.path, i.revision)
            if stale:
                reason += '; stale: the repository moved past it'
            out.append(_cand({'kind': 'repository_inspection', 'id': i.id,
                              'version': irow.version}, 'L1', 'state', 'INSPECTION',
                             'repository_inspection', i.id, i.inspected_at or irow.updated_at,
                             text, 'extracted', reason, stale=stale))
        violated = [f for f in repo.findings if f['status'] == 'violated']
        if violated:
            reason = '%d architecture constraint(s) violated in %s: open blockers' % (
                len(violated), repo.path)
            if stale:
                reason += '; stale: assessed at %s, which the repository moved past' % (
                    repo.last_revision,)
            out.append(_cand({'kind': 'repository', 'id': repo.id, 'version': r.version},
                             'L1', 'state', 'DRIFT', 'repository', repo.id, r.updated_at,
                             '\n'.join(f['constraint'] for f in violated), 'extracted',
                             reason, stale=stale,
                             constraints=sorted(f['constraint_id'] for f in violated)))


def _history(conn, project_id, subject_id, as_of_at, out):
    if as_of_at is None:
        return
    since = (_when(as_of_at) - timedelta(days=P.HISTORY_WINDOW_DAYS)).isoformat(
        timespec='milliseconds').replace('+00:00', 'Z')
    got = conn.execute(
        "SELECT * FROM events WHERE project_id = ? AND visibility = 'user' AND at >= ? "
        "AND subject_id != ? ORDER BY seq DESC LIMIT ?",
        (project_id, since, subject_id, P.HISTORY_CANDIDATES)).fetchall()
    for r in got:
        e = outbox.decode(r)
        text = '%s %s %s' % (e.type, events.REGISTRY[e.type][4],
                             json.dumps(e.payload, sort_keys=True))
        out.append(_cand({'kind': 'event', 'id': e.id, 'seq': e.seq}, 'L3', 'history', e.type,
                         e.subject.kind, e.subject.id, e.at, text, 'extracted',
                         '%s in this project within %d days' % (e.type,
                                                                P.HISTORY_WINDOW_DAYS)))


def snapshot(conn):
    """(as_of_seq, as_of_at): the last event this snapshot contains."""
    r = conn.execute('SELECT at FROM events ORDER BY seq DESC LIMIT 1').fetchone()
    return outbox.head(conn), None if r is None else r[0]


def gather(conn, subject_kind, subject_id):
    """The candidates for one subject, read and never written."""
    as_of_seq, as_of_at = snapshot(conn)
    cands, excluded, missing = [], [], []
    if subject_kind == 'mission':
        mrow = rows.get(conn, entities.Mission, subject_id)
        if mrow is None:
            raise NotFound(subject_id)
        m = mrow.entity
        workspace_id, project_id = m.workspace_id, m.project_id
        query = '%s\n%s' % (m.title, m.objective)
        text = '\n'.join([m.title, m.objective] + [c['text'] for c in m.success_criteria])
        cands.append(_cand({'kind': 'mission', 'id': m.id, 'version': mrow.version}, 'L0',
                           'state', 'MISSION', 'mission', m.id, mrow.updated_at, text,
                           'explicit', 'the mission this context is assembled for'))
        if project_id is None:
            missing.append('the mission names no project, so there is no project, related '
                           'or project-history context (L1-L3)')
    elif subject_kind == 'project':
        prow = rows.get(conn, entities.Project, subject_id)
        if prow is None:
            raise NotFound(subject_id)
        workspace_id, project_id, query = prow.entity.workspace_id, subject_id, ''
    else:
        raise ValueError('a context subject is one of %s' % (entities.CONTEXT_SUBJECTS,))
    if project_id is not None:
        _project(conn, project_id, cands, missing)
        _history(conn, project_id, subject_id, as_of_at, cands)
    _knowledge(conn, workspace_id, project_id, cands, excluded)
    return {'workspace_id': workspace_id, 'project_id': project_id, 'query': query,
            'as_of_seq': as_of_seq, 'as_of_at': as_of_at, 'candidates': cands,
            'excluded': excluded, 'missing_information': missing}


# ── select: pure ───────────────────────────────────────────────────────────

def _recency(observed_at, as_of_at):
    if observed_at is None or as_of_at is None:
        return 0.0
    age = (_when(as_of_at) - _when(observed_at)).total_seconds() / 86400
    return min(1.0, max(0.0, 1.0 - age / P.HISTORY_WINDOW_DAYS))


def _clash(a, b):
    """Why two checkable constraints cannot both hold, or None (D4)."""
    if a['kind'] == b['kind'] == 'framework_pinned':
        sa, sb = a['spec'], b['spec']
        if (sa['package'] == sb['package'] and sa.get('version') is not None
                and sb.get('version') is not None and sa['version'] != sb['version']):
            return 'both pin %s, to %s and to %s' % (sa['package'], sa['version'], sb['version'])
    if a['kind'] == b['kind'] == 'require_layering':
        la, lb = a['spec']['layers'], b['spec']['layers']
        for x, y in combinations(la, 2):            # x above y in a
            if x in lb and y in lb and lb.index(y) < lb.index(x):
                return 'one layering puts %s above %s, the other %s above %s' % (x, y, y, x)
    return None


def conflicts(cands):
    """Pairs of CONFIRMED in-scope constraints that cannot both hold; the newer
    (later created, then larger id) is preferred. Prose is never compared: that
    is P6's `contradicts` relation, not a similarity guess."""
    ks = sorted((c for c in cands if c['store'] == 'knowledge' and c.get('constraint')),
                key=lambda c: (c['created_at'], c['ref']['id']))
    out = []
    for older, newer in combinations(ks, 2):
        why = _clash(older['constraint'], newer['constraint'])
        if why:
            out.append({'items': [older['ref']['id'], newer['ref']['id']],
                        'preferred': newer['ref']['id'], 'kind': older['constraint']['kind'],
                        'reason': '%s; the newer, %s, is preferred' % (why, newer['ref']['id'])})
    return out


def _key(c):
    return (-c['relevance'], c['ref']['kind'], c['ref']['id'])


def select(gathered, *, query=None, levels=P.LEVELS, limit_tokens=P.DEFAULT_BUDGET_TOKENS):
    """The package body for *gathered* candidates: scored, conflicts found, each
    level cut to its budget. Pure: no reads, no writes, no clock."""
    query = gathered['query'] if query is None else query
    cands = [dict(c) for c in gathered['candidates']]
    lex = bm25.normalised(query, {i: c['text'] for i, c in enumerate(cands)})
    for i, c in enumerate(cands):
        score, matched = lex[i]
        c['signals'] = {k: round(v, 6) for k, v in {
            'lex': score, 'anchor': 0.0, 'link': 0.0,
            'rec': _recency(c['observed_at'], gathered['as_of_at']),
            'auth': P.AUTHORITY[c['authority']], 'conf': 0.0,
            'stale': 1.0 if c['stale'] else 0.0, 'useless': 0.0}.items()}
        c['relevance'] = round(P.relevance(c['signals']), 6)
        c['tokens'] = tokens_estimate(c['text'])
        if matched:
            c['reason'] += '; matches %s' % ', '.join(matched[:8])
    found = conflicts(cands)
    for f in found:
        for c in cands:
            if c['ref']['id'] == f['items'][0]:
                c['reason'] += '; conflicts with %s, which is preferred' % f['preferred']
    excluded = list(gathered['excluded'])
    chosen, budget, carry = [], {}, 0
    for level in P.LEVELS:
        quota = int(limit_tokens * P.SHARES[level]) + carry
        mine = sorted((c for c in cands if c['level'] == level), key=_key)
        if level not in levels:
            excluded += [{'ref': c['ref'], 'level': level, 'freshness': _fresh(c),
                          'reason': 'level %s is not in scope' % level} for c in mine]
            budget[level] = {'limit_tokens': 0, 'used_tokens': 0}
            carry = quota
            continue
        used = 0
        for c in mine:
            if used + c['tokens'] <= quota:
                chosen.append(c)
                used += c['tokens']
            else:
                excluded.append({'ref': c['ref'], 'level': level, 'freshness': _fresh(c),
                                 'reason': 'over the %s budget: needs %d tokens, %d left' % (
                                     level, c['tokens'], quota - used)})
        budget[level] = {'limit_tokens': quota, 'used_tokens': used}
        carry = quota - used
    order = {s: i for i, s in enumerate(P.STORES)}
    chosen.sort(key=lambda c: (P.LEVELS.index(c['level']), order[c['store']]) + _key(c))
    items = [{'ref': c['ref'], 'level': c['level'], 'store': c['store'], 'type': c['type'],
              'source_kind': c['source_kind'], 'source_ref': c['source_ref'],
              'observed_at': c['observed_at'], 'freshness': _fresh(c),
              'relevance': c['relevance'], 'signals': c['signals'], 'reason': c['reason'],
              'tokens': c['tokens'],
              'conflicts_with': [f['preferred'] for f in found
                                 if f['items'][0] == c['ref']['id']]}
             for c in chosen]
    return {'query': query, 'levels': [lv for lv in P.LEVELS if lv in levels],
            'budget': {'limit_tokens': limit_tokens,
                       'used_tokens': sum(i['tokens'] for i in items), 'levels': budget},
            'scoring': {'weights': dict(P.WEIGHTS), 'authority': dict(P.AUTHORITY),
                        'recency_window_days': P.HISTORY_WINDOW_DAYS},
            'items': items, 'excluded': excluded, 'conflicts': found, 'assumptions': [],
            'missing_information': list(gathered['missing_information'])}


def _fresh(c):
    return 'stale' if c['stale'] else 'current'


def assemble(conn, subject_kind, subject_id, *, query=None, levels=P.LEVELS,
             limit_tokens=P.DEFAULT_BUDGET_TOKENS):
    """A context package, without an id: read, scored and budgeted, never
    written. `preview` returns it; a mission's `context_ready` records it."""
    if not set(levels) <= set(P.LEVELS):
        raise ValueError('levels are %s' % ', '.join(P.LEVELS))
    if isinstance(limit_tokens, bool) or not isinstance(limit_tokens, int) or limit_tokens < 1:
        raise ValueError('limit_tokens is an integer >= 1')
    g = gather(conn, subject_kind, subject_id)
    body = select(g, query=query, levels=levels, limit_tokens=limit_tokens)
    return dict(body, workspace_id=g['workspace_id'], project_id=g['project_id'],
                subject_kind=subject_kind, subject_id=subject_id, as_of_seq=g['as_of_seq'],
                as_of_at=g['as_of_at'])

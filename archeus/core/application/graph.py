"""The graph queries (p18-design-gate A1, A2, A4-A6): a bounded neighbourhood of
the relationships Core already records, and a focused view of a repository's
stored import graph. Read-only: every function takes a read connection and
nothing here writes, infers, ranks or routes.

Every edge is read from the column (or the `Relation` row) that records it,
from the row that HOLDS the field towards the row it names — the same fields,
in the same words' order, as the list mapper `clients/app/src/graph/relations.ts`
and the TUI's `present.py` (held equal by `parity.json` until P19 moves both
onto this module). A few STRUCTURAL edges are the containment columns no list
function shows (p18 V8); they carry the hierarchy the renderer collapses by.
"""

import functools
import json
import logging
import posixpath

from ...infra.db import rows
from ...infra.db.writer import NotFound
from ...infra.eventlog import outbox
from ..domain import entities as E, ids, states
from ..redact import redact

LABEL_MAX = 120
DEPTH_MAX = 2
LIMIT_MAX = 1000
LIMIT_DEFAULT = 500
EDGE_MAX = 4000

log = logging.getLogger('archeus.core')
_MISSING = set()  # payload shas already reported missing (A5: logged once each)

# kind -> (entity class, machine or None); order is the cap's kind rank (A6)
KINDS = {
    'mission': (E.Mission, 'mission'), 'execution': (E.Execution, 'execution'),
    'task': (E.Task, 'task'), 'plan': (E.Plan, 'plan'), 'session': (E.Session, 'session'),
    'verification': (E.Verification, 'verification'), 'review': (E.Review, 'review'),
    'approval': (E.Approval, 'approval'), 'route_decision': (E.RouteDecision, None),
    'repository': (E.Repository, 'architecture'),
    'knowledge_item': (E.KnowledgeItem, 'knowledge_item'), 'meeting': (E.Meeting, None),
    'automation_run': (E.AutomationRun, 'automation_run'),
    'automation': (E.Automation, 'automation'), 'policy_decision': (E.PolicyDecision, None),
    'context_package': (E.ContextPackage, None), 'project': (E.Project, None),
}
RANK = {k: i for i, k in enumerate(KINDS)}
#: what a route decision may show (A2, P10): recorded selection facts only —
#: never its explanation, requirements, candidates or input snapshot
ROUTE_ATTRS = ('harness_id', 'account_id', 'model', 'effort', 'result', 'fallback_from')


def _terminal(machine):
    """States with no way out: a settled row ranks after an open one (A6)."""
    if machine is None:
        return frozenset()
    moving = {frm for frm, to, _t, _g in states.edges(machine) if to != states.END}
    return frozenset(s for s in states.states(machine) if s not in moving)


TERMINAL = {k: _terminal(m) for k, (_c, m) in KINDS.items()}


def clean_label(text):
    """One inert line of at most LABEL_MAX characters, secrets redacted."""
    s = redact(' '.join(str(text or '').split()))
    s = ''.join(c for c in s if c.isprintable())
    return s if len(s) <= LABEL_MAX else s[:LABEL_MAX - 1] + '…'


def _label(kind, e):
    if kind == 'mission':
        return e.title
    if kind == 'plan':
        return 'Plan v%s' % e.plan_version
    if kind == 'task':
        return e.title or e.key
    if kind == 'execution':
        return 'Attempt %s' % e.attempt
    if kind == 'session':
        return 'Session on %s' % e.harness_id
    if kind == 'verification':
        return 'Verification (%s)' % e.verifier
    if kind == 'review':
        return 'Review' + (' — %s' % e.verdict if e.verdict else '')
    if kind == 'approval':
        return 'Approval: %s' % e.kind
    if kind == 'route_decision':
        return ' · '.join(x for x in (e.harness_id, e.model) if x) or 'Route decision'
    if kind == 'policy_decision':
        return 'Policy: %s' % e.decision
    if kind == 'context_package':
        return 'Context for %s' % e.subject_kind
    if kind == 'knowledge_item':
        return e.title
    if kind in ('meeting', 'automation', 'project'):
        return e.name
    if kind == 'repository':
        return posixpath.basename(e.path.replace('\\', '/').rstrip('/')) or e.path
    if kind == 'automation_run':
        return 'Run at event %s' % e.triggering_event_seq
    return kind


def _parent(kind, e):
    """The containment field (A2): what the renderer collapses a node into."""
    ref = None
    if kind in ('repository', 'mission', 'knowledge_item', 'meeting', 'context_package',
                'automation'):
        ref = ('project', e.project_id)
    elif kind == 'session':
        ref = ('mission', e.mission_id) if e.mission_id else ('project', e.project_id)
    elif kind == 'plan':
        ref = ('mission', e.mission_id)
    elif kind == 'task':
        ref = ('plan', e.plan_id)
    elif kind == 'execution':
        ref = ('task', e.task_id)
    elif kind in ('verification', 'review'):
        ref = ('plan', e.plan_id)
    elif kind in ('approval', 'policy_decision'):
        ref = ('mission', e.mission_id)
    elif kind == 'route_decision':
        ref = ('task', e.task_id) if e.task_id else ('mission', e.mission_id)
    elif kind == 'automation_run':
        ref = ('automation', e.automation_id)
    return {'kind': ref[0], 'id': ref[1]} if ref and ref[1] else None


# ── edges held by a row (A1) ────────────────────────────────────────────────

def _edge(out, holder, field, kind, value, **extra):
    if isinstance(value, str) and value:
        out.append(dict({'from': holder, 'to': {'kind': kind, 'id': value}, 'field': field,
                         'rel': None, 'tier': None, 'inactive': False, 'structural': False},
                        **extra))


def held_edges(conn, kind, e):
    """The edges the row *e* of *kind* holds, from its own columns (and, for a
    mission, the pending approval `get_mission` derives the same way)."""
    me = {'kind': kind, 'id': e.id}
    out = []
    if kind == 'mission':
        _edge(out, me, 'missions.project_id', 'project', e.project_id)
        _edge(out, me, 'Mission.context_package_id', 'context_package', e.context_package_id)
        o = e.origin_ref
        if o is not None and o.kind:
            _edge(out, me, 'Mission.origin_ref', o.kind, o.id)
        pending = [r.entity.id for r in rows.where(conn, E.Approval, mission_id=e.id)
                   if r.entity.state == 'PENDING']
        if pending:
            _edge(out, me, 'approvals.mission_id', 'approval', pending[-1])
    elif kind == 'plan':
        _edge(out, me, 'plans.mission_id', 'mission', e.mission_id,
              inactive=e.state in ('SUPERSEDED', 'REJECTED'))
        _edge(out, me, 'plans.supersedes_plan_id', 'plan', e.supersedes_plan_id)
        _edge(out, me, 'Plan.context_package_id', 'context_package', e.context_package_id)
        _edge(out, me, 'Plan.route_decision_id', 'route_decision', e.route_decision_id)
    elif kind == 'task':
        _edge(out, me, 'tasks.plan_id', 'plan', e.plan_id, structural=True)
        if e.depends_on:
            by_key = {r.entity.key: r.entity.id for r in rows.where(conn, E.Task, plan_id=e.plan_id)}
            for k in e.depends_on:
                _edge(out, me, 'Task.depends_on', 'task', by_key.get(k))
    elif kind == 'execution':
        _edge(out, me, 'executions.task_id', 'task', e.task_id)
        _edge(out, me, 'executions.mission_id', 'mission', e.mission_id)
        _edge(out, me, 'Execution.handoff_from', 'execution', e.handoff_from)
        _edge(out, me, 'Execution.session_id', 'session', e.session_id)
        _edge(out, me, 'Execution.route_decision_id', 'route_decision', e.route_decision_id)
        _edge(out, me, 'Execution.policy_decision_id', 'policy_decision', e.policy_decision_id)
    elif kind == 'verification':
        s = e.subject
        if s is not None and s.kind:
            _edge(out, me, 'Verification.subject', s.kind, s.id)
        _edge(out, me, 'verifications.plan_id', 'plan', e.plan_id)
        _edge(out, me, 'Verification.execution_id', 'execution', e.execution_id)
    elif kind == 'session':
        _edge(out, me, 'sessions.mission_id', 'mission', e.mission_id)
        _edge(out, me, 'sessions.handoff_from_session_id', 'session', e.handoff_from_session_id)
        _edge(out, me, 'sessions.project_id', 'project', e.project_id)
    elif kind == 'knowledge_item':
        _edge(out, me, 'KnowledgeItem.supersedes_id', 'knowledge_item', e.supersedes_id)
        _edge(out, me, 'KnowledgeItem.superseded_by_id', 'knowledge_item', e.superseded_by_id)
        _edge(out, me, 'KnowledgeItem.route_decision_id', 'route_decision', e.route_decision_id)
        _edge(out, me, 'knowledge_items.project_id', 'project', e.project_id, structural=True)
    elif kind == 'automation_run':
        _edge(out, me, 'automation_runs.automation_id', 'automation', e.automation_id)
        _edge(out, me, 'automation_runs.mission_id', 'mission', e.mission_id)
    elif kind == 'repository':
        _edge(out, me, 'repositories.project_id', 'project', e.project_id, structural=True)
    elif kind == 'review':
        _edge(out, me, 'reviews.plan_id', 'plan', e.plan_id, structural=True)
    return out


def relation_edge(r):
    """A `Relation` row as an edge: held by its source, tiered (G22)."""
    return {'from': {'kind': r.src_kind, 'id': r.src_id},
            'to': {'kind': r.dst_kind, 'id': r.dst_id}, 'field': 'relations.' + r.rel,
            'rel': r.rel, 'tier': r.confidence_tier or 'EXTRACTED',
            'inactive': bool(r.valid_until), 'structural': False}


def _holders(conn, kind, node_id):
    """(kind, row) of every row holding an edge towards (kind, node_id), found
    only along indexed columns (p18 §6); a holder's own edges are then read by
    `held_edges`, so a reverse edge is never a second definition."""
    out = []
    def add(k, found):
        out.extend((k, r) for r in found)
    if kind == 'project':
        add('mission', rows.where(conn, E.Mission, workspace_id=ids.GLOBAL_WORKSPACE,
                                  project_id=node_id))
        add('session', rows.where(conn, E.Session, project_id=node_id))
        add('repository', rows.where(conn, E.Repository, project_id=node_id))
        add('knowledge_item', rows.where(conn, E.KnowledgeItem, project_id=node_id))
    elif kind == 'mission':
        plans = rows.where(conn, E.Plan, mission_id=node_id)
        add('plan', plans)
        add('session', rows.where(conn, E.Session, mission_id=node_id))
        add('automation_run', rows.where(conn, E.AutomationRun, mission_id=node_id))
        for t in rows.where(conn, E.Task, mission_id=node_id):
            add('execution', rows.where(conn, E.Execution, task_id=t.entity.id))
        for p in plans:
            add('verification', [v for v in rows.where(conn, E.Verification,
                                                       plan_id=p.entity.id)
                                 if v.entity.subject and v.entity.subject.kind == 'mission'
                                 and v.entity.subject.id == node_id])
    elif kind == 'plan':
        add('task', rows.where(conn, E.Task, plan_id=node_id))
        add('verification', rows.where(conn, E.Verification, plan_id=node_id))
        add('review', rows.where(conn, E.Review, plan_id=node_id))
    elif kind == 'task':
        add('execution', rows.where(conn, E.Execution, task_id=node_id))
        me = rows.get(conn, E.Task, node_id)
        if me is not None:
            add('task', [t for t in rows.where(conn, E.Task, plan_id=me.entity.plan_id)
                         if me.entity.key in (t.entity.depends_on or ())])
    elif kind == 'execution':
        me = rows.get(conn, E.Execution, node_id)
        if me is not None:
            add('execution', [x for x in rows.where(conn, E.Execution, task_id=me.entity.task_id)
                              if x.entity.handoff_from == node_id])
            if me.entity.plan_id:
                add('verification', [v for v in rows.where(conn, E.Verification,
                                                           plan_id=me.entity.plan_id)
                                     if v.entity.execution_id == node_id])
    elif kind == 'session':
        add('session', rows.where(conn, E.Session, handoff_from_session_id=node_id))
    elif kind == 'automation':
        add('automation_run', rows.where(conn, E.AutomationRun, automation_id=node_id))
    elif kind == 'approval':
        # the one edge an approval has is its mission's "waiting on" (the list's)
        me = rows.get(conn, E.Approval, node_id)
        if me is not None and me.entity.mission_id:
            add('mission', [m for m in [rows.get(conn, E.Mission, me.entity.mission_id)] if m])
    return out


def _relations(conn, kind, node_id):
    return ([r.entity for r in rows.where(conn, E.Relation, src_kind=kind, src_id=node_id)]
            + [r.entity for r in rows.where(conn, E.Relation, dst_kind=kind, dst_id=node_id)])


# ── nodes ───────────────────────────────────────────────────────────────────

def _load(conn, kind, node_id):
    if kind not in KINDS:
        return None
    return rows.get(conn, KINDS[kind][0], node_id)


def node_of(kind, row):
    e = row.entity
    machine = KINDS[kind][1]
    n = {'kind': kind, 'id': e.id, 'label': clean_label(_label(kind, e)), 'parent': _parent(kind, e)}
    if machine is not None:
        n['machine'] = machine
        n['state'] = getattr(e, states_field(kind))
    if kind == 'knowledge_item':
        n['type'] = e.type                 # a DECISION is drawn as a diamond (A3, V7)
    if kind == 'route_decision':
        attrs = {a: getattr(e, a) for a in ROUTE_ATTRS}
        attrs['fallback_from'] = list(attrs['fallback_from'] or ())
        attrs['eliminated'] = sum(1 for c in (e.candidates or ())
                                  if isinstance(c, dict) and c.get('eliminated_at_step'))
        n['attrs'] = attrs
    return n


def states_field(kind):
    return KINDS[kind][0]._STATE[0]


def endpoint(ref, missing=False):
    return {'kind': ref['kind'], 'id': ref['id'], 'endpoint': True, 'missing': missing,
            'label': clean_label('%s %s' % (ref['kind'].replace('_', ' '), ref['id'][:12]))}


def _order_key(kind, row, hop):
    e = row.entity
    settled = getattr(e, states_field(kind), None) in TERMINAL[kind] if KINDS[kind][1] else False
    return (hop, RANK[kind], settled, _desc(row.updated_at), e.id)


def _desc(s):
    # descending ISO time as an ascending key
    return tuple(-ord(c) for c in (s or ''))


def _key(ref):
    return (ref['kind'], ref['id'])


# ── GET /v1/world/graph ─────────────────────────────────────────────────────

def world_graph(conn, focus=None, depth=None, limit=LIMIT_DEFAULT):
    """The focused neighbourhood (A4, A6). *focus* is (kind, id) or None for
    the workspace; the caller has validated the kind, depth and limit."""
    seq = outbox.head(conn)
    if focus is None:
        return _world_level(conn, seq, limit)
    kind, fid = focus
    root = _load(conn, kind, fid)
    if root is None:
        raise NotFound(fid)
    if depth is None:
        depth = 1 if kind == 'project' else 2
    loaded = {(kind, fid): (0, root)}     # key -> (hop, row), never more than *limit*
    cut = {}                              # found but over the cap: counted, not drawn
    edges = {}
    frontier = [(kind, fid)]
    for hop in range(1, depth + 1):
        found = {}
        for k, i in frontier:
            row = loaded[(k, i)][1]
            cand = held_edges(conn, k, row.entity)
            for hk, hrow in _holders(conn, k, i):
                mine = [x for x in held_edges(conn, hk, hrow.entity) if _key(x['to']) == (k, i)]
                if mine:                   # a row that holds no edge here is not a neighbour
                    cand += mine
                    found.setdefault((hk, hrow.entity.id), hrow)
            cand += [relation_edge(r) for r in _relations(conn, k, i)]
            for x in cand:
                ek = _edge_key(x)
                if ek not in edges or (edges[ek]['structural'] and not x['structural']):
                    edges[ek] = x            # the list's own edge wins over membership
                for end in (x['from'], x['to']):
                    k2 = _key(end)
                    if (k2 not in loaded and k2 not in cut and k2 not in found
                            and end['kind'] in KINDS):
                        r = _load(conn, end['kind'], end['id'])
                        if r is not None:
                            found[k2] = r
        ranked = sorted(((fk, r) for fk, r in found.items()
                         if fk not in loaded and fk not in cut),
                        key=lambda t: _order_key(t[0][0], t[1], hop))
        room = max(0, limit - len(loaded))
        frontier = []
        for fk, r in ranked[:room]:
            loaded[fk] = (hop, r)
            frontier.append(fk)
        for fk, r in ranked[room:]:
            cut[fk] = r
    # the last ring's own edges among what is already loaded: complete between
    # loaded nodes, and never a reason to load one more (depth holds)
    for k, i in frontier:
        for x in held_edges(conn, k, loaded[(k, i)][1].entity) + [
                relation_edge(r) for r in _relations(conn, k, i)]:
            if _key(x['from']) in loaded and _key(x['to']) in loaded:
                edges.setdefault(_edge_key(x), x)
    return _assemble(seq, {'kind': kind, 'id': fid}, depth, limit, loaded, cut, edges)


def _edge_key(x):
    a, b = _key(x['from']), _key(x['to'])
    return (x['field'],) + ((a, b) if a <= b else (b, a))


def _assemble(seq, focus, depth, limit, loaded, cut, edges):
    nodes = [node_of(k, r) for (k, _i), (_h, r) in sorted(
        loaded.items(), key=lambda t: _order_key(t[0][0], t[1][1], t[1][0]))]
    shown = set(loaded)
    out_edges, ends = [], {}
    for ek in sorted(edges):
        x = edges[ek]
        a, b = _key(x['from']), _key(x['to'])
        if a not in shown and b not in shown:
            continue
        for end, k in ((x['from'], a), (x['to'], b)):
            if k in shown:
                continue
            if k in cut:
                break                      # over the cap: counted in hidden, not drawn
            # a kind with no table (decision, person, message…) or a row that
            # does not exist: an endpoint, never an invented node (A2)
            ends.setdefault(k, endpoint(end, missing=end['kind'] in KINDS))
        else:
            out_edges.append(dict(x, id='%s|%s:%s|%s:%s' % (
                x['field'], x['from']['kind'], x['from']['id'], x['to']['kind'], x['to']['id'])))
    hidden = {}
    for (k, _i), r in cut.items():
        p = _parent(k, r.entity)
        pk = (p['kind'], p['id']) if p else ('workspace', ids.GLOBAL_WORKSPACE)
        hidden[(pk, k)] = hidden.get((pk, k), 0) + 1
    return {
        'focus': focus, 'depth': depth, 'limit': limit, 'as_of_seq': seq,
        'nodes': nodes + [ends[k] for k in sorted(ends)],
        'edges': out_edges[:EDGE_MAX],
        'truncated': bool(cut) or len(out_edges) > EDGE_MAX,
        'hidden': [{'parent': {'kind': pk[0], 'id': pk[1]}, 'kind': k, 'count': n}
                   for (pk, k), n in sorted(hidden.items())],
    }


def _world_level(conn, seq, limit):
    """World level (A4): every project collapsed, with counts — never a child row."""
    projects = rows.where(conn, E.Project, workspace_id=ids.GLOBAL_WORKSPACE)
    projects.sort(key=lambda r: (r.entity.state != 'ACTIVE', r.entity.name, r.entity.id))
    nodes = []
    for r in projects[:limit]:
        p = r.entity
        n = {'kind': 'project', 'id': p.id, 'label': clean_label(p.name), 'parent': None,
             'counts': _counts(conn, p.id)}
        nodes.append(n)
    cut = len(projects) - len(nodes)
    return {'focus': {'kind': 'workspace', 'id': ids.GLOBAL_WORKSPACE}, 'depth': 1,
            'limit': limit, 'as_of_seq': seq, 'nodes': nodes, 'edges': [],
            'truncated': cut > 0,
            'hidden': [{'parent': {'kind': 'workspace', 'id': ids.GLOBAL_WORKSPACE},
                        'kind': 'project', 'count': cut}] if cut else []}


def _counts(conn, project_id):
    def n(sql, *a):
        return conn.execute(sql, a).fetchone()[0]
    states_ = dict(conn.execute(
        'SELECT state, COUNT(*) FROM missions WHERE workspace_id = ? AND project_id = ? '
        'GROUP BY state ORDER BY state', (ids.GLOBAL_WORKSPACE, project_id)).fetchall())
    return {'missions': sum(states_.values()), 'mission_states': states_,
            'repositories': n('SELECT COUNT(*) FROM repositories WHERE project_id = ?',
                              project_id),
            'sessions': n('SELECT COUNT(*) FROM sessions WHERE project_id = ?', project_id),
            'knowledge_items': n('SELECT COUNT(*) FROM knowledge_items WHERE project_id = ?',
                                 project_id)}


# ── GET /v1/repositories/{id}/graph (A5) ────────────────────────────────────

@functools.lru_cache(maxsize=4)
def _payload(sha, read):
    return json.loads(read(sha))


def repository_graph(conn, repository_id, read, focus='', depth=1, limit=LIMIT_DEFAULT):
    """The stored import graph of the repository's latest completed inspection,
    focused on the directory (or file) *focus*: the tree *depth* levels below
    it, and the payload's file edges aggregated to the nodes returned. *read*
    is the artifact store's `get`; nothing walks a working tree."""
    repo = rows.get(conn, E.Repository, repository_id)
    if repo is None:
        raise NotFound(repository_id)
    r = repo.entity
    base = {'repository_id': r.id, 'focus': focus, 'depth': depth, 'limit': limit,
            'as_of_seq': outbox.head(conn)}
    ins = rows.get(conn, E.RepositoryInspection, r.last_inspection_id) \
        if r.last_inspection_id else None
    if ins is None or ins.entity.state != 'COMPLETED' or not ins.entity.payload_sha256:
        return dict(base, available=False, reason='not_inspected')
    i = ins.entity
    try:
        payload = _payload(i.payload_sha256, read)
    except (OSError, KeyError, ValueError, LookupError):
        if i.payload_sha256 not in _MISSING:
            _MISSING.add(i.payload_sha256)
            log.warning('repository %s: its stored inspection payload %s is missing',
                        r.id, i.payload_sha256)
        return dict(base, available=False, reason='payload_missing')
    return dict(base, available=True, **_tree(payload, focus, depth, limit),
                revision=i.revision, inspected_at=i.inspected_at,
                extractor_version=i.extractor_version,
                extractor_truncated=bool(payload.get('truncated')),
                stale=r.architecture_state == 'STALE' or r.last_revision != i.revision)


def _tree(payload, focus, depth, limit):
    files = payload.get('files') or []
    focus = focus.strip('/')
    fileset = set(files)
    prefix = focus + '/' if focus else ''
    if focus and focus not in fileset and not any(f.startswith(prefix) for f in files):
        raise NotFound(focus)
    if focus in fileset:
        under = [focus]
        base_parts = len(focus.split('/')) - 1
    else:
        under = [f for f in files if f.startswith(prefix)]
        base_parts = len(focus.split('/')) if focus else 0

    def visible(f):
        """The node a file shows as: itself, or its ancestor at *depth*."""
        parts = f.split('/')
        if len(parts) - base_parts <= depth:
            return f
        return '/'.join(parts[:base_parts + depth])

    ids_ = {}
    for f in under:
        v = visible(f)
        ids_.setdefault(v, {'files': 0})
        ids_[v]['files'] += 1
    # every directory between the focus and a visible node is a node too
    for v in list(ids_):
        parts = v.split('/')
        for n in range(base_parts + 1, len(parts)):
            ids_.setdefault('/'.join(parts[:n]), None)
    names = sorted(ids_, key=lambda p: (p in fileset, p))     # directories first, then path
    kept, cut = names[:limit], names[limit:]
    kept_set = set(kept)
    nodes = []
    for p in kept:
        parent = posixpath.dirname(p)
        node = {'kind': 'file' if p in fileset else 'directory', 'id': p,
                'label': clean_label(posixpath.basename(p) or p),
                'parent': {'kind': 'directory', 'id': parent} if parent and parent != focus
                and parent in kept_set else None}
        if p not in fileset:
            node['counts'] = {'files': sum(1 for f in under if f.startswith(p + '/'))}
        nodes.append(node)

    def lift(f):
        if f in kept_set:
            return f
        if f.startswith(prefix) or f == focus:
            v = visible(f)
            return v if v in kept_set else None
        return None

    agg, outside = {}, set()
    for a, b in payload.get('edges') or []:
        la, lb = lift(a), lift(b)
        if la is None and lb is None:
            continue
        if la is None:
            la = 'outside:' + a.split('/')[0]
            outside.add(la)
        if lb is None:
            lb = 'outside:' + b.split('/')[0]
            outside.add(lb)
        if la == lb:
            continue
        agg[(la, lb)] = agg.get((la, lb), 0) + 1
    for o in sorted(outside):
        nodes.append({'kind': 'directory', 'id': o, 'endpoint': True, 'missing': False,
                      'label': clean_label(o[len('outside:'):] + '/'), 'parent': None})
    edges = [{'id': '%s|%s' % k, 'from': {'kind': 'path', 'id': k[0]},
              'to': {'kind': 'path', 'id': k[1]}, 'field': 'payload.edges', 'count': n}
             for k, n in sorted(agg.items())]
    hidden = len(cut)
    return {'nodes': nodes, 'edges': edges[:EDGE_MAX],
            'truncated': bool(hidden) or len(edges) > EDGE_MAX,
            'hidden': [{'parent': {'kind': 'directory', 'id': focus}, 'kind': 'path',
                        'count': hidden}] if hidden else []}

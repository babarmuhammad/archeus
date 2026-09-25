"""World commands (P4, p4-design-gate §3.2): projects, repositories,
constraints, inspections, assessments and the digest cursor.

Each is `command(tx, **kwargs)` run by the writer, like every other command:
one transaction, the rows and the events recording them together. Discovery
of a project's repositories runs inside `create_project` so that an
idempotent replay is a replay: the key's hash covers what the client asked
for (name, roots), never what the filesystem said at the time.

Who may call what is the route scope's (admin for `create_project`, D7);
the inspection and assessment commands are the world worker's, acting as
Core's system principal.
"""

import json

from ...infra.db import rows
from ...infra.eventlog import outbox
from ..domain import entities, guards, ids
from ..domain.events import new_event
from ..domain.values import Ref
from ..world import drift, inspection
from . import lifecycle
from .queries import view

#: Failures that say nothing about the repository, so they do not count
#: against the retry cap: the walk raced a commit, or Core died under it.
UNCOUNTED = ('revision_moved_during', 'core_restarted')
MAX_ATTEMPTS = 3


class Conflict(ValueError):
    """The thing already exists under another owner (`409 conflict`)."""

    def __init__(self, why, detail=None):
        super().__init__(why)
        self.detail = detail or {}


def _project(conn, project_id):
    row = rows.get(conn, entities.Project, project_id)
    if row is None:
        raise lifecycle.NotFound(project_id)
    return row


def constraints(conn, project_id):
    """The project's CONFIRMED architecture constraints, as drift reads them:
    every ARCHITECTURE item (a prose one is reported as uncheckable) and every
    DECISION that carries a constraint."""
    out = []
    for r in rows.where(conn, entities.KnowledgeItem, project_id=project_id):
        k = r.entity
        if k.state != 'CONFIRMED':
            continue
        if k.type == 'ARCHITECTURE' or (k.type == 'DECISION' and k.constraint is not None):
            out.append({'id': k.id, 'version': r.version, 'statement': k.title,
                        'constraint': k.constraint})
    return out


def completed_inspection(conn, repository_id, revision):
    """The one COMPLETED inspection of *revision* by the current extractor."""
    hits = [r for r in rows.where(conn, entities.RepositoryInspection,
                                  repository_id=repository_id,
                                  extractor_version=inspection.EXTRACTOR_VERSION)
            if r.entity.state == 'COMPLETED' and r.entity.revision == revision]
    return hits[0] if hits else None


# ── projects and repositories ──────────────────────────────────────────────

def create_project(tx, *, actor, name, root_paths, workspace_id=ids.GLOBAL_WORKSPACE):
    found = inspection.discover(list(root_paths))
    taken = []
    for path, _kind in found:
        key = inspection.path_key(path)
        for r in tx.where(entities.Repository, workspace_id=workspace_id, path_key=key):
            taken.append({'path': path, 'repository_id': r.entity.id,
                          'project_id': r.entity.project_id})
    if taken:
        raise Conflict('repository already registered', {'repositories': taken})
    p = entities.Project(id=ids.new_id('project'), workspace_id=workspace_id, name=name,
                         root_paths=tuple(root_paths))
    prow = tx.insert(p, actor=actor)
    tx.append(new_event('project.created', Ref('project', p.id), actor,
                        payload={'name': name, 'repositories': len(found)},
                        workspace=workspace_id, project=p.id))
    repos_out = []
    for path, kind in found:
        r = entities.Repository(id=ids.new_id('repository'), workspace_id=workspace_id,
                                project_id=p.id, path=path, path_key=inspection.path_key(path),
                                kind=kind)
        repos_out.append(view(tx.insert(r, actor=actor)))
        tx.append(new_event('repository.registered', Ref('repository', r.id), actor,
                            payload={'path': path, 'kind': kind},
                            workspace=workspace_id, project=p.id))
    return {'project': view(prow), 'repositories': repos_out}


# ── constraints (the P4 slice of knowledge, D3) ───────────────────────────

def declare_constraint(tx, *, actor, project_id, statement, kind=None, spec=None):
    """A user-declared ARCHITECTURE item, auto-confirmed because its origin
    is explicit (state-machines §11). With no kind it is prose, which drift
    lists as uncheckable. An identical CONFIRMED one already there is returned
    unchanged: a duplicate would report every violation twice. Every
    repository of the project assessed against the old set goes STALE."""
    prow = _project(tx.conn, project_id)
    if kind is None and spec is not None:
        raise ValueError('a spec needs a kind')
    constraint = None if kind is None else {'kind': kind, 'spec': spec}
    if constraint is not None:
        entities.check_constraint(constraint)
    canon = json.dumps(constraint, sort_keys=True)
    for r in tx.where(entities.KnowledgeItem, project_id=project_id):
        k = r.entity
        same = json.dumps(k.constraint, sort_keys=True) == canon
        if (k.state == 'CONFIRMED' and k.type == 'ARCHITECTURE' and same
                and (constraint is not None or k.title == statement)):
            return {'knowledge_item': view(r), 'changed': False, 'stale': []}
    k = entities.KnowledgeItem(id=ids.new_id('knowledge_item'),
                               workspace_id=prow.entity.workspace_id, type='ARCHITECTURE',
                               title=statement, origin='explicit', project_id=project_id,
                               constraint=constraint)
    tx.insert(k, actor=actor)
    tx.append(new_event('knowledge_item.created', Ref('knowledge_item', k.id), actor,
                        payload={'type': k.type, 'title': statement,
                                 'kind': kind},
                        workspace=k.workspace_id, project=project_id))
    krow, _e = lifecycle.fire(tx, entities.KnowledgeItem, k.id, 'confirm', actor=actor,
                              reason='declared by the user (origin explicit)')
    stale = []
    for r in tx.where(entities.Repository, project_id=project_id):
        if r.entity.architecture_state in ('CONSISTENT', 'DRIFTED'):
            lifecycle.fire(tx, entities.Repository, r.entity.id, 'constraints_changed',
                           actor=actor, reason='constraint %s declared' % k.id)
            stale.append(r.entity.id)
    return {'knowledge_item': view(krow), 'changed': True, 'stale': stale}


# ── inspections (the world worker's) ───────────────────────────────────────

def begin_inspection(tx, *, actor, repository_id, revision, retry_of=None):
    """A new inspection of *revision*, or FAILED -> SCHEDULED for *retry_of*,
    then RUNNING. A repository assessed at another revision goes STALE here:
    that is when Core notices HEAD moved."""
    repo = lifecycle.load(tx, entities.Repository, repository_id)
    if revision is not None and completed_inspection(tx.conn, repository_id, revision):
        raise Conflict('revision already inspected', {'revision': revision})
    if retry_of is None:
        i = entities.RepositoryInspection(id=ids.new_id('repository_inspection'),
                                          repository_id=repository_id, revision=revision,
                                          extractor_version=inspection.EXTRACTOR_VERSION)
        tx.insert(i, actor=actor)
        iid = i.id
    else:
        old = lifecycle.load(tx, entities.RepositoryInspection, retry_of)
        if (old.entity.repository_id, old.entity.revision) != (repository_id, revision):
            raise ValueError('a retry is of the same repository and revision')
        lifecycle.fire(tx, entities.RepositoryInspection, retry_of, 'retry', actor=actor,
                       reason='retry after %s' % old.entity.failure)
        iid = retry_of
    row, _e = lifecycle.fire(tx, entities.RepositoryInspection, iid, 'start', actor=actor,
                             reason='inspecting %s' % (revision or 'an unreadable repository'))
    moved = (revision is not None and repo.entity.architecture_state in ('CONSISTENT', 'DRIFTED')
             and revision != repo.entity.last_revision)
    if moved:
        lifecycle.fire(tx, entities.Repository, repository_id, 'revision_moved', actor=actor,
                       reason='HEAD is %s, assessed at %s' % (revision, repo.entity.last_revision))
    return {'inspection_id': iid, 'state': row.entity.state, 'stale': moved}


def complete_inspection(tx, *, actor, inspection_id, observation, payload_sha256, payload_size,
                        diff_from_previous=None):
    """RUNNING -> COMPLETED with what the pass observed. A second completion
    of the same inspection is a no-op returning the first; completing a
    revision another inspection already completed is refused, so there is one
    COMPLETED observation per (repository, revision, extractor)."""
    row = lifecycle.load(tx, entities.RepositoryInspection, inspection_id)
    if row.entity.state == 'COMPLETED':
        return {'inspection': view(row), 'changed': False}
    other = completed_inspection(tx.conn, row.entity.repository_id, row.entity.revision)
    if other is not None:
        raise Conflict('revision already inspected', {'inspection_id': other.entity.id})
    if tx.get(entities.Artifact, payload_sha256) is None:
        tx.insert(entities.Artifact(id=payload_sha256, media_type='application/json',
                                    size=payload_size), actor=actor)
    fields = dict(observation, payload_sha256=payload_sha256, inspected_at=tx.now,
                  diff_from_previous=diff_from_previous, failure=None)
    row, _e = lifecycle.fire(tx, entities.RepositoryInspection, inspection_id, 'inspected',
                             actor=actor, reason='inspected %s' % row.entity.revision,
                             fields=fields)
    return {'inspection': view(row), 'changed': True}


def fail_inspection(tx, *, actor, inspection_id, failure):
    """RUNNING -> FAILED. `failure` is the reason recorded; unless it is one
    of UNCOUNTED it counts toward MAX_ATTEMPTS for that revision."""
    row = lifecycle.load(tx, entities.RepositoryInspection, inspection_id)
    reason = failure.split(':', 1)[0]
    attempts = row.entity.attempts + (0 if reason in UNCOUNTED else 1)
    row, _e = lifecycle.fire(tx, entities.RepositoryInspection, inspection_id, 'error',
                             actor=actor, reason=failure,
                             fields={'failure': failure, 'failed_at': tx.now,
                                     'attempts': attempts})
    return {'inspection': view(row)}


def record_assessment(tx, *, actor, repository_id, inspection_id, findings, evaluated_against):
    """The repository's architecture assessment: *findings* evaluated on
    *inspection_id* against the constraint set named *evaluated_against*. If
    the project's constraints changed after the evaluation, this is refused
    (VersionConflict, a lost race the worker re-evaluates) — an assessment is
    never recorded against a set it did not see. The edge is chosen from the
    findings and its guard re-checks them against the inspection."""
    repo = lifecycle.load(tx, entities.Repository, repository_id)
    current = constraints(tx.conn, repo.entity.project_id)
    now = drift.token(current)
    if now != evaluated_against:
        raise lifecycle.VersionConflict(repo.entity.project_id, evaluated_against, now)
    ins = lifecycle.load(tx, entities.RepositoryInspection, inspection_id)
    bad = drift.violated(findings)
    state = repo.entity.architecture_state
    if state in ('CONSISTENT', 'DRIFTED'):
        if (repo.entity.last_inspection_id, repo.entity.evaluated_against) == (inspection_id, now):
            return {'repository': view(repo), 'changed': False}
        if repo.entity.last_revision == ins.entity.revision:
            raise lifecycle.IllegalTrigger('architecture', state, 'reinspected_drift' if bad
                                           else 'reinspected_no_drift',
                                           'a current assessment is only replaced after STALE')
        # HEAD went back to a revision inspected before: no new walk, but the
        # assessment is of another revision, so it goes stale first
        lifecycle.fire(tx, entities.Repository, repository_id, 'revision_moved', actor=actor,
                       reason='HEAD is %s, assessed at %s' % (ins.entity.revision,
                                                              repo.entity.last_revision))
        state = 'STALE'
    trigger = {('UNKNOWN', False): 'first_inspection', ('UNKNOWN', True): 'first_inspection_drift',
               ('STALE', False): 'reinspected_no_drift', ('STALE', True): 'reinspected_drift'}[
        (state, bad)]
    facts = guards.ArchitectureFacts.of(ins.entity, bad)
    row, _e = lifecycle.fire(
        tx, entities.Repository, repository_id, trigger, actor=actor, facts=facts,
        reason='%d violated, %d unchecked at %s' % (
            sum(f['status'] == 'violated' for f in findings),
            sum(f['status'] == 'unchecked' for f in findings), ins.entity.revision),
        fields={'last_inspection_id': inspection_id, 'last_revision': ins.entity.revision,
                'findings': tuple(findings), 'evaluated_against': now,
                'evaluated_constraints': tuple((c['id'], c['version']) for c in current)})
    return {'repository': view(row), 'changed': True}


def sweep_inspections(tx, *, actor):
    """Boot: an inspection RUNNING now was running under a Core that died."""
    out = []
    for r in tx.where(entities.RepositoryInspection):
        if r.entity.state != 'RUNNING':
            continue
        fail_inspection(tx, actor=actor, inspection_id=r.entity.id, failure='core_restarted')
        out.append(r.entity.id)
    return {'failed': out}


# ── the digest cursor ───────────────────────────────────────────────────────

def owner(conn):
    """The one user of this Core (V1 is single-user), or None before the
    first acknowledgement writes the row."""
    got = rows.where(conn, entities.User)
    return got[0] if got else None


def ack_digest(tx, *, actor, up_to_seq):
    """Advance the owner's cursor to *up_to_seq*: never backwards (a stale
    device cannot un-see anything) and never past the head."""
    if isinstance(up_to_seq, bool) or not isinstance(up_to_seq, int) or up_to_seq < 0:
        raise ValueError('up_to_seq is an integer >= 0')
    head = outbox.head(tx.conn)
    if up_to_seq > head:
        raise ValueError('up_to_seq %d is ahead of the head (%d)' % (up_to_seq, head))
    row = owner(tx.conn)
    if row is None:
        u = entities.User(id=ids.new_id('user'), display_name='owner',
                          last_ack_event_seq=up_to_seq)
        row = tx.insert(u, actor=actor)
    elif up_to_seq <= row.entity.last_ack_event_seq:
        return {'up_to_seq': row.entity.last_ack_event_seq, 'changed': False}
    else:
        row = tx.update(entities.User, row.entity.id, {'last_ack_event_seq': up_to_seq},
                        actor=actor)
    tx.append(new_event('user.digest_acked', Ref('user', row.entity.id), actor,
                        payload={'up_to_seq': up_to_seq}))
    return {'up_to_seq': row.entity.last_ack_event_seq, 'changed': True}

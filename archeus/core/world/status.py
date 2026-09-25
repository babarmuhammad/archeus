"""`status()` — the deterministic cross-project status (S13, p4-design-gate §8).

One read snapshot, and nothing in the answer that the rows do not say: no
brain, no ranking beyond settled-last. A STALE repository's findings are its
last assessment, labelled `stale`, so "no drift" is never claimed for a
revision nobody has evaluated.
"""

from ...infra.db import rows
from ...infra.db.writer import NotFound
from ...infra.eventlog import outbox
from ..application.queries import view
from ..domain import entities, states

_SETTLED = states.terminal('mission')


def _last_inspection(conn, repository_id):
    got = rows.where(conn, entities.RepositoryInspection, repository_id=repository_id)
    if not got:
        return None
    i = got[-1].entity
    return {'id': i.id, 'state': i.state, 'revision': i.revision, 'inspected_at': i.inspected_at,
            'complete': i.complete, 'dirty': i.dirty, 'failure': i.failure,
            'attempts': i.attempts}


def status(conn, project_id=None):
    projects = rows.where(conn, entities.Project)
    known = {p.entity.id for p in projects}
    if project_id is not None:
        if project_id not in known:
            raise NotFound(project_id)
        projects = [p for p in projects if p.entity.id == project_id]
    missions = [view(r) for r in rows.where(conn, entities.Mission)]
    mine = missions if project_id is None else [m for m in missions
                                                 if m['project_id'] == project_id]
    unsettled = [m for m in mine if m['state'] not in _SETTLED]
    settled = sorted((m for m in mine if m['state'] in _SETTLED),
                     key=lambda m: m['updated_at'], reverse=True)
    unsettled.sort(key=lambda m: m['updated_at'], reverse=True)
    out_projects, drift, unchecked = [], [], []
    for p in projects:
        repos = []
        for r in rows.where(conn, entities.Repository, project_id=p.entity.id):
            repo = r.entity
            last = _last_inspection(conn, repo.id)
            assessed = None
            if repo.last_inspection_id is not None:
                a = rows.get(conn, entities.RepositoryInspection, repo.last_inspection_id).entity
                assessed = {'provisional': bool(a.dirty), 'complete': a.complete}
            repos.append({'id': repo.id, 'path': repo.path, 'kind': repo.kind,
                          'architecture_state': repo.architecture_state,
                          'last_revision': repo.last_revision, 'last_inspection': last})
            for f in repo.findings:
                row = dict(f, repository_id=repo.id, project_id=p.entity.id,
                           revision=repo.last_revision,
                           stale=repo.architecture_state == 'STALE',
                           provisional=bool(assessed and assessed['provisional']))
                if f['status'] == 'violated':
                    drift.append(row)
                elif f['status'] == 'unchecked':
                    unchecked.append(row)
        counts = {}
        for m in missions:
            if m['project_id'] == p.entity.id:
                counts[m['state']] = counts.get(m['state'], 0) + 1
        out_projects.append({'id': p.entity.id, 'name': p.entity.name, 'state': p.entity.state,
                             'repositories': repos, 'missions': counts})
    return {'source': 'deterministic', 'as_of_seq': outbox.head(conn),
            'projects': out_projects, 'missions': unsettled + settled,
            'drift': drift, 'unchecked': unchecked,
            'unknown_project': [] if project_id is not None else sorted(
                m['id'] for m in missions
                if m['project_id'] is not None and m['project_id'] not in known)}


def project(conn, project_id):
    """One project with its repositories (their assessment included)."""
    row = rows.get(conn, entities.Project, project_id)
    if row is None:
        raise NotFound(project_id)
    return dict(view(row), repositories=[
        view(r) for r in rows.where(conn, entities.Repository, project_id=project_id)])


def projects(conn):
    return [project(conn, r.entity.id) for r in rows.where(conn, entities.Project)]


def inspections(conn, repository_id, limit=50):
    """A repository's inspections, newest first (rows, never payloads)."""
    if rows.get(conn, entities.Repository, repository_id) is None:
        raise NotFound(repository_id)
    got = rows.where(conn, entities.RepositoryInspection, repository_id=repository_id)
    return [view(r) for r in reversed(got)][:limit]

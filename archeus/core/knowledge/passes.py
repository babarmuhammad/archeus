"""The three learning passes (P6; plan P6, context-and-knowledge §3, §6.4, §8;
p6-design-gate §7). Each: gather its source, record the ContextPackage it is
given, build a prompt (stable prefix + variable suffix), make one own call
through `archeus_call`, let Core validate the answer, and record what it
produced as CANDIDATEs in the same command that ends the call.

| pass | trigger | schema | produces |
|---|---|---|---|
| knowledge | a project's first COMPLETED inspection | `knowledge.v1` | ENTITY candidates, INFERRED relations, `contradicts` |
| decisions | a meeting imported | `decisions.v1` | DECISION candidates, `decided_in` |
| lessons | a mission COMPLETED or FAILED | `lessons.v1` | LESSON candidates, `learned_from`, corroboration |

A pass never fails its subject: a project whose knowledge pass failed or was
gated by ADR-0021 stays exactly as usable as its deterministic assessment made
it (plan P6) — the outcome is on the pass's RouteDecision, and nothing else.
"""

import json
import os

from ...infra import paths
from ...infra.artifacts import store as artifacts
from ...infra.db import rows
from ..application import calls as C
from ..application import commands
from ..application import knowledge as K
from ..domain import entities

#: What the passes accept from a model: sizes bound what one answer can add.
_TEXT = {'type': 'string', 'maxLength': 1500}
_NAME = {'type': 'string', 'maxLength': 200}
KNOWLEDGE_SCHEMA = {'type': 'object', 'properties': {
    'summary': {'type': 'string', 'maxLength': 2000, 'nullable': True},
    'entities': {'type': 'array', 'maxItems': 100, 'items': {'type': 'object', 'properties': {
        'name': _NAME,
        'kind': {'type': 'string', 'enum': ['module', 'component', 'service', 'model',
                                            'concept']},
        'module': {'type': 'string', 'maxLength': 400, 'nullable': True},
        'summary': _TEXT}, 'required': ['name', 'kind', 'summary']}},
    'relations': {'type': 'array', 'maxItems': 200, 'items': {'type': 'object', 'properties': {
        'from': _NAME, 'rel': {'type': 'string', 'enum': ['depends_on', 'uses', 'contains',
                                                          'calls', 'implements']},
        'to': _NAME}, 'required': ['from', 'rel', 'to']}},
    'contradicts': {'type': 'array', 'maxItems': 50, 'items': {'type': 'object', 'properties': {
        'entity': _NAME, 'existing': {'type': 'string', 'maxLength': 40}, 'why': _TEXT},
        'required': ['entity', 'existing', 'why']}}},
    'required': ['entities']}
DECISIONS_SCHEMA = {'type': 'object', 'properties': {
    'decisions': {'type': 'array', 'maxItems': 50, 'items': {'type': 'object', 'properties': {
        'statement': {'type': 'string', 'maxLength': 500},
        'rationale': {'type': 'string', 'maxLength': 1500, 'nullable': True}},
        'required': ['statement']}}},
    'required': ['decisions']}
LESSONS_SCHEMA = {'type': 'object', 'properties': {
    'lessons': {'type': 'array', 'maxItems': 20, 'items': {'type': 'object', 'properties': {
        'title': _NAME, 'text': _TEXT,
        'outcome': {'type': 'string', 'enum': ['worked', 'failed']}},
        'required': ['title', 'text', 'outcome']}}},
    'required': ['lessons']}

#: How many module directories and context lines a prompt names.
PROMPT_MODULES = 80

KNOWLEDGE_PREFIX = (
    "You are building the knowledge base of a software project for Archeus. Read the "
    "repository in the working directory; you may only read. Describe its main modules and "
    "components: one entry each, with the module path when there is one and a one-to-three "
    "sentence summary of what it is for, and the dependencies between them. Describe only "
    "what the code shows. If an item under 'Existing knowledge' is contradicted by the code, "
    "list it under `contradicts` with its id and why.\n")
DECISIONS_PREFIX = (
    "Read these meeting notes and list the decisions they record: what was decided, and "
    "why when the notes say so. A discussion, an idea or an open question is not a decision. "
    "Do not invent decisions the notes do not state.\n")
LESSONS_PREFIX = (
    "A piece of work has ended. From what is recorded about it below, state the reusable "
    "lessons: what worked or failed and why, phrased so they apply to future work in this "
    "project. Do not restate the objective. Return none if there is nothing reusable.\n")


def _blank(v):
    return not (isinstance(v, str) and v.strip())


def _check_text(items, fields):
    problems = []
    for i, it in enumerate(items):
        for f in fields:
            if f in it and it[f] is not None and len(str(it[f]).encode('utf-8')) > \
                    entities.BODY_MAX_BYTES:
                problems.append('item %d: %s is over %d bytes' % (i, f, entities.BODY_MAX_BYTES))
    return problems


def check_knowledge(parsed):
    ents = parsed['entities']
    problems = ['entities[%d].name is blank' % i for i, e in enumerate(ents)
                if _blank(e['name'])]
    seen = set()
    for e in ents:
        k = K.key(e['name']) if not _blank(e['name']) else None
        if k in seen:
            problems.append('entity %r is listed twice' % e['name'])
        seen.add(k)
    return problems + _check_text(ents, ('summary',))


def check_decisions(parsed):
    return ['decisions[%d].statement is blank' % i for i, d in enumerate(parsed['decisions'])
            if _blank(d['statement'])] + _check_text(parsed['decisions'], ('rationale',))


def check_lessons(parsed):
    return ['lessons[%d].title is blank' % i for i, x in enumerate(parsed['lessons'])
            if _blank(x['title'])] + _check_text(parsed['lessons'], ('text',))


def _context_lines(pkg):
    lines = ['Context selected for this call (context package %s):' % pkg['id']]
    for i in pkg['items'][:PROMPT_MODULES]:
        lines.append('- %s %s %s %s: %s' % (i['level'], i['store'], i['type'], i['ref']['id'],
                                            i['reason']))
    return '\n'.join(lines)


class Passes:
    """The three passes over one Core's database and `OwnCalls`."""

    def __init__(self, db, *, actor, calls):
        self.db, self.actor, self.calls = db, actor, calls

    def _do(self, command, **kw):
        return self.db.writer.execute(command, dict(kw, actor=self.actor))

    def _read(self, fn):
        with self.db.read() as conn:
            return fn(conn)

    def _record(self, c, command, **kw):
        """Record a valid answer and end its call in one command. If that command
        fails, nothing it wrote survives (one transaction), and the call ends
        `failed` on its own, so a pass never takes its worker down with it."""
        try:
            self._do(command, **kw)
            return 'ok'
        except Exception as e:
            self._do(C.end_call, route_decision_id=c.route_decision_id,
                     outcome={'state': 'failed', 'reason': 'could not record the result: '
                              '%s: %s' % (type(e).__name__, e), 'attempts': c.attempts,
                              'account_ref': c.account_ref}, usage=c.usage or None)
            return 'failed'

    def _called(self, c, package_id):
        return {'route_decision_id': c.route_decision_id, 'attempts': c.attempts,
                'account_ref': c.account_ref, 'usage': c.usage,
                'context_package_id': package_id}

    # ── the knowledge pass (legacy memory building, as V1 knowledge) ──

    def knowledge(self, inspection_id):
        i = self._read(lambda c: rows.get(c, entities.RepositoryInspection, inspection_id)).entity
        repo = self._read(lambda c: rows.get(c, entities.Repository, i.repository_id)).entity
        project = self._read(lambda c: rows.get(c, entities.Project, repo.project_id)).entity
        pkg = self._do(commands.record_context_package, subject_kind='project',
                       subject_id=project.id, query='architecture modules components')
        payload = json.loads(artifacts.get(i.payload_sha256)) if i.payload_sha256 else {}
        dirs = sorted({os.path.dirname(f).replace('\\', '/') or '.'
                       for f in payload.get('files', ())})[:PROMPT_MODULES]
        known = [it['ref']['id'] for it in pkg['items'] if it['ref']['kind'] == 'knowledge_item']
        suffix = '\n'.join([
            'Repository: %s at %s' % (repo.path, i.revision),
            'Languages: %s' % ', '.join(lang for lang, _n in i.languages),
            'Frameworks: %s' % ', '.join(i.frameworks),
            'Module directories: %s' % ', '.join(dirs),
            'Existing knowledge: %s' % (', '.join(known) or 'none'),
            _context_lines(pkg)])
        c = self.calls.run(purpose='knowledge_extraction',
                           source={'kind': 'repository_inspection', 'id': i.id},
                           workspace_id=project.workspace_id, project_id=project.id,
                           prompt=KNOWLEDGE_PREFIX + suffix, schema=KNOWLEDGE_SCHEMA,
                           check=check_knowledge, workdir=repo.path,
                           context_package_id=pkg['id'])
        if c.state != 'ok':
            return c.state
        return self._record(c, K.record_knowledge_pass, called=self._called(c, pkg['id']),
                            project_id=project.id, workspace_id=project.workspace_id,
                            inspection_id=i.id, result=c.parsed, known_items=tuple(known))

    # ── decisions from meeting notes ──

    def decisions(self, meeting_id):
        m = self._read(lambda c: rows.get(c, entities.Meeting, meeting_id)).entity
        pkg_id = None
        if m.project_id is not None:
            pkg_id = self._do(commands.record_context_package, subject_kind='project',
                              subject_id=m.project_id, query=m.name)['id']
        notes = artifacts.get(m.notes_artifact_id).decode('utf-8', 'replace')
        c = self.calls.run(purpose='knowledge_extraction',
                           source={'kind': 'meeting', 'id': m.id},
                           workspace_id=m.workspace_id, project_id=m.project_id,
                           prompt=DECISIONS_PREFIX + 'Meeting: %s, %s\n\n%s' % (
                               m.name, 'held %s' % m.held_at if m.held_at else 'undated',
                               notes),
                           schema=DECISIONS_SCHEMA, check=check_decisions,
                           workdir=paths.archeus_home(),
                           context_package_id=pkg_id)
        if c.state != 'ok':
            return c.state
        return self._record(c, K.record_decisions, called=self._called(c, pkg_id),
                            meeting_id=m.id, result=c.parsed)

    # ── lessons from a mission that ended ──

    def lessons(self, mission_id):
        def facts(conn):
            m = rows.get(conn, entities.Mission, mission_id).entity
            plans = [r.entity for r in rows.where(conn, entities.Plan, mission_id=mission_id)]
            execs = [r.entity for r in rows.where(conn, entities.Execution, mission_id=mission_id)]
            verif = [r.entity for r in rows.where(conn, entities.Verification)
                     if getattr(r.entity, 'subject', None) is not None
                     and r.entity.subject.id == mission_id]
            reviews = [r.entity for r in rows.where(conn, entities.Review, mission_id=mission_id)]
            return m, plans, execs, verif, reviews
        m, plans, execs, verif, reviews = self._read(facts)
        lines = ['Mission: %s' % m.title, 'Objective: %s' % m.objective,
                 'Ended as: %s' % m.state]
        lines += ['Plan v%d: %s' % (p.plan_version, p.summary) for p in plans]
        lines += ['Attempt %d: %s' % (e.attempt, e.exit_reason or e.state) for e in execs]
        lines += ['Verification: %s' % v.state for v in verif]
        lines += ['Review: %s' % r.state for r in reviews]
        c = self.calls.run(purpose='lesson', source={'kind': 'mission', 'id': m.id},
                           workspace_id=m.workspace_id, project_id=m.project_id,
                           prompt=LESSONS_PREFIX + '\n'.join(lines), schema=LESSONS_SCHEMA,
                           check=check_lessons, workdir=paths.archeus_home(),
                           context_package_id=m.context_package_id)
        if c.state != 'ok':
            return c.state
        return self._record(c, K.record_lessons, called=self._called(c, m.context_package_id),
                            mission_id=m.id, result=c.parsed)

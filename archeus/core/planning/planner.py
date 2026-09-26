"""`plan.v1`: the planner's proposal for one mission (plan §12, ADR-0006; P8).

The model reads the mission (its objective, desired outcome, requirements and
constraints, each labelled explicit or inferred) against the mission's context
package and proposes tasks. It names objects ONLY by the handles this module
gives: `p` project, `n` repository inspection, `y` repository, `k` knowledge
item, `g` meeting, and `r`/`c` for the mission's own requirements and
constraints. An unknown handle, or one of the wrong kind where it is used, is
invalid output (retried once by `archeus_call`, then the call ends `invalid`).

The model proposes; Core decides. `check` runs Core's validator
(`planning.validate`) as part of the call's own validation, so a plan that
breaks the structural contract never leaves the call; `resolve` turns the
labels into task keys and the handles into `{kind, id}`; everything derived —
key order, serialisation, cost band, digest, readiness — is Core's, in
`validate` and `Work.propose_plan`. Confidence is recorded nowhere as a reason.

Nothing here writes, spawns, routes, authorises, executes or verifies.
"""

from ...infra.db import rows
from ...infra.eventlog import outbox
from ..context.assemble import CHALLENGEABLE
from ..domain import entities
from ..domain.actions import ACTION_CLASSES
from . import validate

#: handle letter per package item kind (the mission itself gets none)
LETTERS = {'project': 'p', 'repository_inspection': 'n', 'repository': 'y',
           'knowledge_item': 'k', 'meeting': 'g'}
WORLD = tuple(LETTERS)
MISSING_KINDS = ('project', 'repository', 'file', 'service', 'person', 'organization',
                 'information', 'other')
#: mission fields a planning round is judged against; a `mission.updated`
#: naming one of them makes a package stale (P8 §11.3)
INPUT_FIELDS = ('requirements', 'constraints', 'objective', 'desired_outcome', 'title')

_S = {'type': 'string', 'maxLength': 500}
_H = {'type': 'string', 'maxLength': 12}
_HN = dict(_H, nullable=True)
_LIST = {'type': 'array', 'maxItems': 20, 'items': _S}
_CHECK = {'type': 'object', 'properties': {
    'text': _S, 'check': {'type': 'string', 'enum': list(entities.CRITERION_CHECKS)}},
    'required': ['text', 'check']}
_TASK = {'type': 'object', 'properties': {
    'id': _H, 'title': {'type': 'string', 'maxLength': 200},
    'kind': {'type': 'string', 'enum': list(entities.TASK_KINDS)},
    'objective': {'type': 'string', 'maxLength': 2000}, 'expected_output': _S,
    'boundaries': {'type': 'array', 'maxItems': 10, 'items': _S},
    'depends_on': {'type': 'array', 'maxItems': validate.MAX_TASKS, 'items': _H},
    'action_classes': {'type': 'array', 'maxItems': 13,
                       'items': {'type': 'string', 'enum': list(ACTION_CLASSES)}},
    'capabilities_required': {'type': 'array', 'maxItems': 5, 'items': {
        'type': 'string', 'enum': list(entities.CAPABILITIES)}},
    'touches': {'type': 'array', 'maxItems': 20, 'items': {'type': 'string', 'maxLength': 200}},
    'refs': {'type': 'array', 'maxItems': 10, 'items': _H},
    'serves': {'type': 'array', 'maxItems': 20, 'items': _H},
    'inputs': {'type': 'array', 'maxItems': 10, 'items': {'type': 'object', 'properties': {
        'from_task': _HN, 'ref': _HN, 'what': _S}, 'required': ['what']}},
    'acceptance': {'type': 'array', 'maxItems': 10, 'items': _CHECK},
    'estimate': {'type': 'integer'},
    'min_model_tier': {'type': 'string', 'enum': list(entities.MODEL_TIERS), 'nullable': True},
    'workspace_mode': {'type': 'string', 'enum': list(entities.WORKSPACE_MODES),
                       'nullable': True}},
    'required': ['id', 'title', 'kind', 'objective', 'expected_output']}
SCHEMA = {'type': 'object', 'properties': {
    'summary': _S,
    'tasks': {'type': 'array', 'maxItems': validate.MAX_TASKS, 'items': _TASK},
    'assumptions': {'type': 'array', 'maxItems': 20, 'items': {
        'type': 'object', 'properties': {'text': _S, 'about': _HN}, 'required': ['text']}},
    'questions': {'type': 'array', 'maxItems': 10, 'items': {'type': 'object', 'properties': {
        'question': {'type': 'string', 'maxLength': 300}, 'blocking': {'type': 'boolean'},
        'about': _HN}, 'required': ['question', 'blocking']}},
    'missing': {'type': 'array', 'maxItems': 10, 'items': {'type': 'object', 'properties': {
        'name': {'type': 'string', 'maxLength': 200},
        'kind': {'type': 'string', 'enum': list(MISSING_KINDS)},
        'required': {'type': 'boolean'}}, 'required': ['name', 'kind', 'required']}},
    'conflicts': {'type': 'array', 'maxItems': 10, 'items': {'type': 'object', 'properties': {
        'ref': _H, 'why': _S}, 'required': ['ref', 'why']}},
    'success_criteria': {'type': 'array', 'maxItems': 10, 'items': _CHECK},
    'risks': _LIST, 'rollback': dict(_S, nullable=True),
    'refs': {'type': 'array', 'maxItems': 20, 'items': _H},
    'confidence': {'type': 'number', 'nullable': True}},
    'required': ['summary', 'tasks']}

PREFIX = (
    "You are the planner of Archeus, a system that carries out work for its user. Propose a "
    "plan for the mission below: tasks another agent will carry out, one at a time or in "
    "parallel. You do not do the work, choose who does it, approve it or judge it done.\n"
    "Each task has an id (your own short label), a title, a kind, an objective, the output it "
    "must produce, its boundaries, the action classes it needs (read, web, write_repo, exec, "
    "git_commit, …), depends_on (the ids of tasks that must finish first), touches (the path "
    "globs it will change, relative to the repository), and at least one acceptance "
    "criterion (automatic when a check can decide it, human when only a person can); a human "
    "task's criteria are all human. Give each task an estimate from 1 (trivial) to 5 (large) "
    "and the model tier it needs (small, mid, large). Do not state a cost band.\n"
    "Refer to things ONLY by the handles in brackets below; never invent one. Every "
    "requirement marked explicit must be served by at least one task (list its handle in "
    "serves) unless you ask a blocking question about it. Do not add requirements: anything "
    "you assume goes in assumptions. When the plan cannot be made without the user — a "
    "requirement is ambiguous, information is missing, something the work needs is not "
    "among the handles — ask a question with blocking true, or list the thing in missing "
    "with required true; never invent it. List under conflicts the handles of items the plan "
    "would go against, and say why.\n")


def handles(pkg):
    """[(handle, ref)] for the package's world items, in its order."""
    counts, out = {}, []
    for it in pkg['items']:
        ref = it['ref']
        letter = LETTERS.get(ref['kind'])
        if letter is None or ref['id'] == pkg['subject_id']:
            continue
        counts[letter] = counts.get(letter, 0) + 1
        out.append(('%s%d' % (letter, counts[letter]), {'kind': ref['kind'], 'id': ref['id']}))
    return out


def describe(conn, pkg, mission):
    """(prompt lines, {handle: facts}): the mission's requirements and
    constraints (`r`, `c`) and the package's world items, read from the rows."""
    lines, facts = [], {}
    for letter, field in (('r', 'requirements'), ('c', 'constraints')):
        for i, item in enumerate(getattr(mission, field), 1):
            h = '%s%d' % (letter, i)
            facts[h] = {'kind': field[:-1], 'origin': item['origin'], 'text': item['text']}
            lines.append('[%s] %s, %s: %s' % (h, field[:-1], item['origin'], item['text']))
    for h, ref in handles(pkg):
        kind, f = ref['kind'], dict(ref)
        if kind == 'knowledge_item':
            k = rows.get(conn, entities.KnowledgeItem, ref['id']).entity
            f.update(state=k.state, ktype=k.type)
            label, text = '%s %s' % (k.type, k.state), '%s. %s' % (k.title, k.text or '')
        elif kind == 'project':
            p = rows.get(conn, entities.Project, ref['id']).entity
            label, text = 'project', '%s (%s)' % (p.name, ', '.join(p.root_paths))
        elif kind == 'repository_inspection':
            i = rows.get(conn, entities.RepositoryInspection, ref['id']).entity
            r = rows.get(conn, entities.Repository, i.repository_id).entity
            label = 'repository inspection'
            text = '%s at %s: test %s; build %s' % (r.path, i.revision, ' | '.join(
                i.test_commands) or '-', ' | '.join(i.build_commands) or '-')
        elif kind == 'repository':
            r = rows.get(conn, entities.Repository, ref['id']).entity
            label, text = 'repository with violated constraints', '%s: %s' % (
                r.path, '; '.join(x['constraint'] for x in r.findings
                                  if x['status'] == 'violated'))
        else:
            m = rows.get(conn, entities.Meeting, ref['id']).entity
            label, text = 'meeting', '%s, %s' % (m.name, m.held_at or 'undated')
        facts[h] = f
        lines.append('[%s] %s: %s' % (h, label, ' '.join(text.split())[:400]))
    return lines, facts


def prompt(mission, lines, *, replan=None):
    """The stable prefix, then the mission, its handles and, for a replan, what
    the previous version did (P8 §14)."""
    parts = [PREFIX, 'The mission:', 'Title: %s' % mission.title,
             'Objective: %s' % mission.objective]
    if mission.desired_outcome:
        parts.append('Desired outcome: %s' % mission.desired_outcome)
    for c in mission.success_criteria:
        parts.append('Success criterion (%s, %s): %s' % (
            c['check'], c.get('origin', 'explicit'), c['text']))
    parts += ['', 'Context:', *(lines or ['(nothing relevant is recorded)'])]
    if replan:
        parts += ['', 'This is a new plan: %s' % replan['why']]
        parts += ['Previous plan v%d:' % replan['plan_version']] + [
            '- %s %s (%s)%s' % (t['key'], t['title'], t['state'],
                                ', failed: %s' % t['failure_class'] if t['failure_class']
                                else '') for t in replan['tasks']]
        parts += ['Failed check: %s' % v for v in replan['failed']]
        if replan.get('review'):
            parts.append('Review: %s' % replan['review'])
    return '\n'.join(parts)


def _world(f):
    return f is not None and f['kind'] in WORLD


def blocking(parsed):
    """The part of an answer that stops a plan being recorded (P8 §10), or None."""
    qs = [q for q in parsed.get('questions') or () if q['blocking']]
    missing = [m for m in parsed.get('missing') or () if m['required']]
    conflicts = list(parsed.get('conflicts') or ())
    if not (qs or missing or conflicts):
        return None
    return {'kind': 'challenge' if conflicts else 'clarification',
            'questions': [q['question'] for q in qs],
            'missing': [{'name': m['name'], 'kind': m['kind']} for m in missing],
            'conflicts': conflicts}


def check(parsed, facts, *, criteria=()):
    """Core's checks beyond the schema (P8 §9, §11): every handle is one the
    prompt gave, of the right kind where it is used; and, when the answer is a
    plan rather than a blocking question, the structural contract. A list of
    problems; empty when the answer holds."""
    p, bad = parsed, []

    def known(h, where, ok, what):
        f = facts.get(h)
        if f is None or not ok(f):
            bad.append('%s: %r is not %s' % (where, h, what))

    for i, h in enumerate(p.get('refs') or ()):
        known(h, 'refs[%d]' % i, _world, 'a world handle')
    for i, c in enumerate(p.get('conflicts') or ()):
        known(c['ref'], 'conflicts[%d].ref' % i,
              lambda f: f['kind'] == 'knowledge_item' and f.get('ktype') in CHALLENGEABLE
              and f.get('state') == 'CONFIRMED',
              'a CONFIRMED decision, architecture, standard or preference item')
    for i, q in enumerate(p.get('questions') or ()):
        if q.get('about') is not None:
            known(q['about'], 'questions[%d].about' % i, lambda f: True, 'a known handle')
    for i, a in enumerate(p.get('assumptions') or ()):
        if a.get('about') is not None:
            known(a['about'], 'assumptions[%d].about' % i, lambda f: True, 'a known handle')
    labels = {t['id'] for t in p['tasks']}
    for t in p['tasks']:
        for i, h in enumerate(t.get('refs') or ()):
            known(h, 'task %s refs[%d]' % (t['id'], i), _world, 'a world handle')
        for i, h in enumerate(t.get('serves') or ()):
            known(h, 'task %s serves[%d]' % (t['id'], i),
                  lambda f: f['kind'] == 'requirement', 'a requirement handle')
        for i, x in enumerate(t.get('inputs') or ()):
            if (x.get('from_task') is None) == (x.get('ref') is None):
                bad.append('task %s inputs[%d] names exactly one of from_task and ref'
                           % (t['id'], i))
            elif x.get('ref') is not None:
                known(x['ref'], 'task %s inputs[%d].ref' % (t['id'], i), _world,
                      'a world handle')
            elif x['from_task'] not in labels:
                bad.append('task %s inputs[%d] comes from %r, which is not in the plan'
                           % (t['id'], i, x['from_task']))
    c = p.get('confidence')
    if c is not None and not 0 <= c <= 1:
        bad.append('confidence is 0..1')
    if blocking(p) is None:
        explicit = [h for h, f in facts.items()
                    if f['kind'] == 'requirement' and f['origin'] == 'explicit']
        asked = {q.get('about') for q in p.get('questions') or () if q['blocking']}
        crit = criteria or tuple(p.get('success_criteria') or ())
        bad += validate.problems(_as_tasks(p['tasks']), criteria=crit, explicit=explicit,
                                 asked=asked)
    return bad


def _as_tasks(tasks):
    return [dict(t, key=t['id'], depends_on=tuple(t.get('depends_on') or ()),
                 estimate=t.get('estimate', 1)) for t in tasks]


def resolve(parsed, facts):
    """(plan spec for `Work.propose_plan`, explicit handles, asked handles):
    tasks in dependency order keyed `t1…tN` by Core, every label and handle
    replaced. The answer must have passed `check` and not be blocking."""
    def ref(h):
        return {'kind': facts[h]['kind'], 'id': facts[h]['id']}
    ordered = validate.order(_as_tasks(parsed['tasks']))
    key = {t['id']: 't%d' % i for i, t in enumerate(ordered, 1)}
    tasks = []
    for t in ordered:
        tasks.append({
            'key': key[t['id']], 'title': t['title'], 'kind': t['kind'],
            'objective': t['objective'], 'expected_output': t['expected_output'],
            'boundaries': list(t.get('boundaries') or ()),
            'depends_on': [key[d] for d in t['depends_on']],
            'action_classes': list(t.get('action_classes') or ()),
            'capabilities_required': list(t.get('capabilities_required') or ()),
            'min_model_tier': t.get('min_model_tier'),
            'workspace_mode': t.get('workspace_mode') or (
                'worktree' if t['kind'] == 'code_change' else 'in_place'),
            'touches': list(t.get('touches') or ()),
            'refs': [ref(h) for h in t.get('refs') or ()],
            'serves': list(t.get('serves') or ()),
            'inputs': [dict({'what': x['what']}, **(
                {'from_task': key[x['from_task']]} if x.get('from_task') is not None
                else {'ref': ref(x['ref'])})) for x in t.get('inputs') or ()],
            'acceptance': [dict(c) for c in t.get('acceptance') or ()],
            'estimate': t['estimate']})
    reqs = [(h, f) for h, f in facts.items() if f['kind'] in ('requirement', 'constraint')]
    served = {}
    for t in tasks:
        for h in t['serves']:
            served.setdefault(h, []).append(t['key'])
    spec = {
        'summary': parsed['summary'], 'tasks': tasks,
        'success_criteria': [dict(c) for c in parsed.get('success_criteria') or ()],
        'inputs': [{'handle': h, 'kind': f['kind'], 'origin': f['origin'], 'text': f['text']}
                   for h, f in reqs],
        'coverage': [{'requirement': h, 'origin': f['origin'], 'tasks': served.get(h, [])}
                     for h, f in reqs if f['kind'] == 'requirement'],
        'assumptions': [dict({'text': a['text'], 'origin': 'inferred'}, **(
            {'about': ref(a['about']) if _world(facts[a['about']]) else a['about']}
            if a.get('about') is not None else {})) for a in parsed.get('assumptions') or ()],
        'questions': [{'question': q['question'], 'about': q.get('about')}
                      for q in parsed.get('questions') or () if not q['blocking']],
        'risks': list(parsed.get('risks') or ()), 'rollback': parsed.get('rollback'),
        'refs': [ref(h) for h in parsed.get('refs') or ()]}
    explicit = [h for h, f in facts.items()
                if f['kind'] == 'requirement' and f['origin'] == 'explicit']
    return spec, explicit, []


def resolve_block(block, facts):
    """A blocking answer with its conflict handles replaced (for the mission)."""
    return dict(block, conflicts=[{'ref': {'kind': facts[c['ref']]['kind'],
                                           'id': facts[c['ref']]['id']}, 'why': c['why']}
                                  for c in block['conflicts']])


# ── currency (P8 §11.3) ────────────────────────────────────────────────────

def currency(conn, mission, package_id):
    """(current, why) of a mission's context package: stale when, after the
    package was assembled, the mission's planning inputs changed, a knowledge
    item it cites moved state, or the mission's project changed. Pure over the
    event log and the package row."""
    pkg = rows.get(conn, entities.ContextPackage, package_id)
    if pkg is None:
        return False, 'the context package %s does not exist' % package_id
    pkg = pkg.entity
    cited = {it['ref']['id'] for it in pkg.items if it['ref']['kind'] == 'knowledge_item'}
    for r in conn.execute('SELECT * FROM events WHERE seq > ? ORDER BY seq', (pkg.as_of_seq,)):
        e = outbox.decode(r)
        sid = e.subject.id
        if (e.type == 'mission.updated' and sid == mission.id
                and set(e.payload.get('fields', ())) & set(INPUT_FIELDS)):
            return False, 'the mission changed after its context was assembled (event %d)' % e.seq
        if e.type == 'knowledge_item.state_changed' and sid in cited:
            return False, 'knowledge item %s it cites became %s (event %d)' % (
                sid, e.payload.get('to'), e.seq)
        if (mission.project_id is not None and e.project == mission.project_id
                and e.type in ('project.changed', 'architecture.state_changed')):
            return False, 'project %s changed (%s, event %d)' % (mission.project_id, e.type,
                                                                 e.seq)
    return True, 'nothing it rests on changed since event %d' % pkg.as_of_seq

"""T-324: the ten highest-risk uncovered branches of archeus/core/knowledge/passes.py.

Fail-closed and denial paths first, then boundary values, then error paths: the
isolation every own call must be given (K-O2: a fresh call directory, never the
user's repository, and no tools) in all three passes; a call that did not answer
recording nothing in all three passes; a result that cannot be recorded ending
its call `failed` and writing nothing else; which verifications the lessons
prompt may name; the byte and shape boundaries of what an answer may carry; the
caps a hostile payload must not get past; the two payload error paths; and what
the model is shown as "existing knowledge".

Same style and fixtures as test_knowledge_units.py and test_own_call_no_tools.py:
a real database on the test's own ARCHEUS_HOME, the real artifact store, the real
writer and the real `end_call`, with the two seams a pass has — the command that
assembles its context package and the own calls it makes — answered in place, and
`os.path.dirname` simulated where the two platforms genuinely differ. No model, no
CLI, no network, no real process, nothing Windows-specific, nothing that reads an
environment value or the clock.
"""

import json
import types

import pytest

from archeus.core.application import commands
from archeus.core.calls import Called
from archeus.core.domain import entities, ids
from archeus.core.domain.events import new_event
from archeus.core.domain.values import Ref
from archeus.core.knowledge import passes
from archeus.infra.artifacts import store as artifacts
from archeus.infra.db import Database, rows

WS = ids.GLOBAL_WORKSPACE
#: A repository path naming no drive and holding no reserved character: here it is
#: only ever prompt text, never a file name.
REPO_PATH = 'repo/under/test'
K1 = 'kno_01J' + '0' * 22
K2 = 'kno_01J' + '1' * 22
ENTITIES = {'entities': [{'name': 'core', 'kind': 'module', 'module': 'app/core',
                          'summary': 'The domain.'}]}
LESSONS = {'lessons': [{'title': 'Pin the formatter', 'text': 'it drifts',
                        'outcome': 'failed'}]}
DECISIONS = {'decisions': [{'statement': 'Ship dark-first', 'rationale': 'most use is at night'}]}


@pytest.fixture
def db():
    d = Database.open()
    yield d
    d.close()


@pytest.fixture
def actor(db):
    return Ref('system', db.writer.execute(commands.register_principal, {
        'kind': 'system', 'scopes': ['system']})['id'])


# ── seeding: the subjects a pass is given ──────────────────────────────────

def _insert(db, who, entity, etype):
    """One row plus the event that says it appeared (the writer refuses a command
    that mutates and records no event), written by the pass's own actor."""
    def put(tx, *, actor):
        tx.insert(entity, actor=actor)
        tx.append(new_event(etype, Ref(ids.kind_of(entity.id), entity.id), actor))
    db.writer.execute(put, {'actor': who})
    return entity.id


def _project(db, who):
    return _insert(db, who, entities.Project(id=ids.new_id('project'), workspace_id=WS,
                                             name='layered-python'), 'project.created')


def _task(db, who, plan_id, mission_id, key):
    return _insert(db, who, entities.Task(id=ids.new_id('task'), plan_id=plan_id,
                                         mission_id=mission_id, key=key, title='t',
                                         kind='code_change'), 'task.created')


def knowledge_source(db, who, *, payload=None, languages=(('python', 4),), frameworks=()):
    """A project, its repository and one COMPLETED inspection of it. `payload` is
    the graph artifact's content as bytes; None means the inspection has none."""
    pid = _project(db, who)
    rid = _insert(db, who, entities.Repository(id=ids.new_id('repository'), workspace_id=WS,
                                               project_id=pid, path=REPO_PATH,
                                               path_key=REPO_PATH), 'repository.registered')
    sha = None if payload is None else artifacts.put(payload)
    iid = _insert(db, who, entities.RepositoryInspection(
        id=ids.new_id('repository_inspection'), repository_id=rid, extractor_version=1,
        revision='rev-1', state='COMPLETED', languages=languages, frameworks=frameworks,
        payload_sha256=sha), 'repository_inspection.state_changed')
    return {'project_id': pid, 'repository_id': rid, 'inspection_id': iid, 'payload_sha': sha}


def meeting_source(db, who, *, project_id=None, held_at='2026-09-20',
                   notes=b'# Planning\nDecide: the dashboard ships dark-first.\n'):
    """One imported meeting: its notes are an artifact, its project may be none."""
    return _insert(db, who, entities.Meeting(id=ids.new_id('meeting'), workspace_id=WS,
                                             name='Planning', held_at=held_at,
                                             project_id=project_id,
                                             notes_artifact_id=artifacts.put(notes)),
                   'meeting.imported')


def mission_source(db, who, *, plan=True, plans=(), attempts=(), verifications=(), reviews=()):
    """One mission that ended, with what a lessons prompt is built from:
    `attempts` is ((attempt, exit_reason), ...), `verifications` the subject kinds
    each verification is bound to, `reviews` their verdicts. `plan=False` leaves the
    mission with no plan at all."""
    pid = _project(db, who)
    mid = _insert(db, who, entities.Mission(id=ids.new_id('mission'), workspace_id=WS,
                                            title='Ship it', objective='dark first',
                                            project_id=pid), 'mission.created')
    pl = None
    if plan:
        pl = _insert(db, who, entities.Plan(id=ids.new_id('plan'), mission_id=mid,
                                            plan_version=1, summary='the first plan'),
                     'plan.created')
    for v in plans:
        _insert(db, who, entities.Plan(id=ids.new_id('plan'), mission_id=mid, plan_version=v,
                                      summary='plan %d' % v), 'plan.created')
    for attempt, exit_reason in attempts:
        tk = _task(db, who, pl, mid, 'a%d' % attempt)
        _insert(db, who, entities.Execution(id=ids.new_id('execution'), task_id=tk,
                                            mission_id=mid, attempt=attempt,
                                            exit_reason=exit_reason), 'execution.state_changed')
    for i, kind in enumerate(verifications):
        subject = mid if kind == 'mission' else _task(db, who, pl, mid, 'v%d' % i)
        _insert(db, who, entities.Verification(
            id=ids.new_id('verification'), subject=Ref(kind, subject), verifier='code',
            criterion=0 if kind == 'mission' else None, plan_id=pl), 'verification.created')
    for verdict in reviews:
        _insert(db, who, entities.Review(id=ids.new_id('review'), mission_id=mid,
                                         reviewer='user', plan_id=pl,
                                         verdict=verdict), 'review.requested')
    ctx = _insert(db, who, entities.ContextPackage(id=ids.new_id('context_package'),
                                                   workspace_id=WS, subject_kind='mission',
                                                   subject_id=mid, query='q'),
                  'context_package.created')
    def bind(tx, *, actor):
        tx.update(entities.Mission, mid, {'context_package_id': ctx}, actor=actor)
        tx.append(new_event('mission.updated', Ref('mission', mid), actor))
    db.writer.execute(bind, {'actor': who})
    return {'mission_id': mid, 'project_id': pid, 'context_package_id': ctx}


def open_call(db, who, purpose, source):
    """A committed own-call decision with no outcome yet, as `OwnCalls.run` leaves
    one before its adapter runs: the real `end_call` needs the real row. Nothing is
    seeded from inside the writer thread — `source` is a ref the test made first."""
    rd = ids.new_id('route_decision')
    def put(tx, *, actor):
        tx.insert(entities.RouteDecision(
            id=rd, subject=Ref('archeus_call', purpose), purpose=purpose, decided_by='router',
            source=source, selected='fake', harness_id='fake',
            result='selected'), actor=actor)
        tx.append(new_event('route.decided', Ref('route_decision', rd), actor))
    db.writer.execute(put, {'actor': who})
    return rd


def answer(state='ok', parsed=None, rd='rte_x', usage=None, attempts=1, account='fake:fake'):
    """One own call's answer: the very tuple `OwnCalls.run` returns."""
    return Called(route_decision_id=rd, state=state, parsed=parsed, usage=usage or {},
                  detail='', attempts=attempts, account_ref=account)


# ── the rig: a pass's two seams, everything else real ──────────────────────

class Rig:
    """The passes over a real database with only what they reach through answered
    here: `record_context_package` (assembled here, stored as a real row) and the
    own calls. `raise_in_record` makes the recording command fail after it wrote
    something, which is how `_record`'s one-transaction rule is tested."""

    def __init__(self, db, who, monkeypatch, *, items=(), answers=None, raise_in_record=None):
        self.db, self.who = db, who
        self.items = list(items)
        self.assembled, self.asked, self.recorded = [], [], []
        self.last_package_id = None
        self.answers = list(answers or [answer()])
        self.raise_in_record = raise_in_record
        monkeypatch.setattr(passes, 'commands', types.SimpleNamespace(
            record_context_package=self._assemble))
        monkeypatch.setattr(passes, 'K', types.SimpleNamespace(
            record_knowledge_pass=self._recording('knowledge'),
            record_decisions=self._recording('decisions'),
            record_lessons=self._recording('lessons')))
        self.passes = passes.Passes(db, actor=who, calls=self)

    def _assemble(self, tx, *, actor, subject_kind, subject_id, query=None):
        pkg = entities.ContextPackage(id=ids.new_id('context_package'), workspace_id=WS,
                                      subject_kind=subject_kind, subject_id=subject_id,
                                      query=query or '', items=tuple(self.items))
        tx.insert(pkg, actor=actor)
        tx.append(new_event('context_package.created', Ref('context_package', pkg.id), actor))
        self.assembled.append({'subject_kind': subject_kind, 'subject_id': subject_id,
                               'query': query})
        self.last_package_id = pkg.id
        return {'id': pkg.id, 'items': list(pkg.items)}

    def _recording(self, which):
        def command(tx, *, actor, **kw):
            self.recorded.append(dict(kw, actor=actor, command=which))
            if self.raise_in_record is not None:
                # it wrote something first: a recording is one transaction or nothing
                p = ids.new_id('project')
                tx.insert(entities.Project(id=p, workspace_id=WS, name='rolled back'),
                          actor=actor)
                tx.append(new_event('project.created', Ref('project', p), actor))
                raise self.raise_in_record
            return {'which': which, 'items': 1}
        command.__qualname__ = 'record_' + which
        return command

    def run(self, **kw):
        self.asked.append(kw)
        return self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]

    def prompt(self, n=-1):
        return self.asked[n]['prompt']

    def asked_last(self):
        return self.asked[-1]


def _rows(db, cls, **eq):
    with db.read() as conn:
        return rows.where(conn, cls, **eq)


def _count(db, cls, **eq):
    return len(_rows(db, cls, **eq))


def _outcome(db, rd):
    with db.read() as conn:
        return rows.get(conn, entities.RouteDecision, rd).entity


def _lines(text):
    return text.split('\n')


def _fact(prompt, label):
    """The value of one `Label: value` line of a pass's suffix."""
    for line in _lines(prompt):
        if line.startswith(label + ': '):
            return line[len(label) + 2:]
    raise AssertionError('no %r line in the prompt:\n%s' % (label, prompt))


def _item(ref_kind, id_, level='L1', store='knowledge', type_='ENTITY', reason='recent'):
    return {'level': level, 'store': store, 'type': type_, 'ref': {'kind': ref_kind, 'id': id_},
            'reason': reason}


def _payload(files=(), edges=(), deps=()):
    return json.dumps({'files': list(files), 'edges': [list(e) for e in edges],
                       'dependencies': [{'name': d} for d in deps]}).encode('utf-8')


def _dirname_returns(value):
    """The one OS call the pass makes, simulated: `os.path.dirname` is posix on
    Linux and nt on Windows, and the branch under test is the one that only the
    payload's own separators can reach on either."""
    return types.SimpleNamespace(path=types.SimpleNamespace(dirname=lambda f: value))


# ── 1–3: what an own call must be given (K-O2: no tools, never the repository) ──

def test_the_knowledge_pass_calls_in_a_fresh_call_directory_with_no_tools(db, actor, monkeypatch):
    """passes.py:193-198. Flip `no_tools=True`, or hand the call `repo.path`
    instead of `paths.fresh_call_dir`, and this fails: a model would then run inside
    the user's repository, with tools, reading what an execution left there."""
    s = knowledge_source(db, actor, payload=_payload(files=['app/core/store.py']))
    r = Rig(db, actor, monkeypatch)
    assert r.passes.knowledge(s['inspection_id']) == 'ok'
    kw = r.asked_last()
    assert kw['workdir'] is passes.paths.fresh_call_dir            # the callable, not a path
    assert kw['no_tools'] is True
    assert kw['purpose'] == 'knowledge_extraction'
    assert kw['source'] == {'kind': 'repository_inspection', 'id': s['inspection_id']}
    assert (kw['workspace_id'], kw['project_id']) == (WS, s['project_id'])
    assert kw['schema'] is passes.KNOWLEDGE_SCHEMA
    assert kw['check'] is passes.check_knowledge
    assert REPO_PATH in kw['prompt'] and kw['workdir'] is not REPO_PATH     # data, never a cwd
    assert kw['context_package_id'] == r.last_package_id        # the package it just assembled
    assert r.recorded[0]['called']['context_package_id'] == r.last_package_id
    assert _count(db, entities.RouteDecision) == 0                  # the pass records no call


def test_the_decisions_pass_calls_in_a_fresh_call_directory_with_no_tools(db, actor, monkeypatch):
    """passes.py:214-222: the same two inversions for a meeting's pass."""
    pid = _project(db, actor)
    mid = meeting_source(db, actor, project_id=pid)
    r = Rig(db, actor, monkeypatch, answers=[answer(parsed=DECISIONS)])
    assert r.passes.decisions(mid) == 'ok'
    kw = r.asked_last()
    assert kw['workdir'] is passes.paths.fresh_call_dir and kw['no_tools'] is True
    assert kw['purpose'] == 'knowledge_extraction'
    assert kw['source'] == {'kind': 'meeting', 'id': mid}
    assert (kw['workspace_id'], kw['project_id']) == (WS, pid)
    assert kw['schema'] is passes.DECISIONS_SCHEMA
    assert kw['check'] is passes.check_decisions


def test_the_lessons_pass_calls_with_the_mission_package_and_no_tools(db, actor, monkeypatch):
    """passes.py:247-251. Drop `no_tools=True`, or stop passing the mission's own
    context package, and this fails."""
    s = mission_source(db, actor)
    r = Rig(db, actor, monkeypatch, answers=[answer(parsed=LESSONS)])
    assert r.passes.lessons(s['mission_id']) == 'ok'
    kw = r.asked_last()
    assert kw['workdir'] is passes.paths.fresh_call_dir and kw['no_tools'] is True
    assert kw['purpose'] == 'lesson'
    assert kw['source'] == {'kind': 'mission', 'id': s['mission_id']}
    assert kw['project_id'] == s['project_id']
    assert kw['context_package_id'] == s['context_package_id']
    assert kw['schema'] is passes.LESSONS_SCHEMA
    assert kw['check'] is passes.check_lessons
    assert r.recorded[0]['called']['context_package_id'] == s['context_package_id']


def test_a_meeting_that_names_no_project_is_passed_with_no_context_package(db, actor, monkeypatch):
    """passes.py:209-212 and 218. Remove the `if m.project_id is not None` guard and
    the pass assembles a package about a nonexistent project; invert it and the call
    carries a package id where there is none; drop the `else 'undated'` half of the
    held-at branch and the prompt says 'held None'."""
    mid = meeting_source(db, actor, project_id=None, held_at=None)
    r = Rig(db, actor, monkeypatch, answers=[answer(parsed=DECISIONS)])
    assert r.passes.decisions(mid) == 'ok'
    assert r.assembled == []                                        # nothing was assembled
    assert r.asked_last()['context_package_id'] is None
    assert r.asked_last()['project_id'] is None
    assert 'Meeting: Planning, undated' in r.prompt()
    assert r.recorded[0]['meeting_id'] == mid
    assert _count(db, entities.ContextPackage) == 0


def test_a_dated_meeting_of_a_project_is_asked_about_by_name(db, actor, monkeypatch):
    """passes.py:210-219. Invert the `held_at` condition and the date is printed
    twice or never; drop the meeting's name from the query and what was assembled
    no longer says what it was for."""
    pid = _project(db, actor)
    mid = meeting_source(db, actor, project_id=pid, held_at='2026-09-20')
    r = Rig(db, actor, monkeypatch, items=[_item('knowledge_item', K1)],
            answers=[answer(parsed=DECISIONS)])
    assert r.passes.decisions(mid) == 'ok'
    assert r.assembled == [{'subject_kind': 'project', 'subject_id': pid, 'query': 'Planning'}]
    assert r.asked_last()['context_package_id'].startswith('ctx_')
    assert 'Meeting: Planning, held 2026-09-20' in r.prompt()
    # the package reached the call as an id alone; a decisions recording names the
    # meeting it came from, and never carries items
    assert r.recorded[0]['meeting_id'] == mid


# ── 4: a call that did not answer records nothing, in every pass ───────────

@pytest.mark.parametrize('state', ['gated', 'unavailable', 'timeout', 'model_unavailable',
                                   'failed', 'invalid'],
                         ids=['gated', 'unavailable', 'timeout', 'model', 'failed', 'invalid'])
def test_a_call_that_did_not_answer_records_nothing_in_any_pass(db, actor, monkeypatch, state):
    """passes.py:199-200, 223-224 and 252-253. Remove any one of the three
    `if c.state != 'ok': return c.state` guards and that pass's row fails: an answer
    the call never gave would be recorded as CANDIDATE knowledge."""
    s = knowledge_source(db, actor, payload=_payload(files=['app/a/one.py']))
    mid = meeting_source(db, actor, project_id=s['project_id'])
    miss = mission_source(db, actor)
    for name, sid, parsed in (('knowledge', s['inspection_id'], ENTITIES),
                              ('decisions', mid, DECISIONS),
                              ('lessons', miss['mission_id'], LESSONS)):
        r = Rig(db, actor, monkeypatch, answers=[answer(state=state, parsed=parsed)])
        assert getattr(r.passes, name)(sid) == state
        assert r.recorded == []
        assert len(r.asked) == 1                                    # it asked, then stopped


# ── 5: a result that cannot be recorded ────────────────────────────────────

def test_a_lesson_that_cannot_be_recorded_ends_its_call_failed_and_writes_nothing(db, actor,
                                                                                 monkeypatch):
    """passes.py:144-156. Delete the `except` and the pass raises into its worker
    instead of naming the failure; delete the `end_call` and the call stays open
    forever; delete `usage` and its consumption is never ledgered."""
    s = mission_source(db, actor)
    rd = open_call(db, actor, 'lesson', Ref('mission', s['mission_id']))
    r = Rig(db, actor, monkeypatch,
            answers=[answer(parsed=LESSONS, rd=rd, usage={'tokens_in': 4}, attempts=2,
                            account='fake:acct')],
            raise_in_record=RuntimeError('disk full'))
    projects = _count(db, entities.Project)
    assert r.passes.lessons(s['mission_id']) == 'failed'
    c = _outcome(db, rd)
    assert c.outcome['state'] == 'failed'
    assert c.outcome['reason'] == 'could not record the result: RuntimeError: disk full'
    assert (c.outcome['attempts'], c.outcome['account_ref']) == (2, 'fake:acct')
    (ledger,) = _rows(db, entities.UsageLedger, route_decision_id=rd)
    # what the call consumed is ledgered, not merely a row: `usage` dropped from
    # `_record`'s end_call leaves basis 'none' and no tokens
    assert (ledger.entity.basis, ledger.entity.tokens_in) == ('partial', 4)
    assert ledger.entity.account_ref == 'fake:acct'
    assert _count(db, entities.Project) == projects        # what it wrote did not survive
    assert [x['command'] for x in r.recorded] == ['lessons']              # tried, once


def test_a_decision_that_cannot_be_recorded_names_its_error_type(db, actor, monkeypatch):
    """passes.py:152-155. Use `str(e)` alone for the reason and the record a user is
    shown no longer says what kind of failure this was."""
    pid = _project(db, actor)
    mid = meeting_source(db, actor, project_id=pid)
    rd = open_call(db, actor, 'knowledge_extraction', Ref('project', pid))
    r = Rig(db, actor, monkeypatch, answers=[answer(parsed=DECISIONS, rd=rd)],
            raise_in_record=ValueError('no such item'))
    assert r.passes.decisions(mid) == 'failed'
    assert _outcome(db, rd).outcome == {
        'state': 'failed', 'attempts': 1, 'account_ref': 'fake:fake',
        'reason': 'could not record the result: ValueError: no such item'}


def test_a_recorded_answer_carries_exactly_its_own_provenance(db, actor, monkeypatch):
    """passes.py:158-162 and 201-203. Drop a key of `_called` and an item is born
    without the decision, attempt count, account or package that made it; drop
    `known_items` and a `contradicts` claim becomes checkable against nothing."""
    s = knowledge_source(db, actor, payload=_payload(files=['app/a/one.py']))
    rd = 'rte_01J' + '0' * 22
    r = Rig(db, actor, monkeypatch, items=[_item('knowledge_item', K1)],
            answers=[answer(parsed=ENTITIES, rd=rd, usage={'tokens_in': 7}, attempts=2,
                            account='fake:acct')])
    assert r.passes.knowledge(s['inspection_id']) == 'ok'
    (got,) = r.recorded
    assert got['command'] == 'knowledge'
    assert got['called'] == {'route_decision_id': rd, 'attempts': 2, 'account_ref': 'fake:acct',
                             'usage': {'tokens_in': 7},
                             'context_package_id': r.asked_last()['context_package_id']}
    assert (got['project_id'], got['workspace_id'], got['inspection_id']) == (
        s['project_id'], WS, s['inspection_id'])
    assert got['result'] == ENTITIES
    assert got['known_items'] == (K1,)
    assert got['actor'] == actor                    # every write is the pass's own actor


# ── 6: which verifications may describe a mission ─────────────────────────

def test_only_verifications_of_the_mission_itself_reach_the_lessons_prompt(db, actor, monkeypatch):
    """passes.py:235-237. Remove the subject filter and another subject's
    verifications are offered as this mission's lessons; invert it and the mission's
    own never is."""
    mission_source(db, actor)                                   # a second, unrelated mission
    s = mission_source(db, actor, verifications=('mission', 'task', 'task'))
    r = Rig(db, actor, monkeypatch, answers=[answer(parsed=LESSONS)])
    assert r.passes.lessons(s['mission_id']) == 'ok'
    assert [ln for ln in _lines(r.prompt()) if ln.startswith('Verification')] == [
        'Verification: PENDING']


def test_an_attempt_is_named_by_its_exit_reason_else_by_its_state(db, actor, monkeypatch):
    """passes.py:243-246. Drop the `or e.state` and an attempt that never reported
    prints 'Attempt 2: None'; drop a plan line and the replan is invisible."""
    s = mission_source(db, actor, plans=(2, 3), attempts=((1, 'error'), (2, None)),
                       reviews=('accept', 'reject'))
    r = Rig(db, actor, monkeypatch, answers=[answer(parsed=LESSONS)])
    assert r.passes.lessons(s['mission_id']) == 'ok'
    body = _lines(r.prompt())[1:]                          # past the prefix's last line
    assert body[0] == 'Mission: Ship it' and body[1] == 'Objective: dark first'
    assert 'Ended as: CREATED' in body
    assert 'Attempt 1: error' in body and 'Attempt 2: INTENT' in body
    assert 'Plan v2: plan 2' in body and 'Plan v3: plan 3' in body
    assert [ln for ln in body if ln.startswith('Review')] == ['Review: PENDING',
                                                               'Review: PENDING']


def test_a_mission_with_nothing_recorded_is_still_asked_about_from_its_three_facts(db, actor,
                                                                                   monkeypatch):
    """passes.py:243-246, the empty comprehensions. Index one of these instead of
    iterating it and a mission with no plan and no attempt raises instead of asking."""
    s = mission_source(db, actor, plan=False)
    r = Rig(db, actor, monkeypatch, answers=[answer(parsed=LESSONS)])
    assert r.passes.lessons(s['mission_id']) == 'ok'
    assert _lines(r.prompt())[1:] == ['Mission: Ship it', 'Objective: dark first',
                                      'Ended as: CREATED']
    assert 'Plan v' not in r.prompt()


# ── 7: module paths are named one way on either platform ───────────────────

def test_a_payload_path_that_uses_backslashes_is_named_with_slashes(monkeypatch):
    """passes.py:120, the `.replace('\\', '/')` half. Delete it and a graph walked
    on Windows puts backslashed directory names in the prompt, so `app\\core` and
    `app/core` read as two modules and the prompt leaks the walker's separators."""
    seen = []
    monkeypatch.setattr(passes, 'os', types.SimpleNamespace(path=types.SimpleNamespace(
        dirname=lambda f: seen.append(f) or 'app\\core')))
    assert passes._module('app/core/store.py') == 'app/core'
    assert seen == ['app/core/store.py']


def test_a_file_at_the_root_of_the_repository_is_named_as_dot(monkeypatch):
    """passes.py:120, the `or '.'` half. Remove it and a root file contributes an
    empty directory name: 'Module directories: , app/core', which the model reads
    as a missing value and which sorts before every real directory."""
    monkeypatch.setattr(passes, 'os', _dirname_returns(''))
    assert passes._module('setup.py') == '.'
    monkeypatch.setattr(passes, 'os', _dirname_returns('app/core'))
    assert passes._module('app/core/store.py') == 'app/core'


def test_two_imports_inside_one_directory_are_not_an_import_between_it(db, actor, monkeypatch):
    """passes.py:173-175, the `if _module(a) != _module(b)` filter. Drop it and the
    prompt tells the model a module imports itself."""
    s = knowledge_source(db, actor, payload=_payload(
        files=['app/a/one.py', 'app/a/two.py', 'app/b/three.py'],
        edges=[['app/a/one.py', 'app/a/two.py'], ['app/a/two.py', 'app/b/three.py'],
               ['app/b/three.py', 'app/b/three.py']]))
    r = Rig(db, actor, monkeypatch)
    assert r.passes.knowledge(s['inspection_id']) == 'ok'
    assert _fact(r.prompt(), 'Imports between module directories') == 'app/a -> app/b'
    assert _fact(r.prompt(), 'Module directories') == ', '.join(['app/a', 'app/b'])


# ── 8: what one prompt may hold ────────────────────────────────────────────

def test_context_lines_name_at_most_prompt_modules_items(monkeypatch):
    """passes.py:123-128. Remove `[:PROMPT_MODULES]` and every selected item of the
    package goes into one model call; drop the header and the answer can cite no
    package."""
    keep = ['kno_01J%022d' % i for i in range(passes.PROMPT_MODULES)]
    items = [_item('knowledge_item', 'kno_01J%022d' % i) for i in range(200)]
    got = passes._context_lines({'id': 'ctx_test', 'items': items})
    body = _lines(got)
    assert body[0] == 'Context selected for this call (context package ctx_test):'
    assert len(body) == 1 + passes.PROMPT_MODULES
    assert body[1] == '- L1 knowledge ENTITY %s: recent' % keep[0]
    assert body[-1] == '- L1 knowledge ENTITY %s: recent' % keep[-1]
    assert ('kno_01J%022d' % passes.PROMPT_MODULES) not in got


def test_the_context_a_pass_shows_is_capped_where_the_prompt_is_built(db, actor, monkeypatch):
    """passes.py:186 calling 125, through the only caller that matters: the same
    inversion seen from a real pass."""
    s = knowledge_source(db, actor, payload=_payload(files=['app/a/one.py']))
    items = [_item('knowledge_item', 'kno_01J%022d' % i) for i in range(3 * passes.PROMPT_MODULES)]
    r = Rig(db, actor, monkeypatch, items=items)
    assert r.passes.knowledge(s['inspection_id']) == 'ok'
    assert len([ln for ln in _lines(r.prompt()) if ln.startswith('- L1 ')]) == passes.PROMPT_MODULES


def test_a_hostile_payload_of_thousands_of_paths_is_deduplicated_and_capped(db, actor, monkeypatch):
    """passes.py:172-176. Each of the three lists is asserted exactly, because each
    of the three guarantees is separately removable: drop one `[:PROMPT_MODULES]` and
    that list reaches the model whole (200 dependencies, not 80); drop the `set({...})`
    and a directory, link or dependency named two or three times is named that many
    times; drop `sorted` and the order is the payload's, or a set's hash order — the
    payload here repeats entries and is deliberately not in sorted order, so any of
    the three is visible."""
    files = ['pkg%04d/extra.py' % i for i in range(50)]              # two files in each of
    files += ['pkg%04d/mod.py' % i for i in range(1000)]             # 50 directories
    edges = [['pkg%04d/mod.py' % i, 'pkg%04d/mod.py' % (i + 1)] for i in range(1000)]
    edges += edges[:5]                                       # the first five named twice
    deps = ['dep%04d' % ((i * 97) % 200) for i in range(600)]    # 200 names, 3 each,
    s = knowledge_source(db, actor, payload=_payload(files=files, edges=edges, deps=deps))
    r = Rig(db, actor, monkeypatch)                     # scrambled order, so order is visible
    assert r.passes.knowledge(s['inspection_id']) == 'ok'
    n = passes.PROMPT_MODULES
    assert _fact(r.prompt(), 'Module directories').split(', ') == [
        'pkg%04d' % i for i in range(n)]
    assert _fact(r.prompt(), 'Imports between module directories').split(', ') == [
        'pkg%04d -> pkg%04d' % (i, i + 1) for i in range(n)]
    assert _fact(r.prompt(), 'Package dependencies').split(', ') == [
        'dep%04d' % i for i in range(n)]


def test_a_repository_that_yielded_no_facts_still_gets_its_pass(db, actor, monkeypatch):
    """passes.py:172-176 with `{}`: every `payload.get(key, ())` default, and the three
    `or 'none'` halves of 183-185. Index `payload['dependencies']` instead of
    defaulting and an inspection that found nothing raises instead of passing."""
    s = knowledge_source(db, actor, payload=_payload())
    r = Rig(db, actor, monkeypatch)
    assert r.passes.knowledge(s['inspection_id']) == 'ok'
    assert _fact(r.prompt(), 'Imports between module directories') == 'none'
    assert _fact(r.prompt(), 'Package dependencies') == 'none'
    assert _fact(r.prompt(), 'Module directories') == ''
    assert _fact(r.prompt(), 'Existing knowledge') == 'none'


# ── 9: the payload's two error paths ───────────────────────────────────────

def test_an_inspection_with_no_payload_at_all_describes_an_empty_project(db, actor, monkeypatch):
    """passes.py:171, the `if i.payload_sha256 else {}` half. Remove the guard and
    `artifacts.get(None)` raises (`not a sha256: None`) and the project never gets a
    knowledge base at all."""
    s = knowledge_source(db, actor)
    assert s['payload_sha'] is None
    r = Rig(db, actor, monkeypatch)
    assert r.passes.knowledge(s['inspection_id']) == 'ok'
    assert _fact(r.prompt(), 'Module directories') == ''
    assert _fact(r.prompt(), 'Repository') == '%s at rev-1' % REPO_PATH
    assert _fact(r.prompt(), 'Languages') == 'python'
    assert _fact(r.prompt(), 'Frameworks') == ''


def test_a_payload_that_is_not_json_makes_no_call_and_records_nothing(db, actor, monkeypatch):
    """passes.py:171. A graph artifact that is not JSON is this pass's failure and
    its worker's effect (`error: JSONDecodeError: ...`, worker.py:67), never a
    knowledge base built from nothing: no call runs, nothing is recorded."""
    s = knowledge_source(db, actor, payload=b'{"files": [truncated')
    r = Rig(db, actor, monkeypatch)
    with pytest.raises(ValueError):
        r.passes.knowledge(s['inspection_id'])
    assert r.asked == [] and r.recorded == []


# ── 10: what an answer may carry, and what the model may be shown ──────────

def test_existing_knowledge_names_only_the_knowledge_items_of_the_package(db, actor, monkeypatch):
    """passes.py:177, 185 and 203. Drop the `ref['kind'] == 'knowledge_item'` filter
    and the model is told a repository id and a meeting id are knowledge items it may
    contradict, and `record_knowledge_pass` is handed them as the same list."""
    items = [_item('knowledge_item', K1),
             _item('repository', 'rep_01J' + '0' * 22, level='L0', store='world', type_='REPO'),
             _item('knowledge_item', K2),
             _item('meeting', 'mtg_01J' + '0' * 22, level='L3', store='notes', type_='MEETING')]
    s = knowledge_source(db, actor, payload=_payload(files=['app/a/one.py']))
    r = Rig(db, actor, monkeypatch, items=items)
    assert r.passes.knowledge(s['inspection_id']) == 'ok'
    assert _fact(r.prompt(), 'Existing knowledge') == ', '.join([K1, K2])
    assert r.recorded[0]['known_items'] == (K1, K2)


def test_notes_that_are_not_valid_utf8_are_read_with_replacements_not_lost(db, actor, monkeypatch):
    """passes.py:213. Decode without `'replace'` and one stray byte aborts the
    meeting's pass; drop the decode and the notes never reach the model."""
    pid = _project(db, actor)
    mid = meeting_source(db, actor, project_id=pid,
                         notes=b'# Planning\r\n\tuse tabs \xff ok\r\n')
    r = Rig(db, actor, monkeypatch, answers=[answer(parsed=DECISIONS)])
    assert r.passes.decisions(mid) == 'ok'
    notes = r.prompt().split('\n\n', 1)[1]
    assert notes.startswith('# Planning')
    assert 'use tabs' in notes and '\ufffd' in notes                # shown, never dropped


def test_a_summary_of_exactly_the_body_limit_is_valid_and_one_byte_more_is_not():
    """passes.py:86-93. Use `>=` instead of `>` and a summary that fits exactly is
    refused; compare `len(str(...))` instead of the utf-8 byte count and a multibyte
    summary twice the size is accepted and then cannot be stored."""
    fits = {'name': 'a', 'kind': 'module', 'summary': 'x' * entities.BODY_MAX_BYTES}
    assert passes.check_knowledge({'entities': [fits]}) == []
    over = dict(fits, summary='x' * (entities.BODY_MAX_BYTES + 1))
    (problem,) = passes.check_knowledge({'entities': [over]})
    assert problem == 'item 0: summary is over %d bytes' % entities.BODY_MAX_BYTES
    half = entities.BODY_MAX_BYTES // 2                             # 1024 é are exactly 2048
    assert passes.check_knowledge({'entities': [dict(fits, summary='\u00e9' * half)]}) == []
    assert passes.check_knowledge({'entities': [dict(fits, summary='\u00e9' * (half + 1))]})


def test_a_field_that_is_null_absent_or_not_a_string_is_measured_not_crashed():
    """passes.py:90, the `f in it` guard and the `str(...)` that measures the value.
    Index `it[f]` without asking whether the field is there and a decision with no
    `rationale` raises KeyError inside its own check; drop `str(...)` and a JSON
    number or list in that field raises AttributeError instead of being measured as
    the text it would become; an answer that cannot be checked is refused by a crash
    rather than by a problem list."""
    assert passes.check_decisions({'decisions': [{'statement': 'ship it'}]}) == []
    assert passes.check_decisions({'decisions': [{'statement': 'ship it',
                                                  'rationale': None}]}) == []
    assert passes.check_lessons({'lessons': [{'title': 't', 'text': 'y',
                                              'outcome': 'worked'}]}) == []
    assert passes.check_decisions({'decisions': [{'statement': 's',
                                                  'rationale': 42}]}) == []
    assert passes.check_lessons({'lessons': [{'title': 't', 'text': True,
                                              'outcome': 'worked'}]}) == []
    (not_text,) = passes.check_knowledge({'entities': [{'name': 'a', 'kind': 'module',
                                                        'summary': ['x' * 3000]}]})
    assert not_text == 'item 0: summary is over %d bytes' % entities.BODY_MAX_BYTES
    long_text = 'y' * (entities.BODY_MAX_BYTES + 1)
    assert passes.check_lessons({'lessons': [{'title': 't', 'text': long_text,
                                              'outcome': 'worked'}]}) == [
        'item 0: text is over %d bytes' % entities.BODY_MAX_BYTES]
    assert passes.check_decisions({'decisions': [{'statement': 's',
                                                  'rationale': long_text}]}) == [
        'item 0: rationale is over %d bytes' % entities.BODY_MAX_BYTES]


@pytest.mark.parametrize('bad', [None, 7, ' ', '\n\t ', ['a']],
                         ids=['null', 'int', 'space', 'blank', 'list'])
def test_a_name_that_is_not_a_usable_string_is_blank_and_never_stored(bad):
    """passes.py:82-83 (`isinstance(v, str) and v.strip()`) and 98-99. Drop the
    isinstance and a JSON `null` name becomes the string 'None', is keyed as a real
    entity and is stored; and two of them are then duplicates of each other. The
    valid name in the last line is the control: it fails if the check is inverted."""
    assert passes.check_knowledge({'entities': [{'name': bad, 'kind': 'module',
                                                 'summary': 's'}]}) == [
        'entities[0].name is blank']
    assert passes._blank(bad) is True
    assert passes._blank(' x') is False
    assert passes.check_knowledge({'entities': [{'name': 'core', 'kind': 'module',
                                                 'summary': 's'}]}) == []

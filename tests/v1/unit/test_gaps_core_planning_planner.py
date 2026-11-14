"""T-318: the highest-risk uncovered branches of archeus/core/planning/planner.py.

Fail-closed and denial paths first — every way `currency` refuses a context package
the plan may not rest on, every way `blocking` holds a plan instead of recording it,
every invented handle `check` refuses — then the boundary values (the event cursor at
exactly the package's own `as_of_seq`, confidence 0 and 1, `validate.MAX_TASKS`, the
empty plan), then the error paths of `handles`, `describe`, `prompt`, `resolve`,
`coverage` and `resolve_block`.

Same style and helpers as tests/v1/unit/test_planning_units.py (its `OK`, `pt` and
`FACTS`), and the same in-memory seams as test_execution_units.py: one fake
connection answering the two reads planner makes with the exact column set
`writer.py` inserts, so the real `rows.decode` and `outbox.decode` do the decoding
here. No database, no model, no process, no sleep, nothing written to disk and
nothing that behaves differently on Windows: every path below is a string Core only
prints, and no OS call is made at all.
"""

import json

import pytest

from archeus.core.domain import entities, ids, shapes
from archeus.core.domain.events import new_event
from archeus.core.planning import planner, validate
from archeus.infra.db import rows

WS = 'ws_global'
OK = [{'text': 'works', 'check': 'automatic'}]
BY_TABLE = {table: cls for cls, table in rows.TABLES.items()}


def oid(kind, tag):
    """A fixed, well-formed id of *kind*: a ULID-shaped tail built from *tag*, so the
    ids in these tests (and their pytest ids) stay short and never move."""
    return '%s_01J%s' % (ids.PREFIXES[kind], (tag.upper() + '0' * 23)[:23])


MSN = oid('mission', 'M')
PRJ = oid('project', 'P')
PRJ2 = oid('project', 'P2')
REP = oid('repository', 'R')
RIN = oid('repository_inspection', 'B')
KNO = oid('knowledge_item', 'K')
KNO2 = oid('knowledge_item', 'K2')
MTG = oid('meeting', 'W')
MTG2 = oid('meeting', 'W2')
CTX = oid('context_package', 'C')
CTX_GONE = oid('context_package', 'Q')
ACTOR = oid('principal', 'S')

REQ = ({'text': 'a --version flag', 'origin': 'explicit'},
       {'text': 'it prints it', 'origin': 'inferred'})
CONS = ({'text': 'no new dependency', 'origin': 'explicit'},)
CRIT = ({'text': 'the flag prints', 'check': 'automatic'},)


def mission(**kw):
    """One mission: two requirements (one of them explicit), one constraint, one automatic
    success criterion, and no desired outcome unless the caller gives one."""
    kw.setdefault('requirements', REQ)
    kw.setdefault('constraints', CONS)
    kw.setdefault('success_criteria', CRIT)
    kw.setdefault('project_id', PRJ)
    return entities.Mission(id=MSN, workspace_id=WS, title='Ship v1',
                            objective='make the release', **kw)


def pt(id_, **kw):
    """One of the planner's own tasks, labelled by its own id (test_planning_units.py's)."""
    return dict({'id': id_, 'title': 'T %s' % id_, 'kind': 'code_change',
                 'objective': 'do %s' % id_, 'expected_output': 'out', 'acceptance': OK}, **kw)


#: The handles the prompt gave (test_planning_units.py's, plus the kinds the checks below
#: need: a repository, and a decision that is only a candidate).
FACTS = {'r1': {'kind': 'requirement', 'origin': 'explicit', 'text': 'a flag'},
         'r2': {'kind': 'requirement', 'origin': 'inferred', 'text': 'it prints'},
         'c1': {'kind': 'constraint', 'origin': 'explicit', 'text': 'no new deps'},
         'p1': {'kind': 'project', 'id': 'prj_x'},
         'y1': {'kind': 'repository', 'id': 'rep_x'},
         'k1': {'kind': 'knowledge_item', 'id': 'kni_x', 'ktype': 'DECISION',
                'state': 'CONFIRMED'},
         'k2': {'kind': 'knowledge_item', 'id': 'kni_y', 'ktype': 'FACT', 'state': 'CONFIRMED'},
         'k3': {'kind': 'knowledge_item', 'id': 'kni_z', 'ktype': 'DECISION',
                'state': 'CANDIDATE'}}


class _Cursor:
    def __init__(self, rows_):
        self.rows = list(rows_)

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def __iter__(self):
        return iter(self.rows)


class Conn:
    """The two reads planner makes, answered from memory.

    `rows.get` asks for one entity row by id and `currency` asks for every event after
    a seq; both get a record holding exactly the columns `writer.py` inserts, so the
    real `rows.decode` and `outbox.decode` do the decoding here. Any other query is an
    assertion failure rather than a silent empty answer.
    """

    def __init__(self, events=()):
        self.rows, self.events = {}, list(events)

    def put(self, entity):
        self.rows[(type(entity), entity.id)] = {
            'body': json.dumps(entity.to_dict(), sort_keys=True), 'version': 1,
            'created_at': '2026-10-30T10:00:00.000Z', 'updated_at': '2026-10-30T10:00:00.000Z',
            'created_by': ACTOR, 'updated_by': ACTOR}
        return entity.id

    def execute(self, sql, params=()):
        if sql.startswith('SELECT * FROM events WHERE seq > ?'):
            return _Cursor([r for r in self.events if r['seq'] > params[0]])
        assert sql.startswith('SELECT * FROM ') and sql.endswith(' WHERE id = ?'), sql
        cls = BY_TABLE[sql[len('SELECT * FROM '):-len(' WHERE id = ?')]]
        row = self.rows.get((cls, params[0]))
        return _Cursor([] if row is None else [row])


def event_row(seq, type, subject, project=None, payload=None):
    """One committed event, as the events table holds it (writer.py's column set)."""
    e = new_event(type, subject, {'kind': 'system', 'id': ACTOR}, payload or {},
                  seq=seq, project=project)
    return {'seq': seq, 'id': e.id, 'type': e.type, 'at': e.at,
            'actor_kind': e.actor.kind, 'actor_id': e.actor.id,
            'subject_kind': e.subject.kind, 'subject_id': e.subject.id,
            'workspace_id': e.workspace, 'project_id': e.project,
            'cause_chain': json.dumps(list(e.cause_chain)), 'visibility': e.visibility,
            'payload': json.dumps(e.payload)}


def ref(kind, id_):
    return {'kind': kind, 'id': id_}


def world_pkg(*refs_, **kw):
    """The package `describe` is given: what the assembler found, in its order."""
    return {'id': CTX, 'subject_kind': 'mission', 'subject_id': kw.get('subject_id', MSN),
            'items': [{'ref': r, 'level': 'L1', 'store': 'knowledge'} for r in refs_]}


def package(as_of=10, cites=(KNO,), id_=CTX):
    return entities.ContextPackage(id=id_, workspace_id=WS, subject_kind='mission',
                                   subject_id=MSN, as_of_seq=as_of,
                                   items=tuple({'ref': ref('knowledge_item', k), 'level': 'L3'}
                                               for k in cites))


def currency(*events, as_of=10, cites=(KNO,), m=None):
    """`planner.currency` over a package recorded at *as_of*, citing *cites*."""
    conn = Conn(events)
    conn.put(package(as_of=as_of, cites=cites))
    return planner.currency(conn, m or mission(), CTX)


@pytest.fixture
def world():
    """One row of every kind of world item a package may cite."""
    conn = Conn()
    conn.put(entities.KnowledgeItem(id=KNO, workspace_id=WS, type='DECISION', title='Ship it',
                                    text='always', state='CONFIRMED'))
    conn.put(entities.Project(id=PRJ, workspace_id=WS, name='Archeus', root_paths=('src', 'docs')))
    conn.put(entities.Project(id=PRJ2, workspace_id=WS, name='Second', root_paths=('docs',)))
    conn.put(entities.Repository(id=REP, workspace_id=WS, project_id=PRJ, path='repos/archeus',
                                 path_key='repos/archeus',
                                 findings=({'constraint': 'no new dependency',
                                            'status': 'violated'},
                                           {'constraint': 'keep it small', 'status': 'ok'})))
    conn.put(entities.RepositoryInspection(id=RIN, repository_id=REP, extractor_version=1,
                                           revision='abc123',
                                           test_commands=('python -m pytest -q',),
                                           build_commands=()))
    conn.put(entities.Meeting(id=MTG, workspace_id=WS, name='Kickoff',
                              held_at='2026-10-01T09:00:00.000Z'))
    conn.put(entities.Meeting(id=MTG2, workspace_id=WS, name='Follow-up', held_at=None))
    return conn


ALL_WORLD = (ref('knowledge_item', KNO), ref('project', PRJ), ref('repository', REP),
             ref('repository_inspection', RIN), ref('meeting', MTG), ref('meeting', MTG2))


# ── currency (P8 §11.3): the round is refused before the model is ever asked ──

def test_currency_refuses_a_package_that_has_no_row_at_all():
    """Fail closed: nothing may be planned against a package Core cannot read back."""
    assert planner.currency(Conn(), mission(), CTX_GONE) == (
        False, 'the context package %s does not exist' % CTX_GONE)


def test_currency_is_current_while_nothing_after_the_package_has_changed():
    assert currency() == (True, 'nothing it rests on changed since event 10')


@pytest.mark.parametrize('field', list(planner.INPUT_FIELDS), ids=list(planner.INPUT_FIELDS))
def test_a_change_to_any_planning_input_makes_the_package_stale(field):
    assert currency(event_row(11, 'mission.updated', ref('mission', MSN),
                              payload={'fields': [field]})) == (
        False, 'the mission changed after its context was assembled (event 11)')


def test_a_mission_change_outside_the_planning_inputs_keeps_the_package_current():
    for field in ('priority', 'max_replans', 'state', 'autonomy_profile'):
        got = currency(event_row(11, 'mission.updated', ref('mission', MSN),
                                 payload={'fields': [field]}))
        assert got[0] is True, field


def test_another_missions_change_keeps_this_package_current():
    assert currency(event_row(11, 'mission.updated', ref('mission', oid('mission', 'M2')),
                              payload={'fields': ['objective']}))[0] is True


def test_a_cited_knowledge_item_moving_state_makes_the_package_stale():
    assert currency(event_row(11, 'knowledge_item.state_changed', ref('knowledge_item', KNO),
                              payload={'from': 'CONFIRMED', 'to': 'SUPERSEDED'})) == (
        False, 'knowledge item %s it cites became SUPERSEDED (event 11)' % KNO)


def test_a_knowledge_item_the_package_never_cited_cannot_stale_it():
    assert currency(event_row(11, 'knowledge_item.state_changed',
                              ref('knowledge_item', KNO2),
                              payload={'from': 'CANDIDATE', 'to': 'RETRACTED'}))[0] is True


@pytest.mark.parametrize('type, subject', [
    ('project.changed', ref('project', PRJ)),
    ('architecture.state_changed', ref('repository', REP))],
    ids=['project.changed', 'architecture.state_changed'])
def test_the_missions_project_changing_makes_the_package_stale(type, subject):
    assert currency(event_row(11, type, subject, project=PRJ)) == (
        False, 'project %s changed (%s, event 11)' % (PRJ, type))


def test_a_mission_with_no_project_is_not_staled_by_a_project_change():
    assert currency(event_row(11, 'project.changed', ref('project', PRJ), project=PRJ),
                    m=mission(project_id=None))[0] is True


def test_a_different_project_changing_leaves_the_package_current():
    assert currency(event_row(11, 'project.changed', ref('project', PRJ2),
                              project=PRJ2))[0] is True


def test_currency_reads_only_the_events_after_the_packages_own_seq():
    """The boundary: the package was assembled AT `as_of_seq`, so that event is not a
    change after it; the one after it is."""
    at = event_row(10, 'mission.updated', ref('mission', MSN), payload={'fields': ['objective']})
    after = event_row(11, 'mission.updated', ref('mission', MSN),
                      payload={'fields': ['objective']})
    assert currency(at, as_of=10)[0] is True
    assert currency(at, after, as_of=10)[0] is False


# ── blocking (P8 §10): what stops a plan being recorded ──────────────

def test_a_required_missing_thing_holds_the_answer_as_a_clarification():
    answer = {'summary': 's', 'tasks': [pt('a', serves=['r1'])],
              'missing': [{'name': 'the repository', 'kind': 'repository', 'required': True},
                          {'name': 'a mock', 'kind': 'other', 'required': False}]}
    assert planner.blocking(answer) == {
        'kind': 'clarification', 'questions': [], 'conflicts': [],
        'missing': [{'name': 'the repository', 'kind': 'repository'}]}
    assert planner.check(answer, FACTS) == []


def test_a_missing_thing_the_plan_can_do_without_does_not_hold_it():
    assert planner.blocking({'summary': 's', 'tasks': [pt('a', serves=['r1'])],
                             'missing': [{'name': 'a mock', 'kind': 'other',
                                          'required': False}]}) is None


def test_a_question_that_blocks_nothing_records_no_block():
    assert planner.blocking({'summary': 's', 'tasks': [pt('a', serves=['r1'])],
                             'questions': [{'question': 'docs too?',
                                            'blocking': False}]}) is None


def test_an_answer_that_holds_is_never_judged_on_the_plan_it_never_gave():
    """The fail-closed split: a blocking answer is judged on its handles only, while an
    empty answer that asks for nothing is refused as a plan."""
    assert planner.check({'summary': 's', 'tasks': [],
                          'missing': [{'name': 'the repo', 'kind': 'service',
                                       'required': True}]}, FACTS) == []
    assert planner.check({'summary': 's', 'tasks': []}, FACTS) == ['a plan has at least one task']


# ── check (P8 §9, §11): an invented handle never becomes a row ───────

@pytest.mark.parametrize('handle, fact', [
    ('k3', FACTS['k3']),
    ('k4', {'kind': 'knowledge_item', 'id': 'kni_w', 'ktype': 'REFERENCE',
            'state': 'CONFIRMED'}),
    ('k5', {'kind': 'knowledge_item', 'id': 'kni_v'}),
    ('r1', FACTS['r1'])],
    ids=['unconfirmed decision', 'a type nothing challenges', 'no type or state',
         'not a knowledge item'])
def test_a_conflict_is_refused_unless_it_can_actually_be_challenged(handle, fact):
    bad = planner.check({'summary': 's', 'tasks': [pt('a', serves=['r1'])],
                         'conflicts': [{'ref': handle, 'why': 'it says otherwise'}]},
                        dict(FACTS, **{handle: fact}))
    assert bad == ["conflicts[0].ref: %r is not a CONFIRMED decision, architecture, standard "
                   "or preference item" % handle]
    assert planner.check({'summary': 's', 'tasks': [pt('a', serves=['r1'])],
                          'conflicts': [{'ref': 'k1', 'why': 'it says otherwise'}]},
                         FACTS) == []


def test_a_question_or_assumption_may_only_be_about_a_handle_the_prompt_gave():
    bad = planner.check({'summary': 's', 'tasks': [pt('a', serves=['r1'])],
                         'questions': [{'question': 'which one?', 'blocking': False,
                                        'about': 'r9'}],
                         'assumptions': [{'text': 'a guess', 'about': 'p9'}]}, FACTS)
    assert bad == ["questions[0].about: 'r9' is not a known handle",
                   "assumptions[0].about: 'p9' is not a known handle"]
    assert planner.check({'summary': 's', 'tasks': [pt('a', serves=['r1'])],
                          'questions': [{'question': 'which one?', 'blocking': False,
                                         'about': 'r2'}],
                          'assumptions': [{'text': 'a guess', 'about': 'p1'}]}, FACTS) == []


def test_a_task_serves_requirements_and_points_only_at_the_world_it_was_shown():
    answer = {'summary': 's', 'refs': ['r1'],
              'tasks': [pt('a', serves=['r1', 'p1', 'r9'], refs=['r1', 'z9'])]}
    assert planner.check(answer, FACTS) == [
        "refs[0]: 'r1' is not a world handle",
        "task a refs[0]: 'r1' is not a world handle",
        "task a refs[1]: 'z9' is not a world handle",
        "task a serves[1]: 'p1' is not a requirement handle",
        "task a serves[2]: 'r9' is not a requirement handle"]


def test_an_input_that_names_both_a_producing_task_and_a_world_handle_is_refused():
    bad = planner.check({'summary': 's', 'tasks': [pt(
        'a', serves=['r1'],
        inputs=[{'from_task': 'a', 'ref': 'p1', 'what': 'something'}])]}, FACTS)
    assert bad == ['task a inputs[0] names exactly one of from_task and ref']


def test_an_input_cannot_come_from_a_task_that_is_not_in_the_plan():
    bad = planner.check({'summary': 's', 'tasks': [pt(
        'a', serves=['r1'], inputs=[{'from_task': 'ghost', 'what': 'something'}])]}, FACTS)
    assert bad == ["task a inputs[0] comes from 'ghost', which is not in the plan"]


@pytest.mark.parametrize('value', [0, 1, 0.0, 1.0, None, -0.1, 1.1, 2, -1],
                         ids=['0', '1', '0.0', '1.0', 'none', 'minus a tenth', 'one point one',
                              'two', 'minus one'])
def test_confidence_is_only_ever_a_number_between_nought_and_one(value):
    bad = planner.check(dict({'summary': 's', 'tasks': [pt('a', serves=['r1'])]},
                             confidence=value), FACTS)
    assert bad == ([] if value is None or 0 <= value <= 1 else ['confidence is 0..1'])


def test_an_explicit_requirement_is_refused_unserved_unless_a_blocking_question_asks_it():
    unserved = {'summary': 's', 'tasks': [pt('a')], 'success_criteria': OK}
    unserved_problem = [
        'explicit requirement r1 is served by no task and asked about by no question']
    assert planner.check(unserved, FACTS) == unserved_problem
    assert planner.check(dict(unserved, questions=[{'question': 'which flag?',
                                                    'blocking': True, 'about': 'r1'}]),
                         FACTS) == []
    # a question that blocks nothing has not stopped the plan, so it covers nothing
    assert planner.check(dict(unserved, questions=[{'question': 'which flag?',
                                                    'blocking': False, 'about': 'r1'}]),
                         FACTS) == unserved_problem


def test_the_mission_criteria_judge_the_plan_when_the_call_supplies_them():
    """`worker` hands `check` the mission's own criteria; the plan's are then ignored."""
    all_human = {'summary': 's', 'tasks': [pt('a', serves=['r1'], kind='human',
                                              action_classes=(),
                                              acceptance=[{'text': 'ok', 'check': 'human'}])]}
    automatic = [{'text': 'the flag prints', 'check': 'automatic'}]
    assert planner.check(all_human, FACTS, criteria=automatic) == [
        'an automatic success criterion needs at least one non-human task']
    assert planner.check(dict(all_human, success_criteria=automatic), FACTS) == [
        'an automatic success criterion needs at least one non-human task']
    # given criteria of its own, the mission does not care what the plan claimed
    assert planner.check(dict(all_human, success_criteria=automatic), FACTS,
                         criteria=[{'text': 'a person agrees', 'check': 'human'}]) == []


def test_a_dependency_cycle_is_reported_and_resolve_refuses_that_plan():
    cyclic = {'summary': 's', 'tasks': [pt('a', serves=['r1'], depends_on=['b']),
                                        pt('b', depends_on=['c']), pt('c', depends_on=['a'])]}
    assert planner.check(cyclic, FACTS) == ['the dependencies form a cycle: a -> b -> c -> a']
    with pytest.raises(ValueError, match='cycle'):
        planner.resolve(cyclic, FACTS)


def test_a_task_never_depends_on_itself_and_core_keys_the_rest_in_dependency_order():
    loop = {'summary': 's', 'tasks': [pt('a', serves=['r1'], depends_on=['a'])]}
    assert planner.check(loop, FACTS) == ['task a depends on itself']


# ── resolve (P8 §13.2): a plan becomes a TaskSpec, labels and references and all ──

def test_resolve_keys_by_dependency_and_replaces_every_kind_of_reference():
    parsed = {'summary': 's', 'tasks': [
        pt('ship', depends_on=['build', 'test'], serves=['r1'],
           inputs=[{'from_task': 'build', 'what': 'the build'},
                   {'ref': 'y1', 'what': 'the tree'}]),
        pt('test', depends_on=['build'], serves=['r1'], kind='inspection',
           min_model_tier='small', workspace_mode='worktree'),
        pt('build', refs=['p1', 'y1'], serves=['r1'], kind='research')]}
    assert planner.check(parsed, FACTS) == []
    spec, explicit, asked = planner.resolve(parsed, FACTS)
    assert [(t['key'], t['title'], t['depends_on']) for t in spec['tasks']] == [
        ('t1', 'T build', []), ('t2', 'T test', ['t1']), ('t3', 'T ship', ['t1', 't2'])]
    # the declared mode wins; otherwise a code_change gets a worktree and all else its place
    assert [t['workspace_mode'] for t in spec['tasks']] == ['in_place', 'worktree', 'worktree']
    assert spec['tasks'][0]['refs'] == [{'kind': 'project', 'id': 'prj_x'},
                                         {'kind': 'repository', 'id': 'rep_x'}]
    assert spec['tasks'][2]['inputs'] == [{'what': 'the build', 'from_task': 't1'},
                                          {'what': 'the tree', 'ref': {'kind': 'repository',
                                                                       'id': 'rep_x'}}]
    assert all(t['estimate'] == 1 and t['expected_output'] == 'out' and t['boundaries'] == []
               for t in spec['tasks'])
    assert (explicit, asked) == (['r1'], [])
    assert spec['coverage'] == [
        {'requirement': 'r1', 'origin': 'explicit', 'tasks': ['t1', 't2', 't3']},
        {'requirement': 'r2', 'origin': 'inferred', 'tasks': []}]


def test_resolve_keeps_the_questions_anyone_can_answer_and_calls_the_rest_assumptions():
    parsed = {'summary': 's', 'tasks': [pt('a', serves=['r1'])],
              'questions': [{'question': 'docs too?', 'blocking': False, 'about': 'r2'},
                            {'question': 'which flag?', 'blocking': True, 'about': 'r1'}],
              'assumptions': [{'text': 'no about at all'},
                              {'text': 'about a world handle', 'about': 'p1'},
                              {'text': 'about a requirement', 'about': 'r2'}],
              'risks': ['the revision moves'], 'rollback': 'git revert the branch',
              'refs': ['p1'], 'confidence': 0.4}
    assert planner.check(parsed, FACTS) == []
    spec, explicit, asked = planner.resolve(parsed, FACTS)
    assert spec['questions'] == [{'question': 'docs too?', 'about': 'r2'}]
    assert spec['assumptions'] == [
        {'text': 'no about at all', 'origin': 'inferred'},
        {'text': 'about a world handle', 'origin': 'inferred',
         'about': {'kind': 'project', 'id': 'prj_x'}},
        {'text': 'about a requirement', 'origin': 'inferred', 'about': 'r2'}]
    assert spec['risks'] == ['the revision moves']
    assert spec['rollback'] == 'git revert the branch'
    assert spec['refs'] == [{'kind': 'project', 'id': 'prj_x'}]
    assert (explicit, asked) == (['r1'], [])
    assert spec['summary'] == 's' and spec['success_criteria'] == []


def test_coverage_names_every_requirement_and_which_of_the_tasks_given_serve_it():
    inputs = [{'handle': 'r1', 'kind': 'requirement', 'origin': 'explicit', 'text': 'a'},
              {'handle': 'r2', 'kind': 'requirement', 'origin': 'inferred', 'text': 'b'},
              {'handle': 'c1', 'kind': 'constraint', 'origin': 'explicit', 'text': 'c'}]
    tasks = [{'key': 't3', 'serves': ['r1']}, {'key': 't1', 'serves': ['r1', 'r2', 'ghost']}]
    assert planner.coverage(inputs, tasks) == [
        {'requirement': 'r1', 'origin': 'explicit', 'tasks': ['t3', 't1']},
        {'requirement': 'r2', 'origin': 'inferred', 'tasks': ['t1']}]
    assert planner.explicit_handles(inputs) == ['r1']


def test_resolve_block_exchanges_the_conflict_handle_for_what_it_points_at():
    block = planner.blocking({'summary': 's', 'tasks': [pt('a', serves=['r1'])],
                              'questions': [{'question': 'which flag?', 'blocking': True,
                                            'about': 'r1'}],
                              'missing': [{'name': 'the repository', 'kind': 'repository',
                                           'required': True}],
                              'conflicts': [{'ref': 'k1', 'why': 'it says never'}]})
    out = planner.resolve_block(block, FACTS)
    assert out['kind'] == 'challenge'
    assert out['conflicts'] == [{'ref': {'kind': 'knowledge_item', 'id': 'kni_x'},
                                 'why': 'it says never'}]
    # only the conflicts are rewritten: the question and the missing thing travel as they are
    assert out['questions'] == ['which flag?']
    assert out['missing'] == [{'name': 'the repository', 'kind': 'repository'}]
    assert set(out) == set(block)
    # the answer the caller handed over is copied, never edited
    assert block['conflicts'] == [{'ref': 'k1', 'why': 'it says never'}]


# ── handles / describe (P8 §9): the model is given handles, never ids of its own ──

def test_handles_number_each_kind_separately_and_never_the_subject_or_an_unlettered_kind(world):
    p = world_pkg(ref('project', PRJ), ref('meeting', MTG), ref('event', 'evt_x'),
                  ref('project', PRJ2), ref('project', MSN),
                  ref('mission', oid('mission', 'M2')), ref('context_package', CTX))
    assert planner.handles(p) == [('p1', ref('project', PRJ)), ('g1', ref('meeting', MTG)),
                                  ('p2', ref('project', PRJ2))]
    # describe agrees with handles(): nothing unlettered, and never the subject itself,
    # so the model is never handed a name it could only have got back from itself
    lines, facts = planner.describe(world, p, mission())
    assert lines == ['[r1] requirement, explicit: a --version flag',
                     '[r2] requirement, inferred: it prints it',
                     '[c1] constraint, explicit: no new dependency',
                     '[p1] project: Archeus (src, docs)',
                     '[g1] meeting: Kickoff, 2026-10-01T09:00:00.000Z',
                     '[p2] project: Second (docs)']
    assert set(facts) == {'r1', 'r2', 'c1', 'p1', 'g1', 'p2'}


def test_every_kind_of_world_item_is_described_from_its_row_and_not_invented(world):
    lines, facts = planner.describe(world, world_pkg(*ALL_WORLD), mission())
    assert lines == [
        '[r1] requirement, explicit: a --version flag',
        '[r2] requirement, inferred: it prints it',
        '[c1] constraint, explicit: no new dependency',
        '[k1] DECISION CONFIRMED: Ship it. always',
        '[p1] project: Archeus (src, docs)',
        '[y1] repository with violated constraints: repos/archeus: no new dependency',
        '[n1] repository inspection: repos/archeus at abc123: test python -m pytest -q; build -',
        '[g1] meeting: Kickoff, 2026-10-01T09:00:00.000Z',
        '[g2] meeting: Follow-up, undated']
    assert facts['k1'] == {'kind': 'knowledge_item', 'id': KNO, 'state': 'CONFIRMED',
                           'ktype': 'DECISION'}
    assert facts['p1'] == {'kind': 'project', 'id': PRJ}
    assert facts['y1'] == {'kind': 'repository', 'id': REP}
    assert facts['n1'] == {'kind': 'repository_inspection', 'id': RIN}
    assert facts['g2'] == {'kind': 'meeting', 'id': MTG2}
    assert set(facts) == {'r1', 'r2', 'c1', 'k1', 'p1', 'y1', 'n1', 'g1', 'g2'}


def test_a_repository_is_described_by_the_constraints_it_actually_violates():
    conn = Conn()
    conn.put(entities.Repository(id=REP, workspace_id=WS, project_id=PRJ, path='repos/archeus',
                                 path_key='repos/archeus',
                                 findings=({'constraint': 'no new dependency', 'status': 'ok'},
                                           {'constraint': 'py310 only', 'status': 'violated'},
                                           {'constraint': 'no new deps', 'status': 'violated'})))
    lines, facts = planner.describe(conn, world_pkg(ref('repository', REP)), mission())
    assert lines[-1] == ('[y1] repository with violated constraints: repos/archeus: '
                         'py310 only; no new deps')
    assert facts['y1'] == {'kind': 'repository', 'id': REP}
    # a package citing a row that has gone is a Core invariant broken loudly: there is
    # nothing left to describe, and describe is not the place to invent one
    conn.rows.clear()
    with pytest.raises(AttributeError):
        planner.describe(conn, world_pkg(ref('repository', REP)), mission())


def test_an_inspection_is_described_by_what_it_actually_ran():
    conn = Conn()
    conn.put(entities.Repository(id=REP, workspace_id=WS, project_id=PRJ, path='repos/archeus',
                                 path_key='repos/archeus', findings=()))
    conn.put(entities.RepositoryInspection(id=RIN, repository_id=REP, extractor_version=3,
                                           revision='deadbeef', test_commands=(),
                                           build_commands=('python -m build',)))
    # a command list nobody filled in is described as never run, not guessed at
    lines, facts = planner.describe(conn, world_pkg(ref('repository_inspection', RIN)),
                                    mission())
    assert lines[-1] == ('[n1] repository inspection: repos/archeus at deadbeef: '
                         'test -; build python -m build')
    assert facts['n1'] == {'kind': 'repository_inspection', 'id': RIN}


def test_a_knowledge_item_is_described_on_one_line_of_at_most_four_hundred_characters():
    conn = Conn()
    conn.put(entities.KnowledgeItem(id=KNO, workspace_id=WS, type='STANDARD', title='Style',
                                    text='head\n\n%s\n\nmore' % ('y' * 500), state='CONFIRMED'))
    conn.put(entities.KnowledgeItem(id=KNO2, workspace_id=WS, type='FACT', title='No body',
                                    text='', state='CONFIRMED'))
    lines, _ = planner.describe(conn, world_pkg(ref('knowledge_item', KNO),
                                                ref('knowledge_item', KNO2)), mission())
    assert lines[-2] == '[k1] STANDARD CONFIRMED: ' + ('Style. head %s more' % ('y' * 500))[:400]
    assert len(lines[-2]) == len('[k1] STANDARD CONFIRMED: ') + 400
    # an item with no body at all is described by its title alone: no stray `None`
    # can reach here, because a KnowledgeItem body is a string by entities.py:465
    assert lines[-1] == '[k2] FACT CONFIRMED: No body.'


# ── prompt (P8 §9): one round of context, and what a re-plan must remember ────

def test_the_prompt_names_the_mission_and_says_so_when_nothing_is_relevant():
    p = planner.prompt(mission(desired_outcome='a flag that prints'), [])
    assert p.startswith(planner.PREFIX)
    assert 'Title: Ship v1' in p
    assert 'Objective: make the release' in p
    assert 'Desired outcome: a flag that prints' in p
    assert 'Success criterion (automatic, explicit): the flag prints' in p
    assert '(nothing relevant is recorded)' in p


def test_the_prompt_leaves_out_what_the_mission_does_not_hold():
    p = planner.prompt(mission(desired_outcome='',
                               success_criteria=({'text': 'a person agrees', 'check': 'human',
                                                 'origin': 'inferred'},)),
                       ['[p1] project: Archeus (src, docs)'])
    assert 'Desired outcome' not in p
    assert 'Success criterion (human, inferred): a person agrees' in p
    # the mission's requirements and constraints reach the model only as described
    # handles from `describe`, never quoted here where it could copy one back
    assert 'a --version flag' not in p and 'no new dependency' not in p
    assert '[p1] project: Archeus (src, docs)' in p


def test_a_replan_tells_the_planner_what_the_last_version_asked_for_and_where_it_stopped():
    p = planner.prompt(mission(), ['[p1] project: Archeus'], replan={
        'why': 't1 failed its check', 'plan_version': 3,
        'tasks': ({'key': 't1', 'title': 'Build', 'state': 'FAILED', 'failure_class': 'timeout'},
                  {'key': 't2', 'title': 'Test', 'state': 'DONE', 'failure_class': None}),
        'failed': ['t1: the check timed out'],
        'checkpoints': ({'key': 't1', 'open_problems': ('the fixture hangs',),
                         'next_action': 'run it alone'},
                        {'key': 't3', 'open_problems': (), 'next_action': None}),
        'review': 'the plan was too big'})
    assert 'This is a new plan: t1 failed its check' in p
    assert '- t1 Build (FAILED), failed: timeout' in p
    assert '- t2 Test (DONE)' in p
    assert 'Failed check: t1: the check timed out' in p
    assert 'Where t1 stopped: the fixture hangs; next: run it alone' in p
    assert 'Where t3 stopped: no open problem recorded; next: continue from the diff' in p
    assert 'Review: the plan was too big' in p
    thin = planner.prompt(mission(), [], replan={'why': 'the terms changed', 'plan_version': 1,
                                                 'tasks': [], 'failed': []})
    assert 'Review' not in thin and 'Where' not in thin and 'Previous plan v1:' in thin


# ── SCHEMA (P8 §11.1): what is refused before a handle or a task is ever stored ──

def test_the_schema_holds_the_plan_to_the_same_limits_core_stores_under():
    def task(n):
        return {'id': 'x%d' % n, 'title': 'T%d' % n, 'kind': 'research',
                'objective': 'do %d' % n, 'expected_output': 'out', 'acceptance': OK}

    shapes.validate({'summary': 's', 'tasks': [task(n) for n in range(validate.MAX_TASKS)]},
                    planner.SCHEMA)
    with pytest.raises(shapes.Invalid, match='more than %d' % validate.MAX_TASKS):
        shapes.validate({'summary': 's',
                         'tasks': [task(n) for n in range(validate.MAX_TASKS + 1)]},
                        planner.SCHEMA)


def plan_task(**kw):
    """One task that passes SCHEMA whole, so a refusal below is the mutated field's own."""
    return dict({'id': 'a', 'title': 'T', 'kind': 'research', 'objective': 'o',
                 'expected_output': 'out', 'acceptance': OK, 'refs': [], 'serves': [],
                 'depends_on': [], 'inputs': [], 'estimate': 1, 'min_model_tier': None,
                 'workspace_mode': None, 'capabilities_required': [],
                 'action_classes': ['read', 'write_repo']}, **kw)


@pytest.mark.parametrize('field, value', [
    ('refs', ['z' * 13]),
    ('depends_on', ['z' * 13]),
    ('estimate', '3'),
    ('estimate', True),
    ('kind', 'dance'),
    ('min_model_tier', 'huge'),
    ('workspace_mode', 'side'),
    ('capabilities_required', ['telepathy']),
    ('action_classes', ['teleport']),
    ('acceptance', [{'text': 'ok', 'check': 'magic'}])],
    ids=['plan ref too long', 'depends_on too long', 'estimate as text', 'estimate as bool',
         'unknown kind', 'unknown tier', 'unknown workspace mode', 'unknown capability',
         'unknown action class', 'unknown acceptance check'])
def test_the_schema_refuses_what_core_could_never_store(field, value):
    shapes.validate({'summary': 's', 'tasks': [plan_task()]}, planner.SCHEMA)
    with pytest.raises(shapes.Invalid):
        shapes.validate({'summary': 's', 'tasks': [plan_task(**{field: value})]}, planner.SCHEMA)


@pytest.mark.parametrize('field, value', [
    ('refs', ['p1', 'y1']),
    ('depends_on', ['a']),
    ('estimate', 3),
    ('estimate', 0),
    ('kind', 'document'),
    ('min_model_tier', 'mid'),
    ('workspace_mode', 'in_place'),
    ('capabilities_required', ['shell']),
    ('action_classes', ['read', 'exec']),
    ('acceptance', [{'text': 'ok', 'check': 'human'}])],
    ids=['plan refs', 'depends_on', 'estimate', 'estimate nought', 'kind', 'tier',
         'workspace mode', 'capability', 'action classes', 'acceptance'])
def test_the_schema_accepts_the_shape_core_stores(field, value):
    """The same task with the same field filled in honestly: so the refusal above is
    that field's own and not the task being wrong all along."""
    shapes.validate({'summary': 's', 'tasks': [plan_task(**{field: value})]}, planner.SCHEMA)

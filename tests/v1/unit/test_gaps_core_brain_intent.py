"""T-719: the highest-risk uncovered branches of archeus/core/brain/intent.py.

`check`'s happy paths and a first round of denials are pinned by
tests/v1/unit/test_intent_units.py (U03-U06) and the projection of homes by
tests/v1/integration/test_t144_prompt_projection.py. This file sits on what
neither reaches, with the emphasis the card gives: the classification boundaries
(what still counts as a stated objective, what is still a confidence, which item
a conflict may be raised against, which handle a supersession may name) and the
ambiguous-input half (`describe`'s labels and facts, which `check` later judges,
and the projection that must happen *before* the 400-character cap).

Style and fixtures are copied from the closest existing tests: the hand-built
`FACTS`/`FULL` of test_intent_units.py:63-113 for the pure functions, the seeded
in-process database of test_gaps_core_metrics.py:84-88 and the `put` helper of
v1/integration/test_graph_query.py:22 for `describe`, and the injected-home style
of test_t144_stored_reads.py:256-265 (a home arrives as
`Homes(registered_homes=[<tmp_path home>], shorts=...)`). No model, no harness, no
process, no network, no clock, no OS call: `shorts` is a lambda, so the Windows
short-name probe is never reached and nothing here is platform-specific.
"""

import copy

import pytest

from archeus.core.brain import intent as brain
from archeus.core.context.assemble import CHALLENGEABLE
from archeus.core.domain import entities, ids, shapes, states
from archeus.core.domain.events import new_event
from archeus.core.domain.values import Ref
from archeus.core.homes import REPLACEMENT, Homes
from archeus.infra.db import Database

WS = ids.GLOBAL_WORKSPACE
KN = 'knowledge_item'


def _kn(id_, state, ktype, source_kind=None):
    return {'kind': KN, 'id': id_, 'state': state, 'ktype': ktype, 'source_kind': source_kind}


def _kn_card(kid):
    return {'type': 'knowledge', 'ref': {'kind': KN, 'id': kid}}


def _msg(id_, cards=()):
    return {'kind': 'message', 'id': id_, 'cards': list(cards)}


#: handles of every kind `check` judges, in the spelling `describe` produces
FACTS = {
    'p1': {'kind': 'project', 'id': 'prj_1'},
    'm1': {'kind': 'mission', 'id': 'msn_1', 'state': 'EXECUTING'},
    'm2': {'kind': 'mission', 'id': 'msn_2', 'state': 'COMPLETED'},
    'i1': {'kind': 'idea', 'id': 'ida_1', 'state': 'CAPTURED'},
    'k1': _kn('kno_1', 'CONFIRMED', 'DECISION', 'user'),          # deciding, confirmed
    'k2': _kn('kno_2', 'CANDIDATE', 'DECISION', 'import'),        # deciding, imported notes
    'k3': _kn('kno_3', 'CANDIDATE', 'DECISION', 'inspection'),    # deciding, not imported
    'k4': _kn('kno_4', 'CONFIRMED', 'ENTITY', 'inspection'),      # confirmed, not deciding
    'k5': _kn('kno_5', 'CANDIDATE', 'PREFERENCE', 'user'),
    'k6': _kn('kno_6', 'CONFIRMED', 'PREFERENCE', 'user'),
    'k7': _kn('kno_7', 'CANDIDATE', 'LESSON', 'execution'),       # a lesson decides nothing
    'k8': _kn('kno_8', 'CONFIRMED', 'ARCHITECTURE', 'brain'),
    'u1': _msg('msg_1', [_kn_card('kno_5')]),                     # the turn that made a preference
    'u2': _msg('msg_2'),                                           # a turn that made nothing
    'u3': _msg('msg_3', [_kn_card('kno_11'),
                         {'type': 'mission', 'ref': {'kind': 'mission', 'id': 'msn_9'}},
                         _kn_card('kno_12')]),                    # two items, one card each
    'u4': _msg('msg_4', [{'type': 'status', 'ref': {'kind': 'mission', 'id': 'msn_8'}}]),
    'g1': {'kind': 'meeting', 'id': 'mtg_1'},
}


def _ok(**kw):
    """A reading that `check` accepts; override any field to sit on one branch."""
    d = {'kind': 'new_work', 'title': 'Add a flag', 'objective': 'a --flag', 'target': None,
         'project': 'p1', 'mentions': [{'name': 'Ada', 'kind': 'person', 'ref': None}],
         'requirements': [], 'constraints': [], 'ambiguities': [], 'conflicts': [],
         'feedback': None, 'answer': None, 'confidence': None}
    d.update(kw)
    return d


# ── 1. supersession: only a preference, a lesson, or the turn that made one ──
# source: intent.py:226-228 (the refusal), intent.py:172-177 (`superseded`)

@pytest.mark.parametrize('h', ['k6', 'k7', 'u1', 'u3'],
                         ids=['confirmed-preference', 'candidate-lesson', 'turn-with-card',
                              'turn-with-two-cards'])
def test_supersedes_accepts_only_what_can_actually_be_replaced(h):
    got = brain.check(_ok(kind='preference', feedback={'signal': 'correction', 'title': 't',
                                                       'supersedes': h}), FACTS)
    assert got == [], got


@pytest.mark.parametrize('h', ['k1', 'k4', 'u2', 'u4', 'p1', 'm1', 'g1', 'i1', 'zz'],
                         ids=['confirmed-decision', 'confirmed-entity', 'empty-turn',
                              'turn-without-a-knowledge-card', 'project', 'mission', 'meeting',
                              'idea', 'invented'])
def test_supersedes_refuses_anything_a_preference_could_never_replace(h):
    """The dangerous inversion: taking `supersedes` at the model's word lets one
    preference silently overwrite a DECISION, a mission or an invented id."""
    got = brain.check(_ok(kind='preference', feedback={'signal': 'correction', 'title': 't',
                                                       'supersedes': h}), FACTS)
    assert got and all('supersedes' in p for p in got), got
    assert ("feedback.supersedes: '%s' is not a preference or lesson" % h) in got[0]


def test_superseded_names_the_last_knowledge_item_a_turn_produced():
    """`made[-1]`, not `cards[-1]`: the turn that made a preference and carried a
    status card must name the preference, and a DECISION must name nothing."""
    assert brain.superseded(FACTS['u3']) == 'kno_12'
    assert brain.superseded(FACTS['u1']) == 'kno_5'
    assert brain.superseded(FACTS['u4']) is None
    assert brain.superseded(FACTS['u2']) is None
    assert brain.superseded({'kind': 'message', 'id': 'msg_5'}) is None      # no cards at all
    assert brain.superseded(_kn('kno_9', 'CONFIRMED', 'LESSON', 'user')) == 'kno_9'
    assert brain.superseded(_kn('kno_10', 'CONFIRMED', 'PREFERENCE', 'user')) == 'kno_10'
    assert brain.superseded(FACTS['k1']) is None                             # not a preference
    assert brain.superseded(FACTS['p1']) is None
    assert brain.superseded(FACTS['g1']) is None


# ── 2. a conflict is only ever raised against something that decides ─────────
# source: intent.py:203-205 and `_challengeable`, intent.py:163-166

@pytest.mark.parametrize('h, ok', [
    ('k1', True), ('k2', True), ('k6', True), ('k8', True),
    ('k3', False), ('k4', False), ('k5', False), ('k7', False),
    ('m1', False), ('p1', False), ('u1', False), ('g1', False), ('i1', False), ('zz', False)],
    ids=['confirmed-decision', 'candidate-decision-imported', 'confirmed-preference',
         'confirmed-architecture', 'candidate-decision-inspected', 'confirmed-entity',
         'candidate-preference', 'candidate-lesson', 'mission', 'project', 'message', 'meeting',
         'idea', 'invented'])
def test_a_conflict_names_only_a_deciding_item_the_package_gave(h, ok):
    """Dropping the state clause lets a CANDIDATE the import never produced (k3)
    or a candidate preference (k5) gate the plan; dropping the type clause lets a
    confirmed ENTITY (k4) do it. `CHALLENGEABLE` is the list, not a guess."""
    assert ('PREFERENCE' in CHALLENGEABLE and 'LESSON' not in CHALLENGEABLE)
    got = brain.check(_ok(conflicts=[{'ref': h, 'why': 'it says so'}]), FACTS)
    assert bool([p for p in got if 'conflicts[0].ref' in p]) is (not ok), (h, got)


# ── 3. continue_work must name a mission that is still running ──────────────
# source: `_live_mission`, intent.py:159-160, and its use at intent.py:207-209

LIVE = [s for s in states.states('mission') if s not in states.terminal('mission')]
DEAD = sorted(states.terminal('mission'))


@pytest.mark.parametrize('state', LIVE, ids=[s.lower() for s in LIVE])
def test_every_mission_state_without_an_end_edge_is_still_continuable(state):
    facts = dict(FACTS, m1={'kind': 'mission', 'id': 'msn_1', 'state': state})
    assert brain.check({'kind': 'continue_work', 'target': 'm1'}, facts) == []


@pytest.mark.parametrize('state', DEAD, ids=[s.lower() for s in DEAD])
def test_continue_work_refuses_a_mission_that_has_reached_its_end(state):
    """`not in terminal(...)` inverted (or a hardcoded COMPLETED-only list, which
    forgets CANCELLED) would let Core continue a finished mission."""
    assert state in ('COMPLETED', 'CANCELLED')
    facts = dict(FACTS, m1={'kind': 'mission', 'id': 'msn_1', 'state': state})
    got = brain.check({'kind': 'continue_work', 'target': 'm1'}, facts)
    assert len(got) == 1 and 'an open mission' in got[0], (state, got)


@pytest.mark.parametrize('h', ['i1', 'k1', 'p1', 'u1', 'g1', 'zz'],
                         ids=['idea', 'knowledge', 'project', 'message', 'meeting', 'invented'])
def test_continue_work_refuses_a_target_that_is_not_a_mission_at_all(h):
    got = brain.check({'kind': 'continue_work', 'target': h}, FACTS)
    assert len(got) == 1 and 'an open mission' in got[0], (h, got)


def test_a_missing_target_is_reported_once_and_as_its_own_problem():
    """The other half of intent.py:207-209: with no target at all the ONLY
    complaint is the one that says what to add (not also "not an open mission"),
    so the retry can fix the right thing. Its mirror — a named live mission
    costing nothing — is the test above, which is where dropping the
    `and t is None` guard shows up."""
    assert brain.check({'kind': 'continue_work'}, FACTS) == [
        'continue_work names the open mission it continues (target)']


# ── 4. a resource_directive that names nothing is refused outright ──────────
# source: intent.py:241-244 (the `any(...)` over prefer/forbid × accounts/harnesses)

@pytest.mark.parametrize('d', [
    {'prefer': {'accounts': ['work']}}, {'forbid': {'harnesses': ['codex']}},
    {'prefer': {'accounts': [], 'harnesses': ['claude']}},
    {'prefer': None, 'forbid': {'accounts': ['a'], 'harnesses': []}}],
    ids=['prefer-account', 'forbid-harness', 'one-name-among-empty', 'forbid-only'])
def test_a_directive_that_names_one_account_or_harness_is_taken(d):
    assert brain.check(_ok(resource_directive=dict(d, scope='standing')), FACTS) == []


@pytest.mark.parametrize('d', [
    {}, {'scope': 'mission'}, {'prefer': None}, {'prefer': {}, 'forbid': {}},
    {'prefer': {'accounts': []}}, {'prefer': {'accounts': []}, 'forbid': {'harnesses': []}},
    {'prefer': {'accounts': None}}, {'prefer': {'accounts': [], 'nothing': ['x']}}],
    ids=['empty', 'scope-only', 'prefer-null', 'both-empty-dicts', 'empty-accounts',
         'everything-empty', 'null-group', 'unknown-group-only'])
def test_a_standing_directive_that_names_nothing_is_refused(d):
    """`any` → `all`, or reading only `prefer`, would let an empty standing
    directive reach Core as a never-satisfiable resource policy (ADR-0042 §2)."""
    got = brain.check(_ok(resource_directive=dict(d, scope='standing')), FACTS)
    assert [p for p in got if 'resource_directive' in p], (d, got)


def test_the_empty_directive_is_the_shapes_job_to_pass_and_checks_to_refuse():
    """The schema allows `{'scope': 'standing'}` (both groups are nullable): only
    the branch above stands between a model's shrug and a standing policy."""
    shapes.validate({'kind': 'question', 'answer': [{'text': 'a', 'refs': []}],
                     'resource_directive': {'scope': 'standing', 'prefer': None,
                                            'forbid': None}}, brain.SCHEMA)
    assert brain.check(_ok(resource_directive={'scope': 'standing'}), FACTS) == [
        'a resource_directive names an account or harness']


# ── 5. a question is answered in claims, and every claim cites something ─────
# source: intent.py:229-237

@pytest.mark.parametrize('answer', [None, []], ids=['null', 'empty-list'])
def test_a_question_that_leaves_nothing_behind_is_refused(answer):
    got = brain.check(_ok(kind='question', answer=answer), FACTS)
    assert [p for p in got if 'claims' in p], got


def test_the_claim_that_cites_nothing_is_named_by_its_own_index():
    """`answer[1]`, not `answer[0]`: the retry message has to point at the claim
    that needs it, and the citing claim must be left alone."""
    got = brain.check(_ok(kind='question', answer=[{'text': 'a', 'refs': ['p1']},
                                                   {'text': 'b', 'refs': []}]), FACTS)
    assert got == ['answer[1] cites nothing']


def test_every_uncited_handle_in_the_answer_is_named_with_its_claim():
    got = brain.check(_ok(kind='question', answer=[{'text': 'a', 'refs': ['p1', 'zz']},
                                                   {'text': 'b', 'refs': ['qq']}]), FACTS)
    assert len(got) == 2, got
    assert any(p.startswith("answer[0].refs: 'zz'") for p in got), got
    assert any(p.startswith("answer[1].refs: 'qq'") for p in got), got


def test_a_claim_cites_any_known_handle_because_citing_is_not_a_kind_test():
    assert brain.check(_ok(kind='question', answer=[
        {'text': 'a', 'refs': ['m1', 'k3', 'u2', 'g1', 'i1', 'p1']}]), FACTS) == []


# ── 6. what still counts as a stated objective or title ──────────────────────
# source: `blank`, intent.py:195-196, and the `t is None` guards at intent.py:217-220

@pytest.mark.parametrize('v', [None, '', '   ', '\t\n', 42, True, 0, [], {}],
                         ids=['none', 'empty', 'spaces', 'tabs', 'int', 'bool', 'zero', 'list',
                              'dict'])
def test_a_title_and_an_objective_said_with_nothing_are_both_refused(v):
    got = brain.check(_ok(title=v, objective=v), FACTS)
    assert sorted(got) == ['new_work has a title', 'new_work states its objective'], (v, got)


@pytest.mark.parametrize('kind', ['new_work', 'idea'])
def test_nothing_more_is_demanded_when_the_reading_names_the_idea_it_makes_work(kind):
    """The `t is None` guard: an idea handle IS the objective, so a reading that
    gives one must not be refused for repeating it in words."""
    assert brain.check(_ok(kind=kind, title=None, objective=None, target='i1'), FACTS) == []


def test_a_new_work_pointing_at_an_unknown_handle_is_told_only_that():
    """`t` is not None, so the objective and title clauses must stay shut: three
    problems for one mistake sends the reader retrying the wrong thing."""
    got = brain.check(_ok(title=None, objective=None, target='zz'), FACTS)
    assert len(got) == 1 and got[0].startswith("target: 'zz'"), got


def test_an_idea_whose_objective_is_only_whitespace_states_nothing():
    assert brain.check(_ok(kind='idea', objective=' \n '), FACTS) == ['idea states its objective']
    assert brain.check(_ok(kind='idea', objective='a digest'), FACTS) == []


# ── 7. the confidence scale, endpoints included ─────────────────────────────
# source: intent.py:238-240 (`not 0 <= c <= 1`)

@pytest.mark.parametrize('c', [None, 0, 1, 0.0, 1.0, 0.5],
                         ids=['none', 'int-zero', 'int-one', 'float-zero', 'float-one', 'half'])
def test_the_endpoints_of_the_confidence_scale_are_still_confidence(c):
    """`not 0 < c < 1` (mutation-checked: 4 of these fail) would refuse a reader
    that said 0 or 1 out loud, which is the difference between retrying a good
    answer and accepting a bad one."""
    assert brain.check(_ok(confidence=c), FACTS) == []


@pytest.mark.parametrize('c', [-0.0001, 1.0001, -1, 2, 1000],
                         ids=['under-zero', 'over-one', 'minus-one', 'two', 'thousand'])
def test_a_confidence_outside_the_scale_is_refused(c):
    assert brain.check(_ok(confidence=c), FACTS) == ['confidence is 0..1']


# ── 8. each mention is judged by its own kind, and a null handle is the norm ──
# source: intent.py:200-202 (the `lambda f, k=m['kind']` default) and `known`, 186-193

def test_mentions_are_judged_by_their_own_kind_not_the_last_ones():
    """Each mention is judged by ITS kind (the `k=m['kind']` default is what fixes
    it at call time). Dropping that kind test, or comparing against one fixed
    kind, makes both orders wrong: the first list gains a refusal, the second
    loses one. The exact message names the kind too, so a silent `project` for
    every mention does not pass either."""
    a = brain.check(_ok(mentions=[{'name': 'Atlas', 'kind': 'project', 'ref': 'p1'},
                                  {'name': 'Ada', 'kind': 'person', 'ref': 'm1'}]), FACTS)
    assert a == ["mentions[1].ref: 'm1' is not a person handle"], a
    b = brain.check(_ok(mentions=[{'name': 'Ada', 'kind': 'person', 'ref': 'p1'},
                                  {'name': 'Atlas', 'kind': 'project', 'ref': 'p1'}]), FACTS)
    assert b == ["mentions[0].ref: 'p1' is not a person handle"], b


def test_a_mention_the_context_cannot_answer_for_carries_no_handle_and_costs_nothing():
    """The named-but-unknown thing the PREFIX asks for: `ref` null, and `known`
    must return before saying anything about it."""
    assert brain.check(_ok(mentions=[{'name': 'Ada', 'kind': 'person', 'ref': None},
                                     {'name': 'the deploy box', 'kind': 'system', 'ref': None}]),
                       FACTS) == []


@pytest.mark.parametrize('m, bad', [({'name': 'Atlas', 'kind': 'project', 'ref': 'p9'}, 'p9'),
                                   ({'name': 'Atlas', 'kind': 'mission', 'ref': 'i1'}, 'i1')],
                         ids=['invented', 'wrong-kind'])
def test_a_mention_cannot_reach_an_object_the_package_never_gave(m, bad):
    got = brain.check(_ok(mentions=[m]), FACTS)
    assert len(got) == 1 and got[0].startswith('mentions[0].ref:') and bad in got[0], got


def test_an_absent_everything_is_not_a_problem_a_wrong_something_is():
    """Every optional handle null at once (the ambiguous reading that names
    nothing): `known(None)` must be silent, so the only problems left are none."""
    quiet = _ok(kind='idea', title=None, objective='a digest', project=None, target=None,
                mentions=None, conflicts=None, feedback=None, answer=None, confidence=None)
    assert brain.check(quiet, FACTS) == []
    quiet['project'] = 'm1'                      # and one wrong handle is exactly one problem
    assert brain.check(quiet, FACTS) == ["project: 'm1' is not a project handle"]


# ── 9. what `describe` says about an item is what `check` later judges ───────
# source: intent.py:113-149 (labels, facts, the projection before the cap)

@pytest.fixture
def db():
    d = Database.open()   # ARCHEUS_HOME is this test's own tmp_path (v1/conftest.py:34-40)
    yield d
    d.close()


def _put(db, *entities_):
    """Insert rows a phase would have written, as one writer command (the writer
    refuses a mutation with no event) — the helper of
    tests/v1/integration/test_graph_query.py:22."""
    def run(tx, **_):
        for x in entities_:
            tx.insert(x, actor=Ref('user_device', ids.new_id('principal')))
        tx.append(new_event('mission.updated', Ref('mission', ids.new_id('mission')),
                            Ref('user_device', ids.new_id('principal')), payload={},
                            workspace=WS))
    db.writer.execute(run, {})


def _describe(db, refs, homes=None, subject_id='none'):
    pkg = {'subject_id': subject_id, 'items': [
        {'ref': {'kind': k, 'id': i}, 'type': 'why-kind', 'reason': 'because'} for k, i in refs]}
    with db.read() as conn:
        return brain.describe(conn, pkg, homes if homes is not None else Homes())


def test_an_empty_knowledge_body_is_not_written_as_a_bare_dot(db):
    """intent.py:123's `if k.text else k.title`, plus the facts `check` judges a
    conflict against: a candidate DECISION from imported notes is challengeable,
    and the label must say it is not confirmed."""
    kid = ids.new_id('knowledge_item')
    _put(db, entities.KnowledgeItem(id=kid, workspace_id=WS, type='DECISION', title='Use tabs',
                                    text='', state='CANDIDATE', source_kind='import'))
    lines, facts = _describe(db, [(KN, kid)])
    assert lines == ['[k1] DECISION not confirmed (candidate): Use tabs']
    assert facts['k1'] == {'kind': KN, 'id': kid, 'type': 'why-kind', 'reason': 'because',
                           'state': 'CANDIDATE', 'ktype': 'DECISION', 'source_kind': 'import'}
    assert brain.check(_ok(project=None, conflicts=[{'ref': 'k1', 'why': 'it says so'}]),
                       facts) == []


def test_the_context_line_projects_the_home_before_it_caps_it(db, tmp_path):
    """intent.py:123 then :148. Cap first, and a raw prefix of the home survives
    the cut (the pattern no longer matches what was left of it) — which is the
    leak T-144 closed in the review prompt and this line still refuses."""
    home = str(tmp_path / 'Brain-Gap-Home')
    kid = ids.new_id('knowledge_item')
    _put(db, entities.KnowledgeItem(id=kid, workspace_id=WS, type='FACT', title='Note',
                                    text=home + '/settings.json ' + 'w' * 500, state='CONFIRMED'))
    lines, _f = _describe(db, [(KN, kid)],
                          homes=Homes(registered_homes=[home], shorts=lambda p: None))
    assert lines == ['[k1] FACT CONFIRMED: '
                     + ('Note. ' + REPLACEMENT + '/settings.json ' + 'w' * 500)[:400]]
    assert 'Brain-Gap-Home' not in lines[0] and home not in lines[0]


def test_the_context_line_collapses_what_a_writer_left_behind_before_the_cap(db):
    kid = ids.new_id('knowledge_item')
    _put(db, entities.KnowledgeItem(id=kid, workspace_id=WS, type='FACT', title='Note',
                                    text='one\n\t two   three   ', state='CONFIRMED'))
    lines, _f = _describe(db, [(KN, kid)])
    assert lines == ['[k1] FACT CONFIRMED: Note. one two three']


def test_every_kind_is_described_by_what_the_checks_then_judge_it_on(db, tmp_path):
    """One line per branch of the `if kind == ...` ladder: the mission's state
    (`_live_mission`), the idea's title-else-text, the meeting's date-else-undated,
    the project's name raw with its roots projected, the user turn as typed."""
    home = str(tmp_path / 'Brain-Gap-Project')
    mid, iid, iid2 = ids.new_id('mission'), ids.new_id('idea'), ids.new_id('idea')
    gid, gid2, pid = ids.new_id('meeting'), ids.new_id('meeting'), ids.new_id('project')
    _put(db, entities.Mission(id=mid, workspace_id=WS, title='Ship it',
                              objective='Finish the card', state='EXECUTING'),
         entities.Idea(id=iid, workspace_id=WS, text='ignored when titled', title='A digest',
                       state='CAPTURED'),
         entities.Idea(id=iid2, workspace_id=WS, text='a thought with no title', state='CAPTURED'),
         entities.Meeting(id=gid, workspace_id=WS, name='Weekly sync'),
         entities.Meeting(id=gid2, workspace_id=WS, name='Board', held_at='2026-10-02'),
         entities.Project(id=pid, workspace_id=WS, name='Atlas ' + home,
                          root_paths=(home + '/repo', home + '/docs')))
    homes = Homes(registered_homes=[home], shorts=lambda p: None)
    lines, facts = _describe(db, [('mission', mid), ('idea', iid), ('idea', iid2),
                                  ('meeting', gid), ('meeting', gid2), ('project', pid)],
                             homes=homes)
    assert lines == ['[m1] mission EXECUTING: Ship it: Finish the card',
                     '[i1] idea CAPTURED: A digest',
                     '[i2] idea CAPTURED: a thought with no title',
                     '[g1] meeting: Weekly sync, undated',
                     '[g2] meeting: Board, 2026-10-02',
                     '[p1] project: Atlas ' + home + ' (' + REPLACEMENT + '/repo, '
                     + REPLACEMENT + '/docs)']
    assert facts['m1']['state'] == 'EXECUTING'              # what `_live_mission` reads
    assert facts['i1']['state'] == 'CAPTURED' and 'ktype' not in facts['i1']
    assert set(facts['g1']) == {'kind', 'id', 'type', 'reason'}   # a meeting decides nothing
    assert brain.check({'kind': 'continue_work', 'target': 'm1'}, facts) == []


def test_a_user_turn_is_known_by_what_its_reply_produced(db):
    """intent.py:139-141: the cards of the reply are merged into the user turn's
    facts, and that is the only way `supersedes` can name an item through the
    earlier message that stated the preference."""
    conv, um, am = (ids.new_id('conversation'), ids.new_id('message'), ids.new_id('message'))
    kid = ids.new_id('knowledge_item')
    _put(db, entities.Conversation(id=conv, kind='primary'),
         entities.Message(id=um, conversation_id=conv, author='user', text='tabs, never spaces'),
         entities.Message(id=am, conversation_id=conv, author='archeus', in_reply_to=um,
                          text='noted', cards=(_kn_card(kid),)))
    lines, facts = _describe(db, [('message', um)])
    assert lines == ['[u1] earlier user turn: tabs, never spaces']
    assert facts['u1']['author'] == 'user' and facts['u1']['cards'] == [dict(_kn_card(kid))]
    assert brain.superseded(facts['u1']) == kid
    assert brain.check(_ok(project=None, kind='preference',
                          feedback={'signal': 'correction', 'title': 't',
                                    'supersedes': 'u1'}), facts) == []


def test_the_subject_and_the_kindless_kinds_get_no_handle_and_no_number():
    """intent.py:99-101: an item with no letter, and the item the package is
    about, are skipped WITHOUT consuming a number, so the handles the model is
    given stay the ones `check` will recognise."""
    pkg = {'subject_id': 'msg_0', 'items': [
        {'ref': {'kind': 'message', 'id': 'msg_0'}},
        {'ref': {'kind': 'repository', 'id': 'rep_1'}},
        {'ref': {'kind': 'project', 'id': 'prj_1'}},
        {'ref': {'kind': 'person', 'id': 'someone'}},
        {'ref': {'kind': 'system', 'id': 'the box'}},
        {'ref': {'kind': 'project', 'id': 'prj_2'}},
        {'ref': {'kind': 'knowledge_item', 'id': 'kno_1'}},
        {'ref': {'kind': 'meeting', 'id': 'mtg_1'}}]}
    assert [h for h, _r in brain.handles(pkg)] == ['p1', 'p2', 'k1', 'g1']
    # and the subject keeps a handle the moment it is not the subject
    pkg['subject_id'] = 'msg_9'
    assert [h for h, _r in brain.handles(pkg)][0] == 'u1'


# ── 10. `prompt`: the question it answers, or the fact that there is nothing ─
# source: intent.py:152-156

@pytest.mark.parametrize('answering', [None, ''], ids=['none', 'blank-question'])
def test_the_prompt_only_offers_an_answer_frame_when_there_is_a_question(answering):
    text = brain.prompt('what about the tests?', ['[p1] project: Atlas'], answering=answering)
    assert 'This message answers' not in text
    assert text.endswith('The message:\nwhat about the tests?')
    assert '[p1] project: Atlas' in text


def test_the_question_being_answered_sits_above_the_message_and_below_the_context():
    text = brain.prompt('It is on Friday.', ['[g1] meeting: Board, 2026-10-02'],
                        answering='When is the release?')
    assert (text.index('[g1] meeting: Board, 2026-10-02')
            < text.index("This message answers Archeus's question: When is the release?")
            < text.index('The message:\nIt is on Friday.'))


@pytest.mark.parametrize('lines', [None, []], ids=['none', 'empty'])
def test_a_package_with_nothing_in_it_says_so_rather_than_nothing(lines):
    text = brain.prompt('hello there', lines)
    assert '(nothing relevant is recorded)' in text.split('The message:')[0]


# ── 11. `resolve` replaces handles, and never invents an object for one ─────
# source: intent.py:251-266

def test_resolve_carries_the_conflict_state_the_challenge_is_built_on():
    p = brain.resolve(_ok(conflicts=[{'ref': 'k2', 'why': 'it says so'}]), FACTS)
    assert p['conflicts'] == [{'ref': {'kind': KN, 'id': 'kno_2'}, 'state': 'CANDIDATE',
                               'why': 'it says so'}]


def test_resolve_turns_the_answers_it_did_not_get_into_empty_lists():
    parsed = _ok(kind='question', mentions=None, conflicts=None, requirements=None,
                 constraints=None, ambiguities=None, answer=None, target=None, project=None)
    p = brain.resolve(parsed, FACTS)
    for k in ('requirements', 'constraints', 'ambiguities', 'mentions', 'conflicts', 'answer'):
        assert p[k] == [], k
    assert p['target'] is None and p['project'] is None
    reqs = [{'text': 'r', 'origin': 'explicit'}]
    p = brain.resolve(_ok(requirements=reqs), FACTS)
    assert p['requirements'] == reqs and p['requirements'] is not reqs


def test_resolve_rewrites_the_reading_it_was_given_into_a_copy():
    """Core stores the result as the Intent's proposal; the reading the caller
    validated (and retries) must survive untouched."""
    parsed = _ok(mentions=[{'name': 'Atlas', 'kind': 'project', 'ref': 'p1'}],
                 conflicts=[{'ref': 'k2', 'why': 'w'}], target='i1',
                 feedback={'signal': 'correction', 'title': 't', 'supersedes': 'u3'},
                 answer=[{'text': 'a', 'refs': ['p1']}],
                 requirements=[{'text': 'r', 'origin': 'explicit'}])
    before = copy.deepcopy(parsed)
    p = brain.resolve(parsed, FACTS)
    assert parsed == before
    assert (p['feedback'] is not parsed['feedback']
            and p['answer'][0] is not parsed['answer'][0]
            and p['mentions'][0] is not parsed['mentions'][0])
    p['feedback']['title'] = 'changed'
    p['answer'][0]['text'] = 'changed'
    p['mentions'][0]['name'] = 'changed'
    p['target'] = 'changed'
    assert parsed == before


def test_resolve_names_the_item_behind_a_supersession_and_leaves_the_rest_alone():
    p = brain.resolve(_ok(kind='preference', feedback={'signal': 'correction', 'title': 't',
                                                       'promote': 'PREFERENCE',
                                                       'supersedes': 'u3'}), FACTS)
    assert p['feedback'] == {'signal': 'correction', 'title': 't', 'promote': 'PREFERENCE',
                             'supersedes': 'kno_12'}
    p = brain.resolve(_ok(kind='feedback', target='u2', feedback={'signal': 'positive'}), FACTS)
    assert p['feedback'] == {'signal': 'positive', 'supersedes': None}
    assert p['target'] == {'kind': 'message', 'id': 'msg_2'}
    p = brain.resolve(_ok(kind='preference', feedback={'signal': 'correction', 'title': 't',
                                                       'supersedes': 'k6'}), FACTS)
    assert p['feedback']['supersedes'] == 'kno_6'          # a preference names itself


def test_resolve_resolves_everywhere_a_handle_can_sit():
    p = brain.resolve(_ok(kind='question', project='p1', target=None,
                          mentions=[{'name': 'Atlas', 'kind': 'project', 'ref': 'p1'}],
                          answer=[{'text': 'a', 'refs': ['p1', 'g1']}]), FACTS)
    assert p['project'] == {'kind': 'project', 'id': 'prj_1'}
    assert p['mentions'][0]['ref'] == {'kind': 'project', 'id': 'prj_1'}
    assert p['mentions'][0]['name'] == 'Atlas' and p['mentions'][0]['kind'] == 'project'
    assert p['answer'] == [{'text': 'a', 'refs': [{'kind': 'project', 'id': 'prj_1'},
                                                   {'kind': 'meeting', 'id': 'mtg_1'}]}]


@pytest.mark.parametrize('parsed', [
    _ok(target='zz'), _ok(project='zz'),
    _ok(mentions=[{'name': 'Atlas', 'kind': 'project', 'ref': 'zz'}]),
    _ok(conflicts=[{'ref': 'zz', 'why': 'w'}]),
    _ok(kind='preference', feedback={'signal': 'correction', 'title': 't', 'supersedes': 'zz'}),
    _ok(kind='question', answer=[{'text': 'a', 'refs': ['zz']}])],
    ids=['target', 'project', 'mention', 'conflict', 'supersedes', 'answer-ref'])
def test_resolve_refuses_to_invent_an_object_for_a_handle_no_package_gave(parsed):
    """`check` is the gate and `resolve` is the last line: an unknown handle is
    an error here, never a `{kind, id}` Core would apply to nothing."""
    with pytest.raises(KeyError):
        brain.resolve(parsed, FACTS)


# ── 12. the classification's own edges: the schema the answer must fit ──────
# source: intent.py:31-73 (SCHEMA) through shapes.validate

def _doc(**kw):
    return dict({'kind': 'new_work'}, **kw)


@pytest.mark.parametrize('kind', list(brain.KINDS), ids=list(brain.KINDS))
def test_a_reading_is_exactly_one_of_the_six_kinds_and_kind_is_all_it_must_have(kind):
    shapes.validate({'kind': kind}, brain.SCHEMA)
    for bad in ({}, {'kind': 'task'}, {'kind': 'question '}, {'kind': None}, {'kind': 4},
                {'title': 't'}, _doc(tasks=[])):
        with pytest.raises(shapes.Invalid):
            shapes.validate(bad, brain.SCHEMA)


@pytest.mark.parametrize('amb', [
    [{'question': 'which one?', 'material': True}], [{'question': 'which one?',
                                                       'material': False}],
    [{'question': 'q' * 300, 'material': False}]],
    ids=['material', 'not-material', 'longest-question'])
def test_an_ambiguity_is_a_question_and_a_real_bool(amb):
    """`material` gates whether Core asks; `1` and `'true'` are not True here."""
    shapes.validate(_doc(ambiguities=amb), brain.SCHEMA)


@pytest.mark.parametrize('amb', [
    [{}], [{'question': 'q'}], [{'material': True}], [{'question': 'q', 'material': 1}],
    [{'question': 'q', 'material': 'true'}], [{'question': 'q', 'material': None}],
    [{'question': 'q', 'material': True, 'extra': 1}], [{'question': 'q' * 301,
                                                          'material': False}]],
    ids=['no-fields', 'no-question', 'no-material', 'int-true', 'string-true', 'null',
         'extra-key', 'question-too-long'])
def test_an_ambiguity_that_is_not_a_question_and_a_bool_is_not_an_ambiguity(amb):
    with pytest.raises(shapes.Invalid):
        shapes.validate(_doc(ambiguities=amb), brain.SCHEMA)


def test_the_lists_core_reads_are_capped_at_what_core_will_read():
    """One item over each cap is a rejection, at the cap is not."""
    item = {'question': 'q', 'material': False}
    shapes.validate(_doc(ambiguities=[dict(item) for _ in range(10)]), brain.SCHEMA)
    with pytest.raises(shapes.Invalid):
        shapes.validate(_doc(ambiguities=[dict(item) for _ in range(11)]), brain.SCHEMA)
    mention = {'name': 'Ada', 'kind': 'person'}
    shapes.validate(_doc(mentions=[dict(mention) for _ in range(20)]), brain.SCHEMA)
    with pytest.raises(shapes.Invalid):
        shapes.validate(_doc(mentions=[dict(mention) for _ in range(21)]), brain.SCHEMA)
    claim = {'text': 'a', 'refs': ['p1']}
    shapes.validate(_doc(kind='question', answer=[dict(claim) for _ in range(20)]), brain.SCHEMA)
    with pytest.raises(shapes.Invalid):
        shapes.validate(_doc(kind='question', answer=[dict(claim) for _ in range(21)]),
                        brain.SCHEMA)


@pytest.mark.parametrize('handle', ['m' + '1' * 11, 'k1', None], ids=['twelve-chars', 'short',
                                                                       'null'])
def test_a_handle_is_a_short_string_or_nothing_at_all(handle):
    shapes.validate(_doc(target=handle, project=handle), brain.SCHEMA)
    for bad in ('m' * 13, 12, True, [], {'kind': 'mission'}):
        with pytest.raises(shapes.Invalid):
            shapes.validate(_doc(target=bad), brain.SCHEMA)


@pytest.mark.parametrize('c', [True, False, 'high', [], {}], ids=['true', 'false', 'string',
                                                                   'list', 'dict'])
def test_a_confidence_is_a_number_or_null_never_a_bool(c):
    """`isinstance(True, int)` is why shapes excludes bool from number; check
    cannot see the difference (0 <= True <= 1), so the schema has to."""
    with pytest.raises(shapes.Invalid):
        shapes.validate(_doc(confidence=c), brain.SCHEMA)


@pytest.mark.parametrize('fb', [
    {}, {'signal': 'mixed'}, {'signal': 'POSITIVE'}, {'signal': True}, {'promote': 'RULE'},
    {'signal': 'positive', 'supersedes': 5}], ids=lambda x: 'empty' if not x else 'bad-field')
def test_feedback_is_a_signal_from_three_and_nothing_else(fb):
    with pytest.raises(shapes.Invalid):
        shapes.validate(_doc(kind='feedback', feedback=fb), brain.SCHEMA)
    shapes.validate(_doc(kind='feedback', feedback={'signal': 'negative', 'title': None,
                                                    'promote': None, 'supersedes': None}),
                    brain.SCHEMA)


def test_a_claim_must_cite_even_when_it_cites_nothing():
    """The schema guarantees the `c['refs']` `check` reaches for directly; the
    empty list it allows is what `check` then refuses."""
    shapes.validate(_doc(kind='question', answer=[{'text': 'a', 'refs': []}]), brain.SCHEMA)
    for bad in ([{'text': 'a'}], [{'text': 'a', 'refs': None}], [{'refs': []}],
                [{'text': 'a', 'refs': 'p1'}], [{'text': 'a', 'refs': ['p' * 13]}]):
        with pytest.raises(shapes.Invalid):
            shapes.validate(_doc(kind='question', answer=bad), brain.SCHEMA)


def test_an_item_or_a_name_longer_than_the_surface_can_show_is_refused():
    shapes.validate(_doc(objective='o' * 1000, title='t' * 120, desired_outcome='d' * 500,
                         requirements=[{'text': 'r' * 500, 'origin': 'inferred'}]), brain.SCHEMA)
    for kw in ({'objective': 'o' * 1001}, {'title': 't' * 121}, {'desired_outcome': 'd' * 501},
              {'requirements': [{'text': 'r' * 501, 'origin': 'explicit'}]},
              {'requirements': [{'text': 'r', 'origin': 'guessed'}]},
              {'requirements': [{'text': 'r'}]},
              {'mentions': [{'name': 'n' * 201, 'kind': 'person'}]},
              {'conflicts': [{'ref': 'k1'}]}):
        with pytest.raises(shapes.Invalid):
            shapes.validate(_doc(**kw), brain.SCHEMA)

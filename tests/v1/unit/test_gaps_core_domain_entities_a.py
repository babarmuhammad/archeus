"""T-700: the highest-risk uncovered branches of archeus/core/domain/entities.py 1-960.

Fail-closed and denial paths first, then boundary values, then error paths: the
secondary (merge-back) machine of a Task, the words and shapes the plan gate and
the mission guards read (`held_from`, success criteria, requirements,
`planning_blocked`, `decided_plan_version`, resource preferences and their
directives, `origin_ref`), the knowledge body cap and the constraint gate, the
typed references a card, a link and a task ref carry, the counters that must
never be a bool, and the immutable provenance of a Plan version.

Construction-time only: no I/O, no clock, no OS, no network. Same style and
fixture shape as tests/v1/unit/test_domain.py (whose `_sample` builds the
smallest valid row of each class, so only the branches nothing reaches are
opened here) and tests/v1/unit/test_gaps_core_domain_guards.py. Where a branch
is already exercised elsewhere the docstring says so and does not repeat it.

Two cases are `xfail(strict=True)` because the SOURCE is wrong, not the test;
both are named in /work/QWEN-DONE-T-700.md.
"""

import pytest

from archeus.core.domain import entities as E, ids, states, values
from archeus.core.domain.values import ORIGINS

i = ids.new_id
WS = ids.GLOBAL_WORKSPACE
HEX64 = 'a' * 64


def _mission(**kw):
    return E.Mission(id=kw.pop('id', i('mission')), workspace_id=WS, title='T',
                     objective='O', **kw)


def _plan(**kw):
    return E.Plan(id=kw.pop('id', i('plan')), mission_id=kw.pop('mission_id', i('mission')),
                  **kw)


def _task(**kw):
    return E.Task(id=kw.pop('id', i('task')), plan_id=kw.pop('plan_id', i('plan')),
                  mission_id=kw.pop('mission_id', i('mission')), key=kw.pop('key', 't1'),
                  title=kw.pop('title', 'do'), kind=kw.pop('kind', 'code_change'), **kw)


def _conversation(**kw):
    return E.Conversation(id=kw.pop('id', i('conversation')), **kw)


def _message(**kw):
    return E.Message(id=kw.pop('id', i('message')),
                     conversation_id=kw.pop('conversation_id', i('conversation')),
                     author='user', **kw)


def _knowledge(**kw):
    return E.KnowledgeItem(id=kw.pop('id', i('knowledge_item')), workspace_id=WS,
                           type=kw.pop('type', 'LESSON'), title='t', **kw)


# ── the secondary machine: a state column, never an ordinary one ─────────────
#
# Tx.transition writes a machine through machine_field, and Tx.update refuses
# every name in state_fields() (infra/db/writer.py:186, 247, 282), so a Task's
# merge-back state is reachable only along the guarded `task_verified` edges of
# state-machines section 13.

def test_the_merge_back_machine_is_a_state_field_of_the_task():
    """entities.py:63-67 + 70-73: machine_field names the column a transition
    writes and state_fields is the set an ordinary update may not touch. Drop
    Task._MACHINES (entities.py:895) and a plain Tx.update(fields=...) could set
    integration_state='MERGED' with no verified revision and no `task_verified`
    proof -- merging work that was never checked -- because writer.py would find
    nothing to refuse."""
    assert E.Task.machine_field() == ('state', 'task')
    assert E.Task.machine_field('integration') == ('integration_state', 'integration')
    assert E.Task.state_fields() == {'state', 'integration_state'}
    # a secondary machine is not in _FROZEN either: state_fields, not _FROZEN, is
    # what keeps an ordinary write away from it
    assert 'integration_state' not in E.Task.frozen_fields()


@pytest.mark.parametrize('state', list(states.states('integration')),
                         ids=['pending', 'merging', 'merged', 'conflict', 'abandoned'])
def test_every_state_of_the_integration_machine_builds(state):
    """entities.py:106-108, the admit side (the refuse side is the next test):
    every state of the machine is storable, so a row in any real state can be read
    back and stepped along its edges again."""
    assert _task(integration_state=state).integration_state == state


@pytest.mark.parametrize('state', [None, 'MERGE_ME', 'merged', 'PENDING ', 'SUCCEEDED',
                                   'CREATED', 'ABANDON'],
                         ids=['none', 'invented', 'lowercase', 'trailing-space', 'task-state',
                              'mission-state', 'typo'])
def test_an_illegal_integration_state_is_refused(state):
    """entities.py:106-108: `(None,) + states.states(machine)` is the whole allow
    list of the secondary machine, and it is read from `self._MACHINES`, not from
    `_STATE` -- which is why `SUCCEEDED` (a task state) and `CREATED` (a mission
    state) are refused while `None`, the not-yet-merged worktree row, is legal.
    Validate this column against the task machine, or drop the loop, and all of
    them are stored."""
    if state is None:
        assert _task(integration_state=None).integration_state is None
    else:
        with pytest.raises(ValueError, match='integration_state is not a integration state'):
            _task(integration_state=state)


# ── Mission: the words the plan gate and the hold/resume guards read ─────────

@pytest.mark.parametrize('held_from, ok', [
    ('EXECUTING', True), ('PAUSED', True),
    ('executing', False),                     # the machine's words are exact
    ('LEARNED', False),                       # a state of the IDEA machine
    ('', False), ('TELEPORTING', False),
], ids=['executing', 'paused', 'lowercase', 'idea-state', 'empty', 'invented'])
def test_a_missions_held_from_is_a_real_mission_state(held_from, ok):
    """entities.py:766-767: `resume` and `redispatch` read held_from as the state
    to go back to (current state, never the event log, which retention may prune:
    the comment at entities.py:710-713). A value from another machine is a mission
    that resumes into a state it was never in; dropping the check stores anything."""
    if ok:
        assert _mission(held_from=held_from).held_from == held_from
    else:
        with pytest.raises(ValueError, match='held_from is not a mission state'):
            _mission(held_from=held_from)


@pytest.mark.parametrize('criteria, ok', [
    (({'text': 'tests pass', 'check': 'automatic'},), True),
    (({'text': 'looks right', 'check': 'human', 'origin': 'explicit'},), True),
    (({'text': 'looks right', 'check': 'human', 'origin': 'inferred'},), True),
    (({'text': 'x', 'check': 'robot'},), False),                # neither word
    (({'text': 'x'},), False),                                  # no check at all
    (({'text': '  ', 'check': 'human'},), False),               # an empty promise
    (({'text': 'x', 'check': 'human', 'origin': 'maybe'},), False),
    (({'text': 'x', 'check': 'human', 'when': 'later'},), False),        # not its keys
    (('tests pass',), False),                                   # not even a dict
], ids=['automatic', 'human-explicit', 'human-inferred', 'bad-check', 'no-check',
        'blank-text', 'bad-origin', 'extra-key', 'not-a-dict'])
def test_a_success_criterion_is_text_check_and_an_optional_origin(criteria, ok):
    """entities.py:771-777: the `verified`, `awaiting_human_acceptance` and
    `verification_failed` guards branch on `check` and on `origin`
    (core/domain/guards.py:200-216). A criterion whose check is neither word is
    judged by nothing, and the mission still reaches REVIEWING as if it had been;
    `origin` defaults to 'explicit' (the user asked) and admits nothing else."""
    if ok:
        assert len(_mission(success_criteria=criteria).success_criteria) == 1
    else:
        with pytest.raises(ValueError, match='a success criterion is'):
            _mission(success_criteria=criteria)


@pytest.mark.parametrize('reqs, ok', [
    (({'text': 'no new dependency', 'origin': 'explicit'},), True),
    (({'text': 'stays offline', 'origin': 'inferred'},), True),
    (({'text': 'x', 'origin': 'explicit',
       'source_ref': {'kind': 'message', 'id': i('message')}},), True),
    (({'text': 'x'},), False),                       # origin is NOT defaulted here
    (({'text': 'x', 'origin': 'maybe'},), False),
    (({'text': '  ', 'origin': 'explicit'},), False),
    (({'text': 'x', 'origin': 'explicit', 'who': 'ada'},), False),
], ids=['explicit', 'inferred', 'source-ref', 'no-origin', 'bad-origin', 'blank',
        'extra-key'])
def test_a_requirement_or_constraint_names_its_origin(reqs, ok):
    """entities.py:778-783: unlike a success criterion, a requirement has no
    default origin -- P7 keeps what the user asked apart from what Archeus
    inferred, and the plan's coverage report reads against it (`Plan.coverage`,
    entities.py:835). Defaulting or inverting that comparison turns an invented
    wish into the user's own word, which the plan gate then holds the mission to."""
    if ok:
        assert len(_mission(requirements=reqs).requirements) == 1
    else:
        with pytest.raises(ValueError, match='a requirement or constraint is'):
            _mission(requirements=reqs)


def _directive(key, ident, **kw):
    d = {'key': key, 'id': ident, 'message_id': kw.pop('message_id', i('message')),
         'intent_id': kw.pop('intent_id', i('intent'))}
    d.update(kw)
    return d


GOOD_RP = {'preferred_accounts': ['acc_x'], 'forbidden_harnesses': ['claude_code'],
           'max_cost_band': 'low', 'since': '2026-10-01T10:00:00Z'}


@pytest.mark.parametrize('rp, why', [
    (dict(GOOD_RP), None),
    (dict(GOOD_RP, max_cost_band=None), None),                    # the ceiling absent
    (dict(GOOD_RP, colour='red'), 'holds only'),
    (dict(GOOD_RP, max_cost_band='epic'), 'max_cost_band is one of'),
    (dict(GOOD_RP, preferred_accounts=[1]), 'is a list of ids'),
    (dict(GOOD_RP, preferred_accounts=['']), 'is a list of ids'),         # an empty id
    (dict(GOOD_RP, forbidden_harnesses='claude_code'), 'is a list of ids'),   # not a list
    (dict(GOOD_RP, forbidden_accounts=('acc_y',)), None),          # a tuple is as good
    ('preferred_accounts', 'holds only'),                          # not a dict at all
], ids=['good', 'no-band', 'unknown-key', 'bad-band', 'not-a-str', 'empty-id', 'not-a-list',
        'tuple', 'not-a-dict'])
def test_resource_preferences_holds_only_the_known_keys(rp, why):
    """entities.py:744-755: `forbidden_accounts` is a routing refusal and
    `max_cost_band` is the auto-approve ceiling (resource-router section 3 and
    10 D). A key Core does not know, or a list entry that is not a non-empty
    string, must not reach a row: the router would obey a preference nobody set,
    and an empty string in `forbidden_accounts` matches no account while reading
    as a refusal."""
    if why is None:
        assert _mission(resource_preferences=rp).resource_preferences == rp
    else:
        with pytest.raises(ValueError, match=why):
            _mission(resource_preferences=rp)


@pytest.mark.parametrize('rp, why', [
    ({'preferred_accounts': ['acc_x'],
      'directives': [_directive('preferred_accounts', 'acc_x')]}, None),
    ({'preferred_accounts': ['acc_x'],
      'directives': [_directive('preferred_accounts', 'acc_other')]}, 'a directive is'),
    ({'preferred_accounts': ['acc_x'],
      'directives': [_directive('max_cost_band', 'acc_x')]}, 'a directive is'),
    ({'directives': [_directive('preferred_accounts', 'acc_x')]}, 'a directive is'),
    ({'preferred_accounts': ['acc_x'],
      'directives': [_directive('preferred_accounts', 'acc_x', added='today')]},
     'a directive is'),
    ({'preferred_accounts': ['acc_x'],
      'directives': [_directive('preferred_accounts', 'acc_x, acc_y')]}, 'a directive is'),
    ({'preferred_accounts': ['acc_x'], 'directives': ['acc_x']}, 'a directive is'),
    ({'preferred_accounts': ['acc_x'], 'directives': None}, None),
    ({'preferred_accounts': ['acc_x'], 'directives': ()}, None),
], ids=['good', 'id-not-in-list', 'key-not-a-list', 'no-list', 'extra-key', 'joined-ids',
        'not-a-dict', 'none', 'empty'])
def test_a_directive_names_an_id_that_is_really_in_the_list_it_edits(rp, why):
    """entities.py:756-761 (ADR-0042 section 3): a directive is the audit trail of
    a standing user instruction, so it must name one of the four lists, an id that
    list really holds, and the message and intent that added it. Drop
    `d['id'] in rp.get(d['key'], ())` and a recorded directive can claim the user
    forbade an account Core never forbade -- the mission thread renders it as the
    user's word."""
    if why is None:
        assert _mission(resource_preferences=rp).resource_preferences == rp
    else:
        with pytest.raises(ValueError, match='a directive is'):
            _mission(resource_preferences=rp)


@pytest.mark.parametrize('block, ok', [
    ({'kind': 'policy', 'round_seq': 2}, True),
    ({'kind': 'clarification'}, True), ({'kind': 'challenge'}, True), ({'kind': 'call'}, True),
    ({'kind': 'nope'}, False),
    ({'round_seq': 2}, False),                     # no kind at all
    ({'kind': 'POLICY'}, False),                   # the words are lower case
    ('policy', False),
], ids=['policy', 'clarification', 'challenge', 'call', 'unknown', 'no-kind', 'upper',
        'not-a-dict'])
def test_planning_blocked_is_a_known_block(block, ok):
    """entities.py:762-765: a `policy` block is a DENY and the other three are a
    question of meaning (p8-design-gate section 10, p9-design-gate D11), and the
    surface decides which of them to offer on `b.get('kind')`. `.get` defaults to
    None, which is not one of PLANNING_BLOCKS either: the refuse side is the only
    safe side, because a block nobody recognises is a mission stuck in PLANNING
    with nothing for the user to answer."""
    if ok:
        assert _mission(planning_blocked=block).planning_blocked == block
    else:
        with pytest.raises(ValueError, match='planning_blocked is'):
            _mission(planning_blocked=block)


@pytest.mark.parametrize('v, ok', [
    (1, True), (7, True), (None, True),
    (0, False), (True, False), ('2', False), (1.0, False), (-1, False),
], ids=['one', 'seven', 'none', 'zero', 'true', 'string', 'float', 'negative'])
def test_decided_plan_version_is_a_plan_version_or_nothing(v, ok):
    """entities.py:768-770: the plan gate never decides the same plan twice, so
    this number is what stops a REPLANNING round re-using an approval -- `True` is
    the bool the declarative _MIN1 fields refuse (entities.py:128-132) and `1.0`
    the equal float, both of which compare equal to plan_version 1 and would let a
    second version be decided by the first approval."""
    if ok:
        assert _mission(decided_plan_version=v).decided_plan_version == v
    else:
        with pytest.raises(ValueError, match='decided_plan_version is a plan_version'):
            _mission(decided_plan_version=v)


@pytest.mark.parametrize('origin, kind', [
    ('conversation', 'idea'), ('idea', 'message'), ('automation', 'message'),
], ids=['conversation-carries-an-idea', 'idea-carries-a-message', 'automation-carries-a-msg'])
@pytest.mark.xfail(strict=True, reason='SOURCE BUG: entities.py:690-691 admits any of '
                                       'message|idea|automation_run for EVERY origin. '
                                       'ORIGIN_REF_KIND (entities.py:677-679) is declared, '
                                       'documented at entities.py:697-699 and read by the '
                                       'graph (infra/graph/graph.py:146-147), but '
                                       'Mission._check never compares origin_ref to it')
def test_an_origin_ref_is_the_id_kind_its_origin_names(origin, kind):
    """entities.py:677-679 + 691: a mission that came from a conversation
    cannot have started from an idea. graph.py emits the `started_from` edge as
    `ORIGIN_REF_KIND[origin]` whatever the id really is, so a mismatched pair
    silently points the provenance edge at the wrong object -- and
    tests/v1/integration/test_graph_query.py:198-200 asserts exactly that parity
    for rows the application wrote, which is the only reason it holds today."""
    with pytest.raises(ValueError, match='origin_ref'):
        _mission(origin=origin, origin_ref=i(kind))


@pytest.mark.parametrize('ref', ['msg_bad', 'msn_' + '0' * 26, i('task'), WS],
                         ids=['malformed', 'wrong-ulid-space', 'a-task-id', 'a-workspace'])
def test_an_origin_ref_is_still_a_wellformed_id_of_a_known_family(ref):
    """entities.py:120-127 (the `any(ids.is_id(v, k) for k in kinds)` loop): a task
    id is not a message, idea or automation run, and `ws_global` is none of them
    either -- the `_REFS` allow list at entities.py:690-692 is a set of kinds, not
    a prefix check."""
    with pytest.raises(ValueError, match='origin_ref is not a'):
        _mission(origin_ref=ref)


@pytest.mark.parametrize('mids, ok', [
    ((i('mission'),), True),
    ((i('mission'), i('mission')), True),
    ((), False),                                # a Pause all that paused nothing
    (('msn_bad',), False),
    ((i('task'),), False),                      # not a mission
    ((i('mission'), 'msn_bad'), False),          # one bad row poisons the batch
], ids=['one', 'two', 'empty', 'malformed', 'a-task', 'second-bad'])
def test_a_pause_batch_names_the_missions_it_paused(mids, ok):
    """entities.py:796-800: Resume all resumes exactly the missions still PAUSED by
    the newest batch (P19.5), matched through `Mission.pause_batch_id`. An empty
    batch is a Pause all that reports success while every mission stays PAUSED; an
    id of another kind is never found, so it silently drops out of the resume list
    and that task keeps running."""
    if ok:
        assert E.PauseBatch(id=i('pause_batch'), mission_ids=mids).mission_ids == mids
    else:
        with pytest.raises(ValueError, match='a pause batch names the missions'):
            E.PauseBatch(id=i('pause_batch'), mission_ids=mids)


def _user(**kw):
    return E.User(id=kw.pop('id', i('user')),
                  display_name=kw.pop('display_name', 'Ada'), **kw)


def _inspection(**kw):
    return E.RepositoryInspection(id=kw.pop('id', i('repository_inspection')),
                                  repository_id=kw.pop('repository_id', i('repository')),
                                  extractor_version=kw.pop('extractor_version', 1), **kw)


def _intent(**kw):
    return E.Intent(id=kw.pop('id', i('intent')),
                    message_id=kw.pop('message_id', i('message')),
                    utterance=kw.pop('utterance', 'ship it'),
                    kind=kw.pop('kind', 'new_work'), **kw)


# ── knowledge: the body cap, and the constraint no LESSON may carry ──────────

@pytest.mark.parametrize('text, ok', [
    ('x' * 2048, True),
    ('\u00e9' * 1024, True),                       # 2048 bytes in UTF-8
    ('x' * 2049, False),
    ('\u00e9' * 1025, False),                      # 2050 bytes, 1025 characters
    ('x' * 3000, False),
], ids=['2048-ascii', '2048-utf8', '2049-ascii', '2050-utf8', '3000'])
def test_a_knowledge_body_over_the_cap_is_an_artifact_not_a_row(text, ok):
    """entities.py:466-468 (BODY_MAX_BYTES, entities.py:424): the cap is on
    ENCODED bytes, not characters -- the second pair is the boundary a `len(text)`
    would wave through, storing a row the store may not hold. Nothing in
    tests/v1 reaches the message: test_domain.py's invalid case for this class
    sets `body=`, which is not a field, so it dies in `from_dict`
    (entities.py:145-148) and never builds the row."""
    if ok:
        assert _knowledge(text=text).text == text
    else:
        with pytest.raises(ValueError, match='knowledge text is over'):
            _knowledge(text=text)


@pytest.mark.parametrize('type_, ok', [
    ('ARCHITECTURE', True), ('DECISION', True),
    ('LESSON', False), ('FACT', False), ('STANDARD', False), ('PREFERENCE', False),
], ids=['architecture', 'decision', 'lesson', 'fact', 'standard', 'preference'])
def test_only_an_architecture_or_decision_item_carries_a_constraint(type_, ok):
    """entities.py:469-471: a constraint is evaluated by knowledge/drift and its
    verdict gates an `architecture` move (core/domain/guards.py:330-343). A LESSON
    or FACT carrying one is never evaluated: it looks like a rule and behaves like
    nothing, and the drift report counts it as a checked rule that never fails.
    The only other constraint test (test_world_units.py:246-260) calls
    `check_constraint` directly and never builds the item, so the gate is open."""
    c = {'kind': 'module_exists', 'spec': {'path': 'app/db.py'}}
    if ok:
        assert _knowledge(type=type_, constraint=c).constraint == c
    else:
        with pytest.raises(ValueError, match='carries a constraint'):
            _knowledge(type=type_, constraint=c)


@pytest.mark.parametrize('c, why', [
    ({'kind': 'forbid_dependency', 'spec': {'from': 1, 'to': 'app'}}, 'has the wrong type'),
    ({'kind': 'forbid_dependency', 'spec': {'from': 'app', 'to': ['core']}},
     'has the wrong type'),
    ({'kind': 'framework_pinned', 'spec': {'package': 'flask', 'version': 3}},
     'has the wrong type'),
    ({'kind': 'framework_pinned', 'spec': {'package': 'flask', 'version': None}}, None),
    ({'kind': 'framework_pinned', 'spec': {'package': 'flask'}}, None),   # version optional
    ({'kind': 'framework_pinned', 'spec': {'package': '  '}}, 'needs a package name'),
    ({'kind': 'forbid_dependency', 'spec': {'from': 'a', 'to': 'b', 'why': 'x'}},
     'spec has exactly'),
    ({'kind': 'module_exists', 'spec': []}, 'spec has exactly'),
    ({'kind': 'require_layering', 'spec': {'layers': ['core']}}, 'at least two layers'),
    ({'kind': 'require_layering', 'spec': {'layers': ['core', '/abs/path']}},
     'must be relative to the repository'),
    ({'kind': 'require_layering', 'spec': {'layers': ['core', 'win\\path']}},
     'must be relative to the repository'),
    ({'kind': 'require_layering', 'spec': {'layers': 'core/api'}}, 'has the wrong type'),
    ({'kind': 'module_exists', 'spec': {'path': 'app/../secrets'}}, 'must be relative'),
    ({'kind': 'doc_matches_code', 'spec': {'doc': 'docs/x.md', 'code': 'app/x.py'}}, None),
    ({'kind': 'teleport_check', 'spec': {}}, 'unknown constraint kind'),
    ('not-a-constraint', 'a constraint is'),
    ({'kind': 'module_exists'}, 'a constraint is'),
], ids=['from-int', 'to-list', 'version-int', 'version-none', 'no-version', 'blank-package',
        'extra-spec-key', 'spec-list', 'one-layer', 'layer-abs', 'layer-backslash',
        'layers-str', 'path-dotdot', 'doc-matches', 'unknown-kind', 'str', 'no-spec'])
def test_a_constraint_is_kind_and_spec_with_typed_values(c, why):
    """entities.py:497-521: the spec keys are matched against CONSTRAINT_SPECS
    (entities.py:477-483) as `required <= set(spec) <= set(want)`, where
    `framework_pinned.version` is optional only because its type allows None
    (entities.py:481 + 506-508); every value present is typed
    (entities.py:509-511); `require_layering` needs two layers and each layer glob
    and every path goes through `check_glob` (entities.py:512-519).
    `doc_matches_code` is accepted and reported uncheckable (its comment,
    entities.py:475-476): refusing it would make a documented kind unusable. The
    per-layer globs are checked nowhere else, so dropping that loop lets an
    absolute or escaping layer into a drift assessment that reads it as in-repo."""
    if why is None:
        E.check_constraint(c)
    else:
        with pytest.raises(ValueError, match=why):
            E.check_constraint(c)


@pytest.mark.parametrize('pattern', ['', '   ', None, 7, ['app/x.py']],
                         ids=['empty', 'blank', 'none', 'int', 'list'])
def test_a_path_pattern_is_a_non_empty_string(pattern):
    """entities.py:489-490, the non-string half: reachable from a constraint whose
    layer list holds a non-string, because the type loop runs first only for spec
    KEYS the table types, and `require_layering` types `layers` as a list, not its
    entries. Dropping this line turns the next one's `pattern.startswith('/')`
    into an AttributeError, which no caller treats as a refusal."""
    with pytest.raises(ValueError, match='a path pattern is a non-empty string'):
        E.check_glob(pattern)


@pytest.mark.parametrize('pattern', ['app/x.py', './app', 'app//x', 'a/..b', 'a..b',
                                     'dir/sub/*.py'],
                         ids=['plain', 'dot-slash', 'double-slash', 'dotdot-prefix',
                              'dots-in-name', 'star'])
def test_a_glob_that_stays_inside_the_repository_is_accepted(pattern):
    """entities.py:491-494, the admit side: `..` is refused only as a WHOLE
    segment (`'..' in pattern.split('/')`), so `a/..b` is a file name and stays
    legal. A check that flagged it as an escape would refuse real paths, and a
    constraint list quietly emptied of them checks nothing."""
    E.check_glob(pattern)


# ── typed references: a card, a link, a task ref ─────────────────────────────

CARD = {'kind': 'mission', 'id': i('mission')}


@pytest.mark.parametrize('card, why', [
    ({'type': 'mission', 'ref': dict(CARD)}, None),
    ({'type': 'estop', 'ref': dict(CARD)}, None),                # the P19 B10 words
    ({'type': 'change', 'ref': {'kind': 'artifact', 'id': HEX64}}, None),   # no prefix
    ({'type': 'invoice', 'ref': dict(CARD)}, 'a card is'),       # not a CARD_TYPE
    ({'type': 'Mission', 'ref': dict(CARD)}, 'a card is'),       # the words are exact
    ({'ref': dict(CARD)}, 'a card is'),                           # no type
    ('mission', 'a card is'),                                     # not a dict
    ({'type': 'mission', 'ref': {'kind': 'mission', 'id': 'msn_bad'}}, 'a card ref'),
    ({'type': 'mission', 'ref': {'kind': 'mission', 'id': i('task')}}, 'a card ref'),
    ({'type': 'mission', 'ref': {'kind': 'mission'}}, 'a card ref'),
    ({'type': 'mission', 'ref': {'kind': '', 'id': i('mission')}}, 'a card ref'),
    ({'type': 'mission', 'ref': None}, 'a card ref'),
], ids=['mission', 'estop', 'prefixless-kind', 'unknown-type', 'capitalised', 'no-type',
        'str', 'malformed-id', 'id-of-another-kind', 'no-id', 'empty-kind', 'no-ref'])
def test_a_card_is_a_typed_reference_to_a_real_object(card, why):
    """entities.py:606-610 + check_ref at 579-584: a card is a live reference the
    surfaces follow, so its type is one of CARD_TYPES (entities.py:574-577) and its
    ref is `{kind, id}` with an id OF that kind -- `r['kind'] not in ids.PREFIXES or
    ids.is_id(r['id'], r['kind'])`. Drop the second half and a card labelled
    'mission' may carry a task id, and every reader of it lands on the wrong row."""
    if why is None:
        assert len(_message(cards=(card,)).cards) == 1
    else:
        with pytest.raises(ValueError, match=why):
            _message(cards=(card,))


@pytest.mark.parametrize('link, why', [
    ({'ref': {'kind': 'task', 'id': i('task')}}, None),
    ({'ref': {'kind': 'task', 'id': i('task')}, 'why': 'touched'}, None),   # {ref, ...}
    ({'ref': {'kind': 'task', 'id': 'tsk_bad'}}, 'a link ref'),
    ({'ref': {'kind': 'task', 'id': i('mission')}}, 'a link ref'),
    ({'why': 'touched'}, 'a link ref'),                       # no ref at all
    ('task', 'a link is'),
], ids=['good', 'extra-key', 'malformed-id', 'id-of-another-kind', 'no-ref', 'str'])
def test_a_link_names_one_world_object_by_kind_and_id(link, why):
    """entities.py:611-613: a link is `{ref, ...}` -- extra keys are allowed, as on
    a card, and only `ref` is checked, by the same `check_ref`. Invert
    `isinstance(link, dict)` and a bare string link raises AttributeError out of
    `link.get` instead of refusing the row."""
    if why is None:
        assert len(_message(links=(link,)).links) == 1
    else:
        with pytest.raises(ValueError, match=why):
            _message(links=(link,))


@pytest.mark.parametrize('r, why', [
    ({'kind': 'knowledge_item', 'id': i('knowledge_item')}, None),
    ({'kind': 'harness', 'id': 'claude_code'}, None),          # a kind with no prefix
    ({'kind': 'knowledge_item', 'id': 'kno_bad'}, 'a task ref'),
    ({'kind': 'knowledge_item', 'id': i('artifact_record')}, 'a task ref'),
    ({'kind': 'knowledge_item', 'id': ''}, 'a task ref'),
    ({'kind': 'knowledge_item', 'id': i('knowledge_item'), 'what': 'the lesson'},
     'a task ref'),                       # the ref itself is exactly {kind, id}
    ('x', 'a task ref'),
], ids=['good', 'prefixless-kind', 'malformed', 'id-of-another-kind', 'empty-id', 'extra-key',
        'str'])
def test_a_task_input_ref_is_a_kind_and_id_pair(r, why):
    """entities.py:957-958: a task's `refs` are the extra material the plan hands
    the executor (domain-model section 7.3), and they are the second half of the
    dispatch contract `Task._FROZEN` pins (entities.py:902-906). An id of another
    kind is handed out as if it were what the plan said: the harness reads a row
    nobody authorised into this task's context."""
    if why is None:
        assert len(_task(refs=(r,)).refs) == 1
    else:
        with pytest.raises(ValueError, match=why):
            _task(refs=(r,))


@pytest.mark.parametrize('kind, mission_id, why', [
    ('primary', None, None),
    ('mission', i('mission'), None),
    ('primary', i('mission'), 'a mission thread names'),   # the direction nothing covers
    ('mission', None, 'a mission thread names'),
    ('mission', 'msn_bad', 'is not a mission id'),         # refused as a ref first
    ('side', None, 'must be one of'),                       # not even a kind
], ids=['primary', 'mission', 'primary-with-mission', 'mission-without', 'bad-id',
        'unknown-kind'])
def test_a_mission_thread_names_its_mission_and_the_primary_one_does_not(kind, mission_id,
                                                                         why):
    """entities.py:564-566: the guard is an `!=` between the two halves, so BOTH
    sides matter. test_domain.py only bends `kind` to 'mission' without a mission
    id; the primary-with-a-mission_id side is the dangerous one -- a second row
    reading as the primary thread of a mission splits one conversation in two, and
    every query for "the" thread picks either. The last two cases are refused one
    step earlier (the _REFS and _CHOICES loops, entities.py:109-127), which is the
    same fail-closed order: a value nothing can name is never a thread."""
    if why is None:
        assert _conversation(kind=kind, mission_id=mission_id).kind == kind
    else:
        with pytest.raises(ValueError, match=why):
            _conversation(kind=kind, mission_id=mission_id)


@pytest.mark.parametrize('c, ok', [
    (0, True), (1, True), (0.0, True), (1.0, True), (0.4, True), (None, True),
    (True, False), (False, False), (-0.0001, False), (1.0001, False), ('0.9', False),
    (float('nan'), False),
], ids=['0', '1', '0.0', '1.0', '0.4', 'none', 'true', 'false', 'below', 'above', 'str',
        'nan'])
def test_an_intents_confidence_is_a_probability(c, ok):
    """entities.py:657-660: the same bool-and-string exclusion `Entity._NONNEG`
    makes (entities.py:128-132), written by hand here because a float is allowed.
    `True` compares equal to 1 and would ride into the challenge threshold as
    certainty; NaN fails both comparisons, so without the range test it would be
    stored and read as a confident intent that never clears anything."""
    if ok:
        assert _intent(confidence=c).confidence == c
    else:
        with pytest.raises(ValueError, match='Intent.confidence'):
            _intent(confidence=c)


def test_an_intents_target_ref_names_a_real_object():
    """entities.py:655-656: the object the user pointed at, checked by the same
    `check_ref` a card uses; an id that is not of its kind resolves to nothing and
    the intent is applied to whatever the surface guessed instead."""
    ref = {'kind': 'mission', 'id': i('mission')}
    assert _intent(target_refs=(ref,)).target_refs == (ref,)
    with pytest.raises(ValueError, match='Intent.target_refs'):
        _intent(target_refs=(dict(ref, id='msn_bad'),))


# ── the declarative rules themselves (Entity.__post_init__) ──────────────────

@pytest.mark.parametrize('factory, field, bad', [
    (_user, 'last_ack_event_seq', -1), (_user, 'last_ack_event_seq', True),
    (_user, 'last_ack_event_seq', 2.0), (_user, 'last_ack_event_seq', '5'),
    (_task, 'max_attempts', True), (_task, 'max_attempts', 0), (_task, 'estimate', True),
    (_inspection, 'extractor_version', -1), (_inspection, 'extractor_version', True),
    (_inspection, 'attempts', -1), (_inspection, 'attempts', False),
    (_mission, 'max_replans', -1), (_mission, 'max_replans', True),
    (_plan, 'plan_version', True), (_plan, 'plan_version', 0),
], ids=['ack-neg', 'ack-true', 'ack-float', 'ack-str', 'attempts-true', 'attempts-0',
        'estimate-true', 'extractor-neg', 'extractor-true', 'tries-neg', 'tries-false',
        'replans-neg', 'replans-true', 'version-true', 'version-0'])
def test_a_counter_is_a_real_integer_and_never_a_bool(factory, field, bad):
    """entities.py:128-132: `isinstance(v, int) and not isinstance(v, bool) and v
    >= low`, one loop for _NONNEG (low 0) and _MIN1 (low 1). `True` IS 1, so
    without the bool clause a retry counter, a `max_attempts` or a `plan_version`
    could be set by a flag that only meant "yes"; the float and string cases are
    the same trap arriving from JSON."""
    with pytest.raises(ValueError, match=field):
        factory(**{field: bad})


@pytest.mark.parametrize('estimate, ok', [
    (1, True), (5, True), (None, False), (0, False), (6, False), (5.0, False),
], ids=['one', 'five', 'none', 'zero', 'six', 'float'])
def test_a_task_estimate_is_one_to_five(estimate, ok):
    """entities.py:950-951: the band the capacity planner sums (resource-router
    section 3) is bounded here and not only in planning/validate.py, which sees the
    model's JSON and never a row built by the plan editor or replayed from the
    store -- where a 0 would make the task free and a 9 invisible to the ceiling."""
    if ok:
        assert _task(estimate=estimate).estimate == estimate
    else:
        with pytest.raises(ValueError, match='estimate'):
            _task(estimate=estimate)


@pytest.mark.parametrize('kw, why', [
    ({'action_classes': ('teleport',)}, 'unknown action classes'),
    ({'action_classes': ('Read',)}, 'unknown action classes'),      # the words are exact
    ({'action_classes': ('read', 'read')}, None),                   # a set: order-free
    ({'capabilities_required': ('telepathy',)}, 'unknown capabilities'),
    ({'capabilities_required': ('shell', 'vision')}, None),
    ({'capabilities_required': ('SHELL',)}, 'unknown capabilities'),
    ({'depends_on': ('t1',)}, 'cannot depend on itself'),
    ({'depends_on': ['t1']}, 'cannot depend on itself'),            # coerced first
    ({'depends_on': ('t0',)}, None),
    ({'kind': 'magic'}, 'Task.kind must be one of'),
    ({'min_model_tier': 'huge'}, 'min_model_tier must be one of'),
    ({'workspace_mode': 'sandbox'}, 'workspace_mode must be one of'),
], ids=['class-unknown', 'class-capital', 'class-duplicate', 'cap-unknown', 'cap-good',
        'cap-capital', 'self-dependency', 'self-dependency-list', 'dependency-other', 'kind',
        'tier', 'mode'])
def test_a_task_names_only_the_closed_vocabs(kw, why):
    """entities.py:941-949 + 114-117: an action class the policy table does
    not know would match no rule at all (an ALLOW_ALL-shaped rule reads
    `in ACTION_CLASSES`), an unknown capability makes the task unroutable in a way
    no resource ever reports, and the list->tuple coercion at entities.py:84-87
    runs BEFORE `_check`, so dependencies arriving as a JSON list still meet the
    self-dependency refusal."""
    if why is None:
        _task(**kw)
    else:
        with pytest.raises(ValueError, match=why):
            _task(**kw)


@pytest.mark.parametrize('c, ok', [
    (({'text': 'the suite passes', 'check': 'automatic'},), True),
    (({'text': 'the owner reads it', 'check': 'human'},), True),
    (({'text': 'x'},), False),
    (({'check': 'human'},), False),
    (({'text': 'x', 'check': 'human', 'note': 'now'},), False),      # EXACTLY two keys
    (({'text': 'x', 'check': 'sometimes'},), False),
    (({'text': '  ', 'check': 'human'},), False),
    (('x',), False),
], ids=['automatic', 'human', 'no-check', 'no-text', 'extra-key', 'bad-check', 'blank',
        'str'])
def test_an_acceptance_criterion_is_exactly_text_and_check(c, ok):
    """entities.py:952-956: `set(c) == {'text', 'check'}` -- unlike a Mission
    success criterion (entities.py:771-777) this one has no `origin` and no room
    for one, so an extra key is a field the task-level verifier has no way to
    read, and a criterion missing either half is never checked."""
    if ok:
        assert len(_task(acceptance=c).acceptance) == 1
    else:
        with pytest.raises(ValueError, match='an acceptance criterion is'):
            _task(acceptance=c)


@pytest.mark.parametrize('factory, kw, why', [
    (_task, {'kind': None}, 'Task.kind must be one of'),
    (_task, {'key': None}, 'Task.key must be a non-empty string'),
    (_inspection, {'extractor_version': None}, 'must be an integer'),
    (_user, {'display_name': None}, 'User.display_name must be a non-empty string'),
], ids=['task-kind', 'task-key', 'extractor', 'display-name'])
def test_a_required_word_or_reference_is_never_silently_none(factory, kw, why):
    """entities.py:83 (`optional` is built from the field DEFAULTS) + 109-117 +
    123-127: a field with no default may not be None. Drop the `field in optional`
    half and every required word admits None, and a row with no kind is a row
    nothing can route, render or transition."""
    with pytest.raises(ValueError, match=why):
        factory(**kw)


@pytest.mark.parametrize('factory, kw', [
    (_task, {'min_model_tier': None}), (_task, {'workspace_mode': None}),
    (_task, {'integration_state': None}), (_task, {'failure_class': None}),
    (_inspection, {'dirty': None}), (_intent, {'confidence': None}),
], ids=['tier', 'mode', 'integration', 'failure-class', 'dirty', 'confidence'])
def test_an_optional_word_or_reference_may_be_absent(factory, kw):
    """entities.py:109-117 + 123-127, the other half of the same split: an absent
    optional is not an invalid one (`v is None and field in optional`). Refusing
    None here is what makes pre-feature rows unreadable -- the reason Task's
    worktree fields (entities.py:934-937) and RepositoryInspection.dirty default to
    None rather than to a word."""
    assert factory(**kw)


# ── Plan: the immutable provenance of one plan version ───────────────────────

@pytest.mark.parametrize('digest, ok', [
    (HEX64, True), ('0' * 64, True), (None, True),
    ('abc', False), ('a' * 63, False), ('a' * 65, False), ('A' * 64, False),
    ('g' * 64, False), (HEX64 + 'beef', False),
], ids=['hex', 'zeros', 'none', 'short', '63', '65', 'upper', 'not-hex', 'extra-tail'])
def test_a_plan_digest_is_a_lowercase_sha256(digest, ok):
    """entities.py:849-851 + 28: `action_hash` binds every approval to a plan
    version by this digest, so a row whose digest is not a sha256 is an approval
    bound to nothing -- and `_HEX64` is `fullmatch`ed, so the last case, a string
    that merely STARTS with a digest, is refused too. Uppercase is refused because
    the pattern is lowercase-only, like every hex column in this file."""
    if ok:
        assert _plan(digest=digest).digest == digest
    else:
        with pytest.raises(ValueError, match='Plan.digest is a sha256 hex digest'):
            _plan(digest=digest)


@pytest.mark.parametrize('value, ok', [
    (1, True), (40, True), (None, True),
    (0, False), (-1, False), ('7', False), (1.5, False), (2.0, False),
], ids=['one', 'forty', 'none', 'zero', 'negative', 'str', 'float', 'integral-float'])
def test_a_plans_round_seq_is_an_event_seq(value, ok):
    """entities.py:852-854: the planning round is the seq of the event that opened
    it (the comment at entities.py:824-825), and None is the stub path. `2.0` is
    refused although it equals 2: a float would never match an event row on read.
    test_domain.py covers the bool rule for Execution.attempt, never here."""
    if ok:
        assert _plan(round_seq=value).round_seq == value
    else:
        with pytest.raises(ValueError, match='round_seq is an event seq'):
            _plan(round_seq=value)


@pytest.mark.xfail(strict=True, reason='SOURCE BUG: entities.py:852-853 tests only '
                                       'isinstance(int) and the bound. Unlike every '
                                       '_MIN1/_NONNEG field (entities.py:128-132) and '
                                       'unlike Mission.decided_plan_version '
                                       '(entities.py:768-770), Plan.round_seq accepts a '
                                       'bool, so True is stored as the seq of the '
                                       'planning round')
def test_a_plans_round_seq_is_not_a_bool():
    """entities.py:852-854: `True` is an int that passes `>= 1` and is not an event
    seq -- the row would point every replan at the mission's first event, the one
    that opened the very first round, which is what `planning_blocked`'s `round_seq`
    and the round's answers are matched on. The neighbouring `not isinstance(v,
    bool)` guards (entities.py:131, 769) show the intended rule."""
    with pytest.raises(ValueError, match='round_seq'):
        _plan(round_seq=True)


@pytest.mark.parametrize('a, ok', [
    (({'text': 'the fixture already exists', 'origin': 'inferred'},), True),
    (({'text': 'x', 'origin': 'inferred', 'because': 'no fixture'},), True),   # {...}
    (({'text': 'x', 'origin': 'explicit'},), False),
    (({'text': 'x'},), False),
    (({'text': '  ', 'origin': 'inferred'},), False),
    (('x',), False),
], ids=['inferred', 'extra-keys', 'explicit', 'no-origin', 'blank', 'str'])
def test_a_plan_assumption_is_always_the_planners_own_guess(a, ok):
    """entities.py:855-858 (p8-design-gate D5): an assumption is gap-filling the
    model invented, so `origin` is pinned to 'inferred' here precisely because the
    Mission's requirement list (entities.py:778-783) admits 'explicit'. One flipped
    comparison and invented content is attributed to the user, and the plan gate
    holds the mission to a requirement the user never set."""
    if ok:
        assert len(_plan(assumptions=a).assumptions) == 1
    else:
        with pytest.raises(ValueError, match='a plan assumption is'):
            _plan(assumptions=a)


@pytest.mark.parametrize('s, ok', [
    (({'task': 't2', 'after': 't1', 'because': 'shared file'},), True),
    (({'task': None, 'after': None, 'because': None},), True),      # keys, not values
    (({'task': 't2', 'after': 't1'},), False),                      # no reason recorded
    (({'task': 't2', 'after': 't1', 'because': 'x', 'by': 'core'},), False),
    (('t2 after t1',), False),
], ids=['good', 'null-values', 'no-because', 'extra-key', 'str'])
def test_a_serialisation_edge_is_task_after_because(s, ok):
    """entities.py:859-861 (p8-design-gate D8): the dependencies Core added are
    shown to the user with the reason they were added, so `set(s) == {task, after,
    because}` refuses both a missing and an invented key -- a serialisation the
    schedule cannot explain never reaches a plan version, and an unexplained one
    would be presented as the model's own ordering."""
    if ok:
        assert len(_plan(serialised=s).serialised) == 1
    else:
        with pytest.raises(ValueError, match='a serialisation edge is'):
            _plan(serialised=s)


# ── the step-up record, and who may hold what ────────────────────────────────

def test_a_step_up_pin_is_a_whole_pbkdf2_record():
    """entities.py:195 + 230-232 (PIN_HASH.fullmatch, P15 D19): the one thing
    that keeps a plaintext PIN out of `devices.pin_hash` and a cheap record out of
    the step-up gate. `[1-9][0-9]{4,6}` puts `[1-9]` FIRST, so a 3-digit count or a
    leading zero is refused although it is still a number, and `fullmatch` (not
    `match`) is what refuses a valid record with the PIN appended after it.
    test_p20_secrets.py:362-369 tries only a real hash and the bare PIN."""
    ok_pin = 'pbkdf2_sha256$200000$%s$%s' % ('1' * 32, '2' * 64)
    device = E.Device(id=i('device'), principal_id=i('principal'), name='laptop',
                      platform='web', pin_hash=ok_pin)
    assert device.pin_hash == ok_pin
    for bad in ('2468',                                        # the PIN itself
                'pbkdf2_sha256$999$%s$%s' % ('1' * 32, '2' * 64),
                'pbkdf2_sha256$10000000$%s$%s' % ('1' * 32, '2' * 64),
                'pbkdf2_sha256$020000$%s$%s' % ('1' * 32, '2' * 64),
                'pbkdf2_sha256$200000$%s$%s' % ('1' * 31, '2' * 64),
                'pbkdf2_sha256$200000$%s$%s' % ('g' * 32, '2' * 64),
                'pbkdf2_sha256$200000$%s$%s' % ('1' * 32, '2' * 63),
                'pbkdf2_sha256$200000$%s$%s' % ('1' * 32, 'F' * 64),
                'PBKDF2_sha256$200000$%s$%s' % ('1' * 32, '2' * 64),
                ok_pin + '2468'):
        with pytest.raises(ValueError, match='pin_hash is not a pbkdf2_sha256'):
            E.Device(id=i('device'), principal_id=i('principal'), name='laptop',
                     platform='web', pin_hash=bad)


@pytest.mark.parametrize('kind, scopes, ok', [
    ('user_device', ('observe', 'control', 'approve', 'admin'), True),
    ('brain', ('propose',), True),
    ('execution', ('report', 'checkpoint', 'request_approval'), True),
    ('automation', ('create_mission',), True),
    ('user_device', (), True),
    ('brain', ('propose', 'approve'), False),        # a brain may never approve
    ('execution', ('create_mission',), False),       # nor open a mission
    ('node', ('node_report', 'admin'), False),
    ('system', ('system', 'admin'), False),
], ids=['device-all', 'brain-propose', 'execution-all', 'automation', 'no-scope',
        'brain-approves', 'execution-creates', 'node-admin', 'system-admin'])
def test_a_principal_holds_only_the_scopes_its_kind_may_have(kind, scopes, ok):
    """entities.py:188-191 + values.PRINCIPAL_SCOPES (values.py:19-26): this table
    is the whole authority of a bearer credential (domain-model section 3.3) -- a
    brain can propose and never approve, an execution cannot create a mission. The
    set difference is safe only because `_CHOICES` (entities.py:183) admits exactly
    the keys of that table: drop the `_CHOICES` entry and an invented kind is a
    KeyError out of `PRINCIPAL_SCOPES[self.kind]` rather than a refusal, and drop
    the difference and a brain row carries `approve`. Nothing in tests/v1 builds
    this row with a bad scope -- the API-side 400s validate `auth.SCOPES`, not
    this entity -- so no test names the message."""
    if ok:
        assert E.Principal(id=i('principal'), kind=kind, scopes=scopes).scopes == scopes
    else:
        with pytest.raises(ValueError, match='cannot hold'):
            E.Principal(id=i('principal'), kind=kind, scopes=scopes)


def test_an_unknown_principal_kind_is_refused_before_the_scope_table_is_read():
    """entities.py:183 + 114-117: the pairing that keeps
    `PRINCIPAL_SCOPES[self.kind]` from raising KeyError -- a kind outside the table
    is refused as a word, not as a missing key. Break it and an unknown kind is a
    500 instead of a refusal, which is what a client that guesses kinds gets."""
    with pytest.raises(ValueError, match='Principal.kind must be one of'):
        E.Principal(id=i('principal'), kind='hacker', scopes=())
    with pytest.raises(KeyError, match='telepath'):
        values.PRINCIPAL_SCOPES['telepath']

"""T-319: the ten highest-risk uncovered branches of archeus/core/planning/validate.py.

Fail-closed and denial paths first: the `digest` that `application.authorization.intact`
re-hashes from the stored rows before an in-force plan may be authorised (a contract
field that is skipped by mistake, or a contract field that is skipped when it should
not be, either one decides whether a real plan is refused or a tampered one is accepted),
`order`/`waves` refusing a cyclic or unresolved graph instead of deriving dispatch
groups from it, and the D8 serialisation that must neither miss an overlap nor invent an
edge across work that is already ordered. Then the boundary values (`MAX_TASKS`, the
1-5 estimate, the cost-band ceilings), then the error paths (`find_cycle` on a malformed
graph, `problems` on malformed task dicts).

Same pure-function style, the same `t(...)`/`OK` fixtures and the same parametrised
shape as tests/v1/unit/test_planning_units.py. Nothing here touches the filesystem, the
environment, a process or the network, so the file is identical on Linux and Windows:
the path globs are plain strings (the backslash cases are deliberately Windows-shaped to
prove `overlap` normalises separators itself, not that the test platform uses them).
"""

from dataclasses import replace

import pytest

from archeus.core.domain import entities
from archeus.core.planning import validate

PLAN_ID = 'pln_01J0000000000000000000000A'
MISSION_ID = 'msn_01J0000000000000000000000A'
OK = [{'text': 'works', 'check': 'automatic'}]
HUMAN = {'text': 'the user says so', 'check': 'human'}


def t(key, **kw):
    """A well-formed task dict, exactly as `test_planning_units.t` builds one."""
    return dict({'key': key, 'title': 'T %s' % key, 'objective': 'do %s' % key,
                 'kind': 'code_change', 'depends_on': (), 'action_classes': ('write_repo',),
                 'acceptance': OK}, **kw)


def plan(**kw):
    return entities.Plan(**dict({'id': PLAN_ID, 'mission_id': MISSION_ID, 'summary': 's',
                                 'estimated_cost': 'low', 'digest': 'a' * 64}, **kw))


def task(key, **kw):
    return entities.Task(**dict({'id': 'tsk_01J0000000000000000000000A',
                                 'plan_id': PLAN_ID, 'mission_id': MISSION_ID, 'key': key,
                                 'title': 'T %s' % key, 'kind': 'code_change',
                                 'objective': 'do %s' % key, 'acceptance': tuple(OK)}, **kw))


# ── G1-G4 the digest: the fields it must ignore, the order it must not see, ──
# ──     the content it must not tolerate changing (authorization.intact) ──

def test_g1_the_digest_ignores_every_task_field_outside_the_contract():
    """`_TASK_SKIP`: `Work.propose_plan` hashes the tasks before they are inserted and
    `authorization.intact` re-hashes them from the rows after dispatch has moved them, so
    a lifecycle field in the hash would deny authorisation to every plan whose tasks have
    run (and P13's merge-back fields are already covered by test_planning_units)."""
    p, t1, t2 = plan(), task('t1'), task('t2', depends_on=('t1',))
    base = validate.digest(p, [t1, t2])
    for moved in (replace(t1, state='RUNNING'), replace(t1, state='SUCCEEDED'),
                  replace(t1, failure_class='task'),
                  replace(t1, plan_id='pln_01J00000000000000000000ZZZ'),
                  replace(t1, id='tsk_01J00000000000000000000ZZZ')):
        assert validate.digest(p, [moved, t2]) == base


def test_g2_the_digest_ignores_the_plan_fields_outside_the_contract():
    """`_PLAN_SKIP`: the digest is computed while the row is still DRAFT and re-checked
    when it is PROPOSED/APPROVED, and it can never contain the digest it is being compared
    to. Hashing `state` or `digest` would make `ready` and `intact` unsatisfiable."""
    p, t1 = plan(), task('t1')
    base = validate.digest(p, [t1])
    assert validate.digest(replace(p, state='PROPOSED'), [t1]) == base
    assert validate.digest(replace(p, state='APPROVED'), [t1]) == base
    assert validate.digest(replace(p, digest='b' * 64), [t1]) == base
    assert validate.digest(replace(p, id='pln_01J00000000000000000000ZZZ'), [t1]) == base
    assert ('state' in validate._PLAN_SKIP and 'digest' in validate._PLAN_SKIP
            and 'id' in validate._PLAN_SKIP)


def test_g3_the_digest_does_not_see_the_order_the_task_rows_came_back_in():
    """The `sorted(..., key=lambda t: t['key'])` of the task bodies: the hash at propose
    time is built from the specs and the hash at authorisation time from
    `tx.where(entities.Task, ...)`, so any order the store happens to return would read as
    content that does not match its digest, and every plan would be refused."""
    p = plan()
    ts = [task('t%d' % i, depends_on=(('t%d' % (i - 1)),) if i else ()) for i in range(4)]
    base = validate.digest(p, ts)
    assert validate.digest(p, list(reversed(ts))) == base
    assert validate.digest(p, [ts[2], ts[0], ts[3], ts[1]]) == base


@pytest.mark.parametrize('field,value', [
    ('title', 'another title'),
    ('objective', 'another objective'),
    ('expected_output', 'something else'),
    ('kind', 'research'),
    ('depends_on', ('zz',)),
    ('action_classes', ('read',)),
    ('capabilities_required', ('shell',)),
    ('min_model_tier', 'large'),
    ('workspace_mode', 'in_place'),
    ('touches', ('src/other.py',)),
    ('serves', ('r1',)),
    ('estimate', 5),
    ('acceptance', (HUMAN,)),
], ids=['title', 'objective', 'expected_output', 'kind', 'depends_on', 'action_classes',
        'capabilities', 'tier', 'workspace_mode', 'touches', 'serves', 'estimate',
        'acceptance'])
def test_g4_a_tampered_task_contract_field_changes_the_digest(field, value):
    """The fail-open half of G1-G3: every dispatch-contract field must be IN the hash, or
    editing the stored row to change it (a different `touches`, a wider action class, a
    human acceptance for an automatic task) would keep matching the digest the approval
    was given for. Adding any of these names to `_TASK_SKIP` is what this catches."""
    p, t1, t2 = plan(), task('t1'), task('t2', depends_on=('t1',))
    tampered = replace(t1, **{field: value})
    assert validate.digest(p, [tampered, t2]) != validate.digest(p, [t1, t2])


@pytest.mark.parametrize('field,value', [
    ('summary', 'another summary'),
    ('estimated_cost', 'high'),
    ('plan_version', 2),
    ('inputs', ({'handle': 'r1', 'text': 'a flag', 'origin': 'explicit'},)),
    ('coverage', ({'requirement': 'r1', 'tasks': ['t1']},)),
    ('serialised', ({'task': 't2', 'after': 't1', 'because': 'touches overlap'},)),
    ('rollback', 'git revert'),
], ids=['summary', 'estimated_cost', 'plan_version', 'inputs', 'coverage', 'serialised',
        'rollback'])
def test_g4b_a_tampered_plan_contract_field_changes_the_digest(field, value):
    """Same for the plan side, `estimated_cost` included: the band is Core's (D9) and it is
    only worth anything because the approved version cannot be quietly re-banded."""
    p, t1 = plan(), task('t1')
    assert validate.digest(replace(p, **{field: value}), [t1]) != validate.digest(p, [t1])


# ── G5/G6 order and waves: a graph Core cannot resolve is refused, never ──
# ──     turned into dispatch groups anyway ──

@pytest.mark.parametrize('tasks', [
    [t('a', depends_on=('b',)), t('b', depends_on=('a',))],
    [t('a', depends_on=('a',))],
    [t('a', depends_on=('b',)), t('b', depends_on=('c',)), t('c', depends_on=('a',))],
    [t('a'), t('b', depends_on=('q',))],
], ids=['pair', 'self', 'three', 'unknown'])
def test_g5_order_refuses_a_graph_it_cannot_resolve(tasks):
    """`raise ValueError('the dependency graph has a cycle')`: `Work.propose_plan` and
    `replan` call `validate.order(specs)` and store whatever comes back, so an unresolvable
    graph must stop there. Replacing the raise with `break`/`return out` would store a plan
    whose blocked tasks are simply missing from the order."""
    with pytest.raises(ValueError) as got:
        validate.order(tasks)
    assert 'cycle' in str(got.value)


def test_g5_order_is_stable_and_never_moves_a_task_before_its_dependencies():
    """The `for t in left: ... break` scan: each step takes the FIRST task of the remaining
    list whose dependencies are all placed, so an independent task keeps the position the
    plan gave it and nothing is sorted by key. Taking the last ready task instead, or
    sorting, is what the `z, y, m` and `b, a` asserts catch; the loop invariant is checked
    directly for a graph where a late-listed task must still jump ahead."""
    assert [x['key'] for x in validate.order(
        [t('z'), t('y'), t('m', depends_on=('z', 'y'))])] == ['z', 'y', 'm']
    assert [x['key'] for x in validate.order([t('b'), t('a')])] == ['b', 'a']
    tasks = [t('c', depends_on=('a', 'b')), t('x'), t('a'), t('b', depends_on=('a',))]
    ordered = [x['key'] for x in validate.order(tasks)]
    assert ordered == ['x', 'a', 'b', 'c']
    deps = {x['key']: x['depends_on'] for x in tasks}
    placed = []
    for k in ordered:
        assert set(deps[k]) <= set(placed), (k, deps[k], placed)
        placed.append(k)


@pytest.mark.parametrize('tasks', [
    [t('a', depends_on=('b',)), t('b', depends_on=('a',))],
    [t('a', depends_on=('b',)), t('b', depends_on=('c',)), t('c', depends_on=('a',))],
], ids=['pair', 'three'])
def test_g6_waves_refuses_a_cyclic_graph_instead_of_grouping_it(tasks):
    """`waves` is the read path (`queries.get_plan`) that hands the parallel groups to
    dispatch: groups built from a cyclic graph would run tasks side by side that each wait
    for the other. It must propagate `order`'s refusal."""
    with pytest.raises(ValueError):
        validate.waves(tasks)


def test_g6_waves_of_no_task_and_of_one_task():
    """The `default=-1` in both `max` calls: `waves([])` is the empty plan (no IndexError,
    no ValueError from an empty `max`) and a single task is one wave of one key."""
    assert validate.waves([]) == []
    assert validate.waves([t('a')]) == [['a']]


def test_g6_a_wave_keeps_the_order_the_tasks_were_given_in():
    """The second loop appends over `tasks`, not over `order(tasks)`: within a wave the
    keys follow the plan's own order, which is what makes a derived, never-stored wave list
    reproducible for the caller (dispatch walks a wave left to right). Iterating the ordered
    list instead would reorder a wave by the order the graph happened to resolve in, which
    here is `c, d` rather than the plan's `d, c`."""
    assert validate.waves([t('x'), t('a'), t('b', depends_on=('a',))]) == [['x', 'a'], ['b']]
    assert validate.waves([t('d', depends_on=('b',)), t('c', depends_on=('a',)),
                          t('a'), t('b')]) == [['a', 'b'], ['d', 'c']]


# ── G7 overlap: the literal-prefix rule is the only thing that catches some ──
# ──     clashes, and the `wild` guard is the only thing that stops the rest ──

@pytest.mark.parametrize('a, b, hit', [
    ('src/pkg/*_test.py', 'src/pkg/models.py', True),
    ('src/**/a.py', 'src/x/b.py', True),
    ('docs/**', 'docs/a/b/c.md', True),
    ('src\\pkg\\*_test.py', 'src/pkg/models.py', True),
    ('docs/a.py', 'docs/a', False),
    ('docs/a', 'docs/a.py', False),
    ('src/a/b.py', 'src/a-c.py', False),
], ids=['prefix-only', 'globstar', 'deep', 'backslash', 'literal-prefix-1',
        'literal-prefix-2', 'near-miss'])
def test_g7_the_prefix_rule_and_the_wild_guard_decide_what_fnmatch_cannot(a, b, hit):
    """`return wild and (pa.startswith(pb) or pb.startswith(pa))`: dropping the last two
    lines loses clashes `fnmatch` cannot see (a pattern against a longer literal in the
    same directory), so two tasks writing under `src/pkg/` would run in parallel; dropping
    the `wild` guard turns every pair of literal paths that share a prefix into a clash, so
    `docs/a.py` and `docs/a` would be serialised for no reason."""
    assert validate.overlap(a, b) is hit
    assert validate.overlap(b, a) is hit


def test_g7_the_prefix_cut_is_at_the_first_metacharacter():
    """`_prefix`: the cut is the first `*?[`, so `[` and `?` also end the literal prefix
    (cutting at only `*` would keep `[a-z]/x` as a prefix and clash it against anything
    starting with the same four characters)."""
    assert validate._prefix('src/a*?[b') == 'src/a'
    assert validate._prefix('src/a') == 'src/a'
    assert validate._prefix('') == ''
    assert validate.overlap('src/a?z.py', 'src/aq.py') is True
    assert validate.overlap('src/a[bc]y.py', 'src/acy.py') is True


# ── G8 serialise: no invented edge across work that is already ordered, and ──
# ──     no hanging on a graph that never passed `problems` ──

def test_g8_an_already_ordered_chain_is_not_serialised_again():
    """`if _reaches(deps, b, a) or _reaches(deps, a, b): continue` and the transitive walk
    in `_reaches`: `c` is already behind `b` which is behind `a`, so the a/c clash is not a
    parallel clash and must add nothing. A one-hop `_reaches` (deleting the `todo +=
    deps.get(k, [])` deepening) would report a bogus `c after a` edge, and the plan's
    `serialised` list — the record of what Core, not the model, decided — would be a lie."""
    tasks = [t('a', touches=('src/x.py',)), t('b', depends_on=('a',), touches=('src/y.py',)),
             t('c', depends_on=('b',), touches=('src/x.py',))]
    out, added = validate.serialise(validate.order(tasks))
    assert added == []
    assert {x['key']: x['depends_on'] for x in out} == {'a': (), 'b': ('a',), 'c': ('b',)}


def test_g8_the_clash_is_still_serialised_with_its_reason_when_it_is_parallel():
    """The other side of the same `continue`: with no path between them the later task is
    made to depend on the earlier one, with both globs in the reason."""
    tasks = [t('a', touches=('src/pkg/*_test.py',)), t('b', touches=('src/pkg/models.py',))]
    out, added = validate.serialise(validate.order(tasks))
    assert added == [{'task': 'b', 'after': 'a',
                      'because': 'touches overlap: src/pkg/*_test.py ~ src/pkg/models.py'}]
    assert {x['key']: x['depends_on'] for x in out} == {'a': (), 'b': ('a',)}


def test_g8_serialise_terminates_on_a_graph_with_an_unreachable_cycle():
    """The `if k not in seen` memo in `_reaches`: `d` reaches the b<->c cycle but can never
    reach `a`, so without the memo the walk spins forever and the caller hangs. `serialise`
    is public and `Work` calls it on a graph it ordered itself, so this is the shape that
    would only ever appear from a caller that skipped validation."""
    tasks = [t('a', touches=('src/a.py',)), t('b', depends_on=('c',), touches=('src/b.py',)),
             t('c', depends_on=('b',), touches=('src/c.py',)),
             t('d', touches=('src/d.py',))]
    out, added = validate.serialise(tasks)
    assert [(e['task'], e['after']) for e in added] == []
    assert {x['key']: x['depends_on'] for x in out} == {
        'a': (), 'b': ('c',), 'c': ('b',), 'd': ()}


# ── G9 find_cycle: a malformed graph is not a cycle and a diamond is not a ──
# ──     cycle, and the cycle that is real is reported from where it repeats ──

@pytest.mark.parametrize('tasks', [
    [t('a', depends_on=('z',))],
    [t('a', depends_on=('b', 'z')), t('b')],
    [t('a', depends_on=('a',))],
    [t('a'), t('b', depends_on=('nope', 'a'))],
], ids=['unknown', 'unknown-plus', 'self', 'unrelated'])
def test_g9_find_cycle_ignores_what_is_not_in_the_plan(tasks):
    """`if d not in deps: continue`: an unknown dependency is `problems`' business ('depends
    on z, which is not in the plan') and must never appear in the cycle answer. What the
    test kills is the wrong answer to an unknown dependency — reporting `[k, d, k]` as a
    cycle (or raising KeyError while walking it); it does NOT kill simply deleting the
    guard, because `deps.get(k, ())` below absorbs the unknown key, and the report says so.
    The `self` case is the `if d != t['key']` filter on the `deps` line, which is killed by
    removing that filter."""
    assert validate.find_cycle(tasks) is None


@pytest.mark.parametrize('tasks', [
    [t('a', depends_on=('b', 'c')), t('b', depends_on=('d',)), t('c', depends_on=('d',)),
     t('d')],
    [t('a', depends_on=('b',)), t('b', depends_on=('d',)), t('c', depends_on=('d',)),
     t('d'), t('e', depends_on=('b', 'c'))],
], ids=['diamond', 'wide-diamond'])
def test_g9_a_diamond_is_not_a_cycle(tasks):
    """`colour[k] = 2` and the `colour.get(d) is None` test around the recursive call: a
    node already finished must not be walked again. Without the finished mark every plan
    with two paths to one task — the normal shape of a parallel plan — would be refused as
    cyclic, which is a failure in the refusing direction but still stops every real plan."""
    assert validate.find_cycle(tasks) is None


@pytest.mark.parametrize('tasks, cycle', [
    ([t('a', depends_on=('b',)), t('b', depends_on=('c',)), t('c', depends_on=('b',))],
     ['b', 'c', 'b']),
    ([t('x'), t('a', depends_on=('b',)), t('b', depends_on=('a',))], ['a', 'b', 'a']),
], ids=['tail', 'after-a-root'])
def test_g9_the_cycle_is_named_from_the_node_that_repeats(tasks, cycle):
    """`return stack[stack.index(d):] + [d]`: the walk enters at `a` (or `x`) but the cycle
    is b -> c -> b, so the sentence the user reads must name the cycle and close it.
    Dropping the `stack.index` slice, or the trailing `[d]`, is what this catches."""
    assert validate.find_cycle(tasks) == cycle


def test_g9_a_cycle_is_only_reported_when_the_graph_is_otherwise_resolved():
    """`if not dup and not any('depends on' in p for p in out)`: with an unresolved or
    duplicated label the cycle sentence is noise next to the reason the graph cannot be
    read at all, and it must not be emitted. Inverting the guard (or removing it) is caught
    by the first two asserts, removing `find_cycle` itself by the third."""
    cycle = [t('a', depends_on=('b',)), t('b', depends_on=('a',))]
    unknown = validate.problems([t('a', depends_on=('b', 'z')), t('b', depends_on=('a',))])
    assert not any('cycle' in p for p in unknown), unknown
    assert any('not in the plan' in p for p in unknown), unknown
    dup = validate.problems([t('a', depends_on=('b',)), t('b', depends_on=('a',)),
                             t('b', title='other', objective='other')])
    assert not any('cycle' in p for p in dup), dup
    assert any('labels repeat' in p for p in dup), dup
    assert any('cycle' in p for p in validate.problems(cycle)), 'a plain cycle is refused'


# ── G10 boundaries: the task ceiling, the 1-5 estimate, the label, and the ──
# ──     rules that must refuse (or must not refuse) on the edge values ──

def test_g10_fifty_tasks_is_the_last_plan_core_accepts():
    """`if len(tasks) > MAX_TASKS`: the limit is inclusive, so a plan of exactly
    `MAX_TASKS` is legal (an off-by-one to `>=` refuses every full plan) and one more is
    refused. It is `append`, not `return`, so the rest of the rules still run on an
    oversized plan — a model answer that is both oversized and defective is retried with
    both reasons."""
    assert validate.MAX_TASKS == 50
    assert validate.problems([t(str(i), title=str(i)) for i in range(validate.MAX_TASKS)]) == []
    found = validate.problems([t(str(i), title=str(i))
                               for i in range(validate.MAX_TASKS + 1)])
    assert found == ['a plan has at most %d tasks' % validate.MAX_TASKS]
    both = validate.problems([t(str(i), title=str(i)) for i in range(validate.MAX_TASKS + 1)]
                             + [t('zz', kind='dance')])
    assert any('at most 50' in p for p in both) and any('unknown kind' in p for p in both), both


@pytest.mark.parametrize('estimate, ok', [
    (1, True), (5, True), (2, True),
    (0, False), (-1, False), (6, False), (True, False), ('3', False), (None, False),
    (1.0, False),
], ids=['one', 'five', 'two', 'zero', 'negative', 'six', 'bool', 'str', 'none', 'float'])
def test_g10_the_estimate_is_an_integer_one_to_five(estimate, ok):
    """`isinstance(est, bool) or not isinstance(est, int) or not 1 <= est <= 5`: `True` is
    an estimate of 1 to Python and `'3'` is an estimate of 3 to `cost_band`'s `int(...)`, so
    both must be refused as the malformed input they are; 1 and 5 are the legal edges."""
    found = any('estimate outside 1-5' in p for p in validate.problems([t('a',
                                                                          estimate=estimate)]))
    assert found is not ok


@pytest.mark.parametrize('key', [None, '', '   ', '\t\n', 123, 0, 1.5],
                         ids=['none', 'empty', 'spaces', 'whitespace', 'int', 'zero', 'float'])
def test_g10_every_task_must_carry_a_usable_label(key):
    """`if any(not (isinstance(k, str) and k.strip()) for k in keys)`: the label is the key
    of the row and what `digest`, `order` and `waves` all index by, so a missing or blank or
    non-string one is refused here — the `isinstance` half is also the only thing that stops
    `k.strip()` raising AttributeError on a model answer with `"key": 3`."""
    assert any('every task has a label' in p for p in validate.problems([t(key)]))


def test_g10_a_label_only_task_is_not_also_reported_as_a_duplicate():
    """The blank-label and duplicate-label rules are independent: two tasks with no label
    are a missing-label refusal, and the pair is only called a repeat once labels exist. An
    early `return` after the label rule would hide the repeat, and dropping the label rule
    would let two label-less tasks through as 'the same task'."""
    found = validate.problems([{'key': '', 'title': 'one', 'objective': 'a',
                                'kind': 'code_change', 'depends_on': (),
                                'action_classes': ('write_repo',), 'acceptance': OK},
                               {'key': '', 'title': 'two', 'objective': 'b',
                                'kind': 'code_change', 'depends_on': (),
                                'action_classes': ('write_repo',), 'acceptance': OK}])
    assert any('every task has a label' in p for p in found), found
    assert any('labels repeat' in p for p in found), found


@pytest.mark.parametrize('acceptance, refused', [
    ((HUMAN,), False),
    ((HUMAN, dict(HUMAN, text='again')), False),
    ((OK[0],), True),
    ((dict(HUMAN), OK[0]), True),
    ((OK[0], dict(HUMAN)), True),
    ((), False),
], ids=['human', 'two-human', 'automatic', 'human-plus-automatic', 'automatic-first', 'none'])
def test_g10_a_human_task_is_refused_for_any_automatic_criterion(acceptance, refused):
    """`if any(c != 'human' for c in checks)`: one automatic criterion among human ones is
    still a claim that a machine can verify a human task, so it must be refused. `any` ->
    `all` is the mutation this catches: the mixed pair would pass."""
    found = any('human task, so its acceptance is human' in p
                for p in validate.problems([t('h', kind='human', acceptance=acceptance,
                                              action_classes=())]))
    assert found is refused


def test_g10_only_an_automatic_criterion_forces_a_non_human_task():
    """The `any(c.get('check') == 'automatic' ...)` half of the last rule: a mission whose
    criteria are all human may be planned entirely by human tasks — refusing it (dropping
    the `any`, or testing `all` instead) is a false refusal of a legitimate plan, while
    letting an automatic criterion be served only by human tasks is the fail-open half,
    which test_planning_units already pins."""
    tasks = [t('h', kind='human', acceptance=(HUMAN,), action_classes=())]
    assert validate.problems(tasks, criteria=(HUMAN,)) == []
    assert validate.problems(tasks, criteria=(HUMAN, OK[0])) == [
        'an automatic success criterion needs at least one non-human task']


@pytest.mark.parametrize('a, b', [
    ({'title': '  Ship It ', 'objective': 'DO THE X'}, {'title': 'ship it', 'objective': ' do the x '}),
    ({'title': None, 'objective': None}, {'title': None, 'objective': None}),
    ({'title': '', 'objective': ''}, {'title': '   ', 'objective': '\n'}),
], ids=['case-space', 'missing', 'blank'])
def test_g10_the_duplicate_check_reads_the_normalised_pair(a, b):
    """`(t.get('title') or '').strip().lower()`: the `or ''` is what stops AttributeError on
    a task with no title at all (and two such tasks are the same task), and the
    strip/lower is what catches the same task quoted twice with different case or padding.
    Dropping either half is caught here."""
    found = validate.problems([t('a', **a), t('b', **b)])
    assert any('are the same task' in p for p in found), found


def test_g10_two_genuinely_different_tasks_are_not_called_duplicates():
    """The same rule must not refuse a real plan: normalising must not go so far as to
    forget which task is which, or every plan is 'the same task' twice over."""
    tasks = [t('a', title='Write the parser', objective='parse the flag'),
             t('b', title='Test the parser', objective='cover the flag')]
    assert validate.problems(tasks) == []


@pytest.mark.parametrize('tier, estimate, band', [
    ('small', 1, 'low'), ('small', 5, 'low'), ('mid', 3, 'low'), ('mid', 4, 'medium'),
    ('large', 5, 'medium'), ('large', 5, 'high'),
], ids=['small1', 'small5', 'mid3', 'mid4', 'large5', 'large5-high'])
def test_g10_the_band_edges_and_the_small_tier(tier, estimate, band):
    """`TIER_WEIGHT` has never been read with 'small' (weight 1) by the existing units, and
    the ceilings are `<=`: score 6 is still low, 7 is medium, 20 is still medium, 21 is
    high. A `<` instead of `<=` moves every boundary one point down and mis-bands whole
    plans."""
    tasks = [t('a', min_model_tier=tier, estimate=estimate)]
    if band == 'high':
        tasks.append(t('b', min_model_tier='small'))
    assert validate.cost_band(tasks) == band


@pytest.mark.parametrize('tasks, band', [
    ([t('a')], 'low'),
    ([t('a', min_model_tier='')], 'low'),
    ([t('a', min_model_tier=None)], 'low'),
    ([t('a', min_model_tier='small', estimate='7')], 'medium'),
    ([], 'low'),
], ids=['no-tier', 'empty-tier', 'none-tier', 'str-estimate', 'empty'])
def test_g10_a_missing_tier_is_costed_as_mid_and_a_numeric_string_is_still_costed(tasks, band):
    """`TIER_WEIGHT[t.get('min_model_tier') or DEFAULT_TIER] * int(t.get('estimate', 1))`:
    an answer that names no tier (or the empty string) is costed as well-specified work
    rather than raising KeyError, and `int(...)` is what lets a `'7'` from a loose answer
    cost 14 (medium) instead of crashing. Removing `or DEFAULT_TIER` or the `int(...)` is
    caught by the two asserts here that would otherwise raise."""
    assert validate.cost_band(tasks) == band

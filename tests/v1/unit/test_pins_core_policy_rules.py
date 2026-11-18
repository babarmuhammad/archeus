"""T-405 hand-mutant pins for `archeus/core/policy/rules.py`.

Every test here names the mutation it exists to kill: a comparison, early
return, membership check, `not`, `and`/`or`, default value or loop bound in
rules.py that an existing test would still pass if it were inverted, removed
or loosened. The twenty-condition read that picked them is in the card report
(/work/QWEN-DONE-T-405.md); a test is added only where that read says
UNCOVERED, and the mutation it kills is written above it.

The module is pure (no I/O, no clock, no OS call), so there is nothing to
fake. The platform rules of the review are followed by writing every path and
pattern with an explicit separator, never relying on case, on an OS error
message, on a sleep or on a real process, and by giving every parametrised
case a short id with no `?` or `:` in it.
"""

import pytest

from archeus.core.domain.actions import RULE_CLASSES, Action
from archeus.core.policy import engine as E
from archeus.core.policy import rules as R

CHAIN = {'USER': 'usr_1', 'WORKSPACE': 'ws_global', 'PROJECT': 'prj_1',
         'MISSION': 'msn_1', 'TASK': 'tsk_1'}


def act(cls, **kw):
    return Action(action_class=cls, target=kw.pop('target', 'task:t1'), **kw)


def rule(level, cls, decision, **kw):
    kw.setdefault('scope_ref', None if level == 'GLOBAL' else CHAIN[level])
    return R.rule(id=kw.pop('id', 'r:%s:%s:%s' % (level, cls, decision)), scope_level=level,
                  action_class=cls, decision=decision, **kw)


def ev(action, *user_rules, **ctx):
    ctx.setdefault('chain', CHAIN)
    return E.evaluate_item(action, dict(ctx, rules=list(user_rules)))


class Row:
    """A PolicyRule row as `from_entity` finds it: the attributes, nothing else."""

    def __init__(self, **kw):
        for k in ('id', 'scope_level', 'action_class', 'decision', 'scope_ref', 'locked',
                  'match', 'boundary', 'outside', 'source', 'expires_at'):
            setattr(self, k, kw.get(k))


# ── the one rule shape the engine reads (rules.py:55-62) ────────────────────

def test_a_deny_rule_stays_locked_when_someone_says_otherwise():
    """MUTANTS: `locked or decision == 'DENY'` -> `locked` (rules.py:60), i.e.
    a stored row that says `locked: false` unlocks its own DENY; and the whole
    DENY-forces-lock half of the expression. The property tests in
    test_policy_units.py only ever pass `locked` explicitly, so nothing else
    reaches this branch."""
    denied = rule('USER', 'install', 'DENY', locked=False, id='deny-broad')
    assert denied['locked'] is True
    assert R.rule(id='d2', scope_level='USER', action_class='install',
                  decision='DENY')['locked'] is True
    # and the lock is the engine's, not a label: a deeper ALLOW cannot answer it
    r = ev(act('install'), denied, rule('TASK', 'install', 'ALLOW', id='allow-deep'))
    assert r['decision'] == 'DENY' and r['deciding_rule'] == 'deny-broad'


def test_a_rule_never_carries_away_the_callers_match_and_boundary_dicts():
    """MUTANTS: `dict(match or {})` -> `match or {}` and
    `dict(boundary) if boundary else None` -> `boundary if boundary else None`
    (rules.py:61): the rule a decision snapshots would then be a live view of
    a dict someone else still holds, and a replay would answer from rules that
    changed after the decision."""
    match, boundary = {'environment': 'prod'}, {'paths': ['src/**']}
    r = R.rule(id='x', scope_level='USER', action_class='write_repo', decision='ASK',
               match=match, boundary=boundary)
    match.clear()
    boundary.clear()
    assert r['match'] == {'environment': 'prod'}
    assert r['boundary'] == {'paths': ['src/**']}
    # an empty boundary is `None`: the engine reads a boundary as predicates
    # that must all hold, and `{}` would say "bounded by nothing, checked".
    assert R.rule(id='e', scope_level='USER', action_class='write_repo',
                  decision='ASK', boundary={})['boundary'] is None


def test_a_rule_copies_its_boundary_all_the_way_down():
    """rule() once copied the boundary one level deep, so a caller that appended
    to a list it passed in still reached into the rule the engine trusts."""
    boundary = {'paths': ['src/**']}
    r = R.rule(id='x', scope_level='USER', action_class='write_repo',
               decision='ALLOW_WITHIN_BOUNDARY', boundary=boundary)
    boundary['paths'].append('@workspace/**')
    assert r['boundary'] == {'paths': ['src/**']}


def test_a_rule_that_names_no_outside_decision_asks():
    """MUTANTS: `'outside': outside or 'ASK'` -> `'outside': outside`
    (rules.py:62), and `'outside': 'ASK'` for the default. `outside` is the
    decision the engine takes when an ALLOW_WITHIN_BOUNDARY rule's predicates
    do not hold, and it is read through STRICTNESS: a None there is not a
    looser answer, it is the boundary check crashing."""
    for blank in (None, ''):
        assert R.rule(id='x', scope_level='USER', action_class='write_repo',
                      decision='ALLOW_WITHIN_BOUNDARY', outside=blank)['outside'] == 'ASK'
    r = ev(act('write_repo', paths=['../escape']),
           rule('USER', 'write_repo', 'ALLOW_WITHIN_BOUNDARY',
                boundary={'paths': ['@workspace/**']}, locked=True, outside=None))
    assert r['decision'] == 'ASK' and r['checks']['outside'] == ['paths']


# ── the built-in floor and the sentinels (rules.py:65-78) ───────────────────

def test_the_prod_floor_is_a_locked_destructive_deny_and_a_locked_deploy_ask():
    """MUTANTS: the floor rules losing `decision`, `locked`, their
    `{'environment': 'prod'}` match, their GLOBAL level or their builtin
    source (rules.py:67-70). test_policy_units.py:40 kills the destructive
    half and tests/v1/integration/test_policy_http.py:126 the locked deploy
    half, but neither pins the shape: a floor that silently becomes a `user`
    rule, or that only matches when the action happens to say prod, is the
    fail-open."""
    destructive, deploy = R.FLOOR
    assert destructive['id'] == 'builtin:floor:destructive-prod'
    assert (destructive['decision'], destructive['locked']) == ('DENY', True)
    assert deploy['id'] == 'builtin:floor:deploy-prod'
    assert (deploy['decision'], deploy['locked']) == ('ASK', True)
    for r in R.FLOOR:
        assert (r['scope_level'], r['source'], r['scope_ref']) == ('GLOBAL', 'builtin', None)
        assert r['match'] == {'environment': 'prod'}
    # the floor is an answer, not a label: whatever a user rule says about prod
    r = ev(act('deploy', environment='prod'), rule('USER', 'deploy', 'ALLOW'))
    assert r['decision'] == 'ASK' and r['deciding_rule'] == 'builtin:floor:deploy-prod'
    assert 'builtin:floor:deploy-prod' in r['effective']


def test_the_dispatch_contract_is_a_locked_ask_at_the_task_level():
    """MUTANTS: `locked=True` or `decision='ASK'` dropped from TASK_CONTRACT
    (rules.py:73-74). test_policy_units.py:86 kills a looser *decision* (the
    rule would then never appear in `effective`), but the contract sits at the
    deepest level there is, so no engine input can show what its lock does —
    the shape is the only place the lock can be seen."""
    assert (R.TASK_CONTRACT['decision'], R.TASK_CONTRACT['locked']) == ('ASK', True)
    assert (R.TASK_CONTRACT['scope_level'], R.TASK_CONTRACT['action_class'],
            R.TASK_CONTRACT['source'], R.TASK_CONTRACT['id']) == (
               'TASK', 'read', 'builtin', 'builtin:task-contract')


def test_the_estop_and_the_missing_policy_sentinels_deny_and_are_locked():
    """MUTANTS: `decision='DENY'` on ESTOP or MISSING (rules.py:75-78). The
    engine writes its own 'DENY' into the result for both (engine.py:112,120),
    so loosening the data is invisible in an answer — which is exactly why it
    has to be pinned: the snapshot a decision replays from carries these
    dicts, and a replayed DENY read from a rule that says ALLOW is a lie.
    test_policy_units.py:121 and :144 pin the answer and the id only."""
    for r, rid in ((R.ESTOP, 'builtin:estop'), (R.MISSING, 'builtin:policy-missing')):
        assert r['id'] == rid
        assert (r['decision'], r['locked']) == ('DENY', True)
        assert (r['scope_level'], r['source']) == ('GLOBAL', 'builtin')


# ── a PolicyRule row as the engine's rule dict (rules.py:94-98) ─────────────

def test_a_stored_row_carries_every_field_the_engine_reads():
    """MUTANTS: one name dropped from the attribute list at rules.py:97-98.
    Each name guards a different fail-open: `locked` lets a broader locked
    rule be loosened, `expires_at` keeps a rule that was meant to die,
    `outside` loses the DENY a boundary was meant to fall back to, `match`
    widens the rule to every action of its class, `boundary` turns an
    ALLOW_WITHIN_BOUNDARY into a bare ALLOW, `scope_ref` makes it chain-wide."""
    row = Row(id='rul_1', scope_level='PROJECT', action_class='git_push',
              decision='ALLOW_WITHIN_BOUNDARY', scope_ref='prj_1', locked=True,
              match={'branch_glob': 'archeus/*'}, boundary={'branches': ['archeus/*']},
              outside='DENY', source='user', expires_at='2026-01-01T00:00:00Z')
    got = R.from_entity(row)
    assert got == {'id': 'rul_1', 'scope_level': 'PROJECT', 'action_class': 'git_push',
                   'decision': 'ALLOW_WITHIN_BOUNDARY', 'scope_ref': 'prj_1',
                   'locked': True, 'match': {'branch_glob': 'archeus/*'},
                   'boundary': {'branches': ['archeus/*']}, 'outside': 'DENY',
                   'source': 'user', 'expires_at': '2026-01-01T00:00:00Z'}
    # and the row cannot unlock its own DENY any more than the builder can
    assert R.from_entity(Row(id='rul_2', scope_level='USER', action_class='install',
                             decision='DENY', scope_ref='usr_1', locked=False,
                             match={}, boundary=None, outside='ASK', source='user',
                             expires_at=None))['locked'] is True


# ── what a task's capabilities make inevitable (rules.py:101-111) ───────────

def test_a_class_is_implied_once_however_often_it_is_named():
    """MUTANTS: `dict.fromkeys(action_classes)` -> `action_classes`
    (rules.py:104) and `seen.add(c)` removed (rules.py:110). The result feeds
    the classes the engine judges and the classes a plan may not declare, so
    a duplicate is a rule counted twice."""
    assert R.implied(['read', 'read', 'web']) == [('read', None), ('web', None)]
    assert R.implied([], ['shell', 'shell']) == [('exec', 'shell')]
    assert R.implied(['exec'], ['shell', 'code_edit']) == [('exec', None),
                                                           ('write_repo', 'code_edit')]
    # an unknown capability implies nothing, and never becomes a class itself
    assert R.implied(['read'], ['vision', 'nope']) == [('read', None)]


# ── globbing (rules.py:116-140) ─────────────────────────────────────────────

@pytest.mark.parametrize('path,pattern,want', [
    ('src\\a\\b.py', 'src/**', True),         # a Windows path in a posix boundary
    ('src/a/b.py', 'src\\**', True),          # and the other way round
    ('\\etc\\passwd', '/etc/**', False),      # a rooted path stays rooted
    ('C:\\work\\a.py', 'C:/**', False),       # a drive is never relative
    ('src\\..\\Windows\\x', '@workspace/**', False),   # the fail-open half
    ('..\\..\\x', '@workspace/**', False),
], ids=['bs-value', 'bs-pattern', 'bs-rooted', 'bs-drive', 'bs-escape-out',
        'bs-escape-upward'])
def test_a_path_is_read_with_one_separator_whatever_the_platform_says(path, pattern, want):
    """MUTANT: `_norm` -> `str(s)` (rules.py:117), i.e. the backslash stops
    being a separator, which is the ordinary spelling on the review machine.
    The deny side (`@workspace/**` containing a `\\` path) is only half of it:
    `_relative` splits on `/` alone, so a backslash-spelled `..` walk
    (`src\\..\\Windows\\x`) is no longer seen leaving the tree and a rule
    bounded to the workspace would approve it. test_policy_units.py:186 covers
    the posix spellings of the same escapes only."""
    assert R.inside(path, pattern) is want
    assert R.glob(pattern, path) is R.glob(pattern.replace('\\', '/'), path.replace('\\', '/'))


def test_a_question_mark_is_one_character_and_never_a_separator():
    """MUTANTS: the `?` arm of `_regex` (rules.py:129-131) deleted (the mark
    becomes a literal) or `[^/]` -> `.` (one character, any, crossing a
    segment). `archeus/*` and `@workspace/**` have no `?` in them, so nothing
    else reads this arm; a boundary pattern with one is a user's."""
    assert R.glob('a?b', 'axb') is True
    assert R.glob('a?b', 'a/b') is False      # never across a segment
    assert R.glob('a?b', 'ab') is False       # never nothing
    assert R.glob('a?b', 'a.b') is True
    assert R.glob('archeus/?ush/x', 'archeus/push/x') is True


def test_a_pattern_means_itself_apart_from_the_two_wildcards():
    """MUTANT: `re.escape(p[i])` -> `p[i]` (rules.py:133). A `.` in a host or
    a version would become "any character", so `good.example` would match the
    host `goodXexample`, and a `[` would open a character class nobody wrote.
    Every pattern the built-ins use happens to hold no regex metacharacter,
    so no existing test can see it."""
    assert R.glob('good.example', 'goodXexample') is False
    assert R.glob('v1.0/x', 'v1X0/x') is False
    assert R.glob('a[bc', 'a[bc') is True
    assert R.glob('good.example', 'good.example') is True
    # the same, on the path an approval is judged for
    allow = R.rule(id='w', scope_level='USER', action_class='web', decision='ALLOW',
                   scope_ref='usr_1', match={'host_glob': 'good.example'})
    assert R.matches(allow, act('web', host='goodXexample')) is False


# ── containment (rules.py:143-167) ──────────────────────────────────────────

@pytest.mark.parametrize('path,want', [
    ('src/a..b.py', True), ('src/..hidden/a.py', True), ('src/....//a', True),
    ('src/../etc/passwd', False), ('src/a/../../b', False), ('../src/a', False),
], ids=['dot-dot-in-a-name', 'dot-dot-prefix-name', 'dot-dot-run', 'escape-up',
        'escape-out', 'escape-first'])
def test_only_a_whole_dot_dot_segment_leaves_the_directory_tree(path, want):
    """MUTANT: `'..' in p.split('/')` -> `'..' in p` (rules.py:145). The
    substring version is the safe-looking one and the wrong one: it refuses
    `src/a..b.py`, a file inside the workspace, while every existing escape
    test still passes, because each of them does use a whole segment."""
    assert R.inside(path, 'src/**') is want


@pytest.mark.parametrize('path,want', [
    ('src/a*/b', True), ('srcx/a*/b', False), ('srcx/a', False),
    ('src/a', True), ('src', True), ('sr**', False),
], ids=['star-inside', 'star-other-tree', 'other-tree', 'inside', 'base-itself',
        'star-in-base-name'])
def test_a_path_with_a_wildcard_is_inside_only_if_its_literal_part_is(path, want):
    """MUTANTS: `startswith(base + '/')` -> `startswith(base)` in the wildcard
    arm (rules.py:166) — `srcx/a*/b` would be `src/**` again — and the arm
    returning True unconditionally. test_policy_units.py:186 covers the plain
    `src*/a`; the near-miss directory name is what tells the two apart."""
    assert R.inside(path, 'src/**') is want


# ── what an action says about itself (rules.py:170-182) ─────────────────────

def test_a_command_rule_reads_the_whole_command_line():
    """MUTANTS: `' '.join(action.argv)` -> `''.join(...)` or `action.argv[0]`
    (rules.py:176-177), and the `if action.argv else None` guard -> `else []`:
    an action that names no command must say nothing, so a permissive command
    rule cannot match it (§6.1, D3)."""
    allow = R.rule(id='c', scope_level='USER', action_class='exec', decision='ALLOW',
                   scope_ref='usr_1', match={'command_glob': 'git push*'})
    assert R.matches(allow, act('exec', argv=('git', 'push', 'origin'))) is True
    assert R.matches(allow, act('exec', argv=('git', 'pull'))) is False
    assert R.matches(allow, act('exec')) is False                 # says nothing
    assert R._values(act('exec', argv=('git', 'push')), 'command_glob') == ['git push']
    assert R._values(act('exec', argv=()), 'command_glob') is None


def test_an_action_never_answers_for_a_cost_band():
    """MUTANTS: the final `return None` of `_values` (rules.py:182) made into
    a getattr for the action's own claim, or the `max_cost_band` arm of
    check_boundary (rules.py:220-221) reached by reading the action: a plan's
    band is judged at the gate, so the answer to an action that claims one is
    "not said", which defers at plan/dispatch and is outside at the action
    stage. A rule bounded by a band the action itself vouches for is no bound."""
    assert R._values(act('spend'), 'max_cost_band') is None
    bounded = rule('USER', 'spend', 'ALLOW_WITHIN_BOUNDARY',
                   boundary={'max_cost_band': 'high'}, locked=True)
    plan = ev(act('spend'), bounded, stage='plan')
    assert plan['decision'] == 'ALLOW_WITHIN_BOUNDARY'
    assert plan['checks'] == {'checked': [], 'deferred': ['max_cost_band'], 'outside': []}
    action = ev(act('spend'), bounded, stage='action')
    assert action['decision'] == 'ASK'
    assert action['checks'] == {'checked': [], 'deferred': [], 'outside': ['max_cost_band']}


def test_an_ask_rule_matches_what_the_action_did_not_say_and_an_allow_never_does():
    """MUTANTS: `'ASK'` out of RESTRICTIVE (rules.py:18), or the `continue` /
    `return False` pair of matches() swapped (rules.py:189-192). The
    permissive half is tested in test_execution_units.py:244 (`command_glob`
    on a permissive rule); nothing tests the restrictive half on an ASK, where
    a class the profiles allow (`read`) has no other rule to fall back to."""
    asked = rule('PROJECT', 'read', 'ASK', match={'branch_glob': 'archeus/*'})
    assert R.matches(asked, act('read')) is True
    assert ev(act('read'), asked)['decision'] == 'ASK'
    allowed = rule('PROJECT', 'read', 'ALLOW', match={'branch_glob': 'archeus/*'})
    assert R.matches(allowed, act('read')) is False
    assert R.matches(allowed, act('read', branch='archeus/t')) is True


@pytest.mark.parametrize('wants', [{'environment': ['dev', 'staging']},
                                   {'environment': ('dev', 'staging')}],
                         ids=['list', 'tuple'])
def test_a_match_may_name_several_values_in_either_form(wants):
    """MUTANT: `isinstance(want, (list, tuple))` -> `isinstance(want, list)`
    (rules.py:194): a tuple from a stored row would be wrapped as one value,
    match nothing, and a DENY rule keyed on two environments would quietly
    stop applying (a list would still work, so the suite stays green)."""
    r = R.rule(id='m', scope_level='USER', action_class='deploy', decision='DENY',
               scope_ref='usr_1', match=wants)
    assert R.matches(r, act('deploy', environment='staging')) is True
    assert R.matches(r, act('deploy', environment='prod')) is False


def test_an_environment_is_named_exactly_where_a_path_is_globs():
    """MUTANTS: `key == 'environment'` in matches() (rules.py:195) dropped, so
    the environment goes through glob() like a path, or the membership test
    inverted. An action that names its environment `pr*d` would then match the
    rule written for `prod` — a wildcard the action chose, on the one attribute
    the prod floor is keyed to."""
    star = R.rule(id='s', scope_level='USER', action_class='deploy', decision='ALLOW',
                  scope_ref='usr_1', match={'environment': 'pr*d'})
    assert R.matches(star, act('deploy', environment='prod')) is False
    plain = R.rule(id='p', scope_level='USER', action_class='deploy', decision='ALLOW',
                   scope_ref='usr_1', match={'environment': 'prod'})
    assert R.matches(plain, act('deploy', environment='prod')) is True
    assert R.matches(plain, act('deploy', environment='production')) is False


def test_a_path_match_needs_only_one_of_the_paths_the_action_touches():
    """MUTANT: the `any(... for w in wants for v in vals)` of matches()
    (rules.py:197) -> `all(...)`. A match is "does this rule speak about this
    action", and it says yes when any touched path is in scope — the opposite
    of a boundary, where every path must hold (pinned below). Flipping the
    two would loosen the match side and tighten the boundary side at once."""
    r = R.rule(id='p', scope_level='USER', action_class='write_repo', decision='DENY',
               scope_ref='usr_1', match={'paths': ['src/**']})
    assert R.matches(r, act('write_repo', paths=['src/a.py', 'docs/b.md'])) is True
    assert R.matches(r, act('write_repo', paths=['src/a.py'])) is True
    assert R.matches(r, act('write_repo', paths=['docs/a.md', 'docs/b.md'])) is False
    # the permissive twin: an action that names no path never reaches it (D3)
    permissive = R.rule(id='q', scope_level='USER', action_class='write_repo',
                        decision='ALLOW', scope_ref='usr_1', match={'paths': ['src/**']})
    assert R.matches(permissive, act('write_repo')) is False
    assert R.matches(permissive, act('write_repo', paths=['src/a.py'])) is True


# ── the boundary predicates (rules.py:204-225) ──────────────────────────────

def test_every_path_an_action_touches_must_be_inside_the_boundary():
    """MUTANT: the outer `all(... for v in vals)` of the paths arm
    (rules.py:216-217) -> `any(...)`. One path in the workspace would then
    carry the rest of them out with it. test_policy_units.py:151 and :176 put
    one path in each action only, and so does test_execution_units.py:244."""
    inside = R.check_boundary({'paths': ['src/**']}, act('write_repo', paths=['src/a.py']),
                              'action')
    assert inside == {'checked': ['paths'], 'deferred': [], 'outside': []}
    mixed = R.check_boundary({'paths': ['src/**']},
                             act('write_repo', paths=['src/a.py', 'docs/b.md']), 'action')
    assert mixed == {'checked': [], 'deferred': [], 'outside': ['paths']}
    both = R.check_boundary({'paths': ['src/**']},
                            act('write_repo', paths=['src/a.py', 'docs/b.md']), 'plan')
    assert both['outside'] == ['paths']


def test_the_environments_an_action_names_must_all_be_allowed():
    """MUTANTS: the `environments` arm (rules.py:218-219) — `v in allowed`
    inverted, or the `all` loosened — and the arm being reached at all when
    the action names no environment. Nothing in the suite puts an `environments`
    key through a boundary that is checked: tests/v1/integration/test_policy_http.py:153
    only asks for a 400 on a malformed one."""
    dev = R.check_boundary({'environments': ['dev', 'staging']},
                           act('deploy', environment='dev'), 'action')
    assert dev == {'checked': ['environments'], 'deferred': [], 'outside': []}
    prod = R.check_boundary({'environments': ['dev', 'staging']},
                            act('deploy', environment='prod'), 'action')
    assert prod == {'checked': [], 'deferred': [], 'outside': ['environments']}
    quiet = R.check_boundary({'environments': ['dev']}, act('deploy'), 'action')
    assert quiet == {'checked': [], 'deferred': [], 'outside': ['environments']}


def test_one_allowed_pattern_is_enough_for_a_value_and_every_value_must_be_covered():
    """MUTANTS: the `any(glob(a, v) for a in allowed)` of the last arm
    (rules.py:222-223) -> `all(...)` — nothing would be allowed but the
    intersection — and `glob(a, v)` written the other way round, which reads
    the action's branch as the pattern and the boundary as the value.
    test_execution_units.py:244 checks one allowed glob only."""
    one_of_two = R.check_boundary({'branches': ['archeus/*', 'rel/*']},
                                 act('git_push', branch='rel/x'), 'action')
    assert one_of_two == {'checked': ['branches'], 'deferred': [], 'outside': []}
    neither = R.check_boundary({'branches': ['archeus/*', 'rel/*']},
                              act('git_push', branch='main'), 'action')
    assert neither == {'checked': [], 'deferred': [], 'outside': ['branches']}
    hosts = R.check_boundary({'hosts': ['good.example']}, act('web', host='good.example'),
                            'action')
    assert hosts == {'checked': ['hosts'], 'deferred': [], 'outside': []}


def test_the_predicates_are_listed_in_one_fixed_order_whatever_the_rule_said_them_in():
    """MUTANT: `sorted(boundary)` -> `boundary` (rules.py:210). The lists land
    in the decision record and in its hash, so their order has to be a fact of
    the module and not of how one rule's JSON happened to be written — a rule
    re-saved with the same predicates in another order would otherwise read as
    a different decision. No existing boundary has more than one key."""
    action = act('git_push', paths=['src/a.py'], branch='archeus/t', host='good.example')
    forward = R.check_boundary({'paths': ['src/**'], 'branches': ['archeus/*'],
                               'hosts': ['good.example']}, action, 'action')
    back = R.check_boundary({'hosts': ['good.example'], 'branches': ['archeus/*'],
                             'paths': ['src/**']}, action, 'action')
    assert forward == back == {'checked': ['branches', 'hosts', 'paths'],
                              'deferred': [], 'outside': []}


# ── the profiles, from the same read (rules.py:34-52) ───────────────────────

def test_a_profile_answers_for_every_class_a_rule_can_name():
    """MUTANTS: `_profile` iterating ACTION_CLASSES instead of RULE_CLASSES
    (rules.py:35) — `mission.start` would have no answer at all — and the
    table carrying a class no rule may name. test_policy_units.py:134 checks
    `builtin()` only, which is the careful table at GLOBAL."""
    for name in ('careful', 'standard', 'autonomous'):
        assert set(R.PROFILES[name]) == set(RULE_CLASSES), name
        assert R.PROFILES[name]['mission.start'][0] == ('ASK' if name == 'careful'
                                                        else 'ALLOW'), name
    assert R.PROFILES['standard']['write_repo'] == ('ALLOW_WITHIN_BOUNDARY',
                                                    {'paths': ['@workspace/**']})
    assert R.PROFILES['autonomous']['git_push'] == ('ALLOW_WITHIN_BOUNDARY',
                                                    {'branches': ['archeus/*']})
    assert R.PROFILES['standard']['git_push'] == ('ASK', None)

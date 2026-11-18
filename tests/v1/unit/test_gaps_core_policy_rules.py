"""Gap tests for archeus/core/policy/rules.py (T-315): the fail-closed and
denial paths of the rule shape, the D3 matching rule, the boundary predicates
and the precedence tables. Pure: no I/O, no clock, no OS — every input is a
literal string, so these read the same on Linux and Windows.

Each test names the source branch (rules.py line) whose removal or inversion
it would catch. The companion list is in /work/QWEN-DONE-T-315.md.
"""

from types import SimpleNamespace

import pytest

from archeus.core.domain.actions import RULE_CLASSES, Action
from archeus.core.policy import rules as R


def act(cls, **kw):
    return Action(action_class=cls, target=kw.pop('target', 'task:t1'), **kw)


def rule(**kw):
    kw.setdefault('id', 'r')
    kw.setdefault('scope_level', 'USER')
    kw.setdefault('action_class', 'exec')
    return R.rule(**kw)


def row(**kw):
    """A PolicyRule row: from_entity only ever reads these eleven attributes."""
    base = dict(id='p1', scope_level='USER', action_class='exec', decision='ALLOW',
                scope_ref='usr_1', locked=None, match=None, boundary=None,
                outside='ASK', source='user', expires_at=None)
    base.update(kw)
    return SimpleNamespace(**base)


# ── the rule shape: locked and the fail-closed defaults (rules.py:55-62) ─────

def test_a_user_deny_is_locked_even_when_the_row_says_otherwise():
    """rules.py:60 — `locked or decision == 'DENY'`: a DENY that could be
    unlocked is a deeper ALLOW winning over it (deny-over-allow fail-open)."""
    assert rule(decision='DENY')['locked'] is True                    # derived (None)
    assert rule(decision='DENY', locked=False)['locked'] is True      # lie refused
    assert rule(decision='ASK')['locked'] is False                    # not auto-locked
    assert rule(decision='ASK', locked=True)['locked'] is True
    assert rule(decision='ALLOW', locked=True)['locked'] is True
    assert R.FLOOR[0]['locked'] is True and R.FLOOR[1]['locked'] is True   # rules.py:66-71
    assert R.ESTOP['locked'] is True and R.MISSING['locked'] is True       # rules.py:75-78
    assert R.from_entity(row(decision='DENY', locked=False))['locked'] is True


def test_a_malformed_outside_falls_back_to_ask_never_to_nothing():
    """rules.py:62 — `outside or 'ASK'`: the engine takes
    max(STRICTNESS[r['outside']]) over AWB rules (engine.py:100); a None or
    '' outside must land on the strict-enough default, never on ALLOW."""
    assert rule(decision='ALLOW_WITHIN_BOUNDARY', outside=None)['outside'] == 'ASK'
    assert rule(decision='ALLOW', outside='')['outside'] == 'ASK'
    assert rule(decision='ALLOW', outside='DENY')['outside'] == 'DENY'
    assert R.from_entity(row(outside=None))['outside'] == 'ASK'


def test_the_rule_shape_survives_junk_and_copies_its_dicts():
    """rules.py:55-62 — `**_ignored` (a stale row column must not crash the
    engine), `dict(match or {})`, `dict(boundary) if boundary else None`:
    the rule must not alias the caller's dicts (a replay snapshot mutates)."""
    m = {'environment': 'prod'}
    b = {'paths': ['src/**']}
    r = rule(decision='ALLOW', match=m, boundary=b, note='x', revision=2, retired_at=None)
    assert sorted(r) == sorted(          # exactly the eleven keys the engine reads
        'id scope_level scope_ref action_class decision locked match boundary '
        'outside source expires_at'.split())
    assert r['match'] is not m and r['boundary'] is not b
    assert rule(decision='ALLOW', match=None)['match'] == {}
    assert rule(decision='ALLOW', boundary={})['boundary'] is None


def test_from_entity_reads_the_row_as_the_same_shape():
    """rules.py:94-98 — an unmapped or dropped column is a silently different
    rule; every attribute of the row must reach the dict the engine reads."""
    m = {'host_glob': 'github.com'}
    b = {'branches': ['archeus/*']}
    got = R.from_entity(row(decision='ASK', locked=True, match=m, boundary=b,
                            expires_at='2026-01-01T00:00:00Z', source='user'))
    assert got == {'id': 'p1', 'scope_level': 'USER', 'scope_ref': 'usr_1',
                   'action_class': 'exec', 'decision': 'ASK', 'locked': True,
                   'match': m, 'boundary': b, 'outside': 'ASK', 'source': 'user',
                   'expires_at': '2026-01-01T00:00:00Z'}
    assert got['match'] is not m and got['boundary'] is not b


# ── D3 matching (rules.py:170-201) ───────────────────────────────────────────

def test_an_action_that_names_no_host_still_meets_a_restrictive_host_rule():
    """rules.py:191-192 — an attribute the action does not carry matches the
    restrictive side (continue): a missing host must not dodge an ASK/DENY."""
    ask = rule(action_class='git_push', decision='ASK', match={'host_glob': 'github.com'})
    assert R.matches(ask, act('git_push')) is True                      # host unknown
    assert R.matches(ask, act('git_push', host='evil.example')) is False
    deny = rule(action_class='web', decision='DENY', match={'host_glob': 'billing.example'})
    assert R.matches(deny, act('web')) is True


def test_an_action_that_names_no_host_never_meets_a_permissive_host_rule():
    """rules.py:193 — the permissive side returns False: ALLOW and
    ALLOW_WITHIN_BOUNDARY (not in RESTRICTIVE, rules.py:19) must not claim an
    action whose host is unknown — that is the fail-open D3 closes."""
    for decision in ('ALLOW', 'ALLOW_WITHIN_BOUNDARY'):
        allow = rule(action_class='git_push', decision=decision,
                     match={'host_glob': 'github.com'}, boundary={'paths': ['src/**']})
        assert R.matches(allow, act('git_push')) is False
    allow = rule(action_class='git_push', decision='ALLOW', match={'host_glob': 'github.com'})
    assert R.matches(allow, act('git_push', host='github.com')) is True


@pytest.mark.parametrize('want', ['pr*d', ['pr*d', 'prod?'], ('pr*d',)])
def test_an_environment_is_matched_by_membership_never_by_glob(want):
    """rules.py:195-196 — `environment` is the one key compared with `in
    wants`; if it fell to the glob branch, 'pr*d' would match 'prod' and a
    permissive rule would reach prod actions it was not written for."""
    allow = rule(action_class='deploy', decision='ALLOW', match={'environment': want})
    assert R.matches(allow, act('deploy', environment='prod')) is False
    ask = rule(action_class='deploy', decision='ASK', match={'environment': want})
    assert R.matches(ask, act('deploy', environment='prod')) is False   # named: real match
    listing = rule(action_class='deploy', decision='ALLOW', match={'environment': want})
    assert R.matches(listing, act('deploy', environment='pr*d')) is True  # membership is exact


def test_a_want_may_be_a_list_or_a_tuple_of_patterns():
    """rules.py:194 — the `isinstance(want, (list, tuple))` branch: without
    it a list want becomes one string pattern and matches nothing (or worse)."""
    for want in (['github.com', 'gitlab.com'], ('github.com', 'gitlab.com')):
        allow = rule(action_class='git_push', decision='ALLOW', match={'host_glob': want})
        assert R.matches(allow, act('git_push', host='gitlab.com')) is True
        assert R.matches(allow, act('git_push', host='bitbucket.org')) is False


def test_a_cost_band_or_unknown_match_key_never_reaches_a_permissive_rule():
    """rules.py:182 + 190-193 — an attribute the action never carries (cost
    band, or any unrecognised key) yields None: restrictive matches (fail
    closed), permissive does not match at all. A typo in a match key must
    never widen what an ALLOW covers."""
    assert R.matches(rule(decision='ALLOW', match={'min_cost_band': 'low'}),
                     act('exec')) is False
    assert R.matches(rule(decision='ASK', match={'min_cost_band': 'low'}),
                     act('exec')) is True
    assert R.matches(rule(decision='DENY', match={'nonsense': 'x'}), act('exec')) is True
    # a malformed rule dict: no usable match at all still matches (engine reads
    # `r.get('match') or {}`, rules.py:188) — the class/level still gate it
    assert R.matches({'decision': 'DENY'}, act('exec')) is True
    assert R.matches({'decision': 'ALLOW', 'match': None}, act('exec')) is True


def test_a_command_glob_matches_the_joined_argv_only_when_there_is_one():
    """rules.py:176-177 — `' '.join(action.argv)` (a wrong join or an argv of
    () must read as "says nothing", routing to the D3 branches 190-193)."""
    allow = rule(action_class='exec', decision='ALLOW', match={'command_glob': 'git push*'})
    assert R.matches(allow, act('exec', argv=['git', 'push', 'origin'])) is True
    assert R.matches(allow, act('exec', argv=['gitpush', 'origin'])) is False
    assert R.matches(allow, act('exec')) is False                      # no argv at all
    assert R.matches(allow, act('exec', argv=[])) is False             # empty: says nothing
    ask = rule(action_class='exec', decision='ASK', match={'command_glob': 'git push*'})
    assert R.matches(ask, act('exec')) is True                          # D3 restrictive side


# ── check_boundary (rules.py:204-225) ────────────────────────────────────────

def test_the_hosts_boundary_globs_its_patterns_over_the_named_host():
    """rules.py:222-223 — the else branch, `glob(a, v)` (pattern=allowed,
    value=host; swapped arguments would invert who may contain wildcards) and
    rules.py:213-214 — hosts unknown: deferred off the action stage, outside
    on it (fail closed: an unprovable host boundary at the action stage)."""
    ok = act('git_push', host='a.internal.io')
    assert R.check_boundary({'hosts': ['github.com', '*.internal.io']}, ok, 'action') == \
        {'checked': ['hosts'], 'deferred': [], 'outside': []}
    out = act('git_push', host='evil.example')
    assert R.check_boundary({'hosts': ['github.com']}, out, 'action')['outside'] == ['hosts']
    # direction: the allowed side may carry the wildcards, the host may not
    assert R.check_boundary({'hosts': ['git*hub.com']}, act('git_push', host='github.com'),
                            'action')['checked'] == ['hosts']
    silent = act('git_push')
    assert R.check_boundary({'hosts': ['github.com']}, silent, 'plan')['deferred'] == ['hosts']
    assert R.check_boundary({'hosts': ['github.com']}, silent, 'dispatch')['deferred'] == \
        ['hosts']
    assert R.check_boundary({'hosts': ['github.com']}, silent, 'action')['outside'] == \
        ['hosts']


def test_an_environments_boundary_admits_only_listed_environments():
    """rules.py:218-219 — membership (`v in allowed`), not glob: 'dev*' must
    not name an environment, and the named environment must be judged on the
    action's own value (rules.py:172-173)."""
    a = act('web', environment='staging')
    assert R.check_boundary({'environments': ['dev', 'staging']}, a, 'action')['checked'] == \
        ['environments']
    assert R.check_boundary({'environments': ['dev']}, a, 'action')['outside'] == \
        ['environments']
    assert R.check_boundary({'environments': ['dev*']}, act('web', environment='dev*'),
                            'plan')['checked'] == ['environments']   # exact string only
    # and the listed side never acts as a pattern: 'dev*' admits only the name 'dev*'
    assert R.check_boundary({'environments': ['dev*']}, act('web', environment='dev'),
                            'action')['outside'] == ['environments']


def test_a_cost_band_boundary_is_deferred_then_never_provable_at_the_action_stage():
    """rules.py:213-214 with rules.py:182 — an action never carries a cost
    band, so at the action stage the boundary is *outside* (fail closed: the
    AWB rule can never be satisfied there, the engine escalates on `outside`),
    while plan/dispatch defer it. Catches inverting the stage test."""
    a = act('exec')
    assert R.check_boundary({'max_cost_band': 'high'}, a, 'action') == \
        {'checked': [], 'deferred': [], 'outside': ['max_cost_band']}
    assert R.check_boundary({'max_cost_band': 'high'}, a, 'plan')['deferred'] == \
        ['max_cost_band']
    assert R.check_boundary({'max_cost_band': 'high'}, a, 'dispatch')['deferred'] == \
        ['max_cost_band']


def test_every_value_of_every_key_is_judged_and_the_lists_come_back_sorted():
    """rules.py:210,217,225 — one bad value poisons its key (all()), several
    allowed patterns can each satisfy a value, and keys are sorted so the
    result (and the recorded reason) is deterministic."""
    a = act('git_push', branch='archeus/m.t', host='evil.example')
    assert R.check_boundary({'branches': ['archeus/*'], 'hosts': ['github.com']},
                            a, 'action') == \
        {'checked': ['branches'], 'deferred': [], 'outside': ['hosts']}
    # all() must stay conjunctive: one path outside makes the key outside
    assert R.check_boundary({'paths': ['src/**']},
                            act('write_repo', paths=['src/a', 'docs/b']),
                            'action')['outside'] == ['paths']
    # each path may be inside a *different* allowed pattern
    assert R.check_boundary({'paths': ['src/**', 'tests/**']},
                            act('write_repo', paths=['src/a', 'tests/b']),
                            'action')['checked'] == ['paths']


# ── glob and inside (rules.py:116-167) ───────────────────────────────────────

@pytest.mark.parametrize('pattern,value,ok', [
    ('a.b', 'axb', False),        # rules.py:132-133 — re.escape: '.' must stay literal
    ('a.b', 'a.b', True),
    ('a?b', 'axb', True),         # rules.py:129-130 — '?' one char, never a separator
    ('a?b', 'a/b', False),
    ('src/**', 'src', False),     # rules.py:123-125 — '**' needs the separator (vs inside)
    ('src/**', 'src/a/b.py', True),
    ('archeus/*', 'archeus\\t1', True),      # rules.py:116-117 — backslash normalised
    ('archeus\\*', 'archeus/t1', True),       # ...on either side
    ('archeus/*', 'archeus\\a\\b', False),    # a single star never crosses a segment
    ('**', 'a/b c.py', True),
])
def test_glob_escapes_metacharacters_and_bounds_each_star(pattern, value, ok):
    assert R.glob(pattern, value) is ok


@pytest.mark.parametrize('path,pattern,ok', [
    ('src/a/*.py', 'src/**', True),      # rules.py:164-166 — provable literal prefix
    ('src/[abc].py', 'src/**', True),
    ('[x]src/a', 'src/**', False),       # wildcard in the first segment: not provable
    ('a/b', '**', True),                 # rules.py:162-163 — empty base admits anything relative
    ('x', '@workspace', False),          # rules.py:159-160 — a bare token is exact, not a root
    ('src', '@workspace/src', True),     # rules.py:154-155 — the token strips, then exact
    ('src/a', '@workspace/src', False),
])
def test_inside_proves_only_what_the_literal_prefix_warrants(path, pattern, ok):
    assert R.inside(path, pattern) is ok


@pytest.mark.parametrize('path', ['\\\\server\\share\\x',      # UNC -> '/server/...'
                                  'C:Users\\x',                  # drive-relative, rules.py:145
                                  'C:/Windows/x',
                                  '\\\\?\\src\\a',               # win32 namespace
                                  'a/../../b',
                                  '/etc/x'])
def test_a_path_that_is_not_workspace_relative_is_never_inside(path):
    """rules.py:143-145+151-152 — absolute, drive or `..` paths fail closed
    before any pattern is read (backslashes normalise first, rules.py:116)."""
    assert R.inside(path, '**') is False
    assert R.inside(path, '@workspace/**') is False


def test_inside_reads_windows_paths_as_paths():
    """rules.py:116-117 in inside(): the same string, written with
    backslashes, must judge identically on every platform (pure string, no OS)."""
    assert R.inside('src\\a.py', 'src/**') is True
    assert R.inside('src\\a.py', '@workspace\\**') is True
    assert R.inside('docs\\a.md', 'src/**') is False


# ── profiles, builtins, tables (rules.py:14-30, 81-91, 101-111) ─────────────

def test_profile_rules_expand_unlocked_versioned_and_copied():
    """rules.py:81-86 — a locked profile rule would let a profile silence
    itself out of the floor; the version in the id is the replay identity;
    `boundary` must not alias the module constant (rules.py:61 copy)."""
    pr = R.profile_rules('standard', 'USER', 'usr_1')
    assert {r['action_class'] for r in pr} == set(RULE_CLASSES)
    assert all(r['locked'] is False for r in pr)
    assert all(r['source'] == 'profile' and r['scope_ref'] == 'usr_1' for r in pr)
    assert 'profile:standard@%d:USER:write_repo' % R.PROFILES_VERSION in \
        {r['id'] for r in pr}
    assert all(r['boundary'] is not R._IN_WORKSPACE for r in pr if r['boundary'])


def test_builtin_is_the_floor_plus_careful_and_a_fresh_container():
    """rules.py:89-91 — `list(FLOOR)` and the locked floors are the fail-closed
    baseline; a caller mutating its list must not poison the next one. A
    profile name that does not exist raises (rules.py:86) rather than
    silently expanding nothing."""
    b = R.builtin()
    assert {r['action_class'] for r in b} == set(RULE_CLASSES)
    assert sum(1 for r in b if r['id'].startswith('builtin:floor')) == 2
    assert all(r['decision'] != 'DENY' or r['locked'] for r in b)   # every DENY locked
    b.append('junk')
    assert 'junk' not in R.builtin()
    with pytest.raises(KeyError):
        R.profile_rules('bogus', 'USER')


def test_declared_classes_are_deduplicated_before_the_implied_ones():
    """rules.py:104-111 — dict.fromkeys dedup and the `not in seen` guard:
    a repeated or already-declared class must appear exactly once, or the
    dispatch contract would ask twice for one class."""
    assert R.implied(['read', 'read', 'exec']) == [('read', None), ('exec', None)]
    assert R.implied([], ['code_edit', 'code_edit']) == [('write_repo', 'code_edit')]
    assert R.implied(['write_repo'], ['code_edit', 'shell']) == \
        [('write_repo', None), ('exec', 'shell')]
    assert R.implied(['read'], ['vision', 'nope']) == [('read', None)]


def test_the_precedence_tables_are_strict_orders():
    """rules.py:16-19,23 — engine.py sorts applicable and effective rules by
    STRICTNESS and _depth by LEVELS: an inverted table entry (DENY <= ASK, or
    TASK shallower than GLOBAL) decides every conflict the wrong way, so the
    tables themselves are pinned here (their use is covered by the engine's
    precedence tests in test_policy_units.py)."""
    assert [R.STRICTNESS[d] for d in ('ALLOW', 'ALLOW_WITHIN_BOUNDARY', 'ASK', 'DENY')] == \
        [0, 1, 2, 3]
    assert set(R.STRICTNESS) == set(('ALLOW', 'ALLOW_WITHIN_BOUNDARY', 'ASK', 'DENY'))
    assert R.LEVELS == ('GLOBAL', 'USER', 'WORKSPACE', 'PROJECT', 'MISSION', 'TASK')
    assert set(R.RESTRICTIVE) == {'ASK', 'DENY'}             # AWB/ALLOW are not (D3)
    assert [R.COST_BANDS.index(b) for b in ('low', 'medium', 'high')] == [0, 1, 2]
    assert R.IMPLIED == {'code_edit': 'write_repo', 'shell': 'exec', 'web': 'web'}

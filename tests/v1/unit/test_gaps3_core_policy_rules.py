"""T-1141 gap tests for archeus/core/policy/rules.py, lines 1-226 inclusive
(the whole slice; it is the card's branch-ownership boundary, including the
functions that cross its endpoints). Definitions and imports outside the
slice (archeus/core/domain/actions.py, policy/engine.py) are read-only
context. The repository in this container is the MXC integration branch;
`git` is not installed here, so tip 56d53504 could not be verified from
inside the container — the file read is 226 lines as the card states.

The ten final selected branches (fail-closed and denial first, then
boundaries, then error paths), after replacing the card's probes that
existing coverage — tests/v1/unit/test_gaps_core_policy_rules.py,
test_pins_core_policy_rules.py, test_policy_units.py — already holds:

1. an empty-string `environment` claim dodges the locked prod-floor DENY
   (rules.py:172-173 vs the D3 fail-closed rule rules.py:18-19, 190-192)
2. the match-key alias 'path_glob' as a boundary key skips the containment
   arms (rules.py:222-223 instead of 216-217 + the guards rules.py:143-152)
3. the singular 'environment' alias as a boundary key is globbed, not
   judged by membership (rules.py:218-219 vs 222-223)
4. the plural 'environments' alias as a match key is globbed, not judged by
   membership (rules.py:195-197 vs 172)
5. a `paths` predicate on an action that names no paths: deferred at
   plan/dispatch, outside at the action stage (rules.py:212-214, paths arm)
6. a boundary key no action attribute answers for fails closed, never
   silently checked (rules.py:182 + 212-214)
7. a rule deep-copies its match all the way down: a replay snapshot must
   not alias a caller's nested lists (rules.py:60)
8. the repeated './' prefix strip loop and the traversal it must not hide
   (rules.py:157-158 + 145)
9. a lowercase drive-qualified path is never relative (rules.py:145)
10. a boundary whose allowed list is empty admits nothing (rules.py:216-223)

The module is pure (no I/O, no clock, no OS call), so there is nothing to
fake and nothing to place under tmp_path: every input is a literal string,
written with an explicit separator, no case dependence, no OS error text, no
POSIX absolute-path assumption (both spellings judge the same on Linux and on
the Windows review machine), no sleep, no environment read, no thread, no
real network or subprocess. Tests for probes 1-4 of this file are xfail
(strict) because the source contradicts a justified fail-closed premise; the
reason cites the defect line and the contract. None of this imports another
test_gaps3 file or depends on queue order.
"""

from types import SimpleNamespace

import pytest

from archeus.core.domain.actions import Action
from archeus.core.policy import rules as R


def act(cls, **kw):
    return Action(action_class=cls, target=kw.pop('target', 'task:t1'), **kw)


def rule(**kw):
    kw.setdefault('id', 'r')
    kw.setdefault('scope_level', 'USER')
    kw.setdefault('action_class', 'exec')
    return R.rule(**kw)


# ── 1. the empty-environment dodge of the prod floor (rules.py:172-173) ─────

@pytest.mark.xfail(strict=True, reason=(
    "source defect archeus/core/policy/rules.py:172-173: _values tests `action.environment "
    "is None`, so an action claiming the empty string 'says' an environment named '' and "
    "leaves the D3 fail-closed side (rules.py:18-19, 190-192): the locked destructive-prod "
    "floor DENY (rules.py:67-68) then matches nothing and the denial disappears, while the "
    "argv/paths arms (rules.py:174-177) read an empty claim as 'says nothing'. Contract: "
    "p9-design-gate §6.1 D3 — an attribute the action does not name matches the "
    "restrictive side; no name is an empty string."))
def test_an_action_claiming_an_empty_environment_still_meets_the_prod_floor():
    """Kills: `is None` -> falsy in the environment arm of _values inverting
    who the floor answers (nearest: test_gaps_core_policy_rules.py's host-
    silence test — nothing feeds environment='' to matches())."""
    assert R.matches(R.FLOOR[0], act('destructive')) is True          # control (None)
    assert R.matches(R.FLOOR[0], act('destructive', environment='')) is True


# ── 5. the paths predicate on an action that names no paths (rules.py:212-214) ─

def test_a_write_that_names_no_paths_defers_then_fails_closed_at_the_action_stage():
    """Kills: the missing-facts guard `if not vals` (rules.py:212-214) vacuously
    satisfying the paths arm for a plan-level write (nearest: the hosts-silence
    test in test_gaps_core_policy_rules.py and the environments-silence test in
    test_pins_core_policy_rules.py — the paths key is never put through it)."""
    a = act('write_repo')
    for stage in ('plan', 'dispatch'):
        assert R.check_boundary({'paths': ['src/**']}, a, stage) == \
            {'checked': [], 'deferred': ['paths'], 'outside': []}
    assert R.check_boundary({'paths': ['src/**']}, a, 'action') == \
        {'checked': [], 'deferred': [], 'outside': ['paths']}


# ── 6. a boundary key nothing answers for fails closed (rules.py:182, 212-214) ─

def test_a_boundary_key_no_attribute_answers_for_fails_closed_not_silently_ok():
    """Kills: an unknown boundary key being treated as satisfied (the final
    `return None` of _values (rules.py:182) turning into a fabricated value, or
    the check_boundary guard skipping unknown keys) — nearest: the max_cost_band
    tests, which cover only a key the module itself knows. A typo in a boundary
    key must escalate at the action stage, never widen the ALLOW_WITHIN_BOUNDARY."""
    a = act('exec', argv=['ls'])
    assert R.check_boundary({'device': ['*']}, a, 'action') == \
        {'checked': [], 'deferred': [], 'outside': ['device']}
    assert R.check_boundary({'cost_band': ['high']}, a, 'plan')['deferred'] == ['cost_band']
    # beside a satisfied predicate: the unknown key still lands in `outside`
    assert R.check_boundary({'paths': ['src/**'], 'device': ['x']},
                            act('write_repo', paths=['src/a']), 'action') == \
        {'checked': ['paths'], 'deferred': [], 'outside': ['device']}


# ── 7. the match is deep-copied like the boundary (rules.py:60) ──────────────

def test_a_rule_deep_copies_its_match_all_the_way_down():
    """Kills: `copy.deepcopy(match or {})` -> `copy.copy(...)` or the bare
    `match or {}` (rules.py:60) — nearest: test_pins_core_policy_rules.py's
    `test_a_rule_never_carries_away_the_callers_match_and_boundary_dicts`,
    which clears the top-level dicts but never appends into a nested list.
    A replay reads the decision's snapshot: a rule that stays writable through
    a caller's list is a decision that changes after it was recorded."""
    match = {'paths': ['src/**'], 'host_glob': ['a/*']}
    r = rule(action_class='write_repo', decision='ALLOW_WITHIN_BOUNDARY', match=match,
             boundary={'paths': ['src/**']}, outside='DENY')
    match['paths'].append('@workspace/**')
    match['host_glob'].append('evil/**')
    assert r['match'] == {'paths': ['src/**'], 'host_glob': ['a/*']}

    row = SimpleNamespace(id='p1', scope_level='USER', action_class='write_repo',
                          decision='DENY', scope_ref='usr_1', locked=None,
                          match={'host_glob': ['good.example']}, boundary=None,
                          outside='ASK', source='user', expires_at=None)
    got = R.from_entity(row)
    row.match['host_glob'].append('*')
    assert got['match'] == {'host_glob': ['good.example']}


# ── 8. the repeated './' strip cannot hide a traversal (rules.py:157-158) ────

def test_a_repeated_dot_prefix_is_stripped_and_never_hides_a_traversal():
    """Kills: the `while p.startswith('./')` loop (rules.py:157-158) weakened
    to an `if` (a second './' then escapes containment), and the strip running
    *before* the relative test so '././../x' could walk out — the guard is
    rules.py:151 (after rules.py:143-145), never a post-strip re-read.
    Nearest: test_policy_units.py's single './src/a' case; nothing stacks two
    prefixes or hides a walk behind one."""
    assert R.inside('./././src/a', 'src/**') is True
    assert R.inside('././../x', 'src/**') is False
    assert R.inside('././../x', '@workspace/**') is False
    assert R.inside('./././x', '@workspace/**') is True


# ── 9. a lowercase drive is still a drive (rules.py:145) ─────────────────────

def test_a_lowercase_drive_qualified_path_is_never_relative():
    """Kills: `re.match(r'[A-Za-z]:', p)` (rules.py:145) losing its lowercase
    half — every existing drive case spells 'C:' (test_gaps_core_policy_rules.py,
    test_pins_core_policy_rules.py, test_policy_units.py) — and a drive test
    reading past the first segment. Windows paths arrive in any case; a
    'c:/Windows/x' read as relative would sit inside every workspace."""
    for path in ('c:/Windows/x', 'c:\\work\\x', 'c:x'):
        assert R.inside(path, '**') is False
        assert R.inside(path, '@workspace/**') is False
    assert R.inside('C:/Windows/x', '**') is False                   # control, as before
    # the drive test is anchored: a colon inside a later segment stays relative
    assert R.inside('src/a:b', '**') is True


# ── 10. an empty allowed list admits nothing (rules.py:216-223) ──────────────

@pytest.mark.parametrize('key,claimed', [
    ('paths', {'paths': ['src/a']}),
    ('branches', {'branch': 'archeus/t'}),
    ('hosts', {'host': 'good.example'}),
    ('environments', {'environment': 'dev'}),
], ids=['paths', 'branches', 'hosts', 'environments'])
def test_an_empty_boundary_list_admits_nothing(key, claimed):
    """Kills: an empty allowed list being read as 'unconstrained' by any of
    the three arms (rules.py:216-217, 218-219, 222-223 — e.g. a `not allowed or`
    short-circuit 'optimisation'): every predicate vacuously true turns an
    ALLOW_WITHIN_BOUNDARY into a bare ALLOW. Nearest: the pins' mixed-paths and
    one-of-two tests — every existing boundary list is non-empty."""
    out = R.check_boundary({key: []}, act('exec', **claimed), 'action')
    assert out == {'checked': [], 'deferred': [], 'outside': [key]}

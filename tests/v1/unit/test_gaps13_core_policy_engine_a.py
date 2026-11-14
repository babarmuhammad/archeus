"""T-1454: the branches of `archeus/core/policy/engine.py` that the existing policy
tests leave open: the order candidate_rules builds its list in (built-in, then
profiles, then the user's rules), a falsy USER profile that expands nothing while
a MISSION one still does (candidate_rules 57-62), a locked rule that is itself the
specific one listed once (_one 85-86), and a user rule one level deeper than a
built-in beating a stricter built-in (_depth 36, _order 41).
"""

from archeus.core.domain.actions import Action
from archeus.core.policy import engine as E
from archeus.core.policy import rules as R

CHAIN = {'USER': 'usr_1', 'PROJECT': 'prj_1', 'TASK': 'tsk_1'}


def _act(cls):
    return Action(action_class=cls, target='task:t1')


def test_user_rules_come_after_the_builtin_and_profile_rules(monkeypatch):
    """engine.py:59-63 — built-in first, then the expanded profiles, then the
    rules the context carries. A reordering changes which of two equal-depth,
    equal-strictness rules sorts first in `matched`."""
    monkeypatch.setattr(R, 'builtin', lambda: [{'id': 'b'}])
    monkeypatch.setattr(R, 'profile_rules', lambda name, level, ref=None: [{'id': 'p:' + level}])
    out = E.candidate_rules({'rules': [{'id': 'u'}]})
    assert [r['id'] for r in out] == ['b', 'p:USER', 'u']


def test_a_falsy_user_profile_expands_nothing_and_the_mission_one_still_does(monkeypatch):
    """engine.py:60-62 — `if profiles.get(level)`: a USER value of None or '' is a
    profile that is not there, while the MISSION profile in the same dict is
    expanded. Testing the dict rather than the value would expand None."""
    calls = []
    monkeypatch.setattr(R, 'builtin', lambda: [])
    monkeypatch.setattr(R, 'profile_rules',
                        lambda name, level, ref=None: calls.append((name, level)) or [])
    E.candidate_rules({'chain': CHAIN, 'profiles': {'USER': None, 'MISSION': 'autonomous'}})
    assert calls == [('autonomous', 'MISSION')]


def test_a_locked_rule_that_is_the_specific_one_is_listed_once():
    """engine.py:85-86 — `r is not specific[0]` keeps the specific rule from being
    added to effective a second time as a locked rule of its own."""
    own = R.rule(id='own', scope_level='TASK', action_class='exec', decision='DENY',
                 scope_ref='tsk_1', locked=True)
    r = E.evaluate_item(_act('exec'), {'chain': CHAIN, 'candidates': [own]})
    assert r['effective'] == ['own'] and r['decision'] == 'DENY'


def test_a_user_rule_one_level_deeper_than_a_builtin_beats_a_stricter_builtin():
    """engine.py:36-41 — _depth gives a user rule +1 at its level, so a user ALLOW
    at USER out-ranks an unlocked built-in ASK at USER: the deeper rule is the
    specific one and nothing else is locked. Dropping the +1 would sort the ASK
    first and decide ASK. (DENY is always locked, rules.py:60, so it is not used.)"""
    builtin_ask = R.rule(id='bi', scope_level='USER', action_class='exec', decision='ASK',
                         scope_ref='usr_1', locked=False, source='builtin')
    user_allow = R.rule(id='me', scope_level='USER', action_class='exec', decision='ALLOW',
                        scope_ref='usr_1', source='user')
    r = E.evaluate_item(_act('exec'),
                        {'chain': CHAIN, 'candidates': [builtin_ask, user_allow]})
    assert r['decision'] == 'ALLOW' and r['deciding_rule'] == 'me'
    assert r['conflicts'] == [] and r['effective'] == ['me']

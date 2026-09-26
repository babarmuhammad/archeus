"""P9 policy engine units (p9-design-gate §4-§6, §21.2 U-*): pure evaluation,
no database. Every test names the gate scenario it covers; the mutation suite
(tools/mutate_p9.py) records which of these kill which mutant."""

import random

import pytest

from archeus.core.domain import entities, ids
from archeus.core.domain.actions import ACTION_CLASSES, Action
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


# ── hierarchy (U-R) ─────────────────────────────────────────────────────────

def test_U_R1_global_allow_from_the_baseline_alone():
    r = ev(act('read'), profiles={'USER': None})
    assert r['decision'] == 'ALLOW' and r['deciding_rule'].startswith('profile:careful')


def test_U_R2_global_deny_cannot_be_loosened_by_a_narrower_allow():
    r = ev(act('destructive', environment='prod'),
           rule('USER', 'destructive', 'ALLOW'), rule('TASK', 'destructive', 'ALLOW'))
    assert r['decision'] == 'DENY' and r['deciding_rule'] == 'builtin:floor:destructive-prod'
    # elsewhere the narrower rule is free to answer
    assert ev(act('destructive', environment='dev'),
              rule('USER', 'destructive', 'ALLOW'))['decision'] == 'ALLOW'


def test_U_R3_a_user_rule_overrides_the_users_own_profile():
    assert ev(act('git_push'))['decision'] == 'ASK'                 # standard
    r = ev(act('git_push'), rule('USER', 'git_push', 'ALLOW'))
    assert r['decision'] == 'ALLOW' and r['deciding_rule'] == 'r:USER:git_push:ALLOW'


def test_U_R4_a_project_restriction_tightens_and_applies_only_to_that_project():
    r = ev(act('write_repo', paths=['src/**']), rule('PROJECT', 'write_repo', 'ASK'))
    assert r['decision'] == 'ASK'
    other = dict(CHAIN, PROJECT='prj_2')
    assert ev(act('write_repo', paths=['src/**']), rule('PROJECT', 'write_repo', 'ASK'),
              chain=other)['decision'] == 'ALLOW_WITHIN_BOUNDARY'


def test_U_R4b_a_locked_broader_ask_is_not_loosened_by_a_deeper_allow():
    r = ev(act('install'), rule('USER', 'install', 'ASK', locked=True),
           rule('PROJECT', 'install', 'ALLOW'))
    assert r['decision'] == 'ASK'
    assert r['effective'] == ['r:USER:install:ASK', 'r:PROJECT:install:ALLOW'] or \
        set(r['effective']) == {'r:USER:install:ASK', 'r:PROJECT:install:ALLOW'}


def test_U_R5_a_task_rule_restricts_that_task_only():
    deny = rule('TASK', 'exec', 'DENY')
    assert ev(act('exec', paths=['a']), deny)['decision'] == 'DENY'
    assert ev(act('exec', paths=['a']), deny,
              chain=dict(CHAIN, TASK='tsk_2'))['decision'] == 'ALLOW_WITHIN_BOUNDARY'


def test_U_R6_same_depth_conflict_takes_the_strictest_and_says_so():
    a = rule('PROJECT', 'web', 'ALLOW', id='a')
    b = rule('PROJECT', 'web', 'ASK', id='b')
    for order in ((a, b), (b, a)):
        r = ev(act('web'), *order)
        assert r['decision'] == 'ASK' and sorted(r['conflicts']) == ['a', 'b']


def test_U_R7_the_task_contract_asks_for_an_undeclared_class_outside_the_plan_stage():
    r = ev(act('install'), stage='dispatch', task_classes=('write_repo',),
           profiles={'USER': 'autonomous'})
    assert r['decision'] == 'ASK'
    assert 'builtin:task-contract' in r['effective']
    # declared -> the profile answers; the plan stage never applies the contract
    assert ev(act('read'), stage='dispatch', task_classes=('read',))['decision'] == 'ALLOW'
    assert ev(act('read'), task_classes=())['decision'] == 'ALLOW'


def test_U_R7b_an_unclassified_action_is_judged_as_its_strictest_class():
    r = ev(act('exec', paths=['a']), stage='action', unclassified=True,
           task_classes=('read', 'git_push'))
    assert r['decision'] == 'ASK' and r['class'] == 'git_push'


def test_U_R8_leaving_an_attribute_out_never_reaches_a_permissive_rule():
    allow_dev = rule('USER', 'deploy', 'ALLOW', match={'environment': 'dev'})
    assert ev(act('deploy', environment='dev'), allow_dev)['decision'] == 'ALLOW'
    assert ev(act('deploy'), allow_dev)['decision'] == 'ASK'          # unknown env
    # (deploy also meets the locked prod floor; install has no floor at all)
    allow_install = rule('USER', 'install', 'ALLOW', match={'environment': 'dev'})
    assert ev(act('install', environment='dev'), allow_install)['decision'] == 'ALLOW'
    assert ev(act('install'), allow_install)['decision'] == 'ASK'
    # ...while a restrictive rule matches the unknown
    assert ev(act('destructive'))['decision'] == 'DENY'


def test_U_R9_inheritance_falls_back_to_the_nearest_broader_level():
    assert ev(act('git_push'), profiles={'USER': 'autonomous'})['deciding_rule'].startswith(
        'profile:autonomous@1:USER')
    assert ev(act('git_push'), profiles={'USER': None})['deciding_rule'].startswith(
        'profile:careful@1:GLOBAL')


def test_U_R10_no_applicable_rule_is_a_deny():
    r = ev(act('read'), profiles={'USER': None}, rules=[])
    assert r['decision'] == 'ALLOW'
    import archeus.core.policy.engine as eng
    saved = eng.R.builtin
    try:
        eng.R.builtin = lambda: []
        r = ev(act('read'), profiles={'USER': None})
    finally:
        eng.R.builtin = saved
    assert r['decision'] == 'DENY' and r['deciding_rule'] == 'builtin:policy-missing'


def test_the_baseline_covers_every_class():
    assert {r['action_class'] for r in R.builtin()} == set(ACTION_CLASSES)


def test_an_expired_rule_is_ignored():
    r = rule('USER', 'git_push', 'ALLOW', expires_at='2026-01-01T00:00:00Z')
    assert ev(act('git_push'), r, now='2025-12-31T00:00:00Z')['decision'] == 'ALLOW'
    assert ev(act('git_push'), r, now='2026-01-02T00:00:00Z')['decision'] == 'ASK'


def test_estop_denies_everything():
    r = ev(act('read'), estop=True)
    assert r['decision'] == 'DENY' and r['deciding_rule'] == 'builtin:estop'


# ── boundaries (U-B) ────────────────────────────────────────────────────────

def test_U_B1_inside_the_workspace_is_allowed_within_bounds_and_branches_deferred():
    r = ev(act('write_repo', paths=['archeus/cli/**', 'tests/x.py']))
    assert r['decision'] == 'ALLOW_WITHIN_BOUNDARY'
    assert r['checks'] == {'checked': ['paths'], 'deferred': [], 'outside': []}
    c = ev(act('git_commit'))
    assert c['decision'] == 'ALLOW_WITHIN_BOUNDARY' and c['checks']['deferred'] == ['branches']


@pytest.mark.parametrize('path', ['../x', '/etc/**', 'C:/Windows/**', 'a/../../b'])
def test_U_B2_a_path_that_leaves_the_workspace_is_outside(path):
    r = ev(act('write_repo', paths=[path]))
    assert r['decision'] == 'ASK' and r['checks']['outside'] == ['paths']
    deny_out = rule('PROJECT', 'write_repo', 'ALLOW_WITHIN_BOUNDARY',
                    boundary={'paths': ['@workspace/**']}, outside='DENY')
    assert ev(act('write_repo', paths=[path]), deny_out)['decision'] == 'DENY'


def test_U_B3_outside_the_plan_stage_an_absent_attribute_is_outside():
    r = ev(act('git_commit'), stage='dispatch', task_classes=('git_commit',))
    assert r['decision'] == 'ASK' and r['checks']['outside'] == ['branches']


def test_U_B4_every_awb_in_effect_must_hold():
    locked = rule('USER', 'write_repo', 'ALLOW_WITHIN_BOUNDARY', locked=True,
                  boundary={'paths': ['src/**']})
    deeper = rule('PROJECT', 'write_repo', 'ALLOW_WITHIN_BOUNDARY',
                  boundary={'paths': ['@workspace/**']})
    assert ev(act('write_repo', paths=['src/a.py']), locked, deeper)['decision'] == \
        'ALLOW_WITHIN_BOUNDARY'
    assert ev(act('write_repo', paths=['docs/a.md']), locked, deeper)['decision'] == 'ASK'


@pytest.mark.parametrize('path, pattern, ok', [
    ('src/a.py', 'src/**', True), ('src/**', 'src/**', True), ('src', 'src/**', True),
    ('srcx/a', 'src/**', False), ('src*/a', 'src/**', False), ('sr*', 'src/**', False),
    ('./src/a', 'src/**', True), ('x', '@workspace/**', True), ('../x', '@workspace/**', False),
    ('src/a.py', 'src/a.py', True), ('src/b.py', 'src/a.py', False)])
def test_containment_is_conservative(path, pattern, ok):
    assert R.inside(path, pattern) is ok


def test_glob_stars_stay_within_a_segment_and_double_stars_cross():
    assert R.glob('archeus/*', 'archeus/t1') and not R.glob('archeus/*', 'archeus/a/b')
    assert R.glob('src/**', 'src/a/b.py') and not R.glob('main', 'archeus/main')


# ── autonomy (U-P) ──────────────────────────────────────────────────────────

EXPECTED = {
    'careful': {'read': 'ALLOW', 'web': 'ALLOW', 'write_repo': 'ASK', 'git_push': 'ASK'},
    'standard': {'read': 'ALLOW', 'write_repo': 'ALLOW_WITHIN_BOUNDARY',
                 'exec': 'ALLOW_WITHIN_BOUNDARY', 'git_commit': 'ALLOW_WITHIN_BOUNDARY',
                 'git_push': 'ASK', 'deploy': 'ASK'},
    'autonomous': {'git_push': 'ALLOW_WITHIN_BOUNDARY', 'install': 'ASK', 'deploy': 'ASK',
                   'credential': 'ASK'},
}


@pytest.mark.parametrize('profile', sorted(EXPECTED))
def test_U_P1_each_profile_answers_its_table(profile):
    for cls, want in EXPECTED[profile].items():
        assert ev(act(cls, paths=['a']), profiles={'USER': profile})['decision'] == want, cls


def test_U_P2_a_mission_profile_is_deeper_than_the_users():
    r = ev(act('git_push'), profiles={'USER': 'careful', 'MISSION': 'autonomous'})
    assert r['decision'] == 'ALLOW_WITHIN_BOUNDARY'
    assert r['deciding_rule'].startswith('profile:autonomous@1:MISSION')


def test_U_P3_autonomy_never_loosens_a_locked_rule_or_the_floor():
    locked = rule('USER', 'git_push', 'ASK', locked=True)
    assert ev(act('git_push'), locked,
              profiles={'MISSION': 'autonomous'})['decision'] == 'ASK'
    assert ev(act('destructive'), profiles={'MISSION': 'autonomous'})['decision'] == 'DENY'
    # and it never removes a boundary: autonomous is AWB, never a bare ALLOW
    assert all(d != 'ALLOW' or c in ('read', 'web')
               for c, (d, _b) in R.PROFILES['autonomous'].items())


def test_an_explicit_rule_beats_a_profile_at_the_same_level():
    r = ev(act('git_push'), rule('MISSION', 'git_push', 'ASK'),
           profiles={'MISSION': 'autonomous'})
    assert r['decision'] == 'ASK' and r['deciding_rule'] == 'r:MISSION:git_push:ASK'


def test_step_up_is_required_for_deploy_and_destructive_asks():
    assert ev(act('deploy'))['step_up'] is True
    assert ev(act('git_push'))['step_up'] is False


def test_implied_classes_follow_the_capabilities():
    assert R.implied(['read'], ['code_edit', 'shell', 'vision', 'web']) == [
        ('read', None), ('write_repo', 'code_edit'), ('exec', 'shell'), ('web', 'web')]
    assert R.implied(['exec'], ['shell']) == [('exec', None)]


# ── determinism (property tests, fixed seeds) ───────────────────────────────

POOL = [rule(level, cls, d, id='p%d' % i, locked=(i % 5 == 0) or d == 'DENY')
        for i, (level, cls, d) in enumerate(
            (lv, c, d) for lv in R.LEVELS[1:] for c in ('git_push', 'install', 'web')
            for d in ('ALLOW', 'ASK', 'DENY'))]


def _pick(rng):
    return rng.sample(POOL, rng.randint(0, 8))


def test_U_P_rule_order_never_changes_a_decision():
    rng = random.Random(9)
    for _ in range(300):
        chosen, cls = _pick(rng), rng.choice(('git_push', 'install', 'web'))
        first = ev(act(cls), *chosen)
        rng.shuffle(chosen)
        again = ev(act(cls), *chosen)
        assert (first['decision'], first['deciding_rule']) == (again['decision'],
                                                               again['deciding_rule'])


def test_U_P_nothing_ever_decides_looser_than_a_locked_applicable_rule():
    """Locks are the floor of every answer: whatever else is added, the
    decision is at least as strict as each locked rule that applies."""
    rng = random.Random(11)
    for _ in range(400):
        chosen, cls = _pick(rng), rng.choice(('git_push', 'install', 'web'))
        got = ev(act(cls), *chosen)['decision']
        floor = max([R.STRICTNESS[r['decision']] for r in chosen
                     if r['locked'] and r['action_class'] == cls] or [0])
        assert R.STRICTNESS[got] >= floor, (cls, got, chosen)


def test_U_P_an_unlocked_broader_rule_never_changes_what_a_deeper_rule_decides():
    rng = random.Random(13)
    for _ in range(300):
        cls = rng.choice(('git_push', 'install', 'web'))
        deep = rule('TASK', cls, rng.choice(('ALLOW', 'ASK')), id='deep')
        broad = rule(rng.choice(('USER', 'WORKSPACE', 'PROJECT', 'MISSION')), cls,
                     rng.choice(('ALLOW', 'ASK')), id='broad')
        assert ev(act(cls), deep)['decision'] == ev(act(cls), deep, broad)['decision']


def test_U_P3_a_decision_replays_from_its_own_snapshot():
    """Replay equality (§9): the rules a result records as matched are the
    whole input — evaluating again over exactly them gives the same answer."""
    rng = random.Random(17)
    for _ in range(300):
        cls = rng.choice(('git_push', 'install', 'web', 'write_repo', 'deploy'))
        a = act(cls, paths=['src/x'] if rng.random() < .5 else None)
        r = ev(a, *_pick(rng), profiles={'USER': rng.choice(sorted(R.PROFILES)),
                                         'MISSION': rng.choice([None] + sorted(R.PROFILES))})
        again = E.evaluate_item(a, {'chain': CHAIN, 'candidates': r['matched']})
        assert (again['decision'], again['deciding_rule'], again['effective']) == (
            r['decision'], r['deciding_rule'], r['effective'])


def test_the_port_answers_a_policy_decision_entity_and_is_not_a_stub():
    d = E.PolicyEngine().evaluate(act('read'), {'chain': CHAIN, 'policy_version': 'v'})
    assert isinstance(d, entities.PolicyDecision) and d.decision == 'ALLOW'
    assert E.PolicyEngine.is_stub is False and ids.is_id(d.id, 'policy_decision')
    assert d.items[0]['deciding_rule'] and d.policy_version == 'v'

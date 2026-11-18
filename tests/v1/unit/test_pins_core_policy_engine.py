"""Hand-mutant pins for archeus/core/policy/engine.py (T-828). One test per
security-relevant condition that no existing test would notice being inverted,
removed or loosened. Each test names the condition it pins; the mutation it
kills is recorded in the card report and re-run in a scratch copy.

Pure evaluation like test_policy_units.py: no database, no clock, no process.
"""

from archeus.core.domain.actions import Action
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


# ── the ordering of rules and the scope chain (engine.py:36,46,48) ──────────

def test_a_project_rule_never_rises_to_a_mission_profile():
    ask = rule('PROJECT', 'read', 'ASK', id='ask0')
    ctx = dict(profiles={'USER': None, 'MISSION': 'standard'})
    r = ev(act('read'), ask, **ctx)
    assert (r['decision'], r['conflicts'], r['effective']) == (
        'ALLOW', [], ['profile:standard@2:MISSION:read'])
    deeper = rule('TASK', 'read', 'ASK', id='ask9')
    assert ev(act('read'), ask, deeper, **ctx)['decision'] == 'ASK'


def test_a_profile_is_on_chain_even_with_no_chain_at_all():
    r = E.evaluate_item(act('write_repo', paths=['src/a.py']), {'chain': {}, 'rules': []})
    assert r['decision'] == 'ALLOW_WITHIN_BOUNDARY'
    assert r['deciding_rule'] == 'profile:standard@2:USER:write_repo'


def test_a_rule_naming_no_scope_ref_never_binds_a_level_the_chain_lacks():
    loose = rule('PROJECT', 'exec', 'DENY', id='loose', scope_ref=None)
    got = E.evaluate_item(act('exec', paths=['a']), {'chain': {'USER': 'usr_1'},
                                                     'rules': [loose]})
    assert got['decision'] == 'ALLOW_WITHIN_BOUNDARY'
    tight = dict(loose, scope_ref='prj_1')
    bound = E.evaluate_item(act('exec', paths=['a']), {'chain': {'USER': 'usr_1',
                                                                 'PROJECT': 'prj_1'},
                                                       'rules': [tight]})
    assert bound['decision'] == 'DENY' and bound['deciding_rule'] == 'loose'


# ── replay from a snapshot (engine.py:55,56,63,107) ─────────────────────────

def test_an_empty_replay_snapshot_replays_nothing_and_stays_closed():
    r = E.evaluate_item(act('read'), {'chain': CHAIN, 'candidates': []})
    assert r['decision'] == 'DENY' and r['deciding_rule'] == 'builtin:policy-missing'
    assert [m['id'] for m in r['matched']] == ['builtin:policy-missing']


def test_the_record_is_a_copy_of_the_rules_not_the_callers_themselves():
    mine = rule('TASK', 'git_push', 'ALLOW', id='copy1')
    first = ev(act('git_push'), mine)
    assert first['decision'] == 'ALLOW'
    mine['decision'] = 'DENY'
    assert [m['decision'] for m in first['matched'] if m['id'] == 'copy1'] == ['ALLOW']
    snap = rule('TASK', 'git_push', 'ALLOW', id='copy2')
    second = E.evaluate_item(act('git_push'), {'chain': CHAIN, 'candidates': [snap]})
    assert second['decision'] == 'ALLOW'
    snap['decision'] = 'DENY'
    assert [m['decision'] for m in second['matched'] if m['id'] == 'copy2'] == ['ALLOW']


def test_the_record_lists_every_rule_read_not_only_the_winning_ones():
    win = rule('TASK', 'git_push', 'ALLOW', id='win')
    floor = rule('USER', 'git_push', 'DENY', id='floor')
    r = ev(act('git_push'), win, floor)
    assert r['decision'] == 'DENY'
    assert [m['id'] for m in r['matched']] == [
        'win', 'floor', 'profile:standard@2:USER:git_push', 'profile:careful@2:GLOBAL:git_push']
    assert r['effective'] == ['floor', 'win']


# ── expiry (engine.py:72) ────────────────────────────────────────────────────

def test_a_rule_is_expired_at_the_instant_it_says_not_one_after():
    ok = rule('USER', 'git_push', 'ALLOW', id='exp1', expires_at='2026-01-01T00:00:00Z')
    assert ev(act('git_push'), ok, now='2025-12-31T23:59:59Z')['decision'] == 'ALLOW'
    assert ev(act('git_push'), ok, now='2026-01-01T00:00:00Z')['decision'] == 'ASK'


def test_the_engine_reads_no_clock_so_no_now_means_no_expiry():
    old = rule('USER', 'git_push', 'ALLOW', id='exp2', expires_at='2000-01-01T00:00:00Z')
    r = ev(act('git_push'), old)
    assert r['decision'] == 'ALLOW' and r['deciding_rule'] == 'exp2'


# ── the implicit task contract (engine.py:74) ────────────────────────────────

def test_no_declared_classes_means_no_contract_rule_and_no_crash():
    r = ev(act('read'), stage='dispatch')
    assert r['decision'] == 'ALLOW'
    assert 'builtin:task-contract' not in r['effective']
    declared = ev(act('install'), stage='dispatch', task_classes=('read',))
    assert declared['decision'] == 'ASK'
    assert 'builtin:task-contract' in declared['effective']


# ── specific and conflicts (engine.py:82,84,85,86) ──────────────────────────

def test_only_a_same_depth_disagreement_is_a_conflict():
    deep = rule('TASK', 'git_push', 'ALLOW', id='deepA')
    broad = rule('USER', 'git_push', 'ASK', id='broadB')
    r = ev(act('git_push'), deep, broad)
    assert (r['decision'], r['conflicts'], r['effective']) == ('ALLOW', [], ['deepA'])
    same = rule('TASK', 'git_push', 'ASK', id='deepC')
    both = ev(act('git_push'), deep, same, broad)
    assert both['decision'] == 'ASK' and sorted(both['conflicts']) == ['deepA', 'deepC']


def test_a_locked_rule_at_the_deepest_level_is_counted_once():
    top = rule('TASK', 'git_push', 'ASK', id='lock1', locked=True)
    r = ev(act('git_push'), top)
    assert r['decision'] == 'ASK' and r['effective'] == ['lock1']
    broad = rule('USER', 'git_push', 'DENY', id='lock0')
    r2 = ev(act('git_push'), top, broad)
    assert r2['decision'] == 'DENY' and r2['effective'] == ['lock0', 'lock1']


# ── ALLOW_WITHIN_BOUNDARY (engine.py:90,91,95,96,97,99,100,105) ─────────────

def test_every_boundary_counts_not_only_the_last_one_checked():
    deep = rule('PROJECT', 'write_repo', 'ALLOW_WITHIN_BOUNDARY', id='out1',
                boundary={'paths': ['src/**']})
    broad = rule('USER', 'write_repo', 'ALLOW_WITHIN_BOUNDARY', id='in1', locked=True,
                 boundary={'paths': ['@workspace/**']})
    r = ev(act('write_repo', paths=['docs/a.md']), deep, broad)
    assert r['decision'] == 'ASK'
    assert r['checks'] == {'checked': ['paths'], 'deferred': [], 'outside': ['paths']}


def test_a_predicate_that_fails_twice_is_recorded_once():
    deep = rule('PROJECT', 'write_repo', 'ALLOW_WITHIN_BOUNDARY', id='o1',
                boundary={'paths': ['src/**']})
    broad = rule('USER', 'write_repo', 'ALLOW_WITHIN_BOUNDARY', id='o2', locked=True,
                 boundary={'paths': ['docs/**']})
    r = ev(act('write_repo', paths=['notes/a.md']), deep, broad)
    assert r['decision'] == 'ASK'
    assert r['checks'] == {'checked': [], 'deferred': [], 'outside': ['paths']}


def test_the_recorded_boundary_is_one_dict_or_every_dict():
    one = rule('TASK', 'write_repo', 'ALLOW_WITHIN_BOUNDARY', id='b1',
               boundary={'paths': ['src/**']})
    r = ev(act('write_repo', paths=['src/a.py']), one)
    assert r['decision'] == 'ALLOW_WITHIN_BOUNDARY'
    assert r['boundary'] == {'paths': ['src/**']}
    two = rule('USER', 'write_repo', 'ALLOW_WITHIN_BOUNDARY', id='b2', locked=True,
               boundary={'paths': ['src/**', 'docs/**']})
    r2 = ev(act('write_repo', paths=['src/a.py']), one, two)
    assert r2['boundary'] == [{'paths': ['src/**']}, {'paths': ['src/**', 'docs/**']}]


def test_the_strictest_outside_of_all_the_boundaries_is_the_answer():
    soft = rule('PROJECT', 'write_repo', 'ALLOW_WITHIN_BOUNDARY', id='askOut',
                boundary={'paths': ['src/**']}, outside='ASK')
    hard = rule('USER', 'write_repo', 'ALLOW_WITHIN_BOUNDARY', id='denyOut', locked=True,
                boundary={'paths': ['docs/**']}, outside='DENY')
    r = ev(act('write_repo', paths=['notes/a.md']), soft, hard)
    assert r['decision'] == 'DENY' and r['deciding_rule'] == 'denyOut'


def test_the_reason_names_the_rule_its_boundary_and_its_lock():
    bnd = rule('PROJECT', 'exec', 'ALLOW_WITHIN_BOUNDARY', id='bnd', locked=True,
               boundary={'paths': ['src/**']}, outside='ASK')
    r = ev(act('exec', paths=['docs/a.md']), bnd)
    assert r['decision'] == 'ASK'
    assert 'outside its boundary on paths' in r['reason']
    assert 'bnd (ALLOW_WITHIN_BOUNDARY, PROJECT, locked)' in r['reason']


# ── step-up (engine.py:117) ─────────────────────────────────────────────────

def test_step_up_belongs_to_an_ask_of_a_step_up_class_and_to_nothing_else():
    free = rule('USER', 'deploy', 'ALLOW', id='free1', match={'environment': 'dev'})
    allowed = ev(act('deploy', environment='dev'), free)
    assert allowed['decision'] == 'ALLOW' and allowed['step_up'] is False
    ask = rule('USER', 'git_push', 'ASK', id='askA')
    asked = ev(act('git_push'), ask)
    assert asked['decision'] == 'ASK' and asked['step_up'] is False
    assert ev(act('deploy'))['step_up'] is True


# ── the e-stop (engine.py:123) ──────────────────────────────────────────────

def test_any_armed_sentinel_stops_and_only_an_armed_one_does():
    for armed in (True, 'STOP', object()):
        r = ev(act('read'), estop=armed)
        assert r['decision'] == 'DENY' and r['deciding_rule'] == 'builtin:estop'
    for off in (False, None, 0, ''):
        assert ev(act('read'), estop=off)['decision'] == 'ALLOW'


# ── an unclassified action (engine.py:127,129,131,132) ───────────────────────

def test_an_unclassified_action_is_also_judged_as_exec():
    r = ev(act('read'), stage='action', unclassified=True, task_classes=('read',))
    assert r['decision'] == 'ASK' and r['class'] == 'exec'
    assert 'builtin:task-contract' in r['effective']


def test_an_unclassified_decision_breaks_ties_by_class_and_says_so():
    r = ev(act('read'), stage='action', unclassified=True, task_classes=('deploy',))
    assert r['decision'] == 'ASK' and r['class'] == 'exec'
    assert r['reason'].startswith('unclassified action, judged as its strictest class: ')
    assert 'ASK exec:' in r['reason']


# ── the Policy port (engine.py:142-148) ──────────────────────────────────────

def test_the_port_writes_the_portable_types_into_its_entity():
    d = E.PolicyEngine().evaluate(act('read'), {'chain': CHAIN, 'policy_version': 'v',
                                                'estop': 'STOP', 'stage': 'dispatch'})
    assert d.decision == 'DENY' and d.stage == 'dispatch' and d.estop is True
    assert isinstance(d.engine_version, str) and d.engine_version == str(R.ENGINE_VERSION)
    assert d.policy_version == 'v'
    plain = E.PolicyEngine().evaluate(act('read'), {'chain': CHAIN})
    assert plain.decision == 'ALLOW' and plain.estop is False and plain.stage == 'plan'

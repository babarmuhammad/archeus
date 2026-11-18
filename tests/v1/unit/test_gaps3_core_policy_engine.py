"""T-1140 gap tests for archeus/core/policy/engine.py lines 1-148 (tip 56d53504).

Fail-closed and denial first, then boundaries, then error paths. The ten final
branches (each the closest-existing-test evidence is in the report):

  1. engine.py:123-126  the e-stop denies before candidate_rules / profiles /
                        the class loop are ever read (poisoned payload test)
  2. engine.py:127-133 + 76-79   an unclassified replay: a judged class the
                        snapshot does not cover is DENY policy_missing
  3. engine.py:55 + 67  a replayed rule off the chain (foreign scope_ref) is
                        excluded; a profile-source one is on it
  4. engine.py:55 + 72  a replayed rule still expires at its own deadline
  5. engine.py:55 + 73-75   the implicit task contract binds a replayed
                        judgement outside the plan stage
  6. engine.py:55       candidate copies: the replay cannot mutate the context
  7. engine.py:62       user-rule copies: the audit trail cannot mutate the
                        context's rule dicts
  8. engine.py:36       the explicit-before-profile half level at GLOBAL
                        (source == 'user' +1 against Core's own baseline)
  9. engine.py:60-62    an unknown profile name raises, never answers
 10. engine.py:100      the outside escalation on a tie keeps the stable,
                        strictest-first attribution

Pure: no database, no clock, no OS, no network, no process, no environment.
Every path, host and timestamp is a literal string, so nothing differs between
Linux and Windows. Self-contained: no import of any other test_gaps3 file and
no dependence on queue order.
"""

import pytest

from archeus.core.domain.actions import Action
from archeus.core.policy import engine as E
from archeus.core.policy import rules as R

CHAIN = {'USER': 'usr_1', 'WORKSPACE': 'ws_global', 'PROJECT': 'prj_1',
         'MISSION': 'msn_1', 'TASK': 'tsk_1'}


def act(cls, **kw):
    return Action(action_class=cls, target=kw.pop('target', 'task:t1'), **kw)


def rule(level, cls, decision, **kw):
    kw.setdefault('scope_ref', None if level == 'GLOBAL' else CHAIN.get(level))
    return R.rule(id=kw.pop('id', 'r:%s:%s:%s' % (level, cls, decision)),
                  scope_level=level, action_class=cls, decision=decision, **kw)


def ev(action, *user_rules, **ctx):
    ctx.setdefault('chain', CHAIN)
    return E.evaluate_item(action, dict(ctx, rules=list(user_rules)))


def entry(r, rid):
    """The audit entry with this id (there is exactly one)."""
    found = [m for m in r['matched'] if m['id'] == rid]
    assert len(found) == 1, (rid, [m['id'] for m in r['matched']])
    return found[0]


# ── fail closed, denial first ───────────────────────────────────────────────

def test_estop_denies_before_any_rule_source_is_read():
    """1 · engine.py:123-126 (with 55, 62, 69-72, 129). The e-stop is judged
    BEFORE candidate_rules, the profile expansion and the unclassified class
    loop, so a context whose candidates, rules and profile names are all
    poison still returns the e-stop DENY. Closest existing:
    test_gaps_core_policy_engine.py::test_the_emergency_stop_is_answered_before_
    the_replay_and_the_classes — it hands only well-formed payloads, so an
    engine that materialised candidates or expanded profiles before the e-stop
    check would raise instead of denying and that test would never see a wrong
    answer. Same context, estop cleared, must raise: the poison is real."""
    poison = {'chain': CHAIN, 'estop': 1, 'candidates': ['junk'], 'rules': [object()],
              'profiles': {'USER': 'reckless', 'MISSION': 'reckless'},
              'stage': 'action', 'unclassified': True,
              'task_classes': ('deploy', 'destructive')}
    r = E.evaluate_item(act('deploy', environment='dev'), poison)
    assert r['decision'] == 'DENY' and r['deciding_rule'] == 'builtin:estop'
    assert r['class'] == 'deploy' and r['effective'] == ['builtin:estop']
    assert r['matched'] == [dict(R.ESTOP, action_class='deploy')]
    assert r['reason'] == 'emergency stop armed: every action is denied'
    assert r['boundary'] is None and r['checks'] is None and r['step_up'] is False
    assert R.ESTOP['action_class'] == 'read'              # the constant was not touched
    with pytest.raises((TypeError, ValueError, KeyError)):   # the payload does poison it
        E.evaluate_item(act('deploy', environment='dev'), dict(poison, estop=0))


def test_an_unclassified_replay_denies_a_class_its_snapshot_lacks():
    """2 · engine.py:127-133 with 76-79 over the candidate list of 55: an
    unclassified action replayed from a snapshot that covers one judged class
    but not another takes the strictest judgement, which is the fail-closed
    DENY of the uncovered class — a recorded permissive snapshot cannot make an
    unclassifiable action an allow. Closest existing:
    test_gaps_core_policy_engine.py::test_an_unclassified_action_is_always_
    judged_as_exec_too — live rules only, where builtin()'s careful baseline
    covers every class, so the policy_missing DENY branch of the class loop is
    never entered there."""
    snap = rule('GLOBAL', 'read', 'ALLOW', id='snap')
    r = E.evaluate_item(act('read'), {'chain': CHAIN, 'candidates': [snap],
                                      'unclassified': True, 'stage': 'action',
                                      'task_classes': ('read', 'web')})
    assert r['decision'] == 'DENY' and r['class'] == 'web'   # exec and web both uncovered,
    assert r['deciding_rule'] == 'builtin:policy-missing'    # 'web' > 'exec' breaks the tie
    assert r['reason'] == ('unclassified action, judged as its strictest class: '
                           'no policy covers web: denied (fail closed)')
    assert r['effective'] == ['builtin:policy-missing'] and r['conflicts'] == []
    assert [m['id'] for m in r['matched']] == ['builtin:policy-missing']
    assert r['matched'][0]['action_class'] == 'web'          # copied with the judged class
    assert r['action']['class'] == 'read'                    # asked about, as it was asked
    assert r['step_up'] is False and r['boundary'] is None and r['checks'] is None
    assert R.MISSING['action_class'] == 'read'


def test_a_replay_excludes_a_rule_that_is_not_on_the_chain():
    """3 · engine.py:55 with 69-72 (`_on_chain` at 71): a recorded snapshot is
    replayed against the present chain, so an ALLOW whose TASK scope_ref names
    another task never decides — the replay falls to the fail-closed DENY.
    Closest existing: test_gaps_core_policy_engine.py::test_a_replay_decides_
    from_its_own_snapshot_and_nothing_else — it never varies scope_ref, and the
    chain tests (test_a_rule_that_names_no_scope_ref_binds_no_scope) only use
    ctx['rules'], so an engine that trusted a snapshot's rules unconditionally
    would let one task replay another task's allow."""
    foreign = rule('TASK', 'exec', 'ALLOW', id='snap-allow', scope_ref='tsk_other')
    r = E.evaluate_item(act('exec', paths=['src/a.py']),
                        {'chain': CHAIN, 'candidates': [foreign]})
    assert r['decision'] == 'DENY' and r['deciding_rule'] == 'builtin:policy-missing'
    assert 'snap-allow' not in [m['id'] for m in r['matched']]
    own = rule('TASK', 'exec', 'ALLOW', id='snap-allow')   # same rule, its own task
    ok = E.evaluate_item(act('exec', paths=['src/a.py']),
                         {'chain': CHAIN, 'candidates': [own]})
    assert ok['decision'] == 'ALLOW' and ok['deciding_rule'] == 'snap-allow'
    # a profile-source snapshot rides the chain even at a level the chain lacks
    prof = R.rule(id='profile:standard@2:USER:exec', scope_level='USER', scope_ref=None,
                  action_class='exec', decision='ALLOW', source='profile')
    p = E.evaluate_item(act('exec', paths=['src/a.py']),
                        {'chain': {'USER': 'usr_1'}, 'candidates': [prof]})
    assert p['decision'] == 'ALLOW' and p['deciding_rule'] == 'profile:standard@2:USER:exec'


def test_a_replayed_rule_still_expires_at_its_own_deadline():
    """4 · engine.py:55 with 72 (the expiry gate): a snapshot rule carrying
    `expires_at` cannot be replayed once the caller's clock is past it — the
    temporary allow the owner already revoked would otherwise answer forever
    from the recorded decision. Closest existing: test_gaps_core_policy_engine.
    py::test_expiry_is_inclusive_and_only_the_callers_clock_expires_a_rule —
    ctx['rules'] only; the replay tests (test_a_replay_decides_from_its_own_
    snapshot_and_nothing_else) never carry an expiry, so an engine that skipped
    the gate for candidates (a snapshot "is" its own truth") would pass them."""
    temp = rule('TASK', 'exec', 'ALLOW', id='temp', expires_at='2026-01-01T00:00:00Z')
    base = {'chain': CHAIN, 'candidates': [temp]}
    before = E.evaluate_item(act('exec', paths=['src/a.py']),
                             dict(base, now='2025-12-31T23:59:59Z'))
    assert before['decision'] == 'ALLOW' and before['deciding_rule'] == 'temp'
    for now in ('2026-01-01T00:00:00Z', '2026-01-01T00:00:01Z'):   # `<=` is inclusive
        gone = E.evaluate_item(act('exec', paths=['src/a.py']), dict(base, now=now))
        assert gone['decision'] == 'DENY' and gone['deciding_rule'] == 'builtin:policy-missing'
        assert 'temp' not in [m['id'] for m in gone['matched']]
    no_clock = E.evaluate_item(act('exec', paths=['src/a.py']), dict(base))
    assert no_clock['decision'] == 'ALLOW' and no_clock['deciding_rule'] == 'temp'
    assert temp['expires_at'] == '2026-01-01T00:00:00Z'            # snapshot untouched


def test_the_implicit_task_contract_binds_a_replay_outside_plan():
    """5 · engine.py:55 with 73-75: the implicit task contract is a live
    constant, not a rule source, so a replayed dispatch/action judgement of a
    class the task did not declare still asks even when the snapshot holds a
    bare ALLOW for it. Closest existing: test_gaps_core_policy_engine.py::
    test_a_locked_rule_of_cores_own_at_the_same_level_is_still_broader (live
    rules) and test_a_replay_decides_from_its_own_snapshot_and_nothing_else
    (plan stage only) — no existing test combines candidates with a non-plan
    stage, so appending the contract only in the live path (skipping it once
    `candidates` replaces the rules) would replay an undeclared class as the
    snapshot's ALLOW."""
    snap = rule('USER', 'exec', 'ALLOW', id='snap')
    plain = E.evaluate_item(act('exec', paths=['src/a.py']),
                            {'chain': CHAIN, 'candidates': [snap]})
    assert plain['decision'] == 'ALLOW' and plain['deciding_rule'] == 'snap'
    for stage in ('dispatch', 'action'):
        r = E.evaluate_item(act('exec', paths=['src/a.py']),
                            {'chain': CHAIN, 'candidates': [snap], 'stage': stage,
                             'task_classes': ('read',)})
        assert r['decision'] == 'ASK' and r['deciding_rule'] == 'builtin:task-contract'
        assert r['effective'] == ['builtin:task-contract']       # snapshot rule is unlocked
        assert [m['id'] for m in r['matched']] == ['builtin:task-contract', 'snap']
        assert entry(r, 'builtin:task-contract')['action_class'] == 'exec'
        assert r['step_up'] is False                             # exec is not a step-up class
        assert R.TASK_CONTRACT['action_class'] == 'read'
    declared = E.evaluate_item(act('exec', paths=['src/a.py']),
                               {'chain': CHAIN, 'candidates': [snap], 'stage': 'action',
                                'task_classes': ('exec',)})
    assert declared['decision'] == 'ALLOW' and declared['deciding_rule'] == 'snap'


# ── the audit trail is a copy, never the caller's data ──────────────────────

def test_a_replay_hands_back_copies_never_the_recorded_dicts():
    """6 · engine.py:55 (`[dict(r) for r in ctx['candidates']]`): the returned
    audit entries are copies, so writing to a decision's `matched` cannot
    mutate the stored snapshot the next replay reads. Closest existing:
    test_a_replay_decides_from_its_own_snapshot_and_nothing_else compares ids
    only, and the rules.py copy tests (test_gaps_core_policy_rules.py::
    test_the_rule_shape_survives_junk_and_copies_its_dicts) cover rule()
    building its own dicts, not the engine's handling of caller-owned ones;
    drop the dict(r) and matched[0] IS the stored dict — one tampered field
    (an audit view, a log printer, a repair script) turns the recorded allow
    into a permanent denial, or back."""
    snap = rule('TASK', 'exec', 'ALLOW', id='snap')
    ctx = {'chain': CHAIN, 'candidates': [snap]}
    r = E.evaluate_item(act('exec', paths=['src/a.py']), ctx)
    assert r['decision'] == 'ALLOW' and r['deciding_rule'] == 'snap'
    m = entry(r, 'snap')
    assert m is not snap
    m['decision'] = 'DENY'                                        # tamper the returned audit
    assert snap['decision'] == 'ALLOW'                            # the stored snapshot is intact
    r2 = E.evaluate_item(act('exec', paths=['src/a.py']), ctx)
    assert r2['decision'] == 'ALLOW' and r2['deciding_rule'] == 'snap'
    assert entry(r2, 'snap') is not m and entry(r2, 'snap') is not snap


def test_the_audit_trail_cannot_mutate_the_callers_rule_dicts():
    """7 · engine.py:62 (`[dict(r) for r in ctx.get('rules') or ()]`): the
    user rules a context hands in are copied, so the audit trail of one
    decision cannot poison every later decision that reuses the same ctx (the
    application keeps one context per evaluation session). Closest existing:
    test_gaps_core_policy_engine.py::test_the_record_lists_every_rule_that_
    could_have_applied_in_order only reads matched; the rules.py copy test
    covers rule()'s own dicts, not the engine's read of caller dicts — drop
    the dict(r) and matched is the caller's dict itself: a tampered `decision`
    or `locked` rewrites the owner's rule for every subsequent evaluation."""
    live = rule('TASK', 'exec', 'ALLOW', id='live')
    ctx = {'chain': CHAIN, 'rules': [live], 'stage': 'action', 'task_classes': ('exec',)}
    r = E.evaluate_item(act('exec', paths=['src/a.py']), ctx)
    assert r['decision'] == 'ALLOW' and r['deciding_rule'] == 'live'
    m = entry(r, 'live')
    assert m is not live
    m['decision'] = 'DENY'
    m['locked'] = True
    assert live['decision'] == 'ALLOW' and live['locked'] is False
    r2 = E.evaluate_item(act('exec', paths=['src/a.py']), ctx)
    assert r2['decision'] == 'ALLOW' and r2['deciding_rule'] == 'live'
    assert entry(r2, 'live') is not m and entry(r2, 'live') is not live


# ── boundaries ───────────────────────────────────────────────────────────────

def test_an_explicit_rule_at_global_sits_above_the_baseline():
    """8 · engine.py:36 — the `(1 if r['source'] == 'user' else 0)` half level
    at GLOBAL: an explicit (imported/CLI-created) user rule at GLOBAL must
    beat Core's own careful baseline (GLOBAL, source 'profile', depth 0) the
    same way it beats a profile at USER or MISSION. Closest existing:
    test_policy_units.py::test_U_R3_a_user_rule_overrides_the_users_own_profile
    (USER level, where the half level is not contested by a builtin) and
    test_gaps_core_policy_engine.py::test_a_locked_rule_of_cores_own_at_the_
    same_level_is_still_broader (the half level at TASK). Only GLOBAL puts a
    profile source and an explicit rule at the same LEVELS.index, so removing
    the +1 there — the profile then ties and answers by strictness — is
    invisible to every existing test."""
    g = rule('GLOBAL', 'exec', 'ALLOW', id='g', source='user')
    assert g['source'] == 'user' and g['locked'] is False
    r = E.evaluate_item(act('exec', paths=['src/a.py']),
                        {'chain': CHAIN, 'rules': [g], 'profiles': {'USER': None}})
    base = 'profile:careful@%d:GLOBAL:exec' % R.PROFILES_VERSION
    assert r['decision'] == 'ALLOW' and r['deciding_rule'] == 'g'
    assert r['effective'] == ['g']                     # the baseline ASK is unlocked, not in force
    assert [m['id'] for m in r['matched']] == ['g', base]   # but it is in the audit trail
    assert r['conflicts'] == []


def test_a_boundary_tie_blames_the_rule_the_answer_came_from():
    """10 · engine.py:100 — `worst = max(bounded, key=STRICTNESS[r['outside']])`
    on a TIE: when every AWB rule in force carries the same `outside`, the
    escalating rule must be the strictest-first `effective` head (the deepest,
    which is also the rule that decided), stably under any input order — that
    id is what the denial is recorded against and what the approval UI names.
    Closest existing: test_gaps_core_policy_engine.py::test_a_violated_boundary_
    escalates_to_the_strictest_outside_in_effect has unequal outsides, so the
    max has a strict winner and never exercises the tie; `max` written as
    `min` (or folding over ctx['rules'] order) attributes the denial to the
    broader locked rule instead and every existing test still passes."""
    deep = rule('TASK', 'write_repo', R.AWB, id='deep',
                boundary={'paths': ['src/**']}, outside='DENY')
    loose = rule('PROJECT', 'write_repo', R.AWB, id='loose',
                 boundary={'paths': ['docs/**']}, outside='DENY', locked=True)
    for order in ((deep, loose), (loose, deep)):
        r = ev(act('write_repo', paths=['src/a.py']), *order)
        assert r['decision'] == 'DENY' and r['deciding_rule'] == 'deep'
        assert r['effective'] == ['deep', 'loose']                 # strictest-first, then depth
        assert r['boundary'] == [{'paths': ['src/**']}, {'paths': ['docs/**']}]
        assert r['checks'] == {'checked': ['paths'], 'deferred': [], 'outside': ['paths']}
        assert r['step_up'] is False                               # DENY never steps up
        assert r['reason'].startswith('DENY write_repo: ')
        assert 'outside its boundary on paths' in r['reason']


# ── error paths ──────────────────────────────────────────────────────────────

def test_an_unknown_profile_name_raises_never_answers():
    """9 · engine.py:60-62 — `R.profile_rules(profiles[level], ...)` indexes
    PROFILES directly, so a profile name the context misspells raises (the
    rules.py contract pinned for a direct call in test_builtin_is_the_floor_
    plus_careful_and_a_fresh_container) rather than quietly expanding no rules:
    an engine-side permissive default (`PROFILES.get(name)` and expand
    nothing) would drop the caller's profile and answer from the careful
    baseline alone — a wrong answer, not a crash, and no existing engine test
    passes an unknown profile name through ctx."""
    with pytest.raises(KeyError) as ei:
        E.evaluate_item(act('git_push'), {'chain': CHAIN, 'profiles': {'USER': 'reckless'}})
    assert 'reckless' in str(ei.value)
    with pytest.raises(KeyError) as ei:
        E.evaluate_item(act('git_push'), {'chain': CHAIN,
                                          'profiles': {'USER': 'standard',
                                                       'MISSION': 'reckless'}})
    assert 'reckless' in str(ei.value)
    with pytest.raises(KeyError) as ei:
        E.evaluate_item(act('credential'), {'chain': CHAIN, 'profiles': {'USER': 'standardx'}})
    assert 'standardx' in str(ei.value)

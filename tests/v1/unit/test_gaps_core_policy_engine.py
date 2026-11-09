"""Gap tests for archeus/core/policy/engine.py (T-737): the fail-closed and
denial paths of the engine itself — the e-stop, the missing policy, the replay
— then rule evaluation order, the scope chain, the ALLOW_WITHIN_BOUNDARY
boundaries, the expiry boundary and the error paths of a rule the engine cannot
read. rules.py has its own gap file (test_gaps_core_policy_rules.py); this one
only ever hands the engine plain dicts and `Action`s.

Pure: no database, no clock, no OS, no network, no process. Every path, branch,
host and timestamp is a literal string, so nothing here differs between Linux
and Windows and no skipif is needed.

Each test names the source branch (engine.py line) whose removal or inversion
it would catch; the ten highest-risk ones are listed in the report.
"""

import pytest

from archeus.core.domain import entities
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


def outcome(action, ctx):
    """evaluate_item, or the exception it raises, as (error, result)."""
    try:
        return None, E.evaluate_item(action, ctx)
    except (KeyError, TypeError, ValueError) as exc:
        return type(exc).__name__, None


# ── the fail-closed gates: engine.py:55, 76-79, 123-134 ─────────────────────

def test_an_empty_replay_list_is_no_policy_not_the_live_one():
    """engine.py:55 — `ctx.get('candidates') is not None`, never truthiness: a
    recorded decision whose `matched` snapshot is empty is judged on that empty
    snapshot (nothing covers it -> DENY). Written as `if ctx.get('candidates')`
    an empty replay falls back to the built-in floor, the profiles and the
    owner's live rules, so a decision recorded under no policy at all is
    re-decided by whatever the rules happen to say now."""
    rescue = rule('USER', 'exec', 'ALLOW')
    for live in ([], [rescue]):
        r = E.evaluate_item(act('exec', paths=['src/a.py']),
                            {'chain': CHAIN, 'candidates': [], 'rules': live})
        assert r['decision'] == 'DENY' and r['deciding_rule'] == 'builtin:policy-missing'
        assert r['effective'] == ['builtin:policy-missing']
        assert [m['id'] for m in r['matched']] == ['builtin:policy-missing']


def test_a_replay_decides_from_its_own_snapshot_and_nothing_else():
    """engine.py:55-56 — `candidates` *replaces* built-in + profiles + user
    rules (§9). If the snapshot were appended to `R.builtin()` and the profiles
    instead of replacing them, a replayed decision would be denied by rules it
    was never decided on (and the floor would answer for a class the snapshot
    had an explicit rule for)."""
    allow_prod = rule('TASK', 'destructive', 'ALLOW', id='snap', match={'environment': 'prod'})
    r = E.evaluate_item(act('destructive', environment='prod'),
                        {'chain': CHAIN, 'candidates': [allow_prod]})
    assert r['decision'] == 'ALLOW' and r['effective'] == ['snap']
    assert [m['id'] for m in r['matched']] == ['snap']       # the prod floor is not injected
    # ...and a live locked DENY the snapshot does not hold cannot deny the replay
    replay = E.evaluate_item(act('exec', paths=['src/a.py']), {
        'chain': CHAIN, 'candidates': [rule('USER', 'exec', 'ALLOW', id='snap2')],
        'rules': [rule('USER', 'exec', 'DENY', id='live', locked=True)]})
    assert replay['decision'] == 'ALLOW' and replay['deciding_rule'] == 'snap2'
    assert 'live' not in [m['id'] for m in replay['matched']]


def test_the_emergency_stop_is_answered_before_the_replay_and_the_classes():
    """engine.py:123 — judged before 127 (the unclassified branch) and before
    the replay of engine.py:55: armed, the e-stop denies whatever the context
    holds, including a recorded ALLOW replayed from its own
    snapshot and an action judged as several classes. Move it after either and a
    stored decision answers while STOP is armed. `if ctx.get('estop')` (not
    `if 'estop' in ctx`) is what keeps an unarmed, present key harmless."""
    armed = rule('TASK', 'exec', 'ALLOW', id='snap')
    r = E.evaluate_item(act('exec', paths=['src/a.py']),
                        {'chain': CHAIN, 'candidates': [armed], 'estop': True})
    assert r['decision'] == 'DENY' and r['deciding_rule'] == 'builtin:estop'
    assert [m['id'] for m in r['matched']] == ['builtin:estop']    # the snapshot is gone
    u = E.evaluate_item(act('exec', paths=['src/a.py']),
                        {'chain': CHAIN, 'estop': True, 'unclassified': True,
                         'task_classes': ('deploy', 'destructive'), 'stage': 'action'})
    assert u['decision'] == 'DENY' and u['deciding_rule'] == 'builtin:estop'
    assert u['class'] == 'exec'              # the action's own class, judged once
    assert u['reason'] == 'emergency stop armed: every action is denied'
    assert ev(act('exec', paths=['src/a.py']), estop=False)['decision'] == \
        'ALLOW_WITHIN_BOUNDARY'
    # the stop/missing/contract rules are copied with the judged class, never shared
    assert r['matched'][0]['action_class'] == 'exec'
    assert R.ESTOP['action_class'] == 'read' and R.MISSING['action_class'] == 'read' \
        and R.TASK_CONTRACT['action_class'] == 'read'


def test_nothing_applicable_denies_by_the_class_it_judged():
    """engine.py:76-79 — the fail-closed default: `dict(R.MISSING,
    action_class=cls)` (share the constant, or leave its own 'read', and a
    replay of this decision judges a class that was never asked about), plus
    the whole record it writes. A DENY is never approvable so `step_up` stays
    False even for a step-up class (engine.py:117 reads `decision == 'ASK'`)."""
    r = E.evaluate_item(act('deploy'), {'chain': CHAIN, 'candidates': []})
    assert r['decision'] == 'DENY' and r['class'] == 'deploy'
    assert r['reason'] == 'no policy covers deploy: denied (fail closed)'
    assert r['effective'] == ['builtin:policy-missing'] and r['conflicts'] == []
    assert r['boundary'] is None and r['checks'] is None and r['step_up'] is False
    miss, = r['matched']
    assert miss['action_class'] == 'deploy' and miss['decision'] == 'DENY' \
        and miss['locked'] is True and miss['scope_level'] == 'GLOBAL'
    assert R.MISSING['action_class'] == 'read'


# ── the scope chain: engine.py:44-48, 57-62 ─────────────────────────────────

def test_a_rule_that_names_no_scope_ref_binds_no_scope():
    """engine.py:48 — `r['scope_ref'] is not None and chain.get(level) ==
    r['scope_ref']`: authorization.context builds chains whose TASK and MISSION
    entries are None (no task, mission-less chat), so drop the guard and
    `chain.get(level) == r['scope_ref']` is true for a rule with no ref — every
    context missing that level would be answered by it."""
    loose = rule('TASK', 'exec', 'ALLOW', id='nullref', scope_ref=None)
    for chain in ({'USER': 'usr_1'}, dict(CHAIN, TASK=None), dict(CHAIN), {}):
        r = E.evaluate_item(act('exec', paths=['src/a.py']),
                            {'chain': chain, 'rules': [loose]})
        assert r['deciding_rule'] != 'nullref' and r['effective'] != ['nullref']
        assert 'nullref' not in [m['id'] for m in r['matched']]
    # the same rule, once it names the task the context holds, does bind
    mine = rule('TASK', 'exec', 'ALLOW', id='ref')
    assert E.evaluate_item(act('exec', paths=['src/a.py']),
                           {'chain': CHAIN, 'rules': [mine]})['deciding_rule'] == 'ref'
    # and one that names another task binds nothing
    other = rule('TASK', 'exec', 'ALLOW', id='other', scope_ref='tsk_other')
    assert E.evaluate_item(act('exec', paths=['src/a.py']),
                           {'chain': CHAIN, 'rules': [other]})['deciding_rule'] != 'other'


def test_a_profile_rule_is_on_chain_whether_or_not_its_level_is_in_the_chain():
    """engine.py:46-47 — `if level == 'GLOBAL' or r['source'] == 'profile'`:
    candidate_rules (engine.py:60-62) expands a mission profile with
    `chain.get('MISSION')`, which is None for a mission that has no row of its
    own yet; a profile is Core's answer for the whole context, not a scoped
    row, so it must not fall to the ref comparison. Remove the clause and the
    mission's autonomy silently stops applying."""
    r = E.evaluate_item(act('git_push', host='github.com'),
                        {'chain': {'USER': 'usr_1'}, 'profiles': {'MISSION': 'autonomous'}})
    assert r['deciding_rule'] == 'profile:autonomous@%d:MISSION:git_push' % R.PROFILES_VERSION
    assert r['decision'] == 'ALLOW_WITHIN_BOUNDARY'
    # the USER profile still defaults to `standard` beside it (engine.py:57)
    assert 'profile:standard@%d:USER:git_push' % R.PROFILES_VERSION in \
        [m['id'] for m in r['matched']]
    # a user rule with no ref is *not* on chain: the two sides of 46-48 differ
    assert E.evaluate_item(act('git_push', host='github.com'),
                           {'chain': {'USER': 'usr_1'},
                            'rules': [rule('MISSION', 'git_push', 'ALLOW', id='noref',
                                           scope_ref=None)]})['decision'] == 'ASK'


# ── rule evaluation order: engine.py:35-41, 80-88 ───────────────────────────

def test_effective_is_ordered_strictest_first_not_deepest_first():
    """engine.py:87 — `effective.sort(key=lambda r: (-STRICTNESS[r['decision']],)
    + _order(r))` and `deciding = effective[0]`: the answer is the strictest
    rule in force, not the deepest. Lose the minus (or sort by `_order` alone)
    and a deeper ALLOW decides over the locked DENY the same context holds."""
    deny = rule('USER', 'install', 'DENY', id='deny', locked=True)
    ask = rule('WORKSPACE', 'install', 'ASK', id='ask', locked=True)
    allow = rule('TASK', 'install', 'ALLOW', id='allow')
    for order in ((deny, ask, allow), (allow, ask, deny)):
        r = ev(act('install'), *order)
        assert r['decision'] == 'DENY' and r['deciding_rule'] == 'deny'
        assert r['effective'] == ['deny', 'ask', 'allow']       # strictness, then depth
        assert r['effective'][0] == r['deciding_rule']


def test_a_tie_at_the_deepest_level_breaks_by_id_never_by_input_order():
    """engine.py:41 — `_order` ends in `r['id']`: two rules on one level with
    the same decision (two ALLOW_WITHIN_BOUNDARY rows is the common case) tie
    on depth and strictness, and `specific[0]` — whose boundary alone is then
    checked (engine.py:85, 91) — must be the same rule whichever order the
    caller's list happens to be in. Drop the id from the key and which boundary
    gets enforced follows the row order of the query that read them."""
    p = rule('PROJECT', 'git_commit', R.AWB, id='p', boundary={'paths': ['src/**']})
    q = rule('PROJECT', 'git_commit', R.AWB, id='q', boundary={'paths': ['docs/**']})
    for order in ((p, q), (q, p)):
        r = ev(act('git_commit', paths=['src/a.py']), *order)
        assert r['deciding_rule'] == 'p' and r['effective'] == ['p']
        assert r['boundary'] == {'paths': ['src/**']} and r['conflicts'] == []


def test_a_locked_rule_of_cores_own_at_the_same_level_is_still_broader():
    """engine.py:36 — the `+1` for `source == 'user'` sits an explicit rule
    half a level below Core's own at the same level, so the dispatch contract
    (rules.py TASK_CONTRACT: TASK, ASK, locked) is *broader* than a user's TASK
    rule and reaches `effective` through the locked branch of engine.py:85-86.
    Without the half level, a task's own rule silences the dispatch contract;
    without the contract's `locked` (unpinned anywhere else) the same."""
    own = rule('TASK', 'install', 'ALLOW', id='own')
    r = ev(act('install'), own, stage='action', task_classes=('read',))
    assert r['decision'] == 'ASK' and r['deciding_rule'] == 'builtin:task-contract'
    assert r['effective'] == ['builtin:task-contract', 'own']
    contract = [m for m in r['matched'] if m['id'] == 'builtin:task-contract']
    assert contract and contract[0]['action_class'] == 'install'   # copied, not shared
    assert R.TASK_CONTRACT['locked'] is True and R.TASK_CONTRACT['action_class'] == 'read'
    # declared -> the task's rule answers; and the plan stage never applies it (74)
    assert ev(act('install'), own, stage='action',
              task_classes=('install',))['deciding_rule'] == 'own'
    assert ev(act('install'), own, stage='dispatch',
              task_classes=('install',))['deciding_rule'] == 'own'
    assert ev(act('install'), own, task_classes=('read',))['deciding_rule'] == 'own'
    # no task_classes at all -> nothing is "undeclared", so no contract either (74)
    assert ev(act('install'), own, stage='action', task_classes=None)['decision'] == 'ALLOW'


def test_conflicts_are_the_deepest_rules_only_and_come_back_strictest_first():
    """engine.py:83-84 — `[r['id'] for r in specific] if len({...}) > 1 else []`,
    over the *deepest* rules in precedence order: from `applicable` every
    decision would report a conflict; from `sorted(...)` the audit trail would
    not name the rule that decided first; with `> 0` one rule conflicts with
    itself; without the set (`len(specific) > 1`) two rules that agree do."""
    a = rule('PROJECT', 'web', 'ALLOW', id='a')
    b = rule('PROJECT', 'web', 'ASK', id='b')
    for order in ((a, b), (b, a)):
        r = ev(act('web'), *order)
        assert r['decision'] == 'ASK' and r['deciding_rule'] == 'b'
        assert r['conflicts'] == ['b', 'a']          # decided-first first, both input orders
    # a broader locked restriction is inheritance, not a conflict
    broad = rule('USER', 'web', 'DENY', id='broad', locked=True)
    r = ev(act('web'), a, broad)
    assert r['decision'] == 'DENY' and r['effective'] == ['broad', 'a'] and r['conflicts'] == []
    # two rules, one decision: nothing conflicted
    assert ev(act('web'), a, rule('PROJECT', 'web', 'ALLOW', id='a2'))['conflicts'] == []


def test_the_record_lists_every_rule_that_could_have_applied_in_order():
    """engine.py:69-72, 80 and 113 — `matched` is the audit trail of the answer
    and the replay input (§9): everything that passed the class, chain, match
    and expiry gates, deepest first, then strictest, then id. A rule dropped by
    any of those gates must not appear (a replay would invent it) and one that
    applied without deciding must (a replay that hides a restriction it was
    judged under is not a replay)."""
    expired = rule('TASK', 'exec', 'DENY', id='expired', expires_at='2026-01-01T00:00:00Z')
    elsewhere = rule('TASK', 'exec', 'DENY', id='elsewhere', scope_ref='tsk_other')
    otherclass = rule('TASK', 'git_push', 'DENY', id='otherclass')
    unmatched = rule('TASK', 'exec', 'DENY', id='unmatched', match={'host_glob': 'billing'})
    ask = rule('USER', 'exec', 'ASK', id='ask')
    r = ev(act('exec', paths=['src/a.py'], host='shop.example'), expired, elsewhere,
           otherclass, unmatched, ask, now='2026-06-01T00:00:00Z')
    assert r['decision'] == 'ASK' and r['deciding_rule'] == 'ask'
    assert [m['id'] for m in r['matched']] == [
        'ask', 'profile:standard@%d:USER:exec' % R.PROFILES_VERSION,
        'profile:careful@%d:GLOBAL:exec' % R.PROFILES_VERSION]
    # the profiles applied but did not decide: in the trail, not in force (engine.py:85)
    assert r['effective'] == ['ask']
    for rid in r['effective']:
        assert rid in r['reason']


# ── ALLOW_WITHIN_BOUNDARY: engine.py:90-106 ─────────────────────────────────

def test_every_awb_boundary_in_effect_is_checked_and_each_key_reported_once():
    """engine.py:91-98 — `bounded` is every AWB rule in effective, not just the
    deciding one; the three lists are unioned under `if x not in checks[k]`;
    and `boundary` is the single dict of a one-boundary answer but the list of a
    multi-boundary one. Without the dedupe the recorded checks and the approval's
    boundary repeat a key once per rule; without the `len(bounded) == 1` branch
    a two-boundary answer records only the boundary it proved."""
    locked = rule('USER', 'write_repo', R.AWB, id='locked', boundary={'paths': ['src/**']},
                  locked=True)
    deep = rule('PROJECT', 'write_repo', R.AWB, id='deep',
                boundary={'paths': ['@workspace/**'], 'branches': ['archeus/*']})
    r = ev(act('write_repo', paths=['src/a.py']), locked, deep)
    assert r['decision'] == 'ALLOW_WITHIN_BOUNDARY' and r['deciding_rule'] == 'deep'
    assert r['effective'] == ['deep', 'locked']
    assert r['checks'] == {'checked': ['paths'], 'deferred': ['branches'], 'outside': []}
    assert r['boundary'] == [{'paths': ['@workspace/**'], 'branches': ['archeus/*']},
                             {'paths': ['src/**']}]
    # the locked broader rule is what fails when the deeper one is satisfied
    out = ev(act('write_repo', paths=['docs/a.md']), locked, deep)
    assert out['decision'] == 'ASK' and out['checks']['outside'] == ['paths']
    assert 'outside its boundary on paths' in out['reason']             # engine.py:105-106
    # one AWB rule alone answers with its own boundary, as one dict
    one = ev(act('write_repo', paths=['src/a.py']),
             rule('PROJECT', 'write_repo', R.AWB, id='one', boundary={'paths': ['src/**']}))
    assert one['boundary'] == {'paths': ['src/**']} and one['effective'] == ['one']


def test_a_violated_boundary_escalates_to_the_strictest_outside_in_effect():
    """engine.py:99-101 — `worst = max(bounded, key=STRICTNESS[r['outside']])`:
    on an outside predicate the answer is the strictest `outside` of every AWB
    rule in force and the rule that owns it becomes the deciding one (its id is
    what the denial is recorded against). Reading the deciding rule's own
    `outside` instead — the obvious tightening — lets a locked DENY-outside
    boundary answer ASK, because the deciding rule is the deepest one."""
    loose = rule('PROJECT', 'write_repo', R.AWB, id='loose',
                 boundary={'paths': ['@workspace/**']}, outside='ASK')
    guarded = rule('USER', 'write_repo', R.AWB, id='guarded', boundary={'paths': ['src/**']},
                   outside='DENY', locked=True)
    r = ev(act('write_repo', paths=['docs/a.md']), loose, guarded)   # guarded violated only
    assert r['decision'] == 'DENY' and r['deciding_rule'] == 'guarded'
    assert r['checks']['outside'] == ['paths'] and r['step_up'] is False
    assert r['reason'].startswith('DENY write_repo: ')
    # the reason names the rules as they are written (AWB) beside the answer they gave
    assert 'guarded (ALLOW_WITHIN_BOUNDARY, USER, locked)' in r['reason']
    assert 'outside its boundary' in r['reason']
    # both outside -> still the strictest outside, still the guarded rule that decides
    far = ev(act('write_repo', paths=['../etc/x']), loose, guarded)
    assert far['decision'] == 'DENY' and far['deciding_rule'] == 'guarded'
    # nothing outside -> the AWB answer stands, however the outsides are spelled
    inside = ev(act('write_repo', paths=['src/a.py']), loose, guarded)
    assert inside['decision'] == 'ALLOW_WITHIN_BOUNDARY' and inside['checks']['outside'] == []


@pytest.mark.xfail(strict=True,
                   reason='engine.py:85-86 keeps only specific[0] from the deepest level and '
                          'adds locked rules only when _depth(r) < top_depth, so a locked rule '
                          'that ties with another rule of the same decision never reaches '
                          'effective: its boundary is never checked and which boundary binds '
                          'is settled by the id at engine.py:41')
def test_a_locked_boundary_holds_beside_another_rule_at_the_same_level():
    """engine.py:85-86 — `effective = [specific[0]] + [r for r in applicable if
    r['locked'] and _depth(r) < top_depth]`: only the one strictest deepest rule
    is kept, and locked rules are picked up from *broader* levels only. Two
    ALLOW_WITHIN_BOUNDARY rules on one level tie on strictness, so the loser is
    dropped: its boundary is never checked (engine.py:91-93), it is not in
    `effective` or the reason, and which one loses is settled by the id at
    engine.py:41. A boundary the owner cannot loosen is escaped by writing a
    looser one beside it with a smaller id."""
    loose = rule('PROJECT', 'write_repo', R.AWB, id='a', boundary={'paths': ['@workspace/**']})
    locked = rule('PROJECT', 'write_repo', R.AWB, id='z', boundary={'paths': ['src/**']},
                  locked=True)
    r = ev(act('write_repo', paths=['docs/a.md']), loose, locked)
    assert r['decision'] == 'ASK' and 'z' in r['effective']


# ── the expiry boundary: engine.py:72 ───────────────────────────────────────

def test_expiry_is_inclusive_and_only_the_callers_clock_expires_a_rule():
    """engine.py:72 — `not (r.get('expires_at') and now and r['expires_at'] <=
    now)`: `<=`, so the second a temporary rule expires it is gone (`<` leaves
    it live for the whole of its last second, and a rule the owner revoked by
    expiry keeps answering); and `and now`, so a context with no clock expires
    nothing — the engine never reads one itself, which is why every caller that
    must expire has to pass `now`."""
    temp = rule('USER', 'git_push', 'ALLOW', id='temp', expires_at='2026-01-01T00:00:00Z')
    profile = 'profile:standard@%d:USER:git_push' % R.PROFILES_VERSION
    assert ev(act('git_push'), temp, now='2026-01-01T00:00:00Z')['deciding_rule'] == profile
    assert ev(act('git_push'), temp, now='2026-01-01T00:00:01Z')['deciding_rule'] == profile
    assert ev(act('git_push'), temp, now='2025-12-31T23:59:59Z')['deciding_rule'] == 'temp'
    assert ev(act('git_push'), temp)['deciding_rule'] == 'temp'          # no clock at all
    assert ev(act('git_push'), temp, now=None)['deciding_rule'] == 'temp'
    # a rule with no expiry answers whatever the clock says
    assert ev(act('git_push'), rule('USER', 'git_push', 'ALLOW', id='plain'),
              now='2999-01-01T00:00:00Z')['deciding_rule'] == 'plain'


# ── the unclassified action: engine.py:127-133 ──────────────────────────────

def test_an_unclassified_action_is_always_judged_as_exec_too():
    """engine.py:129 — `sorted(set(ctx.get('task_classes') or ()) | {'exec'})`:
    an action the classifier could not place is judged as exec as well as as
    everything the task holds, so a task with nothing declared cannot escape
    the exec judgement. Drop the union and `results` is empty (ValueError in
    max), or with a permissive default an unclassifiable command is answered as
    the 'read' the executor guessed."""
    # the task declares two harmless classes: only `exec` keeps the answer short
    r = E.evaluate_item(act('read'), {'chain': CHAIN, 'unclassified': True, 'stage': 'action',
                                      'task_classes': ('read', 'web')})
    assert r['class'] == 'exec' and r['decision'] == 'ASK'
    assert r['deciding_rule'] == 'builtin:task-contract'   # exec was undeclared too
    assert r['reason'].startswith('unclassified action, judged as its strictest class: ')
    # with nothing declared at all, exec is still one of the classes judged
    none = E.evaluate_item(act('read'), {'chain': CHAIN, 'unclassified': True,
                                         'stage': 'action', 'task_classes': None})
    assert none['class'] == 'exec' and none['decision'] == 'ASK'
    assert none['deciding_rule'] == 'profile:standard@%d:USER:exec' % R.PROFILES_VERSION
    assert none['checks']['outside'] == ['paths']     # the workspace is not proved yet


def test_an_unclassified_action_answers_the_strictest_class_and_its_step_up():
    """engine.py:131 — `max(results, key=(STRICTNESS[decision], r['class']))`
    and engine.py:117: the whole answer, including its class and its `step_up`,
    comes from the strictest judgement, not from the class the executor
    labelled. An ASK on `deploy` must ask for a step-up proof even on an action
    labelled `read`, or the approval is recorded without one. The class name in
    the key settles a tie without depending on set iteration order."""
    r = E.evaluate_item(act('read'), {'chain': CHAIN, 'unclassified': True,
                                      'task_classes': ('deploy', 'read')})
    assert r['decision'] == 'ASK' and r['class'] == 'deploy' and r['step_up'] is True
    assert r['deciding_rule'] == 'profile:standard@2:USER:deploy'
    assert r['effective'][0] == 'profile:standard@2:USER:deploy' and r['matched']
    assert r['action']['class'] == 'read'            # what was asked, as it was asked
    t = E.evaluate_item(act('read'), {'chain': CHAIN, 'unclassified': True,
                                      'profiles': {'USER': None},
                                      'task_classes': ('deploy', 'install')})
    assert t['decision'] == 'ASK' and t['class'] == 'install'


# ── a rule the engine cannot read: engine.py:36, 41, 86, 94, 100 ────────────

def readable(**kw):
    """One engine rule dict, exactly the shape rules.py builds, minus one key."""
    base = dict(id='g', scope_level='USER', action_class='exec', decision='ALLOW',
                scope_ref='usr_1', locked=False, match={}, boundary=None, outside='ASK',
                source='user', expires_at=None)
    base.update(kw)
    return base


@pytest.mark.parametrize('broken', [
    pytest.param(readable(decision='MAYBE'), id='decision'),
    pytest.param({k: v for k, v in readable().items() if k != 'locked'}, id='no-locked'),
    pytest.param(readable(decision=R.AWB, boundary={'paths': ['src/**']}, outside=None),
                 id='outside-null'),
    pytest.param({k: v for k, v in readable(decision=R.AWB,
                                            boundary={'paths': ['src/**']}).items()
                  if k != 'outside'}, id='outside-absent'),
    pytest.param(readable(decision=R.AWB, boundary=None), id='boundary-null'),
    pytest.param(readable(decision=R.AWB, boundary={'max_cost_band': 'low'}),
                 id='boundary-unprovable'),
])
def test_a_rule_the_engine_cannot_read_never_answers_as_an_allow(broken):
    """engine.py:41 (`R.STRICTNESS[r['decision']]`), 86 (`r['locked']`), 94
    (`check_boundary(r['boundary'], ...)`) and 100 (`STRICTNESS[r['outside']]`)
    index a closed vocabulary directly. Replace any of them with a permissive
    default — `STRICTNESS.get(d, 0)`, `r.get('locked', False)`, `r.get('boundary')`
    defaulting to something that proves nothing — and a rule the engine cannot read
    becomes the allow: it must raise, or answer no looser than ASK. The last case, a
    boundary nothing can satisfy (a cost band an action never carries), is the same
    shape answered by rules.py at the action stage: `outside`, therefore never an
    allow."""
    err, got = outcome(act('exec', paths=['etc/x']),
                       {'chain': CHAIN, 'rules': [broken], 'stage': 'action'})
    assert err is not None or got['decision'] in ('ASK', 'DENY'), (broken, got and got['decision'])


def test_a_rule_the_engine_cannot_place_on_the_chain_binds_nothing():
    """engine.py:48 with `_depth` (engine.py:36, `R.LEVELS.index`): a
    scope_level outside LEVELS never equals a chain entry, so the rule is
    dropped before `LEVELS.index` would raise — the same for a DENY and an
    ALLOW. PolicyRule validates scope_level at insert (entities.py), which is
    what makes the silence safe; it is pinned here because the engine's own
    answer to an unreadable level is silence, not a denial, and a rule treated
    as GLOBAL instead would deny (or allow) outside its scope."""
    for cls, decision, want in (('exec', 'DENY', 'ALLOW_WITHIN_BOUNDARY'),
                                ('git_push', 'ALLOW', 'ASK')):
        action = act(cls, paths=['src/a.py'] if cls == 'exec' else None,
                     host='github.com' if cls == 'git_push' else None)
        bogus = readable(scope_level='SECTOR', decision=decision, id='bogus',
                         locked=decision == 'DENY')
        r = E.evaluate_item(action, {'chain': CHAIN, 'rules': [bogus]})
        assert r['decision'] == want, (cls, decision, r['decision'])
        assert 'bogus' not in [m['id'] for m in r['matched']]


# ── the port: engine.py:137-148 ─────────────────────────────────────────────

def test_the_port_records_the_stage_it_was_asked_for_and_whether_stop_was_armed():
    """engine.py:142-148 — `stage=ctx.get('stage', 'plan')`,
    `estop=bool(ctx.get('estop'))` and `items=(r,)`: the entity the rest of Core
    reads has to say which stage judged, must not carry a truthy non-bool
    through as the stop flag, and must carry the item the decision was built
    from (authorization.judge reads `d.items[0]`). An empty context is the plan
    stage, no stop, the `standard` user profile — never an error."""
    d = E.PolicyEngine().evaluate(act('exec', paths=['src/a.py']),
                                  {'chain': CHAIN, 'stage': 'action', 'estop': 'yes',
                                   'policy_version': 'pv-9'})
    assert isinstance(d, entities.PolicyDecision)
    assert d.decision == 'DENY' and d.estop is True and d.stage == 'action'
    assert d.policy_version == 'pv-9' and d.engine_version == str(R.ENGINE_VERSION)
    assert d.items[0]['decision'] == d.decision and d.items[0]['class'] == 'exec'
    assert d.items[0]['deciding_rule'] == 'builtin:estop'
    empty = E.PolicyEngine().evaluate(act('read'), {})
    assert empty.decision == 'ALLOW' and empty.stage == 'plan' and empty.estop is False
    assert empty.policy_version is None and len(empty.items) == 1
    assert empty.items[0]['matched'], 'a decision with no rules in it cannot be replayed'

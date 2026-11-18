"""T-747: the highest-risk uncovered branches of archeus/core/domain/actions.py.

Guards and value rules of the canonical action and its approval hash: every
class/target/binding word that must be rejected, the fail-closed `start`
binding rule, the `chip_host` exclusion (never policy input, slice I I-F4),
the argv/paths copy-on-build (an approved identity must not mutate afterwards)
and the exact stable bytes the Approval binds to. Pure functions only: no I/O,
no clock, no OS — the same style and fixtures as
tests/v1/unit/test_gaps_core_domain_guards.py (what test_domain.py already
covers — item/binding happy paths, item order-freedom, one unknown class — is
not re-opened here; only the gaps are).
"""

import hashlib

import pytest

from archeus.core.domain import actions

BAD_CLASSES = ['Read', 'READ', 'read ', 'read\n', 'git-commit', '', 'mission.stop',
               'mission.starts', 'delete', 'spend,', None, 7]
BAD_KINDS = ['PLAN', 'plan ', 'approve', 'exec', '', None, 7]
STRING_FIELDS = ('diff_hash', 'environment', 'branch', 'host', 'chip_host')


def _action(**kw):
    kw.setdefault('action_class', 'read')
    kw.setdefault('target', 'README.md')
    return actions.Action(**kw)


def _bind(**kw):
    b = dict(mission_id='msn_a', plan_id='pln_a', plan_version=2, plan_digest='d' * 64)
    b.update(kw)
    return actions.binding(**b)


def _one_item():
    return [actions.item('t1', _action())]


# ── Action.__post_init__: the closed class vocabulary and the target ──────────

def test_every_rule_class_names_a_buildable_action_including_cores_own():
    """actions.py:63 (`action_class not in RULE_CLASSES`): the membership test
    is the whole closed vocabulary. Narrowing it to ACTION_CLASSES would refuse
    `mission.start` (P19 S4); `in` for `not in` would refuse all thirteen."""
    for c in actions.RULE_CLASSES:
        assert _action(action_class=c).action_class == c
    assert 'mission.start' in actions.RULE_CLASSES


@pytest.mark.parametrize('bad', BAD_CLASSES,
                         ids=['title', 'upper', 'trailing', 'newline', 'dash', 'empty',
                              'core-fake', 'core-typo', 'new-word', 'comma', 'none', 'int'])
def test_a_class_outside_the_closed_list_is_refused(bad):
    """actions.py:63-64: a judged action naming e.g. `mission.stop` or `delete`
    would authorise a class no rule can ever speak of; case or whitespace
    leniency would make 'Read' a second, unjudged spelling of 'read'."""
    with pytest.raises(ValueError):
        _action(action_class=bad)


@pytest.mark.parametrize('bad', ['', None, 42, 7.5, ['x'], b'x', True],
                         ids=['empty', 'none', 'int', 'float', 'list', 'bytes', 'bool'])
def test_an_action_needs_a_non_empty_string_target(bad):
    """actions.py:65-66: the `isinstance(self.target, str)` half refuses a
    non-string (bytes/list/int); the `and self.target` half refuses ''. A
    truthiness-only check would let target=42 through; dropping the guard
    approves an action that names nothing."""
    with pytest.raises(ValueError):
        _action(target=bad)


def test_a_single_space_target_is_a_target_boundary_not_a_miss():
    """actions.py:65: the guard is emptiness, not blankness — ' ' is truthy, so
    it builds; a later `strip()` tightening would break this pinned boundary."""
    assert _action(target=' ').target == ' '


@pytest.mark.parametrize('field', STRING_FIELDS)
@pytest.mark.parametrize('bad', [7, ['x'], {'k': 1}], ids=['int', 'list', 'dict'])
def test_the_optional_string_fields_refuse_anything_but_string_or_none(field, bad):
    """actions.py:67-69: one loop over the five; dropping the loop (or one name
    from its tuple) lets a non-string branch/host reach the canonical JSON, so
    branch 'main' and branch 42 become two different approved identities."""
    with pytest.raises(ValueError):
        _action(**{field: bad})


# ── argv/paths: copy-on-build and coercion (actions.py:70-72) ────────────────

def test_a_mutated_caller_list_cannot_change_an_approved_action():
    """actions.py:70-72: `object.__setattr__(self, k, tuple(...))` is the only
    thing between the caller's list and the frozen identity. Without the copy
    (store as-is) appending to argv after judging changes what the approval
    hash covers — the classic approve-then-swap exec hole."""
    argv = ['git', 'status']
    a = _action(action_class='exec', target='git', argv=argv)
    argv.append('&&')
    argv[0] = 'rm'
    assert a.argv == ('git', 'status') and isinstance(a.argv, tuple)
    assert a.canonical_dict()['argv'] == ['git', 'status']


def test_argv_and_paths_members_are_canonicalised_to_strings():
    """actions.py:72: `str(a) for a in ...` — argv=[1] and argv=['1'] must
    canonicalise to the SAME bytes, or an argv built as ints hashes apart from
    the judged argv and the approval binds to one spelling only."""
    a = _action(action_class='exec', target='git', argv=['git', 1, 2.5])
    b = _action(action_class='exec', target='git', argv=('git', '1', '2.5'))
    assert a.argv == b.argv == ('git', '1', '2.5') and a.canonical() == b.canonical()
    assert _action(paths=[1, 'src/**']).paths == ('1', 'src/**')


# ── canonical form: exact bytes, chip_host never in it (actions.py:74-88) ────

def test_the_canonical_form_is_the_exact_pinned_bytes():
    """actions.py:75-88: the field is named 'class', the JSON is sorted and
    separatorless (`_json`). Changing a key name, the 'class' spelling, the
    separators or sort_keys changes every action_hash at once: approvals stop
    matching the bytes they were granted on."""
    assert _action().canonical() == '{"class":"read","target":"README.md"}'
    full = _action(action_class='exec', target='git', argv=('git', 'log'),
                   diff_hash='a' * 64, environment='staging', paths=('docs/**',),
                   branch='archeus/msn_a.t1', host='github.com', chip_host='chip.example')
    assert full.canonical() == (
        '{"argv":["git","log"],"branch":"archeus/msn_a.t1","class":"exec",'
        '"diff_hash":"' + 'a' * 64 + '","environment":"staging","host":"github.com",'
        '"paths":["docs/**"],"target":"git"}')


def test_an_empty_argv_is_canonically_present_but_empty_and_not_the_same_as_none():
    """actions.py:78 (`if v is not None`, boundary None vs ()):
    None means 'unknown, not approved',
    () means 'judged: no arguments'. Folding () to absent (a plain truthiness
    test) would let an approval granted for argv=[] also cover an argv=None
    action of the same class and target."""
    none_argv = _action(action_class='exec', target='git')
    empty_argv = _action(action_class='exec', target='git', argv=())
    assert 'argv' not in none_argv.canonical_dict()
    assert empty_argv.canonical_dict()['argv'] == []
    assert none_argv.canonical() != empty_argv.canonical()


def test_chip_host_is_never_policy_input_never_in_the_hash():
    """actions.py:74-80 with the comment at 58-60 (P21 D6, I-F4): chip_host is
    display only — adding it to the loop's tuple at line 76 would change the
    approval bytes whenever a chip is clicked, and the host field (which IS
    policy input) must still change the hash: both halves are asserted."""
    plain = _action(action_class='web', target='https://x.example/a', host='x.example')
    chipped = _action(action_class='web', target='https://x.example/a', host='x.example',
                      chip_host='c.example')
    assert chipped.chip_host == 'c.example'                  # kept on the entity…
    assert chipped.canonical_dict() == plain.canonical_dict()  # …never in the identity
    h = actions.action_hash('action', _bind(), [actions.item('t1', plain)])
    assert actions.action_hash('action', _bind(), [actions.item('t1', chipped)]) == h
    other = _action(action_class='web', target='https://x.example/a', host='y.example')
    assert actions.action_hash('action', _bind(), [actions.item('t1', other)]) != h


# ── action_hash: the closed kind word and the binding shape ──────────────────

@pytest.mark.parametrize('kind', [k for k in actions.APPROVAL_KINDS if k != 'start'])
def test_every_plan_side_approval_kind_hashes_a_valid_identity(kind):
    """actions.py:104-121 accept side for the four plan-side kinds (the `start`
    kind has its own rule, tested below): a kind word is exactly APPROVAL_KINDS
    and each of the four takes the full binding."""
    h = actions.action_hash(kind, _bind(), _one_item())
    assert len(h) == 64 and all(c in '0123456789abcdef' for c in h)


@pytest.mark.parametrize('bad', BAD_KINDS,
                         ids=['upper', 'trailing', 'approve', 'exec', 'empty', 'none', 'int'])
def test_a_kind_outside_the_closed_list_is_refused(bad):
    """actions.py:109-110: 'approve' or 'exec' is not an approval kind; without
    the guard any word hashes, and an approval minted under a typo'd kind sits
    beside real ones invisible to the guards that match on kind."""
    with pytest.raises(ValueError):
        actions.action_hash(bad, _bind(), _one_item())


@pytest.mark.parametrize('over', [
    'missing-execution', 'extra-key', 'renamed-key', 'empty', 'policy-version',
], ids=['miss', 'extra', 'renamed', 'empty', 'policy'])
def test_a_binding_must_name_exactly_the_seven_identity_keys(over):
    """actions.py:111-112 (`set(bind) != set(BINDING_KEYS)`): one missing key
    ('execution_id' simply absent) must not hash — it would bind to different
    bytes from the same identity spelled `execution_id=None`; a policy_version
    smuggled into the binding is refused (D7: recorded beside, never in)."""
    b = dict(mission_id='msn_a', plan_id='pln_a', plan_version=2, plan_digest='d' * 64,
             task_id=None, task_key=None, execution_id=None)
    if over == 'missing-execution':
        b.pop('execution_id')
    elif over == 'extra-key':
        b['not_a_field'] = 1
    elif over == 'renamed-key':
        b.pop('plan_id')
        b['planid'] = 'pln_a'
    elif over == 'policy-version':
        b['policy_version'] = 7
    else:
        b = {}
    with pytest.raises(ValueError):
        actions.action_hash('action', b, _one_item())


def test_binding_builds_exactly_the_seven_keys_with_none_defaults():
    """actions.py:91-96: the accept side of the guard above — what `binding()`
    returns always passes it, and the three optional slots default to None
    (never absent), so every caller spells an identity the same way."""
    b = actions.binding(mission_id='msn_a', plan_id='pln_a', plan_version=1,
                        plan_digest='d' * 64)
    assert set(b) == set(actions.BINDING_KEYS)
    for k in ('task_id', 'task_key', 'execution_id'):
        assert b[k] is None
    assert actions.action_hash('action', b, _one_item())


# ── the start rule: fail-closed identity for mission.start (113-116) ─────────

def test_a_start_binding_names_the_mission_alone_and_hashes():
    """actions.py:113 accept side (P19 B6): the P19 start consent exists only
    because this branch lets a plan-less binding through; deleting the branch
    makes authorization.start_hash raise and no mission can ever start."""
    h = actions.action_hash('start', actions.binding(mission_id='msn_a', plan_id=None,
                                                     plan_version=None, plan_digest=None),
                            [actions.item(None, _action(action_class='mission.start',
                                                        target='mission:msn_a'))])
    assert len(h) == 64


@pytest.mark.parametrize('bad_mission', [None, '', 0, False],
                         ids=['none', 'empty', 'zero', 'false'])
def test_a_start_binding_without_its_mission_is_refused(bad_mission):
    """actions.py:114 (`not bind['mission_id']`): a start consent bound to no
    mission would authorise starting anything — the truthiness half is the
    fail-closed rule, since every other key is allowed to be None."""
    b = actions.binding(mission_id=bad_mission, plan_id=None, plan_version=None,
                        plan_digest=None)
    with pytest.raises(ValueError):
        actions.action_hash('start', b, _one_item())


@pytest.mark.parametrize('k', ['plan_id', 'plan_version', 'plan_digest', 'task_id',
                               'task_key', 'execution_id'])
@pytest.mark.parametrize('v', ['x', 0], ids=['str', 'zero'])
def test_a_start_binding_with_any_second_name_is_refused(k, v):
    """actions.py:114-115 (`any(v is not None ...)`, `is not None` and not
    truthiness): plan_id='' and plan_version=0 are still *named* — a start
    approval secretly bound to a plan or task row is consent beyond starting."""
    b = actions.binding(mission_id='msn_a', plan_id=None, plan_version=None,
                        plan_digest=None)
    b[k] = v
    with pytest.raises(ValueError):
        actions.action_hash('start', b, _one_item())


# ── non-start kinds: mission, plan and digest are mandatory (117-118) ────────

@pytest.mark.parametrize('kind', ['plan', 'task', 'action', 'route'])
@pytest.mark.parametrize('k', ['mission_id', 'plan_id', 'plan_digest'])
def test_a_plan_side_binding_needs_mission_plan_and_digest(k, kind):
    """actions.py:117-118: each of the three is refused empty and None; a
    truthiness flip or dropping the `and` chain approves a hash whose provenance
    (which mission's which plan version) is not actually pinned."""
    with pytest.raises(ValueError):
        actions.action_hash(kind, _bind(**{k: None}), _one_item())
    with pytest.raises(ValueError):
        actions.action_hash(kind, _bind(**{k: ''}), _one_item())


def test_task_slots_may_be_none_for_a_non_start_kind_boundary():
    """actions.py:117 only guards the three: task_id/task_key/execution_id and
    plan_version may be None for an action-of-plan approval (authorization.py
    binds plan hashes exactly that way) — refusing them would make every plan
    approval raise."""
    assert len(actions.action_hash('plan', _bind(task_id=None, task_key=None,
                                                 execution_id=None), _one_item())) == 64


# ── the digest itself: pinned body, order-free and versioned (119-121) ───────

def test_the_digest_is_sha256_of_the_exact_pinned_body():
    """actions.py:119-121: 'v':1, the four body keys, sorted items — pinned
    byte-for-byte. Bumping 'v', renaming 'binding'/'items', or dropping
    sort_keys silently retires every outstanding approval: the hash no longer
    matches what the card displayed (X02)."""
    expected = ('{"binding":{"execution_id":null,"mission_id":"msn_a","plan_digest":"'
                + 'd' * 64 + '","plan_id":"pln_a","plan_version":2,"task_id":null,'
                '"task_key":null},"items":[{"action":{"class":"read","target":'
                '"README.md"},"task":"t1"}],"kind":"action","v":1}')
    h = actions.action_hash('action', _bind(), _one_item())
    assert h == hashlib.sha256(expected.encode('utf-8')).hexdigest()


def test_the_hash_ignores_the_construction_order_of_items_and_bindings():
    """actions.py:121 (`sorted(..., key=_json)`) + 88 (`sort_keys=True`): items
    arrive in any order, the binding dict was built by `binding()` in field
    order — the digest must not care. Unsorting the items or dropping sort_keys
    splits one identity into several hashes."""
    a = actions.item('t1', _action())
    b = actions.item('t2', _action(action_class='web', target='https://x.example'))
    forward = actions.action_hash('plan', _bind(), [a, b])
    assert forward == actions.action_hash('plan', _bind(), [b, a])
    shuffled_bind = {k: v for k, v in reversed(list(_bind().items()))}
    assert forward == actions.action_hash('plan', shuffled_bind, [a, b])


def test_item_names_the_task_and_the_canonical_action_and_nothing_else():
    """actions.py:99-101: exactly {'task','action'} — renaming either key (or
    leaking a third) changes every hash above and lets a non-canonical copy of
    the action sneak into the item."""
    act = _action(action_class='exec', target='git', argv=['git', 'push'])
    got = actions.item('t1', act)
    assert set(got) == {'task', 'action'} and got['task'] == 't1'
    assert got['action'] == act.canonical_dict()
    assert actions.item(None, act)['task'] is None           # the start_hash spelling


# ── the closed constant lists themselves ─────────────────────────────────────

def test_the_constant_vocabularies_are_the_closed_lists_and_set_unions():
    """actions.py:16-40: RULE_CLASSES must stay exactly ACTION_CLASSES +
    CORE_CLASSES, and the match/boundary/kind/binding lists are closed words.
    Adding e.g. 'mission.stop' to CORE_CLASSES would let rules name a class no
    executor ever produces; duplicating a word would make membership ambiguous."""
    assert actions.RULE_CLASSES == actions.ACTION_CLASSES + actions.CORE_CLASSES
    assert actions.CORE_CLASSES == ('mission.start',)
    assert actions.DECISIONS == ('ALLOW', 'ASK', 'ALLOW_WITHIN_BOUNDARY', 'DENY')
    assert actions.APPROVAL_KINDS == ('plan', 'task', 'action', 'route', 'start')
    assert actions.BINDING_KEYS == ('mission_id', 'plan_id', 'plan_version', 'plan_digest',
                                    'task_id', 'task_key', 'execution_id')
    assert actions.MATCH_KEYS == ('environment', 'path_glob', 'branch_glob', 'host_glob',
                                  'command_glob', 'min_cost_band')
    assert actions.BOUNDARY_KEYS == ('paths', 'branches', 'hosts', 'environments',
                                     'max_cost_band')
    for lst in (actions.RULE_CLASSES, actions.DECISIONS, actions.APPROVAL_KINDS,
                actions.BINDING_KEYS, actions.MATCH_KEYS, actions.BOUNDARY_KEYS):
        assert len(set(lst)) == len(lst)

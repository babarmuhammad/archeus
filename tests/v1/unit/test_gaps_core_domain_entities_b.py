"""T-701: the highest-risk uncovered branches of archeus/core/domain/entities.py 960-1906.

Executions, sessions, evidence, resources and control rows: the fail-closed
guards of their `_check`, the closed vocabularies they validate against, the id
kind of every reference, the bounds of every counter, the fields frozen at
insert and the lifecycle each row holds. Pure construction — no I/O, no clock,
no OS call, no process, nothing Windows- or POSIX-specific: a field is an
opaque string here, never a path the test touches.

The style and the fixtures are tests/v1/unit/test_domain.py's (`_sample`,
`test_invalid_values_are_refused`); only the branches no test there (or in the
module's own `test_*_units.py` files) reaches are re-opened here. Each test
names the source branch it would catch being removed or inverted.
"""

import dataclasses
import math

import pytest

from archeus.core.domain import entities as E, ids, states
from archeus.core.domain.values import Ref

#: a lowercase sha256 / sha1, the way the domain spells them
SHA1, SHA256 = 'b' * 40, 'a' * 64


def _i(kind):
    return ids.new_id(kind)


# ── fixtures: one builder per entity of the section ─────────────────────────

def _execution(**kw):
    kw.setdefault('task_id', _i('task'))
    kw.setdefault('mission_id', _i('mission'))
    return E.Execution(id=_i('execution'), **kw)


def _session(**kw):
    kw.setdefault('harness_id', 'fake')
    kw.setdefault('workspace_id', ids.GLOBAL_WORKSPACE)
    kw.setdefault('cwd', 'projects/app')
    kw.setdefault('mode', 'manual')
    return E.Session(id=_i('session'), **kw)


def _checkpoint(**kw):
    kw.setdefault('execution_id', _i('execution'))
    kw.setdefault('mission_id', _i('mission'))
    kw.setdefault('trigger', 'task_boundary')
    return E.Checkpoint(id=_i('checkpoint'), **kw)


def _verification(**kw):
    kw.setdefault('subject', Ref('task', _i('task')))
    kw.setdefault('verifier', 'code')
    return E.Verification(id=_i('verification'), **kw)


def _review(**kw):
    kw.setdefault('mission_id', _i('mission'))
    kw.setdefault('reviewer', 'brain')
    return E.Review(id=_i('review'), **kw)


def _feedback(**kw):
    kw.setdefault('subject', Ref('mission', _i('mission')))
    kw.setdefault('signal', 'positive')
    return E.Feedback(id=_i('feedback'), **kw)


def _artifact(**kw):
    kw.setdefault('id', SHA256)
    kw.setdefault('media_type', 'text/markdown')
    kw.setdefault('size', 10)
    return E.Artifact(**kw)


def _artifact_record(**kw):
    kw.setdefault('artifact_id', SHA256)
    kw.setdefault('produced_by', Ref('execution', _i('execution')))
    kw.setdefault('kind', 'report')
    return E.ArtifactRecord(id=_i('artifact_record'), **kw)


def _package(**kw):
    kw.setdefault('workspace_id', ids.GLOBAL_WORKSPACE)
    kw.setdefault('subject_kind', 'mission')
    kw.setdefault('subject_id', _i('mission'))
    return E.ContextPackage(id=_i('context_package'), **kw)


def _terms(**kw):
    kw.setdefault('id', 'claude_code')
    return E.ProviderTerms(**kw)


def _harness(**kw):
    kw.setdefault('id', 'claude_code')
    return E.Harness(**kw)


def _account(**kw):
    kw.setdefault('harness_id', 'claude_code')
    kw.setdefault('label', 'Work')
    kw.setdefault('auth_kind', 'api_key')
    return E.Account(id=_i('account'), **kw)


def _model(**kw):
    kw.setdefault('id', 'claude-opus-5-5')
    kw.setdefault('family', 'opus')
    kw.setdefault('tier', 'large')
    kw.setdefault('context_window', 1_000_000)
    return E.Model(**kw)


def _offer(**kw):
    kw.setdefault('account_id', _i('account'))
    kw.setdefault('model_id', 'claude-opus-5-5')
    return E.ModelOffer(**kw)


def _policy(**kw):
    kw.setdefault('account_id', _i('account'))
    return E.ResourcePolicy(id=_i('resource_policy'), **kw)


def _opt_in(**kw):
    kw.setdefault('kind', 'plugin')
    kw.setdefault('name', 'caveman@caveman')
    if kw.get('account_id') is None and kw.get('project_id') is None and 'account_id' not in kw \
            and 'project_id' not in kw:
        kw['account_id'] = _i('account')          # the owner the test did not name
    return E.OptIn(id=_i('opt_in'), **kw)


def _owner_for(owner):
    """Exactly one of the two OptIn owners (entities.py:1546 counts them)."""
    return {'account_id': _i('account')} if owner == 'account' else {'project_id': _i('project')}


def _snapshot(**kw):
    kw.setdefault('account_id', _i('account'))
    kw.setdefault('window', '5h')
    kw.setdefault('utilisation_pct', 42.5)
    kw.setdefault('source', 'usage_api')
    kw.setdefault('observed_at', '2026-11-02T10:00:00Z')
    return E.UsageSnapshot(id=_i('usage_snapshot'), **kw)


def _ledger(**kw):
    kw.setdefault('route_decision_id', _i('route_decision'))
    return E.UsageLedger(id=_i('usage_ledger'), **kw)


def _route(**kw):
    kw.setdefault('subject', Ref('task', _i('task')))
    return E.RouteDecision(id=_i('route_decision'), **kw)


def _node(**kw):
    kw.setdefault('name', 'this-pc')
    return E.ExecutionNode(id=_i('execution_node'), **kw)


def _rule(**kw):
    kw.setdefault('scope_level', 'USER')
    kw.setdefault('action_class', 'exec')
    kw.setdefault('decision', 'ALLOW')
    kw.setdefault('scope_ref', _i('user'))
    return E.PolicyRule(id=_i('policy_rule'), **kw)


def _global_rule(**kw):
    kw.setdefault('scope_level', 'GLOBAL')
    kw.setdefault('action_class', 'exec')
    kw.setdefault('decision', 'ASK')
    kw.setdefault('scope_ref', None)
    kw.setdefault('source', 'builtin')
    return E.PolicyRule(id=_i('policy_rule'), **kw)


def _decision(**kw):
    kw.setdefault('decision', 'ALLOW')
    return E.PolicyDecision(id=_i('policy_decision'), **kw)


def _approval(**kw):
    kw.setdefault('subject', Ref('plan', _i('plan')))
    kw.setdefault('action_hash', SHA256)
    kw.setdefault('requested_by', _i('principal'))
    return E.Approval(id=_i('approval'), **kw)


def _automation(**kw):
    kw.setdefault('workspace_id', ids.GLOBAL_WORKSPACE)
    kw.setdefault('name', 'docs on new model')
    return E.Automation(id=_i('automation'), **kw)


def _run(**kw):
    kw.setdefault('automation_id', _i('automation'))
    kw.setdefault('triggering_event_seq', 7)
    return E.AutomationRun(id=_i('automation_run'), **kw)


# ── Execution (entities.py:962-1060): the state, the hashes, the counters ─────

@pytest.mark.parametrize('state', list(states.states('execution')))
def test_an_execution_accepts_every_state_its_machine_declares(state):
    """entities.py:964 `_STATE = ('state', 'execution')` + the membership test
    of entities.py:104-105: narrowing that machine (or the tuple) would make a
    row Core can no longer write."""
    assert _execution(state=state).state == state


@pytest.mark.parametrize('state', ['OPEN', 'PENDING', 'APPROVED', 'AWAITING_HUMAN', 'ONLINE',
                                   'UNVERIFIED', 'ENABLED', 'CLAIMED'],
                         ids=['session', 'task', 'plan', 'verification', 'node', 'account',
                              'automation', 'automation_run'])
def test_an_execution_refuses_a_state_of_another_machine(state):
    """entities.py:104-105: dropping the membership test lets a foreign lifecycle
    state live on an Execution row, where no edge of the table leads out."""
    with pytest.raises(ValueError, match='is not a execution state'):
        _execution(state=state)


def test_an_execution_with_no_state_said_starts_at_the_machines_initial_one():
    """entities.py:102-103: `state=None` defaults to `states.initial`; inverted
    defaults insert an execution whose first transition has no edge in."""
    assert _execution(state=None).state == states.initial('execution') == 'INTENT'


def test_an_execution_inventory_is_a_sha256_artifact_or_nothing():
    """entities.py:1050-1051: inverting `_HEX64.fullmatch` (or accepting any
    string) lets an `isolated` decision cite an artifact Core cannot resolve."""
    assert _execution(inventory_sha256=SHA256).inventory_sha256 == SHA256
    assert _execution(inventory_sha256=None).inventory_sha256 is None      # never inventoried
    for bad in ('A' * 64, 'a' * 63, 'a' * 65, 'sha256:' + 'a' * 58, 'inventory'):
        with pytest.raises(ValueError, match='names an artifact'):
            _execution(inventory_sha256=bad)


def test_an_inventory_that_is_not_a_string_is_refused_as_a_value_error():
    """entities.py:1050: three digest guards in this range (1050, 1232, 1332)
    hand the value straight to `_HEX64.fullmatch`, so a JSON payload with a
    number where a digest belongs arrives as a TypeError, not the ValueError a
    writer catches; `Approval.action_hash` (entities.py:1846) is the only one
    that tests `isinstance(..., str)` first."""
    with pytest.raises(ValueError):
        _execution(inventory_sha256=7)


@pytest.mark.parametrize('isolated', [True, False], ids=['true', 'false'])
def test_an_isolation_decision_is_a_bool_when_it_is_there(isolated):
    """entities.py:1052-1053: None means unknown, a bool means decided."""
    assert _execution(isolated=isolated).isolated is isolated


@pytest.mark.parametrize('isolated', [1, 0, 'true', 'yes', '', [], 1.0],
                         ids=['one', 'zero', 'true-str', 'yes', 'empty-str', 'list', 'float'])
def test_an_isolation_decision_that_is_not_a_bool_is_refused(isolated):
    """entities.py:1052-1053: `isolated='false'` is truthy — without the
    isinstance it would read as isolated, which is the fail-open direction."""
    with pytest.raises(ValueError, match='isolated is a bool or None'):
        _execution(isolated=isolated)


@pytest.mark.parametrize('rev', [SHA1, SHA256, '0' * 40, 'f' * 64],
                         ids=['sha1', 'sha256', 'zeros', 'ff64'])
def test_a_seed_revision_is_a_lowercase_commit_id(rev):
    """entities.py:1054-1056 (`SEED_REVISION`, both digest lengths, lowercase)."""
    assert _execution(seed_revision=rev).seed_revision == rev


@pytest.mark.parametrize('rev', ['B' * 40, 'A' * 64, 'b' * 39, 'b' * 41, 'HEAD', 'main',
                                 'git:abc', 'g' * 40, 'b' * 39 + 'g'],
                         ids=['upper40', 'upper64', 'short', 'long', 'head', 'branch',
                              'prefixed', 'non-hex', 'non-hex-tail'])
def test_a_seed_revision_that_is_not_a_commit_id_is_refused(rev):
    """entities.py:1054-1056: a non-commit seed (a branch name, an uppercase
    hex) would silently become the base of every later step."""
    with pytest.raises(ValueError, match='seed_revision is a commit id'):
        _execution(seed_revision=rev)


def test_an_import_revision_is_a_sha1_and_never_the_wider_seed_grammar():
    """entities.py:1057-1060: the import commit is what P2 wrote with this
    repository's own hash; widening it to SEED_REVISION (a sha256) or to
    uppercase would name a commit that store cannot resolve."""
    assert _execution(import_revision=SHA1).import_revision == SHA1
    for bad in (SHA256, 'B' * 40, 'b' * 39, 'b' * 41, 'HEAD'):
        with pytest.raises(ValueError, match='import_revision is a commit id'):
            _execution(import_revision=bad)


@pytest.mark.parametrize('field', ['attempt'], ids=['attempt'])
def test_an_attempt_count_starts_at_one(field):
    """entities.py:968 `_MIN1 = ('attempt',)`: an attempt 0 row would be
    chargeable before it was ever dispatched."""
    assert getattr(_execution(**{field: 1}), field) == 1
    for bad in (0, -1, True, False, None, '1', 1.0):
        with pytest.raises(ValueError, match='must be an integer >= 1'):
            _execution(**{field: bad})


@pytest.mark.parametrize('field', ['process_seq', 'hook_seq', 'stream_offset'],
                         ids=['process_seq', 'hook_seq', 'stream_offset'])
def test_an_execution_cursor_is_never_below_zero(field):
    """entities.py:973 `_NONNEG`: a negative hook_seq or stream offset rewinds
    the replay the hook and the stream reader depend on."""
    assert getattr(_execution(**{field: 0}), field) == 0
    for bad in (-1, True, None, '0', 1.5):
        with pytest.raises(ValueError, match='must be an integer >= 0'):
            _execution(**{field: bad})


@pytest.mark.parametrize('field,value', [
    ('exit_reason', 'ok'), ('exit_reason', 'handoff'),
    ('stop_reason', 'estop'), ('stop_reason', 'path_too_long'), ('stop_reason', 'spawn'),
    ('failure', 'resource'), ('failure', 'limit'),
    ('served_level', 'BILLED'), ('served_level', 'REQUESTED'),
], ids=['ok', 'handoff', 'estop', 'path_too_long', 'spawn', 'resource', 'limit', 'billed',
        'requested'])
def test_an_end_is_reported_in_the_closed_vocabulary(field, value):
    """entities.py:969-972 `_CHOICES`: the words the UI and the breaker read."""
    assert getattr(_execution(**{field: value}), field) == value


@pytest.mark.parametrize('field,value', [
    ('exit_reason', 'timeout'), ('exit_reason', 'OK'), ('exit_reason', ''),
    ('stop_reason', 'user '), ('stop_reason', 'ESTOP'), ('stop_reason', 'paused'),
    ('failure', 'resources'), ('failure', 'unknown'),
    ('served_level', 'served'), ('served_level', 'GUESS'),
], ids=['exit-timeout', 'exit-upper', 'exit-empty', 'stop-space', 'stop-upper', 'stop-paused',
        'fail-plural', 'fail-unknown', 'level-lower', 'level-guess'])
def test_an_end_the_vocabulary_does_not_name_is_refused(field, value):
    """entities.py:969-972: an unlisted word must not be stored to be read back
    by a consumer that switches on the closed list."""
    with pytest.raises(ValueError, match='must be one of'):
        _execution(**{field: value})


@pytest.mark.parametrize('field', ['task_id', 'mission_id', 'plan_id', 'route_decision_id',
                                   'account_id', 'policy_decision_id', 'session_id',
                                   'handoff_from'],
                         ids=['task', 'mission', 'plan', 'route', 'account', 'policy',
                              'session', 'handoff'])
def test_an_execution_reference_names_the_kind_it_says(field):
    """entities.py:965-967 `_REFS` + entities.py:122-127: a reference has to carry
    its own prefix, or a `mission_id` could quietly hold a task and the execution
    would be attached to the wrong work."""
    kind = field[:-3]
    good = _execution(**{field: _i(kind) if field != 'handoff_from' else _i('execution')})
    assert getattr(good, field) is not None
    with pytest.raises(ValueError, match='is not a'):
        _execution(**{field: _i('checkpoint')})
    with pytest.raises(ValueError, match='is not a'):
        _execution(**{field: '%s_not_a_ulid' % kind})


# ── Session (entities.py:1071-1128): launches and the headless binding ───────

def test_a_headless_session_names_the_execution_it_ran():
    """entities.py:1123-1124: a headless session with no execution is a
    provider conversation nobody owns — the guard is what refuses it."""
    exe = _i('execution')
    assert _session(mode='headless', execution_id=exe).execution_id == exe
    for mode in ('headless',):
        with pytest.raises(ValueError, match='headless session names the execution'):
            _session(mode=mode, execution_id=None)


@pytest.mark.parametrize('mode', list(E.SESSION_MODES), ids=list(E.SESSION_MODES))
def test_a_session_says_how_it_came_to_exist(mode):
    """entities.py:1083 `_CHOICES = {'mode': SESSION_MODES}`."""
    kw = {'execution_id': _i('execution')} if mode == 'headless' else {}
    assert _session(mode=mode, **kw).mode == mode


@pytest.mark.parametrize('mode', ['HEADLESS', 'interactive', 'attached', '', None],
                         ids=['upper', 'interactive', 'attached', 'empty', 'none'])
def test_a_session_mode_the_domain_does_not_have_is_refused(mode):
    """entities.py:1083: `mode` decides whether a launch is allowed at all."""
    with pytest.raises(ValueError, match='mode must be one of'):
        _session(mode=mode)


@pytest.mark.parametrize('launched,asked,ok', [
    (0, 0, True), (1, 1, True), (3, 5, True),                # at or below the ask
    (1, 0, False), (2, 1, False),                            # more than was asked
    (0, -1, None),                                           # malformed: see below
], ids=['none', 'equal', 'under', 'over-zero', 'over-one', 'negative-asked'])
def test_a_session_never_reports_more_launches_than_it_was_asked_for(launched, asked, ok):
    """entities.py:1125-1126: dropping the comparison lets a session that was
    asked for nothing report a terminal it opened."""
    if ok is None:
        with pytest.raises(ValueError, match='must be an integer >= 0'):
            _session(launch_seq=asked, launched_seq=launched)
    elif ok:
        assert _session(launch_seq=asked, launched_seq=launched).launched_seq == launched
    else:
        with pytest.raises(ValueError, match='more than it was asked to'):
            _session(launch_seq=asked, launched_seq=launched)


@pytest.mark.parametrize('claimed,asked,ok', [
    (0, 0, True), (1, 1, True), (1, 4, True),                # T-116: one claim per ask
    (1, 0, False), (4, 3, False), (2, 1, False),
], ids=['none', 'equal', 'under', 'over-zero', 'over-one', 'over-by-one'])
def test_a_session_never_claims_a_launch_it_was_not_asked_for(claimed, asked, ok):
    """entities.py:1127-1128 (T-116): the claim is what stops a second
    terminal for one launch_seq; a claim above `launch_seq` forges that
    authority, so the row must not exist."""
    if ok:
        assert _session(launch_seq=asked, launch_claimed_seq=claimed).launch_claimed_seq \
            == claimed
    else:
        with pytest.raises(ValueError, match='claim a launch it was not asked for'):
            _session(launch_seq=asked, launch_claimed_seq=claimed)


@pytest.mark.parametrize('field', ['last_seen_seq', 'launch_seq', 'launched_seq',
                                   'launch_claimed_seq'],
                         ids=['last_seen', 'launch', 'launched', 'claimed'])
def test_a_session_cursor_is_never_below_zero(field):
    """entities.py:1084 `_NONNEG`: a negative cursor would replay the log."""
    assert getattr(_session(**{field: 0}), field) == 0
    for bad in (-1, True, None, '0'):
        with pytest.raises(ValueError, match='must be an integer >= 0'):
            _session(**{field: bad})


@pytest.mark.parametrize('field', ['harness_id', 'cwd'], ids=['harness', 'cwd'])
def test_a_session_names_a_harness_and_a_working_directory(field):
    """entities.py:1078 `_TEXT`: one harness, one cwd per provider conversation."""
    for bad in ('', '   ', None, 7):
        with pytest.raises(ValueError, match='must be a non-empty string'):
            _session(**{field: bad})


@pytest.mark.parametrize('state', list(states.states('session')))
def test_a_session_accepts_the_three_states_of_its_machine(state):
    """entities.py:1077 `_STATE = ('state', 'session')` (nothing here is
    terminal, state-machines §12)."""
    assert _session(state=state).state == state


@pytest.mark.parametrize('state', ['RUNNING', 'PENDING', 'DRAFT', 'CLAIMED', 'AVAILABLE'],
                         ids=['execution', 'task', 'plan', 'automation_run', 'account'])
def test_a_session_refuses_a_state_of_another_machine(state):
    """entities.py:104-105: `OPEN/CLOSED/LOST` only; anything else is unreachable."""
    with pytest.raises(ValueError, match='is not a session state'):
        _session(state=state)


def test_a_session_reference_of_the_wrong_kind_is_refused():
    """entities.py:1079-1082 `_REFS`: a task id in `execution_id` would bind a
    conversation to a row that is not an execution."""
    with pytest.raises(ValueError, match='is not a execution id'):
        _session(execution_id=_i('task'))
    with pytest.raises(ValueError, match='is not a session id'):
        _session(handoff_from_session_id=_i('task'))
    with pytest.raises(ValueError, match='is not a account id'):
        _session(account_id='acc_x')


# ── Checkpoint (entities.py:1132-1161): immutable history ────────────────────

@pytest.mark.parametrize('trigger', list(E.CHECKPOINT_TRIGGERS), ids=list(E.CHECKPOINT_TRIGGERS))
def test_a_checkpoint_says_why_history_was_written(trigger):
    """entities.py:1137 `_CHOICES = {'trigger': CHECKPOINT_TRIGGERS}`."""
    assert _checkpoint(trigger=trigger).trigger == trigger


@pytest.mark.parametrize('trigger', ['TASK_BOUNDARY', 'timer', '', None, 'pressure '],
                         ids=['upper', 'timer', 'empty', 'none', 'trailing-space'])
def test_a_checkpoint_that_came_to_exist_for_no_declared_reason_is_refused(trigger):
    """entities.py:1137: the trigger is what the next prompt suffix trusts."""
    with pytest.raises(ValueError, match='trigger must be one of'):
        _checkpoint(trigger=trigger)


def test_a_checkpoint_cursor_and_references_are_checked():
    """entities.py:1138-1140: `as_of_seq >= 0`, and the row must point at real
    executions, missions, tasks, sessions, plans and packages."""
    assert _checkpoint(as_of_seq=0).as_of_seq == 0
    with pytest.raises(ValueError, match='must be an integer >= 0'):
        _checkpoint(as_of_seq=-1)
    for field in ('execution_id', 'mission_id', 'task_id', 'session_id', 'plan_id',
                  'context_package_id'):
        with pytest.raises(ValueError, match='is not a'):
            _checkpoint(**{field: _i('checkpoint')})


# ── Verification (entities.py:1172-1241): the evidence a mission is judged on ─

@pytest.mark.parametrize('kind', ['task', 'mission'], ids=['task', 'mission'])
def test_a_verification_is_of_a_task_or_a_mission(kind):
    """entities.py:1215-1216: the two subjects a verifier can really check."""
    kw = {'criterion': 0} if kind == 'mission' else {}
    assert _verification(subject=Ref(kind, _i(kind)), **kw).subject.kind == kind


@pytest.mark.parametrize('kind', ['plan', 'execution', 'checkpoint', 'review', 'user_device',
                                  'mission '],
                         ids=['plan', 'execution', 'checkpoint', 'review', 'principal',
                              'trailing-space'])
def test_a_verification_of_anything_else_is_refused(kind):
    """entities.py:1215-1216: widening this pair lets a row claim to verify
    something no verifier can observe."""
    with pytest.raises(ValueError, match='of a task or a mission'):
        _verification(subject=Ref(kind, _i('task')))


def test_only_a_mission_verification_names_a_criterion():
    """entities.py:1217-1218: the `!=` of `criterion is not None` against
    `subject.kind == 'mission'` — either side of it alone would let an
    unbound mission verification count as a passing criterion."""
    with pytest.raises(ValueError, match='names its criterion'):
        _verification(subject=Ref('mission', _i('mission')))
    with pytest.raises(ValueError, match='names its criterion'):
        _verification(subject=Ref('task', _i('task')), criterion=0)


@pytest.mark.parametrize('criterion', [-1, True, False, 1.0, '0'],
                         ids=['negative', 'true', 'false', 'float', 'string'])
def test_a_criterion_is_a_real_index(criterion):
    """entities.py:1219-1222: an index, not a bool or a float. A bool index
    would read as criterion 0 or 1 and decide a mission."""
    with pytest.raises(ValueError, match='criterion is an index'):
        _verification(subject=Ref('mission', _i('mission')), criterion=criterion)


def test_only_a_task_verification_names_the_execution_it_watched():
    """entities.py:1223-1225: `execution_id` is the end that moved a TASK to
    VERIFYING; a mission row with one (or a foreign id there) would bind a
    mission verdict to one execution's process."""
    exe = _i('execution')
    assert _verification(execution_id=exe).execution_id == exe
    with pytest.raises(ValueError, match='an execution of a task subject'):
        _verification(subject=Ref('mission', _i('mission')), criterion=2, execution_id=exe)
    with pytest.raises(ValueError, match='an execution of a task subject'):
        _verification(execution_id=_i('task'))


GOOD_CHECK = {'name': 'pytest', 'kind': 'command', 'result': 'pass'}


@pytest.mark.parametrize('check', [
    GOOD_CHECK,
    {'name': 'snapshot', 'kind': 'git', 'result': 'error'},
    dict(GOOD_CHECK, output_sha256=SHA256, exit_code=0, truncated=False),
], ids=['command', 'git-error', 'with-sha'])
def test_a_check_is_the_evidence_row_the_domain_declares(check):
    """entities.py:1226-1233: the accepted side of the same guard."""
    assert _verification(checks=(check,)).checks == (check,)


@pytest.mark.parametrize('check', [
    {'kind': 'command', 'result': 'pass'},
    {'name': 'pytest', 'result': 'pass'},
    {'name': 'pytest', 'kind': 'shell', 'result': 'pass'},
    {'name': 'pytest', 'kind': 'COMMAND', 'result': 'pass'},
    {'name': 'pytest', 'kind': 'command', 'result': 'ok'},
    {'name': 'pytest', 'kind': 'command', 'result': 'PASSED'},
    {'name': None, 'kind': 'command', 'result': 'pass'},
    {'name': 7, 'kind': 'command', 'result': 'pass'},
    'pytest',
    None,
], ids=['no-name', 'no-kind', 'kind-shell', 'kind-upper', 'result-ok', 'result-upper',
        'none-name', 'int-name', 'not-a-dict', 'none'])
def test_a_malformed_check_is_never_recorded_as_evidence(check):
    """entities.py:1226-1230: a check Core cannot have run must not become the
    reason a task succeeded."""
    with pytest.raises(ValueError, match='a check is'):
        _verification(checks=(check,))


@pytest.mark.parametrize('sha', ['a' * 63, 'A' * 64, 'not-a-hash', 'z' * 64, '0' * 63 + 'g'],
                         ids=['short', 'upper', 'text', 'non-hex', 'non-hex-tail'])
def test_a_check_output_is_named_by_a_sha256(sha):
    """entities.py:1231-1233: `output_sha256` is the artifact id of the output;
    anything else is an evidence pointer Core cannot resolve."""
    with pytest.raises(ValueError, match='sha256 artifact id'):
        _verification(checks=(dict(GOOD_CHECK, output_sha256=sha),))


def test_a_check_output_that_is_not_a_string_is_refused_as_a_value_error():
    with pytest.raises(ValueError):
        _verification(checks=(dict(GOOD_CHECK, output_sha256=7),))


GOOD_CRITERION = {'index': 0, 'text': 'docs build', 'check': 'automatic', 'result': 'satisfied'}


@pytest.mark.parametrize('reading', [
    GOOD_CRITERION,
    {'index': 3, 'text': 'owner agrees', 'check': 'human', 'result': 'unknown'},
    {'index': 0, 'text': 'x', 'check': 'human', 'result': 'failed'},
], ids=['satisfied', 'unknown', 'failed'])
def test_a_criterion_reading_is_a_reading(reading):
    """entities.py:1234-1238: the accepted side."""
    assert _verification(criteria=(reading,)).criteria == (reading,)


@pytest.mark.parametrize('reading', [
    {'index': 0, 'text': 'x', 'check': 'automatic'},
    {'index': 0, 'text': 'x', 'result': 'satisfied'},
    {'index': 0, 'text': 'x', 'check': 'auto', 'result': 'satisfied'},
    {'index': 0, 'text': 'x', 'check': 'automatic', 'result': 'pass'},
    {'index': 0, 'text': 'x', 'check': 'automatic', 'result': 'PASS'},
    'satisfied',
], ids=['no-result', 'no-check', 'check-auto', 'result-pass', 'result-upper', 'not-a-dict'])
def test_a_criterion_reading_that_is_not_one_is_refused(reading):
    """entities.py:1234-1238: `result` is a CRITERION result and `check` a
    CRITERION_CHECKS kind; mixing the two vocabularies (a check's `pass` for a
    criterion) would read as a satisfied criterion."""
    with pytest.raises(ValueError, match='criterion reading is'):
        _verification(criteria=(reading,))


@pytest.mark.parametrize('errors', [-1, True, False, '2', 1.0],
                         ids=['negative', 'true', 'false', 'string', 'float'])
def test_an_error_count_is_a_count(errors):
    """entities.py:1239-1241: `errors` decides whether the row holds the
    mission; a bool or a string is not a count."""
    with pytest.raises(ValueError, match='errors is an integer'):
        _verification(errors=errors)


def test_a_verification_states_who_verifies_it():
    """entities.py:1175-1176 `_CHOICES = {'verifier': ...}`: `generic_human` is
    the only human verifier, and the human/automatic split is read from it."""
    assert _verification(verifier='generic_human').verifier == 'generic_human'
    for bad in ('human', 'Generic_Human', 'code ', '', None):
        with pytest.raises(ValueError, match='verifier must be one of'):
            _verification(verifier=bad)


@pytest.mark.parametrize('state', list(states.states('verification')),
                         ids=list(states.states('verification')))
def test_a_verification_lives_in_the_verification_machine(state):
    """entities.py:1174 `_STATE = ('state', 'verification')`."""
    assert _verification(state=state).state == state


@pytest.mark.parametrize('state', ['OPEN', 'ENDED_OK', 'IN_REVIEW', 'CLAIMED', 'READY',
                                   'UNVERIFIED'],
                         ids=['session', 'execution', 'review', 'automation_run', 'task',
                              'account'])
def test_a_verification_refuses_a_state_of_another_machine(state):
    """entities.py:104-105: a row that claims a state its own machine has never
    had cannot be moved by any edge, so it must not be written at all."""
    with pytest.raises(ValueError, match='is not a verification state'):
        _verification(state=state)


def test_a_verification_reference_and_its_initial_state_are_checked():
    """entities.py:1177 `_REFS = {'plan_id': 'plan'}` + the default of
    entities.py:102-103: PENDING is the state a verifier is asked to leave."""
    with pytest.raises(ValueError, match='is not a plan id'):
        _verification(plan_id=_i('mission'))
    assert _verification(state=None).state == states.initial('verification') == 'PENDING'


# ── Review (entities.py:1245-1275): what the reviewer found ──────────────────

@pytest.mark.parametrize('listing', list(E.REVIEW_LISTS), ids=list(E.REVIEW_LISTS))
def test_every_review_list_is_a_list_of_strings(listing):
    """entities.py:1273-1275: the five lists are rendered straight to the user;
    one non-string in them is an exception in the UI, not a review."""
    assert getattr(_review(**{listing: ['one', 'two']}), listing) == ('one', 'two')
    for bad in ([1], [{'text': 'x'}], [None], (True,), ['ok', 2]):
        with pytest.raises(ValueError, match='is a list of strings'):
            _review(**{listing: bad})


@pytest.mark.parametrize('verdict', ['accept', 'changes_requested', 'reject'],
                         ids=['accept', 'changes', 'reject'])
def test_a_review_verdict_is_one_of_the_three(verdict):
    """entities.py:1249 `_CHOICES = {'verdict': ...}`."""
    assert _review(verdict=verdict).verdict == verdict


@pytest.mark.parametrize('verdict', ['ACCEPT', 'accepted', 'maybe', '', 'changes'],
                         ids=['upper', 'accepted', 'maybe', 'empty', 'short'])
def test_a_review_verdict_the_domain_has_no_edge_for_is_refused(verdict):
    """entities.py:1249: `verdict_accept`/`verdict_changes`/`verdict_reject` are
    the only review triggers the machine has (state-machines §11)."""
    with pytest.raises(ValueError, match='verdict must be one of'):
        _review(verdict=verdict)


def test_a_review_names_a_reviewer_and_real_references():
    """entities.py:1248 `_TEXT` + entities.py:1250-1251 `_REFS`."""
    for bad in ('', '  ', None, 7):
        with pytest.raises(ValueError, match='reviewer must be a non-empty string'):
            _review(reviewer=bad)
    for field, kind in (('mission_id', 'mission'), ('plan_id', 'plan'),
                        ('route_decision_id', 'route_decision'), ('principal_id', 'principal')):
        assert getattr(_review(**{field: _i(kind)}), field) is not None
        with pytest.raises(ValueError, match='is not a'):
            _review(**{field: _i('checkpoint')})


@pytest.mark.parametrize('state', list(states.states('review')),
                         ids=list(states.states('review')))
def test_a_review_lives_in_the_review_machine(state):
    """entities.py:1247 `_STATE = ('state', 'review')`."""
    assert _review(state=state).state == state


def test_a_review_starts_pending_and_refuses_another_machines_state():
    """entities.py:102-105 for `review`: PENDING is the initial state, and a
    state of no other machine is never a review state."""
    assert _review(state=None).state == states.initial('review') == 'PENDING'
    for state in ('RUNNING', 'PASSED', 'EXECUTING', 'OPEN'):
        with pytest.raises(ValueError, match='is not a review state'):
            _review(state=state)


# ── Feedback, Artifact, ArtifactRecord, ContextPackage (1279-1372) ──────────

@pytest.mark.parametrize('signal', list(E.Feedback._CHOICES['signal']),
                         ids=['positive', 'negative', 'correction'])
def test_feedback_is_one_of_the_three_signals(signal):
    """entities.py:1283 `_CHOICES = {'signal': ...}`: promotion to a LESSON or a
    PREFERENCE reads the signal, so an unknown word must not be stored."""
    assert _feedback(signal=signal).signal == signal


@pytest.mark.parametrize('signal', [' Positive', 'POSITIVE', 'mixed', '', None],
                         ids=['space', 'upper', 'mixed', 'empty', 'none'])
def test_feedback_that_is_not_a_signal_is_refused(signal):
    """entities.py:1283 `_CHOICES`: the signal is what decides whether a lesson is
    written, so an unlisted word must not be stored."""
    with pytest.raises(ValueError, match='signal must be one of'):
        _feedback(signal=signal)


def test_feedback_references_are_checked_and_a_none_is_allowed():
    """entities.py:1284 `_REFS`: an optional reference may be absent, never wrong."""
    assert _feedback(principal_id=None).principal_id is None
    with pytest.raises(ValueError, match='is not a principal id'):
        _feedback(principal_id=_i('device'))
    with pytest.raises(ValueError, match='is not a knowledge_item id'):
        _feedback(promoted_knowledge_id=_i('mission'))
    with pytest.raises(ValueError, match='is not a project id'):
        _feedback(project_id=_i('mission'))


@pytest.mark.parametrize('sha', ['A' * 64, 'a' * 63, 'a' * 65, 'g' * 64, 'ab' * 31 + 'z',
                                 'sha256:' + 'a' * 57, '', ' '],
                         ids=['upper', 'short', 'long', 'non-hex', 'non-hex-tail', 'prefixed',
                              'empty', 'space'])
def test_an_artifact_id_is_its_own_lowercase_sha256(sha):
    """entities.py:1305-1306: the Artifact is content-addressed, so an id that
    is not the lowercase digest of its bytes is a different object lying about
    being the same one (the uppercase form is the real-world trap)."""
    with pytest.raises(ValueError):
        _artifact(id=sha)


def test_an_artifact_size_is_a_byte_count_and_its_media_type_a_word():
    """entities.py:1299 `_NONNEG = ('size',)` + entities.py:1298 `_TEXT`."""
    assert _artifact(size=0).size == 0
    for bad in (-1, True, None, 1.5):
        with pytest.raises(ValueError, match='size must be an integer >= 0'):
            _artifact(size=bad)
    for bad in ('', '  ', None):
        with pytest.raises(ValueError, match='media_type must be a non-empty string'):
            _artifact(media_type=bad)


@pytest.mark.parametrize('kind', list(E.ARTIFACT_KINDS), ids=list(E.ARTIFACT_KINDS))
def test_an_artifact_record_says_what_kind_of_thing_it_is(kind):
    """entities.py:1321 `_CHOICES = {'kind': ARTIFACT_KINDS}`."""
    assert _artifact_record(kind=kind).kind == kind


@pytest.mark.parametrize('kind', ['PATCH', 'transcript', 'log', '', None],
                         ids=['upper', 'not-a-kind', 'log', 'empty', 'none'])
def test_an_artifact_record_of_an_unknown_kind_is_refused(kind):
    """entities.py:1321: `checkpoint`/`transcript_excerpt`/… are the eight kinds
    ADR-0034 §1 lists; anything else is not something Core may cite."""
    with pytest.raises(ValueError, match='kind must be one of'):
        _artifact_record(kind=kind)


@pytest.mark.parametrize('sha', ['A' * 64, 'a' * 63, 'nope', 'g' * 64],
                         ids=['upper', 'short', 'text', 'non-hex'])
def test_an_artifact_record_names_a_real_artifact(sha):
    """entities.py:1332-1333: the record's `artifact_id` must resolve to bytes."""
    with pytest.raises(ValueError, match='artifact_id names an artifact'):
        _artifact_record(artifact_id=sha)


def test_an_artifact_record_digest_that_is_not_a_string_is_refused_as_a_value_error():
    with pytest.raises(ValueError):
        _artifact_record(artifact_id=7)


def test_an_artifact_record_is_produced_by_one_execution():
    """entities.py:1334-1337: provenance. A record produced by a task, or by a
    string that is not an execution id, claims a producer that cannot run."""
    assert _artifact_record().produced_by.kind == 'execution'
    for bad in (Ref('task', _i('task')), Ref('user_device', _i('principal')),
                Ref('execution', 'exe_bad'), Ref('execution', 'a' * 26),
                Ref('Execution', _i('execution'))):
        with pytest.raises(ValueError, match='produced by an execution'):
            _artifact_record(produced_by=bad)


@pytest.mark.parametrize('kind', list(E.CONTEXT_SUBJECTS), ids=list(E.CONTEXT_SUBJECTS))
def test_a_package_is_assembled_for_what_it_names(kind):
    """entities.py:1351 `_CHOICES` + entities.py:1371-1372: the subject id must
    be an id of the subject kind."""
    assert _package(subject_kind=kind, subject_id=_i(kind)).subject_id.startswith(
        ids.PREFIXES[kind])


@pytest.mark.parametrize('kind,other', [('mission', 'project'), ('project', 'mission'),
                                        ('message', 'mission'), ('mission', 'message')],
                         ids=['mission-project', 'project-mission', 'message-mission',
                              'mission-message'])
def test_a_package_never_describes_an_object_of_another_kind(kind, other):
    """entities.py:1371-1372: without it a package of one mission answers a
    question about another."""
    with pytest.raises(ValueError, match='subject_id is not a'):
        _package(subject_kind=kind, subject_id=_i(other))


@pytest.mark.parametrize('kind', ['harness', 'task', 'idea', '', None],
                         ids=['harness', 'task', 'idea', 'empty', 'none'])
def test_a_package_assembled_for_no_declared_subject_is_refused(kind):
    """entities.py:1351: only mission, project and message can be assembled for."""
    with pytest.raises(ValueError, match='subject_kind must be one of'):
        _package(subject_kind=kind)


def test_a_package_cursor_and_its_workspace_are_checked():
    """entities.py:1352 `_NONNEG = ('as_of_seq',)` and the shared `workspace_id`
    reference of entities.py:118-127."""
    assert _package(as_of_seq=0).as_of_seq == 0
    with pytest.raises(ValueError, match='must be an integer >= 0'):
        _package(as_of_seq=-1)
    with pytest.raises(ValueError, match='is not a workspace id'):
        _package(workspace_id=_i('project'))
    assert _package(workspace_id=ids.GLOBAL_WORKSPACE).workspace_id == ids.GLOBAL_WORKSPACE


# ── resources (entities.py:1388-1510): terms, harnesses, accounts, policies ──

@pytest.mark.parametrize('answer', list(E.TERMS), ids=['unknown', 'permitted', 'refused'])
def test_the_provider_terms_answer_is_the_one_the_user_gave(answer):
    """entities.py:1393 `_CHOICES = {'headless': TERMS, 'rotation': TERMS}`."""
    assert _terms(headless=answer, rotation=answer).headless == answer


def test_the_terms_default_is_the_blocking_unknown():
    """entities.py:1396-1397: `unknown` is the default and blocks exactly as
    `refused` does; defaulting to `permitted` would open headless calls the
    user never answered for."""
    t = _terms()
    assert (t.headless, t.rotation) == ('unknown', 'unknown')


@pytest.mark.parametrize('answer', ['yes', 'PERMITTED', 'permitted ', 'no', True, '', None],
                         ids=['yes', 'upper', 'space', 'no', 'bool', 'empty', 'none'])
def test_a_vague_terms_answer_is_not_an_answer(answer):
    """entities.py:1393: only three words count as an answer, and anything else
    must not be stored as one."""
    with pytest.raises(ValueError, match='headless must be one of'):
        _terms(headless=answer)
    with pytest.raises(ValueError, match='rotation must be one of'):
        _terms(rotation=answer)


@pytest.mark.parametrize('hid', ['claude_code', 'generic_cli:aider', 'a', 'x:y-1.z_2'],
                         ids=['plain', 'namespaced', 'one-char', 'punct'])
def test_a_harness_id_grammar_accepts(hid):
    """entities.py:1400-1401 + entities.py:1415-1416 (`_HARNESS_ID` at 1403)."""
    assert _terms(id=hid).id == hid
    assert _harness(id=hid).id == hid


@pytest.mark.parametrize('hid', ['Claude Code', 'Claude', 'claude code', '9x', '-x', '_',
                                 'claude_code:', ':aider', 'claude/aider', 'x:a b', '.aider'],
                         ids=['upper-space', 'upper', 'space', 'digit-first', 'dash-first',
                              'underscore-only', 'empty-ns', 'no-name', 'slash',
                              'space-in-ns', 'dot-first'])
def test_a_harness_id_that_is_not_an_id_is_refused(hid):
    """entities.py:1400-1401, entities.py:1415-1416 and entities.py:1444-1445: a harness id is a filename and a
    key; the two entities that name one must refuse everything else (an
    uppercase name would collide with another harness on Windows)."""
    with pytest.raises(ValueError, match='ProviderTerms.id is a harness id'):
        _terms(id=hid)
    with pytest.raises(ValueError, match='harness id'):
        _harness(id=hid)
    with pytest.raises(ValueError, match='Account.harness_id is a harness id'):
        _account(harness_id=hid)


@pytest.mark.parametrize('blank', ['', None, 7], ids=['empty', 'none', 'int'])
def test_a_harness_id_that_is_not_even_a_name_is_refused(blank):
    """entities.py:109-113 before entities.py:1400-1401: a blank harness id has no
    grammar to check, and `Account.harness_id`/`Model.id` are `_TEXT`/non-empty
    for the same reason."""
    with pytest.raises(ValueError, match='non-empty string'):
        _harness(id=blank)
    with pytest.raises(ValueError, match='non-empty string'):
        _terms(id=blank)
    with pytest.raises(ValueError, match='non-empty string'):
        _account(harness_id=blank)
    with pytest.raises(ValueError, match='non-empty string'):
        _model(id=blank)


@pytest.mark.parametrize('enforcement', ['hook', 'sandbox', 'none'],
                         ids=['hook', 'sandbox', 'none'])
def test_a_harness_says_how_it_enforces(enforcement):
    """entities.py:1409 `_CHOICES = {'enforcement': ...}`."""
    assert _harness(enforcement=enforcement).enforcement == enforcement


def test_a_harness_defaults_to_no_enforcement_and_to_the_sets_first_state():
    """entities.py:1408-1416: `none` and AVAILABLE are the fail-closed defaults;
    `harness` is a STATE_SETS machine (states.py:375), not an edge list."""
    h = _harness()
    assert (h.enforcement, h.state) == ('none', states.initial('harness')) == ('none', 'AVAILABLE')
    for bad in ('HOOK', 'hooks', '', None):
        with pytest.raises(ValueError, match='enforcement must be one of'):
            _harness(enforcement=bad)
    for bad in ('OPEN', 'AVAILABLE ', 'active', 'available'):
        with pytest.raises(ValueError, match='is not a harness state'):
            _harness(state=bad)


@pytest.mark.parametrize('health', list(states.states('account_health')),
                         ids=list(states.states('account_health')))
def test_an_account_reports_the_health_of_its_machine(health):
    """entities.py:1427 `_STATE = ('health', 'account_health')` — the health
    column is the state, and `health=None` is UNVERIFIED."""
    assert _account(health=health).health == health
    assert _account(health=None).health == states.initial('account_health') == 'UNVERIFIED'


@pytest.mark.parametrize('health', ['ONLINE', 'RUNNING', 'AVAILABLE ', 'active', 'OPEN '],
                         ids=['node', 'execution', 'space', 'lower', 'open-space'])
def test_an_account_refuses_a_health_the_machine_has_no_state_for(health):
    """entities.py:104-105 for account_health: an unlisted health would be read by
    the router as neither available nor blocked."""
    with pytest.raises(ValueError, match='is not a account_health state'):
        _account(health=health)


@pytest.mark.parametrize('auth_kind', list(E.AUTH_KINDS), ids=list(E.AUTH_KINDS))
def test_an_account_says_how_it_authenticates(auth_kind):
    """entities.py:1429 `_CHOICES = {'auth_kind': AUTH_KINDS}`."""
    assert _account(auth_kind=auth_kind).auth_kind == auth_kind


def test_an_account_names_a_node_of_the_right_kind_and_nothing_vague():
    """entities.py:1430 `_REFS = {'node_id': 'execution_node'}` + `_TEXT` of
    entities.py:1428: the label and harness id are never blank."""
    assert _account(node_id=_i('execution_node')).node_id is not None
    assert _account(node_id=None).node_id is None                  # None is the local node
    with pytest.raises(ValueError, match='is not a execution_node id'):
        _account(node_id=_i('account'))
    for field in ('label', 'harness_id'):
        for bad in ('', '   ', None, 7):
            with pytest.raises(ValueError, match='must be a non-empty string'):
                _account(**{field: bad})


@pytest.mark.parametrize('tier', ['large', 'mid', 'small'], ids=['large', 'mid', 'small'])
def test_a_model_is_in_one_of_the_three_tiers(tier):
    """entities.py:1451 `_CHOICES = {'tier': ...}`: bands, never a precise rank."""
    assert _model(tier=tier).tier == tier


def test_a_model_window_is_at_least_one_token():
    """entities.py:1452 `_MIN1 = ('context_window',)`: a model that holds no
    token routes nothing; 0 or negative is not a window."""
    assert _model(context_window=1).context_window == 1
    for bad in (0, -1, True, None, 1.5, '1000'):
        with pytest.raises(ValueError, match='context_window must be an integer >= 1'):
            _model(context_window=bad)
    with pytest.raises(ValueError, match='family must be a non-empty string'):
        _model(family=' ')
    with pytest.raises(ValueError, match='tier must be one of'):
        _model(tier='nano')


def test_an_offer_names_a_real_account_and_a_model_that_is_not_blank():
    """entities.py:1461-1462: `ModelOffer` has no id of its own, so both its
    columns must be there: an empty `model_id` would offer nothing."""
    assert _offer().account_id is not None
    for bad in ('', ' ', None):
        with pytest.raises(ValueError, match='model_id must be a non-empty string'):
            _offer(model_id=bad)
    with pytest.raises(ValueError, match='is not a account id'):
        _offer(account_id='acc_bad')
    assert _offer(available=False).available is False


@pytest.mark.parametrize('pct', [0, 1, 99, 100], ids=['zero', 'one', 'ninety-nine', 'hundred'])
def test_an_allocation_is_a_share_of_the_provider_window(pct):
    """entities.py:1483 + entities.py:1499-1500 (`allocation_pct > 100`): a ceiling on
    the window, so 0..100 and nothing else (resource-router §4)."""
    assert _policy(allocation_pct=pct).allocation_pct == pct


@pytest.mark.parametrize('pct', [101, 200, 1000], ids=['over', 'double', 'thousand'])
def test_an_allocation_above_the_whole_window_is_refused(pct):
    """entities.py:1499-1500: 150% of a window would let an account be used
    beyond what the provider reports, which is what the ceiling is for."""
    with pytest.raises(ValueError, match='is a share of the provider window'):
        _policy(allocation_pct=pct)


@pytest.mark.parametrize('pct', [-1, True, False, None, 1.0, '50'],
                         ids=['negative', 'true', 'false', 'none', 'float', 'string'])
def test_an_allocation_that_is_not_a_percentage_is_refused(pct):
    """entities.py:1483 `_NONNEG` (which excludes bool): `allocation_pct=True`
    would read as a 1% account."""
    with pytest.raises(ValueError, match='allocation_pct must be an integer >= 0'):
        _policy(allocation_pct=pct)


@pytest.mark.parametrize('reserve,brain,alloc,ok', [
    (0, 0, 100, True), (100, 0, 100, True), (60, 40, 100, True), (0, 0, 0, True),
    (60, 41, 100, False), (1, 0, 0, False), (0, 100, 99, False),
], ids=['none', 'all', 'split', 'exact', 'one-over', 'over-zero', 'brain-over'])
def test_the_reserves_never_exceed_what_the_account_may_give(reserve, brain, alloc, ok):
    """entities.py:1501-1502: reserve + brain_reserve over the allocation means
    'nothing would ever route here' — the row must not exist to be read."""
    if ok:
        p = _policy(reserve_pct=reserve, brain_reserve_pct=brain, allocation_pct=alloc)
        assert p.reserve_pct == reserve
    else:
        with pytest.raises(ValueError, match='reserves exceed the allocation'):
            _policy(reserve_pct=reserve, brain_reserve_pct=brain, allocation_pct=alloc)


@pytest.mark.parametrize('budgets', [
    None, {}, {'tokens_per_day': 0}, {'cost_per_day': 0.25}, {'concurrency': 1},
    {'tokens_per_day': 10, 'cost_per_day': 1.0, 'concurrency': 2},
], ids=['none', 'empty', 'zero-tokens', 'fraction-cost', 'one-at-a-time', 'all-three'])
def test_a_budget_is_a_known_key_holding_a_number(budgets):
    """entities.py:1503-1507: the accepted side (resource-router §4)."""
    assert _policy(budgets=budgets).budgets == budgets


@pytest.mark.parametrize('budgets', [
    {'tokens_per_day': -1}, {'tokens_per_day': True}, {'tokens_per_day': False},
    {'tokens_per_day': '10'}, {'tokens_per_day': None}, {'cost_per_day': -0.5},
    {'concurrency': 'two'}, {'tokens_per_week': 10}, {'': 1}, {'Tokens_per_day': 1},
    {'tokens_per_day': 10, 'tokens_per_week': 5},
], ids=['negative', 'true', 'false', 'string', 'none', 'negative-cost', 'word', 'unknown-key',
        'empty-key', 'upper-key', 'one-unknown'])
def test_a_budget_that_is_not_a_governor_is_refused(budgets):
    """entities.py:1503-1507: a key outside BUDGET_KEYS is a governor nobody
    reads; a bool, a string or a negative number is not a limit — the ledger
    governs an account with no readable window, so this is the only ceiling."""
    with pytest.raises(ValueError, match='a budget is one of'):
        _policy(budgets=budgets)


@pytest.mark.parametrize('listing', ['project_allow', 'project_deny'],
                         ids=['allow', 'deny'])
def test_a_project_restriction_names_a_project(listing):
    """entities.py:1508-1510: an allow/deny entry that is not a project id can
    never match, so a typo would silently open (or close) the account."""
    good = _i('project')
    assert getattr(_policy(**{listing: (good,)}), listing) == (good,)
    assert getattr(_policy(**{listing: ()}), listing) == ()
    for bad in ('prj_not_a_ulid', _i('task'), _i('account'), ids.GLOBAL_WORKSPACE, 'project', 7):
        with pytest.raises(ValueError, match='names a project id'):
            _policy(**{listing: (good, bad)})


@pytest.mark.parametrize('field,value', [
    ('fallback', 'allow'), ('fallback', 'deny'), ('consumption', 'normal'),
    ('consumption', 'explicit_only'),
], ids=['allow', 'deny', 'normal', 'explicit-only'])
def test_a_policy_says_what_happens_when_the_account_is_not_chosen(field, value):
    """entities.py:1481 `_CHOICES` + entities.py:1472 CONSUMPTION (ADR-0041 §1)."""
    assert getattr(_policy(**{field: value}), field) == value


def test_a_policy_refuses_words_its_router_does_not_switch_on():
    """entities.py:1481 + entities.py:1484 `_MIN1 = ('priority',)`."""
    for bad in ('ASK', 'askme', '', None):
        with pytest.raises(ValueError, match='fallback must be one of'):
            _policy(fallback=bad)
    for bad in ('Normal', 'last-resort', 'always', ''):
        with pytest.raises(ValueError, match='consumption must be one of'):
            _policy(consumption=bad)
    for bad in (0, -1, True, None, 1.5):
        with pytest.raises(ValueError, match='priority must be an integer >= 1'):
            _policy(priority=bad)


# ── OptIn (entities.py:1523-1555): what an execution may load again ─────────

@pytest.mark.parametrize('owner,name', [('account', 'user'), ('project', 'project'),
                                        ('project', 'local')],
                         ids=['account-user', 'project-project', 'project-local'])
def test_a_source_opt_in_names_a_source_its_owner_holds(owner, name):
    """entities.py:1553-1555 with SOURCE_OWNERS (ADR-0049 D6): the account home
    is the account's, a project's committed `.claude/` and local settings are
    the project's."""
    o = _opt_in(kind='source', name=name, **_owner_for(owner))
    assert (o.owner, o.name) == (owner, name)


@pytest.mark.parametrize('owner,name', [('account', 'project'), ('account', 'local'),
                                        ('project', 'user'), ('project', 'User'),
                                        ('account', 'USER')],
                         ids=['account-project', 'account-local', 'project-user',
                              'project-upper', 'account-upper'])
def test_a_source_opt_in_never_lends_a_project_its_owners_settings(owner, name):
    """entities.py:1553-1555: a project opted into the `user` source would let
    its executions load the account home's settings — the one thing D6 stops."""
    with pytest.raises(ValueError, match='holds the'):
        _opt_in(kind='source', name=name, **_owner_for(owner))


@pytest.mark.parametrize('kw', [
    {'kind': 'plugin', 'name': 'caveman@caveman'},                       # no owner at all
    {'kind': 'plugin', 'name': 'caveman@caveman', 'account_id': _i('account'),
     'project_id': _i('project')},                                        # both
], ids=['no-owner', 'two-owners'])
def test_an_opt_in_has_exactly_one_owner(kw):
    """entities.py:1546-1547: with none it binds nothing, with both the answer
    to "whose settings source" is undefined — and `owner` would silently answer
    'account'."""
    with pytest.raises(ValueError, match='exactly one owner'):
        E.OptIn(id=_i('opt_in'), **kw)


@pytest.mark.parametrize('name', [
    'caveman@caveman', 'a', 'a.b', 'a-b_1', 'X9@market.place', 'mcp_server', 'a' * 128,
], ids=['plugin', 'single', 'dots', 'dash-underscore', 'at-marketplace', 'mcp', 'max-length'])
def test_an_opt_in_names_a_thing(name):
    """entities.py:1550-1552 (`_OPT_IN_NAME`, 1..128 of `[A-Za-z0-9_.@-]`)."""
    assert _opt_in(name=name).name == name


@pytest.mark.parametrize('name', [
    'user/../etc', '../etc', 'a..b', '.claude/settings.json', 'src/plugin', './x', 'a b',
    'a/b', 'a\\b', '-lead', '@lead', 'a$b', 'a*' + 'b', 'a' * 129, 'a\u00a0b',
], ids=['traversal', 'relative', 'double-dot', 'dotfile', 'path', 'dot-slash', 'space', 'slash',
        'backslash', 'dash-first', 'at-first', 'dollar', 'star', 'too-long', 'nbsp'])
def test_an_opt_in_name_is_never_a_path(name):
    """entities.py:1550-1552: the name becomes a settings lookup and, for a
    plugin, an install spec; a path (or `..`, which the character class does
    allow and the separate `'..' in name` test catches) must not be opt-in-able."""
    with pytest.raises(ValueError, match='never a path'):
        _opt_in(name=name)


@pytest.mark.parametrize('kind', list(E.OPT_IN_KINDS), ids=list(E.OPT_IN_KINDS))
def test_an_opt_in_is_a_source_a_plugin_an_mcp_a_context_or_a_verify(kind):
    """entities.py:1531 `_CHOICES = {'kind': OPT_IN_KINDS}`."""
    kw = _owner_for('project' if kind in ('context', 'verify') else 'account')
    name = {'source': 'user', 'context': 'injection', 'verify': 'baseline'}.get(
        kind, 'caveman@caveman')
    assert _opt_in(kind=kind, name=name, **kw).kind == kind


@pytest.mark.parametrize('owner,name', [('account', 'injection'), ('project', 'plugin'),
                                        ('project', 'caveman@caveman')])
def test_a_context_opt_in_is_only_a_projects_and_only_a_named_one(owner, name):
    with pytest.raises(ValueError, match='context opt-in'):
        _opt_in(kind='context', name=name, **_owner_for(owner))


def test_an_opt_in_change_is_a_version_of_the_same_row_not_a_new_row():
    """entities.py:1548-1549: `opted_in` is a real boolean — an opt-out is the
    row's next version, and a truthy string must not read as either."""
    assert _opt_in(opted_in=False).opted_in is False
    assert _opt_in().opted_in is True
    for bad in (1, 0, 'true', '', None, 'False'):
        with pytest.raises(ValueError, match='OptIn.opted_in is a boolean'):
            _opt_in(opted_in=bad)


@pytest.mark.parametrize('name', ['', '   ', None, 7], ids=['empty', 'spaces', 'none', 'int'])
def test_an_opt_in_names_something(name):
    """entities.py:1530 `_TEXT = ('name',)` before the path grammar: a blank
    name opts in to nothing at all."""
    with pytest.raises(ValueError, match='non-empty string'):
        _opt_in(name=name)


def test_an_opt_in_reference_is_an_account_id():
    """entities.py:1532 `_REFS = {'account_id': 'account'}` — `project_id` is
    not id-validated here, so this guard is the one that must hold."""
    with pytest.raises(ValueError, match='is not a account id'):
        _opt_in(account_id=_i('project'))


# ── usage (entities.py:1558-1625): what the provider said, what we spent ─────

@pytest.mark.parametrize('window', list(E.USAGE_WINDOWS), ids=list(E.USAGE_WINDOWS))
def test_a_snapshot_reports_one_of_the_known_windows(window):
    """entities.py:1564-1565 `_CHOICES = {'window': USAGE_WINDOWS, ...}` (1384)."""
    assert _snapshot(window=window).window == window


@pytest.mark.parametrize('window', ['5H', 'daily', 'hourly', '', '1d', None],
                         ids=['upper', 'daily', 'hourly', 'empty', 'one-day', 'none'])
def test_a_window_the_provider_does_not_report_is_refused(window):
    """entities.py:1564-1565: the window is the key of the utilisation row; a fourth
    word would be a row no reader can place."""
    with pytest.raises(ValueError, match='window must be one of'):
        _snapshot(window=window)


@pytest.mark.parametrize('source', ['usage_api', 'rate_limit_headers', 'rollout_file',
                                    'scripted'],
                         ids=['api', 'headers', 'rollout', 'scripted'])
def test_a_snapshot_says_where_the_number_came_from(source):
    """entities.py:1564-1565: provenance of the reading; `scripted` is the fake
    feed's and is unrestricted (1561-1562)."""
    assert _snapshot(source=source).source == source


def test_a_snapshot_says_when_it_was_read_and_of_which_account():
    """entities.py:1566-1567 `_REFS`/`_TEXT`: `observed_at` without a time is a
    reading nobody can age, and `account_id` must be an account."""
    assert _snapshot(resets_at=None).resets_at is None
    with pytest.raises(ValueError, match='is not a account id'):
        _snapshot(account_id='acc_x')
    for bad in ('', '   ', None):
        with pytest.raises(ValueError, match='observed_at must be a non-empty string'):
            _snapshot(observed_at=bad)


@pytest.mark.parametrize('pct', [0, 0.0, 0.5, 100, 42.5, 1e9],
                         ids=['zero', 'zero-float', 'half', 'full', 'percent', 'huge'])
def test_a_utilisation_is_a_number_that_is_not_below_zero(pct):
    """entities.py:1578-1579: the accepted side — an over-100 reading is what
    the provider reports when it is throttling, so it is not clamped here."""
    assert _snapshot(utilisation_pct=pct).utilisation_pct == pct


@pytest.mark.parametrize('pct', [-0.1, -1, math.nan, -math.nan, '42', None],
                         ids=['negative-float', 'negative-int', 'nan', 'minus-nan', 'string',
                              'none'])
def test_a_utilisation_that_is_not_a_reading_is_refused(pct):
    """entities.py:1578-1579: `nan >= 0` is False and a string would compare
    badly downstream; None means no reading, which is a missing row instead."""
    with pytest.raises(ValueError, match='utilisation_pct must be a number'):
        _snapshot(utilisation_pct=pct)


def test_a_utilisation_that_is_a_bool_is_refused():
    """entities.py:1578: `isinstance(True, int)` is True, so `True` passes as a
    100%-used window and `False` as an empty one -- the `_NONNEG` walk
    (entities.py:131) and the ledger figures (entities.py:1620) both exclude
    bool; this guard does not."""
    with pytest.raises(ValueError, match='utilisation_pct must be a number'):
        _snapshot(utilisation_pct=True)


@pytest.mark.parametrize('figure', list(E.UsageLedger._FIGURES),
                         ids=list(E.UsageLedger._FIGURES))
def test_a_usage_figure_is_a_count_or_absolutely_nothing(figure):
    """entities.py:1598 + entities.py:1619-1621 (`_FIGURES`): None is "not reported", 0 is zero
    (ADR-0048 D-25.3) — the two must not collapse."""
    assert getattr(_ledger(**{figure: 0}), figure) == 0
    assert getattr(_ledger(**{figure: None}), figure) is None
    for bad in (-1, True, False, 1.5, '5'):
        with pytest.raises(ValueError, match='must be an integer >= 0 or None'):
            _ledger(**{figure: bad})


@pytest.mark.parametrize('cost', [0, 0.0, 1, 12.5, 0.000001],
                         ids=['zero-int', 'zero-float', 'one', 'dollars', 'fraction'])
def test_a_cost_of_record_is_an_amount(cost):
    """entities.py:1622-1625: the accepted side."""
    assert _ledger(cost_usd=cost).cost_usd == cost


@pytest.mark.parametrize('cost', [-0.000001, -1, math.inf, -math.inf, math.nan, '1.5', True, 1.0j],
                         ids=['negative-fraction', 'negative', 'inf', 'minus-inf', 'nan',
                              'string', 'bool', 'complex'])
def test_a_cost_that_is_not_a_finite_amount_is_refused(cost):
    """entities.py:1622-1625: `math.isfinite` is what stops an `inf` cost (the
    classic float leak) from being billed, and the bool test stops `True`."""
    with pytest.raises(ValueError, match='finite amount'):
        _ledger(cost_usd=cost)


def test_a_usage_row_always_names_the_route_decision_that_chosen_where_it_ran():
    """entities.py:1615-1617: the row is attributable or it is not a ledger
    row; this guard is the only thing that makes cost per decision possible."""
    assert _ledger().route_decision_id is not None
    with pytest.raises(ValueError, match='belongs to the route decision'):
        _ledger(route_decision_id=None)
    # an Archeus own call has no execution (ADR-0022), so the rest may be absent
    assert _ledger(execution_id=None, account_id=None).execution_id is None


def test_a_usage_row_reference_and_basis_are_the_declared_ones():
    """entities.py:1595-1597 `_REFS`/`_CHOICES`."""
    for field in ('execution_id', 'account_id', 'route_decision_id'):
        with pytest.raises(ValueError, match='is not a'):
            _ledger(**{field: _i('checkpoint')})
        with pytest.raises(ValueError, match='is not a'):
            _ledger(**{field: 'chk_0000000000000000000000000'})
    assert _ledger(basis='reported_total').basis == 'reported_total'
    assert _ledger(basis='none').basis == 'none'
    for bad in ('REPORTED_TOTAL', 'estimated', '', 'exact'):
        with pytest.raises(ValueError, match='basis must be one of'):
            _ledger(basis=bad)


@pytest.mark.parametrize('result', list(E.ROUTE_RESULTS), ids=list(E.ROUTE_RESULTS))
def test_a_routing_decision_says_how_it_ended(result):
    """entities.py:1629 ROUTE_RESULTS + entities.py:1642-1643 `_CHOICES`: `blocked`
    and `ask` are the two ways a decision decides nothing."""
    assert _route(result=result).result == result


@pytest.mark.parametrize('field,value', [
    ('result', 'SELECTED'), ('result', 'no_choice'), ('result', ''),
    ('purpose', 'brain'), ('purpose', 'BRAIN'), ('purpose', 'chat'),
    ('decided_by', 'router'), ('decided_by', 'pre_router'), ('decided_by', 'human'),
], ids=['result-upper', 'result-novel', 'result-empty', 'purpose-brain', 'purpose-upper',
        'purpose-chat', 'by-router', 'by-pre', 'by-human'])
def test_a_routing_decision_uses_the_words_the_router_uses(field, value):
    """entities.py:1642-1643: an unlisted word here is a decision the audit
    reader cannot classify."""
    if value in ('brain', 'router', 'pre_router'):
        assert getattr(_route(**{field: value}), field) == value
    else:
        with pytest.raises(ValueError, match='must be one of'):
            _route(**{field: value})


def test_a_routing_decision_reference_names_the_row_it_was_made_for():
    """entities.py:1644-1646 `_REFS`: a task id in `context_package_id` (or a
    malformed id in any of them) would point an audit replay at nothing."""
    for field, kind in (('context_package_id', 'context_package'), ('mission_id', 'mission'),
                        ('task_id', 'task'), ('account_id', 'account'),
                        ('policy_decision_id', 'policy_decision')):
        assert getattr(_route(**{field: _i(kind)}), field) is not None
        with pytest.raises(ValueError, match='is not a'):
            _route(**{field: _i('checkpoint')})
        with pytest.raises(ValueError, match='is not a'):
            _route(**{field: kind + '_0000000000000000000000000'})


def test_a_node_is_one_of_the_two_kinds_and_lives_in_the_node_machine():
    """entities.py:1688-1690: `local`/`remote`, and ONLINE/GRACE/OFFLINE/RETIRED
    with ONLINE initial (states.py STATE_SETS)."""
    assert _node(kind='remote').kind == 'remote'
    assert _node(state=None).state == states.initial('execution_node') == 'ONLINE'
    for state in list(states.states('execution_node')):
        assert _node(state=state).state == state
    with pytest.raises(ValueError, match='kind must be one of'):
        _node(kind='LOCAL')
    with pytest.raises(ValueError, match='is not a execution_node state'):
        _node(state='AVAILABLE')
    with pytest.raises(ValueError, match='name must be a non-empty string'):
        _node(name=' ')


# ── control (entities.py:1700-1906): rules, decisions, approvals, automations ─

def test_a_deny_rule_is_locked_and_says_so():
    """entities.py:1737-1740: `locked` is derived from the decision, and a DENY
    that is not locked would let a later rule relax a prohibition — the core
    fail-closed invariant of the gate."""
    assert _rule(decision='DENY').locked is True
    assert _rule(decision='ALLOW').locked is False          # derived, entities.py:1737-1738
    with pytest.raises(ValueError, match='DENY is always locked'):
        _rule(decision='DENY', locked=False)
    with pytest.raises(ValueError, match='DENY is always locked'):
        _rule(decision='DENY', locked=0)


@pytest.mark.parametrize('level,ref,ok', [
    ('GLOBAL', None, True), ('USER', 'user', True), ('WORKSPACE', 'workspace', True),
    ('PROJECT', 'project', True), ('MISSION', 'mission', True), ('TASK', 'task', True),
    ('GLOBAL', 'user', False), ('USER', None, False), ('TASK', None, False),
], ids=['global-none', 'user', 'workspace', 'project', 'mission', 'task',
        'global-with-ref', 'user-none', 'task-none'])
def test_only_a_global_rule_has_no_scope(level, ref, ok):
    """entities.py:1741-1742: the `!=` of `(scope_level == 'GLOBAL')` against
    `(scope_ref is None)`. A non-GLOBAL rule without a scope_ref would apply
    everywhere while claiming to be a user's own; a GLOBAL one with a scope_ref
    would be Core's rule aimed at one person."""
    kw = {'scope_ref': _i(ref) if ref else None, 'source': 'builtin'}
    if ok:
        assert _rule(scope_level=level, **kw).scope_level == level
    else:
        with pytest.raises(ValueError, match='has no scope_ref'):
            _rule(scope_level=level, **kw)


@pytest.mark.parametrize('source', ['builtin', 'profile'], ids=['builtin', 'profile'])
def test_a_global_rule_is_cores_own(source):
    """entities.py:1743-1744: GLOBAL is Core's own (built-in and profile rules,
    in code); a user-supplied GLOBAL rule is privilege escalation."""
    assert _global_rule(source=source).source == source
    with pytest.raises(ValueError, match="GLOBAL rules are Core's own"):
        _global_rule(source='user')


@pytest.mark.parametrize('expires', [None, '2026-11-02T10:00:00Z', ''],
                         ids=['never', 'timestamp', 'empty-string'])
def test_a_temporary_rule_carries_a_timestamp_or_nothing(expires):
    """entities.py:1745-1747 (`expires_at is None or isinstance(str)`)."""
    assert _rule(expires_at=expires).expires_at == expires


@pytest.mark.parametrize('expires', [1730000000, 1.0, True, [], {}],
                         ids=['epoch-int', 'float', 'bool', 'list', 'dict'])
def test_a_temporary_rule_that_expires_at_a_number_is_refused(expires):
    """entities.py:1745-1747: a rule whose expiry is not a timestamp would be
    compared as a string downstream and never expire (or always expire)."""
    with pytest.raises(ValueError, match='expires_at is a timestamp or null'):
        _rule(expires_at=expires)


@pytest.mark.parametrize('match', [
    None, {}, {'environment': 'dev'}, {'path_glob': 'src/**'},
    {'environment': 'prod', 'command_glob': 'pytest *', 'min_cost_band': 'low'},
    {'branch_glob': 'main', 'host_glob': 'this-pc'},
], ids=['none', 'empty', 'environment', 'path-glob', 'three', 'branch-host'])
def test_a_rule_applies_on_the_keys_the_matcher_reads(match):
    """entities.py:1748-1750 (MATCH_KEYS, §6.1): the accepted side."""
    assert _rule(match=match).match == match


@pytest.mark.parametrize('match', [
    {'paths': ['src']}, {'environment': 'dev', 'paths': ['src']}, {'PATH_GLOB': 'x'},
    {'': 'x'}, 'environment', ['environment'],
], ids=['boundary-key', 'extra-boundary-key', 'upper-key', 'empty-key', 'string', 'list'])
def test_a_rule_that_applies_on_an_unknown_key_is_refused(match):
    """entities.py:1748-1750: a key the matcher does not know is a condition
    silently never (or always) satisfied — a rule broader than it reads."""
    with pytest.raises(ValueError, match='match keys are'):
        _rule(match=match)


BOUNDARY = {'paths': ['src/**'], 'branches': ['main'], 'hosts': ['this-pc'],
            'environments': ['dev'], 'max_cost_band': 'high'}


def test_a_bounded_allowance_carries_a_real_boundary():
    """entities.py:1751-1765: ALLOW_WITHIN_BOUNDARY is the one decision with a
    boundary, and its shape is what `rules.check_boundary` reads (§6.2)."""
    r = _rule(decision='ALLOW_WITHIN_BOUNDARY', boundary=BOUNDARY)
    assert r.boundary == BOUNDARY
    assert _rule(decision='ALLOW_WITHIN_BOUNDARY',
                 boundary={'max_cost_band': 'low'}).boundary == {'max_cost_band': 'low'}


@pytest.mark.parametrize('decision,boundary,message', [
    ('ALLOW', {'paths': ['src/**']}, 'only ALLOW_WITHIN_BOUNDARY has a boundary'),
    ('DENY', {'paths': ['src/**']}, 'only ALLOW_WITHIN_BOUNDARY has a boundary'),
    ('ASK', {'max_cost_band': 'low'}, 'only ALLOW_WITHIN_BOUNDARY has a boundary'),
    ('ALLOW_WITHIN_BOUNDARY', None, 'needs a boundary'),
    ('ALLOW_WITHIN_BOUNDARY', {}, 'boundary keys are'),
], ids=['allow-paths', 'deny-paths', 'ask-band', 'none', 'empty'])
def test_a_boundary_and_a_decision_that_disagree_are_refused(decision, boundary, message):
    """entities.py:1751-1756: a boundary on an ALLOW would be ignored (the
    action allowed past it); no boundary on a bounded ALLOW means no limit."""
    with pytest.raises(ValueError, match=message):
        _rule(decision=decision, boundary=boundary)


@pytest.mark.parametrize('boundary', [
    {'max_cost_band': 'HIGH'}, {'max_cost_band': 'highest'}, {'max_cost_band': True},
    {'max_cost_band': 1}, {'paths': ['src', '']}, {'paths': [7]}, {'paths': ['']},
    {'paths': ({'a': 1},)}, {'branches': None}, {'paths': 'src/**'}, {'paths': {'a': 1}},
], ids=['upper-band', 'unknown-band', 'bool-band', 'int-band', 'empty-entry', 'int-entry',
        'empty-string', 'dict-entry', 'none', 'string-not-list', 'dict-not-list'])
def test_a_boundary_that_check_boundary_cannot_read_is_refused(boundary):
    """entities.py:1758-1763: `max_cost_band` is one of COST_BANDS and every
    other key a list of non-empty strings. A bare string for `paths` is the
    trap: `any(inside(v, a) for a in 'src/**')` would compare the action
    against single characters."""
    with pytest.raises(ValueError, match='is one of|is a list of non-empty strings'):
        _rule(decision='ALLOW_WITHIN_BOUNDARY', boundary=boundary)


def test_an_empty_boundary_list_limits_nothing_rather_than_failing_open():
    """entities.py:1758-1763 accepts `{'paths': ()}` (a list of zero non-empty
    strings is still one), and rules.check_boundary then finds no allowed
    pattern, so every value lands in `outside`: fail-closed, as it must be."""
    assert _rule(decision='ALLOW_WITHIN_BOUNDARY',
                 boundary={'paths': ()}).boundary == {'paths': ()}


@pytest.mark.parametrize('field,value', [
    ('outside', 'ASK'), ('outside', 'DENY'), ('source', 'profile'),
    ('scope_level', 'MISSION'), ('action_class', 'mission.start'), ('decision', 'ASK'),
], ids=['ask', 'deny', 'profile', 'mission', 'mission-start', 'ask-decision'])
def test_a_rule_reads_the_control_vocabulary(field, value):
    """entities.py:1712-1713 `_CHOICES` (SCOPE_LEVELS, RULE_CLASSES, DECISIONS,
    RULE_SOURCES) + entities.py:1713 `outside`."""
    assert getattr(_rule(**{field: value}), field) == value


@pytest.mark.parametrize('field,value', [
    ('outside', 'ask'), ('outside', 'ALLOW'), ('outside', ''),
    ('source', 'admin'), ('source', 'Builtin'), ('source', ''),
    ('scope_level', 'user'), ('scope_level', 'ACTION'), ('scope_level', 'global'),
    ('action_class', 'teleport'), ('action_class', 'EXEC'), ('action_class', ''),
    ('decision', 'MAYBE'), ('decision', 'allow'), ('decision', ''),
], ids=['outside-ask', 'outside-allow', 'outside-empty', 'source-admin', 'source-upper',
        'source-empty', 'level-user', 'level-action', 'level-global', 'class-teleport',
        'class-upper', 'class-empty', 'decision-maybe', 'decision-lower', 'decision-empty'])
def test_a_rule_with_a_word_the_gate_does_not_switch_on_is_refused(field, value):
    """entities.py:1712-1713: an unlisted decision or level is a rule the gate
    neither applies nor ignores — it must not reach the store."""
    with pytest.raises(ValueError, match='must be one of'):
        _rule(**{field: value})


def test_a_rule_revision_starts_at_one_and_supersedes_a_rule():
    """entities.py:1715 `_MIN1` + entities.py:1714 `_REFS`: a revision 0 could
    not be the "next" version of anything."""
    assert _rule(revision=1).revision == 1
    for bad in (0, -1, True, None, 1.5):
        with pytest.raises(ValueError, match='revision must be an integer >= 1'):
            _rule(revision=bad)
    with pytest.raises(ValueError, match='is not a policy_rule id'):
        _rule(supersedes_rule_id=_i('policy_decision'))
    assert _rule(retired_at=None).retired_at is None


@pytest.mark.parametrize('stage', list(E.POLICY_STAGES), ids=list(E.POLICY_STAGES))
def test_a_decision_records_the_stage_it_was_made_at(stage):
    """entities.py:1774 `_CHOICES = {'decision': DECISIONS, 'stage':
    POLICY_STAGES}` (plan/dispatch/action/start)."""
    assert _decision(stage=stage, decision='ASK').stage == stage


def test_a_decision_reference_names_the_evaluation_it_explains():
    """entities.py:1775-1776 `_REFS` + entities.py:1775: the row is the audit
    trail, so its subject rows must be resolvable and its words listed."""
    for field, kind in (('mission_id', 'mission'), ('plan_id', 'plan'), ('task_id', 'task'),
                        ('execution_id', 'execution'), ('approval_id', 'approval')):
        assert getattr(_decision(**{field: _i(kind)}), field) is not None
        with pytest.raises(ValueError, match='is not a'):
            _decision(**{field: _i('policy_rule')})
    with pytest.raises(ValueError, match='decision must be one of'):
        _decision(decision='allow')
    with pytest.raises(ValueError, match='stage must be one of'):
        _decision(stage='execute')


@pytest.mark.parametrize('sha', ['A' * 64, 'a' * 63, 'a' * 65, 'nope', 'g' * 64, '', ' ', None],
                         ids=['upper', 'short', 'long', 'text', 'non-hex', 'empty', 'space',
                              'none'])
def test_an_approval_binds_the_exact_action_by_its_digest(sha):
    """entities.py:1846-1847: the approval covers one canonical action and
    nothing else; an `action_hash` that is not the lowercase digest (or is
    missing, which a `None` column would be) would approve a different action
    than the one shown."""
    with pytest.raises(ValueError, match='action_hash is the hex sha256'):
        _approval(action_hash=sha)


@pytest.mark.parametrize('kind', list(E.Approval._CHOICES['kind']),
                         ids=['plan', 'task', 'action', 'route', 'start'])
def test_an_approval_is_of_one_of_the_five_things_a_device_decides(kind):
    """entities.py:1848-1851: `kind` defaults to the subject's kind, which is
    how an approval of a plan and an approval of an action stay distinct."""
    a = _approval(subject=Ref(kind, _i('plan' if kind == 'plan' else 'task')), kind=None)
    assert a.kind == kind


def test_an_approval_whose_subject_is_not_decidable_is_refused():
    """entities.py:1848-1851: a `mission` subject has no approval kind, so the
    derived `kind` must be checked, not trusted."""
    with pytest.raises(ValueError, match='Approval.kind is one of'):
        _approval(subject=Ref('mission', _i('mission')))
    # an explicit `kind` is caught by the declared `_CHOICES` (which runs before
    # `_check`, entities.py:114-117); only the derived one reaches the guard of
    # entities.py:1850-1851 -- both refuse, in two different words
    for bad in ('checkpoint', 'PLAN', 'plan ', '', 0):
        with pytest.raises(ValueError, match='Approval.kind'):
            _approval(kind=bad)


@pytest.mark.parametrize('decision', [None, 'approve', 'reject', 'request_changes'],
                         ids=['undecided', 'approve', 'reject', 'changes'])
def test_an_approval_is_decided_once_and_in_one_of_three_words(decision):
    """entities.py:1816-1817 `_CHOICES['decision']`: None is still pending."""
    assert _approval(decision=decision).decision == decision
    for bad in ('APPROVE', 'approved', 'maybe', ''):
        with pytest.raises(ValueError, match='decision must be one of'):
            _approval(decision=bad)


def test_an_approval_reference_names_the_rows_it_was_raised_for():
    """entities.py:1812-1815 `_REFS`: `decided_by` is a principal, not whoever
    wrote the row, and `decided_policy_decision_id` is the decision that asked."""
    for field, kind in (('requested_by', 'principal'), ('mission_id', 'mission'),
                        ('plan_id', 'plan'), ('task_id', 'task'), ('execution_id', 'execution'),
                        ('policy_decision_id', 'policy_decision'), ('decided_by', 'principal'),
                        ('decided_policy_decision_id', 'policy_decision')):
        assert getattr(_approval(**{field: _i(kind)}), field) is not None
        with pytest.raises(ValueError, match='is not a'):
            _approval(**{field: _i('review')})


@pytest.mark.parametrize('state', list(states.states('approval')),
                         ids=list(states.states('approval')))
def test_an_approval_lives_in_the_approval_machine(state):
    """entities.py:1811 `_STATE = ('state', 'approval')`; PENDING is where an
    approval that nobody has answered yet sits."""
    assert _approval(state=state).state == state
    assert _approval(state=None).state == states.initial('approval') == 'PENDING'


@pytest.mark.parametrize('state', ['OPEN', 'RUNNING', 'ENABLED', 'AWAITING_HUMAN', 'ONLINE'],
                         ids=['session', 'execution', 'automation', 'verification', 'node'])
def test_an_approval_refuses_a_state_of_another_machine(state):
    """entities.py:104-105: SUPERSEDED and CONSUMED exist for a reason; a state no
    edge of the `approval` machine leads to must not be stored."""
    with pytest.raises(ValueError, match='is not a approval state'):
        _approval(state=state)


# ── automation (entities.py:1855-1906): the trigger and its one decision ─────

def test_an_automation_is_armed_at_the_outbox_head_it_saw():
    """entities.py:1859-1860 `_MIN1 = ('max_depth','rate_limit')` +
    entities.py:1861 `_NONNEG = ('armed_seq',)`: a rate_limit of 0 would never fire, and a
    negative armed_seq would fire for an event from before it was enabled."""
    assert _automation(armed_seq=0).armed_seq == 0
    assert _automation(max_depth=1, rate_limit=1).rate_limit == 1
    for field in ('max_depth', 'rate_limit'):
        for bad in (0, -1, True, None, 1.5, '3'):
            with pytest.raises(ValueError, match='%s must be an integer >= 1' % field):
                _automation(**{field: bad})
    with pytest.raises(ValueError, match='armed_seq must be an integer >= 0'):
        _automation(armed_seq=-1)


def test_an_automation_lives_in_one_workspace_and_names_a_principal():
    """entities.py:1861 `_REFS = {'principal_id': 'principal'}` and the shared
    workspace reference (entities.py:118-127): an automation fires as its own
    principal, so that id must resolve."""
    with pytest.raises(ValueError, match='is not a principal id'):
        _automation(principal_id=_i('account'))
    with pytest.raises(ValueError, match='is not a workspace id'):
        _automation(workspace_id=_i('project'))
    with pytest.raises(ValueError, match='name must be a non-empty string'):
        _automation(name='  ')


@pytest.mark.parametrize('state', list(states.states('automation')),
                         ids=list(states.states('automation')))
def test_an_automation_lives_in_the_automation_machine(state):
    """entities.py:1857 `_STATE = ('state', 'automation')`; DRAFT initial."""
    assert _automation(state=state).state == state
    assert _automation(state=None).state == states.initial('automation') == 'DRAFT'


def test_an_automation_refuses_a_state_of_another_machine():
    """entities.py:104-105 + entities.py:1857: `SUSPENDED` is the automation's own
    word for it; `SKIPPED` belongs to its runs, not to it."""
    for state in ('SKIPPED', 'OPEN', 'RUNNING', 'SUSPENDED '):
        with pytest.raises(ValueError, match='is not a automation state'):
            _automation(state=state)


@pytest.mark.parametrize('state', list(states.states('automation_run')),
                         ids=list(states.states('automation_run')))
def test_a_run_ends_in_one_of_the_seven_states(state):
    """entities.py:1886 `_STATE = ('state', 'automation_run')`, CLAIMED initial
    (p14-design-gate §7)."""
    assert _run(state=state).state == state
    assert _run(state=None).state == states.initial('automation_run') == 'CLAIMED'


def test_a_run_is_one_decision_about_one_event():
    """entities.py:1887-1888 `_REFS`/`_NONNEG`: the sequence is the event it
    answers (never negative, never a bool), `depth` is the triggering event's
    + 1, and `automation_id` must name a real automation."""
    assert _run(depth=1).depth == 1
    assert _run(depth=0).depth == 0
    for field in ('triggering_event_seq', 'depth'):
        for bad in (-1, True, None, '7', 1.5):
            with pytest.raises(ValueError, match='%s must be an integer >= 0' % field):
                _run(**{field: bad})
    with pytest.raises(ValueError, match='is not a automation id'):
        _run(automation_id=_i('mission'))
    with pytest.raises(ValueError, match='is not a mission id'):
        _run(mission_id=_i('automation'))


def test_a_run_refuses_a_state_of_another_machine():
    """entities.py:104-105 + entities.py:1886: `ENABLED` is the automation's, not
    the run's; a run in a state of its own machine has no edge out of it."""
    for state in ('ENABLED', 'OPEN', 'RUNNING', 'DRAFT'):
        with pytest.raises(ValueError, match='is not a automation_run state'):
            _run(state=state)


# ── what is frozen at insert, and what is in the registry ───────────────────

@pytest.mark.parametrize('cls,expect', [
    (E.Verification, {'subject', 'verifier', 'plan_id', 'criterion', 'execution_id', 'revision',
                      'base_revision', 'workspace', 'performed_by', 'verifier_version'}),
    (E.Account, {'harness_id', 'auth_kind', 'node_id', 'home_ref', 'home_key'}),
    (E.ResourcePolicy, {'account_id'}),
    (E.OptIn, {'account_id', 'project_id', 'kind', 'name'}),
    (E.PolicyRule, {'scope_level', 'action_class', 'decision', 'scope_ref', 'locked', 'match',
                    'boundary', 'outside', 'expires_at', 'source', 'note', 'revision',
                    'supersedes_rule_id'}),
    (E.RouteDecision, {'subject', 'selected', 'explanation', 'purpose', 'decided_by',
                       'workspace_id', 'project_id', 'source', 'requirements', 'candidates',
                       'account_ref', 'model', 'input_snapshot', 'context_package_id',
                       'mission_id', 'task_id', 'harness_id', 'account_id', 'effort', 'result',
                       'fallback_from', 'policy_decision_id', 'unblock_at', 'task_family',
                       'capability_snapshot'}),
    (E.Approval, {'kind', 'subject', 'action_hash', 'requested_by', 'step_up', 'mission_id',
                  'plan_id', 'plan_version', 'plan_digest', 'task_id', 'execution_id',
                  'presented', 'items', 'expires_at', 'policy_decision_id', 'policy_version'}),
    (E.AutomationRun, {'automation_id', 'triggering_event_seq', 'triggering_event_id', 'depth',
                       'cause_chain', 'rationale'}),
    (E.UsageSnapshot, None), (E.UsageLedger, None), (E.PolicyDecision, None),
], ids=['verification', 'account', 'resource_policy', 'opt_in', 'policy_rule', 'route_decision',
        'approval', 'automation_run', 'usage_snapshot', 'usage_ledger', 'policy_decision'])
def test_the_fields_frozen_at_insert_are_the_declared_ones(cls, expect):
    """The `_FROZEN` tuples (entities.py:1179, 1431, 1485, 1533, 1716, 1647, 1818, 1890) are
    what the store refuses a later UPDATE of; `FROZEN_ALL` (entities.py:31, `frozen_fields` 75) is "every
    column". Dropping a name here turns an immutable history row into an editable one."""
    names = {f.name for f in dataclasses.fields(cls)}
    if expect is None:
        assert cls._FROZEN is E.FROZEN_ALL
        assert cls.frozen_fields() == names          # nothing exempt: no state column either
    else:
        assert cls.frozen_fields() == expect
        assert expect <= names


def test_every_entity_of_this_section_is_still_in_the_registry():
    """entities.py:1908-1910 (`ENTITIES`): the module-wide walks (`test_domain.py`'s
    id/`_TEXT`/`_REFS` sweeps) iterate this tuple; a class that drops out of it stops
    being tested by anything else."""
    for cls in (E.Execution, E.Session, E.Checkpoint, E.Verification, E.Review, E.Feedback,
                E.Artifact, E.ArtifactRecord, E.ContextPackage, E.ProviderTerms, E.Harness,
                E.Account, E.Model, E.ModelOffer, E.ResourcePolicy, E.OptIn, E.UsageSnapshot,
                E.UsageLedger, E.RouteDecision, E.ExecutionNode, E.PolicyRule, E.PolicyDecision,
                E.Approval, E.Automation, E.AutomationRun):
        assert cls in E.ENTITIES

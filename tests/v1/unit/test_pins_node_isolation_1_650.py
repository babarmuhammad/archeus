"""T-836 hand-mutant pins on archeus/node/isolation.py lines 1-650.

Every test names one condition of the module's first 650 lines (a comparison, an early
return, a membership check, a `not`, an `and`/`or` or a default value) and fails when
that condition is inverted, removed or loosened. The mutation that proves each pin is
quoted in the card's report, applied only to a scratch copy of the source.

Nothing here reaches the OS: the boundary is a fake that only answers, every path is a
`tmp_path` directory, and no principal is ever created, deleted or launched.
"""

import hashlib
import json
import os

import pytest

from archeus.core.domain import ids
from archeus.infra.paths import isolation_state
from archeus.node import isolation as iso

EID = ids.new_id('execution')
VID = ids.new_id('verification')
JOB = {'type': 'Job', 'name': '', 'inheritable': False}
_MISSING = object()


def _own_norm(path):
    """The test's own normalization (the source has its own): which paths the fake
    boundary answers "granted" for must not move with a mutation of `isolation._norm`."""
    return os.path.normcase(os.path.abspath(path)) if path else ''


class Api:
    """The boundary's answers about one principal: every one a knob, none a decision."""

    def __init__(self):
        self.available_ok = True
        self.established = True
        self.broad = None
        self.granted = ()
        self.caps = ()
        self.derive_fail = ''

    def available(self):
        return self.available_ok

    def derive_sid(self, execution_id):
        if self.derive_fail:
            raise iso.IsolationUnavailable(self.derive_fail, 'synthetic')
        name = iso.profile_name(execution_id)
        return 'S-1-15-3-9-' + hashlib.sha1(name.encode('utf-8')).hexdigest()[:12]

    def grant_established(self, path, sid, access):
        return bool(self.established)

    def broad_write_grant(self, path, sid):
        return self.broad

    def granted_to(self, path, sid):
        return _own_norm(path) in {_own_norm(p) for p in self.granted}

    def capability_grants(self):
        return tuple(self.caps)


def _dir(root, name):
    path = os.path.join(str(root), name)
    os.makedirs(path, exist_ok=True)
    return path


def _file(root, name):
    path = os.path.join(str(root), name)
    with open(path, 'wb') as f:
        f.write(b'{"argv": []}')
    return path


def _exec_request(root, execution_id=EID):
    d = {n: _dir(root, n) for n in ('workspace', 'runtime', 'hook', 'mailbox', 'response',
                                    'sentinel', 'state', 'core_state', 'broker')}
    return iso.IsolationRequest(
        execution_id=execution_id, workspace=d['workspace'],
        grants=(iso.Grant(d['workspace'], 'rw', 'workspace'),
                iso.Grant(d['runtime'], 'rx', 'runtime'),
                iso.Grant(d['hook'], 'rx', 'hook'),
                iso.Grant(d['mailbox'], 'rw', 'request'),
                iso.Grant(d['response'], 'rx', 'response'),
                iso.Grant(d['sentinel'], 'rx', 'sentinel'),
                iso.Grant(d['state'], 'rw', 'state')),
        mailbox=d['mailbox'], response=d['response'], sentinel=d['sentinel'],
        spawn_config=_file(d['response'], 'spawn.json'), state_dir=d['state'],
        core_state=d['core_state'], broker=d['broker'])


def _verify_request(root, attempt=0, vid=VID, tag=''):
    key = iso.Principal('verify', vid, attempt).key
    checkout = _dir(root, 'checkout' + tag)
    return iso.IsolationRequest(
        execution_id=key, workspace=checkout,
        grants=(iso.Grant(checkout, 'rw', 'checkout'),
                iso.Grant(_dir(root, 'scratch' + tag), 'rw', 'scratch'),
                iso.Grant(_dir(root, 'toolchain' + tag), 'rx', 'toolchain')),
        core_state=_dir(root, 'core_state' + tag))


def _replace(request, **over):
    return iso.IsolationRequest(**{**request.__dict__, **over})


def _conds(api, request, identity=_MISSING, job=JOB):
    if identity is _MISSING:
        identity = {'profile': iso.profile_name(request.execution_id),
                    'sid': api.derive_sid(request.execution_id), 'created': True,
                    'package_dir': 'materialized'}
    return iso.check_invariant(api, request, identity, job)


def _unmet(api, request, **over):
    return iso.unmet_conditions(_conds(api, request, **over))


def _record_dict(api, execution_id, **over):
    d = {'execution_id': execution_id, 'profile': iso.profile_name(execution_id),
         'sid': api.derive_sid(execution_id), 'state': 'established', 'reason': '',
         'failure': '', 'conditions': {}, 'applied': [], 'pid': None, 'create_time': None,
         'capabilities': [], 'owned': True, 'preexisting': False, 'attempts': 0,
         'at': 0.0, 'updated': 0.0}
    d['planned'] = [{'path': iso.profile_name(execution_id), 'access': 'rx',
                     'row': 'runtime'}]
    d.update(over)
    return d


def _plant(execution_id, record):
    path = isolation_state(execution_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as f:
        f.write(json.dumps(record).encode('utf-8'))
    return path


# ── the profile name (lines 56-68) ────────────────────────────────────────────

@pytest.mark.parametrize('raw,want', [
    ('exe_a/b', 'exe_a-b'),
    ('exe_a\\b', 'exe_a-b'),
    ('exe_a:b', 'exe_a-b'),
    ('exe_a|b `c`', 'exe_a-b--c-'),
    ('exe_a../b', 'exe_a..-b'),
    ('exe_ab\u00e9', 'exe_ab\u00e9'),
], ids=['slash', 'backslash', 'colon', 'pipe-and-backquote', 'dotdot-slash', 'accented'])
def test_a_name_that_is_not_a_name_component_never_reaches_a_profile_name(raw, want):
    name = iso.profile_name(raw)
    assert name == iso.PROFILE_PREFIX + want
    assert not any(sep in name for sep in ('/', '\\', ':', '|', '`', ' '))


def test_a_profile_name_never_reaches_the_os_bound_of_127_characters():
    name = iso.profile_name('exe_' + 'z' * 300)
    assert name.startswith(iso.PROFILE_PREFIX) and len(name) == 127


@pytest.mark.parametrize('name', [
    None, '', 'archeus.spike.life0', 'xarcheus.exec.a', 'xarcheus.verify.a',
    'microsoft.windowscalculator_8wekyb3d8bbwe', 'exec.1', 0,
], ids=['none', 'empty', 'a-spike-profile', 'exec-suffix', 'verify-suffix', 'other-app',
        'bare-exec', 'zero'])
def test_only_a_profile_derivable_from_a_principal_is_stale(name):
    assert iso.is_stale_profile(name) is False


def test_both_derivable_prefixes_are_stale_whatever_their_case():
    exec_name = iso.profile_name(EID)
    verify_name = iso.profile_name(iso.Principal('verify', VID, 1).key)
    assert iso.is_stale_profile(exec_name) is True
    assert iso.is_stale_profile(verify_name) is True
    assert iso.is_stale_profile(exec_name.upper()) is True
    assert iso.is_stale_profile(verify_name.upper()) is True


# ── condition 1: the identity the OS answered (lines 243-252) ─────────────────

@pytest.mark.parametrize('shape', ['none', 'empty', 'no-sid-key', 'blank-sid', 'no-created',
                                   'created-false'])
def test_an_identity_nobody_created_or_named_is_never_condition_1(tmp_path, shape):
    api, req = Api(), _exec_request(tmp_path)
    sid = api.derive_sid(req.execution_id)
    identity = {'none': None, 'empty': {}, 'no-sid-key': {'created': True},
                'blank-sid': {'created': True, 'sid': ''}, 'no-created': {'sid': sid},
                'created-false': {'created': False, 'sid': sid}}[shape]
    conds = _conds(api, req, identity=identity)
    assert conds['identity'][0] is False
    assert iso.unmet_conditions(conds) == ('identity',)


def test_an_identity_that_was_created_and_derives_holds_condition_1(tmp_path):
    api, req = Api(), _exec_request(tmp_path)
    assert _unmet(api, req) == ()


# ── condition 2: the inventory rows (lines 216-229, 262-286) ──────────────────

@pytest.mark.parametrize('field,row', [('mailbox', 'request'), ('response', 'response'),
                                        ('sentinel', 'sentinel')],
                         ids=['class1', 'class2', 'class3'])
def test_a_mailbox_class_without_its_own_directory_fails_condition_5(tmp_path, field, row):
    api, req = Api(), _exec_request(tmp_path)
    assert _unmet(api, req) == ()
    broken = _replace(req, **{field: ''},
                      grants=tuple(g for g in req.grants if g.row != row))
    conds = _conds(api, broken)
    assert conds['mailbox'][0] is False and conds['grants'][0] is False


def test_a_workspace_that_is_not_a_directory_fails_condition_2(tmp_path):
    api, req = Api(), _exec_request(tmp_path)
    missing = _replace(req, workspace=os.path.join(str(tmp_path), 'never-created'))
    for broken in (_replace(req, workspace=''), missing):
        conds = _conds(api, broken)
        assert conds['grants'][0] is False
        assert 'no Core-established workspace' in conds['grants'][1]


def test_a_workspace_that_is_a_file_is_no_workspace(tmp_path):
    api, req = Api(), _exec_request(tmp_path)
    conds = _conds(api, _replace(req, workspace=_file(tmp_path, 'workspace-file')))
    assert conds['grants'][0] is False
    assert 'no Core-established workspace' in conds['grants'][1]


@pytest.mark.parametrize('form', ['dot', 'separator'])
def test_the_same_toolchain_granted_twice_is_a_duplicate_however_it_is_spelled(tmp_path, form):
    api, req = Api(), _verify_request(tmp_path)
    toolchain = req.grant_for('toolchain').path
    spelling = os.path.join(toolchain, '.') if form == 'dot' else toolchain + os.sep
    conds = _conds(api, _replace(req, grants=req.grants + (
        iso.Grant(spelling, 'rx', 'toolchain'),)))
    assert conds['grants'][0] is False
    assert 'toolchain:duplicate' in conds['grants'][1]


def test_a_second_read_only_toolchain_that_is_a_different_directory_holds(tmp_path):
    api, req = Api(), _verify_request(tmp_path)
    conds = _conds(api, _replace(req, grants=req.grants + (
        iso.Grant(_dir(tmp_path, 'toolchain-2'), 'rx', 'toolchain'),)))
    assert iso.unmet_conditions(conds) == ()


def test_the_checkout_may_be_the_workspace_under_another_spelling(tmp_path):
    api, req = Api(), _verify_request(tmp_path)
    assert _unmet(api, _replace(req, workspace=os.path.join(req.workspace, '.'))) == ()


def test_the_checkout_may_not_be_the_workspace_one_component_deeper(tmp_path):
    api, req = Api(), _verify_request(tmp_path)
    deeper = _dir(req.workspace, 'sub')
    conds = _conds(api, _replace(req, workspace=deeper))
    assert conds['grants'][0] is False and 'checkout' in conds['grants'][1]


# ── condition 3: broad and Core-owned grants (lines 292-322) ──────────────────

@pytest.mark.parametrize('dot_side', ['core', 'grant'], ids=['core-spelling', 'grant-spelling'])
def test_core_state_granted_under_another_spelling_is_still_core_state(tmp_path, dot_side):
    api, req = Api(), _exec_request(tmp_path)
    workspace = os.path.join(req.workspace, '.')
    grants = tuple(iso.Grant(workspace, g.access, g.row) if g.row == 'workspace' else g
                   for g in req.grants)
    broken = _replace(req, grants=grants,
                      core_state=req.workspace if dot_side == 'core' else workspace,
                      core_only=() if dot_side == 'core' else (req.workspace,))
    conds = _conds(api, broken)
    assert conds['no_broad_grants'][0] is False
    assert 'Core-owned state is granted to the execution' in conds['no_broad_grants'][1]


def test_core_state_the_boundary_reads_as_granted_fails_condition_3(tmp_path):
    api, req = Api(), _exec_request(tmp_path)
    api.granted = (req.core_state,)
    conds = _conds(api, req)
    assert conds['no_broad_grants'][0] is False
    assert 'Core-owned state is granted to the execution' in conds['no_broad_grants'][1]


def test_a_verifier_whose_core_state_is_granted_fails_its_own_condition_5(tmp_path):
    api, req = Api(), _verify_request(tmp_path)
    api.granted = (req.core_state,)
    conds = _conds(api, req)
    assert conds['mailbox'][0] is False
    assert 'Core-owned state is unnamed or granted' in conds['mailbox'][1]
    assert conds['no_broad_grants'][0] is False


# ── condition 4: the Job facts (lines 303-309) ────────────────────────────────

@pytest.mark.parametrize('job', [
    None, {}, {'type': 'Process', 'name': '', 'inheritable': False},
    {'type': 'job', 'name': '', 'inheritable': False},
    {'name': '', 'inheritable': False},
    {'type': 'Job', 'name': None, 'inheritable': False},
    {'type': 'Job', 'name': 0, 'inheritable': False},
    {'type': 'Job', 'name': '', 'inheritable': True},
    {'type': 'Job', 'name': '', 'inheritable': 'yes'},
], ids=['none', 'empty', 'a-process', 'lowercase-type', 'no-type', 'unreadable-name',
        'numeric-name', 'inheritable', 'inheritable-truthy'])
def test_only_an_unnamed_uninheritable_job_object_is_condition_4(tmp_path, job):
    api, req = Api(), _exec_request(tmp_path)
    assert _unmet(api, req, job=job) == ('job',)


# ── condition 5: the mailbox classes (lines 314-334) ──────────────────────────

def test_a_class_directory_that_is_a_file_and_not_a_directory_fails_closed(tmp_path):
    api, req = Api(), _exec_request(tmp_path)
    a_file = _file(tmp_path, 'not-a-class')
    broken = _replace(req, mailbox=a_file, grants=tuple(
        iso.Grant(a_file, g.access, g.row) if g.row == 'request' else g for g in req.grants))
    assert _conds(api, broken)['mailbox'][0] is False


def test_the_spawn_configuration_must_sit_directly_in_class_2(tmp_path):
    api, req = Api(), _exec_request(tmp_path)
    deeper = _file(_dir(req.response, 'sub'), 'spawn.json')
    assert _unmet(api, _replace(req, spawn_config=deeper)) == ('mailbox',)


def test_a_spawn_configuration_written_with_a_trailing_newline_still_holds(tmp_path):
    api, req = Api(), _exec_request(tmp_path)
    with open(req.spawn_config, 'wb') as f:
        f.write(b'{"argv": []}\n')
    assert _unmet(api, req) == ()


# ── condition 6: the isolated path (lines 336-340) ────────────────────────────

def test_a_request_that_did_not_select_the_isolated_path_fails_condition_6(tmp_path):
    api, req = Api(), _exec_request(tmp_path)
    conds = _conds(api, _replace(req, isolated_path=False))
    assert iso.unmet_conditions(conds) == ('isolated_path',)
    assert conds['isolated_path'][1] == 'the detached path was selected'


def test_an_unavailable_boundary_fails_condition_6_alone(tmp_path):
    api, req = Api(), _exec_request(tmp_path)
    api.available_ok = False
    conds = _conds(api, req)
    assert iso.unmet_conditions(conds) == ('isolated_path',)
    assert conds['isolated_path'][1] == 'the OS boundary is unavailable'


def test_a_falsy_isolated_path_selection_is_not_the_isolated_path(tmp_path):
    api, req = Api(), _exec_request(tmp_path)
    for falsy in (0, '', None, []):
        assert iso.unmet_conditions(_conds(api, _replace(req, isolated_path=falsy))) \
            == ('isolated_path',)


# ── unmet_conditions (lines 381-382) ──────────────────────────────────────────

def test_a_condition_nobody_answered_is_unmet_never_held():
    answered = {name: (True, '') for name in iso.CONDITIONS}
    assert iso.unmet_conditions({}) == iso.CONDITIONS
    assert iso.unmet_conditions(answered) == ()
    assert iso.unmet_conditions({**answered, 'not_a_condition': (False, 'x')}) == ()
    assert iso.unmet_conditions({**answered, 'job': (False, 'why')}) == ('job',)


# ── A4 and the test-harness gate (lines 400-440) ──────────────────────────────

GOOD_A4 = dict(harness_id='real-agent', isolated_launch=True, job_held=True,
               sandbox=False, exception_claimed=False, evidence='from-path')


@pytest.mark.parametrize('field,value,unmet', [
    ('harness_id', '', 'production_dispatch'),
    ('harness_id', 'fake-agent', 'production_dispatch'),
    ('harness_id', 'test-agent', 'production_dispatch'),
    ('isolated_launch', 1, 'pv20_identity'),
    ('isolated_launch', 'yes', 'pv20_identity'),
    ('isolated_launch', None, 'pv20_identity'),
    ('job_held', 1, 'core_held_job'),
    ('job_held', 'True', 'core_held_job'),
    ('sandbox', 1, 'sandbox_inner_layer'),
    ('sandbox', 'inner', 'sandbox_inner_layer'),
    ('sandbox', None, 'sandbox_inner_layer'),
    ('exception_claimed', 0, 'no_harness_exception'),
    ('exception_claimed', None, 'no_harness_exception'),
    ('exception_claimed', 'none', 'no_harness_exception'),
    ('evidence', '', 'evidence_from_path'),
    ('evidence', 0, 'evidence_from_path'),
    ('evidence', [], 'evidence_from_path'),
], ids=['no-id', 'fake-id', 'test-id', 'launch-1', 'launch-yes',
        'launch-none', 'job-1', 'job-string', 'sandbox-1', 'sandbox-word', 'sandbox-none',
        'except-0', 'except-none', 'except-word', 'evidence-empty', 'evidence-0',
        'evidence-empty-list'])
def test_a4_eligibility_takes_facts_and_nothing_merely_truthy_or_falsy(field, value, unmet):
    ok, unmet_names = iso.a4_eligibility(**{**GOOD_A4, field: value})
    assert ok is False
    assert isinstance(unmet_names, tuple) and unmet in unmet_names


def test_a4_eligibility_holds_on_exactly_the_six_facts():
    assert iso.a4_eligibility(**GOOD_A4) == (True, ())


@pytest.mark.parametrize('harness_id,attrs', [
    ('real-agent', {'test_harness': True}),
    ('real-agent', {'test_harness': 1}),
    ('fake-agent', {}),
    ('test-agent', {}),
    ('', {'test_harness': True}),
], ids=['flagged-real', 'flagged-by-1', 'fake-id', 'test-id', 'flagged-without-id'])
def test_a_test_harness_is_recognised_by_its_id_or_by_its_own_flag(harness_id, attrs):
    assert iso.is_test_harness(type('A', (), dict({'id': harness_id}, **attrs))()) is True


@pytest.mark.parametrize('harness_id', ['real-agent', '', None],
                         ids=['real', 'empty', 'missing'])
def test_an_adapter_that_is_not_a_test_harness_is_never_one(harness_id):
    assert iso.is_test_harness(type('A', (), {'id': harness_id})()) is False


def test_a_flagged_test_harness_is_isolated_and_a_real_one_is_not(tmp_path):
    a = iso.Isolation(boundary=Api(), authorize=lambda eid, adapter: True)
    flagged = type('A', (), {'id': 'real-agent', 'test_harness': True})()
    real = type('A', (), {'id': 'real-agent'})()
    assert a.requested(ids.new_id('execution'), flagged) is True
    assert a.requested(ids.new_id('execution'), real) is False


# ── the record as evidence (lines 485-548) ────────────────────────────────────

RECORD_FIELDS = {'execution_id', 'profile', 'sid', 'state', 'reason', 'failure',
                 'conditions', 'planned', 'applied', 'pid', 'create_time',
                 'capabilities', 'owned', 'preexisting', 'attempts', 'at', 'updated',
                 'gen'}


def test_a_record_survives_the_dict_it_is_written_as(tmp_path):
    grant = iso.Grant(_dir(tmp_path, 'planned'), 'rx', 'runtime')
    api = Api()
    rec = iso.IsolationRecord(execution_id=EID, profile=iso.profile_name(EID),
                              sid=api.derive_sid(EID), state='established',
                              conditions={'identity': [True, '']}, planned=(grant,),
                              pid=4242, create_time=1.5, owned=True)
    assert set(rec.as_dict()) == RECORD_FIELDS
    assert _plant(EID, rec.as_dict())
    a = iso.Isolation(boundary=api)
    got = a.record(EID)
    assert got.state == 'established' and got.sid == rec.sid and got.owned is True
    assert got.planned == (grant,) and got.conditions == {'identity': [True, '']}
    assert got.pid == 4242 and got.create_time == 1.5 and a.invalid == {}


@pytest.mark.parametrize('state,want', [
    ('invalid', 'state_unknown'), ('established', 'sid_missing'), ('quarantined', ''),
    ('pending', ''), ('torn_down', ''), ('failed', ''),
], ids=['invalid', 'established', 'quarantined', 'pending', 'torn-down', 'failed'])
def test_only_a_persisted_state_is_a_state_and_a_sidless_one_is_trusted_only_in_some(
        tmp_path, state, want):
    api = Api()
    _plant(EID, _record_dict(api, EID, state=state, sid=''))
    a = iso.Isolation(boundary=api)
    got = a.record(EID)
    assert a.invalid.get(EID, '') == want
    assert got.state == ('invalid' if want else state)


def test_a_sid_that_cannot_be_derived_is_reported_and_never_raises(tmp_path):
    api = Api()
    good = _record_dict(api, EID)
    api.derive_fail = 'sid_derive'
    _plant(EID, good)
    a = iso.Isolation(boundary=api)
    assert a.record(EID).state == 'invalid'
    assert a.invalid[EID] == 'sid_underivable'


# ── the owner-set budgets (lines 84-86, 595-600) ──────────────────────────────

def test_the_confined_verifier_and_job_budgets_stay_at_the_owner_values():
    assert (iso.VERIFY_ACTIVE_PROCESSES, iso.VERIFY_JOB_MEMORY) == (64, 4 << 30)
    assert iso.VERIFY_JOB_CPU_100NS == 6_000_000_000        # 10 minutes in 100 ns units
    assert (iso.CONFINED_OUT_MAX, iso.CONFINED_GROWTH_MAX) == (64 << 20, 2 << 30)
    assert (iso.CONFINED_POLL_S, iso.CONFINED_WALK_MAX) == (1.0, 200000)


# ── the constants nothing may widen (lines 33-49) ─────────────────────────────

def test_no_capability_and_no_production_dispatch_are_the_shipped_values():
    assert iso.CAPABILITIES == ()
    assert iso.NETWORK_CAPABILITY_SIDS == ('S-1-15-3-1', 'S-1-15-3-2')
    assert iso.PRODUCTION_DISPATCH_ENABLED is False
    assert iso.production_dispatch_enabled() is False
    assert iso.A4_ENFORCED is False and iso.a4_enforced() is False
    assert iso.CONDITIONS == ('identity', 'grants', 'no_broad_grants', 'job', 'mailbox',
                              'isolated_path')
    assert iso.VERIFY_GRANTS == (('checkout', 'rw'), ('scratch', 'rw'), ('toolchain', 'rx'))
    assert iso.CLASS_ROWS == (('request', 'rw'), ('response', 'rx'), ('sentinel', 'rx'))

"""Hand-mutant pins for archeus/node/mxc_resources.py.

Each test names one condition in the module and fails when that condition is
inverted, removed or loosened. Synthetic facts only: no Windows API, no network,
no real process; nothing here depends on the platform the suite runs on.
"""

import pytest

from archeus.node import mxc_resources as resources


SID = 'S-1-15-3-1'
SID_TEN = 'S-1-15-3-10'
S1 = 'S-1-15-1-1'
S5 = 'S-1-15-3-2'
S6 = 'S-1-15-4-1'
OWNER = 'S-1-15-2-999999'
OTHER_OWNER = 'S-1-15-2-888888'
BACKEND = 'processcontainer'
TIER = 'base-container'
PAIRS = (('toolchain', 'ro'), ('workspace', 'rw'))
QUIET = (('toolchain', 'ro'), ('workspace', 'ro'))
BAD = 'bad\x01value'


def grants(*pairs):
    return [{'resource': resource, 'access': access} for resource, access in pairs]


def observed(**changes):
    facts = {'pid': 41, 'create_time': 900, 'backend': BACKEND, 'tier': TIER,
             'effective_grants': grants(*PAIRS), 'workload_identity': OWNER,
             'capability_sids': [SID]}
    facts.update(changes)
    return facts


def planned(**changes):
    facts = {'backend': BACKEND, 'tier': TIER, 'grants': grants(*PAIRS)}
    facts.update(changes)
    return facts


def build(**changes):
    args = {'execution_id': 'exec-1', 'pid': 41, 'create_time': 900,
            'planned': planned(), 'applied': grants(*PAIRS), 'observed': observed()}
    args.update(changes)
    return resources.build_record(**args)


def differences(**changes):
    return resources.observed_matches_requested(build(**changes))


@pytest.mark.parametrize('call, refused', [
    pytest.param(lambda: build(planned=planned(backend=BAD)),
                 'invalid requested backend', id='req-backend'),
    pytest.param(lambda: build(planned=planned(tier=BAD)),
                 'invalid requested tier', id='req-tier'),
    pytest.param(lambda: build(applied=grants((BAD, 'ro'), ('toolchain', 'ro'))),
                 'invalid grant resource', id='grant-res'),
    pytest.param(lambda: build(observed=observed(backend=BAD)),
                 'invalid observed backend', id='obs-backend'),
    pytest.param(lambda: build(observed=observed(tier=BAD)),
                 'invalid observed tier', id='obs-tier'),
    pytest.param(lambda: build(observed=observed(workload_identity=BAD)),
                 'invalid workload identity', id='identity'),
])
def test_every_quoted_identity_field_is_text_validated(call, refused):
    with pytest.raises(resources.ResourceRecordError, match=refused):
        call()


def test_planned_policy_must_be_a_mapping_of_names():
    with pytest.raises(resources.ResourceRecordError,
                       match='planned policy must hold exactly'):
        build(planned=list(resources.PLANNED_FIELDS))


@pytest.mark.parametrize('value', ['', 'rw', b'', b'rw'],
                         ids=['empty-str', 'str', 'empty-bytes', 'bytes'])
def test_applied_grants_reject_text_values(value):
    with pytest.raises(resources.ResourceRecordError,
                       match='applied grants must be a list of grants'):
        build(applied=value)


@pytest.mark.parametrize('value', [b'', b'S-1-15-3-1'], ids=['empty', 'bytes'])
def test_capability_sids_reject_bytes(value):
    with pytest.raises(resources.ResourceRecordError,
                       match='capability SID list must be a list of SIDs'):
        build(observed=observed(capability_sids=value))


def test_capability_sids_are_deduped_and_sorted():
    seen = build(observed=observed(capability_sids=[S6, SID, S1, S5, SID, SID_TEN,
                                                    OTHER_OWNER]))
    assert seen.observed.capability_sids == (S1, OTHER_OWNER, SID, SID_TEN, S5, S6)


def test_grant_tuples_are_stored_sorted():
    unsorted = grants(('workspace', 'rw'), ('toolchain', 'ro'))
    record = build(planned=planned(grants=unsorted), applied=unsorted)
    assert record.requested_grants == PAIRS
    assert record.applied_grants == PAIRS


def test_deny_is_a_known_grant_access_class():
    deny = grants(('toolchain', 'deny'), ('workspace', 'rw'))
    record = build(applied=deny, observed=observed(effective_grants=deny))
    assert record.applied_grants == (('toolchain', 'deny'), ('workspace', 'rw'))
    assert record.observed.effective_grants == (('toolchain', 'deny'),
                                                ('workspace', 'rw'))


@pytest.mark.parametrize('left, right', [
    pytest.param('planned', 'applied', id='planned-applied'),
    pytest.param('planned', 'observed', id='planned-observed'),
    pytest.param('applied', 'observed', id='applied-observed'),
])
def test_two_layers_never_share_one_object(left, right):
    shared = observed() if right == 'observed' else planned()
    with pytest.raises(resources.ResourceRecordError, match='facts are separate'):
        build(**{left: shared, right: shared})


def test_observed_defaults_to_nothing_when_omitted():
    record = resources.build_record(execution_id='exec-1', pid=41, create_time=900,
                                    planned=planned(), applied=grants(*PAIRS))
    assert record.observed is None


def test_observation_defaults_to_no_capability_sids():
    observation = resources.Observation(pid=41, create_time=900, backend=BACKEND,
                                        tier=TIER, effective_grants=(),
                                        workload_identity=OWNER)
    assert observation.capability_sids == ()


def test_writable_gate_reads_requested_grants_not_the_observed_ones():
    quiet = grants(*QUIET)
    assert differences(observed=observed(effective_grants=quiet)) == [
        'grant workspace observed ro, requested rw']


def test_writable_gate_reads_requested_grants_not_the_applied_ones():
    quiet = grants(*QUIET)
    assert differences(planned=planned(grants=quiet), applied=grants(*PAIRS),
                       observed=observed(effective_grants=quiet)) == [
        'grant workspace applied rw, requested ro',
        'capability SID %s observed, no writable grant requested' % SID]


@pytest.mark.parametrize('value', ['exec-1', b'exec-1'], ids=['str', 'bytes'])
def test_separation_problems_rejects_text_containers(value):
    with pytest.raises(resources.ResourceRecordError,
                       match='a list of resource records is required'):
        resources.separation_problems(value)

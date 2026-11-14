"""The PSEC resource record is checked with synthetic facts only: no Windows API, no
network, no real process, and every host fact is passed in as an argument.
"""

import pytest

from archeus.node import mxc_resources as resources


SID = 'S-1-15-3-1'
OWNER = 'S-1-15-2-999999'
OTHER_OWNER = 'S-1-15-2-888888'
BACKEND = 'processcontainer'
TIER = 'base-container'
PAIRS = (('toolchain', 'ro'), ('workspace', 'rw'))


def grants(*pairs):
    return [{'resource': resource, 'access': access} for resource, access in pairs]


def observed(drop=(), **changes):
    facts = {'pid': 41, 'create_time': 900, 'backend': BACKEND, 'tier': TIER,
             'effective_grants': grants(*PAIRS), 'workload_identity': OWNER,
             'capability_sids': [SID]}
    facts.update(changes)
    for key in drop:
        del facts[key]
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


def build_pair(**changes):
    stamps = {key: changes[key] for key in ('pid', 'create_time') if key in changes}
    return build(observed=observed(**stamps), **changes)


def differences(**changes):
    return resources.observed_matches_requested(build(**changes))


def test_the_three_fact_layers_stay_separate():
    record = build()
    assert record.requested_grants == PAIRS
    assert record.applied_grants == PAIRS
    assert record.observed.effective_grants == PAIRS
    assert resources.observed_matches_requested(record) == []


@pytest.mark.parametrize('field', resources.PLANNED_FIELDS)
def test_incomplete_planned_policy_refuses(field):
    policy = planned()
    del policy[field]
    with pytest.raises(resources.ResourceRecordError, match='planned policy must hold exactly'):
        build(planned=policy)


def test_unknown_planned_field_refuses():
    policy = planned()
    policy['effective_backend'] = BACKEND
    with pytest.raises(resources.ResourceRecordError, match='planned policy must hold exactly'):
        build(planned=policy)


@pytest.mark.parametrize('field', resources.OBSERVED_FIELDS)
def test_incomplete_observation_refuses(field):
    with pytest.raises(resources.ResourceRecordError, match='observation must hold exactly'):
        build(observed=observed(drop=(field,)))


def test_missing_applied_grants_refuse():
    with pytest.raises(resources.ResourceRecordError, match='applied grants must be a list'):
        build(applied=None)


def test_applied_grant_rejects_a_bare_mapping():
    with pytest.raises(resources.ResourceRecordError, match='applied grants must be a list'):
        build(applied={'resource': 'workspace', 'access': 'rw'})


def test_observing_the_requested_policy_itself_refuses():
    policy = planned()
    with pytest.raises(resources.ResourceRecordError, match='facts are separate'):
        resources.build_record(execution_id='exec-1', pid=41, create_time=900,
                               planned=policy, applied=policy['grants'], observed=policy)


@pytest.mark.parametrize('value', ['', ' ', 'exec-1 ', 'exec\x011', 'exec\n1', 'exec\x001',
                                    'exec\x7f1', None, 7])
def test_invalid_execution_id_refuses(value):
    with pytest.raises(resources.ResourceRecordError, match='invalid execution ID'):
        build(execution_id=value)


@pytest.mark.parametrize('value', ['41', True, False, 0, -5, 1.5, None])
def test_invalid_process_stamp_refuses(value):
    with pytest.raises(resources.ResourceRecordError, match='invalid pid'):
        build(pid=value, observed=observed(pid=value))
    with pytest.raises(resources.ResourceRecordError, match='invalid create time'):
        build(create_time=value, observed=observed(create_time=value))


@pytest.mark.parametrize('value', ['readwrite', 'WRITE', 'read-only', 'all'])
def test_unknown_grant_access_refuses(value):
    with pytest.raises(resources.ResourceRecordError, match='unknown grant access'):
        build(applied=[{'resource': 'workspace', 'access': value},
                       {'resource': 'toolchain', 'access': 'ro'}])


@pytest.mark.parametrize('value', ['', ' rw', 'rw '])
def test_blank_grant_access_refuses(value):
    with pytest.raises(resources.ResourceRecordError, match='invalid grant access'):
        build(applied=[{'resource': 'workspace', 'access': value},
                       {'resource': 'toolchain', 'access': 'ro'}])


def test_duplicate_grant_refuses():
    with pytest.raises(resources.ResourceRecordError, match='duplicate grant workspace'):
        build(applied=grants(('workspace', 'rw'), ('workspace', 'ro')))


@pytest.mark.parametrize('value', [SID, {'sid': SID}, 'S-1-15-3-1'])
def test_capability_sids_must_be_a_list(value):
    with pytest.raises(resources.ResourceRecordError,
                       match='capability SID list must be a list of SIDs'):
        build(observed=observed(capability_sids=value))


def test_blank_capability_sid_refuses():
    with pytest.raises(resources.ResourceRecordError, match='invalid capability SID'):
        build(observed=observed(capability_sids=[SID, ' ']))


def test_observed_pid_must_be_the_execution_process():
    with pytest.raises(resources.ResourceRecordError,
                       match='observed pid is not the execution process'):
        build(observed=observed(pid=42))


def test_observed_create_time_must_match_the_execution():
    with pytest.raises(resources.ResourceRecordError,
                       match='observed create time is not the execution process'):
        build(observed=observed(create_time=901))


def test_backend_mismatch_is_a_difference():
    assert differences(observed=observed(backend='mxc-sandbox')) == [
        'backend observed mxc-sandbox, requested processcontainer']


def test_tier_mismatch_is_a_difference():
    assert differences(observed=observed(tier='standard-container')) == [
        'tier observed standard-container, requested base-container']


def test_requested_grant_that_was_never_observed_is_a_difference():
    assert differences(observed=observed(effective_grants=grants(('toolchain', 'ro')))) == [
        'grant workspace requested, not observed']


def test_observed_grant_that_was_never_requested_is_a_difference():
    assert differences(observed=observed(effective_grants=grants(*PAIRS, ('secret', 'ro')))) == [
        'grant secret observed, never requested',
        'grant secret observed, not applied by Core']


def test_observed_access_that_differs_from_the_request_is_a_difference():
    assert differences(observed=observed(
        effective_grants=grants(('toolchain', 'ro'), ('workspace', 'ro')))) == [
        'grant workspace observed ro, requested rw']


def test_applied_access_that_differs_from_the_request_is_a_difference():
    assert differences(applied=grants(('toolchain', 'ro'), ('workspace', 'ro'))) == [
        'grant workspace applied ro, requested rw']


def test_applied_grant_that_was_never_requested_is_a_difference():
    assert differences(applied=grants(*PAIRS, ('extra', 'ro'))) == [
        'grant extra applied by Core, never requested']


def test_requested_grant_that_core_never_applied_is_a_difference():
    assert differences(applied=grants(('toolchain', 'ro'))) == [
        'grant workspace requested, not applied by Core',
        'grant workspace observed, not applied by Core']


def test_capability_sid_without_a_writable_request_is_a_difference():
    quiet = grants(('toolchain', 'ro'), ('workspace', 'ro'))
    assert differences(planned=planned(grants=quiet), applied=quiet,
                       observed=observed(effective_grants=quiet)) == [
        'capability SID %s observed, no writable grant requested' % SID]


def test_capability_sid_backed_by_a_writable_request_is_not_a_difference():
    assert differences(observed=observed(capability_sids=[SID])) == []


def test_an_absent_observation_is_a_difference_and_refuses_effective_policy():
    record = build(observed=None)
    assert resources.observed_matches_requested(record) == ['observation missing']
    with pytest.raises(resources.ResourceRecordError, match='no observation'):
        resources.effective_policy(record)


def test_requested_policy_is_never_reported_as_effective_policy():
    record = build(observed=None)
    requested = resources.requested_policy(record)
    assert requested['source'] == 'requested'
    assert requested['grants'] == grants(*PAIRS)
    with pytest.raises(resources.ResourceRecordError, match='no observation'):
        resources.effective_policy(record)


def test_effective_policy_reports_only_the_observed_facts():
    policy = resources.effective_policy(build())
    assert policy == {'source': 'observed', 'execution_id': 'exec-1', 'pid': 41,
                      'create_time': 900, 'backend': BACKEND, 'tier': TIER,
                      'effective_grants': grants(*PAIRS), 'workload_identity': OWNER,
                      'capability_sids': [SID]}


def test_effective_policy_refuses_while_any_difference_stands():
    with pytest.raises(resources.ResourceRecordError,
                       match='effective policy differs from the requested policy') as caught:
        resources.effective_policy(build(observed=observed(tier='standard-container')))
    assert 'tier observed standard-container, requested base-container' in str(caught.value)


@pytest.mark.parametrize('call', ['observed_matches_requested', 'effective_policy',
                                  'requested_policy', 'separation_key'])
def test_a_bare_mapping_is_not_a_record(call):
    argument = {'execution_id': 'exec-1', 'pid': 41, 'create_time': 900,
                'observed': observed()}
    with pytest.raises(resources.ResourceRecordError, match='resource record required'):
        getattr(resources, call)(argument)


def test_separation_key_is_execution_pid_and_creation_time():
    assert resources.separation_key(build()) == ('exec-1', 41, 900)


def test_workload_identity_is_never_part_of_the_separation_key():
    other = build(observed=observed(workload_identity=OTHER_OWNER))
    assert other.observed.workload_identity != build().observed.workload_identity
    assert resources.separation_key(other) == resources.separation_key(build())
    assert resources.same_execution(build(), other) is True


def test_one_host_sid_shared_by_two_executions_never_merges_them():
    other = build(execution_id='exec-2')
    assert other.observed.workload_identity == build().observed.workload_identity
    assert resources.same_execution(build(), other) is False
    assert resources.separation_problems([build(), other]) == []


@pytest.mark.parametrize('change', [{'execution_id': 'exec-2'}, {'pid': 42},
                                    {'create_time': 901}])
def test_two_shared_facts_are_not_the_same_execution(change):
    assert resources.same_execution(build(), build_pair(**change)) is False


def test_reusing_an_execution_id_for_another_process_fails_closed():
    reused = build_pair(pid=42)
    assert resources.separation_problems([build(), reused]) == [
        'execution exec-1: execution id reused by another process']


def test_reusing_an_execution_id_with_another_creation_time_fails_closed():
    reused = build_pair(create_time=901)
    assert resources.separation_problems([build(), reused]) == [
        'execution exec-1: creation time mismatch']


def test_two_executions_sharing_one_host_sid_separate_without_problems():
    records = [build(), build(execution_id='exec-2'),
               build(execution_id='exec-3', observed=observed(workload_identity=OTHER_OWNER))]
    assert resources.separation_problems(records) == []


def test_an_absent_observation_fails_closed_for_separation():
    assert resources.separation_problems([build(), build(execution_id='exec-2',
                                                         observed=None)]) == [
        'execution exec-2: observation missing, separation unverified']


def test_a_second_observation_of_one_execution_is_not_a_problem():
    assert resources.separation_problems([build(), build()]) == []


def test_separation_problems_requires_a_list_of_records():
    with pytest.raises(resources.ResourceRecordError,
                       match='a list of resource records is required'):
        resources.separation_problems({'exec-1': build()})
    with pytest.raises(resources.ResourceRecordError, match='resource record required'):
        resources.separation_problems([{'execution_id': 'exec-1', 'pid': 41,
                                        'create_time': 900}])

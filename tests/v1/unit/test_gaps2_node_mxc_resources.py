"""T-1013 gap tests for archeus/node/mxc_resources.py lines 1-225 (the whole module).

Each test here names a branch of that slice which tests/v1/unit/test_mxc_resources.py
and tests/v1/unit/test_mxc_wire_resources.py do not decide: the module is line-covered
by them, but the listed conditions are one-sided or their denial path is never reached
with this kind of input. Ranked by owner risk - denial and fail-closed first, then
boundaries, then error paths - with the source line, the branch and the reason:

 1. (214-224) separation_problems registers (pid, create_time) for a record whose
    observation is missing, and reports every problem in a fixed order. Without the
    stamp an unverified record hides execution id reuse, and without the sorted pass
    the report order follows the caller's list order.
    -> test_a_record_without_an_observation_still_exposes_process_reuse
 2. (84-87) _sids refuses a capability SID list that is not a list instead of reading a
    missing/odd value as "no capabilities". Capability SIDs are the write-privilege
    evidence, so an absent list must be a refusal, never an empty tuple.
    -> test_a_capability_sid_list_that_is_not_a_list_refuses
 3. (60-64, 71-79) _grants validates the shape of every grant entry at all three
    layers; a pair, a bare string, a half grant, a grant with an extra key, a non-text
    resource or a control character in a resource must be refused.
    -> test_a_malformed_grant_entry_refuses_at_every_layer
 4. (167-170) the writable-grant gate reads the requested access classes only, and
    only 'rw' opens it: a request with no 'rw' (deny and ro only) still has to report
    every observed capability SID.
    -> test_a_deny_only_request_never_excuses_a_capability_sid
 5. (94-97, 203-204) same_execution runs both arguments through _record, so two equal
    bare mappings are never read as the same execution.
    -> test_same_execution_refuses_a_bare_mapping
 6. (60-64, 106, 113) _fields pins the exact key set of both layers, so an observation
    cannot carry planned fields and a planned policy cannot carry effective ones.
    -> test_an_observation_cannot_carry_planned_fields
 7. (174-178) requested_policy reports the planned layer even for a fully observed
    record, and never a single observed fact.
    -> test_requested_policy_hides_every_observed_fact
 8. (90-91, 176-178, 190-195) the reported policies are fresh containers: rewriting a
    report must not rewrite the record or the next report.
    -> test_reported_policies_are_detached_from_the_record
 9. (22-43) Observation and ResourceRecord are frozen, so the facts that the match was
    checked against cannot be rewritten after the check.
    -> test_record_and_observed_facts_cannot_be_rewritten_after_the_match
10. (54-57) _stamp bounds: the open side is the lower bound - the smallest positive
    stamp must be accepted on both the record side and the observation side; the
    widest stamps are kept so that an invented upper cap is caught too.
    -> test_the_minimum_and_maximum_process_stamps_are_accepted

Synthetic facts only: no OS call, no Windows API, no network, no real process, nothing
platform dependent, and no dependency on any other test_gaps2 file or on queue order.
"""

import dataclasses

import pytest

from archeus.node import mxc_resources as resources


SID = 'S-1-15-3-1'
SECOND_SID = 'S-1-15-3-2'
OWNER = 'S-1-15-2-999999'
OTHER_OWNER = 'S-1-15-2-888888'
BACKEND = 'processcontainer'
TIER = 'base-container'
PAIRS = (('toolchain', 'ro'), ('workspace', 'rw'))
BAD = 'tool%chain' + chr(1)


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


def build_pair(**changes):
    stamps = {key: changes[key] for key in ('pid', 'create_time') if key in changes}
    execution_id = changes.pop('execution_id', 'exec-1')
    return build(execution_id=execution_id, observed=observed(**stamps), **changes)


def test_separation_problems_refuses_a_container_that_is_not_a_list():
    """Extra: separation_problems will not reason about a non-list (208-209)."""
    for container in (None, 7, {SID}):
        with pytest.raises(resources.ResourceRecordError,
                           match='a list of resource records is required'):
            resources.separation_problems(container)


def test_a_record_without_an_observation_still_exposes_process_reuse():
    """Branch 1: the stamp table is filled before the observation check (214-224)."""
    unseen = build(execution_id='exec-1', pid=42, create_time=901, observed=None)
    assert resources.separation_problems([build(), unseen]) == [
        'execution exec-1: observation missing, separation unverified',
        'execution exec-1: execution id reused by another process']

    problems = resources.separation_problems([
        build(execution_id='zz-exec', observed=None),
        build_pair(execution_id='mm-exec', pid=71),
        build_pair(execution_id='mm-exec', pid=72),
        build(execution_id='aa-exec'),
        build_pair(execution_id='aa-exec', create_time=902),
    ])
    assert problems == [
        'execution zz-exec: observation missing, separation unverified',
        'execution aa-exec: creation time mismatch',
        'execution mm-exec: execution id reused by another process']


@pytest.mark.parametrize('value', [None, 0, 7, 1.5, {SID}],
                         ids=['none', 'zero', 'int', 'float', 'set'])
def test_a_capability_sid_list_that_is_not_a_list_refuses(value):
    """Branch 2: _sids has no lenient side for a missing or odd SID list (84-87)."""
    with pytest.raises(resources.ResourceRecordError,
                       match='capability SID list must be a list of SIDs'):
        build(observed=observed(capability_sids=value))


@pytest.mark.parametrize('entry, message', [
    pytest.param(('toolchain', 'ro'), 'grant must hold exactly', id='pair-entry'),
    pytest.param('toolchain=ro', 'grant must hold exactly', id='text-entry'),
    pytest.param({'resource': 'toolchain'}, 'grant must hold exactly', id='no-access'),
    pytest.param({'resource': 'toolchain', 'access': 'ro', 'source': 'planned'},
                 'grant must hold exactly', id='extra-key'),
    pytest.param({'resource': 7, 'access': 'ro'}, 'invalid grant resource',
                 id='int-resource'),
    pytest.param({'resource': BAD, 'access': 'ro'}, 'invalid grant resource',
                 id='control-char'),
])
def test_a_malformed_grant_entry_refuses_at_every_layer(entry, message):
    """Branch 3: every grant of every layer is shape-checked, not just the applied one."""
    planned_grants = grants(('toolchain', 'ro'), ('workspace', 'rw'))
    planned_grants[0] = entry
    with pytest.raises(resources.ResourceRecordError, match=message):
        build(planned=planned(grants=planned_grants), applied=planned_grants)
    effective_grants = grants(('toolchain', 'ro'), ('workspace', 'rw'))
    effective_grants[0] = entry
    with pytest.raises(resources.ResourceRecordError, match=message):
        build(observed=observed(effective_grants=effective_grants))


def test_a_deny_only_request_never_excuses_a_capability_sid():
    """Branch 4: only a requested 'rw' opens the capability SID gate (167-170)."""
    quiet = grants(('toolchain', 'deny'), ('workspace', 'ro'))
    record = build(planned=planned(grants=quiet), applied=quiet,
                   observed=observed(effective_grants=quiet,
                                     capability_sids=[SECOND_SID, SID]))
    assert resources.observed_matches_requested(record) == [
        'capability SID %s observed, no writable grant requested' % SID,
        'capability SID %s observed, no writable grant requested' % SECOND_SID]
    with pytest.raises(resources.ResourceRecordError,
                       match='effective policy differs from the requested policy') as caught:
        resources.effective_policy(record)
    assert str(caught.value).count('no writable grant requested') == 2


def test_same_execution_refuses_a_bare_mapping():
    """Branch 5: same_execution validates both arguments before comparing (203-204)."""
    mapping = {'execution_id': 'exec-1', 'pid': 41, 'create_time': 900}
    with pytest.raises(resources.ResourceRecordError, match='resource record required'):
        resources.same_execution(mapping, dict(mapping))
    with pytest.raises(resources.ResourceRecordError, match='resource record required'):
        resources.same_execution(build(), mapping)
    with pytest.raises(resources.ResourceRecordError, match='resource record required'):
        resources.same_execution(None, build())


@pytest.mark.parametrize('field', ['grants', 'requested_grants', 'applied_grants',
                                   'policy'],
                         ids=['grants', 'requested-grants', 'applied-grants', 'policy'])
def test_an_observation_cannot_carry_planned_fields(field):
    """Branch 6: _fields compares the key set exactly, in both directions (60-64)."""
    with pytest.raises(resources.ResourceRecordError,
                       match='observation must hold exactly'):
        build(observed=observed(**{field: grants(('workspace', 'rw'))}))
    with pytest.raises(resources.ResourceRecordError,
                       match='planned policy must hold exactly'):
        build(planned=planned(effective_grants=grants(('workspace', 'rw'))))


def test_requested_policy_hides_every_observed_fact():
    """Branch 7: requested_policy (174-178) is asked for a record that has one."""
    wanted = {'source': 'requested', 'execution_id': 'exec-1', 'backend': BACKEND,
              'tier': TIER, 'grants': grants(*PAIRS)}
    assert resources.requested_policy(build()) == wanted
    contradicted = build(observed=observed(effective_grants=grants(('toolchain', 'ro')),
                                           capability_sids=[SECOND_SID],
                                           workload_identity=OTHER_OWNER,
                                           backend='mxc-sandbox',
                                           tier='standard-container'))
    assert resources.requested_policy(contradicted) == wanted
    assert resources.requested_policy(build(observed=None)) == wanted


def test_reported_policies_are_detached_from_the_record():
    """Branch 8: _grant_dicts (90-91) rebuilds every report, so a report cannot leak."""
    record = build()
    requested = resources.requested_policy(record)
    requested['source'] = 'observed'
    requested['grants'][0]['access'] = 'rw'
    requested['grants'].append({'resource': 'secret', 'access': 'rw'})
    effective = resources.effective_policy(record)
    effective['source'] = 'requested'
    effective['effective_grants'][0]['access'] = 'ro'
    effective['capability_sids'].append(SECOND_SID)
    assert record.requested_grants == PAIRS
    assert record.applied_grants == PAIRS
    assert record.observed.effective_grants == PAIRS
    assert record.observed.capability_sids == (SID,)
    assert resources.requested_policy(record)['grants'] == grants(*PAIRS)
    assert resources.effective_policy(record)['capability_sids'] == [SID]
    assert resources.observed_matches_requested(record) == []


def test_record_and_observed_facts_cannot_be_rewritten_after_the_match():
    """Branch 9: the frozen dataclasses (22-43) are what keeps a match checked."""
    record = build()
    assert resources.observed_matches_requested(record) == []
    with pytest.raises(dataclasses.FrozenInstanceError):
        record.observed.effective_grants = grants(('toolchain', 'ro'),
                                                  ('workspace', 'ro'))
    with pytest.raises(dataclasses.FrozenInstanceError):
        record.observed.pid = 99
    with pytest.raises(dataclasses.FrozenInstanceError):
        record.applied_grants = ()
    assert record.observed.effective_grants == PAIRS
    assert record.observed.pid == 41
    assert record.applied_grants == PAIRS
    assert resources.separation_key(record) == ('exec-1', 41, 900)
    assert resources.observed_matches_requested(record) == []
    resources.effective_policy(record)


@pytest.mark.parametrize('changes', [
    pytest.param({'pid': 1}, id='pid-min'),
    pytest.param({'create_time': 1}, id='create-min'),
    pytest.param({'pid': 1 << 63}, id='pid-widest'),
    pytest.param({'create_time': (1 << 64) - 1}, id='create-widest'),
])
def test_the_minimum_and_maximum_process_stamps_are_accepted(changes):
    """Branch 10: _stamp (54-57) keeps every positive int, both sides of the record."""
    record = build(**changes, observed=observed(**changes))
    wanted = (changes.get('pid', 41), changes.get('create_time', 900))
    assert resources.separation_key(record)[1:] == wanted
    assert resources.separation_problems([record, build_pair(**changes)]) == []
    assert resources.same_execution(record, build_pair(**changes)) is True
    assert resources.effective_policy(record)['pid'] == wanted[0]

"""T-1347: the highest-risk uncovered branches of `archeus/node/mxc_resources.py` 84-131
(the MXC resource record keeps planned, applied and observed facts apart), at the source tip
6b1a30b8 of round eleven.

Selected probes, ranked denial and fail-closed first, then boundaries, then error paths. Each
names the source branch whose removal or inversion its assertion catches:

  1 `build_record` 104                  applied and observed as one object is refused before the
                                        observed facts are read
  2 `build_record` 101                  the execution id is checked before the process stamps
  3 `build_record` 114                  an observed pid goes through the integer check first
  4 `build_record` 116                  an observed create time goes through the integer check first
  5 `_sids` 85-87                       a capability SID tuple is accepted, and an empty list is none
  6 `build_record` 110                  applied grants are validated even with no observation
  7 `build_record` 112-113              with no observation, applied grants stay their own facts
  8 `build_record` 106-109              planned grants are validated through `_grants`
  9 `build_record` 118-120              observed effective grants are validated through `_grants`
 10 `build_record` 117-122              observed backend and workload identity are text-checked

Pure data: every host fact is an argument, and no Windows API, process or file is involved.
"""

import pytest

from archeus.node import mxc_resources as resources

SID = 'S-1-15-3-1'
OWNER = 'S-1-15-2-999999'
BACKEND = 'processcontainer'
TIER = 'base-container'
PAIRS = (('toolchain', 'ro'), ('workspace', 'rw'))


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


# ── 1: one object for two layers is refused before anything is read (104) ──

def test_applied_and_observed_as_one_object_refuse_before_the_observation_is_read():
    shared = []
    with pytest.raises(resources.ResourceRecordError, match='facts are separate'):
        resources.build_record(execution_id='exec-1', pid=41, create_time=900,
                               planned=planned(), applied=shared, observed=shared)


# ── 2: the execution id is checked before the process stamps (101) ──

def test_the_execution_id_is_checked_before_the_process_stamps():
    with pytest.raises(resources.ResourceRecordError, match='invalid execution ID'):
        resources.build_record(execution_id='', pid=0, create_time=0,
                               planned=planned(), applied=grants(*PAIRS),
                               observed=observed())


# ── 3: an observed pid is an integer before it is compared (114) ──

def test_an_observed_pid_that_is_a_bool_is_refused_as_invalid_not_as_a_mismatch():
    # True == 1, so without the integer check this observation would match pid 1
    with pytest.raises(resources.ResourceRecordError, match='invalid observed pid'):
        build(pid=1, create_time=900, observed=observed(pid=True))


# ── 4: an observed create time is an integer before it is compared (116) ──

def test_an_observed_create_time_that_is_a_bool_is_refused_as_invalid():
    with pytest.raises(resources.ResourceRecordError, match='invalid observed create time'):
        build(create_time=1, observed=observed(create_time=True))


# ── 5: capability SIDs as a tuple, and none as an empty list (85-87) ──

def test_capability_sids_given_as_a_tuple_are_kept_and_none_is_empty():
    record = build(observed=observed(capability_sids=(SID,)))
    assert record.observed.capability_sids == (SID,)
    assert build(observed=observed(capability_sids=[])).observed.capability_sids == ()


# ── 6: applied grants are validated even with no observation (110, 112) ──

def test_applied_grants_are_validated_when_nothing_is_observed():
    with pytest.raises(resources.ResourceRecordError, match='applied grants must be a list'):
        build(applied='workspace', observed=None)


# ── 7: with no observation, applied grants stay their own fact (112-113) ──

def test_with_no_observation_the_applied_grants_stay_apart_from_the_request():
    applied = grants(('toolchain', 'ro'))
    record = build(applied=applied, observed=None)
    assert record.observed is None
    assert record.requested_grants == PAIRS
    assert record.applied_grants == (('toolchain', 'ro'),)


# ── 8: planned grants are validated through `_grants` (106-109) ──

def test_a_planned_grant_with_an_unknown_access_refuses_as_a_requested_one():
    policy = planned(grants=grants(('workspace', 'write')))
    with pytest.raises(resources.ResourceRecordError, match='unknown grant access write'):
        build(planned=policy)


# ── 9: observed effective grants are validated through `_grants` (119-120) ──

@pytest.mark.parametrize('value', [dict(resource='workspace', access='rw'), 'workspace'])
def test_observed_effective_grants_must_be_a_list_of_grants(value):
    with pytest.raises(resources.ResourceRecordError,
                       match='effective grants must be a list of grants'):
        build(observed=observed(effective_grants=value))


# ── 10: observed backend and workload identity are text-checked (117-122) ──

@pytest.mark.parametrize('field, value, label', [
    ('backend', ' ' + BACKEND, 'observed backend'),
    ('backend', '', 'observed backend'),
    ('workload_identity', OWNER + '\x01', 'workload identity'),
    ('workload_identity', 'two words', 'workload identity'),
])
def test_observed_backend_and_workload_identity_are_text_checked(field, value, label):
    with pytest.raises(resources.ResourceRecordError, match='invalid ' + label):
        build(observed=observed(**{field: value}))

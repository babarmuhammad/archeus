"""PSEC-aware resource record: planned, applied and observed facts never merge.

Pure data and logic. No archeus import, no OS call and no Windows API: every host
fact arrives as an argument, and a record never reports a requested policy as an
effective one. Separation is execution id plus PID plus creation time; a workload
identity is only ever an observation.
"""

from dataclasses import dataclass

PLANNED_FIELDS = ('backend', 'grants', 'tier')
GRANT_FIELDS = ('resource', 'access')
GRANT_ACCESS = ('deny', 'ro', 'rw')
OBSERVED_FIELDS = ('backend', 'capability_sids', 'create_time', 'effective_grants',
                   'pid', 'tier', 'workload_identity')


class ResourceRecordError(ValueError):
    pass


@dataclass(frozen=True)
class Observation:
    pid: int
    create_time: int
    backend: str
    tier: str
    effective_grants: tuple
    workload_identity: str
    capability_sids: tuple = ()


@dataclass(frozen=True)
class ResourceRecord:
    execution_id: str
    pid: int
    create_time: int
    requested_backend: str
    requested_tier: str
    requested_grants: tuple
    applied_grants: tuple
    observed: Observation | None


def _text(value, label):
    # Separation and match messages quote these values, so a control character in
    # one of them could forge a line that a reviewer (or a log reader) parses apart.
    if (not isinstance(value, str) or not value or value != value.strip()
            or any(ch.isspace() or ord(ch) < 32 or ord(ch) == 127 for ch in value)):
        raise ResourceRecordError('invalid %s' % label)
    return value


def _stamp(value, label):
    if type(value) is not int or value <= 0:
        raise ResourceRecordError('invalid %s' % label)
    return value


def _fields(facts, required, label):
    if not isinstance(facts, dict) or set(facts) != set(required):
        raise ResourceRecordError('%s must hold exactly: %s'
                                  % (label, ', '.join(required)))
    return dict(facts)


def _grants(facts, label):
    if isinstance(facts, (dict, str, bytes)) or not isinstance(facts, (list, tuple)):
        raise ResourceRecordError('%s must be a list of grants' % label)
    out = []
    for grant in facts:
        _fields(grant, GRANT_FIELDS, 'grant')
        resource = _text(grant['resource'], 'grant resource')
        access = _text(grant['access'], 'grant access')
        # An unknown access class must not default to the closest known one.
        if access not in GRANT_ACCESS:
            raise ResourceRecordError('unknown grant access %s' % access)
        if any(resource == seen for seen, _ in out):
            raise ResourceRecordError('duplicate grant %s' % resource)
        out.append((resource, access))
    return tuple(sorted(out))


def _sids(values):
    if isinstance(values, (str, bytes, dict)) or not isinstance(values, (list, tuple)):
        raise ResourceRecordError('capability SID list must be a list of SIDs')
    return tuple(sorted({_text(sid, 'capability SID') for sid in values}))


def _grant_dicts(grants):
    return [dict(zip(GRANT_FIELDS, grant)) for grant in grants]


def _record(value):
    if not isinstance(value, ResourceRecord):
        raise ResourceRecordError('resource record required')
    return value


def build_record(*, execution_id, pid, create_time, planned, applied, observed=None):
    execution_id = _text(execution_id, 'execution ID')
    pid = _stamp(pid, 'pid')
    create_time = _stamp(create_time, 'create time')
    if planned is applied or planned is observed or applied is observed:
        raise ResourceRecordError('planned, applied and observed facts are separate')
    planned = _fields(planned, PLANNED_FIELDS, 'planned policy')
    requested_backend = _text(planned['backend'], 'requested backend')
    requested_tier = _text(planned['tier'], 'requested tier')
    requested_grants = _grants(planned['grants'], 'requested grants')
    applied_grants = _grants(applied, 'applied grants')
    observation = None
    if observed is not None:
        facts = _fields(observed, OBSERVED_FIELDS, 'observation')
        observation = Observation(pid=_stamp(facts['pid'], 'observed pid'),
                                  create_time=_stamp(facts['create_time'],
                                                     'observed create time'),
                                  backend=_text(facts['backend'], 'observed backend'),
                                  tier=_text(facts['tier'], 'observed tier'),
                                  effective_grants=_grants(facts['effective_grants'],
                                                           'effective grants'),
                                  workload_identity=_text(facts['workload_identity'],
                                                          'workload identity'),
                                  capability_sids=_sids(facts['capability_sids']))
        if observation.pid != pid:
            raise ResourceRecordError('observed pid is not the execution process')
        if observation.create_time != create_time:
            raise ResourceRecordError('observed create time is not the execution process')
    return ResourceRecord(execution_id=execution_id, pid=pid, create_time=create_time,
                          requested_backend=requested_backend, requested_tier=requested_tier,
                          requested_grants=requested_grants, applied_grants=applied_grants,
                          observed=observation)


def observed_matches_requested(record):
    record = _record(record)
    if record.observed is None:
        return ['observation missing']
    differences = []
    if record.observed.backend != record.requested_backend:
        differences.append('backend observed %s, requested %s'
                           % (record.observed.backend, record.requested_backend))
    if record.observed.tier != record.requested_tier:
        differences.append('tier observed %s, requested %s'
                           % (record.observed.tier, record.requested_tier))
    requested = dict(record.requested_grants)
    applied = dict(record.applied_grants)
    effective = dict(record.observed.effective_grants)
    for resource in sorted(set(requested) | set(applied) | set(effective)):
        if resource in requested and resource in applied:
            if applied[resource] != requested[resource]:
                differences.append('grant %s applied %s, requested %s'
                                   % (resource, applied[resource], requested[resource]))
        elif resource in requested:
            differences.append('grant %s requested, not applied by Core' % resource)
        elif resource in applied:
            differences.append('grant %s applied by Core, never requested' % resource)
        if resource in effective and resource not in requested:
            differences.append('grant %s observed, never requested' % resource)
        if resource in effective and resource in requested:
            if effective[resource] != requested[resource]:
                differences.append('grant %s observed %s, requested %s'
                                   % (resource, effective[resource], requested[resource]))
        elif resource in requested:
            differences.append('grant %s requested, not observed' % resource)
        if resource in effective and resource not in applied:
            differences.append('grant %s observed, not applied by Core' % resource)
    if not any(access == 'rw' for access in requested.values()):
        for sid in record.observed.capability_sids:
            differences.append('capability SID %s observed, no writable grant requested'
                               % sid)
    return differences


def requested_policy(record):
    record = _record(record)
    return {'source': 'requested', 'execution_id': record.execution_id,
            'backend': record.requested_backend, 'tier': record.requested_tier,
            'grants': _grant_dicts(record.requested_grants)}


def effective_policy(record):
    record = _record(record)
    if record.observed is None:
        raise ResourceRecordError('no observation: %s reports no effective policy'
                                  % record.execution_id)
    differences = observed_matches_requested(record)
    if differences:
        raise ResourceRecordError('effective policy differs from the requested policy: %s'
                                  % '; '.join(differences))
    return {'source': 'observed', 'execution_id': record.execution_id,
            'pid': record.observed.pid, 'create_time': record.observed.create_time,
            'backend': record.observed.backend, 'tier': record.observed.tier,
            'effective_grants': _grant_dicts(record.observed.effective_grants),
            'workload_identity': record.observed.workload_identity,
            'capability_sids': list(record.observed.capability_sids)}


def separation_key(record):
    record = _record(record)
    return (record.execution_id, record.pid, record.create_time)


def same_execution(left, right):
    return separation_key(left) == separation_key(right)


def separation_problems(records):
    if isinstance(records, (dict, str, bytes)) or not isinstance(records, (list, tuple)):
        raise ResourceRecordError('a list of resource records is required')
    problems = []
    stamps = {}
    for record in records:
        record = _record(record)
        if record.observed is None:
            problems.append('execution %s: observation missing, separation unverified'
                            % record.execution_id)
        stamps.setdefault(record.execution_id, set()).add((record.pid, record.create_time))
    for execution_id in sorted(stamps):
        if len(stamps[execution_id]) > 1:
            pids = {pid for pid, _ in stamps[execution_id]}
            problems.append('execution %s: %s'
                            % (execution_id,
                               'execution id reused by another process' if len(pids) > 1
                               else 'creation time mismatch'))
    return problems

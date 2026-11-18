# ruff: noqa: F811  (the imported wire fixtures are taken as arguments)
"""T-801: the PSEC-aware resource record is built, checked and journalled between the
Job membership and the single resume. Same fakes as the wire tests."""

import copy
from types import SimpleNamespace

import pytest

from archeus.node import local, mxc_resources as resources, staging

from .test_mxc_wire import (CREATION_TIME, PID, args, journal_ops, journal_records,  # noqa: F401
                            native_parts, wire)


def grants(launch):
    fs = launch.policy.raw['filesystem']
    return [{'resource': local.mxc_resource_id(path), 'access': access}
            for key, access in (('readwritePaths', 'rw'), ('readonlyPaths', 'ro'),
                                ('deniedPaths', 'deny')) for path in fs[key]]


def facts(launch, **observed):
    seen = dict(pid=PID, create_time=CREATION_TIME, backend='processcontainer',
                tier='base-container', effective_grants=grants(launch),
                workload_identity='workload-1', capability_sids=[])
    return {'applied': grants(launch), 'observed': dict(seen, **observed)}


def read_back(h, answer=None, **observed):
    calls = []

    def readback(child):
        calls.append(child)
        if isinstance(answer, BaseException):
            raise answer
        return copy.deepcopy(facts(h.launch, **observed)) if answer is None else answer

    h.launch.readback = readback
    return calls


def refused(h, match):
    with pytest.raises((staging.StageError, OSError, resources.ResourceRecordError), match=match):
        h.launch.start(job=h.job)
    assert h.api.events.count('resume') == 0 and h.api.events.count('kill') == 1
    assert h.api.handles == {} and h.launch.process is None
    ops = journal_ops(h.journal)
    assert 'ownership' not in ops and ops[-1] == 'quarantine'


def test_a_read_back_that_matches_is_journalled_and_resumes(wire):
    h = wire()
    calls = read_back(h)
    h.launch.start(job=h.job)
    assert calls == [h.launch.process] and h.api.events.count('resume') == 1
    owner = journal_records(h.journal)[1]
    wanted = sorted(grants(h.launch), key=lambda grant: grant['resource'])
    assert owner['applied'] == wanted
    assert owner['observed']['source'] == 'observed' and owner['observed']['pid'] == PID
    assert owner['observed']['effective_grants'] == wanted
    assert owner['owned'] == []
    h.launch.process.terminate()


@pytest.mark.parametrize('change', [
    dict(tier='other-tier'), dict(backend='other'), dict(effective_grants=[]),
    dict(capability_sids=['S-1-15-3-1'], effective_grants=None),
])
def test_a_read_back_that_differs_never_resumes(wire, change):
    h = wire()
    seen = {key: value for key, value in change.items() if value is not None}
    if change.get('effective_grants', 1) is None:
        seen['effective_grants'] = grants(h.launch) + [{'resource': 'C:/extra',
                                                        'access': 'rw'}]
        seen.pop('capability_sids')
    read_back(h, **seen)
    refused(h, 'differ from the request')


def test_a_read_back_that_raises_never_resumes(wire):
    h = wire()
    read_back(h, OSError('read-back failed'))
    refused(h, 'read-back failed')


@pytest.mark.parametrize('answer', [None, {'applied': []}, {'applied': [], 'observed': None},
                                    {'applied': 'x', 'observed': {}}, 'ok'])
def test_a_read_back_that_answers_nothing_usable_never_resumes(wire, answer):
    h = wire()
    h.launch.readback = lambda child: answer
    refused(h, 'read-back|observation missing|resource|grants')


def test_a_read_back_for_another_process_never_resumes(wire):
    h = wire()
    read_back(h, pid=PID + 1)
    refused(h, 'observed pid')


def test_the_default_is_unverified_and_still_launches(wire):
    h = wire()
    h.launch.start(job=h.job)
    owner = journal_records(h.journal)[1]
    assert owner['applied'] == [] and owner['observed'] == {} and owner['owned'] == []
    assert h.launch.readback is None and h.launch._resource.observed is None
    h.launch.process.terminate()


def test_a_path_with_whitespace_is_still_a_valid_resource(wire):
    assert local.mxc_resource_id('a b%' + chr(10)) == 'a%0020b%0025%000A'
    h = wire()
    h.launch.policy.raw['filesystem']['readonlyPaths'].append('C:/Program Files/x')
    record = h.launch._resource_record(SimpleNamespace(pid=PID, create_time=CREATION_TIME))
    assert ('C:/Program%0020Files/x', 'ro') in record.requested_grants


def test_two_live_launches_never_share_a_process(wire):
    first, second = wire(), wire(execution_id='e2')
    first.launch.start(job=first.job)
    with pytest.raises(staging.StageError, match='shares'):
        second.launch.start(job=second.job)
    assert second.api.events.count('resume') == 0
    assert journal_ops(second.journal, 'e2-p1')[-1] == 'quarantine'
    first.launch.process.terminate()


def test_an_ended_launch_releases_its_process(wire):
    first = wire(outcome=lambda process: 0)
    first.launch.start(job=first.job)
    first.launch.wait()
    second = wire(execution_id='e2')
    second.launch.start(job=second.job)
    assert second.api.events.count('resume') == 1
    second.launch.process.terminate()


def test_launches_on_other_ledgers_are_not_compared(wire, tmp_path):
    first, second = wire(), wire(execution_id='e2')
    second.journal.journal.root = str(tmp_path / 'elsewhere')
    second.journal.journal.__init__(second.journal.journal.root)
    first.launch.start(job=first.job)
    second.launch.start(job=second.job)
    assert second.api.events.count('resume') == 1
    first.launch.process.terminate()
    second.launch.process.terminate()

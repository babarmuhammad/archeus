"""PV20 B6: the production MXC boundary, over fakes.

Nothing here starts a process or reaches a Windows API. The Win32 transport is
`LauncherApi`, the Job and process half is `Jobs` (the shape of the existing Win32 Job
code), the ledger is the real journal under tmp_path, and native admission is opened only
inside a test that needs the boundary to be available (`mxc.NATIVE_RUN_ENABLED` is closed
in the shipped code, and a closed gate is what makes this boundary unavailable).
"""

import hashlib
import json
import os
import subprocess
from types import SimpleNamespace

import pytest

from archeus.node import isolation as iso
from archeus.node import local, mxc, mxc_boundary, mxc_ledger, staging
from archeus.node.mxc_boundary import MxcBoundary

from .test_pv20_isolation import (FakeBoundary, make_satisfying_request, new_execution_id,
                                  os_tripwire)  # noqa: F401  (the autouse tripwire)

POLICY = 'C:\\protected\\policy-%d.json'


def outcome(launcher_exit=0, agent_outcome=3, stdout=b'', stderr=b''):
    """The launcher's own exit, kept apart from what the workload reports."""
    return mxc.FakeOutcome(launcher_exit=launcher_exit, agent_outcome=agent_outcome,
                           stdout=stdout, stderr=stderr)


def script(specs):
    """One scripted answer per launch; the last repeats."""
    specs = list(specs) or [outcome()]
    while True:
        for spec in specs:
            yield spec


class LauncherApi:
    """The Win32 surface of the MXC transport, scripted one launch at a time: handles are
    integers, the launcher exits as soon as it is resumed, and a launch's stdout and
    stderr are the bytes its script holds."""

    def __init__(self, outcomes=(), events=None):
        self.outcomes = script(outcomes)
        self.events = events if events is not None else []
        self.handles, self.created, self.agent = {}, [], {}
        self.policies, self.exited = [], {}
        self._next, self._pipes, self._current = 100, 0, None

    def _new(self, label, **info):
        self._next += 1
        self.handles[self._next] = (label, info)
        return self._next

    def protected_policy(self, data):
        self.policies.append(json.loads(data))
        return POLICY % len(self.policies), self._new('policy')

    def remove_policy(self, path, handle):
        self.close_handle(handle)

    def pipe(self, *, parent_reads):
        index, self._pipes = self._pipes % 3, self._pipes + 1
        if index == 0:
            self._current = next(self.outcomes)
        data = {1: self._current.stdout, 2: self._current.stderr}.get(index)
        queue = [] if data is None else [data, b''] if data else [b'']
        return self._new('parent', queue=queue), self._new('child')

    def attribute_list(self, handles):
        return self._new('attributes')

    def delete_attribute_list(self, handle):
        self.close_handle(handle)

    def create_process_w(self, **kwargs):
        pid = 1000 + len(self.created)
        self.created.append(dict(kwargs, pid=pid))
        self.agent[pid] = self._current.agent_outcome
        self.events.append('create_suspended')
        return self._new('process', pid=pid, exit=self._current.launcher_exit), \
            self._new('thread'), pid

    def creation_time(self, process):
        return self.handles[process][1]['pid'] * 100

    def in_job(self, job, process):
        self.events.append('verify_job')
        return True

    def resume_thread(self, thread):
        self.events.append('resume')
        return 1

    def terminate_process(self, process):
        self.exited[self.handles[process][1]['pid']] = 1

    def close_handle(self, handle):
        del self.handles[handle]

    def poll(self, process):
        info = self.handles[process][1]
        return self.exited.get(info['pid'], info['exit'])

    def read(self, handle, size):
        queue = self.handles[handle][1].get('queue')
        return queue.pop(0) if queue else None

    def write(self, handle, data):
        return len(data)


class Jobs(FakeBoundary):
    """The Job, handle and DACL reads the production class reuses from the Win32 code."""

    def __init__(self, events=None):
        super().__init__()
        self.events = events if events is not None else []
        self.terminated, self.serial = [], 0
        self.on_close = []

    def create_job(self, execution_id):
        self.serial += 1
        return {'job': execution_id, 'handle': 'synthetic-job-%d' % self.serial}

    def assign_job(self, job, process_handle):
        self.events.append('assign_job')
        super().assign_job(job, process_handle)

    def terminate_job(self, job):
        self.terminated.append(job)
        self.events.append('end_job')

    def close_job(self, job):
        super().close_job(job)
        for hook in self.on_close:
            hook(job)

    def broad_writer(self, path):
        return self.broad


@pytest.fixture
def sdk(tmp_path):
    """An expanded MXC SDK: the two artifacts the reviewed pin names, and no other."""
    root = tmp_path / 'mxc-sdk'
    (root / 'bin' / 'x64').mkdir(parents=True)
    (root / 'package.json').write_text(
        json.dumps({'name': staging.MXC_PACKAGE, 'version': staging.MXC_VERSION}),
        encoding='utf-8')
    (root / staging.MXC_EXE).write_bytes(b'the fake launcher')
    pins = {rel: hashlib.sha256((root / rel).read_bytes()).hexdigest()
            for rel in ('package.json', staging.MXC_EXE)}
    return str(root), pins


@pytest.fixture
def gate(monkeypatch):
    """Native admission opened for the test only, over fakes that start nothing."""
    monkeypatch.setattr(mxc, 'NATIVE_RUN_ENABLED', True)


def make(tmp_path, sdk, *, cls=MxcBoundary, outcomes=(), **over):
    events = []
    jobs, api = Jobs(events), LauncherApi(outcomes, events)
    ledger = mxc_ledger.Ledger(tmp_path / 'ledger')
    kw = dict(win32=api, ledger=ledger, sdk_root=sdk[0], pins=sdk[1],
              schema_validator=lambda raw: True, jobs=jobs, timeout_ms=5000,
              env_rows={'SYSTEMROOT': 'C:\\Windows'},
              outcome=lambda process: api.agent[process.pid],
              resource_reader=lambda execution_id, owner: True,
              process_reader=lambda pid: None)
    kw.update(over)
    return SimpleNamespace(boundary=cls(**kw), jobs=jobs, api=api, ledger=ledger,
                           events=events)


def request(tmp_path):
    return make_satisfying_request(new_execution_id(), str(tmp_path / 'layout'))


def conditions(h, req):
    """The six conditions as `establish` reads them, from a fresh identity and Job."""
    identity = h.boundary.create_profile(req.execution_id)
    job = h.boundary.create_job(req.execution_id)
    out = iso.check_invariant(h.boundary, req, identity, h.boundary.job_facts(job))
    return {name: holds for name, (holds, _why) in out.items()}, out


# ── available(): only with every part, and only while admission is open ──

def test_a_boundary_given_nothing_is_unavailable_and_launches_nothing(tmp_path):
    boundary = MxcBoundary()
    assert boundary.available() is False
    assert boundary.timeout_ms is None and boundary.win32 is None


def test_a_complete_boundary_is_unavailable_while_native_admission_is_closed(tmp_path, sdk):
    assert mxc.NATIVE_RUN_ENABLED is False
    assert make(tmp_path, sdk).boundary.available() is False


def test_a_complete_boundary_is_available_once_admission_is_open(tmp_path, sdk, gate):
    assert make(tmp_path, sdk).boundary.available() is True


@pytest.mark.parametrize('missing', ['win32', 'ledger', 'sdk_root', 'pins',
                                     'schema_validator', 'process_reader'])
def test_every_part_is_needed_for_it_to_be_available(tmp_path, sdk, gate, missing):
    assert make(tmp_path, sdk, **{missing: None}).boundary.available() is False


def test_a_validator_that_is_not_callable_is_no_validator(tmp_path, sdk, gate):
    assert make(tmp_path, sdk, schema_validator=True).boundary.available() is False


def test_pins_that_the_staged_sdk_does_not_match_make_it_unavailable(tmp_path, sdk, gate):
    h = make(tmp_path, sdk)
    assert h.boundary.available() is True
    with open(os.path.join(sdk[0], *staging.MXC_EXE.split('/')), 'wb') as f:
        f.write(b'a launcher nobody reviewed')
    assert h.boundary.available() is False


def test_no_pins_for_the_launcher_is_unavailable(tmp_path, sdk, gate):
    pins = {k: v for k, v in sdk[1].items() if k == 'package.json'}
    assert make(tmp_path, sdk, pins=pins).boundary.available() is False


# ── the identity: a reserved name, never a SID ──

def test_the_identity_is_a_marker_that_is_not_a_sid(tmp_path, sdk):
    h = make(tmp_path, sdk)
    eid = new_execution_id()
    marker = h.boundary.derive_sid(eid)
    assert marker == 'psec:' + iso.profile_name(eid)
    assert not marker.startswith('S-1-')
    assert h.boundary.derive_sid(eid) == marker
    assert h.boundary.derive_sid(new_execution_id()) != marker


def test_creating_a_profile_reserves_the_name_and_a_second_create_says_it_existed(tmp_path,
                                                                                 sdk):
    h = make(tmp_path, sdk)
    eid = new_execution_id()
    assert h.boundary.profile_exists(eid) is False
    first = h.boundary.create_profile(eid)
    assert first == {'profile': iso.profile_name(eid), 'sid': h.boundary.derive_sid(eid),
                     'created': True, 'existed': False, 'package_dir': ''}
    assert h.boundary.profile_exists(eid) is True
    assert h.boundary.create_profile(eid)['existed'] is True


def test_a_name_that_is_not_a_principal_is_refused_before_it_is_reserved(tmp_path, sdk):
    h = make(tmp_path, sdk)
    with pytest.raises(iso.IsolationUnavailable, match='profile_name'):
        h.boundary.create_profile('exe_not-an-id')
    assert h.boundary._reserved == {}


def seed_journal(h, name, *ops):
    digest = '0' * 64
    facts = {'intent': dict(requested_policy_digest=digest, planned=[], applied=[],
                            observed={}),
             'ownership': dict(pid=1, create_time=1, requested_policy_digest=digest,
                               applied=[], observed={}, owned=[]),
             'disposal': dict(verified_absent=True), 'completion': dict(outcome=0),
             'quarantine': dict(reason='restart_unverified')}
    for op in ops:
        h.ledger.append(name, op, **facts[op])


@pytest.mark.parametrize('ops', [('intent',), ('intent', 'ownership'),
                                 ('intent', 'ownership', 'quarantine')])
def test_a_generation_that_never_ended_with_a_completion_refuses_the_next_identity(
        tmp_path, sdk, ops):
    h = make(tmp_path, sdk)
    eid = new_execution_id()
    seed_journal(h, mxc_ledger.journal_name(eid, 1), *ops)
    with pytest.raises(iso.IsolationUnavailable, match='generation_unresolved') as err:
        h.boundary.create_profile(eid)
    assert mxc_ledger.journal_name(eid, 1) in str(err.value)
    assert h.boundary.profile_exists(eid) is False


def test_a_damaged_generation_refuses_the_next_identity(tmp_path, sdk):
    h = make(tmp_path, sdk)
    eid = new_execution_id()
    with open(os.path.join(h.ledger.root, mxc_ledger.journal_name(eid, 1) + '.jsonl'),
              'wb') as f:
        f.write(b'not a journal\n')
    with pytest.raises(iso.IsolationUnavailable, match='generation_unresolved'):
        h.boundary.create_profile(eid)


def test_only_a_later_generation_that_is_open_counts_after_a_completed_one(tmp_path, sdk):
    h = make(tmp_path, sdk)
    eid = new_execution_id()
    seed_journal(h, mxc_ledger.journal_name(eid, 1), 'intent', 'ownership', 'disposal',
             'completion')
    assert h.boundary.create_profile(eid)['created'] is True
    seed_journal(h, mxc_ledger.journal_name(eid, 2), 'intent')
    with pytest.raises(iso.IsolationUnavailable, match='-p2'):
        h.boundary.create_profile(eid)


def test_another_executions_open_generation_is_not_this_ones(tmp_path, sdk):
    h = make(tmp_path, sdk)
    seed_journal(h, mxc_ledger.journal_name(new_execution_id(), 1), 'intent')
    assert h.boundary.create_profile(new_execution_id())['created'] is True


def test_the_identity_calls_refuse_without_a_ledger(tmp_path, sdk):
    h = make(tmp_path, sdk, ledger=None)
    eid = new_execution_id()
    for call in (h.boundary.create_profile, h.boundary.delete_profile):
        with pytest.raises(iso.IsolationUnavailable, match='mxc_ledger'):
            call(eid)


def test_deleting_a_profile_releases_the_name_and_records_the_residue(tmp_path, sdk):
    h = make(tmp_path, sdk, clock=lambda: 12.5)
    eid = new_execution_id()
    h.boundary.create_profile(eid)
    assert h.boundary.delete_profile(eid) is None
    assert h.boundary.profile_exists(eid) is False
    with open(os.path.join(h.ledger.root, mxc_boundary.RESIDUE), encoding='utf-8') as f:
        lines = [json.loads(x) for x in f]
    assert len(lines) == 1
    assert (lines[0]['op'], lines[0]['execution_id'], lines[0]['profile'], lines[0]['at']) == (
        'registration_residue', eid, iso.profile_name(eid), 12.5)
    assert 'MXC-R10' in lines[0]['reason']
    assert h.jobs.mutations() == []              # nothing was deleted at the OS


def test_the_residue_file_is_not_a_journal(tmp_path, sdk):
    h = make(tmp_path, sdk)
    eid = new_execution_id()
    h.boundary.create_profile(eid)
    h.boundary.delete_profile(eid)
    assert h.ledger.journals() == {}
    assert mxc_boundary.RESIDUE.endswith('.log')


def test_a_residue_that_cannot_be_recorded_keeps_the_name_and_refuses(tmp_path, sdk):
    h = make(tmp_path, sdk)
    eid = new_execution_id()
    h.boundary.create_profile(eid)
    os.mkdir(os.path.join(h.ledger.root, mxc_boundary.RESIDUE))
    with pytest.raises(iso.IsolationUnavailable, match='residue_unrecorded'):
        h.boundary.delete_profile(eid)
    assert h.boundary.profile_exists(eid) is True


def test_a_malformed_key_is_refused_by_every_identity_call(tmp_path, sdk):
    h = make(tmp_path, sdk)
    for call in (h.boundary.create_profile, h.boundary.delete_profile,
                 h.boundary.profile_exists, h.boundary.derive_sid):
        with pytest.raises(iso.IsolationUnavailable, match='profile_name'):
            call('exe_not-an-id')


def test_a_verifier_attempt_is_named_and_reserved_like_an_execution(tmp_path, sdk):
    from archeus.core.domain import ids
    h = make(tmp_path, sdk)
    key = iso.Principal('verify', ids.new_id('verification'), 2).key
    created = h.boundary.create_profile(key)
    assert created['profile'] == iso.profile_name(key) and created['created'] is True
    assert h.boundary.profile_exists(key) is True


@pytest.mark.parametrize('sid, shown', [('S-1-15-2-1-2-3', 'S-1-15-2-1-2-3'),
                                        ('S-1-5-21-9', 'S-1-5-21-9'),
                                        ('psec:archeus.exec.x', ''), ('', ''),
                                        ('s-1-5-21', ''), ('S-1', ''), (None, '')])
def test_the_registry_names_an_identity_a_sid_only_when_it_is_one(sid, shown):
    assert iso.registry_sid(sid) == shown


# ── the six conditions, as this boundary answers them ──

def test_every_condition_holds_for_a_satisfying_plan_over_an_open_boundary(tmp_path, sdk,
                                                                          gate):
    h = make(tmp_path, sdk)
    req = request(tmp_path)
    held, out = conditions(h, req)
    assert held == dict.fromkeys(iso.CONDITIONS, True), out
    assert iso.unmet_conditions(out) == ()


def test_the_isolated_path_condition_is_the_boundarys_availability(tmp_path, sdk):
    h = make(tmp_path, sdk)                                  # admission closed
    req = request(tmp_path)
    held, _ = conditions(h, req)
    assert held['isolated_path'] is False
    assert [k for k, v in held.items() if not v] == ['isolated_path']


def test_the_identity_condition_needs_the_marker_the_name_derives(tmp_path, sdk, gate):
    h = make(tmp_path, sdk)
    req = request(tmp_path)
    identity = dict(h.boundary.create_profile(req.execution_id), sid='psec:someone-else')
    out = iso.check_invariant(h.boundary, req, identity,
                              h.boundary.job_facts(h.boundary.create_job(req.execution_id)))
    assert out['identity'][0] is False
    assert iso.check_invariant(h.boundary, req, None, None)['identity'][0] is False


def test_a_row_the_policy_cannot_list_is_not_an_established_grant(tmp_path, sdk, gate):
    h = make(tmp_path, sdk)
    req = request(tmp_path)
    req = req.__class__(**{**req.__dict__, 'grants': tuple(
        iso.Grant(g.path, 'x' if g.row == 'hook' else g.access, g.row) for g in req.grants)})
    held, _ = conditions(h, req)
    assert [k for k, v in held.items() if not v] == ['grants']


def test_a_second_name_for_one_file_in_a_granted_tree_fails_the_grants_condition(
        tmp_path, sdk, gate):
    h = make(tmp_path, sdk)
    req = request(tmp_path)
    first = os.path.join(req.workspace, 'one.txt')
    with open(first, 'xb') as f:
        f.write(b'two names')
    os.link(first, os.path.join(req.workspace, 'two.txt'))
    held, _ = conditions(h, req)
    assert [k for k, v in held.items() if not v] == ['grants']


def test_a_grant_for_a_principal_that_was_never_reserved_is_not_established(tmp_path, sdk):
    h = make(tmp_path, sdk)
    req = request(tmp_path)
    assert h.boundary.grant_established(req.workspace, h.boundary.derive_sid(req.execution_id),
                                        'rw') is False
    assert h.boundary._reserved == {}


def test_a_verified_grant_is_registered_once_per_path_for_the_launch(tmp_path, sdk):
    h = make(tmp_path, sdk)
    req = request(tmp_path)
    identity = h.boundary.create_profile(req.execution_id)
    assert h.boundary.grant_established(req.workspace, identity['sid'], 'rw') is True
    assert h.boundary.grant_established(req.grant_for('runtime').path, identity['sid'],
                                        'rx') is True
    assert h.boundary._reserved[req.execution_id] == [
        (os.path.normpath(req.workspace), 'rw'),
        (os.path.normpath(req.grant_for('runtime').path), 'rx')]
    h.boundary.create_profile(req.execution_id)
    assert h.boundary._reserved[req.execution_id] == []         # a new establishment starts over


def test_a_broad_principal_that_can_write_a_grant_fails_the_broad_grants_condition(
        tmp_path, sdk, gate):
    h = make(tmp_path, sdk)
    h.jobs.broad = 'S-1-1-0'
    req = request(tmp_path)
    held, _ = conditions(h, req)
    assert [k for k, v in held.items() if not v] == ['no_broad_grants']


def test_core_state_inside_a_granted_path_is_reachable_and_fails_two_conditions(
        tmp_path, sdk, gate):
    h = make(tmp_path, sdk)
    req = request(tmp_path)
    inside = os.path.join(req.workspace, 'core')
    os.mkdir(inside)
    req = req.__class__(**{**req.__dict__, 'core_only': (inside,)})
    held, _ = conditions(h, req)
    assert [k for k, v in held.items() if not v] == ['no_broad_grants', 'mailbox']


def test_a_granted_path_inside_core_state_reaches_nothing_of_it(tmp_path, sdk, gate):
    h = make(tmp_path, sdk)
    req = request(tmp_path)
    identity = h.boundary.create_profile(req.execution_id)
    h.boundary.grant_established(req.workspace, identity['sid'], 'rw')
    assert h.boundary.granted_to(os.path.dirname(req.workspace), identity['sid']) is False
    assert h.boundary.granted_to(os.path.join(req.workspace, 'a', 'b'),
                                 identity['sid']) is True
    assert h.boundary.granted_to(req.workspace, 'psec:never-reserved') is True


def test_the_job_condition_reads_the_existing_job_code(tmp_path, sdk, gate):
    h = make(tmp_path, sdk)
    h.jobs.job_inheritable = True
    req = request(tmp_path)
    held, _ = conditions(h, req)
    assert [k for k, v in held.items() if not v] == ['job']


def test_no_capability_is_ever_granted():
    assert MxcBoundary().capability_grants() == ()


# ── the Job and the handles are the existing code, called through ──

@pytest.mark.parametrize('name, args', [
    ('create_job', ('exe_1',)), ('job_facts', ('job',)),
    ('job_active_processes', ('job',)), ('assign_job', ('job', 'process')),
    ('terminate_job', ('job',)), ('close_job', ('job',)), ('process_started', (7,)),
    ('open_inherited', ('p', 'read')), ('close_handle', ('h',)),
    ('broad_write_grant', ('p', 'psec:x'))])
def test_the_job_and_handle_calls_go_to_the_win32_code_untouched(name, args):
    calls = []

    class Spy:
        def __getattr__(self, attr):
            return lambda *a: calls.append((attr, a)) or attr

    boundary = MxcBoundary(jobs=Spy())
    answer = getattr(boundary, name)(*args)
    want = 'broad_writer' if name == 'broad_write_grant' else name
    assert answer == want
    assert calls == [(want, args[:1] if name == 'broad_write_grant' else args)]


def test_the_default_job_code_is_the_windows_boundary_or_nothing():
    jobs = MxcBoundary().jobs
    assert type(jobs) is (iso.WindowsBoundary if iso.WINDOWS else iso.UnavailableBoundary)


# ── the launch ──

class Made:
    """`local.MxcLaunch`, recorded: what the boundary builds, and nothing started."""
    made = []

    def __init__(self, **kw):
        self.kw = kw
        Made.made.append(self)

    def start(self, *, job):
        self.job = job
        return self


@pytest.fixture
def launched(tmp_path, sdk, monkeypatch):
    Made.made = []
    monkeypatch.setattr(local, 'MxcLaunch', Made)
    h = make(tmp_path, sdk)
    req = request(tmp_path)
    identity = h.boundary.create_profile(req.execution_id)
    for g in req.grants:
        assert h.boundary.grant_established(g.path, identity['sid'], g.access)

    def go(**over):
        kw = dict(argv=['agent.exe', 'two words'], cwd=req.workspace, env={'A': '1'},
                  profile=identity['profile'], job={'job': 1}, stdin=None, stdout=None)
        kw.update(over)
        return h.boundary.launch(kw.pop('argv'), **kw)

    return SimpleNamespace(h=h, req=req, go=go, made=Made.made, identity=identity)


def test_a_launch_is_one_policy_over_exactly_the_verified_grants(launched):
    child = launched.go()
    kw = child.kw
    rows = {g.row: os.path.normpath(g.path) for g in launched.req.grants}
    assert kw['workspace'] == rows['workspace'] and kw['cwd'] == launched.req.workspace
    assert sorted(kw['writable']) == sorted([rows['request'], rows['state']])
    assert sorted(kw['readonly']) == sorted([rows['runtime'], rows['hook'], rows['response'],
                                              rows['sentinel']])
    assert child.job == {'job': 1}
    assert kw['command_line'] == subprocess.list2cmdline(['agent.exe', 'two words'])


def test_the_launch_is_built_from_the_native_parts_and_nothing_else(launched):
    kw = launched.go().kw
    h = launched.h
    assert kw['api'] is h.api and kw['boundary'] is h.boundary and kw['ledger'] is h.ledger
    assert kw['sdk_root'] == h.boundary.sdk_root and kw['pins'] == h.boundary.pins
    assert kw['schema_validator'] is h.boundary.schema_validator
    assert kw['execution_id'] == launched.req.execution_id and 'backend' not in kw
    assert kw['timeout_ms'] == 5000


def test_a_resume_is_the_next_process_generation(launched):
    assert launched.go().kw['process_seq'] == 1
    seed_journal(launched.h, mxc_ledger.journal_name(launched.req.execution_id, 1), 'intent',
             'ownership', 'disposal', 'completion')
    assert launched.go().kw['process_seq'] == 2


def test_the_environment_gains_the_boundarys_rows_without_a_second_spelling(launched):
    assert launched.go(env={'A': '1'}).kw['env'] == {'A': '1', 'SYSTEMROOT': 'C:\\Windows'}
    assert launched.go(env={'SystemRoot': 'D:\\W'}).kw['env'] == {'SystemRoot': 'D:\\W'}


def test_a_working_directory_that_is_not_a_writable_grant_is_refused(launched):
    runtime = launched.req.grant_for('runtime').path
    for cwd in (runtime, os.path.join(launched.req.workspace, 'sub'), launched.req.mailbox + 'x'):
        with pytest.raises(iso.IsolationUnavailable, match='mxc_policy'):
            launched.go(cwd=cwd)
    assert launched.made == []


def test_a_profile_that_was_never_reserved_is_refused(launched):
    with pytest.raises(iso.IsolationUnavailable, match='profile_unknown'):
        launched.go(profile=iso.profile_name(new_execution_id()))
    assert launched.made == []


def test_a_launch_without_a_deadline_is_refused(launched):
    launched.h.boundary.timeout_ms = None
    with pytest.raises(iso.IsolationUnavailable, match='mxc_timeout'):
        launched.go()
    assert launched.made == []


def test_the_same_path_twice_is_one_grant(launched):
    again = launched.req.grant_for('runtime').path
    launched.h.boundary.grant_established(again, launched.identity['sid'], 'rx')
    launched.h.boundary.grant_established(launched.req.workspace, launched.identity['sid'], 'rw')
    kw = launched.go().kw
    assert len(kw['readonly']) == len(set(kw['readonly']))
    assert kw['workspace'] not in kw['writable']


@pytest.mark.parametrize('name', ['broker', 'resource_reader', 'readback', 'watchdog'])
def test_the_ending_parts_reach_the_launch(tmp_path, sdk, monkeypatch, name):
    Made.made = []
    monkeypatch.setattr(local, 'MxcLaunch', Made)
    mark = object()
    h = make(tmp_path, sdk, **{name: mark})
    req = request(tmp_path)
    identity = h.boundary.create_profile(req.execution_id)
    h.boundary.grant_established(req.workspace, identity['sid'], 'rw')
    child = h.boundary.launch(['a.exe'], cwd=req.workspace, env={}, profile=identity['profile'],
                              job=None, stdin=None, stdout=None)
    assert child.kw[name] is mark


def test_the_default_outcome_is_the_launchers_exit_and_nothing_a_stream_said():
    assert mxc_boundary.launcher_exit(SimpleNamespace(launcher_exit=7, stdout=b'0')) == 7
    assert MxcBoundary().outcome is mxc_boundary.launcher_exit


# ── MxcLaunch takes more writable grants than the workspace ──

class Compiler:
    """A backend that only compiles: the launch under test is never started."""
    compile_policy = staticmethod(mxc.compile_policy)


def a_launch(tmp_path, sdk, **over):
    work = tmp_path / 'work'
    work.mkdir(exist_ok=True)
    args = dict(backend=Compiler(), sdk_root=sdk[0], pins=sdk[1], outcome=lambda p: 0,
                workspace=str(work), cwd=str(work), command_line='agent.exe', timeout_ms=1000,
                env={'SYSTEMROOT': 'C:\\Windows', 'LOCALAPPDATA': str(work)})
    args.update(over)
    return local.MxcLaunch(**args)


def test_extra_writable_grants_join_the_workspace_in_the_policy(tmp_path, sdk):
    extra = tmp_path / 'mailbox'
    extra.mkdir()
    fs = a_launch(tmp_path, sdk, writable=[str(extra)]).policy.raw['filesystem']
    assert fs['readwritePaths'] == [os.path.normpath(tmp_path / 'work'), os.path.normpath(extra)]


def test_with_no_extra_grant_the_workspace_is_the_one_writable_path(tmp_path, sdk):
    fs = a_launch(tmp_path, sdk).policy.raw['filesystem']
    assert fs['readwritePaths'] == [os.path.normpath(tmp_path / 'work')]


def test_a_second_name_in_an_extra_writable_grant_is_refused_at_construction(tmp_path, sdk):
    extra = tmp_path / 'mailbox'
    extra.mkdir()
    (extra / 'one.txt').write_bytes(b'x')
    os.link(extra / 'one.txt', extra / 'two.txt')
    with pytest.raises(staging.StageError, match='multiple links in grant'):
        a_launch(tmp_path, sdk, writable=[str(extra)])


def test_an_extra_writable_grant_that_is_not_there_is_refused(tmp_path, sdk):
    with pytest.raises(staging.StageError, match='hardlink scan failed'):
        a_launch(tmp_path, sdk, writable=[str(tmp_path / 'absent')])

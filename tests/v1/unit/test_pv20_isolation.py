"""PV-20 S1 — the isolated execution path, synthetic acceptance (pv20-execution-
isolation-design §3.1-§3.4, §3.7-§3.8; S1 gate §4/§7).

These tests run on every platform against a *synthetic* boundary (`FakeBoundary`): a
fake that answers the OS questions Core asks, so the nine authorized S1 items are
exercised for their contract without touching AppContainer/Job Win32 calls. The real
mechanism and C6's full sole-holder property are accepted on Windows only, in
`tests/v1/integration/test_pv20_isolation_windows.py`.

The nine items map to the classes below; the C6 sole-holder evidence lives in the
Windows file, not here (a fake cannot establish sole holding -- that is the point).
"""

import ast
import ctypes
import json
import os
import re
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest

from archeus.core.application import executions as X
from archeus.core.domain import ids
from archeus.core.execution import manager as M
from archeus.harnesses import base
from archeus.infra.paths import (ExecPaths, VerifyPaths, isolation_dir, isolation_state,
                                  quarantine_log, run_dir, verify_consumed)
from archeus.node import isolation as iso
from archeus.node.local import LocalNode

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def _staged_hook(tmp_path):
    """The hook command Core hands `default_plan` (C4b): a real stage, built from a
    synthetic runtime tree, so no installed runtime is ever read or copied."""
    from archeus.infra import paths
    from archeus.node import staging
    src = tmp_path / 'synthetic-py'
    for rel in ('python.exe', 'python310.dll', 'Lib/os.py'):
        p = src / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b'synthetic')
    hook = tmp_path / 'synthetic-hook' / 'hook.py'
    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.write_bytes(b'# the hook')
    os.makedirs(paths.archeus_home(), exist_ok=True)
    stage = staging.stage(str(src), str(hook), version=(3, 10))
    return os.path.join(stage, 'python.exe'), '-I', os.path.join(stage, 'hook.py')

#: an ACL-changing program, however it is spelled on a command line
ACL_TOOL = re.compile(r'(?i)(?:^|[\s\\/"\'])(?:i?cacls|takeown)(?:\.exe)?(?:$|[\s"\'])|set-acl')


# ── the lowest mutation boundary, armed for every test in this file ───────────

@pytest.fixture(autouse=True)
def os_tripwire(monkeypatch):
    """No test here may reach the OS's own mutation primitives — an ACL tool started
    as a process, the real AppContainer profile APIs, process creation, a Job, a handle's
    flags — nor a real security-descriptor, SID or process read: the grant readers, the
    launch and the process probe are tested over synthetic answers. Each fails the
    test where it happens, and the fixture fails it again at teardown in case something
    on the way swallowed the first failure (`IsolationContext.launch` catches broadly)."""
    hits = []
    popen, system = subprocess.Popen, os.system

    def guarded_popen(args, *a, **k):
        argv = [args] if isinstance(args, (str, bytes)) else list(args)
        if any(ACL_TOOL.search(os.fsdecode(x) if isinstance(x, bytes) else str(x)) for x in argv):
            hits.append(argv)
            raise AssertionError('an ACL tool was started: %r' % (argv,))
        return popen(args, *a, **k)

    def guarded_system(cmd):
        if ACL_TOOL.search(str(cmd)):
            hits.append(cmd)
            raise AssertionError('an ACL tool was started: %r' % (cmd,))
        return system(cmd)

    monkeypatch.setattr(subprocess, 'Popen', guarded_popen)
    monkeypatch.setattr(os, 'system', guarded_system)
    for name in ('_CreateAppContainerProfile', '_DeleteAppContainerProfile',
                 '_GetSecurityInfoByNameW', '_GetAclInformation', '_GetAce',
                 '_ConvertSidToStringSidW', '_OpenProcess', '_GetExitCodeProcess',
                 '_GetProcessTimes', '_DeriveAppContainerSidFromAppContainerName',
                 '_CreateProcessW', '_ResumeThread', '_TerminateProcess',
                 '_AssignProcessToJobObject', '_CreateJobObjectW', '_SetInformationJobObject',
                 '_InitializeProcThreadAttributeList', '_UpdateProcThreadAttribute',
                 '_DeleteProcThreadAttributeList', '_SetHandleInformation',
                 '_GetHandleInformation', '_CreateFileW', '_CloseHandle',
                 '_QueryInformationJobObject'):
        def trip(*a, _name=name):
            hits.append((_name, a))
            raise AssertionError('the real %s was reached' % _name)
        monkeypatch.setattr(iso, name, trip, raising=False)
    yield hits
    assert hits == [], 'a real mutation primitive was reached: %r' % (hits,)


# ── the synthetic boundary: answers Core's OS questions, decides nothing ───────

class FakeChild:
    """Stands in for the launched process (`IsolatedProcess`'s public shape)."""

    def __init__(self, pid=424242):
        self.pid = pid
        self.returncode = None
        self.waits = []

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        self.waits.append(timeout)
        return self.returncode

    def kill(self):
        self.returncode = 1


def _stable_sid(name):
    return 'S-1-15-3-9-' + str(abs(hash(str(name))) % (10 ** 8))


class FakeBoundary:
    """A boundary whose every answer is a knob, so each §3.4 condition can be flipped
    to fail closed independently while the others stay satisfied. It never *launches* a
    real process; it records what it was asked to launch."""
    id = 'fake'

    def __init__(self):
        self.available_ok = True
        self.grant_ok = True
        self.broad = None                 # a broad principal holding write, or None
        self.core_state_granted = False   # is Core's own state granted to the exec?
        self.caps = ()                    # capability SIDs found (must be empty)
        self.job_named = False
        self.job_name_unknown = False     # the Job's name could not be read
        self.job_inheritable = False
        self.presence_fail = False        # the profile's state could not be read
        self.job_type = 'Job'
        self.create_fail = None           # reason to raise on create_profile
        self.delete_fail = set()          # profile names whose delete fails
        self.delete_leaves = set()        # profile names a delete reports gone and leaves
        self.looked = []                  # every presence read
        self.processes = {}               # pid -> creation time of what runs under it now
        self.process_unreadable = False   # what runs under a PID cannot be read
        self.probed = []                  # every process read
        self.launch_ok = True
        self.launch_calls = []
        self.profiles = set()             # the profiles that exist, as the OS would say
        self.created = []
        self.deleted = []
        self.closed = []
        self.assigned = []
        #: the Job's active-process count, one answer per read (K3); an exception
        #: instance is raised; the last answer repeats
        self.active = [0]
        self.order = []                   # the fence's reads and the closes, in order

    def available(self):
        return self.available_ok

    # the profile operations take an execution id and derive the name exactly as the
    # real boundary does, so a malformed id is refused before anything is recorded
    def create_profile(self, execution_id):
        name = iso.validated_profile(execution_id)
        if self.create_fail:
            raise iso.IsolationUnavailable(self.create_fail, 'synthetic')
        existed = name in self.profiles
        self.profiles.add(name)
        self.created.append(name)
        return {'profile': name, 'sid': _stable_sid(name), 'created': True,
                'existed': existed, 'package_dir': 'materialized'}

    def delete_profile(self, execution_id):
        name = iso.validated_profile(execution_id)
        self.deleted.append(name)
        if name in self.delete_fail:
            raise iso.IsolationUnavailable('profile_delete', 'in use (synthetic)')
        if name not in self.delete_leaves:
            self.profiles.discard(name)

    def profile_exists(self, execution_id):
        self.looked.append(iso.profile_name(execution_id))
        if self.presence_fail:
            raise iso.IsolationUnavailable('profile_state', 'unreadable (synthetic)')
        return iso.profile_name(execution_id) in self.profiles

    def process_started(self, pid):
        self.probed.append(pid)
        if self.process_unreadable:
            raise iso.IsolationUnavailable('process_state', 'unreadable (synthetic)')
        return self.processes.get(pid)

    def mutations(self):
        """Every call that would change OS state: the profile store, a Job, a process."""
        return self.created + self.deleted + self.assigned + self.launch_calls

    def derive_sid(self, execution_id):
        return _stable_sid(iso.profile_name(execution_id))

    def derive(self, execution_id):
        return self.derive_sid(execution_id)

    def grant_established(self, path, sid, access):
        return bool(self.grant_ok)

    def broad_write_grant(self, path, sid):
        return self.broad

    def granted_to(self, path, sid):
        return bool(self.core_state_granted) and 'core_state' in str(path)

    def capability_grants(self):
        return tuple(self.caps)

    def create_job(self, execution_id):
        return {'job': execution_id}

    def job_facts(self, handle):
        if handle is None:
            return None
        name = None if self.job_name_unknown else 'synthetic-job' if self.job_named else ''
        return {'type': self.job_type, 'name': name, 'inheritable': self.job_inheritable}

    def assign_job(self, job, process_handle):
        self.assigned.append((job, process_handle))

    def close_job(self, job):
        self.closed.append(job)
        self.order.append('close')

    def job_active_processes(self, job):
        self.order.append('query')
        n = self.active.pop(0) if len(self.active) > 1 else self.active[0]
        if isinstance(n, Exception):
            raise n
        return n

    def close_handle(self, handle):
        pass

    def open_inherited(self, path, mode):
        return {'stdio': path, 'mode': mode}

    def launch(self, argv, *, cwd, env, profile, job, stdin, stdout):
        self.launch_calls.append({'argv': argv, 'cwd': cwd, 'env': env, 'profile': profile,
                                  'job': job, 'stdin': stdin, 'stdout': stdout})
        if not self.launch_ok:
            raise iso.IsolationUnavailable('launch', 'synthetic')
        return FakeChild()


class FakeNode:
    id = 'fake-node'

    def __init__(self):
        self.registry = []
        self.kills = []

    def _registry(self, line):
        self.registry.append(line)

    def alive(self, handle):
        return True

    def kill(self, adapter, handle):
        self.kills.append((adapter, handle))
        return 'killed'


def new_execution_id():
    return ids.new_id('execution')


def make_satisfying_request(execution_id, root):
    """An §3.1 inventory a synthetic fixture can satisfy but production cannot: every
    required row present on a real directory, the broker present, the class 1, 2 and 3
    directories separated, and Core's own state kept outside the boundary."""
    def d(name):
        p = os.path.join(root, name)
        os.makedirs(p, exist_ok=True)
        return p
    workspace = d('workspace')
    runtime = d('runtime')
    hook = d('hook')
    mailbox = d('mailbox')
    response = d('response')
    sentinel = d('sentinel')
    state = d('state')
    core_state = d('core_state')
    broker = d('broker')
    spawn_config = os.path.join(response, 'spawn_config.json')
    with open(spawn_config, 'w', encoding='utf-8') as f:
        json.dump({'argv': []}, f)
    grants = (iso.Grant(workspace, 'rw', 'workspace'),
              iso.Grant(runtime, 'rx', 'runtime'),
              iso.Grant(hook, 'rx', 'hook'),
              iso.Grant(mailbox, 'rw', 'request'),
              iso.Grant(response, 'rx', 'response'),
              iso.Grant(sentinel, 'rx', 'sentinel'),
              iso.Grant(state, 'rw', 'state'))
    return iso.IsolationRequest(execution_id=execution_id, workspace=workspace,
                                grants=grants, mailbox=mailbox, response=response,
                                sentinel=sentinel, spawn_config=spawn_config,
                                state_dir=state, core_state=core_state, broker=broker)


def authority(tmp_path, *, boundary=None, authorize=None, plan=None, request=None):
    """An `Isolation` authority wired to a fake boundary and a satisfying plan."""
    node = FakeNode()
    b = boundary or FakeBoundary()
    req = request or make_satisfying_request(new_execution_id(), str(tmp_path))
    plan = plan or (lambda spec: req)
    a = iso.Isolation(node, boundary=b, authorize=authorize, plan=plan)
    return a, b, req, node


# ── item 1 + R7: per-execution identity, reused by resumes, never shared ──────

class TestIdentity:
    def test_profile_is_per_execution_and_rederivable(self):
        p1 = iso.profile_name('exe_A')
        p2 = iso.profile_name('exe_B')
        assert p1 != p2
        assert p1 == iso.profile_name('exe_A')          # re-derivable: resume reuses it
        assert p1.startswith(iso.PROFILE_PREFIX)

    def test_resume_reuses_the_established_identity(self, tmp_path):
        a, b, req, _ = authority(tmp_path)
        rec = a.establish(req)
        # once a record exists, the execution is isolated and its identity is its own
        assert a.requested(req.execution_id) is True
        assert a.record(req.execution_id).sid == rec.sid
        # a second execution gets a different identity, never this one
        req2 = make_satisfying_request(new_execution_id(), str(tmp_path))
        assert a.establish(req2).sid != rec.sid

    def test_two_executions_never_share_a_principal(self, tmp_path):
        a, b, _, _ = authority(tmp_path)
        sids = {a.establish(make_satisfying_request(new_execution_id(), str(tmp_path))).sid
                for _ in range(2)}
        assert len(sids) == 2


# ── item 9: zero network capability ───────────────────────────────────────────

class TestZeroCapability:
    def test_no_capabilities_are_granted(self, tmp_path):
        a, b, req, _ = authority(tmp_path)
        assert iso.CAPABILITIES == ()
        rec = a.establish(req)
        assert tuple(rec.capabilities) == ()
        assert b.capability_grants() == ()

    def test_no_network_capability_sid_present(self, tmp_path):
        a, b, req, _ = authority(tmp_path)
        rec = a.establish(req)
        assert not (set(rec.capabilities) & set(iso.NETWORK_CAPABILITY_SIDS))


# ── item 7 + the §3.4 invariant: each condition fails closed on its own ───────

class TestInvariantFailClosed:
    def _api(self, boundary):
        return boundary

    def test_all_six_hold_when_satisfied(self, tmp_path):
        a, b, req, _ = authority(tmp_path)
        conds = iso.check_invariant(b, req, {'created': True, 'sid': b.derive_sid(req.execution_id)},
                                    {'type': 'Job', 'name': '', 'inheritable':False})
        assert iso.unmet_conditions(conds) == ()
        assert set(conds) == set(iso.CONDITIONS)

    def test_condition_1_identity_fails_closed(self, tmp_path):
        a, b, req, _ = authority(tmp_path)
        conds = iso.check_invariant(b, req, {'created': True, 'sid': 'S-1-15-3-9-wrong'},
                                    {'type': 'Job', 'name': '', 'inheritable':False})
        assert iso.unmet_conditions(conds) == ('identity',)

    def test_condition_2_grants_missing_row(self, tmp_path):
        a, b, req, _ = authority(tmp_path)
        broken = iso.IsolationRequest(**{**req.__dict__, 'grants': req.grants[:-1]})
        conds = iso.check_invariant(b, broken, {'created': True, 'sid': b.derive_sid(req.execution_id)},
                                    {'type': 'Job', 'name': '', 'inheritable':False})
        assert 'grants' in iso.unmet_conditions(conds)

    def test_condition_3_no_broad_grants(self, tmp_path):
        a, b, req, _ = authority(tmp_path)
        b.broad = 'S-1-1-0'
        conds = iso.check_invariant(b, req, {'created': True, 'sid': b.derive_sid(req.execution_id)},
                                    {'type': 'Job', 'name': '', 'inheritable':False})
        assert iso.unmet_conditions(conds) == ('no_broad_grants',)

    def test_condition_4_named_job_fails(self, tmp_path):
        a, b, req, _ = authority(tmp_path)
        conds = iso.check_invariant(b, req, {'created': True, 'sid': b.derive_sid(req.execution_id)},
                                    {'type': 'Job', 'name': 'shared', 'inheritable': False})
        assert iso.unmet_conditions(conds) == ('job',)

    def test_condition_4_inheritable_job_fails(self, tmp_path):
        a, b, req, _ = authority(tmp_path)
        conds = iso.check_invariant(b, req, {'created': True, 'sid': b.derive_sid(req.execution_id)},
                                    {'type': 'Job', 'name': '', 'inheritable':True})
        assert iso.unmet_conditions(conds) == ('job',)

    def test_condition_5_mailbox_missing(self, tmp_path):
        a, b, req, _ = authority(tmp_path)
        broken = iso.IsolationRequest(**{**req.__dict__, 'spawn_config': ''})
        conds = iso.check_invariant(b, broken, {'created': True, 'sid': b.derive_sid(req.execution_id)},
                                    {'type': 'Job', 'name': '', 'inheritable':False})
        assert 'mailbox' in iso.unmet_conditions(conds)

    def test_condition_6_boundary_unavailable(self, tmp_path):
        a, b, req, _ = authority(tmp_path)
        b.available_ok = False
        conds = iso.check_invariant(b, req, {'created': True, 'sid': b.derive_sid(req.execution_id)},
                                    {'type': 'Job', 'name': '', 'inheritable':False})
        assert 'isolated_path' in iso.unmet_conditions(conds)

    def test_core_state_granted_fails_condition_3(self, tmp_path):
        a, b, req, _ = authority(tmp_path)
        b.core_state_granted = True
        conds = iso.check_invariant(b, req, {'created': True, 'sid': b.derive_sid(req.execution_id)},
                                    {'type': 'Job', 'name': '', 'inheritable':False})
        assert 'no_broad_grants' in iso.unmet_conditions(conds)

    def test_capability_sid_present_fails_condition_3(self, tmp_path):
        a, b, req, _ = authority(tmp_path)
        b.caps = ('S-1-15-3-1',)                  # internetClientServer would reach network
        conds = iso.check_invariant(b, req, {'created': True, 'sid': b.derive_sid(req.execution_id)},
                                    {'type': 'Job', 'name': '', 'inheritable':False})
        assert 'no_broad_grants' in iso.unmet_conditions(conds)


# ── §7.5 (S2-L): each mailbox class is its own directory, with its own access ──
# What these show is the plan and the invariant over a fake boundary; that the OS
# keeps an execution to its classes is Windows evidence, not this.

def _conds(b, req):
    return iso.check_invariant(b, req, {'created': True, 'sid': b.derive_sid(req.execution_id)},
                               {'type': 'Job', 'name': '', 'inheritable': False})


def _moved(req, **where):
    """*req* with class directories moved and the grants naming them moved with them,
    so the only thing that changes is where a class is."""
    rows = {'mailbox': 'request', 'response': 'response', 'sentinel': 'sentinel'}
    to = {rows[k]: v for k, v in where.items() if k in rows}
    grants = tuple(iso.Grant(to[g.row], g.access, g.row) if g.row in to else g
                   for g in req.grants)
    return iso.IsolationRequest(**{**req.__dict__, **where, 'grants': grants})


class TestClassSeparation:
    def test_each_class_carries_its_own_access_and_no_other(self, tmp_path):
        a, b, req, _ = authority(tmp_path)
        for row, wrong in (('request', 'rx'), ('response', 'rw'), ('sentinel', 'rw')):
            grants = tuple(iso.Grant(g.path, wrong, g.row) if g.row == row else g
                           for g in req.grants)
            conds = _conds(b, iso.IsolationRequest(**{**req.__dict__, 'grants': grants}))
            assert iso.unmet_conditions(conds) == ('grants',), row

    def test_a_class_granted_at_another_classs_directory_fails_closed(self, tmp_path):
        a, b, req, _ = authority(tmp_path)
        grants = tuple(iso.Grant(req.mailbox, g.access, g.row) if g.row == 'response' else g
                       for g in req.grants)
        conds = _conds(b, iso.IsolationRequest(**{**req.__dict__, 'grants': grants}))
        assert iso.unmet_conditions(conds) == ('grants',)

    def test_requests_and_answers_in_one_directory_fail_closed(self, tmp_path):
        a, b, req, _ = authority(tmp_path)
        config = os.path.join(req.mailbox, 'spawn_config.json')
        open(config, 'w').close()
        merged = _moved(req, response=req.mailbox, spawn_config=config)
        assert iso.unmet_conditions(_conds(b, merged)) == ('mailbox',)

    def test_a_class_inside_another_fails_closed(self, tmp_path):
        a, b, req, _ = authority(tmp_path)
        inner = os.path.join(req.mailbox, 'ctl')
        os.makedirs(inner)
        assert iso.unmet_conditions(_conds(b, _moved(req, sentinel=inner))) == ('mailbox',)

    @pytest.mark.parametrize('where', ['mailbox', 'core_state'])
    def test_a_spawn_configuration_outside_class_2_fails_closed(self, tmp_path, where):
        a, b, req, _ = authority(tmp_path)
        config = os.path.join(getattr(req, where), 'spawn_config.json')
        open(config, 'w').close()
        moved = iso.IsolationRequest(**{**req.__dict__, 'spawn_config': config})
        assert iso.unmet_conditions(_conds(b, moved)) == ('mailbox',)

    def test_a_workspace_that_is_cores_own_directory_fails_closed(self, tmp_path):
        # a project-less execution's workspace used to be its whole directory
        a, b, req, _ = authority(tmp_path)
        own = iso.IsolationRequest(**{**req.__dict__, 'core_only': (req.workspace,)})
        assert iso.unmet_conditions(_conds(b, own)) == ('no_broad_grants',)

    def test_a_class_that_is_cores_own_directory_fails_closed(self, tmp_path):
        a, b, req, _ = authority(tmp_path)
        own = iso.IsolationRequest(**{**req.__dict__, 'core_only': (req.mailbox,)})
        assert iso.unmet_conditions(_conds(b, own)) == ('no_broad_grants', 'mailbox')

    @pytest.mark.parametrize('field,row', [('workspace', 'workspace'), ('state_dir', 'state')])
    @pytest.mark.parametrize('shape', ['is_class_1', 'inside_class_2', 'holds_class_3'])
    def test_class_7_is_no_mailbox_class_and_neither_holds_nor_lies_in_one(
            self, tmp_path, field, row, shape):
        a, b, req, _ = authority(tmp_path)
        if shape == 'holds_class_3':
            inner = os.path.join(getattr(req, field), 'ctl')
            os.makedirs(inner)
            bad = _moved(req, sentinel=inner)
        else:
            where = req.mailbox if shape == 'is_class_1' else os.path.join(req.response, 'own')
            os.makedirs(where, exist_ok=True)
            grants = tuple(iso.Grant(where, g.access, g.row) if g.row == row else g
                           for g in req.grants)
            bad = iso.IsolationRequest(**{**req.__dict__, field: where, 'grants': grants})
        assert iso.unmet_conditions(_conds(b, bad)) == ('mailbox',)

    @pytest.mark.parametrize('nested', [False, True])
    def test_the_workspace_may_hold_its_own_state(self, tmp_path, nested):
        a, b, req, _ = authority(tmp_path)
        state = os.path.join(req.workspace, 'state') if nested else req.workspace
        os.makedirs(state, exist_ok=True)
        grants = tuple(iso.Grant(state, g.access, g.row) if g.row == 'state' else g
                       for g in req.grants)
        together = iso.IsolationRequest(**{**req.__dict__, 'state_dir': state,
                                           'grants': grants})
        assert iso.unmet_conditions(_conds(b, together)) == ()

    def test_the_production_plan_puts_each_class_in_its_own_directory(self, tmp_path,
                                                                      monkeypatch):
        monkeypatch.setenv('ARCHEUS_HOME', str(tmp_path))
        spec = base.ExecutionSpec(execution_id=new_execution_id(), prompt='go',
                                  workdir=str(tmp_path), hook_settings=_staged_hook(tmp_path))
        req = iso.default_plan(spec)
        p = ExecPaths(spec.execution_id)
        assert (req.mailbox, req.response, req.sentinel) == (p.req, p.res, p.ctl)
        assert os.path.dirname(req.spawn_config) == p.res
        assert req.core_only == (p.dir,) and req.broker == ''
        assert {g.row: (g.path, g.access) for g in req.grants
                if g.row in ('request', 'response', 'sentinel')} == {
            'request': (p.req, 'rw'), 'response': (p.res, 'rx'), 'sentinel': (p.ctl, 'rx')}

    def test_one_executions_plan_names_nothing_of_anothers(self, tmp_path, monkeypatch):
        monkeypatch.setenv('ARCHEUS_HOME', str(tmp_path))
        hook = _staged_hook(tmp_path)

        def plan():
            return iso.default_plan(base.ExecutionSpec(
                execution_id=new_execution_id(), prompt='go', workdir=str(tmp_path),
                hook_settings=hook))

        def own(r):
            return {r.mailbox, r.response, r.sentinel, r.spawn_config, r.state_dir,
                    *r.core_only}
        a, b = plan(), plan()
        assert not own(a) & own(b)
        assert not any(p.startswith(b.core_only[0]) for p in own(a))


class TestNoBoundaryForTheUnisolated:
    def test_ending_an_execution_that_was_never_isolated_touches_no_boundary(self):
        b = FakeBoundary()
        a = iso.Isolation(FakeNode(), boundary=b)
        assert a.teardown(new_execution_id(), reason='ended') is None
        assert a.reclaim(()) == []
        assert (b.mutations(), b.looked, b.probed, b.closed) == ([], [], [], [])


class TestEstablish:
    def test_unmet_condition_raises_and_records(self, tmp_path):
        b = FakeBoundary()
        a, b, req, node = authority(tmp_path, boundary=b)
        b.broad = 'S-1-5-32-545'
        with pytest.raises(iso.IsolationUnavailable) as ei:
            a.establish(req)
        assert 'no_broad_grants' in ei.value.reason
        rec = a.record(req.execution_id)
        assert rec.state == 'failed'
        assert rec.conditions['no_broad_grants'][0] is False
        # the deterministic, restart-reconcilable line
        assert any(x.get('op') == 'isolation_failed' and
                   x.get('execution_id') == req.execution_id for x in node.registry)

    def test_establish_succeeds_established(self, tmp_path):
        a, b, req, _ = authority(tmp_path)
        rec = a.establish(req)
        assert rec.state == 'established'
        assert a.held_job(req.execution_id) is not None

    def test_create_failure_is_platform_free_unavailable(self, tmp_path):
        b = FakeBoundary()
        a, b, req, _ = authority(tmp_path, boundary=b)
        b.create_fail = 'profile_create'
        with pytest.raises(iso.IsolationUnavailable) as ei:
            a.establish(req)
        assert ei.value.reason == 'profile_create'


# ── item 7: no unisolated fallback (the launcher seam) ────────────────────────

class TestNoFallback:
    def test_isolation_object_selects_isolated_path_only(self, tmp_path, monkeypatch):
        # the detached launcher must never be reachable once isolation rides the spec
        def boom(*a, **k):
            raise AssertionError('unisolated spawn_detached was reached')
        monkeypatch.setattr(base.proc, 'spawn_detached', boom)

        a, b, req, node = authority(tmp_path)

        class Adapter:
            id = 'fake-one'
            test_harness = True

            def start(self, spec):
                return base.spawn(spec, [sys.executable, '-c', 'pass'])[0]

            def resume(self, spec, state):
                return self.start(spec)

        spec = base.ExecutionSpec(execution_id=new_execution_id(), prompt='go',
                                  workdir=str(tmp_path))
        spec = __import__('dataclasses').replace(spec, isolation=a.request_for(spec))
        assert spec.isolation is not None
        handle = Adapter().start(spec)
        assert handle.pid == 424242
        # the explicit environment block reached the launcher (never inherited by luck)
        assert b.launch_calls and b.launch_calls[0]['env'].get('ARCHEUS_EXECUTION_ID') \
            == spec.execution_id

    def test_establishment_failure_is_spawnfailed_not_detached(self, tmp_path, monkeypatch):
        def boom(*a, **k):
            raise AssertionError('unisolated spawn_detached was reached')
        monkeypatch.setattr(base.proc, 'spawn_detached', boom)
        b = FakeBoundary()
        b.available_ok = False                     # the boundary is gone: nothing starts
        a, b, req, _ = authority(tmp_path, boundary=b)

        class Adapter:
            id = 'fake'
            test_harness = True

            def start(self, spec):
                return base.spawn(spec, [sys.executable, '-c', 'pass'])[0]

        spec = base.ExecutionSpec(execution_id=new_execution_id(), prompt='go',
                                  workdir=str(tmp_path))
        spec = __import__('dataclasses').replace(spec, isolation=a.request_for(spec))
        with pytest.raises(base.SpawnFailed) as ei:
            Adapter().start(spec)
        assert 'platform' in str(ei.value)


# ── item 3: process-registry entry is an instrument, not the authority ────────

class TestRegistryEntry:
    def test_registry_line_carries_isolation_facts(self, tmp_path, monkeypatch):
        monkeypatch.setattr(base.proc, 'spawn_detached',
                            lambda *a, **k: (_ for _ in ()).throw(AssertionError('detached!')))
        node = LocalNode()
        a, b, req, _ = authority(tmp_path)
        node.isolation = a

        class Adapter:
            id = 'fake'
            test_harness = True

            def start(self, spec):
                return base.spawn(spec, [sys.executable, '-c', 'pass'])[0]

        spec = base.ExecutionSpec(execution_id=req.execution_id, prompt='go',
                                  workdir=str(tmp_path))
        handle = node.spawn(Adapter(), spec, isolated=True)
        assert handle.pid == 424242
        from archeus.infra.paths import processes_registry
        lines = [json.loads(x) for x in open(processes_registry(), encoding='utf-8')]
        line = next(x for x in lines if x.get('op') == 'spawn'
                    and x['execution_id'] == req.execution_id)
        assert line['isolated'] is True and line['ac_sid'] == a.record(req.execution_id).sid
        assert 'core-held' in line['job']

    def test_node_spawn_takes_no_isolation_decision_of_its_own(self, tmp_path):
        # T-021 D1: the manager's one decision is required; a caller that forgets it
        # fails loudly, and a decision passed in is never re-asked
        node = LocalNode()
        asked = []
        node.isolation = SimpleNamespace(requested=lambda *a: asked.append(a) or True)

        class Adapter:
            id = 'fake'

            def start(self, spec):
                return SimpleNamespace(pid=7, create_time=1.0)

        spec = base.ExecutionSpec(execution_id=new_execution_id(), prompt='go',
                                  workdir=str(tmp_path))
        with pytest.raises(TypeError):
            node.spawn(Adapter(), spec)
        assert node.spawn(Adapter(), spec, isolated=False).pid == 7
        assert asked == []


# ── item 4 + teardown on every end path ───────────────────────────────────────

class TestTeardown:
    def test_teardown_deletes_the_identity_and_revokes_nothing(self, tmp_path):
        # S1 applies no access, so teardown has nothing to revoke: the boundary it
        # talks to has no revoke at all, and the planned rows are not cleanup input
        a, b, req, _ = authority(tmp_path)
        a.establish(req)
        out = a.teardown(req.execution_id, reason='ended')
        assert out['job'] == 'closed' and out['profile'] == 'torn_down'
        assert b.deleted == [iso.profile_name(req.execution_id)]
        assert not hasattr(b, 'revoke')
        assert a.record(req.execution_id) is None      # the record goes with it

    def test_teardown_is_idempotent_and_safe_on_unknown(self, tmp_path):
        a, b, req, _ = authority(tmp_path)
        a.establish(req)
        a.teardown(req.execution_id, reason='ended')
        assert a.teardown(req.execution_id) is None     # already gone: no error
        assert a.teardown(new_execution_id()) is None   # valid id that never existed

    def test_failure_to_delete_quarantines(self, tmp_path):
        b = FakeBoundary()
        a, b, req, _ = authority(tmp_path, boundary=b)
        a.establish(req)
        b.delete_fail.add(iso.profile_name(req.execution_id))
        out = a.teardown(req.execution_id, reason='ended')
        assert out['profile'] == 'quarantined'
        assert req.execution_id in a.quarantined()

    def test_quarantine_is_retried_and_released_on_reclaim(self, tmp_path):
        b = FakeBoundary()
        a, b, req, _ = authority(tmp_path, boundary=b)
        a.establish(req)
        b.delete_fail.add(iso.profile_name(req.execution_id))
        a.teardown(req.execution_id, reason='ended')
        assert req.execution_id in a.quarantined()
        # boot: the OS lets it go this time
        b.delete_fail.clear()
        done = a.reclaim(live_execution_ids=[])
        assert req.execution_id in done
        assert req.execution_id not in a.quarantined()

    def test_quarantined_grant_is_never_reissued(self, tmp_path):
        b = FakeBoundary()
        a, b, req, _ = authority(tmp_path, boundary=b)
        rec = a.establish(req)
        b.delete_fail.add(rec.profile)
        a.teardown(req.execution_id, reason='ended')
        entry = a.quarantined()[req.execution_id]
        # the quarantined ACE names only this execution's own principal
        assert entry['sid'] == rec.sid
        assert entry['sid'] != _stable_sid('some-other-execution')


# ── A6-1 (T-055): a verifier attempt is its own principal, apart from executions ──

_EID, _VID = ids.new_id('execution'), ids.new_id('verification')


def make_verifier_request(key, root):
    """A verifier attempt's whole inventory (A6): the checkout and scratch it writes, the
    staged toolchain it runs, and Core's own state named and kept apart."""
    def d(name):
        p = os.path.join(root, name)
        os.makedirs(p, exist_ok=True)
        return p
    checkout = d('checkout')
    return iso.IsolationRequest(execution_id=key, workspace=checkout,
                                grants=(iso.Grant(checkout, 'rw', 'checkout'),
                                        iso.Grant(d('scratch'), 'rw', 'scratch'),
                                        iso.Grant(d('toolchain'), 'rx', 'toolchain')),
                                core_state=d('core_state'))


def _verify_key(attempt=0, vid=_VID):
    return iso.Principal('verify', vid, attempt).key


class TestVerifierPrincipal:
    def test_an_execution_is_keyed_named_and_recorded_as_before(self):
        p = iso.principal(_EID)
        assert p == iso.Principal('exec', _EID, 0) and p.key == _EID
        assert iso.validated_profile(_EID) == iso.profile_name(_EID) == 'archeus.exec.' + _EID.lower()
        assert isolation_state(_EID) == os.path.join(isolation_dir(), _EID + '.json')

    def test_a_verifier_attempt_has_its_own_key_name_record_and_files(self):
        key = _verify_key(3)
        assert key == 'verify/%s.3' % _VID and iso.principal(key) == iso.Principal('verify', _VID, 3)
        assert iso.validated_profile(key) == 'archeus.verify.%s.3' % _VID.lower()
        assert isolation_state(key) == os.path.join(isolation_dir(), 'verify', _VID + '.3.json')
        v = VerifyPaths(_VID, 3)
        assert v.dir == os.path.join(run_dir(), 'verify', _VID, '3')
        assert v.out == os.path.join(v.dir, 'out.log')
        own = os.path.join(v.dir, 'own')
        assert (v.checkout, v.home, v.tmp, v.config) == tuple(
            os.path.join(own, n) for n in ('checkout', 'home', 'tmp', 'config'))

    @pytest.mark.parametrize('kind,owner,attempt', [
        ('verify', _EID, 0), ('exec', _VID, 0), ('exec', _EID, 1), ('verify', _VID, -1),
        ('verify', _VID, iso.MAX_ATTEMPT), ('verify', _VID, True), ('verify', _VID, '1'),
        ('job', _EID, 0)])
    def test_a_cross_kind_or_malformed_principal_is_refused_at_construction(
            self, kind, owner, attempt):
        with pytest.raises(iso.IsolationUnavailable):
            iso.Principal(kind, owner, attempt)

    @pytest.mark.parametrize('key', [
        'verify/%s.01' % _VID, 'verify/%s.' % _VID, 'verify/%s' % _VID,
        'verify/%s.\u00b2' % _VID, 'verify/%s.0' % _EID, 'verify/../%s.0' % _VID,
        'verify/%s.%d' % (_VID, iso.MAX_ATTEMPT), 'exe_not-an-id'])
    def test_a_malformed_key_names_no_principal_profile_or_record(self, key):
        with pytest.raises(iso.IsolationUnavailable):
            iso.principal(key)
        with pytest.raises(iso.IsolationUnavailable):
            iso.validated_profile(key)
        with pytest.raises(ValueError):
            isolation_state(key)

    @pytest.mark.parametrize('owner,attempt', [(_EID, 0), (_VID, -1), (_VID, '../x')])
    def test_verify_paths_take_only_a_verifier_attempt(self, owner, attempt):
        with pytest.raises(ValueError):
            VerifyPaths(owner, attempt)

    def test_no_name_is_ever_cut_so_no_two_keys_share_one(self):
        # every valid key's name is below the 127-character cut, so the cut never
        # applies and the name keeps the whole key: distinct keys, distinct names
        longest = iso.profile_name(_verify_key(iso.MAX_ATTEMPT - 1))
        assert len(longest) < 127 and len(iso.profile_name(_EID)) < 127
        names = {iso.profile_name(_verify_key(n)) for n in (0, 1, 10, 11, iso.MAX_ATTEMPT - 1)}
        assert len(names) == 5
        same_ulid = 'ver_' + _EID[len('exe_'):]
        assert iso.profile_name(_verify_key(0, same_ulid)) != iso.profile_name(_EID)
        assert iso.is_stale_profile(longest) and iso.is_stale_profile(iso.profile_name(_EID))

    def test_a_verifier_attempt_establishes_with_exactly_its_three_rows(self, tmp_path):
        a, b, req, _ = authority(tmp_path)
        key = _verify_key()
        rec = a.establish(make_verifier_request(key, str(tmp_path / 'v')))
        assert rec.state == 'established' and rec.profile == iso.validated_profile(key)
        assert all(holds for holds, _ in rec.conditions.values())
        assert b.created == [rec.profile]
        # never the parent's identity: another principal, another SID, another Job slot
        exe = a.establish(req)
        assert exe.sid != rec.sid and exe.profile != rec.profile
        assert set(a.held_jobs()) == {key, req.execution_id}
        assert a.held_job(key) != a.held_job(req.execution_id)

    @pytest.mark.parametrize('change', ['no_checkout', 'no_scratch', 'no_toolchain',
                                        'toolchain_rw', 'checkout_rx', 'workspace_elsewhere'])
    def test_a_missing_or_wrongly_granted_row_fails_condition_2(self, tmp_path, change):
        b = FakeBoundary()
        req = make_verifier_request(_verify_key(), str(tmp_path))
        rows = {g.row: g for g in req.grants}
        if change.startswith('no_'):
            rows.pop(change[3:])
        elif change == 'toolchain_rw':
            rows['toolchain'] = iso.Grant(rows['toolchain'].path, 'rw', 'toolchain')
        elif change == 'checkout_rx':
            rows['checkout'] = iso.Grant(rows['checkout'].path, 'rx', 'checkout')
        workspace = (rows['scratch'].path if change == 'workspace_elsewhere'
                     else req.workspace)
        broken = iso.IsolationRequest(**{**req.__dict__, 'grants': tuple(rows.values()),
                                         'workspace': workspace})
        conds = _conds(b, broken)
        assert conds['grants'][0] is False and conds['mailbox'][0] is True

    @pytest.mark.parametrize('change', ['extra_toolchain_rw', 'second_checkout',
                                        'second_scratch', 'same_toolchain_twice'])
    def test_every_grant_is_checked_not_only_the_first_of_its_row(self, tmp_path, change):
        a, b, _, _ = authority(tmp_path)
        req = make_verifier_request(_verify_key(), str(tmp_path / 'v'))
        rows = {g.row: g for g in req.grants}
        other = str(tmp_path / 'other')
        os.makedirs(other)
        extra = {'extra_toolchain_rw': iso.Grant(other, 'rw', 'toolchain'),
                 'second_checkout': iso.Grant(other, 'rw', 'checkout'),
                 'second_scratch': iso.Grant(other, 'rw', 'scratch'),
                 'same_toolchain_twice': rows['toolchain']}[change]
        broken = iso.IsolationRequest(**{**req.__dict__, 'grants': req.grants + (extra,)})
        conds = _conds(b, broken)
        assert conds['grants'][0] is False and conds['mailbox'][0] is True
        # and so the attempt never launches: the invariant refuses it at establishment
        with pytest.raises(iso.IsolationUnavailable) as err:
            a.establish(broken)
        assert err.value.reason.startswith('condition_unmet:') and 'grants' in err.value.reason
        assert b.launch_calls == []

    def test_several_distinct_read_only_toolchains_hold(self, tmp_path):
        b = FakeBoundary()
        req = make_verifier_request(_verify_key(), str(tmp_path))
        more = str(tmp_path / 'toolchain2')
        os.makedirs(more)
        two = iso.IsolationRequest(**{**req.__dict__, 'grants': req.grants + (
            iso.Grant(more, 'rx', 'toolchain'),)})
        assert all(holds for holds, _ in _conds(b, two).values())

    @pytest.mark.parametrize('extra', ['mailbox', 'response', 'sentinel', 'spawn_config',
                                       'broker', 'hook_row', 'request_row', 'no_core_state'])
    def test_an_execution_interface_on_a_verifier_fails_condition_5(self, tmp_path, extra):
        b = FakeBoundary()
        req = make_verifier_request(_verify_key(), str(tmp_path))
        elsewhere = str(tmp_path / 'elsewhere')
        os.makedirs(elsewhere)
        if extra.endswith('_row'):
            change = {'grants': req.grants + (iso.Grant(elsewhere, 'rx', extra[:-4]),)}
        elif extra == 'no_core_state':
            change = {'core_state': ''}
        else:
            change = {extra: elsewhere}
        conds = _conds(b, iso.IsolationRequest(**{**req.__dict__, **change}))
        assert conds['mailbox'][0] is False and conds['grants'][0] is True
        assert _conds(b, req)['mailbox'][0] is True

    def test_an_attempt_starts_once_and_a_retry_is_a_new_principal(self, tmp_path):
        a, b, _, _ = authority(tmp_path)
        key0, key1 = _verify_key(0), _verify_key(1)
        req0 = make_verifier_request(key0, str(tmp_path / 'a0'))
        rec0 = a.establish(req0)
        # re-entry for a running attempt: refused before anything is created or launched
        created = list(b.created)
        with pytest.raises(iso.IsolationUnavailable) as err:
            a.establish(req0)
        assert err.value.reason == 'attempt_consumed'
        assert b.created == created and b.launch_calls == []
        # attempt 0 will not go: quarantined, its record and evidence kept
        b.delete_fail.add(rec0.profile)
        assert a.teardown(key0, reason='ended')['profile'] == 'quarantined'
        assert key0 in a.quarantined()
        out0 = VerifyPaths(_VID, 0).out
        os.makedirs(os.path.dirname(out0))
        with open(out0, 'wb') as f:
            f.write(b'attempt 0 evidence')
        before = {p: open(p, 'rb').read() for p in (isolation_state(key0), quarantine_log(), out0)}
        # the retry is attempt 1: its own key, profile and record; attempt 0 untouched
        rec1 = a.establish(make_verifier_request(key1, str(tmp_path / 'a1')))
        assert rec1.profile == iso.validated_profile(key1) != rec0.profile
        assert os.path.isfile(isolation_state(key1))
        assert {p: open(p, 'rb').read() for p in before} == before
        with pytest.raises(iso.IsolationUnavailable) as err:
            a.establish(req0)
        assert err.value.reason == 'attempt_consumed'

    @pytest.mark.parametrize('route', ['teardown', 'reclaim'])
    def test_a_released_attempt_is_never_started_again_under_any_authority(self, tmp_path, route):
        a, b, _, _ = authority(tmp_path)
        key0, key1 = _verify_key(0), _verify_key(1)
        req0 = make_verifier_request(key0, str(tmp_path / 'a0'))
        rec0 = a.establish(req0)
        out0 = VerifyPaths(_VID, 0).out
        os.makedirs(os.path.dirname(out0))
        with open(out0, 'wb') as f:
            f.write(b'attempt 0 evidence')
        if route == 'teardown':
            assert a.teardown(key0, reason='ended')['profile'] == 'torn_down'
        else:
            assert key0 in a.reclaim(live_execution_ids=[])
        # the release really happened: profile deleted, record gone, marker kept
        assert rec0.profile in b.deleted and not os.path.lexists(isolation_state(key0))
        marker = verify_consumed(key0)
        kept = {p: open(p, 'rb').read() for p in (marker, out0)}
        created = list(b.created)
        with pytest.raises(iso.IsolationUnavailable) as err:
            a.establish(req0)
        assert err.value.reason == 'attempt_consumed'
        # a restarted Core: a new authority over a new boundary, same disk
        a2, b2, _, _ = authority(tmp_path)
        with pytest.raises(iso.IsolationUnavailable) as err:
            a2.establish(req0)
        assert err.value.reason == 'attempt_consumed'
        assert b.created == created and b2.created == [] and b2.launch_calls == []
        assert not os.path.lexists(isolation_state(key0))
        # the next attempt is a new principal and starts; attempt 0's evidence stays
        rec1 = a2.establish(make_verifier_request(key1, str(tmp_path / 'a1')))
        assert rec1.state == 'established' and os.path.isfile(verify_consumed(key1))
        assert {p: open(p, 'rb').read() for p in kept} == kept

    def test_a_record_without_a_marker_is_still_consumed(self, tmp_path):
        a, b, _, _ = authority(tmp_path)
        key = _verify_key()
        path = isolation_state(key)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            f.write('{}')
        with pytest.raises(iso.IsolationUnavailable) as err:
            a.establish(make_verifier_request(key, str(tmp_path / 'v')))
        assert err.value.reason == 'attempt_consumed'
        assert b.created == [] and not os.path.lexists(verify_consumed(key))

    def test_an_attempt_that_cannot_be_marked_is_not_admitted(self, tmp_path, monkeypatch):
        a, b, _, _ = authority(tmp_path)
        key = _verify_key()
        real = open

        def refuse(path, *args, **kw):
            if str(path).endswith('.consumed'):
                raise PermissionError('denied')
            return real(path, *args, **kw)
        monkeypatch.setattr('builtins.open', refuse)
        with pytest.raises(iso.IsolationUnavailable) as err:
            a.establish(make_verifier_request(key, str(tmp_path / 'v')))
        assert err.value.reason == 'attempt_unadmitted'
        assert b.created == [] and not os.path.lexists(isolation_state(key))

    def test_reclaim_sees_both_kinds_and_acts_only_on_derivable_records(self, tmp_path):
        a, b, req, node = authority(tmp_path)
        key = _verify_key(2)
        a.establish(req)
        rec = a.establish(make_verifier_request(key, str(tmp_path / 'v')))
        junk = os.path.join(isolation_dir(), 'verify')
        for name in ('junk.json', _EID + '.0.json', _VID + '.01.json'):
            with open(os.path.join(junk, name), 'w', encoding='utf-8') as f:
                f.write('{}')
        assert sorted(a.stale(live_execution_ids=[key])) == [req.execution_id]
        assert set(a.reclaim(live_execution_ids=[])) == {req.execution_id, key}
        assert rec.profile in b.deleted and iso.profile_name(req.execution_id) in b.deleted
        # the junk is left as found, and the reclaimed attempt keeps only its marker
        assert sorted(os.listdir(junk)) == sorted(
            ['junk.json', _EID + '.0.json', _VID + '.01.json',
             os.path.basename(verify_consumed(key))])
        assert {v for k, v in a.invalid.items() if k.startswith('verify/')} == {
            'not_a_verifier_key'}


# ── Finding 1: the profile-before-record crash window (record-first + recovery) ─

class TestCrashWindow:
    """The identity is created against the OS before the established record exists.
    `establish` persists a *pending* record first, so a hard Core crash in that interval
    leaves evidence; and it records the OS's answer (`owned`) the moment it has one, so
    recovery can tell a profile Core made from one it cannot account for. A pending
    record without that answer is never a reason to delete: the profile is kept (an
    orphan at worst), and only an absent one lets the record go. The crash is simulated
    by raising a plain error (not the caught `IsolationUnavailable`)."""

    def _crash_in_the_window(self, b, *, after_create):
        def crash_create(execution_id):
            if after_create:
                FakeBoundary.create_profile(b, execution_id)   # the OS profile is really made...
            raise RuntimeError('simulated hard Core crash before the established save')
        b.create_profile = crash_create

    # Test A: the OS made the profile, and its answer never reached the record
    def test_crash_after_profile_create_keeps_the_profile(self, tmp_path):
        b = FakeBoundary()
        a, b, req, _ = authority(tmp_path, boundary=b)
        self._crash_in_the_window(b, after_create=True)
        with pytest.raises(RuntimeError):
            a.establish(req)
        # the pending record is the only evidence, and it does not say Core made it
        rec = a.record(req.execution_id)
        assert rec is not None and rec.state == 'pending' and not rec.owned
        assert rec.sid == '' and rec.planned == () and rec.applied == ()
        # a fresh Core cannot tell this profile from one it never made, so it keeps it
        name = iso.profile_name(req.execution_id)
        b2 = FakeBoundary()
        b2.profiles.add(name)                                   # what the OS made
        node2 = FakeNode()
        a2 = iso.Isolation(node2, boundary=b2)
        assert req.execution_id not in a2.reclaim(live_execution_ids=[])
        path = isolation_state(req.execution_id)
        with open(path, 'rb') as f:
            first = f.read()
        for _ in range(3):                                      # later passes change nothing
            assert req.execution_id not in a2.reclaim(live_execution_ids=[])
            assert _sweep(a2) == []
        with open(path, 'rb') as f:
            assert f.read() == first
        kept = a2.record(req.execution_id)
        assert kept.state == 'failed' and kept.reason == 'provenance_unknown'
        assert not kept.owned and kept.sid == b2.derive_sid(req.execution_id)
        assert b2.deleted == [] and name in b2.profiles          # an orphan, never a deletion
        assert [x['op'] for x in node2.registry] == ['isolation_provenance_unknown']
        # once the profile is gone the record is finished with, still with no delete
        b2.profiles.discard(name)
        assert req.execution_id in a2.reclaim(live_execution_ids=[])
        assert a2.record(req.execution_id) is None and b2.deleted == []

    # Test B: pending record but the OS profile was never created -> idempotent no-op
    def test_crash_before_profile_create_recovers_idempotently(self, tmp_path):
        b = FakeBoundary()
        a, b, req, _ = authority(tmp_path, boundary=b)
        self._crash_in_the_window(b, after_create=False)
        with pytest.raises(RuntimeError):
            a.establish(req)
        assert a.record(req.execution_id).state == 'pending'
        b2 = FakeBoundary()
        a2 = iso.Isolation(FakeNode(), boundary=b2)
        out = a2.teardown(req.execution_id, reason='recovered')
        assert out['profile'] == 'torn_down'               # absent: the record is finished
        assert b2.deleted == []                            # and the OS was asked nothing
        assert a2.record(req.execution_id) is None
        assert req.execution_id not in a2.quarantined()    # no false cleanup failure
        assert req.execution_id not in a2.reclaim(live_execution_ids=[])

    # Test C: the answer reached the record, then Core died: recovery deletes what Core
    # made, a delete that fails is quarantined, and the boot retry finishes the job
    def test_crash_after_the_ownership_save_is_recovered(self, tmp_path):
        b = FakeBoundary()
        a, b, req, _ = authority(tmp_path, boundary=b)

        def crash_job(execution_id):
            raise RuntimeError('simulated hard Core crash after the ownership save')

        b.create_job = crash_job
        with pytest.raises(RuntimeError):
            a.establish(req)
        rec = a.record(req.execution_id)
        assert rec.state == 'pending' and rec.owned
        assert rec.sid == b.derive_sid(req.execution_id)
        # a fresh Core whose boot cannot remove the profile must NOT call it cleaned
        name = iso.profile_name(req.execution_id)
        b2 = FakeBoundary()
        b2.profiles.add(name)
        b2.delete_fail.add(name)
        a2 = iso.Isolation(FakeNode(), boundary=b2)
        # reclaim returns what it released; a profile that would not go is not in it
        assert req.execution_id not in a2.reclaim(live_execution_ids=[])
        rec = a2.record(req.execution_id)
        assert rec is not None and rec.state == 'quarantined'   # failure kept, not success
        assert req.execution_id in a2.quarantined()             # and it is retried next boot
        # when the OS finally lets it go, the next boot releases it, once
        b2.delete_fail.clear()
        assert req.execution_id in a2.reclaim(live_execution_ids=[])
        assert a2.record(req.execution_id) is None
        assert req.execution_id not in a2.quarantined()
        assert a2.reclaim(live_execution_ids=[]) == [] and b2.deleted == [name, name]


# ── item 6: restart reconciliation (through the manager pass) ─────────────────

def _manager_with_fake_node():
    m = M.ExecutionManager.__new__(M.ExecutionManager)
    m._procs = {}
    m._noted = set()
    m.node = FakeNode()
    m.calls = []

    def _do(command, **kw):
        m.calls.append((command, kw))

    m._do = _do
    m._reload = lambda e: e
    m._tombstone = lambda e: None
    return m


def _e(state, isolated=True):
    from types import SimpleNamespace
    return SimpleNamespace(id=new_execution_id(), state=state, usage=0, stream_offset=0,
                           isolated=isolated, process_seq=1, seed_revision=None, harness_id='h', pid=None)


class TestRestartReconciliation:
    def _reconcile(self, state, *, iso_state='established', handle=None, adapter=None):
        m = _manager_with_fake_node()
        rec = iso.IsolationRecord(execution_id='x', profile='p', state=iso_state,
                                  reason='condition_unmet:grants' if iso_state == 'failed' else '')
        e = _e(state)
        changed = m._reconcile_isolated(e, adapter or object(), rec, handle, disarmed=False)
        return m, e, changed

    def test_live_isolated_process_is_killed_never_adopted(self):
        adapter, handle = object(), {'pid': 1}
        m, e, changed = self._reconcile('RUNNING', handle=handle, adapter=adapter)
        assert m.node.kills == [(adapter, handle)]
        # no adoption: nothing records a live process
        assert not any(c is X.record_process for c, _ in m.calls)

    def test_pausing_becomes_paused_via_cores_own_halt(self):
        m, e, changed = self._reconcile('PAUSING')
        ended = [k for c, k in m.calls if c is X.record_end]
        assert len(ended) == 1 and ended[0]['core_halt'] is True and ended[0]['isolated']
        assert 'halted' not in ended[0]                  # never the execution's report

    def test_paused_leaves_the_decision_to_the_pass(self):
        m, e, changed = self._reconcile('PAUSED')
        assert changed is False
        assert not any(c is X.record_end for c, _ in m.calls)

    def test_handing_off_ends_killed(self):
        m, e, changed = self._reconcile('HANDING_OFF')
        ended = [(c, k) for c, k in m.calls if c is X.record_end]
        assert ended and ended[0][1]['killed'] is True and ended[0][1]['isolated'] is True

    def test_establishment_failure_is_uncharged_refuse(self):
        m, e, changed = self._reconcile('INTENT', iso_state='failed')
        refused = [(c, k) for c, k in m.calls if c is X.refuse]
        assert refused and refused[0][1]['stop_reason'] == 'binding'

    def test_running_without_handle_is_lost(self):
        m, e, changed = self._reconcile('RUNNING', handle=None)
        assert any(c is X.lost for c, _ in m.calls)

    def test_halted_json_is_never_authority(self, tmp_path, monkeypatch):
        # a forged halted.json claiming the process is paused/halted must not change
        # the record-driven outcome: PAUSING still resolves through Core's own halt
        from archeus.infra.paths import ExecPaths
        eid = new_execution_id()
        paths = ExecPaths(eid)
        os.makedirs(paths.req, exist_ok=True)
        with open(base.halted_path(paths.dir), 'w', encoding='utf-8') as f:
            json.dump({'state': 'HANDLING', 'adopt': True, 'note': 'forged'}, f)
        m = _manager_with_fake_node()
        rec = iso.IsolationRecord(execution_id=eid, profile='p', state='established')
        from types import SimpleNamespace
        e = SimpleNamespace(id=eid, state='PAUSING', usage=0, stream_offset=0)
        m._reconcile_isolated(e, object(), rec, None, disarmed=False)
        ended = [k for c, k in m.calls if c is X.record_end]
        assert ended and ended[0]['core_halt'] is True   # record drove it, not the file
        assert 'halted' not in ended[0]


class TestIsolatedLiveEndRoute:
    """manager._collect (PV-20 §3.3 H2 / A7): which command a live end reaches. For an
    isolated execution only Core's observed exit and kill decide a hand-off."""

    def _collect(self, state, code, *, isolated=True, halted=False, killed=False, field=None,
                 registry_fails=False):
        m = _manager_with_fake_node()
        if registry_fails:
            m.node._registry = _no_registry
        e = SimpleNamespace(id=new_execution_id(), state=state, account_id=None,
                            isolated=field, process_seq=1, seed_revision=None)
        rec = iso.IsolationRecord(execution_id=e.id, profile='p', state='established')
        m.node.isolation_record = lambda eid: rec if isolated else None
        m.node.ended = lambda handle, code, seq: None
        m._tail = m._progress = lambda e, p: None
        m._facts = lambda e, p: {}
        m._release_isolation = lambda e: None
        m.policy = m.missions = m.router = None
        result = base.ExecutionResult(exit_reason='killed' if killed else
                                      ('ok' if code == 0 else 'error'),
                                      exit_code=code, halted=halted)
        adapter = SimpleNamespace(collect_result=lambda handle: result)
        p = {'adapter': adapter, 'handle': object(), 'seq': 1, 'offset': 0, 'usage': 0}
        m._collect(e, p, base.ProcStatus('exited', code))
        return m.calls

    @pytest.mark.parametrize('halted', [False, True])
    def test_an_isolated_handoff_that_exited_0_ends_through_record_handoff(self, halted):
        calls = self._collect('HANDING_OFF', 0, halted=halted)
        assert [c for c, _ in calls] == [X.record_handoff]

    @pytest.mark.parametrize('code,killed', [(1, False), (None, False), (0, True)])
    def test_any_other_isolated_handoff_end_reaches_record_end(self, code, killed):
        calls = self._collect('HANDING_OFF', code, killed=killed, halted=True)
        assert [c for c, _ in calls] == [X.record_end]
        assert calls[0][1]['isolated'] is True and calls[0][1]['killed'] is killed

    def test_an_isolated_pause_without_a_report_reaches_record_end_as_isolated(self):
        calls = self._collect('PAUSING', 0)
        assert [c for c, _ in calls] == [X.record_end] and calls[0][1]['isolated'] is True

    @pytest.mark.parametrize('field', [False, None])
    @pytest.mark.parametrize('code,halted,want', [(0, False, 'record_end'),
                                                  (0, True, 'record_handoff'),
                                                  (1, False, 'record_handoff')])
    def test_an_ordinary_handoff_keeps_its_route(self, code, halted, want, field):
        calls = self._collect('HANDING_OFF', code, isolated=False, halted=halted, field=field)
        assert [c for c, _ in calls] == [getattr(X, want)]
        if want == 'record_end':
            assert calls[0][1]['isolated'] is False

    # T-037 rule 1: the record gone, the row's decision still routes the end
    @pytest.mark.parametrize('code,killed', [(1, False), (None, False), (0, True)])
    def test_a_lost_record_handoff_end_still_reaches_record_end(self, code, killed):
        calls = self._collect('HANDING_OFF', code, isolated=False, field=True, killed=killed,
                              halted=True)
        assert [c for c, _ in calls] == [X.record_end] and calls[0][1]['isolated'] is True

    def test_a_lost_record_clean_handoff_still_hands_off(self):
        calls = self._collect('HANDING_OFF', 0, isolated=False, field=True)
        assert [c for c, _ in calls] == [X.record_handoff]

    def test_a_lost_record_pause_reaches_record_end_as_isolated(self):
        calls = self._collect('PAUSING', 0, isolated=False, field=True)
        assert [c for c, _ in calls] == [X.record_end] and calls[0][1]['isolated'] is True

    # the note is an instrument: a registry that cannot be written changes no end, and by
    # now the handle is already out of _procs, so a raise would turn it into a restart
    @pytest.mark.parametrize('state,code,field,want,isolated', [
        ('HANDING_OFF', 0, True, 'record_handoff', None),
        ('HANDING_OFF', 1, True, 'record_end', True),
        ('RUNNING', 0, True, 'record_end', True),
        ('HANDING_OFF', 0, None, 'record_end', False)])
    def test_a_registry_that_cannot_be_written_never_changes_a_live_end(
            self, caplog, state, code, field, want, isolated):
        calls = self._collect(state, code, isolated=False, field=field, registry_fails=True)
        assert [c for c, _ in calls] == [getattr(X, want)]
        if want == 'record_end':
            assert (calls[0][1]['isolated'], calls[0][1]['exit_code']) == (isolated, code)
        assert 'registry note was not written' in caplog.text


def _no_registry(line):
    raise OSError('the registry cannot be written')


#: the Core Git a known-isolated execution never reaches (T-044)
_CORE_GIT = ('git_branch', 'git_remotes', 'diff_stat', 'end_state')
#: (its isolation record's state or none, the row's decision): known-isolated (T-038)
KNOWN = [('established', True), ('established', None), ('established', False),
         ('invalid', None), (None, True)]


def _git_node(m, allow):
    """Every Core Git call recorded; unless *allow*, the first one fails the test where
    it is made."""
    seen = []
    answers = {'git_branch': 'archeus/m.t1', 'git_remotes': {'origin': 'u'},
               'diff_stat': [' a.py | 1 +'], 'end_state': 'digest'}

    def method(name):
        def call(path):
            seen.append(name)
            if not allow:
                raise AssertionError('Core ran %s in %s' % (name, path))
            return answers[name]
        return call
    for name in _CORE_GIT:
        setattr(m.node, name, method(name))
    return seen


class TestIsolatedFactsWithoutCoreGit:
    """T-044 (K4a): a known-isolated execution - its record present, valid or not, or the
    row's decision True with the record gone - gets no Core Git in its workdir at a live
    end, a restart or a hook, and its diff is stated as not measured, never as empty. A
    row with no record keeps today's Git: legacy None (the owner's L1) and ordinary False."""

    def _m(self, record, field, allow, branch=None):
        m = _manager_with_fake_node()
        git = _git_node(m, allow)
        e = SimpleNamespace(id=new_execution_id(), state='RUNNING', account_id=None,
                            isolated=field, process_seq=1, seed_revision=None, branch=branch, workdir='w',
                            usage=0, stream_offset=0, harness_id='h', pid=None)
        rec = None if record is None else iso.IsolationRecord(execution_id=e.id, profile='p',
                                                              state=record)
        m.node.isolation_record = lambda eid: rec
        return m, e, git

    def _end(self, state, code, record, field, *, killed=False, allow=False):
        m, e, git = self._m(record, field, allow)
        e.state = state
        m.node.ended = lambda handle, code, seq: None
        m._tail = m._progress = lambda e, p: None
        m._release_isolation = lambda e: None
        m.policy = m.missions = m.router = None
        result = base.ExecutionResult(exit_reason='killed' if killed else
                                      ('ok' if code == 0 else 'error'), exit_code=code)
        p = {'adapter': SimpleNamespace(collect_result=lambda handle: result),
             'handle': object(), 'seq': 1, 'offset': 0, 'usage': 0,
             'decisions': ['kept'], 'last_error': 'boom'}
        m._collect(e, p, base.ProcStatus('exited', code))
        ((cmd, kw),) = m.calls
        return cmd, kw, git

    @pytest.mark.parametrize('record,field', KNOWN)
    @pytest.mark.parametrize('state,code,killed,want', [
        ('RUNNING', 0, False, 'record_end'), ('RUNNING', None, True, 'record_end'),
        ('HANDING_OFF', 0, False, 'record_handoff'), ('HANDING_OFF', 1, False, 'record_end'),
        ('PAUSING', 0, False, 'record_end')])
    def test_a_known_isolated_end_runs_no_core_git_and_says_so(self, record, field, state,
                                                               code, killed, want):
        from archeus.core.execution import pressure
        cmd, kw, git = self._end(state, code, record, field, killed=killed)
        assert git == [] and cmd is getattr(X, want)
        assert kw['facts'] == {'files_changed': [M.UNMEASURED], 'decisions': ['kept'],
                               'last_error': 'boom', 'end_state': None}
        if want == 'record_end':
            assert kw['isolated'] is True
        # P1: an unmeasured end is no progress, so a pressure link that hands off again
        # keeps its charged stop
        assert not pressure.progressed(kw['facts']['end_state'], (), [])

    @pytest.mark.parametrize('field', [None, False])
    def test_an_end_without_a_record_keeps_its_git(self, field):
        cmd, kw, git = self._end('RUNNING', 0, None, field, allow=True)
        assert cmd is X.record_end and kw['isolated'] is False
        assert git == ['diff_stat', 'end_state']
        assert (kw['facts']['files_changed'], kw['facts']['end_state']) == (
            [' a.py | 1 +'], 'digest')

    @pytest.mark.parametrize('record,field', KNOWN)
    @pytest.mark.parametrize('state', ['PAUSING', 'STOPPING', 'HANDING_OFF'])
    def test_a_restart_states_the_facts_as_not_measured(self, record, field, state):
        m, e, git = self._m(record, field, allow=False)
        e.state = state
        m.node.files = lambda eid: ({'process_seq': 1}, {'pid': 1, 'create_time': 1.0,
                                                         'process_seq': 1}, None)
        m.node.alive = lambda h: False
        m.registry = SimpleNamespace(get=lambda hid: object())
        assert m._reconcile_one(e, disarmed=False) is True
        ((cmd, kw),) = m.calls
        assert cmd is X.record_end and git == []
        assert kw['facts'] == {'files_changed': [M.UNMEASURED], 'decisions': [],
                               'last_error': None, 'end_state': None}

    def _hook(self, monkeypatch, record, field, branch, allow=False):
        m, e, git = self._m(record, field, allow, branch=branch)
        m.node.pending_requests = lambda eid: [(1, {'tool': 'Read', 'input': {}})]
        answered, ctxs = [], []
        m.node.respond = lambda eid, seq, decision, reason: answered.append(decision)
        m._tail = lambda e, p: None
        m.policy = None
        monkeypatch.setattr(M.canonical, 'canonicalise',
                            lambda tool, inp, ctx: ctxs.append(ctx) or ((), ()))

        def _do(command, **kw):
            m.calls.append((command, kw))
            return {'decision': 'allow', 'reason': 'ok'}
        m._do = _do
        assert m._hooks(e, {}, disarmed=False) is True
        ((cmd, kw),) = m.calls
        assert cmd is X.serve_hook and answered == ['allow']
        return kw, ctxs[0], git

    @pytest.mark.parametrize('record,field', KNOWN)
    def test_a_known_isolated_hook_reads_no_git_in_its_workdir(self, monkeypatch, record,
                                                               field):
        kw, ctx, git = self._hook(monkeypatch, record, field, None)
        assert git == [] and kw['branch_ok'] is True
        assert (ctx['branch'], ctx['remotes']) == (None, {})

    @pytest.mark.parametrize('record,field', KNOWN)
    def test_a_known_isolated_hook_with_a_branch_fails_its_gate_unread(self, monkeypatch,
                                                                      record, field):
        kw, ctx, git = self._hook(monkeypatch, record, field, 'archeus/m.t1')
        assert git == [] and kw['branch_ok'] is False
        assert (ctx['branch'], ctx['remotes']) == (None, {})

    @pytest.mark.parametrize('field', [None, False])
    def test_a_hook_without_a_record_keeps_its_branch_check(self, monkeypatch, field):
        kw, ctx, git = self._hook(monkeypatch, None, field, 'archeus/m.t1', allow=True)
        assert git == ['git_branch', 'git_remotes'] and kw['branch_ok'] is True
        assert (ctx['branch'], ctx['remotes']) == ('archeus/m.t1', {'origin': 'u'})

    def test_the_checkpoint_says_the_diff_was_not_measured_never_none(self):
        from archeus.core.execution import checkpoint
        from archeus.core.sessions import render
        facts = M._unmeasured({})
        cp = SimpleNamespace(id='c', task_id='t', mission_id='m', plan_version=1,
                             execution_id='e', trigger='pause', objective='o', constraints=(),
                             success_criteria=(), completed_steps=(),
                             files_changed=checkpoint._clip(facts['files_changed']),
                             decisions=(), open_problems=(), verification=(),
                             next_action=None, as_of_seq=1)
        assert '## Files changed\n\n- %s\n' % M.UNMEASURED in render.checkpoint(cp)


class TestLostIsolationRecord:
    """T-037 / T-038: the transient record is gone and the row recorded Core's decision
    (T-036). A known-isolated execution is never adopted, never read for its own report,
    and killed only through a verified identity; a legacy unknown row keeps today's
    ordinary rules (the owner's N1) and is never written as ordinary."""

    def _reconcile(self, state, *, field=True, record=None, alive=True, create_time=1.0,
                   pid=True, adapter=None, registry_fails=False):
        m = _manager_with_fake_node()
        if registry_fails:
            m.node._registry = _no_registry
        e = _e(state, isolated=field)
        m.node.isolation_record = lambda eid: record
        m.node.files = lambda eid: ({'process_seq': 1}, {'pid': 4242, 'create_time': create_time,
                                                         'process_seq': 1} if pid else None,
                                    None)
        # verified identity: alive only with a create time to match against
        m.node.alive = lambda h: alive and h.create_time is not None
        # any read of the execution's own files would go through the adapter: object()
        # has no status/collect_result, so such a read raises
        adapter = adapter or object()
        m.registry = SimpleNamespace(get=lambda hid: adapter)
        m._adopt = lambda e, a, h: m.calls.append(('adopt', {'handle': h}))
        m._collect_gone = lambda e, a, h: m.calls.append(('collect_gone', {}))
        changed = m._reconcile_one(e, disarmed=False)
        return m, e, adapter, changed

    def _commands(self, m):
        return [c for c, _ in m.calls]

    @pytest.mark.parametrize('state,want', [
        ('RUNNING', [X.lost]), ('STARTING', [X.lost]), ('INTENT', [X.lost]),
        ('PAUSING', [X.record_end]), ('STOPPING', [X.record_end]),
        ('HANDING_OFF', [X.record_end]), ('PAUSED', []), ('AWAITING_APPROVAL', [])])
    def test_a_live_process_is_killed_by_identity_never_adopted(self, state, want):
        m, e, adapter, _ = self._reconcile(state)
        (killed,) = m.node.kills
        assert killed[0] is adapter and (killed[1].pid, killed[1].create_time) == (4242, 1.0)
        assert self._commands(m) == want                  # no record_process/adopt/handoff
        if state == 'PAUSING':
            assert m.calls[0][1]['core_halt'] is True and m.calls[0][1]['isolated'] is True
        if state in ('STOPPING', 'HANDING_OFF'):
            assert m.calls[0][1]['killed'] is True and m.calls[0][1]['isolated'] is True

    @pytest.mark.parametrize('state,want', [('RUNNING', [X.lost]), ('PAUSING', [X.record_end]),
                                            ('PAUSED', [])])
    def test_a_pid_without_a_verified_identity_is_never_killed(self, state, want):
        m, e, adapter, _ = self._reconcile(state, create_time=None)
        assert m.node.kills == []
        assert self._commands(m) == want

    def test_the_executions_own_report_is_never_read(self):
        # an adapter that would report what a forged halted.json and a result line say:
        # exit 0, halted. The outcome is Core's, and the adapter is never asked
        asked = []
        adapter = SimpleNamespace(
            status=lambda h: asked.append('status') or base.ProcStatus('exited', 0),
            collect_result=lambda h: asked.append('collect') or base.ExecutionResult(
                exit_reason='ok', exit_code=0, halted=True))
        m, e, _, _ = self._reconcile('RUNNING', alive=False, adapter=adapter)
        assert asked == [] and self._commands(m) == [X.lost]

    def test_without_a_process_the_intent_is_refused_uncharged(self):
        m, e, _, _ = self._reconcile('INTENT', pid=False)
        assert self._commands(m) == [X.refuse] and m.calls[0][1]['stop_reason'] == 'binding'

    @pytest.mark.parametrize('field,lines', [(None, ['isolation_decision_unknown']),
                                             (False, [])])
    def test_a_row_not_known_isolated_keeps_the_ordinary_route(self, field, lines):
        m, e, _, _ = self._reconcile('RUNNING', field=field)
        assert m.node.kills == [] and [c for c, _ in m.calls] == ['adopt']
        assert [x['op'] for x in m.node.registry] == lines
        assert e.isolated is field                        # nothing relabels it

    def test_a_record_still_decides_over_an_ordinary_field(self):
        rec = iso.IsolationRecord(execution_id='x', profile='p', state='established')
        m, e, _, _ = self._reconcile('RUNNING', field=False, record=rec)
        assert len(m.node.kills) == 1 and self._commands(m) == [X.lost]
        assert m.node.registry == []

    def test_reconcile_isolated_takes_no_record(self):
        m = _manager_with_fake_node()
        e = _e('INTENT')
        assert m._reconcile_isolated(e, object(), None, None, disarmed=False) is True
        assert [c for c, _ in m.calls] == [X.refuse]
        assert m.calls[0][1]['stop_reason'] == 'binding'

    def test_the_registry_line_is_left_once_per_execution(self, caplog):
        m = _manager_with_fake_node()
        e = _e('PAUSED')
        m.node.isolation_record = lambda eid: None
        m.node.files = lambda eid: (None, None, None)
        m.registry = SimpleNamespace(get=lambda hid: object())
        m._reconcile_one(e, disarmed=False)
        m._reconcile_one(e, disarmed=False)
        assert [x['op'] for x in m.node.registry] == ['isolation_record_missing']
        assert m.node.registry[0]['execution_id'] == e.id
        assert caplog.text.count('isolation_record_missing') == 1    # and one warning

    def test_a_registry_that_cannot_be_written_never_stops_the_kill(self, caplog):
        m, e, adapter, _ = self._reconcile('RUNNING', registry_fails=True)
        assert len(m.node.kills) == 1 and self._commands(m) == [X.lost]
        assert 'registry note was not written' in caplog.text

    @pytest.mark.parametrize('field,op', [(True, 'isolation_record_missing'),
                                          (None, 'isolation_decision_unknown')])
    def test_the_note_survives_the_boot_compaction(self, field, op):
        m = _manager_with_fake_node()
        e = _e('RUNNING', isolated=field)
        m._read = lambda: ([e], {})
        m._sweep_isolation = lambda live: []
        m.node.disarmed = lambda: False
        m.node.isolation_record = lambda eid: None
        m.node.files = lambda eid: (None, None, None)
        m.node.compact_registry = m.node.registry.clear      # keeps no note line
        m.registry = SimpleNamespace(get=lambda hid: object())
        m.boot()
        assert self._commands(m) == [X.lost]
        assert [(x['op'], x['execution_id']) for x in m.node.registry] == [(op, e.id)]


# ── item 8: A4 built, not enforced ────────────────────────────────────────────

class TestA4:
    def test_a4_is_built_but_not_enforced(self):
        assert iso.a4_enforced() is False
        assert callable(iso.a4_eligibility)
        assert iso.A4_CONDITIONS == ('production_dispatch', 'pv20_identity', 'core_held_job',
                                     'sandbox_inner_layer', 'no_harness_exception',
                                     'evidence_from_path')

    def test_a4_fails_closed_on_missing_facts(self):
        ok, unmet = iso.a4_eligibility(harness_id='real-agent')
        assert ok is False
        assert unmet                                     # every unknown fact is unmet

    def test_a4_fails_for_test_harness(self):
        ok, unmet = iso.a4_eligibility(harness_id='fake-x', isolated_launch=True,
                                       job_held=True, sandbox=False,
                                       exception_claimed=False, evidence='from-path')
        assert ok is False and 'production_dispatch' in unmet

    def test_a4_eligible_only_when_every_fact_holds(self):
        ok, unmet = iso.a4_eligibility(harness_id='real-agent', isolated_launch=True,
                                       job_held=True, sandbox=False,
                                       exception_claimed=False, evidence='from-path')
        assert ok is True and unmet == ()

    def test_nothing_on_the_dispatch_path_calls_a4_while_unenforced(self):
        # A4 is built but not enforced: the dispatch path may not call a4_eligibility
        # while A4_ENFORCED is False. Confirm none of the dispatch modules import/call it.
        import archeus.core.execution.manager as mg
        import archeus.node.local as lc
        import archeus.harnesses.base as bs
        for mod in (mg, lc, bs):
            src = open(mod.__file__, encoding='utf-8').read()
            assert 'a4_eligibility' not in src, '%s calls A4 while unenforced' % mod.__name__


# ── production dispatch stays disabled ────────────────────────────────────────

class TestProductionDispatchDisabled:
    def test_constant_is_false(self):
        assert iso.PRODUCTION_DISPATCH_ENABLED is False
        assert iso.production_dispatch_enabled() is False

    def test_real_harness_is_never_requested_while_disabled(self, tmp_path):
        a, b, req, _ = authority(tmp_path, authorize=lambda eid, adapter: True)
        # a non-test adapter stays unisolated while production dispatch is E's
        class Real:
            id = 'real-agent'
        assert a.requested(new_execution_id(), Real()) is False

    def test_test_harness_is_requested_when_authorized(self, tmp_path):
        a, b, req, _ = authority(tmp_path, authorize=lambda eid, adapter: True)
        class T:
            id = 'fake-agent'
        assert a.requested(new_execution_id(), T()) is True

    def test_unauthorized_is_never_requested(self, tmp_path):
        a, b, req, _ = authority(tmp_path)          # authorize=None
        class T:
            id = 'fake-agent'
        assert a.requested(new_execution_id(), T()) is False

    def test_default_plan_is_unsatisfiable_in_production(self, tmp_path, monkeypatch):
        # a project apart from the home: a workspace holding the class directories
        # would fail condition 5 on its own (see TestClassSeparation)
        project = tmp_path / 'project'
        project.mkdir()
        monkeypatch.setenv('ARCHEUS_HOME', str(tmp_path / 'home'))
        spec = base.ExecutionSpec(execution_id=new_execution_id(), prompt='go',
                                  workdir=str(project), hook_settings=_staged_hook(tmp_path))
        req = iso.default_plan(spec)
        # the class 1-3 directories and the spawn configuration as `base.spawn` and the
        # adapter leave them: the layout is there, and production still cannot start
        for p in (req.mailbox, req.response, req.sentinel, req.state_dir):
            os.makedirs(p)
        open(req.spawn_config, 'w').close()
        b = FakeBoundary()
        conds = iso.check_invariant(b, req, {'created': True,
                                             'sid': b.derive_sid(spec.execution_id)},
                                    {'type': 'Job', 'name': '', 'inheritable':False})
        unmet = iso.unmet_conditions(conds)
        assert 'grants' in unmet and 'mailbox' not in unmet
        assert conds['grants'][1] == 'no broker holds provider access (R3-B)'


# ── T-040 (C4b): the runtime and hook rows name Core's verified stage ─────────

class TestStagedHookRows:
    def test_the_runtime_and_hook_rows_name_the_stage_and_nothing_shared(self, tmp_path,
                                                                         monkeypatch):
        from archeus.infra import paths
        monkeypatch.setenv('ARCHEUS_HOME', str(tmp_path / 'home'))
        cmd = _staged_hook(tmp_path)
        project = tmp_path / 'project'
        project.mkdir()
        req = iso.default_plan(base.ExecutionSpec(
            execution_id=new_execution_id(), prompt='go', workdir=str(project),
            hook_settings=cmd))
        stage = os.path.dirname(cmd[0])
        assert {g.row: (g.path, g.access) for g in req.grants if g.row in ('runtime', 'hook')} \
            == {'runtime': (stage, 'rx'), 'hook': (stage, 'rx')}
        assert os.path.dirname(stage) == paths.runtime_dir()
        for g in req.grants:
            for shared in (os.path.dirname(os.path.abspath(sys.executable)), sys.base_prefix,
                           REPO):
                p, s = os.path.normcase(g.path), os.path.normcase(shared)
                assert p != s and not p.startswith(s + os.sep), (g.row, g.path)

    def _refused(self, tmp_path, cmd):
        b = FakeBoundary()
        a = iso.Isolation(FakeNode(), boundary=b)
        started = []

        class Adapter:
            id = 'fake'

            def start(self, spec):
                started.append(spec)

        node = LocalNode(isolation=a)
        spec = base.ExecutionSpec(execution_id=new_execution_id(), prompt='go',
                                  workdir=str(tmp_path), hook_settings=cmd)
        with pytest.raises(base.SpawnFailed, match='isolation: the hook'):
            node.spawn(Adapter(), spec, isolated=True)
        # refused before any profile operation, and nothing started
        assert (b.created, b.looked, b.launch_calls, started) == ([], [], [], [])
        assert a.record(spec.execution_id) is None

    @pytest.mark.parametrize('forge', [
        'missing', 'ordinary', 'list', 'no -I', 'relative', 'relative to the stage',
        'hook elsewhere', 'not under runtime', 'tampered'])
    def test_a_missing_forged_or_unverified_hook_command_is_refused(self, tmp_path,
                                                                    monkeypatch, forge):
        monkeypatch.setenv('ARCHEUS_HOME', str(tmp_path / 'home'))
        exe, flag, hook = _staged_hook(tmp_path)
        stage = os.path.dirname(exe)
        fake = tmp_path / 'fake'
        fake.mkdir()
        if forge == 'tampered':
            with open(os.path.join(stage, 'Lib', 'os.py'), 'ab') as f:
                f.write(b' changed')
        if forge == 'relative to the stage':
            # it would verify from here, and the CLI would resolve it from the workdir
            monkeypatch.chdir(os.path.dirname(stage))
        digest = os.path.basename(stage)
        cmd = {'missing': None,
               'ordinary': (sys.executable, M.HOOK),
               'list': [exe, flag, hook],
               'no -I': (exe, '-E', hook),
               'relative': ('python.exe', '-I', 'hook.py'),
               'relative to the stage': (os.path.join(digest, 'python.exe'), '-I',
                                         os.path.join(digest, 'hook.py')),
               'hook elsewhere': (exe, '-I', M.HOOK),
               'not under runtime': (str(fake / 'python.exe'), '-I', str(fake / 'hook.py')),
               'tampered': (exe, flag, hook)}[forge]
        self._refused(tmp_path, cmd)


# ── Phase A containment (ACL incident, 2026-10-09) ────────────────────────────
# S1 changes no ACL anywhere, plans are evidence rather than cleanup input, and
# persisted state is never authority over what gets mutated. Every refusal here is
# asserted as ZERO calls at the boundary Core talks to, under the OS tripwire above.

PY_INSTALL = os.path.dirname(os.path.abspath(sys.executable))
SHARED = (PY_INSTALL, REPO, os.path.expanduser('~'),
          os.environ.get('ProgramFiles', r'C:\Program Files'))


def _row(path, row='runtime', access='rx'):
    return {'path': path, 'access': access, 'row': row}


def _good_record(b, eid, **over):
    """A record as Core writes it for an established execution, with *over* on top."""
    d = iso.IsolationRecord(execution_id=eid, profile=iso.profile_name(eid),
                            sid=b.derive_sid(eid), state='established',
                            planned=(iso.Grant(PY_INSTALL, 'rx', 'runtime'),)).as_dict()
    d.update(over)
    return d


def _plant(name, payload):
    """A record file written exactly as given, bypassing Core; returns (path, bytes)."""
    os.makedirs(isolation_dir(), exist_ok=True)
    path = os.path.join(isolation_dir(), name)
    data = payload if isinstance(payload, bytes) else json.dumps(payload).encode('utf-8')
    with open(path, 'wb') as f:
        f.write(data)
    return path, data


def _ledger(*lines):
    os.makedirs(isolation_dir(), exist_ok=True)
    with open(quarantine_log(), 'ab') as f:
        for line in lines:
            f.write((line if isinstance(line, bytes) else json.dumps(line).encode('utf-8'))
                    + b'\n')


def _sweep(a):
    """The manager's own periodic sweep, over a LocalNode carrying *a*."""
    return M.ExecutionManager._sweep_isolation(
        SimpleNamespace(node=LocalNode(isolation=a), _isolation_fault=None), [])


#: nested past the interpreter's recursion limit: `json` raises RecursionError, which
#: is not a ValueError, on input like this
DEEP = b'[' * 100000 + b']' * 100000


FORGED = [
    ('applied access on the python install',
     lambda b, e: _good_record(b, e, applied=[_row(PY_INSTALL)]), 'applied_access'),
    ('applied access on the repository',
     lambda b, e: _good_record(b, e, applied=[_row(REPO, 'workspace', 'rw')]), 'applied_access'),
    ('the legacy grants field naming shared paths',
     lambda b, e: _good_record(b, e, grants=[_row(p) for p in SHARED]), 'unknown_fields:grants'),
    ("a user's SID", lambda b, e: _good_record(b, e, sid='S-1-5-21-1-2-3-1001'), 'sid_mismatch'),
    ('a non-string failure', lambda b, e: _good_record(b, e, failure=1), 'malformed:failure'),
    ('SYSTEM', lambda b, e: _good_record(b, e, sid='S-1-5-18'), 'sid_mismatch'),
    ('Everyone', lambda b, e: _good_record(b, e, sid='S-1-1-0'), 'sid_mismatch'),
    ('ALL APPLICATION PACKAGES', lambda b, e: _good_record(b, e, sid='S-1-15-2-1'),
     'sid_mismatch'),
    ("another execution's SID",
     lambda b, e: _good_record(b, e, sid=b.derive_sid(new_execution_id())), 'sid_mismatch'),
    ('a spike profile', lambda b, e: _good_record(b, e, profile='archeus.spike.life0'),
     'profile_mismatch'),
    ("another application's profile",
     lambda b, e: _good_record(b, e, profile='microsoft.windowscalculator_8wekyb3d8bbwe'),
     'profile_mismatch'),
    ('an empty profile', lambda b, e: _good_record(b, e, profile=''), 'profile_mismatch'),
    ('an established identity without a SID', lambda b, e: _good_record(b, e, sid=''),
     'sid_missing'),
    ('a capability', lambda b, e: _good_record(b, e, capabilities=['S-1-15-3-1']),
     'capabilities'),
    ('an unknown state', lambda b, e: _good_record(b, e, state='granted'), 'state_unknown'),
    ('a malformed plan row', lambda b, e: _good_record(b, e, planned=[{'path': PY_INSTALL}]),
     'planned_malformed'),
    # nothing nested may survive the check, or writing it back could recurse too deep
    ('a nested create time', lambda b, e: _good_record(b, e, create_time=[[1]]),
     'malformed:create_time'),
    ('nested conditions', lambda b, e: _good_record(b, e, conditions={'job': [[True], 'x']}),
     'conditions_malformed'),
    ('a refused profile claiming to be established',
     lambda b, e: _good_record(b, e, preexisting=True), 'preexisting_state'),
    ('a non-boolean refusal', lambda b, e: _good_record(b, e, preexisting='yes'),
     'malformed:preexisting'),
    ('ownership claimed for a refused profile',
     lambda b, e: _good_record(b, e, state='failed', owned=True, preexisting=True),
     'ownership_conflict'),
    ('a non-boolean ownership', lambda b, e: _good_record(b, e, owned='yes'), 'malformed:owned'),
]

#: Windows APIs that write a security descriptor or an ACL. S1 calls none of them.
ACL_APIS = ('SetNamedSecurityInfo', 'SetSecurityInfo', 'SetFileSecurity',
            'SetKernelObjectSecurity', 'SetEntriesInAcl', 'TreeSetNamedSecurityInfo',
            'TreeResetNamedSecurityInfo', 'SetSecurityDescriptorDacl',
            'SetPrivateObjectSecurity', 'AddAccessAllowedAce', 'AddAccessDeniedAce',
            'SetAclInformation', 'win32security',
            # by handle: Nt/Zw/RtlSetSecurityObject, and the user and service objects
            'SetSecurityObject', 'SetUserObjectSecurity', 'SetServiceObjectSecurity')
PROFILE_APIS = ('CreateAppContainerProfile', 'DeleteAppContainerProfile')
ISOLATION = 'archeus/node/isolation.py'


def _boundary_violations(tree, rel):
    """Every reference in *tree* to an ACL-changing program or API, and every use of
    the profile APIs outside the boundary's own `create_profile`/`delete_profile`
    (where the name is derived from a validated execution id). Docstrings are prose."""
    prose = {id(n.value) for n in ast.walk(tree)
             if isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant)
             and isinstance(n.value.value, str)}
    allowed = set()
    if rel == ISOLATION:
        for fn in ast.walk(tree):
            if isinstance(fn, ast.FunctionDef) and fn.name in ('create_profile', 'delete_profile'):
                allowed |= {id(n) for n in ast.walk(fn)}
    out = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in prose:
            text = n.value
        elif isinstance(n, ast.Name):
            text = n.id
        elif isinstance(n, ast.Attribute):
            text = n.attr
        elif isinstance(n, ast.alias):
            text = n.name
        else:
            continue
        where = (rel, getattr(n, 'lineno', 0), text)
        if ACL_TOOL.search(' %s ' % text) or any(api in text for api in ACL_APIS):
            out.append(where)
        elif any(api in text for api in PROFILE_APIS):
            # the ctypes binding itself (`_X = _f(userenv, 'X', ...)`) is not a call
            binding = rel == ISOLATION and (isinstance(n, ast.Constant)
                                            or isinstance(getattr(n, 'ctx', None), ast.Store))
            if not binding and id(n) not in allowed:
                out.append(where)
    return out


class TestPhaseAContainment:
    def test_the_production_plan_failing_its_conditions_changes_no_acl(self, tmp_path):
        # this is the path that used to run `icacls /T /remove:g` over the real Python
        # install, the repository and its harness sources on every unmet establishment
        b = FakeBoundary()
        a = iso.Isolation(FakeNode(), boundary=b)
        spec = base.ExecutionSpec(execution_id=new_execution_id(), prompt='go', workdir=REPO,
                                  hook_settings=_staged_hook(tmp_path))
        with pytest.raises(iso.IsolationUnavailable) as err:
            a.establish(iso.default_plan(spec))
        assert err.value.reason.startswith('condition_unmet:')
        rec = a.record(spec.execution_id)
        assert rec.state == 'failed' and rec.applied == ()
        planned = {g.path for g in rec.planned}                        # kept as evidence
        assert REPO in planned and os.path.dirname(spec.hook_settings[0]) in planned
        assert PY_INSTALL not in planned                    # C4b: the stage, never the install
        name = iso.profile_name(spec.execution_id)
        assert b.deleted == [name] and b.assigned == [] and b.launch_calls == []
        # the end path and the sweep finish the job with nothing but the profile
        a.teardown(spec.execution_id, reason='ended')
        assert _sweep(a) == []
        assert a.record(spec.execution_id) is None
        assert b.mutations() == [name, name, name]       # created, then deleted twice

    def test_planned_access_is_kept_apart_from_applied_access(self, tmp_path):
        a, b, req, _ = authority(tmp_path)
        rec = a.establish(req)
        assert rec.planned == req.grants and rec.applied == ()
        with open(isolation_state(req.execution_id), encoding='utf-8') as f:
            on_disk = json.load(f)
        assert on_disk['planned'] == [_row(g.path, g.row, g.access) for g in req.grants]
        assert on_disk['applied'] == [] and 'grants' not in on_disk
        assert a.record(req.execution_id).planned == req.grants

    def test_applied_access_stays_empty_on_every_path(self, tmp_path, monkeypatch):
        saved = []
        real_save = iso.Isolation._save

        def spy(self, rec):
            saved.append(rec.as_dict())
            return real_save(self, rec)

        monkeypatch.setattr(iso.Isolation, '_save', spy)
        b = FakeBoundary()
        a, b, ok, _ = authority(tmp_path, boundary=b)
        a.establish(ok)                                               # success
        b.broad = 'S-1-1-0'
        with pytest.raises(iso.IsolationUnavailable):                 # failure
            a.establish(make_satisfying_request(new_execution_id(), str(tmp_path)))
        b.broad = None
        stuck = make_satisfying_request(new_execution_id(), str(tmp_path))
        a.establish(stuck)
        b.delete_fail.add(iso.profile_name(stuck.execution_id))
        a.teardown(ok.execution_id, reason='ended')                   # teardown
        a.teardown(stuck.execution_id, reason='ended')                # quarantine
        a.reclaim(live_execution_ids=[])                              # reclaim, still stuck
        b.delete_fail.clear()
        _sweep(a)                                                     # the periodic sweep
        assert {d['state'] for d in saved} >= {'pending', 'established', 'failed',
                                                'quarantined', 'torn_down'}
        assert all(d['applied'] == [] for d in saved)
        claims = iso.IsolationRecord(execution_id=new_execution_id(), profile='p',
                                     applied=(iso.Grant(PY_INSTALL, 'rx', 'runtime'),))
        with pytest.raises(ValueError):
            real_save(a, claims)
        assert not os.path.exists(isolation_state(claims.execution_id))

    def test_the_boundary_has_no_acl_mutation_primitive(self):
        for name in ('_call_icacls', 'ICACLS', 'require_core_owned', 'user_sid', 'ACCESS_MASKS'):
            assert not hasattr(iso, name), name
        assert not hasattr(iso.Isolation, '_revoke')
        if iso.WindowsBoundary is not None:
            for name in ('grant', 'revoke', '_set_owner_baseline'):
                assert not hasattr(iso.WindowsBoundary, name), name

    @pytest.mark.parametrize('label,forge,reason', FORGED, ids=[f[0] for f in FORGED])
    def test_a_forged_record_mutates_nothing_and_is_left_as_found(self, tmp_path, label,
                                                                  forge, reason):
        node, b = FakeNode(), FakeBoundary()
        a = iso.Isolation(node, boundary=b)
        eid = new_execution_id()
        path, data = _plant(eid + '.json', forge(b, eid))
        assert a.requested(eid) is True          # still isolated: never run unisolated
        with pytest.raises(iso.IsolationUnavailable) as err:
            a.establish(make_satisfying_request(eid, str(tmp_path)))
        assert err.value.reason == 'record_invalid'
        assert a.teardown(eid, reason='ended')['profile'] == 'invalid_record'
        assert a.reclaim(live_execution_ids=[]) == []
        assert _sweep(a) == []
        assert b.mutations() == []                         # zero calls at the boundary
        with open(path, 'rb') as f:
            assert f.read() == data                        # the evidence is untouched
        assert a.invalid == {eid: reason}
        noted = [(x['key'], x['reason']) for x in node.registry
                 if x.get('op') == 'isolation_invalid']
        assert noted == [(eid, reason)]                    # visible, once

    @pytest.mark.parametrize('name', ['archeus.spike.life0',
                                      'microsoft.windowscalculator_8wekyb3d8bbwe', '',
                                      '..\\x', iso.profile_name(ids.new_id('execution'))])
    def test_no_profile_name_reaches_a_profile_api(self, name, os_tripwire):
        # a NAME is refused even when it is a real execution's: only an id derives one
        fake = FakeBoundary()
        bounds = [fake] + ([iso.WindowsBoundary()] if iso.WindowsBoundary is not None else [])
        for boundary in bounds:
            for op in (boundary.create_profile, boundary.delete_profile):
                with pytest.raises(iso.IsolationUnavailable) as err:
                    op(name)
                assert err.value.reason == 'profile_name'
        assert fake.mutations() == []
        assert os_tripwire == []           # the real (tripwired) APIs were never reached

    def test_malformed_record_files_are_contained_and_visible(self, tmp_path):
        b = FakeBoundary()
        a = iso.Isolation(FakeNode(), boundary=b)
        mismatched = new_execution_id()
        planted = [_plant(mismatched + '.json', _good_record(b, new_execution_id())),
                   _plant('notes.json', {'note': 'not a record'}),
                   _plant(new_execution_id() + '.json', b'{not json'),
                   _plant(new_execution_id() + '.json', b'\xff\xfe\x00not utf-8'),
                   _plant(new_execution_id() + '.json', b'[1, 2]')]
        os.makedirs(os.path.join(isolation_dir(), new_execution_id() + '.json'))
        assert a.reclaim(live_execution_ids=[]) == []
        assert _sweep(a) == []
        assert b.mutations() == []
        for path, data in planted:
            with open(path, 'rb') as f:
                assert f.read() == data
        assert a.invalid[mismatched] == 'execution_id_mismatch'
        assert a.invalid['notes.json'] == 'not_an_execution_id'
        assert sorted(a.invalid.values()).count('unreadable') == 3   # bad JSON, bytes, a dir
        assert 'not_an_object' in a.invalid.values()

    def test_malformed_or_forged_ledger_lines_reach_no_profile_operation(self, tmp_path):
        b = FakeBoundary()
        a = iso.Isolation(FakeNode(), boundary=b)
        eid = new_execution_id()
        good = {'op': 'quarantine', 'execution_id': eid, 'profile': iso.profile_name(eid),
                'sid': '', 'planned': [], 'reason': 'x', 'at': 1.0}
        probe = 'exe_PROBE0000000000000000001'               # a pi probe's id: not a ULID
        lines = [b'not json', b'\xff\xfe broken bytes', [], {'op': 'quarantine'},
                 dict(good, profile='archeus.spike.life0'),
                 dict(good, profile='microsoft.windowscalculator_8wekyb3d8bbwe'),
                 dict(good, profile=''), dict(good, sid='S-1-5-18'),
                 dict(good, execution_id=probe, profile=iso.profile_name(probe)),
                 dict(good, grants=[_row(PY_INSTALL)]), dict(good, op='grant')]
        _ledger(*lines)
        assert a.quarantined() == {}
        assert a.reclaim(live_execution_ids=[]) == []
        assert _sweep(a) == []
        assert b.mutations() == []
        assert sorted(a.invalid) == sorted('quarantine.jsonl:%d' % n
                                           for n in range(1, len(lines) + 1))

    def test_a_failed_cleanup_keeps_the_record_profile_and_sid(self, tmp_path):
        b = FakeBoundary()
        a, b, req, _ = authority(tmp_path, boundary=b)
        rec = a.establish(req)
        name = iso.profile_name(req.execution_id)
        b.delete_fail.add(name)
        assert a.teardown(req.execution_id, reason='ended')['profile'] == 'quarantined'
        for _ in range(2):                         # the boot retry, then a later pass
            assert req.execution_id not in a.reclaim(live_execution_ids=[])
            kept = a.record(req.execution_id)
            assert kept.state == 'quarantined' and kept.sid == rec.sid
            assert kept.planned == req.grants
            assert name in b.profiles             # the mapping that interprets its SID
            entry = a.quarantined()[req.execution_id]
            assert entry['sid'] == rec.sid and entry['profile'] == name

    def test_the_sweep_finishes_valid_work_around_invalid_state(self, tmp_path):
        b = FakeBoundary()
        a, b, req, _ = authority(tmp_path, boundary=b)
        a.establish(req)                                    # a valid record, now stale
        q = make_satisfying_request(new_execution_id(), str(tmp_path))
        a.establish(q)
        b.delete_fail.add(iso.profile_name(q.execution_id))
        a.teardown(q.execution_id, reason='ended')          # a valid quarantine entry
        b.delete_fail.clear()
        bad = new_execution_id()
        path, data = _plant(bad + '.json', _good_record(b, bad, sid='S-1-5-18'))
        _plant('notes.json', {'x': 1})
        _ledger(b'not json', {'op': 'quarantine', 'execution_id': bad,
                              'profile': 'archeus.spike.life0'})
        assert sorted(_sweep(a)) == sorted([req.execution_id, q.execution_id])
        assert iso.profile_name(bad) not in b.deleted
        assert 'archeus.spike.life0' not in b.deleted
        with open(path, 'rb') as f:
            assert f.read() == data
        assert a.record(bad).state == 'invalid'
        assert {bad, 'notes.json'} <= set(a.invalid)

    def test_a_failed_boundary_read_is_an_establishment_failure(self, tmp_path):
        # the user SID now comes from the process token and can fail; it must be
        # recorded and the identity released, never left pending with a profile
        b = FakeBoundary()
        a, b, req, _ = authority(tmp_path, boundary=b)

        def unreadable(path, sid):
            raise iso.IsolationUnavailable('token', 'synthetic')

        b.broad_write_grant = unreadable
        with pytest.raises(iso.IsolationUnavailable) as err:
            a.establish(req)
        assert err.value.reason == 'token'
        assert a.record(req.execution_id).state == 'failed'
        assert b.deleted == [iso.profile_name(req.execution_id)]

    def test_an_existing_profile_is_adopted_only_by_its_own_established_resume(self, tmp_path):
        b = FakeBoundary()
        a, b, req, _ = authority(tmp_path, boundary=b)
        first = a.establish(req)
        again = a.establish(req)             # a resume: the record proves the identity
        assert again.state == 'established' and again.sid == first.sid
        stray = make_satisfying_request(new_execution_id(), str(tmp_path))
        name = iso.profile_name(stray.execution_id)
        b.profiles.add(name)                     # standing, no record of it
        with pytest.raises(iso.IsolationUnavailable) as err:
            a.establish(stray)
        assert err.value.reason == 'profile_preexisting'

        def untouched():
            # refused, so never deleted, and the record says why and whose it is not
            assert name in b.profiles and name not in b.deleted
            kept = a.record(stray.execution_id)
            assert kept.state == 'failed' and kept.preexisting is True and not kept.owned
            assert kept.reason == 'profile_preexisting'
            assert kept.sid == b.derive_sid(stray.execution_id)

        untouched()                                          # the failure cleanup
        assert a.teardown(stray.execution_id, reason='ended')['profile'] == 'preexisting'
        untouched()                                          # the end path
        assert stray.execution_id not in a.reclaim(live_execution_ids=[])
        assert stray.execution_id not in _sweep(a)
        untouched()                                          # boot reclaim, periodic sweep
        _ledger({'op': 'quarantine', 'execution_id': stray.execution_id, 'profile': name,
                 'sid': '', 'planned': [], 'reason': 'x', 'at': 1.0})
        assert stray.execution_id not in a.reclaim(live_execution_ids=[])
        untouched()                                          # even named by the ledger
        with pytest.raises(iso.IsolationUnavailable) as err:
            a.establish(stray)                               # a retry adopts nothing either
        assert err.value.reason == 'profile_preexisting'
        assert b.created.count(name) == 1                    # and asks the OS nothing
        untouched()

    @pytest.mark.parametrize('snippet,rel', [
        ("subprocess.run(['icacls', path, '/grant', ace])", 'archeus/x.py'),
        ("subprocess.run([r'C:\\Windows\\System32\\icacls.exe', path])", 'archeus/x.py'),
        ("os.system('icacls %s /reset /T' % path)", 'archeus/x.py'),
        ("subprocess.run(['powershell', '-c', 'Set-Acl -Path x'])", 'tools/x.py'),
        ("subprocess.run(['takeown', '/f', path])", 'claude_sessions/x.py'),
        ("_f(advapi32, 'SetNamedSecurityInfoW', W.DWORD, [])", ISOLATION),
        ("advapi32.SetEntriesInAclW(1, None, None, None)", 'archeus/x.py'),
        ('import win32security', 'archeus/x.py'),
        ("_f(ntdll, 'NtSetSecurityObject', C.c_long, [])", ISOLATION),
        ('ntdll.ZwSetSecurityObject(h, 4, sd)', 'archeus/x.py'),
        ('user32.SetUserObjectSecurity(h, si, sd)', 'tools/x.py'),
        ('advapi32.SetServiceObjectSecurity(h, si, sd)', 'claude_sessions/x.py'),
        ('_DeleteAppContainerProfile(name)', 'archeus/x.py'),
        ('def teardown(self):\n    _DeleteAppContainerProfile(n)', ISOLATION),
    ])
    def test_the_static_gate_sees_each_kind_of_mutation(self, snippet, rel):
        assert _boundary_violations(ast.parse(snippet), rel)

    def test_the_static_gate_allows_only_the_derived_profile_calls(self):
        ok = ("_DeleteAppContainerProfile = _f(userenv, 'DeleteAppContainerProfile', None, [])\n"
              'def delete_profile(self, execution_id):\n'
              '    _DeleteAppContainerProfile(validated_profile(execution_id))\n')
        assert _boundary_violations(ast.parse(ok), ISOLATION) == []

    def test_no_acl_mutation_primitive_exists_in_production_code(self):
        found, scanned = [], 0
        for top in ('archeus', 'claude_sessions', 'tools'):
            for dirpath, dirnames, files in os.walk(os.path.join(REPO, top)):
                dirnames[:] = [d for d in dirnames if d != '__pycache__']
                for f in files:
                    if f.endswith('.py'):
                        p = os.path.join(dirpath, f)
                        with open(p, encoding='utf-8-sig') as fh:
                            tree = ast.parse(fh.read())
                        found += _boundary_violations(
                            tree, os.path.relpath(p, REPO).replace('\\', '/'))
                        scanned += 1
        assert scanned > 100                     # a gate that scans nothing passes
        assert found == []


WINDOWS_MODULE = os.path.join(REPO, 'tests', 'v1', 'integration',
                              'test_pv20_isolation_windows.py')


def _ledger_ops():
    with open(quarantine_log(), encoding='utf-8') as f:
        return [json.loads(x)['op'] for x in f]


class TestCorrectivePass:
    """The independent review's A1-A3 and A5, each held to the behaviour it fixes."""

    # ── A3: input nested too deep to parse is invalid evidence, never a crash ──

    def test_a_deeply_nested_record_is_invalid_evidence_not_a_crash(self, tmp_path):
        with pytest.raises(RecursionError):
            json.loads(DEEP)                     # the planted input really is the hazard
        node, b = FakeNode(), FakeBoundary()
        a = iso.Isolation(node, boundary=b)
        eid = new_execution_id()
        path, data = _plant(eid + '.json', DEEP)
        assert a.record(eid).state == 'invalid' and a.invalid[eid] == 'unreadable'
        assert a.requested(eid) is True          # present, so never treated as absent
        with pytest.raises(iso.IsolationUnavailable) as err:
            a.establish(make_satisfying_request(eid, str(tmp_path)))
        assert err.value.reason == 'record_invalid'
        assert a.teardown(eid, reason='ended')['profile'] == 'invalid_record'
        assert b.mutations() == []
        with open(path, 'rb') as f:
            assert f.read() == data

    def test_a_deeply_nested_ledger_line_is_reported_and_skipped(self, tmp_path):
        node, b = FakeNode(), FakeBoundary()
        a = iso.Isolation(node, boundary=b)
        eid = new_execution_id()
        good = {'op': 'quarantine', 'execution_id': eid, 'profile': iso.profile_name(eid),
                'sid': '', 'planned': [], 'reason': 'x', 'at': 1.0}
        _ledger(DEEP, b'{"op": "quarantine", "x": ' + DEEP + b'}', good)
        with open(quarantine_log(), 'rb') as f:
            planted = f.read()
        assert set(a.quarantined()) == {eid}
        assert a.invalid['quarantine.jsonl:1'] == 'not_an_object'
        assert a.invalid['quarantine.jsonl:2'] == 'not_an_object'
        assert a.reclaim(live_execution_ids=[]) == [eid]   # the line after them still works
        with open(quarantine_log(), 'rb') as f:
            assert f.read().startswith(planted)            # the evidence is kept as written

    def test_the_sweep_handles_valid_records_after_malformed_ones(self, tmp_path):
        a, b, _, node = authority(tmp_path)
        deep, nested = new_execution_id(), new_execution_id()  # minted first: sorted first
        planted = [_plant(deep + '.json', DEEP),
                   _plant(nested + '.json', _good_record(b, nested, create_time=[[1]]))]
        valid = make_satisfying_request(new_execution_id(), str(tmp_path))
        a.establish(valid)                       # stale once its execution is not live
        assert sorted(a.stale()) == [deep, nested, valid.execution_id]
        assert _sweep(a) == [valid.execution_id]
        assert a.record(valid.execution_id) is None
        assert b.deleted == [iso.profile_name(valid.execution_id)]
        for path, data in planted:
            with open(path, 'rb') as f:
                assert f.read() == data
        assert a.invalid[deep] == 'unreadable' and a.invalid[nested] == 'malformed:create_time'
        for _ in range(3):
            assert _sweep(a) == []
        noted = [x for x in node.registry if x.get('op') == 'isolation_invalid']
        assert len(noted) == 2                   # once each, not once per pass

    def test_a_sweep_fault_is_logged_once_per_distinct_fault(self, caplog):
        faults = iter([OSError('disk gone'), OSError('disk gone'), OSError('other'), None])

        def reclaim(live):
            fault = next(faults)
            if fault:
                raise fault
            return []

        m = SimpleNamespace(node=SimpleNamespace(reclaim_isolation=reclaim),
                            _isolation_fault=None)
        with caplog.at_level('WARNING', logger='archeus.execution'):
            for _ in range(4):
                assert M.ExecutionManager._sweep_isolation(m, []) == []
        said = [r.getMessage() for r in caplog.records if 'isolation sweep' in r.getMessage()]
        assert len(said) == 2 and 'disk gone' in said[0] and 'other' in said[1]
        assert m._isolation_fault is None        # cleared once a pass completes

    # ── A5: a cleanup that keeps failing does not grow the ledger every pass ──

    def test_repeated_failed_cleanup_keeps_the_ledger_bounded(self, tmp_path):
        a, b, req, node = authority(tmp_path)
        rec = a.establish(req)
        b.delete_fail.add(rec.profile)
        a.teardown(req.execution_id, reason='ended')       # enters quarantine
        for _ in range(10):                                # ten passes, all failing
            assert _sweep(a) == []
        assert _ledger_ops() == ['quarantine']
        assert sum(x.get('op') == 'quarantine' for x in node.registry) == 1
        assert b.deleted.count(rec.profile) == 11          # one attempt per pass, not two
        kept = a.record(req.execution_id)
        assert kept.state == 'quarantined' and kept.attempts == 11
        assert kept.reason == 'profile_delete: in use (synthetic)' and kept.sid == rec.sid
        assert rec.profile in b.profiles and req.execution_id in a.quarantined()

        def denied(execution_id):
            b.deleted.append(iso.validated_profile(execution_id))
            raise iso.IsolationUnavailable('profile_delete', 'access denied (synthetic)')

        b.delete_profile = denied                          # the failure itself changes
        for _ in range(3):
            assert _sweep(a) == []
        assert _ledger_ops() == ['quarantine', 'quarantine']
        assert a.record(req.execution_id).reason == 'profile_delete: access denied (synthetic)'
        del b.delete_profile
        b.delete_fail.clear()
        assert _sweep(a) == [req.execution_id]             # and it is still recoverable
        assert _ledger_ops() == ['quarantine', 'quarantine', 'released']
        assert a.record(req.execution_id) is None

    # ── A1: the real-boundary module runs only when asked, and only in its own home ──

    def test_the_windows_module_skips_before_it_imports_anything_real(self):
        with open(WINDOWS_MODULE, encoding='utf-8') as f:
            tree = ast.parse(f.read())

        def is_gate(n):
            return isinstance(n, ast.If) and 'ARCHEUS_REAL_BOUNDARY' in ast.dump(n.test) and any(
                isinstance(c, ast.Call) and getattr(c.func, 'attr', '') == 'skip'
                and any(k.arg == 'allow_module_level' for k in c.keywords) for c in ast.walk(n))

        gate = next(i for i, n in enumerate(tree.body) if is_gate(n))
        early = set()
        for n in tree.body[:gate]:
            if isinstance(n, ast.Import):
                early |= {x.name.split('.')[0] for x in n.names}
            elif isinstance(n, ast.ImportFrom):
                early.add((n.module or '').split('.')[0])
            else:
                assert not isinstance(n, (ast.FunctionDef, ast.ClassDef)), n.name
        assert early <= {'os', 'subprocess', 'sys', 'time', 'pytest'}

        parents = {c: p for p in ast.walk(tree) for c in ast.iter_child_nodes(p)}
        for n in ast.walk(tree):
            if isinstance(n, ast.Attribute) and n.attr == 'environ' \
                    and getattr(n.value, 'id', '') == 'os':
                # a single named lookup, never the environment itself
                assert getattr(parents[n], 'attr', '') == 'get', ast.unparse(parents[n])
            if isinstance(n, ast.ExceptHandler):
                assert n.type is not None and not all(isinstance(s, ast.Pass) for s in n.body)

        funcs = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
        assert 'owned_home' in [x.arg for x in funcs['boundary'].args.args]
        tests = [f for name, f in funcs.items() if name.startswith('test_')]
        assert tests and all('boundary' in [x.arg for x in f.args.args] for f in tests)
        assert 'exe_' not in ast.unparse(tree)   # every execution id is freshly minted


# ── A4: the grant readers fail closed (pure: synthetic descriptors, any platform) ─
# The masks and ACE layouts below are written from the Windows contract (winnt.h,
# MS-DTYP 2.4), not from the module under test, so they can disagree with it.

ME = 'S-1-5-21-1111-2222-3333-1001'                 # Core's own user
APPC = ('S-1-15-2-2860417396-1414370549-4071012870-3201281005-2155183018-1990463016-'
        '3964358779')                               # an AppContainer SID: 7 sub-authorities
RX, RW = 0x1 | 0x20, 0x1 | 0x2                      # FILE_READ_DATA|FILE_EXECUTE, |FILE_WRITE_DATA
WRITE_EA, DELETE_CHILD, WRITE_ATTRIBUTES, GENERIC_ALL = 0x10, 0x40, 0x100, 0x10000000
INHERIT_ONLY = 0x08 | 0x01 | 0x02                   # inherit-only, object- and container-inherit


def _sid_bytes(text):
    parts = text.split('-')                         # S-1-<authority>-<sub>...
    subs = [int(x) for x in parts[3:]]
    return (bytes([1, len(subs)]) + int(parts[2]).to_bytes(6, 'big')
            + b''.join(s.to_bytes(4, 'little') for s in subs))


def _ace(ace_type, sid, mask, flags=0, tail=b''):
    """One ACE as Windows lays it out: ACE_HEADER (type, flags, size), mask, SID[, data]."""
    body = mask.to_bytes(4, 'little') + _sid_bytes(sid) + tail
    return bytes([ace_type, flags]) + (4 + len(body)).to_bytes(2, 'little') + body


def _resized(raw, size):
    return raw[:2] + size.to_bytes(2, 'little') + raw[4:]


A_EVERYONE = _ace(0x0, 'S-1-1-0', 0x1200A9)
OBJECT_ACE = (bytes([0x5, 0]) + (16).to_bytes(2, 'little') + RX.to_bytes(4, 'little')
              + (0).to_bytes(4, 'little') + _sid_bytes('S-1-1-0')[:4])
OVERRUN = _resized(_ace(0x0, 'S-1-5-18', RX)[:8] + bytes([1, 2]) + bytes(6) + bytes(4), 20)


def _readers(acl):
    """The real grant readers over `acl[path]`: an ACE list, or the error its read raises."""
    class Readers(iso.DaclReaders):
        def dacl(self, path):
            got = acl[path]
            if isinstance(got, Exception):
                raise got
            return list(got)

        def _user_sid(self):
            return ME
    return Readers()


def _descriptor_boundary(acl):
    """A fake boundary whose grant readers are the real ones, over `acl[path]`."""
    class Boundary(iso.DaclReaders, FakeBoundary):
        def dacl(self, path):
            self.reads.append(path)
            got = acl[path]
            if isinstance(got, Exception):
                raise got
            return list(got)

        def _user_sid(self):
            return ME
    b = Boundary()
    b.reads = []
    return b


def _exact(req, sid):
    """A descriptor per path that satisfies conditions 2, 3 and 5 exactly."""
    acl = {g.path: [(0x0, sid, RW if g.access == 'rw' else RX, 0)] for g in req.grants}
    acl[req.core_state] = []                        # an empty DACL: nobody at all
    return acl


class TestAclInspection:
    @pytest.mark.parametrize('raw,expect', [
        (A_EVERYONE, (0x0, 'S-1-1-0', 0x1200A9, 0)),
        (_ace(0x1, 'S-1-5-32-545', 0x2, 0x10), (0x1, 'S-1-5-32-545', 0x2, 0x10)),
        (_ace(0x0, APPC, RX, 0x13), (0x0, APPC, RX, 0x13)),
        # a conditional ACE carries its condition after the SID
        (_ace(0x9, ME, RW, 0, tail=b'artx\x00\x00\x00\x00'), (0x9, ME, RW, 0)),
        (_ace(0xA, 'S-1-1-0', RW, 0, tail=b'artx'), (0xA, 'S-1-1-0', RW, 0)),
    ])
    def test_an_access_ace_is_read_from_its_own_bytes(self, raw, expect):
        assert iso.parse_ace(raw) == expect

    @pytest.mark.parametrize('ace_type', [0x2, 0x3, 0x4, 0x5, 0x6, 0x7, 0x8, 0xB, 0xC, 0xD,
                                          0x11, 0x12, 0x13, 0x14, 0x15, 0x16, 0xFF])
    def test_every_other_ace_type_is_refused_not_guessed(self, ace_type):
        # object, compound, audit, alarm, label and unknown ACEs: never an allow ACE
        with pytest.raises(iso.IsolationUnavailable) as err:
            iso.parse_ace(bytes([ace_type]) + A_EVERYONE[1:])
        assert err.value.reason == 'dacl_unsupported_ace'

    @pytest.mark.parametrize('label,raw,reason', [
        ('shorter than any ACE', A_EVERYONE[:8], 'dacl_malformed'),
        ('a size that is not its length', _resized(A_EVERYONE, len(A_EVERYONE) + 4),
         'dacl_malformed'),
        ('a SID revision that is not 1', A_EVERYONE[:8] + b'\x02' + A_EVERYONE[9:],
         'dacl_malformed'),
        ('more sub-authorities than a SID may have',
         _resized(A_EVERYONE[:8] + bytes([1, 16]) + bytes(6) + bytes(64), 80), 'dacl_malformed'),
        ('a SID that runs past its ACE', OVERRUN, 'dacl_malformed'),
        ('a SID that runs past a conditional ACE', bytes([0x9]) + OVERRUN[1:], 'dacl_malformed'),
        ('bytes after the SID of a plain ACE', _ace(0x0, 'S-1-1-0', RX, tail=bytes(4)),
         'dacl_malformed'),
        ('an authority written in hex', A_EVERYONE[:10] + (2 ** 40).to_bytes(6, 'big')
         + A_EVERYONE[16:], 'dacl_unsupported_sid'),
    ])
    def test_a_malformed_ace_is_refused(self, label, raw, reason):
        with pytest.raises(iso.IsolationUnavailable) as err:
            iso.parse_ace(raw)
        assert err.value.reason == reason

    @pytest.mark.parametrize('label,aces,access,expect', [
        ('an exact allow for the execution', [(0x0, APPC, RX, 0)], 'rx', True),
        ('more than the row allows', [(0x0, APPC, RW, 0)], 'rx', False),
        ('inherit-only: not on the object itself', [(0x0, APPC, RX, INHERIT_ONLY)], 'rx', False),
        ('conditional: may not hold', [(0x9, APPC, RX, 0)], 'rx', False),
        ('an app-package group, not the execution', [(0x0, 'S-1-15-2-1', RX, 0)], 'rx', False),
        ('a deny', [(0x1, APPC, RX, 0)], 'rx', False),
        ('an empty DACL', [], 'rx', False),
        # every allow ACE for the execution, taken together (C5)
        ('read and execute as Windows writes them', [(0x0, APPC, 0x1200A9, 0)], 'rx', True),
        ('read and execute split over two ACEs', [(0x0, APPC, 0x1, 0), (0x0, APPC, 0x20, 0)],
         'rx', True),
        ('a second ACE that writes', [(0x0, APPC, RX, 0), (0x0, APPC, 0x2, 0)], 'rx', False),
        ('an inherit-only ACE that writes what is created inside',
         [(0x0, APPC, RX, 0), (0x0, APPC, 0x2, INHERIT_ONLY)], 'rx', False),
        ('a conditional ACE that writes', [(0x0, APPC, RX, 0), (0x9, APPC, 0x2, 0)], 'rx', False),
        ('and delete children', [(0x0, APPC, RX | DELETE_CHILD, 0)], 'rx', False),
        ('and write attributes', [(0x0, APPC, RX | WRITE_ATTRIBUTES, 0)], 'rx', False),
        ('and write extended attributes', [(0x0, APPC, RX | WRITE_EA, 0)], 'rx', False),
        ('and delete', [(0x0, APPC, RX | 0x10000, 0)], 'rx', False),
        ('execute alone, for an execute row', [(0x0, APPC, 0x20, 0)], 'x', True),
        ('execute and write attributes, for an execute row',
         [(0x0, APPC, 0x20 | WRITE_ATTRIBUTES, 0)], 'x', False),
        ('read and write, for a writable row', [(0x0, APPC, RW, 0)], 'rw', True),
        ('a row that is none of the three', [(0x0, APPC, RW, 0)], 'r', False),
    ])
    def test_a_grant_is_established_only_by_an_unconditional_ace_on_the_object(
            self, label, aces, access, expect):
        assert _readers({'p': aces}).grant_established('p', APPC, access) is expect

    @pytest.mark.parametrize('label,aces,expect', [
        ('the execution itself', [(0x0, APPC, RX, 0)], True),
        ('ALL APPLICATION PACKAGES', [(0x0, 'S-1-15-2-1', RX, 0)], True),
        ('ALL RESTRICTED APPLICATION PACKAGES', [(0x0, 'S-1-15-2-2', RX, 0)], True),
        ('a conditional allow', [(0x9, APPC, RX, 0)], True),
        ('an inherit-only allow', [(0x0, APPC, RX, INHERIT_ONLY)], True),
        ('a NULL DACL', None, True),
        ('a deny only', [(0x1, APPC, RX, 0)], False),
        ('somebody else', [(0x0, ME, RW, 0)], False),
        ('an empty DACL', [], False),
    ])
    def test_reaching_a_path_counts_every_way_in(self, label, aces, expect):
        acl = {'p': list(iso.NULL_DACL) if aces is None else aces}
        assert _readers(acl).granted_to('p', APPC) is expect

    @pytest.mark.parametrize('label,aces,expect', [
        ('a NULL DACL', None, 'S-1-1-0'),
        ('Everyone may delete children', [(0x0, 'S-1-1-0', DELETE_CHILD, 0)], 'S-1-1-0'),
        ('Everyone may write attributes', [(0x0, 'S-1-1-0', WRITE_ATTRIBUTES, 0)], 'S-1-1-0'),
        ('Everyone may write extended attributes', [(0x0, 'S-1-1-0', WRITE_EA, 0)], 'S-1-1-0'),
        ('Administrators may write', [(0x0, 'S-1-5-32-544', RW, 0)], 'S-1-5-32-544'),
        ('a conditional write', [(0x9, 'S-1-1-0', RW, 0)], 'S-1-1-0'),
        ('an inherit-only write', [(0x0, 'S-1-5-32-545', RW, INHERIT_ONLY)], 'S-1-5-32-545'),
        ('a SID that only starts like SYSTEM', [(0x0, 'S-1-5-180-1', RW, 0)], 'S-1-5-180-1'),
        ('Everyone may read', [(0x0, 'S-1-1-0', 0x1200A9, 0)], None),
        ('SYSTEM', [(0x0, 'S-1-5-18', GENERIC_ALL, 0)], None),
        ("Core's own user", [(0x0, ME, RW, 0)], None),
        ('the execution itself', [(0x0, APPC, RW, 0)], None),
        ('a deny', [(0x1, 'S-1-1-0', RW, 0)], None),
    ])
    def test_a_broad_write_is_any_write_for_somebody_else(self, label, aces, expect):
        acl = {'p': list(iso.NULL_DACL) if aces is None else aces}
        assert _readers(acl).broad_write_grant('p', APPC) == expect

    def test_an_unreadable_descriptor_is_never_read_as_clean(self):
        r = _readers({'p': iso.IsolationUnavailable('dacl_unreadable', 'synthetic')})
        for read in (lambda: r.grant_established('p', APPC, 'rx'),
                     lambda: r.granted_to('p', APPC), lambda: r.broad_write_grant('p', APPC)):
            with pytest.raises(iso.IsolationUnavailable) as err:
                read()
            assert err.value.reason == 'dacl_unreadable'
        assert _readers({}).granted_to('', APPC) is False     # nothing named, nothing read

    # ── through `establish`, with the real readers over synthetic descriptors ──

    def _authority(self, tmp_path, change=None):
        acl = {}
        a, b, req, node = authority(tmp_path, boundary=_descriptor_boundary(acl))
        sid = b.derive_sid(req.execution_id)
        acl.update(_exact(req, sid))
        if change:
            change(acl, req, sid)
        return a, b, req

    def test_exact_descriptors_establish_the_identity(self, tmp_path):
        a, b, req = self._authority(tmp_path)
        assert a.establish(req).state == 'established'

    @pytest.mark.parametrize('label,change,reason', [
        ("Core's state cannot be read",
         lambda acl, req, sid: acl.update({req.core_state: iso.IsolationUnavailable(
             'dacl_unreadable', 'synthetic')}), 'dacl_unreadable'),
        ("a NULL DACL on Core's state",
         lambda acl, req, sid: acl.update({req.core_state: list(iso.NULL_DACL)}),
         'condition_unmet:no_broad_grants,mailbox'),
        ("an app package may read Core's state",
         lambda acl, req, sid: acl.update({req.core_state: [(0x0, 'S-1-15-2-1', RX, 0)]}),
         'condition_unmet:no_broad_grants,mailbox'),
        ('a NULL DACL on a granted path',
         lambda acl, req, sid: acl.update({req.grant_for('runtime').path: list(iso.NULL_DACL)}),
         'condition_unmet:grants,no_broad_grants'),
        ('Everyone may delete inside the workspace',
         lambda acl, req, sid: acl[req.workspace].append((0x0, 'S-1-1-0', DELETE_CHILD, 0)),
         'condition_unmet:no_broad_grants'),
        ('the grant is conditional',
         lambda acl, req, sid: acl.update({req.grant_for('runtime').path: [(0x9, sid, RX, 0)]}),
         'condition_unmet:grants'),
        ('the grant is inherit-only',
         lambda acl, req, sid: acl.update({req.grant_for('runtime').path:
                                           [(0x0, sid, RX, INHERIT_ONLY)]}),
         'condition_unmet:grants'),
        ('the execution may also write the runtime',
         lambda acl, req, sid: acl[req.grant_for('runtime').path].append((0x0, sid, 0x2, 0)),
         'condition_unmet:grants'),
    ])
    def test_every_unclean_descriptor_fails_establishment(self, tmp_path, label, change, reason):
        a, b, req = self._authority(tmp_path, change)
        with pytest.raises(iso.IsolationUnavailable) as err:
            a.establish(req)
        assert err.value.reason == reason
        rec = a.record(req.execution_id)
        assert rec.state == 'failed' and rec.reason == reason
        assert b.deleted == [iso.profile_name(req.execution_id)]   # Core's own: released
        assert b.launch_calls == [] and b.assigned == []

    def test_a_missing_grant_directory_is_unmet_by_name_and_never_read(self, tmp_path):
        a, b, req = self._authority(tmp_path)
        runtime = req.grant_for('runtime').path
        os.rmdir(runtime)
        with pytest.raises(iso.IsolationUnavailable) as err:
            a.establish(req)
        assert err.value.reason == 'condition_unmet:grants'
        assert runtime not in b.reads

    def test_a_job_whose_name_cannot_be_read_is_not_unnamed(self, tmp_path):
        a, b, req, _ = authority(tmp_path)
        sid = b.derive_sid(req.execution_id)
        conds = iso.check_invariant(b, req, {'created': True, 'sid': sid},
                                    {'type': 'Job', 'name': None, 'inheritable': False})
        assert iso.unmet_conditions(conds) == ('job',)
        b.job_name_unknown = True
        with pytest.raises(iso.IsolationUnavailable) as err:
            a.establish(req)
        assert err.value.reason == 'condition_unmet:job'

    def test_core_state_must_be_named_to_be_kept_out(self, tmp_path):
        a, b, req, _ = authority(tmp_path)
        unnamed = iso.IsolationRequest(**{**req.__dict__, 'core_state': ''})
        conds = iso.check_invariant(b, unnamed, {'created': True,
                                                 'sid': b.derive_sid(req.execution_id)},
                                    {'type': 'Job', 'name': '', 'inheritable': False})
        assert iso.unmet_conditions(conds) == ('mailbox',)

    @pytest.mark.skipif(iso.WindowsBoundary is None, reason='a Win32 failure exists on Windows')
    def test_a_win32_failure_is_an_isolation_failure_and_never_escapes(self, tmp_path):
        assert issubclass(iso._WinFail, iso.IsolationUnavailable)
        a, b, req, _ = authority(tmp_path)

        def job(execution_id):
            raise iso._WinFail('SetInformationJobObject', 5)

        b.create_job = job
        with pytest.raises(iso.IsolationUnavailable) as err:
            a.establish(req)
        assert err.value.reason == 'winapi'
        rec = a.record(req.execution_id)
        assert rec.state == 'failed' and rec.reason == 'winapi'   # tracked, never pending
        assert b.deleted == [iso.profile_name(req.execution_id)]


# ── A4: the real descriptor read, over mocked Win32 calls (Windows only) ──────

@pytest.fixture
def winapi(monkeypatch):
    """`dacl()`'s four Win32 calls replaced by fakes over a synthetic ACL in memory, so
    the real read is exercised with no real security API (the tripwire stays armed)."""
    s = SimpleNamespace(error=0, null_dacl=False, info_ok=True, aces=[], fail_at=None,
                        null_at=None, in_use=None, freed=[], keep=[], sd=None, acl=None)

    def get_security(path, kind, what, owner, group, ppdacl, ppsacl, ppsd):
        if s.error:
            return s.error
        blob = b''.join(s.aces)
        acl = ctypes.create_string_buffer(bytes([2, 0]) + (8 + len(blob)).to_bytes(2, 'little')
                                          + len(s.aces).to_bytes(2, 'little') + bytes(2) + blob)
        sd = ctypes.create_string_buffer(20)
        s.keep += [acl, sd]
        s.acl, s.sd = ctypes.addressof(acl), ctypes.addressof(sd)
        ppsd._obj.value = s.sd
        if not s.null_dacl:
            ppdacl._obj.value = s.acl
        return 0

    def get_info(pacl, pinfo, size, cls):
        if not s.info_ok:
            return 0
        pinfo._obj.AceCount = len(s.aces)
        pinfo._obj.AclBytesInUse = s.in_use or 8 + sum(map(len, s.aces))
        return 1

    def get_ace(pacl, i, ppace):
        if i == s.fail_at:
            return 0
        if i != s.null_at:
            ppace._obj.value = s.acl + 8 + sum(map(len, s.aces[:i]))
        return 1

    monkeypatch.setattr(iso, '_GetSecurityInfoByNameW', get_security)
    monkeypatch.setattr(iso, '_GetAclInformation', get_info)
    monkeypatch.setattr(iso, '_GetAce', get_ace)
    monkeypatch.setattr(iso, '_LocalFree', lambda p: s.freed.append(p.value))
    return s


@pytest.mark.skipif(iso.WindowsBoundary is None, reason='the Windows boundary')
class TestDaclReadOnWindows:
    PATH = 'C:\\synthetic\\never-read'

    @pytest.mark.parametrize('label,setup,reason', [
        ('the descriptor cannot be read', {'error': 5}, 'dacl_unreadable'),
        ('the ACL cannot be sized', {'info_ok': False, 'aces': [A_EVERYONE]}, 'dacl_unreadable'),
        ('an ACE cannot be fetched', {'aces': [A_EVERYONE] * 3, 'fail_at': 1}, 'dacl_unreadable'),
        ('an ACE pointer is null', {'aces': [A_EVERYONE], 'null_at': 0}, 'dacl_unreadable'),
        ('an ACE type it does not read', {'aces': [A_EVERYONE, OBJECT_ACE]},
         'dacl_unsupported_ace'),
        ('a SID past its ACE', {'aces': [OVERRUN]}, 'dacl_malformed'),
        ('an ACE past the ACL', {'aces': [A_EVERYONE], 'in_use': 12}, 'dacl_malformed'),
    ])
    def test_every_failure_raises_and_frees_the_descriptor(self, winapi, label, setup, reason):
        for k, v in setup.items():
            setattr(winapi, k, v)
        with pytest.raises(iso.IsolationUnavailable) as err:
            iso.WindowsBoundary().dacl(self.PATH)
        assert err.value.reason == reason
        assert winapi.freed == ([] if setup.get('error') else [winapi.sd])

    def test_a_null_dacl_reads_as_everyone_with_everything(self, winapi):
        winapi.null_dacl = True
        assert iso.WindowsBoundary().dacl(self.PATH) == list(iso.NULL_DACL)
        assert winapi.freed == [winapi.sd]

    def test_an_empty_dacl_is_empty_and_not_a_null_one(self, winapi):
        assert iso.WindowsBoundary().dacl(self.PATH) == []
        assert winapi.freed == [winapi.sd]

    def test_a_well_formed_dacl_reads_every_ace(self, winapi):
        winapi.aces = [A_EVERYONE, _ace(0x1, ME, 0x2, 0x10),
                       _ace(0x9, APPC, RX, 0, tail=b'artx\x00\x00\x00\x00')]
        assert iso.WindowsBoundary().dacl(self.PATH) == [
            (0x0, 'S-1-1-0', 0x1200A9, 0), (0x1, ME, 0x2, 0x10), (0x9, APPC, RX, 0)]
        assert winapi.freed == [winapi.sd]

    def test_an_unreadable_package_directory_is_not_an_absent_one(self, tmp_path, monkeypatch):
        w, eid, other = iso.WindowsBoundary(), new_execution_id(), new_execution_id()
        monkeypatch.setenv('LOCALAPPDATA', str(tmp_path))
        assert w.profile_exists(eid) is False                       # absent
        os.makedirs(tmp_path / 'Packages' / iso.profile_name(eid))
        assert w.profile_exists(eid) is True                        # materialized
        (tmp_path / 'Packages' / iso.profile_name(other)).write_bytes(b'')
        with pytest.raises(iso.IsolationUnavailable):               # not a directory
            w.profile_exists(other)
        monkeypatch.delenv('LOCALAPPDATA')
        with pytest.raises(iso.IsolationUnavailable):               # nowhere to look
            w.profile_exists(eid)


# ── ownership-safe recovery: Core deletes only a profile it recorded creating ──

class TestOwnershipRecovery:
    """`owned` is what Core saw the OS answer — that it created this profile — saved
    before anything else can fail. Like every field in the record it is writable by the
    same user, so it is recovery evidence, not an authentication."""

    def test_the_answer_is_on_disk_before_the_job_or_the_invariant(self, tmp_path):
        a, b, req, _ = authority(tmp_path)
        seen = []
        real_job, real_grant = b.create_job, b.grant_established

        def job(execution_id):
            seen.append(('job', a.record(execution_id)))
            return real_job(execution_id)

        def grant(path, sid, access):
            seen.append(('grant', None))
            return real_grant(path, sid, access)

        b.create_job, b.grant_established = job, grant
        rec = a.establish(req)
        step, on_disk = seen[0]
        assert step == 'job' and on_disk.state == 'pending' and on_disk.owned
        assert on_disk.sid == rec.sid == b.derive_sid(req.execution_id)
        assert rec.owned and a.record(req.execution_id).owned

    def test_a_create_that_failed_deletes_nothing(self, tmp_path):
        a, b, req, _ = authority(tmp_path)
        b.create_fail = 'profile_create'
        with pytest.raises(iso.IsolationUnavailable):
            a.establish(req)
        rec = a.record(req.execution_id)
        assert rec.state == 'failed' and rec.reason == 'profile_create' and not rec.owned
        assert b.deleted == []                       # the failure cleanup asks the OS nothing
        assert _sweep(a) == [req.execution_id]       # absent: the record is finished with
        assert a.record(req.execution_id) is None and b.deleted == []

    def test_a_failed_ownership_save_leaves_the_profile_alone(self, tmp_path, monkeypatch):
        a, b, req, _ = authority(tmp_path)
        real_save = iso.Isolation._save

        def save(self, rec):
            if rec.owned:
                raise OSError('disk full (synthetic)')
            return real_save(self, rec)

        monkeypatch.setattr(iso.Isolation, '_save', save)
        with pytest.raises(iso.IsolationUnavailable) as err:     # a failure, not a crash
            a.establish(req)
        assert err.value.reason == 'os_error' and 'disk full' in err.value.detail
        monkeypatch.setattr(iso.Isolation, '_save', real_save)
        kept = a.record(req.execution_id)
        assert kept.state == 'failed' and kept.reason == 'os_error' and not kept.owned
        name = iso.profile_name(req.execution_id)
        assert b.deleted == [] and b.launch_calls == []
        assert a.teardown(req.execution_id, reason='ended')['profile'] == 'provenance_unknown'
        assert _sweep(a) == [] and a.reclaim(live_execution_ids=[]) == []
        assert b.deleted == [] and name in b.profiles

    def test_a_profile_that_was_there_before_a_failed_answer_is_kept(self, tmp_path):
        # the OS said the profile already stood, then reading its SID failed: nothing on
        # disk says Core made it, so neither the failure cleanup nor any pass deletes it
        a, b, req, _ = authority(tmp_path)
        name = iso.profile_name(req.execution_id)
        b.profiles.add(name)

        def create(execution_id):
            b.created.append(name)
            raise iso.IsolationUnavailable('profile_derive', 'synthetic')

        b.create_profile = create
        with pytest.raises(iso.IsolationUnavailable):
            a.establish(req)
        assert b.deleted == [] and name in b.profiles
        assert a.teardown(req.execution_id, reason='ended')['profile'] == 'provenance_unknown'
        assert a.reclaim(live_execution_ids=[]) == [] and _sweep(a) == []
        assert b.deleted == [] and name in b.profiles

    def _resume_that_dies(self, tmp_path):
        a, b, req, _ = authority(tmp_path)
        first = a.establish(req)
        real_create = b.create_profile

        def crash(execution_id):
            raise RuntimeError('simulated hard Core crash during the resume')

        b.create_profile = crash
        after = iso.Isolation(FakeNode(), boundary=b)        # the Job died with the old Core
        with pytest.raises(RuntimeError):
            after.establish(req)
        b.create_profile = real_create
        return b, req, first

    def test_a_resume_that_dies_keeps_its_ownership_and_sid(self, tmp_path):
        b, req, first = self._resume_that_dies(tmp_path)
        mid = iso.Isolation(FakeNode(), boundary=b).record(req.execution_id)
        assert mid.state == 'pending' and mid.owned and mid.sid == first.sid
        again = iso.Isolation(FakeNode(), boundary=b).establish(req)   # its retry
        assert again.state == 'established' and again.owned and again.sid == first.sid
        assert not again.preexisting and b.deleted == []

    def test_a_resume_that_dies_is_still_cores_to_delete(self, tmp_path):
        b, req, first = self._resume_that_dies(tmp_path)
        a = iso.Isolation(FakeNode(), boundary=b)
        assert a.reclaim(live_execution_ids=[]) == [req.execution_id]
        assert b.deleted == [first.profile] and a.record(req.execution_id) is None

    @pytest.mark.parametrize('route', ['teardown', 'reclaim', 'sweep', 'ledger'])
    def test_every_deletion_route_requires_recorded_ownership(self, tmp_path, route):
        node, b = FakeNode(), FakeBoundary()
        a = iso.Isolation(node, boundary=b)
        eid = new_execution_id()
        name = iso.profile_name(eid)
        b.profiles.add(name)                     # standing, and nothing says Core made it
        if route == 'ledger':
            _ledger({'op': 'quarantine', 'execution_id': eid, 'profile': name,
                     'sid': b.derive_sid(eid), 'planned': [], 'reason': 'x', 'at': 1.0})
        else:
            _plant(eid + '.json', _good_record(b, eid))      # valid, but without `owned`
        run = {'teardown': lambda: a.teardown(eid, reason='ended')['profile'],
               'reclaim': lambda: a.reclaim(live_execution_ids=[]),
               'sweep': lambda: _sweep(a),
               'ledger': lambda: a.reclaim(live_execution_ids=[])}[route]
        for _ in range(3):
            assert run() in ('provenance_unknown', [])
        assert b.deleted == [] and name in b.profiles
        kept = a.record(eid)
        assert kept.state == 'failed' and kept.reason == 'provenance_unknown'
        assert kept.sid == b.derive_sid(eid) and not kept.owned
        assert [x['op'] for x in node.registry] == ['isolation_provenance_unknown']

    def test_an_unreadable_profile_state_is_not_absence(self, tmp_path):
        node, b = FakeNode(), FakeBoundary()
        a = iso.Isolation(node, boundary=b)
        eid = new_execution_id()
        _plant(eid + '.json', _good_record(b, eid, state='pending', sid=''))
        b.presence_fail = True
        assert a.teardown(eid, reason='ended')['profile'] == 'provenance_unknown'
        kept = a.record(eid)
        assert kept.reason == 'provenance_unknown' and kept.sid == b.derive_sid(eid)
        assert b.deleted == []


# ── S2-G preparatory: an unsettled record is never a new start ────────────────

UNSETTLED = [
    ('quarantined', dict(state='quarantined', reason='profile_delete: in use', owned=True)),
    ('failed', dict(state='failed', reason='condition_unmet:grants',
                    failure='condition_unmet:grants', owned=True)),
    ('failed, then quarantined by its cleanup',
     dict(state='quarantined', reason='process_unverified', failure='condition_unmet:grants',
          owned=True)),
    ('provenance unknown', dict(state='failed', reason='provenance_unknown')),
    ('a torn-down record whose removal failed', dict(state='torn_down', reason='ended', sid='')),
    ('established, but carrying a failure', dict(failure='launch', owned=True)),
]


class TestUnsettledRecords:
    """D1: `establish` used to reset any prior record to pending and create again, so
    a Core that crashed between quarantining an identity and refusing its execution
    would resume a process under the quarantined identity. D2: the cleanup after a
    failed establishment overwrote the failure with its own reason."""

    @pytest.mark.parametrize('label,over', UNSETTLED)
    def test_an_unsettled_record_is_refused_before_anything_is_written(self, tmp_path,
                                                                       label, over):
        a, b, req, node = authority(tmp_path)
        eid = req.execution_id
        b.profiles.add(iso.profile_name(eid))
        path, before = _plant(eid + '.json', _good_record(b, eid, **over))
        _ledger({'op': 'quarantine', 'execution_id': eid, 'profile': iso.profile_name(eid),
                 'sid': b.derive_sid(eid), 'planned': [], 'reason': 'x', 'at': 1.0})
        ledger = _ledger_bytes()
        with pytest.raises(iso.IsolationUnavailable) as err:
            a.establish(req)
        assert err.value.reason == 'record_unsettled'
        with open(path, 'rb') as f:
            assert f.read() == before
        assert _ledger_bytes() == ledger
        assert b.mutations() == [] and b.closed == [] and b.looked == []
        assert a.held_job(eid) is None and node.registry == []

    def test_a_refused_resume_launches_nothing(self, tmp_path, monkeypatch):
        a, b, req, _ = authority(tmp_path)
        eid = req.execution_id
        _plant(eid + '.json', _good_record(b, eid, **dict(UNSETTLED[0][1])))
        with pytest.raises(base.SpawnFailed) as err:
            _launch(a, req, monkeypatch)
        assert 'record_unsettled' in str(err.value)
        assert b.launch_calls == [] and b.created == [] and a.launched(eid) is None

    def test_a_paused_resume_reuses_its_identity(self, tmp_path):
        a, b, req, _ = authority(tmp_path)
        first = a.establish(req)
        again = iso.Isolation(FakeNode(), boundary=b).establish(req)   # after a restart
        assert again.state == 'established' and again.sid == first.sid and again.owned
        assert b.deleted == []

    def test_cleanup_never_overwrites_the_establishment_failure(self, tmp_path):
        a, b, req, _ = authority(tmp_path)
        name = iso.profile_name(req.execution_id)
        b.grant_ok, b.delete_fail = False, {name}
        with pytest.raises(iso.IsolationUnavailable) as err:
            a.establish(req)
        failure = err.value.reason
        assert failure.startswith('condition_unmet:')
        for attempt in (1, 2, 3):
            rec = a.record(req.execution_id)
            assert rec.state == 'quarantined' and rec.failure == failure
            assert rec.attempts == attempt
            assert _sweep(a) == []
        b.delete_fail = set()
        assert _sweep(a) == [req.execution_id] and a.record(req.execution_id) is None

    @pytest.mark.parametrize('state', ['PAUSED', 'INTENT', 'AWAITING_APPROVAL'])
    def test_a_failure_later_quarantined_is_still_refused_uncharged(self, state):
        m = _manager_with_fake_node()
        rec = iso.IsolationRecord(execution_id='x', profile='p', state='quarantined',
                                  reason='process_unverified',
                                  failure='condition_unmet:grants')
        assert m._reconcile_isolated(_e(state), object(), rec, None, disarmed=False) is True
        (command, kw), = m.calls
        assert command is X.refuse and kw['stop_reason'] == 'binding'
        assert kw['reason'].endswith('condition_unmet:grants')


# ── F6-F9: a release is believed once it is seen, and only after its process ──

def _ops():
    return _ledger_ops() if os.path.exists(quarantine_log()) else []


def _ledger_bytes():
    with open(quarantine_log(), 'rb') as f:
        return f.read()


def _launch(a, req, monkeypatch, created=777):
    """Core's own isolated launch of *req* through the real `IsolationContext`, with the
    creation time it records pinned: nothing real is started or read."""
    from archeus.infra.paths import ExecPaths
    monkeypatch.setattr(iso, 'base_create_time', lambda pid: created)
    child, _ = iso.IsolationContext(a, req).launch(['fake'], cwd=req.workspace, env={},
                                                   paths=ExecPaths(req.execution_id))
    return child


def _released_line(b, eid):
    """A quarantine, then its release, as an earlier Core wrote them; returns the bytes."""
    _ledger({'op': 'quarantine', 'execution_id': eid, 'profile': iso.profile_name(eid),
             'sid': b.derive_sid(eid), 'planned': [], 'reason': 'x', 'at': 1.0},
            {'op': 'released', 'execution_id': eid, 'at': 2.0})
    return _ledger_bytes()


class TestRecoveryCorrectness:
    """F6-F9 of the recovery review. A profile is released only once the boundary has
    been seen to answer that it is gone, and the ledger's `released` means exactly that
    (F6, F8); one execution's failed write is that execution's alone (F7); and nothing is
    deleted while the process launched under it may still run (F9)."""

    # ── F6: a delete is believed only once the profile is seen gone ──

    @pytest.mark.parametrize('before', ['standing', 'already gone'])
    def test_a_delete_seen_through_is_a_release(self, tmp_path, before):
        a, b, req, _ = authority(tmp_path)
        rec = a.establish(req)
        if before == 'already gone':
            b.profiles.discard(rec.profile)              # the OS will answer "not found"
        assert a.teardown(req.execution_id, reason='ended')['profile'] == 'torn_down'
        assert b.deleted == [rec.profile] and b.looked == [rec.profile]
        assert a.record(req.execution_id) is None and _ops() == []

    @pytest.mark.parametrize('route', ['teardown', 'stale record', 'ledger',
                                       'failed establishment'])
    def test_a_delete_that_leaves_the_profile_standing_is_not_a_release(self, tmp_path,
                                                                          route):
        a, b, req, node = authority(tmp_path)
        eid, name = req.execution_id, iso.profile_name(req.execution_id)
        b.delete_leaves.add(name)
        if route == 'failed establishment':
            b.broad = 'S-1-1-0'
            with pytest.raises(iso.IsolationUnavailable):
                a.establish(req)
            b.broad = None
        else:
            a.establish(req)
        if route == 'teardown':
            assert a.teardown(eid, reason='ended')['profile'] == 'quarantined'
        elif route == 'stale record':
            a = iso.Isolation(node, boundary=b)          # a later Core finds the record
            assert a.reclaim(live_execution_ids=[]) == []
        elif route == 'ledger':
            b.delete_fail.add(name)
            a.teardown(eid, reason='ended')              # quarantined: in use
            b.delete_fail.clear()
            assert a.reclaim(live_execution_ids=[]) == []
        kept = a.record(eid)
        assert kept.state == 'quarantined' and kept.reason == 'profile_delete_unverified'
        assert kept.owned and kept.sid == b.derive_sid(eid) and name in b.profiles
        assert 'released' not in _ops() and eid in a.quarantined()
        lines = _ops()
        for _ in range(3):                               # retried, never re-announced
            assert _sweep(a) == []
        assert _ops() == lines and a.record(eid).attempts >= 4
        b.delete_leaves.discard(name)                    # the OS finally lets it go
        assert _sweep(a) == [eid]
        assert _ops() == lines + ['released'] and a.record(eid) is None
        for _ in range(2):
            assert _sweep(a) == []
        assert _ops() == lines + ['released']

    @pytest.mark.parametrize('answer', ['raises', 'no answer'])
    def test_a_profile_whose_presence_cannot_be_read_after_its_delete_is_kept(
            self, tmp_path, answer):
        a, b, req, _ = authority(tmp_path)
        eid = req.execution_id
        rec = a.establish(req)
        if answer == 'raises':
            b.presence_fail = True
        else:
            b.profile_exists = lambda execution_id: None
        assert a.teardown(eid, reason='ended')['profile'] == 'quarantined'
        kept = a.record(eid)
        assert kept.state == 'quarantined' and kept.reason == 'profile_presence_unknown'
        assert kept.sid == rec.sid and _ops() == ['quarantine']
        for _ in range(3):
            assert _sweep(a) == []
        assert _ops() == ['quarantine'] and a.record(eid).sid == rec.sid
        b.presence_fail = False
        b.__dict__.pop('profile_exists', None)
        assert _sweep(a) == [eid] and _ops() == ['quarantine', 'released']

    # ── F7: one execution's failed write is that execution's alone ──

    @pytest.mark.parametrize('loop', ['stale records', 'ledger'])
    def test_a_failed_write_for_one_execution_does_not_stop_the_next(self, tmp_path,
                                                                       monkeypatch, loop):
        a, b, first, node = authority(tmp_path)
        second = make_satisfying_request(new_execution_id(), str(tmp_path))
        assert first.execution_id < second.execution_id     # sorted: the first goes first
        a.establish(first)
        a.establish(second)
        if loop == 'ledger':
            b.delete_fail.add(iso.profile_name(first.execution_id))
            a.teardown(first.execution_id, reason='ended')     # on the ledger
            b.delete_fail.clear()
        real_save = iso.Isolation._save
        fault = ['disk full (synthetic)']

        def save(self, rec):
            if rec.execution_id == first.execution_id and fault[0]:
                raise OSError(fault[0])
            return real_save(self, rec)

        monkeypatch.setattr(iso.Isolation, '_save', save)
        later = iso.Isolation(node, boundary=b)
        assert later.reclaim(live_execution_ids=[]) == [second.execution_id]
        assert later.record(second.execution_id) is None
        assert later.record(first.execution_id) is not None    # kept for the retry
        assert later.faults == {first.execution_id: 'disk full (synthetic)'}
        for _ in range(3):                                     # the same fault, said once
            assert later.reclaim(live_execution_ids=[]) == []

        def said():
            return [(x['execution_id'], x['reason']) for x in node.registry
                    if x.get('op') == 'isolation_fault']

        assert said() == [(first.execution_id, 'disk full (synthetic)')]
        fault[0] = 'access denied (synthetic)'                 # a different one is said too
        assert later.reclaim(live_execution_ids=[]) == []
        assert said()[1:] == [(first.execution_id, 'access denied (synthetic)')]
        fault[0] = None                                        # and recovery clears it
        assert later.reclaim(live_execution_ids=[]) == [first.execution_id]
        assert later.faults == {} and later.record(first.execution_id) is None
        assert len(said()) == 2

    def test_only_a_persistence_error_is_contained(self, tmp_path, monkeypatch):
        a, b, req, _ = authority(tmp_path)
        a.establish(req)

        def broken(self, rec):
            raise ValueError('a bug, not a fault (synthetic)')

        monkeypatch.setattr(iso.Isolation, '_save', broken)
        with pytest.raises(ValueError):
            iso.Isolation(FakeNode(), boundary=b).reclaim(live_execution_ids=[])

    def test_a_ledger_that_cannot_be_read_is_the_whole_sweeps_fault(self, tmp_path):
        a, b, req, _ = authority(tmp_path)
        a.establish(req)
        os.makedirs(quarantine_log())                   # there, and not readable as a file
        with pytest.raises(OSError):
            a.reclaim(live_execution_ids=[])
        assert a.faults == {} and b.deleted == []

    # ── F8: a released line is believed only while the profile is seen gone ──

    def test_a_release_seen_through_settles_and_costs_nothing_more(self, tmp_path):
        node, b = FakeNode(), FakeBoundary()
        a = iso.Isolation(node, boundary=b)
        eid = new_execution_id()
        written = _released_line(b, eid)
        for _ in range(3):
            assert a.reclaim(live_execution_ids=[]) == [] and _sweep(a) == []
        assert b.looked == [iso.profile_name(eid)]          # seen gone once, then settled
        assert b.mutations() == [] and a.record(eid) is None and a.invalid == {}
        assert _ledger_bytes() == written and node.registry == []

    @pytest.mark.parametrize('presence', ['present', 'unknown'])
    def test_a_release_the_profile_contradicts_is_reported_once_and_kept(self, tmp_path,
                                                                          presence):
        node, b = FakeNode(), FakeBoundary()
        a = iso.Isolation(node, boundary=b)
        eid = new_execution_id()
        name = iso.profile_name(eid)
        written = _released_line(b, eid)
        if presence == 'present':
            b.profiles.add(name)
        else:
            b.presence_fail = True
        for _ in range(3):
            assert a.reclaim(live_execution_ids=[]) == [] and _sweep(a) == []
        assert b.deleted == [] and _ledger_bytes() == written    # history as written
        assert a.invalid == {'quarantine.jsonl:2': 'released_but_' + presence}
        kept = a.record(eid)                                     # recovery goes on
        assert kept.state == 'failed' and kept.reason == 'provenance_unknown'
        assert kept.sid == b.derive_sid(eid) and not kept.owned
        assert sorted(x['op'] for x in node.registry) == ['isolation_invalid',
                                                         'isolation_provenance_unknown']
        b.profiles.discard(name)                                 # seen gone at last
        b.presence_fail = False
        assert a.reclaim(live_execution_ids=[]) == [eid]
        assert a.record(eid) is None and b.deleted == []
        for _ in range(2):
            assert a.reclaim(live_execution_ids=[]) == []
        assert len(node.registry) == 2 and _ledger_bytes() == written

    @pytest.mark.parametrize('presence', ['absent', 'present', 'unknown'])
    def test_a_release_never_overrides_a_record(self, tmp_path, presence):
        a, b, req, node = authority(tmp_path)
        eid, name = req.execution_id, iso.profile_name(req.execution_id)
        rec = a.establish(req)                             # a later lifecycle's record
        written = _released_line(b, eid)
        if presence == 'absent':
            b.profiles.discard(name)
        elif presence == 'unknown':
            b.presence_fail = True
        later = iso.Isolation(node, boundary=b)
        done = later.reclaim(live_execution_ids=[])
        assert b.deleted == [name]                         # still Core's to delete
        assert _ledger_bytes().startswith(written) and later.invalid == {}
        if presence == 'unknown':
            assert done == []
            kept = later.record(eid)
            assert kept.state == 'quarantined' and kept.reason == 'profile_presence_unknown'
            assert kept.sid == rec.sid
            assert _ops() == ['quarantine', 'released', 'quarantine']   # a new fact
        else:
            assert done == [eid] and later.record(eid) is None
            assert _ops() == ['quarantine', 'released']    # nothing said twice
            assert later.reclaim(live_execution_ids=[]) == []
            assert _ops() == ['quarantine', 'released']

    # ── F9: no profile goes while the process launched under it may still run ──

    def test_launch_holds_the_process_before_anything_can_fail(self, tmp_path, monkeypatch):
        a, b, req, _ = authority(tmp_path)
        real_save = iso.Isolation._save

        def save(self, rec):
            if rec.pid is not None:
                raise OSError('disk full (synthetic)')
            return real_save(self, rec)

        monkeypatch.setattr(iso.Isolation, '_save', save)
        with pytest.raises(base.SpawnFailed):
            _launch(a, req, monkeypatch)
        monkeypatch.setattr(iso.Isolation, '_save', real_save)
        child = a.launched(req.execution_id)
        assert child is not None and a.record(req.execution_id).pid is None
        assert a.teardown(req.execution_id, reason='ended')['profile'] == 'busy'
        assert b.deleted == [] and b.probed == []
        child.returncode = 0
        assert _sweep(a) == [req.execution_id]
        assert b.deleted == [iso.profile_name(req.execution_id)]

    def test_a_process_core_holds_is_waited_for_by_its_handle(self, tmp_path, monkeypatch):
        a, b, req, _ = authority(tmp_path)
        eid, name = req.execution_id, iso.profile_name(req.execution_id)
        child = _launch(a, req, monkeypatch)
        out = a.teardown(eid, reason='ended')             # the Job closed; the root lives
        assert out['job'] == 'closed' and out['profile'] == 'busy'
        assert child.waits == [iso.EXIT_WAIT_S] and b.probed == []   # by handle, not PID
        kept = a.record(eid)
        assert kept.state == 'quarantined' and kept.reason == 'process_alive'
        assert kept.sid == b.derive_sid(eid) and b.deleted == [] and name in b.profiles
        for _ in range(3):                                # retried, never re-announced
            assert _sweep(a) == []
        assert _ops() == ['quarantine'] and b.deleted == []
        child.returncode = 0                              # it exits
        assert _sweep(a) == [eid] and b.deleted == [name]
        assert _ops() == ['quarantine', 'released'] and a.launched(eid) is None
        assert child.waits[1:] == [0, 0, 0, 0]            # a retry does not wait again

    def test_an_exited_process_lets_its_profile_go(self, tmp_path, monkeypatch):
        a, b, req, _ = authority(tmp_path)
        child = _launch(a, req, monkeypatch)
        child.returncode = 0
        assert a.teardown(req.execution_id, reason='ended')['profile'] == 'torn_down'
        assert b.deleted == [iso.profile_name(req.execution_id)] and b.probed == []
        assert a.launched(req.execution_id) is None

    @pytest.mark.parametrize('label,created,running,unreadable,outcome', [
        ('nothing runs under its PID', 777, {}, False, 'torn_down'),
        ('it still runs', 777, {424242: 777}, False, 'process_alive'),
        ('another process reuses its PID', 777, {424242: 778}, False, 'torn_down'),
        ('its creation time was never read, and the PID runs', None, {424242: 5}, False,
         'process_unverified'),
        ('its creation time was never read, and nothing runs', None, {}, False, 'torn_down'),
        ('what runs under its PID cannot be read', 777, {424242: 777}, True,
         'process_unverified'),
    ])
    def test_without_its_handle_a_process_is_its_pid_and_creation_time(
            self, tmp_path, monkeypatch, label, created, running, unreadable, outcome):
        a, b, req, node = authority(tmp_path)
        eid, name = req.execution_id, iso.profile_name(req.execution_id)
        _launch(a, req, monkeypatch, created=created)
        later = iso.Isolation(node, boundary=b)          # restarted: no handle, no Job
        b.processes, b.process_unreadable = dict(running), unreadable
        out = later.teardown(eid, reason='stale')
        assert b.probed == [424242]                      # no Job closed here: one look
        if outcome == 'torn_down':
            assert out['profile'] == 'torn_down' and b.deleted == [name]
            return
        assert out['profile'] == 'busy' and b.deleted == [] and name in b.profiles
        kept = later.record(eid)
        assert kept.state == 'quarantined' and kept.reason == outcome
        assert kept.sid == b.derive_sid(eid)
        assert kept.pid == 424242 and kept.create_time == created

    def test_a_busy_profile_goes_once_its_process_has(self, tmp_path, monkeypatch):
        a, b, req, node = authority(tmp_path)
        eid, name = req.execution_id, iso.profile_name(req.execution_id)
        _launch(a, req, monkeypatch)
        later = iso.Isolation(node, boundary=b)
        b.processes = {424242: 777}
        assert later.teardown(eid, reason='stale')['profile'] == 'busy'
        for _ in range(3):
            assert _sweep(later) == []
        assert _ops() == ['quarantine'] and b.deleted == []
        b.processes = {}
        assert _sweep(later) == [eid] and b.deleted == [name]
        assert _ops() == ['quarantine', 'released'] and later.record(eid) is None

    @pytest.mark.parametrize('exits', [False, True])
    def test_the_wait_after_the_job_closes_is_bounded(self, tmp_path, monkeypatch, exits):
        monkeypatch.setattr(iso, 'EXIT_WAIT_S', 0.3)
        a, b, req, _ = authority(tmp_path)
        rec = a.establish(req)                           # Core holds the Job...
        rec.pid, rec.create_time = 4242, 777             # ...and no handle for this one
        a._save(rec)
        b.processes = {4242: 777}
        if exits:
            real = b.process_started

            def dying(pid):
                if len(b.probed) == 2:
                    b.processes.clear()
                return real(pid)

            b.process_started = dying
        start = time.monotonic()
        out = a.teardown(req.execution_id, reason='ended')
        took = time.monotonic() - start
        if exits:
            assert out['profile'] == 'torn_down' and len(b.probed) == 3
        else:
            assert out['profile'] == 'busy' and took >= 0.3 and len(b.probed) > 2
            assert b.deleted == []

    @pytest.mark.parametrize('route', ['teardown', 'stale record', 'ledger',
                                       'failed establishment'])
    def test_every_deletion_route_waits_for_the_process(self, tmp_path, monkeypatch, route):
        monkeypatch.setattr(iso, 'EXIT_WAIT_S', 0)
        a, b, req, node = authority(tmp_path)
        eid, name = req.execution_id, iso.profile_name(req.execution_id)
        _launch(a, req, monkeypatch)                     # pid 424242, created 777
        a = iso.Isolation(node, boundary=b)              # no handle from here on
        b.processes = {424242: 777}                      # and it still runs
        if route == 'teardown':
            a.teardown(eid, reason='ended')
        elif route in ('stale record', 'ledger'):
            if route == 'ledger':
                _ledger({'op': 'quarantine', 'execution_id': eid, 'profile': name,
                         'sid': b.derive_sid(eid), 'planned': [], 'reason': 'x', 'at': 1.0})
            assert a.reclaim(live_execution_ids=[]) == []
        else:
            b.broad = 'S-1-1-0'
            with pytest.raises(iso.IsolationUnavailable):
                a.establish(req)                         # its resume fails to establish
        assert b.deleted == [] and name in b.profiles
        kept = a.record(eid)
        assert kept.state == 'quarantined' and kept.reason == 'process_alive'
        assert kept.sid == b.derive_sid(eid)


# ── F9: the real process probe, over mocked Win32 calls (Windows only) ──────────

@pytest.fixture
def procapi(monkeypatch):
    """`process_started`'s Win32 calls replaced by fakes, so the real probe runs and no
    real process is opened (the tripwire stays armed beneath them)."""
    s = SimpleNamespace(open_error=None, code=259, code_ok=True, times_ok=True,
                        created=(0x01DB1234, 0x89ABCDEF), closed=[], last=0)

    def open_process(access, inherit, pid):
        if s.open_error is not None:
            s.last = s.open_error
            return None
        return 0x5150

    def exit_code(h, ref):
        if not s.code_ok:
            s.last = 6
            return 0
        ref._obj.value = s.code
        return 1

    def times(h, created, exited, kernel, user):
        if not s.times_ok:
            s.last = 5
            return 0
        created._obj.dwHighDateTime, created._obj.dwLowDateTime = s.created
        return 1

    monkeypatch.setattr(iso, '_OpenProcess', open_process)
    monkeypatch.setattr(iso, '_GetExitCodeProcess', exit_code)
    monkeypatch.setattr(iso, '_GetProcessTimes', times)
    monkeypatch.setattr(iso, '_CloseHandle', s.closed.append)
    monkeypatch.setattr(iso, '_err', lambda: s.last)
    return s


@pytest.mark.skipif(iso.WindowsBoundary is None, reason='the Windows boundary')
class TestProcessProbeOnWindows:
    @pytest.mark.parametrize('label,setup,answer', [
        ('nothing has the PID', {'open_error': 87}, None),
        ('it has exited', {'code': 0}, None),
        # the encoding `proc.process_create_time` records, so the two compare
        ('it runs', {}, (0x01DB1234 << 32) | 0x89ABCDEF),
    ])
    def test_what_runs_under_a_pid(self, procapi, label, setup, answer):
        for k, v in setup.items():
            setattr(procapi, k, v)
        assert iso.WindowsBoundary().process_started(4242) == answer
        assert procapi.closed == ([] if 'open_error' in setup else [0x5150])

    @pytest.mark.parametrize('label,setup', [
        ('the open is refused', {'open_error': 5}),
        ('the exit code cannot be read', {'code_ok': False}),
        ('the creation time cannot be read', {'times_ok': False}),
    ])
    def test_an_unreadable_process_is_not_an_exited_one(self, procapi, label, setup):
        for k, v in setup.items():
            setattr(procapi, k, v)
        with pytest.raises(iso.IsolationUnavailable) as err:
            iso.WindowsBoundary().process_started(4242)
        assert err.value.reason == 'process_state'
        assert procapi.closed == ([] if 'open_error' in setup else [0x5150])


# ── C3: a write that fails is one execution's failure, never Core's ──────────────

def _release(a, eid):
    """The manager's own end-path release, over a LocalNode carrying *a*."""
    return M.ExecutionManager._release_isolation(
        SimpleNamespace(node=LocalNode(isolation=a)), SimpleNamespace(id=eid))


def _writes_fail(monkeypatch, when=lambda rec: True):
    """Every record write matching *when* raises the `OSError` a full disk would; the
    real `_save` is returned so a test can put it back."""
    real = iso.Isolation._save

    def save(self, rec):
        if when(rec):
            raise OSError('disk full (synthetic)')
        return real(self, rec)

    monkeypatch.setattr(iso.Isolation, '_save', save)
    return real


def _not_resumed(b, child):
    """The boundary created the process and could not resume it: it terminated it and
    hands its handle back on the error, as `WindowsBoundary.launch` does."""
    def launch(*args, **kw):
        err = iso.IsolationUnavailable('process_resume', 'previous suspend count 2, not 1')
        err.child = child
        raise err
    b.launch = launch


class TestPersistenceFaults:
    """C3. Persistence raises `OSError`; outside the sweep it used to escape `tick` and
    stop Core, whose exit closes every Job it holds. It is now the failing execution's
    alone: a setup that cannot write starts nothing, a cleanup that cannot write never
    replaces the failure being reported, and the end path leaves the record on disk for
    the sweep. Ownership is read from disk throughout, so no fault widens a deletion."""

    @pytest.mark.parametrize('lost_from,created,on_disk', [
        (1, False, None),                       # the pending record
        (2, True, 'unowned'),                   # the ownership answer
        (3, True, 'owned'),                     # the established record
    ])
    def test_a_setup_that_cannot_write_starts_nothing(self, tmp_path, monkeypatch, lost_from,
                                                      created, on_disk):
        a, b, req, _ = authority(tmp_path)
        eid, name = req.execution_id, iso.profile_name(req.execution_id)
        writes = []
        real = _writes_fail(monkeypatch, lambda rec: writes.append(rec.state) or
                            len(writes) >= lost_from)          # the disk is gone from there on
        with pytest.raises(iso.IsolationUnavailable) as err:   # a failure, not a crash
            a.establish(req)
        assert err.value.reason == 'os_error' and 'disk full' in err.value.detail
        assert 'cleanup incomplete' in err.value.detail
        monkeypatch.setattr(iso.Isolation, '_save', real)
        assert (name in b.created) is created and b.launch_calls == []
        kept = a.record(eid)
        if on_disk is None:
            assert kept is None and b.deleted == []
            return
        assert kept.state == 'pending' and kept.owned is (on_disk == 'owned')
        if on_disk == 'unowned':
            assert b.deleted == []                             # nothing says it is Core's
            _release(a, eid)
            assert a.record(eid).reason == 'provenance_unknown' and b.deleted == []
            return
        assert b.deleted == [name]                             # Core's, by its record
        _release(a, eid)                                       # and finished from the record
        assert a.record(eid) is None and b.deleted == [name, name]

    @pytest.mark.parametrize('fault', ['record', 'ledger', 'registry'])
    def test_a_cleanup_write_that_fails_never_replaces_the_failure(self, tmp_path, monkeypatch,
                                                                   fault):
        a, b, req, node = authority(tmp_path)
        eid, name = req.execution_id, iso.profile_name(req.execution_id)
        b.broad = 'S-1-1-0'                                    # condition 3 does not hold
        real = None
        if fault == 'record':
            real = _writes_fail(monkeypatch, lambda rec: rec.state == 'failed')
        elif fault == 'ledger':
            b.delete_fail.add(name)                            # quarantined, on a ledger
            os.makedirs(quarantine_log())                      # that cannot take its line
        else:
            def full(line):
                raise OSError('registry unwritable (synthetic)')
            node._registry = full
        with pytest.raises(iso.IsolationUnavailable) as err:
            a.establish(req)
        assert err.value.reason == 'condition_unmet:no_broad_grants'
        assert 'cleanup incomplete' in err.value.detail and b.launch_calls == []
        # the fault goes away, and the record on disk is enough to finish
        if real is not None:
            monkeypatch.setattr(iso.Isolation, '_save', real)
        if fault == 'ledger':
            os.rmdir(quarantine_log())
            b.delete_fail.clear()
        node.__dict__.pop('_registry', None)
        b.broad = None
        assert _sweep(a) == [eid]
        assert a.record(eid) is None and name not in b.profiles

    def test_one_executions_failed_release_does_not_stop_the_next(self, tmp_path, caplog):
        a, b, first, node = authority(tmp_path)
        second = make_satisfying_request(new_execution_id(), str(tmp_path))
        a.establish(first)
        a.establish(second)
        stuck, fine = (iso.profile_name(first.execution_id),
                       iso.profile_name(second.execution_id))
        b.delete_fail.add(stuck)                               # its delete is refused,
        os.makedirs(quarantine_log())                          # and its ledger line is lost
        with caplog.at_level('WARNING', logger='archeus.execution'):
            _release(a, first.execution_id)                    # the OSError stops here,
            _release(a, second.execution_id)                   # and the next one goes on
        assert 'isolation release did not complete' in caplog.text
        assert first.execution_id in caplog.text and second.execution_id not in caplog.text
        assert b.deleted.count(fine) == 1 and a.record(second.execution_id) is None
        kept = a.record(first.execution_id)
        assert kept.state == 'quarantined' and kept.owned and stuck in b.profiles
        assert kept.sid == b.derive_sid(first.execution_id)
        os.rmdir(quarantine_log())                             # recovered by the sweep
        b.delete_fail.clear()
        assert _sweep(a) == [first.execution_id] and stuck not in b.profiles

    def test_the_release_contains_a_write_failure_and_nothing_else(self, tmp_path,
                                                                  monkeypatch):
        a, b, req, _ = authority(tmp_path)
        a.establish(req)

        def bug(self, execution_id, *, reason=''):
            raise ValueError('a bug, not a fault (synthetic)')

        monkeypatch.setattr(iso.Isolation, 'teardown', bug)
        with pytest.raises(ValueError):
            _release(a, req.execution_id)

    def test_a_spawn_failure_outlives_a_registry_that_cannot_take_its_line(self, tmp_path):
        a, b, req, node = authority(tmp_path)

        def full(line):
            raise OSError('registry unwritable (synthetic)')

        node._registry = full
        spec = SimpleNamespace(isolation=object(), execution_id=req.execution_id)
        assert a.note_failure(spec, base.SpawnFailed('isolation: synthetic')) is None

    def test_a_held_process_survives_a_release_whose_writes_fail(self, tmp_path, monkeypatch):
        a, b, req, _ = authority(tmp_path)
        eid, name = req.execution_id, iso.profile_name(req.execution_id)
        held = FakeChild()
        _not_resumed(b, held)
        with pytest.raises(base.SpawnFailed):
            _launch(a, req, monkeypatch)
        real = _writes_fail(monkeypatch)
        _release(a, eid)                                       # the Job closes; no write lands
        assert a.launched(eid) is held and held.waits == [iso.EXIT_WAIT_S]
        assert b.deleted == []
        monkeypatch.setattr(iso.Isolation, '_save', real)
        assert _sweep(a) == [] and b.deleted == []             # it still runs: still waited on
        held.returncode = 1
        assert _sweep(a) == [eid] and b.deleted == [name] and a.launched(eid) is None


# ── C11: a process that was not resumed is never named launched ──────────────────

class TestNotResumed:
    def test_it_is_held_by_its_handle_and_its_record_names_no_process(self, tmp_path,
                                                                      monkeypatch):
        a, b, req, _ = authority(tmp_path)
        eid, name = req.execution_id, iso.profile_name(req.execution_id)
        held = FakeChild()
        _not_resumed(b, held)
        with pytest.raises(base.SpawnFailed) as err:
            _launch(a, req, monkeypatch)
        assert 'process_resume' in str(err.value)
        rec = a.record(eid)
        assert rec.pid is None and rec.create_time is None and rec.owned
        assert a.launched(eid) is held
        assert a.teardown(eid, reason='ended')['profile'] == 'busy'
        assert held.waits == [iso.EXIT_WAIT_S] and b.probed == [] and b.deleted == []
        held.returncode = 1
        assert _sweep(a) == [eid] and b.deleted == [name]


# ── C1, C4, C11 on the real boundary, over mocked Win32 calls (Windows only) ─────
# Written from the Windows contract, not from the module: userenv.h states the
# existing-profile answer as HRESULT_FROM_WIN32(ERROR_ALREADY_EXISTS), ERROR_ALREADY_EXISTS
# is 183 (winerror.h), and ctypes reads an HRESULT returned as `c_int` as a signed int.

ALREADY_EXISTS = ctypes.c_int(0x80070000 | 183).value
HANDLE_LIST, SECURITY_CAPABILITIES = 0x00020002, 0x00020009      # WinBase.h
STDIN, STDOUT, OTHER = 0x101, 0x102, 0x103


@pytest.fixture
def profileapi(monkeypatch, tmp_path):
    """`create_profile`'s Win32 call replaced by a fake over a set of profiles that exist.
    It answers as ctypes delivers an HRESULT; nothing real is created or derived."""
    s = SimpleNamespace(existing=set(), answer=None)

    def create(name, display, description, caps, count, ppsid):
        if s.answer is not None:
            return s.answer
        if name in s.existing:
            return ALREADY_EXISTS
        s.existing.add(name)
        return 0

    monkeypatch.setattr(iso, '_CreateAppContainerProfile', create)
    monkeypatch.setattr(iso, '_derive_name', _stable_sid)
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path))
    return s


@pytest.mark.skipif(iso.WindowsBoundary is None, reason='the Windows boundary')
class TestExistingProfileAnswer:
    def test_a_fresh_profile_is_created_and_not_existing(self, profileapi):
        eid = new_execution_id()
        ident = iso.WindowsBoundary().create_profile(eid)
        assert ident['created'] is True and ident['existed'] is False
        assert ident['sid'] == _stable_sid(iso.profile_name(eid))

    def test_the_documented_answer_is_an_existing_profile(self, profileapi):
        eid = new_execution_id()
        profileapi.existing.add(iso.profile_name(eid))
        ident = iso.WindowsBoundary().create_profile(eid)
        assert ident['existed'] is True and ident['created'] is True

    @pytest.mark.parametrize('label,hr', [
        ('E_ACCESSDENIED', 0x80070005),
        ('E_INVALIDARG', 0x80070057),
        ('the constant this replaced, HRESULT of Win32 1324', 0x8007052C),
        ('HRESULT_FROM_WIN32(ERROR_FILE_EXISTS), which is not documented here', 0x80070050),
        ('ERROR_ALREADY_EXISTS as a bare Win32 code, not an HRESULT', 183),
    ])
    def test_every_other_answer_is_a_failure_not_an_existing_profile(self, profileapi, label,
                                                                     hr):
        profileapi.answer = ctypes.c_int(hr).value
        with pytest.raises(iso.IsolationUnavailable) as err:
            iso.WindowsBoundary().create_profile(new_execution_id())
        assert err.value.reason == 'profile_create'

    def test_a_resume_adopts_its_own_profile_and_a_strangers_is_never_deleted(
            self, profileapi, tmp_path):
        class Boundary(FakeBoundary):
            create_profile = iso.WindowsBoundary.create_profile
            package_dir_state = iso.WindowsBoundary.package_dir_state

        a, b, req, node = authority(tmp_path, boundary=Boundary())
        first = a.establish(req)
        assert first.owned and not first.preexisting
        again = iso.Isolation(node, boundary=b).establish(req)       # its resume
        assert again.state == 'established' and again.owned and again.sid == first.sid
        stranger = make_satisfying_request(new_execution_id(), str(tmp_path))
        profileapi.existing.add(iso.profile_name(stranger.execution_id))
        with pytest.raises(iso.IsolationUnavailable) as err:
            a.establish(stranger)
        assert err.value.reason == 'profile_preexisting'
        kept = a.record(stranger.execution_id)
        assert kept.preexisting and not kept.owned and b.deleted == []


@pytest.mark.skipif(iso.WindowsBoundary is None, reason='the Windows boundary')
class TestDeleteProfileAnswer:
    """`delete_profile` reads its answer as ctypes delivers it, a signed int. Compared
    signed, HRESULT_FROM_WIN32(ERROR_NOT_FOUND) never matched and an already-gone
    profile raised."""

    def _delete(self, monkeypatch, hr):
        asked = []
        monkeypatch.setattr(iso, '_DeleteAppContainerProfile',
                            lambda name: asked.append(name) or ctypes.c_int(hr).value)
        eid = new_execution_id()
        try:
            iso.WindowsBoundary().delete_profile(eid)
        finally:
            assert asked == [iso.profile_name(eid)]

    @pytest.mark.parametrize('label,hr', [('S_OK', 0), ('not found: already gone', 0x80070490)])
    def test_the_accepted_answers_are_a_release(self, monkeypatch, label, hr):
        self._delete(monkeypatch, hr)

    @pytest.mark.parametrize('label,hr', [
        ('sharing violation: in use', 0x80070020),
        ('E_ACCESSDENIED', 0x80070005),
        ('ERROR_NOT_FOUND as a bare Win32 code, not an HRESULT', 0x490),
    ])
    def test_every_other_answer_is_a_failure_reported_unsigned(self, monkeypatch, label, hr):
        with pytest.raises(iso.IsolationUnavailable) as err:
            self._delete(monkeypatch, hr)
        assert err.value.reason == 'profile_delete' and err.value.detail == 'hr=%s' % hex(hr)


@pytest.fixture
def launchapi(monkeypatch):
    """`WindowsBoundary.launch`'s Win32 calls replaced by fakes: the real launch runs,
    and nothing is created, assigned, resumed, terminated or made inheritable."""
    s = SimpleNamespace(flags={STDIN: 0, STDOUT: 0, OTHER: 1}, attrs={}, created=[],
                        at_create=None, create_ok=True, set_ok=True, assign_ok=True, resume=1,
                        terminate_ok=True, resumed=[], terminated=[], lists_deleted=0,
                        freed=[], count=None, last=0)

    def init(attrs, count, flags, psize):
        if attrs is None:
            psize._obj.value = 64
            return 0
        s.count = count
        return 1

    def update(attrs, flags, attr, pvalue, size, previous, returned):
        s.attrs[attr] = list(pvalue._obj) if attr == HANDLE_LIST else pvalue._obj
        return 1

    def get_info(h, pflags):
        pflags._obj.value = s.flags[h]
        return 1

    def set_info(h, mask, value):
        if not s.set_ok:
            s.last = 6
            return 0
        s.flags[h] = (s.flags[h] & ~mask) | (value & mask)
        return 1

    def create(app, command, pattrs, tattrs, inherit, flags, env, cwd, psi, ppi):
        si = psi._obj.StartupInfo
        s.created.append({'inherit': inherit, 'flags': flags, 'list': psi._obj.lpAttributeList,
                          'std': (si.hStdInput, si.hStdOutput, si.hStdError)})
        s.at_create = dict(s.flags)
        if not s.create_ok:
            s.last = 5
            return 0
        ppi._obj.hProcess, ppi._obj.hThread, ppi._obj.dwProcessId = 0x700, 0x701, 4242
        return 1

    def derive(name, ppsid):
        ppsid._obj.value = 0x5150
        return 0

    def assign(job, h):
        s.last = 0 if s.assign_ok else 5
        return 1 if s.assign_ok else 0

    def terminate(h, code):
        s.terminated.append(h)
        return 1 if s.terminate_ok else 0

    def deleted(attrs):
        s.lists_deleted += 1

    for name, fake in (('_InitializeProcThreadAttributeList', init),
                       ('_UpdateProcThreadAttribute', update),
                       ('_DeleteProcThreadAttributeList', deleted),
                       ('_GetHandleInformation', get_info), ('_SetHandleInformation', set_info),
                       ('_CreateProcessW', create), ('_AssignProcessToJobObject', assign),
                       ('_ResumeThread', lambda h: s.resumed.append(h) or s.resume),
                       ('_TerminateProcess', terminate),
                       ('_DeriveAppContainerSidFromAppContainerName', derive),
                       ('_LocalFree', lambda p: s.freed.append(p.value)),
                       ('_err', lambda: s.last)):
        monkeypatch.setattr(iso, name, fake)
    return s


def _real_launch():
    return iso.WindowsBoundary().launch(['fake.exe', '--x'], cwd='C:/synthetic',
                                        env={'A': '1', 'LOCALAPPDATA': 'C:/synthetic/local'},
                                        profile='archeus.exec.synthetic',
                                        job=0x900, stdin=STDIN, stdout=STDOUT)


@pytest.mark.skipif(iso.WindowsBoundary is None, reason='the Windows boundary')
class TestLaunchOnWindows:
    # ── C4: only the stdio handles reach the child ──

    def test_the_child_inherits_its_stdio_and_nothing_else(self, launchapi):
        child = _real_launch()
        assert launchapi.attrs[HANDLE_LIST] == [STDIN, STDOUT]      # stderr is stdout's
        assert SECURITY_CAPABILITIES in launchapi.attrs and launchapi.count == 2
        (call,) = launchapi.created
        assert call['inherit'] is True and call['flags'] & 0x80000 and call['list']
        assert call['std'] == (STDIN, STDOUT, STDOUT)
        assert launchapi.at_create[STDIN] & 1 and launchapi.at_create[STDOUT] & 1
        assert launchapi.flags == {STDIN: 0, STDOUT: 0, OTHER: 1}     # put back, nothing else
        assert child.pid == 4242 and launchapi.resumed == [0x701]
        assert launchapi.terminated == [] and launchapi.lists_deleted == 1
        assert launchapi.freed == [0x5150]

    def test_a_create_that_fails_puts_every_flag_back(self, launchapi):
        launchapi.create_ok = False
        with pytest.raises(iso.IsolationUnavailable) as err:
            _real_launch()
        assert err.value.reason == 'winapi'
        assert launchapi.at_create[STDIN] & 1                         # it was tried
        assert launchapi.flags == {STDIN: 0, STDOUT: 0, OTHER: 1}
        assert launchapi.resumed == [] and launchapi.lists_deleted == 1

    def test_a_flag_that_cannot_be_set_stops_the_launch_before_any_process(self, launchapi):
        launchapi.set_ok = False
        with pytest.raises(iso.IsolationUnavailable) as err:
            _real_launch()
        assert err.value.reason == 'winapi' and launchapi.created == []
        assert launchapi.flags == {STDIN: 0, STDOUT: 0, OTHER: 1}

    def test_a_handle_already_inheritable_is_left_as_it_was(self, launchapi):
        launchapi.flags[STDIN] = 1
        _real_launch()
        assert launchapi.flags == {STDIN: 1, STDOUT: 0, OTHER: 1}

    def test_the_stdio_handles_are_opened_not_inheritable(self, monkeypatch, tmp_path):
        seen = []

        def open_file(path, access, share, security, creation, flags, template):
            seen.append(security)
            return 0x104

        monkeypatch.setattr(iso, '_CreateFileW', open_file)
        assert iso.WindowsBoundary().open_inherited(str(tmp_path / 'prompt'), 'read') == 0x104
        assert seen == [None]                          # no SECURITY_ATTRIBUTES: not inheritable

    # ── C11: only CREATE_SUSPENDED's own suspension, lifted once, is a launch ──

    @pytest.mark.parametrize('label,resume,reason', [
        ('the resume failed: (DWORD)-1', 0xFFFFFFFF, 'winapi'),
        ('the thread was not suspended', 0, 'process_resume'),
        ('the thread is still suspended', 2, 'process_resume'),
    ])
    def test_a_process_not_resumed_exactly_once_is_terminated_and_handed_back(
            self, launchapi, label, resume, reason):
        launchapi.resume = resume
        with pytest.raises(iso.IsolationUnavailable) as err:
            _real_launch()
        assert err.value.reason == reason
        assert launchapi.terminated == [0x700] and err.value.child.pid == 4242
        assert launchapi.lists_deleted == 1

    def test_a_terminate_that_fails_still_reports_the_resume_failure(self, launchapi):
        launchapi.resume, launchapi.terminate_ok = 0xFFFFFFFF, False
        with pytest.raises(iso.IsolationUnavailable) as err:
            _real_launch()
        assert err.value.reason == 'winapi' and 'ResumeThread' in err.value.detail
        assert err.value.child.pid == 4242            # still Core's to wait on

    def test_a_process_the_job_refused_is_terminated_and_never_resumed(self, launchapi):
        launchapi.assign_ok = False
        with pytest.raises(iso.IsolationUnavailable) as err:
            _real_launch()
        assert 'AssignProcessToJobObject' in err.value.detail
        assert launchapi.resumed == [] and launchapi.terminated == [0x700]
        assert err.value.child.pid == 4242



# ── K3 (C-1012-T030-2 §1-§2): the held-Job fence and the order of an end ─────

@pytest.fixture
def fence_clock(monkeypatch):
    """The fence's clock, moved only by its own sleeps."""
    now = [0.0]
    monkeypatch.setattr(iso, '_clock', lambda: now[0])
    monkeypatch.setattr(iso, '_sleep', lambda s: now.__setitem__(0, now[0] + s))
    return now


SEED, IMP = 'a' * 40, 'c' * 40


class TestFence:
    def _held(self, tmp_path, *answers):
        a, b, req, _ = authority(tmp_path)
        a._ensure_job(req.execution_id)
        b.active = list(answers)
        return a, b, req.execution_id

    def test_zero_after_some_polls_is_quiescence_and_the_job_closes_after(self, tmp_path,
                                                                        fence_clock):
        a, b, eid = self._held(tmp_path, 2, 1, 0)
        assert a.fence(eid) is None
        assert b.order == ['query', 'query', 'query', 'close']
        assert a.held_job(eid) is None

    def test_a_survivor_at_the_bound_is_no_import_and_the_job_still_closes(self, tmp_path,
                                                                          fence_clock):
        a, b, eid = self._held(tmp_path, 1)
        why = a.fence(eid)
        assert '1 process(es) still in its Job' in why
        assert b.order[-1] == 'close' and b.order.count('close') == 1
        assert fence_clock[0] >= iso.EXIT_WAIT_S                   # waited the bound, no more
        assert fence_clock[0] < iso.EXIT_WAIT_S + 2 * iso.FENCE_POLL_S

    @pytest.mark.parametrize('answer', [iso.IsolationUnavailable('job_query', 'synthetic'),
                                        OSError('denied'), -1, None, True, '0', 0.0])
    def test_a_query_that_fails_or_is_no_count_is_no_import(self, tmp_path, fence_clock,
                                                            answer):
        a, b, eid = self._held(tmp_path, answer)
        assert a.fence(eid) is not None
        assert b.order == ['query', 'close']

    def test_no_held_job_is_no_import_and_nothing_is_asked(self, tmp_path, fence_clock):
        a, b, req, _ = authority(tmp_path)
        assert a.fence(req.execution_id) == 'no Job is held for it'
        assert b.order == []

    def test_the_unavailable_boundary_imports_nothing(self, tmp_path, fence_clock):
        # its close fails too, so the fence raises; the manager reads any raise as
        # no import (TestEndOrder), and the Job is no longer Core's to hold
        a, _b, req, _ = authority(tmp_path, boundary=iso.UnavailableBoundary())
        a._jobs[req.execution_id] = 'job'
        with pytest.raises(iso.IsolationUnavailable):
            a.fence(req.execution_id)
        assert a.held_job(req.execution_id) is None


class TestEndOrder:
    """manager._collect for a seeded isolated execution: the exit tombstone, the fence's
    query, the close, the import, one transaction, then the teardown."""

    def _end(self, tmp_path, state='RUNNING', code=0, *, killed=False, answers=(0,),
             record=True, seeded=True, import_fails=False):
        m = _manager_with_fake_node()
        a, b, req, _ = authority(tmp_path)
        eid = req.execution_id
        a._ensure_job(eid)
        b.active = list(answers)
        log = b.order
        e = SimpleNamespace(id=eid, state=state, account_id=None, isolated=True,
                            process_seq=1, seed_revision=SEED if seeded else None,
                            mission_id='msn')
        rec = iso.IsolationRecord(execution_id=eid, profile='p', state='established')
        m.node.isolation_record = lambda x: rec if record else None
        m.node.ended = lambda handle, code, seq: log.append('tombstone')
        m.node.fence_isolation = a.fence

        def imported(pid, x, seed, *, workdirs):
            log.append('import')
            if import_fails:
                raise OSError('the seeded link link was changed')
            assert (pid, x, seed, workdirs) == ('prj', eid, SEED, ['w'])
            return {'revision': IMP, 'tree': 'f' * 40, 'files_changed': ['A x'],
                    'deleted': 0, 'dropped_dirs': 0}
        m.node.import_workspace = imported
        m._store_inputs = lambda x: ('prj', ['w'])
        m._tail = m._progress = lambda e, p: None
        m._release_isolation = lambda e: log.append('teardown')
        m.policy = m.missions = m.router = None
        real_do = m._do
        m._do = lambda command, **kw: (log.append(command.__name__), real_do(command, **kw))
        reloads = []
        # the end is written by the transaction: the row the pass reads after it has ended
        m._reload = lambda x: reloads.append(1) or (
            x if len(reloads) == 1 else SimpleNamespace(**dict(vars(x), state='ENDED_OK')))
        result = base.ExecutionResult(exit_reason='killed' if killed else
                                      ('ok' if code == 0 else 'error'), exit_code=code)
        p = {'adapter': SimpleNamespace(collect_result=lambda handle: result),
             'handle': object(), 'seq': 1, 'offset': 1, 'usage': 0}
        m._collect(e, p, base.ProcStatus('exited', code))
        ((cmd, kw),) = m.calls
        return log, cmd, kw

    @pytest.mark.parametrize('state,want', [('RUNNING', 'record_end'),
                                            ('HANDING_OFF', 'record_handoff')])
    def test_exit_fence_close_import_transaction_teardown(self, tmp_path, fence_clock,
                                                          state, want):
        log, cmd, kw = self._end(tmp_path, state, answers=(1, 0))
        assert log == ['tombstone', 'query', 'query', 'close', 'import', want, 'teardown']
        assert (kw['import_revision'], kw['no_import']) == (IMP, None)
        assert kw['facts']['end_state'] == 'f' * 40 and kw['facts']['files_changed'] == ['A x']

    @pytest.mark.parametrize('answers,record,import_fails,why', [
        ((1,), True, False, 'not quiescent: 1 process(es)'),
        ((OSError('x'),), True, False, 'could not be queried'),
        ((iso.IsolationUnavailable('job_close', 'x'),), True, False, 'could not be queried'),
        ((0,), False, False, 'isolation record is gone'),
        ((0,), True, True, 'seeded link link was changed')])
    def test_every_no_import_case_reaches_the_transaction_with_its_cause(
            self, tmp_path, fence_clock, answers, record, import_fails, why):
        log, cmd, kw = self._end(tmp_path, answers=answers, record=record,
                                 import_fails=import_fails)
        assert cmd is X.record_end and kw['import_revision'] is None and why in kw['no_import']
        assert 'import' not in log or import_fails
        assert kw['facts']['end_state'] is None                       # unmeasured stands
        assert log[-2:] == ['record_end', 'teardown']

    def test_a_held_job_with_no_record_is_never_imported(self, tmp_path, fence_clock):
        log, _cmd, kw = self._end(tmp_path, record=False)
        assert 'query' not in log and 'import' not in log

    @pytest.mark.parametrize('state,code,killed,seeded', [
        ('RUNNING', 1, False, True), ('RUNNING', 0, True, True), ('PAUSING', 0, False, True),
        ('HANDING_OFF', 1, False, True), ('RUNNING', 0, False, False)])
    def test_an_end_that_imports_nothing_is_not_fenced(self, tmp_path, fence_clock, state,
                                                       code, killed, seeded):
        log, _cmd, kw = self._end(tmp_path, state, code, killed=killed, seeded=seeded)
        assert 'query' not in log and 'import' not in log
        assert 'import_revision' not in kw and 'no_import' not in kw


@pytest.mark.skipif(iso.WindowsBoundary is None, reason='the Windows boundary')
def test_an_appcontainer_block_without_localappdata_is_refused_before_any_os_call(monkeypatch):
    # T-088: CreateProcessW answers 203 for such a block; the boundary says why first
    def touched(*a, **k):
        raise AssertionError('an OS call was made')
    for name in ('_InitializeProcThreadAttributeList', '_DeriveAppContainerSidFromAppContainerName',
                 '_CreateProcessW', '_SetHandleInformation'):
        monkeypatch.setattr(iso, name, touched)
    env = {'SystemRoot': r'C:\Windows', 'PATH': r'C:\Windows\System32'}
    with pytest.raises(iso.IsolationUnavailable) as err:
        iso.WindowsBoundary().launch(['cmd.exe'], cwd='.', env=env, profile='p', job=None,
                                     stdin=None, stdout=None)
    assert (err.value.reason, err.value.detail) == (
        'environment_block', 'an AppContainer block needs LOCALAPPDATA')


def _job_info_written(monkeypatch, execution_id):
    """What create_job hands SetInformationJobObject, copied out of the call."""
    import ctypes
    seen = []

    def set_info(h, cls, ref, size):
        seen.append((cls, iso._ELI.from_buffer_copy(ctypes.string_at(ctypes.addressof(ref._obj),
                                                                     size))))
        return 1
    monkeypatch.setattr(iso, '_CreateJobObjectW', lambda *a: 0x77)
    monkeypatch.setattr(iso, '_SetHandleInformation', lambda *a: 1)
    monkeypatch.setattr(iso, '_SetInformationJobObject', set_info)
    monkeypatch.setattr(iso.WindowsBoundary, 'job_facts',
                        lambda self, h: {'type': 'Job', 'name': '', 'inheritable': False})
    assert iso.WindowsBoundary().create_job(execution_id) == 0x77
    (cls, li), = seen
    assert cls == iso.JOB_OBJECT_EXTENDED_LIMIT_INFORMATION
    b = li.Basic
    return (b.LimitFlags, b.ActiveProcessLimit, li.JobMemoryLimit, b.PerJobUserTimeLimit,
            b.PerProcessUserTimeLimit, li.ProcessMemoryLimit)


@pytest.mark.skipif(iso.WindowsBoundary is None, reason='the Windows boundary')
def test_the_verifier_job_carries_its_budgets_and_an_execution_job_does_not(monkeypatch):
    # T-090 (owner values): 64 processes, 4 GiB for the Job, 10 minutes of Job user CPU
    verify = iso.Principal('verify', ids.new_id('verification'), 0).key
    assert _job_info_written(monkeypatch, verify) == (
        0x2000 | 0x8 | 0x200 | 0x4, 64, 4 * 1024 ** 3, 10 * 60 * 10 ** 7, 0, 0)
    assert _job_info_written(monkeypatch, ids.new_id('execution')) == (0x2000, 0, 0, 0, 0, 0)

"""T-335 — the fail-closed branches of `archeus/node/isolation.py` 650-1300 that the
PV-20 suites never reach (pv20-execution-isolation-design §3.2 Cleanup, §3.4, §3.7).

Every test runs against a *synthetic* boundary — the same seam
`tests/v1/unit/test_pv20_isolation.py` uses — so it answers the OS questions Core asks
without one AppContainer, Job, process or handle call: it runs unchanged on Linux and
on Windows. The autouse tripwire below fails any test that reaches a real Win32
primitive, and no test sleeps, starts a process or reads the environment.

Each test names (in its docstring) the one source branch it exists for; removing or
inverting that branch must fail exactly that test and nothing else.
"""

import dataclasses
import json
import os
import re
import subprocess
import zlib

import pytest

from archeus.core.domain import ids
from archeus.harnesses import base
from archeus.infra.paths import ExecPaths, isolation_dir, isolation_state, quarantine_log
from archeus.node import isolation as iso

#: an ACL-changing program, however it is spelled on a command line
ACL_TOOL = re.compile(r'(?i)(?:^|[\s\\/"\'])(?:i?cacls|takeown)(?:\.exe)?(?:$|[\s"\'])|set-acl')


# ── the lowest mutation boundary, armed for every test in this file ───────────

@pytest.fixture(autouse=True)
def os_tripwire(monkeypatch):
    """No test here may reach the OS's own mutation primitives. They only exist on
    Windows, so the guard is a belt: the synthetic boundary is the reason they cannot
    be reached at all (RULES: the tests are reviewed on Windows, written on Linux)."""
    hits = []
    popen, system = subprocess.Popen, os.system

    def guarded_popen(args, *a, **k):
        argv = [args] if isinstance(args, (str, bytes)) else list(args)
        if any(ACL_TOOL.search(os.fsdecode(x) if isinstance(x, bytes) else str(x))
               for x in argv):
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
                 '_GetSecurityInfoByNameW', '_CreateProcessW', '_CreateJobObjectW',
                 '_AssignProcessToJobObject', '_TerminateProcess', '_CloseHandle',
                 '_SetInformationJobObject', '_ResumeThread', '_OpenProcess'):
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

    def wait(self, timeout=None):
        return self.returncode


def _stable_sid(name):
    """A SID derived from a profile name: deterministic (no `hash` salt), so a test
    reads the same answer on Windows as on Linux."""
    return 'S-1-15-3-9-%08d' % (zlib.crc32(str(name).encode('utf-8')) % (10 ** 8),)


class FakeBoundary:
    """A boundary whose every answer is a knob. It never launches a real process and
    never names the OS: it records what it was asked to do."""
    id = 'fake'

    def __init__(self):
        self.available_ok = True
        self.grant_ok = True
        self.broad = None
        self.core_state_granted = False
        self.caps = ()
        self.job_named = False
        self.job_inheritable = False
        self.job_type = 'Job'
        self.job_creates = 0
        self.presence_fail = False
        self.presence_answers = {}        # profile -> an answer that is not True/False
        self.create_fail = None
        self.delete_fail = set()
        self.delete_leaves = set()
        self.looked = []                  # every presence read
        self.probed = []                  # every process read
        self.processes = {}
        self.sids = {}                    # profile -> the SID create_profile answers with
        self.on_create = None             # called inside create_profile (flip a knob)
        self.snapshot = None              # called inside create_profile (read the record)
        self.seen = []                    # what the record said at each create
        self.launch_ok = True
        self.launch_calls = []
        self.profiles = set()
        self.created = []
        self.deleted = []
        self.closed = []
        self.assigned = []

    def available(self):
        return self.available_ok

    def create_profile(self, execution_id):
        name = iso.validated_profile(execution_id)
        if self.on_create is not None:
            self.on_create()
        if self.snapshot is not None:
            self.seen.append(self.snapshot())
        if self.create_fail:
            raise iso.IsolationUnavailable(self.create_fail, 'synthetic')
        existed = name in self.profiles
        self.profiles.add(name)
        self.created.append(name)
        return {'profile': name, 'sid': self.sids.get(name) or _stable_sid(name),
                'created': True, 'existed': existed, 'package_dir': 'materialized'}

    def delete_profile(self, execution_id):
        name = iso.validated_profile(execution_id)
        self.deleted.append(name)
        if name in self.delete_fail:
            raise iso.IsolationUnavailable('profile_delete', 'in use (synthetic)')
        if name not in self.delete_leaves:
            self.profiles.discard(name)

    def profile_exists(self, execution_id):
        name = iso.profile_name(execution_id)
        self.looked.append(name)
        if self.presence_fail:
            raise iso.IsolationUnavailable('profile_state', 'unreadable (synthetic)')
        if name in self.presence_answers:
            return self.presence_answers[name]
        return name in self.profiles

    def process_started(self, pid):
        self.probed.append(pid)
        return self.processes.get(pid)

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
        self.job_creates += 1
        return {'job': execution_id}

    def job_facts(self, handle):
        if handle is None:
            return None
        return {'type': self.job_type,
                'name': 'synthetic-job' if self.job_named else '',
                'inheritable': self.job_inheritable}

    def assign_job(self, job, process_handle):
        self.assigned.append((job, process_handle))

    def close_job(self, job):
        self.closed.append(job)

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

    def mutations(self):
        """Every call that would change OS state: the profile store, a Job, a process."""
        return self.created + self.deleted + self.assigned + self.launch_calls


class FakeNode:
    id = 'fake-node'

    def __init__(self):
        self.registry = []

    def _registry(self, line):
        self.registry.append(line)


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


def authority(tmp_path, *, boundary=None, request=None):
    """An `Isolation` authority wired to a fake boundary and a satisfying plan."""
    node = FakeNode()
    b = boundary or FakeBoundary()
    req = request or make_satisfying_request(new_execution_id(), str(tmp_path))
    a = iso.Isolation(node, boundary=b, plan=lambda spec: req)
    return a, b, req, node


def _row(row='runtime', access='rx', path='tool'):
    return iso.Grant(path, access, row)


def _good_record(b, execution_id, **over):
    """A record as Core writes it for an established execution, with *over* on top."""
    d = iso.IsolationRecord(execution_id=execution_id, profile=iso.profile_name(execution_id),
                            sid=b.derive_sid(execution_id), state='established',
                            planned=(_row(),)).as_dict()
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


def _plant_ledger(*lines):
    os.makedirs(isolation_dir(), exist_ok=True)
    with open(quarantine_log(), 'ab') as f:
        for line in lines:
            f.write((line if isinstance(line, bytes) else json.dumps(line).encode('utf-8'))
                    + b'\n')


def _ledger_ops():
    if not os.path.exists(quarantine_log()):
        return []
    with open(quarantine_log(), encoding='utf-8') as f:
        return [json.loads(x)['op'] for x in f.read().splitlines() if x.strip()]


def _read_record_bytes(execution_id):
    with open(isolation_state(execution_id), 'rb') as f:
        return f.read()


# ── §3.7: the sweep never acts on what it cannot account for ─────────────────
#
# isolation.py:1171-1173 `reclaim`: `if execution_id in live: continue`
# isolation.py:1216-1217 `_reclaim_entry`: `if rec.state == 'invalid': return False`

class TestTheSweepLeavesWhatItMayNotTouch:
    def test_a_live_executions_quarantined_identity_is_never_torn_down_by_the_pass(
            self, tmp_path):
        """`reclaim` line 1172: the ledger names an execution that is still live, so
        the pass must not touch it. Were the skip dropped, the sweep would close its
        Job (kill-on-close: its process dies) and delete the profile it is running
        under, and would call that a completed teardown."""
        b = FakeBoundary()
        a, b, req, _ = authority(tmp_path, boundary=b)
        a.establish(req)
        name = iso.profile_name(req.execution_id)
        b.delete_fail.add(name)                    # the first cleanup cannot remove it
        assert a.teardown(req.execution_id, reason='ended')['profile'] == 'quarantined'
        b.delete_fail.clear()                      # this pass *could* remove it
        asked, looked = len(b.deleted), len(b.looked)
        node = FakeNode()
        boot = iso.Isolation(node, boundary=b)     # a later Core, the same disk
        assert boot.reclaim(live_execution_ids=[req.execution_id]) == []
        assert len(b.deleted) == asked             # not one delete was even asked for
        assert len(b.looked) == looked             # nor one presence read
        assert name in b.profiles                  # the identity still stands
        assert os.path.lexists(isolation_state(req.execution_id))
        with open(isolation_state(req.execution_id), encoding='utf-8') as f:
            assert json.load(f)['state'] == 'quarantined'
        assert _ledger_ops() == ['quarantine']     # no `released` for a standing profile
        assert node.registry == []                 # and nothing about it in the registry

    def test_a_quarantine_line_whose_record_cannot_be_read_deletes_nothing(self, tmp_path):
        """`_reclaim_entry` line 1216: the record behind a ledger line cannot be
        trusted, so the pass returns before the delete. Were the refusal dropped, the
        untrusted record would be walked into `_unowned`, rewritten as
        `provenance_unknown` and the evidence of what stood there destroyed."""
        b = FakeBoundary()
        node = FakeNode()
        a = iso.Isolation(node, boundary=b)
        eid = new_execution_id()
        name = iso.profile_name(eid)
        b.profiles.add(name)                       # a profile does stand under the name
        planted = b'{ this is not json'
        _plant(eid + '.json', planted)
        _plant_ledger({'op': 'quarantine', 'execution_id': eid, 'profile': name,
                       'sid': '', 'planned': [], 'reason': 'process_unverified',
                       'at': 1.0})
        assert a.reclaim(live_execution_ids=[]) == []
        assert b.mutations() == []                 # no create, no delete, no assign
        assert name in b.profiles
        assert _read_record_bytes(eid) == planted  # the evidence is exactly as found
        assert a.invalid[eid] == 'unreadable'
        assert [l['op'] for l in node.registry] == ['isolation_invalid']
        assert _ledger_ops() == ['quarantine']

    def test_a_quarantine_line_still_belongs_to_the_record_it_names(self, tmp_path):
        """The same branch's other side, so the test above is not a vacuous pass on an
        authority that never reaches the record at all: with a trustworthy record the
        pass does the work and calls it done."""
        b = FakeBoundary()
        a, b, req, _ = authority(tmp_path, boundary=b)
        a.establish(req)
        name = iso.profile_name(req.execution_id)
        b.delete_fail.add(name)
        assert a.teardown(req.execution_id, reason='ended')['profile'] == 'quarantined'
        b.delete_fail.clear()
        boot = iso.Isolation(FakeNode(), boundary=b)
        assert boot.reclaim(live_execution_ids=[]) == [req.execution_id]
        assert b.deleted == [name, name]      # the quarantine's own attempt, then the pass
        assert not os.path.lexists(isolation_state(req.execution_id))
        assert _ledger_ops() == ['quarantine', 'released']


# ── §3.7: a record Core cannot prove it wrote is no record at all ────────────
#
# isolation.py:709-711 `_save`: `if not config.write_json_atomic(...): raise OSError`

class TestARecordThatWasNotWritten:
    def test_a_quiet_write_failure_is_an_error_and_not_a_saved_record(self, tmp_path,
                                                                       monkeypatch):
        """`_save` line 711: `write_json_atomic` answers False, and the answer is what
        makes the write a claim. Dropping the check leaves Core holding an identity no
        file says it holds, which no later pass can find and no restart can reconcile."""
        monkeypatch.setattr(iso.config, 'write_json_atomic', lambda *a, **k: False)
        a = iso.Isolation(FakeNode(), boundary=FakeBoundary())
        rec = iso.IsolationRecord(execution_id=new_execution_id(),
                                  profile='archeus.exec.notwritten')
        with pytest.raises(OSError):
            a._save(rec)
        assert not os.path.lexists(isolation_state(rec.execution_id))

    def test_an_establishment_whose_record_cannot_be_written_starts_nothing(
            self, tmp_path, monkeypatch):
        """`_save` line 711 through `establish`: the pending record is the first thing
        written, so if it cannot be written nothing else may happen — no profile, no
        Job, no process — and the failure is recorded as `os_error`, the same word a
        restarted Core would read."""
        monkeypatch.setattr(iso.config, 'write_json_atomic', lambda *a, **k: False)
        a, b, req, node = authority(tmp_path)
        with pytest.raises(iso.IsolationUnavailable) as got:
            a.establish(req)
        assert got.value.reason == 'os_error'
        assert b.created == [] and b.closed == [] and b.assigned == []
        assert b.launch_calls == [] and b.job_creates == 0
        assert b.deleted == []        # nothing on disk says Core made anything
        assert a.record(req.execution_id) is None
        assert [(l['op'], l['reason']) for l in node.registry] == [
            ('isolation_failed', 'os_error')]


# ── §3.4/§3.7: a resume adopts the identity its own record proves, and only it ─
#
# isolation.py:822 `_establish`: `identity.get('existed') and not (rec.owned and
# rec.sid and rec.sid == sid)`
# isolation.py:1090 `_release_best_effort`: `if not self.boundary.available() or ...`

class TestAdoptionAndItsAbsence:
    def test_a_profile_that_now_answers_another_sid_is_never_adopted(self, tmp_path):
        """`_establish` line 822, the `rec.sid == sid` term: the name existed and the
        SID it answers is not the one this execution's own record carries, so what
        stands there is a different principal. Drop the comparison and Core adopts it:
        the execution runs as somebody else's identity."""
        a, b, req, _ = authority(tmp_path)
        rec = a.establish(req)
        name = rec.profile
        assert rec.owned and rec.sid == b.derive_sid(req.execution_id)
        b.sids[name] = 'S-1-15-3-9-99999998'        # somebody else's profile, same name
        with pytest.raises(iso.IsolationUnavailable) as got:
            a.establish(req)
        assert got.value.reason == 'profile_preexisting'
        with open(isolation_state(req.execution_id), encoding='utf-8') as f:
            d = json.load(f)
        assert d['state'] == 'failed' and d['failure'] == 'profile_preexisting'
        assert d['preexisting'] is True and d['owned'] is False
        assert d['sid'] == 'S-1-15-3-9-99999998'    # recorded as seen, never as Core's
        assert b.launch_calls == [] and b.assigned == []
        assert b.deleted == []                      # refusing it is not deleting it
        assert a.held_job(req.execution_id) is None

    def test_an_identity_that_lost_its_boundary_mid_establishment_is_left_as_it_is(
            self, tmp_path):
        """`_release_best_effort` line 1090, the `available()` term: with no boundary
        there is nothing to delete and nothing to quarantine, so Core asks the OS for
        neither. Drop it and a failed establishment on a boundary that has gone away
        deletes a profile it can no longer see the answer to, and reports it gone."""
        b = FakeBoundary()
        b.on_create = lambda: setattr(b, 'available_ok', False)   # gone by the next read
        a, b, req, _ = authority(tmp_path, boundary=b)
        with pytest.raises(iso.IsolationUnavailable) as got:
            a.establish(req)
        assert got.value.reason == 'condition_unmet:isolated_path'
        rec = a.record(req.execution_id)
        assert rec.state == 'failed' and rec.owned and rec.sid
        assert b.deleted == [] and b.looked == []   # no delete asked, no presence read
        assert iso.profile_name(req.execution_id) in b.profiles
        assert a.held_job(req.execution_id) is None  # its Job was closed (kill-on-close)
        assert b.closed == [{'job': req.execution_id}]


# ── §3.7: the Job table is Core's alone, and a process enters only through it ─
#
# isolation.py:943-944 `assign`: `self.boundary.assign_job(self._ensure_job(...), ...)`
# isolation.py:905-906 `held_jobs`: `return dict(self._jobs)`

class TestTheJobTable:
    def test_a_process_is_assigned_into_the_one_job_core_holds_for_its_execution(
            self, tmp_path):
        """`assign` line 944: the handle goes into the Job this execution's key holds,
        created once through `_ensure_job`. Skip the call and the process runs free of
        any Job (R6-A: nothing holds it); pass anything else and it runs in a Job Core
        does not hold."""
        a, b, req, _ = authority(tmp_path)
        a.assign(req.execution_id, 'PROCESS-HANDLE')
        assert b.assigned == [({'job': req.execution_id}, 'PROCESS-HANDLE')]
        assert a.held_job(req.execution_id) == {'job': req.execution_id}
        assert b.job_creates == 1
        a.assign(req.execution_id, 'SECOND-HANDLE')
        assert b.job_creates == 1                    # never a second Job for one key
        assert [h for _job, h in b.assigned] == ['PROCESS-HANDLE', 'SECOND-HANDLE']
        assert b.closed == []                        # assigning never closes it

    def test_the_job_table_a_caller_is_handed_cannot_empty_cores_reference(self, tmp_path):
        """`held_jobs` line 906: the caller gets a copy. Hand it the live dict and one
        `del` drops Core's only reference to a kill-on-close Job, which then leaks its
        whole process tree on the way out."""
        a, b, req, _ = authority(tmp_path)
        a.assign(req.execution_id, 'PROCESS-HANDLE')
        jobs = a.held_jobs()
        del jobs[req.execution_id]
        jobs['invented'] = 'not-a-job'
        assert a.held_job(req.execution_id) == {'job': req.execution_id}
        assert list(a.held_jobs()) == [req.execution_id]
        assert b.closed == []


# ── §3.2 Cleanup: what may be deleted, and by whom ────────────────────────────
#
# isolation.py:959-965 `teardown`: `if rec is None: return out`
# isolation.py:985-986 `_delete_profile`: `if rec.state == 'torn_down' and not rec.sid`

class TestTeardownWithoutProof:
    def test_a_held_job_closes_and_no_profile_is_named_when_the_record_is_gone(self,
                                                                               tmp_path):
        """`teardown` line 964: Core still holds the Job but the record is gone, so the
        Job is closed (kill-on-close) and the profile is nobody's to delete. Without
        that return `teardown` reads the state of `None`, and the execution's end dies
        in an AttributeError instead of reporting what it did."""
        a, b, req, _ = authority(tmp_path)
        a.establish(req)
        name = iso.profile_name(req.execution_id)
        os.remove(isolation_state(req.execution_id))
        out = a.teardown(req.execution_id, reason='ended')
        assert out == {'execution_id': req.execution_id, 'reason': 'ended',
                       'job': 'closed', 'profile': 'none'}
        assert b.closed == [{'job': req.execution_id}]
        assert b.deleted == [] and name in b.profiles   # nothing says Core made it
        assert a.teardown(req.execution_id, reason='ended') is None

    def test_a_record_already_torn_down_with_no_sid_asks_for_no_delete(self, tmp_path):
        """`_delete_profile` line 986, the `not rec.sid` half: a record that is already
        `torn_down` and names no SID is finished — no second delete of a profile that
        may have been re-created under the same derived name since. Drop the whole
        guard and every cleanup of such a record reaches for the profile store again."""
        b = FakeBoundary()
        a = iso.Isolation(FakeNode(), boundary=b)
        eid = new_execution_id()
        _plant(eid + '.json', _good_record(b, eid, state='torn_down', sid='', owned=True))
        b.profiles.add(iso.profile_name(eid))           # something stands there now
        out = a.teardown(eid, reason='ended')
        assert out['profile'] == 'none'
        assert b.deleted == [] and b.looked == [] and b.closed == []
        assert os.path.lexists(isolation_state(eid))    # the finished record is kept

    def test_a_record_torn_down_that_still_names_a_sid_is_finished_off(self, tmp_path):
        """`_delete_profile` line 985, the `rec.state == 'torn_down'` half: an owned
        record whose SID never went with it is still Core's to remove. Read the guard
        as `state == 'torn_down'` alone and such a record is called finished while its
        profile — and the process that can still run under it — is left standing."""
        b = FakeBoundary()
        a = iso.Isolation(FakeNode(), boundary=b)
        eid = new_execution_id()
        name = iso.profile_name(eid)
        _plant(eid + '.json', _good_record(b, eid, state='torn_down', owned=True,
                                           sid=b.derive_sid(eid)))
        b.profiles.add(name)
        out = a.teardown(eid, reason='ended')
        assert out['profile'] == 'torn_down'
        assert b.deleted == [name] and b.looked == [name]
        assert name not in b.profiles
        assert not os.path.lexists(isolation_state(eid))
        assert _ledger_ops() == []                      # a finished teardown is no fault


# ── §3.7: a record that does not prove ownership never carries a SID ─────────
#
# isolation.py:813-815 `_establish`: `if not rec.owned: rec.sid = ''`

class TestAPendingRecordCarriesNoSid:
    def test_a_record_that_proves_no_ownership_is_persisted_without_a_sid(self, tmp_path):
        """`_establish` line 814: `owned` is what makes a SID Core's, so a record that
        does not prove ownership is saved pending with its SID cleared. Leave the SID
        in and an unowned record names a principal the cleanup paths could act on —
        the one thing that separates a profile Core may delete from anybody else's."""
        b = FakeBoundary()
        eid = new_execution_id()
        _plant(eid + '.json', _good_record(b, eid, state='pending', owned=False,
                                           sid=b.derive_sid(eid)))
        req = make_satisfying_request(eid, str(tmp_path))
        b.snapshot = lambda: json.loads(_read_record_bytes(eid).decode('utf-8'))
        a, b, req, _ = authority(tmp_path, boundary=b, request=req)
        rec = a.establish(req)
        assert len(b.seen) >= 1
        assert b.seen[0]['state'] == 'pending'
        assert b.seen[0]['owned'] is False
        assert b.seen[0]['sid'] == ''
        assert rec.state == 'established' and rec.owned
        assert rec.sid == b.derive_sid(eid)


# ── §3.7: the registry says what happened, once, and only what happened ──────
#
# isolation.py:751-752 `note_failure`: `if getattr(spec, 'isolation', None) is None`
# isolation.py:755 `note_failure`: `if rec is None or rec.state not in ('failed',
# 'quarantined')`
# isolation.py:694 `_report_invalid`: `if self.invalid.get(key) == problem: return`
# isolation.py:714-720 `_note`: `if self.node is not None`

def _spec(execution_id, tmp_path, isolated):
    spec = base.ExecutionSpec(execution_id=execution_id, prompt='go', workdir=str(tmp_path))
    return spec if not isolated else dataclasses.replace(spec, isolation=object())


class TestTheWordOfASpawnThatNeverHappened:
    def test_a_process_that_was_never_isolated_leaves_no_isolation_line(self, tmp_path):
        """`note_failure` line 751-752: a spec with no isolation object never went
        through the isolated path, so nothing may be recorded as its isolation failure.
        Drop the guard and every detached spawn that fails is charged an
        `isolation_failed` line — the registry accusing Core of a confinement it was
        never asked to provide."""
        a, b, req, node = authority(tmp_path)
        spec = _spec(req.execution_id, tmp_path, isolated=False)
        assert spec.isolation is None
        a.note_failure(spec, base.SpawnFailed('isolation: condition_unmet:grants'))
        assert node.registry == []
        assert b.mutations() == []

    def test_a_record_that_already_carries_the_failure_is_not_written_up(self, tmp_path):
        """`note_failure` line 755, the state test's other half: the record already
        says `failed`, because `_fail` noted this same failure when it happened. Drop
        the state test and one spawn leaves two `isolation_failed` lines, and O7's
        reconciliation cannot tell one failed start from two."""
        a, b, req, node = authority(tmp_path)
        b.available_ok = False
        with pytest.raises(iso.IsolationUnavailable):
            a.establish(req)
        first = [l for l in node.registry if l['op'] == 'isolation_failed']
        assert len(first) == 1 and first[0]['reason'] == 'platform'
        a.note_failure(_spec(req.execution_id, tmp_path, isolated=True),
                       base.SpawnFailed('isolation: platform'))
        assert [l for l in node.registry if l['op'] == 'isolation_failed'] == first
        assert a.record(req.execution_id).state == 'failed'

    def test_a_record_still_claiming_establishment_is_corrected_by_the_word(self,
                                                                           tmp_path):
        """`note_failure` line 755, the state test itself: the process failed to spawn
        while the record still says the execution is established, which is neither of
        the two states the note is skipped for, so the failure is written. Invert the
        test into `if rec is None` and a spawn that died before its record was touched
        is never reported at all — Core keeps an established execution with no process
        and no line saying why."""
        a, b, req, node = authority(tmp_path)
        a.establish(req)
        assert a.record(req.execution_id).state == 'established'
        node.registry.clear()                      # the establishment's own lines
        a.note_failure(_spec(req.execution_id, tmp_path, isolated=True),
                       base.SpawnFailed('isolation: broker_unreachable'))
        lines = [l for l in node.registry if l['op'] == 'isolation_failed']
        assert len(lines) == 1
        assert lines[0]['execution_id'] == req.execution_id
        assert lines[0]['state'] == 'isolation_failed'
        assert lines[0]['reason'] == 'isolation: broker_unreachable'
        assert b.deleted == [] and b.assigned == [] and b.launch_calls == []   # nothing
        # is deleted or launched by a word about a spawn that failed

    def test_an_isolated_spawn_that_never_happened_leaves_exactly_one_line(self, tmp_path):
        """The same branch's other side: with an isolation object on the spec and no
        record yet, the word is written, and only once."""
        a, b, req, node = authority(tmp_path)
        a.note_failure(_spec(req.execution_id, tmp_path, isolated=True),
                       base.SpawnFailed('isolation: launch_failed'))
        lines = [l for l in node.registry if l['op'] == 'isolation_failed']
        assert len(lines) == 1
        assert lines[0]['execution_id'] == req.execution_id
        assert lines[0]['state'] == 'isolation_failed'
        assert b.mutations() == []


class TestUntrustedStateIsReportedAsItIsFound:
    def test_a_second_distinct_problem_for_one_key_is_reported_too(self, tmp_path):
        """`_report_invalid` line 694: the note is once per key *and problem*, not once
        per key. Coarsen the test to the key and the record rotting under Core's nose —
        unreadable, then forged — is reported as the first thing only, and the second
        never reaches the instrument at all."""
        b = FakeBoundary()
        node = FakeNode()
        a = iso.Isolation(node, boundary=b)
        eid = new_execution_id()
        _plant(eid + '.json', b'{ not json')
        assert a.record(eid).state == 'invalid'
        assert a.invalid[eid] == 'unreadable'
        assert a.record(eid).state == 'invalid'           # read again: noted once
        assert [l['op'] for l in node.registry] == ['isolation_invalid']
        _plant(eid + '.json', _good_record(b, eid, profile='archeus.exec.someone_else'))
        assert a.record(eid).state == 'invalid'
        assert a.invalid[eid] == 'profile_mismatch'
        noted = [l for l in node.registry if l['op'] == 'isolation_invalid']
        assert len(noted) == 2 and noted[1]['reason'] == 'profile_mismatch'
        assert b.mutations() == []                        # a suspect record is left alone

    def test_an_authority_with_no_node_still_fails_closed(self, tmp_path):
        """`_note` line 718: the registry is the instrument, and an authority built
        without a node has none — the failure path must still record the record and
        raise the failure. Read the guard as `self.node` being there and the very first
        note of a failing establishment raises AttributeError out of the failure path."""
        b = FakeBoundary()
        b.available_ok = False
        req = make_satisfying_request(new_execution_id(), str(tmp_path))
        a = iso.Isolation(None, boundary=b)
        with pytest.raises(iso.IsolationUnavailable) as got:
            a.establish(req)
        assert got.value.reason == 'platform'
        assert a.node is None
        rec = a.record(req.execution_id)
        assert rec.state == 'failed' and rec.reason == 'platform'
        assert b.mutations() == []


# ── §3.7: an end that is already written is not Core's to rewrite ────────────
#
# isolation.py:882 `_fail`: `if paths is not None and not os.path.exists(paths.ended)`

class TestAFailureThatIsAlreadyEnded:
    def test_an_establishment_failure_never_rewrites_a_tombstone_that_exists(self,
                                                                            tmp_path,
                                                                            monkeypatch):
        """`_fail` line 882, the `os.path.exists(paths.ended)` term: the tombstone is
        the execution's end, written by whoever saw the process end. Rewriting it from
        a later failed establishment replaces a real exit with `isolation: ...`, and
        the two stories about that process no longer fit in one file."""
        a, b, req, _ = authority(tmp_path)
        b.available_ok = False
        paths = ExecPaths(req.execution_id)
        os.makedirs(paths.dir, exist_ok=True)
        written = b'{"exit_code": 0, "at": 1}'
        with open(paths.ended, 'wb') as f:
            f.write(written)
        calls = []
        monkeypatch.setattr(iso.base, 'mark_ended',
                            lambda *args, **kw: calls.append((args, kw)))
        with pytest.raises(iso.IsolationUnavailable):
            a.establish(req, paths=paths)
        assert calls == []
        with open(paths.ended, 'rb') as f:
            assert f.read() == written
        assert b.mutations() == []

    def test_and_writes_one_where_there_is_none(self, tmp_path, monkeypatch):
        """The same branch's other side, so the test above cannot pass by never
        marking an end at all: with no tombstone the failure leaves one, named for the
        reason it raised."""
        a, b, req, _ = authority(tmp_path)
        b.available_ok = False
        paths = ExecPaths(req.execution_id)
        os.makedirs(paths.dir, exist_ok=True)
        calls = []
        monkeypatch.setattr(iso.base, 'mark_ended',
                            lambda *args, **kw: calls.append((args, kw)))
        with pytest.raises(iso.IsolationUnavailable) as got:
            a.establish(req, paths=paths)
        assert got.value.reason == 'platform'
        assert len(calls) == 1
        assert calls[0][0] == (paths, None)
        assert calls[0][1]['isolation_reason'] == 'platform'
        assert calls[0][1]['isolation_state'] == 'failed'

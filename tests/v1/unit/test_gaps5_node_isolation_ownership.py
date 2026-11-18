"""T-1240 — the ownership retry of Core's isolation record can never lose the created SID.

Source slice under test: `archeus/node/isolation.py` lines 860-907 inclusive at tip
6bbd3b44 — `establish` (860-873), `_check_establishment` (875-879), `_own` (881-902)
and `_save_establishment` (904-906). Everything outside the slice (definitions,
imports, `_establish`, `_settle`, `_fail`, cleanup) is read-only context: every branch
this file selects lives inside it, and no source file is edited.

Round-8 candidate list, denial/fail-closed first, then boundaries, then error paths.
Each was compared with the closest existing assertion before it was kept; none had to
be replaced, and the closest test named is why that assertion misses the case.

 1. 892 `_own` conflict refresh -> invalid record: stop immediately, no overwrite of
    the evidence, the OSError ownership message, and the created SID never used for a
    foreign deletion. Closest: test_pv20_isolation.py::test_a_failed_ownership_save_
    leaves_the_profile_alone — its `_save` raises OSError for an owned record over a
    *trusted* file, so the refresh of 891 and the `invalid` break of 892 never run and
    there is no evidence on disk to preserve.
    -> test_an_untrusted_refresh_stops_the_ownership_save_and_deletes_nothing
 2. 891 `_own` conflict refresh -> newer owned pending record: the next save preserves
    its gen and its evidence while restoring the created SID. Closest:
    test_fx32_isolation_stop.py::test_a_late_ownership_write_is_not_undone_by_a_stale_
    reclaim — the newer record is written there by `_own` itself, the very path under
    test, and only the surviving fields are read, never the loser's refresh.
    -> test_a_conflict_refresh_onto_a_newer_owned_record_keeps_its_evidence
 3. 894 `_own` conflict refresh -> None: synthesize the same execution/profile with
    the created SID and never reuse the stale gen. Closest: test_fx32_isolation_stop
    .py::test_ownership_is_never_turned_back_to_unowned_by_a_write_from_an_older_read
    — it stops at the refusal, so what `_own` builds afterwards is asserted nowhere.
    -> test_a_conflict_refresh_onto_a_vanished_record_synthesizes_the_same_principal
 4. 886 all RECORD_RETRIES ownership saves conflict: bounded saves, the terminal
    OSError, and the identity the OS made still named by the failure record so only
    that one profile is removed. Closest:
    test_pv20_isolation.py::test_a_failed_ownership_save_leaves_the_profile_alone —
    one OSError on the FIRST save, so neither the bound of 886 nor the exhaustion tail
    of 900-902.
    -> test_the_ownership_loop_is_bounded_and_the_created_identity_survives_it
 5. 897 a non-RecordChanged OSError on the second ownership save: the latest record's
    `owned` is reset, and there is no further refresh or save; the first conflict must
    not swallow the actual I/O failure. Closest: the same test — a single OSError,
    never a conflict followed by an I/O error.
    -> test_a_real_io_failure_after_a_conflict_is_not_swallowed_by_that_conflict
 6. 871-872 admission conflicts twice then succeeds on the last retry: success exactly
    once and no extra boundary creation after it. Closest: test_gaps3_node_isolation_a
    .py::TestClosedEstablishmentRefusesBeforeAnythingElse — it never lets one save
    conflict, so the retry arm is unexecuted there.
    -> test_an_establishment_that_conflicts_twice_is_established_once
 7. 873 every admission retry conflicts: `record_changed`, not a generic `os_error`,
    and no fourth attempt. Closest: test_fx32_isolation_stop.py::test_a_record_saved_
    on_a_stale_read_is_refused_and_the_stored_one_stays — it asserts the `_save`
    conflict, never what `establish` decides once its retries are spent.
    -> test_an_establishment_that_always_conflicts_is_refused_as_record_changed
 8. 867 closed before `establish`: no admission attempt at all even when the fake
    would conflict, so the closure wins the retry loop. Closest:
    test_gaps3_node_isolation_a.py::test_a_stopped_core_leaves_a_resumable_record_byte_
    for_byte — it stops an authority with a *readable* record, so a loop that kept
    deciding before raising could still run to 873 unnoticed.
    -> test_a_closed_authority_never_enters_the_admission_retry_loop
 9. 885 an empty SID from the boundary is kept empty and handed to the validator at the
    next stage; ownership is never invented by deriving a replacement SID. Closest:
    test_pv20_isolation.py::test_the_answer_is_on_disk_before_the_job_or_the_invariant
    — it only ever sees a boundary that answers with a SID.
    -> test_an_empty_sid_answer_is_saved_empty_and_handed_to_the_validator
10. 905 `_save_establishment`'s close check refuses: the writer is never called; the
    contrast is `_own`, which must save an already-created identity even after the
    stop. Closest: test_fx32_isolation_stop.py::test_a_profile_created_after_the_stop_
    returned_is_deleted_by_its_own_establishment — it observes the whole thread race
    and the surviving record, never *whether each writer was allowed to write at all*.
    -> test_the_stop_stops_the_writer_that_owns_nothing_and_never_the_ownership_writer

Nothing here measures coverage: these are the highest-risk branches of the slice, chosen
as the card directs. Everything runs against a synthetic boundary — no AppContainer,
Job, process, handle, DLL, subprocess, real lock, real clock or environment value is
reached (the fixtures below trip on any of them, and the record store is asserted to sit
under tmp_path). No thread is started, nothing sleeps, and no probe is Windows-only.
"""

import json
import os
import zlib

import pytest

from archeus.core.domain import ids
from archeus.harnesses import base
from archeus.infra import discovery
from archeus.infra.paths import isolation_dir, isolation_state, quarantine_log
from archeus.node import isolation as iso

#: the SID a same-user writer claims for itself inside a forged record
FOREIGN_SID = 'S-1-15-3-9-12345678'


# ── the lowest mutation boundary, armed for every test in this file ───────────

@pytest.fixture(autouse=True)
def no_real_win32(monkeypatch):
    """Nothing in this file may reach a native primitive: the synthetic boundary is the
    reason none is reachable, this guard is the belt (RULES: written on Linux, reviewed
    on Windows, never a real DLL)."""
    hits = []
    for name in ('_CreateAppContainerProfile', '_DeleteAppContainerProfile',
                 '_GetSecurityInfoByNameW', '_CreateProcessW', '_CreateJobObjectW',
                 '_AssignProcessToJobObject', '_TerminateProcess', '_TerminateJobObject',
                 '_CloseHandle', '_SetInformationJobObject', '_ResumeThread',
                 '_OpenProcess', '_OpenProcessToken'):
        def trip(*a, _name=name):
            hits.append(_name)
            raise AssertionError('the real %s was reached' % _name)
        monkeypatch.setattr(iso, name, trip, raising=False)
    yield hits
    assert hits == [], 'a real mutation primitive was reached: %r' % (hits,)


@pytest.fixture(autouse=True)
def no_real_lock_clock_or_sleep(monkeypatch):
    """The record lock's `msvcrt`/`fcntl` call, Core's clock and its sleep are faked
    before anything is called, so no test here can block, sleep or load a Win32 module.
    A bounded ownership loop never waits, which the teardown asserts."""
    slept = []
    monkeypatch.setattr(iso, '_clock', lambda: 0.0)
    monkeypatch.setattr(iso, '_sleep', lambda s: slept.append(s))
    taken = []
    monkeypatch.setattr(discovery, '_try_lock', lambda fd: taken.append(fd))

    def release(self):
        taken.append(self._fd)
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None

    monkeypatch.setattr(discovery.CoreLock, 'release', release)
    yield slept, taken
    assert slept == [], 'a test slept: %r' % (slept,)


@pytest.fixture(autouse=True)
def record_store_under_tmp(tmp_path, monkeypatch):
    """Every record, lock file and ledger line is asserted to live under `tmp_path`:
    the store is pinned there, not merely expected to be, and no real home is read."""
    monkeypatch.setenv('ARCHEUS_HOME', str(tmp_path / 'archeus-home'))
    monkeypatch.delenv('ARCHEUS_EXECUTION_ID', raising=False)
    root = os.path.normcase(str(tmp_path))

    def guarded(fn):
        def seen(*a, **k):
            p = os.path.normcase(str(fn(*a, **k)))
            assert p.startswith(root), 'a test wrote outside tmp_path: %s' % p
            return fn(*a, **k)
        return seen

    for name in ('isolation_state', 'isolation_dir', 'quarantine_log'):
        monkeypatch.setattr(iso, name, guarded(getattr(iso, name)))
        monkeypatch.setattr('archeus.infra.paths.' + name, guarded(getattr(iso, name)))


# ── the synthetic boundary: answers Core's OS questions, decides nothing ───────

def _stable_sid(name):
    """A SID derived from a profile name, deterministic across platforms, so a test
    reads the same answer on Windows as on Linux."""
    return 'S-1-15-3-9-%08d' % (zlib.crc32(str(name).encode('utf-8')) % (10 ** 8),)


class FakeBoundary:
    """A boundary whose every answer is a knob. It never launches a process and never
    names the OS: it records what it was asked to do and counts the calls a refusal
    must have avoided."""
    id = 'fake'

    def __init__(self):
        self.available_ok = True
        self.available_calls = 0
        self.derive_calls = 0
        self.create_fail = None
        self.delete_fail = set()
        self.profiles = set()
        self.sid_answer = None              # None: the derived SID; '': the OS gave none
        self.on_create = None               # called inside create_profile (a seam)
        self.on_job_facts = None            # called inside job_facts (a seam)
        self.created = []
        self.deleted = []
        self.closed = []
        self.assigned = []
        self.job_creates = 0

    def available(self):
        self.available_calls += 1
        return self.available_ok

    def create_profile(self, execution_id):
        name = iso.validated_profile(execution_id)
        if self.on_create is not None:
            self.on_create()
        if self.create_fail:
            raise iso.IsolationUnavailable(self.create_fail, 'synthetic')
        existed = name in self.profiles
        self.profiles.add(name)
        self.created.append(name)
        sid = _stable_sid(name) if self.sid_answer is None else self.sid_answer
        return {'profile': name, 'sid': sid, 'created': True, 'existed': existed,
                'package_dir': 'materialized'}

    def delete_profile(self, execution_id):
        name = iso.validated_profile(execution_id)
        self.deleted.append(name)
        if name in self.delete_fail:
            raise iso.IsolationUnavailable('profile_delete', 'in use (synthetic)')
        self.profiles.discard(name)

    def profile_exists(self, execution_id):
        return iso.profile_name(execution_id) in self.profiles

    def derive_sid(self, execution_id):
        self.derive_calls += 1
        return _stable_sid(iso.profile_name(execution_id))

    def derive(self, execution_id):
        return self.derive_sid(execution_id)

    def grant_established(self, path, sid, access):
        return True

    def broad_write_grant(self, path, sid):
        return None

    def granted_to(self, path, sid):
        return False

    def capability_grants(self):
        return ()

    def create_job(self, execution_id):
        self.job_creates += 1
        return {'job': execution_id}

    def job_facts(self, handle):
        if handle is None:
            return None
        if self.on_job_facts is not None:
            self.on_job_facts()
        return {'type': 'Job', 'name': '', 'inheritable': False}

    def job_active_processes(self, job):
        return 0

    def assign_job(self, job, process_handle):
        self.assigned.append((job, process_handle))

    def close_job(self, job):
        self.closed.append(job)

    def mutations(self):
        """Every call that would change OS state: the profile store, a Job, a process."""
        return self.created + self.deleted + self.assigned


class FakeNode:
    """The registry is the instrument, never the authority: its notes are a list."""
    id = 'fake-node'

    def __init__(self):
        self.registry = []

    def _registry(self, line):
        self.registry.append(line)


def new_execution_id():
    return ids.new_id('execution')


def make_exec_request(execution_id, root):
    """An §3.1 inventory a synthetic fixture can satisfy but production cannot: every
    required row present on a real directory, the broker present, the class 1, 2 and 3
    directories separated, and Core's own state kept outside the boundary."""
    def d(name):
        p = os.path.join(root, name)
        os.makedirs(p, exist_ok=True)
        return p
    workspace = d('workspace')
    mailbox, response = d('mailbox'), d('response')
    sentinel, state = d('sentinel'), d('state')
    spawn_config = os.path.join(response, 'spawn_config.json')
    with open(spawn_config, 'w', encoding='utf-8') as f:
        json.dump({'argv': []}, f)
    grants = (iso.Grant(workspace, 'rw', 'workspace'),
              iso.Grant(d('runtime'), 'rx', 'runtime'),
              iso.Grant(d('hook'), 'rx', 'hook'),
              iso.Grant(mailbox, 'rw', 'request'),
              iso.Grant(response, 'rx', 'response'),
              iso.Grant(sentinel, 'rx', 'sentinel'),
              iso.Grant(state, 'rw', 'state'))
    return iso.IsolationRequest(execution_id=execution_id, workspace=workspace,
                                grants=grants, mailbox=mailbox, response=response,
                                sentinel=sentinel, spawn_config=spawn_config,
                                state_dir=state, core_state=d('core_state'),
                                broker=d('broker'))


def authority(tmp_path, *, boundary=None, request=None):
    """An `Isolation` authority wired to the fake boundary and a satisfying plan."""
    node = FakeNode()
    b = boundary or FakeBoundary()
    req = request or make_exec_request(new_execution_id(), str(tmp_path))
    return iso.Isolation(node, boundary=b, plan=lambda spec: req), b, req, node


# ── reading what is on disk, without Core's help ──────────────────────────────

def _bytes_of(execution_id):
    with open(isolation_state(execution_id), 'rb') as f:
        return f.read()


def _disk(execution_id):
    return json.loads(_bytes_of(execution_id).decode('utf-8'))


def _plant_forged(execution_id, data):
    """A record file written by somebody other than Core, exactly the bytes given."""
    os.makedirs(isolation_dir(), exist_ok=True)
    with open(isolation_state(execution_id), 'wb') as f:
        f.write(data)
    return data


def _ledger_ops():
    path = quarantine_log()
    if not os.path.exists(path):
        return []
    with open(path, encoding='utf-8') as f:
        return [json.loads(x)['op'] for x in f.read().splitlines() if x.strip()]


def _ops(node):
    return [line['op'] for line in node.registry]


# ── the two store seams every conflict test uses ───────────────────────────────

def _observed_saves(monkeypatch):
    """Wrap `_save` to OBSERVE every write attempt (state, ownership, gen, SID) while
    the real generation check still runs. Returns the list the wrapper fills in."""
    real = iso.Isolation._save
    seen = []

    def spy(self, rec):
        seen.append({'owned': bool(rec.owned), 'state': rec.state, 'gen': rec.gen,
                     'sid': rec.sid, 'rec': rec})
        return real(self, rec)

    monkeypatch.setattr(iso.Isolation, '_save', spy)
    return seen


def _concurrent_writer(monkeypatch, conflicts):
    """A concurrent writer that wins the next *conflicts* generation checks (pass
    float('inf') for one that never yields). Returns its call counter: the number of
    saves Core attempted, which is how the retry bound is read."""
    real = iso._stored_record
    calls = []

    def racy(path, execution_id, api):
        calls.append(os.path.basename(path))
        if len(calls) <= conflicts:
            return {'gen': -1}                    # a write Core never saw happened
        return real(path, execution_id, api)

    monkeypatch.setattr(iso, '_stored_record', racy)
    return calls


def _ownership_writes_always_lose(monkeypatch):
    """A store with a writer that never yields its record exactly when Core tries to
    claim ownership of it while the record is still `pending`, and that leaves every
    other write alone. Returns the observation list of every save attempted."""
    real = iso.Isolation._save
    seen = []

    def contested(self, rec):
        seen.append({'owned': bool(rec.owned), 'state': rec.state, 'gen': rec.gen,
                     'sid': rec.sid, 'rec': rec})
        if rec.owned and rec.state == 'pending':
            raise iso.RecordChanged('the isolation record of %s changed (synthetic)'
                                    % rec.execution_id)
        return real(self, rec)

    monkeypatch.setattr(iso.Isolation, '_save', contested)
    return seen


# ── 1. isolation.py:892 — an untrusted refresh stops the ownership save ───────

class TestTheOwnershipRefreshRefusesToTouchUntrustedEvidence:
    def test_an_untrusted_refresh_stops_the_ownership_save_and_deletes_nothing(self,
                                                                               tmp_path,
                                                                               monkeypatch):
        """Lines 892-893 (`if fresh is not None and fresh.state == 'invalid': break`)
        with the tail of 900-902. A same-user writer replaces the record between the
        pending save and the ownership save; the refresh of 891 reads it back as
        `invalid`, so `_own` must stop at once with the OSError ownership message.
        test_pv20_isolation.py's test_a_failed_ownership_save_leaves_the_profile_alone
        makes `_save` raise for an owned record, but always over a *trusted* file: line
        891 is never reached and there is no evidence on disk to preserve, so nothing
        there catches a loop that re-decides from an unreadable record.

        Catches: removing the 892 test — the loop would re-save the `invalid` fresh
        record, which `_save` answers with a ValueError that escapes `_own` and
        `establish` entirely — and removing `rec.owned = False` at 900, which would
        hand the failure cleanup an owned record and delete a profile that no record
        of Core's vouches for."""
        a, b, req, node = authority(tmp_path)
        eid, name = req.execution_id, iso.profile_name(req.execution_id)
        forged = json.dumps({'execution_id': eid, 'profile': name, 'sid': FOREIGN_SID,
                             'state': 'established',
                             'capabilities': ['-SeImpersonatePrivilege']}).encode('utf-8')
        # the replacement lands while the OS is answering the create: the pending save
        # is already on disk, and the record Core decided from is now the evidence
        b.on_create = lambda: _plant_forged(eid, forged)
        saves = _observed_saves(monkeypatch)
        with pytest.raises(iso.IsolationUnavailable) as got:
            a.establish(req)
        assert got.value.reason == 'os_error'
        assert 'changed under its ownership' in got.value.detail    # 902's terminal OSError
        assert not isinstance(got.value, iso.IsolationClosed)
        assert _bytes_of(eid) == forged                 # the evidence was never overwritten
        assert _disk(eid)['sid'] == FOREIGN_SID         # and never rewritten with Core's own
        rec = a.record(eid)
        assert rec.state == 'invalid' and rec.reason == 'capabilities'
        assert rec.owned is False                       # nothing claims Core made it
        # the break of 892: one ownership save was attempted and lost, and no second
        # write was ever aimed at the unreadable record (`_save` would have refused it)
        assert [(s['state'], s['owned'], s['gen']) for s in saves] \
            == [('pending', False, 0), ('pending', True, 1), ('failed', False, 1)]
        assert _ops(node) == ['isolation_invalid', 'isolation_failed']
        # no privileged side effect: the created SID is never used to delete anything —
        # not even the profile Core itself just made, because no record vouches for it
        assert b.deleted == [] and name in b.profiles
        assert b.closed == [] and b.job_creates == 0 and b.assigned == []
        assert _ledger_ops() == []


# ── 2. isolation.py:891 — the refresh keeps what it did not write ─────────────

class TestTheOwnershipRefreshKeepsWhatItDidNotWrite:
    def test_a_conflict_refresh_onto_a_newer_owned_record_keeps_its_evidence(self,
                                                                             tmp_path):
        """Line 891 (`fresh = self.record(rec.execution_id)`) feeding 894-896. A second
        Core owns the record and has written its evidence; Core's ownership write must
        be re-decided from that record, keeping its gen, its pid and its inventory, and
        restoring only the SID the OS just answered with. fx32's
        test_a_late_ownership_write_is_not_undone_by_a_stale_reclaim has that newer
        record written by `_own` itself — the path under test here — and reads back the
        winner's fields, never what the loser of the race preserved.

        Catches: dropping the refresh (`rec = fresh or ...` alone re-decides from a
        synthesized record whose gen is stale, so the ownership never lands), and
        re-saving the stale read, which would bury the other Core's evidence under
        pid 111 and gen 1."""
        a, b, req, node = authority(tmp_path)
        a2 = iso.Isolation(FakeNode(), boundary=b)                 # the concurrent Core
        eid, name = req.execution_id, iso.profile_name(req.execution_id)
        sid = _stable_sid(name)                                     # the OS's answer to Core
        stale = iso.IsolationRecord(execution_id=eid, profile=name, state='pending',
                                    pid=111, conditions={'identity': [False, 'stale']},
                                    planned=(iso.Grant(str(tmp_path / 'stale'),
                                                        'rw', 'workspace'),))
        a._save(stale)                                              # Core's own read: gen 1
        newer = a2.record(eid)                                      # the other Core reads it
        newer.pid, newer.owned = 222, True
        newer.conditions = {'identity': [True, '']}
        newer.planned = (iso.Grant(str(tmp_path / 'newer'), 'rw', 'workspace'),)
        a2._save(newer)                                             # it owns the record: gen 2
        assert (_disk(eid)['gen'], _disk(eid)['pid']) == (2, 222)
        won = a._own(stale, sid)                                    # the conflict, then 891
        assert won is not newer and won is not stale
        assert won.gen == newer.gen + 1 == 3                        # written ON the newer one
        assert won.state == 'pending' and won.owned is True
        assert won.sid == sid                                       # the created SID restored
        assert won.pid == 222                                       # the other Core's evidence
        assert [g.row for g in won.planned] == ['workspace']
        assert won.planned[0].path == str(tmp_path / 'newer')
        on_disk = _disk(eid)
        assert (on_disk['gen'], on_disk['pid'], on_disk['owned'], on_disk['sid']) \
            == (3, 222, True, sid)
        assert on_disk['planned'][0]['path'] == str(tmp_path / 'newer')   # never pid 111
        assert b.deleted == [] and b.created == [] and _ops(node) == []


# ── 3. isolation.py:894 — the refresh onto nothing keeps the same principal ───

class TestTheOwnershipRefreshInventsNoPrincipal:
    def test_a_conflict_refresh_onto_a_vanished_record_synthesizes_the_same_principal(
            self, tmp_path):
        """Line 894 (`rec = fresh or IsolationRecord(execution_id=..., profile=...)`)
        with 885's `rec.sid = sid`. Cleanup removed the record between Core's read and
        its ownership save, so the refresh answers None and `_own` must synthesize a
        record for the same execution and the same profile, carrying the created SID,
        and must not write from the stale generation. fx32's
        test_ownership_is_never_turned_back_to_unowned_by_a_write_from_an_older_read
        asserts the refusal (`_save` raises) and stops there, so the one moment a
        profile could be attributed to the wrong name — the synthesis — is untested.

        Catches: synthesizing without `profile=rec.profile` (the record would name no
        profile and read back untrusted, and cleanup would then refuse to delete what
        Core made), and carrying the stale gen over (every save would conflict and the
        ownership of a live profile would be lost)."""
        a, b, req, node = authority(tmp_path)
        eid, name = req.execution_id, iso.profile_name(req.execution_id)
        sid = _stable_sid(name)
        stale = iso.IsolationRecord(execution_id=eid, profile=name, state='pending',
                                    pid=111, gen=7)        # a read that is no longer it
        assert a.record(eid) is None                        # cleanup has taken the record
        won = a._own(stale, sid)
        assert won is not stale
        assert won.execution_id == eid and won.profile == name      # the same principal
        assert won.state == 'pending' and won.owned is True
        assert won.sid == sid                               # the created SID, never a new one
        assert won.gen == 1 != stale.gen                    # the stale gen was not reused
        on_disk = _disk(eid)
        assert (on_disk['gen'], on_disk['execution_id'], on_disk['profile']) \
            == (1, eid, name)
        assert on_disk['owned'] is True and on_disk['sid'] == sid
        assert on_disk['pid'] is None                       # the stale read proved nothing
        assert b.deleted == [] and b.derive_calls == 0 and _ops(node) == []


# ── 4. isolation.py:886 — the ownership loop is bounded and never self-certifying ─

class TestTheOwnershipLoopIsBounded:
    def test_the_ownership_loop_is_bounded_and_the_created_identity_survives_it(
            self, tmp_path, monkeypatch):
        """Line 886 (`for _ in range(RECORD_RETRIES)`) and the tail of 900-902. A writer
        never yields the record exactly when Core tries to claim ownership of it, so the
        loop must fight exactly RECORD_RETRIES saves and end in the terminal OSError —
        and the identity the OS did create must still be named by the failure record,
        while the profile is kept, because no ownership save ever reached disk. test_pv20_isolation.py's
        test_a_failed_ownership_save_leaves_the_profile_alone fails the FIRST save, so
        neither the bound of 886 nor the exhaustion tail of 900-902 is exercised there.

        Catches: widening or removing the bound of 886 (an unbounded fight with a writer
        that never yields), and deleting the raise at 901-902 — `_own` would return None
        and `_establish` would settle a None record, charging the execution with an
        AttributeError instead of the establishment failure it is. The reset at 900 is
        not reachable from this path (the loop has rebound `rec` twice by then, and the
        record `_own` hands the failure to is `_establish`'s own); it is caught by the
        break of 892, which leaves the caller's object as the one it unowns."""
        a, b, req, node = authority(tmp_path)
        eid, name = req.execution_id, iso.profile_name(req.execution_id)
        sid = _stable_sid(name)
        saves = _ownership_writes_always_lose(monkeypatch)
        with pytest.raises(iso.IsolationUnavailable) as got:
            a.establish(req)
        assert got.value.reason == 'os_error'
        assert 'changed under its ownership' in got.value.detail
        assert not isinstance(got.value, (OSError, iso.IsolationClosed))
        fights = [s for s in saves if s['owned'] and s['state'] == 'pending']
        assert len(fights) == iso.RECORD_RETRIES, 'the ownership loop was not bounded by 886'
        assert {s['gen'] for s in fights} == {1}      # all three fought the same record
        assert [s['state'] for s in saves] == ['pending'] * (iso.RECORD_RETRIES + 1) \
            + ['failed']
        assert b.created == [name]                    # the loop never re-made the identity
        # what the exhausted loop leaves is a failed record that still names the profile
        # the OS really made, with the SID the boundary answered, but never as owned: no
        # ownership save reached disk, so the profile is kept, not deleted
        on_disk = _disk(eid)
        assert (on_disk['state'], on_disk['owned'], on_disk['sid'], on_disk['failure']) \
            == ('failed', False, sid, 'os_error')
        assert b.deleted == [] and name in b.profiles
        assert b.closed == [] and b.job_creates == 0 and b.assigned == []
        assert _ledger_ops() == [] and _ops(node) == ['isolation_failed']
        assert a.held_jobs() == {}


# ── 5. isolation.py:897 — a real I/O failure is not swallowed by the conflict ──

class TestTheOwnershipLoopKeepsTheRealFailure:
    def test_a_real_io_failure_after_a_conflict_is_not_swallowed_by_that_conflict(
            self, tmp_path, monkeypatch):
        """Lines 897-899 (`except OSError: rec.owned = False; raise`): the first
        ownership save conflicts through the real generation check, the refresh
        synthesizes a fresh record, and the second save meets an actual write failure.
        The closest test, test_pv20_isolation.py::
        test_a_failed_ownership_save_leaves_the_profile_alone, fails the FIRST save with
        no conflict before it, so the ordering that can hide a real disk failure — a
        conflict followed by an I/O error — is untested, as is the reset of 898 on the
        very record Core was about to write.

        Catches: dropping the `raise` of 899 (the loop would keep saving to an
        unwritable disk and end with the wrong OSError), and dropping 898 (the record
        handed back to `_establish` would still claim an ownership that never reached
        disk, and the cleanup would delete the profile on that claim)."""
        a, b, req, node = authority(tmp_path)
        eid, name = req.execution_id, iso.profile_name(req.execution_id)
        sid = _stable_sid(name)
        stale = iso.IsolationRecord(execution_id=eid, profile=name, state='pending',
                                    gen=1)          # the store no longer agrees with it
        real_save, real_record = iso.Isolation._save, iso.Isolation.record
        saves, refreshes, owned_at_write = [], [], []

        def save(self, rec):
            saves.append(rec)
            owned_at_write.append(rec.owned)
            if len(saves) >= 2:
                raise OSError('disk full (synthetic)')        # the actual I/O failure
            return real_save(self, rec)             # the first one conflicts for real

        def record(self, execution_id):
            refreshes.append(execution_id)
            return real_record(self, execution_id)

        monkeypatch.setattr(iso.Isolation, '_save', save)
        monkeypatch.setattr(iso.Isolation, 'record', record)
        with pytest.raises(OSError) as got:
            a._own(stale, sid)
        err = got.value
        assert not isinstance(err, iso.RecordChanged)     # the I/O failure survives as itself
        assert type(err) is OSError and 'disk full' in str(err)
        assert len(saves) == 2, 'the loop kept saving after the real failure'
        assert refreshes == [eid]                         # one refresh, then the raise
        assert saves[1].owned is False                    # 898 on the record being written
        assert owned_at_write == [True, True]             # both saves claimed ownership
        assert not os.path.lexists(isolation_state(eid))  # nothing reached the disk
        assert b.deleted == [] and b.created == [] and name not in b.profiles
        assert _ops(node) == [] and _ledger_ops() == []


# ── isolation.py:881-902 — a failed ownership save after a refresh claims nothing ──

class TestAFailedOwnershipSaveAfterARefreshClaimsNothing:
    def test_a_failed_ownership_save_after_refresh_never_deletes_from_the_stale_callers_claim(
            self, tmp_path, monkeypatch):
        """The caller's record says `owned=True` for generation 1. A rival writer saves
        generation 2, unowned, while the profile is being created. `_own` finds the
        conflict, refreshes onto generation 2, and the ownership save on that refreshed
        record is refused by the OS. Disk never says owned, so `_fail` must not delete
        the profile on the stale caller's claim."""
        a, b, req, node = authority(tmp_path)
        eid, name = req.execution_id, iso.profile_name(req.execution_id)
        real_save = iso.Isolation._save
        rival = {}

        def rival_writes_generation_two():
            real_save(a, a.record(eid))          # gen 1 -> gen 2, still unowned, pending
            rival['bytes'] = _bytes_of(eid)

        def refused(self, rec):
            if rec.owned and rec.gen == 2:
                raise PermissionError('access denied (synthetic)')
            return real_save(self, rec)

        b.on_create = rival_writes_generation_two
        monkeypatch.setattr(iso.Isolation, '_save', refused)
        with pytest.raises(iso.IsolationUnavailable) as got:
            a.establish(req)
        assert got.value.reason == 'os_error'
        assert 'access denied (synthetic)' in got.value.detail
        assert _bytes_of(eid) == rival['bytes']          # generation 2 stays as written
        on_disk = _disk(eid)
        assert (on_disk['gen'], on_disk['state'], on_disk['owned']) == (2, 'pending', False)
        assert b.created == [name] and name in b.profiles  # the created profile survives
        assert b.deleted == []                             # zero deletions


# ── 6-8. isolation.py:867-873 — the establishment's own retry loop ─────────────

class TestTheEstablishmentRetryLoop:
    def test_an_establishment_that_conflicts_twice_is_established_once(self, tmp_path,
                                                                       monkeypatch):
        """Lines 871-872 (`except RecordChanged: pass`): the admission re-decides from
        the record as it now is, and the last retry establishes. The closest existing
        tests (test_gaps3_node_isolation_a.py's
        TestClosedEstablishmentRefusesBeforeAnythingElse, test_pv20_isolation.py's
        TestEstablish) never let a save conflict, so the retry arm is unexecuted there:
        a `pass` replaced by a `raise`, or an attempt made after the success, passes them
        both.

        Catches: not retrying at all (the arm re-raises), and retrying past success —
        another attempt would ask the boundary to create the identity a second time,
        which the boundary's own call list shows."""
        a, b, req, node = authority(tmp_path)
        eid, name = req.execution_id, iso.profile_name(req.execution_id)
        calls = _concurrent_writer(monkeypatch, conflicts=2)      # two, then it yields
        saves = _observed_saves(monkeypatch)
        rec = a.establish(req)
        assert rec.state == 'established' and rec.owned is True
        assert rec.sid == _stable_sid(name) and rec.gen == 3      # pending, owned, established
        assert _disk(eid)['state'] == 'established' and _disk(eid)['owned'] is True
        assert b.created == [name] and b.job_creates == 1         # once, never after success
        assert b.deleted == [] and b.closed == [] and b.assigned == []
        # 868's loop: three admission attempts, the first two refused by the writer
        assert [s['owned'] for s in saves] == [False, False, False, True, True]
        assert [s['gen'] for s in saves] == [0, 0, 0, 1, 2]       # the last one was written
        assert len(calls) == 5                          # three admission saves, two after
        assert _ops(node) == [] and _ledger_ops() == []           # a retried success notes nothing
        assert a.held_job(eid) == {'job': eid}

    def test_a_closed_authority_never_enters_the_admission_retry_loop(self, tmp_path,
                                                                      monkeypatch):
        """Line 867 (`self._check_establishment()` before the loop of 868): the stop is
        checked once, outside the retry loop, so a closed authority makes NO admission
        attempt even when every attempt would have conflicted — the closure wins, and
        873 is never reached. test_gaps3_node_isolation_a.py's
        test_a_stopped_core_leaves_a_resumable_record_byte_for_byte stops an authority
        with a *readable* record, so a loop that kept deciding and only then raised the
        stop (or raised `record_changed` instead) is not distinguished there.

        Catches: moving the closed check inside the loop or after it — the caller would
        be handed `record_changed`, which the end path charges to the execution as an
        establishment failure, where a stop is a cancellation — and any write or
        boundary call the refused attempts would have made."""
        a, b, req, node = authority(tmp_path)
        eid = req.execution_id
        calls = _concurrent_writer(monkeypatch, float('inf'))     # would conflict forever
        saves = _observed_saves(monkeypatch)
        a.close_admission(deadline=0.0)
        with pytest.raises(iso.IsolationClosed) as got:
            a.establish(req)
        assert isinstance(got.value, base.SpawnFailed)
        assert not isinstance(got.value, iso.IsolationUnavailable)     # closure won the loop
        assert calls == [] and saves == [] and b.available_calls == 0  # not one attempt
        assert not os.path.lexists(isolation_state(eid))              # and not one write
        assert b.mutations() == [] and b.job_creates == 0 and b.closed == []
        assert _ops(node) == [] and _ledger_ops() == []

    def test_an_establishment_that_always_conflicts_is_refused_as_record_changed(
            self, tmp_path, monkeypatch):
        """Line 873 (`raise IsolationUnavailable('record_changed', ...)`): every retry
        conflicts, so the refusal names the record, not the disk, and the loop stops at
        RECORD_RETRIES. fx32's
        test_a_record_saved_on_a_stale_read_is_refused_and_the_stored_one_stays asserts
        the `_save` conflict itself and never asks what `establish` decides when its
        retries are spent, so a generic `os_error` reason, a fourth attempt or a
        half-written record would each pass it.

        Catches: a wrong reason (an `os_error` line is a failure the record, the
        tombstone and the registry agree on; `record_changed` is only a re-decision), a
        widened loop bound, and any attempt leaving evidence, a profile or a note."""
        a, b, req, node = authority(tmp_path)
        eid = req.execution_id
        calls = _concurrent_writer(monkeypatch, float('inf'))
        saves = _observed_saves(monkeypatch)
        with pytest.raises(iso.IsolationUnavailable) as got:
            a.establish(req)
        assert got.value.reason == 'record_changed' and got.value.detail == eid
        assert got.value.reason != 'os_error'
        assert not isinstance(got.value, OSError)             # a refusal, not an I/O failure
        assert not isinstance(got.value, iso.IsolationClosed)
        assert len(calls) == iso.RECORD_RETRIES                # no fourth attempt
        assert b.available_calls == iso.RECORD_RETRIES         # and no third OS entry
        assert len(saves) == iso.RECORD_RETRIES                # one refused save per attempt
        assert not os.path.lexists(isolation_state(eid))       # nothing was ever written
        assert b.mutations() == [] and b.created == [] and b.job_creates == 0
        assert _ops(node) == [] and _ledger_ops() == []


# ── 9. isolation.py:885 — an empty SID stays empty ────────────────────────────

class TestTheOwnershipSaveInventsNoSid:
    def test_an_empty_sid_answer_is_saved_empty_and_handed_to_the_validator(self, tmp_path):
        """Line 885 (`rec.sid = sid`) with the loop of 886: the OS answered the create
        with NO SID, and Core must record that absence as the only ownership evidence
        it has, then let the §3.4 validator be the one that refuses. The closest test,
        test_pv20_isolation.py::test_the_answer_is_on_disk_before_the_job_or_the_
        invariant, only ever drives a boundary that answers with a SID, so the empty
        answer — the one case where deriving a replacement would look like it helped —
        is nowhere.

        Catches: `rec.sid = sid or _derive(...)` (inventing ownership evidence the OS
        never gave: both the boundary's derive count and the saved record show it), and
        clearing `owned` for an empty SID (the profile Core made would then be deletable
        by nobody, forever)."""
        a, b, req, node = authority(tmp_path)
        eid, name = req.execution_id, iso.profile_name(req.execution_id)
        b.sid_answer = ''                                       # the OS gave no SID at all
        seen = []
        b.on_job_facts = lambda: seen.append(a.record(eid))     # the next stage's entry
        with pytest.raises(iso.IsolationUnavailable) as got:
            a.establish(req)
        assert got.value.reason == 'condition_unmet:identity'
        assert len(seen) == 1
        at_save = seen[0]                                       # what the validator read
        assert at_save.state == 'pending' and at_save.owned is True
        assert at_save.sid == '', 'ownership was invented for an unanswered SID'
        on_disk = _disk(eid)
        assert on_disk['sid'] == '' and on_disk['owned'] is True
        assert on_disk['conditions']['identity'][0] is False    # refused by name, not guessed
        assert on_disk['state'] == 'failed'
        assert on_disk['failure'] == 'condition_unmet:identity'
        assert b.derive_calls == 0, 'a replacement SID was derived to prove ownership'
        assert b.created == [name] and b.deleted == [name]      # only its own profile, once
        # the Job is made before the validator, so the failure path must have closed it
        assert b.job_creates == 1 and b.closed == [{'job': eid}]
        assert b.assigned == []                                 # nothing was ever put in it
        assert _ledger_ops() == [] and _ops(node) == ['isolation_failed']


# ── 10. isolation.py:905 — the stop stops one writer and must not stop the other ─

class TestTheStopStopsOneWriterAndNotTheOther:
    def test_the_stop_stops_the_writer_that_owns_nothing_and_never_the_ownership_writer(
            self, tmp_path, monkeypatch):
        """Line 905 (`self._check_establishment()` inside `_save_establishment`) read
        against `_own`, which has no such check. Once the OS has made the profile, the
        record of who made it may not be refused by a stop: an owned record is the only
        thing that ever lets that profile be deleted. fx32's
        test_a_profile_created_after_the_stop_returned_is_deleted_by_its_own_
        establishment watches the whole thread race and asserts the surviving record, so
        it cannot tell a `_save_establishment` that refused from one that ran, nor a
        `_own` that saved from one that skipped.

        Catches: deleting the 905 check (a stopping Core would write the `established`
        record of a spawn it refused), and adding one to `_own` (a profile that already
        exists would go unrecorded, and nothing could ever remove it)."""
        a, b, req, node = authority(tmp_path)
        eid, name = req.execution_id, iso.profile_name(req.execution_id)
        sid = _stable_sid(name)
        checks = []
        real_check = iso.Isolation._check_establishment

        def counted(self):
            checks.append('check')
            return real_check(self)                    # the real closed check still runs

        monkeypatch.setattr(iso.Isolation, '_check_establishment', counted)
        saves = _observed_saves(monkeypatch)            # observation only
        rec = iso.IsolationRecord(execution_id=eid, profile=name, state='pending')
        assert b.create_profile(eid)['created'] is True          # the identity exists now
        a.close_admission(deadline=0.0)                 # the stop is published
        with pytest.raises(iso.IsolationClosed) as got:
            a._save_establishment(rec)
        assert isinstance(got.value, base.SpawnFailed)
        assert saves == [], '_save_establishment wrote while Core was stopping'
        assert checks == ['check']                      # the 905 check is what refused
        assert not os.path.lexists(isolation_state(eid))
        assert b.deleted == [] and _ops(node) == []
        # the contrast: an identity the OS already made is always recorded, stop or not
        owned = a._own(rec, sid)
        assert owned.owned is True and owned.state == 'pending' and owned.sid == sid
        assert [s['owned'] for s in saves] == [True]    # one writer ran, after the stop
        assert checks == ['check'], '_own asked whether Core was stopping'
        on_disk = _disk(eid)
        assert (on_disk['owned'], on_disk['sid'], on_disk['state'], on_disk['gen']) \
            == (True, sid, 'pending', 1)
        assert name in b.profiles and b.deleted == []   # its only witness is this record
        assert _ledger_ops() == [] and a.held_jobs() == {}

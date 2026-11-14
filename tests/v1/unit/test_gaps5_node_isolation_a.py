import json
import os
import zlib

import pytest

from archeus.core.domain import ids
from archeus.harnesses import base
from archeus.infra.paths import isolation_dir, isolation_state, quarantine_log, \
    verify_consumed
from archeus.node import isolation as iso
from archeus.node.pv20_switches import Pv20Switches


@pytest.fixture(autouse=True)
def no_real_win32(monkeypatch):
    hits = []
    for name in ('_CreateAppContainerProfile', '_DeleteAppContainerProfile',
                 '_GetSecurityInfoByNameW', '_CreateProcessW', '_CreateJobObjectW',
                 '_AssignProcessToJobObject', '_TerminateProcess', '_CloseHandle',
                 '_SetInformationJobObject', '_ResumeThread', '_OpenProcess'):
        def trip(*a, _name=name):
            hits.append(_name)
            raise AssertionError('the real %s was reached' % _name)
        monkeypatch.setattr(iso, name, trip, raising=False)
    yield hits
    assert hits == [], 'a real mutation primitive was reached: %r' % (hits,)


def _stable_sid(name):
    return 'S-1-15-3-9-%08d' % (zlib.crc32(str(name).encode('utf-8')) % (10 ** 8),)


class FakeBoundary:
    id = 'fake'

    def __init__(self):
        self.available_ok = True
        self.available_raises = None
        self.create_fail = None
        self.delete_fail = set()
        self.profiles = set()
        self.sids = {}
        self.on_create = None
        self.created = []
        self.deleted = []
        self.closed = []
        self.assigned = []
        self.job_creates = 0

    def available(self):
        if self.available_raises is not None:
            raise self.available_raises
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
        return {'profile': name, 'sid': self.sids.get(name) or _stable_sid(name),
                'created': True, 'existed': existed, 'package_dir': 'materialized'}

    def delete_profile(self, execution_id):
        name = iso.validated_profile(execution_id)
        self.deleted.append(name)
        if name in self.delete_fail:
            raise iso.IsolationUnavailable('profile_delete', 'in use (synthetic)')
        self.profiles.discard(name)

    def profile_exists(self, execution_id):
        return iso.profile_name(execution_id) in self.profiles

    def derive_sid(self, execution_id):
        return _stable_sid(iso.profile_name(execution_id))

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
        return {'type': 'Job', 'name': '', 'inheritable': False}

    def assign_job(self, job, process_handle):
        self.assigned.append((job, process_handle))

    def close_job(self, job):
        self.closed.append(job)

    def mutations(self):
        return self.created + self.deleted + self.assigned


class FakeNode:
    id = 'fake-node'

    def __init__(self):
        self.registry = []

    def _registry(self, line):
        self.registry.append(line)


def new_execution_id():
    return ids.new_id('execution')


def make_exec_request(execution_id, root):
    def d(name):
        p = os.path.join(root, name)
        os.makedirs(p, exist_ok=True)
        return p
    workspace = d('workspace')
    mailbox = d('mailbox')
    response = d('response')
    sentinel = d('sentinel')
    state = d('state')
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


def make_verify_request(key, root):
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


def authority(tmp_path, *, boundary=None, request=None, switches=None):
    node = FakeNode()
    b = boundary or FakeBoundary()
    req = request or make_exec_request(new_execution_id(), str(tmp_path))
    a = iso.Isolation(node, boundary=b, plan=lambda spec: req, switches=switches)
    return a, b, req, node


def _verify_key(attempt=0, vid=None):
    return iso.Principal('verify', vid or ids.new_id('verification'), attempt).key


def _record_bytes(execution_id):
    with open(isolation_state(execution_id), 'rb') as f:
        return f.read()


def _record_disk(execution_id):
    return json.loads(_record_bytes(execution_id).decode('utf-8'))


def _plant(execution_id, payload):
    os.makedirs(isolation_dir(), exist_ok=True)
    path = isolation_state(execution_id)
    data = payload if isinstance(payload, bytes) else json.dumps(payload).encode('utf-8')
    with open(path, 'wb') as f:
        f.write(data)
    return data


def _plant_record(b, execution_id, **over):
    d = iso.IsolationRecord(execution_id=execution_id,
                            profile=iso.profile_name(execution_id),
                            sid=b.derive_sid(execution_id), state='pending').as_dict()
    d.update(over)
    return _plant(execution_id, d)


def _noted(node, op=None):
    return [(l['op'], l.get('reason')) for l in node.registry
            if op is None or l['op'] == op]


def _ledger_ops():
    if not os.path.exists(quarantine_log()):
        return []
    with open(quarantine_log(), encoding='utf-8') as f:
        return [json.loads(x)['op'] for x in f.read().splitlines() if x.strip()]


class TestARecordThatNeverSettles:
    def test_an_execution_whose_record_will_not_settle_is_refused_without_being_written(
            self, tmp_path, monkeypatch):
        a, b, req, node = authority(tmp_path)
        eid = req.execution_id
        real = iso._stored_record
        arm, reads = [True], []

        def churning(path, execution_id, api):
            d = real(path, execution_id, api)
            if arm[0]:
                reads.append(execution_id)
                gen = d.get('gen', 0)
                return dict(d, gen=(0 if gen is None else gen) + 1)
            return d

        monkeypatch.setattr(iso, '_stored_record', churning)
        with pytest.raises(iso.IsolationUnavailable) as got:
            a.establish(req)
        arm[0] = False
        assert got.value.reason == 'record_changed'
        assert got.value.detail == eid
        assert not isinstance(got.value, OSError)
        assert 0 < len(reads) <= iso.RECORD_RETRIES
        assert b.mutations() == [] and b.created == []
        assert b.job_creates == 0 and b.closed == []
        assert not os.path.lexists(isolation_state(eid))
        assert _noted(node) == [] and _ledger_ops() == []
        assert a.establish(req).state == 'established'
        assert b.created == [iso.profile_name(eid)] and b.job_creates == 1


class TestAConcurrentCoreSettledIt:
    def test_a_record_another_core_settled_is_never_settled_again(self, tmp_path,
                                                                  monkeypatch):
        a, b, req, node = authority(tmp_path)
        eid = req.execution_id

        def concurrent_core_settles_it():
            other = iso.Isolation(FakeNode(), boundary=b)
            fresh = other.record(eid)
            assert fresh is not None and fresh.state == 'pending'
            fresh.state, fresh.sid = 'established', b.derive_sid(eid)
            other._save(fresh)

        b.on_create = concurrent_core_settles_it
        asked = []
        real_invariant = iso.check_invariant

        def spy_invariant(*args, **kw):
            asked.append(args)
            return real_invariant(*args, **kw)

        monkeypatch.setattr(iso, 'check_invariant', spy_invariant)
        with pytest.raises(iso.IsolationUnavailable) as got:
            a.establish(req)
        assert got.value.reason == 'record_unsettled'
        assert 'established' in got.value.detail
        d = _record_disk(eid)
        assert d['state'] == 'failed' and d['failure'] == 'record_unsettled'
        assert d['owned'] is True and d['sid'] == b.derive_sid(eid)
        assert asked == [] and b.job_creates == 0 and b.closed == []
        assert a.held_job(eid) is None
        assert b.deleted == [iso.profile_name(eid)] \
            and iso.profile_name(eid) not in b.profiles
        assert _noted(node, 'isolation_failed') == [('isolation_failed', 'record_unsettled')]
        assert _ledger_ops() == []


class TestAnAdmittedAttemptIsAdmittedOnce:
    def test_an_attempt_the_launcher_already_admitted_is_admitted_no_second_time(
            self, tmp_path, monkeypatch):
        a, b, _req, node = authority(tmp_path)
        key = _verify_key()
        req = make_verify_request(key, str(tmp_path / 'v'))
        calls = []
        real_admit = iso._admit

        def spy_admit(k):
            calls.append(k)
            return real_admit(k)

        monkeypatch.setattr(iso, '_admit', spy_admit)
        a._admitted.add(key)
        rec = a.establish(req)
        assert rec.state == 'established' and rec.sid == b.derive_sid(key)
        assert calls == []
        assert a._admitted == set()
        assert not os.path.lexists(verify_consumed(key))
        before = _record_bytes(key)
        assert b.created == [iso.profile_name(key)] and b.job_creates == 1
        with pytest.raises(iso.IsolationUnavailable) as got:
            a.establish(req)
        assert got.value.reason == 'attempt_consumed'
        assert calls == [key]
        assert _record_bytes(key) == before
        assert b.created == [iso.profile_name(key)] and b.deleted == []
        assert b.job_creates == 1 and b.closed == []
        assert _noted(node) == [] and _ledger_ops() == []


class TestTheProductionGateSkipsTheVerifier:
    def test_an_open_a4_gate_refuses_an_execution_and_never_asks_about_an_attempt(
            self, tmp_path, monkeypatch):
        switches = Pv20Switches(*[True] * 10)
        a, b, _req, node = authority(tmp_path, switches=switches)
        asked = []
        real_eligibility = iso.a4_eligibility

        def spy_eligibility(**kw):
            asked.append(kw)
            return real_eligibility(**kw)

        monkeypatch.setattr(iso, 'a4_eligibility', spy_eligibility)
        key = _verify_key()
        rec = a.establish(make_verify_request(key, str(tmp_path / 'v')))
        assert rec.state == 'established' and tuple(rec.capabilities) == ()
        assert asked == []
        ok, unmet = real_eligibility(harness_id=None, isolated_launch=True, job_held=True,
                                     sandbox=False, exception_claimed=False,
                                     evidence={'identity': (True, '')})
        assert ok is False and unmet == ('production_dispatch',)
        eid = new_execution_id()
        with pytest.raises(iso.IsolationUnavailable) as got:
            a.establish(make_exec_request(eid, str(tmp_path / 'e')))
        assert got.value.reason == 'a4_unmet' and 'production_dispatch' in got.value.detail
        assert len(asked) == 1 and asked[0]['harness_id'] is None \
            and asked[0]['job_held'] is True
        assert _record_disk(key)['state'] == 'established'
        assert _record_disk(eid)['state'] == 'failed' \
            and _record_disk(eid)['failure'] == 'a4_unmet'
        assert b.deleted == [iso.profile_name(eid)]
        assert iso.profile_name(key) in b.profiles
        assert b.closed == [{'job': eid}] and b.job_creates == 2
        assert a.held_job(eid) is None and a.held_job(key) == {'job': key}
        assert _noted(node, 'isolation_failed') == [('isolation_failed', 'a4_unmet')]
        assert _ledger_ops() == []


class TestOwnershipOutOfNothing:
    def test_ownership_is_still_written_when_the_record_went_away_under_it(self, tmp_path):
        a, b, req, node = authority(tmp_path)
        eid = req.execution_id
        name = iso.profile_name(eid)
        seen = {}

        def sweep_took_the_record():
            path = isolation_state(eid)
            seen['existed'] = os.path.lexists(path)
            if seen['existed']:
                os.remove(path)

        b.on_create = sweep_took_the_record
        rec = a.establish(req)
        assert seen == {'existed': True}
        assert rec.state == 'established' and rec.owned is True
        assert rec.sid == b.derive_sid(eid) and not rec.preexisting
        d = _record_disk(eid)
        assert d['state'] == 'established' and d['owned'] is True and d['sid'] == rec.sid
        assert d['gen'] > 0
        assert b.created == [name] and b.job_creates == 1
        assert b.deleted == [] and b.closed == []
        assert _noted(node) == [] and _ledger_ops() == []
        assert a.teardown(eid, reason='ended')['profile'] == 'torn_down'
        assert b.deleted == [name] and name not in b.profiles


class TestAnOwnershipThatNeverLands:
    def test_an_ownership_the_record_will_not_accept_is_recorded_and_its_own_identity_released(
            self, tmp_path, monkeypatch):
        a, b, req, node = authority(tmp_path)
        eid = req.execution_id
        name = iso.profile_name(eid)
        real = iso._stored_record
        armed, reads = [], []

        def churning(path, execution_id, api):
            d = real(path, execution_id, api)
            if armed:
                reads.append(execution_id)
                gen = d.get('gen', 0)
                return dict(d, gen=(0 if gen is None else gen) + 1)
            return d

        monkeypatch.setattr(iso, '_stored_record', churning)
        b.on_create = lambda: armed.append(True)
        with pytest.raises(iso.IsolationUnavailable) as got:
            a.establish(req)
        assert got.value.reason == 'os_error'
        assert 'changed under its ownership' in got.value.detail
        assert 'cleanup incomplete' in got.value.detail
        assert 0 < len(reads) <= iso.RECORD_RETRIES + 1
        d = _record_disk(eid)
        assert d['state'] == 'pending' and d['owned'] is False and d['sid'] == ''
        assert d['gen'] == 1
        assert d['failure'] == '' and d['reason'] == ''
        rec = a.record(eid)
        assert rec.state == 'pending' and rec.owned is False
        assert b.created == [name]
        assert b.deleted == [] and name in b.profiles
        assert b.mutations() == [name]
        assert b.job_creates == 0 and b.closed == [] and b.assigned == []
        assert a.held_job(eid) is None and a.held_jobs() == {}
        assert _noted(node, 'isolation_failed') == [('isolation_failed', 'os_error')]
        assert _ledger_ops() == []

        armed.clear()
        assert a.teardown(eid, reason='sweep')['profile'] == 'provenance_unknown'
        kept = _record_disk(eid)
        assert kept['state'] == 'failed' and kept['reason'] == 'provenance_unknown'
        assert kept['owned'] is False and kept['sid'] == b.derive_sid(eid)
        assert b.deleted == [] and name in b.profiles
        assert _noted(node, 'isolation_provenance_unknown') == [
            ('isolation_provenance_unknown', None)]
        before = _record_bytes(eid)
        assert a.teardown(eid, reason='sweep')['profile'] == 'provenance_unknown'
        assert _record_bytes(eid) == before


class TestThePendingWriteClaimsNothing:
    def test_a_not_owned_record_is_written_without_a_sid_or_plan_and_its_name_is_refused(
            self, tmp_path):
        a, b, req, node = authority(tmp_path)
        eid = req.execution_id
        name = iso.profile_name(eid)
        planned = [{'path': os.path.join(str(tmp_path), 'elsewhere'),
                    'access': 'rw', 'row': 'workspace'}]
        _plant_record(b, eid, state='pending', owned=False, preexisting=False,
                      sid=b.derive_sid(eid), planned=planned, failure='', reason='')
        b.profiles.add(name)
        seen = {}

        def look_while_core_waits():
            seen.update(_record_disk(eid))

        b.on_create = look_while_core_waits
        with pytest.raises(iso.IsolationUnavailable) as got:
            a.establish(req)
        assert seen, 'the boundary was never asked'
        assert seen['state'] == 'pending' and seen['owned'] is False
        assert seen['sid'] == ''
        assert seen['planned'] == []
        assert got.value.reason == 'profile_preexisting'
        assert 'was not created by Core' in got.value.detail or \
            'no record that Core created' in got.value.detail
        d = _record_disk(eid)
        assert d['state'] == 'failed' and d['failure'] == 'profile_preexisting'
        assert d['preexisting'] is True and d['owned'] is False
        assert d['sid'] == b.derive_sid(eid)
        assert b.created == [name] and b.deleted == []
        assert name in b.profiles
        assert b.job_creates == 0 and b.closed == [] and b.assigned == []
        assert _noted(node, 'isolation_failed') == [('isolation_failed', 'profile_preexisting')]
        assert _ledger_ops() == []


class TestAStopOnTheLastWrite:
    def test_a_stop_landing_on_the_established_write_publishes_nothing_and_ends_the_job(
            self, tmp_path, monkeypatch):
        a, b, req, node = authority(tmp_path)
        eid = req.execution_id
        name = iso.profile_name(eid)
        real_invariant = iso.check_invariant

        def stop_begins_on_the_last_read(api, request, identity, job_facts=None):
            a.close_admission()
            return real_invariant(api, request, identity, job_facts)

        monkeypatch.setattr(iso, 'check_invariant', stop_begins_on_the_last_read)
        with pytest.raises(iso.IsolationClosed) as got:
            a.establish(req)
        assert isinstance(got.value, base.SpawnFailed)
        assert not isinstance(got.value, iso.IsolationUnavailable)
        assert 'cleanup failed' not in str(got.value)
        d = _record_disk(eid)
        assert d['state'] == 'pending' and d['owned'] is True
        assert d['sid'] == b.derive_sid(eid) and d['failure'] == '' and d['reason'] == ''
        assert d['conditions'] == {} and d['planned'] == []
        assert b.job_creates == 1 and b.closed == [{'job': eid}]
        assert a.held_job(eid) is None and a.held_jobs() == {}
        assert b.deleted == [name] and name not in b.profiles
        assert _noted(node) == [] and _ledger_ops() == []
        assert b.assigned == []


class TestOwnershipOfAnUntrustedRecord:
    def test_ownership_of_a_record_that_cannot_be_trusted_is_never_claimed(self, tmp_path):
        a, b, req, node = authority(tmp_path)
        eid = req.execution_id
        name = iso.profile_name(eid)
        garbage = b'{ this is not json'

        def rot_the_record():
            with open(isolation_state(eid), 'wb') as f:
                f.write(garbage)

        b.on_create = rot_the_record
        with pytest.raises(iso.IsolationUnavailable) as got:
            a.establish(req)
        assert got.value.reason == 'os_error'
        assert 'changed under its ownership' in got.value.detail
        assert 'cleanup incomplete' in got.value.detail
        assert _record_bytes(eid) == garbage
        assert a.record(eid).state == 'invalid'
        assert b.deleted == [] and name in b.profiles
        assert b.created == [name]
        assert b.job_creates == 0 and b.closed == [] and b.assigned == []
        assert a.held_job(eid) is None
        assert _noted(node, 'isolation_failed') == [('isolation_failed', 'os_error')]
        assert _ledger_ops() == []


class TestABoundaryThatCannotAnswer:
    def test_a_boundary_whose_availability_cannot_be_read_is_an_os_error_not_a_platform(
            self, tmp_path):
        a, b, req, node = authority(tmp_path)
        eid = req.execution_id
        b.available_raises = OSError('the token could not be read (synthetic)')
        with pytest.raises(iso.IsolationUnavailable) as got:
            a.establish(req)
        assert got.value.reason == 'os_error'
        assert got.value.reason != 'platform'
        assert 'the token could not be read' in got.value.detail
        assert b.created == [] and b.mutations() == []
        assert b.job_creates == 0 and b.closed == [] and b.deleted == []
        d = _record_disk(eid)
        assert d['state'] == 'failed' and d['reason'] == 'os_error' \
            and d['failure'] == 'os_error'
        assert d['owned'] is False and d['preexisting'] is False and d['sid'] == ''
        assert _noted(node, 'isolation_failed') == [('isolation_failed', 'os_error')]
        assert _ledger_ops() == []

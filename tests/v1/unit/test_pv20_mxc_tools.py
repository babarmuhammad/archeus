"""Synthetic files and injected backends only; never launch a native process."""

import hashlib
import json
import stat
from types import SimpleNamespace
from uuid import uuid4

import pytest

from tools.pv20_mxc import controller, fixtures
from tools.pv20_mxc.controller import Watchdog, digest, run_batch, run_stage
from tools.pv20_mxc.fixtures import Refused, create_root, origin_matches, policy, scan
from tools.pv20_mxc.protocol import CLEANUP_FLAGS, STAGES, SUMMARY_FIELDS


class Clock:
    def __init__(self):
        self.now = 0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


def result(outcome='PASS'):
    return {'acceptance_rows': ['fixture-only'], 'controls': ['positive-control'],
            'expected': 'bounded fixture result', 'observed': 'bounded fixture result',
            'outcome': outcome, 'identity_verified': True, 'resource_policy_verified': True}


class FakeBackend:
    def __init__(self, outcome='PASS', *, hang=False, cleanup=True, armed=True):
        self.outcome = outcome
        self.hang = hang
        self.cleanup = cleanup
        self.armed = armed
        self.calls = []

    def arm_watchdog(self, root, limits):
        self.calls.append('arm')
        assert limits['kill_s'] == 5
        return self.armed

    def start_case(self, case_id, root, compiled, deadline):
        self.calls.append(case_id)

    def poll_case(self):
        return None if self.hang else result(self.outcome)

    def cancel_owned(self):
        self.calls.append('cancel')

    def stage_facts(self):
        return {'observed_backend': 'processcontainer', 'observed_tier': 'fake-only',
                'effective_policy_verified': True, 'principal_links': ['fake-psec'],
                'outer_job_links': ['fake-retained-job'], 'timestamps': ['fake-clock']}

    def begin_cleanup(self):
        self.calls.append('cleanup')

    def poll_cleanup(self):
        if not self.cleanup:
            return None
        return dict.fromkeys(CLEANUP_FLAGS, True) | {
            'mxc_disposal_result': 'verified', 'unresolved_resources': []}


@pytest.fixture
def frozen(tmp_path):
    fixture_uuid = str(uuid4())
    artifact = tmp_path / 'synthetic-probe.exe'
    artifact.write_bytes(b'never executed')
    manifest = {'stage': 'F1', 'fixture_parent': str(tmp_path),
                'fixture_uuid': fixture_uuid, 'cases': list(STAGES['F1'].cases),
                'sdk_version': '1.0.1', 'schema_version_mxc': '1.0.0',
                'policy': {'command_line': 'fixture-probe', 'systemroot': str(tmp_path)},
                'batch_id': 'fake-batch', 'candidate_sha': 'a' * 40,
                'protocol_hash': 'b' * 64, 'os_build': 'fake-build', 'architecture': 'fake',
                'command_ids': ['fake-command'],
                'runtime_hashes': {'fake': hashlib.sha256(b'never executed').hexdigest()},
                'approved_capability_inventory': [], 'fixture_inventory': ['synthetic'],
                'executed_file_hashes': {
                    str(artifact): hashlib.sha256(b'never executed').hexdigest()}}
    token_file = tmp_path / 'owner-authorization.json'
    token = {'authorization_id': 'owner-fixture-test', 'fixture_only': True,
             'manifest_hash': digest(manifest), 'stage': 'F1',
             'fixture_uuid': fixture_uuid, 'fixture_parent': str(tmp_path)}
    token_file.write_text(json.dumps(token), encoding='utf-8')
    return manifest, token_file


def execute(frozen, backend, **kwargs):
    manifest, token_file = frozen
    clock = Clock()
    return run_stage(manifest, token_file=token_file, backend=backend, native=True,
                     clock=clock, pause=clock.sleep, **kwargs)


def test_catalog_and_schema():
    assert set(STAGES) == {f'F{i}' for i in range(10)} | {f'N{i}' for i in range(1, 6)}
    assert 'pid-creation-time-reuse-refusal' in STAGES['F9'].cases
    assert 'hardlink-grant-refusal' in STAGES['N1'].cases
    assert STAGES['N4'].budget == STAGES['N5'].budget == 1800


def test_run_requires_explicit_argument_and_owner_token(frozen):
    manifest, token_file = frozen
    backend = FakeBackend()
    with pytest.raises(Refused, match='native=True'):
        run_stage(manifest, token_file=token_file, backend=backend)
    token_file.unlink()
    with pytest.raises(OSError):
        execute(frozen, backend)
    assert backend.calls == []
    assert not (token_file.parent / manifest['fixture_uuid']).exists()


def test_mutated_manifest_refused(frozen):
    manifest, _ = frozen
    manifest['policy']['ui'] = True
    backend = FakeBackend()
    with pytest.raises(Refused, match='frozen fixture manifest'):
        execute(frozen, backend)
    assert backend.calls == []


def test_missing_native_backend_is_blocked(frozen):
    manifest, token_file = frozen
    with pytest.raises(Refused, match='native backend'):
        run_stage(manifest, token_file=token_file, native=True)


def resign(frozen):
    manifest, token_file = frozen
    token = json.loads(token_file.read_text())
    token.update(stage=manifest['stage'], manifest_hash=digest(manifest))
    token_file.write_text(json.dumps(token), encoding='utf-8')


def test_artifact_change_refuses_before_backend(frozen):
    artifact = frozen[1].parent / 'synthetic-probe.exe'
    artifact.write_bytes(b'changed')
    backend = FakeBackend()
    with pytest.raises(Refused, match='hash mismatch'):
        execute(frozen, backend)
    assert backend.calls == []


@pytest.mark.parametrize('previous', ['LOCAL_SUBSET_PASS', 'FAIL', 'NOT_RUN', None])
def test_n4_subset_cannot_advance_n5(frozen, previous):
    manifest, _ = frozen
    manifest.update(stage='N5', cases=list(STAGES['N5'].cases), prerequisites={'N4': previous})
    resign(frozen)
    backend = FakeBackend()
    with pytest.raises(Refused, match='Previous acceptance stage'):
        execute(frozen, backend)
    assert backend.calls == []


def test_success_order_coverage_journal_and_summary(frozen):
    backend = FakeBackend()
    summary = execute(frozen, backend)
    assert summary['status'] == 'PASS'
    assert summary['coverage']['missing'] == []
    assert set(summary) == set(SUMMARY_FIELDS)
    assert backend.calls == ['arm', *STAGES['F1'].cases, 'cleanup']
    root = frozen[1].parent / frozen[0]['fixture_uuid']
    journal = [json.loads(line) for line in
               (root / 'evidence' / 'journal.jsonl').read_text().splitlines()]
    assert [item['sequence'] for item in journal] == list(range(len(journal)))
    assert journal[0]['event'] == 'intent'
    assert journal[-1]['event'] == 'cleanup-completion'
    assert json.loads((root / 'evidence' / 'summary.json').read_text()) == summary
    with pytest.raises(FileExistsError):
        execute(frozen, FakeBackend())


@pytest.mark.parametrize('outcome', ['FAIL', 'INCONCLUSIVE', 'BLOCKED', 'NOT_RUN'])
def test_first_failure_stops_and_retains_root(frozen, outcome):
    backend = FakeBackend(outcome)
    summary = execute(frozen, backend)
    assert summary['status'] == outcome
    assert backend.calls == ['arm', STAGES['F1'].cases[0], 'cleanup']
    assert len(summary['coverage']['missing']) == len(STAGES['F1'].cases) - 1


def test_expected_negative_contributes_to_stage_pass(frozen):
    assert execute(frozen, FakeBackend('EXPECTED_NEGATIVE'))['status'] == 'PASS'


def test_case_timeout_cancels_owned_work_and_cleans(frozen):
    backend = FakeBackend(hang=True)
    summary = execute(frozen, backend)
    assert summary['status'] == 'INCONCLUSIVE'
    assert summary['stop_reason'] == 'deadline'
    assert backend.calls[-2:] == ['cancel', 'cleanup']


def test_cleanup_timeout_quarantines(frozen):
    summary = execute(frozen, FakeBackend(cleanup=False))
    assert summary['status'] == 'INCONCLUSIVE'
    assert summary['cleanup']['quarantine'] is True
    assert summary['elapsed_ms'] >= 300000


def test_no_watchdog_no_spawn(frozen):
    backend = FakeBackend(armed=False)
    assert execute(frozen, backend)['status'] == 'BLOCKED'
    assert backend.calls == ['arm', 'cleanup']


def test_revoked_token_stops_new_cases_but_allows_owned_cleanup(frozen):
    backend = FakeBackend()
    def poll():
        frozen[1].unlink()
        return result()
    backend.poll_case = poll
    summary = execute(frozen, backend)
    assert summary['status'] == 'BLOCKED'
    assert backend.calls == ['arm', STAGES['F1'].cases[0], 'cleanup']


def test_cleanup_still_runs_when_intent_journal_fails(frozen, monkeypatch):
    real = controller.Evidence.journal
    def journal(self, event, case):
        if event == 'cleanup-intent':
            raise OSError('fake journal failure')
        return real(self, event, case)
    monkeypatch.setattr(controller.Evidence, 'journal', journal)
    backend = FakeBackend()
    summary = execute(frozen, backend)
    assert summary['status'] == 'INCONCLUSIVE'
    assert backend.calls[-1] == 'cleanup'


def test_missing_effective_backend_facts_cannot_pass(frozen):
    backend = FakeBackend()
    backend.stage_facts = lambda: {}
    assert execute(frozen, backend)['status'] == 'BLOCKED'


def test_unverified_case_cannot_pass(frozen):
    backend = FakeBackend()
    backend.poll_case = lambda: dict(result(), identity_verified=False)
    summary = execute(frozen, backend)
    assert summary['status'] == 'BLOCKED'
    assert summary['coverage']['completed'] == []


def test_batch_marks_later_stages_not_run(frozen):
    manifest, token_file = frozen
    later = dict(manifest, stage='N1')
    clock = Clock()
    summaries = run_batch([manifest, later], token_files={'F1': token_file},
                          native=True, backend=FakeBackend('FAIL'),
                          clock=clock, pause=clock.sleep)
    assert [item['status'] for item in summaries] == ['FAIL', 'NOT_RUN']


def test_scan_refuses_faked_hardlink_reparse_symlink_and_unknown_type(tmp_path, monkeypatch):
    target = tmp_path / 'synthetic'
    target.write_bytes(b'fixture')
    real = fixtures.os.lstat
    for mode, links, attrs in ((stat.S_IFREG, 2, 0), (stat.S_IFREG, 0, 0),
                               (stat.S_IFDIR, 1, 0x400), (stat.S_IFLNK, 1, 0),
                               (stat.S_IFIFO, 1, 0)):
        def fake(path, mode=mode, links=links, attrs=attrs):
            if str(path) == str(target):
                return SimpleNamespace(st_mode=mode, st_nlink=links, st_file_attributes=attrs)
            return real(path)
        monkeypatch.setattr(fixtures.os, 'lstat', fake)
        with pytest.raises(Refused):
            scan(tmp_path)


def test_readonly_grant_rescanned_at_launch(tmp_path, monkeypatch):
    root = create_root(tmp_path, str(uuid4()))
    target = root / 'runtime' / 'probe.exe'
    target.write_bytes(b'fake binary')
    compiled = policy(root, command_line='fixture-probe', systemroot=tmp_path)
    real = fixtures.os.lstat
    def fake(path):
        if str(path) == str(target):
            return SimpleNamespace(st_mode=stat.S_IFREG, st_nlink=2, st_file_attributes=0)
        return real(path)
    monkeypatch.setattr(fixtures.os, 'lstat', fake)
    with pytest.raises(Refused):
        fixtures.launch_scan(root, compiled)
    with pytest.raises(Refused):
        policy(root, command_line='fixture-probe', systemroot=tmp_path)


def test_new_hardlink_between_cases_stops_launch(frozen, monkeypatch):
    backend = FakeBackend()
    real = fixtures.os.lstat
    reads = []
    def fake(path):
        if str(path).endswith('synthetic-probe.exe'):
            reads.append(1)
            if len(reads) >= 3:
                return SimpleNamespace(st_mode=stat.S_IFREG, st_nlink=2, st_file_attributes=0)
        return real(path)
    monkeypatch.setattr(fixtures.os, 'lstat', fake)
    summary = execute(frozen, backend)
    assert summary['status'] == 'BLOCKED'
    assert backend.calls == ['arm', STAGES['F1'].cases[0], 'cleanup']


def test_policy_default_deny_ui_and_explicit_proxy(tmp_path):
    root = create_root(tmp_path, str(uuid4()))
    compiled = policy(root, command_line='fixture-probe', systemroot=tmp_path)
    assert compiled['ui'] == {'disable': True, 'clipboard': 'none', 'injection': False}
    assert compiled['process']['inheritDefaultEnv'] is False
    assert compiled['network']['ingress'] == {'default': 'deny', 'hostLoopback': 'deny'}
    assert 'runtimeConfig' not in compiled
    assert str(root) not in compiled['filesystem']['readwritePaths']
    proxy = policy(root, command_line='fixture-probe', systemroot=tmp_path, proxy_port=18080)
    assert proxy['runtimeConfig']['networkProxy'] == 'http://127.0.0.1:18080'
    assert proxy['network']['ingress']['hostLoopback'] == 'allow'
    assert 'allowedProxyPeer' not in json.dumps(proxy)


def test_ancestor_reparse_refused_before_root_creation(tmp_path, monkeypatch):
    real = fixtures.os.lstat
    def fake(path):
        if str(path) == str(tmp_path):
            return SimpleNamespace(st_mode=stat.S_IFDIR, st_nlink=1, st_file_attributes=0x400)
        return real(path)
    monkeypatch.setattr(fixtures.os, 'lstat', fake)
    with pytest.raises(Refused):
        create_root(tmp_path, str(uuid4()))


def test_pid_creation_time_and_liveness_fail_closed():
    accepted = {'pid': 123, 'creation_time': 456, 'alive': True}
    current = dict(accepted, outer_job_member=True, launcher_ancestry_verified=True)
    assert origin_matches(accepted, current)
    for changes in ({'alive': False}, {'creation_time': 457}, {'pid': 124},
                    {'outer_job_member': False}, {'launcher_ancestry_verified': False}):
        assert not origin_matches(accepted, dict(current, **changes))
    assert not origin_matches({}, current)


def test_watchdog_deadline_cancels_once():
    clock = Clock()
    calls = []
    watchdog = Watchdog(5, lambda: calls.append('cancel'), clock=clock)
    assert watchdog.check()
    clock.sleep(5)
    assert not watchdog.check()
    assert not watchdog.check()
    assert calls == ['cancel']


def test_launcher_framing_is_data_only(tmp_path):
    exe = tmp_path / 'wxc-exec.exe'
    config = tmp_path / 'policy.json'
    assert fixtures.launcher_argv(exe, config) == [str(exe), '--debug', str(config)]
    with pytest.raises(Refused):
        fixtures.launcher_argv('wxc-exec.exe', config)


def test_imports_do_not_launch_or_inspect_native_state(monkeypatch):
    import importlib.util
    import socket
    import subprocess
    def forbidden(*args, **kwargs):
        pytest.fail('Import attempted native activity')
    monkeypatch.setattr(subprocess, 'Popen', forbidden)
    monkeypatch.setattr(socket, 'socket', forbidden)
    monkeypatch.setattr(fixtures.os, 'lstat', forbidden)
    for module in (fixtures, controller):
        spec = importlib.util.spec_from_file_location('tools.pv20_mxc._import_probe', module.__file__)
        isolated = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(isolated)

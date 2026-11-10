# ruff: noqa: F811
import json
import hashlib
import os
from types import SimpleNamespace

import pytest

from tools.pv20_mxc.native import common, n2_check as n2, n5_check as n5
from tools.pv20_mxc.protocol import STAGES

from .test_mxc_boundary import sdk  # noqa: F401
from .test_pv20_native_drift import machine  # noqa: F401
from .test_pv20_isolation import os_tripwire  # noqa: F401
from .test_pv20_mxc_tools import frozen  # noqa: F401


def test_frozen_cases_have_explicit_limits():
    assert tuple(n5.LIMITATIONS) == STAGES['N5'].cases
    assert n5.BUDGET_S < STAGES['N5'].budget
    assert all(n5.LIMITATIONS.values())


@pytest.mark.parametrize('argv', [[], ['D:\\pv20-fixtures\\run'],
                                  ['D:\\pv20-fixtures\\run', '--yes'],
                                  ['C:\\elsewhere', n5.AUTHORIZATION],
                                  ['D:\\pv20-fixtures\\run', n5.AUTHORIZATION, 'extra']])
def test_no_authorization_means_no_fixture_or_process(monkeypatch, argv):
    def forbidden(*args, **kwargs):
        pytest.fail('authorization refusal performed an effect')

    monkeypatch.setattr(common, 'safe_root', forbidden)
    monkeypatch.setattr(n2, '_on_windows', forbidden)
    assert n5.main(argv) == 3


@pytest.mark.parametrize('case', n5.CASES)
def test_first_failure_is_durable_before_stop(tmp_path, case):
    path = tmp_path / 'evidence.jsonl'
    rec = n5.Evidence(path)
    with pytest.raises(common.StopRun):
        n5.require(rec, case, False, 'broken control')
    assert json.loads(path.read_text(encoding='utf-8')) == {
        'case': case, 'status': 'FAIL', 'detail': 'broken control'}
    assert rec.exit_code() == 1


@pytest.mark.parametrize('status', ['PASS', 'INCONCLUSIVE'])
def test_evidence_format_matches_other_native_scripts(tmp_path, status):
    path = tmp_path / 'rows.jsonl'
    rec = n5.Evidence(path)
    rec.record(n5.CASES[0], status, 'fixture observation')
    assert json.loads(path.read_text(encoding='utf-8'))['status'] == status
    assert rec.exit_code() == (0 if status == 'PASS' else 2)


@pytest.mark.parametrize('code,created,expected', [
    (0, None, None), (1, None, None), (259, 1234, 1234)])
def test_identity_distinguishes_exit_from_live(monkeypatch, code, created, expected):
    monkeypatch.setattr(n2, '_exit_code', lambda pid: code)
    monkeypatch.setattr(common, '_process_creation_time', lambda pid: created)
    assert n5.identity(42) == expected


@pytest.mark.parametrize('code,created', [(None, 1234), (259, None), (259, 0),
                                         (259, True), (259, '1234')])
def test_unreadable_identity_is_never_absence(monkeypatch, code, created):
    monkeypatch.setattr(n2, '_exit_code', lambda pid: code)
    monkeypatch.setattr(common, '_process_creation_time', lambda pid: created)
    with pytest.raises(OSError):
        n5.identity(42)


def test_require_does_not_record_pass_for_a_partial_fact(tmp_path):
    path = tmp_path / 'rows.jsonl'
    rec = n5.Evidence(path)
    n5.require(rec, n5.CASES[0], True, 'partial control')
    assert rec.results == [] and not path.exists()


@pytest.mark.parametrize('damage', [None, 'stage', 'cases', 'fixture_parent',
                                    'prerequisites', 'n5_script_hash', 'token', 'artifact'])
def test_manifest_token_and_artifacts_are_bound_before_fixture_creation(
        frozen, monkeypatch, damage):
    from pathlib import Path
    from tools.pv20_mxc import controller, fixtures

    manifest, token_path = frozen
    parent = manifest['fixture_parent']
    manifest.update(stage='N5', cases=list(n5.CASES), prerequisites={'N4': 'PASS'},
                    n5_script_hash=hashlib.sha256(Path(n5.__file__).read_bytes()).hexdigest())
    if damage in ('stage', 'cases', 'fixture_parent', 'prerequisites', 'n5_script_hash'):
        manifest[damage] = None
    token = {'authorization_id': 'test-only', 'fixture_only': True,
             'manifest_hash': controller.digest(manifest), 'stage': manifest['stage'],
             'fixture_uuid': manifest['fixture_uuid'], 'fixture_parent': parent}
    if damage == 'token':
        token['fixture_only'] = False
    Path(parent, 'n5-manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
    Path(parent, 'n5-authorization.json').write_text(json.dumps(token), encoding='utf-8')
    if damage == 'artifact':
        Path(next(iter(manifest['executed_file_hashes']))).write_bytes(b'changed')
    monkeypatch.setattr(common, '_validate_parent', lambda path: path)
    if damage is None:
        assert n5.authorized_manifest(parent) == manifest
    else:
        with pytest.raises(fixtures.Refused):
            n5.authorized_manifest(parent)
    assert not Path(parent, manifest['fixture_uuid']).exists()


def test_run_stops_before_next_case_on_failure(monkeypatch, tmp_path):
    calls = []

    def fail(h, rec):
        calls.append('first')
        rec.record(n5.CASES[0], 'FAIL', 'injected')

    monkeypatch.setattr(n5, 'step_candidate', fail)
    monkeypatch.setattr(n5, 'step_estop', lambda h, rec: calls.append('second'))
    h = SimpleNamespace(prepare=lambda: None, budget=SimpleNamespace(check=lambda: None))
    with pytest.raises(common.StopRun):
        n5.run(h, n5.Evidence(tmp_path / 'rows.jsonl'))
    assert calls == ['first']


@pytest.mark.parametrize('ops,invalid,count', [
    (['intent', 'ownership', 'completion'], False, 0),
    (['intent', 'ownership'], False, 0),
    (['intent', 'ownership', 'quarantine'], True, 0),
    (['intent', 'ownership', 'quarantine'], False, 1),
])
def test_estop_control_failures_stop(tmp_path, ops, invalid, count):
    launch = SimpleNamespace(cancel=lambda **kwargs: None)
    h = SimpleNamespace(start_tree=lambda tag: ('e', launch, 'job', 1),
                        ops=lambda eid: (ops, invalid), wait_job=lambda *args: count)
    with pytest.raises(common.StopRun):
        n5.step_estop(h, n5.Evidence(tmp_path / 'rows.jsonl'))


@pytest.mark.parametrize('observed', [1, 456])
def test_close_needs_confirmed_death(tmp_path, observed):
    launch = SimpleNamespace(process=SimpleNamespace(pid=42, create_time=123))
    h = SimpleNamespace(start_tree=lambda tag: ('e', launch,
                        SimpleNamespace(close=lambda: None), 1),
                        wait_dead=lambda *args: observed != 1, observe=lambda pid: observed)
    with pytest.raises(common.StopRun):
        n5.step_close(h, n5.Evidence(tmp_path / 'rows.jsonl'), n5.CASES[3])


def test_all_six_invariants_remain_explicitly_unverified(tmp_path):
    from archeus.node import isolation

    h = SimpleNamespace(m=SimpleNamespace(isolation=isolation))
    path = tmp_path / 'rows.jsonl'
    rec = n5.Evidence(path)
    n5.step_invariants(h, rec)
    rows = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
    assert len(rows) == 6
    assert [row['detail'].split(':')[0] for row in rows] == list(isolation.CONDITIONS)
    assert all(row['status'] == 'INCONCLUSIVE' for row in rows)


@pytest.mark.skipif(os.name != 'nt', reason='production native harness uses Windows paths')
def test_all_rows_use_production_classes_over_signature_checked_machine(
        machine, monkeypatch, tmp_path, sdk):
    root = tmp_path / 'n5root'
    root.mkdir()
    h = n5.Harness(str(root), sdk[0], 'C:\\Windows', n2.Budget(1e9))
    monkeypatch.setattr(h, 'observe', machine.live_ctime)
    monkeypatch.setattr(n5.time, 'monotonic', machine.clock)
    monkeypatch.setattr(n5.time, 'sleep', machine.pause)
    rec = n5.Evidence(root / n5.JOURNAL)
    try:
        n5.run(h, rec)
        journals = h.ledger.journals()
        assert journals
        for name, data in journals.items():
            records, invalid = h.m.mxc_ledger.read_records(data, name)
            assert not invalid and records[0]['op'] == 'intent'
            assert 'completion' not in [row['op'] for row in records]
        assert h.m.local.MxcLaunch.__module__ == 'archeus.node.local'
        assert type(h.ledger).__module__ == 'archeus.node.mxc_ledger'
    finally:
        assert h.wind_down() == 0
    assert set(case for case, _ in rec.results) == set(n5.CASES)
    assert all(status == 'INCONCLUSIVE' for _, status in rec.results)
    assert rec.exit_code() == 2


@pytest.mark.parametrize('case', n5.CASES)
def test_native_rows_never_become_qualification_from_standins(tmp_path, case):
    rec = n5.Evidence(tmp_path / 'rows.jsonl')
    rec.record(case, 'INCONCLUSIVE', n5.LIMITATIONS[case])
    assert rec.exit_code() == 2

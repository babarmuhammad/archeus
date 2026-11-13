"""T-239 gap closures for tools/pv20_mxc: synthetic files and injected fakes only.

Covers ten highest-risk controller branches that test_pv20_mxc_tools.py leaves
unexercised: owner-token authorization marker fields and its input size limit,
fixture-parent confinement of staged artifacts and of every scanned path, the
frozen evidence metadata gate, mid-stage first-failure stop, stage-budget
watchdog expiry between cases, cleanup verification and cleanup-error
quarantine, the case/journal evidence record shape, and a full authorized run
under forbidden network, process and home-directory seams. Style mirrors the
neighbouring test file; no native process, socket or Windows API is touched.
"""

import hashlib
import json
import os
import socket
import subprocess
from pathlib import Path
from uuid import uuid4

import pytest

from tools.pv20_mxc import controller, fixtures
from tools.pv20_mxc.controller import Evidence, case_record, run_stage
from tools.pv20_mxc.fixtures import (Refused, ancestors, create_root, launch_scan,
                                     policy)
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
             'manifest_hash': controller.digest(manifest), 'stage': 'F1',
             'fixture_uuid': fixture_uuid, 'fixture_parent': str(tmp_path)}
    token_file.write_text(json.dumps(token), encoding='utf-8')
    return manifest, token_file


def resign(manifest, token_file, **token_changes):
    token = json.loads(token_file.read_text(encoding='utf-8'))
    token.update({'stage': manifest['stage'], 'fixture_uuid': manifest['fixture_uuid'],
                  'fixture_parent': manifest['fixture_parent'],
                  'manifest_hash': controller.digest(manifest)})
    token.update(token_changes)
    token_file.write_text(json.dumps(token), encoding='utf-8')


def execute(frozen, backend, **kwargs):
    manifest, token_file = frozen
    clock = Clock()
    return run_stage(manifest, token_file=token_file, backend=backend, native=True,
                     clock=clock, pause=clock.sleep, **kwargs)


def root_of(frozen):
    return frozen[1].parent / frozen[0]['fixture_uuid']


# Branch 1 -- controller.py:29-38 (authorize): the token must carry every
# authorization marker as its own exact value, and native must be exactly True.
# Existing coverage is only a changed manifest hash and a missing file; each
# remaining marker clause is mutated here one at a time.
@pytest.mark.parametrize(('field', 'poison'), [
    ('fixture_only', 1),           # truthy but not the marker True
    ('fixture_only', False),
    ('authorization_id', ''),      # owner label missing
    ('stage', 'N1'),               # token minted for another stage
    ('fixture_uuid', 'not-the-fixture-uuid'),
    ('fixture_parent', 'D:\\archeus-worktrees\\pv20-fixtures-other'),
])
def test_authorization_marker_fields_refuse_before_backend(frozen, field, poison):
    manifest, token_file = frozen
    resign(manifest, token_file, **{field: poison})
    backend = FakeBackend()
    with pytest.raises(Refused, match='frozen fixture manifest'):
        execute(frozen, backend)
    assert backend.calls == []
    assert not root_of(frozen).exists()
    with pytest.raises(Refused, match='frozen fixture manifest'):
        execute(frozen, FakeBackend())  # still refuses on a fresh backend


def test_native_must_be_exactly_true_not_merely_truthy(frozen):
    manifest, token_file = frozen
    for impostor in (1, 'true'):
        with pytest.raises(Refused, match='native=True'):
            run_stage(manifest, token_file=token_file, native=impostor,
                      backend=FakeBackend(), clock=Clock(), pause=lambda s: None)


# Branch 2 -- controller.py:21-25 (read_json): an owner token beyond the input
# bound is refused as data, never parsed, and no root is created.
def test_oversized_token_refused_unparsed_before_backend(frozen):
    manifest, token_file = frozen
    token_file.write_text(token_file.read_text(encoding='utf-8')
                          + ' ' * 262145, encoding='utf-8')
    backend = FakeBackend()
    with pytest.raises(Refused, match='JSON exceeds input limit'):
        execute(frozen, backend)
    assert backend.calls == []
    assert not root_of(frozen).exists()


# Branch 3 -- controller.py:58-61 (verify_manifest): every executed artifact
# must be staged under the approved fixture parent; a path that escapes the
# D:\archeus-worktrees\pv20-fixtures-style parent (sibling directory or a home/credential path)
# is a refusal, not a hash check.
@pytest.mark.parametrize('escapee', ['outside-dir', 'fakehome-credentials'])
def test_artifact_outside_fixture_parent_refuses_before_backend(frozen, tmp_path, escapee):
    manifest, token_file = frozen
    if escapee == 'outside-dir':
        outside = tmp_path.parent / (tmp_path.name + '-outside')
        outside.mkdir(exist_ok=True)
        rogue = outside / 'synthetic-probe.exe'
    else:
        rogue = tmp_path.parent / (tmp_path.name + '-fakehome') / '.aws' / 'credentials'
        rogue.parent.mkdir(parents=True, exist_ok=True)
    rogue.write_bytes(b'never executed')
    manifest['executed_file_hashes'][str(rogue)] = \
        hashlib.sha256(b'never executed').hexdigest()
    resign(manifest, token_file)
    backend = FakeBackend()
    with pytest.raises(Refused, match='approved fixture parent'):
        execute(frozen, backend)
    assert backend.calls == []
    assert not root_of(frozen).exists()


# Branch 4 -- fixtures.py:26-32, 45-51, 115-122: confinement primitives. The
# fixture parent must be absolute and normalized, the fresh root must be the
# canonical UUID itself, and no launch grant may be the root or leave it.
def test_parent_must_be_absolute_and_normalized(tmp_path):
    with pytest.raises(Refused, match='Absolute normalized path'):
        ancestors('pv20-fixtures/fake')
    with pytest.raises(Refused, match='Absolute normalized path'):
        ancestors(Path(str(tmp_path)) / '..' / 'elsewhere')


def test_non_canonical_uuid_refuses_before_any_mkdir(tmp_path):
    rogue = str(uuid4()).upper()
    with pytest.raises(Refused, match='Canonical UUID required'):
        create_root(tmp_path, rogue)
    assert not (tmp_path / rogue).exists()
    assert not any(child.name.lower() == rogue.lower() for child in tmp_path.iterdir())


def test_launch_grants_may_not_be_root_or_escape_it(tmp_path):
    root = create_root(tmp_path, str(uuid4()))
    compiled = policy(root, command_line='fixture-probe', systemroot=tmp_path)
    launch_scan(root, compiled)  # sane policy passes
    broad = dict(compiled, filesystem=dict(
        compiled['filesystem'], readwritePaths=[str(root)]))
    with pytest.raises(Refused, match='Grant outside fixture or broad root grant'):
        launch_scan(root, broad)
    escape = dict(compiled, filesystem=dict(
        compiled['filesystem'], readonlyPaths=[str(tmp_path.parent)]))
    with pytest.raises(Refused, match='Grant outside fixture or broad root grant'):
        launch_scan(root, escape)


# Branch 5 -- controller.py:42-57 (verify_manifest): frozen evidence metadata
# is a preflight gate; each missing or inconsistent entry refuses before any
# backend call, so a stage can never launch with unverifiable provenance.
@pytest.mark.parametrize(('field', 'poison', 'message'), [
    ('candidate_sha', 'a' * 39, 'candidate or protocol hash'),
    ('protocol_hash', 'b' * 63, 'candidate or protocol hash'),
    ('batch_id', None, 'Missing frozen evidence metadata'),
    ('fixture_inventory', None, 'Missing frozen evidence metadata'),
    ('executed_file_hashes', {}, 'executed-file inventory'),
    ('runtime_hashes', {'fake': 'c' * 64}, 'Runtime hashes must appear'),
])
def test_frozen_evidence_metadata_gate(frozen, field, poison, message):
    manifest, token_file = frozen
    manifest[field] = poison
    resign(manifest, token_file)
    backend = FakeBackend()
    with pytest.raises(Refused, match=message):
        execute(frozen, backend)
    assert backend.calls == []
    assert not root_of(frozen).exists()


# Branch 6 -- controller.py:205-212 with the finally at 226-243: a failure at
# a mid-stage case stops the stage immediately, the remainder is never started
# (NOT_RUN, still listed in coverage['missing']), prior completions are kept,
# and owned cleanup runs exactly once afterwards.
class Scripted(FakeBackend):
    def __init__(self, outcomes):
        super().__init__()
        self.outcomes = list(outcomes)
        self.started = []

    def start_case(self, case_id, root, compiled, deadline):
        self.calls.append(case_id)
        self.started.append(case_id)
        if len(self.started) > len(self.outcomes):
            pytest.fail('stage continued past the first failure')

    def poll_case(self):
        return result(self.outcomes[len(self.started) - 1])


def test_mid_stage_failure_stops_rest_and_cleans_once(frozen):
    cases = STAGES['F1'].cases
    backend = Scripted(['PASS', 'PASS', 'FAIL'])
    summary = execute(frozen, backend)
    assert summary['status'] == 'FAIL'
    assert summary['stop_reason'] == cases[2]
    assert backend.calls == ['arm', cases[0], cases[1], cases[2], 'cleanup']
    assert summary['coverage']['completed'] == list(cases[:3])
    assert summary['coverage']['missing'] == list(cases[3:])
    assert [item['id'] for item in summary['cases']] == list(cases[:3])
    assert summary['cases'][-1]['outcome'] == 'FAIL'
    assert summary['cleanup']['quarantine'] is False  # cleanup fully verified
    assert root_of(frozen).exists()  # retained, never deleted by cleanup
    journal = [json.loads(line) for line in
               (root_of(frozen) / 'evidence' / 'journal.jsonl').read_text().splitlines()]
    assert [item['event'] for item in journal] == \
        ['intent', 'completion'] * 3 + ['cleanup-intent', 'cleanup-completion']
    assert json.loads((root_of(frozen) / 'evidence' / 'summary.json')
                      .read_text(encoding='utf-8')) == summary


# Branch 7 -- controller.py:84-88 consumed at 185-186: the stage-budget
# watchdog expiring between cases cancels owned work exactly once, marks the
# stage INCONCLUSIVE/deadline and leaves the not-run remainder missing.
def test_stage_budget_watchdog_expires_between_cases(frozen, monkeypatch):
    cases = STAGES['F1'].cases
    manifest, token_file = frozen
    clock = Clock()
    backend = FakeBackend()
    real_journal = Evidence.journal

    def journal(self, event, case):
        if event == 'completion' and case == cases[0]:
            clock.now = STAGES['F1'].budget  # stage budget fully spent
        return real_journal(self, event, case)

    monkeypatch.setattr(controller.Evidence, 'journal', journal)
    summary = run_stage(manifest, token_file=token_file, backend=backend, native=True,
                        clock=clock, pause=clock.sleep)
    assert summary['status'] == 'INCONCLUSIVE'
    assert summary['stop_reason'] == 'deadline'
    assert backend.calls.count('cancel') == 1  # terminate fired once only
    assert backend.calls == ['arm', cases[0], 'cancel', 'cleanup']
    assert summary['coverage']['completed'] == [cases[0]]
    assert summary['coverage']['missing'] == list(cases[1:])


# Branch 8 -- controller.py:240-249 finally: after a case failure, cleanup is
# trusted only when every flag, the MXC disposal result and the unresolved
# list are clean; anything else (or a raising cleaner) quarantines the root
# and downgrades to INCONCLUSIVE, while the journal and summary still complete.
def _tampered_cleanup(kind):
    if kind == 'flag':
        return dict(dict.fromkeys(CLEANUP_FLAGS, True) | {
            'mxc_disposal_result': 'verified', 'unresolved_resources': []},
            owned_workers_exited=False)
    if kind == 'disposal':
        return dict(dict.fromkeys(CLEANUP_FLAGS, True) | {
            'unresolved_resources': []}, mxc_disposal_result='unverified')
    if kind == 'unresolved':
        return dict.fromkeys(CLEANUP_FLAGS, True) | {
            'mxc_disposal_result': 'verified', 'unresolved_resources': ['retained-job']}
    raise AssertionError(kind)


@pytest.mark.parametrize('kind', ['flag', 'disposal', 'unresolved', 'raises'])
def test_cleanup_after_failure_must_be_fully_verified(frozen, kind):
    backend = FakeBackend('FAIL')
    if kind == 'raises':
        def begin():
            backend.calls.append('cleanup')
            raise RuntimeError('fake cleaner fault')
        backend.begin_cleanup = begin
    else:
        payload = _tampered_cleanup(kind)
        backend.poll_cleanup = lambda: dict(payload)
    summary = execute(frozen, backend)
    assert summary['status'] == 'INCONCLUSIVE'
    assert summary['stop_reason'] == ('cleanup-error' if kind == 'raises'
                                      else 'cleanup-unverified')
    assert summary['cleanup']['quarantine'] is True
    assert 'cleanup' in backend.calls  # attempted exactly once
    assert backend.calls.count('cleanup') == 1
    assert root_of(frozen).exists()  # uncertain cleanup retains, never deletes
    journal = (root_of(frozen) / 'evidence' / 'journal.jsonl').read_text().splitlines()
    assert json.loads(journal[-1])['event'] == 'cleanup-completion'
    assert json.loads((root_of(frozen) / 'evidence' / 'summary.json')
                      .read_text(encoding='utf-8')) == summary


# Branch 9 -- controller.py:91-116 and 119-132: the evidence record itself.
# Case evidence must be exactly the seven required fields with a known
# outcome, non-empty controls and acceptance mapping, verification for any
# positive outcome, and bounded size; the journal only accepts its four
# events within its byte bound; the summary schema is checked on creation.
def test_case_record_exact_field_set_and_outcome_are_mandatory():
    assert case_record('c1', result(), 7) == dict(result(), id='c1', elapsed_ms=7)
    dropped = result()
    dropped.pop('observed')
    with pytest.raises(Refused, match='Invalid case evidence'):
        case_record('c1', dropped, 1)
    with pytest.raises(Refused, match='Invalid case evidence'):
        case_record('c1', dict(result(), outcome='Succeeded'), 1)
    with pytest.raises(Refused, match='Invalid case evidence'):
        case_record('c1', dict(result(), extra=1), 1)


@pytest.mark.parametrize(('field', 'poison'), [
    ('controls', []), ('controls', 'not-a-list'), ('acceptance_rows', [])])
def test_case_record_requires_nonempty_list_mapping(field, poison):
    with pytest.raises(Refused, match='Missing case controls or acceptance mapping'):
        case_record('c1', dict(result(), **{field: poison}), 1)


@pytest.mark.parametrize('outcome', ['PASS', 'EXPECTED_NEGATIVE'])
@pytest.mark.parametrize('field', ['identity_verified', 'resource_policy_verified'])
def test_positive_outcomes_require_both_verifications(outcome, field):
    with pytest.raises(Refused, match='Unverified identity or resource policy'):
        case_record('c1', dict(result(outcome), **{field: False}), 1)
    # Polarity: a FAIL records without verification, only positives are gated.
    assert case_record('c1', dict(result('FAIL'), **{field: False}), 1)['id'] == 'c1'


def test_case_record_is_size_bounded():
    with pytest.raises(Refused, match='Case evidence exceeds limit'):
        case_record('c1', dict(result(), observed='x' * 8300), 1)


def test_evidence_schema_journal_events_and_size_bound(tmp_path):
    root = create_root(tmp_path, str(uuid4()))
    short = {key: None for key in SUMMARY_FIELDS}
    short.pop('status')
    with pytest.raises(Refused, match='Incomplete evidence schema'):
        Evidence(root, short)
    assert not (root / 'evidence' / 'journal.jsonl').exists()
    evidence = Evidence(root, {key: None for key in SUMMARY_FIELDS})
    with pytest.raises(Refused, match='Invalid journal event'):
        evidence.journal('flush', 'fake-case')
    big = 'x' * 100000
    evidence.journal('intent', big)
    evidence.journal('completion', big)
    with pytest.raises(Refused, match='Journal exceeds evidence limit'):
        evidence.journal('intent', big)
    body = (root / 'evidence' / 'journal.jsonl').read_bytes()
    assert len(body) <= 262144
    assert [json.loads(line)['sequence'] for line in body.splitlines()] == [0, 1]


# Branch 10 -- whole controller path: one complete authorized stage with every
# network, process-spawn and filesystem seam guarded. Nothing may open a
# socket, spawn anything, or open/lstat anything under the fake account home
# (credentials planted there), and the generated policy must redirect every
# home/cache variable into the fixture root and deny the sibling zones.
def test_full_authorized_run_touches_no_network_no_home_no_process(tmp_path, monkeypatch):
    fakehome = tmp_path / 'fakehome'
    for secret in ('.aws/credentials', '.ssh/id_rsa', '.git-credentials',
                   '.azure/accessTokens.json'):
        secret_path = fakehome / secret
        secret_path.parent.mkdir(parents=True, exist_ok=True)
        secret_path.write_text('sentinel-never-read', encoding='utf-8')
    monkeypatch.setenv('HOME', str(fakehome))

    def forbidden(name):
        def raiser(*args, **kwargs):
            pytest.fail(f'authorized run attempted {name}')
        return raiser

    monkeypatch.setattr(socket, 'socket', forbidden('socket'))
    monkeypatch.setattr(socket, 'create_connection', forbidden('create_connection'))
    monkeypatch.setattr(socket, 'getaddrinfo', forbidden('getaddrinfo'))
    monkeypatch.setattr(subprocess, 'Popen', forbidden('Popen'))
    monkeypatch.setattr(subprocess, 'run', forbidden('run'))
    monkeypatch.setattr(subprocess, 'check_output', forbidden('check_output'))
    for name in ('system', 'execv', 'spawnv', 'startfile'):
        if hasattr(os, name):
            monkeypatch.setattr(os, name, forbidden(name))

    opened, inspected = [], []
    real_open = Path.open

    def guarded_open(self, *args, **kwargs):
        path = Path(str(self))
        opened.append(str(path))
        if path == fakehome or fakehome in path.parents:
            pytest.fail(f'controller opened a path under the account home: {path}')
        if not path.is_relative_to(tmp_path):
            pytest.fail(f'controller opened a path outside the temp area: {path}')
        return real_open(self, *args, **kwargs)

    real_lstat = fixtures.os.lstat

    def guarded_lstat(path, *args, **kwargs):
        target = Path(str(path))
        inspected.append(str(target))
        if target == fakehome or fakehome in target.parents:
            pytest.fail(f'controller inspected the account home: {target}')
        return real_lstat(path, *args, **kwargs)

    monkeypatch.setattr(Path, 'open', guarded_open)
    monkeypatch.setattr(fixtures.os, 'lstat', guarded_lstat)

    backend = FakeBackend()
    staged_manifest, staged_token = _fresh(tmp_path)
    clock = Clock()
    summary = run_stage(staged_manifest, token_file=staged_token, backend=backend,
                        native=True, clock=clock, pause=clock.sleep)
    assert summary['status'] == 'PASS'
    assert backend.calls == ['arm', *STAGES['F1'].cases, 'cleanup']
    # The guards were live: real files were opened and scanned, and none of
    # them was the home, a credential or a socket.
    assert opened and inspected
    assert not any('credentials' in item or 'id_rsa' in item or '.git-credentials'
                   in item for item in opened + inspected)
    assert not any(Path(item) == fakehome or fakehome in Path(item).parents
                   for item in opened + inspected)

    staged = tmp_path / staged_manifest['fixture_uuid']
    compiled = policy(staged, command_line='fixture-probe', systemroot=str(tmp_path))
    env_map = dict(entry.split('=', 1) for entry in compiled['process']['env'])
    assert set(env_map) == {'SYSTEMROOT', 'LOCALAPPDATA', 'USERPROFILE', 'HOME',
                            'TEMP', 'TMP'}
    for key in ('LOCALAPPDATA', 'USERPROFILE', 'HOME'):
        assert Path(env_map[key]).is_relative_to(staged)
    for key in ('TEMP', 'TMP'):
        assert Path(env_map[key]).is_relative_to(staged)
    assert compiled['process']['inheritDefaultEnv'] is False
    for name in ('q', 'verifier', 'core-private', 'authority-fixtures', 'evidence'):
        assert str(staged / name) in compiled['filesystem']['deniedPaths']
    assert compiled['network'] == {'egress': {'default': 'deny'},
                                   'ingress': {'default': 'deny', 'hostLoopback': 'deny'}}
    assert 'processContainer' not in compiled and 'runtimeConfig' not in compiled
    frozen_text = json.dumps(compiled)
    assert str(fakehome) not in frozen_text and 'sentinel-never-read' not in frozen_text


def _fresh(tmp_path):
    """Build the same frozen fixture as the fixture, but keyed to tmp_path."""
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
             'manifest_hash': controller.digest(manifest), 'stage': 'F1',
             'fixture_uuid': fixture_uuid, 'fixture_parent': str(tmp_path)}
    token_file.write_text(json.dumps(token), encoding='utf-8')
    return manifest, token_file

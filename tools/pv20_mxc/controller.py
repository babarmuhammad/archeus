"""Serial, authorization-gated orchestration over an explicitly supplied backend.

No native backend is supplied: identity inspection, atomic Job assignment and
owned disposal must be reviewed together before one can be admitted.
"""

import hashlib
import json
from pathlib import Path
import time

from .fixtures import Refused, ancestors, create_root, launch_scan, policy, write_json
from .protocol import CLEANUP_FLAGS, OUTCOMES, STAGES, SUMMARY_FIELDS


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False,
                                     separators=(',', ':')).encode()).hexdigest()


def read_json(path):
    path = ancestors(path)
    if path.stat().st_size > 262144:
        raise Refused('JSON exceeds input limit')
    return json.loads(path.read_text(encoding='utf-8'))


def authorize(manifest, token_file, *, native):
    if native is not True:
        raise Refused('Explicit native=True required')
    token = read_json(token_file)
    if (token.get('manifest_hash') != digest(manifest)
            or token.get('stage') != manifest['stage']
            or token.get('fixture_uuid') != manifest['fixture_uuid']
            or token.get('fixture_parent') != manifest['fixture_parent']
            or not token.get('authorization_id')
            or token.get('fixture_only') is not True):
        raise Refused('Owner token does not authorize this frozen fixture manifest')
    return token


def verify_manifest(manifest):
    for key, size in (('candidate_sha', 40), ('protocol_hash', 64)):
        value = manifest.get(key, '')
        if len(value) != size or any(char not in '0123456789abcdef' for char in value):
            raise Refused('Missing candidate or protocol hash')
    for key in ('batch_id', 'os_build', 'architecture', 'command_ids',
                'runtime_hashes', 'approved_capability_inventory', 'fixture_inventory'):
        if manifest.get(key) is None:
            raise Refused('Missing frozen evidence metadata')
    artifacts = manifest.get('executed_file_hashes')
    if not isinstance(artifacts, dict) or not artifacts:
        raise Refused('Missing frozen executed-file inventory')
    parent = ancestors(manifest['fixture_parent'])
    if manifest.get('runtime_hashes') and not set(manifest['runtime_hashes'].values()).issubset(
            set(artifacts.values())):
        raise Refused('Runtime hashes must appear in executed-file inventory')
    for name, expected in artifacts.items():
        path = Path(name)
        if not path.is_relative_to(parent):
            raise Refused('Artifacts must be staged under the approved fixture parent')
        ancestors(path)
        hashed = hashlib.sha256()
        with path.open('rb') as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                hashed.update(chunk)
        if hashed.hexdigest() != expected:
            raise Refused('Executed artifact hash mismatch')


class Watchdog:
    """Deadline logic usable by an independent, owner-authorized fixture observer.

    Observer receives retained process identities, never a duplicate outer Job
    handle. Its terminate callback must be ownership-bound and nonblocking.
    """

    def __init__(self, deadline, terminate, *, clock=time.monotonic):
        self.deadline = deadline
        self.terminate = terminate
        self.clock = clock
        self.expired = False

    def check(self):
        if self.clock() >= self.deadline and not self.expired:
            self.expired = True
            self.terminate()
        return not self.expired


class Evidence:
    def __init__(self, root, summary):
        if set(summary) != set(SUMMARY_FIELDS):
            raise Refused('Incomplete evidence schema')
        self.root = root
        self.summary = summary
        self.sequence = 0
        self.path = root / 'evidence' / 'journal.jsonl'
        with self.path.open('xb'):
            pass

    def journal(self, event, case):
        if event not in ('intent', 'completion', 'cleanup-intent', 'cleanup-completion'):
            raise Refused('Invalid journal event')
        ancestors(self.path)
        entry = {'sequence': self.sequence, 'event': event, 'case': case}
        encoded = json.dumps(entry, sort_keys=True).encode() + b'\n'
        if self.path.stat().st_size + len(encoded) > 262144:
            raise Refused('Journal exceeds evidence limit')
        with self.path.open('ab') as stream:
            stream.write(encoded)
            stream.flush()
        self.sequence += 1

    def finish(self):
        write_json(self.root / 'evidence' / 'summary.json', self.summary)


def case_record(case_id, result, elapsed):
    required = {'acceptance_rows', 'controls', 'expected', 'observed', 'outcome',
                'identity_verified', 'resource_policy_verified'}
    if set(result) != required or result['outcome'] not in OUTCOMES:
        raise Refused('Invalid case evidence')
    for name in ('controls', 'acceptance_rows'):
        if not isinstance(result[name], list) or not result[name]:
            raise Refused('Missing case controls or acceptance mapping')
    if result['outcome'] in ('PASS', 'EXPECTED_NEGATIVE'):
        if result['identity_verified'] is not True or result['resource_policy_verified'] is not True:
            raise Refused('Unverified identity or resource policy')
    if len(json.dumps(result)) > 8192:
        raise Refused('Case evidence exceeds limit')
    return dict(result, id=case_id, elapsed_ms=elapsed)


def run_stage(manifest, *, token_file, native=False, backend=None, clock=time.monotonic,
              pause=time.sleep):
    """Run only with an owner-created token and reviewed injected backend.

    Backend methods must be nonblocking. arm_watchdog establishes an independent
    watchdog before any native work, enforcing process/memory/CPU and wall limits.
    start_case establishes suspended launcher/Job membership before resume;
    poll_case returns structured evidence, never inferred launcher success.
    begin_cleanup/poll_cleanup operate on retained owned resources only. No
    method may sweep PIDs, adopt journal-only ownership or delete fixture roots.
    """
    token = authorize(manifest, token_file, native=native)
    verify_manifest(manifest)
    stage_id = manifest['stage']
    stage = STAGES[stage_id]
    if backend is None:
        raise Refused('BLOCKED: reviewed native backend is not supplied')
    if stage_id.startswith('N') and stage_id != 'N1':
        previous = 'N' + str(int(stage_id[1:]) - 1)
        if manifest.get('prerequisites', {}).get(previous) != 'PASS':
            raise Refused('Previous acceptance stage must PASS; local subsets cannot advance')
    if manifest.get('cases') != list(stage.cases):
        raise Refused('Frozen complete case order required')
    if manifest.get('sdk_version') != '1.0.1' or manifest.get('schema_version_mxc') != '1.0.0':
        raise Refused('Pinned SDK and schema required')
    root = create_root(manifest['fixture_parent'], manifest['fixture_uuid'])
    compiled = policy(root, **manifest['policy'])
    write_json(root / 'spawn-config' / 'policy.json', compiled)
    summary = {key: manifest.get(key) for key in SUMMARY_FIELDS}
    summary.update(schema_version=1, authorization_id=token['authorization_id'],
                   authorized_scope={'fixture_only': True, 'stage': stage_id},
                   manifest_hash=digest(manifest), requested_backend='processcontainer',
                   policy_hash=digest(compiled), ui_policy=compiled['ui'],
                   effective_policy_verified=False, cases=[],
                   coverage={'required': list(stage.cases), 'completed': [],
                             'missing': list(stage.cases)},
                   cleanup={'quarantine': True}, status='BLOCKED', stop_reason='',
                   timeout_limits={'case_s': 10, 'establishment_s': 15, 'kill_s': 5,
                                   'stage_s': stage.budget, 'teardown_s': 300,
                                   'processes': 64 if stage_id == 'N4' else 8,
                                   'memory_bytes': (4096 if stage_id == 'N4' else 512) * 1024**2,
                                   'user_cpu_s': 600, 'priority': 'below-normal'})
    evidence = Evidence(root, summary)
    started = clock()
    stage_deadline = started + stage.budget
    watchdog = Watchdog(stage_deadline, backend.cancel_owned, clock=clock)
    try:
        if backend.arm_watchdog(root, summary['timeout_limits']) is not True:
            raise Refused('Independent watchdog and pre-spawn limits are not verified')
        for case_id in stage.cases:
            if not watchdog.check():
                raise TimeoutError
            evidence.journal('intent', case_id)
            authorize(manifest, token_file, native=native)
            verify_manifest(manifest)
            if digest(compiled) != summary['policy_hash']:
                raise Refused('Frozen policy changed')
            launch_scan(root, compiled)
            began = clock()
            deadline = min(began + 10, stage_deadline)
            backend.start_case(case_id, root, compiled, deadline)
            result = None
            while clock() < deadline and watchdog.check():
                result = backend.poll_case()
                if result is not None:
                    break
                pause(min(0.05, max(0, deadline - clock())))
            if result is None or clock() >= deadline:
                backend.cancel_owned()
                raise TimeoutError
            record = case_record(case_id, result, int((clock() - began) * 1000))
            summary['cases'].append(record)
            summary['coverage']['completed'].append(case_id)
            summary['coverage']['missing'].remove(case_id)
            evidence.journal('completion', case_id)
            if record['outcome'] not in ('PASS', 'EXPECTED_NEGATIVE'):
                summary.update(status=record['outcome'], stop_reason=case_id)
                break
        else:
            facts = backend.stage_facts()
            required = {'observed_backend', 'observed_tier', 'effective_policy_verified',
                        'principal_links', 'outer_job_links', 'timestamps'}
            if (set(facts) != required or facts['observed_backend'] != 'processcontainer'
                    or facts['effective_policy_verified'] is not True
                    or any(not facts[key] for key in required - {'effective_policy_verified'})):
                raise Refused('Missing effective backend, policy, identity or Job evidence')
            summary.update(facts, status='PASS')
    except TimeoutError:
        summary.update(status='INCONCLUSIVE', stop_reason='deadline')
    except Exception:
        summary.update(status='BLOCKED', stop_reason='controller-or-backend-refusal')
    finally:
        try:
            evidence.journal('cleanup-intent', stage_id)
        except Exception:
            summary.update(status='INCONCLUSIVE', stop_reason='journal-error')
        try:
            backend.begin_cleanup()
            cleanup_deadline = clock() + 300
            cleanup = None
            while clock() < cleanup_deadline:
                cleanup = backend.poll_cleanup()
                if cleanup is not None:
                    break
                pause(0.05)
            clean = (cleanup is not None and clock() < cleanup_deadline
                     and all(cleanup.get(key) is True for key in CLEANUP_FLAGS)
                     and cleanup.get('mxc_disposal_result') == 'verified'
                     and cleanup.get('unresolved_resources') == [])
            summary['cleanup'] = dict(cleanup or {}, quarantine=not clean)
            if not clean:
                summary.update(status='INCONCLUSIVE', stop_reason='cleanup-unverified')
        except Exception:
            summary.update(status='INCONCLUSIVE', stop_reason='cleanup-error')
        summary['elapsed_ms'] = int((clock() - started) * 1000)
        evidence.journal('cleanup-completion', stage_id)
        evidence.finish()
    return summary


def run_batch(manifests, *, token_files, **kwargs):
    results = []
    stopped = False
    for manifest in manifests:
        if stopped:
            results.append({'stage': manifest['stage'], 'status': 'NOT_RUN'})
            continue
        try:
            result = run_stage(manifest, token_file=token_files[manifest['stage']], **kwargs)
        except (Refused, OSError, KeyError, ValueError):
            result = {'stage': manifest['stage'], 'status': 'BLOCKED',
                      'stop_reason': 'preflight-refusal'}
        results.append(result)
        stopped = result['status'] != 'PASS'
    return results


def write_batch(path, results):
    write_json(path, {'schema_version': 1, 'stages': results})

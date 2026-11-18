"""Frozen case order and conservative budgets, not native acceptance claims."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Stage:
    cases: tuple[str, ...]
    budget: int = 600


STAGES = {
    'F0': Stage(('schema-artifacts-license', 'cli-contract', 'identity-disposal-side-effects')),
    'F1': Stage(('positive-controls', 'p-q-token-psec', 'suspended-job-assignment',
                 'child-grandchild', 'core-death')),
    'F2': Stage(('positive-controls', 'hardlink-grant-refusal', 'access-matrix',
                 'hostile-creator-ancestor-acls', 'aliases', 'handle-transfer')),
    'F3': Stage(('host-controls', 'deny-all-both-directions', 'proxy-reach',
                 'forbidden-endpoints', 'peer-exclusion')),
    'F4': Stage(('containment-canary-before', 'blocked-ui-matrix',
                 'explicit-enabled-ui-matrix', 'containment-canary-after')),
    'F5': Stage(('broker-controls', 'synthetic-agent-edit', 'data-only-import')),
    'F6': Stage(('pinned-codex-version-help', 'fake-broker-tool-cycle')),
    'F7': Stage(('containment-canary-before', 'git-bash-child-git', 'containment-canary-after')),
    'F8': Stage(('authority-positive-controls', 'synthetic-file-agent-ipc-denial')),
    'F9': Stage(('live-origin', 'host-forwarder-refusal', 'dead-owner-refusal',
                 'pid-creation-time-reuse-refusal')),
    'N1': Stage(('positive-controls', 'p-q-token-psec', 'hardlink-grant-refusal',
                 'access-matrix', 'hostile-creator-ancestor-acls', 'aliases',
                 'handle-transfer', 'synthetic-authority-denial', 'child-grandchild',
                 'launcher-death', 'outer-job-close', 'core-death', 'stale-reopen')),
    'N2': Stage(('production-adapter', 'effective-policy', 'positive-controls',
                 'seven-resource-classes', 'hostile-descendants', 'setup-faults-no-spawn',
                 'revocation', 'disposal-quarantine', 'restart-reconciliation'), 1200),
    'N3': Stage(('host-controls', 'deny-all-both-directions', 'broker-reach',
                 'forbidden-ipv4-ipv6-descendants', 'wrong-peer-squatting-replacement',
                 'malformed-replay-destination-model-redirect-limits',
                 'privileged-effect-origin-matrix', 'pid-exit-reuse-races',
                 'revocation-broker-core-death'), 1200),
    'N4': Stage(('copy-only-seed', 'real-cli-fake-broker', 'stream-edit-commit-stop-resume',
                 'data-only-import', 'hostile-git-inert-controls', 'two-fresh-verifiers',
                 'authority-peer-network-denials', 'limits-forged-results',
                 'separately-authorized-live-provider'), 1800),
    'N5': Stage(('candidate-dispatch-identities-jobs', 'e-stop-rearm-refusal',
                 'hung-core-sentinel-registry-kill', 'core-death', 'restart-reconciliation',
                 'each-invariant-no-spawn', 'unsupported-routes-no-fallback',
                 'sentinel-present-absent-denied', 'forged-replayed-lifecycle',
                 'outer-job-sole-ownership'), 1800),
}

OUTCOMES = {'PASS', 'EXPECTED_NEGATIVE', 'FAIL', 'INCONCLUSIVE', 'BLOCKED', 'NOT_RUN'}
CLEANUP_FLAGS = ('owned_workers_exited', 'outer_jobs_empty', 'grants_revoked',
                 'descriptors_restored', 'registration_absence_verified')
SUMMARY_FIELDS = tuple('''schema_version batch_id stage fixture_uuid authorization_id
authorized_scope protocol_hash manifest_hash candidate_sha executed_file_hashes os_build
architecture sdk_version runtime_hashes schema_version_mxc requested_backend observed_backend
observed_tier policy_hash effective_policy_verified ui_policy command_ids timestamps elapsed_ms
timeout_limits principal_links outer_job_links approved_capability_inventory cases coverage
cleanup status stop_reason fixture_inventory'''.split())

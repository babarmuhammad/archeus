# ruff: noqa: F811  (the imported fixtures are taken as arguments)
"""G6 `os_isolation` scenarios: the PV-20 acceptance rows (design section 4) as
scenarios over fakes, in the shape of tests/v1/judge/test_g06_security.py.

Two kinds, and the difference is the point. A scenario that runs here drives
production code (the real HTTP gate over a fake process table, `LocalNode.spawn`
over a fake boundary) and shows what Core does when the OS reports what the fake says.
It is NOT evidence that any OS boundary holds: the gates it exercises are closed in
production and no native call is made. A scenario marked `native` is drafted, not
run: the row can only be established against the real MXC boundary (N-protocol stages,
all NOT_RUN for these rows), so it skips unless ARCHEUS_REAL_BOUNDARY=1 and then fails
loudly instead of passing empty. ADR-0053: nothing here lets a document call V1
OS-confined."""

import os
import re
from dataclasses import replace

import pytest

from archeus.api import origin, routes
from archeus.core.domain import ids
from archeus.harnesses import base
from archeus.node import local, mxc_ledger
from archeus.node.origin_native import ESTABLISHED, TcpRow, native_readers
from archeus.node.origin_windows import WindowsOriginBackend

from v1.integration.test_pv20_mxc_agent_path import (  # noqa: F401  (fixtures used by name)
    agent_case, checks, no_process, registry_lines, sdk)
from v1.unit.test_origin_native import JOB, T0, FakeApi

pytestmark = pytest.mark.os_isolation

native = pytest.mark.skipif(
    os.environ.get('ARCHEUS_REAL_BOUNDARY') != '1',
    reason='UNVERIFIED (native NOT_RUN): this row needs the real MXC boundary')


def draft(row):
    pytest.fail('os_isolation row %d is drafted, not implemented: it needs the MXC boundary '
                'adapter and its native fixture (completion plan C2, N-protocol)' % row)


# ── scenarios that run: Core's own behaviour against a fake OS ──

def _gate(tc, table):
    """Core's real HTTP gate, switched on, with the native backend and attestor over
    a fake process table: the peer's port is whatever the client really connected from."""
    api = FakeApi()
    table(api)

    class Spy(WindowsOriginBackend):
        def attest(self, context):
            api.peer = context.remote_endpoint[1]
            return super().attest(context)

    api.tcp_rows = lambda: [TcpRow('127.0.0.1', api.peer, '127.0.0.1', tc.port,
                                   ESTABLISHED, 4124)]
    core = tc.core.api
    core.origin_backend = Spy(readers=native_readers(
        api, core_port=tc.port, jobs=lambda: [JOB], clock=lambda: T0))
    core.origin_registry = origin.CorePathRegistry((tc.port,))
    core.origin_enforcement_enabled = True


def _refused(r):
    return r.status == 403 and r.json()['error'] == 'origin_refused'


def _guarded():
    return [r for r in routes.ROUTES if routes.CLASS[(r.method, r.path)] != 'public']


def _call(tc, r):
    path = r.path.replace('{id}', 'x').replace('/*', '/x.js')
    return tc.http(r.method, path, body={} if r.method == 'POST' else None)


def test_row_04_a_peer_inside_a_core_job_holding_the_local_token_is_refused_every_route(tc):
    """Row 4: the hook token or the local token an execution holds buys no route
    while its process is attested as an execution (inside Core's Job, under the launcher)."""
    _gate(tc, lambda api: api.contained())
    for r in _guarded():
        assert _refused(_call(tc, r)), (r.method, r.path)


def test_row_04_the_same_requests_from_the_user_are_not_refused_by_the_gate(tc):
    _gate(tc, lambda api: api.user())
    assert tc.http('GET', '/v1/health').status == 200
    assert tc.http('GET', '/v1/missions').status == 200


def test_row_04_an_execution_that_left_its_job_is_still_refused(tc):
    """Launcher ancestry alone, with no Job membership, is not the user."""
    def escaped(api):
        api.contained()
        api.table[4124] = replace(api.table[4124], in_jobs=False)
    _gate(tc, escaped)
    assert _refused(tc.http('GET', '/v1/health'))


def test_row_05_an_execution_origin_cannot_re_arm_after_an_estop_even_with_the_token(tc):
    """The user halts; a re-arm from the execution's process is refused at the gate
    before any guard or credential, so the halt stands."""
    _gate(tc, lambda api: api.user())
    assert tc.http('POST', '/v1/estop', body={'idempotency_key': 'g6-estop'}).status == 200
    _gate(tc, lambda api: api.contained())
    r = tc.http('POST', '/v1/rearm', body={'idempotency_key': 'g6-rearm'})
    assert _refused(r)


CONDITIONS = {
    'identity unavailable': lambda b: setattr(b, 'create_fail', 'profile_create'),
    'boundary unavailable': lambda b: setattr(b, 'available_ok', False),
    'a grant not established': lambda b: setattr(b, 'grant_ok', False),
    'a broad principal holds write': lambda b: setattr(b, 'broad', 'S-1-1-0'),
    "Core's own state is granted": lambda b: setattr(b, 'core_state_granted', True),
    'a network capability is present': lambda b: setattr(b, 'caps', ('S-1-15-3-1',)),
    'the Job is inheritable': lambda b: setattr(b, 'job_inheritable', True),
    'the Job is named': lambda b: setattr(b, 'job_named', True),
    "the Job's name cannot be read": lambda b: setattr(b, 'job_name_unknown', True),
}


@pytest.mark.parametrize('unmet', CONDITIONS)
def test_row_10_with_a_condition_unmet_nothing_is_launched_and_nothing_falls_back(
        tmp_path, sdk, no_process, unmet):
    """Row 10: no configuration disables the invariant; an unmet condition is no spawn,
    no registry spawn line, no detached process, and no retry by Core."""
    case = agent_case(tmp_path, sdk)
    CONDITIONS[unmet](case.boundary)
    with pytest.raises(base.SpawnFailed, match='isolation'):
        case.node.spawn(case.agent, case.spec, isolated=True)
    assert case.boundary.launch_calls == [] and case.boundary.backend.spawned == []
    assert not [x for x in registry_lines() if x.get('op') == 'spawn']
    assert no_process == []


def test_row_08_an_estop_with_core_up_ends_the_tree_through_the_job(tmp_path, sdk, no_process):
    """Row 8, Core up: ending the Job reaps the launcher tree; nothing is left running
    and the Job is closed exactly once."""
    case = agent_case(tmp_path, sdk)
    case.boundary.kill_on_close = True
    handle = case.node.spawn(case.agent, case.spec, isolated=True)
    job = case.boundary.launch_calls[0]['job']
    case.node.kill(case.agent, handle)
    case.node.fence_isolation(case.spec.execution_id)
    assert case.boundary.launches[0].process.is_alive() is False
    assert case.boundary.closed == [job]
    assert case.authority.held_job(case.spec.execution_id) is None


def test_row_14_with_no_confined_identity_no_check_command_runs(checks):
    """Row 14: with the verification identity unavailable nothing is launched, and the
    answer is an error, never an exit code a verification could read as a pass."""
    checks.boundary.create_fail = 'profile_create'
    result = checks.run(ids.new_id('verification'), 0)
    assert checks.boundary.launch_calls == []
    assert result['exit_code'] is None and result['error']


def test_row_15_a_workload_that_reports_no_exit_is_never_a_clean_end(tmp_path, sdk):
    """Row 15 / A7: only the Core-owned outcome reader gives an exit; a process that
    prints a result and gives none ends unverified, with nothing completed."""
    case = agent_case(tmp_path, sdk, agent=lambda process: None)
    case.node.spawn(case.agent, case.spec, isolated=True)
    launch = case.boundary.launches[0]
    with pytest.raises(local.staging.StageError, match='outcome'):
        launch.wait()
    assert launch.completed is None
    assert launch.end_state['state'] == mxc_ledger.DEAD_UNVERIFIED


# ── rows that only the real boundary can establish: drafted, skipped ──

@native
def test_row_01_a_code_change_works_under_isolation_through_the_broker():
    """Edit, commit locally, reach the provider only through the broker, hand the push
    to Core. Needs the real CLI inside MXC (N4a) and the broker transport (B10)."""
    draft(1)


@native
def test_row_02_each_credential_authority_is_denied_under_isolation_and_open_without():
    """A synthetic sentinel in Credential Manager, a package registry file, an SSH key
    and agent, a Git token store: the isolated read is denied, the baseline read
    succeeds, and the test asserts the delta. MXC-CRED is NOT_RUN (F8)."""
    draft(2)


@native
def test_row_03_the_local_token_path_cannot_be_read_from_inside_the_container():
    """Under isolation, reading run/local-token is denied (boolean)."""
    draft(3)


@native
def test_row_06_the_execution_cannot_author_a_response_a_flag_or_core_state():
    """Request writable; response, flags, halt/pause/handoff/approval state and another
    execution's directory unwritable, from inside the container."""
    draft(6)


@native
def test_row_07_an_unreadable_sentinel_halts_while_the_mailbox_stays_writable():
    """Present halts, absent proceeds, undeterminable halts, with the sentinel
    unreadable from the isolated identity."""
    draft(7)


@native
def test_row_09_a_grandchild_shell_is_in_the_job_and_denied_like_its_parent():
    """A descendant is inside the container and the Job and fails rows 2 and 3 itself.
    N1 shows Job inheritance for the launcher tree only."""
    draft(9)


@native
def test_row_11_a_killed_core_leaves_no_isolated_process_and_the_restart_never_adopts():
    """Real Core death, then a restarted Core reconciling from the ledger. The fake
    level is test_pv20_isolation.py TestRestartReconciliation; real death is N5."""
    draft(11)


@native
def test_row_12_hostile_git_config_in_the_workspace_is_inert_and_the_import_is_data_only():
    """The execution's repository holds hooks, filters and refs; Core's pinned git
    over it runs none, and the user's repository metadata is unreachable. N4 case."""
    draft(12)


@native
def test_row_13_after_the_end_the_identity_can_no_longer_reach_the_workspace():
    """MXC has no profile or ACE to delete; what is proved is that a process left over
    from the ended execution cannot read or write the workspace. N5."""
    draft(13)


def test_every_acceptance_row_has_a_scenario_here_and_none_is_silently_dropped():
    have = {int(m.group(1)) for m in (re.match(r'test_row_(\d+)_', n) for n in globals()) if m}
    assert have == set(range(1, 16))

"""G6 — approval boundaries and destructive-action controls.

P9 (p9-design-gate D21): *a locked deny cannot be loosened by a narrower scope*
scripts a mid-execution `terraform destroy`, which only the action stage sees
(the P11 hook), so it is P11's, its body unchanged — and its objective is left
without a planner recording on purpose, so no plan-level denial can make it
pass early. The P9 function beside it asks the same of the plan gate.
"""

import pytest

from .client import CoreClientError
from .support import events_of, wait_for


def test_a_locked_deny_cannot_be_loosened_by_a_narrower_scope(client, rig):
    rig.script_harness('t1', [{'emit': {'type': 'tool', 'name': 'Bash',
                                        'input': 'terraform destroy -auto-approve'}}])
    m = client.create_mission(title='Prod', objective='Destructive on prod')
    blocked = wait_for(lambda: client.get_mission(m['id'])['state'] in ('BLOCKED', 'FAILED'))
    assert blocked


def test_the_brain_principal_can_never_approve(client, rig):
    client.create_mission(title='Deploy', objective='Ship to prod')
    apr = wait_for(lambda: events_of(client, 'approval.requested'))[0]['subject']['id']
    brain = rig.principal_client('brain')
    with pytest.raises(CoreClientError) as err:
        brain.decide_approval(apr, 'approve', idempotency_key='b')
    assert err.value.status == 403


def test_a_locked_deny_cannot_be_loosened_at_the_plan_gate(client):
    """A user-level ALLOW for destructive actions does not reach under the
    locked GLOBAL floor: the plan is denied, nothing is approved, and the
    denial names the floor rule (p9-design-gate §4.2, X05)."""
    client.set_policy_rule(scope_level='USER', action_class='destructive', decision='ALLOW',
                           idempotency_key='loosen')
    m = client.create_mission(title='Staging', objective='Destroy the staging database')
    blocked = wait_for(lambda: (client.get_mission(m['id']).get('planning_blocked') or {})
                       .get('kind') == 'policy')
    assert blocked
    got = client.get_mission(m['id'])
    assert got['state'] == 'BLOCKED' and got['plan_id'] is None
    assert got['planning_blocked']['denied'][0]['rule'] == 'builtin:floor:destructive-prod'
    assert not events_of(client, 'approval.requested')
    assert [e['payload']['trigger'] for e in events_of(client, 'mission.state_changed')
            if e['subject']['id'] == m['id']][-1] == 'plan_denied'


def test_revoking_a_device_closes_its_live_stream(client, rig):
    phone = rig.device('phone', scopes=('observe',))
    stream = phone.open_stream()
    rig.revoke(phone)
    assert stream.closed()


def test_a_token_in_the_query_string_is_rejected(client, rig):
    assert rig.http_get('/v1/now?token=' + rig.device_token()).status == 401


# ── P20 slice E (ADR-0049, D6): what an execution loads from its settings sources ──

def _first_execution(client):
    prepared = wait_for(lambda: events_of(client, 'execution.prepared'))
    return prepared[0]['subject']['id']


def test_an_execution_records_its_settings_sources_and_excludes_them_by_default(client, rig):
    """Nothing opted in: the execution is spawned with every settings source
    left out, MCP strict with no server, skills disabled, no plugin; and the
    record of what those sources hold, with what became of each, is its read."""
    client.create_mission(title='Inherit', objective='Run one task')
    got = client.execution(_first_execution(client))
    inv = got['inventory']
    assert inv['flags'] == {'setting_sources': [], 'strict_mcp_config': True,
                            'mcp_servers': [], 'disable_slash_commands': True,
                            'plugin_dirs': []}
    assert inv['observed'] is False and inv['opt_ins'] == []
    assert {i['status'] for i in inv['items']} <= {'excluded', 'not_excludable', 'builtin'}
    # the CLI's own plugins are said, as outside Archeus's controls (P20 O5)
    assert {(i['source'], i['type'], i['status']) for i in inv['items']
            if i['status'] == 'builtin'} == {('cli', 'plugin', 'builtin')}
    assert got['inventory_sha256']


def _progress_lines(client):
    return [line for ev in events_of(client, 'execution.progress')
            for line in ev['payload']['last']]


# ── P20 slice F (ADR-0052, PV-22): tool removal beneath the hook ──────────────

@pytest.mark.tool_removal
def test_a_tool_the_task_does_not_hold_never_runs_and_never_reaches_the_hook(client, rig):
    """The task holds `write_repo` only: Bash is absent from the process's
    tools, so the call never runs and Core is never asked about it; the held
    Write is still judged, and allowed. Every MCP tool is denied while no
    server is opted in, and Skill is absent while no skill is."""
    rig.script_harness('t1', [
        {'emit': {'type': 'tool', 'name': 'Bash', 'input': 'git push origin main'}},
        {'emit': {'type': 'tool', 'name': 'mcp__gh__create_issue', 'input': {}}},
        {'emit': {'type': 'tool', 'name': 'Skill', 'input': {'skill': 'any'}}},
        {'emit': {'type': 'tool', 'name': 'Write',
                  'input': {'file_path': 'notes.txt', 'content': 'x'}}}])
    m = client.create_mission(title='Removal', objective='Write one note')
    wait_for(lambda: client.get_mission(m['id'])['state'] == 'COMPLETED')
    hooks = [ev['payload']['decision'] for ev in events_of(client, 'execution.hook')]
    assert hooks == ['allow']                                   # the Write, alone
    lines = _progress_lines(client)
    assert lines.count('tool_unavailable') == 3 and 'tool Write: notes.txt' in lines
    assert not [x for x in lines if x.startswith(('tool Bash', 'tool mcp__', 'tool Skill'))]
    # the inventory is slice E's, unchanged: tool removal is not recorded in it
    got = client.execution(_first_execution(client))
    assert got['inventory']['inventory_version'] == 2 and 'tools' not in got['inventory']['flags']


def test_only_a_user_device_opts_a_settings_source_in(client, rig):
    """An opt-in is the user's (ADR-0035's pattern): the brain principal is
    refused, the user's change is one row whose version counts every change."""
    acc = client.register_account(harness_id='fake', label='Work', auth_kind='api_key')['id']
    with pytest.raises(CoreClientError) as err:
        rig.principal_client('brain').set_opt_in(acc, 'mcp', 'gh', True)
    assert err.value.status == 403
    first = client.set_opt_in(acc, 'mcp', 'gh', True)
    out = client.set_opt_in(acc, 'mcp', 'gh', False)
    assert (first['opt_in']['version'], out['opt_in']['version']) == (1, 2)
    (row,) = client.opt_ins()
    assert (row['owner'], row['name'], row['opted_in'], row['version']) == (
        'account', 'gh', False, 2)
    with pytest.raises(CoreClientError) as err:
        client.set_opt_in(acc, 'source', 'project', True)       # not the account's source
    assert err.value.status == 400

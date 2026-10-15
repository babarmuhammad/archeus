"""P20 slice E (PV-10; ADR-0049, D6): settings-source opt-ins and the inventory,
through Core.

The opt-in command (a user device only; versioned; account and project apart;
`changed` explicit), the exact scope an opt-in applies in, the routes' scopes,
the CLI, and the execution path end to end on the fake harness standing in for
Claude Code's settings sources: the inventory is taken before the process
exists, stored redacted as an artifact the execution references, read back by
the execution read, and the process is given exactly the flags it records. An
inventory that cannot be taken starts nothing; a deny reaches the agent as the
exit-code-2 block.
"""

import hashlib
import json
import os
import subprocess
import sys
import time

import pytest

from archeus.cli import main as cli
from archeus.core.application import authorization as A
from archeus.core.application import commands, executions as X, lifecycle, optins, world
from archeus.core.domain import entities, ids
from archeus.harnesses import base, sources
from archeus.harnesses.fake import FakeHarness
from archeus.infra.artifacts import store
from archeus.infra.paths import ExecPaths, processes_registry
from archeus.node.local import LocalNode
from claude_sessions import proc

from v1.integration.test_execution import DONE, TOOL, Rig, _running, ended
from v1.integration.test_policy import AUTO, task

TOKEN = 'Bearer ' + 'z' * 30


def _write(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(obj, f)


def _git_commit(root):
    """A project is a git repository; its committed `.claude/` and `.mcp.json`
    are what a task's worktree holds."""
    for args in (['init', '-q'], ['add', '-A'],
                 ['-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-qm', 'init']):
        subprocess.run(['git', *args], cwd=root, check=True, capture_output=True)


def _git_commit_empty(root):
    subprocess.run(['git', 'init', '-q'], cwd=root, check=True, capture_output=True)


@pytest.fixture
def x(db, tmp_path, monkeypatch):
    """The execution rig on a fake harness that stands in for Claude Code's
    settings sources, an account whose home has hooks, a plugin, an MCP server
    and a secret, and a project (a git repository) with its own settings and
    server committed."""
    monkeypatch.setattr(sources, 'MANAGED', str(tmp_path / 'no-managed.json'))
    home, root = str(tmp_path / 'home'), str(tmp_path / 'proj')
    hooks = {'PreToolUse': [{'hooks': [{'type': 'command',
                                        'command': 'curl -H "Authorization: %s" x' % TOKEN}]}]}
    _write(os.path.join(home, 'settings.json'), {'hooks': hooks, 'env': {'K': 'sk-' + 'q' * 30}})
    _write(os.path.join(home, '.claude.json'), {'mcpServers': {'gh': {'command': 'gh-mcp'}}})
    _write(os.path.join(root, '.claude', 'settings.json'), {'permissions': {'deny': ['Read(x)']}})
    _write(os.path.join(root, '.mcp.json'), {'mcpServers': {'db': {'command': 'db-mcp'}}})
    _git_commit(root)
    rig = Rig(db, adapters=[FakeHarness(sources=True)])
    rig.home, rig.root = home, root
    rig.acc = rig.account('Work', home_ref=home)
    rig.prj = rig.do(world.create_project, who=rig.user, name='p', root_paths=[root])[
        'project']['id']
    yield rig
    rig.cleanup()


def ready_in(x, project_id, *tasks_):
    mid = x.do(commands.create_mission, who=x.user, title='M', objective='o',
               project_id=project_id, success_criteria=[AUTO])['id']
    for trig in ('start', 'understood'):
        x.do(x.missions.fire, mission_id=mid, trigger=trig, reason='test')
    x.do(x.missions.context_ready, mission_id=mid)
    out = x.propose(mid, *(tasks_ or [task('t1', 'write_repo')]))
    assert out['mission']['state'] == 'APPROVED', out
    x.do(x.missions.fire, mission_id=mid, trigger='dispatch', reason='go')
    x.do(x.work.ready_tasks, mission_id=mid)
    return mid


def opt(x, owner_id, kind, name, opted_in=True, **kw):
    return x.do(optins.set_opt_in, who=x.user, owner_id=owner_id, kind=kind, name=name,
                opted_in=opted_in, **kw)


def run_one(x, mid):
    e = x.drive(mid, lambda: x.exe(mission_id=mid))
    x.drive(mid, ended(x, e.id))
    return x.state(e.id)


def started(e):
    with open(ExecPaths(e.id).stream, encoding='utf-8') as f:
        return next(json.loads(line) for line in f if '"started"' in line)


# ── the command: a user device, versioned, account and project apart ─────────

def test_I01_an_account_opt_in_is_one_row_whose_version_counts_every_change(x):
    got = opt(x, x.acc, 'mcp', 'gh')
    assert got['changed'] and (got['opt_in']['version'], got['opt_in']['opted_in']) == (1, True)
    assert opt(x, x.acc, 'mcp', 'gh')['changed'] is False                 # already so
    out = opt(x, x.acc, 'mcp', 'gh', opted_in=False)
    assert (out['changed'], out['opt_in']['version'], out['opt_in']['opted_in']) == (
        True, 2, False)
    back = opt(x, x.acc, 'mcp', 'gh')
    assert (back['opt_in']['id'], back['opt_in']['version']) == (got['opt_in']['id'], 3)
    (row,) = x.all(entities.OptIn)
    assert (row.account_id, row.project_id, row.opted_in) == (x.acc, None, True)
    evs = x.events('opt_in.changed')
    assert [(e['payload']['opted_in'], e['payload']['version']) for e in evs] == [
        (True, 1), (False, 2), (True, 3)]
    assert {e['payload']['owner'] for e in evs} == {'account'}


def test_I02_a_project_opt_in_is_the_projects_alone(x):
    out = opt(x, x.prj, 'source', 'project')
    assert out['opt_in']['project_id'] == x.prj and out['opt_in']['account_id'] is None
    (ev,) = x.events('opt_in.changed')
    assert (ev['payload']['owner'], ev['scope']['project']) == ('project', x.prj)
    opt(x, x.acc, 'plugin', 'p@m')
    assert sorted((r.owner, r.kind) for r in x.all(entities.OptIn)) == [
        ('account', 'plugin'), ('project', 'source')]


def test_I03_an_opt_out_of_what_was_never_opted_in_writes_nothing(x):
    assert opt(x, x.acc, 'plugin', 'p@m', opted_in=False) == {'opt_in': None, 'changed': False}
    assert x.all(entities.OptIn) == [] and x.events('opt_in.changed') == []


def test_I04_only_a_user_device_may_and_only_for_a_real_owner_within_its_sources(x):
    with pytest.raises(A.NotPermitted):
        x.do(optins.set_opt_in, who=x.system, owner_id=x.acc, kind='mcp', name='gh',
             opted_in=True)
    with pytest.raises(lifecycle.NotFound):
        opt(x, ids.new_id('account'), 'mcp', 'gh')
    with pytest.raises(ValueError):
        opt(x, ids.new_id('mission'), 'mcp', 'gh')
    with pytest.raises(ValueError):
        opt(x, x.acc, 'source', 'project')           # the account holds `user` only
    with pytest.raises(ValueError):
        opt(x, x.prj, 'source', 'user')              # the project holds project and local
    with pytest.raises(ValueError):
        opt(x, x.acc, 'plugin', '../../evil')
    v1 = opt(x, x.acc, 'mcp', 'gh')['opt_in']['version']
    with pytest.raises(lifecycle.VersionConflict):
        opt(x, x.acc, 'mcp', 'gh', opted_in=False, expected_version=v1 + 1)
    assert x.all(entities.OptIn)[0].opted_in is True
    assert len(x.events('opt_in.changed')) == 1


def test_I05_an_opt_in_applies_to_exactly_its_own_account_and_project(x):
    other_acc = x.account('Other', home_ref=x.home + '2')
    os.makedirs(x.root + '2')
    _git_commit_empty(x.root + '2')
    other_prj = x.do(world.create_project, who=x.user, name='q',
                     root_paths=[x.root + '2'])['project']['id']
    opt(x, x.acc, 'mcp', 'gh')
    opt(x, x.prj, 'source', 'project')
    opt(x, x.prj, 'mcp', 'db')
    opt(x, x.prj, 'mcp', 'db', opted_in=False)
    with x.db.read() as r:
        assert optins.effective(r, account_id=x.acc, project_id=x.prj) == (
            ('account', 'mcp', 'gh'), ('project', 'source', 'project'))
        assert optins.effective(r, account_id=other_acc, project_id=x.prj) == (
            ('project', 'source', 'project'),)
        assert optins.effective(r, account_id=x.acc, project_id=other_prj) == (
            ('account', 'mcp', 'gh'),)
        assert optins.effective(r, account_id=None, project_id=None) == ()


# ── the execution: inventory before the process, flags from the record ───────

def test_I06_an_execution_records_its_inventory_and_is_given_exactly_its_flags(x):
    mid = ready_in(x, x.prj)
    e = run_one(x, mid)
    assert e.state == 'ENDED_OK' and e.inventory_sha256
    data = store.get(e.inventory_sha256)
    assert hashlib.sha256(data).hexdigest() == e.inventory_sha256
    (art,) = x.all(entities.Artifact, id=e.inventory_sha256)
    assert (art.media_type, art.size) == ('application/json', len(data))
    inv = json.loads(data)
    assert inv['flags']['setting_sources'] == [] and inv['flags']['disable_slash_commands']
    with x.db.read() as r:
        assert X.view(r, e.id)['inventory'] == inv
    argv = started(e)['argv']
    assert argv == ['--setting-sources', '', '--strict-mcp-config', '--disable-slash-commands']
    (prep,) = [ev for ev in x.events('execution.prepared') if ev['subject']['id'] == e.id]
    assert prep['payload']['inventory'] == e.inventory_sha256


def test_I07_the_owners_opt_ins_reach_the_spawn_and_no_one_elses(x):
    opt(x, x.acc, 'mcp', 'gh')
    opt(x, x.prj, 'source', 'project')
    e = run_one(x, ready_in(x, x.prj))
    inv = json.loads(store.get(e.inventory_sha256))
    assert inv['opt_ins'] == [{'owner': 'account', 'kind': 'mcp', 'name': 'gh'},
                              {'owner': 'project', 'kind': 'source', 'name': 'project'}]
    argv = started(e)['argv']
    assert argv[:2] == ['--setting-sources', 'project'] and '--strict-mcp-config' in argv
    assert started(e)['mcp_servers'] == ['gh']               # never the project's `db`
    assert [i['status'] for i in inv['items'] if i['name'] == 'db'] == ['excluded']
    # a mission with no project gets the account's opt-ins and nothing of the project's
    e2 = run_one(x, x.ready())
    assert e2.account_id == x.acc
    assert json.loads(store.get(e2.inventory_sha256))['opt_ins'] == [
        {'owner': 'account', 'kind': 'mcp', 'name': 'gh'}]
    assert started(e2)['argv'][:2] == ['--setting-sources', '']


def test_I08_the_stored_inventory_carries_no_secret(x):
    opt(x, x.acc, 'source', 'user')
    e = run_one(x, ready_in(x, x.prj))
    raw = store.get(e.inventory_sha256).decode('utf-8')
    assert 'z' * 30 not in raw and 'q' * 30 not in raw and '[redacted]' in raw
    assert any(i['type'] == 'hook' and i['status'] == 'opted_in'
               for i in json.loads(raw)['items'])


def test_I09_an_inventory_that_cannot_be_taken_starts_nothing(x, monkeypatch):
    def broken(spec, *, isolated=False):
        raise OSError('disk')
    monkeypatch.setattr(x.registry.get('fake'), 'inventory', broken)
    mid = ready_in(x, x.prj)
    t = x.drive(mid, lambda: (lambda t: t if t.state == 'FAILED' else None)(x.task_of(mid)))
    es = [r for r in x.all(entities.Execution) if r.task_id == t.id]
    # charged, so a failure that persists spends the task's attempts and stops
    # there, never one new execution per tick
    assert len(es) == t.max_attempts
    assert {(e.state, e.stop_reason, e.charged, e.pid, e.inventory_sha256) for e in es} == {
        ('ABANDONED', 'workspace', True, None, None)}
    assert not any(os.path.exists(ExecPaths(e.id).stream) for e in es)


def test_I10_a_deny_reaches_the_agent_as_the_exit_code_2_block(x):
    x.scenarios['t1'] = [{'emit': {'type': 'working'}}, {'sleep': 0.8},
                         {'emit': {'type': 'tool', 'name': 'Write',
                                   'input': {'file_path': 'a.py', 'content': 'x'}}},
                         {'sleep': 5}]
    mid = x.ready(task('t1', 'write_repo', 'read'))
    e = _running(x, mid)
    x.rule('USER', 'write_repo', 'DENY')         # what the next hook request meets
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        x.manager.tick()
        evs = [json.loads(line) for line in open(ExecPaths(e.id).stream, encoding='utf-8')
               if line.startswith('{')] if os.path.exists(ExecPaths(e.id).stream) else []
        denied = [v for v in evs if v.get('type') == 'tool_denied']
        if denied:
            break
        time.sleep(0.05)
    assert denied and denied[0]['reason'], evs
    assert 'hook_error' not in [v.get('type') for v in evs]
    assert [ev['payload']['decision'] for ev in x.events('execution.hook')] == ['deny']


# ── T-099: the MCP config holds keys, so it lives only while a process runs ──

def _mcp_running(x, sleep=30):
    opt(x, x.acc, 'mcp', 'gh')
    x.scenarios['t1'] = [{'emit': {'type': 'working'}}, {'sleep': sleep}, DONE]
    mid = ready_in(x, x.prj)
    e = _running(x, mid)
    assert os.path.exists(ExecPaths(e.id).mcp)
    argv = started(e)['argv']
    assert argv[argv.index('--mcp-config') + 1] == ExecPaths(e.id).mcp
    return mid, e


def test_T099_a_clean_exit_leaves_no_mcp_config(x):
    mid, e = _mcp_running(x, sleep=0.5)
    x.drive(mid, ended(x, e.id))
    assert x.state(e.id).state == 'ENDED_OK'
    assert not os.path.exists(ExecPaths(e.id).mcp)


def test_T099_a_stopped_execution_leaves_no_mcp_config(x):
    mid, e = _mcp_running(x)
    x.do(X.Executions(missions=x.missions).stop_execution, who=x.user, execution_id=e.id)
    x.drive(mid, ended(x, e.id))
    assert x.state(e.id).state == 'ENDED_KILLED'
    assert not os.path.exists(ExecPaths(e.id).mcp)


def test_T099_a_spawn_that_fails_leaves_no_mcp_config(x, monkeypatch):
    opt(x, x.acc, 'mcp', 'gh')
    monkeypatch.setattr(base.proc, 'spawn_detached', lambda *a, **k: (None, 'no process'))
    mid = ready_in(x, x.prj)
    refused = lambda: [r for r in x.all(entities.Execution) if r.state == 'ABANDONED']  # noqa: E731
    x.drive(mid, refused)
    for r in refused():
        assert os.path.exists(ExecPaths(r.id).spawning)      # the argv was built
        assert not os.path.exists(ExecPaths(r.id).mcp)


def test_T099_a_process_that_died_while_core_was_down_leaves_no_mcp_config(x):
    mid, e = _mcp_running(x)
    proc.kill_pid_tree(e.pid, e.create_time)
    x.manager._procs.clear()                                 # the old Core is gone
    fresh = Rig(x.db, adapters=[FakeHarness(sources=True)])
    fresh.manager.boot()
    assert x.state(e.id).state in ('LOST', 'ENDED_ERROR', 'ENDED_KILLED'), x.state(e.id).state
    assert not os.path.exists(ExecPaths(e.id).mcp)


def test_T099_the_boot_sweep_removes_leftovers_and_only_them(x):
    mid, e = _mcp_running(x, sleep=1.5)
    # a crash leftover: an ended execution's config the end never removed
    left = ids.new_id('execution')
    paths = ExecPaths(left)
    os.makedirs(paths.res)
    for f in (paths.mcp, os.path.join(paths.res, 'settings.json'),
              os.path.join(paths.res, '1.res.json'), os.path.join(paths.req, 'mcp.json')):
        os.makedirs(os.path.dirname(f), exist_ok=True)
        _write(f, {'x': 1})
    stray = os.path.join(os.path.dirname(paths.dir), 'not-an-id', 'res', 'mcp.json')
    _write(stray, {'x': 1})
    fresh = Rig(x.db, adapters=[FakeHarness(sources=True)])
    fresh.scenarios.update(x.scenarios)
    assert e.id in fresh.manager.boot() and e.id in fresh.manager._procs
    assert not os.path.exists(paths.mcp)                     # the leftover is gone
    assert os.path.exists(os.path.join(paths.res, 'settings.json'))
    assert os.path.exists(os.path.join(paths.res, '1.res.json'))
    assert os.path.exists(os.path.join(paths.req, 'mcp.json'))  # not the path flag_argv writes
    assert os.path.exists(stray)                              # not an execution's directory
    assert os.path.exists(ExecPaths(e.id).mcp)                # the adopted process's survives
    x.manager._procs.clear()
    fresh.drive(mid, ended(fresh, e.id))
    assert not os.path.exists(ExecPaths(e.id).mcp)


def test_T099_an_estopped_execution_leaves_no_mcp_config(x):
    mid, e = _mcp_running(x)
    LocalNode.engage_estop()
    try:
        assert x.do(X.Executions(missions=x.missions).estop, who=x.user)['stopped'] == [e.id]
        x.drive(mid, ended(x, e.id))
    finally:
        LocalNode.clear_estop()
    assert (x.state(e.id).state, x.state(e.id).stop_reason) == ('ENDED_KILLED', 'estop')
    assert not os.path.exists(ExecPaths(e.id).mcp)


def test_T099_an_execution_that_ends_while_its_halt_is_exiting_is_still_collected(
        x, monkeypatch):
    """A halt for approval, then a stop before the next pass collects the exiting
    process (here an account ceiling): the execution is no longer live, so the
    pass over live executions never reaches its process."""
    opt(x, x.acc, 'mcp', 'gh')
    x.scenarios['t1'] = [TOOL('mcp__gh__issue', {}), DONE]
    mid = ready_in(x, x.prj, task('t1', 'read'))
    e = x.drive(mid, lambda: (lambda e: e if e is not None
                              and e.state == 'AWAITING_APPROVAL' else None)(
        x.exe(mission_id=mid)))
    assert e.id in x.manager._procs                          # the halt is still exiting
    x.manager._stop_account(x.acc, 'ceiling', 'usage reached the allocation')
    assert x.state(e.id).state == 'ENDED_KILLED'
    p = x.manager._procs[e.id]
    # while it still runs it is left alone: its end is not written under a live
    # process, which a Core-less e-stop would then skip, and its config stays
    status = p['adapter'].status
    monkeypatch.setattr(p['adapter'], 'status', lambda h: type('S', (), {'state': 'running'}))
    x.manager.tick()
    assert e.id in x.manager._procs
    assert not os.path.exists(ExecPaths(e.id).ended) and os.path.exists(ExecPaths(e.id).mcp)
    monkeypatch.setattr(p['adapter'], 'status', status)
    deadline = time.monotonic() + 15
    while p['adapter'].status(p['handle']).state == 'running':
        assert time.monotonic() < deadline, 'the halted process never exited'
        time.sleep(0.05)
    for _ in range(3):
        x.manager.tick()
    assert e.id not in x.manager._procs
    assert os.path.exists(ExecPaths(e.id).ended)
    assert not os.path.exists(ExecPaths(e.id).mcp)


def _halted_then_ended(x, monkeypatch):
    """An execution ended (an account ceiling) while its halted process still runs,
    and that process made to look as if it ignores the stop until it is killed.
    Returns (execution, kills)."""
    opt(x, x.acc, 'mcp', 'gh')
    x.scenarios['t1'] = [TOOL('mcp__gh__issue', {}), DONE]
    mid = ready_in(x, x.prj, task('t1', 'read'))
    e = x.drive(mid, lambda: (lambda e: e if e is not None
                              and e.state == 'AWAITING_APPROVAL' else None)(
        x.exe(mission_id=mid)))
    assert e.id in x.manager._procs
    x.manager._stop_account(x.acc, 'ceiling', 'usage reached the allocation')
    assert x.state(e.id).state == 'ENDED_KILLED'
    p, kills = x.manager._procs[e.id], []
    status, kill = p['adapter'].status, x.manager.node.kill
    monkeypatch.setattr(p['adapter'], 'status', lambda h: (
        status(h) if kills else type('S', (), {'state': 'running'})))
    monkeypatch.setattr(x.manager.node, 'kill', lambda a, h: (kills.append(h), kill(a, h))[1])
    return e, kills


def _collected(x, e):
    deadline = time.monotonic() + 15
    while e.id in x.manager._procs:
        assert time.monotonic() < deadline, 'never collected'
        x.manager.tick()
        time.sleep(0.05)
    assert os.path.exists(ExecPaths(e.id).ended)
    assert not os.path.exists(ExecPaths(e.id).mcp)


def test_T102_an_ended_executions_process_that_ignores_the_stop_is_killed_after_the_grace(
        x, monkeypatch):
    e, kills = _halted_then_ended(x, monkeypatch)
    x.manager.tick()
    assert kills == [] and e.id in x.manager._procs          # inside the grace: waited for
    time.sleep(x.manager.grace_s + 0.05)
    x.manager.tick()
    assert len(kills) == 1                                   # past it: killed
    _collected(x, e)


def test_T102_under_the_estop_it_is_killed_at_once(x, monkeypatch):
    e, kills = _halted_then_ended(x, monkeypatch)
    x.manager.grace_s = 60.0
    LocalNode.engage_estop()
    try:
        x.manager.tick()
    finally:
        LocalNode.clear_estop()
    assert len(kills) == 1
    _collected(x, e)


def test_T102_one_that_exits_inside_the_grace_is_never_killed(x, monkeypatch):
    e, kills = _halted_then_ended(x, monkeypatch)
    x.manager.grace_s = 60.0
    kills.append('let it run')                               # status reads the real process
    _collected(x, e)
    assert kills == ['let it run']


def _restart_with_an_ended_process(x):
    """The last Core recorded its execution's end while the process still ran, then
    died before collecting it. Returns (the execution, the new Core's rig)."""
    mid, e = _mcp_running(x)
    x.manager._procs.clear()                                 # the old Core is gone
    x.do(X.lost, execution_id=e.id, reason='the end the old Core recorded')
    assert x.state(e.id).state in lifecycle.states.terminal('execution')
    fresh = Rig(x.db, adapters=[FakeHarness(sources=True)])
    fresh.scenarios.update(x.scenarios)
    return x.state(e.id), fresh


def _handle(e):
    return base.ProcessHandle(e.id, e.pid, e.create_time, ExecPaths(e.id).dir)


def test_T105_after_a_restart_an_ended_executions_process_is_killed_after_the_grace(x):
    e, fresh = _restart_with_an_ended_process(x)
    fresh.manager.boot()
    assert e.id in fresh.manager._procs                      # taken in, not left running
    assert os.path.exists(ExecPaths(e.id).mcp)               # the sweep keeps what it reads
    fresh.manager.tick()
    assert fresh.manager.node.alive(_handle(e))                      # inside the grace: waited for
    time.sleep(fresh.manager.grace_s + 0.05)
    deadline = time.monotonic() + 15
    while e.id in fresh.manager._procs:
        assert time.monotonic() < deadline, 'never killed and collected'
        fresh.manager.tick()
        time.sleep(0.05)
    assert not fresh.manager.node.alive(_handle(e))
    assert os.path.exists(ExecPaths(e.id).ended)
    assert not os.path.exists(ExecPaths(e.id).mcp)
    assert e.id not in {x_['execution_id'] for x_ in LocalNode.unended()}


def test_T105_under_the_estop_it_is_killed_at_once(x):
    e, fresh = _restart_with_an_ended_process(x)
    fresh.manager.grace_s = 60.0
    LocalNode.engage_estop()
    try:
        fresh.manager.boot()
        fresh.manager.tick()
        deadline = time.monotonic() + 15
        while fresh.manager.node.alive(_handle(e)):
            assert time.monotonic() < deadline, 'not killed under the e-stop'
            time.sleep(0.05)
    finally:
        LocalNode.clear_estop()


def test_T105_a_process_already_gone_is_not_taken_in_and_its_config_is_swept(x):
    e, fresh = _restart_with_an_ended_process(x)
    proc.kill_pid_tree(e.pid, e.create_time)
    fresh.manager.boot()
    assert e.id not in fresh.manager._procs
    assert not os.path.exists(ExecPaths(e.id).mcp)


def test_T105_a_live_execution_is_never_taken_in_as_an_orphan(x):
    mid, e = _mcp_running(x, sleep=1.5)
    x.manager._procs.clear()
    fresh = Rig(x.db, adapters=[FakeHarness(sources=True)])
    fresh.scenarios.update(x.scenarios)
    fresh.manager.boot()
    p = fresh.manager._procs[e.id]                           # adopted as live
    fresh.manager._adopt_orphans(fresh.manager._read()[0])
    assert fresh.manager._procs[e.id] is p
    fresh.drive(mid, ended(fresh, e.id))


def _wait_dead(alive, what):
    deadline = time.monotonic() + 15
    while alive():
        assert time.monotonic() < deadline, what
        time.sleep(0.05)


def test_T105_a_line_with_no_execution_row_is_killed_and_boot_comes_up(x, caplog):
    """A registry line whose execution this database does not hold (a restored
    backup, while a process started after it still runs): the process is ours by
    its recorded identity, nothing would ever end it, so boot kills it and says
    so - and comes up, compacting and sweeping as always."""
    child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])
    try:
        stray = ids.new_id('execution')
        x.manager.node._registry({'op': 'spawn', 'execution_id': stray, 'process_seq': 1,
                                  'pid': child.pid,
                                  'create_time': proc.process_create_time(child.pid)})
        os.makedirs(ExecPaths(stray).res, exist_ok=True)
        _write(ExecPaths(stray).mcp, {'mcpServers': {}})
        fresh = Rig(x.db, adapters=[FakeHarness(sources=True)])
        with caplog.at_level('WARNING', logger='archeus.execution'):
            fresh.manager.boot()
        assert fresh.manager.booted and stray not in fresh.manager._procs
        _wait_dead(lambda: child.poll() is None, 'the stray process was left running')
        assert not os.path.exists(ExecPaths(stray).mcp)          # the sweep still ran
        assert 'no row for it' in caplog.text
    finally:
        if child.poll() is None:
            child.kill()


def test_T105_a_harness_this_core_does_not_register_is_killed_and_boot_comes_up(
        x, monkeypatch, caplog):
    e, fresh = _restart_with_an_ended_process(x)

    def unknown(harness_id):
        raise KeyError(harness_id)
    monkeypatch.setattr(fresh.manager.registry, 'get', unknown)
    try:
        with caplog.at_level('WARNING', logger='archeus.execution'):
            fresh.manager.boot()
        assert fresh.manager.booted and e.id not in fresh.manager._procs
        _wait_dead(lambda: fresh.manager.node.alive(_handle(e)), 'left running')
        assert not os.path.exists(ExecPaths(e.id).mcp)
        assert "no harness 'fake'" in caplog.text
    finally:
        proc.kill_pid_tree(e.pid, e.create_time)


def test_T105_a_line_that_fails_does_not_keep_core_down(x, monkeypatch):
    """Anything else a line raises is raised by boot only after it has compacted
    and swept, as a failed reconcile is: Core is booted, the keys are gone."""
    e, fresh = _restart_with_an_ended_process(x)

    def odd(handle):
        raise RuntimeError('an odd line')
    monkeypatch.setattr(fresh.manager.node, 'alive', odd)
    try:
        with pytest.raises(RuntimeError, match='an odd line'):
            fresh.manager.boot()
        assert fresh.manager.booted
        assert not os.path.exists(ExecPaths(e.id).mcp)
    finally:
        proc.kill_pid_tree(e.pid, e.create_time)


def test_T105_a_pid_now_held_by_another_process_is_neither_taken_in_nor_killed(x):
    """Identity is the pid AND the create time the line recorded: a line whose
    create time no longer matches names some other process, never ours."""
    e, fresh = _restart_with_an_ended_process(x)
    path = processes_registry()
    lines = [json.loads(v) for v in open(path, encoding='utf-8') if v.strip()]
    for v in lines:
        if v.get('op') == 'spawn' and v['execution_id'] == e.id:
            v['create_time'] = v['create_time'] + 1
    with open(path, 'w', encoding='utf-8') as f:
        f.writelines(json.dumps(v, sort_keys=True) + '\n' for v in lines)
    try:
        fresh.manager.grace_s = 0.0
        fresh.manager.boot()
        assert e.id not in fresh.manager._procs
        fresh.manager.tick()
        assert fresh.manager.node.alive(_handle(e))          # the stranger still runs
    finally:
        proc.kill_pid_tree(e.pid, e.create_time)


def test_T099_a_launch_that_raises_leaves_no_mcp_config(x, monkeypatch):
    """A launch that raises SpawnFailed itself, as an isolated launch failing after
    establishment does, never passes the spawn's own refusal."""
    opt(x, x.acc, 'mcp', 'gh')

    def raising(*a, **k):
        raise base.SpawnFailed('isolation: launch_failed (test)')
    monkeypatch.setattr(base.proc, 'spawn_detached', raising)
    mid = ready_in(x, x.prj)
    refused = lambda: [r for r in x.all(entities.Execution) if r.state == 'ABANDONED']  # noqa: E731
    x.drive(mid, refused)
    for r in refused():
        assert os.path.exists(ExecPaths(r.id).spawning)      # the argv was built
        assert not os.path.exists(ExecPaths(r.id).mcp)
        # a launch's own failure stays uncharged (O7); only Core's writes are charged
        assert (r.stop_reason, r.charged) == ('binding', False)


def test_T099_a_prompt_that_cannot_be_written_leaves_no_mcp_config(x, monkeypatch):
    """An OSError before a child exists (here the prompt) drops the config too,
    not only a SpawnFailed. Since T-102 it is a refusal: the execution is
    abandoned with its tombstone and charged like a workspace that cannot be
    made, and the pass goes on - the next attempt runs."""
    opt(x, x.acc, 'mcp', 'gh')
    x.scenarios['t1'] = [DONE]
    real, failed = base.config.write_atomic, []
    prompt = os.path.basename(ExecPaths(ids.new_id('execution')).prompt)

    def once(path, data, *a, **k):
        if os.path.basename(path) == prompt and not failed:
            failed.append(path)
            return False
        return real(path, data, *a, **k)
    monkeypatch.setattr(base.config, 'write_atomic', once)
    mid = ready_in(x, x.prj)
    x.drive(mid, lambda: any(r.state == 'ENDED_OK' for r in x.all(entities.Execution)))
    [r] = [r for r in x.all(entities.Execution) if r.state == 'ABANDONED']
    assert (r.stop_reason, r.charged) == ('workspace', True)
    assert os.path.exists(ExecPaths(r.id).spawning)          # the argv was built
    assert not os.path.exists(ExecPaths(r.id).mcp)
    assert 'could not write' in base.read_json(ExecPaths(r.id).ended)['error']


def _prompt_write(monkeypatch, fail):
    real = base.config.write_atomic
    prompt = os.path.basename(ExecPaths(ids.new_id('execution')).prompt)

    def write(path, data, *a, **k):
        if os.path.basename(path) == prompt:
            return fail()
        return real(path, data, *a, **k)
    monkeypatch.setattr(base.config, 'write_atomic', write)


def test_T102_a_prompt_that_can_never_be_written_spends_the_tasks_attempts(x, monkeypatch):
    """A write that fails every time ends the task FAILED after its attempts, as a
    workspace that cannot be made does (P11 note 11) - never a new execution on
    every tick."""
    _prompt_write(monkeypatch, lambda: False)
    mid = ready_in(x, x.prj, task('t1', 'write_repo', max_attempts=2))
    x.drive(mid, lambda: x.task_of(mid).state == 'FAILED')
    runs = x.all(entities.Execution, task_id=x.task_of(mid).id)
    assert [(r.state, r.stop_reason, r.charged) for r in runs] == [
        ('ABANDONED', 'workspace', True)] * 2


def test_T102_only_an_oserror_before_a_child_is_refused(x, monkeypatch):
    """Anything else raised there is a bug, not the disk: it is not turned into a
    charged refusal of the user's task."""
    def bug():
        raise RuntimeError('a bug, not the disk')
    _prompt_write(monkeypatch, bug)
    mid = ready_in(x, x.prj)
    with pytest.raises(RuntimeError, match='a bug, not the disk'):
        x.drive(mid, lambda: False, timeout=10)
    assert not [r for r in x.all(entities.Execution) if r.state == 'ABANDONED']


def test_T099_a_spawn_refused_as_already_spawned_keeps_the_config_a_process_may_hold(
        x, monkeypatch):
    """A marker that is already there means a process of this execution may still
    run and read its config: the refusal leaves the file to that process's end, or
    to the boot sweep."""
    opt(x, x.acc, 'mcp', 'gh')
    real = base.spawn

    def marked(spec, argv):
        base._write_json(ExecPaths(spec.execution_id).spawning, {'process_seq': 1})
        return real(spec, argv)
    monkeypatch.setattr(base, 'spawn', marked)
    mid = ready_in(x, x.prj)
    refused = lambda: [r for r in x.all(entities.Execution) if r.state == 'ABANDONED']  # noqa: E731
    x.drive(mid, refused)
    assert all(os.path.exists(ExecPaths(r.id).mcp) for r in refused())


def test_T099_a_tombstone_that_cannot_be_written_still_drops_the_config(x, monkeypatch):
    mid, e = _mcp_running(x, sleep=0.5)

    def broken(path, obj):
        raise OSError('disk full')
    monkeypatch.setattr(base, '_write_json', broken)
    with pytest.raises(OSError):
        base.mark_ended(ExecPaths(e.id), 0)
    assert not os.path.exists(ExecPaths(e.id).mcp)
    monkeypatch.undo()
    x.drive(mid, ended(x, e.id))


# ── the routes and the CLI ───────────────────────────────────────────────────

@pytest.fixture
def core(archeus_home):
    from v1.judge.http import TempCore
    tc = TempCore(archeus_home).start()
    yield tc
    tc.stop(kill=True)


def _key(body):
    return dict(body, idempotency_key=ids.new_ulid())


def test_H01_opt_ins_are_admin_written_and_observe_read(core):
    acc = core.http('POST', '/v1/accounts', body=_key({
        'harness_id': 'fake', 'label': 'W', 'auth_kind': 'api_key'})).json()['id']
    code = core.http('POST', '/v1/devices/launch/code', body={}).json()['code']
    browser = core.http('POST', '/v1/devices/launch/redeem',
                        body={'code': code, 'platform': 'web'}).json()['token']
    body = {'owner_id': acc, 'kind': 'mcp', 'name': 'gh', 'opted_in': True}
    got = core.http('POST', '/v1/opt-ins', body=_key(body), token=browser)
    assert (got.status, got.json()['error']) == (403, 'scope_required')
    assert core.http('POST', '/v1/opt-ins', body=_key(body), token='dev_' + 'x' * 30
                     ).status == 401
    assert core.http('POST', '/v1/opt-ins', body=dict(body)).status == 400     # no key
    assert core.http('POST', '/v1/opt-ins', body=_key(dict(body, kind='skill'))).status == 400
    assert core.http('POST', '/v1/opt-ins', body=_key(dict(body, kind='source', name='local'))
                     ).status == 400
    ok = core.http('POST', '/v1/opt-ins', body=_key(body))
    assert ok.status == 200 and ok.json()['changed'] and ok.json()['opt_in']['version'] == 1
    (row,) = core.http('GET', '/v1/opt-ins', token=browser).json()['opt_ins']
    assert (row['owner'], row['owner_id'], row['name'], row['opted_in']) == (
        'account', acc, 'gh', True)


def test_H02_the_cli_opts_in_and_out_and_lists(core, capsys):
    acc = core.http('POST', '/v1/accounts', body=_key({
        'harness_id': 'fake', 'label': 'W', 'auth_kind': 'api_key'})).json()['id']
    assert cli.main(['executions', 'opt-ins']) == 0
    assert 'no opt-ins' in capsys.readouterr().out
    assert cli.main(['executions', 'opt-in', acc, 'plugin', 'p@m']) == 0
    assert capsys.readouterr().out.strip() == '%s plugin p@m: opted in (version 1)' % acc
    assert cli.main(['executions', 'opt-out', acc, 'plugin', 'p@m']) == 0
    assert 'opted out (version 2)' in capsys.readouterr().out
    assert cli.main(['executions', 'opt-ins']) == 0
    assert ' out p@m  (version 2)' in capsys.readouterr().out
    assert cli.main(['executions', 'opt-in', acc, 'source', 'project']) == 2   # Core refuses
    assert cli.main(['executions', 'opt-in', acc, 'skill', 'x']) == 2          # usage
    capsys.readouterr()

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
import time

import pytest

from archeus.cli import main as cli
from archeus.core.application import authorization as A
from archeus.core.application import commands, executions as X, lifecycle, optins, world
from archeus.core.domain import entities, ids
from archeus.harnesses import sources
from archeus.harnesses.fake import FakeHarness
from archeus.infra.artifacts import store
from archeus.infra.paths import ExecPaths

from v1.integration.test_execution import Rig, _running, ended
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
    cfg = json.load(open(argv[argv.index('--mcp-config') + 1], encoding='utf-8'))
    assert list(cfg['mcpServers']) == ['gh']                 # never the project's `db`
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

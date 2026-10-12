"""P20 slice E (PV-10; ADR-0049, D6): what an execution's settings sources load.

The rule without a process: the inventory and the flags `sources.take` derives
from the account home, the workdir and the opt-ins; the argv `flag_argv` makes
of them; the OptIn entity's own invariants; the hook's exit-code-2 deny and its
fail-closed paths, run as a real process; and the fake agent reading a hook's
answer the way Claude Code documents it, so a hook that fails open is caught.
"""

import json
import os
import subprocess
import sys
import threading
import time

import pytest

from archeus.core.domain import entities as E, ids
from archeus.core.redact import redact
from archeus.harnesses import base, hook, sources
from archeus.harnesses.claude_code import adapter as cc

HOOK = hook.__file__
AGENT = os.path.join(os.path.dirname(hook.__file__), 'fake_agent.py')
SECRET = 'sk-ant-' + 'S' * 30


def _write(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(obj if isinstance(obj, str) else json.dumps(obj))


def _hooks(cmd):
    return {'PreToolUse': [{'matcher': '*', 'hooks': [{'type': 'command', 'command': cmd}]}]}


@pytest.fixture
def world(tmp_path):
    """An account home and a project workdir, each with something in every
    place ADR-0049 names, and a managed settings file."""
    home, work = str(tmp_path / 'home'), str(tmp_path / 'proj')
    _write(os.path.join(home, 'settings.json'), {
        'hooks': _hooks('user-hook.sh'), 'enabledPlugins': {'up@m': True, 'off@m': False},
        'permissions': {'allow': ['Bash(npm test)']},
        'env': {'ANTHROPIC_API_KEY': SECRET}})
    _write(os.path.join(home, '.claude.json'), {'mcpServers': {
        'gh': {'command': 'gh-mcp', 'env': {'GITHUB_TOKEN': SECRET}},
        'web': {'url': 'https://example.test/mcp?token=' + SECRET}}})
    _write(os.path.join(home, 'CLAUDE.md'), 'user memory')
    _write(os.path.join(home, 'skills', 'uskill', 'SKILL.md'), 'x')
    plug = os.path.join(home, 'plugins', 'cache', 'm', 'pl', '1')
    _write(os.path.join(plug, 'skills', 'pskill', 'SKILL.md'), 'x')
    _write(os.path.join(plug, 'hooks', 'hooks.json'), {'hooks': _hooks('plugin-hook.sh')})
    _write(os.path.join(home, 'plugins', 'installed_plugins.json'), {'version': 2, 'plugins': {
        'pl@m': [{'scope': 'user', 'installPath': plug}],
        'bad@m': [{'scope': 'user', 'installPath': str(tmp_path)}]}})
    _write(os.path.join(work, '.claude', 'settings.json'), {
        'hooks': _hooks('project-hook.sh'), 'permissions': {'deny': ['Read(.env)']}})
    _write(os.path.join(work, '.claude', 'settings.local.json'), {'hooks': _hooks('local.sh')})
    _write(os.path.join(work, '.mcp.json'), {'mcpServers': {'db': {'command': 'db-mcp'}}})
    _write(os.path.join(work, 'CLAUDE.md'), 'project memory')
    _write(os.path.join(work, '.claude', 'skills', 'pjskill', 'SKILL.md'), 'x')
    managed = str(tmp_path / 'managed' / 'managed-settings.json')
    _write(managed, {'hooks': _hooks('managed.sh')})
    return home, work, managed


def take(world, *opt_ins, **kw):
    home, work, managed = world
    kw.setdefault('managed', managed)
    return sources.take(home, work, opt_ins, **kw)


def items(inv, **eq):
    return [i for i in inv['items'] if all(i.get(k) == v for k, v in eq.items())]


def status_of(inv, type_, name):
    (i,) = [i for i in inv['items'] if i['type'] == type_ and i['name'].endswith(name)]
    return i['status']


# ── the default: every source excluded ───────────────────────────────────────

def test_E01_with_nothing_opted_in_every_source_is_excluded(world):
    inv = take(world)
    assert inv['flags'] == {'setting_sources': [], 'strict_mcp_config': True,
                            'mcp_servers': [], 'disable_slash_commands': True,
                            'plugin_dirs': []}
    for src in sources.SOURCES:
        for i in items(inv, source=src):
            if i['type'] in ('hook', 'permission', 'plugin', 'mcp_server', 'skill'):
                assert i['status'] == 'excluded', i
    assert {i['name'] for i in items(inv, type='hook')} >= {
        'PreToolUse: user-hook.sh', 'PreToolUse: project-hook.sh', 'PreToolUse: local.sh'}
    assert {i['name'] for i in items(inv, type='mcp_server')} == {'gh', 'web', 'db'}
    # a CLAUDE.md follows its source too: none loads (PV-19, O5)
    assert {m['status'] for m in items(inv, type='claude_md')} == {'excluded'}
    # the CLI's own are said, never omitted; the flag keeps its bundled skills out
    assert [(i['type'], i['status']) for i in items(inv, source='cli')] == [
        ('plugin', 'builtin'), ('skill', 'excluded')]
    assert inv['observed'] is False and inv['inventory_version'] == 2


def test_E02_the_argv_always_names_the_sources_even_when_none(world, tmp_path):
    a = sources.flag_argv(take(world)['flags'], home=world[0], workdir=world[1],
                          exec_dir=str(tmp_path / 'x'))
    assert a == ['--setting-sources', '', '--strict-mcp-config', '--disable-slash-commands']
    # no inventory at all is the same narrowest set, never the CLI's default of all
    assert sources.flag_argv(sources.DEFAULT_FLAGS, home=None, workdir=None,
                             exec_dir=str(tmp_path / 'y')) == a


def test_E03_managed_settings_always_apply_and_claude_md_follows_its_source(world):
    inv = take(world)
    assert status_of(inv, 'managed_settings', 'managed-settings.json') == 'not_excludable'
    assert status_of(inv, 'hook', 'managed.sh') == 'not_excludable'
    mds = items(inv, type='claude_md')
    assert {(m['source'], m['status']) for m in mds} >= {('user', 'excluded'),
                                                         ('project', 'excluded')}
    assert all(len(m['sha256']) == 64 for m in mds)
    assert 'not_excludable' not in {i['status'] for i in inv['items']
                                    if i['source'] != 'managed'}


# ── opt-ins, each in exactly the scope granted ───────────────────────────────

def test_E04_an_account_opting_in_its_source_loads_user_and_nothing_else(world):
    inv = take(world, ('account', 'source', 'user'))
    assert inv['flags']['setting_sources'] == ['user']
    assert status_of(inv, 'hook', 'user-hook.sh') == 'opted_in'
    assert status_of(inv, 'hook', 'project-hook.sh') == 'excluded'
    assert status_of(inv, 'hook', 'local.sh') == 'excluded'
    (md,) = items(inv, type='claude_md', source='user')
    assert md['status'] == 'opted_in'
    assert {m['status'] for m in items(inv, type='claude_md', source='project')} == {
        'excluded'}


def test_E05_a_project_opting_in_project_does_not_load_local(world):
    inv = take(world, ('project', 'source', 'project'))
    assert inv['flags']['setting_sources'] == ['project']
    assert status_of(inv, 'permission', 'Read(.env)') == 'opted_in'
    assert status_of(inv, 'hook', 'local.sh') == 'excluded'
    assert status_of(inv, 'hook', 'user-hook.sh') == 'excluded'
    inv = take(world, ('project', 'source', 'local'))
    assert inv['flags']['setting_sources'] == ['local']
    assert status_of(inv, 'hook', 'local.sh') == 'opted_in'


def test_E06_strict_mcp_passes_only_the_opted_in_server_of_its_own_owner(world, tmp_path):
    inv = take(world, ('account', 'mcp', 'gh'), ('project', 'mcp', 'web'))
    assert inv['flags']['mcp_servers'] == [{'owner': 'account', 'name': 'gh'}]
    assert status_of(inv, 'mcp_server', 'gh') == 'opted_in'
    assert status_of(inv, 'mcp_server', 'db') == 'excluded'
    # `web` is the account's server: a project's opt-in of that name is not it
    assert [i['status'] for i in items(inv, type='mcp_server', name='web')] == [
        'excluded', 'not_found']
    d = str(tmp_path / 'exec')
    a = sources.flag_argv(inv['flags'], home=world[0], workdir=world[1], exec_dir=d)
    i = a.index('--mcp-config')
    assert '--strict-mcp-config' in a
    cfg = json.load(open(a[i + 1], encoding='utf-8'))
    assert sorted(cfg['mcpServers']) == ['gh']


def test_E07_a_plugin_is_loaded_by_its_own_directory_and_carries_its_skills(world, tmp_path):
    inv = take(world, ('account', 'plugin', 'pl@m'))
    (d,) = inv['flags']['plugin_dirs']
    assert d['name'] == 'pl@m' and os.path.isdir(d['path'])
    assert status_of(inv, 'skill', 'pskill') == 'opted_in'
    assert status_of(inv, 'hook', 'plugin-hook.sh') == 'opted_in'
    # a skill arrived with the plugin: the flag is dropped, which lets the CLI's
    # bundled skills in, and the user's own skill, from a source that stays
    # out, still does not load (PV-19, O5)
    assert inv['flags']['disable_slash_commands'] is False
    assert status_of(inv, 'skill', 'uskill') == 'excluded'
    assert status_of(inv, 'skill', 'bundled skills') == 'builtin'
    a = sources.flag_argv(inv['flags'], home=world[0], workdir=world[1],
                          exec_dir=str(tmp_path / 'e'))
    assert a[a.index('--plugin-dir') + 1] == d['path'] and '--disable-slash-commands' not in a
    # an enabled plugin that is not opted in stays excluded
    assert status_of(inv, 'plugin', 'up@m') == 'excluded'


def test_E08_a_plugin_that_resolves_outside_the_homes_plugins_is_not_loaded(world):
    inv = take(world, ('account', 'plugin', 'bad@m'), ('account', 'plugin', 'nope@m'))
    assert [d['path'] for d in inv['flags']['plugin_dirs']] == [None, None]
    assert {i['status'] for i in items(inv, source='plugin')} == {'not_found'}
    assert inv['flags']['disable_slash_commands'] is True


def test_E09_skills_stay_disabled_unless_a_skill_is_opted_in(world):
    assert take(world)['flags']['disable_slash_commands'] is True
    assert take(world, ('account', 'mcp', 'gh'))['flags']['disable_slash_commands'] is True
    inv = take(world, ('project', 'source', 'project'))
    assert inv['flags']['disable_slash_commands'] is False
    assert status_of(inv, 'skill', 'pjskill') == 'opted_in'
    assert status_of(inv, 'skill', 'uskill') == 'excluded'


def test_E10_the_fallback_loads_a_source_and_says_it_is_only_recorded(world):
    inv = take(world, recorded_only=('user',))
    assert inv['flags']['setting_sources'] == ['user']
    assert status_of(inv, 'hook', 'user-hook.sh') == 'recorded_only'
    assert inv['recorded_only'] == ['user']
    assert sources.RECORDED_ONLY == ()          # nothing falls back until PV-19 says so


def test_E11_no_secret_reaches_the_record(world):
    inv = take(world, ('account', 'mcp', 'gh'), ('account', 'source', 'user'))
    raw = json.dumps(inv)
    # never read: an env block, an MCP server's definition, its URL
    assert SECRET not in raw and 'GITHUB_TOKEN' not in raw and 'example.test' not in raw
    # a hook command is recorded, and Core redacts the record before storing it
    home = world[0]
    _write(os.path.join(home, 'settings.json'), {'hooks': _hooks('curl -H "Authorization: '
                                                                 'Bearer %s" x' % ('t' * 30))})
    raw = json.dumps(take(world))
    assert 'Bearer ' + 't' * 30 in raw
    assert 't' * 30 not in redact(raw)


def test_E12_an_unreadable_file_is_recorded_and_still_excluded(world):
    _write(os.path.join(world[1], '.claude', 'settings.json'), '{not json')
    inv = take(world)
    (u,) = items(inv, type='unreadable', source='project')
    assert (u['status'], u['error']) == ('excluded', 'not JSON')


def test_E13_the_record_is_bounded(world, monkeypatch):
    monkeypatch.setattr(sources, 'MAX_ITEMS', 3)
    inv = take(world)
    assert len(inv['items']) == 3 and inv['truncated'] is True


# ── the opt-in entity ───────────────────────────────────────────────────────

@pytest.mark.parametrize('bad', [
    dict(kind='plugin', name='p@m'),                                       # no owner
    dict(kind='plugin', name='p@m', account_id='A', project_id='P'),       # two owners
    dict(kind='source', name='project', account_id='A'),                   # not the account's
    dict(kind='source', name='user', project_id='P'),                      # not the project's
    dict(kind='mcp', name='../x', account_id='A'),                         # a path
    dict(kind='mcp', name='a/b', account_id='A'),
    dict(kind='skill', name='s', account_id='A'),                          # no such kind
    dict(kind='mcp', name='gh', account_id='A', opted_in='yes'),
])
def test_E14_an_opt_in_has_one_owner_its_own_sources_and_never_a_path(bad):
    acc, prj = ids.new_id('account'), ids.new_id('project')
    bad = dict(bad, **{k: {'A': acc, 'P': prj}[v] for k, v in bad.items()
                       if k in ('account_id', 'project_id')})
    with pytest.raises(ValueError):
        E.OptIn(id=ids.new_id('opt_in'), **bad)


def test_E15_each_owner_holds_its_own_sources():
    assert E.SOURCE_OWNERS == {'account': ('user',), 'project': ('project', 'local')}
    E.OptIn(id=ids.new_id('opt_in'), kind='source', name='user', account_id=ids.new_id('account'))
    for n in ('project', 'local'):
        E.OptIn(id=ids.new_id('opt_in'), kind='source', name=n, project_id=ids.new_id('project'))


# ── the hook: exit code 2 denies; nothing else ever lets a call through ─────

def _env(tmp_path, wait='5'):
    eid = ids.new_id('execution')
    return eid, dict(os.environ, ARCHEUS_HOME=str(tmp_path), ARCHEUS_EXECUTION_ID=eid,
                     ARCHEUS_HOOK_TOKEN='hook_' + 'k' * 20, ARCHEUS_HOOK_WAIT=wait)


def _answer_with(tmp_path, eid, res):
    d = os.path.join(str(tmp_path), 'run', 'exec', eid)

    def core():
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if os.path.exists(os.path.join(d, 'req', '1.req.json')):
                _write(os.path.join(d, 'res', '1.res.json'), res)
                return
            time.sleep(0.02)
    t = threading.Thread(target=core)
    t.start()
    return t


def _run_hook(env, stdin):
    return subprocess.run([sys.executable, HOOK], input=stdin, capture_output=True,
                          text=True, encoding='utf-8', env=env, timeout=60)


def test_E16_a_deny_is_exit_code_2_with_the_reason_on_stderr(tmp_path):
    eid, env = _env(tmp_path)
    t = _answer_with(tmp_path, eid, {'decision': 'deny', 'reason': 'not here — no'})
    r = _run_hook(env, json.dumps({'tool_name': 'Bash', 'tool_input': {'command': 'x'}}))
    t.join()
    assert (r.returncode, r.stdout, r.stderr) == (2, '', 'not here — no')


def test_E17_allow_and_halt_keep_their_json_at_exit_0(tmp_path):
    eid, env = _env(tmp_path)
    t = _answer_with(tmp_path, eid, {'decision': 'allow'})
    r = _run_hook(env, json.dumps({'tool_name': 'Read'}))
    t.join()
    assert r.returncode == 0
    assert json.loads(r.stdout)['hookSpecificOutput']['permissionDecision'] == 'allow'
    os.makedirs(os.path.join(str(tmp_path), 'run'), exist_ok=True)
    open(os.path.join(str(tmp_path), 'run', 'STOP'), 'w').close()
    r = _run_hook(env, json.dumps({'tool_name': 'Read'}))
    # a halt stops the agent AND denies the call it answers: `continue: false`
    # alone lets Claude Code run the call first (PV-19, O4)
    assert (r.returncode, json.loads(r.stdout)) == (0, {
        'continue': False, 'stopReason': 'emergency stop',
        'hookSpecificOutput': {'hookEventName': 'PreToolUse', 'permissionDecision': 'deny',
                               'permissionDecisionReason': 'emergency stop'}})


def test_E18_a_hook_crash_halts_and_never_exits_with_another_code(tmp_path):
    _eid, env = _env(tmp_path)
    r = _run_hook(env, 'this is not json')
    out = json.loads(r.stdout)
    assert r.returncode == 0 and out['continue'] is False
    assert out['hookSpecificOutput']['permissionDecision'] == 'deny'
    # whatever escapes, even the write of the halt, is the deny's exit code
    assert hook.guarded(lambda: 1 / 0) == hook.DENY_EXIT
    assert hook.guarded(lambda: 1) == hook.DENY_EXIT
    assert hook.guarded(lambda: sys.exit(3)) == hook.DENY_EXIT
    assert hook.guarded(lambda: 0) == 0 and hook.guarded(lambda: 2) == 2


def test_E19_a_core_that_never_answers_is_a_halt_before_claude_codes_own_timeout(tmp_path):
    eid, env = _env(tmp_path, wait='0.3')
    r = _run_hook(env, json.dumps({'tool_name': 'Read'}))
    out = json.loads(r.stdout)
    assert r.returncode == 0 and out['continue'] is False
    assert out['hookSpecificOutput']['permissionDecision'] == 'deny'
    assert os.path.exists(os.path.join(str(tmp_path), 'run', 'exec', eid, 'req', 'halted.json'))
    # the hook's own deadline is well inside the one Claude Code enforces on it
    assert float(os.environ.get('ARCHEUS_HOOK_WAIT', '60')) < cc.HOOK_TIMEOUT_S
    assert hook.WAIT_S < cc.HOOK_TIMEOUT_S


def test_the_spawn_configuration_is_core_authored_class_2(archeus_home):
    """PV-20 §7.5: the settings file that installs the hook sits where the execution
    may read and never write — not beside its own reports, not in Core's directory.
    Where it sits is all this shows: that the real CLI loads its hook from there is
    runtime evidence this test cannot give."""
    eid = ids.new_id('execution')
    spec = base.ExecutionSpec(execution_id=eid, prompt='go', workdir=str(archeus_home),
                              hook_settings=(sys.executable, HOOK))
    argv = cc.ClaudeCodeAdapter('claude').argv(spec, 'session')
    settings = argv[argv.index('--settings') + 1]
    assert os.path.dirname(settings) == base.ExecPaths(eid).res
    assert os.path.isfile(settings)


# ── the fake agent reads a hook as Claude Code documents it ─────────────────

@pytest.mark.parametrize('code, out, expect', [
    (2, '', 'tool_denied'),             # the block
    (1, '', 'hook_error'),              # any other code: the call proceeds
    (3, '', 'hook_error'),
    (0, 'not json', 'hook_error'),      # exit 0 with no decision: proceeds
    (0, json.dumps({'continue': False, 'hookSpecificOutput': {'hookEventName': 'PreToolUse', 'permissionDecision': 'deny'}}), 'halted'),
])
def test_E20_the_fake_agent_lets_a_failing_hook_through_as_claude_code_would(
        tmp_path, code, out, expect):
    script = tmp_path / 'h.py'
    script.write_text('import sys\nsys.stdout.write(%r)\nsys.stderr.write("why")\n'
                      'sys.exit(%d)\n' % (out, code))
    steps = [{'emit': {'type': 'tool', 'name': 'Read', 'input': {}}}]
    env = dict(os.environ, ARCHEUS_HOOK_CMD=json.dumps([sys.executable, str(script)]))
    r = subprocess.run([sys.executable, AGENT, json.dumps(steps), '0', '--x'], input='',
                       capture_output=True, text=True, env=env, timeout=60)
    evs = [json.loads(line) for line in r.stdout.splitlines()]
    assert expect in [e['type'] for e in evs]
    assert evs[0]['argv'] == ['--x']
    if expect == 'hook_error':
        assert 'tool' in [e['type'] for e in evs]     # it ran: the worst case, modelled
    if expect == 'halted':
        assert 'tool' not in [e['type'] for e in evs]   # the halt's deny blocked it


@pytest.mark.parametrize('answer, ran', [
    (json.dumps({'continue': False, 'hookSpecificOutput': {'hookEventName': 'PreToolUse', 'permissionDecision': 'deny'}}), False),
    (json.dumps({'continue': False}), True),
])
def test_E23_the_fake_agent_halts_as_claude_code_does(tmp_path, answer, ran):
    """PV-19 (O4): `continue: false` alone does not block the call it answers
    in Claude Code 2.1.291 — the call runs and the agent stops after it; with
    the deny the call is blocked and the agent stops. The fake models both, so
    a halt that loses its deny is caught here; the real CLI's own behaviour is
    PV-19's to prove (p20-design-gate §12)."""
    script = tmp_path / 'h.py'
    script.write_text('import sys\nsys.stdin.read()\nsys.stdout.write(%r)\n' % answer)
    target = tmp_path / 'work'
    target.mkdir()
    steps = [{'emit': {'type': 'tool', 'name': 'Write',
                       'input': {'file_path': 'ran.txt', 'content': 'x'}}},
             {'emit': {'type': 'assistant', 'text': 'after'}}]
    env = dict(os.environ, ARCHEUS_HOOK_CMD=json.dumps([sys.executable, str(script)]))
    r = subprocess.run([sys.executable, AGENT, json.dumps(steps), '0'], input='',
                       capture_output=True, text=True, env=env, timeout=60, cwd=str(target))
    evs = [json.loads(line) for line in r.stdout.splitlines()]
    kinds = [e['type'] for e in evs]
    assert 'halted' in kinds and 'assistant' not in kinds and r.returncode == 0
    assert ('tool' in kinds) is ran and (target / 'ran.txt').exists() is ran


def test_E25_what_a_plugin_brings_and_the_synced_skills_are_recorded(world):
    """PV-19 (O5): a plugin's hooks may sit in its manifest (`plugin.json`), a
    plugin a source enables brings its skills and hooks with that source, its
    MCP servers stay out under --strict-mcp-config, the CLI names it by its
    manifest, and the account's synced skills come with `user`. None of it
    moves a flag."""
    home, work, _m = world
    up = os.path.join(home, 'plugins', 'cache', 'm', 'up', '1')
    _write(os.path.join(up, '.claude-plugin', 'plugin.json'), {
        'name': 'up-cli', 'hooks': {'SessionStart': [{'hooks': [
            {'type': 'command', 'command': 'inline.sh'}]}]},
        'mcpServers': {'upmcp': {'command': 'x'}},
        'skills': ['./.claude/skills/', './', '../../../../../outside']})
    _write(os.path.join(up, 'skills', 'upskill', 'SKILL.md'), 'x')
    # skill paths the manifest declares: a directory of skills, and a path that
    # is one skill named by its SKILL.md; one outside the plugin is not read
    _write(os.path.join(up, '.claude', 'skills', 'declskill', 'SKILL.md'), 'x')
    _write(os.path.join(up, 'SKILL.md'), '---\r\nname: rootskill\r\n---\r\nbody\r\n')
    _write(os.path.join(home, 'outside', 'SKILL.md'), '---\nname: escaped\n---\n')
    _write(os.path.join(home, 'skills', 'synced', 'org_1', 'synskill', 'SKILL.md'), 'x')
    inst = os.path.join(home, 'plugins', 'installed_plugins.json')
    d = json.load(open(inst))
    d['plugins']['up@m'] = [{'scope': 'user', 'installPath': up}]
    _write(inst, d)
    before = {k: take(world, *o)['flags'] for k, o in (
        ('none', ()), ('user', (('account', 'source', 'user'),)))}
    for opt, st in (((), 'excluded'), ((('account', 'source', 'user'),), 'opted_in')):
        inv = take(world, *opt)
        assert [(i['status'], i.get('loads_as')) for i in items(inv, type='plugin', name='up@m')] == [
            (st, 'up-cli')]
        assert status_of(inv, 'hook', 'inline.sh') == st
        assert status_of(inv, 'skill', 'upskill') == st
        assert {i['name'] for i in items(inv, source='plugin:up@m', type='skill')} == {
            'upskill', 'declskill', 'rootskill'}
        assert status_of(inv, 'mcp_server', 'upmcp') == 'excluded'
        (syn,) = items(inv, type='skill', name='synskill')
        assert (syn['source'], syn['status'], syn['via']) == ('user', st, 'synced')
    # recording more never changes what the process is given
    assert before == {'none': take(world)['flags'],
                      'user': take(world, ('account', 'source', 'user'))['flags']}
    assert before['none']['disable_slash_commands'] is True


def test_E24_every_claude_md_follows_its_setting_source_ancestors_too(world, tmp_path):
    """PV-19 (O5): CLAUDE.md and .claude/CLAUDE.md, in the workdir and every
    ancestor, follow `project`; CLAUDE.local.md there follows `local`."""
    for rel in ('CLAUDE.md', 'CLAUDE.local.md', os.path.join('.claude', 'CLAUDE.md')):
        _write(str(tmp_path / rel), 'ancestor')
    _write(os.path.join(world[1], 'CLAUDE.local.md'), 'local')

    anc = str(tmp_path).replace(os.sep, '/')

    def mds(inv):
        return {(m['source'], m['name'].replace(os.sep, '/').replace(anc, '<anc>'), m['status'])
                for m in items(inv, type='claude_md')}
    want = lambda p, lo: {  # noqa: E731
        ('project', '<anc>/CLAUDE.md', p), ('project', '<anc>/.claude/CLAUDE.md', p),
        ('local', '<anc>/CLAUDE.local.md', lo), ('project', 'CLAUDE.md', p),
        ('local', 'CLAUDE.local.md', lo)}
    assert mds(take(world)) >= want('excluded', 'excluded')
    assert mds(take(world, ('project', 'source', 'project'))) >= want('opted_in', 'excluded')
    assert mds(take(world, ('project', 'source', 'local'))) >= want('excluded', 'opted_in')


# ── the Claude Code adapter: the argv reads the recorded inventory ───────────

def _spec(**kw):
    from archeus.harnesses import base
    return base.ExecutionSpec(execution_id=ids.new_id('execution'), prompt='p',
                              workdir=kw.pop('workdir', '.'), **kw)


def test_E21_claude_code_is_spawned_with_the_flags_of_its_recorded_inventory(world):
    from archeus.harnesses import base
    a = cc.ClaudeCodeAdapter(exe='claude')
    acct = base.AccountRef('acc', world[0])
    spec = _spec(workdir=world[1], account=acct, opt_ins=(('project', 'source', 'project'),
                                                         ('account', 'plugin', 'pl@m')))
    inv = a.inventory(spec)
    assert inv['flags']['setting_sources'] == ['project']
    argv = a.argv(_spec(workdir=world[1], account=acct, inventory=inv), 'sess')
    i = argv.index('--setting-sources')
    assert argv[i + 1] == 'project' and '--strict-mcp-config' in argv
    assert argv[argv.index('--plugin-dir') + 1] == inv['flags']['plugin_dirs'][0]['path']
    assert '--disable-slash-commands' not in argv          # the plugin carries a skill
    # no inventory: the narrowest flags, never Claude Code's default of every source
    bare = a.argv(_spec(account=acct), 'sess')
    j = bare.index('--setting-sources')
    assert bare[j:j + 4] == ['--setting-sources', '', '--strict-mcp-config',
                             '--disable-slash-commands']
    # Archeus's own hook is still installed through --settings, as before
    assert '--settings' in bare


def test_E22_a_hook_that_cannot_write_its_answer_still_exits_with_the_deny(tmp_path):
    """Claude Code reading nothing back is the last place a hook could fail
    open: Python's own exit flush fails and exits 120, a code Claude Code lets
    the call through on. The hook flushes itself and leaves with the deny."""
    _eid, env = _env(tmp_path)
    r, w = os.pipe()
    os.close(r)                                  # nobody reads the answer
    p = subprocess.Popen([sys.executable, HOOK], stdin=subprocess.PIPE, stdout=w,
                         stderr=subprocess.PIPE, env=env)
    os.close(w)
    _out, err = p.communicate(b'not json', timeout=60)
    assert p.returncode == hook.DENY_EXIT, (p.returncode, err)


# ── T-028 (T-017 C2): an isolated execution's inventory (ADR-0053 A2) ─────────

#: every opt-in that would let something of the account home, or an MCP server, in
EVERYTHING = (('account', 'source', 'user'), ('account', 'plugin', 'pl@m'),
              ('account', 'mcp', 'gh'), ('account', 'mcp', 'nope'), ('project', 'mcp', 'db'),
              ('project', 'source', 'project'), ('project', 'source', 'local'))


def _from_home(i):
    return (i['source'] in ('user', 'plugin') or i['source'].startswith('plugin:')
            or (i['type'] == 'plugin' and i['source'] in ('project', 'local')))


def _inside(path, root):
    p, r = (os.path.normcase(os.path.realpath(x)) for x in (path, root))
    return p == r or p.startswith(r.rstrip(os.sep) + os.sep)


def test_an_isolated_inventory_admits_no_mcp_server(world, tmp_path):
    ordinary, inv = take(world, *EVERYTHING), take(world, *EVERYTHING, isolated=True)
    assert ordinary['flags']['mcp_servers']                 # the opt-ins do reach a server
    assert inv['flags']['mcp_servers'] == []
    mcp = items(inv, type='mcp_server')
    assert {i['name'] for i in mcp} >= {'gh', 'web', 'db', 'nope'}
    assert {i['reason'] for i in mcp} == {sources.ISOLATED_NO_MCP}
    assert {(i['name'], i['status']) for i in mcp if i['name'] in ('gh', 'db', 'nope')} == {
        ('gh', 'excluded'), ('db', 'excluded'), ('nope', 'not_found')}
    res = str(tmp_path / 'res')
    argv = sources.flag_argv(inv['flags'], home=world[0], workdir=world[1], exec_dir=res)
    assert '--mcp-config' not in argv and not os.path.exists(os.path.join(res, 'mcp.json'))


@pytest.mark.parametrize('recorded_only', [(), ('user',)])
def test_an_isolated_inventory_never_predicts_an_account_home_item_loaded(world,
                                                                        recorded_only):
    inv = take(world, *EVERYTHING, isolated=True, recorded_only=recorded_only)
    home = [i for i in inv['items'] if _from_home(i)]
    assert {i['type'] for i in home} >= {'hook', 'permission', 'plugin', 'skill', 'claude_md'}
    assert not [i for i in home if i['status'] in sources.LOADED]
    assert {i['reason'] for i in home if i['type'] != 'mcp_server'} == {
        sources.ISOLATED_NOT_MATERIALISED}
    assert (inv['flags']['setting_sources'], inv['flags']['plugin_dirs']) == (
        ['project', 'local'], [])
    assert inv['recorded_only'] == []
    # what is not the home's still follows its own source, and managed still applies
    assert status_of(inv, 'hook', 'project-hook.sh') == 'opted_in'
    assert 'reason' not in items(inv, source='project', type='hook')[0]
    assert status_of(inv, 'hook', 'managed.sh') == 'not_excludable'
    # every item predicted loaded is one the flags actually pass
    loaded = {i['source'] for i in inv['items'] if i['status'] in sources.LOADED}
    assert loaded <= set(inv['flags']['setting_sources'])


def test_the_home_and_its_plugins_bring_no_skill_to_an_isolated_execution(world):
    opts = (('account', 'source', 'user'), ('account', 'plugin', 'pl@m'))
    assert take(world, *opts)['flags']['disable_slash_commands'] is False
    assert take(world, *opts, isolated=True)['flags']['disable_slash_commands'] is True
    both = take(world, *opts, ('project', 'source', 'project'), isolated=True)
    assert both['flags']['disable_slash_commands'] is False      # the project's own skill


def test_an_isolated_argv_names_no_path_inside_the_account_home(world, tmp_path):
    a = cc.ClaudeCodeAdapter(exe='claude')
    acct = base.AccountRef('acc', world[0])
    spec = _spec(workdir=world[1], account=acct, opt_ins=EVERYTHING)
    inv = a.inventory(spec, isolated=True)
    argv = a.argv(_spec(workdir=world[1], account=acct, inventory=inv), 'sess')
    assert '--plugin-dir' not in argv and '--mcp-config' not in argv
    assert not [x for x in argv if os.path.isabs(x) and _inside(x, world[0])]
    assert a.inventory(spec) == a.inventory(spec, isolated=False)   # ordinary: unchanged
    ordinary = a.argv(_spec(workdir=world[1], account=acct, inventory=a.inventory(spec)), 's')
    assert '--plugin-dir' in ordinary and '--mcp-config' in ordinary


def test_the_fake_harness_forwards_the_decision_to_the_same_inventory(world):
    from archeus.harnesses.fake import FakeHarness
    spec = _spec(workdir=world[1], account=base.AccountRef('acc', world[0]),
                 opt_ins=EVERYTHING)
    got = FakeHarness(sources=True).inventory(spec, isolated=True)
    want = sources.take(world[0], world[1], EVERYTHING, isolated=True)
    assert (got['flags'], [(i['source'], i['type'], i['name'], i['status'])
                           for i in got['items'] if _from_home(i)]) == \
        (want['flags'], [(i['source'], i['type'], i['name'], i['status'])
                         for i in want['items'] if _from_home(i)])
    assert FakeHarness(sources=True).inventory(spec)['flags']['mcp_servers']


def test_a_plugin_the_project_enables_still_lives_in_the_home(world):
    path = os.path.join(world[1], '.claude', 'settings.json')
    with open(path, encoding='utf-8') as f:
        d = json.load(f)
    _write(path, dict(d, enabledPlugins={'pl@m': True}))
    opt = ('project', 'source', 'project')
    assert items(take(world, opt), source='project', type='plugin')[0]['status'] == 'opted_in'
    (p,) = items(take(world, opt, isolated=True), source='project', type='plugin')
    assert (p['status'], p['reason']) == ('excluded', sources.ISOLATED_NOT_MATERIALISED)

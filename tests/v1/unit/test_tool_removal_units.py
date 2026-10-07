"""P20 slice F (PV-22; ADR-0052): Claude Code tool removal beneath the hook.

Without a process: the argv the adapter builds for every set of action classes
(`--tools` always, `--settings` always, `--allowedTools` never), the mapping's
completeness against ACTION_CLASSES and the canonicaliser, the checked-in CLI
snapshot (C1), the MCP deny with its normalised names and its collision rule
(C2), the conditional `Skill` (C3); and the fake agent honouring the tool flags
the way Claude Code 2.1.292 was observed to (p20-design-gate §12, F.0).
"""

import itertools
import json
import os
import subprocess
import sys

import pytest

from archeus.core.domain import ids
from archeus.core.domain.actions import ACTION_CLASSES
from archeus.core.execution import canonical
from archeus.harnesses import base, sources
from archeus.harnesses.calls import claude_models
from archeus.harnesses.claude_code import adapter as cc, tools as T

from v1.unit.test_settings_sources_units import _write, take, world  # noqa: F401

AGENT = os.path.join(os.path.dirname(sources.__file__), 'fake_agent.py')
MAPPED = [t for ts in T.TOOLS.values() for t in ts]
OFFERED = [t for t in MAPPED if t not in ('LS', 'MultiEdit')]


def _spec(classes, **kw):
    return base.ExecutionSpec(execution_id=ids.new_id('execution'), prompt='p',
                              workdir=kw.pop('workdir', '.'),
                              task_contract={'action_classes': list(classes)}, **kw)


def _flag(argv, name):
    assert argv.count(name) <= 1, argv
    return argv[argv.index(name) + 1] if name in argv else None


def _inv(servers=(), items=(), skills=False):
    return {'flags': dict(sources.DEFAULT_FLAGS, mcp_servers=list(servers),
                          disable_slash_commands=not skills), 'items': list(items)}


def _mcp(source, name, status='excluded'):
    return {'source': source, 'type': 'mcp_server', 'name': name, 'status': status}


# ── the argv: every set of classes ───────────────────────────────────────────

def test_F01_every_set_of_action_classes_gets_exactly_its_mapped_offered_tools():
    """All 8192 subsets of ACTION_CLASSES: `--tools` is the mapping of the
    classes held, in the mapping's order, never a name the CLI does not offer;
    `--allowedTools` never appears."""
    offered = T.offered()
    for n in range(len(ACTION_CLASSES) + 1):
        for held in itertools.combinations(ACTION_CLASSES, n):
            a = T.tool_argv(held, None)
            got = a[a.index('--tools') + 1].split(',') if a[a.index('--tools') + 1] else []
            assert got == [t for c in T.TOOLS if c in held for t in T.TOOLS[c] if t in offered]
            assert set(got) <= offered and not {'LS', 'MultiEdit'} & set(got)
            assert ('Bash' in got) == ('exec' in held) and ('Write' in got) == ('write_repo' in held)
            assert ('WebFetch' in got) == ('web' in held) and ('Read' in got) == ('read' in held)
            assert '--allowedTools' not in a and T.SKILL not in got


@pytest.mark.parametrize('held', [
    c for n in range(5) for c in itertools.combinations(['read', 'write_repo', 'exec', 'web'], n)]
    + [('deploy',), ('git_push', 'credential'), ('read', 'destructive')])
def test_F02_the_adapter_always_passes_tools_and_settings_and_never_allowed_tools(held):
    a = cc.ClaudeCodeAdapter(exe='claude').argv(_spec(held), 'sess')
    assert '--allowedTools' not in a and '--allowed-tools' not in a
    hook = _flag(a, '--settings')
    assert hook and os.path.isfile(hook)
    assert _flag(a, '--tools') == ','.join(T.allowed(held))
    # the source flags slice E records are untouched, and come first
    assert a.index('--setting-sources') < a.index('--tools')
    assert _flag(a, '--disallowedTools') == 'mcp__*'


def test_F03_a_task_with_no_mapped_class_is_given_an_empty_tools_never_none():
    """Left out, `--tools` would mean every tool: a task holding only classes
    with no tool of their own (they act through Bash) gets `--tools ""`, which
    Claude Code 2.1.292 accepts and reads as no tool (F.0)."""
    for held in ((), ('deploy',), ('destructive', 'git_push')):
        a = cc.ClaudeCodeAdapter(exe='claude').argv(_spec(held), 'sess')
        i = a.index('--tools')
        assert a[i + 1] == '' and not a[i + 1].startswith('-')


# ── the MCP deny (C2) ────────────────────────────────────────────────────────

def test_F04_nothing_opted_in_denies_every_mcp_tool():
    assert T.mcp_deny(None) == T.mcp_deny({}) == T.mcp_deny(_inv()) == ['mcp__*']
    assert T.mcp_deny(_inv(items=[_mcp('user', 'gh')])) == ['mcp__*']


def test_F05_with_an_opt_in_each_named_excluded_server_is_denied_and_the_opted_in_never():
    inv = _inv(servers=[{'owner': 'account', 'name': 'gh'}],
               items=[_mcp('user', 'gh', 'opted_in'), _mcp('user', 'web'), _mcp('project', 'db'),
                      _mcp('project', 'gone', 'not_found'),
                      # L2: a plugin's server is not named (strict keeps it out)
                      _mcp('plugin:up@m', 'upmcp')])
    assert T.mcp_deny(inv) == ['mcp__db', 'mcp__web']
    a = T.tool_argv(('read',), inv)
    assert _flag(a, '--disallowedTools') == 'mcp__db,mcp__web' and 'mcp__*' not in a
    # an opt-in with nothing else excluded: nothing to deny, no flag
    only = _inv(servers=[{'owner': 'account', 'name': 'gh'}], items=[_mcp('user', 'gh', 'opted_in')])
    assert T.mcp_deny(only) == [] and '--disallowedTools' not in T.tool_argv(('read',), only)


def test_F06_a_deny_names_a_server_as_claude_code_names_its_tools():
    """Observed on 2.1.292 (F.0): `.` and `@` become `_`, `-` and case are
    kept, and a deny with the raw name matches nothing."""
    assert [T.mcp_name(n) for n in ('pv.dot', 'pv@at', 'pv-dash', 'PvCase', 'a_b')] == [
        'pv_dot', 'pv_at', 'pv-dash', 'PvCase', 'a_b']
    inv = _inv(servers=[{'owner': 'account', 'name': 'keep'}],
               items=[_mcp('user', n) for n in ('pv.dot', 'pv@at', 'pv-dash', 'PvCase')])
    deny = T.mcp_deny(inv)
    assert deny == ['mcp__PvCase', 'mcp__pv-dash', 'mcp__pv_at', 'mcp__pv_dot']
    assert not any('.' in p or '@' in p for p in deny)


def test_F07_an_excluded_server_that_collides_with_an_opted_in_one_is_not_denied():
    """L1: a deny cannot tell them apart and would take the opted-in server
    with it; --strict-mcp-config, which loads only the opted-in definition,
    is what keeps the excluded one out."""
    dot = _inv(servers=[{'owner': 'project', 'name': 'pv_dot'}],
               items=[_mcp('user', 'pv.dot'), _mcp('project', 'pv_dot', 'opted_in'),
                      _mcp('user', 'other')])
    assert T.mcp_deny(dot) == ['mcp__other']
    # the same name under the other owner is the commonest collision
    same = _inv(servers=[{'owner': 'project', 'name': 'gh'}],
                items=[_mcp('user', 'gh'), _mcp('project', 'gh', 'opted_in')])
    assert T.mcp_deny(same) == []


# ── Skill (C3) ───────────────────────────────────────────────────────────────

def test_F08_skill_is_allowed_exactly_when_an_opted_in_source_brings_a_skill(world):  # noqa: F811
    def tools_of(inv, held=('read',)):
        return _flag(T.tool_argv(held, inv), '--tools').split(',')
    none = take(world)
    assert none['flags']['disable_slash_commands'] and T.SKILL not in tools_of(none)
    user = take(world, ('account', 'source', 'user'))          # the home holds a skill
    assert not user['flags']['disable_slash_commands'] and T.SKILL in tools_of(user)
    plug = take(world, ('account', 'plugin', 'pl@m'))          # the plugin carries one
    assert T.SKILL in tools_of(plug)
    # an opt-in that brings no skill keeps them off, and Skill out
    mcp = take(world, ('account', 'mcp', 'gh'))
    assert mcp['flags']['disable_slash_commands'] and T.SKILL not in tools_of(mcp)
    # a task holding no mapped class still gets Skill when a skill is opted in
    assert tools_of(user, held=('deploy',)) == [T.SKILL]


@pytest.mark.parametrize('tool, inp', [('Skill', {'skill': 'x'}), ('PowerShell', {'command': 'ls'}),
                                       ('mcp__gh__issue', {})])
def test_F09_a_held_tool_the_canonicaliser_does_not_know_is_judged_unclassified_exec(tool, inp):
    actions, unclassified = canonical.canonicalise(tool, inp, {'workdir': '.', 'branch': None,
                                                               'remotes': {}})
    assert unclassified and [a.action_class for a in actions] == ['exec']


# ── completeness and the snapshot (C1) ───────────────────────────────────────

def test_F10_every_action_class_and_every_canonicaliser_tool_has_a_mapping():
    assert set(T.TOOLS) | set(T.NO_TOOL) == set(ACTION_CLASSES)
    assert not set(T.TOOLS) & set(T.NO_TOOL) and len(T.NO_TOOL) == len(set(T.NO_TOOL))
    named = canonical.READ_TOOLS + canonical.WRITE_TOOLS + ('Bash', 'WebFetch', 'WebSearch')
    cls = {t: c for c, ts in T.TOOLS.items() for t in ts}
    for tool in named:
        assert tool in cls, tool                 # LS and MultiEdit too: ADR-0052 §2 as written
        inp = {'command': 'make build'} if tool == 'Bash' else {'url': 'https://example.test/'} \
            if tool == 'WebFetch' else {'query': 'q'} if tool == 'WebSearch' else {'file_path': 'a'}
        actions, unclassified = canonical.canonicalise(tool, inp, {'workdir': '.', 'branch': None,
                                                                   'remotes': {}})
        assert not unclassified and {a.action_class for a in actions} == {cls[tool]}, tool


def test_F11_every_offered_tool_is_mapped_or_excluded_and_the_snapshot_says_what_is_not_offered():
    snap, norm = T.SNAPSHOT, lambda xs: {T.ALIASES.get(x, x) for x in xs}  # noqa: E731
    offered = norm(T.offered())
    # every name the CLI offers: mapped, Skill (conditional), or excluded by default
    assert offered == (set(MAPPED) & offered) | {T.SKILL} | norm(T.EXCLUDED)
    assert not norm(T.EXCLUDED) & set(MAPPED) and T.SKILL not in T.EXCLUDED
    assert len(T.EXCLUDED) == len(set(T.EXCLUDED))
    # mapped but not offered by this CLI: exactly what the snapshot records
    assert set(MAPPED) - offered == set(snap['mapped_not_offered']) == {'LS', 'MultiEdit'}
    # Task and Agent are one tool; the API's name is excluded through the alias
    assert T.ALIASES == {'Agent': 'Task'} and 'Task' in T.EXCLUDED and 'Agent' not in offered
    # a model's own tools are offered tools, and excluded
    assert set(snap['model_only']) <= set(snap['tools']) & set(T.EXCLUDED)
    assert {m for ms in snap['model_only'].values() for m in ms} <= set(snap['models'])
    # every model an execution may name was read
    assert {m.id for m in claude_models() if not m.id.startswith('claude-')} == set(snap['models'])
    assert snap['version'] == '2.1.292' and set(OFFERED) <= offered


# ── the fake agent honours the tool flags ───────────────────────────────────

def _agent(tmp_path, steps, flags, cwd=None):
    """Run the fake agent with a hook that logs every call it is asked about."""
    log = tmp_path / 'hook.log'
    if log.exists():
        log.unlink()
    script = tmp_path / 'h.py'
    script.write_text('import sys, json\nd = json.loads(sys.stdin.read())\n'
                      'open(%r, "a").write(d["tool_name"] + "\\n")\n'
                      'print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",'
                      ' "permissionDecision": "allow"}}))\n' % str(log))
    env = dict(os.environ, ARCHEUS_HOOK_CMD=json.dumps([sys.executable, str(script)]))
    r = subprocess.run([sys.executable, AGENT, json.dumps(steps), '0'] + flags, input='',
                       capture_output=True, text=True, env=env, timeout=60,
                       cwd=str(cwd or tmp_path))
    evs = [json.loads(line) for line in r.stdout.splitlines()]
    asked = log.read_text().split() if log.exists() else []
    return evs, asked


def _tool(name, **inp):
    return {'emit': {'type': 'tool', 'name': name, 'input': inp}}


def test_F12_the_fake_agent_never_runs_a_tool_absent_from_tools(tmp_path):
    steps = [_tool('Bash', command='rm -rf x'), _tool('Write', file_path='w.txt', content='x'),
             _tool('Agent'), _tool('Skill', skill='s'), _tool('Read', file_path='a'),
             _tool('mcp__gh__issue')]
    evs, asked = _agent(tmp_path, steps, ['--setting-sources', '', '--strict-mcp-config',
                                          '--disable-slash-commands', '--tools', 'Read,Glob,Grep',
                                          '--disallowedTools', 'mcp__*'])
    gone = [e['name'] for e in evs if e['type'] == 'tool_unavailable']
    assert gone == ['Bash', 'Write', 'Agent', 'Skill', 'mcp__gh__issue']
    assert [e['name'] for e in evs if e['type'] == 'tool'] == ['Read'] == asked
    assert not (tmp_path / 'w.txt').exists() and evs[-1] == {'type': 'exit', 'code': 0}
    # empty --tools: nothing at all
    evs, asked = _agent(tmp_path, [_tool('Read', file_path='a')], ['--tools', ''])
    assert [e['type'] for e in evs][1:] == ['tool_unavailable', 'exit']


def test_F13_the_fake_agent_loads_only_strict_mcp_servers_and_honours_each_deny(tmp_path):
    cfg = tmp_path / 'mcp.json'
    cfg.write_text(json.dumps({'mcpServers': {'pv.dot': {}, 'keep': {}, 'pvother': {}}}))
    base_ = ['--strict-mcp-config', '--mcp-config', str(cfg), '--tools', '']
    steps = [_tool('mcp__pv_dot__ping'), _tool('mcp__keep__ping'), _tool('mcp__pvother__ping'),
             _tool('mcp__unloaded__ping')]

    def ran(deny):
        flags = base_ + (['--disallowedTools', deny] if deny else [])
        return [e['name'] for e in _agent(tmp_path, steps, flags)[0] if e['type'] == 'tool']
    assert ran(None) == ['mcp__pv_dot__ping', 'mcp__keep__ping', 'mcp__pvother__ping']
    assert ran('mcp__pv_dot,mcp__pvother__*') == ['mcp__keep__ping']
    assert ran('mcp__pv') == ran(None)                 # a deny is not a prefix
    assert ran('mcp__pv*') == ['mcp__keep__ping']       # unless it is a glob
    assert ran('mcp__*') == []
    # without --strict-mcp-config the agent does not model other sources: offered
    evs, _ = _agent(tmp_path, [_tool('mcp__any__x')], ['--tools', ''])
    assert [e['type'] for e in evs][1] == 'tool'


def test_F14_skill_needs_slash_commands_on_and_a_place_in_tools(tmp_path):
    def ran(flags):
        evs, asked = _agent(tmp_path, [_tool('Skill', skill='s')], flags)
        return [e['type'] for e in evs][1] == 'tool' and asked == ['Skill']
    assert ran(['--tools', 'Read,Skill'])
    assert not ran(['--tools', 'Read'])
    assert not ran(['--tools', 'Read,Skill', '--disable-slash-commands'])

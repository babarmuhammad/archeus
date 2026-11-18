"""P20 slice F (PV-22; ADR-0052): tool removal through Core.

On the fake harness standing in for Claude Code's settings sources AND its tool
removal: the process is given `--tools` from its task's action classes and the
MCP deny from its recorded inventory, and the agent honours them as Claude
Code 2.1.292 was observed to (F.0). A removed tool never runs and never reaches
the hook; a held one is still judged by Core; an opted-in MCP server stays
usable while the excluded ones are denied by the name Claude Code gives them,
except one whose name collides with the opted-in server's (C2, L1); `Skill`
exists exactly when an opted-in source brings a skill (C3).
"""

import json
import os
import time

import pytest

from archeus.core.domain import entities
from archeus.harnesses import sources
from archeus.harnesses.fake import FakeHarness
from archeus.infra.paths import ExecPaths

from v1.integration.test_execution import DONE, TOOL, Rig, _running, ended
from v1.integration.test_policy import task
from v1.integration.test_settings_sources import _git_commit, _write, opt, ready_in, run_one, \
    started
from archeus.core.application import world


@pytest.fixture
def x(db, tmp_path, monkeypatch):
    """An account whose home holds three MCP servers (one named with a `.`) and
    a skill; a project (a git repository) whose `.mcp.json` holds two, one of
    them named as Claude Code names the account's `pv.dot`."""
    monkeypatch.setattr(sources, 'MANAGED', str(tmp_path / 'no-managed.json'))
    home, root = str(tmp_path / 'home'), str(tmp_path / 'proj')
    _write(os.path.join(home, '.claude.json'), {'mcpServers': {
        'gh': {'command': 'gh-mcp'}, 'web': {'command': 'w'}, 'pv.dot': {'command': 'd'}}})
    os.makedirs(os.path.join(home, 'skills', 'uskill'))
    open(os.path.join(home, 'skills', 'uskill', 'SKILL.md'), 'w').write('x')
    _write(os.path.join(root, '.mcp.json'), {'mcpServers': {
        'db': {'command': 'db-mcp'}, 'pv_dot': {'command': 'p'}}})
    _git_commit(root)
    rig = Rig(db, adapters=[FakeHarness(sources=True, tools=True)])
    rig.home, rig.root = home, root
    rig.acc = rig.account('Work', home_ref=home)
    rig.prj = rig.do(world.create_project, who=rig.user, name='p', root_paths=[root])[
        'project']['id']
    yield rig
    rig.cleanup()


def stream(e):
    with open(ExecPaths(e.id).stream, encoding='utf-8') as f:
        return [json.loads(line) for line in f if line.startswith('{')]


def hooks(x, e):
    return [ev['payload']['decision'] for ev in x.events('execution.hook')
            if ev['subject']['id'] == e.id]


def flag(argv, name):
    return argv[argv.index(name) + 1] if name in argv else None


def through_approval(x, mid):
    """An opted-in MCP tool or Skill is an unclassified `exec` to the hook, so
    Core asks (never ALLOW, p9 §6.3): approve it, and the same execution
    resumes and runs the call (P11)."""
    e = x.drive(mid, lambda: (x.exe(mission_id=mid) is not None
                              and x.exe(mission_id=mid).state == 'AWAITING_APPROVAL'
                              and x.exe(mission_id=mid)))
    a = x.pending(mid)
    assert (a.kind, a.execution_id) == ('action', e.id)
    x.decide(a)
    x.drive(mid, ended(x, e.id))
    return x.state(e.id)


def test_R01_a_removed_tool_never_runs_and_never_reaches_the_hook(x):
    x.scenarios['t1'] = [TOOL('Bash', {'command': 'rm -rf .'}),
                         TOOL('Write', {'file_path': 'w.txt', 'content': 'x'}),
                         TOOL('Read', {'file_path': 'a'}), DONE]
    e = run_one(x, ready_in(x, x.prj, task('t1', 'read')))
    argv = started(e)['argv']
    assert flag(argv, '--tools') == 'Read,Glob,Grep'
    assert flag(argv, '--disallowedTools') == 'mcp__*' and '--allowedTools' not in argv
    evs = stream(e)
    assert [v['name'] for v in evs if v['type'] == 'tool_unavailable'] == ['Bash', 'Write']
    assert [v['name'] for v in evs if v['type'] == 'tool'] == ['Read']
    # only the held tool was judged, and it was allowed
    assert hooks(x, e) == ['allow'] and e.state == 'ENDED_OK'
    assert not os.path.exists(os.path.join(e.workdir, 'w.txt'))


def test_R02_a_held_tool_is_still_judged_by_core_beneath_removal(x):
    x.scenarios['t1'] = [{'emit': {'type': 'working'}}, {'sleep': 0.8},
                         TOOL('Write', {'file_path': 'w.txt', 'content': 'x'}), {'sleep': 5}]
    mid = ready_in(x, x.prj, task('t1', 'write_repo', 'read'))
    e = _running(x, mid)
    x.rule('USER', 'write_repo', 'DENY')                # what the hook request meets
    deadline = time.monotonic() + 30
    evs = []
    while time.monotonic() < deadline and 'tool_denied' not in [v['type'] for v in evs]:
        x.manager.tick()
        evs = stream(e) if os.path.exists(ExecPaths(e.id).stream) else []
        time.sleep(0.05)
    assert flag(started(e)['argv'], '--tools') == 'Read,Glob,Grep,Write,Edit,NotebookEdit'
    assert [v['type'] for v in evs if v['type'] in ('tool', 'tool_denied', 'tool_unavailable')] == [
        'tool_denied']
    assert hooks(x, e) == ['deny'] and not os.path.exists(os.path.join(e.workdir, 'w.txt'))


def test_R03_an_opted_in_mcp_server_stays_usable_and_the_excluded_are_denied_by_name(x):
    opt(x, x.acc, 'mcp', 'gh')
    x.scenarios['t1'] = [TOOL('mcp__web__get', {}), TOOL('mcp__db__query', {}),
                         TOOL('mcp__pv_dot__x', {}), TOOL('mcp__gh__issue', {}), DONE]
    e = through_approval(x, ready_in(x, x.prj, task('t1', 'read')))
    argv = started(e)['argv']
    # every excluded server, named as Claude Code names its tools; never mcp__*
    assert flag(argv, '--disallowedTools') == 'mcp__db,mcp__pv_dot,mcp__web'
    assert started(e)['mcp_servers'] == ['gh']              # what the process loaded
    evs = stream(e)
    assert [v['name'] for v in evs if v['type'] == 'tool'] == ['mcp__gh__issue']
    assert [v['name'] for v in evs if v['type'] == 'tool_unavailable'] == [
        'mcp__web__get', 'mcp__db__query', 'mcp__pv_dot__x']
    # judged as an unclassified exec: asked, approved, run once
    assert (e.state, e.process_seq) == ('ENDED_OK', 2) and hooks(x, e)[-1] == 'allow'


def test_R04_an_excluded_server_whose_name_collides_with_the_opted_in_one_is_not_denied(x):
    """L1: the account's `pv.dot` and the project's opted-in `pv_dot` are one
    name to Claude Code. A deny would take the opted-in server with it, so the
    excluded one is left to --strict-mcp-config, which does not load it."""
    opt(x, x.prj, 'mcp', 'pv_dot')
    x.scenarios['t1'] = [TOOL('mcp__gh__issue', {}), TOOL('mcp__pv_dot__x', {}), DONE]
    e = through_approval(x, ready_in(x, x.prj, task('t1', 'read')))
    argv = started(e)['argv']
    assert flag(argv, '--disallowedTools') == 'mcp__db,mcp__gh,mcp__web'
    assert started(e)['mcp_servers'] == ['pv_dot']      # the opted-in definition alone
    evs = stream(e)
    assert [v['name'] for v in evs if v['type'] == 'tool'] == ['mcp__pv_dot__x']
    assert [v['name'] for v in evs if v['type'] == 'tool_unavailable'] == ['mcp__gh__issue']
    assert e.state == 'ENDED_OK'


def test_R05_skill_exists_exactly_when_an_opted_in_source_brings_a_skill(x):
    x.scenarios['t1'] = [TOOL('Skill', {'skill': 'uskill'}), DONE]
    off = run_one(x, ready_in(x, x.prj, task('t1', 'read')))
    argv = started(off)['argv']
    assert '--disable-slash-commands' in argv and 'Skill' not in flag(argv, '--tools').split(',')
    assert [v['type'] for v in stream(off) if v.get('name') == 'Skill'] == ['tool_unavailable']
    assert hooks(x, off) == []
    opt(x, x.acc, 'source', 'user')                     # the home holds a skill
    on = through_approval(x, ready_in(x, x.prj, task('t1', 'read')))
    argv = started(on)['argv']
    assert '--disable-slash-commands' not in argv
    assert flag(argv, '--tools') == 'Read,Glob,Grep,Skill'
    assert [v['type'] for v in stream(on) if v.get('name') == 'Skill'] == ['tool']
    assert hooks(x, on)[-1] == 'allow' and on.state == 'ENDED_OK'   # asked, approved, run
    assert {e.id for e in x.all(entities.Execution)} == {off.id, on.id}

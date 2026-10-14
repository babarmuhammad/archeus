"""K-O2 (T-053 §6, P6): Archeus's own calls run as the user, so none of them
may run in the user's repository, where an execution's merged work can leave
project settings and hooks; every own call, whose prompt carries
execution-influenced text, runs with no tools at all in a fresh empty
directory of its own, never Core's state root (T-081); and a verification
command gets none of Core's ARCHEUS_* discovery or credentials. Fake adapters,
stand-in runners and a fake process only: no CLI is spawned."""

import ast
import inspect
import os
import stat
import subprocess
from types import SimpleNamespace

import pytest

from archeus.core.calls import OwnCalls
from archeus.core.domain import entities, ids
from archeus.core.knowledge import ingest
from archeus.harnesses import base
from archeus.harnesses import calls as real
from archeus.harnesses.fake import FakeCaller
from archeus.infra import paths
from archeus.node.local import LocalNode
from v1.integration.test_intent import WORK
from v1.integration.test_knowledge import GOOD, Rig, project
from v1.integration.test_planning import ONE, Rig as PRig

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(
    __file__)))))
#: CallSpec is built in exactly one place, from OwnCalls.run's own `workdir`
PASS_THROUGH = 'archeus/core/calls.py'


def _sources():
    for base, dirs, files in os.walk(os.path.join(ROOT, 'archeus')):
        dirs[:] = [d for d in dirs if d != '__pycache__']
        for f in files:
            if f.endswith('.py'):
                p = os.path.join(base, f)
                yield os.path.relpath(p, ROOT).replace('\\', '/'), ast.parse(
                    open(p, encoding='utf-8').read())


def _name(fn):
    return fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, 'id', None)


#: every own call, by the function that makes it: each runs in a fresh empty
#: directory of its own, with no tools
FRESH = {('archeus/core/knowledge/passes.py', 'knowledge'),
         ('archeus/core/knowledge/passes.py', 'decisions'),
         ('archeus/core/knowledge/passes.py', 'lessons'),
         ('archeus/core/missions/intent.py', '_brain'),
         ('archeus/core/planning/worker.py', 'plan'),
         ('archeus/core/verification/worker.py', '_review')}


def _fresh(v):
    """`paths.fresh_call_dir`, handed over uncalled: OwnCalls.run makes it."""
    return (isinstance(v, ast.Attribute) and v.attr == 'fresh_call_dir'
            and isinstance(v.value, ast.Name) and v.value.id == 'paths')


def _in_functions():
    for rel, tree in _sources():
        for fn in ast.walk(tree):
            if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for n in ast.walk(fn):
                    yield rel, fn.name, n


def _no_tools(kw):
    v = kw.get('no_tools')
    return isinstance(v, ast.Constant) and v.value is True


def test_every_own_call_runs_in_a_fresh_directory_with_no_tools():
    """An own call is any call carrying both `purpose=` and `workdir=` (OwnCalls.run,
    the argument dict a caller builds for it, CallSpec); its workdir is
    `paths.fresh_call_dir` handed over uncalled, never ARCHEUS_HOME, a repository
    path or a variable, and it says `no_tools=True` (T-081)."""
    for src in ('paths.fresh_call_dir(x)', 'other.fresh_call_dir', 'paths.call_dir',
                'paths.archeus_home()', 'repo.path', 'workdir', 'os.getcwd()'):
        assert not _fresh(ast.parse(src, mode='eval').body), src
    for src in ('f(no_tools=False)', 'f()', 'f(no_tools=x)', "f(no_tools='True')"):
        assert not _no_tools({k.arg: k.value for k in ast.parse(src, mode='eval').body.keywords})
    seen, bad, fresh = set(), [], set()
    for rel, fn, n in _in_functions():
        if not isinstance(n, ast.Call):
            continue
        kw = {k.arg: k.value for k in n.keywords if k.arg}
        if _name(n.func) == 'CallSpec':
            assert rel == PASS_THROUGH, '%s:%d builds a CallSpec' % (rel, n.lineno)
        if 'purpose' not in kw or 'workdir' not in kw:
            continue
        seen.add((rel, n.lineno))
        w = kw['workdir']
        through = (rel == PASS_THROUGH and _name(n.func) == 'CallSpec'
                   and isinstance(w, ast.Name) and w.id == 'workdir')
        if _fresh(w) and _no_tools(kw):
            fresh.add((rel, fn))
        elif not through:
            bad.append('%s:%d workdir=%s no_tools=%s' % (
                rel, n.lineno, ast.unparse(w), kw.get('no_tools') and ast.unparse(kw['no_tools'])))
    assert not bad, bad
    assert fresh == FRESH
    # the helper is named nowhere else in archeus/ but where it is defined
    named = {(rel, fn) for rel, fn, n in _in_functions()
             if isinstance(n, (ast.Attribute, ast.Name))
             and 'fresh_call_dir' in (getattr(n, 'attr', None), getattr(n, 'id', None))}
    assert named == FRESH, named
    # three passes, intent, planner, review, and CallSpec itself: a scan that
    # stops finding them reports clean
    assert len(seen) >= 7, seen


def test_the_knowledge_pass_runs_outside_the_repository_on_its_facts(db, tmp_path):
    parent = tmp_path / 'repos'
    parent.mkdir()
    f = FakeCaller(replies={'knowledge_extraction': [{'parsed': GOOD}]})
    r = Rig(db, str(parent), [f])
    repo = project(r)
    (spec, prompt), = [s for s in f.sent if s[0].purpose == 'knowledge_extraction']
    # its own fresh directory, named after its route decision, under run/
    assert spec.workdir == paths.call_dir(spec.route_decision_id)
    assert os.path.isdir(spec.workdir) and os.listdir(spec.workdir) == []
    assert os.path.normcase(spec.workdir) != os.path.normcase(paths.archeus_home())
    assert os.path.normcase(os.path.abspath(repo.path)) not in os.path.normcase(spec.workdir)
    assert 'Read the repository in the working directory' not in prompt
    facts = dict(line.split(': ', 1) for line in prompt.splitlines()
                 if line.startswith(('Module directories', 'Imports between',
                                     'Package dependencies', 'Repository')))
    assert repo.path in facts['Repository']
    assert facts['Module directories'] and facts['Imports between module directories'] != 'none'
    assert ' -> ' in facts['Imports between module directories']
    assert spec.no_tools is True


# ── the fresh call directory: fresh-only, plain, empty, kept ──

def _rd():
    return ids.new_id('route_decision')


def test_a_call_directory_is_fresh_empty_and_its_own(db):
    a, b = _rd(), _rd()
    got = paths.fresh_call_dir(a)
    assert got == paths.call_dir(a) == os.path.join(paths.run_dir(), 'calls', a)
    assert os.path.isdir(got) and os.listdir(got) == []
    assert paths.fresh_call_dir(b) != got
    with pytest.raises(FileExistsError):        # never reused, even empty
        paths.fresh_call_dir(a)
    assert os.path.isdir(got)                   # and the refusal removed nothing


@pytest.mark.parametrize('name', ['..', 'rte_x', '../../repo', 'exe_' + '0' * 26])
def test_a_call_directory_is_named_only_by_a_route_decision_id(db, name):
    with pytest.raises(ValueError):
        paths.call_dir(name)


def test_nothing_in_paths_deletes_or_moves():
    tree = ast.parse(open(os.path.join(ROOT, 'archeus', 'infra', 'paths.py'),
                          encoding='utf-8').read())
    called = {_name(n.func) for n in ast.walk(tree) if isinstance(n, ast.Call)
              and isinstance(n.func, ast.Attribute) and isinstance(n.func.value, ast.Name)
              and n.func.value.id in ('os', 'shutil')}
    assert 'mkdir' in called
    assert not called & {'rmdir', 'removedirs', 'remove', 'unlink', 'rmtree', 'rename',
                         'replace', 'move'}


def _fake_lstat(monkeypatch, target, kind, when=lambda: True):
    """os.lstat as it is, except that *target* is a junction, a symlink or a file
    (while *when* holds)."""
    real_lstat = os.lstat
    fake = {'junction': SimpleNamespace(st_mode=stat.S_IFDIR | 0o777,
                                        st_file_attributes=stat.FILE_ATTRIBUTE_REPARSE_POINT),
            'symlink': SimpleNamespace(st_mode=stat.S_IFLNK | 0o777, st_file_attributes=0),
            'file': SimpleNamespace(st_mode=stat.S_IFREG | 0o666, st_file_attributes=0)}[kind]

    def lstat(p, *a, **kw):
        if when() and os.path.normcase(os.path.abspath(p)) == os.path.normcase(target()):
            return fake
        return real_lstat(p, *a, **kw)
    monkeypatch.setattr(os, 'lstat', lstat)


COMPONENTS = {'home': lambda rd: paths.archeus_home(), 'run': lambda rd: paths.run_dir(),
              'calls': lambda rd: os.path.dirname(paths.call_dir(rd)),
              'leaf': lambda rd: paths.call_dir(rd)}


@pytest.mark.parametrize('kind', ['junction', 'symlink', 'file'])
@pytest.mark.parametrize('where', sorted(COMPONENTS))
def test_an_alias_anywhere_from_home_to_the_call_directory_is_refused(db,
                                                                       monkeypatch, where,
                                                                       kind):
    rd = _rd()
    _fake_lstat(monkeypatch, lambda: COMPONENTS[where](rd), kind)
    with pytest.raises(OSError, match='not a plain directory'):
        paths.fresh_call_dir(rd)
    # an alias above it is seen before anything is made through it
    assert (where == 'leaf') == os.path.isdir(paths.call_dir(rd))


@pytest.mark.parametrize('where', ['home', 'run', 'calls'])
def test_a_parent_swapped_for_an_alias_after_the_mkdir_is_refused(db, monkeypatch, where):
    """Checked before the leaf is made and again after: a swap in between is seen."""
    rd, made, real_mkdir = _rd(), [], os.mkdir
    monkeypatch.setattr(os, 'mkdir', lambda p, *a, **kw: (
        real_mkdir(p, *a, **kw), made.append(p == paths.call_dir(rd)))[0])
    _fake_lstat(monkeypatch, lambda: COMPONENTS[where](rd), 'junction', when=lambda: any(made))
    with pytest.raises(OSError, match='not a plain directory'):
        paths.fresh_call_dir(rd)


def test_a_call_directory_that_is_not_empty_is_refused(db, monkeypatch):
    rd, real = _rd(), os.listdir
    monkeypatch.setattr(os, 'listdir', lambda p: ['planted'] if p == paths.call_dir(rd)
                        else real(p))
    with pytest.raises(OSError, match='not empty'):
        paths.fresh_call_dir(rd)


def test_a_refused_directory_fails_the_knowledge_pass_with_nothing_spawned(db, tmp_path,
                                                                          monkeypatch):
    parent = tmp_path / 'repos'
    parent.mkdir()
    f = FakeCaller(replies={'knowledge_extraction': [{'parsed': GOOD}]})
    r = Rig(db, str(parent), [f])
    _fake_lstat(monkeypatch, lambda: os.path.join(paths.run_dir(), 'calls'), 'junction')
    repo = project(r)
    kp = r.kp(repo.project_id)
    assert (kp['state'], kp['items']) == ('failed', 0)
    assert 'no working directory' in kp['reason'] and 'not a plain directory' in kp['reason']
    assert not [s for s in f.sent if s[0].purpose == 'knowledge_extraction']


# ── T-081: the other own calls, each made once through its own path ──

LESSON = {'lessons': [{'title': 'Pin the formatter', 'text': 'it drifts', 'outcome': 'failed'}]}
DECIDED = {'decisions': [{'statement': 'Ship dark-first'}]}
REPLIES = {'brain': [{'parsed': WORK}], 'planner': [{'parsed': ONE}],
           'knowledge_extraction': [{'parsed': DECIDED}], 'lesson': [{'parsed': LESSON}]}
#: the four own calls this rig reaches (the review is in test_verification.py)
FOUR = {'brain', 'planner', 'knowledge_extraction', 'lesson'}


def _four(db, tmp_path, caller):
    """brain (a message), planner (a mission), decisions (meeting notes) and lessons
    (asked directly: this rig's engine never ends a mission); what each recorded."""
    parent = tmp_path / 'repos'
    parent.mkdir()
    r = PRig(db, str(parent), [caller])
    _reply, it = r.say('Add a --version flag to the CLI')
    mid = r.mission()
    r.settle()
    notes = tmp_path / 'planning-2026-09-20.md'
    notes.write_text('# Planning\nDECISION: ship dark-first.\n', encoding='utf-8')
    ingest.import_file(r.db, r.user, str(notes))
    r.settle()
    return r, {'brain': it.resolution, 'planner': r.m(mid).planning_blocked,
               'lesson': r.passes.lessons(mid),
               'decisions': [d.state for d in r.items(type='DECISION')]}


def test_every_other_own_call_runs_with_no_tools_in_a_fresh_directory_of_its_own(db,
                                                                                tmp_path):
    f = FakeCaller('fake', replies=REPLIES)
    r, got = _four(db, tmp_path, f)
    assert got['brain'] == 'mission_created' and got['decisions'] == ['CANDIDATE']
    assert (got['planner'], got['lesson']) == (None, 'ok')
    assert {spec.purpose for spec, _ in f.sent} == FOUR
    home = os.path.normcase(paths.archeus_home())
    for spec, _ in f.sent:
        assert spec.no_tools is True, spec.purpose
        assert spec.workdir == paths.call_dir(spec.route_decision_id), spec.purpose
        assert os.path.isdir(spec.workdir) and os.listdir(spec.workdir) == []
        assert os.path.normcase(spec.workdir) != home


def test_with_only_pi_every_other_own_call_is_unavailable_and_nothing_is_made(db, tmp_path):
    """pi cannot make a call with no tools (T-069), so with nothing else eligible
    each call ends unavailable at the router's capability step: nothing spawned,
    no call directory, and each worker records it as any unavailable call."""
    pi = FakeCaller('pi', no_tools=False, replies=REPLIES)
    r, got = _four(db, tmp_path, pi)
    assert pi.sent == []
    assert got['brain'] == 'declined' and got['decisions'] == []
    assert got['planner']['outcome'] == 'unavailable' and got['lesson'] == 'unavailable'
    rds = r.all(entities.RouteDecision)
    assert {rd.purpose for rd in rds} == FOUR
    for rd in rds:
        assert rd.result == 'blocked' and rd.requirements['capabilities'] == [
            'headless', 'no_tools']
        (c,) = rd.candidates
        assert (c['resource'], c['eliminated_at_step']) == ('pi', 'capability')
        assert not os.path.exists(paths.call_dir(rd.id))


def test_every_own_call_and_nothing_else_asks_for_no_tools():
    """Every `no_tools=` in archeus/, by the function it is in: each own call
    sets it, OwnCalls.run hands it to CallSpec, and both default to False."""
    got = set()
    for rel, tree in _sources():
        for fn in ast.walk(tree):
            if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                got |= {(rel, fn.name, ast.unparse(k.value)) for n in ast.walk(fn)
                        if isinstance(n, ast.Call) for k in n.keywords if k.arg == 'no_tools'}
    assert got == {(rel, fn, 'True') for rel, fn in FRESH} | {(PASS_THROUGH, 'run', 'no_tools')}
    assert inspect.signature(OwnCalls.run).parameters['no_tools'].default is False
    assert base.CallSpec.__dataclass_fields__['no_tools'].default is False


def _call(monkeypatch, tmp_path, caller, **kw):
    """The argv a real adapter would spawn, from a stand-in runner."""
    from claude_sessions import config, harnesses, llmcall
    seen = []
    monkeypatch.setattr(llmcall, 'run_headless', lambda cmd, stdin=None, **k: (
        seen.append(cmd), llmcall.Result(0, '{}', '', '', False))[1])
    monkeypatch.setattr(llmcall, 'budget_args', lambda: [])
    monkeypatch.setattr(config, 'get_claude_exe', lambda: 'C:/x/claude.exe')
    monkeypatch.setattr(harnesses, 'exe', lambda hid=None: 'C:/x/pi.exe')
    monkeypatch.setattr(harnesses, 'disabled', lambda: set())
    spec = base.CallSpec(route_decision_id='rte_x', purpose='knowledge_extraction',
                         prompt='P', workdir='.', account=base.AccountRef('a', str(tmp_path)),
                         schema={'type': 'object'}, **kw)
    return seen, caller.call(spec)


def test_claude_with_no_tools_gets_an_empty_tools_list(monkeypatch, tmp_path):
    (cmd,), _ = _call(monkeypatch, tmp_path, real.ClaudeCodeCaller(), no_tools=True)
    # left out, --tools would mean every tool: present once, and empty
    assert cmd.count('--tools') == 1 and cmd[cmd.index('--tools') + 1] == ''
    assert '--allowedTools' not in cmd
    deny = cmd.index('--disallowedTools') + 1        # the only list that may name a tool
    named = {t for i, a in enumerate(cmd) if i != deny for t in a.split(',')}
    assert not named & {'Read', 'Grep', 'Glob', 'LS', 'WebFetch', 'Bash'}


def test_pi_refuses_a_call_with_no_tools_and_spawns_nothing(monkeypatch, tmp_path):
    seen, res = _call(monkeypatch, tmp_path, real.PiCaller(), no_tools=True)
    assert seen == [] and res.error == 'failed' and 'no tools' in res.detail


def test_every_other_own_call_keeps_its_argv(monkeypatch, tmp_path):
    (cmd,), _ = _call(monkeypatch, tmp_path, real.ClaudeCodeCaller())
    assert cmd[:6] == ['C:/x/claude.exe', '-p', '--max-turns', '20', '--disallowedTools',
                       'Write,Edit,NotebookEdit,Bash']
    assert '--tools' not in cmd
    (cmd,), _ = _call(monkeypatch, tmp_path, real.PiCaller())
    assert cmd == ['C:/x/pi.exe', '-p', '--no-session', '--tools', 'read,grep,find,ls']


class _Child:
    returncode = 0

    def wait(self, timeout=None):
        return 0


def test_a_verification_command_gets_no_archeus_environment(monkeypatch, tmp_path):
    got = {}

    def popen(argv, **kw):
        got.update(kw['env'])
        return _Child()

    monkeypatch.setattr(subprocess, 'Popen', popen)
    for k, v in (('ARCHEUS_HOME', str(tmp_path)), ('ARCHEUS_HOOK_TOKEN', 'secret'),
                 ('ARCHEUS_EXECUTION_ID', 'exe_x'), ('PYTEST_X', '1'), ('KEEP_ME', 'yes')):
        monkeypatch.setenv(k, v)
    out = LocalNode.run_check(str(tmp_path), ['x'], timeout=5,
                              out_path=str(tmp_path / 'o' / 'out.log'))
    assert out['exit_code'] == 0
    assert not [k for k in got if k.upper().startswith(('ARCHEUS_', 'PYTEST_'))]
    assert got['KEEP_ME'] == 'yes'


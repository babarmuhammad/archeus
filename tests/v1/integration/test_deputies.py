"""K-O2 (T-053 §6, P6): Archeus's own calls run as the user, so none of them
may run in the user's repository, where an execution's merged work can leave
project settings and hooks; and a verification command gets none of Core's
ARCHEUS_* discovery or credentials. Fake adapters and a fake process only."""

import ast
import os
import subprocess

from archeus.harnesses.fake import FakeCaller
from archeus.infra import paths
from archeus.node.local import LocalNode
from v1.integration.test_knowledge import GOOD, Rig, project

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(
    __file__)))))
#: the ARCHEUS_HOME helpers whose result an own call may run in
CORE_OWNED = {'archeus_home'}
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


def _core_owned(v):
    return (isinstance(v, ast.Call) and isinstance(v.func, ast.Attribute)
            and isinstance(v.func.value, ast.Name) and v.func.value.id == 'paths'
            and v.func.attr in CORE_OWNED and not v.args and not v.keywords)


def test_every_own_call_runs_in_a_core_owned_directory():
    """An own call is any call carrying both `purpose=` and `workdir=` (OwnCalls.run,
    the argument dict a caller builds for it, CallSpec); its workdir is a
    Core-owned paths helper, never a repository path or a variable."""
    for src in ('repo.path', 'workdir', 'os.getcwd()', 'paths.archeus_home(x)',
                'other.archeus_home()', 'paths.exec_paths()', "paths.archeus_home(a='b')"):
        assert not _core_owned(ast.parse(src, mode='eval').body), src
    assert _core_owned(ast.parse('paths.archeus_home()', mode='eval').body)
    seen, bad = [], []
    for rel, tree in _sources():
        for n in ast.walk(tree):
            if not isinstance(n, ast.Call):
                continue
            kw = {k.arg: k.value for k in n.keywords if k.arg}
            if _name(n.func) == 'CallSpec':
                assert rel == PASS_THROUGH, '%s:%d builds a CallSpec' % (rel, n.lineno)
            if 'purpose' not in kw or 'workdir' not in kw:
                continue
            seen.append((rel, n.lineno))
            w = kw['workdir']
            through = (rel == PASS_THROUGH and _name(n.func) == 'CallSpec'
                       and isinstance(w, ast.Name) and w.id == 'workdir')
            if not (through or _core_owned(w)):
                bad.append('%s:%d workdir=%s' % (rel, n.lineno, ast.unparse(w)))
    assert not bad, bad
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
    assert spec.workdir == paths.archeus_home()
    assert os.path.normcase(os.path.abspath(repo.path)) not in os.path.normcase(spec.workdir)
    assert 'Read the repository in the working directory' not in prompt
    facts = dict(line.split(': ', 1) for line in prompt.splitlines()
                 if line.startswith(('Module directories', 'Imports between',
                                     'Package dependencies', 'Repository')))
    assert repo.path in facts['Repository']
    assert facts['Module directories'] and facts['Imports between module directories'] != 'none'
    assert ' -> ' in facts['Imports between module directories']


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


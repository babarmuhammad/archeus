"""An execution's children never open a visible console window.

Under DETACHED_PROCESS an execution has no console, so every console program
it starts — the fake agent's PreToolUse hook on each tool call, a real
harness's hooks, git, test commands — gets a NEW, visible one: a window
flashing per tool call, in the test suite and in production alike. Executions
are spawned with a hidden console of their own instead, which their children
inherit (proc.hidden_console_flags)."""

import ast
import json
import os
import subprocess
import sys

import pytest

from archeus.harnesses import base
from claude_sessions import proc

GRAND = ("import ctypes, json, sys; k=ctypes.windll.kernel32; u=ctypes.windll.user32; "
         "h=k.GetConsoleWindow(); open(sys.argv[1],'w').write(json.dumps("
         "{'visible': bool(h and u.IsWindowVisible(h))}))")
CHILD = ("import subprocess, sys; subprocess.run([sys.executable, '-c', %r, sys.argv[1]], "
         "capture_output=True)" % GRAND)


def test_the_harness_spawn_asks_for_a_hidden_console():
    tree = ast.parse(open(base.__file__, encoding='utf-8').read())
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
             and getattr(n.func, 'attr', None) == 'spawn_detached']
    assert calls, 'the harness spawns through proc.spawn_detached'
    for c in calls:
        kw = {k.arg: k.value for k in c.keywords}
        assert isinstance(kw.get('hidden_console'), ast.Constant) and kw['hidden_console'].value is True


def test_hidden_console_flags_are_a_hidden_console_in_its_own_group():
    if not proc.WINDOWS:
        assert proc.hidden_console_flags == 0
        return
    assert proc.hidden_console_flags == (subprocess.CREATE_NO_WINDOW
                                         | subprocess.CREATE_NEW_PROCESS_GROUP)
    assert not proc.hidden_console_flags & subprocess.DETACHED_PROCESS


@pytest.mark.skipif(not sys.platform.startswith('win'), reason='a Windows console property')
def test_a_grandchild_of_an_execution_spawn_has_no_visible_window(tmp_path):
    out = str(tmp_path / 'r.json')
    child, err = proc.spawn_detached([sys.executable, '-c', CHILD, out], hidden_console=True)
    assert child is not None, err
    child.wait(30)
    assert os.path.exists(out)
    assert json.load(open(out)) == {'visible': False}

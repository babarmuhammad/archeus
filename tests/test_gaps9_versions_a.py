"""T-1359 · claude_sessions/versions.py lines 450-529 (update_self): self-update worker argv, environment handoff and wait outcomes.

Selected branches, highest risk first:
1. 480-483 checkout or non-installed mode refuses and never calls spawn_detached
2. 484-486 pipx runs `pipx upgrade`, pip runs `<py> -m pip install -U`, py is proc.python_exe()
3. 491-492 pid is 0 unless defer or restart; then os.getpid()
4. 493-496 environment copied, os.environ untouched, ARCHEUS_UPDATE_TO empty without cache, ARCHEUS_FREE holds console scripts
5. 497-504 restart with no argv tail adds --gui, an existing --gui is not duplicated, sys.argv not mutated
6. 508-509 ARCHEUS_RELAUNCH uses sys.executable, not python_exe()
7. 510-512 spawn failure returns (False, err) or the fixed 'could not start the update worker' text
8. 517-524 wait path: a raising wait gives the 'Still installing' success text; non-zero rc gives _last_update_error or the log path text
9. 513-516 restart and defer return their own messages without waiting on the process
10. 525-527 success names the cached latest or not; no wait gives 'Installing in the background'

Every seam is faked: self_install_mode, proc.python_exe, proc.spawn_detached, console_scripts, jsonstore.load, _last_update_error and the config dir. No pip, no pipx, no detached process.
"""

import json
import os
import sys

import pytest

from claude_sessions import jsonstore
from claude_sessions import proc
from claude_sessions import versions as v

PY = 'C:/Py/python.exe'
SCRIPT = 'C:/Py/Scripts/archeus.exe'


class _Process:
    def __init__(self, rc=0, raises=None):
        self.rc = rc
        self.raises = raises
        self.waits = []

    def wait(self, timeout=None):
        self.waits.append(timeout)
        if self.raises is not None:
            raise self.raises
        return self.rc


class _Spawn:
    def __init__(self, process=None, err=''):
        self.process = process
        self.err = err
        self.calls = []

    def __call__(self, argv, **kw):
        self.calls.append((list(argv), kw))
        return self.process, self.err

    @property
    def argv(self):
        return self.calls[-1][0]

    @property
    def env(self):
        return self.calls[-1][1]['env']


@pytest.fixture
def worker(monkeypatch, tmp_path):
    monkeypatch.setattr(v._c, 'config_dir', str(tmp_path))
    monkeypatch.setattr(v, 'self_install_mode', lambda: 'pip')
    monkeypatch.setattr(proc, 'python_exe', lambda: PY)
    monkeypatch.setattr(v, 'console_scripts', lambda: [SCRIPT])
    monkeypatch.setattr(jsonstore, 'load', lambda path, default=None: {})
    monkeypatch.setattr(v, '_last_update_error', lambda: '')
    monkeypatch.delenv('ARCHEUS_UPDATE_TO', raising=False)
    monkeypatch.delenv('ARCHEUS_RELAUNCH', raising=False)
    spawn = _Spawn(_Process())
    monkeypatch.setattr(proc, 'spawn_detached', spawn)
    return spawn


@pytest.mark.parametrize('mode, text', [
    ('checkout', 'git pull'),
    ('', 'not an installed package'),
])
def test_a_checkout_or_uninstalled_copy_refuses_before_any_spawn(worker, monkeypatch, mode, text):
    monkeypatch.setattr(v, 'self_install_mode', lambda: mode)
    ok, msg = v.update_self(restart=True, defer=True, wait=5)
    assert ok is False and text in msg
    assert worker.calls == []


def test_the_pip_worker_is_started_by_python_exe_and_never_pythonw(worker, monkeypatch):
    monkeypatch.setattr(sys, 'executable', 'C:/Py/pythonw.exe')
    assert v.update_self()[0]
    argv = worker.argv
    assert argv[0] == PY and argv[5] == PY
    assert argv[0] != sys.executable
    assert argv[6:] == ['-m', 'pip', 'install', '-U', v.SELF_PKG]


def test_defer_hands_over_our_pid_without_asking_for_a_relaunch(worker):
    ok, _msg = v.update_self(defer=True)
    assert ok
    assert worker.argv[4] == str(os.getpid())
    assert 'ARCHEUS_RELAUNCH' not in worker.env


def test_the_worker_environment_is_a_copy_with_empty_target_and_the_free_list(worker, monkeypatch):
    monkeypatch.setenv('ARCHEUS_CALLER_MARK', 'kept')
    before = dict(os.environ)
    assert v.update_self()[0]
    env = worker.env
    assert env is not os.environ
    assert env['ARCHEUS_UPDATE_TO'] == ''
    assert env['ARCHEUS_CALLER_MARK'] == 'kept'
    assert json.loads(env['ARCHEUS_FREE']) == [SCRIPT]
    assert 'ARCHEUS_UPDATE_TO' not in os.environ
    assert dict(os.environ) == before


def test_restart_keeps_the_arguments_adds_gui_once_and_leaves_argv_alone(worker, monkeypatch):
    monkeypatch.setattr(sys, 'argv', ['archeus', '--tui', 'x'])
    assert v.update_self(restart=True)[0]
    relaunch = json.loads(worker.env['ARCHEUS_RELAUNCH'])
    assert relaunch[3:] == ['--tui', 'x', '--gui']
    assert sys.argv == ['archeus', '--tui', 'x']

    monkeypatch.setattr(sys, 'argv', ['archeus', '--gui'])
    assert v.update_self(restart=True)[0]
    relaunch = json.loads(worker.env['ARCHEUS_RELAUNCH'])
    assert relaunch[3:] == ['--gui']

    monkeypatch.setattr(sys, 'argv', ['archeus'])
    assert v.update_self(restart=True)[0]
    relaunch = json.loads(worker.env['ARCHEUS_RELAUNCH'])
    assert relaunch[3:] == ['--gui']


def test_the_relaunch_runs_sys_executable_not_the_python_exe_worker(worker, monkeypatch):
    monkeypatch.setattr(sys, 'executable', 'C:/Py/pythonw.exe')
    assert v.update_self(restart=True)[0]
    relaunch = json.loads(worker.env['ARCHEUS_RELAUNCH'])
    assert relaunch[0] == 'C:/Py/pythonw.exe'
    assert relaunch[0] != PY


def test_a_spawn_failure_without_a_reason_gets_the_fixed_text(worker):
    worker.process, worker.err = None, ''
    ok, msg = v.update_self()
    assert ok is False and msg == 'could not start the update worker'


@pytest.mark.parametrize('raises, rc, error, expected', [
    (TimeoutError('slow'), None, '', 'Still installing in the background'),
    (None, 1, 'ERROR: boom', 'ERROR: boom'),
    (None, 1, '', 'the install failed'),
])
def test_wait_outcomes_report_what_the_worker_did(worker, monkeypatch, tmp_path, raises, rc, error, expected):
    process = _Process(rc=rc or 0, raises=raises)
    worker.process = process
    monkeypatch.setattr(v, '_last_update_error', lambda: error)
    ok, msg = v.update_self(wait=7)
    assert process.waits == [7]
    assert expected in msg
    if raises is not None:
        assert ok is True
    else:
        assert ok is False
    if expected == 'the install failed':
        assert os.path.join(str(tmp_path), 'archeus-update.log') in msg


def test_restart_and_defer_return_their_own_text_without_waiting(worker):
    process = _Process()
    worker.process = process
    ok, msg = v.update_self(restart=True, wait=30)
    assert ok and msg == 'Installing — archeus will close and come back'
    ok, msg = v.update_self(defer=True, wait=30)
    assert ok and msg == 'Update staged — it installs when you close archeus'
    assert process.waits == []


def test_a_finished_install_names_the_cached_latest_only_when_there_is_one(worker, monkeypatch):
    worker.process = _Process()
    assert v.update_self(wait=5) == (True, 'Installed — restart archeus to use it')

    monkeypatch.setattr(jsonstore, 'load', lambda path, default=None: {'latest': '1.7.0'})
    assert v.update_self(wait=5) == (True, 'Installed 1.7.0 — restart archeus to use it')

    worker.process = _Process()
    assert v.update_self() == (True, 'Installing in the background — restart archeus to use it')
    assert worker.process.waits == []

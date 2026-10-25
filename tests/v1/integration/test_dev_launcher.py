"""tools/v1_env.py, the developer launcher: it orchestrates the real Core and
adds nothing to it. Readiness is discovery plus `/v1/health`, the URL is the one
`archeus core --open` opens, a Core it did not start is never stopped, and the
Core it did start is stopped gracefully, never tree-killed.

The launch path runs against the REAL Core runtime in a child process (the
judge's `CHILD`, on a free port and the fake harness): `archeus core` itself
binds the fixed port 7337, which a test may not take."""

import getpass
import json
import os
import re
import subprocess
import sys
import types

import pytest

from archeus.cli import main as cli
from archeus.infra import discovery
from claude_sessions import proc
from v1.judge.http import CHILD, ROOT, free_port

sys.path.insert(0, os.path.join(ROOT, 'tools'))
import v1_env  # noqa: E402

WINDOWS = sys.platform.startswith('win')
HEALTHY = {'core': {'pid': 1, 'version': 'dev', 'ports': 'real'}, 'armed': True,
           'engine': {'state': 'idle'}, 'world': {'state': 'running', 'pending': 0},
           'exec': {'state': 'idle', 'live': 0}, 'plan': {'state': 'idle', 'pending': 0}}


def _real_core_argv(**cfg):
    return [sys.executable, '-c', CHILD % {'root': ROOT},
            json.dumps(dict(cfg, port=free_port()))]


@pytest.fixture
def no_spawn(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError('the launcher started a process')
    monkeypatch.setattr(subprocess, 'Popen', refuse)


# ── what it starts, and how it decides Core is ready ──

def test_core_is_the_archeus_console_entry_run_from_this_checkout():
    argv = v1_env.core_argv(['phone.example.ts.net'])
    assert argv == [proc.python_exe(), '-u', '-c', 'from claude_sessions.cli import run; run()',
                    'core', '--remote-host', 'phone.example.ts.net']
    from claude_sessions import cli as entry
    assert 'core' in entry.V1_VERBS           # that entry sends `core` to archeus/cli/main.py
    assert v1_env.ROOT == ROOT and os.path.isfile(v1_env.WRAPPER)


def test_ready_means_every_component_running_idle_or_stopped():
    assert v1_env.not_ready(HEALTHY) == [] and v1_env.failed(HEALTHY) == []
    booting = dict(HEALTHY, engine={'state': 'reconciling'}, exec={'state': 'starting'})
    assert v1_env.not_ready(booting) == ['engine reconciling', 'exec starting']
    broken = dict(HEALTHY, world={'state': 'failed'})
    assert v1_env.failed(broken) == ['world'] and v1_env.not_ready(broken) == ['world failed']
    # owner decision (p21-design-gate 4.2, 2026-10-22): a worker the launch did not start is ready
    unstarted = dict(HEALTHY, plan={'state': 'stopped', 'pending': 0},
                     verify={'state': 'stopped', 'pending': 0})
    assert v1_env.not_ready(unstarted) == [] and v1_env.failed(unstarted) == []
    always = dict(HEALTHY, automation={'state': 'stopped', 'pending': 0})
    assert v1_env.not_ready(always) == ['automation stopped']
    dead_engine = dict(HEALTHY, engine={'state': 'stopped'})
    assert v1_env.not_ready(dead_engine) == ['engine stopped']
    crashed = dict(HEALTHY, verify={'state': 'failed', 'pending': 0})
    assert v1_env.failed(crashed) == ['verify'] and v1_env.not_ready(crashed) == ['verify failed']


def test_the_url_opened_is_the_one_archeus_core_open_opens(monkeypatch):
    info = {'pid': 4242, 'port': 7337, 'create_time': 1}
    monkeypatch.setattr(discovery, 'discover', lambda: ('running', info))
    monkeypatch.setattr(cli, '_get', lambda i, m, p, b=None:
                        {'code': 'CODE'} if p == '/v1/devices/launch/code' else None)
    opened = []
    import webbrowser
    monkeypatch.setattr(webbrowser, 'open', opened.append)
    assert cli.core(open_browser=True) == 0
    assert opened == [v1_env.ui_url(info)] == ['http://127.0.0.1:7337/#launch=CODE']


# ── a Core it did not start ──

def test_a_healthy_running_core_is_opened_never_duplicated(monkeypatch, no_spawn, capsys):
    info = {'pid': 4242, 'port': 7337, 'create_time': 1}
    monkeypatch.setattr(discovery, 'discover', lambda: ('running', info))
    monkeypatch.setattr(v1_env, 'read_health', lambda i: HEALTHY)
    monkeypatch.setattr(cli, '_launch_code', lambda i: 'CODE')
    opened = []
    assert v1_env.main([], opener=opened.append) == 0
    assert opened == ['http://127.0.0.1:7337/#launch=CODE']
    assert 'will not stop it' in capsys.readouterr().out


@pytest.mark.parametrize('state,health', [('unreadable', None), ('running', None)])
def test_a_core_it_cannot_talk_to_gets_nothing_started_and_nothing_opened(
        monkeypatch, no_spawn, state, health):
    monkeypatch.setattr(discovery, 'discover',
                        lambda: (state, {'pid': 4242, 'port': 7337, 'create_time': 1}))
    monkeypatch.setattr(v1_env, 'read_health', lambda i: health)
    opened = []
    assert v1_env.main([], opener=opened.append) == 2
    assert opened == []


def test_an_unbuilt_app_is_not_launched(monkeypatch, no_spawn, tmp_path, capsys):
    monkeypatch.setattr(v1_env, 'STATIC_INDEX', str(tmp_path / 'missing' / 'index.html'))
    assert v1_env.main(['--no-browser']) == 2
    assert 'npm run build' in capsys.readouterr().out


# ── the Core it starts: the real runtime ──

def test_it_waits_for_health_opens_after_it_and_a_ctrl_c_stops_core_cleanly(monkeypatch,
                                                                            capsys):
    argv = _real_core_argv()
    monkeypatch.setattr(v1_env, 'core_argv', lambda hosts=(): argv)
    # CI's test job does not build the SPA; the unbuilt case has its own test
    monkeypatch.setattr(v1_env, 'spa_problem', lambda: (None, None))
    events = []

    def opener(url):
        info = discovery.discover()[1]
        assert v1_env.not_ready(v1_env.read_health(info)) == []      # healthy BEFORE the open
        events.append(url)

    def ctrl_c(self, poll_s=v1_env.POLL_S):
        events.append(('running', self.child.pid))
        raise KeyboardInterrupt
    monkeypatch.setattr(v1_env.Env, 'run', ctrl_c)
    assert v1_env.main(['--timeout', '60'], opener=opener) == 0
    port = json.loads(argv[-1])['port']
    assert re.fullmatch(r'http://127\.0\.0\.1:%d/#launch=\S+' % port, events[0])
    pid = events[1][1]
    out = capsys.readouterr().out
    at = [out.find(s) for s in ('STARTING', 'HEALTHY', 'opened the app', 'STOPPING',
                                'STOPPED: Core exited 0')]
    assert -1 not in at and at == sorted(at), out
    assert discovery.discover()[0] == 'not_running'
    assert not proc.pid_alive(pid)


def test_a_core_still_reconciling_is_up_but_not_ready(tmp_path, capsys):
    gate = str(tmp_path / 'sweep-may-run')
    env = v1_env.Env(_real_core_argv(hold_sweep=gate), echo=False).start()
    try:
        assert env.wait_healthy(3) is False                 # HTTP answers; the engine does not
        assert 'still: engine reconciling' in capsys.readouterr().out
        assert discovery.discover()[1]['pid'] == env.child.pid
        open(gate, 'w').close()
        assert env.wait_healthy(60) and env.state == 'HEALTHY'
    finally:
        env.stop()


def test_a_core_that_dies_while_running_is_reported_with_its_logs(capsys):
    env = v1_env.Env(_real_core_argv(), echo=False).start()
    try:
        assert env.wait_healthy(60)
        env.child.kill()                        # Core dies under the launcher
        code = env.run(poll_s=0.1)
        env._exited()
    finally:
        env.stop()
    assert code != 0 and env.state == 'FAILED'
    out = capsys.readouterr().out
    assert 'FAILED: Core exited %s (killed or crashed)' % code in out and env.log_path in out
    assert os.path.dirname(env.log_path) == os.path.join(os.environ['ARCHEUS_HOME'], 'logs')


def test_the_watch_loop_never_blocks_in_a_timed_wait(monkeypatch):
    """A Ctrl+C that arrives inside Popen.wait(timeout) on Windows is raised only
    once the wait times out, and CPython 3.10's KeyboardInterrupt branch then
    waits min(0.25, remaining) — negative, which WaitForSingleObject reads as
    INFINITE: the launcher hung until Core exited on its own (found by hand)."""
    env = v1_env.Env(_real_core_argv(), echo=False).start()
    try:
        assert env.wait_healthy(60)
        real = env.child.wait

        def wait(timeout=None):
            raise AssertionError('the watch loop blocked in wait(%r)' % timeout)
        monkeypatch.setattr(env.child, 'wait', wait)
        slept = []

        def sleep(s):
            slept.append(s)
            if len(slept) == 3:                 # Core dies while it is watched
                env.child.kill()
                real(10)
        monkeypatch.setattr(v1_env, 'time', types.SimpleNamespace(sleep=sleep))
        assert env.run(poll_s=0.05) != 0
        assert slept[:3] == [0.05] * 3
    finally:
        monkeypatch.undo()
        env.stop()


def test_a_core_that_exits_at_start_fails_the_launch_and_says_why(capsys):
    env = v1_env.Env([sys.executable, '-c', 'import sys; print("port in use"); sys.exit(2)'],
                     echo=False).start()
    assert env.wait_healthy(30) is False and env.state == 'FAILED'
    assert v1_env.EXIT_MEANING[2] in capsys.readouterr().out
    with open(env.log_path, encoding='utf-8') as f:
        assert 'port in use' in f.read()                # its output is kept


def test_a_core_that_never_becomes_healthy_times_out_and_is_stopped(capsys):
    env = v1_env.Env([sys.executable, '-c', 'import time; time.sleep(120)'], echo=False).start()
    try:
        assert env.wait_healthy(1.5) is False and env.state == 'FAILED'
        assert 'not healthy after' in capsys.readouterr().out
    finally:
        env.stop(wait_s=10)
    assert env.child.poll() is not None and not proc.pid_alive(env.child.pid)


def test_stopping_is_cores_own_signal_and_never_a_tree_kill():
    src = open(v1_env.__file__, encoding='utf-8').read()
    assert 'kill_tree' not in src and 'kill_pid_tree' not in src and 'taskkill' not in src
    assert 'CTRL_BREAK_EVENT' in src and 'SIGTERM' in src


# ── nothing about this machine is written down ──

def test_the_launcher_and_its_wrapper_name_no_machine_path():
    me = getpass.getuser()
    for rel in ('tools/v1_env.py', 'tools/archeus-v1.bat'):
        with open(os.path.join(ROOT, rel), encoding='utf-8') as f:
            text = f.read()
        assert not re.search(r'\b[A-Za-z]:[\\/]', text), rel
        assert not re.search(r'\b%s\b' % re.escape(me), text, re.I), rel
        assert 'LOCALAPPDATA' not in text and 'Desktop\\' not in text, rel
    with open(os.path.join(ROOT, 'tools', 'archeus-v1.bat'), encoding='utf-8') as f:
        bat = f.read()
    assert '%~dp0' in bat and 'v1_env.py' in bat


def test_the_shortcut_asks_windows_for_the_desktop_and_points_at_this_checkout():
    script = v1_env.shortcut_script('install')
    assert "[Environment]::GetFolderPath('Desktop')" in script and "'Archeus V1.lnk'" in script
    assert "$s.TargetPath = '%s'" % v1_env.WRAPPER in script
    assert "$s.WorkingDirectory = '%s'" % ROOT in script
    odd = v1_env.shortcut_script('install', wrapper=os.path.join("o'brien", 'tools', 'x.bat'))
    assert "'%s'" % os.path.join("o''brien", 'tools', 'x.bat') in odd       # quoted, not broken
    assert 'Remove-Item -LiteralPath $p' in v1_env.shortcut_script('remove')


def test_making_the_shortcut_runs_one_powershell_and_touches_no_desktop(monkeypatch):
    calls = []

    def run(argv, **kw):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout='<desktop>\\Archeus V1.lnk\n',
                                           stderr='')
    monkeypatch.setattr(v1_env, 'WINDOWS', True)
    assert v1_env.shortcut('install', run=run) == 0
    assert calls == [['powershell', '-NoProfile', '-NonInteractive', '-Command',
                      v1_env.shortcut_script('install')]]
    monkeypatch.setattr(v1_env, 'WINDOWS', False)
    assert v1_env.shortcut('install', run=run) == 2 and len(calls) == 1

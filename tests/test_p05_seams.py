"""P0.5 seams of the Archeus V1 plan (docs/architecture/ARCHEUS_V1_REARCHITECTURE_PLAN.md
§31.1 P0.5; migration-plan §3): the UI-free headless runner, the process-control
primitives, and the hook environment guard. No test here starts a real model:
every child process is `sys.executable`."""
import io
import json
import os
import subprocess
import sys
import threading
import time

import pytest

from claude_sessions import gui_api, llmcall, memory, proc

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG = os.path.join(ROOT, 'claude_sessions')
UI_MODULES = ('claude_sessions.ui', 'claude_sessions.gui_api',
              'claude_sessions.main', 'claude_sessions.gui')


def _py(code, **kw):
    return subprocess.run([sys.executable, '-c', code], capture_output=True,
                          text=True, timeout=60, cwd=ROOT, **kw)


def _wait_dead(pid, secs=10):
    end = time.time() + secs
    while time.time() < end:
        if proc.pid_alive(pid) is False:
            return True
        time.sleep(0.1)
    return False


# ── seam 1: the headless runner ─────────────────────────────────────────

def test_the_runner_and_proc_import_no_ui():
    """The point of the seam: V1's Core imports these, and importing gui_api
    would run `_install_bridge()` and monkeypatch the terminal UI in that
    process. Checked in a fresh interpreter, after actually using the builder
    (its lazy import of `sessions` must not drag the UI in either)."""
    r = _py("import sys, claude_sessions.llmcall as L, claude_sessions.proc\n"
            "L.build_headless_args('claude', 'hi')\n"
            "print([m for m in %r if m in sys.modules])" % (UI_MODULES,))
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == '[]', r.stdout


def test_build_headless_args_is_the_argv_memory_always_sent():
    from claude_sessions.sessions import HEADLESS_MARK
    args, stdin = llmcall.build_headless_args(
        'claude', 'do it', 'm1', ['--max-budget-usd', '2'], ('--output-format', 'json'))
    assert args == ['claude', '-p', '--max-turns', '20', '--disallowedTools',
                    'Write,Edit,NotebookEdit,Bash', '--model', 'm1',
                    '--max-budget-usd', '2', '--output-format', 'json']
    assert stdin == 'do it\n\n' + HEADLESS_MARK
    args, _ = llmcall.build_headless_args('claude', None)
    assert '--model' not in args


def test_memory_headless_call_routes_through_the_seam(monkeypatch):
    """memory._claude_stdin on the silent path: same argv as before the move,
    prompt still marked, and still delivered through gui_api._run_cancellable
    (which is where a dozen legacy tests intercept it)."""
    from claude_sessions import config
    from claude_sessions.sessions import HEADLESS_MARK
    seen = {}

    def fake(args, **kw):
        seen['args'], seen['kw'] = args, kw
        return 'ok'

    monkeypatch.setattr(config, 'get_claude_exe', lambda: 'claude.exe')
    monkeypatch.setattr(memory, '_provider_headless', lambda m: (None, m))
    monkeypatch.setattr(memory, '_budget_args', lambda: ['--max-budget-usd', '1'])
    monkeypatch.setattr(gui_api, '_run_cancellable', fake)
    monkeypatch.setattr(memory._tls, 'silent', True, raising=False)
    calls = []
    real = llmcall.build_headless_args
    monkeypatch.setattr(llmcall, 'build_headless_args',
                        lambda *a, **k: calls.append(a) or real(*a, **k))
    assert memory._claude_stdin('P', '/cwd', model='mx', extra_args=('--x',)) == 'ok'
    assert calls, 'memory must build its argv through llmcall'
    assert seen['args'] == ['claude.exe', '-p', '--max-turns', '20', '--disallowedTools',
                            'Write,Edit,NotebookEdit,Bash', '--model', 'mx',
                            '--max-budget-usd', '1', '--x']
    assert seen['kw']['input_text'] == 'P\n\n' + HEADLESS_MARK


def test_another_harness_builds_its_argv_through_the_seam_too(monkeypatch):
    """ADR-0022: an own call on a non-Claude harness is still one seam. Its argv
    comes from the harness descriptor via llmcall, in its own vocabulary: no
    Claude model id, budget or schema flag crosses over."""
    from claude_sessions import config, harnesses
    from claude_sessions.sessions import HEADLESS_MARK
    seen = {}
    monkeypatch.setattr(memory, 'headless_harness', lambda: 'pi')
    monkeypatch.setattr(harnesses, 'exe', lambda hid=None: 'pi.exe')
    monkeypatch.setattr(config, 'load_settings',
                        lambda: {'headless_harness_model': 'spark/qwen3.8'})
    monkeypatch.setattr(gui_api, '_run_cancellable',
                        lambda args, **kw: seen.update(args=args, kw=kw) or 'ok')
    monkeypatch.setattr(memory._tls, 'silent', True, raising=False)
    calls = []
    real = llmcall.build_headless_args
    monkeypatch.setattr(llmcall, 'build_headless_args',
                        lambda *a, **k: calls.append(k) or real(*a, **k))
    assert memory._claude_stdin('P', '/cwd', model='claude-haiku-4-5',
                                extra_args=('--json-schema', '{}')) == 'ok'
    assert calls == [{'harness': 'pi'}]
    assert seen['args'] == ['pi.exe', '-p', '--no-session', '--tools', 'read,grep,find,ls',
                            '--model', 'spark/qwen3.8']
    assert seen['kw']['input_text'] == 'P\n\n' + HEADLESS_MARK


def test_run_headless_success_and_failure_records(monkeypatch):
    noted, recorded = [], []
    from claude_sessions import events, quota
    monkeypatch.setattr(quota, 'note_failure', lambda *a: noted.append(a))
    monkeypatch.setattr(events, 'record', lambda *a, **k: recorded.append((a, k)))

    ok = llmcall.run_headless([sys.executable, '-c',
                               'import sys; print(sys.stdin.read().upper())'], 'abc')
    assert ok == (0, 'ABC', '', '', False)
    assert not noted and not recorded

    envelope = json.dumps({'result': "You've hit your session limit"})
    bad = llmcall.run_headless([sys.executable, '-c',
                                'import sys; print(%r); sys.exit(3)' % envelope])
    assert bad.returncode == 3 and not bad.timed_out
    assert bad.reason == "You've hit your session limit"
    assert bad.error == "claude exited 3: You've hit your session limit"
    assert noted and noted[0][2] == envelope          # the full envelope, not the sentence
    assert recorded[0][0] == ('subprocess', bad.error)


def test_run_headless_timeout_and_spawn_failure(monkeypatch):
    from claude_sessions import events
    recorded = []
    monkeypatch.setattr(events, 'record', lambda *a, **k: recorded.append(a))
    r = llmcall.run_headless([sys.executable, '-c', 'import time; time.sleep(30)'],
                             timeout=0.5)
    assert r.returncode is None and r.timed_out and 'timed out' in r.error
    assert recorded and recorded[0][0] == 'subprocess'
    r = llmcall.run_headless([os.path.join(ROOT, 'no-such-executable-xyz')])
    assert r.returncode is None and not r.timed_out and r.error


def test_run_headless_cancel_kills_the_process():
    cancel = threading.Event()
    spawned = []
    out = {}

    def go():
        out['r'] = llmcall.run_headless(
            [sys.executable, '-c', 'import time; time.sleep(60)'],
            cancel=cancel, on_spawn=spawned.append, timeout=120)

    t = threading.Thread(target=go)
    t.start()
    for _ in range(100):
        if spawned:
            break
        time.sleep(0.05)
    assert spawned
    cancel.set()
    t.join(timeout=20)
    assert not t.is_alive(), 'cancel did not stop the call'
    assert out['r'].returncode != 0
    assert _wait_dead(spawned[0].pid)


def test_the_job_runner_delegates_and_keeps_its_contract(monkeypatch):
    """gui_api._run_cancellable is a wrapper now: the process runs in llmcall,
    the job bookkeeping stays here."""
    from claude_sessions import quota
    monkeypatch.setattr(quota, 'preflight', lambda cmd, env: (env, False))
    calls = []

    def fake(cmd, input_text=None, **kw):
        calls.append(kw)
        kw['on_spawn'](object())
        return llmcall.Result(5, 'raw', 'why', 'claude exited 5: why', False)

    monkeypatch.setattr(llmcall, 'run_headless', fake)
    job = {'cancel_event': threading.Event(), 'procs': []}
    gui_api._JOBCTX.job = job
    try:
        assert gui_api._run_cancellable(['claude'], input_text='x') == ''
    finally:
        gui_api._JOBCTX.job = None
    assert calls and calls[0]['cancel'] is job['cancel_event']
    assert job['last_subprocess_error'] == {'code': 5, 'output': 'why'}
    assert memory.last_call_error == 'claude exited 5: why'
    assert job['procs'] == []                  # tracked while running, removed after


def test_the_job_runner_still_raises_on_cancel(monkeypatch):
    from claude_sessions import quota
    monkeypatch.setattr(quota, 'preflight', lambda cmd, env: (env, False))
    job = {'cancel_event': threading.Event(), 'procs': []}

    def fake(cmd, input_text=None, **kw):
        job['cancel_event'].set()
        return llmcall.Result(None, '', '', 'killed', False)

    monkeypatch.setattr(llmcall, 'run_headless', fake)
    gui_api._JOBCTX.job = job
    try:
        with pytest.raises(gui_api.JobCancelled):
            gui_api._run_cancellable(['claude'])
    finally:
        gui_api._JOBCTX.job = None


# ── seam 2: process control ─────────────────────────────────────────────

def test_create_time_names_one_process():
    me = proc.process_create_time(os.getpid())
    assert me is not None and me == proc.process_create_time(os.getpid())
    p = subprocess.Popen([sys.executable, '-c', 'pass'])
    p.wait()
    assert proc.process_create_time(p.pid) is None       # exited: nothing to match
    assert proc.process_create_time(0) is None
    assert proc.process_create_time('x') is None


@pytest.mark.skipif(sys.platform != 'darwin', reason='the libproc start time is macOS-only')
def test_two_processes_started_in_the_same_second_have_different_create_times():
    """`ps -o lstart` read whole seconds, so on macOS a stranger started in
    the same second as the orphan whose pid it now holds looked like it — and
    was killed. The libproc start time is in microseconds."""
    for _ in range(10):
        a, b = (subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])
                for _ in range(2))
        try:
            ca, cb = proc.process_create_time(a.pid), proc.process_create_time(b.pid)
            assert isinstance(ca, int) and isinstance(cb, int), (ca, cb)
            assert abs(ca / 1e6 - time.time()) < 60          # microseconds since the epoch
            assert proc.process_create_time(a.pid) == ca     # stable across readings
            if ca // 1000000 == cb // 1000000:
                assert ca != cb
                return
        finally:
            for p in (a, b):
                p.kill()
                p.wait()
    pytest.fail('no two processes started within one second in ten tries')


def test_kill_pid_tree_refuses_a_mismatch_and_kills_a_match(tmp_path):
    """A recorded (pid, create time) only kills the process it recorded — and
    then the whole tree, including a grandchild."""
    marker = tmp_path / 'grandchild.pid'
    code = ('import subprocess, sys, time\n'
            'g = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])\n'
            'open(%r, "w").write(str(g.pid))\n'
            'time.sleep(60)\n' % str(marker))
    child, err = proc.spawn_detached([sys.executable, '-c', code])
    assert child, err
    try:
        for _ in range(100):
            if marker.exists() and marker.read_text():
                break
            time.sleep(0.05)
        grandchild = int(marker.read_text())
        ct = proc.process_create_time(child.pid)
        assert ct is not None
        # refused: no create time, a wrong one — and the process survives
        assert proc.kill_pid_tree(child.pid, None) is False
        wrong = ct + 1 if isinstance(ct, int) else ct + 'x'
        assert proc.kill_pid_tree(child.pid, wrong) is False
        assert proc.pid_alive(child.pid) is True
        # matched: the tree goes
        assert proc.kill_pid_tree(child.pid, ct) is True
        assert _wait_dead(child.pid)
        assert _wait_dead(grandchild)
    finally:
        proc.kill_tree(child)


def test_kill_pid_tree_refuses_a_dead_pid():
    p = subprocess.Popen([sys.executable, '-c', 'pass'])
    p.wait()
    assert proc.kill_pid_tree(p.pid, 12345) is False


def test_spawn_detached_stdin_path(tmp_path):
    src = tmp_path / 'prompt.txt'
    src.write_text('hello from the file', encoding='utf-8')
    log = tmp_path / 'out.log'
    code = 'import sys; sys.stdout.write("<" + sys.stdin.read() + ">")'
    child, err = proc.spawn_detached([sys.executable, '-c', code],
                                     log=str(log), stdin_path=str(src))
    assert child, err
    child.wait(timeout=30)
    for _ in range(50):                       # the parent's log handle is lazy
        if log.exists() and log.read_text():
            break
        time.sleep(0.05)
    assert log.read_text(encoding='utf-8') == '<hello from the file>'


def test_spawn_detached_default_stdin_is_unchanged(tmp_path):
    """Existing callers pass no stdin_path: the child still gets an empty stdin."""
    log = tmp_path / 'out.log'
    child, err = proc.spawn_detached(
        [sys.executable, '-c', 'import sys; sys.stdout.write(repr(sys.stdin.read()))'],
        log=str(log))
    assert child, err
    child.wait(timeout=30)
    for _ in range(50):
        if log.exists() and log.read_text():
            break
        time.sleep(0.05)
    assert log.read_text() == "''"


def test_spawn_detached_missing_stdin_file(tmp_path):
    child, err = proc.spawn_detached([sys.executable, '-c', 'pass'],
                                     stdin_path=str(tmp_path / 'absent.txt'))
    assert child is None and err


# ── seam 3: hook environment guard ──────────────────────────────────────

GUARDED = ('recall_hook', 'worklog_hook', 'memdirty_hook')


class _Payload(io.StringIO):
    """Records whether the hook touched its payload. Recording, not raising:
    every hook wraps its read in `except Exception`, which would swallow an
    assertion and let a hook with no guard pass."""
    def __init__(self, text):
        super().__init__(text)
        self.touched = False

    def read(self, *a):
        self.touched = True
        return super().read(*a)


@pytest.mark.parametrize('name', GUARDED)
def test_guarded_hooks_stand_down_inside_an_archeus_execution(name, monkeypatch, capsys):
    """Stand down means before anything else: the payload is never read."""
    import importlib
    mod = importlib.import_module('claude_sessions.' + name)
    payload = _Payload(json.dumps({'hook_event_name': 'SessionStart', 'cwd': os.getcwd()}))
    monkeypatch.setenv('ARCHEUS_EXECUTION_ID', 'exe_TEST')
    monkeypatch.setattr(sys, 'stdin', payload)
    assert mod.main() == 0
    assert not payload.touched
    assert capsys.readouterr().out == ''


def _run_script(name, payload, env_extra):
    env = {k: v for k, v in os.environ.items() if k != 'ARCHEUS_EXECUTION_ID'}
    env.update(env_extra)
    return subprocess.run([sys.executable, os.path.join(PKG, name + '.py')],
                          input=json.dumps(payload), capture_output=True,
                          text=True, timeout=60, env=env)


def test_recall_hook_paired(tmp_path):
    """Same payload, same project: context without the variable, nothing with it."""
    from test_recall_hook import _graph
    proj = tmp_path / 'proj'
    (proj / '.archeus' / 'memory').mkdir(parents=True)
    (proj / '.archeus' / 'memory' / 'graph.json').write_text(json.dumps(_graph()),
                                                             encoding='utf-8')
    home = tmp_path / 'home'
    (home / '.claude').mkdir(parents=True)
    (home / '.claude' / 'archeus.json').write_text(
        json.dumps({'memory_prompt_hook': True, 'memory_budget': 600}), encoding='utf-8')
    payload = {'hook_event_name': 'UserPromptSubmit', 'cwd': str(proj),
               'prompt': 'fix the usage limits parser'}
    legacy = _run_script('recall_hook', payload, {'USERPROFILE': str(home), 'HOME': str(home)})
    assert legacy.returncode == 0
    assert 'UsageParser' in legacy.stdout
    v1 = _run_script('recall_hook', payload, {'USERPROFILE': str(home), 'HOME': str(home),
                                              'ARCHEUS_EXECUTION_ID': 'exe_TEST'})
    assert v1.returncode == 0 and v1.stdout == ''


def test_memdirty_hook_paired(tmp_path):
    proj = tmp_path / 'proj'
    proj.mkdir()
    payload = {'hook_event_name': 'PostToolUse', 'cwd': str(proj),
               'tool_input': {'file_path': str(proj / 'a.py')}}
    log = memory.dirty_log_path(str(proj))
    v1 = _run_script('memdirty_hook', payload, {'ARCHEUS_EXECUTION_ID': 'exe_TEST'})
    assert v1.returncode == 0 and not os.path.exists(log)
    legacy = _run_script('memdirty_hook', payload, {})
    assert legacy.returncode == 0
    with open(log, encoding='utf-8') as f:
        assert os.path.abspath(str(proj / 'a.py')) in f.read()


def test_limit_hook_keeps_the_latch_and_skips_rotation_in_an_execution(monkeypatch, tmp_path):
    from claude_sessions import limit_hook, quota, rotate
    latched, offered = [], []
    monkeypatch.setattr(quota, 'note_limit', lambda *a, **k: latched.append(k))
    monkeypatch.setattr(rotate, 'offer', lambda *a, **k: offered.append(a))
    data = {'cwd': str(tmp_path), 'session_id': 'S1', 'transcript_path': ''}

    monkeypatch.delenv('ARCHEUS_EXECUTION_ID', raising=False)
    assert limit_hook.handle(data) == {'terminalSequence': limit_hook.BELL}
    assert len(latched) == 1 and len(offered) == 1          # legacy: both

    monkeypatch.setenv('ARCHEUS_EXECUTION_ID', 'exe_TEST')
    assert limit_hook.handle(data) == {'terminalSequence': limit_hook.BELL}
    assert len(latched) == 2 and len(offered) == 1          # V1: latch only


def test_every_guard_names_the_same_variable():
    """Four copies of one string is a place for one to drift; this is its
    single definition check."""
    for name in GUARDED + ('limit_hook',):
        with open(os.path.join(PKG, name + '.py'), encoding='utf-8') as f:
            assert "os.environ.get('ARCHEUS_EXECUTION_ID')" in f.read(), name

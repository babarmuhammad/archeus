"""Developer tooling, not part of Archeus: run the local V1 environment for
manual testing, open its app once Core is healthy, and stop Core cleanly.

    py tools/v1_env.py [--no-browser] [--remote-host H]... [--timeout S]
    py tools/v1_env.py --install-shortcut | --remove-shortcut      (Windows)

`tools/archeus-v1.bat` is the double-click wrapper; the runbook is
notes/v1-local-environment.md.

The environment is ONE process, Core: `archeus core` run through the console
script's own entry (`claude_sessions.cli:run`) from this checkout. It hosts the
API, the SSE streams and the built SPA on 127.0.0.1:7337; the CLI, the TUI and
the browser are its clients. This file adds nothing to Core and changes nothing
it does:

- readiness is what the judge's `wait_ready` and `archeus status` already read:
  discovery reports `running` for THIS child's pid, and `/v1/health` (with the
  local token, as `status` sends it) answers with every component running or
  idle;
- the app URL is the one `archeus core --open` opens for a running Core: a
  launch code in the fragment, from `/v1/devices/launch/code`;
- stopping is the signal `archeus core` already handles (CTRL_BREAK on Windows,
  SIGTERM elsewhere), and a kill, when Core will not stop, is of Core's own
  process only. Never a tree kill: executions are detached on purpose and the
  next Core adopts or reconciles them (P11), so killing them would be the
  launcher deciding something Core owns.

A Core this launcher did not start is never stopped by it: it opens that
Core's app and leaves.
"""

import argparse
import os
import signal
import subprocess
import sys
import threading
import time
import webbrowser

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from archeus.cli import main as cli  # noqa: E402
from archeus.infra import discovery, paths  # noqa: E402
from claude_sessions import proc  # noqa: E402

WINDOWS = sys.platform.startswith('win')
ENTRY = 'from claude_sessions.cli import run; run()'
STATIC_INDEX = os.path.join(ROOT, 'archeus', 'api', 'static', 'index.html')
SPA_SRC = os.path.join(ROOT, 'clients', 'app', 'src')
WRAPPER = os.path.join(ROOT, 'tools', 'archeus-v1.bat')
SHORTCUT = 'Archeus V1.lnk'
#: `runtime.run`'s exit codes
EXIT_MEANING = {0: 'stopped cleanly',
                1: 'another Core holds this home, or Core refused to start',
                2: 'its port is in use by another program',
                3: 'the engine or a worker thread failed'}
READY_STATES = ('running', 'idle')
#: workers a launch may leave unstarted (their port is wired elsewhere): stopped is ready for them only
UNWIRED = ('plan', 'verify')
POLL_S = 2.0
STOP_WAIT_S = 30.0


def say(msg):
    print('[archeus-v1] %s' % msg, flush=True)


def core_argv(remote_hosts=()):
    argv = [proc.python_exe(), '-u', '-c', ENTRY, 'core']
    for h in remote_hosts:
        argv += ['--remote-host', h]
    return argv


def components(health):
    """{name: state} of every component `/v1/health` reports a state for."""
    return {k: v['state'] for k, v in health.items() if isinstance(v, dict) and 'state' in v}


def not_ready(health):
    return sorted('%s %s' % (k, s) for k, s in components(health).items()
                  if s not in READY_STATES and not (s == 'stopped' and k in UNWIRED))


def failed(health):
    return sorted(k for k, s in components(health).items() if s == 'failed')


def read_health(info):
    return cli._get(info, 'GET', '/v1/health')


def ui_url(info):
    """The URL `archeus core --open` opens for a running Core, or None."""
    code = cli._launch_code(info)
    return None if code is None else 'http://127.0.0.1:%d/#launch=%s' % (info['port'], code)


def open_ui(info, opener=webbrowser.open):
    url = ui_url(info)
    if url is None:
        return False
    opener(url)
    say('opened the app: http://127.0.0.1:%d (sign-in code in the link, used once)'
        % info['port'])
    return True


def spa_problem():
    """Why the built app cannot be served as it stands (None: it can), and a
    warning when the build is older than its sources."""
    if not os.path.isfile(STATIC_INDEX):
        return 'the app is not built: run `npm ci` then `npm run build` in clients/app', None
    built = os.path.getmtime(STATIC_INDEX)
    newest = max((os.path.getmtime(os.path.join(d, f))
                  for d, _s, fs in os.walk(SPA_SRC) for f in fs), default=0)
    if newest > built:
        return None, ('the app build is older than clients/app/src: run `npm run build` '
                      'in clients/app to test the current sources')
    return None, None


class Env:
    """The one child this launcher starts, and its lifecycle:
    STARTING -> HEALTHY -> RUNNING -> STOPPING -> STOPPED (or FAILED)."""

    def __init__(self, argv=None, *, log_path=None, echo=True):
        self.argv = argv or core_argv()
        self.log_path = log_path or os.path.join(paths.archeus_home(), 'logs',
                                                 'dev-core-output.log')
        self.echo, self.child, self.info, self.state = echo, None, None, None
        self._tail_stop, self._tailer = threading.Event(), None

    def _to(self, state, detail=''):
        self.state = state
        say(state + (': ' + detail if detail else ''))

    def start(self):
        self._to('STARTING', 'archeus core, from %s' % ROOT)
        os.makedirs(os.path.dirname(self.log_path), exist_ok=True)
        kw = ({'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP} if WINDOWS
              else {'start_new_session': True})
        # the output goes to a FILE, never a pipe: Core must not block, or die
        # on a broken pipe, because this window closed
        with open(self.log_path, 'wb') as out:
            # UTF-8 because the output is read back as UTF-8: a file stdout is
            # otherwise the locale codepage, and Core prints an em dash
            self.child = subprocess.Popen(self.argv, cwd=ROOT, stdin=subprocess.DEVNULL,
                                          stdout=out, stderr=subprocess.STDOUT,
                                          env=dict(os.environ, PYTHONIOENCODING='utf-8'), **kw)
        if self.echo:
            self._tailer = threading.Thread(target=self._tail, daemon=True)
            self._tailer.start()
        return self

    def _tail(self):
        with open(self.log_path, encoding='utf-8', errors='replace') as f:
            while True:
                line = f.readline()
                if line:
                    print('  core | ' + line.rstrip('\n'), flush=True)
                elif self._tail_stop.is_set():
                    return
                else:
                    time.sleep(0.1)

    def wait_healthy(self, timeout=60.0, poll_s=0.1):
        """True once Core is discoverable as this child and every component is
        running, idle or stopped; False (and why) if it exits, fails or runs out of time."""
        deadline, last = time.monotonic() + timeout, None
        while time.monotonic() < deadline:
            if self.child.poll() is not None:
                self._exited()
                return False
            state, info = discovery.discover()
            if state == 'running' and info['pid'] == self.child.pid:
                h = read_health(info)
                if h is not None:
                    if failed(h):
                        self._to('FAILED', 'unhealthy at start: %s' % ', '.join(failed(h)))
                        return False
                    last = not_ready(h)
                    if not last:
                        self.info = info
                        self._to('HEALTHY', 'pid %d, port %d, version %s, %s ports, %s' % (
                            info['pid'], info['port'], h['core']['version'],
                            h['core']['ports'], 'armed' if h.get('armed') else
                            'DISARMED (an e-stop is in force; re-arm from a device)'))
                        return True
            time.sleep(poll_s)
        self._to('FAILED', 'not healthy after %ds%s' % (
            timeout, ' (still: %s)' % ', '.join(last) if last else ''))
        return False

    def run(self, poll_s=POLL_S):
        """Watch Core until it exits (its exit code) or Ctrl+C
        (KeyboardInterrupt, to the caller)."""
        self._to('RUNNING', 'Ctrl+C here stops Core; logs: %s' % self.log_path)
        unhealthy = None
        while True:
            # sleep + poll, never wait(timeout): on Windows (CPython 3.10) a Ctrl+C
            # lands only once that wait has timed out, and its KeyboardInterrupt
            # branch then waits min(0.25, remaining) — negative, i.e. INFINITE
            time.sleep(poll_s)
            if self.child.poll() is not None:
                return self.child.returncode
            h = read_health(self.info)
            now = ('/v1/health did not answer' if h is None
                   else 'failed: %s' % ', '.join(failed(h)) if failed(h) else None)
            if now != unhealthy and self.child.poll() is None:
                self._to('UNHEALTHY' if now else 'HEALTHY', now or 'again')
                unhealthy = now

    def _exited(self):
        self._tail_stop.set()               # Core's last words print before the verdict
        if self._tailer is not None:
            self._tailer.join(2)
        code = self.child.returncode
        # 1 and 2 are start refusals; once healthy, Core itself ends only 0 or 3,
        # and a killed process ends 1 on Windows — not "another Core holds this home"
        meaning = EXIT_MEANING.get(code) if self.info is None or code in (0, 3) else None
        self._to('STOPPED' if code == 0 else 'FAILED', 'Core exited %s (%s)' % (
            code, meaning or 'killed or crashed'))
        if code:
            say('its output: %s' % self.log_path)
            say('its log:    %s' % os.path.join(paths.archeus_home(), 'logs', 'core.log'))

    def stop(self, wait_s=STOP_WAIT_S):
        """Stop the child, gracefully first; Core's own process only."""
        if self.child is None:
            return None
        if self.child.poll() is None:
            self._to('STOPPING')
            try:
                self.child.send_signal(signal.CTRL_BREAK_EVENT if WINDOWS else signal.SIGTERM)
            except OSError:
                pass
            try:
                self.child.wait(wait_s)
            except subprocess.TimeoutExpired:
                say('Core did not stop in %ds: killing Core (its own process only; a running '
                    'execution is left for the next Core to adopt)' % wait_s)
                self.child.kill()
                self.child.wait(10)
            self._exited()
        self._tail_stop.set()
        if discovery.lock_is_held():
            say('warning: this home is still locked by another process')
        return self.child.returncode


def attach(state, info, *, browser=True, opener=webbrowser.open):
    """A Core this launcher did not start: open its app, never stop it."""
    if state == 'unreadable':
        say('a Core holds this home but its discovery file is unreadable (%s); nothing was '
            'started and nothing was sent to it' % discovery.core_json_path())
        return 2
    h = read_health(info)
    if h is None:
        say('a Core is running (pid %d, port %d) but /v1/health did not answer'
            % (info['pid'], info['port']))
        return 2
    say('ALREADY RUNNING: pid %d, port %d%s. This launcher did not start it and will not '
        'stop it; stop it where it was started.' % (
            info['pid'], info['port'],
            ' (unhealthy: %s)' % ', '.join(failed(h)) if failed(h) else ''))
    if browser and not open_ui(info, opener):
        return 2
    return 0


def main(argv=None, *, opener=webbrowser.open):
    ap = argparse.ArgumentParser(
        prog='tools/v1_env.py', description='Developer tooling, not part of Archeus: run the '
        'local V1 environment (Core) for manual testing and open its app once it is healthy. '
        'Runbook: notes/v1-local-environment.md')
    ap.add_argument('--no-browser', action='store_true', help='do not open the app')
    ap.add_argument('--remote-host', action='append', default=[], metavar='H',
                    help='passed to `archeus core --remote-host` (a tunnel you set up)')
    ap.add_argument('--timeout', type=float, default=60.0, help='seconds to become healthy')
    ap.add_argument('--install-shortcut', action='store_true',
                    help='put an "Archeus V1" shortcut to this checkout on the desktop')
    ap.add_argument('--remove-shortcut', action='store_true', help='remove that shortcut')
    a = ap.parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    if a.install_shortcut or a.remove_shortcut:
        return shortcut('install' if a.install_shortcut else 'remove')
    say('developer environment (tools/v1_env.py); ARCHEUS_HOME %s' % paths.archeus_home())
    state, info = discovery.discover()
    if state != 'not_running':
        return attach(state, info, browser=not a.no_browser, opener=opener)
    problem, warning = spa_problem()
    if problem:
        say('not started: ' + problem)
        return 2
    if warning:
        say('warning: ' + warning)
    env = Env(core_argv(a.remote_host))
    before = {s: signal.getsignal(s) for s in (signal.SIGINT, getattr(signal, 'SIGBREAK', None))
              if s is not None}
    if WINDOWS:                                     # the console window being closed
        signal.signal(signal.SIGBREAK, signal.default_int_handler)
    try:
        env.start()
        if not env.wait_healthy(a.timeout):
            return 1                                    # `finally` stops what did start
        if not a.no_browser and not open_ui(env.info, opener):
            say('Core is healthy but gave no launch code; open http://127.0.0.1:%d yourself'
                % env.info['port'])
        env.run()
        env._exited()                                   # Core ended by itself
    except KeyboardInterrupt:
        signal.signal(signal.SIGINT, signal.SIG_IGN)      # one stop, not two
    finally:
        env.stop()
        for s, h in before.items():
            signal.signal(s, h)
    return 0 if env.child is None or env.child.returncode == 0 else 1


# ── the Windows desktop shortcut ──

def _ps_quote(s):
    return "'%s'" % s.replace("'", "''")


def shortcut_script(action, wrapper=WRAPPER):
    """The PowerShell that makes or removes the desktop shortcut. The desktop is
    asked of Windows (it moves with OneDrive and localisation), the target is
    this checkout's wrapper: nothing about the machine is written down here."""
    find = ("$p = Join-Path ([Environment]::GetFolderPath('Desktop')) %s; "
            % _ps_quote(SHORTCUT))
    if action == 'remove':
        return find + "if (Test-Path -LiteralPath $p) { Remove-Item -LiteralPath $p }; $p"
    return find + (
        "$s = (New-Object -ComObject WScript.Shell).CreateShortcut($p); "
        "$s.TargetPath = %s; $s.WorkingDirectory = %s; "
        "$s.Description = 'Archeus V1 local developer environment (tools/v1_env.py)'; "
        "$s.Save(); $p" % (_ps_quote(wrapper), _ps_quote(os.path.dirname(os.path.dirname(
            wrapper)))))


def shortcut(action, run=subprocess.run):
    if not WINDOWS:
        say('the desktop shortcut is Windows-only; run `python tools/v1_env.py` instead')
        return 2
    r = run(['powershell', '-NoProfile', '-NonInteractive', '-Command',
             shortcut_script(action)], capture_output=True, text=True)
    if r.returncode:
        say('the shortcut could not be %s: %s' % (
            'made' if action == 'install' else 'removed', (r.stderr or '').strip()))
        return 2
    say('%s %s' % ('made' if action == 'install' else 'removed (if it was there)',
                   r.stdout.strip()))
    return 0


if __name__ == '__main__':
    sys.exit(main())

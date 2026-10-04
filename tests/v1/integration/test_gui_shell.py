"""`archeus gui` without a display (p19-design-gate B8): the shell's decisions
against a real Core — attaching (and starting Core only when nothing holds its
lock), the page's launch address, the shell's own in-memory `observe`+`control`
credential, the tray's Pause all / Emergency stop / Attention count reaching the
right routes with the right credential, Core down, the persistent profile's
directory and the colours drawn outside the page; and the legacy GUI's "Open
Archeus V1". The Qt window itself is tests/v1/e2e/test_gui_qt.py.
Mutation-verified by tools/mutate_p19.py (P111 onward)."""

import io
import json
import os
import time

import pytest

from archeus.api import auth
from archeus.cli import gui
from archeus.cli import main as cli
from archeus.cli.tui import client
from archeus.core import engine, ports, runtime
from archeus.harnesses.fake import FakeHarness
from archeus.infra import discovery, paths
from claude_sessions import proc
from v1.judge.http import CoreProcess, TempCore

TOKENS = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'clients', 'app', 'tokens',
                      'tokens.json')
SLOW = {'work': [{'emit': {'type': 'working'}}, {'sleep': 30}]}


def _never(*a, **k):
    raise AssertionError('the shell started Core')


@pytest.fixture
def core(archeus_home):
    tc = TempCore(archeus_home, ports=runtime.Ports(
        brain=ports.FixedPlanBrain(engine.SKELETON_PLAN), scenarios=dict(SLOW),
        executors=[FakeHarness()])).start()
    yield tc
    for p in list(tc.core.manager._procs.values()) if tc.core else ():
        proc.kill_pid_tree(p['handle'].pid, p['handle'].create_time)
    tc.stop(kill=True)


@pytest.fixture
def sent(monkeypatch):
    """Every request a client.Core makes: (method, path, the token it carried)."""
    seen, real = [], client.Core._open

    def spy(self, method, path, body=None, headers=None, **kw):
        seen.append((method, path.split('?')[0], self._token))
        return real(self, method, path, body, headers, **kw)
    monkeypatch.setattr(client.Core, '_open', spy)
    return seen


def _shell():
    shell, why = gui.attach(start=_never)
    assert why is None and shell is not None, why
    return shell


def _until(fn, what, timeout=30):
    deadline = time.monotonic() + timeout
    while not fn():
        assert time.monotonic() < deadline, 'timed out: %s' % what
        time.sleep(0.05)


def _mission(tc, title):
    r = tc.http('POST', '/v1/missions', body={'title': title, 'objective': 'o',
                                              'idempotency_key': 'k-%s-%f' % (title, time.time())})
    assert r.status == 200, r.body
    return r.json()['id']


# ── attaching ──

def test_a_running_core_is_attached_and_never_started_again(core):
    shell = _shell()
    assert shell.info['port'] == core.port


def test_with_no_core_the_shell_starts_it_once_and_waits_for_it(archeus_home):
    started = []

    def start():                    # returns before Core answers, as a spawn does
        started.append(CoreProcess(archeus_home).start(wait=False))
        return ''
    shell, why = gui.attach(start=start)
    try:
        assert why is None and len(started) == 1
        assert shell.info['port'] == started[0].port and shell.attention() == 0
    finally:
        started[0].kill()
        started[0].wait(30)


def test_a_core_that_cannot_start_is_said_and_nothing_is_attached(archeus_home):
    shell, why = gui.attach(start=lambda: 'no python here')
    assert shell is None and why == 'could not start Archeus Core: no python here'
    shell, why = gui.attach(start=lambda: '', wait_s=0.3)
    assert shell is None and why.startswith('Archeus Core did not start (see ')
    assert gui.start_log() in why


def test_the_start_runs_archeus_core_in_the_background(archeus_home, monkeypatch):
    got = {}

    def spawn(argv, **kw):
        got.update(argv=argv, **kw)
        return object(), ''
    monkeypatch.setattr(proc, 'spawn_detached', spawn)
    assert gui.start_core() == ''
    assert got['argv'][-1].endswith('sys.exit(main(["core"]))')
    assert got['hidden_console'] is True              # Core's executions start consoles
    assert got['log'] == os.path.join(str(archeus_home), 'logs', 'gui-core.log')
    monkeypatch.setattr(proc, 'spawn_detached', lambda argv, **kw: (None, 'denied'))
    assert gui.start_core() == 'denied'


# ── the page and the shell's own credential ──

def test_the_page_opens_on_a_launch_code_with_the_full_local_grant(core):
    url = _shell().page_url()
    head, code = url.split('#launch=')
    assert head == 'http://127.0.0.1:%d/' % core.port
    r = core.http('POST', '/v1/devices/launch/redeem', body={'code': code, 'platform': 'web'})
    assert r.json()['scopes'] == ['observe', 'control', 'approve', 'admin']


def test_the_shells_credential_is_observe_and_control_named_desktop_shell_in_memory(
        core, archeus_home):
    shell = _shell()
    token = shell._own._token
    rows = [d for d in core.http('GET', '/v1/devices').json()['devices']
            if d['name'] == gui.SHELL_NAME]
    assert len(rows) == 1
    assert rows[0]['platform'] == 'desktop' and rows[0]['scopes'] == ['observe', 'control']
    assert token != discovery.read_local_token()
    for top, _dirs, files in os.walk(str(archeus_home)):    # held in memory only (§9)
        for f in files:
            try:
                with open(os.path.join(top, f), 'rb') as fh:
                    held = fh.read()
            except PermissionError:           # core.lock, held open by Core
                continue
            assert token.encode() not in held, os.path.join(top, f)
    # a redeem that names nothing is still the browser it always was
    code = core.http('POST', '/v1/devices/launch/code', body={}).json()['code']
    core.http('POST', '/v1/devices/launch/redeem', body={'code': code, 'platform': 'web'})
    assert 'browser (web)' in [d['name'] for d in core.http('GET', '/v1/devices').json()['devices']]


# ── the tray ──

def test_pause_all_pauses_what_runs_with_the_shells_credential(core, sent):
    shell = _shell()
    assert shell.pause_all() == 'Nothing was running'
    mid = _mission(core, 'Held by the tray')
    _until(lambda: core.http('GET', '/v1/missions/' + mid).json()['state'] == 'EXECUTING',
           'the mission executes')
    del sent[:]
    assert shell.pause_all() == 'Paused 1 running mission'
    assert sent == [('POST', '/v1/missions/pause-all', shell._own._token)]
    assert core.http('GET', '/v1/missions/' + mid).json()['state'] in ('PAUSING', 'PAUSED')


def test_with_core_down_pause_all_says_so(core):
    shell = _shell()
    core.stop(kill=True)
    assert shell.pause_all() == gui.NOT_RUNNING == 'Archeus Core is not running'
    assert shell.attention() is None


def test_emergency_stop_is_archeus_estops_code(core, sent):
    shell = _shell()
    del sent[:]
    code, said = shell.estop()
    assert code == 0 and said.startswith('emergency stop: '), said
    assert [s[:2] for s in sent] == [('POST', '/v1/estop')]
    assert sent[0][2] == discovery.read_local_token()      # the CLI's own credential
    assert os.path.exists(paths.stop_sentinel())             # the e-stop engaged


def test_emergency_stop_with_core_down_never_starts_it(archeus_home, monkeypatch):
    monkeypatch.setattr(gui, 'start_core', _never)
    code, said = gui.estop()
    assert code == 2 and 'Core is not running' in said and 'P20' in said
    assert discovery.discover()[0] == 'not_running'


def test_the_attention_count_is_cores(archeus_home):
    deploy = dict(engine.SKELETON_PLAN, tasks=[dict(engine.SKELETON_PLAN['tasks'][0],
                                                    action_classes=['deploy'])])
    tc = TempCore(archeus_home, ports=runtime.Ports(brain=ports.FixedPlanBrain(deploy))).start()
    try:
        shell = _shell()
        assert shell.attention() == 0
        mid = _mission(tc, 'Needs a person')
        _until(lambda: tc.http('GET', '/v1/missions/' + mid).json()['state']
               == 'APPROVAL_REQUIRED', 'the mission asks')
        assert shell.attention() == tc.http('GET', '/v1/attention').json()['count'] >= 1
    finally:
        tc.stop(kill=True)


# ── what lives outside the page ──

def test_the_profile_lives_in_the_qt_shells_own_entry(archeus_home):
    assert gui.profile_dir() == os.path.join(str(archeus_home), 'QtWebEngine', 'archeus')
    assert 'QtWebEngine' in paths.QT_OWNED and 'QtWebEngine' not in paths.V1_OWNED


def test_the_colours_outside_the_page_are_the_tokens_of_the_os_scheme():
    with open(TOKENS, encoding='utf-8') as f:
        themes = json.load(f)['themes']
    assert gui.preload_bg(True) == themes['dark']['bg']
    assert gui.preload_bg(False) == themes['light']['bg']          # never a fixed dark
    assert gui.attention_colour(True) == themes['dark']['state.attention']
    assert gui.attention_colour(False) == themes['light']['state.attention']


# ── the verb ──

def test_the_gui_verb_without_qt_says_so_and_starts_nothing(archeus_home, monkeypatch, capsys):
    import builtins
    real = builtins.__import__

    def no_qt(name, *a, **k):
        if name.startswith('PyQt6'):
            raise ImportError(name)
        return real(name, *a, **k)
    monkeypatch.setattr(builtins, '__import__', no_qt)
    monkeypatch.setattr(gui, 'start_core', _never)
    assert cli.main(['gui']) == 2
    assert 'PyQt6' in capsys.readouterr().err
    assert cli.main(['gui', 'x']) == 2                      # the usage
    assert 'archeus gui ' in capsys.readouterr().err


# ── the legacy GUI's "Open Archeus V1" ──

def test_open_archeus_v1_from_the_legacy_gui(archeus_home, monkeypatch):
    import webbrowser
    from claude_sessions import gui_api
    opened = []
    monkeypatch.setattr(webbrowser, 'open', lambda url, *a, **k: opened.append(url))
    assert gui_api.api_open_v1({}, {}) == {
        'ok': False, 'error': 'Archeus Core is not running: start it with `archeus core`'}
    assert opened == []
    tc = TempCore(archeus_home).start()
    try:
        assert gui_api.api_open_v1({}, {}) == {'ok': True}
        head, code = opened[0].split('#launch=')
        assert head == 'http://127.0.0.1:%d/' % tc.port
        r = tc.http('POST', '/v1/devices/launch/redeem', body={'code': code, 'platform': 'web'})
        assert r.json()['scopes'] == list(auth.LOCAL_SCOPES)
    finally:
        tc.stop(kill=True)


def test_the_legacy_sidebar_foot_offers_it():
    web = os.path.join(os.path.dirname(gui_api_file()), 'web')
    with io.open(os.path.join(web, 'index.html'), encoding='utf-8') as f:
        html = f.read()
    foot = html[html.index('<div class="foot">'):html.index('</aside>')]
    assert 'id="bOpenV1" aria-label="Open Archeus V1"' in foot
    assert '><span>Open Archeus </span>V1</button>' in foot
    with io.open(os.path.join(web, 'app.js'), encoding='utf-8') as f:
        js = f.read()
    assert "$('#bOpenV1').onclick=" in js and "post('/api/v1/open'" in js


def gui_api_file():
    from claude_sessions import gui_api
    return gui_api.__file__

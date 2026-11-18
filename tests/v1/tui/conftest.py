"""Shared pieces of the TUI tests (p17-design-gate §12): a real in-process Core,
an App on it with the stream replaced by explicit signals (so every test is
deterministic), and the scripted keyboard of tests/harness.py driving the real
key decoder in `claude_sessions.term`."""

import os
import re
import sys
import time

import pytest

from archeus.cli.tui import app as A, client as C
from archeus.cli.tui.view import Style
from archeus.core import engine, ports, runtime
from archeus.harnesses.fake import FakeHarness
from claude_sessions import proc, render
from v1.judge.http import TempCore

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
import harness  # noqa: E402  (the legacy TUI's scripted keyboard, reused)

DEPLOY = dict(engine.SKELETON_PLAN, tasks=[dict(engine.SKELETON_PLAN['tasks'][0],
                                                 action_classes=['deploy'])])
SLOW = {'work': [{'emit': {'type': 'working'}}, {'sleep': 30}]}
SGR = re.compile(r'\x1b\[(?:0|1|38;5;\d+)m')


@pytest.fixture
def core(archeus_home):
    tc = TempCore(archeus_home).start()
    yield tc
    tc.stop(kill=True)


@pytest.fixture
def deploy(archeus_home):
    """A Core whose plan deploys: the plan asks for approval (P9)."""
    tc = TempCore(archeus_home, ports=runtime.Ports(brain=ports.FixedPlanBrain(DEPLOY))).start()
    yield tc
    tc.stop(kill=True)


@pytest.fixture
def slow(archeus_home):
    """A Core whose one task runs for 30 s on the fake harness."""
    tc = TempCore(archeus_home, ports=runtime.Ports(
        brain=ports.FixedPlanBrain(engine.SKELETON_PLAN), scenarios=dict(SLOW),
        executors=[FakeHarness()])).start()
    yield tc
    for p in list(tc.core.manager._procs.values()):
        proc.kill_pid_tree(p['handle'].pid, p['handle'].create_time)
    tc.stop(kill=True)


def mission(tc, title='Fix the flaky date test', objective='Tests pass'):
    r = tc.http('POST', '/v1/missions', body={'title': title, 'objective': objective,
                                              'idempotency_key': 'k-%s-%f' % (title,
                                                                              time.time())})
    assert r.status == 200, r.body
    return r.json()['id']


def state(tc, mid):
    return tc.http('GET', '/v1/missions/' + mid).json()['state']


def settled(tc, mid, want, timeout=30):
    deadline = time.monotonic() + timeout
    while state(tc, mid) != want:
        assert time.monotonic() < deadline, 'mission %s never reached %s' % (mid, want)
        time.sleep(0.05)


def app_on(tc, *, size=(100, 40), token=None, style=None, live=True):
    """An App on *tc* with no stream thread; a test says what the stream said."""
    a = A.App(C.Core(tc.port, token or tc.token), style or Style(False, 'dark', False),
              size=lambda: size, stream=False)
    if live:
        a.signal('stream_open')
    return a


def plain(app):
    return '\n'.join(render.strip_ansi(x) for x in app.frame())


def press(app, *keys):
    """Keys as events: a one-character string is a char, else a key name."""
    for k in keys:
        app.frame()
        app.handle(('char', k) if len(k) == 1 else (k,))
    return plain(app)


def row(app, pred):
    """Move the cursor to the first row whose target satisfies *pred*."""
    app.frame()
    rows = app.rows()
    for n, i in enumerate(rows):
        if pred(app._doc.lines[i]):
            app.cursor = n
            return app._doc.lines[i]
    raise AssertionError('no such row in:\n' + plain(app))


class Spy:
    """Every GET and POST the TUI makes, passed through to Core."""

    def __init__(self, core):
        self.core, self.gets, self.posts = core, [], []

    def get(self, path):
        self.gets.append(path)
        return self.core.get(path)

    def post(self, path, body):
        self.posts.append((path, body))
        return self.core.post(path, body)

    def events(self, last_id=None):
        return self.core.events(last_id)


def spy(app):
    s = Spy(app.core)
    app.core = s
    return s


def drive(monkeypatch, app, script):
    """Run the real loop on scripted keys until they run out; return what it
    wrote. The keys are Windows scancodes (tests/harness.py), decoded by term."""
    cap = harness.CapturingStdout()
    monkeypatch.setattr(sys, 'stdout', cap)
    harness.TuiScript(script).install(monkeypatch)
    with pytest.raises(harness.OutOfKeys):
        A.run(app, live=False)
    return cap

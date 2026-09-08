"""Every endpoint answers, and none of them answers 500.

Forty-nine of the routes had no HTTP-level test of any kind. That is the exact
class of bug already recorded in CLAUDE.md: `gate['diff']` shipped broken
because the only gate test covered one of the two shapes its producers passed.

The check is deliberately shallow and total rather than deep and partial — one
real request per route, asserting the server does not fault. A handler that
raises reaches the generic 500, and a 500 is indistinguishable to the SPA from
the server being down.

Nothing here may launch anything: every process-spawning seam is stubbed, so a
run cannot open a terminal or an editor on the machine running it.
"""

import json
import os
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from harness import Sandbox
from claude_sessions import gui, gui_api

#: query parameters good enough for any GET route. A route that wants something
#: else answers 400, which is a pass — the point is that it does not fault.
def _params(sb, enc, path):
    return {'enc': enc, 'path': path, 'sid': 'aaaa', 'q': 'x', 'days': '7',
            'limit': '5', 'scope': 'project', 'name': 'x', 'id': 'x',
            'file': os.path.join(path, 'CLAUDE.md')}


@pytest.fixture
def live(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    actual, enc, folder, _ = sb.add_project('alpha')

    # every seam that could start a process
    from claude_sessions import proc
    monkeypatch.setattr(proc, 'spawn_terminal',
                        lambda *a, **kw: (None, 'blocked in tests'))
    monkeypatch.setattr(proc, 'run', lambda *a, **kw: None)
    monkeypatch.setattr(gui_api, 'start_job', lambda *a, **kw: 'stub-job')
    # An OSError, not a test failure: some routes legitimately shell out to the
    # claude CLI, every one of them already handles it being absent, and
    # raising something the handler cannot catch just kills the connection and
    # reports as a mysterious RemoteDisconnected.
    import subprocess
    monkeypatch.setattr(subprocess, 'Popen',
                        lambda *a, **kw: (_ for _ in ()).throw(
                            OSError('no process may be spawned by a test')))

    srv = gui.make_server(0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = 'http://127.0.0.1:%d' % srv.server_address[1]
    yield base, enc, actual
    srv.shutdown()
    srv.server_close()


def _call(url, body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data,
                               headers={'X-Archeus': gui.TOKEN},
                               method='POST' if data is not None else 'GET')
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def _all(table_name):
    from claude_sessions import gui as g, gui_api as ga
    local = getattr(g, '_LOCAL_' + table_name)
    return sorted(set(getattr(ga, table_name + '_ROUTES')) | set(local))


@pytest.mark.parametrize('route', _all('GET'))
def test_every_get_route_answers_without_faulting(live, route):
    base, enc, path = live
    url = base + route + '?' + urllib.parse.urlencode(_params(None, enc, path))
    code, payload = _call(url)
    assert code != 500, '%s -> 500 %s' % (route, payload[:300])
    assert code in (200, 400, 404), '%s -> %s' % (route, code)
    json.loads(payload or b'{}')          # every route answers JSON


@pytest.mark.parametrize('route', _all('POST'))
def test_every_post_route_rejects_an_empty_body_without_faulting(live, route):
    """An empty body is the caller getting it wrong, which is a 400. It was a
    500 carrying a bare KeyError message."""
    base, _enc, _path = live
    code, payload = _call(base + route, {})
    assert code != 500, '%s -> 500 %s' % (route, payload[:300])
    json.loads(payload or b'{}')

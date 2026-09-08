"""Phase 4 gates: a caller cannot get a 500 by being wrong, and a wrong
caller cannot reach the filesystem.

`_folder(cfgdir, enc)` reaches roughly forty endpoints with values taken
straight off the wire.
"""

import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from harness import Sandbox
from claude_sessions import gui, gui_api


def _serve():
    srv = gui.make_server(0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f'http://127.0.0.1:{srv.server_address[1]}'


def _req(url, body=None, raw=None):
    data = raw if raw is not None else (
        json.dumps(body).encode() if body is not None else None)
    r = urllib.request.Request(url, data=data, headers={'X-Archeus': gui.TOKEN},
                               method='POST' if data is not None else 'GET')
    try:
        with urllib.request.urlopen(r) as resp:
            return resp.status, json.loads(resp.read() or b'{}')
    except urllib.error.HTTPError as e:
        payload = e.read()
        try:
            return e.code, json.loads(payload or b'{}')
        except Exception:
            return e.code, {'raw': payload[:200].decode('utf-8', 'replace')}


@pytest.fixture
def server(monkeypatch, tmp_path):
    Sandbox(monkeypatch, tmp_path)
    srv, base = _serve()
    yield base
    srv.shutdown()
    srv.server_close()


# ── the caller's mistakes are 400s ───────────────────────────

def test_a_missing_parameter_is_400_not_500(server):
    """It surfaced as 500 {"error": "'enc'"} — a KeyError leaking through the
    generic handler, indistinguishable to the SPA from the server breaking."""
    code, d = _req(server + '/api/transcript')
    assert code == 400, d
    assert 'enc' in d.get('error', '')


def test_a_traversal_in_enc_is_refused(server):
    code, d = _req(server + '/api/transcript?enc=..%2F..%2F..&sid=abc')
    assert code == 400, d


def test_a_traversal_in_sid_is_refused(server):
    code, d = _req(server + '/api/transcript?enc=D--x&sid=..%2F..%2Fsecret')
    assert code == 400, d


def test_an_unknown_cfgdir_is_refused(server):
    """Unvalidated, cfgdir is a filesystem read primitive: it is joined with
    'projects' and a name on about forty endpoints."""
    code, d = _req(server + '/api/transcript?enc=D--x&sid=abc&cfgdir=C%3A%5CWindows')
    assert code == 400, d
    assert 'cfgdir' in d.get('error', '')


def test_a_known_cfgdir_is_accepted(server):
    from claude_sessions import config as _c
    good = _c.all_config_dirs()[0][1]
    code, _d = _req(server + '/api/transcript?enc=D--x&sid=abc&cfgdir='
                    + urllib.parse.quote(good))
    assert code == 200


def test_an_unknown_route_is_still_404(server):
    code, _d = _req(server + '/api/does-not-exist')
    assert code == 404


def test_the_hardcoded_routes_answer_json_when_they_fail(server, monkeypatch):
    """They bypassed the wrapper and let the exception reach
    BaseHTTPRequestHandler, which answers with an HTML traceback that the SPA's
    resp.json() then chokes on."""
    monkeypatch.setattr(gui, 'state_payload',
                        lambda: (_ for _ in ()).throw(RuntimeError('boom')))
    code, d = _req(server + '/api/state')
    assert code == 500
    assert d.get('error') == 'boom', d


def test_launch_reports_a_bad_path_as_400(server):
    code, d = _req(server + '/api/launch',
                   {'path': '', 'enc': 'D--x', 'choice': 'new'})
    assert code == 400, d


# ── body limits ──────────────────────────────────────────────

def test_an_oversized_body_is_refused_without_being_read(server):
    """Content-Length was trusted verbatim and read unbounded."""
    big = b'{"pad":"' + b'x' * (gui.MAX_BODY + 1024) + b'"}'
    code, _d = _req(server + '/api/settings', raw=big)
    assert code == 413


def test_a_non_object_body_is_400(server):
    code, _d = _req(server + '/api/settings', raw=b'[1,2,3]')
    assert code == 400


def test_the_body_cap_is_declared():
    assert 0 < gui.MAX_BODY <= 8 * 1024 * 1024


def test_the_connection_ceiling_is_declared():
    """ThreadingHTTPServer starts one thread per connection with no ceiling."""
    assert 0 < gui.MAX_CONNECTIONS <= 256


# ── job hygiene ──────────────────────────────────────────────

def test_every_job_carries_its_own_lock():
    """_JOBS_LOCK covers the REGISTRY; four threads mutate a job's CONTENTS."""
    jid = gui_api.start_job('t', lambda: 1)
    job = gui_api._job(jid)
    assert isinstance(job['lock'], type(threading.RLock()))


def test_a_job_stuck_running_forever_is_reaped():
    """Only terminal jobs were trimmed, so a job whose thread died without
    setting a terminal status stayed in the registry forever."""
    with gui_api._JOBS_LOCK:
        gui_api._JOBS.clear()
        gui_api._JOBS['zombie'] = {
            'id': 'zombie', 'status': 'running', 'label': 'z', 'messages': [],
            'error': '', 'started': time.time() - gui_api._STUCK_AFTER - 1,
            'lock': threading.RLock()}
        gui_api._reap_locked()
        assert gui_api._JOBS['zombie']['status'] == 'error'


def test_terminal_jobs_are_trimmed_to_a_ceiling():
    with gui_api._JOBS_LOCK:
        gui_api._JOBS.clear()
        for i in range(gui_api._KEEP_TERMINAL + 20):
            gui_api._JOBS['j%d' % i] = {
                'id': 'j%d' % i, 'status': 'done', 'label': 'x', 'messages': [],
                'error': '', 'started': time.time() - i, 'lock': threading.RLock()}
        gui_api._reap_locked()
        assert len(gui_api._JOBS) == gui_api._KEEP_TERMINAL


def test_an_unknown_job_kind_is_400(server):
    """It answered 200 with ok:false, and the SPA reads a 200 as 'the server
    understood me' — so a typo'd kind produced the generic failure toast."""
    code, d = _req(server + '/api/job', {'kind': 'not-a-real-kind'})
    assert code == 400, d


def test_the_approval_gate_does_not_park_for_an_hour():
    """A parked job holds a worker thread and usually a claude subprocess."""
    assert gui_api.GATE_TIMEOUT <= 900


def test_the_gate_reports_its_countdown():
    job = {'id': 'g', 'status': 'running', 'label': 'g', 'messages': [],
           'error': '', 'started': time.time(), 'gate': None, 'decision': None,
           'decision_evt': threading.Event(), 'lock': threading.RLock(),
           'result': None}
    with gui_api._JOBS_LOCK:
        gui_api._JOBS['g'] = job

    done = threading.Event()

    def _park():
        gui_api._gate(job, 'T', 'a', 'b', ['-a', '+b'])
        done.set()

    threading.Thread(target=_park, daemon=True).start()
    for _ in range(200):
        st = gui_api.job_status('g')
        if st and st['status'] == 'awaiting':
            break
        time.sleep(0.01)
    st = gui_api.job_status('g')
    assert st['status'] == 'awaiting'
    assert 0 < st['gate_seconds_left'] <= gui_api.GATE_TIMEOUT
    gui_api.job_decide('g', True)
    assert done.wait(2)


def test_both_background_loops_can_be_stopped():
    """server_close() closed the socket and said nothing to two threads parked
    in a sleep."""
    from claude_sessions import usage
    assert hasattr(usage, 'stop_background')
    assert hasattr(gui_api, 'stop_auto_memory_scheduler')
    usage.stop_background()
    gui_api.stop_auto_memory_scheduler()
    assert usage._stop.is_set() and gui_api._sched_stop.is_set()
    usage._stop.clear()
    gui_api._sched_stop.clear()


def test_spawning_a_background_worker_twice_only_spawns_once(monkeypatch, tmp_path):
    """The check was an unsynchronised read of a set nothing wrote, so two
    callers arriving together both spawned a detached worker — and the child
    only takes scan.lock milliseconds later."""
    import subprocess
    from claude_sessions import memory
    spawned = []
    monkeypatch.setattr(subprocess, 'Popen',
                        lambda *a, **kw: spawned.append(1) or object())
    monkeypatch.setattr(memory, 'scan_lock_status', lambda p: None)
    memory._bg_spawned.clear()
    root = str(tmp_path)
    memory.spawn_background_worker(root, '')
    memory.spawn_background_worker(root, '')
    assert len(spawned) == 1

"""Core ownership: the lock, discovery, the local token, startup and failure
(p3.5b design gate §7, §10 G1–G6, M13). Real child processes: only a
real process can hold an OS lock, occupy a port or be killed."""

import os
import socket
import sys
import time

import pytest

from archeus.cli import main as cli
from archeus.infra import discovery, paths
from archeus.infra.db import connection
from claude_sessions import proc
from v1.judge.client import InProcessClient
from v1.judge.http import CoreProcess, TempCore

WINDOWS = sys.platform.startswith('win')


def _status(capsys, monkeypatch, *, allow_socket=True):
    """Run `archeus status` in process; with allow_socket=False any socket
    connect fails the test — the CLI must not send anything anywhere."""
    def refuse(*a, **k):
        raise AssertionError('status opened a socket')
    with monkeypatch.context() as m:
        if not allow_socket:
            m.setattr(socket.socket, 'connect', refuse)
        code = cli.main(['status'])
    return code, capsys.readouterr().out


# ── G1 second Core, G2 stale lock ──

def test_a_second_core_is_refused_and_never_opens_the_database(archeus_home):
    first = CoreProcess(archeus_home).start()
    try:
        db = connection.db_path()
        before = (os.stat(db).st_mtime_ns, os.stat(db).st_size)
        discovered = discovery.read_core_json()
        second = CoreProcess(archeus_home).start(wait=False)
        assert second.wait() == 1
        assert 'Core is already running (pid %d' % first.proc.pid in second.output()
        assert (os.stat(db).st_mtime_ns, os.stat(db).st_size) == before
        assert discovery.read_core_json() == discovered      # its discovery is untouched
        assert first.http('GET', '/v1/health').status == 200
    finally:
        first.kill()


def test_a_killed_core_leaves_no_lock_and_the_next_one_replaces_core_json(archeus_home):
    first = CoreProcess(archeus_home).start()
    first.kill()
    stale = discovery.read_core_json()
    assert stale['pid'] == first.proc.pid                     # left behind by the kill
    assert not discovery.lock_is_held()                       # the OS released the lock
    second = CoreProcess(archeus_home).start()
    try:
        assert discovery.read_core_json()['pid'] == second.proc.pid
        assert second.http('GET', '/v1/health').json()['core']['pid'] == second.proc.pid
    finally:
        second.kill()


def test_an_in_process_engine_host_and_a_core_cannot_share_a_home(archeus_home):
    """A1: two engine hosts on one home would each kill the other's children."""
    core = TempCore(archeus_home, lock_retry_s=0).start()
    try:
        with pytest.raises(discovery.LockHeld):
            InProcessClient(archeus_home).get_mission('msn_x')
    finally:
        core.stop()
    client = InProcessClient(archeus_home)
    client.events(0)
    try:
        with pytest.raises(discovery.LockHeld):
            TempCore(archeus_home, lock_retry_s=0).start()
    finally:
        client.close()


# ── G3 discovery, G5 stale / malformed core.json ──

def test_status_finds_a_running_core_and_reports_not_running_without_a_socket(
        archeus_home, capsys, monkeypatch):
    code, out = _status(capsys, monkeypatch, allow_socket=False)
    assert (code, out.strip()) == (1, 'Core: not running')
    core = CoreProcess(archeus_home).start()
    try:
        code, out = _status(capsys, monkeypatch)
        assert code == 0, out
        assert 'Core: running (pid %d, port %d' % (core.proc.pid, core.port) in out
        assert 'engine idle' in out or 'engine running' in out
        assert 'ports real' in out            # the policy engine is real since P9 (D20)
    finally:
        core.kill()
    code, out = _status(capsys, monkeypatch, allow_socket=False)
    assert code == 1                    # the stale core.json of the killed Core is not trusted


def test_a_held_lock_with_garbage_discovery_sends_nothing(archeus_home, capsys, monkeypatch):
    lock = discovery.acquire()
    try:
        with open(discovery.core_json_path(), 'w') as f:
            f.write('{not json')
        code, out = _status(capsys, monkeypatch, allow_socket=False)
        assert code == 2 and 'discovery file unreadable' in out
        # a readable file naming a process that is not alive is no better
        discovery.write_core_json({'pid': 2 ** 22 + 7, 'create_time': 1, 'port': 7,
                                   'started_at': 'x', 'version': 'x', 'schema': 2})
        code, out = _status(capsys, monkeypatch, allow_socket=False)
        assert code == 2 and 'discovery file unreadable' in out
    finally:
        lock.release()
    code, out = _status(capsys, monkeypatch, allow_socket=False)
    assert code == 1                    # a stale pid with the lock free: not running


# ── G4 port in use ──

def test_binding_the_port_does_no_reverse_dns_lookup(monkeypatch):
    """HTTPServer.server_bind resolves getfqdn('127.0.0.1') for a CGI-only
    server_name; on macOS CI that reverse lookup outlived Core's 30 s start."""
    from archeus.api import server

    def lookup(*a):
        raise AssertionError('binding did a reverse DNS lookup')
    monkeypatch.setattr(socket, 'getfqdn', lookup)
    s = server.Server(None, 0)
    try:
        port = s.socket.getsockname()[1]
        assert port and (s.server_name, s.server_port) == ('127.0.0.1', port)
    finally:
        s.server_close()


def test_a_port_in_use_exits_2_names_it_and_writes_no_core_json(archeus_home):
    squatter = socket.socket()
    squatter.bind(('127.0.0.1', 0))
    squatter.listen(1)
    port = squatter.getsockname()[1]
    try:
        core = CoreProcess(archeus_home, port=port).start(wait=False)
        assert core.wait() == 2
        assert 'port %d is in use' % port in core.output()
        assert not os.path.exists(discovery.core_json_path())
        assert not discovery.lock_is_held()
    finally:
        squatter.close()


# ── G6 the local token ──

def test_the_local_token_survives_a_restart_and_only_its_hash_is_stored(archeus_home):
    core = CoreProcess(archeus_home).start()
    token = core.token
    core.kill()
    assert token and token.startswith('dev_')
    again = CoreProcess(archeus_home).start()
    try:
        assert again.token == token
        assert again.http('GET', '/v1/version').status == 200
    finally:
        again.kill()
    import sqlite3
    conn = sqlite3.connect(connection.db_path())
    stored = [r[0] for r in conn.execute('SELECT token_hash FROM tokens')]
    conn.close()
    assert token not in stored and all(len(h) == 64 for h in stored)


@pytest.mark.skipif(WINDOWS, reason='POSIX file modes')
def test_the_token_file_is_0600_and_a_loose_mode_refuses_to_start(archeus_home):
    core = TempCore(archeus_home).start()
    core.stop()
    assert os.stat(discovery.local_token_path()).st_mode & 0o777 == 0o600
    os.chmod(discovery.local_token_path(), 0o644)
    with pytest.raises(Exception, match='readable by other users'):
        TempCore(archeus_home).start()
    assert not discovery.lock_is_held()


@pytest.mark.skipif(not WINDOWS, reason='the Windows profile-ACL rule')
def test_a_home_outside_the_profile_warns_in_status_and_the_log(archeus_home, capsys,
                                                                 monkeypatch, tmp_path):
    monkeypatch.setenv('USERPROFILE', str(tmp_path / 'someone-else'))
    core = TempCore(archeus_home).start()
    try:
        assert 'outside your user profile' in (core.core.warning or '')
        code, out = _status(capsys, monkeypatch)
        assert code == 0 and 'warning: ARCHEUS_HOME is outside your user profile' in out
    finally:
        core.stop()
    log = open(os.path.join(paths.archeus_home(), 'logs', 'core.log'), encoding='utf-8').read()
    assert 'outside your user profile' in log


# ── M13 engine failure ──

def test_an_engine_failure_stops_core_with_exit_3_and_the_next_start_carries_on(archeus_home):
    broken = CoreProcess(archeus_home, brain_fails=True).start()
    r = broken.http('POST', '/v1/missions', body={'title': 't', 'objective': 'o',
                                                  'idempotency_key': 'k'})
    assert r.status == 200
    mid = r.json()['id']
    assert broken.wait(30) == 3
    log = open(os.path.join(paths.archeus_home(), 'logs', 'core.log'), encoding='utf-8').read()
    assert 'the engine thread failed' in log and 'scripted brain failure' in log
    assert not os.path.exists(discovery.core_json_path())
    healthy = CoreProcess(archeus_home).start()
    try:
        deadline = time.monotonic() + 30
        while healthy.http('GET', '/v1/missions/' + mid).json()['state'] != 'COMPLETED':
            assert time.monotonic() < deadline, 'the restarted Core did not carry on'
            time.sleep(0.1)
    finally:
        healthy.kill()


def test_core_json_names_a_live_process_by_pid_and_creation_time(archeus_home):
    core = CoreProcess(archeus_home).start()
    try:
        info = discovery.read_core_json()
        assert set(info) == {'pid', 'create_time', 'port', 'started_at', 'version', 'schema'}
        assert proc.process_create_time(info['pid']) == info['create_time']
        assert discovery.discover()[0] == 'running'
    finally:
        core.kill()


def test_core_waits_out_a_probe_that_holds_the_lock_for_an_instant(archeus_home):
    """The CLI's discovery probe takes the lock for a moment; a Core starting
    at that moment retries (for 2 s) instead of refusing (§7)."""
    import threading
    probe = discovery.acquire()
    threading.Timer(0.5, probe.release).start()
    t0 = time.monotonic()
    core = TempCore(archeus_home).start()
    try:
        assert 0.4 < time.monotonic() - t0 < 2.0
        assert core.http('GET', '/v1/version').status == 200
    finally:
        core.stop()

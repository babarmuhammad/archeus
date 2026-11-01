"""Fix batch 11, from the review of fix batches 9 and 10: the answered-request memo is
dropped when an execution's process ends and is bounded (F5); a settings file nested past
the parser's depth is an unreadable file, not a crash (F8); a lock with no creation time
does not wedge Daemon.stop (F6); a failing step-up revoke does not open unlimited PIN
guesses (F4)."""

import os
from types import SimpleNamespace

from archeus.harnesses import sources
from archeus.infra import paths
from archeus.node import local
from archeus.node.local import LocalNode
from archeus.core.domain import ids


def _answered_pair(eid):
    p = paths.ExecPaths(eid)
    os.makedirs(p.req)
    os.makedirs(p.res, exist_ok=True)
    for box, name in ((p.req, '1.req.json'), (p.res, '1.res.json')):
        with open(os.path.join(box, name), 'w', encoding='utf-8') as f:
            f.write('{"nonce": "n"}')
        os.utime(os.path.join(box, name), (1, 1))             # settled long ago, so the pair is remembered


def test_f5_the_answered_memo_is_dropped_when_the_process_ends():
    eid = ids.new_id('execution')
    _answered_pair(eid)
    assert LocalNode.pending_requests(eid) == [] and local._ANSWERED[eid]
    me = SimpleNamespace(isolation=SimpleNamespace(children={}), _registry=lambda line: None)
    LocalNode.ended(me, SimpleNamespace(execution_id=eid), 0, 1)
    assert eid not in local._ANSWERED


def test_f5_the_answered_memo_holds_at_most_a_bounded_number_of_executions(monkeypatch):
    monkeypatch.setattr(local, '_ANSWERED', {})
    monkeypatch.setattr(local, '_ANSWERED_MAX', 3)
    eids = [ids.new_id('execution') for _ in range(5)]
    for eid in eids:
        _answered_pair(eid)
        assert LocalNode.pending_requests(eid) == []
    assert list(local._ANSWERED) == eids[-3:]


def test_f8_a_settings_file_nested_past_the_parser_depth_is_not_json(tmp_path):
    f = tmp_path / 'deep.json'
    f.write_text('{"mcpServers": ' + '[' * 100000 + ']' * 100000 + '}', encoding='utf-8')
    assert sources._json(str(f)) == (None, 'not JSON')


# ── F6: a lock with no creation time must not wedge Daemon.stop ──

def _daemon_with_stranger(tmp_path, monkeypatch, lock):
    import json
    import subprocess
    import sys
    from claude_sessions import config as _c, proxy_base
    monkeypatch.setattr(_c, 'settings_file', str(tmp_path / 'settings.json'))
    stranger = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])
    d = proxy_base.Daemon('gw', '--gw', 'gateway')
    with open(d.lock_path(), 'w', encoding='utf-8') as f:
        json.dump(dict(lock, pid=stranger.pid, port=5999, started=0), f)
    return d, stranger


def test_f6_a_lock_older_than_its_pid_is_cleared_and_the_stranger_left_alone(tmp_path, monkeypatch):
    d, stranger = _daemon_with_stranger(tmp_path, monkeypatch, {})
    try:
        os.utime(d.lock_path(), (1, 1))                   # written long before this pid started
        ok, msg = d.stop()
        assert ok and 'lock cleared' in msg and not os.path.exists(d.lock_path())
        assert stranger.poll() is None
        assert d.claim_spawn(5999)
    finally:
        stranger.kill()
        stranger.wait()


def test_f6_a_lock_the_pid_may_have_written_is_kept_and_the_refusal_names_the_way_out(tmp_path, monkeypatch):
    d, stranger = _daemon_with_stranger(tmp_path, monkeypatch, {})
    try:
        ok, msg = d.stop()
        assert not ok and 'delete %s' % d.lock_path() in msg and os.path.exists(d.lock_path())
        assert stranger.poll() is None
    finally:
        stranger.kill()
        stranger.wait()


def test_f6_a_kill_that_fails_on_the_recorded_process_says_so(tmp_path, monkeypatch):
    import json
    from claude_sessions import proc
    d, stranger = _daemon_with_stranger(tmp_path, monkeypatch, {})
    try:
        with open(d.lock_path(), 'w', encoding='utf-8') as f:
            json.dump({'pid': stranger.pid, 'port': 5999, 'started': 0,
                       'ctime': proc.process_create_time(stranger.pid)}, f)
        monkeypatch.setattr(proc, 'kill_pid_tree', lambda pid, ctime: False)
        ok, msg = d.stop()
        assert not ok and msg == 'could not stop pid %s' % stranger.pid and os.path.exists(d.lock_path())
    finally:
        stranger.kill()
        stranger.wait()
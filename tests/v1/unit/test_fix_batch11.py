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
"""Fix batch 12a, from the Codex review of the int4 delta (int4-delta-2c77cb32): the answered-request
memo is bounded per execution as well as in executions (S3)."""

import os

from archeus.core.domain import ids
from archeus.infra import paths
from archeus.node import local
from archeus.node.local import LocalNode


def test_s3_one_execution_remembers_a_bounded_number_of_answered_pairs(monkeypatch):
    monkeypatch.setattr(local, '_ANSWERED', {})
    monkeypatch.setattr(local, '_ANSWERED_PAIRS_MAX', 3)
    eid = ids.new_id('execution')
    p = paths.ExecPaths(eid)
    os.makedirs(p.req)
    os.makedirs(p.res)
    for seq in range(1, 8):
        for box, name in ((p.req, '%d.req.json' % seq), (p.res, '%d.res.json' % seq)):
            with open(os.path.join(box, name), 'w', encoding='utf-8') as f:
                f.write('{"nonce": "n"}')
            os.utime(os.path.join(box, name), (1, 1))
    assert LocalNode.pending_requests(eid) == []
    assert len(local._ANSWERED[eid]) == 3
    assert LocalNode.pending_requests(eid) == []                  # an evicted pair is re-read, still answered

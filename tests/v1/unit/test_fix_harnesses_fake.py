"""Regression tests for hostile-audit findings on archeus/harnesses/fake.py."""

from archeus.harnesses import base
from archeus.harnesses.fake import FakeCaller


def test_a_recorded_reply_that_does_not_match_leaves_the_queue_to_advance():
    """T-650#F1: the queue was filtered into a copy, so its pop was lost and every call
    got the first reply."""
    caller = FakeCaller(replies={'p': [{'when': 'R', 'parsed': 0}, {'parsed': 1},
                                       {'parsed': 2}]})
    spec = base.CallSpec(route_decision_id='r', purpose='p', prompt='x', workdir='.',
                         account=caller.default_account(), schema={})
    assert [caller.call(spec).parsed for _ in range(3)] == [1, 2, 2]

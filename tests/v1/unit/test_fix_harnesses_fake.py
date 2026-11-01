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


def _stream(tmp_path, *events):
    import json
    (tmp_path / 'stream.jsonl').write_text(''.join(json.dumps(e) + '\n' for e in events))
    return base.ProcessHandle('exe_1', 2 ** 22 - 1, None, str(tmp_path))


def test_a_restarted_core_does_not_read_an_earlier_process_exit_as_the_later_ones(tmp_path):
    """T-650#F4: process 1 exited 0, process 2 was killed and left no tombstone."""
    from archeus.harnesses.fake import FakeHarness
    handle = _stream(tmp_path, {'type': 'started'}, {'type': 'exit', 'code': 0},
                     {'type': 'started'})
    assert FakeHarness().status(handle).exit_code is None

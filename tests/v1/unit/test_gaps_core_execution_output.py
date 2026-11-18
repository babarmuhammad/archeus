"""T-772: the highest-risk branches of archeus/core/execution/output.py the other
tests never reached — the refusals (no process yet, no adapter, an id that may not
become a path), the reads that must fail closed instead of answering a tail the
caller cannot trust (a raising adapter),
the one output cap and its boundary, and the seam values (the handle, the caller's
offset, the snapshot's next_offset).

Everything runs on fakes at the seams the module's own tests use: the adapter half
of `test_gaps_core_execution_manager.py` (`inspect(handle, offset) -> Snapshot`)
and the `entities.Execution` + `FakeHarness` style of the D4 test in
`test_ui_seams.py`, minus the file: the output reader needs no OS call at all here,
so the same file passes or fails the same way on Linux and Windows. What is NOT
faked is the reader itself: no answer is built by the test, every assertion reads
what `output.read` returned.
"""

import json
from types import SimpleNamespace

import pytest

from archeus.core.domain import entities, ids
from archeus.core.execution import output
from archeus.harnesses import base
from archeus.infra.paths import ExecPaths


# ── the fake: the adapter half of the seam, recorded ─────────────────────────

class Recorder:
    """What `read` asks of a harness adapter, recorded and answered by the test.
    `inspect` is the one call the module makes; a second call, or a handle or an
    offset other than what was passed in, fails the test that pins it."""

    id = 'fake'

    def __init__(self, events=(), next_offset=0, raises=None):
        self.events, self.next_offset, self.raises = tuple(events), next_offset, raises
        self.calls = []

    def inspect(self, handle, offset=0):
        self.calls.append((handle, offset))
        if self.raises is not None:
            raise self.raises
        return base.Snapshot(self.events, self.next_offset)


def _exe(pid=4242, create_time=1.0):
    return entities.Execution(id=ids.new_id('execution'), task_id=ids.new_id('task'),
                              mission_id=ids.new_id('mission'), harness_id='fake',
                              pid=pid, create_time=create_time)


def _refusal(execution_id, offset):
    """The one answer a read that must refuse can give: empty, and NOT available."""
    return {'execution_id': execution_id, 'offset': offset, 'next_offset': offset,
            'events': [], 'truncated': False, 'available': False}


# ── the refusals (output.py:21-24) ───────────────────────────────────────────

def test_no_process_is_a_refusal_the_adapter_never_sees():
    # output.py:23 `execution.pid is None` → 24 `return out`, before any path or
    # adapter call: a tail for a process that never started is empty AND not
    # available, and no adapter may be asked (this adapter would raise if called)
    exe = _exe(pid=None)
    a = Recorder(raises=AssertionError('adapter must not be inspected'))
    assert output.read(exe, a, offset=7) == _refusal(exe.id, 7)
    assert a.calls == []


def test_no_adapter_is_a_refusal():
    # output.py:23 `adapter is None` (the harness lost its adapter, the process
    # row still holds a pid): the same refusal, never an AttributeError
    exe = _exe()
    assert output.read(exe, None, offset=11) == _refusal(exe.id, 11)
    # and with neither: still exactly the refusal, offset echoed into BOTH
    # offsets so a client tailing from 4096 does not restart from 0
    both = _exe(pid=None)
    assert output.read(both, None, offset=4096) == _refusal(both.id, 4096)


def test_a_bad_execution_id_is_refused_before_the_adapter():
    # output.py:25-26 `ExecPaths(execution.id).dir`: the id becomes a directory
    # name, so a malformed one raises there — never a handle to a directory the
    # caller pointed at, and never an inspect that could read it
    a = Recorder()
    fake = SimpleNamespace(id=ids.new_id('task'), pid=1234, create_time=2.0)
    with pytest.raises(ValueError, match='not an execution id'):
        output.read(fake, a)
    assert a.calls == []


# ── the reads that must fail closed (output.py:27, 30) ───────────────────────

def test_a_failing_read_is_not_answered_as_an_empty_tail():
    # output.py:27 `adapter.inspect(...)`: an OSError must propagate, not be
    # swallowed into `out` — an empty, available:false answer would tell a
    # tailing client its output is gone while its offset still claims it was read
    exe = _exe()
    a = Recorder(raises=OSError(2, 'stream file gone'))
    with pytest.raises(OSError):
        output.read(exe, a, offset=90)
    assert [c[1] for c in a.calls] == [90]          # asked once, at that offset


def test_every_event_is_redacted_in_its_whole_serialised_form():
    # output.py:46 `redact_json(e)`: the one redactor
    # sees the whole event — a nested value and a dict KEY are secrets
    # too, and what it does not replace must survive the round trip unchanged
    secret = 'dev_' + 'x' * 30
    key_secret = 'dev_' + 'y' * 30
    bearer = 'Bearer abcdefghijkl'
    exe = _exe()
    a = Recorder(events=({'type': 'text', 'text': 'keep %s here' % secret},
                         {'type': 'tool', 'args': {'inner': [bearer]}},
                         {key_secret: 'value', 'note': 'café ✓ 日本語'}),
                 next_offset=64)
    got = output.read(exe, a)
    blob = json.dumps(got)
    for leak in (secret, key_secret, bearer):
        assert leak not in blob                     # fail-closed: none survives
    assert got['events'][0]['text'] == 'keep [redacted] here'
    assert got['events'][1]['args']['inner'] == ['[redacted]']
    assert got['events'][2] == {'[redacted]': 'value', 'note': 'café ✓ 日本語'}
    assert blob.count('[redacted]') == 3
    assert (got['available'], got['offset'], got['next_offset'], got['truncated']) == (
        True, 0, 64, False)


# ── the one cap (output.py:31) ───────────────────────────────────────────────

def test_exactly_a_full_tail_is_not_truncated():
    # output.py:31 `len(events) > MAX_EVENTS`: the boundary is `>`, so a read of
    # exactly the cap carries every event and does NOT claim truncation (a `>=`
    # there tells a client it lost an event it still holds)
    assert output.MAX_EVENTS == 1000                # the frozen launch-side cap
    events = tuple({'n': i} for i in range(output.MAX_EVENTS))
    got = output.read(_exe(), Recorder(events=events, next_offset=7))
    assert got['truncated'] is False and got['available'] is True
    assert len(got['events']) == output.MAX_EVENTS
    assert (got['events'][0]['n'], got['events'][-1]['n']) == (0, output.MAX_EVENTS - 1)
    assert got['next_offset'] == 7                  # the client may tail from here


def test_over_the_cap_the_newest_tail_is_kept():
    # output.py:31 `events[-MAX_EVENTS:]`: a client tails, it does not archive —
    # one event over the cap drops the OLDEST, keeps the newest MAX, and says so
    # (dropping the slice returns the whole batch; [:MAX] keeps the wrong end)
    events = tuple({'n': i} for i in range(output.MAX_EVENTS + 1))
    a = Recorder(events=events, next_offset=123)
    got = output.read(_exe(), a, offset=5)
    assert got['truncated'] is True and got['available'] is True
    assert len(got['events']) == output.MAX_EVENTS
    assert (got['events'][0]['n'], got['events'][-1]['n']) == (1, output.MAX_EVENTS)
    assert (got['offset'], got['next_offset']) == (5, 123)


# ── the seam values (output.py:25-27, 31-32) ─────────────────────────────────

def test_the_handle_names_the_process_it_reads():
    # output.py:25-26 `base.ProcessHandle(execution.id, execution.pid,
    # execution.create_time, ExecPaths(execution.id).dir)`: the adapter finds the
    # stream through THAT directory — a swapped or defaulted field reads some
    # other execution's output, which no assertion on the events would catch
    exe = _exe(pid=987654, create_time=17.5)
    a = Recorder()
    output.read(exe, a, offset=3)
    assert a.calls == [(base.ProcessHandle(exe.id, 987654, 17.5,
                                           ExecPaths(exe.id).dir), 3)]


def test_the_answer_offsets_come_from_the_caller_and_the_snapshot():
    # output.py:21/27/31-32: `offset` is what the caller asked and `next_offset`
    # is what the adapter returned — conflating them (next_offset=offset) loses
    # every event the next tail should have seen; a live process whose tail is
    # empty stays `available: true` (returning `out` here says "no process")
    exe = _exe()
    a = Recorder(events=(), next_offset=555)
    got = output.read(exe, a, offset=321)
    assert got == dict(_refusal(exe.id, 321), available=True, next_offset=555)
    assert a.calls == [((base.ProcessHandle(exe.id, exe.pid, exe.create_time,
                                            ExecPaths(exe.id).dir)), 321)]

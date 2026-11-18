"""T-310: the ten highest-risk uncovered branches of archeus/api/sse.py, as units.

Fail-closed and refusals first — the pool's 429 refusing before any stream byte, a
cursor the log cannot honour refused before the 200, a credential revoked mid-stream,
a transport origin withdrawn mid-stream, a client's own presence traces suppressed
while everyone else's pass, and a failing trace neither refusing nor keeping a
stream — then boundaries — a full MAX_LIMIT page replaying inside one wake with the
cursor advancing on the raw page tail, and the heartbeat firing only when the write
budget is gone — then error paths — a prune overtaking a stream writing exactly one
`cursor_expired` frame, and teardown of a stream whose socket is already gone.

Same in-process fake style as tests/v1/unit/test_stream_takeover_units.py and
tests/v1/unit/test_broker_gaps.py: the pool and serve() are driven directly against a
fake db, writer and request object, with the outbox reads patched at the module seam
and `_still_valid` at the seam tests/v1/integration/test_sse.py already uses. No
processes, no sockets, no threads, no sleep over 0.2 s; every framing assertion is on
explicit bytes, so it reads the same on Windows as on Linux.
"""

import json
import socket
import time
import types

import pytest

from archeus.api import sse
from archeus.api.routes import Refused
from archeus.core.application import commands
from archeus.core.domain import ids
from archeus.core.domain.events import new_event
from archeus.core.domain.values import Ref
from archeus.infra.eventlog import outbox

MAX = outbox.MAX_LIMIT


class _Conn:
    """The server-side socket of a stream; `fail` makes a hangup face a dead peer."""

    def __init__(self, fail=None):
        self.shut, self.fail, self.attempts = False, fail, 0

    def shutdown(self, how):
        self.attempts += 1
        assert how == socket.SHUT_RDWR
        if self.fail is not None:
            raise self.fail
        self.shut = True


class _Writer:
    """The commit notifier: records every wait, and a test drives what happens in it."""

    def __init__(self, max_waits=8):
        self.commit_count, self.wakes, self.waits = 0, 0, []
        self.on_wait, self.max_waits = None, max_waits

    def wake(self):
        self.wakes += 1

    def wait_commit(self, seen, timeout, until=None):
        self.waits.append({'seen': seen, 'timeout': timeout, 'until': until})
        if self.on_wait is not None:
            self.on_wait(len(self.waits), self)
        if len(self.waits) > self.max_waits:
            raise AssertionError('the stream never ended (%d waits)' % len(self.waits))
        return self.commit_count


class _Log:
    """The committed log behind db.read(): one head, queued pages, a tail, and the
    pre-200 probe (limit=1) with an error it can raise. Every read is recorded."""

    def __init__(self, head=0):
        self.head, self.stopping = head, False
        self.queue, self.tail = [], []
        self.probe_error, self.probe_fired, self.reads = None, 0, []

    def read(self):
        log = self

        class _Ctx:
            def __enter__(self):
                return ('conn', id(log))

            def __exit__(self, *exc):
                return False
        return _Ctx()

    def events_after(self, conn, cursor, *, limit):
        self.reads.append((cursor, limit))
        if limit == 1:                                    # serve's cursor probe pre-200
            self.probe_fired += 1
            err, self.probe_error = self.probe_error, None
            if err is not None:
                raise err
            return []
        item = self.queue.pop(0) if self.queue else self.tail
        if isinstance(item, BaseException):
            raise item
        return item


class _Req:
    """The face of server.Handler that serve(), _loop() and _trace() touch."""

    def __init__(self, device_id=None, conn=None):
        self.principal = {'device_id': device_id or ids.new_id('device'),
                          'principal_id': ids.new_id('principal'), 'scopes': ['observe']}
        self.connection = conn
        self.token_hash = 'th_' + self.principal['device_id']
        self.writes, self.started, self.runs = [], 0, []
        self.run_error, self.valid, self.origin_ok = None, True, True
        self.origin_checks = 0

    def start_stream(self):
        self.started += 1

    def write(self, data):
        self.writes.append(data)

    def run(self, fn, kwargs, *, keyed=True):
        self.runs.append((fn, dict(kwargs), keyed))
        if self.run_error is not None:
            raise self.run_error

    def origin_holds(self):
        self.origin_checks += 1
        return self.origin_ok


def _streams(monkeypatch, head=0, heartbeat_s=15.0, always_valid=False):
    log = _Log(head)
    monkeypatch.setattr(sse.outbox, 'head', lambda conn: log.head)
    monkeypatch.setattr(sse.outbox, 'events_after', log.events_after)
    writer = _Writer()
    db = types.SimpleNamespace(writer=writer, read=log.read)
    st = sse.Streams(db, heartbeat_s=heartbeat_s, stopping=lambda: log.stopping)
    if always_valid:                                      # the seam test_sse.py uses
        monkeypatch.setattr(sse.Streams, '_still_valid', lambda self, h: True)
    return st, log, writer


def _ev(seq, type_='mission.updated', kind='mission', ident=None, project=None):
    return new_event(type_, Ref(kind, ident or ids.new_id(kind)),
                     Ref('system', ids.new_id('principal')), payload={},
                     seq=seq, project=project)


def _ids(req):
    return [int(line[4:]) for chunk in req.writes for line in chunk.decode('utf-8').split('\n')
            if line.startswith('id: ')]


# ── fail-closed and refusals ──

def test_a_full_pool_refuses_a_new_device_with_429_and_writes_nothing(monkeypatch):
    """sse.py:163-165: the pool's cap is the only refusal, and it is a Refused the
    HTTP layer answers — no 200, no frame, no trace, no slot taken."""
    st, log, writer = _streams(monkeypatch)
    for i in range(sse.MAX_STREAMS // sse.PER_DEVICE):
        for _ in range(sse.PER_DEVICE):
            st._register('dvc_%d' % i, _Conn())[0].started = True
    req = _Req(conn=_Conn())
    with pytest.raises(Refused) as got:
        st.serve(req, 0)
    assert (got.value.status, got.value.code) == (429, 'too_many_streams')
    assert req.started == 0 and req.writes == [] and req.runs == []      # nothing on the wire
    assert st.count() == sse.MAX_STREAMS and writer.waits == []


def test_a_cursor_the_log_cannot_honour_is_refused_before_the_200(monkeypatch):
    """sse.py:156-160: the pre-200 probe is the ONLY place a 410 (or the route's 400)
    is produced; if it ran after start_stream the client would see stream bytes."""
    st, log, writer = _streams(monkeypatch, head=20)
    req = _Req(conn=_Conn())
    log.probe_error = outbox.CursorExpired(5, 'pruned', 10, 20)
    with pytest.raises(outbox.CursorExpired):
        st.serve(req, 5)
    assert log.reads == [(5, 1)] and log.probe_fired == 1          # probed, exactly once
    assert req.started == 0 and req.writes == [] and st.count() == 0 and writer.waits == []
    req2 = _Req(conn=_Conn())                                     # malformed -> the route's 400
    log.probe_error = ValueError('a cursor is an integer >= 0')
    with pytest.raises(ValueError):
        st.serve(req2, -1)
    assert req2.started == 0 and req2.writes == [] and st.count() == 0


def test_a_credential_revoked_mid_stream_closes_the_stream_within_one_wake(monkeypatch):
    """sse.py:223-225: a revocation made by any other path must end the stream on
    the wake after it, with the close traced as 'revoked' — never serve on a dead token."""
    st, log, writer = _streams(monkeypatch)
    req = _Req(conn=_Conn())
    checked = []

    def still_valid(self, h):
        checked.append(h)
        return req.valid
    monkeypatch.setattr(sse.Streams, '_still_valid', still_valid)
    writer.on_wait = lambda n, w: setattr(req, 'valid', n < 1)
    assert st.serve(req, 0) is None
    assert checked and checked[0] == req.token_hash                # the stream's own token
    assert writer.waits[0]['timeout'] > 0                          # it waited, never polled
    opened, closed = req.runs
    assert opened[0] is commands.record_connection and opened[1]['opened'] is True \
        and opened[1]['reason'] is None and opened[2] is False
    assert closed[0] is commands.record_connection and closed[1]['opened'] is False \
        and closed[1]['reason'] == 'revoked' and closed[1]['connection_id'] == opened[1]['connection_id']
    assert st.count() == 0


def test_an_withdrawn_origin_closes_the_stream_within_one_wake(monkeypatch):
    """sse.py:227-229: a stream over a tunnel that is withdrawn closes with
    'origin_lost' on its next wake — the origin is re-checked, not just the token."""
    st, log, writer = _streams(monkeypatch, always_valid=True)   # token fine, origin goes
    req = _Req(conn=_Conn())
    writer.on_wait = lambda n, w: setattr(req, 'origin_ok', False) if n == 1 else None
    assert st.serve(req, 0) is None
    assert req.origin_checks == 1                                  # checked once per wake
    assert req.runs[-1][1]['reason'] == 'origin_lost' and req.runs[-1][1]['opened'] is False
    assert st.count() == 0


def test_a_client_never_sees_its_own_traces_and_everyones_else_it_does(monkeypatch):
    """sse.py:206-208: the self-suppression drops only `device.stream_*` whose
    subject is this client — another device's trace and a non-trace event about my
    own device both still arrive, and dropping the filter or widening it both fail here."""
    st, log, writer = _streams(monkeypatch)
    mine, other = ids.new_id('device'), ids.new_id('device')
    req = _Req(device_id=mine, conn=_Conn())
    log.queue = [[_ev(1, 'device.stream_opened', 'device', mine),        # mine: dropped
                  _ev(2, 'device.stream_closed', 'device', other),       # someone else's: kept
                  _ev(3, 'mission.created'),                              # ordinary: kept
                  _ev(4, 'device.state_changed', 'device', mine)]]        # not a trace: kept
    writer.on_wait = lambda n, w: setattr(req, 'valid', False) if n == 1 else None
    monkeypatch.setattr(sse.Streams, '_still_valid', lambda self, h: req.valid)
    assert st.serve(req, 0) is None
    assert _ids(req) == [2, 3, 4]
    raw = b''.join(req.writes)
    assert b'id: 1\n' not in raw and raw.endswith(b'\n\n')


def test_a_failing_trace_refuses_nothing_and_keeps_no_stream(monkeypatch):
    """sse.py:180-186: both traces are attempted and every exception from them is
    swallowed — a dead writer may neither turn an opening into a refusal nor stop the
    closing teardown (slot released, done set, 200 already out)."""
    st, log, writer = _streams(monkeypatch)
    req = _Req(conn=_Conn())
    req.run_error = RuntimeError('the writer is closed')
    stream = {}

    def on_wait(n, w):
        stream['s'] = st._open[0]
        req.valid = False
    writer.on_wait = on_wait
    monkeypatch.setattr(sse.Streams, '_still_valid', lambda self, h: req.valid)
    assert st.serve(req, 0) is None                                # the errors never escape
    assert req.started == 1 and [r[0] for r in req.runs] == [commands.record_connection] * 2
    assert st.count() == 0 and stream['s'].done.is_set()


def test_a_stream_closed_from_outside_reports_its_reason_not_client_gone(monkeypatch):
    """sse.py:196-197: a takeover/revocation flag set from outside ends _loop with
    the stream's own `why`, and that reason is what the close trace carries."""
    st, log, writer = _streams(monkeypatch, always_valid=True)
    req = _Req(conn=_Conn())

    def on_wait(n, w):
        s = st._open[0]
        s.why, _ = 'superseded', s.closing.set()
    writer.on_wait = on_wait
    assert st.serve(req, 0) is None
    assert req.runs[-1][1]['reason'] == 'superseded' and st.count() == 0


@pytest.mark.parametrize('what', ('closing', 'stopping'), ids=('closing', 'stopping'))
def test_the_wait_listens_for_both_a_closing_stream_and_a_stopping_core(monkeypatch, what):
    """sse.py:221-222: `wait_commit` is woken by its until — dropping either half of
    `stream.closing.is_set() or self.stopping()` (or passing no until at all) means a
    takeover or a shutdown waits out the whole heartbeat instead of returning."""
    st, log, writer = _streams(monkeypatch, always_valid=True)
    req = _Req(conn=_Conn())
    flags = {}

    def on_wait(n, w):
        if n == 1:
            flags['s'] = st._open[0]
            assert callable(w.waits[0]['until']) and w.waits[0]['until']() is False
            if what == 'closing':
                flags['s'].closing.set()
            else:
                log.stopping = True
            assert w.waits[0]['until']() is True               # this wake is over
    writer.on_wait = on_wait
    assert st.serve(req, 0) is None
    assert len(writer.waits) == 1                                # one wake, not a heartbeat


def test_a_shutdown_writes_its_frame_and_stopping_outranks_a_pending_close(monkeypatch):
    """sse.py:193-195: the shutdown frame is exactly `event: shutdown\\ndata: {}\\n\\n`,
    and stopping is checked BEFORE closing — a stream both closing and stopping reports
    the stop, or the client resyncs instead of quitting."""
    st, log, writer = _streams(monkeypatch, always_valid=True)
    req = _Req(conn=_Conn())
    log.stopping = True
    assert st.serve(req, 0) is None
    assert req.writes == [b'event: shutdown\ndata: {}\n\n']
    assert req.runs[-1][1]['reason'] == 'core_stopping' and req.origin_checks == 0
    s = st._register('dvc_x', _Conn())[0]                            # closing AND stopping
    s.why, _ = 'superseded', s.closing.set()
    assert st._loop(req, s, 0, sse.narrowing()) == 'core_stopping'


def test_a_full_page_replays_in_one_wake_and_the_raw_tail_moves_the_cursor(monkeypatch):
    """sse.py:212-214: a page of exactly MAX_LIMIT keeps replaying without waiting for
    a commit, and the cursor advances on the raw page's last seq — not the filtered
    one's (here the page tail is the client's own trace), or the next page replays."""
    st, log, writer = _streams(monkeypatch)
    mine = ids.new_id('device')
    req = _Req(device_id=mine, conn=_Conn())
    page1 = [_ev(i) for i in range(1, MAX)] + [                          # exactly MAX_LIMIT
        _ev(MAX, 'device.stream_opened', 'device', mine)]
    log.queue = [page1, [_ev(MAX + 1), _ev(MAX + 2)]]
    writer.on_wait = lambda n, w: setattr(req, 'valid', False) if n == 1 else None
    monkeypatch.setattr(sse.Streams, '_still_valid', lambda self, h: req.valid)
    assert st.serve(req, 0) is None
    assert log.reads == [(0, 1), (0, MAX), (MAX, MAX)]                   # cursor = raw tail
    assert len(writer.waits) == 1                                        # a full page never waited
    assert _ids(req) == list(range(1, MAX)) + [MAX + 1, MAX + 2]         # in order, no dupes
    assert b': hb\n\n' not in b''.join(req.writes)                       # a busy stream is silent


def test_an_idle_stream_writes_one_heartbeat_only_when_its_write_budget_is_gone(monkeypatch):
    """sse.py:216-220: `: hb\n\n` exactly when heartbeat_s has passed since the last
    frame, then the budget restarts — removing `if wait <= 0` (or the reset) either
    never heartbeats or heartbeats a busy stream."""
    clock = [1000.0]
    monkeypatch.setattr(sse, 'time', types.SimpleNamespace(monotonic=lambda: clock[0]))
    st, log, writer = _streams(monkeypatch, heartbeat_s=5.0, always_valid=True)
    req = _Req(conn=_Conn())

    def on_wait(n, w):
        if n == 1:
            clock[0] += 6.0                                             # idle past the budget
        if n == 2:
            req.valid = False
    writer.on_wait = on_wait
    monkeypatch.setattr(sse.Streams, '_still_valid', lambda self, h: req.valid)
    assert st.serve(req, 0) is None
    assert req.writes == [b': hb\n\n']
    assert [w['timeout'] for w in writer.waits] == [5.0, 5.0]           # full budget, then reset


def test_a_prune_that_overtakes_a_stream_writes_one_cursor_expired_frame_then_ends(monkeypatch):
    """sse.py:199-205: mid-stream the refusal is an explicit frame naming the reason
    and the retained range, then the close is traced 'cursor_expired' — a skipped
    branch here either leaks the exception past serve or skips silently."""
    st, log, writer = _streams(monkeypatch, always_valid=True)
    req = _Req(conn=_Conn())
    log.queue = [[_ev(1)]]
    log.tail = outbox.CursorExpired(1, 'pruned', 10, 20)
    assert st.serve(req, 0) is None
    assert req.writes[0].startswith(b'id: 1\nevent: mission.updated\n')
    lines = req.writes[-1].decode('utf-8').split('\n')
    assert len(req.writes) == 2 and req.writes[-1].endswith(b'\n\n')
    assert lines[0] == 'event: cursor_expired'
    assert json.loads(lines[1][len('data: '):]) == {'reason': 'pruned', 'floor': 10, 'head': 20}
    assert req.runs[-1][1]['reason'] == 'cursor_expired' and st.count() == 0


def test_a_stream_whose_socket_is_already_gone_still_shuts_down_clean(monkeypatch):
    """sse.py:57-64: hangup swallows OSError (peer reset) and AttributeError (no
    socket) — without them the finally of serve() dies before unregistering, the slot
    leaks and the close trace never happens."""
    st, log, writer = _streams(monkeypatch)
    conn = _Conn(fail=ConnectionResetError(100, 'Connection reset by peer'))
    req = _Req(conn=conn)
    stream = {}

    def on_wait(n, w):
        stream['s'] = st._open[0]
        req.valid = False
    writer.on_wait = on_wait
    monkeypatch.setattr(sse.Streams, '_still_valid', lambda self, h: req.valid)
    assert st.serve(req, 0) is None                                # the OSError never escapes
    assert conn.attempts == 1 and st.count() == 0
    assert stream['s'].done.is_set() and req.runs[-1][1]['opened'] is False
    req2 = _Req(conn=None)                                         # the AttributeError path
    writer.on_wait = lambda n, w: setattr(req2, 'valid', False)
    monkeypatch.setattr(sse.Streams, '_still_valid', lambda self, h: req2.valid)
    assert st.serve(req2, 0) is None and st.count() == 0


# ── the seams the ten lean on, pinned too ──

def test_a_frame_is_id_event_data_and_a_blank_line_and_nothing_else(monkeypatch):
    """frame()/sse.py:79-83 over serve: exact bytes, identities only, one write()
    per page in seq order — an added payload field or a broken separator fails here."""
    st, log, writer = _streams(monkeypatch, always_valid=True)
    req = _Req(conn=_Conn())
    e1 = _ev(7, 'mission.created')
    e2 = _ev(8, 'mission.updated', ident=e1.subject.id, project=ids.new_id('project'))
    log.queue = [[e1, e2]]
    writer.on_wait = lambda n, w: setattr(req, 'valid', False)
    monkeypatch.setattr(sse.Streams, '_still_valid', lambda self, h: req.valid)
    assert st.serve(req, 0) is None
    assert req.writes == [b''.join(
        b'id: %d\nevent: %s\ndata: {"subject":{"kind":"%s","id":"%s"},"scope":{"workspace":%s,'
        b'"project":%s}}\n\n' % (e.seq, e.type.encode(), e.subject.kind.encode(),
                                 e.subject.id.encode(), json.dumps(e.workspace).encode(),
                                 json.dumps(e.project).encode())
        for e in (e1, e2))]


def test_no_cursor_streams_live_from_the_head_and_a_given_cursor_probes_first(monkeypatch):
    """sse.py:156-161: `cursor=None` means live-only starting AT head (replaying the
    whole log from 0 would be the bug), and an explicit cursor is probed (limit=1)
    before the pages (limit=MAX_LIMIT) resume from just after it."""
    st, log, writer = _streams(monkeypatch, head=50, always_valid=True)
    req = _Req(conn=_Conn())
    log.queue = [[_ev(51)]]
    writer.on_wait = lambda n, w: setattr(req, 'valid', False)
    monkeypatch.setattr(sse.Streams, '_still_valid', lambda self, h: req.valid)
    assert st.serve(req, None) is None
    assert log.probe_fired == 0 and log.reads[0] == (50, MAX) and _ids(req) == [51]
    st2, log2, writer2 = _streams(monkeypatch, head=50, always_valid=True)
    req2 = _Req(conn=_Conn())
    log2.queue = [[_ev(41)]]
    writer2.on_wait = lambda n, w: setattr(req2, 'valid', False)
    monkeypatch.setattr(sse.Streams, '_still_valid', lambda self, h: req2.valid)
    assert st2.serve(req2, 40) is None
    assert log2.probe_fired == 1 and log2.reads == [(40, 1), (40, MAX)] and _ids(req2) == [41]


def test_a_superseded_stream_closes_no_presence_transition_while_the_device_holds_one(monkeypatch):
    """sse.py:121-126: the removed-by-a-takeover stream is not in the pool, yet the
    answer is about the DEVICE: False while any of its streams remains, True only
    when it was truly the last — serve traces presence on transitions only, so an
    unconditional True here is a presence storm and an `in self._open` answer is a lost close."""
    st, log, writer = _streams(monkeypatch)
    dev = ids.new_id('device')
    a1, first = st._register(dev, _Conn())
    assert first is True
    a2, _ = st._register(dev, _Conn())
    a3, first = st._register(dev, _Conn())                     # a1 superseded, out of the pool
    assert first is False and st.count() == 2
    assert st._unregister(a1) is False                         # not the device's last
    assert st._unregister(a2) is False
    assert st._unregister(a3) is True                          # now it was the last


def test_close_device_closes_only_its_own_streams_and_never_waits_on_a_stalled_one(monkeypatch):
    """sse.py:128-135: closing flags its device, wakes the writer so waiting streams
    see it, and returns after `timeout` even if `done` never comes — drop the timeout
    (or thread the match wrong) and this either hangs or closes the wrong device."""
    st, log, writer = _streams(monkeypatch)
    a = st._register('dvc_a', _Conn())[0]
    b = st._register('dvc_b', _Conn())[0]
    a.started = b.started = True
    t0 = time.monotonic()
    st.close_device('dvc_a', timeout=0.2)                      # a.done never set: it returns
    assert 0.15 <= time.monotonic() - t0 < 1.0                 # it did wait, and bounded so
    assert a.closing.is_set() and writer.wakes >= 1
    assert not b.closing.is_set() and st.count() == 2          # still counted until it ends
    a.done.set()
    st.close_device('dvc_a', timeout=0.2)                      # now it waits and returns at once
    b.done.set()
    st.close_all(timeout=0.2)
    assert b.closing.is_set()

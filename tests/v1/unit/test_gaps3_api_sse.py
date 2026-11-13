"""T-1161: the ten highest-risk uncovered branches of archeus/api/sse.py lines
1-232 inclusive (tip 56d53504), as units. Fail-closed and denial first, then
boundaries, then error paths.

The ten final branches, ranked by risk, with the probe each one came from:

1. sse.py:151-153 + 226-228 (probe 1, revoked token) — the per-wake credential
   check is the slice's only token judgement and it must fail CLOSED: a missing,
   hash-mismatched, revoked, inactive or expired row is False, it is asked once
   per wake with the stream's own hash, and the revocation preempts the page
   that arrived with it. [test_the_per_wake_credential_check_fails_closed]
2. sse.py:169-180 (probe 6, disconnect releases once) — a client that dies
   before the 200 releases its slot, hangs up its socket, pairs the two traces
   with `client_gone` and lets the next stream be the device's first again.
   [test_a_client_that_dies_before_the_200_frees_its_slot]
3. sse.py:176-180 + 213 (probe 6) — a client that dies mid-replay: the write
   error is not swallowed, nothing is retried, and the teardown still runs.
   [test_a_client_that_dies_mid_replay_frees_its_slot]
4. sse.py:231-232 (probe 10, origin invalidation) — a withdrawn origin stops
   the NEXT write: a page already queued is never read, let alone written.
   [test_a_withdrawn_origin_never_writes_the_pending_page]
5. sse.py:171-172 + 178-179 (replaces probe 2, already covered) — presence is
   traced on transitions only, inside serve: a device's second stream traces
   neither open nor close while its first is still open.
   [test_a_devices_second_stream_traces_no_transition]
6. sse.py:123-125 + 178 (probe 6, replaces probe 4, already covered) — a stream
   superseded while it serves releases no slot, traces no close and cannot
   crash the teardown with a second removal.
   [test_a_superseded_stream_in_flight_releases_nothing]
7. sse.py:65-69 (replaces probe 5, whose single-prefix intersection is covered)
   — the subscription filter over SEVERAL projects and SEVERAL type prefixes:
   the whole tuple is a prefix set, and the two halves intersect.
   [test_a_type_filter_of_two_prefixes_keeps_either]
8. sse.py:210-216 (probe 5 composition; replaces probe 3, which is inapplicable)
   — what the filter drops still moves the cursor on the raw page tail and
   produces no write at all, not even an empty one.
   [test_dropped_events_move_the_cursor_and_write_nothing]
9. sse.py:219-223 (probe 9, heartbeat keeps cursor) — the heartbeat is a bare
   comment: it carries no `id:` (which would corrupt the client's reconnect
   cursor) and the page after it still starts at the same cursor.
   [test_a_heartbeat_carries_no_id_and_moves_no_cursor]
10. sse.py:135-138 (probe 8, shared close deadline) — one deadline serves the
    whole device: the second wedged stream is waited on with what is LEFT of
    it, clamped at zero, and both are hung up while another device is untouched.
    [test_two_wedged_streams_share_one_close_deadline]

Probes dropped as already covered or inapplicable, with the evidence:
- probe 2 (a stream-limit failure leaks no slot): tests/v1/unit/test_gaps_api_sse.py:158
  (`test_a_full_pool_refuses_a_new_device_with_429_and_writes_nothing`) already asserts
  `st.count() == sse.MAX_STREAMS`, `writer.waits == []` and `req.runs == []`, and
  tests/v1/unit/test_stream_takeover_units.py:52 covers the capped device's takeover.
- probe 3 (stopping refuses registration): not a branch of this slice. `_register`
  (sse.py:103-119) consults no `stopping` and must not: docs/architecture/p3.5b-design-gate.md
  §5.4 step 2 (that file, line 343) requires a stream alive at shutdown to be answered with an
  `event: shutdown` frame and EOF, never a refusal, and the frame is covered by
  tests/v1/unit/test_gaps_api_sse.py:300
  (`test_a_shutdown_writes_its_frame_and_stopping_outranks_a_pending_close`). The refusal the
  probe actually describes lives one layer up, in `if self.api.stopping: raise
  Refused(503, 'core_stopping')` (archeus/api/server.py:443-444), where
  tests/v1/unit/test_gaps_api_server.py:553
  (`test_shutdown_refuses_a_known_route_only_after_the_route_is_known`) already GETs the stream
  route itself and asserts `503 core_stopping`. Nothing inside lines 1-232 is left unproven.
- probe 4 (cursor pruned after registration): tests/v1/unit/test_gaps_api_sse.py:355
  (`test_a_prune_that_overtakes_a_stream_writes_one_cursor_expired_frame_then_ends`)
  already raises CursorExpired from the first page after registration.
- probe 5 as literally named (project AND type intersection): covered by
  tests/v1/unit/test_presence_units.py:108 and tests/v1/unit/test_gaps_api_routes.py:685,
  both with ONE project and ONE prefix; branch 7 above adds the untested tuple case.

Same in-process style as the neighbouring sse units: the pool and `serve()` are driven
directly against a fake db, writer, log and request object, with the outbox reads faked
at the module seam the other sse units use and the credential READ (`queries.credential`)
faked with invented values while the real `auth.live` judges them. Nothing at all is
patched on `Streams`: every stream is ended by what the client, the pool, the log or the
credential table really does, so an end condition cannot silently mask another one.
No processes, no sockets, no threads, no real sleep; the clock and the `done` event are
faked where a deadline or a heartbeat is what is being measured, so the timing assertions
are exact and identical on Windows and Linux. The tests create no file, directory or home.
"""

import socket
import types

import pytest

from archeus.api import sse
from archeus.core.application import commands
from archeus.core.domain import ids
from archeus.core.domain.events import new_event
from archeus.core.domain.values import Ref
from archeus.infra.eventlog import outbox

MAX = outbox.MAX_LIMIT
FUTURE = '2999-01-01T00:00:00.000Z'
PAST = '2000-01-01T00:00:00.000Z'
REVOKED_AT = '2026-01-01T00:00:00.000Z'


class _Conn:
    """The server-side socket of a stream."""

    def __init__(self):
        self.shut, self.attempts = False, 0

    def shutdown(self, how):
        self.attempts += 1
        assert how == socket.SHUT_RDWR
        self.shut = True


class _Writer:
    """The commit notifier: every wait is recorded and a test drives what happens in it."""

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
    """The committed log behind `db.read()`: queued pages, a tail, and every read
    counted. `tokens` is the invented credential table the fake `credential` reads."""

    def __init__(self, head=0):
        self.head, self.stopping = head, False
        self.queue, self.tail, self.reads = [], [], []
        self.tokens, self.credential_calls, self.open_reads = {}, [], 0

    def read(self):
        log = self

        class _Ctx:
            def __enter__(self):
                log.open_reads += 1
                return ('conn', log.open_reads)

            def __exit__(self, *exc):
                return False
        return _Ctx()

    def events_after(self, conn, cursor, *, limit):
        self.reads.append((cursor, limit))
        if limit == 1:                                    # serve's cursor probe pre-200
            return []
        return self.queue.pop(0) if self.queue else self.tail


class _Req:
    """The face of server.Handler that serve(), _loop() and _trace() touch. The 200 and
    the writes can be made to fail the way a dead client makes them fail: an OSError
    that got nothing out."""

    def __init__(self, device_id=None, conn=None):
        self.principal = {'device_id': device_id or ids.new_id('device'),
                          'principal_id': ids.new_id('principal'), 'scopes': ['observe']}
        self.connection = conn
        self.token_hash = 'th_' + self.principal['device_id'][-16:]
        self.writes, self.started, self.runs = [], 0, []
        self.started_raises, self.write_fail, self.write_attempts = None, None, 0
        self.origin_ok, self.origin_checks = True, 0

    def start_stream(self):
        self.started += 1
        if self.started_raises is not None:
            raise self.started_raises

    def write(self, data):
        if self.write_fail is not None:
            self.write_attempts += 1                # the OS took nothing
            raise self.write_fail
        self.write_attempts += 1
        self.writes.append(data)

    def run(self, fn, kwargs, *, keyed=True):
        self.runs.append((fn, dict(kwargs), keyed))

    def origin_holds(self):
        self.origin_checks += 1
        return self.origin_ok


def _streams(monkeypatch, head=0, heartbeat_s=15.0):
    """A Streams over a fake log/writer, with the credential READ (never the judgement)
    faked: `auth.live` in sse.py:153 stays the real one."""
    log = _Log(head)
    monkeypatch.setattr(sse.outbox, 'head', lambda conn: log.head)
    monkeypatch.setattr(sse.outbox, 'events_after', log.events_after)
    monkeypatch.setattr(sse, 'queries', types.SimpleNamespace(
        credential=lambda conn, token_hash: (log.credential_calls.append((conn, token_hash)),
                                             log.tokens.get(token_hash))[1]))
    writer = _Writer()
    db = types.SimpleNamespace(writer=writer, read=log.read)
    return sse.Streams(db, heartbeat_s=heartbeat_s, stopping=lambda: log.stopping), log, writer


def _live(hash_, **over):
    return dict({'token_hash': hash_, 'revoked_at': None,
                 'device_state': 'ACTIVE', 'expires_at': FUTURE}, **over)


def _live_token(log, req):
    """The invented row that makes `req`'s credential live (sse.py:153 judges it for real)."""
    log.tokens[req.token_hash] = _live(req.token_hash)
    return req


def _ev(seq, type_='mission.updated', kind='mission', ident=None, project=None):
    return new_event(type_, Ref(kind, ident or ids.new_id(kind)),
                     Ref('system', ids.new_id('principal')), payload={},
                     seq=seq, project=project)


def _ids(req):
    return [int(line[4:]) for chunk in req.writes for line in chunk.decode('utf-8').split('\n')
            if line.startswith('id: ')]


class _Wedged:
    """A stream's `done` event whose client never stops reading: `wait` records the time
    it was given, consumes it from the fake clock, and says the stream did not finish."""

    def __init__(self, clock):
        self.clock, self.timeouts = clock, []

    def is_set(self):
        return False

    def wait(self, timeout):
        self.timeouts.append(timeout)
        self.clock[0] += timeout + 0.01                 # the whole budget went by
        return False


# ── 1. fail-closed: the per-wake credential check ──

def test_the_per_wake_credential_check_fails_closed(monkeypatch):
    """sse.py:151-153 and 226-228. Every existing test hands `_still_valid` a verdict
    (tests/v1/unit/test_gaps_api_sse.py:141, tests/v1/integration/test_sse.py:150), so
    the row-to-verdict judgement itself has never run in a unit test: it must read the
    row for the hash it was GIVEN, inside one read snapshot, and answer False — never
    fail open — for a row that is gone, another token's, revoked, not ACTIVE or expired.
    And it must be asked again on EVERY wake (p3.5b-design-gate.md:398), so a revocation
    that lands late ends the stream in that same wake, before its page is read."""
    st, log, writer = _streams(monkeypatch)
    hash_ = 'th_' + 'a' * 32
    log.tokens[hash_] = _live(hash_)
    assert st._still_valid(hash_) is True
    assert log.credential_calls == [(('conn', 1), hash_)] and log.open_reads == 1
    for field, value in (('token_hash', 'th_' + 'b' * 32),      # another token's row
                         ('revoked_at', REVOKED_AT),
                         ('device_state', 'REVOKED'),
                         ('expires_at', PAST)):
        log.tokens[hash_] = _live(hash_, **{field: value})
        assert st._still_valid(hash_) is False                  # fail closed, no exceptions
    log.tokens[hash_] = None                                    # the row is gone
    assert st._still_valid(hash_) is False
    # the same judgement, with nothing patched anywhere, ends a live stream
    st, log, writer = _streams(monkeypatch)
    req = _Req(conn=_Conn())
    log.tokens[req.token_hash] = _live(req.token_hash)

    def on_wait(n, w):
        if n == 3:                                              # revoked at the third wake
            log.tokens[req.token_hash] = _live(req.token_hash, revoked_at=REVOKED_AT)
            log.queue.append([_ev(9)])                          # and a page arrived with it
    writer.on_wait = on_wait
    assert st.serve(req, 0) is None
    assert [h for _, h in log.credential_calls] == [req.token_hash] * 3    # once per wake
    assert req.writes == [] and len(log.queue) == 1              # that page was never read
    assert req.runs[-1][0] is commands.record_connection
    assert req.runs[-1][1]['reason'] == 'revoked' and st.count() == 0


# ── 2-4. denial: a client and a credential that go away ──

def test_a_client_that_dies_before_the_200_frees_its_slot(monkeypatch):
    """sse.py:169-180: `start_stream` is the first byte out and it can face a dead peer
    (its `wfile.flush()`, server.py:340). Nothing covers it: tests/v1/unit/test_gaps_api_sse.py:372
    only makes the HANGUP fail, after a full stream. The finally must still hang the
    socket up, leave the pool (the close trace sees an empty pool and a hung-up socket,
    so it cannot run before them) and pair the traces with the contract's `client_gone`
    (p15-design-gate.md:158) — an unpaired open is a presence lie and a leaked slot
    leaves the device refused at its cap forever."""
    st, log, writer = _streams(monkeypatch)
    conn = _Conn()
    req = _Req(conn=conn)
    req.started_raises = ConnectionResetError(104, 'Connection reset by peer')
    seen = []

    def run(fn, kwargs, *, keyed=True):
        req.runs.append((fn, dict(kwargs), keyed))
        seen.append((st.count(), conn.shut, [s.conn for s in st._open]))
    req.run = run
    with pytest.raises(ConnectionResetError):                # the server logs it; serve does not eat it
        st.serve(req, 0)
    assert st.count() == 0 and conn.shut is True
    assert seen[1][:2] == (0, True)                          # released and hung up before the close trace
    assert [(r[0], r[1]['opened']) for r in req.runs] == [      # paired, once each, the connection trace
        (commands.record_connection, True), (commands.record_connection, False)]
    assert [r[2] for r in req.runs] == [False, False]               # a trace is never a keyed command
    assert req.runs[0][1]['reason'] is None and req.runs[1][1]['reason'] == 'client_gone'
    assert req.runs[0][1]['connection_id'] == req.runs[1][1]['connection_id']
    assert writer.waits == [] and req.write_attempts == 0          # the loop was never entered
    assert st._register(req.principal['device_id'], _Conn())[1] is True   # first again: no leak


def test_a_client_that_dies_mid_replay_frees_its_slot(monkeypatch):
    """sse.py:176-180 with 213: `req.write` is server.py:343-345, a plain blocking
    `wfile.write` plus `flush`, so a
    client that stops reading raises mid-frame. tests/v1/unit/test_gaps_api_sse.py:372
    fails the shutdown() of the socket, not the write, and no existing test asserts the
    reason of this end at unit level. The error must escape (a swallowed one leaves the
    stream "clean" and the server never logs a broken client), nothing may be retried,
    and the teardown must still run exactly once."""
    st, log, writer = _streams(monkeypatch)
    req = _Req(conn=_Conn())
    req.write_fail = BrokenPipeError(32, 'Broken pipe')
    log.queue = [[_ev(1), _ev(2)]]
    with pytest.raises(BrokenPipeError):
        st.serve(req, 0)
    assert req.write_attempts == 1 and req.writes == []           # one attempt, nothing out
    assert writer.waits == [] and req.origin_checks == 0          # the loop was left, not parked
    assert [(r[0], r[1]['opened']) for r in req.runs] == [
        (commands.record_connection, True), (commands.record_connection, False)]
    assert req.runs[-1][1]['reason'] == 'client_gone'
    assert st.count() == 0 and st.connections(req.principal['device_id']) == []


def test_a_withdrawn_origin_never_writes_the_pending_page(monkeypatch):
    """sse.py:231-232: the origin is re-checked every wake. tests/v1/unit/
    test_gaps_api_sse.py:213 drives it over an EMPTY log, so it proves the reason string
    but not the denial: with a page already queued behind the wake, dropping the check
    ships that page to a client whose tunnel is gone. Nothing of it may be read either."""
    st, log, writer = _streams(monkeypatch)
    req = _live_token(log, _Req(conn=_Conn()))
    log.queue = [[_ev(1)], [_ev(2)]]                              # 2 is committed as the tunnel dies

    def on_wait(n, w):
        if n == 1:
            req.origin_ok = False
    writer.on_wait = on_wait
    assert st.serve(req, 0) is None
    assert _ids(req) == [1] and b'id: 2' not in b''.join(req.writes)
    assert len(log.queue) == 1 and log.reads == [(0, 1), (0, MAX)]    # the pending page stayed unread
    assert req.origin_checks == 1                                      # one check per wake
    assert req.runs[-1][1]['reason'] == 'origin_lost' and st.count() == 0


# ── 5-6. the pool's promises about presence and slots ──

def test_a_devices_second_stream_traces_no_transition(monkeypatch):
    """sse.py:171-172 and 178-179: presence is traced on the DEVICE's transitions only.
    tests/v1/unit/test_gaps_api_sse.py:190 and :300 both serve a device's ONLY stream, so
    `first` is always True and the close is always the device's last: neither the `if
    first` guard nor the `if self._unregister(...)` guard has ever been false under serve.
    A device with two tabs (p15 §5 D4) must produce no trace for the second one at all."""
    st, log, writer = _streams(monkeypatch)
    dev = ids.new_id('device')
    peer, first = st._register(dev, _Conn())
    assert first is True and peer.started is False

    def on_wait(n, w):
        if n == 1:
            st._open[-1].closing.set()                # a close from outside: why stays 'revoked'
    writer.on_wait = on_wait
    req = _live_token(log, _Req(device_id=dev, conn=_Conn()))
    assert st.serve(req, 0) is None
    assert req.runs == []                                            # neither opened nor closed
    assert req.started == 1                                          # it did get its 200
    assert st.count() == 1 and st.connections(dev) == [peer.connection_id]
    assert peer.conn.shut is False and not peer.closing.is_set()     # its sibling was untouched


def test_a_superseded_stream_in_flight_releases_nothing(monkeypatch):
    """sse.py:123-125 with 178: the stream a takeover removed from the pool is not the
    device's last and must not be answered as if it were. tests/v1/unit/
    test_gaps_api_sse.py:334 and tests/v1/unit/test_fix_sse.py:31 call `_unregister`
    directly; neither ever runs a superseded stream's own teardown. Removing the guard
    turns the teardown into a ValueError escaping serve; answering True anyway writes a
    `device.stream_closed` for a device that is still streaming (a presence lie) and
    drops the pool count by one too many."""
    st, log, writer = _streams(monkeypatch)
    dev = ids.new_id('device')
    req = _live_token(log, _Req(device_id=dev, conn=_Conn()))
    held = {}

    def on_wait(n, w):
        if n == 1:
            held['s'] = [s for s in st._open if s.conn is req.connection][0]
            new = [st._register(dev, _Conn())[0] for _ in range(2)]      # it takes the cap
            held['new'] = new
            held['during'] = (st.count(), st.connections(dev))           # it left the pool already
    writer.on_wait = on_wait
    assert st.serve(req, None) is None                              # the second removal is quiet
    assert held['during'] == (2, [s.connection_id for s in held['new']])   # a dead stream counts for none
    assert st.count() == 2 and st.connections(dev) == [s.connection_id for s in held['new']]
    assert [(r[0], r[1]['opened']) for r in req.runs] == [(commands.record_connection, True)]   # only its own open
    assert held['s'].done.is_set() and held['s'].conn.shut is True   # hung up by the takeover
    assert all(not s.closing.is_set() for s in held['new'])          # the live two were not touched


# ── 7-9. boundaries: the filter and the heartbeat ──

def test_a_type_filter_of_two_prefixes_keeps_either():
    """sse.py:65-69. tests/v1/unit/test_presence_units.py:108 and tests/v1/unit/
    test_gaps_api_routes.py:685 both pass ONE project and ONE prefix, so nothing pins
    that `types` is a whole tuple (routes.py:210 forwards every `type=` the query
    repeats) nor that the two halves INTERSECT rather than union: `types[:1]`,
    `startswith(types[0])`, or `or` instead of `and` all survive there. A list is what
    the route gives, so the frozenset/tuple conversion is exercised too."""
    everything = sse.narrowing()
    keep = sse.narrowing(['prj_a', 'prj_b'], ['mission.', 'execution.'])   # lists, as routes.py does
    cases = [('mission.created', 'prj_b', True),        # the second project
             ('execution.output', 'prj_a', True),       # the SECOND prefix
             ('execution.output', None, True),          # an event with no project is always in scope
             ('approval.requested', 'prj_a', False),    # the type fails: the project cannot save it
             ('mission.created', 'prj_c', False),       # the project fails: the type cannot save it
             ('missionx.created', 'prj_a', False)]      # a prefix, not a substring
    for type_, project, want in cases:
        e = types.SimpleNamespace(type=type_, project=project)
        assert keep(e) is want, (type_, project)
        assert everything(e) is True                    # it can only narrow (p15 §11)
    assert sse.narrowing([], ['mission.'])(types.SimpleNamespace(type='mission.x', project='prj_z'))
    assert sse.narrowing(['prj_a'], ())(types.SimpleNamespace(type='anything', project='prj_a'))
    assert not sse.narrowing(['prj_a'], ())(types.SimpleNamespace(type='anything', project='prj_z'))


def test_dropped_events_move_the_cursor_and_write_nothing(monkeypatch):
    """sse.py:210-216. tests/v1/unit/test_gaps_api_sse.py:225 filters only the client's
    own presence traces, with the default keep: the `keep` half of the comprehension and
    the `if shown` guard have never been false under serve. A page whose events the
    subscription rejects must produce NO write (not an empty one) and must still move the
    cursor to the raw page tail — `cursor = shown[-1].seq` replays that range forever,
    and a cursor that skips the dropped events loses them for a widened filter later."""
    st, log, writer = _streams(monkeypatch)
    req = _live_token(log, _Req(conn=_Conn()))
    mine, theirs, elsewhere = (ids.new_id('project') for _ in range(3))
    keep = sse.narrowing([mine], ['mission.'])
    log.queue = [[_ev(1, 'approval.requested', 'approval', project=theirs),
                  _ev(2, 'mission.created', 'mission', project=elsewhere)],
                 [_ev(3, 'mission.created', 'mission', project=mine)]]

    def on_wait(n, w):
        if n == 2:                                              # the credential dies with the wait
            log.tokens[req.token_hash] = _live(req.token_hash, revoked_at=REVOKED_AT)
    writer.on_wait = on_wait
    assert st.serve(req, 0, keep) is None
    assert len(req.writes) == 1 and req.writes[0].startswith(b'id: 3\nevent: mission.created\n')
    assert b'approval.requested' not in b''.join(req.writes) and b'\n\n\n' not in b''.join(req.writes)
    assert log.reads == [(0, 1), (0, MAX), (2, MAX)]            # the RAW tail, dropped or not
    assert st.count() == 0


def test_a_heartbeat_carries_no_id_and_moves_no_cursor(monkeypatch):
    """sse.py:219-223. tests/v1/unit/test_gaps_api_sse.py:334 measures the heartbeat over
    an always-empty log, so it proves the budget but not that the comment is inert: an
    `id:` line on it would overwrite the client's Last-Event-ID (its reconnect cursor),
    and a heartbeat that advanced the server's cursor would silently skip whatever
    committed while the client sat idle. The clock is faked, so the budget arithmetic is
    exact on any host."""
    clock = [1024.0]
    monkeypatch.setattr(sse, 'time', types.SimpleNamespace(monotonic=lambda: clock[0]))
    st, log, writer = _streams(monkeypatch, heartbeat_s=5.0)
    req = _live_token(log, _Req(conn=_Conn()))

    def on_wait(n, w):
        if n == 1:
            clock[0] += 6.0                                     # idle past the whole budget
        if n == 2:
            log.queue.append([_ev(1), _ev(2)])                   # committed during the heartbeat
        if n == 3:
            log.tokens[req.token_hash] = _live(req.token_hash, revoked_at=REVOKED_AT)
    writer.on_wait = on_wait
    assert st.serve(req, 0) is None
    assert req.writes[0] == b': hb\n\n'                          # exactly the comment
    assert b'id:' not in req.writes[0] and b'event:' not in req.writes[0]
    assert len(req.writes) == 2 and req.writes[1].startswith(b'id: 1\n')   # one hb, then the frames
    assert _ids(req) == [1, 2]                                   # nothing was skipped by it
    assert log.reads == [(0, 1), (0, MAX), (0, MAX), (0, MAX)]   # probe + three pages, all at cursor 0
    assert [w['timeout'] for w in writer.waits] == [5.0, 5.0, 5.0]
    assert req.runs[-1][1]['reason'] == 'revoked'


# ── 10. error path: a close that must not wait forever, twice ──

def test_two_wedged_streams_share_one_close_deadline(monkeypatch):
    """sse.py:135-138. tests/v1/unit/test_fix_sse.py:14 and tests/v1/unit/
    test_gaps_api_sse.py:453 each close ONE wedged stream, so `deadline` is never used
    twice: moved into the loop it waits the full timeout per stream and a revoke that
    carries two tabs (p15 §6, PER_DEVICE=2) takes twice as long to answer, and without
    the `max(0.0, ...)` clamp the second wait is handed a negative budget. Both are hung
    up, and a third device is neither flagged nor cut."""
    clock = [1024.0]
    monkeypatch.setattr(sse, 'time', types.SimpleNamespace(monotonic=lambda: clock[0]))
    woke = []
    db = types.SimpleNamespace(writer=types.SimpleNamespace(wake=lambda: woke.append(1)))
    st = sse.Streams(db)
    a, _ = st._register('dvc_a', _Conn())
    b, _ = st._register('dvc_a', _Conn())
    other, _ = st._register('dvc_b', _Conn())
    for s in (a, b, other):
        s.started = True
    wa, wb = _Wedged(clock), _Wedged(clock)
    a.done, b.done = wa, wb
    st.close_device('dvc_a', timeout=0.25)
    assert wa.timeouts == [0.25] and wb.timeouts == [0.0]         # one deadline, spent once
    assert a.closing.is_set() and b.closing.is_set()
    assert a.conn.shut is True and b.conn.shut is True            # both wedged writers cut off
    assert woke == [1]                                            # one wake, before the waiting
    assert not other.closing.is_set() and other.conn.shut is False
    assert other.done.is_set() is False and st.count() == 3       # still theirs until they end

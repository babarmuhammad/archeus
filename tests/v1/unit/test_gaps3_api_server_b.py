"""T-1159 · the ten highest-risk uncovered branches of `archeus/api/server.py`
lines 524-564 (inclusive): the lingering close that drains a refused body
(`Handler._linger`, 524-539) and the listener that binds the loopback port
(`Server`, 544-564). Ranked fail-closed and denial first, then boundaries, then
error paths. Two extra fault compositions (11, 12) close the same `try`.

Nothing here edits a source file, starts a server, opens a socket, spawns a
process, sleeps or touches anything outside `tmp_path`. The handler is built with
`object.__new__` (the seam `tests/v1/unit/test_gaps_api_server.py:439` and
`tests/v1/unit/test_pins_api_server.py:88` already use), the drain's whole outside
world is one fake connection plus one scripted `rfile`, the clock is a scripted
list, and the listener's socket is an ordered log of what was asked of it. The
fake connection has no `sendall`/`write`/`send` at all, so a drain that tried to
answer a second time raises instead of quietly doing it. Platform-neutral: the
Windows half of `server_bind` and the Windows-side `allow_reuse_address` are
reached through faked OS seams (`server.sys`, `server.socket`, `sys.platform` at
import), so the same file is meaningful on this Linux container and on the Windows
review box, where the POSIX half is the faked one.

THE TEN FINAL BRANCHES (source file:line → test), with the closest existing
coverage and the assertion it does not make. Existing coverage read first, as the
card directs: `tests/v1/unit/test_fix_p_api_server.py`, `test_pins_api_server.py`,
`test_gaps2_api_server_a.py`, `test_gaps_api_server.py`,
`tests/v1/contract/test_core_client.py`, `tests/v1/unit/test_api_errors.py`, plus
`tests/v1/integration/test_core_lifecycle.py` as read-only context.

1. server.py:558-559 (`server_bind`, the win side) — `SO_EXCLUSIVEADDRUSE` must be
   armed BEFORE `socketserver.TCPServer.server_bind` binds the port, and it must be
   the exclusive option rather than the squatting-friendly `SO_REUSEADDR`.
   Closest: `test_gaps_api_server.py:534` `test_a_second_live_listener_on_the_
   loopback_port_is_refused` — `skipif win32`, so on the box that owns this branch
   it does not run, and it never looks at a `setsockopt` at all.
   → `test_a_windows_bind_arms_the_exclusive_option_first`
2. server.py:550, the `win` side — `allow_reuse_address` decided in the class body.
   Closest: `test_gaps_api_server.py:538`, which compares the attribute with the
   RUNNING platform and is itself inside the `skipif win32` test: on Linux
   `allow_reuse_address = True` (the squatting bug) passes the whole suite.
   → `test_a_windows_import_never_allows_address_reuse`
3. server.py:558 False, 563-564 — off Windows no Windows option is set at all, the
   bind still goes through `TCPServer`, and the listener still names itself by
   number. Closest: `test_gaps_api_server.py:543` and
   `test_core_lifecycle.py:133`: both build a REAL listener, so they pin the values
   but can never see the ABSENCE of a privileged `setsockopt`, and the reverse-DNS
   one only pins `getfqdn` for the platform it runs on.
   → `test_a_posix_bind_sets_no_windows_socket_option`
4. server.py:550, the POSIX side — the same attribute's other half: `False` there
   strands a restart behind its own TIME_WAIT connections. No test evaluates the
   class body under a platform name that is not the running one.
   → `test_a_posix_import_allows_reuse_past_time_wait`
5. server.py:532 + 537 — `while left > 0 ...: left -= len(chunk)`: the byte budget
   is spent by the bytes actually READ, not by the buffer asked for, and the loop
   stops the round `left` reaches zero. Closest:
   `test_gaps_api_server.py:445` `test_the_lingering_close_stops_at_its_byte_bound`
   feeds 65536-byte chunks against a 65536-multiple budget, where `left -= 65536`
   and `left -= len(chunk)` are the same number, so it cannot see the budget being
   spent by the wrong measure. → `test_the_linger_counts_the_bytes_it_actually_read`
6. server.py:532, the clock test on a LATER round — the deadline is re-read every
   round, so a client that stalls mid-drain is dropped mid-drain. Closest:
   `test_gaps_api_server.py:457` sets `LINGER_S = 0.0`, where the loop body never
   runs at all: hoisting the clock check out of the loop is invisible to it.
   → `test_the_linger_stops_when_the_deadline_passes_midway`
7. server.py:535-536 — `if not chunk: return`: the peer's EOF ends the drain at
   once. No existing test reaches it; every `_linger` fake answers with bytes
   forever (`test_gaps_api_server.py:414` `_Pipe`), so the loop always left through
   one of its bounds. → `test_the_peers_eof_ends_the_linger_at_once`
8. server.py:533 — `max(0.01, deadline - time.monotonic())`: the clock is read a
   second time AFTER the loop agreed there was time left, so the slice can be under
   the floor (or gone). The floor keeps `settimeout` from arming an already-expired
   socket, which would drop the tail of the refusal the linger exists to deliver.
   Closest: `test_gaps_api_server.py:435` (`_Conn.settimeout`) is a no-op, so no
   existing test ever looks at the value, let alone at a clock that moves.
   → `test_the_linger_never_arms_a_timeout_below_the_floor`
9. server.py:533, the other half of the same expression — the armed timeout is THIS
   peek's remaining budget: never 0 or negative, never more than `LINGER_S`, never
   the absolute deadline. The same no-op fake lets `settimeout(0)`,
   `settimeout(LINGER_S)` and `settimeout(deadline)` all through.
   → `test_the_linger_arms_only_the_time_left_to_run`
10. server.py:531 + 538 — the `shutdown(SHUT_WR)` itself raising `OSError` (the peer
   is gone: ENOTCONN/ENOTSOCK) is swallowed, before a single peek. Closest:
   `test_gaps_api_server.py:468` `test_the_lingering_close_survives_a_client_that_
   resets` fails the READ instead, by which time the shutdown and the re-arm have
   both succeeded, so it cannot see a drain that peeks at a socket whose half-close
   failed. → `test_a_shutdown_that_raises_lingers_over_nothing`

WHAT BECAME OF THE TEN STARTING PROBES. Six are open ground and stayed (shutdown
error → 10, empty read → 7, the timeout floor when the clock advances → 8, the
nonnegative minimum → 9, the Windows option before the bind → 1, POSIX omitting it
→ 3). Four were already covered, and were replaced by an open branch inside the
same slice:

* probe 2, the read error at `self.rfile.read1` (534) — already the
  `_Pipe(fail=ConnectionResetError(...))` of `test_gaps_api_server.py:468`. Its
  place is taken by the read path's other fault point, the re-arm of 533 (extra 11).
* probe 4, exact byte exhaustion (532, 537) — the exact stop is pinned by
  `test_gaps_api_server.py:445`, but only ever on whole 65536-byte chunks; 5 keeps
  the boundary where the two measures of the budget disagree.
* probe 5, the elapsed deadline (532) — `test_gaps_api_server.py:457` only has
  `LINGER_S = 0.0`, where the loop never runs; 6 takes the re-check between peeks.
* probe 10, the loopback bind without a reverse DNS lookup (560-564) —
  `tests/v1/integration/test_core_lifecycle.py:133` patches `socket.getfqdn` to
  explode around a real `Server(None, 0)`. 3 keeps that rule visible from the unit
  side too, and the two freed slots went to the import-time halves of 550 (2, 4).

Extras 11 and 12 are fault compositions of the same `try` (530-539): the re-arm
failing, and the `except` being narrower or wider than `OSError`.

Each test below names the one source branch whose removal or inversion it catches;
a test that still passes on the wrong code is not one of these. All 12 were run
against 20 in-memory mutants of those lines (`left -= 65536`, `left >= 0`, the
clock test hoisted out of the loop, the EOF `return` dropped, `settimeout` armed
with 0.0005 / 0.0 / `LINGER_S` / the absolute deadline, `except
ConnectionResetError`, `except Exception`, the half-close dropped, the Windows
option always / never / armed with 0 / armed after the bind, HTTPServer's bind
called, the numeric name dropped, `allow_reuse_address` forced True, forced False
and keyed on the wrong platform word): every mutant was killed by the test named
for it, and the table is in the T-1159 report.
"""

import importlib
import inspect
import socket
import sys
import types
from types import SimpleNamespace

import pytest

from archeus.api import server

PORT = 8777
READ_SIZE = 65536                     # the one buffer the drain reads with (server.py:534)
EXCLUSIVE = 'SO_EXCLUSIVEADDRUSE'     # stands in for the windows-only socket constant
HALF_CLOSE = socket.SHUT_WR           # what the linger promises the peer (server.py:531)
BIG = 1 << 20                         # a byte budget no test in here can spend
SHIPPED_REUSE = server.Server.allow_reuse_address       # the live class, unchanged by any fake


# ── the fakes: a connection, a body, a clock, and no OS ──

class _Conn:
    """The connection `_linger` half-closes. It records the two calls it makes and
    can fail either of them, because an `OSError` is the only thing the drain may
    swallow (server.py:538). It has no write method of any kind: the answer is
    already on the wire, and anything that tried to send again raises."""

    def __init__(self, shutdown_with=None, settimeout_with=None):
        self.shutdowns, self.timeouts = [], []
        self.shutdown_with, self.settimeout_with = shutdown_with, settimeout_with

    def shutdown(self, how):
        self.shutdowns.append(how)                        # the attempt is the evidence
        if self.shutdown_with is not None:
            raise self.shutdown_with

    def settimeout(self, seconds):
        self.timeouts.append(seconds)
        if self.settimeout_with is not None:
            raise self.settimeout_with


class _Pipe:
    """The unread body. `read1` answers from a script and then, once the script is
    spent, does what the test says: EOF (`then`, what a finished peer returns) or
    explode (`late`). `late` is deliberately NOT an `OSError`: a drain that reads
    past the peer's EOF is a bug in the code under test, and swallowing it would
    spin the test instead of failing it."""

    def __init__(self, chunks=(), then=b'', late=None, fail=None):
        self.chunks, self.then, self.late, self.fail = list(chunks), then, late, fail
        self.asked, self.served = [], []

    def read1(self, n):
        self.asked.append(n)
        if self.fail is not None:
            raise self.fail
        if self.chunks:
            chunk = self.chunks.pop(0)
        elif self.late is not None:
            raise self.late                                   # read past the peer's EOF
        else:
            chunk = self.then                                 # the peer has finished sending
        self.served.append(chunk)
        return chunk

    @property
    def read_bytes(self):
        return sum(len(c) for c in self.served)


class _Clock:
    """`time` as the drain sees it: `monotonic()` walks a scripted list and then
    holds its last value, so a test scripts exactly where the clock stands at each
    of the three places server.py:529-533 reads it (the deadline, the loop test and
    the remaining-time calculation)."""

    def __init__(self, *values):
        self.values, self.reads = list(values), []

    def monotonic(self):
        value = self.values.pop(0) if len(self.values) > 1 else self.values[0]
        self.reads.append(value)
        return value


def _lingering(monkeypatch, pipe, conn=None, clock=None, linger_s=None, linger_bytes=None):
    """A handler ready for one `_linger` over the fakes: `object.__new__` so no
    socket, no `rbufready`, no `BaseHTTPRequestHandler.__init__`, and the module's
    own clock and bounds replaced only for this test."""
    if clock is not None:
        monkeypatch.setattr(server, 'time', SimpleNamespace(monotonic=clock.monotonic))
    if linger_s is not None:
        monkeypatch.setattr(server, 'LINGER_S', linger_s)
    if linger_bytes is not None:
        monkeypatch.setattr(server, 'LINGER_BYTES', linger_bytes)
    h = object.__new__(server.Handler)
    h.rfile, h.connection = pipe, conn if conn is not None else _Conn()
    return h


# ── 1 and 3: the listener's bind, both platform halves ──

class _Sock:
    """The listener's socket as an ordered log: it answers what was asked of it and
    nothing that could hold a real port, so no bind ever reaches the OS."""

    def __init__(self, port=PORT):
        self.calls, self.port = [], port

    def setsockopt(self, level, option, value):
        self.calls.append(('setsockopt', level, option, value))

    def bind(self, address):
        self.calls.append(('bind', address))

    def getsockname(self):
        self.calls.append(('getsockname',))
        return ('127.0.0.1', self.port)


def _binding(monkeypatch, platform_name):
    """`Server.server_bind` run over the only OS facts it reads: the platform name
    (server.py:558) and the socket option constants (559). `SO_EXCLUSIVEADDRUSE`
    does not exist on Linux and `getfqdn` is patched so a reverse lookup is a
    failure rather than a 30 s stall, which is what makes the branch of the other
    platform reachable from either box. `allow_reuse_address` is pinned on the
    instance (its own two halves are tests 2 and 4) so the log holds only what
    `server_bind` itself arms."""
    monkeypatch.setattr(server, 'sys', SimpleNamespace(platform=platform_name))
    monkeypatch.setattr(server, 'socket', SimpleNamespace(
        SOL_SOCKET=socket.SOL_SOCKET, SO_EXCLUSIVEADDRUSE=EXCLUSIVE))
    lookups = []
    monkeypatch.setattr(socket, 'getfqdn', lambda *a, **k: lookups.append(a) or 'a-name')
    s = object.__new__(server.Server)
    s.socket, s.server_address = _Sock(), ('127.0.0.1', 0)
    s.allow_reuse_address, s.fqdn = False, lookups
    return s


def test_a_windows_bind_arms_the_exclusive_option_first(monkeypatch):
    """server.py:558-559 — on Windows the listener arms the exclusive option BEFORE
    it binds; after the bind the port is already open to a second socket, which is
    the squatter the comment at 546-547 is about. Inverting `startswith('win')`,
    moving the `setsockopt` below line 563 or dropping the value's `1` all die here,
    and no existing test can see it: the one that names this line is `skipif win32`
    (test_gaps_api_server.py:534) and never inspects a setsockopt."""
    s = _binding(monkeypatch, 'win32')
    s.server_bind()
    calls = s.socket.calls
    armed = [n for n, c in enumerate(calls) if c[0] == 'setsockopt']
    bound = [n for n, c in enumerate(calls) if c[0] == 'bind']
    assert armed and bound, calls                             # something was armed, and bound
    assert armed[0] < bound[0], calls                         # the option came first
    assert calls[armed[0]] == ('setsockopt', socket.SOL_SOCKET, EXCLUSIVE, 1)
    assert calls[bound[0]] == ('bind', ('127.0.0.1', 0))
    assert (s.server_name, s.server_port) == ('127.0.0.1', PORT)


def test_a_posix_bind_sets_no_windows_socket_option(monkeypatch):
    """server.py:558 False + 560-564 — off Windows NOTHING is armed (the absence of
    the privileged side effect is the whole assertion: the existing POSIX coverage
    builds a real listener at test_gaps_api_server.py:543 / test_core_lifecycle.py:133
    and can only ever see values, never absences), the bind still goes through
    `socketserver.TCPServer.server_bind`, and `HTTPServer.server_bind` — the one
    that resolves `getfqdn('127.0.0.1')` for a CGI-only server_name — stayed unused.
    Setting the option unconditionally, or calling the HTTPServer bind, fails here on
    either platform."""
    s = _binding(monkeypatch, 'linux')
    s.server_bind()
    assert [c for c in s.socket.calls if c[0] == 'setsockopt'] == [], s.socket.calls
    assert ('bind', ('127.0.0.1', 0)) in s.socket.calls
    assert (s.server_name, s.server_port) == ('127.0.0.1', PORT)
    assert s.fqdn == []                                       # no reverse DNS, no FQDN name


# ── 2 and 4: the attribute the class body decides once, at import ──

SERVER_IMPORTS = ('concurrent.futures', 'itertools', 'json', 'logging', 'os', 're',
                  'secrets', 'socket', 'socketserver', 'sys', 'threading', 'time',
                  'http.server', 'urllib.parse', 'archeus.core.application',
                  'archeus.core.domain.values', 'archeus.infra.eventlog',
                  'archeus.api.auth', 'archeus.api.origin', 'archeus.api.routes',
                  'archeus.api.schemas', 'archeus.api.sse')


def _imported_on(monkeypatch, platform_name):
    """`server.py` imported again with the OS's platform name faked. The two platform
    reads are not alike: `server_bind` asks at bind time (patchable on the live
    class, above) while `allow_reuse_address` is decided ONCE in the class body
    (server.py:550), so the only honest seam for the platform you are not on is to
    run that class body again. Everything the body imports is cached first, so the
    fake-platform window covers these module's own lines and no other module's import
    time; the live `archeus.api.server` is never reloaded."""
    for name in SERVER_IMPORTS:
        importlib.import_module(name)
    monkeypatch.setattr(sys, 'platform', platform_name)
    module = types.ModuleType('archeus.api.server_under_' + platform_name)
    module.__dict__.update({'__file__': server.__file__, '__package__': 'archeus.api',
                            '__spec__': server.__spec__})
    exec(compile(inspect.getsource(server), server.__file__, 'exec'), module.__dict__)
    return module


def test_a_windows_import_never_allows_address_reuse(monkeypatch):
    """server.py:550, the win side — `allow_reuse_address = not
    sys.platform.startswith('win')`. On Windows SO_REUSEADDR lets a second socket
    bind a port already in use, i.e. a squatter in front of the API, so the shipped
    value there must be False. The closest existing assertion
    (test_gaps_api_server.py:538) compares the attribute with the RUNNING platform
    and sits inside a `skipif win32` test, so `allow_reuse_address = True` passes the
    whole Linux suite; here the class body is run again under `win32`."""
    assert _imported_on(monkeypatch, 'win32').Server.allow_reuse_address is False
    assert server.Server.allow_reuse_address is SHIPPED_REUSE     # the live class untouched


def test_a_posix_import_allows_reuse_past_time_wait(monkeypatch):
    """server.py:550, the other half — POSIX keeps SO_REUSEADDR or a restart cannot
    bind its own port again until the last run's TIME_WAIT connections expire (a
    live listener still refuses it, which is what test_gaps_api_server.py:534 proves
    on this platform). Nothing evaluates the class body under a platform name that is
    not the running one, so `allow_reuse_address = False` is green on Windows and
    green for any fake Windows import; run under `linux` it is not."""
    assert _imported_on(monkeypatch, 'linux').Server.allow_reuse_address is True
    assert server.Server.allow_reuse_address is SHIPPED_REUSE     # the live class untouched


# ── 5, 6, 7: the drain is bounded in bytes, in time, and by the peer ──

def test_the_linger_counts_the_bytes_it_actually_read(monkeypatch):
    """server.py:532 + 537 — `while left > 0 ...: left -= len(chunk)`: the budget is
    spent by the bytes READ, not by the buffer asked for, and it stops as soon as it
    is spent, at the exact byte and not one peek later. The existing bound test
    (test_gaps_api_server.py:445) reads 65536-byte chunks against a 65536-multiple
    budget, where `left -= len(chunk)` and `left -= 65536` are the same number and
    the exact stop is only ever reached on a buffer-sized chunk. Here the final chunk
    is half a buffer: replace `len(chunk)` with the buffer size and this drains 1000
    bytes where it owes 2500; invert `left > 0` to `left >= 0` and it peeks again
    after the budget is exactly spent."""
    pipe = _Pipe(chunks=[b'x' * 1000, b'x' * 1000, b'x' * 500, b'x' * 1000], then=b'y' * 1000)
    h = _lingering(monkeypatch, pipe, clock=_Clock(0.0), linger_bytes=2500)
    h._linger()
    assert pipe.asked == [READ_SIZE] * 3                      # the budget, in three peeks
    assert pipe.read_bytes == 2500                            # exactly spent, in whole peeks
    assert 2500 <= pipe.read_bytes < 2500 + 1000              # and not one peek earlier
    assert h.connection.shutdowns == [HALF_CLOSE]             # the answer is already out
    assert h.connection.timeouts == [2.0] * 3                 # LINGER_S, the default budget


def test_the_linger_stops_when_the_deadline_passes_midway(monkeypatch):
    """server.py:532, the clock test on a LATER round — `time.monotonic() < deadline`
    is re-read every round, so a client that keeps the socket open but stops
    answering is dropped as soon as the budget is gone, mid-drain. The existing
    time-bound test (test_gaps_api_server.py:457) sets `LINGER_S = 0.0`, where the
    body never runs at all: hoisting the clock out of the loop, or testing it once,
    passes it and hangs here on a second peek."""
    pipe = _Pipe(chunks=[b'x' * 10], then=b'')                # a second peek would be EOF
    h = _lingering(monkeypatch, pipe, clock=_Clock(0.0, 1.0, 1.0, 5.0),
                   linger_s=5.0, linger_bytes=BIG)
    h._linger()
    assert pipe.asked == [READ_SIZE]                          # one peek, then the deadline
    assert h.connection.timeouts == [4.0]                     # armed with what was left
    assert h.connection.shutdowns == [HALF_CLOSE]


def test_the_peers_eof_ends_the_linger_at_once(monkeypatch):
    """server.py:535-536 — `if not chunk: return`: a peer that has finished sending
    is finished, and the drain stops instead of peeking at a dead socket until the
    deadline. NO existing test reaches this branch: every `_linger` fake answers with
    bytes for ever (test_gaps_api_server.py:414), so the loop has only ever left
    through one of its two bounds. `if chunk is None`, or the `return` dropped, spins
    here on the EOF until the `late` read raises."""
    pipe = _Pipe(chunks=[b''], late=RuntimeError('peeked again past the peer EOF'))
    h = _lingering(monkeypatch, pipe, clock=_Clock(0.0), linger_s=30.0, linger_bytes=BIG)
    h._linger()
    assert pipe.asked == [READ_SIZE]                          # the EOF was enough
    assert h.connection.timeouts == [30.0]                    # armed once, before that peek
    assert h.connection.shutdowns == [HALF_CLOSE]


# ── 8 and 9: the socket timeout the drain re-arms every round ──

def test_the_linger_never_arms_a_timeout_below_the_floor(monkeypatch):
    """server.py:533 — `max(0.01, deadline - time.monotonic())`: the clock is read a
    SECOND time, after the loop has already agreed there is time left, so what is
    left can be under the floor or gone. Arming 0.0 (or a negative) would time the
    socket out before the peer's next byte and lose the tail of the refusal the
    linger exists to deliver; the floor is what stops that. No existing test looks at
    the argument at all (`_Conn.settimeout` at test_gaps_api_server.py:435 is a
    no-op) and none moves the clock. Drop the `max` and the armed value here is
    0.0005."""
    pipe = _Pipe(chunks=[b'x' * 4096], then=b'')
    h = _lingering(monkeypatch, pipe, clock=_Clock(0.0, 0.999, 0.9995, 1.0),
                   linger_s=1.0, linger_bytes=BIG)
    h._linger()
    assert h.connection.timeouts == [0.01]                    # not 0.0005, not 0.0, not None
    assert pipe.asked == [READ_SIZE]
    assert h.connection.shutdowns == [HALF_CLOSE]


def test_the_linger_arms_only_the_time_left_to_run(monkeypatch):
    """server.py:533, the other half of the same expression — the armed timeout is
    THIS peek's remaining budget: exactly `deadline - now`, so never 0 or negative
    (already expired), never more than `LINGER_S` (a peek that outlives the whole
    linger), never the absolute deadline. Every existing fake ignores the argument,
    so `settimeout(0)`, `settimeout(LINGER_S)` and `settimeout(deadline)` are all
    invisible to them; here the two rounds must be 1.5 then 0.75 of a 2.0 s budget."""
    pipe = _Pipe(chunks=[b'x' * 100, b'y' * 100], then=b'')
    h = _lingering(monkeypatch, pipe, clock=_Clock(0.0, 0.0, 0.5, 1.0, 1.25, 2.0),
                   linger_s=2.0, linger_bytes=BIG)
    h._linger()
    assert h.connection.timeouts == [1.5, 0.75]
    assert all(0.0 < t <= 2.0 for t in h.connection.timeouts)
    assert h.connection.timeouts == sorted(h.connection.timeouts, reverse=True)
    assert pipe.asked == [READ_SIZE, READ_SIZE]


# ── 10, 11, 12: what the drain may swallow, and what it may not ──

def test_a_shutdown_that_raises_lingers_over_nothing(monkeypatch):
    """server.py:531 + 538 — the `shutdown(SHUT_WR)` ITSELF raising `OSError` (the
    peer went away: ENOTCONN, ENOTSOCK) is swallowed, and nothing is read afterwards:
    a socket that would not half-close has no reason to be drained. The existing
    OSError test (test_gaps_api_server.py:468) fails the READ instead, by which time
    the shutdown and the re-arm have both succeeded, so it cannot see a drain that
    peeks at a socket whose half-close failed. Narrow the `except` to
    `ConnectionResetError` and the OSError escapes into the handler's finally."""
    conn = _Conn(shutdown_with=OSError(9, 'the peer has already gone'))
    pipe = _Pipe(chunks=[b'x' * 10], late=RuntimeError('peeked at a socket that would not shut down'))
    h = _lingering(monkeypatch, pipe, conn=conn, clock=_Clock(0.0), linger_s=30.0,
                   linger_bytes=BIG)
    h._linger()                                               # must not raise
    assert conn.shutdowns == [HALF_CLOSE]                     # the attempt was made
    assert (conn.timeouts, pipe.asked) == ([], [])            # and nothing after it


def test_a_failed_rearm_lingers_over_nothing(monkeypatch):
    """server.py:533 + 538 — the read path's other fault point: `settimeout` raising
    `OSError` is swallowed too, and no peek is attempted with a timeout the socket
    never accepted (an unarmed blocking read here is the unbounded wait the two
    bounds exist to prevent). The existing `_linger` fakes make `settimeout` a no-op
    (test_gaps_api_server.py:435), so this half of the `try` has never failed in
    tests."""
    conn = _Conn(settimeout_with=OSError(9, 'the descriptor is no longer good'))
    pipe = _Pipe(chunks=[b'x' * 10], late=RuntimeError('peeked with a timeout never armed'))
    h = _lingering(monkeypatch, pipe, conn=conn, clock=_Clock(0.0), linger_s=30.0,
                   linger_bytes=BIG)
    h._linger()                                               # must not raise
    assert conn.shutdowns == [HALF_CLOSE]
    assert conn.timeouts == [30.0]                            # armed once, and that failed
    assert pipe.asked == []


def test_the_linger_swallows_only_an_oserror(monkeypatch):
    """server.py:538 — `except OSError`, not `except Exception`: the drain pays for
    the OS being rude, not for its own bug. Widening it hides a real defect (the
    wrong attribute, a pipe that cannot be read at all) behind two silent seconds and
    a clean request log, which is the failure mode this file's other tests cannot
    see because they all hand it a pipe that works."""
    pipe = _Pipe(chunks=[b''], fail=ValueError('the drain was handed something unreadable'))
    h = _lingering(monkeypatch, pipe, clock=_Clock(0.0), linger_s=30.0, linger_bytes=BIG)
    with pytest.raises(ValueError):
        h._linger()

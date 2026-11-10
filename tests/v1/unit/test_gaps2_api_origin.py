"""T-1003 · the highest-risk uncovered branches of `archeus/api/origin.py` lines 1-223.

Pure unit coverage of the origin contract's own gate, in the placement of the other gap
tests: no server, no socket, no harness, no real DLL, no OS probe, no network, no process,
no sleep over one second. Every outside fact stays a seam-faked callable, and the only
threads that exist are the ones `origin.bounded` starts itself.

The ten selected branches, ranked (denial first, then boundaries, then error paths), each
with the closest existing test and why that test's assertion misses the case:

1. origin.py:156-157 - `_loopback` compares the parsed host against the two loopback
   addresses themselves. Closest: test_origin_native.py:438 (a `192.168.0.4` end) and,
   for the other loopback owner, test_gaps_api_auth.py:40 which accepts the whole 127/8.
   Neither feeds `127.0.0.2`, `127.255.255.254` or `::2` to THIS predicate, so widening
   it to a network test or to `startswith('127.')` fails nothing today while handing a
   peer that never came from the loopback address the direct local path. ->
   `test_only_the_loopback_address_itself_is_a_direct_local_path`
2. origin.py:156 - the element is handed to `ipaddress.ip_address` unchecked, and that
   accepts an int (2130706433 is 127.0.0.1) and an address object. Closest: nothing, no
   origin test ever passes a non-string host element. -> xfail
   `test_a_non_string_endpoint_host_is_never_the_direct_loopback_path`
3. origin.py:164 and :187 - an endpoint with no port still reads as direct local
   (`_loopback` only looks at `[0]`), and `approved` then indexes `[1]` outside the
   try/except, so IndexError escapes the fail-closed gate. Closest:
   test_origin_native.py:445, which uses `local=None` and therefore dies inside
   `_loopback` and never reaches :187. -> xfail
   `test_an_endpoint_with_no_port_is_refused_by_the_path_gate_instead_of_raising`
4. origin.py:187 - the registered listener port must be the LOCAL end. Closest:
   test_origin_native.py:438 refuses one unregistered local port, but never with the
   registered port on the peer side, so reading the peer's port instead answers from
   neither side of the socket. -> `test_the_registered_listener_port_is_the_local_end_
   never_the_peer_side`
5. origin.py:158-159 - the malformed-endpoint refusals. Closest: test_origin_native.py:445
   again, which exercises one of the three caught exception classes (TypeError) and
   nothing else: a hostname, `'127.0.0.1:80'`, `()` or a bytes host are unanswered, and
   anything that escapes instead of answering False is swallowed at server.py:301 as a
   log line. -> `test_an_endpoint_that_is_not_an_address_is_refused_without_escaping_an_
   exception`
6. origin.py:200-201 - the reason tag is matched whole. Closest: test_origin_gaps.py:104
   (`''`, `'Approved'`, `'1abc'`, `'a-b'`, `'a b'`, `'x'*65`, None, 1) has no value that
   begins legally and then breaks, so `fullmatch` -> `match` (or an added `$`) keeps
   every suite green and admits `attested\n`, the verdict an operator reads. ->
   `test_a_reason_tag_that_only_begins_well_is_refused`
7. origin.py:176-180 - the ports are frozen before they are validated, and the bound is
   1..65535 inclusive. Closest: test_origin_native.py:451 and :456 only ever refuse (an
   empty registry, `[0]`, `[65536]`, `['8731']`, `[True]`, `[8731.0]`) and always hand a
   tuple or a set literal: the accepted bounds are never built, and a constructor that
   consumed the iterable twice (`self._ports = direct_local_ports` after the validating
   loop) would approve nothing and fail no test. ->
   `test_the_registered_ports_are_one_and_65535_and_survive_a_single_pass_iterator`
8. origin.py:107-122 - the reader bundle decides what the attestor may see: the injected
   clock, the age, the launcher. Closest: test_origin_native.py:599 and
   test_origin_reattest.py:60 call these two builders but assert nothing about their
   answer, so leaking `reattest` or `max_age_s=None` (a TypeError inside `valid`, hence a
   permanent undetermined for every local device request) or dropping a falsy launcher
   into the attestor's default answers green. ->
   `test_building_the_attestation_kwargs_observes_nothing_and_leaks_no_reader_option`,
   `test_the_launcher_reaches_the_attestor_only_when_it_is_not_none`,
   `test_the_age_reaches_the_attestor_only_when_it_is_not_none_and_reattest_never`
9. origin.py:26-27 - a saturated backend must fail before the probe runs. Closest:
   test_origin_native.py:483 fills a two-slot semaphore with hung calls and matches the
   message, but never asserts that the refused call was never executed, that no thread
   was started for it, or that a freed slot is usable again. ->
   `test_a_saturated_origin_backend_refuses_before_running_the_probe`
10. origin.py:32-34 and :46-48 - a probe that dies with a non-Exception `BaseException` must
    still arrive as that error and still return its slot. Closest:
    test_origin_native.py:468 uses `KeyError`; narrowing `except BaseException` to
    `except Exception` leaves `box` empty, so the caller reads `box[0]` and gets an
    `IndexError` in place of the probe's own error, unnoticed today. ->
    `test_a_backend_probe_that_dies_with_a_base_exception_is_reported_and_frees_its_slot`

The card's ten risk probes, and where they went. Already covered, so replaced by a
genuinely uncovered branch above: UNKNOWN/undetermined origin (test_origin_native.py:288,
test_origin_gaps.py:34 and :184), execution on a user route and user on an execution route
(test_api_origin.py:104 matrix, test_origin_native.py:271 and :429, where the registry
refuses an execution origin on the user's direct path), credential mismatch
(test_origin_gaps.py:112-166), missing evidence (test_origin_gaps.py:112,
test_api_origin.py:135), registry denial (test_api_origin.py:145 through
`UnapprovedRegistry`, test_origin_gaps.py:198) and identity drift (test_origin_gaps.py:85
and :91, plus test_origin_reattest.py:215, which refuses evidence whose binding was
swapped under the same generation). Not owned by this slice, so replaced as well: the age
boundary and the clock reversal are decided in `archeus/node/attest.py:183` (`0 <= now -
binding.accepted_at <= max_age_s`) and in `WindowsOriginBackend._reattest`, both outside
1-223; what this slice owns of them is the seam that forwards `clock`, `max_age_s` and
`launcher`, which is entry 8. `backend exception` is covered only for `Exception`, which
is why entry 10 takes the `BaseException` half of it.
"""

import ipaddress
import threading
import time

import pytest

from archeus.api import origin

CORE_PORT, PEER_PORT, GEN = 8731, 54321, 'g1'
REGISTRY = origin.CorePathRegistry((CORE_PORT,))


class NativeProbeDied(BaseException):
    """A probe that died hard. Not an Exception, so nothing may read it as no answer."""


def _context(local=None, remote=None, generation=GEN):
    return origin.ConnectionContext(
        object(),
        ('127.0.0.1', CORE_PORT) if local is None else local,
        ('127.0.0.1', PEER_PORT) if remote is None else remote,
        generation)


def _user_evidence(**over):
    fields = dict(origin=origin.OriginClass.USER, path=origin.PathClass.DIRECT_LOCAL,
                  identity='process:4124:100.0', process_binding=object(),
                  accept_generation=GEN, reason='attested')
    fields.update(over)
    return origin.OriginEvidence(**fields)


def _settled(predicate, limit_s=0.5):
    """A `bounded` worker frees its slot in its own `finally`, after it has woken the
    caller: wait out at most half a second for that to become observable."""
    deadline = time.monotonic() + limit_s
    while time.monotonic() < deadline and not predicate():
        time.sleep(0.01)
    return predicate()


class Slots(threading.BoundedSemaphore):
    """The hung-call counter, with the accounting the shipped code never reports."""

    def __init__(self, value):
        super().__init__(value)
        self.released = 0

    def release(self):
        self.released += 1
        return super().release()


class ReaderTable:
    """The three injected outside facts, counted: naming them must observe nothing. Each
    is bound once in the instance, so a test can compare the callable itself and not
    merely its name, and tell a forwarded clock from an OS clock."""

    def __init__(self, **over):
        self.owner_calls = self.process_calls = self.clock_calls = 0
        self.resolve_owner = self._resolve_owner
        self.read_process = self._read_process
        self.clock = self._clock
        self.readers = origin.AttestationReaders(resolve_owner=self.resolve_owner,
                                                 read_process=self.read_process,
                                                 clock=self.clock, **over)

    def _resolve_owner(self, port):
        self.owner_calls += 1
        return port

    def _read_process(self, pid):
        self.process_calls += 1
        return pid

    def _clock(self):
        self.clock_calls += 1
        return 1000.0


# ── 1. the direct local path is the loopback address itself, never the block ──

NOT_LOOPBACK = ['127.0.0.2', '127.255.255.254', '127.1.2.3', '::2', '0.0.0.0',
                'fe80::1', '10.0.0.5', '169.254.1.1']
NOT_LOOPBACK_IDS = ['127.0.0.2', '127.255.255.254', '127.1.2.3', 'v6-any', 'unspec',
                    'link-local', 'private-v4', 'link-local-v4']


@pytest.mark.parametrize('host', NOT_LOOPBACK, ids=NOT_LOOPBACK_IDS)
def test_only_the_loopback_address_itself_is_a_direct_local_path(host):
    """origin.py:156-157 tests the parsed host against 127.0.0.1 and ::1 themselves. Read
    it as a 127/8 membership test or as `startswith('127.')` and every other test stays
    green while a peer that never came from the loopback address holds the direct local
    path, which origin.py:219-220 then opens to the local device credential."""
    both = _context(local=(host, CORE_PORT), remote=(host, PEER_PORT))
    assert origin.direct_loopback(both) is False
    assert origin.direct_loopback(_context(local=(host, CORE_PORT))) is False
    assert origin.direct_loopback(_context(remote=(host, PEER_PORT))) is False
    assert REGISTRY.approved(both, _user_evidence()) is False
    assert REGISTRY.approved(_context(local=(host, CORE_PORT)), _user_evidence()) is False
    assert REGISTRY.approved(_context(), _user_evidence()) is True          # the control


# ── 2. only a string element is ever a socket address ──

@pytest.mark.xfail(strict=True, reason=(
    'origin.py:156 validates nothing about the element before handing it to '
    'ipaddress.ip_address, which accepts an int (2130706433 == 127.0.0.1) and an '
    'IPv4Address/IPv6Address object, so the branch origin.py:156-157 answers True for a '
    'host that is not an address string and origin.py:186 approves the direct local path '
    'for it; Handler.setup (server.py:270) is the only thing that keeps real endpoints '
    'strings'))
def test_a_non_string_endpoint_host_is_never_the_direct_loopback_path():
    packed = int(ipaddress.IPv4Address('127.0.0.1'))
    for host in (packed, ipaddress.IPv4Address('127.0.0.1'), ipaddress.IPv6Address('::1')):
        context = _context(local=(host, CORE_PORT), remote=(host, PEER_PORT))
        assert origin.direct_loopback(context) is False, host
        assert REGISTRY.approved(context, _user_evidence()) is False, host


# ── 3. an endpoint that carries no port is a refusal, never an exception ──

@pytest.mark.xfail(strict=True, reason=(
    'origin.py:164 only ever reads element [0] of an endpoint, so (127.0.0.1,) with no '
    'port still reads as the direct local path, and origin.py:187 then indexes [1] '
    'outside the try/except that origin.py:158 applies: CorePathRegistry.approved raises '
    'IndexError instead of answering False, so the Core gate escapes as an exception that '
    'server.py:301 hides as a log line'))
def test_an_endpoint_with_no_port_is_refused_by_the_path_gate_instead_of_raising():
    for endpoint in (('127.0.0.1',), ['127.0.0.1']):
        assert origin.direct_loopback(_context(local=endpoint)) is False, endpoint
        assert REGISTRY.approved(_context(local=endpoint), _user_evidence()) is False


# ── 4. the registered port is the local end of the connection ──

def test_the_registered_listener_port_is_the_local_end_never_the_peer_side():
    """origin.py:187 keeps the listener on the local endpoint. Read the peer's port there
    instead - the likelier edit beside `direct_loopback`, and the shape a forwarded peer
    presents - and the swapped context below is approved by the registry that correctly
    refuses it today."""
    swapped = _context(local=('127.0.0.1', PEER_PORT), remote=('127.0.0.1', CORE_PORT))
    assert REGISTRY.approved(swapped, _user_evidence()) is False
    assert origin.CorePathRegistry((PEER_PORT,)).approved(swapped, _user_evidence()) is True
    assert origin.CorePathRegistry((CORE_PORT,)).approved(
        _context(remote=('127.0.0.1', PEER_PORT)), _user_evidence()) is True


# ── 5. a malformed endpoint is a refusal, never an exception out of the gate ──

MALFORMED = [(), [], 'not-an-ip', 'localhost', '127.0.0.1:80', '', '127.0.0', '127',
             b'127.0.0.1', 'http://127.0.0.1', '127.0.0.1 ', ' 127.0.0.1 ', '127.0.0.01',
             '127.0.0.1.1', '::gg', 2130706433.0, '0x7f000001', '127000001']
MALFORMED_IDS = ['empty-tuple', 'empty-list', 'hostname', 'host-name', 'host-and-port',
                 'empty-host', 'three-octets', 'one-octet', 'bytes-host', 'url',
                 'padded-right', 'padded-both', 'leading-zero', 'five-octets', 'bad-v6',
                 'float-host', 'hex-string', 'packed-digits']


@pytest.mark.parametrize('bad', MALFORMED, ids=MALFORMED_IDS)
def test_an_endpoint_that_is_not_an_address_is_refused_without_escaping_an_exception(bad):
    """origin.py:158-159 is the only thing between a bogus endpoint and origin.py:187's
    `endpoint[1]`, and it catches three exception classes. Existing coverage exercises
    exactly one of them (None, a TypeError): the ValueError family (a hostname, a URL, a
    padded address) and the IndexError family (an empty endpoint) are unanswered, and
    whatever escapes rather than answering False is swallowed at server.py:301 as
    `origin observation failed`, so the local device only ever sees a 403."""
    assert origin.direct_loopback(_context(local=bad)) is False
    assert origin.direct_loopback(_context(remote=bad)) is False
    assert origin.direct_loopback(_context(local=bad, remote=bad)) is False
    assert REGISTRY.approved(_context(local=bad), _user_evidence()) is False
    assert REGISTRY.approved(_context(remote=bad), _user_evidence()) is False
    assert origin.direct_loopback(_context(local=('192.0.2.5', CORE_PORT))) is False


# ── 6. the reason tag is matched whole ──

BAD_REASONS = ['attested\n', '\nattested', 'attested\n\n', 'attested ', ' attested',
               'attested\t', 'attestèd', 'attested;', 'att ested', 'attested:', 'x' * 65]
BAD_REASON_IDS = ['nl-tail', 'nl-head', 'nl-twice', 'sp-tail', 'sp-head', 'tab-tail',
                  'accent', 'semicolon', 'inner-space', 'colon', 'too-long']


@pytest.mark.parametrize('reason', BAD_REASONS, ids=BAD_REASON_IDS)
def test_a_reason_tag_that_only_begins_well_is_refused(reason):
    """origin.py:200-201 is a `fullmatch` and no existing reason case begins legally and
    then breaks: with `re.match`, or with a `$` added to the pattern, all of these
    validate, and the reason is the field a refusal carries to the operator, so an
    unvalidated tag becomes the reported origin verdict."""
    assert origin.validate_evidence(_context(), _user_evidence(reason=reason)) is False
    assert origin.validate_evidence(_context(), _user_evidence(reason='attested')) is True
    assert origin.validate_evidence(_context(), _user_evidence(reason='x' * 64)) is True


# ── 7. the registered port bound, and one pass over the configured ports ──

def test_the_registered_ports_are_one_and_65535_and_survive_a_single_pass_iterator():
    """origin.py:176-180 freezes the ports before validating them, and the bound is
    1..65535 inclusive. Every existing registry test refuses something
    (test_origin_native.py:451, :456) and hands a tuple or set literal, so neither of the
    accepted bounds nor a second pass over the configured iterable is answered anywhere -
    and a second pass is precisely what turns a running Core into one that approves
    nothing, locking the user's own CLI out."""
    registry = origin.CorePathRegistry(iter((1, 65535)))
    assert registry.approved(_context(local=('127.0.0.1', 1)), _user_evidence()) is True
    assert registry.approved(_context(local=('::1', 65535), remote=('::1', PEER_PORT)),
                             _user_evidence()) is True
    assert registry.approved(_context(local=('127.0.0.1', 2)), _user_evidence()) is False
    assert origin.CorePathRegistry(frozenset({CORE_PORT})).approved(
        _context(), _user_evidence()) is True
    for ports in ([0], [65536], [-1], [1, 0], ['8731'], [True], [8731.0], [None]):
        with pytest.raises(ValueError):
            origin.CorePathRegistry(ports)


# ── 8. the reader seam: what the attestor is allowed to see ──

def test_building_the_attestation_kwargs_observes_nothing_and_leaks_no_reader_option():
    """origin.py:107-122 only names the injected facts; the two builders are called
    blind elsewhere (test_origin_native.py:599, test_origin_reattest.py:60). Leaking
    `reattest` or `max_age_s=None` into the attestor is a TypeError inside `valid`, which
    server.py:301 reads as undetermined: every local device request refused forever, with
    nothing in this suite to tell that apart from a real probe failure. And naming the
    facts must not observe them: an accept-time probe hidden in the argument build is a
    second, unbudgeted native call."""
    table = ReaderTable()
    assert table.readers.attest_kwargs(PEER_PORT) == {
        'remote_port': PEER_PORT, 'resolve_owner': table.resolve_owner,
        'read_process': table.read_process, 'clock': table.clock}
    assert table.readers.recheck_kwargs() == {'read_process': table.read_process,
                                              'clock': table.clock}
    assert (table.owner_calls, table.process_calls, table.clock_calls) == (0, 0, 0)
    # the clock the attestor runs on is the injected one, never an OS clock
    assert table.readers.attest_kwargs(PEER_PORT)['clock'] is table.clock
    assert table.readers.attest_kwargs(PEER_PORT)['clock']() == 1000.0
    assert table.clock_calls == 1


@pytest.mark.parametrize('launcher,forwarded', [(None, False), ('wxc-exec', True),
                                                ('', True)],
                         ids=['none', 'named', 'empty'])
def test_the_launcher_reaches_the_attestor_only_when_it_is_not_none(launcher, forwarded):
    """origin.py:111 and :118 test `is not None`, not truthiness: an explicitly supplied
    empty launcher name must stay supplied. Read as a truth test it disappears and the
    attestor's DEFAULT_LAUNCHER (attest.py:72) decides the ancestry instead, which is the
    one fact that separates an execution's process from the user's."""
    table = ReaderTable(launcher=launcher)
    for kwargs in (table.readers.attest_kwargs(PEER_PORT), table.readers.recheck_kwargs()):
        assert ('launcher' in kwargs) is forwarded
        if forwarded:
            assert kwargs['launcher'] == launcher
        assert kwargs['read_process'] is table.read_process
        assert kwargs['clock'] is table.clock


@pytest.mark.parametrize('max_age_s,forwarded', [(None, False), (1.5, True), (0, True)],
                         ids=['none', 'set', 'zero'])
def test_the_age_reaches_the_attestor_only_when_it_is_not_none_and_reattest_never(
        max_age_s, forwarded):
    """origin.py:120 tests `is not None` so an unset age keeps the attestor's own
    DEFAULT_MAX_AGE_S (attest.py:71) - forwarding None would make attest.py:183's
    `now - accepted_at <= max_age_s` raise and refuse every connection at once - while an
    explicit 0 stays an explicit 0. `reattest` belongs to the backend, never to the
    attestor: forwarding it is a TypeError inside the re-check."""
    table = ReaderTable(max_age_s=max_age_s, reattest=True)
    kwargs = table.readers.recheck_kwargs()
    assert ('max_age_s' in kwargs) is forwarded
    if forwarded:
        assert kwargs['max_age_s'] == max_age_s
    assert 'reattest' not in kwargs
    assert set(kwargs) <= {'read_process', 'clock', 'launcher', 'max_age_s'}
    assert set(table.readers.attest_kwargs(PEER_PORT)) <= {
        'remote_port', 'resolve_owner', 'read_process', 'clock', 'launcher'}


# ── 9. a saturated backend refuses before the probe runs ──

def test_a_saturated_origin_backend_refuses_before_running_the_probe(monkeypatch):
    """origin.py:26-27 fails a call at once when the MAX_HUNG_CALLS slots are gone. The
    existing saturation test (test_origin_native.py:483) only matches the message: run
    the probe anyway, or start a thread for it, and a stuck native probe still takes one
    thread and one OS observation per refused request, which is the whole thing the slot
    counter exists to stop. The refusal must also be temporary, or one burst would end
    the origin gate."""
    assert 0 < origin.MAX_HUNG_CALLS <= 64 and 0 < origin.BACKEND_DEADLINE_S <= 5
    slots = threading.BoundedSemaphore(2)
    slots.acquire()
    slots.acquire()
    monkeypatch.setattr(origin, '_slots', slots)
    started = []
    real_start = threading.Thread.start
    monkeypatch.setattr(threading.Thread, 'start',
                        lambda self: (started.append(self), real_start(self)))
    ran = []

    def probe():
        ran.append(1)
        return 'observed'

    with pytest.raises(TimeoutError, match='saturated'):
        origin.bounded(probe)
    assert ran == []                                  # the native probe never ran
    assert started == [], [t.name for t in started]    # and no thread was started for it
    slots.release()
    assert origin.bounded(probe) == 'observed'        # one freed slot, one call
    assert ran == [1] and len(started) == 1


# ── 10. a probe that dies with a BaseException is still the probe's own error ──

def test_a_backend_probe_that_dies_with_a_base_exception_is_reported_and_frees_its_slot(
        monkeypatch):
    """origin.py:33 catches BaseException and origin.py:46-48 re-raises it unchanged, and
    the finally at :35-37 is what returns the slot. The existing test
    (test_origin_native.py:468) only ever raises a KeyError, so narrowing that except to
    `Exception` leaves `box` empty and hands the caller an IndexError from `box[0]` in
    place of the probe's error, while dropping the release leaks the hung-call budget a
    few calls at a time."""
    slots = Slots(4)
    monkeypatch.setattr(origin, '_slots', slots)
    died = NativeProbeDied('the process table died')
    ran = []

    def probe():
        ran.append(1)
        raise died

    for _ in range(3):
        with pytest.raises(NativeProbeDied) as raised:
            origin.bounded(probe)
        assert raised.value is died                   # the same error, not a re-wrap
    assert ran == [1, 1, 1]                           # one observation per call
    assert _settled(lambda: slots.released == 3) is True
    assert origin.bounded(lambda: 'value') == 'value'     # the budget still works

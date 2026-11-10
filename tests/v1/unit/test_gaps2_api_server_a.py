"""T-1032 · the ten highest-risk uncovered branches of `archeus/api/server.py`
lines 182-324 (inclusive): the `Api` origin wiring and the `Handler` accept
lifecycle. The focus is the accept rule the shipped gates rest on — evidence is
captured once, at accept, and every later request only revalidates what that one
capture stored — and the fail-closed half of it: a probe that explodes, an
approval that explodes, a verdict that is merely truthy, a release that explodes,
or a connection that never bound anything at all must never read as permission.

Nothing here is a source edit and nothing here is a real OS call: the handler is
built with `object.__new__` (the seam `tests/v1/unit/test_origin_attest_wiring.py`
and `tests/v1/unit/test_api_origin.py` already use) and the whole outside world
is one `Recorder` behind the backend and registry ports, so every assertion is
about observable denial, handler state, probe ORDER and the absence of probes.
Platform-neutral: no sockets, no processes, no sleeps, no Windows API, no case
sensitivity, no environment values.

The ten branches (source file:line → test), fail-closed first:

1. server.py:301-303 reached from 277-278 — `setup`'s accept-time bind when the
   attest probe raises: the `except` must swallow, leave `evidence` None with
   `evidence_acquired` already True, and `finish` must still release that
   nothing. → `test_setup_survives_an_attest_that_raises_and_still_releases_the_nothing_it_bound`
2. server.py:299 → 301-303 — Core's registry raising on a revalidation of the
   reused evidence is a denial, with no re-attest and the release kept.
   → `test_a_registry_that_raises_on_revalidation_denies_without_reattesting`
3. server.py:298 — `backend.valid(...) is True`: on a reused connection a merely
   truthy (non-True) verdict is a denial, and the captured evidence stays intact.
   → `test_a_truthy_valid_verdict_on_a_reused_connection_is_still_a_denial`
4. server.py:299 — `registry.approved(...) is True`: a merely truthy approval is
   not approval. → `test_a_truthy_registry_approval_is_not_approval`
5. server.py:315-316 — `origin_holds`' enforcement switch: disabled (the shipped
   default) is an unconditional hold that probes nothing at all.
   → `test_the_recheck_probes_nothing_and_holds_when_enforcement_is_off`
6. server.py:317-318 — the hold side of the stream re-check: True, with the
   evidence captured once at accept and re-validated (never re-attested) on it.
   → `test_the_stream_holds_while_the_captured_evidence_still_holds`
7. server.py:285 False — `finish` of a connection that bound nothing (setup with
   enforcement off, the shipped default) releases nothing, yet still closes.
   → `test_a_connection_that_bound_nothing_releases_nothing`
8. server.py:288-289 — a `release` that raises is swallowed and logged after the
   close, never out of `finish`. → `test_a_release_that_raises_cannot_break_the_close`
9. server.py:294/297 — reuse of a FAILED capture (`evidence_acquired` True,
   `evidence` None, the state branch 1 leaves behind): `validate_evidence`
   short-circuits, so neither attest nor valid nor approved may be probed again.
   → `test_a_failed_capture_is_never_validated_and_never_reattested`
10. server.py:235-236 — the shipped registry default is fail-closed
    (`UnapprovedRegistry` denies even a perfect evidence) and an injected one is
    kept through construction.
    → `test_the_default_registry_approves_nothing_and_an_injected_one_survives_construction`

Replaced risk probes, with the coverage that already pins them (found by
searching tests/v1 for the target symbols, as the card directs): the attestor
that raises or answers an unknown origin (server.py:246-251, probes 1/2) —
`test_api_origin.py:211`; a dead or unknown credential (server.py:255-261,
probe 4) — `test_api_origin.py:203` plus `tests/v1/integration/test_api_auth.py:132`;
a changed accept generation (server.py:297, probe 6) —
`test_origin_attest_wiring.py:266` and `tests/v1/integration/test_api_origin_transport.py:70`;
the ordinary reuse (server.py:294 False, probe 5) — `test_origin_attest_wiring.py:136`
and `test_api_origin.py:145`; the non-bool constructor switch (server.py:193-195,
probe 10's first half) — `test_api_origin.py:104`. Each entry above is therefore
an arm no existing assertion catches: removing or inverting the cited branch
fails the test named for it.
"""

import itertools
import logging
import socketserver
from types import SimpleNamespace

from archeus.api import auth, origin, server

CORE_PORT = 8731
PEER_PORT = 54321
GENERATION = 'test-instance:7'
HOST = '127.0.0.1:%d' % CORE_PORT
DENIAL = origin.OriginEvidence()          # what every refusal of this slice must be


def _context(generation=GENERATION):
    return origin.ConnectionContext(object(), ('127.0.0.1', CORE_PORT),
                                    ('127.0.0.1', PEER_PORT), generation)


def _evidence(generation=GENERATION, kind=origin.OriginClass.USER,
              path=origin.PathClass.DIRECT_LOCAL, binding='binding'):
    """The one evidence the transport gate accepts on the local path: a known
    origin, a known path, this connection's generation, a binding, a clean reason."""
    return origin.OriginEvidence(origin=kind, path=path, identity='process:4124:100.0',
                                 process_binding=binding, accept_generation=generation,
                                 reason='attested')


class Recorder:
    """The whole outside world: one object plays the OS backend and Core's
    registry, records every probe in order, and answers as configured. `fail`
    names the probes that explode instead of answering (the exception the real
    `origin.bounded` would re-raise in the handler)."""

    def __init__(self, *, valid=True, approved=True, fail=()):
        self.valid_result = valid
        self.approved_result = approved
        self.fail = set(fail)
        self.calls = []
        self.released = []

    def _probe(self, name):
        self.calls.append(name)
        if name in self.fail:
            raise RuntimeError('the %s probe exploded' % name)

    def attest(self, context):
        self._probe('attest')
        return _evidence(context.accept_generation)

    def valid(self, context, evidence):
        self._probe('valid')
        return self.valid_result

    def release(self, context, evidence):
        self.calls.append('release')                        # the attempt is recorded
        self.released.append((context, evidence))           # even when it explodes
        if 'release' in self.fail:
            raise RuntimeError('the release probe exploded')

    def approved(self, context, evidence):
        self._probe('approved')
        return self.approved_result


def _connected(rec, *, enforcement=True, acquired=False, evidence=None, credential='local'):
    """A connection as `setup` leaves it (the `object.__new__` seam of
    test_origin_attest_wiring.py:99), minus the OS: *rec* is both the backend and
    the registry so one list orders every probe the handler makes."""
    api = SimpleNamespace(origin=auth.Origin(CORE_PORT),
                          origin_enforcement_enabled=enforcement,
                          origin_backend=rec, origin_registry=rec,
                          instance='test-instance')
    handler = object.__new__(server.Handler)
    handler.api = api
    handler.server = SimpleNamespace(api=api, accept_generations=itertools.count())
    handler.request = SimpleNamespace(getsockname=lambda: ('127.0.0.1', CORE_PORT))
    handler.client_address = ('127.0.0.1', PEER_PORT)
    handler.context = _context()
    handler.evidence, handler.evidence_acquired = evidence, acquired
    handler.origin_backend = rec
    handler.origin_registry = rec
    handler.attested = None
    handler.headers = {'Host': HOST}
    handler.principal = {'origin': credential}
    return handler


def _accepted(rec):
    """One connection that got through accept: the capture ran once and held."""
    handler = _connected(rec)
    assert handler.transport_evidence() == _evidence()
    assert rec.calls == ['attest', 'valid', 'approved']
    return handler


def _closing(monkeypatch):
    """`super().finish()` as a counter: the close must happen, but no socket."""
    closed = []
    monkeypatch.setattr(server.BaseHTTPRequestHandler, 'finish',
                        lambda self: closed.append('close'))
    return closed


def _no_op_setup(monkeypatch):
    """`super().setup()` silenced, exactly as the accept-boundary test of
    test_origin_attest_wiring.py:191 does it: there is no rfile and no socket."""
    monkeypatch.setattr(socketserver.StreamRequestHandler, 'setup', lambda self: None)


# ── 1+2: a probe that explodes at accept is a closed connection, not a crash ──

def test_setup_survives_an_attest_that_raises_and_still_releases_the_nothing_it_bound(
        monkeypatch):
    """server.py 277→296→301-303: with enforcement on, `setup` binds at accept;
    the attest raising through `origin.bounded` must be swallowed there. The
    state is the fail-closed one no other test pins: `evidence_acquired` already
    True (set at 295, BEFORE the capture, so a re-entry cannot re-attest),
    `evidence` None, and `finish` (285-287) still releases that nothing exactly
    once. Remove the try/except and setup explodes with the peer still connecting;
    move 295 after the capture and a failed accept re-attests on every retry and
    releases nothing at all."""
    _no_op_setup(monkeypatch)
    closed = _closing(monkeypatch)
    rec = Recorder(fail={'attest'})
    handler = _connected(rec)
    handler.setup()                                           # must not raise
    assert handler.evidence_acquired is True                  # bound before the probe
    assert handler.evidence is None                           # and the capture died
    assert rec.calls == ['attest']

    assert handler.transport_evidence() == DENIAL             # the refusal is the empty one
    assert handler.evidence_acquired is True and handler.evidence is None
    assert rec.calls == ['attest']                            # never re-attested, never probed

    handler.finish()
    assert closed == ['close']                                # the close came first
    assert rec.calls == ['attest', 'release']
    assert rec.released == [(handler.context, None)]          # released once, the nothing it held


def test_a_registry_that_raises_on_revalidation_denies_without_reattesting(monkeypatch):
    """server.py 299→301-303: Core's approval is a second, independent security
    actor; its failure on a revalidation of the REUSED evidence is a denial — the
    empty evidence, not the captured one — with no re-attest (the capture stays
    the single one), the backend re-check still reached first, and the release of
    the captured evidence still owed. Un-guard the registry call and this raises
    out of the request instead of refusing it."""
    _closing(monkeypatch)
    rec = Recorder()
    handler = _accepted(rec)
    captured = handler.evidence
    rec.fail = {'approved'}

    assert handler.transport_evidence() == DENIAL
    assert rec.calls == ['attest', 'valid', 'approved', 'valid', 'approved']
    assert handler.evidence is captured                       # the capture itself untouched
    assert handler.transport_evidence().origin is origin.OriginClass.UNDETERMINED

    handler.finish()
    assert rec.released == [(handler.context, captured)]      # the deny still releases


# ── 3+4: permission is `is True`, everything else is denial ──

def test_a_truthy_valid_verdict_on_a_reused_connection_is_still_a_denial(monkeypatch):
    """server.py:298 `origin.bounded(backend.valid, ...) is True`: the accepted
    connection's next revalidation answers 1, not True. `is True` reads that as
    the denial it is — the fresh empty evidence — while the captured evidence
    stays exactly as accept stored it and nothing is re-attested. Replace `is
    True` with `== True` (or plain truthiness) and this stream survives on a
    verdict the contract never allows. The backends of the existing tests only
    ever answer literal bools (test_api_origin.py:158), so none of them sees it."""
    _closing(monkeypatch)
    rec = Recorder()
    handler = _accepted(rec)
    captured = handler.evidence
    rec.valid_result = 1                                      # truthy, not True

    assert handler.origin_holds() is False
    assert rec.calls == ['attest', 'valid', 'approved', 'valid']   # revalidated, never re-attested
    assert handler.attested == DENIAL                         # a fresh deny, not the captured one
    assert handler.attested.reason == 'unavailable'
    assert handler.evidence == captured                       # the store itself untouched


def test_a_truthy_registry_approval_is_not_approval(monkeypatch):
    """server.py:299 `self.origin_registry.approved(...) is True`: the backend
    says True and Core's registry says 'yes'. That is a denial — the same empty
    evidence an absent approval gets — and it comes back after the backend probe
    was reached, so the conjuncts stay in order. Truthiness here (a dict, a
    count, a non-empty string leaking out of a registry refactor) is fail-open
    on every privileged route; no existing registry answers anything but True or
    False (test_api_origin.py:171, test_origin_attest_wiring.py:106)."""
    _no_op_setup(monkeypatch)
    rec = Recorder(approved='yes')
    handler = _connected(rec)
    handler.setup()                                           # the accept bind itself denies
    assert rec.calls == ['attest', 'valid', 'approved']       # probed, and truthily unapproved
    assert handler.evidence == _evidence('test-instance:0')   # the capture is kept, unproved
    assert handler.transport_evidence() == DENIAL
    assert rec.calls == ['attest', 'valid', 'approved', 'valid', 'approved']   # never re-attested
    assert handler.origin_allows('local') is False            # the gate reads the denial too


# ── 5+6: the stream re-check, both sides of the switch ──

def test_the_recheck_probes_nothing_and_holds_when_enforcement_is_off(monkeypatch):
    """server.py:315-316: with the switch off (the shipped default of
    `ORIGIN_ENFORCEMENT_ENABLED`) the stream's re-check is an unconditional hold
    that must not touch a probe — the stream lives, and the backend that exists
    but is switched off never runs. Delete the guard and this same handler
    revalidates: three probes appear and, on the shipped no-reader backend's
    shape, the stream would die on every request of a default-off Core."""
    _closing(monkeypatch)
    rec = Recorder()                                          # would approve everything
    handler = _connected(rec, enforcement=False)
    assert handler.origin_holds() is True
    assert rec.calls == []                                    # not one OS-facing probe ran
    assert handler.attested is None                           # and no state moved


def test_the_stream_holds_while_the_captured_evidence_still_holds(monkeypatch):
    """server.py:317-318 True side: enforcement on, the captured evidence still
    valid and approved, a local credential on the loopback Host — the stream
    holds. The two halves no existing assertion pins: `attested` moves to the
    evidence THIS re-check read (drop 317 and `origin_allows` gates on stale
    state), and the capture stays the single one — every hold is a revalidation
    (`valid` then `approved`, in that order), never a second attest. The only
    shipped assertion of `origin_holds` is its False side
    (test_origin_attest_wiring.py:226)."""
    _closing(monkeypatch)
    rec = Recorder()
    handler = _accepted(rec)
    assert handler.origin_holds() is True
    assert rec.calls == ['attest', 'valid', 'approved', 'valid', 'approved']
    assert handler.attested is handler.evidence               # the re-read became the gate
    assert handler.origin_allows('local') is True             # and it is permission, not luck


# ── 7+8: how a connection ends ──

def test_a_connection_that_bound_nothing_releases_nothing(monkeypatch):
    """server.py:285 False — finish after a setup that bound nothing (enforcement
    off, the shipped default; setup at 277 never ran the bind): `finish` still
    closes, and `release` is never called. The one existing `finish` test pins
    only the release side (test_api_origin.py:178); drop the `evidence_acquired`
    guard and every idle connection of a default-off Core starts releasing an
    evidence it never captured."""
    _no_op_setup(monkeypatch)
    closed = _closing(monkeypatch)
    rec = Recorder()
    handler = _connected(rec, enforcement=False)
    handler.setup()
    assert handler.evidence_acquired is False and handler.evidence is None
    handler.finish()
    assert closed == ['close']                                # the close is owed regardless
    assert rec.calls == []                                    # nothing captured, nothing released
    assert rec.released == []


def test_a_release_that_raises_cannot_break_the_close(monkeypatch, caplog):
    """server.py:288-289: the close happened, the release explodes through
    `origin.bounded`, and `finish` swallows it with the one warning. The peer
    already has its answer; a raise here aborts the close path of a real socket
    instead. The hung-release integration test (test_api_origin_transport.py:274)
    still sees its 200 if the exception escapes — the response is already sent —
    so only this pins the swallow, the order and the exactly-once release."""
    closed = _closing(monkeypatch)
    rec = Recorder(fail={'release'})
    handler = _accepted(rec)
    captured = handler.evidence
    with caplog.at_level(logging.WARNING, logger='archeus.core'):
        handler.finish()                                      # must not raise
    assert closed == ['close']                                # closed first, then released
    assert rec.calls == ['attest', 'valid', 'approved', 'release']
    assert rec.released == [(handler.context, captured)]      # tried once, with the capture
    assert 'origin release failed' in caplog.text


# ── 9: reuse of a capture that failed ──

def test_a_failed_capture_is_never_validated_and_never_reattested(monkeypatch):
    """server.py 294 False → 297 False: the state branch 1 leaves — acquired
    True, evidence None. Every later revalidation must fail closed on
    `validate_evidence` alone: no attest (the capture is never retried), and —
    the conjunct order, which is the whole point of validating first — no valid
    and no approved either, so no probe is ever handed a None evidence. Reorder
    the `and`s at 297-299 or drop the validate and a probe sees the None."""
    _closing(monkeypatch)
    rec = Recorder()
    handler = _connected(rec, acquired=True, evidence=None)   # as the failed accept left it
    assert handler.transport_evidence() == DENIAL
    assert rec.calls == []                                    # nothing probed. full stop.
    assert handler.origin_holds() is False
    assert rec.calls == []                                    # the gate asked, got the deny
    handler.finish()
    assert rec.released == [(handler.context, None)]          # still released, once


# ── 10: the registry default is Core's deny-by-default ──

def test_the_default_registry_approves_nothing_and_an_injected_one_survives_construction():
    """server.py:235-236: an `Api` built the way Core builds it gets
    `UnapprovedRegistry` — a perfect USER/DIRECT_LOCAL evidence of its own
    connection is still denied, because OS observation alone never earns a path
    (the shipped-api test of test_origin_attest_wiring.py:352 asserts the
    backend, never the registry half) — while a registry handed in is kept by
    identity. Default this ternary to an approving object and native confinement
    is one construction argument from fail-open."""
    def ship(**over):
        return server.Api(db=None, missions=SimpleNamespace(policy=None),
                          port=CORE_PORT, health=None, version='v', **over)

    shipped = ship()
    assert isinstance(shipped.origin_registry, origin.UnapprovedRegistry)
    context, evidence = _context(), _evidence()               # the best evidence there is
    assert shipped.origin_registry.approved(context, evidence) is False
    assert shipped.origin_enforcement_enabled is False        # the deny is the shipped shape

    chosen = Recorder()
    assert ship(origin_registry=chosen).origin_registry is chosen

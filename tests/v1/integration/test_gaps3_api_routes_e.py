"""T-1156 · the ten highest-risk uncovered branches of archeus/api/routes.py
lines 977-1086 inclusive (the step-up/revocation tail, the P13 verification and
review reads and writes, and the whole P14 automation family).

Source range: `archeus/api/routes.py:977-1086`. This container sits on the MXC
integration branch tip `02d2e72c4916ec22f92f8df30e91c77e649a1c92` (`git` is not
installed here, so the tip is read from `.git/HEAD` and `.git/refs/heads/master`);
the handlers inside the range are the ones the card names.

FINAL SELECTED BRANCHES (ranked by risk; probe 5 is replaced outright, probes 1
and 4 are kept as the fault/boundary composition their existing coverage does
not pin — evidence for each entry is in /work/QWEN-DONE-T-1156.md):

  B1  routes.py:992-996  `_revoke_locked_out`: the counter stands, NO stream
      closes and nothing is swallowed while the revoke write keeps failing.
  B2  routes.py:960, 971-980 `_with_step_up`: `counted` is a proof AND paired;
      the reservation is released exactly once; the count is cleared only for a
      proof that was really weighed.
  B3  routes.py:1054-1058 + route row 1265 `decide_verification`: approve scope
      only, the id from the path, `note` defaulted to ''.
  B4  routes.py:1026-1027 + 96-99 `simulate_automation`: `days=0` and the
      non-digit window refused before any read is opened.
  B5  routes.py:1011-1036 (replaces probe 5) the automation reads hand the
      query a `homes` reader bound to their own live read, and forward
      `schedule_faults()`.
  B6  routes.py:1024 + 91-93 `simulate_automation`: a repeated `days` parameter
      takes the LAST value; an empty list is no parameter at all.
  B7  routes.py:1047-1051 `set_automation_state`: `expected_version` is carried
      once and a lost race is never retried here.
  B8  routes.py:1066-1073 `review_mission`: the requirement lists are forged
      when absent and a review the schema refuses runs no command.
  B9  routes.py:1076-1078 `abandon_integration`: the path names the task, an
      absent body is tolerated, a foreign denial leaves nothing behind.
  B10 routes.py:1081-1084 + route row 1127 `revoke_device`: only the authorized
      command, and the streams close after the write landed, never before.

The `SUPPORTING` tests below the ten are the rest of what the card asks of an
owned route family: insufficient scope, malformed bodies, wrong method and the
rows' own metadata. Content-type framing is NOT probed and NOT claimed: that
branch belongs to the server's already-assigned accept/body pipeline
(archeus/api/server.py `_length`/`_body`), which is context only here.

Seams: nothing here opens a socket, a thread, a subprocess, a real clock or a
credential file, and no test sleeps. The `tc` fixture of
tests/v1/integration/conftest.py is never requested — it starts a real server.
Requests are fake `server.Handler`-shaped objects carrying the real writer-seam
signature (`run(fn, kwargs, *, actor_id=None, keyed=True)`, the principal as the
`user_device` actor, the body's `idempotency_key`), built over an app-shaped
fake api whose db hands out one read connection at a time and whose runtime
root is `tmp_path`. Every refusal asserted comes from real source: `match()`,
the real `ROUTES` rows and the real `schemas.validate`. No test imports another
`test_gaps3` file or depends on queue order; nothing is xfailed, nothing skipped.
"""

from types import SimpleNamespace

import pytest

from archeus.api import auth, routes, schemas
from archeus.api.routes import Refused
from archeus.api.schemas import Invalid, validate
from archeus.core.application import errors
from archeus.core.domain import guards
from archeus.core.domain.values import Ref

LOCAL_HOST = '127.0.0.1:7337'
PEER = ('127.0.0.1', 54321)
HOMES = object()                               # the fake homes builder's answer


def _principal(**over):
    p = {'principal_id': 'prn_u', 'device_id': 'dvc_u', 'origin': 'local',
         'scopes': list(auth.SCOPES)}
    p.update(over)
    return p


def _raiser(exc):
    def go(*args, **kw):
        raise exc
    return go


def guard_failed(reason):
    return errors.GuardFailed('device', 'ARMED', 'ARMED', 'rearm',
                              guards.GuardResult('step_up', False, reason))


class Recorder:
    """A fake collaborator: records every call, may fault once, and may tag a
    shared order list so an ordering invariant is observable."""

    def __init__(self, ret=None, raises=None, order=None, label=None):
        self.calls = []
        self.ret = ret
        self.raises = raises
        self.order = order
        self.label = label

    def __call__(self, *args, **kw):
        self.calls.append((args, kw))
        if self.order is not None:
            self.order.append(self.label)
        if self.raises is not None:
            fault, self.raises = self.raises, None          # one fault, then healthy
            raise fault
        return self.ret() if callable(self.ret) else self.ret


class Conn:
    """The token one open read hands out. It carries its own db, so a `homes`
    reader that was spent after its read had been given back is observable."""

    def __init__(self, db, number):
        self.db = db
        self.number = number


class Db:
    """An app-shaped read side: one connection per open read, counted, so
    "refused before the read" and "the read was closed" are observable."""

    def __init__(self):
        self.reads = 0
        self.live = 0
        self.closed_reads = 0

    def read(self):
        db = self

        class _Cm:
            def __enter__(self):
                db.reads += 1
                db.live += 1
                return Conn(db, db.reads)

            def __exit__(self, *exc):
                db.live -= 1
                db.closed_reads += 1
                return False

        return _Cm()


class Api:
    """The `req.api` half of the app, faked: the writer, the sse hub, the
    step-up counter, the resource registry, the schedule-fault table and the
    P13 decision service — over a tmp_path runtime root and a transport that
    was never opened."""

    def __init__(self, tmp_path=None, order=None, step_up=None, **over):
        self.order = order if order is not None else []
        self.root = None if tmp_path is None else tmp_path / 'runtime'
        if tmp_path is not None:
            self.root.mkdir(parents=True, exist_ok=True)
        self.db = Db()
        self.transport = SimpleNamespace(connected=False, sockets=0)
        self.sentinel = SimpleNamespace(armed=False, engaged=[], cleared=[])
        self.resources = SimpleNamespace(registry=None, callers=())
        self.sse = SimpleNamespace(close_device=Recorder(order=self.order, label='close'),
                                   serve=Recorder(ret=('stream', 'sent')))
        self.step_up = auth.StepUpFailures() if step_up is None else step_up
        self.schedule_faults = Recorder(ret={'quarantined': []}, order=self.order,
                                        label='faults')
        self.decisions = SimpleNamespace(decide=Recorder(ret={'decided': True}),
                                         review=Recorder(ret={'reviewed': True}))
        self.origin = SimpleNamespace(local_host=lambda h: h == LOCAL_HOST, remote=None)
        self.command_timeout = 1.0
        self.artifacts = SimpleNamespace(root=self.root, wrote=[])
        self.__dict__.update(over)


class StepUp:
    """A fake `auth.StepUpFailures` with every arm observable."""

    LIMIT = auth.StepUpFailures.LIMIT

    def __init__(self, admit=True, trips=False, locked=False):
        self.admit = admit
        self.trips = trips
        self.is_locked = locked
        self.begun, self.ended, self.counted, self.cleared = [], [], [], []

    def begin(self, device_id):
        self.begun.append(device_id)
        return self.admit

    def end(self, device_id):
        self.ended.append(device_id)

    def failed(self, device_id):
        self.counted.append(device_id)
        return self.trips

    def reset(self, device_id):
        self.cleared.append(device_id)

    def locked(self, device_id):
        return self.is_locked


class Req:
    """The handler-facing half of `server.Handler`: body/query/headers/params/
    principal/peer/proven/replayed plus the writer seam `run`, which mirrors
    server.py:325-331 (the actor is the principal, the key is the body's)."""

    def __init__(self, api=None, body=None, query=None, headers=None, params=None,
                 principal=None, peer=PEER, proven=False, replayed=False, ret=None,
                 raises=None, order=None):
        if api is None:
            api = Api(order=order)
        self.api = api
        self.order = order if order is not None else api.order
        self.body = body
        self.query = {} if query is None else query
        self.headers = {} if headers is None else headers
        self.params = {} if params is None else params
        self.principal = _principal() if principal is None else principal
        self.peer = peer
        self.proven = proven
        self.replayed = replayed
        self.ret = {} if ret is None else ret
        self.raises = raises
        self.submits = []

    def run(self, fn, kwargs, *, actor_id=None, keyed=True):
        actor = Ref('user_device', actor_id or self.principal['principal_id'])
        key = (self.body or {}).get('idempotency_key') if keyed else None
        self.submits.append(SimpleNamespace(fn=fn, kwargs=dict(kwargs, actor=actor),
                                            actor=actor, keyed=keyed, key=key))
        self.order.append('run')
        if self.raises is not None:
            fault, self.raises = self.raises, None          # the first command may fail
            raise fault
        return dict(self.ret)


def dispatch(req, method, path):
    """The gate the slice sits behind, driven by the REAL route table and the
    REAL request schema: `match` picks the row (404/405 from source), the row's
    own `scope` admits the credential or refuses 403, `schemas.validate` refuses
    a body that is not the shape the row declares — and only then does the real
    handler run. The server's accept/Host/CORS/body pipeline stays context."""
    route, params = routes.match(method, path)
    req.params.update(params)
    if route.scope is not None:
        if req.principal is None:
            raise Refused(401, 'unauthenticated')
        if route.scope not in req.principal['scopes']:
            raise Refused(403, 'scope_required', {'scope': route.scope})
    if route.request_schema is not None:
        validate(req.body or {}, route.request_schema)
    return route.handler(req)


def refused(call, *args, **kw):
    with pytest.raises(Refused) as got:
        call(*args, **kw)
    return got.value


def files_under(tmp_path):
    return sorted(p.name for p in tmp_path.iterdir())


# ── B1 · routes.py:992-996: a revoke that did not land leaves the lockout ──

def test_a_failing_revoke_write_leaves_the_lockout_standing_and_the_stream_open():
    """Catch: routes.py:993-996 with the `reset`/`close_device` moved above the
    `run`, or the run wrapped so the fault is swallowed. Then a client whose
    revoke faulted gets its wrong-PIN counter cleared — five more guesses per
    request, forever, because `locked()` is what holds the door — and a device
    that was never revoked has its event streams closed anyway. The closest
    existing coverage (tests/v1/unit/test_fix_batch11.py:109-138 and
    tests/v1/integration/test_api_audit_fixes.py:113-138) pins that no guess is
    admitted while the write keeps failing and that the retry lands, but its
    fakes never watch `close_device` and its `except` swallows the fault, so a
    fail-open revocation passes them both."""
    su = auth.StepUpFailures()
    for _ in range(su.LIMIT):
        trips = su.failed('dvc_u')
    assert trips and su.locked('dvc_u')                     # the fifth strike locked it
    req = Req(principal=_principal(origin='paired'))
    req.api.step_up = su
    req.raises = RuntimeError('writer busy')
    with pytest.raises(RuntimeError):
        routes._step_up_failed(req)                         # the fault is not swallowed
    (run,) = req.submits
    assert run.fn is routes.commands.revoke_device
    assert run.kwargs == {'device_id': 'dvc_u', 'reason': 'step_up_failures',
                          'actor': Ref('user_device', 'prn_u')}
    assert run.keyed is False, 'a replayed answer would revoke twice'
    assert su.locked('dvc_u'), 'the counter was cleared although the revoke failed'
    assert req.api.sse.close_device.calls == [], 'a live device had its streams closed'

    routes._step_up_failed(req)                             # the retry lands
    assert [s.fn for s in req.submits][-1] is routes.commands.revoke_device
    assert not su.locked('dvc_u'), 'the landed revoke did not clear the counter'
    assert req.api.sse.close_device.calls == [(('dvc_u',), {})]


# ── B2 · routes.py:960, 971-980: `counted` is a proof AND a paired client ──

def test_a_local_clients_wrong_proof_is_never_counted_towards_revocation():
    """Catch: routes.py:960 read as `counted = proof is not None` (or 972 without
    `counted`). The local desktop is not a credential a guess rate can break, and
    revoking it on one mistyped proof shuts the machine out of its own service;
    `end` would also be spent on a reservation `begin` never granted."""
    su = StepUp(admit=True, trips=True)
    req = Req(principal=_principal(origin='local'))
    req.api.step_up = su
    with pytest.raises(errors.GuardFailed):
        routes._with_step_up(req, '000000', _raiser(guard_failed('the step-up proof is wrong')))
    assert su.begun == [] and su.ended == [] and su.counted == []
    assert req.submits == [], 'a local client was revoked for a wrong proof'
    assert req.api.sse.close_device.calls == []


def test_a_paired_guess_is_released_once_and_cleared_only_on_a_proof_that_counted():
    """Catch: the `finally` on routes.py:978-980 (drop it and the reservation
    leaks, so the sixth guess of a burst is refused forever), and the `req.proven`
    test on 975-976 (drop it and a paired request that carried NO proof — where
    the guard weighed nothing — wipes the same device's counter four strikes
    deep)."""
    su = StepUp(admit=True, trips=True)
    req = Req(principal=_principal(origin='paired'))
    req.api.step_up = su
    with pytest.raises(errors.GuardFailed):
        routes._with_step_up(req, '000000', _raiser(guard_failed('step-up proof wrong')))
    assert su.begun == ['dvc_u'] and su.ended == ['dvc_u'], 'the reservation leaked'
    assert su.counted == ['dvc_u']
    assert [s.fn for s in req.submits] == [routes.commands.revoke_device]
    assert su.cleared == ['dvc_u']                          # cleared by the revoke only

    good = StepUp(admit=True, trips=False)
    req = Req(principal=_principal(origin='paired'), proven=True)
    req.api.step_up = good
    assert routes._with_step_up(req, '482913', lambda proof: {'ok': True}) == {'ok': True}
    assert good.begun == ['dvc_u'] and good.ended == ['dvc_u'] and good.cleared == ['dvc_u']
    assert good.counted == []

    unweighed = StepUp(admit=True, trips=False)
    req = Req(principal=_principal(origin='paired'), proven=False)
    req.api.step_up = unweighed
    assert routes._with_step_up(req, None, lambda proof: {'ok': True}) == {'ok': True}
    assert unweighed.begun == [], 'a request with no proof reserved a slot'
    assert unweighed.cleared == [], 'a proof that weighed nothing cleared the count'


def test_a_guard_refusal_that_is_not_about_the_proof_revokes_nobody():
    """Catch: routes.py:972 read as `if counted` (any GuardFailed counts). A
    device refused because of some other guard would be revoked for a PIN it
    never got wrong, and the fifth such refusal would lock out a good client."""
    su = StepUp(admit=True, trips=True)
    req = Req(principal=_principal(origin='paired'))
    req.api.step_up = su
    with pytest.raises(errors.GuardFailed):
        routes._with_step_up(req, '000000', _raiser(guard_failed('the plan still has 3 tasks')))
    assert su.counted == [], 'an unrelated guard refusal was counted as a wrong PIN'
    assert req.submits == [] and su.cleared == []
    assert su.begun == ['dvc_u'] and su.ended == ['dvc_u']


# ── SUPPORTING · routes.py:961-967: a locked-out device is refused, never served ──

def test_a_locked_out_guess_is_429_and_spends_no_proof():
    """Catch: routes.py:961-967. Answer the refused `begin` by falling through
    and the locked-out client keeps guessing; call `end` on the way out and
    `auth.StepUpFailures.end` decrements a reservation `begin` never gave
    (KeyError, a 500 on a client that is already locked); drop the `Retry-After`
    and the client hammers blind."""
    su = auth.StepUpFailures()
    for _ in range(su.LIMIT):
        su.failed('dvc_u')
    req = Req(principal=_principal(origin='paired'))
    req.api.step_up = su
    tried = []
    got = refused(routes._with_step_up, req, '000000', lambda proof: tried.append(proof) or {})
    assert (got.status, got.code, got.headers) == (429, 'step_up_locked', {'Retry-After': '1'})
    assert tried == [], 'a guess was admitted past the breaker'
    assert [s.fn for s in req.submits] == [routes.commands.revoke_device], \
        'the revoke that did not land was not retried'
    assert not su.locked('dvc_u'), 'the count stayed at LIMIT after a landed revoke'

    su = auth.StepUpFailures()
    for _ in range(su.LIMIT):
        su.failed('dvc_u')
    req = Req(principal=_principal(origin='paired'))
    req.api.step_up = su
    req.raises = RuntimeError('writer busy')                # the retry faults too
    got = refused(routes._with_step_up, req, '000000', _raiser(AssertionError('no guess')))
    assert (got.status, got.code) == (429, 'step_up_locked')
    assert su.locked('dvc_u'), 'the counter was cleared while the revoke still failed'


# ── B3 · routes.py:1054-1058 + row 1265: only `approve` decides a verification ──

def test_only_an_approve_credential_decides_a_verification_and_its_note_defaults():
    """Catch: row 1265 with `scope='observe'` (any reader decides what waited on
    a human), `idempotent=None` (a retried decision runs twice), and
    routes.py:1058 `b.get('note') or ''` read as `b.get('note')` (None reaches
    the decision service); 1057 read as `b.get('id')` so a body that names a
    verification decides that one instead of the path's. The rows keying is
    pinned by `test_every_owned_route_declares_its_scope_key_and_schema`, and
    that the handler submits through the keyed writer seam by the assertion on
    the submitted record here."""
    req = Req(body={'decision': 'accept', 'idempotency_key': 'k1'},
              params={'id': 'vrf_7'}, ret={'decided': True})
    status, out = dispatch(req, 'POST', '/v1/verifications/vrf_7/decide')
    assert (status, out) == (200, {'decided': True}), 'the answer was not the commands'
    (sub,) = req.submits
    assert sub.fn is req.api.decisions.decide
    assert sub.kwargs == {'verification_id': 'vrf_7', 'decision': 'accept', 'note': '',
                          'actor': Ref('user_device', 'prn_u')}
    assert sub.keyed is True and sub.key == 'k1', \
        'the decision was submitted through the unkeyed seam'

    # a body that names another verification must not decide that one: the row
    # is the path's, and that is what the guard checked the scope against
    hijack = Req(body={'decision': 'accept', 'id': 'vrf_OTHER', 'idempotency_key': 'k'},
                params={'id': 'vrf_7'})
    routes.decide_verification(hijack)
    assert hijack.submits[-1].kwargs['verification_id'] == 'vrf_7', 'the body picked the row'
    assert hijack.body['id'] == 'vrf_OTHER'

    for note in (None, ''):
        said = Req(body={'decision': 'reject', 'note': note, 'idempotency_key': 'k'},
                   params={'id': 'vrf_7'})
        routes.decide_verification(said)
        assert said.submits[-1].kwargs['note'] == ''

    no_say = Req(body={'decision': 'accept', 'idempotency_key': 'k'}, params={'id': 'vrf_7'},
                 principal=_principal(scopes=['observe', 'control', 'admin']))
    got = refused(dispatch, no_say, 'POST', '/v1/verifications/vrf_7/decide')
    assert (got.status, got.code, got.detail) == (403, 'scope_required', {'scope': 'approve'})
    assert no_say.submits == [], 'a device without approve decided anyway'

    for body in ({'decision': 'maybe', 'idempotency_key': 'k'}, {'idempotency_key': 'k'},
                 {'decision': 'accept'}, {'decision': 1, 'idempotency_key': 'k'},
                 {'decision': 'accept', 'note': ['a'], 'idempotency_key': 'k'}):
        bad = Req(body=body, params={'id': 'vrf_7'})
        pytest.raises(Invalid, dispatch, bad, 'POST', '/v1/verifications/vrf_7/decide')
        assert bad.submits == [], 'a decision the schema refuses reached the writer'


# ── B4 · routes.py:1026-1027: a window of zero days is refused before any read ──

def test_a_simulation_window_of_zero_is_refused_before_the_database_is_read():
    """Catch: routes.py:1026 written as `if days > 180`. The upper bound is
    pinned at tests/v1/unit/test_gaps_api_routes.py:613-621 ('181' -> Invalid,
    default 30) and the *status* of `?days=0` over the real server at
    tests/v1/integration/test_automation_http.py:61; neither pins WHY the
    request was refused (field `days`, why `is 1..180`) nor that the refusal
    happened before `db.read()` — a mutant that opens the read, builds the
    caller's homes and only then refuses is invisible to both, and it is exactly
    the ownership read this slice must not spend for a request it will not
    answer."""
    req = Req(params={'id': 'aut_1'}, query={'days': ['0']})
    bad = pytest.raises(Invalid, routes.simulate_automation, req)
    assert (bad.value.field, bad.value.why) == ('days', 'is 1..180')
    assert req.api.db.reads == 0 and req.api.db.closed_reads == 0 and req.api.db.live == 0

    seen = []

    def simulate(conn, automation_id, *, now, days, homes):
        seen.append((conn, days, homes()))
        return {'days': days}

    monkey = pytest.MonkeyPatch()
    monkey.setattr(routes.automations, 'simulate', simulate)
    monkey.setattr(routes.resources, 'homes', lambda *a, **k: HOMES)
    try:
        for raw in ('1', '180'):
            ok = Req(params={'id': 'aut_1'}, query={'days': [raw]})
            assert routes.simulate_automation(ok)[1] == {'days': int(raw)}
            conn, days, spent = seen[-1]
            assert days == int(raw) and spent is HOMES
            assert conn.db is ok.api.db and conn.number == 1
            assert ok.api.db.reads == 1 and ok.api.db.live == 0
    finally:
        monkey.undo()


@pytest.mark.parametrize('raw', ['x', '', ' 1', '+1', '-1', '0x7', '1' * 19, '1_0'],
                         ids=['word', 'empty', 'space', 'plus', 'minus', 'hex', 'nineteen',
                              'underscore'])
def test_a_simulation_window_is_digits_only(raw):
    """Catch: routes.py:1025 replacing `_cursor(raw, 'days')` with `int(raw)`.
    Then ' 1', '+1', '-1' and '1_0' all parse, the range check sees a different
    number than the client sent, and a 19-digit window is a 500 instead of a 400."""
    req = Req(params={'id': 'aut_1'}, query={'days': [raw]})
    bad = pytest.raises(Invalid, routes.simulate_automation, req)
    assert (bad.value.field, bad.value.why) == ('days', 'is an integer >= 0')
    assert req.api.db.reads == 0, 'a refused window still opened a read'


# ── B6 · routes.py:1024 + 91-93: a repeated `days` takes the LAST value ──

def test_a_repeated_days_parameter_takes_the_last_value_and_nothing_else():
    """Catch: routes.py:1024 with `_one` reading `query[name][0]`, or joining the
    values. `?days=0&days=7` would answer 200 for a window that cannot exist, or
    `?days=7&days=0` 400 for a legal one; and `?days=` (an empty list) is not the
    same request as no `days` at all — routes.py:92 `if not values`. The
    last-value rule itself is pinned for the *events* feed
    (tests/v1/unit/test_gaps_api_routes.py:536-551) and for no other parameter:
    nothing pins it where it decides a bound, `days`."""
    seen = []

    def simulate(conn, automation_id, *, now, days, homes):
        seen.append(days)
        return {'days': days}

    monkey = pytest.MonkeyPatch()
    monkey.setattr(routes.automations, 'simulate', simulate)
    monkey.setattr(routes.resources, 'homes', lambda *a, **k: HOMES)
    try:
        last_wins = Req(params={'id': 'aut_1'}, query={'days': ['0', '7']})
        assert routes.simulate_automation(last_wins)[1] == {'days': 7}
        assert seen == [7], 'the first value won'

        last_is_bad = Req(params={'id': 'aut_1'}, query={'days': ['7', '0']})
        bad = pytest.raises(Invalid, routes.simulate_automation, last_is_bad)
        assert (bad.value.field, bad.value.why) == ('days', 'is 1..180')
        assert last_is_bad.api.db.reads == 0

        empty = Req(params={'id': 'aut_1'}, query={'days': []})
        assert routes.simulate_automation(empty)[1] == {'days': 30}
        assert seen == [7, 30], 'an empty parameter was read as a window'
    finally:
        monkey.undo()


# ── B5 · routes.py:1011-1036: the automation reads keep ownership in the query ──

def test_the_automation_reads_hand_the_query_a_homes_reader_of_their_own_read(tmp_path):
    """Catch: routes.py:1016-1036 with `homes=` dropped, or the homes computed
    eagerly / from a second read, and 1019 with `schedule_faults()` not
    forwarded. Drop `homes=` and every run and mission row comes back unscrubbed
    for a reader that owns none of those accounts: no existing test drives these
    three handlers with a fake `resources.homes` (tests/v1/integration/
    test_t144_leak_sweep.py:291-292 calls `queries.list_verifications` directly,
    without the handler, so it cannot see the wiring). `list_automations`'
    forwarding is also pinned over HTTP at tests/v1/integration/
    test_automation_http.py:77; `get_automation`'s is not pinned anywhere."""
    api = Api(tmp_path=tmp_path)
    before = files_under(tmp_path)
    req = Req(api=api, params={'id': 'aut_1'})
    built = []

    def homes(conn, registry, callers):
        assert conn.db.live == 1 and conn.db.closed_reads == 0, \
            'the ownership read ran outside the read it belongs to'
        built.append((conn, registry, callers))
        return HOMES

    seen = {}

    def get_automation(conn, automation_id, *, homes=None, schedule_faults=None):
        # the query is the one that decides whether the reader is spent, and it
        # spends it while its own read is still open
        seen['get'] = (conn, automation_id, callable(homes), homes() if callable(homes) else None,
                       schedule_faults)
        return {'id': automation_id}

    def explain(conn, run_id, *, homes=None):
        seen['explain'] = (conn, run_id, callable(homes),
                           homes() if callable(homes) else None)
        return {'id': run_id}

    def list_automations(conn, schedule_faults=None):
        seen['list'] = (conn, schedule_faults)
        return {'automations': []}

    monkey = pytest.MonkeyPatch()
    monkey.setattr(routes.resources, 'homes', homes)
    monkey.setattr(routes.automations, 'get_automation', get_automation)
    monkey.setattr(routes.automations, 'explain', explain)
    monkey.setattr(routes.automations, 'list_automations', list_automations)
    try:
        assert routes.get_automation(req)[0] == 200
        conn, _id, is_reader, spent, faults = seen['get']
        assert conn.db is api.db and is_reader, 'the query was handed no homes reader'
        assert spent is HOMES and built == [(conn, None, ())], \
            'the reader did not come from this read, or the handler spent it itself'
        assert faults is api.schedule_faults.ret

        api2 = Api(tmp_path=tmp_path)
        assert routes.get_automation_run(Req(api=api2, params={'id': 'arn_1'}))[0] == 200
        conn, _rid, is_reader, spent = seen['explain']
        assert conn.db is api2.db and is_reader and spent is HOMES
        assert api2.db.reads == 1 and api2.db.live == 0

        api3 = Api(tmp_path=tmp_path)
        assert routes.list_automations(Req(api=api3))[0] == 200
        listed_conn, listed_faults = seen['list']
        assert listed_conn.db is api3.db and listed_faults is api3.schedule_faults.ret
        assert api3.schedule_faults.calls == [((), {})] and api3.db.reads == 1
        assert len(built) == 2, 'list_automations spent an ownership read it never asked for'
        assert files_under(tmp_path) == before, 'a read wrote into the runtime root'
    finally:
        monkey.undo()


# ── B7 · routes.py:1047-1051: a stale state version is carried, not swallowed ──

def test_a_stale_automation_state_version_reaches_the_command_once():
    """Catch: routes.py:1051 without `'expected_version': b.get(...)` — two
    screens then race and the enable that lost the row silently wins, because the
    command is never told what the client read — and a lost race retried here
    instead of answered 409. Row 1290 (`admin`, `required`, AUTOMATION_STATE) is
    pinned over HTTP at tests/v1/integration/test_automation_http.py:65-73; the
    version the client read is carried by no test at all — the judge scenarios
    (tests/v1/judge/test_s10_automation.py:16) enable without one."""
    req = Req(body={'action': 'enable', 'expected_version': 3, 'idempotency_key': 'k'},
              params={'id': 'aut_1'}, ret={'state': 'ENABLED'})
    status, out = dispatch(req, 'POST', '/v1/automations/aut_1/state')
    assert (status, out) == (200, {'state': 'ENABLED'})
    (sub,) = req.submits
    assert sub.fn is routes.automations.set_state
    assert sub.kwargs == {'automation_id': 'aut_1', 'action': 'enable', 'expected_version': 3,
                          'actor': Ref('user_device', 'prn_u')}
    assert sub.keyed is True and sub.key == 'k'

    plain = Req(body={'action': 'disable', 'idempotency_key': 'k'}, params={'id': 'aut_1'})
    routes.set_automation_state(plain)
    assert plain.submits[-1].kwargs['expected_version'] is None

    stale = Req(body={'action': 'enable', 'expected_version': 2, 'idempotency_key': 'k'},
                params={'id': 'aut_1'}, raises=errors.VersionConflict('aut_1', 2, 4))
    pytest.raises(errors.VersionConflict, dispatch, stale, 'POST',
                  '/v1/automations/aut_1/state')
    assert [s.kwargs['expected_version'] for s in stale.submits] == [2], 'the write retried'
    assert stale.api.sse.close_device.calls == []

    outsider = Req(body={'action': 'enable', 'idempotency_key': 'k'}, params={'id': 'aut_1'},
                   principal=_principal(scopes=['observe', 'control', 'approve']))
    got = refused(dispatch, outsider, 'POST', '/v1/automations/aut_1/state')
    assert (got.status, got.code, got.detail) == (403, 'scope_required', {'scope': 'admin'})
    assert outsider.submits == [], 'a non-admin changed an automations state'

    for body in ({'action': 'run-now', 'idempotency_key': 'k'}, {'idempotency_key': 'k'},
                 {'action': 'enable'}, {'action': 1, 'idempotency_key': 'k'}):
        bad = Req(body=body, params={'id': 'aut_1'})
        pytest.raises(Invalid, dispatch, bad, 'POST', '/v1/automations/aut_1/state')
        assert bad.submits == [], 'an action outside the enum reached the writer'


# ── B8 · routes.py:1066-1073: a user review forges the lists it was not given ──

def test_a_user_review_forges_the_requirement_lists_it_was_not_given():
    """Catch: routes.py:1071-1073 with the `or []` dropped (the command is handed
    None where it iterates a list) or applied unconditionally (a review that
    names what it checked — or names the SAME requirement in both lists, which
    only P13 may judge — is stripped of its evidence before the guard sees it),
    and row 1269's `approve` scope. No existing test drives this handler at all:
    `review_mission` appears in no other file, and the requirement lists are only
    ever built by the P13 judge (tests/v1/unit/test_gaps_core_application_
    verification.py:1031)."""
    req = Req(body={'verdict': 'accept', 'idempotency_key': 'k'}, params={'id': 'msn_1'},
              ret={'reviewed': True})
    status, out = dispatch(req, 'POST', '/v1/missions/msn_1/review')
    assert (status, out) == (200, {'reviewed': True}), 'the answer was not the command output'
    (sub,) = req.submits
    assert sub.fn is req.api.decisions.review
    assert sub.kwargs == {'mission_id': 'msn_1', 'verdict': 'accept', 'note': '',
                          'requirements_met': [], 'requirements_missing': [],
                          'actor': Ref('user_device', 'prn_u')}
    assert sub.keyed is True and sub.key == 'k'

    lineage = Req(params={'id': 'msn_1'}, principal=_principal(origin='paired'), body={
        'verdict': 'changes_requested', 'note': 'both', 'requirements_met': ['runs', 'tests'],
        'requirements_missing': ['runs', 'docs'], 'idempotency_key': 'k2'})
    routes.review_mission(lineage)
    gave = lineage.submits[-1].kwargs
    assert gave['requirements_met'] == ['runs', 'tests'], 'the met list was dropped'
    assert gave['requirements_missing'] == ['runs', 'docs'], 'the missing list was dropped'
    assert gave['note'] == 'both' and gave['mission_id'] == 'msn_1'

    for empty in ({}, {'requirements_met': None, 'requirements_missing': None},
                  {'requirements_met': [], 'requirements_missing': []}, {'note': None}):
        r = Req(body=dict(empty, verdict='reject', idempotency_key='k'), params={'id': 'msn_1'})
        routes.review_mission(r)
        assert r.submits[-1].kwargs['requirements_met'] == []
        assert r.submits[-1].kwargs['requirements_missing'] == []
        assert r.submits[-1].kwargs['note'] == ''

    no_say = Req(body={'verdict': 'accept', 'idempotency_key': 'k'}, params={'id': 'msn_1'},
                 principal=_principal(scopes=['observe', 'control', 'admin']))
    got = refused(dispatch, no_say, 'POST', '/v1/missions/msn_1/review')
    assert (got.status, got.code, got.detail) == (403, 'scope_required', {'scope': 'approve'})
    assert no_say.submits == [], 'a device without approve reviewed a mission'

    for body in ({'idempotency_key': 'k'}, {'verdict': 'approved', 'idempotency_key': 'k'},
                 {'verdict': 'accept', 'requirements_met': 'runs', 'idempotency_key': 'k'},
                 {'verdict': 'accept', 'requirements_missing': [1], 'idempotency_key': 'k'},
                 {'verdict': 'accept'}):
        bad = Req(body=body, params={'id': 'msn_1'})
        pytest.raises(Invalid, dispatch, bad, 'POST', '/v1/missions/msn_1/review')
        assert bad.submits == [], 'a malformed review was recorded'


# ── B9 · routes.py:1076-1078: abandon names the path's task and nothing else ──

def test_abandoning_names_the_tasks_own_row_and_leaves_nothing_behind():
    """Catch: routes.py:1078 taking the task id from the body (one request then
    abandons a task other than the one the URL named, and only the path's owner
    was checked by the guard), and `(req.body or {})` dropped (a body-less POST
    is a 500). A denial that was caught here instead of propagated would answer
    200 for a foreign or already-decided task that changed nothing. The closest
    coverage calls the application command directly (tests/v1/integration/
    test_verification.py:335-338, `core.abandon_integration`), so neither the
    path-vs-body precedence nor the body-less POST is reachable from it."""
    # the body carries a field the row does not declare, on purpose: it is the
    # handler that must ignore it (schemas would refuse it on the way in)
    req = Req(body={'reason': 'conflict, redo it', 'task_id': 'tsk_OTHER',
                    'idempotency_key': 'k'}, params={'id': 'tsk_1'})
    routes.abandon_integration(req)
    assert req.body['task_id'] == 'tsk_OTHER'
    (sub,) = req.submits
    assert sub.fn is routes.verification.abandon_integration
    assert sub.kwargs == {'task_id': 'tsk_1', 'reason': 'conflict, redo it',
                          'actor': Ref('user_device', 'prn_u')}, 'the body picked the task'
    assert sub.keyed is True and sub.key == 'k'

    bare = Req(body=None, params={'id': 'tsk_1'})
    routes.abandon_integration(bare)
    assert bare.submits[-1].kwargs == {'task_id': 'tsk_1', 'reason': '',
                                       'actor': Ref('user_device', 'prn_u')}
    for empty in ({}, {'reason': None}, {'reason': ''}):
        r = Req(body=dict(empty, idempotency_key='k'), params={'id': 'tsk_1'})
        routes.abandon_integration(r)
        assert r.submits[-1].kwargs['reason'] == ''

    foreign = Req(body={'reason': 'mine?', 'idempotency_key': 'k'}, params={'id': 'tsk_x'},
                  raises=errors.NotFound('tsk_x'))
    pytest.raises(errors.NotFound, dispatch, foreign, 'POST',
                  '/v1/tasks/tsk_x/integration/abandon')
    assert [s.fn for s in foreign.submits] == [routes.verification.abandon_integration]
    assert foreign.api.sse.close_device.calls == [], 'a denial touched another device'

    not_user = Req(body={'reason': 'x', 'idempotency_key': 'k'}, params={'id': 'tsk_1'},
                   raises=errors.LineageRefused('only a user device abandons a merge'))
    pytest.raises(errors.LineageRefused, dispatch, not_user, 'POST',
                  '/v1/tasks/tsk_1/integration/abandon')
    assert len(not_user.submits) == 1, 'a refused abandon was retried here'

    outsider = Req(body={'reason': 'x', 'idempotency_key': 'k'}, params={'id': 'tsk_1'},
                   principal=_principal(scopes=['observe', 'approve', 'admin']))
    got = refused(dispatch, outsider, 'POST', '/v1/tasks/tsk_1/integration/abandon')
    assert (got.status, got.code, got.detail) == (403, 'scope_required', {'scope': 'control'})
    assert outsider.submits == [], 'a device without control abandoned a merge'


# ── B10 · routes.py:1081-1084 + row 1127: revoke is a command, then a stream close ──

def test_a_revoke_lands_in_the_writer_before_its_streams_close_and_only_by_command(tmp_path):
    """Catch: routes.py:1082-1083 with `close_device` moved above the `run` (a
    revoke that then faulted has kicked out a device that is not revoked and
    answered with a command that never ran). The `admin` scope and the
    `'required'` keying of row 1127 are already pinned over HTTP
    (tests/v1/integration/test_api_auth.py:156, test_api_idempotency.py:56);
    what nothing pins is the ORDER — that the streams go down only after the
    write landed — because no existing test injects a failing revoke into this
    handler (tests/v1/integration/test_api_audit_fixes.py:113 injects one into
    the rearm breaker path, over the real server, and only watches statuses and
    call counts)."""
    api = Api(tmp_path=tmp_path)
    before = files_under(tmp_path)
    req = Req(api=api, params={'id': 'dvc_bad'}, ret={'state': 'REVOKED'},
              body={'idempotency_key': 'k-rev'})
    status, out = dispatch(req, 'POST', '/v1/devices/dvc_bad/revoke')
    assert (status, out) == (200, {'state': 'REVOKED'})
    assert api.order == ['run', 'close'], 'the streams were closed before the write'
    (sub,) = req.submits
    assert sub.fn is routes.commands.revoke_device
    assert sub.kwargs == {'device_id': 'dvc_bad', 'actor': Ref('user_device', 'prn_u')}
    assert sub.keyed is True and sub.key == 'k-rev'
    assert api.sse.close_device.calls == [(('dvc_bad',), {})]
    assert files_under(tmp_path) == before, 'a revoke wrote into the runtime root'

    flaky = Req(api=Api(tmp_path=tmp_path), params={'id': 'dvc_bad'},
                body={'idempotency_key': 'k2'}, raises=RuntimeError('writer busy'))
    with pytest.raises(RuntimeError):
        dispatch(flaky, 'POST', '/v1/devices/dvc_bad/revoke')
    assert flaky.api.order == ['run'], 'a failed write still closed the streams'
    assert flaky.api.sse.close_device.calls == []

    outsider = Req(api=Api(tmp_path=tmp_path), params={'id': 'dvc_bad'},
                   body={'idempotency_key': 'k3'},
                   principal=_principal(scopes=['observe', 'control', 'approve']))
    got = refused(dispatch, outsider, 'POST', '/v1/devices/dvc_bad/revoke')
    assert (got.status, got.code, got.detail) == (403, 'scope_required', {'scope': 'admin'})
    assert outsider.submits == [] and outsider.api.order == [], \
        'a non-admin revoke closed a device stream'


# ── SUPPORTING · routes.py:1039-1044: a limit of zero is still a limit ──

def test_a_zero_automation_limit_survives_the_handler_and_an_absent_one_is_not_sent():
    """Catch: routes.py:1041 written on truthiness (`if b.get(k)`): `max_depth:
    0` is dropped, the command falls back to its default depth and the loop
    guard the row exists for is gone — an automation that spawns itself is
    exactly what P14 quarantines."""
    req = Req(body={'name': 'follower', 'trigger': {'type': 'mission.created'},
                    'template': {'title': 't', 'objective': 'o'}, 'max_depth': 0,
                    'rate_limit': 0, 'idempotency_key': 'k'})
    status, out = dispatch(req, 'POST', '/v1/automations')
    assert status == 200 and out == {}
    (sub,) = req.submits
    assert sub.fn is routes.automations.create
    assert sub.kwargs == {'max_depth': 0, 'rate_limit': 0, 'name': 'follower',
                          'trigger': {'type': 'mission.created'},
                          'template': {'title': 't', 'objective': 'o'}, 'project_id': None,
                          'actor': Ref('user_device', 'prn_u')}
    assert sub.keyed is True and sub.key == 'k'

    plain = Req(body={'name': 'n', 'trigger': {}, 'template': {}, 'max_depth': None,
                      'rate_limit': None, 'idempotency_key': 'k'})
    routes.create_automation(plain)
    assert 'max_depth' not in plain.submits[-1].kwargs
    assert 'rate_limit' not in plain.submits[-1].kwargs
    assert plain.submits[-1].kwargs['project_id'] is None

    whole = Req(body={'name': 'n', 'trigger': {}, 'template': {}, 'project_id': 'prj_2',
                      'max_depth': 2, 'rate_limit': 5, 'idempotency_key': 'k'})
    routes.create_automation(whole)
    assert whole.submits[-1].kwargs['max_depth'] == 2
    assert whole.submits[-1].kwargs['rate_limit'] == 5
    assert whole.submits[-1].kwargs['project_id'] == 'prj_2'

    outsider = Req(body={'name': 'n', 'trigger': {}, 'template': {}, 'idempotency_key': 'k'},
                   principal=_principal(scopes=['observe', 'control', 'approve']))
    got = refused(dispatch, outsider, 'POST', '/v1/automations')
    assert (got.status, got.code) == (403, 'scope_required')
    assert outsider.submits == [], 'a non-admin wrote an automation'

    for body in ({'name': 'n', 'trigger': {}, 'idempotency_key': 'k'},
                 {'name': 'n', 'trigger': {}, 'template': {}, 'max_depth': 'deep',
                  'idempotency_key': 'k'},
                 {'name': 'n', 'trigger': {}, 'template': {}},
                 {'name': 'n', 'trigger': [], 'template': {}, 'idempotency_key': 'k'}):
        bad = Req(body=body)
        pytest.raises(Invalid, dispatch, bad, 'POST', '/v1/automations')
        assert bad.submits == [], 'a malformed automation reached the writer'


# ── SUPPORTING · routes.py:999-1006, 1061-1063: the verification reads scrub ──

def test_the_verification_and_review_reads_scrub_through_the_requests_own_homes():
    """Catch: routes.py:999-1006 and 1061-1063 with the `homes=` keyword dropped
    (every check's evidence text comes back unscrubbed for a reader that owns
    none of those accounts) or taken from a second read (the answer then mixes
    two transactions)."""
    seen = {}

    def remember(name):
        def query(conn, ident, *, homes=None):
            seen[name] = (conn, ident, homes)
            return {'id': ident}
        return query

    def missing(conn, ident, *, homes=None):
        raise errors.NotFound(ident)

    built = []

    def homes(conn, registry, callers):
        built.append((conn, registry, callers))
        return HOMES

    monkey = pytest.MonkeyPatch()
    monkey.setattr(routes.queries, 'list_verifications', remember('list_verifications'))
    monkey.setattr(routes.queries, 'get_verification', remember('get_verification'))
    monkey.setattr(routes.queries, 'list_reviews', remember('list_reviews'))
    monkey.setattr(routes.resources, 'homes', homes)
    try:
        for handler, ident, name in ((routes.list_verifications, 'msn_1', 'list_verifications'),
                                     (routes.get_verification, 'vrf_1', 'get_verification'),
                                     (routes.list_reviews, 'msn_1', 'list_reviews')):
            req = Req(params={'id': ident})
            assert handler(req)[0] == 200
            conn, got_id, got_homes = seen[name]
            assert conn.db is req.api.db and got_id == ident and got_homes is HOMES
            assert req.api.db.reads == 1 and req.api.db.closed_reads == 1 and req.api.db.live == 0
        assert (built[0][1], built[0][2]) == (None, ()), 'homes came from somewhere else'

        gone = Req(params={'id': 'msn_gone'})
        monkey.setattr(routes.queries, 'list_verifications', missing)
        pytest.raises(errors.NotFound, routes.list_verifications, gone)
        assert gone.api.db.reads == 1 and gone.api.db.live == 0
        assert gone.api.db.closed_reads == 1, 'the read was left open on a 404'
    finally:
        monkey.undo()


# ── SUPPORTING · the owned rows: a verb is not a guess, and every row says what it needs ──

@pytest.mark.parametrize('method,path', [
    ('DELETE', '/v1/automations'), ('PUT', '/v1/automations/aut_1'),
    ('GET', '/v1/automations/aut_1/state'), ('POST', '/v1/automations/aut_1'),
    ('PUT', '/v1/automations/aut_1/simulate'), ('POST', '/v1/automation-runs/arn_1'),
    ('GET', '/v1/verifications/vrf_1/decide'), ('DELETE', '/v1/missions/msn_1/reviews'),
    ('GET', '/v1/missions/msn_1/review'), ('POST', '/v1/missions/msn_1/reviews'),
    ('GET', '/v1/tasks/tsk_1/integration/abandon'), ('DELETE', '/v1/devices/dvc_1/revoke'),
    ('PUT', '/v1/devices/dvc_1/revoke'),
])
def test_an_owned_route_refuses_a_verb_its_row_does_not_declare(method, path):
    """`match()` (routes.py:1372-1383) over the rows that own this slice: the
    path is known and the verb is not, so the answer is 405 and the handler is
    never reached — never a 404 that hides a writable route, and never the read
    that shares its path."""
    got = refused(routes.match, method, path)
    assert (got.status, got.code) == (405, 'method_not_allowed')


@pytest.mark.parametrize('method,path,scope,idempotent,schema', [
    ('GET', '/v1/automations', 'observe', None, None),
    ('GET', '/v1/automations/aut_1', 'observe', None, None),
    ('GET', '/v1/automations/aut_1/simulate', 'observe', None, None),
    ('GET', '/v1/automation-runs/arn_1', 'observe', None, None),
    ('POST', '/v1/automations', 'admin', 'required', schemas.CREATE_AUTOMATION),
    ('POST', '/v1/automations/aut_1/state', 'admin', 'required', schemas.AUTOMATION_STATE),
    ('GET', '/v1/missions/msn_1/verifications', 'observe', None, None),
    ('GET', '/v1/verifications/vrf_1', 'observe', None, None),
    ('POST', '/v1/verifications/vrf_1/decide', 'approve', 'required',
     schemas.DECIDE_VERIFICATION),
    ('GET', '/v1/missions/msn_1/reviews', 'observe', None, None),
    ('POST', '/v1/missions/msn_1/review', 'approve', 'required', schemas.USER_REVIEW),
    ('POST', '/v1/tasks/tsk_1/integration/abandon', 'control', 'required',
     schemas.ABANDON_INTEGRATION),
    ('POST', '/v1/devices/dvc_1/revoke', 'admin', 'required', schemas.KEYED),
])
def test_every_owned_route_declares_its_scope_key_and_schema(method, path, scope, idempotent,
                                                              schema):
    """The rows behind the handlers at 999-1084: an `observe` read that lost its
    scope (None) is a public read of private rows, and a command that lost
    `'required'` is replayable by accident and writes twice."""
    route, _params = routes.match(method, path)
    assert route.scope == scope
    assert route.idempotent == idempotent
    assert route.request_schema is schema


def test_an_observe_credential_is_enough_to_read_and_never_to_write():
    """The same rows from the other side: a read-scoped credential reaches the
    handler for every owned read, one read each, and is refused — with no
    command, no stream closed and no read opened at all — by every owned
    write."""
    monkey = pytest.MonkeyPatch()
    monkey.setattr(routes.queries, 'list_verifications', lambda c, i, *, homes=None: {'id': i})
    monkey.setattr(routes.queries, 'get_verification', lambda c, i, *, homes=None: {'id': i})
    monkey.setattr(routes.queries, 'list_reviews', lambda c, i, *, homes=None: {'id': i})
    monkey.setattr(routes.automations, 'list_automations', lambda c, sf=None: {'automations': []})
    monkey.setattr(routes.automations, 'get_automation', lambda c, i, *, homes=None, **k: {'id': i})
    monkey.setattr(routes.automations, 'explain', lambda c, i, *, homes=None: {'id': i})
    monkey.setattr(routes.automations, 'simulate', lambda c, i, *, now, days, homes: {'days': days})
    monkey.setattr(routes.resources, 'homes', lambda *a, **k: HOMES)
    for path in ('/v1/automations', '/v1/automations/aut_1', '/v1/automations/aut_1/simulate',
                 '/v1/automation-runs/arn_1', '/v1/missions/msn_1/verifications',
                 '/v1/verifications/vrf_1', '/v1/missions/msn_1/reviews'):
        req = Req(principal=_principal(scopes=['observe']))
        assert dispatch(req, 'GET', path)[0] == 200, path
        assert req.api.db.reads == 1 and req.api.db.live == 0, path
        assert req.submits == [], path
    for path in ('/v1/automations', '/v1/automations/aut_1/state',
                 '/v1/verifications/vrf_1/decide', '/v1/missions/msn_1/review',
                 '/v1/tasks/tsk_1/integration/abandon', '/v1/devices/dvc_1/revoke'):
        req = Req(principal=_principal(scopes=['observe']), body={'idempotency_key': 'k'})
        got = refused(dispatch, req, 'POST', path)
        assert (got.status, got.code) == (403, 'scope_required'), path
        assert req.submits == [] and req.api.sse.close_device.calls == [], path
        assert req.api.db.reads == 0, path
    monkey.undo()

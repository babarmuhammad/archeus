"""T-307: the highest-risk unit gaps in archeus/api/routes.py — the fail-closed
and denial paths, the boundary values and the error paths of the route handlers
and of `match`, driven with fake requests (no Core, no HTTP, no OS calls).

The table itself is pinned elsewhere (test_api_structure, test_api_origin);
nothing here re-pins it. Every OS touch the handlers make (the e-stop sentinel)
is faked through the seams the existing tests use (monkeypatch on the objects
the handler looks up at call time); the in-memory credential machines
(`auth.LaunchCodes`, `auth.PairingCodes`) are the real ones: they are pure and
platform-neutral.
"""

from types import SimpleNamespace

import pytest

from archeus.api import auth, routes
from archeus.api.schemas import Invalid
from archeus.core import metrics
from archeus.core.application import attention, errors
from archeus.core.domain import guards
from archeus.node import local

LOCAL_HOST = '127.0.0.1:7337'
TUNNEL_HOST = 'pc.tailnet.ts.net'
LOOPBACK = ('127.0.0.1', 54321)
REMOTE = ('10.1.2.3', 54321)


def _principal(**over):
    p = {'principal_id': 'prn_u', 'device_id': 'dvc_u', 'scopes': list(auth.SCOPES),
         'origin': 'local'}
    p.update(over)
    return p


class _Rec:
    """A fake collaborator: records calls, optionally raises."""

    def __init__(self, ret=None, raises=None):
        self.calls, self.ret, self.raises = [], ret, raises

    def __call__(self, *args, **kw):
        self.calls.append((args, kw))
        if self.raises is not None:
            raise self.raises
        return self.ret


def _api(**over):
    api = SimpleNamespace(
        db=None,
        origin=SimpleNamespace(local_host=lambda h: h == LOCAL_HOST, remote=None),
        launch=SimpleNamespace(mint=_Rec(ret='code-minted'), redeem=_Rec(ret=None)),
        pairing=SimpleNamespace(mint=_Rec(ret='CODE'), redeem=_Rec(ret=None)),
        resources=SimpleNamespace(registry=None, callers=None),
        sse=SimpleNamespace(serve=_Rec(ret=('stream', 'sent')), close_device=_Rec()),
        step_up=SimpleNamespace(begin=lambda d: True, end=lambda d: None, failed=lambda device: False, reset=_Rec()),
        executions=SimpleNamespace(estop=_Rec(ret={}), rearm=_Rec(ret={'rearmed': True})),
        authorization=SimpleNamespace(decide=_Rec(ret={}),
                                      decide_by_message=_Rec(ret={'message_id': 'msg_1'})),
        conversations=SimpleNamespace(choose=_Rec(ret={'chosen': True}),
                                      confirm_by_message=_Rec(ret={})),
        schedule_faults=_Rec(ret={}))
    api.__dict__.update(over)
    return api


class _Req:
    """The handler-facing half of server.Handler: body/query/headers/params/
    principal/peer plus the writer seam `run`, recorded."""

    def __init__(self, api=None, body=None, query=None, headers=None, params=None,
                 principal=None, peer=LOOPBACK, replayed=False, proven=False, run_ret=None,
                 raises=None, order=None):
        self.api = _api() if api is None else api
        self.body = {} if body is None else body
        self.query = {} if query is None else query
        self.headers = {} if headers is None else headers
        self.params = {} if params is None else params
        self.principal = _principal() if principal is None else principal
        self.peer = peer
        self.replayed, self.proven = replayed, proven
        self.runs = []
        self.ret = {'device_id': 'dvc_new'} if run_ret is None else run_ret
        self.raises = raises
        self.order = order

    def run(self, fn, kwargs, *, actor_id=None, keyed=True):
        self.runs.append(SimpleNamespace(fn=fn, kwargs=kwargs, actor_id=actor_id,
                                         keyed=keyed))
        if self.order is not None:
            self.order.append('run')
        if self.raises is not None:
            raised, self.raises = self.raises, None         # one command may fail; the
            raise raised                                    # revocation after it runs
        return dict(self.ret)


class _Db:
    def __init__(self):
        self.reads = 0

    def read(self):
        db = self

        class _Cm:
            def __enter__(self):
                db.reads += 1
                return 'conn'

            def __exit__(self, *exc):
                return False

        return _Cm()


def _guard_failed(reason):
    return errors.GuardFailed('user_device', 'ARMED', 'ARMED', 'rearm',
                              guards.GuardResult('step_up', False, reason))


def _refused(call, *args, **kw):
    with pytest.raises(routes.Refused) as e:
        call(*args, **kw)
    return e.value


# ── match(): exact method, anchored path, no parameter across a '/' ──

def test_match_selects_the_route_by_method_and_path_and_never_guesses():
    r, params = routes.match('GET', '/v1/missions')
    assert (r.handler, params) == (routes.list_missions, {})
    r, _p = routes.match('POST', '/v1/missions')
    assert r.handler is routes.create_mission                 # same path, other verb
    with pytest.raises(routes.Refused) as e:
        routes.match('DELETE', '/v1/missions')                # path known, verb not
    assert (e.value.status, e.value.code) == (405, 'method_not_allowed')
    with pytest.raises(routes.Refused) as e:
        routes.match('GET', '/v1/nope')
    assert (e.value.status, e.value.code) == (404, 'not_found')


def test_a_method_of_the_wrong_case_or_a_trailing_slash_matches_nothing():
    with pytest.raises(routes.Refused) as e:                  # exact comparison
        routes.match('get', '/v1/version')
    assert e.value.status == 405
    with pytest.raises(routes.Refused) as e:                  # '^path$' is anchored
        routes.match('GET', '/v1/version/')
    assert (e.value.status, e.value.code) == (404, 'not_found')


@pytest.mark.parametrize('path', ['/v1/missions/a/b', '/v1/plans/a/b', '/v1/missions/'])
def test_a_path_parameter_never_crosses_a_slash(path):
    with pytest.raises(routes.Refused) as e:                  # `[^/]+`, not `.+`
        routes.match('GET', path)
    assert (e.value.status, e.value.code) == (404, 'not_found')


def test_the_wildcard_asset_path_needs_its_slash_and_something_behind_it():
    r, params = routes.match('GET', '/assets/app.js')
    assert (r.handler, params) == (routes.static_asset, {'path': 'app.js'})
    _r, params = routes.match('GET', '/assets/dir/app.js')    # it may hold slashes
    assert params == {'path': 'dir/app.js'}
    for bad in ('/assets', '/assets/'):
        with pytest.raises(routes.Refused) as e:
            routes.match('GET', bad)
        assert (e.value.status, e.value.code) == (404, 'not_found'), bad
    with pytest.raises(routes.Refused) as e:                  # the wildcard route is
        routes.match('POST', '/assets/app.js')                # known: 405, not 404
    assert e.value.status == 405


# ── _loopback(): a tunnel forwards from loopback, so the Host is checked too ──

LOCAL_ONLY = {'launch_code': (routes.launch_code, {}),
              'launch_redeem': (routes.launch_redeem, {'code': 'x'}),
              'pair_start': (routes.pair_start, {})}


@pytest.mark.parametrize('name', ['launch_code', 'launch_redeem', 'pair_start'])
@pytest.mark.parametrize('peer,host', [(LOOPBACK, TUNNEL_HOST), (REMOTE, LOCAL_HOST)],
                         ids=['tunnel-host', 'remote-peer'])
def test_a_local_only_route_refuses_either_half_of_the_loopback_proof(name, peer, host):
    handler, body = LOCAL_ONLY[name]
    req = _Req(peer=peer, headers={'Host': host}, body=body)
    got = _refused(handler, req)
    assert (got.status, got.code) == (403, 'host_not_allowed')
    assert req.runs == []                                     # nothing ran
    if name == 'launch_code':
        assert req.api.launch.mint.calls == []                # nothing was minted
    if name == 'pair_start':
        assert req.api.pairing.mint.calls == []


def test_the_loopback_pair_mint_is_allowed_and_answers_the_public_url():
    req = _Req(headers={'Host': LOCAL_HOST}, body={'name': 'phone'})
    status, out = routes.pair_start(req)
    assert status == 200 and out['url'] is None                # no remote configured
    assert out['expires_in'] == int(auth.PAIR_TTL_S)
    req.api.origin.remote = (TUNNEL_HOST,)
    status, out = routes.pair_start(req)
    assert out['url'] == 'https://%s/#pair=%s' % (TUNNEL_HOST, 'CODE')


# ── launch/redeem: the grant is bounded, a refused code writes nothing ──

def test_a_launch_code_always_includes_observe():
    req = _Req(body={'scopes': ['control']}, headers={'Host': LOCAL_HOST})
    bad = pytest.raises(Invalid, routes.launch_code, req)
    assert (bad.value.field, bad.value.why) == ('scopes', 'always includes observe')
    assert req.api.launch.mint.calls == []
    req = _Req(body={'scopes': []}, headers={'Host': LOCAL_HOST})   # [] falls back
    status, out = routes.launch_code(req)
    assert out['scopes'] == list(auth.LAUNCH_SCOPES)


def test_a_launch_code_cannot_ask_for_a_scope_the_minter_lacks():
    req = _Req(body={'scopes': ['observe', 'admin']}, headers={'Host': LOCAL_HOST},
               principal=_principal(scopes=['observe', 'control']))
    got = _refused(routes.launch_code, req)
    assert (got.status, got.code, got.detail) == (403, 'scope_required', {'scope': 'admin'})
    assert req.api.launch.mint.calls == []                      # nothing was minted


def test_a_launch_code_grants_the_asked_scopes_in_the_canonical_order():
    req = _Req(body={'scopes': ['approve', 'observe', 'control'],
                     'supersede': 'slot-1'}, headers={'Host': LOCAL_HOST})
    status, out = routes.launch_code(req)
    wanted = [s for s in auth.SCOPES if s in ('approve', 'observe', 'control')]
    assert out['scopes'] == wanted                             # the canonical order wins
    (args, _kw) = req.api.launch.mint.calls[0]
    assert args == ('prn_u', 'dvc_u', wanted, 'slot-1')         # supersede fixed at mint
    assert out['expires_in'] == int(auth.LAUNCH_TTL_S)


def test_a_used_or_unknown_launch_code_is_401_and_registers_nothing():
    codes = auth.LaunchCodes()
    code = codes.mint('prn_m', 'dvc_m', ('observe', 'control'), 'slot')
    req = _Req(body={'code': 'never-minted', 'platform': 'web'}, headers={'Host': LOCAL_HOST})
    req.api.launch = codes
    got = _refused(routes.launch_redeem, req)
    assert (got.status, got.code) == (401, 'invalid_launch_code')
    assert req.runs == []                                       # no command, no device
    good = _Req(body={'code': code, 'platform': 'web'}, headers={'Host': LOCAL_HOST})
    good.api.launch = codes
    status, out = routes.launch_redeem(good)                    # the code works once
    assert status == 200 and out['device_id'] == 'dvc_new'
    again = _Req(body={'code': code, 'platform': 'web'}, headers={'Host': LOCAL_HOST})
    again.api.launch = codes
    got = _refused(routes.launch_redeem, again)                 # and the pop IS the use
    assert (got.status, got.code) == (401, 'invalid_launch_code')


def test_a_launch_redeem_carries_only_the_token_hash_and_no_idempotency_key():
    codes = auth.LaunchCodes()
    code = codes.mint('prn_m', 'dvc_m', ('observe', 'control'), None)
    req = _Req(body={'code': code, 'platform': 'web', 'name': '  '},
               headers={'Host': LOCAL_HOST})
    req.api.launch = codes
    status, out = routes.launch_redeem(req)
    (run,) = req.runs
    assert run.fn is routes.commands.register_device
    assert run.keyed is False                                   # A4: nothing stores it
    assert run.actor_id == 'prn_m'                              # the minter decides
    assert run.kwargs['token_hash'] == auth.token_hash(out['token'])
    assert 'token' not in run.kwargs                            # the token never enters
    assert run.kwargs['name'] == 'browser (web)'                # blank name falls back
    assert run.kwargs['scopes'] == ['observe', 'control']       # the minter's grant


# ── pairing: everything checkable is checked before the code is spent ──

def _pairing_with_code():
    pairing = auth.PairingCodes()
    grant = {'starter': 'prn_s', 'device_id': 'dvc_s', 'scopes': ['observe'], 'name': None,
             'host_label': None}
    return pairing, pairing.mint(grant)


@pytest.mark.parametrize('pin', ['12345', '1234567890123', 'abcdef', '12345a', ' 123456'],
                         ids=['short', 'long', 'alpha', 'alnum', 'space'])
def test_a_malformed_pin_is_refused_without_spending_the_pairing_code(pin):
    pairing, code = _pairing_with_code()
    req = _Req(body={'code': code, 'platform': 'android', 'pin': pin})
    req.api.pairing = pairing
    bad = pytest.raises(Invalid, routes.pair_redeem, req)
    assert (bad.value.field, bad.value.why) == ('pin', 'is 6 to 12 digits')
    assert req.runs == []
    ok = _Req(body={'code': code, 'platform': 'android', 'pin': '482913'})
    ok.api.pairing = pairing
    routes.pair_redeem(ok)                                      # the code was not spent


def test_a_blank_pairing_name_is_refused_before_the_code_is_spent():
    pairing, code = _pairing_with_code()
    req = _Req(body={'code': code, 'platform': 'android', 'name': '   '})
    req.api.pairing = pairing
    bad = pytest.raises(Invalid, routes.pair_redeem, req)
    assert (bad.value.field, bad.value.why) == ('name', 'is a non-empty string')
    assert req.runs == []


def test_an_unknown_pairing_code_is_401_and_runs_no_command():
    pairing, _code = _pairing_with_code()
    req = _Req(body={'code': 'x' * 22, 'platform': 'android'})
    req.api.pairing = pairing
    got = _refused(routes.pair_redeem, req)
    assert (got.status, got.code) == (401, 'invalid_pairing_code')
    assert req.runs == []


def test_the_pairing_breaker_answers_429_with_the_retry_window():
    pairing, code = _pairing_with_code()
    statuses = []
    for _ in range(auth.PairingCodes.FAIL_LIMIT + 1):
        req = _Req(body={'code': 'x' * 22, 'platform': 'web'})
        req.api.pairing = pairing
        statuses.append(_refused(routes.pair_redeem, req).status)
    assert statuses[:10] == [401] * 10 and statuses[10] == 429   # the 11th burns it
    req = _Req(body={'code': code, 'platform': 'web'})            # a live code: still 429
    req.api.pairing = pairing
    got = _refused(routes.pair_redeem, req)
    assert (got.status, got.code) == (429, 'pairing_locked')
    assert got.headers == {'Retry-After': str(int(auth.PairingCodes.FAIL_WINDOW_S))}
    assert req.runs == []


def test_a_pair_redeem_hashes_the_pin_and_registers_as_the_starter():
    pairing, code = _pairing_with_code()
    req = _Req(body={'code': code, 'platform': 'android', 'pin': '482913'})
    req.api.pairing = pairing
    status, out = routes.pair_redeem(req)
    assert status == 200 and out['scopes'] == ['observe']
    (run,) = req.runs
    assert run.fn is routes.commands.register_device
    assert run.keyed is False and run.actor_id == 'prn_s'       # the starter decides
    record = run.kwargs['pin_hash']
    assert record != '482913' and 'pin' not in run.kwargs        # never the PIN itself
    assert routes.commands.pin_matches(record, '482913')
    assert not routes.commands.pin_matches(record, '000000')
    assert run.kwargs['token_hash'] == auth.token_hash(out['token'])
    assert run.kwargs['name'] == 'paired android'               # the grant's name was None


def test_pair_start_narrows_the_grant_and_refuses_a_blank_name_or_label():
    req = _Req(headers={'Host': LOCAL_HOST}, body={'scopes': ['admin', 'observe', 'bogus']})
    status, out = routes.pair_start(req)
    (grant,), _kw = req.api.pairing.mint.calls[0]
    assert grant['scopes'] == ['observe', 'admin']              # SCOPES order, no bogus
    req = _Req(headers={'Host': LOCAL_HOST}, body={'scopes': ['admin']})
    bad = pytest.raises(Invalid, routes.pair_start, req)
    assert (bad.value.field, bad.value.why) == ('scopes', 'always includes observe')
    for field in ('name', 'host_label'):
        req = _Req(headers={'Host': LOCAL_HOST}, body={field: '   '})
        bad = pytest.raises(Invalid, routes.pair_start, req)
        assert (bad.value.field, bad.value.why) == (field, 'is a non-empty string')
        assert req.api.pairing.mint.calls == []                 # nothing minted


# ── post_message / decide_approval: a DENY never answers 200 ──

def test_a_message_carrying_both_a_decision_and_a_confirmation_is_rejected():
    req = _Req(body={'text': 'x', 'decision': {'approval_id': 'apr_1',
                                               'action_hash': 'a' * 64},
                     'confirm': {'message_id': 'msg_9'}})
    with pytest.raises(ValueError) as e:
        routes.post_message(req)
    assert 'not both' in str(e.value)
    assert req.runs == []


def test_a_confirmation_only_message_goes_to_the_stop_confirm_command():
    req = _Req(params={'id': 'cvs_1'}, body={'text': 'stop', 'confirm': {'message_id': 'm'}})
    routes.post_message(req)
    (run,) = req.runs
    assert run.fn is req.api.conversations.confirm_by_message
    assert run.kwargs == {'text': 'stop', 'conversation_id': 'cvs_1', 'message_id': 'm'}


def test_a_plain_message_posts_without_touching_the_approval_path():
    req = _Req(params={'id': 'cvs_1'}, body={'text': 'hello', 'in_reply_to': 'msg_2'})
    routes.post_message(req)
    (run,) = req.runs
    assert run.fn is routes.conversation.post_message
    assert run.kwargs == {'text': 'hello', 'conversation_id': 'cvs_1',
                          'in_reply_to': 'msg_2'}


def test_a_denied_chat_decision_answers_423_with_the_approval_id():
    req = _Req(params={'id': 'cvs_1'}, principal=_principal(scopes=['control', 'approve']),
               body={'text': 'approve',
                     'decision': {'approval_id': 'apr_1', 'action_hash': 'a' * 64}},
               run_ret={'message_id': 'msg_1',
                        'decided': {'denied': {'reason': 'locked'}, 'approval_id': 'apr_1'}})
    got = _refused(routes.post_message, req)
    assert (got.status, got.code) == (423, 'policy_denied')
    assert got.detail == {'reason': 'locked', 'approval_id': 'apr_1'}


def test_a_denied_approval_decision_answers_423_and_carries_its_id():
    req = _Req(params={'id': 'apr_2'}, body={'decision': 'approve', 'action_hash': 'a' * 64},
               run_ret={'approval_id': 'apr_2', 'denied': {'reason': 'scope'}})
    got = _refused(routes.decide_approval, req)
    assert (got.status, got.code) == (423, 'policy_denied')
    assert got.detail == {'reason': 'scope', 'approval_id': 'apr_2'}


def test_a_step_up_failure_is_counted_only_when_the_client_gave_a_proof():
    """No proof in the body: nothing counts, and the guard failure is re-raised as is."""
    req = _Req(params={'id': 'apr_1'},
               body={'decision': 'approve', 'action_hash': 'a' * 64},
               raises=_guard_failed('the step-up proof is wrong'))
    with pytest.raises(errors.GuardFailed):
        routes.decide_approval(req)
    assert len(req.runs) == 1                                   # only the decide itself
    assert req.api.step_up.reset.calls == []


def test_a_step_up_failure_on_an_approval_counts_towards_revocation():
    req = _Req(params={'id': 'apr_1'},
               body={'decision': 'approve', 'action_hash': 'a' * 64, 'step_up': '999999'},
               principal=_principal(origin='paired'), raises=_guard_failed('step-up wrong'))
    req.api.step_up = SimpleNamespace(begin=lambda d: True, end=lambda d: None, failed=lambda device: True, reset=_Rec())
    with pytest.raises(errors.GuardFailed):
        routes.decide_approval(req)
    (_decide, revoke) = req.runs
    assert revoke.fn is routes.commands.revoke_device
    assert revoke.kwargs == {'device_id': 'dvc_u', 'reason': 'step_up_failures'}
    assert revoke.keyed is False
    assert req.api.step_up.reset.calls == [(('dvc_u',), {})]
    assert req.api.sse.close_device.calls == [(('dvc_u',), {})]


def test_a_replayed_decision_resets_nothing():
    req = _Req(params={'id': 'apr_1'},
               body={'decision': 'approve', 'action_hash': 'a' * 64, 'step_up': '482913'},
               replayed=True, run_ret={'approval_id': 'apr_1'})
    routes.decide_approval(req)
    assert req.api.step_up.reset.calls == []                    # the replay decided nothing


def test_a_decision_that_weighed_no_proof_resets_nothing():
    req = _Req(params={'id': 'apr_1'},
               body={'decision': 'reject', 'action_hash': 'a' * 64, 'step_up': '000000'},
               principal=_principal(origin='paired'), run_ret={'approval_id': 'apr_1'})
    routes.decide_approval(req)
    assert req.api.step_up.reset.calls == []


# ── _step_up_failed: access control only, and only for paired clients ──

def test_only_a_paired_client_with_a_counted_failure_is_revoked_and_its_streams_closed():
    req = _Req(principal=_principal(origin='paired'))
    seen = []

    def failed(device):
        seen.append(device)
        return True

    req.api.step_up = SimpleNamespace(begin=lambda d: True, end=lambda d: None, failed=failed, reset=_Rec())
    routes._step_up_failed(req)
    assert seen == ['dvc_u']
    (run,) = req.runs
    assert run.fn is routes.commands.revoke_device and run.keyed is False
    assert run.kwargs == {'device_id': 'dvc_u', 'reason': 'step_up_failures'}
    assert req.api.step_up.reset.calls == [(('dvc_u',), {})]
    assert req.api.sse.close_device.calls == [(('dvc_u',), {})]

    req = _Req(principal=_principal(origin='local'))            # not paired: never revoked
    req.api.step_up = SimpleNamespace(begin=lambda d: True, end=lambda d: None, failed=lambda d: True, reset=_Rec())
    routes._step_up_failed(req)
    assert req.runs == [] and req.api.sse.close_device.calls == []

    req = _Req(principal=_principal(origin='paired'))           # failure below the limit
    req.api.step_up = SimpleNamespace(begin=lambda d: True, end=lambda d: None, failed=lambda d: False, reset=_Rec())
    routes._step_up_failed(req)
    assert req.runs == [] and req.api.step_up.reset.calls == []


# ── estop / rearm: the sentinel, the replay answer, the counted proof ──

def test_the_estop_hits_the_sentinel_before_it_touches_the_writer(monkeypatch):
    order = []
    monkeypatch.setattr(local.LocalNode, 'engage_estop',
                        staticmethod(lambda: order.append('sentinel')))
    req = _Req(run_ret={'stopped': 2}, order=order)
    status, out = routes.estop(req)
    assert order == ['sentinel', 'run']                         # even if Core dies next
    assert status == 200 and out['armed'] is False and out['stopped'] == 2


def test_a_replayed_rearm_answers_what_core_really_is_and_clears_nothing(monkeypatch):
    req = _Req(body={'step_up': '482913'}, replayed=True, run_ret={'rearmed': True})
    cleared = []
    monkeypatch.setattr(local.LocalNode, 'disarmed', staticmethod(lambda: True))
    monkeypatch.setattr(local.LocalNode, 'clear_estop', staticmethod(lambda: cleared.append(1)))
    status, out = routes.rearm(req)
    assert out == {'rearmed': True, 'armed': False}             # T-107: nothing re-armed
    assert cleared == [] and req.api.step_up.reset.calls == []


def test_a_rearm_with_a_wrong_proof_counts_and_reraises():
    req = _Req(body={'step_up': '000000'}, principal=_principal(origin='paired'),
               raises=_guard_failed('the step-up proof is wrong'))
    req.api.step_up = SimpleNamespace(begin=lambda d: True, end=lambda d: None, failed=lambda d: True, reset=_Rec())
    with pytest.raises(errors.GuardFailed):
        routes.rearm(req)
    assert [r.fn for r in req.runs] == [req.api.executions.rearm,
                                        routes.commands.revoke_device]


def test_a_rearm_with_a_good_proof_resets_the_count_and_clears_the_sentinel(monkeypatch):
    req = _Req(body={'step_up': '482913'}, principal=_principal(origin='paired'),
               run_ret={'rearmed': True}, proven=True)
    cleared = []
    monkeypatch.setattr(local.LocalNode, 'clear_estop', staticmethod(lambda: cleared.append(1)))
    status, out = routes.rearm(req)
    assert cleared == [1]
    assert req.api.step_up.reset.calls == [(('dvc_u',), {})]
    assert out == {'rearmed': True}                             # no `armed` on a real one


# ── boundary values on the cursors and the query limits ──

@pytest.mark.parametrize('raw', [None, '', '-1', '+1', '1_000', '0x10', ' 1', '1' * 19],
                         ids=['none', 'empty', 'minus', 'plus', 'underscore', 'hex',
                              'space', 'nineteen'])
def test_a_cursor_is_one_to_eighteen_plain_digits(raw):
    bad = pytest.raises(Invalid, routes._cursor, raw, 'cursor')
    assert (bad.value.field, bad.value.why) == ('cursor', 'is an integer >= 0')
    assert routes._cursor('0', 'cursor') == 0
    assert routes._cursor('1' * 18, 'cursor') == int('1' * 18)   # the 18th digit is fine


def test_the_last_query_value_wins_and_the_event_default_stays_500(monkeypatch):
    seen = []
    monkeypatch.setattr(routes.queries, 'events',
                        lambda conn, after, limit, homes: seen.append((after, limit)) or [])
    req = _Req(query={'after': ['1', '9'], 'limit': ['7']})
    req.api.db = _Db()
    status, out = routes.events(req)
    assert seen == [(9, 7)] and out == {'events': []} and req.api.db.reads == 1
    req = _Req()
    req.api.db = _Db()
    routes.events(req)
    assert seen[-1] == (0, 500)                                  # after '0', limit 500


@pytest.mark.parametrize('bad', ['0', str(metrics.MAX_DAYS + 1)], ids=['zero', 'over'])
def test_the_metrics_window_is_bounded(bad, monkeypatch):
    req = _Req(query={'days': [bad]})
    req.api.db = _Db()
    e = pytest.raises(Invalid, routes.metrics_days, req)
    assert (e.value.field, e.value.why) == ('days', 'is 1..%d' % metrics.MAX_DAYS)
    assert req.api.db.reads == 0                                 # refused before the read
    called = []
    monkeypatch.setattr(metrics, 'daily',
                        lambda conn, days: called.append(days) or {'days': []})
    req = _Req()
    req.api.db = _Db()
    routes.metrics_days(req)
    assert called == [14]                                        # the default


def test_the_timeline_limit_is_bounded_and_its_before_is_a_cursor(monkeypatch):
    bad = _Req(params={'id': 'msn_1'}, query={'limit': [str(attention.MAX_TIMELINE + 1)]})
    bad.api.db = _Db()
    e = pytest.raises(Invalid, routes.mission_timeline, bad)
    assert (e.value.field, e.value.why) == ('limit', 'is 1..%d' % attention.MAX_TIMELINE)
    assert bad.api.db.reads == 0
    bad = _Req(params={'id': 'msn_1'}, query={'before': ['x']})
    bad.api.db = _Db()
    e = pytest.raises(Invalid, routes.mission_timeline, bad)
    assert e.value.field == 'before'
    monkeypatch.setattr(routes.resources, 'homes', lambda *a, **k: ())
    called = []
    monkeypatch.setattr(attention, 'timeline',
                        lambda conn, mid, before, limit, homes=None:
                        called.append((before, limit)) or {'events': []})
    req = _Req(params={'id': 'msn_1'})
    req.api.db = _Db()
    routes.mission_timeline(req)
    assert called == [(None, 50)]                                # the defaults


@pytest.mark.parametrize('q', [None, '', '   ', 'a' * 201],
                         ids=['absent', 'empty', 'blank', 'too-long'])
def test_the_title_search_needs_one_to_two_hundred_characters(q, monkeypatch):
    req = _Req(query={} if q is None else {'q': [q]})
    req.api.db = _Db()
    bad = pytest.raises(Invalid, routes.search_titles, req)
    assert (bad.value.field, bad.value.why) == ('q', 'is 1..200 characters')
    assert req.api.db.reads == 0                                 # refused before the read
    needle = ' ' + 'b' * 198 + ' '
    seen = []
    monkeypatch.setattr(routes.queries, 'search',
                        lambda conn, n: seen.append(n) or {'hits': []})
    req = _Req(query={'q': [needle]})
    req.api.db = _Db()
    routes.search_titles(req)
    assert seen == [needle.strip()] and len(seen[0]) == 198


def test_a_context_preview_budget_below_one_is_refused_before_any_read():
    req = _Req(body={'subject': {'kind': 'mission', 'id': 'msn_1'}, 'limit_tokens': 0})
    req.api.db = _Db()
    bad = pytest.raises(Invalid, routes.preview_context, req)
    assert (bad.value.field, bad.value.why) == ('limit_tokens', 'is an integer >= 1')
    assert req.api.db.reads == 0


def test_the_automation_simulation_window_is_bounded(monkeypatch):
    req = _Req(params={'id': 'aut_1'}, query={'days': ['181']})
    req.api.db = _Db()
    bad = pytest.raises(Invalid, routes.simulate_automation, req)
    assert (bad.value.field, bad.value.why) == ('days', 'is 1..180')
    assert req.api.db.reads == 0
    monkeypatch.setattr(routes.resources, 'homes', lambda *a, **k: ())
    called = []
    monkeypatch.setattr(routes.automations, 'simulate',
                        lambda conn, aid, now=None, days=None, homes=None:
                        called.append(days) or {})
    good = _Req(params={'id': 'aut_1'})
    good.api.db = _Db()
    routes.simulate_automation(good)
    assert called == [30]


def test_clarify_demands_exactly_one_of_a_choice_and_an_answer():
    both = _Req(params={'id': 'int_1'}, body={'choice': 'proceed', 'text': 'yes'})
    bad = pytest.raises(Invalid, routes.clarify_intent, both)
    assert (bad.value.field, bad.value.why) == ('choice', 'give exactly one of choice and text')
    neither = _Req(params={'id': 'int_1'}, body={})
    assert pytest.raises(Invalid, routes.clarify_intent, neither)
    req = _Req(params={'id': 'int_1'}, body={'choice': 'drop'})
    routes.clarify_intent(req)
    (run,) = req.runs
    assert run.fn is req.api.conversations.choose
    assert run.kwargs == {'intent_id': 'int_1', 'choice': 'drop'}


# ── repository_graph: a focus is a plain relative path inside the repository ──

@pytest.mark.parametrize('focus', ['..', 'a/../b', 'a\\b', './a', 'a/./b', 'x' * 1025],
                         ids=['dotdot', 'walkup', 'backslash', 'here', 'innerdot', 'huge'])
def test_a_repository_graph_focus_cannot_walk_or_hide(focus):
    req = _Req(params={'id': 'rep_1'}, query={'focus': [focus]})
    req.api.db = _Db()
    bad = pytest.raises(Invalid, routes.repository_graph, req)
    assert (bad.value.field, bad.value.why) == ('focus', 'is a path inside the repository')
    assert req.api.db.reads == 0


def test_a_clean_repository_graph_focus_reaches_the_query(monkeypatch):
    called = []
    monkeypatch.setattr(routes.graph, 'repository_graph',
                        lambda conn, rid, get, focus, depth, limit:
                        called.append((conn, rid, focus, depth, limit)) or {'nodes': []})
    req = _Req(params={'id': 'rep_1'}, query={'focus': ['src/main.py']})
    req.api.db = _Db()
    status, out = routes.repository_graph(req)
    assert status == 200 and out == {'nodes': []}
    assert called == [('conn', 'rep_1', 'src/main.py', 1, routes.graph.LIMIT_DEFAULT)]


# ── the stream's reconnect cursor: the header wins, and narrowing only removes ──

def test_the_stream_takes_its_cursor_from_the_reconnect_header_first():
    req = _Req(headers={'Last-Event-ID': '42'}, query={'after': ['7']})
    routes.events_stream(req)
    (_req, cursor, _keep) = req.api.sse.serve.calls[0][0]
    assert cursor == 42                                           # the header beats ?after=
    req = _Req(query={'after': ['7']})
    routes.events_stream(req)
    assert req.api.sse.serve.calls[0][0][1] == 7
    req = _Req()
    routes.events_stream(req)
    assert req.api.sse.serve.calls[0][0][1] is None               # a fresh stream
    req = _Req(headers={'Last-Event-ID': 'not-a-number'})
    bad = pytest.raises(Invalid, routes.events_stream, req)
    assert bad.value.field == 'cursor'


def test_the_stream_narrowing_can_only_narrow():
    req = _Req(query={'project': ['prj_1'], 'type': ['mission.']})
    routes.events_stream(req)
    keep = req.api.sse.serve.calls[0][0][2]
    assert keep(SimpleNamespace(project='prj_1', type='mission.created'))
    assert keep(SimpleNamespace(project=None, type='mission.created'))   # no project kept
    assert not keep(SimpleNamespace(project='prj_2', type='mission.created'))
    assert not keep(SimpleNamespace(project='prj_1', type='execution.output'))

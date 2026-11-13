"""T-1155: the highest-risk uncovered branches of archeus/api/routes.py 741-904.

Card: T-1155 (owner 2026-11-10). Source slice: `archeus/api/routes.py` lines
741-904 inclusive at tip 56d53504 -- `_device`, the P12 session/checkpoint
handlers, P7's conversation/intent handlers and P9's policy-rule mutations. No
source file is edited by this card, and nothing is faked outside the seams the
existing tests already use: the handler-facing request object is a plain bag of
attributes (as in tests/v1/unit/test_pins_api_routes.py), `db.read()` is a fake
snapshot opener that hands out a NEW connection token per read, and every
application function a handler reaches is patched on the module attribute the
handler reads (`routes.sessions`, `routes.executions`, `routes.resources`,
`routes.conversation`). No worker starts, no clock advances, no sentinel is
touched, no adapter, transport, socket, process, thread or OS call is made, and
no file is written at all. Platform-neutral by construction (Linux here,
reviewed on Windows): no case-insensitive comparison, no path separator, no OS
error text, no POSIX absolute path, no thread inventory, no environment value,
no sleep.

The ten selected branches (fail-closed and denial first, then boundaries, then
error paths), each cited in the test that covers it:

 1. routes.py:837-838  post_message: a decision needs the `approve` scope, and
    the gate sits BEFORE `_with_step_up` (839), so a refused client burns no PIN
    strike, posts no turn and decides nothing.
 2. routes.py:839-844  post_message: the card's echoed `action_hash` AND its
    `expected_version` and the client's proof reach `decide_by_message`, so a
    card that changed after it was displayed cannot be decided.
 3. routes.py:844-848  post_message: a granted decision answers 200 with the
    turn only; the internal `decided` block is popped, never returned.
 4. routes.py:764-773  create_session: `launch` picks the launcher, a launch can
    never carry a `provider_session_ref`, a register always keeps its own, the
    body's nulled-out fields are omitted; the family is POST-only.
 5. routes.py:783-790  handoff_session: the actor is the credential's PRINCIPAL
    (`_device`, 741-743), never its device, and a blank reason becomes ''.
 6. routes.py:775-781  resume_session: the actor is the PRINCIPAL and only a
    real true delivers the brief (`bool(b.get('deliver_brief'))`).
 7. routes.py:796-799  close_session: an absent or blank reason is OMITTED, so
    the command's own `'closed by the user'` is what the audit records.
 8. routes.py:791-793  link_session: `mission_id` is always sent, so an empty
    body unbinds instead of quietly keeping the mission already bound.
 9. routes.py:887-892  create_rule: an omitted or blank `outside` defaults to
    ASK (never ALLOW) and no key outside the nine, nor `idempotency_key`,
    reaches the command.
10. routes.py:758-761  session_brief (and 803-806 list_checkpoints): the homes
    are read LAZILY and on the very snapshot connection the read returned.

Considered and not selected (evidence in the card's report): `list_sessions`'s
three `_one` filters (746-750), `list_messages`'s `after` (813-817),
`retire_rule`/`handoff_execution`'s path-versus-body ids (895-896, 807-808),
`set_profile` (899-902) and the thin reads `get_session`/`get_intent`/
`list_ideas`/`get_policies`. The card's probes 2, 3, 8 and 9 (a decision plus a
confirmation, a denied decision's 423, a clarification's both/neither fields)
were found ALREADY covered -- tests/v1/unit/test_gaps_api_routes.py:363, 390 and
630, tests/v1/unit/test_pins_api_routes.py:663, 674, 690 and 707,
tests/v1/integration/test_chat_approve.py:96 -- and were replaced by the
uncovered branches of the same handlers listed above.
"""

from types import SimpleNamespace

import pytest

from archeus.api import auth, routes
from archeus.api.routes import Refused
from archeus.core.domain.values import Ref

PRIN = 'prn_owner'                                # the credential's principal
DEV = 'dvc_phone'                                 # ... and its device: another id
LOCAL_HOST = '127.0.0.1:7337'
PEER = ('127.0.0.1', 54321)
CARD = {'approval_id': 'apr_1', 'action_hash': 'h' * 64, 'expected_version': 4}


# ── the seams: one request, an Api of recording collaborators, one call order ──

class Seam:
    """One fake collaborator: every call is kept, and named in the order log."""

    def __init__(self, order, name, ret=None):
        self.order, self.name, self.calls = order, name, []
        self.ret = {} if ret is None else ret

    def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        self.order.append(self.name)
        return self.ret

    def returns(self, **ret):
        """What this collaborator answers (a fresh dict per call)."""
        self.ret = ret
        return self

    def submit(self, **kwargs):
        """The answer of a call `req.run` submitted (already logged by the run). The
        handler may edit it -- `post_message` pops its `decided` -- so it is copied.
        """
        return dict(self.ret) if isinstance(self.ret, dict) else self.ret

    @property
    def called(self):
        return bool(self.calls)

    @property
    def last(self):
        assert self.calls, 'the collaborator was never called'
        return self.calls[-1]


class Run:
    """What `req.run` records: one writer submit of one application command."""

    def __init__(self, fn, kwargs, actor_id, keyed):
        self.fn, self.kwargs, self.actor_id, self.keyed = fn, kwargs, actor_id, keyed


class Runs:
    """`req.run` as api/server.py:325 is: one submit of one command, replayable.
    A fake service answers with what it was told to answer, exactly as the writer
    thread would have handed its result back."""

    def __init__(self, order):
        self.order, self.calls = order, []

    def __call__(self, fn, kwargs, *, actor_id=None, keyed=True):
        self.calls.append(Run(fn, dict(kwargs), actor_id, keyed))
        self.order.append(getattr(fn, '__name__', 'run'))
        return fn.submit(**kwargs) if isinstance(fn, Seam) else {'ok': True}

    @property
    def targets(self):
        return [c.fn for c in self.calls]

    @property
    def last(self):
        assert self.calls, 'the handler ran no command at all'
        return self.calls[-1]


class Db:
    """A snapshot reader handing out a NEW connection token per read, so a
    handler that read outside its own snapshot shows up in `conns`."""

    def __init__(self, order):
        self.order, self.reads, self.conns = order, 0, []

    def read(self):
        outer = self

        class _Snapshot:
            def __enter__(self):
                outer.reads += 1
                conn = ('snapshot', outer.reads)
                outer.conns.append(conn)
                outer.order.append('read')
                return conn

            def __exit__(self, *exc):
                return False

        return _Snapshot()


def _api(order):
    """The `Api` a handler reads: a DB, the harnesses' homes and one fake per
    application service a handler in this slice may reach."""
    return SimpleNamespace(
        db=Db(order),
        resources=SimpleNamespace(registry=None, callers=()),
        sessions=SimpleNamespace(
            launch=Seam(order, 'svc.launch', {'id': 'ses_new'}),
            register=Seam(order, 'svc.register', {'id': 'ses_new'}),
            resume=Seam(order, 'svc.resume', {'id': 'ses_1'}),
            handoff=Seam(order, 'svc.handoff', {'id': 'ses_2'})),
        authorization=SimpleNamespace(
            create_rule=Seam(order, 'svc.create_rule', {'id': 'rul_1'}),
            retire_rule=Seam(order, 'svc.retire_rule', {'id': 'rul_1'}),
            set_profile=Seam(order, 'svc.set_profile', {'scope': 'user'}),
            decide_by_message=Seam(order, 'svc.decide_by_message',
                                   {'message_id': 'msg_1', 'conversation_id': 'cnv_9',
                                    'decided': {'approval_id': 'apr_1', 'changed': True}})),
        conversations=SimpleNamespace(
            choose=Seam(order, 'svc.choose', {'chosen': True}),
            confirm_by_message=Seam(order, 'svc.confirm_by_message', {'ok': True})),
        step_up=SimpleNamespace(
            begin=Seam(order, 'step_up.begin', True), end=Seam(order, 'step_up.end'),
            failed=Seam(order, 'step_up.failed', False), reset=Seam(order, 'step_up.reset')),
        sse=SimpleNamespace(close_device=Seam(order, 'sse.close_device')))


def Req(scopes=None, origin='local', body=None, params=None,
        principal_id=PRIN, device_id=DEV):
    """What a handler sees (the request object of api/server.py), with the fake Api."""
    order = []
    runs = Runs(order)
    return SimpleNamespace(
        body={} if body is None else body, params={} if params is None else params,
        query={}, headers={'Host': LOCAL_HOST}, peer=PEER, replayed=False, proven=False,
        principal={'principal_id': principal_id, 'device_id': device_id, 'origin': origin,
                   'scopes': list(auth.SCOPES) if scopes is None else list(scopes)},
        api=_api(order), run=runs, runs=runs, order=order)


def _refused(call, *args, **kw):
    with pytest.raises(Refused) as e:
        call(*args, **kw)
    return e.value


def _decision_body(**over):
    return dict({'text': 'approve', 'decision': dict(CARD), 'idempotency_key': 'k-1'}, **over)


# ══ 1. a message decision needs `approve`, BEFORE any proof is weighed (837-838) ══

def test_a_message_decision_without_approve_is_refused_before_any_proof_is_counted():
    """routes.py:837-838. Move the gate below `_with_step_up` (839) and a client
    that may not decide still spends its PIN: five such requests revoke the device
    and close its streams. Remove the gate and this very request decides a card."""
    req = Req(scopes=['observe', 'control'], origin='paired',
              body=_decision_body(step_up='482913'))
    got = _refused(routes.post_message, req)
    assert (got.status, got.code, got.detail) == (403, 'scope_required', {'scope': 'approve'})
    assert req.runs.calls == [], 'a turn was posted by a client that may not decide'
    assert req.api.step_up.begin.calls == [], 'a refused client spent a PIN strike'
    assert req.api.step_up.failed.calls == []
    assert req.api.sse.close_device.calls == [], 'a refused client was locked out'
    assert req.api.authorization.decide_by_message.called is False


def test_the_same_card_reaches_the_approver_when_the_scope_is_there():
    """The gate's other arm (routes.py:837). Widen the test to `control`, or move
    the gate above the plain-turn branch (833), and one half of this pair answers
    403: either anyone may decide, or a `control` client can no longer speak."""
    ok = Req(params={'id': 'cnv_9'}, scopes=['approve'], origin='paired',
             body=_decision_body(step_up='482913'))
    status, _out = routes.post_message(ok)
    assert status == 200
    assert ok.runs.targets == [ok.api.authorization.decide_by_message]
    plain = Req(params={'id': 'cnv_9'}, scopes=['observe', 'control'],
                body={'text': 'hello', 'in_reply_to': None, 'idempotency_key': 'k-2'})
    status, _ = routes.post_message(plain)
    assert status == 200, 'a control client may still post an ordinary turn'
    assert plain.runs.targets == [routes.conversation.post_message]


# ══ 2. the card's hash AND its version travel into the one transaction (839-844) ══

def test_a_message_decision_carries_the_cards_hash_its_version_and_the_proof():
    """routes.py:840-843. Drop `'expected_version': d.get(...)` -- the natural
    tidy-up, since nothing in this file reads it -- and a card the user has been
    looking at since before the approval moved still decides it: the whole point
    of echoing the version (X02) is gone, and no existing test sees it because
    tests/v1/integration/test_chat_approve.py:47 always echoes the CURRENT
    version. Swap `approval_id` for `action_hash` and the guard is checked against
    the wrong row."""
    req = Req(params={'id': 'cnv_9'}, scopes=list(auth.SCOPES), origin='paired',
              body=_decision_body(step_up='482913'))
    req.api.authorization.decide_by_message.returns(
        message_id='msg_1', conversation_id='cnv_9',
        decided={'approval_id': 'apr_1', 'changed': True})
    status, _out = routes.post_message(req)
    assert status == 200
    (call,) = req.runs.calls
    assert call.fn is req.api.authorization.decide_by_message
    assert call.keyed is True, 'a decision is a command: it carries its idempotency key'
    assert call.kwargs == {'text': 'approve', 'conversation_id': 'cnv_9',
                           'approval_id': 'apr_1', 'action_hash': 'h' * 64,
                           'expected_version': 4, 'step_up': '482913'}
    assert req.api.step_up.begin.calls == [(('dvc_phone',), {})], 'the proof was counted'
    assert req.api.step_up.end.calls == [(('dvc_phone',), {})]


def test_a_card_without_a_version_says_so_rather_than_claiming_version_zero():
    """routes.py:843 (`d.get('expected_version')`). Default it to 0 or '' and a
    card whose version the client never read is decided as if it had been checked
    against version 0 -- `decide` (core/application/authorization.py:676) only
    compares when the value is not None."""
    body = _decision_body(step_up=None)
    body['decision'] = {'approval_id': 'apr_1', 'action_hash': 'h' * 64}
    req = Req(params={'id': 'cnv_9'}, scopes=list(auth.SCOPES), body=body)
    routes.post_message(req)
    assert req.runs.last.kwargs['expected_version'] is None
    assert req.runs.last.kwargs['step_up'] is None
    assert req.api.step_up.begin.calls == [], 'no proof: nothing is counted'


# ══ 3. a granted decision answers with the turn, never the decided block (844-848) ══

def test_an_approved_message_never_answers_with_the_internal_decided_block():
    """routes.py:844 (`decided = out.pop('decided')`). Read it as `out.get(...)`
    and the answer grows Core's private decision row -- the policy decision id,
    the guard's reason -- into a client-facing body, while the 423 branch keeps
    working and every existing test still passes."""
    req = Req(params={'id': 'cnv_9'}, scopes=list(auth.SCOPES), body=_decision_body())
    req.api.authorization.decide_by_message.returns(
        message_id='msg_1', conversation_id='cnv_9',
        decided={'approval_id': 'apr_1', 'changed': True,
                 'policy_decision_id': 'pol_7', 'guard': {'reason': 'locked on prod'}})
    status, out = routes.post_message(req)
    assert status == 200
    assert 'decided' not in out, out
    assert 'policy_decision_id' not in str(out) and 'locked on prod' not in str(out)
    assert out == {'message_id': 'msg_1', 'conversation_id': 'cnv_9'}
    assert req.runs.targets == [req.api.authorization.decide_by_message]


# ══ 4. create_session: launch or register, never both, never a forged ref (764-773) ══

BASE_SESSION = {'harness_id': 'claude', 'cwd': 'project/app', 'idempotency_key': 'k-9'}


def test_a_launch_never_carries_a_provider_session_the_client_named():
    """routes.py:770-772. `launch` opens a NEW terminal; a body that also names a
    `provider_session_ref` would have Archeus attach a terminal to a transcript
    somebody else chose. Delete the `b.pop('provider_session_ref', None)` and
    this fails -- and nothing else catches it: no test has ever posted a launch
    with a ref (tests/v1/judge/http.py:431 `launch_session` has no caller and
    sends none), and tests/v1/integration/test_sessions_http.py:29 only registers."""
    req = Req(body=dict(BASE_SESSION, launch=True, provider_session_ref='ref-someone-elses',
                        model='fake-large'))
    status, out = routes.create_session(req)
    assert status == 200 and out == {'id': 'ses_new'}
    svc = req.api.sessions
    assert svc.launch.calls and not svc.register.called, "a launch registered, or both ran"
    (args, kwargs) = svc.launch.last
    assert args == (Ref('user_device', PRIN),)
    assert 'provider_session_ref' not in kwargs, kwargs
    assert kwargs == {'key': 'k-9', 'harness_id': 'claude', 'cwd': 'project/app',
                      'model': 'fake-large'}


def test_a_register_keeps_the_provider_session_it_was_given_and_opens_nothing():
    """routes.py:772. Pop the ref on BOTH arms and a registered session arrives
    anonymous: Core can never locate the transcript the user pointed at, and every
    later resume of it is a 409 (tests/v1/integration/test_sessions_http.py:75)."""
    req = Req(body=dict(BASE_SESSION, provider_session_ref='ref-mine', launch=False))
    status, _out = routes.create_session(req)
    assert status == 200
    svc = req.api.sessions
    assert svc.register.calls and not svc.launch.called
    (args, kwargs) = svc.register.last
    assert args == (Ref('user_device', PRIN),)
    assert kwargs == {'key': 'k-9', 'harness_id': 'claude', 'cwd': 'project/app',
                      'provider_session_ref': 'ref-mine'}


@pytest.mark.parametrize('launch', [None, False, 0], ids=['null', 'false', 'zero'])
def test_a_session_that_does_not_ask_for_a_terminal_is_only_registered(launch):
    """routes.py:766 (`b.pop('launch', None)`) and 769 (`if launch:`). Keep the
    key and `launch: 0` opens a terminal; forget the pop of `idempotency_key` and
    it is both the key and a body field, and the service takes `key=` alone
    (core/sessions/service.py:129-131), so the stray one rides into the command
    beside it."""
    req = Req(body=dict(BASE_SESSION, launch=launch))
    routes.create_session(req)
    svc = req.api.sessions
    assert not svc.launch.called, 'a body that did not ask for a terminal opened one'
    assert svc.register.calls
    assert 'launch' not in svc.register.last[1], svc.register.last[1]
    assert svc.register.last[1]['key'] == 'k-9'


def test_a_session_body_sends_no_field_it_nulled_out():
    """routes.py:767 (`b = {k: v for k, v in b.items() if v is not None}`). The
    route's filter is the only thing that makes an absent field and a nulled one
    the same request: drop it and `account_id=None, model=None, ...` ride onto the
    command as keywords, where the service's own defaults (`service.py:129-140`)
    no longer apply."""
    req = Req(body=dict(BASE_SESSION, account_id=None, project_id=None, mission_id=None,
                        model=None, effort=None, provider_session_ref=None))
    status, out = routes.create_session(req)
    assert status == 200 and out == {'id': 'ses_new'}
    (_args, kwargs) = req.api.sessions.register.last
    assert kwargs == {'key': 'k-9', 'harness_id': 'claude', 'cwd': 'project/app'}
    for nulled in ('account_id', 'project_id', 'mission_id', 'model', 'effort',
                   'provider_session_ref'):
        assert nulled not in kwargs, nulled


def test_the_session_command_family_answers_only_to_post_on_its_own_path():
    """The route metadata this slice's handlers depend on (table at
    routes.py:1216-1228): a command verb is POST only (a GET is 405, never a
    silent 404 that a client retries forever), every one of them needs `control`
    and every one carries a REQUIRED idempotency key -- a resume without a key
    would launch a second terminal on a retry, and these handlers read
    `b['idempotency_key']` unguarded."""
    for path in ('/v1/sessions/ses_1/resume', '/v1/sessions/ses_1/handoff',
                 '/v1/sessions/ses_1/link', '/v1/sessions/ses_1/close'):
        with pytest.raises(Refused) as e:
            routes.match('GET', path)
        assert (e.value.status, e.value.code) == (405, 'method_not_allowed'), path
        with pytest.raises(Refused) as e:
            routes.match('DELETE', path)
        assert e.value.status == 405, path
    family = {
        '/v1/sessions': (routes.create_session, 'control', 'required'),
        '/v1/sessions/ses_1/resume': (routes.resume_session, 'control', 'required'),
        '/v1/sessions/ses_1/handoff': (routes.handoff_session, 'control', 'required'),
        '/v1/sessions/ses_1/link': (routes.link_session, 'control', 'required'),
        '/v1/sessions/ses_1/close': (routes.close_session, 'control', 'required'),
    }
    for path, expected in family.items():
        route, _params = routes.match('POST', path)
        assert (route.handler, route.scope, route.idempotent) == expected, path
    _route, params = routes.match('POST', '/v1/sessions/ses_1/close')
    assert params == {'id': 'ses_1'}


# ══ 5. a handoff is the person's, not the device's (783-790, 741-743) ══

def test_a_handoff_is_recorded_as_the_person_and_a_blank_reason_is_an_empty_one():
    """routes.py:741-743 (`_device`) and 788 (`reason=b.get('reason') or ''`).
    Read `_device` as the `device_id` and every session write is attributed to a
    device instead of the principal that asked -- `_user`
    (core/application/sessions.py:32) checks the KIND alone, so nothing downstream
    notices and the audit of who moved the session is simply wrong. Drop the
    `or ''` and a reason the client left out is stored as None."""
    req = Req(params={'id': 'ses_1'},
              body={'request_id': 'h-1', 'harness_id': 'fake_b', 'account_id': 'acc_2',
                    'idempotency_key': 'k-3'})
    status, out = routes.handoff_session(req)
    assert status == 200 and out == {'id': 'ses_2'}
    (args, kwargs) = req.api.sessions.handoff.last
    assert args[0].kind == 'user_device' and args[0].id == PRIN, 'not the principal'
    assert args == (Ref('user_device', PRIN),)
    assert kwargs == {'source_session_id': 'ses_1', 'request_id': 'h-1',
                      'harness_id': 'fake_b', 'account_id': 'acc_2', 'model': None,
                      'effort': None, 'reason': '', 'key': 'k-3'}


def test_a_reason_the_client_gave_is_carried_word_for_word():
    """routes.py:788's truthy arm. Coerce it (`strip()`, or `or ''` widened over
    the whole body) and the one human-written note on a handoff is lost -- and a
    reason of '0' or ' ' is exactly the boundary `or` gets wrong for anyone who
    rewrites it as `b['reason'] if 'reason' in b else ''`."""
    req = Req(params={'id': 'ses_1'},
              body={'request_id': 'h-2', 'harness_id': 'fake_b', 'reason': '  battery  ',
                    'idempotency_key': 'k-4'})
    routes.handoff_session(req)
    (_args, kwargs) = req.api.sessions.handoff.last
    assert kwargs['reason'] == '  battery  '
    assert kwargs['account_id'] is None and kwargs['key'] == 'k-4'


# ══ 6. a resume is the principal's own, and only a real true delivers the brief ══

@pytest.mark.parametrize('deliver,expected', [('missing', False), (None, False), (True, True)],
                         ids=['missing', 'null', 'true'])
def test_a_resume_delivers_the_brief_only_for_a_real_true(deliver, expected):
    """routes.py:780 (`deliver_brief=bool(b.get('deliver_brief'))`). Pass the raw
    body value through and `deliver_brief: None` reaches the service, where
    `out['artifact_sha'] if deliver_brief else None` (core/sessions/service.py:162)
    is the same test on a None -- the same answer today, and the brief is not
    attached to the launch. The actor half (778, `_device`) is what no session
    test asserts at all: tests/v1/integration/test_presence.py:676 pins the actor
    of a mission pause, never of a resume."""
    body = {'request_id': 'r-1', 'idempotency_key': 'k-5'}
    if deliver != 'missing':
        body['deliver_brief'] = deliver
    req = Req(params={'id': 'ses_1'}, body=body)
    status, _out = routes.resume_session(req)
    assert status == 200
    (args, kwargs) = req.api.sessions.resume.last
    assert args == (Ref('user_device', PRIN),), "the resume is not the principal's"
    assert kwargs == {'session_id': 'ses_1', 'request_id': 'r-1', 'model': None,
                      'effort': None, 'deliver_brief': expected, 'key': 'k-5'}
    assert isinstance(kwargs['deliver_brief'], bool)


def test_a_resume_names_the_model_and_effort_the_user_chose_for_that_session():
    """routes.py:779. Take `model`/`effort` from the harness default instead of
    the body and the choice never reaches the terminal; the CLI's `resume --model`
    (tests/v1/integration/test_sessions_http.py:104) checks the hostile case at
    the service, never that a good choice is carried by the route."""
    req = Req(params={'id': 'ses_1'},
              body={'request_id': 'r-2', 'model': 'fake-large', 'effort': 'high',
                    'deliver_brief': True, 'idempotency_key': 'k-6'})
    routes.resume_session(req)
    (_args, kwargs) = req.api.sessions.resume.last
    assert (kwargs['model'], kwargs['effort'], kwargs['deliver_brief']) == \
        ('fake-large', 'high', True)
    assert kwargs['session_id'] == 'ses_1' and kwargs['request_id'] == 'r-2'


# ══ 7. closing without a reason keeps the command's own reason (796-799) ══

@pytest.mark.parametrize('body', [{}, {'reason': None}, {'reason': ''}],
                         ids=['absent', 'null', 'blank'])
def test_a_close_with_no_reason_sends_no_reason_at_all(body):
    """routes.py:798-799 (`if req.body.get('reason'): kw['reason'] = ...`). Test
    `'reason' in b` instead and a null or blank reason is passed on, and the
    session's `closed_reason` -- the only record of why a session ended -- becomes
    None or '' rather than the command's own `'closed by the user'`
    (core/application/sessions.py:142)."""
    req = Req(params={'id': 'ses_1'}, body=dict(body, idempotency_key='k-7'))
    status, _out = routes.close_session(req)
    assert status == 200
    (call,) = req.runs.calls
    assert call.fn is routes.sessions.close and call.keyed is True
    assert call.kwargs == {'session_id': 'ses_1'}


def test_a_close_with_a_reason_records_what_the_user_said():
    """routes.py:799's truthy arm -- no test has ever sent one
    (tests/v1/integration/test_sessions_http.py:50 and tests/v1/judge/http.py:468
    both post an empty body). Invert the branch and the reason is dropped."""
    req = Req(params={'id': 'ses_1'},
              body={'reason': 'finished it myself', 'idempotency_key': 'k-8'})
    status, _out = routes.close_session(req)
    assert status == 200
    (call,) = req.runs.calls
    assert call.fn is routes.sessions.close and call.keyed is True, \
        'a close is a command: it carries its idempotency key'
    assert call.kwargs == {'session_id': 'ses_1',
                           'reason': 'finished it myself'}


# ══ 8. linking with no mission unbinds instead of keeping the old one (791-793) ══

@pytest.mark.parametrize('mission', [('msn_9',), ()], ids=['bound', 'unbind'])
def test_a_link_always_names_the_mission_key_even_when_it_unbinds(mission):
    """routes.py:793 (`'mission_id': req.body.get('mission_id')`). `link` takes
    `mission_id` as a REQUIRED keyword and clears the binding only when it is
    present and None (core/application/sessions.py:170-179). Filter the key out
    when the body omits it -- the obvious tidy-up, the shape of `close` above --
    and an unlink is a TypeError at best and a session left bound to a mission it
    was released from at worst."""
    body = dict(idempotency_key='k-10')
    if mission:
        body['mission_id'] = mission[0]
    req = Req(params={'id': 'ses_1'}, body=body)
    status, _out = routes.link_session(req)
    assert status == 200
    (call,) = req.runs.calls
    assert call.fn is routes.sessions.link and call.keyed is True
    assert call.kwargs == {'session_id': 'ses_1',
                           'mission_id': mission[0] if mission else None}


# ══ 9. a rule that says nothing about the rest of the world ASKS (887-892) ══

def test_a_rule_that_asks_nothing_about_the_rest_of_the_world_is_an_ask_rule():
    """routes.py:892 (`'outside': b.get('outside') or 'ASK'`). `outside` is what
    happens to an action the rule set does not speak about; make the default
    ALLOW -- one word, schema-legal bodies all unchanged (the enum is ASK/DENY and
    the route supplies the value after validation) -- and every rule written from
    now on stops asking. The nine-key comprehension is the other half: an
    `idempotency_key` on the command's kwargs is a duplicate keyword."""
    req = Req(body={'scope_level': 'USER', 'action_class': 'deploy', 'decision': 'DENY',
                    'idempotency_key': 'k-11'})
    status, out = routes.create_rule(req)
    assert status == 200 and out == {'id': 'rul_1'}
    (call,) = req.runs.calls
    assert call.fn is req.api.authorization.create_rule
    assert call.keyed is True, 'a rule is a command: it carries its idempotency key'
    assert call.kwargs == {'scope_level': 'USER', 'scope_ref': None, 'action_class': 'deploy',
                           'decision': 'DENY', 'locked': None, 'match': None,
                           'boundary': None, 'expires_at': None, 'supersedes_rule_id': None,
                           'outside': 'ASK', 'note': ''}
    assert 'idempotency_key' not in call.kwargs


def test_a_blank_outside_or_note_still_default_to_the_careful_pair():
    """routes.py:892 again: `or`, not `get(k, default)` -- an explicit null or ''
    is the same request as an absent one, and the fail-closed value is what the
    command must be handed. A `get('outside', 'ASK')` passes the omitted case
    above and fails here. A stale `supersedes_rule_id` is passed through untouched
    for the command to refuse (authorization.py:966-970), never swallowed."""
    req = Req(body={'scope_level': 'MISSION', 'action_class': 'install', 'decision': 'ASK',
                    'outside': '', 'note': None, 'supersedes_rule_id': 'rul_old',
                    'expires_at': '2026-12-01T00:00:00+00:00', 'idempotency_key': 'k-12'})
    routes.create_rule(req)
    kwargs = req.runs.last.kwargs
    assert (kwargs['outside'], kwargs['note']) == ('ASK', '')
    assert kwargs['supersedes_rule_id'] == 'rul_old'
    assert kwargs['expires_at'] == '2026-12-01T00:00:00+00:00'


# ══ 10. a brief's homes are read lazily, on its own snapshot (758-761, 803-806) ══

def test_a_session_brief_reads_its_homes_lazily_on_the_snapshot_it_read_from(monkeypatch):
    """routes.py:759-761 (`h = lambda: _read_homes(req, conn)`). Evaluate it
    eagerly and the homes -- the account home paths every redaction is built from
    -- are read for a brief nobody asked for; hoist it out of the `with`, or let it
    open its own `db.read()`, and the homes come from ANOTHER snapshot than the
    session row: a brief that describes one state with somebody else's redactions.
    tests/v1/integration/test_sessions_http.py:43 reads a brief on a real DB,
    where all three shapes answer the same."""
    req = Req(params={'id': 'ses_1'})
    seen, homes_reads = {}, []

    def homes(conn, registry, callers):
        homes_reads.append((conn, registry, callers))
        return 'HOMES'

    def preview_brief(conn, session_id, homes=None):
        seen['conn'] = conn
        seen['read_before_being_asked'] = list(homes_reads)
        seen['order_at_view'] = list(req.order)
        seen['homes'] = homes
        return {'session': {'id': session_id}}

    monkeypatch.setattr(routes.resources, 'homes', homes)
    monkeypatch.setattr(routes.sessions, 'preview_brief', preview_brief)
    status, out = routes.session_brief(req)
    assert status == 200 and out['session']['id'] == 'ses_1'
    assert seen['read_before_being_asked'] == [], 'the homes were read eagerly'
    assert seen['order_at_view'] == ['read'], seen['order_at_view']
    assert seen['homes']() == 'HOMES'
    assert homes_reads == [(seen['conn'], None, ())], 'the homes read another connection'
    assert req.api.db.conns == [seen['conn']], 'a second snapshot was opened'


def test_an_executions_checkpoints_share_the_one_snapshot_with_their_homes(monkeypatch):
    """routes.py:805: the same lazy shape for the checkpoint list -- one read,
    and the homes that redact a checkpoint's paths come from that same snapshot
    (tests/v1/integration/test_sessions_http.py:89 reads checkpoints on a real DB,
    where eager and lazy are indistinguishable)."""
    req = Req(params={'id': 'exe_1'})
    seen, homes_reads = {}, []

    def homes(conn, registry, callers):
        homes_reads.append((conn, registry, callers))
        return 'HOMES'

    def checkpoints(conn, execution_id, homes=None):
        seen['conn'] = conn
        seen['homes'] = homes
        seen['order_at_view'] = list(req.order)
        return [{'id': 'cpt_1', 'execution_id': execution_id}]

    monkeypatch.setattr(routes.resources, 'homes', homes)
    monkeypatch.setattr(routes.executions, 'checkpoints', checkpoints)
    status, out = routes.list_checkpoints(req)
    assert status == 200 and out['checkpoints'][0]['execution_id'] == 'exe_1'
    assert seen['order_at_view'] == ['read'], 'the homes were read before the caller asked'
    assert seen['homes']() == 'HOMES'
    assert homes_reads == [(seen['conn'], None, ())]
    assert req.api.db.conns == [seen['conn']]

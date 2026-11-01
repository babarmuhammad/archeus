"""T-403: the hand-mutant pass on `archeus/api/routes.py` (tests that fail on
wrong code).

Every test here is written so that it FAILS if the condition it names were
inverted, removed or loosened. The twenty conditions considered — each with the
existing test that covers it, or the reason it is uncovered — and the tests this
file adds for the uncovered ones are listed in the card's report
(`/work/QWEN-DONE-T-403.md`).

Nothing is faked outside the seams the existing tests already use: the request
object is a plain object like the `SimpleNamespace` fakes of
`tests/v1/unit/test_execution_units.py`, `db.read()` is a `nullcontext` (the same
seam), `LocalNode`'s sentinel methods are patched as in
`tests/v1/integration/test_estop_drills.py:138`, and every application function a
handler reaches is patched on the module attribute the handler reads. No real OS
call, process, socket or sleep happens and nothing is written outside the
per-test `ARCHEUS_HOME`. Platform-neutral by construction: no case-insensitive
comparison, no path separator, no OS error text, no clock finer than a day.
"""

import contextlib
from types import SimpleNamespace

import pytest

from archeus.api import auth, routes
from archeus.api.routes import Refused
from archeus.api.schemas import Invalid
from archeus.core.application import errors
from archeus.core.domain import ids
from archeus.core.domain.guards import GuardResult
from archeus.node.local import LocalNode

CONN = object()                                     # the read snapshot's connection
REMOTE = ('pc.tailnet.example',)                    # Origin.remote's shape, as a tuple


# ── the request object and its seams ──

class Runs:
    """`req.run` as the server's is: one writer submit, recorded, replayable.
    The first submit may raise (the command that was refused); a later one — the
    revocation `_step_up_failed` runs — is recorded like any other."""

    def __init__(self, out=None, raising=None):
        self.calls = []
        self.out = {'device_id': 'dvc_9'} if out is None else out
        self.raising = raising

    def __call__(self, fn, kwargs, *, actor_id=None, keyed=True):
        call = SimpleNamespace(fn=fn, kwargs=kwargs, actor_id=actor_id, keyed=keyed)
        self.calls.append(call)
        if self.raising is not None and len(self.calls) == 1:
            raise self.raising
        return dict(self.out)

    @property
    def last(self):
        assert self.calls, 'the handler ran no command at all'
        return self.calls[-1]

    @property
    def targets(self):
        return [c.fn for c in self.calls]


def Req(**over):
    """What a handler sees (api/server.py, "the request object handlers see")."""
    req = SimpleNamespace(body={}, params={}, query={}, headers={'Host': '127.0.0.1:7337'},
                          peer='127.0.0.1', replayed=False,
                          principal={'principal_id': 'prn_1', 'device_id': 'dvc_1',
                                     'origin': 'local', 'scopes': list(auth.SCOPES)})
    req.api = api()
    runs = Runs(out=over.pop('out', None), raising=over.pop('raising', None))
    req.runs, req.run = runs, runs
    for name, value in over.items():
        if name == 'api':
            req.api = value if value is not None else api()
        else:
            setattr(req, name, value)
    return req


def api(**over):
    """The `Api` a handler reads: the DB read, the origin, the two code stores and
    one attribute per application service a route may run through `req.run`."""
    base = {'db': SimpleNamespace(read=lambda: contextlib.nullcontext(CONN)),
            'device_active': lambda d: True,
            'origin': SimpleNamespace(local_host=lambda h: h == '127.0.0.1:7337', remote=()),
            'version': 'v1', 'instance': 'core-1', 'started_at': '2026-10-30T09:00:00+00:00',
            'resources': SimpleNamespace(registry=SimpleNamespace(ids=lambda: [],
                                                                   get=lambda h: None),
                                         callers=(), probe=lambda *a: 'PROBE',
                                         usage_measures=lambda *a: ()),
            'step_up': SimpleNamespace(begin=lambda d: True, end=lambda d: None, failed=lambda d: False, reset=lambda d: None),
            'sse': SimpleNamespace(close_device=lambda d: None),
            'launch': SimpleNamespace(mint=lambda *a, **k: 'CODE', redeem=lambda c: None),
            'pairing': SimpleNamespace(mint=lambda g: 'PCODE', redeem=lambda c: None),
            'sessions': SimpleNamespace(launch=None, register=None, resume=None, handoff=None),
            'executions': SimpleNamespace(rearm='executions.rearm',
                                          estop='executions.estop',
                                          stop_execution='executions.stop_execution',
                                          stop_mission='executions.stop_mission'),
            'conversations': SimpleNamespace(choose='conversations.choose',
                                             confirm_by_message='conversations.confirm'),
            'authorization': SimpleNamespace(decide='authorization.decide',
                                             decide_by_message='authorization.decide_by_message'),
            'missions': SimpleNamespace(pause='missions.pause'),
            'decisions': SimpleNamespace(decide='decisions.decide',
                                         review='decisions.review'),
            'work': SimpleNamespace(edit_plan='work.edit_plan')}
    base.update(over)
    return SimpleNamespace(**base)


def paired(**over):
    """A principal from a paired client (the only kind that holds a PIN)."""
    over.setdefault('principal', {'principal_id': 'prn_1', 'device_id': 'dvc_p',
                                 'origin': 'paired', 'scopes': list(auth.SCOPES)})
    return Req(**over)


def grant(**over):
    base = {'starter': 'prn_m', 'device_id': 'dvc_m', 'name': 'Phone', 'host_label': "Babar's phone",
            'scopes': ['observe', 'control']}
    base.update(over)
    return base


def step_up(record, *, fails=False):
    return SimpleNamespace(begin=lambda d: True, end=lambda d: None, failed=lambda d: record.append(('failed', d)) or fails,
                           reset=lambda d: record.append(('reset', d)))


# ── 1. `_one`: a repeated query parameter is answered by its LAST value ──

def test_a_repeated_query_parameter_is_answered_by_its_last_value():
    """routes.py:93 (`None if not values else values[-1]`). First-wins lets a
    client smuggle `?state=ACTIVE&state=PAUSED` and read the row it named first,
    past whatever the last name was meant to say."""
    assert routes._one({'state': ['ACTIVE', 'PAUSED']}, 'state') == 'PAUSED'
    assert routes._one({'state': []}, 'state') is None
    assert routes._one({}, 'state') is None


def test_the_mission_list_asks_for_the_state_the_query_named_last(monkeypatch):
    """The same condition through the handler that reads the query."""
    seen = []
    monkeypatch.setattr(routes.queries, 'list_missions',
                        lambda conn, state, project, homes=None: seen.append((state, project)) or [])
    monkeypatch.setattr(routes.resources, 'homes', lambda *a, **k: {})
    status, out = routes.list_missions(Req(query={'state': ['ACTIVE', 'PAUSED'],
                                                  'project': ['prj_a']}))
    assert status == 200 and out == {'missions': []}
    assert seen == [('PAUSED', 'prj_a')], seen


# ── 2. `_cursor`: 1..18 ASCII digits, nothing else ──

@pytest.mark.parametrize('raw', ['0', '7', '123456789012345678'],
                         ids=['zero', 'seven', 'eighteen-digits'])
def test_a_cursor_of_one_to_eighteen_digits_is_its_integer(raw):
    assert routes._cursor(raw, 'cursor') == int(raw)


@pytest.mark.parametrize('raw', ['', '1234567890123456789', '+1', '-1', '1 ', ' 1', '1_0',
                                 '0x10', '1e3', '1.0', 'x', '\n1'],
                         ids=['empty', 'nineteen', 'plus', 'minus', 'space-after',
                              'space-before', 'underscore', 'hex', 'exponent', 'float',
                              'letter', 'newline'])
def test_anything_else_is_refused_as_a_cursor(raw):
    """routes.py:97 (`re.fullmatch(r'\\d{1,18}', raw)`). `int()` alone, or
    `str.isdigit()`, would take the sign, the space and the underscore; `{1,18}`
    read as `{1,19}` would take nineteen digits, which is a row no page can hold."""
    with pytest.raises(Invalid) as got:
        routes._cursor(raw, 'cursor')
    assert (got.value.field, got.value.why) == ('cursor', 'is an integer >= 0')


def test_a_cursor_written_in_another_scripts_digits_is_refused():
    with pytest.raises(Invalid):
        routes._cursor('\u0661\u0662\u0663', 'cursor')            # ١٢٣


# ── 5. `launch_code`: a minter cannot mint a scope it does not hold ──

def test_a_launch_code_cannot_hold_a_scope_its_minter_does_not_have():
    """routes.py:220-222. Remove the membership check, or bound it by the asked
    list instead of `req.principal['scopes']`, and an `observe`/`control` device
    mints a code holding `admin` — which the redeem then hands out."""
    minted = []
    req = Req(body={'scopes': ['observe', 'admin']},
              principal={'principal_id': 'prn_1', 'device_id': 'dvc_1', 'origin': 'local',
                         'scopes': ['observe', 'control']},
              api=api(launch=SimpleNamespace(mint=lambda *a, **k: minted.append(a) or 'CODE')))
    with pytest.raises(Refused) as got:
        routes.launch_code(req)
    assert (got.value.status, got.value.code, got.value.detail) == (
        403, 'scope_required', {'scope': 'admin'})
    assert minted == [], 'a code was minted beyond the minter scopes'


def test_a_launch_code_mints_what_was_asked_once_and_answers_in_the_canonical_order():
    """routes.py:225-229 (`[s for s in auth.SCOPES if s in asked]`, one mint).
    Answer `asked` instead and the client is told a grant in the order it typed
    it, duplicates and all; two mints would be two live codes for one call."""
    minted = []
    req = Req(body={'scopes': ['control', 'observe', 'control']},
              principal={'principal_id': 'prn_1', 'device_id': 'dvc_1', 'origin': 'local',
                         'scopes': ['observe', 'control']},
              api=api(launch=SimpleNamespace(
                  mint=lambda *a, **k: minted.append(a) or 'CODE')))
    status, out = routes.launch_code(req)
    assert status == 200
    assert out == {'code': 'CODE', 'expires_in': int(auth.LAUNCH_TTL_S),
                   'scopes': ['observe', 'control']}
    assert len(minted) == 1 and list(minted[0][2]) == ['observe', 'control'], minted


# ── 7. `launch_redeem`: an unnamed client is named after its platform ──

@pytest.mark.parametrize('body', [{'platform': 'web'}, {'platform': 'web', 'name': None},
                                  {'platform': 'web', 'name': ''},
                                  {'platform': 'web', 'name': '   '},
                                  {'platform': 'desktop', 'name': '\t\n'}],
                         ids=['absent', 'null', 'empty', 'spaces', 'tab-newline'])
def test_a_launch_redeem_names_an_unnamed_client_after_its_platform(body):
    """routes.py:241 (`(req.body.get('name') or '').strip() or 'browser (%s)'`).
    Without the `.strip()` a name of blanks is stored as the device's name;
    without the `or` chain the device is registered nameless."""
    req = Req(body=dict({'code': 'CODE'}, **body),
              api=api(launch=SimpleNamespace(redeem=lambda c: ('prn_m', 'dvc_m',
                                                               ('observe',), None))))
    status, out = routes.launch_redeem(req)
    assert status == 200 and set(out) == {'device_id', 'token', 'scopes'}
    assert req.runs.last.kwargs['name'] == 'browser (%s)' % body['platform']


def test_a_launch_redeem_keeps_a_real_name_but_trims_it():
    req = Req(body={'code': 'CODE', 'platform': 'web', 'name': '  Laptop  '},
              api=api(launch=SimpleNamespace(redeem=lambda c: ('prn_m', 'dvc_m',
                                                               ('observe',), None))))
    routes.launch_redeem(req)
    assert req.runs.last.kwargs['name'] == 'Laptop'


def test_a_launch_redeem_is_unkeyed_and_its_token_never_enters_the_command():
    """routes.py:238-247 (A4): the answer that carries the secret runs with no
    idempotency key, the actor is the minter, and only the hash goes in."""
    req = Req(body={'code': 'CODE', 'platform': 'web'},
              api=api(launch=SimpleNamespace(redeem=lambda c: ('prn_m', 'dvc_m',
                                                               ('observe', 'control'),
                                                               'shell'))))
    status, out = routes.launch_redeem(req)
    call = req.runs.last
    assert status == 200 and call.keyed is False, 'a secret answer was keyed'
    assert call.fn is routes.commands.register_device
    assert call.actor_id == 'prn_m'
    assert call.kwargs['scopes'] == ['observe', 'control']
    assert call.kwargs['supersede'] == 'shell'
    assert call.kwargs['token_hash'] == auth.token_hash(out['token']) != out['token']
    assert len(call.kwargs['token_hash']) == 64
    assert out['token'] not in [str(v) for v in call.kwargs.values()]


# ── 9. `pair_start`: a grant never carries a blank name or host label ──

@pytest.mark.parametrize('field', ['name', 'host_label'])
@pytest.mark.parametrize('blank', ['', '   ', '\t', '\n'],
                         ids=['empty', 'spaces', 'tab', 'newline'])
def test_a_pairing_grant_carries_no_blank_name_or_host_label(field, blank):
    """routes.py:259-261 (`b.get(f) is not None and not b[f].strip()`). Without
    the `.strip()` a code is minted whose client is born with a blank identity."""
    minted = []
    req = Req(body={field: blank}, api=api(pairing=SimpleNamespace(
        mint=lambda g: minted.append(g) or 'PCODE')))
    with pytest.raises(Invalid) as got:
        routes.pair_start(req)
    assert (got.value.field, got.value.why) == (field, 'is a non-empty string')
    assert minted == [], 'a code was minted with a blank %s' % field


def test_a_pairing_grant_may_carry_no_name_at_all():
    """The same condition's other half: `None` is a choice, not a blank. Written
    `if not b.get(f)` a null name is refused too, and this fails."""
    minted = []
    req = Req(body={'name': None, 'host_label': None}, api=api(pairing=SimpleNamespace(
        mint=lambda g: minted.append(g) or 'PCODE')))
    status, out = routes.pair_start(req)
    assert status == 200 and out['url'] is None                   # no remote host, no url
    assert minted[0]['name'] is None and minted[0]['host_label'] is None
    assert minted[0]['scopes'] == list(auth.PAIR_SCOPES)
    assert out['expires_in'] == int(auth.PAIR_TTL_S)


def test_a_pairing_start_names_the_tunnel_only_when_there_is_one():
    """routes.py:266 (`'https://%s/#pair=%s' % (remote[0], code) if remote else
    None`) — the code is never sent to an http origin."""
    req = Req(body={'name': 'Pixel'}, api=api(
        origin=SimpleNamespace(local_host=lambda h: True, remote=REMOTE),
        pairing=SimpleNamespace(mint=lambda g: 'PCODE')))
    out = routes.pair_start(req)[1]
    assert out['url'] == 'https://%s/#pair=PCODE' % REMOTE[0] and out['url'].startswith('https')


# ── 10. `pair_redeem`: a PIN is 6 to 12 digits, matched whole ──

@pytest.mark.parametrize('pin', ['12345', '1234567890123', '12 3456', 'abc123', '48291a',
                                 '482913x', 'x482913', '482913000000000000', '', '+482913'],
                         ids=['five', 'thirteen', 'inner-space', 'letters', 'last-letter',
                              'suffix', 'prefix', 'twenty', 'empty', 'plus'])
def test_a_pairing_pin_that_is_not_six_to_twelve_digits_whole_is_refused(pin):
    """routes.py:275 (`auth.PIN.fullmatch(b['pin'])`). With `search` instead of
    `fullmatch` the prefix, the suffix and the twenty-digit case all pass, and a
    PIN policy that short is no policy."""
    req = Req(body={'code': 'PCODE', 'platform': 'ios', 'pin': pin},
              api=api(pairing=SimpleNamespace(redeem=lambda c: grant())))
    with pytest.raises(Invalid) as got:
        routes.pair_redeem(req)
    assert (got.value.field, got.value.why) == ('pin', 'is 6 to 12 digits')
    assert req.runs.calls == [], 'a device was registered on a malformed PIN'


@pytest.mark.parametrize('pin', ['482913', '123456789012'], ids=['six', 'twelve'])
def test_a_pairing_pin_of_six_to_twelve_digits_whole_is_taken(pin):
    req = Req(body={'code': 'PCODE', 'platform': 'ios', 'pin': pin},
              api=api(pairing=SimpleNamespace(redeem=lambda c: grant())))
    assert routes.pair_redeem(req)[0] == 200
    assert req.runs.last.kwargs['pin_hash'] is not None and pin not in str(
        req.runs.last.kwargs)


# ── 11. `pair_redeem`: a tripped breaker says when to come back ──

def test_a_locked_pairing_is_429_with_a_retry_after_of_the_breakers_window():
    """routes.py:280-283. Drop the `headers=` (or send the wrong window) and the
    client retries blind and keeps the breaker hammered."""
    def locked(code):
        raise auth.PairingLocked()

    req = Req(body={'code': 'PCODE', 'platform': 'web'},
              api=api(pairing=SimpleNamespace(redeem=locked)))
    with pytest.raises(Refused) as got:
        routes.pair_redeem(req)
    assert (got.value.status, got.value.code) == (429, 'pairing_locked')
    assert got.value.headers == {'Retry-After': str(int(auth.PairingCodes.FAIL_WINDOW_S))}
    assert got.value.headers['Retry-After'] == '60'


def test_an_unknown_pairing_code_is_401_and_spends_nothing():
    """routes.py:284-285 (`if grant is None`). `if not grant` answers 200 for a
    grant that is an empty mapping, and registers a device from it."""
    req = Req(body={'code': 'PCODE', 'platform': 'web'},
              api=api(pairing=SimpleNamespace(redeem=lambda c: None)))
    with pytest.raises(Refused) as got:
        routes.pair_redeem(req)
    assert (got.value.status, got.value.code, got.value.detail) == (
        401, 'invalid_pairing_code', {})
    assert req.runs.calls == []


# ── 12. `pair_redeem`: the answer that holds a secret is never stored ──

def test_a_pairing_redeem_is_unkeyed_and_only_hashes_reach_the_command():
    """routes.py:286-296 (P3.5b A4): `keyed=False`, the starter is the actor, and
    the token and the PIN enter only as their hashes."""
    g = grant(name='Pixel')
    req = Req(body={'code': 'PCODE', 'platform': 'ios', 'pin': None},
              api=api(pairing=SimpleNamespace(redeem=lambda c: g)))
    status, out = routes.pair_redeem(req)
    call = req.runs.last
    assert status == 200 and call.keyed is False, 'the secret-bearing answer was keyed'
    assert call.fn is routes.commands.register_device and call.actor_id == 'prn_m'
    assert call.kwargs['scopes'] == g['scopes'] and call.kwargs['origin'] == 'paired'
    assert call.kwargs['host_label'] == g['host_label']
    assert call.kwargs['pin_hash'] is None and call.kwargs['client_type'] == 'spa'
    assert out['token'].startswith(ids.TOKEN_PREFIXES['device'] + '_')
    assert call.kwargs['token_hash'] == auth.token_hash(out['token']) != out['token']
    assert out['token'] not in [str(v) for v in call.kwargs.values()]
    assert out['expires_at'][:4].isdigit() and int(out['expires_at'][:4]) >= 2026, out['expires_at']


def test_a_pairing_redeem_names_the_client_from_the_grant_first(monkeypatch):
    """routes.py:292 (`grant['name'] or b.get('name') or 'paired %s'`): a
    redeemer cannot rename the client the starter named (D9)."""
    monkeypatch.setattr(routes.commands, 'hash_pin', lambda p: 'pbkdf2$' + auth.token_hash(p))
    req = Req(body={'code': 'PCODE', 'platform': 'ios', 'name': 'Evil', 'pin': '482913'},
              api=api(pairing=SimpleNamespace(redeem=lambda c: grant(name='Pixel'))))
    routes.pair_redeem(req)
    assert req.runs.last.kwargs['name'] == 'Pixel'
    assert req.runs.last.kwargs['pin_hash'].startswith('pbkdf2$')
    assert '482913' not in req.runs.last.kwargs['pin_hash']


def test_a_pairing_redeem_falls_back_to_the_platform_name_and_the_callers_name(monkeypatch):
    """The same `or` chain's two remaining arms."""
    req = Req(body={'code': 'PCODE', 'platform': 'android', 'name': 'Tablet'},
              api=api(pairing=SimpleNamespace(redeem=lambda c: grant(name=None))))
    routes.pair_redeem(req)
    assert req.runs.last.kwargs['name'] == 'Tablet'
    req = Req(body={'code': 'PCODE', 'platform': 'android', 'name': None},
              api=api(pairing=SimpleNamespace(redeem=lambda c: grant(name=None))))
    routes.pair_redeem(req)
    assert req.runs.last.kwargs['name'] == 'paired android'


# ── 13. `list_inspections`: one page is 1..500 rows, 50 by default ──

@pytest.mark.parametrize('raw,want', [(None, 50), ('1', 1), ('500', 500)],
                         ids=['default', 'one', 'five-hundred'])
def test_an_inspection_page_defaults_to_fifty_and_may_ask_for_five_hundred(monkeypatch,
                                                                           raw, want):
    """routes.py:352-353 (`limit = 50 if raw is None else _cursor(...)`): read
    500 for the default, or 50 for the ceiling, and the answer is not what was
    asked — and a page with no bound at all reads a repository whole."""
    seen = []
    monkeypatch.setattr(routes.world_status, 'inspections',
                        lambda conn, rid, limit: seen.append((conn, rid, limit)) or [])
    status, out = routes.list_inspections(Req(params={'id': 'rep_1'},
                                              query={} if raw is None else {'limit': [raw]}))
    assert status == 200 and out == {'inspections': []}
    assert seen == [(CONN, 'rep_1', want)], seen


@pytest.mark.parametrize('raw,why', [('0', 'is 1..500'), ('501', 'is 1..500'),
                                      ('999999', 'is 1..500'), ('-1', 'is an integer >= 0'),
                                      ('x', 'is an integer >= 0'), ('', 'is an integer >= 0')],
                         ids=['zero', 'over', 'huge', 'minus', 'letter', 'empty'])
def test_an_inspection_page_outside_1_to_500_is_refused(monkeypatch, raw, why):
    """routes.py:355-356 (`if not 1 <= limit <= 500`), and the cursor check under
    it. `<=` read as `<` refuses 500 and takes 501; without the range check
    999 999 is a page."""
    def never(conn, rid, limit):
        raise AssertionError('the query ran for a page refused: limit=%r' % (limit,))

    monkeypatch.setattr(routes.world_status, 'inspections', never)
    with pytest.raises(Invalid) as got:
        routes.list_inspections(Req(params={'id': 'rep_1'}, query={'limit': [raw]}))
    assert (got.value.field, got.value.why) == ('limit', why)


# ── 14. `repository_graph`: the focus is a path inside the repository ──

@pytest.mark.parametrize('focus', ['.', './a', 'a/./b', 'a/.', 'a/../b', '../a', 'a\\b',
                                   '.' * 1025, 'a/..', 'C:\\users'],
                         ids=['dot', 'dot-slash', 'inner-dot', 'trailing-dot', 'dotdot',
                              'up-one', 'backslash', 'over-1024', 'tail-dotdot', 'drive'])
def test_a_repository_graph_focus_never_walks_out_of_the_repository(monkeypatch, focus):
    """routes.py:395 (`len(focus) > 1024 or '\\\\' in focus or any(p in ('..',
    '.') for p in focus.split('/'))`). The existing HTTP test refuses `..` and a
    backslash (tests/v1/integration/test_graph_routes.py:49); the single `.`
    component and the 1024 bound are unpinned, and a dropped arm of the `or` is
    an escape or an unbounded argument."""
    asked = []
    monkeypatch.setattr(routes.graph, 'repository_graph',
                        lambda conn, rid, get, f, depth, limit: asked.append(f) or {})
    with pytest.raises(Invalid) as got:
        routes.repository_graph(Req(params={'id': 'rep_1'}, query={'focus': [focus]}))
    assert got.value.field == 'focus'
    assert asked == [], 'a traversal focus reached the graph query'


@pytest.mark.parametrize('focus', ['', 'a', 'a/b/c', 'a.b/c.d', 'x' * 1024],
                         ids=['empty', 'one', 'nested', 'dotted-names', 'at-1024'])
def test_a_repository_graph_focus_is_passed_through_unchanged(monkeypatch, focus):
    """The `or` arms must not refuse what they were not written for: a dot inside
    a name is not `.`; 1024 is allowed where 1025 is not."""
    asked = []
    monkeypatch.setattr(routes.graph, 'repository_graph',
                        lambda conn, rid, get, f, depth, limit: asked.append((f, depth)) or {})
    routes.repository_graph(Req(params={'id': 'rep_1'}, query={'focus': [focus]}))
    assert asked == [(focus, 1)], asked                            # P18: one hop by default


def test_a_repository_graph_asks_the_artifact_store_and_never_the_filesystem(monkeypatch):
    """routes.py:397-399: the only reader handed to the query is `artifacts.get`
    (M21), and the depth/limit of the route are the graph's own."""
    asked = {}

    def repo_graph(conn, rid, get, f, depth, limit):
        asked.update(get=get, depth=depth, limit=limit)
        return {'nodes': []}

    monkeypatch.setattr(routes.graph, 'repository_graph', repo_graph)
    status, _ = routes.repository_graph(Req(params={'id': 'rep_1'}, query={'depth': ['2'],
                                                                           'limit': ['10']}))
    assert status == 200 and asked['get'] is routes.artifacts.get and asked['depth'] == 2


# ── 15. `import_meeting`: undated notes need the flag, really ──

@pytest.mark.parametrize('asked', [None, 'true', 'yes', 1, [], {}, 'True', 'False'],
                         ids=['null', 'true-string', 'yes', 'one', 'list', 'dict',
                              'capitalised', 'false-string'])
def test_only_a_real_true_allows_an_undated_meeting(monkeypatch, asked):
    """routes.py:487-490 (`allow_undated=b.get('allow_undated') is True`). Read
    as plain truthiness, `'true'`, `1` and even `[]` smuggle an undated note into
    knowledge — the one thing ADR-0024's date rule refuses."""
    seen = []

    def read_notes(path, held_at, allow_undated=False):
        seen.append(allow_undated)
        return {'name': 'Standup', 'held_at': held_at, 'sha256': 'a' * 64, 'size': 3,
                'path': path}

    monkeypatch.setattr(routes.ingest, 'read_notes', read_notes)
    routes.import_meeting(Req(body={'path': 'notes/standup.md', 'allow_undated': asked}))
    assert seen == [False], asked


def test_a_real_true_is_passed_on_as_a_true_bool(monkeypatch):
    seen = []

    def read_notes(path, held_at, allow_undated=False):
        seen.append(allow_undated)
        return {'name': 'Standup', 'held_at': None, 'sha256': 'a' * 64, 'size': 3,
                'path': path}

    monkeypatch.setattr(routes.ingest, 'read_notes', read_notes)
    req = Req(body={'path': 'notes/standup.md', 'allow_undated': True, 'project_id': None})
    status, _ = routes.import_meeting(req)
    assert status == 200 and seen == [True]
    assert req.runs.last.fn is routes.knowledge.import_meeting
    assert req.runs.last.kwargs == {'name': 'Standup', 'held_at': None, 'notes_sha256': 'a' * 64,
                                    'notes_size': 3, 'imported_from': 'notes/standup.md',
                                    'project_id': None}


# ── 16. `execution_stream`: an unknown harness gets no adapter, so no trust ──

def _stream_req(monkeypatch, harness, ids_of_registry, from_=None):
    from archeus.core.execution import output as output_module
    seen = []
    e = SimpleNamespace(id='exe_1', harness_id=harness)
    monkeypatch.setattr(routes.executions, 'entity', lambda conn, eid: e)
    monkeypatch.setattr(routes.resources, 'homes', lambda *a, **k: {'homes': {}})
    monkeypatch.setattr(output_module, 'read',
                        lambda ent, adapter, offset: seen.append((ent, adapter, offset)) or 'RAW')
    monkeypatch.setattr(routes, 'public_output', lambda payload, homes: (payload, homes))
    req = Req(params={'id': 'exe_1'}, query=({} if from_ is None else {'from': [from_]}),
              api=api(resources=SimpleNamespace(
                  registry=SimpleNamespace(ids=lambda: list(ids_of_registry),
                                           get=lambda h: 'ADAPTER'), callers=())))
    return req, seen


def test_an_execution_whose_harness_is_unknown_is_read_without_an_adapter(monkeypatch):
    """routes.py:605-612 (`adapter = reg.get(...) if e.harness_id in reg.ids()
    else None`). Ask the registry regardless and an uninstalled harness is either
    a KeyError (a 500 for a plain read) or an adapter object the redactor trusts
    with a stream it cannot actually interpret."""
    req, seen = _stream_req(monkeypatch, 'ghost', ['fake'])
    status, out = routes.execution_stream(req)
    assert status == 200 and out == ('RAW', {'homes': {}})          # still redacted, still public
    assert len(seen) == 1, seen
    assert seen[0][1] is None, 'an adapter was trusted for a harness that is not installed'
    assert seen[0][2] == 0 and seen[0][0].harness_id == 'ghost', seen


def test_an_execution_of_a_known_harness_is_read_from_the_offset_it_asks_for(monkeypatch):
    req, seen = _stream_req(monkeypatch, 'fake', ['fake'], from_='4096')
    routes.execution_stream(req)
    assert seen[0][1] == 'ADAPTER' and seen[0][2] == 4096


def test_a_negative_offset_is_refused_before_anything_is_read(monkeypatch):
    """routes.py:601-602 (`offset = 0 if raw is None else _cursor(raw, 'from')`).
    `int(raw)` alone takes '-1', and a negative seek is a read from the end."""
    req, seen = _stream_req(monkeypatch, 'fake', ['fake'], from_='-1')
    with pytest.raises(Invalid) as got:
        routes.execution_stream(req)
    assert (got.value.field, got.value.why) == ('from', 'is an integer >= 0')
    assert seen == []


# ── 17. `rearm`: only a step-up refusal is a strike; only a proof clears one ──

def _guard(reason):
    return errors.GuardFailed('execution', 'RUNNING', 'STOPPED', 'rearm',
                              GuardResult('step_up', False, reason))


def test_rearming_without_a_proof_counts_no_strike_even_when_a_guard_refused_it():
    """routes.py:700-702 (`if proof is not None and 'step-up' in e.result.reason`).
    Drop the `proof is not None` arm and a paired client's ordinary re-arm — the
    one where it was never asked for a PIN — starts the five-strike revocation
    that belongs to a WRONG PIN, and the client that re-arms blindly is locked
    out by its own guard."""
    calls = []
    req = paired(raising=_guard('no step-up proof given'),
                 body={'step_up': None, 'idempotency_key': 'k'},
                 api=api(step_up=step_up(calls, fails=True)))
    with pytest.raises(errors.GuardFailed):
        routes.rearm(req)
    assert calls == [], 'a strike was counted for a request that gave no proof'


def test_rearming_past_a_guard_that_refused_something_else_counts_no_strike():
    """The `'step-up' in e.result.reason` arm: a refusal of another guard is not
    a wrong PIN, and counting it revokes a good client for nothing."""
    calls = []
    req = paired(raising=_guard('the plan still has 3 tasks'),
                 body={'step_up': '000000', 'idempotency_key': 'k'},
                 api=api(step_up=step_up(calls, fails=True)))
    with pytest.raises(errors.GuardFailed):
        routes.rearm(req)
    assert calls == [], 'an unrelated guard refusal was counted as a wrong PIN'


def test_a_wrong_proof_is_counted_and_the_fifth_revokes_resets_and_closes_the_streams():
    """routes.py:700-702 and 938-945: revoke, then clear the counter, then end
    the revoked client's streams — before the answer."""
    calls = []
    req = paired(raising=_guard('step-up required: wrong PIN'),
                 body={'step_up': '000000', 'idempotency_key': 'k'},
                 api=api(step_up=step_up(calls, fails=True),
                         sse=SimpleNamespace(close_device=lambda d: calls.append(('close', d)))))
    with pytest.raises(errors.GuardFailed):
        routes.rearm(req)
    assert calls == [('failed', 'dvc_p'), ('reset', 'dvc_p'), ('close', 'dvc_p')], calls
    assert req.runs.targets[0] == 'executions.rearm'            # the refused command
    assert req.runs.targets[1:] == [routes.commands.revoke_device]
    assert req.runs.last.kwargs == {'device_id': 'dvc_p', 'reason': 'step_up_failures'}
    assert req.runs.last.keyed is False, 'a replayed answer would revoke twice'


def test_a_right_proof_clears_the_count_and_lifts_the_sentinel(monkeypatch):
    """routes.py:703-709. Read `if proof is not None` as `if True` and a re-arm
    with NO proof — the desktop's — wipes the wrong-PIN counter of a client that
    is four strikes deep: the breaker is worth nothing."""
    calls, cleared = [], []
    monkeypatch.setattr(LocalNode, 'clear_estop', staticmethod(lambda: cleared.append(1)))
    req = Req(body={'step_up': '482913', 'idempotency_key': 'k'}, out={'ok': True},
              api=api(step_up=SimpleNamespace(begin=lambda d: True, end=lambda d: None, failed=lambda d: False,
                                              reset=lambda d: calls.append(('reset', d)))))
    status, out = routes.rearm(req)
    assert status == 200 and out == {'ok': True} and calls == [('reset', 'dvc_1')]
    assert cleared == [1], 'Core was left disarmed after a real re-arm'
    plain = Req(body={'idempotency_key': 'k'}, out={'ok': True},
                api=api(step_up=SimpleNamespace(begin=lambda d: True, end=lambda d: None, failed=lambda d: False,
                                                reset=lambda d: calls.append(('reset', d)))))
    routes.rearm(plain)
    assert calls == [('reset', 'dvc_1')], 'a re-arm with no proof reset the wrong-PIN count'
    assert cleared == [1, 1], 'a re-arm with no proof left the sentinel up'


def test_a_replayed_rearm_answers_what_core_is_and_lifts_nothing(monkeypatch):
    """routes.py:704-705 (T-107): a replay ran nothing, so it neither clears the
    sentinel nor the PIN counter; it reports Core's real state."""
    cleared, reset = [], []
    monkeypatch.setattr(LocalNode, 'clear_estop', staticmethod(lambda: cleared.append(1)))
    monkeypatch.setattr(LocalNode, 'disarmed', staticmethod(lambda: True))
    req = Req(body={'step_up': '482913', 'idempotency_key': 'k'}, out={'ok': True},
              replayed=True,
              api=api(step_up=SimpleNamespace(begin=lambda d: True, end=lambda d: None, failed=lambda d: False,
                                              reset=lambda d: reset.append(('reset', d)))))
    status, out = routes.rearm(req)
    assert status == 200 and out == {'ok': True, 'armed': False}, out
    assert cleared == [] and reset == []


# ── 18. `post_message`: a turn carries a decision OR a confirmation ──

def test_a_message_carrying_both_a_decision_and_a_confirmation_is_refused():
    """routes.py:797-799. Answer both branches and one user turn would decide an
    approval AND confirm a stop card."""
    req = Req(params={'id': 'cnv_1'},
              body={'text': 'x', 'decision': {'approval_id': 'apr_1', 'action_hash': 'a' * 64},
                    'confirm': {'message_id': 'msg_2'}})
    with pytest.raises(ValueError):
        routes.post_message(req)
    assert req.runs.calls == [], 'a command ran for a message that named two things'


def test_a_stop_cards_confirmation_needs_no_approve_scope_and_decides_nothing():
    """routes.py:800-804: the confirm branch is checked FIRST and runs the
    conversation's own command. Move the `approve` scope test above it and a
    `control` client cannot confirm a stop (and this answers 403)."""
    req = Req(params={'id': 'cnv_1'},
              body={'text': 'stop it', 'confirm': {'message_id': 'msg_2'},
                    'idempotency_key': 'k'}, out={'ok': True},
              principal={'principal_id': 'prn_1', 'device_id': 'dvc_1', 'origin': 'paired',
                         'scopes': ['observe', 'control']})
    status, out = routes.post_message(req)
    assert status == 200
    assert req.runs.targets == ['conversations.confirm']
    assert req.runs.last.kwargs == {'text': 'stop it', 'conversation_id': 'cnv_1',
                                    'message_id': 'msg_2'}


def test_a_plain_turn_is_posted_once_and_never_decides():
    req = Req(params={'id': 'cnv_1'},
              body={'text': 'hello', 'in_reply_to': None, 'idempotency_key': 'k'},
              out={'message_id': 'msg_1'})
    status, _ = routes.post_message(req)
    assert status == 200
    assert req.runs.targets == [routes.conversation.post_message]
    assert req.runs.last.kwargs == {'text': 'hello', 'conversation_id': 'cnv_1',
                                    'in_reply_to': None}


# ── 19. `clarify_intent`: exactly one of a choice and an answer ──

@pytest.mark.parametrize('body', [{}, {'choice': None, 'text': None},
                                  {'choice': 'proceed', 'text': 'the web one'},
                                  {'choice': 'drop', 'text': ''}],
                         ids=['empty', 'neither', 'both', 'both-with-blank-text'])
def test_a_challenge_answer_gives_exactly_one_of_a_choice_and_a_text(body):
    """routes.py:839-840 (`(b.get('choice') is None) == (b.get('text') is None)`).
    Written as `and`, the BOTH row is accepted: one call would both choose and
    answer, which is two answers to one question — and the worker would read a
    reply the user never meant."""
    req = Req(params={'id': 'int_1'}, body=body)
    with pytest.raises(Invalid) as got:
        routes.clarify_intent(req)
    assert (got.value.field, got.value.why) == ('choice', 'give exactly one of choice and text')
    assert req.runs.calls == []


def test_an_answer_of_text_only_replies_to_the_question_it_answers(monkeypatch):
    monkeypatch.setattr(routes.queries, 'question_of',
                        lambda conn, iid: {'conversation_id': 'cnv_1', 'id': 'msg_q'})
    req = Req(params={'id': 'int_1'}, body={'text': 'the web one'}, out={'message_id': 'msg_new'})
    status, out = routes.clarify_intent(req)
    assert status == 200
    assert out == {'reply_id': None, 'intent_id': None, 'resolution': None,
                   'message_id': 'msg_new'}
    assert req.runs.targets == [routes.conversation.post_message]
    assert req.runs.last.kwargs == {'text': 'the web one', 'conversation_id': 'cnv_1',
                                    'in_reply_to': 'msg_q'}


def test_a_choice_only_routes_the_challenge_choice_once(monkeypatch):
    monkeypatch.setattr(routes.queries, 'question_of',
                        lambda conn, iid: pytest.fail('a choice must not read a question'))
    req = Req(params={'id': 'int_1'}, body={'choice': 'drop'}, out={'resolution': 'declined'})
    status, out = routes.clarify_intent(req)
    assert status == 200 and out == {'resolution': 'declined'}
    assert req.runs.targets == ['conversations.choose']
    assert req.runs.last.kwargs == {'intent_id': 'int_1', 'choice': 'drop'}


# ── 20. `_step_up_failed`: only a PAIRED client is counted, and revoked ──

def test_a_local_clients_refused_proof_revokes_nothing():
    """routes.py:940-942 (`req.principal['origin'] == 'paired' and
    req.api.step_up.failed(device)`). Read the `and` as `or` and the desktop's own
    re-arm — which is never asked for a PIN — can be revoked by a counter it never
    touched, and `failed()` is consulted for a client with no PIN to get wrong."""
    calls = []
    req = Req(api=api(step_up=step_up(calls, fails=True),
                      sse=SimpleNamespace(close_device=lambda d: calls.append(('close', d)))))
    routes._step_up_failed(req)
    assert calls == [], 'a local device was counted toward a revocation'
    assert req.runs.calls == [], 'a local device was revoked'


def test_a_paired_clients_fifth_wrong_proof_revokes_resets_and_closes_its_streams():
    calls = []
    req = paired(api=api(step_up=step_up(calls, fails=True),
                         sse=SimpleNamespace(close_device=lambda d: calls.append(('close', d)))))
    routes._step_up_failed(req)
    assert calls == [('failed', 'dvc_p'), ('reset', 'dvc_p'), ('close', 'dvc_p')], calls
    assert req.runs.last.fn is routes.commands.revoke_device
    assert req.runs.last.kwargs == {'device_id': 'dvc_p', 'reason': 'step_up_failures'}
    assert req.runs.last.keyed is False


def test_a_paired_client_below_the_limit_is_counted_and_kept():
    """The `and`'s right arm: `failed()` alone decides. Drop it and the first
    wrong PIN revokes the client."""
    req = paired(api=api(step_up=SimpleNamespace(begin=lambda d: True, end=lambda d: None, failed=lambda d: False,
                                                 reset=lambda d: pytest.fail(
                                                     'nothing to reset: nothing was revoked')),
                         sse=SimpleNamespace(close_device=lambda d: pytest.fail(
                             'no stream was closed for a client that kept its token'))))
    routes._step_up_failed(req)
    assert req.runs.calls == [], 'the client was revoked before its fifth wrong proof'

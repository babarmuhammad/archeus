"""T-1154 · the highest-risk uncovered branches of `archeus/api/routes.py`
lines 518-740 inclusive at tip 56d53504 — the e-stop sentinel pair, the account
/ resource-policy / opt-in writes, the three query-parameter reads and the
harness list, driven through fake request and writer seams only.

THE TEN FINAL BRANCHES (fail-closed and denial first, then boundaries, then
error paths), each with the source line it owns. A card probe an existing test
already closes is replaced, and the replacement is named:

 1. `estop` with a writer that never answers (routes.py:722-724) — probe 2.
 2. `estop` replayed from an offline queue (routes.py:718-725) — replaces probe
    1, whose order is closed by tests/v1/unit/test_gaps_api_routes.py:483.
 3. `register_account` probes the login before the writer (routes.py:557-561) —
    replaces card probe 3 (`replayed rearm reports actual state`), which is
    already closed twice: tests/v1/unit/test_gaps_api_routes.py:493 and
    tests/v1/unit/test_pins_api_routes.py:646. The handler itself is never called
    in the suite: tests/v1/judge/client.py:573-580 is a copy of it that calls the
    command directly.
 4. `register_account` when the probe itself fails: no row (routes.py:557).
 5. `set_account_state`: a disable makes no probe, an enable probes the ROW's
    own harness and home (routes.py:565-569) — probe 4.
 6. `set_resource_policy`: the client's `expected_version` and the row's own
    usage measures, never the body's (routes.py:578-581) — probe 5.
 7. `set_resource_policy` refused as stale is never resubmitted unversioned
    (routes.py:580) — probe 5's fault half.
 8. `set_opt_in`: one keyed submit built from the body's five fields, on a route
    only an admin credential reaches (routes.py:592-597, row routes.py:1200) —
    probe 6.
 9. `execution_stream` with a malformed output offset: refused before the
    snapshot, the adapter lookup and the output read, and a repeated `from` read
    as its LAST value (routes.py:625-631, helper 91-93) — probe 7, composed past
    tests/v1/unit/test_pins_api_routes.py:568.
10. `usage_by`: an unknown grouping refused before any read, a blank one
    grouping by account, keys made public before grouping (routes.py:657-665) —
    probe 9.
11. `mission_timeline`: an empty cursor is refused rather than answered as the
    first page, a repeated parameter means its LAST value, and the limit ends are
    inclusive (routes.py:670-677, helpers 91-98) — probe 10, composed past
    tests/v1/unit/test_gaps_api_routes.py:566.
12. `list_harnesses`: one breaker per harness from one snapshot and one `now`,
    rows copied never written into (routes.py:599-605) — replaces probe 8, whose
    refusals are closed by tests/v1/unit/test_gaps_api_routes.py:551.

(These twelve tests are the card's ten branches: 3 and 4 are one branch's two
halves, as are 6 and 7.)

Supplementary tests after the ten cover what the replaced probes left genuinely
open in the same slice: the legal `days` extremes (routes.py:645-650), the
preference keys a resource card may send (607-614), an unknown account behind
the two account writes (563-570), `_read_homes`' positional contract (518-520)
and the reads that must carry the public homes (616-619, 680-687, 689-693), the
own-caller list behind `/v1/provider-terms` (535-539), the path-bound harness of
a terms answer (541-546), the path-bound subject of the two stop commands
(709-716) and the verb each route row grants (1094-1277).

Nothing here is real OS work. The e-stop sentinel (`LocalNode.disarmed`) is the
real sentinel only as far as `ARCHEUS_HOME`, which tests/v1/conftest.py:37 pins
under `tmp_path`; the writer (server.py:325's `run` shape), the reader, the
adapters, the registry, the application queries and the request itself are
fakes. The `tc` fixture of
`tests/v1/integration/conftest.py` starts a real socket and is never asked for.
No network, no subprocess, no sleep, no real credential, no thread inventory,
nothing read from the host environment, no case-sensitivity or path-separator
assumption, no OS error text.
"""

import contextlib
from types import SimpleNamespace

import pytest

from archeus.api import auth, routes, schemas
from archeus.api.schemas import Invalid
from archeus.core import metrics
from archeus.core.application import attention, outcomes
from archeus.core.application import replay as replay_module
from archeus.core.application import trace as trace_module
from archeus.core.execution import output as output_module
from archeus.infra.db.writer import NotFound, VersionConflict
from archeus.node.local import LocalNode

CONN = object()                                       # the read snapshot's connection
SHOWN = {'homes': {'hm_1': '/users/invented/hm_1'}}   # a public-homes mapping, invented
LOCAL_HOST = '127.0.0.1:7337'


# ── the seams a handler sees ──

class Db:
    """`req.api.db`. Every read the handler takes is counted, so a refusal that
    is supposed to come first can be shown to have opened no snapshot."""

    def __init__(self):
        self.reads = 0

    def read(self):
        self.reads += 1
        return contextlib.nullcontext(CONN)


class Registry:
    """`req.api.resources.registry`, recording that it was asked at all."""

    def __init__(self, ids=(), adapter='ADAPTER'):
        self._ids, self.adapter = list(ids), adapter
        self.ids_calls, self.get_calls = 0, []

    def ids(self):
        self.ids_calls += 1
        return list(self._ids)

    def get(self, harness_id):
        self.get_calls.append(harness_id)
        return self.adapter


class Resources:
    """`req.api.resources`: the adapter-facing calls this slice makes, recorded,
    plus the registry and callers `_read_homes` hands on."""

    def __init__(self, probe_ret='PROBE', probe_raises=None, measures=('tokens',),
                 harness_list=(), registry=None, callers=(), order=None):
        self.probe_ret, self.probe_raises = probe_ret, probe_raises
        self.measures, self.harness_list = measures, list(harness_list)
        self.registry = Registry() if registry is None else registry
        self.callers, self.order = callers, order
        self.probe_calls, self.usage_calls, self.harness_calls = [], [], 0

    def _mark(self, what):
        if self.order is not None:
            self.order.append(what)

    def probe(self, harness_id, home_ref):
        self._mark('probe')
        self.probe_calls.append((harness_id, home_ref))
        if self.probe_raises is not None:
            raise self.probe_raises
        return self.probe_ret

    def usage_measures(self, harness_id, home_ref):
        self._mark('measures')
        self.usage_calls.append((harness_id, home_ref))
        return self.measures

    def harnesses(self):
        self.harness_calls += 1
        self._mark('harnesses')
        return self.harness_list


class Writer:
    """`req.run` as server.py:325 is: one writer submit, recorded, keyed by
    default, answered by what the future resolved to. `errors` is the queue of
    submits that never resolve (the writer died, the command was refused), so a
    handler cannot be forgiven for what the ledger never took."""

    def __init__(self, out=None, errors=(), order=None, watch=None):
        self.calls = []
        self.out = {'ok': True} if out is None else out
        self.errors = list(errors)
        self.order, self.watch = order, watch

    def __call__(self, fn, kwargs, *, actor_id=None, keyed=True):
        call = SimpleNamespace(fn=fn, kwargs=dict(kwargs), actor_id=actor_id, keyed=keyed)
        self.calls.append(call)
        if self.watch is not None:
            self.watch(call)                    # the world AS THE SUBMIT SEES IT
        if self.order is not None:
            self.order.append('run')
        if self.errors:
            raise self.errors.pop(0)
        return dict(self.out)

    @property
    def last(self):
        assert self.calls, 'the handler ran no command at all'
        return self.calls[-1]


def Api(resources=None, db=None):
    """The `Api` a handler reads (api/server.py). Nothing in it opens anything."""
    return SimpleNamespace(db=db if db is not None else Db(),
                           resources=resources if resources is not None else Resources(),
                           executions=SimpleNamespace(
                               estop='executions.estop', rearm='executions.rearm',
                               stop_execution='executions.stop_execution',
                               stop_mission='executions.stop_mission'),
                           static=SimpleNamespace(root_file=lambda name: (200, {'file': name})),
                           sse=SimpleNamespace(close_device=lambda d: None),
                           origin=SimpleNamespace(local_host=lambda h: h == LOCAL_HOST,
                                                  remote=()))


def Req(body=None, params=None, query=None, resources=None, db=None, out=None, errors=(),
        order=None, watch=None, replayed=False, proven=False):
    """What a handler sees: the parsed halves of a request plus the writer seam."""
    req = SimpleNamespace(body={} if body is None else body,
                          params={} if params is None else params,
                          query={} if query is None else query,
                          headers={'Host': LOCAL_HOST}, peer=('127.0.0.1', 54321),
                          principal={'principal_id': 'prn_u', 'device_id': 'dvc_u',
                                     'origin': 'local', 'scopes': list(auth.SCOPES)},
                          replayed=replayed, proven=proven,
                          api=Api(resources=resources, db=db))
    writer = Writer(out=out, errors=errors, order=order, watch=watch)
    req.runs, req.run = writer, writer
    return req


# ══════════════ the ten final branches: fail-closed and denial first ══════════════

# 1 ── `estop`: a writer that never answers.
def test_estop_a_writer_that_never_answers_leaves_the_sentinel_up_and_answers_nothing():
    """routes.py:722-724. Wrap `out = req.run(...)` in a `try` that answers
    anyway and the one request whose command never landed reports `armed: False`
    while every live process keeps running. Move the sentinel after the submit
    and Core is still armed while the stop is being decided — the hooks halt on
    the sentinel, not on the answer."""
    seen = []
    req = Req(out={'stopped': 3}, errors=[RuntimeError('the writer did not answer')],
              watch=lambda call: seen.append((call.fn, LocalNode.disarmed())))
    with pytest.raises(RuntimeError):
        routes.estop(req)
    assert seen == [('executions.estop', True)], 'the sentinel was not up at the submit'
    assert len(req.runs.calls) == 1
    assert LocalNode.disarmed() is True, 'a failed e-stop left Core armed'


# 2 ── `estop` replayed from an offline queue.
def test_a_replayed_estop_still_engages_the_sentinel_and_still_answers_disarmed():
    """routes.py:718-725. A replay applies NOTHING, so the sentinel is the only
    thing that halts the hooks: skip it for a replay (`if not req.replayed`) and
    the answer still reads `armed: False` with nothing halted.
    tests/v1/unit/test_gaps_api_routes.py:483 only ever runs a first submit, and
    the two replay tests in the suite (`test_gaps_api_routes.py:493`,
    `test_pins_api_routes.py:646`) are `rearm`'s."""
    req = Req(out={'stopped': 0}, replayed=True)
    status, out = routes.estop(req)
    assert (status, out) == (200, {'stopped': 0, 'armed': False})
    assert LocalNode.disarmed() is True, 'a replayed e-stop halted nothing'
    assert [(c.fn, c.keyed) for c in req.runs.calls] == [('executions.estop', True)]


# 3 & 4 ── `register_account`: the probe is outside the transaction, before it.
def test_registering_an_account_probes_the_login_before_the_writer_submits():
    """routes.py:557-561. Run the command first and the account is on the ledger
    before anyone knows whether the login works; drop the probe's answer into
    `auth` and it stays UNVERIFIED forever (resources.py:73-77 says `auth` IS the
    probe), so the router never uses it. The probe is asked about the body's own
    harness and home, and the idempotency key stays out of the command."""
    order = []
    probe = {'ok': True, 'detail': 'logged in'}
    res = Resources(probe_ret=probe, order=order)
    body = {'harness_id': 'fake', 'label': 'Work', 'auth_kind': 'oauth',
            'home_ref': 'invented-home', 'idempotency_key': 'key-1'}
    req = Req(body=body, resources=res, order=order)
    status, _out = routes.register_account(req)
    assert status == 200
    assert order == ['probe', 'run'], 'the probe did not precede the submit'
    assert res.probe_calls == [('fake', 'invented-home')]
    assert req.runs.last.fn is routes.resources.register_account
    assert req.runs.last.kwargs == {'harness_id': 'fake', 'label': 'Work',
                                    'auth_kind': 'oauth', 'home_ref': 'invented-home',
                                    'auth': probe}
    assert req.runs.last.keyed is True


def test_a_login_probe_that_fails_writes_no_account_row():
    """routes.py:557. Swallow the probe's failure and the row is written with
    `auth=None`, which resources.register_account records as an account nothing
    may be routed to — a login that could not be checked becomes a permanent
    refusal the user never asked for, and no error ever reaches the client."""
    res = Resources(probe_raises=RuntimeError('the login probe failed'))
    body = {'harness_id': 'fake', 'label': 'Work', 'auth_kind': 'oauth',
            'home_ref': None, 'idempotency_key': 'key-1'}
    req = Req(body=body, resources=res)
    with pytest.raises(RuntimeError):
        routes.register_account(req)
    assert res.probe_calls == [('fake', None)]
    assert req.runs.calls == [], 'an unprobed account was written anyway'


# 5 ── `set_account_state`: no probe for a disable; the ROW's own home for an enable.
def test_disabling_an_account_probes_nothing_and_enabling_probes_that_accounts_own_home(
        monkeypatch):
    """routes.py:565-569 (`... if b['enabled'] else None`). Drop the `if
    b['enabled']` and switching an account OFF spends a login probe and hands the
    command an `auth`, which fires the extra verified transition of
    resources.set_account_enabled (resources.py:111-112): the account the user
    just disabled is recorded as verified. The probe is asked about the ROW's
    harness and home, so no body can point it at another account's login."""
    rows = {'acc_1': {'harness_id': 'fake', 'home_ref': 'invented-home'},
            'acc_2': {'harness_id': 'other', 'home_ref': None}}
    monkeypatch.setattr(routes.queries, 'get_account', lambda conn, aid: dict(rows[aid]))
    order = []
    res = Resources(probe_ret='PROBE', order=order)
    off = Req(params={'id': 'acc_1'}, resources=res, order=order,
              body={'enabled': False, 'harness_id': 'fake', 'home_ref': 'invented-home',
                    'idempotency_key': 'key-1'})
    status, _out = routes.set_account_state(off)
    assert status == 200
    assert res.probe_calls == [] and order == ['run'], 'a disable probed the login'
    assert off.runs.last.fn is routes.resources.set_account_enabled
    assert off.runs.last.kwargs == {'account_id': 'acc_1', 'enabled': False, 'auth': None}
    assert off.runs.last.keyed is True

    on = Req(params={'id': 'acc_2'}, resources=res, order=order,
             body={'enabled': True, 'harness_id': 'invented-other', 'idempotency_key': 'key-2'})
    status, _out = routes.set_account_state(on)
    assert status == 200
    assert order == ['run', 'probe', 'run'], 'the enable did not probe before submitting'
    assert res.probe_calls == [('other', None)], 'the probe used the body, not the row'
    assert on.runs.last.kwargs == {'account_id': 'acc_2', 'enabled': True, 'auth': 'PROBE'}


# 6 & 7 ── `set_resource_policy`: the client's version, the row's own measures.
def test_a_resource_policy_carries_the_clients_version_and_only_the_measures_that_account_reports(
        monkeypatch):
    """routes.py:576-581. Drop `expected_version=b.get(...)` and two Control tabs
    silently overwrite one another's ceilings (the command's own optimistic
    check, optins/resources lifecycle, never sees a version to compare). Ask the
    adapter about the BODY's harness instead of the row's and a budget is allowed
    on a measure a different account reports, which is exactly what
    resources.set_resource_policy refuses (resources.py:118-126). And a body that
    names `account_id` or `actor` may not write one."""
    monkeypatch.setattr(routes.queries, 'get_account',
                        lambda conn, aid: {'harness_id': 'fake', 'home_ref': 'invented-home'})
    order = []
    res = Resources(measures=('tokens',), order=order)
    body = {'idempotency_key': 'key-1', 'expected_version': 7, 'priority': 3,
            'budgets': {'cost': 5}, 'consumption': 'explicit_only',
            'account_id': 'acc_TROJAN', 'actor': 'system', 'harness_id': 'invented-other',
            'usage_measures': ['cost']}
    req = Req(params={'id': 'acc_1'}, body=body, resources=res, order=order)
    status, _out = routes.set_resource_policy(req)
    assert status == 200
    assert order == ['measures', 'run'], 'the adapter was asked inside the submit'
    assert res.usage_calls == [('fake', 'invented-home')], 'measures came from the body'
    assert req.runs.last.fn is routes.resources.set_resource_policy
    assert req.runs.last.keyed is True
    assert req.runs.last.kwargs == {'priority': 3, 'allocation_pct': None, 'reserve_pct': None,
                                    'brain_reserve_pct': None, 'fallback': None,
                                    'budgets': {'cost': 5}, 'project_allow': None,
                                    'project_deny': None, 'consumption': 'explicit_only',
                                    'account_id': 'acc_1', 'expected_version': 7,
                                    'usage_measures': ('tokens',)}
    assert req.api.db.reads == 1                  # the account row, read once
    thin = Req(params={'id': 'acc_1'}, body={'idempotency_key': 'key-2'}, resources=res)
    routes.set_resource_policy(thin)
    assert thin.runs.last.kwargs['expected_version'] is None, 'a missing version became a 0'


def test_a_stale_resource_policy_is_refused_once_and_never_resubmitted_without_its_version(
        monkeypatch):
    """routes.py:580. Catch the VersionConflict and retry without the version
    "so the user's change lands" and the optimistic check is worth nothing: the
    older tab wins over the newer one, ceilings and all."""
    monkeypatch.setattr(routes.queries, 'get_account',
                        lambda conn, aid: {'harness_id': 'fake', 'home_ref': None})
    res = Resources(measures=('tokens',))
    req = Req(params={'id': 'acc_1'}, body={'idempotency_key': 'key-1', 'expected_version': 7,
                                            'priority': 4}, resources=res,
              errors=[VersionConflict('acc_1', 7, 9)])
    with pytest.raises(VersionConflict):
        routes.set_resource_policy(req)
    assert len(req.runs.calls) == 1, 'a refused policy was submitted more than once'
    assert req.runs.calls[0].kwargs['expected_version'] == 7


# 8 ── `set_opt_in`: one keyed submit, on an admin-only route.
def test_an_opt_in_is_one_keyed_submit_built_from_the_body_alone_on_an_admin_route():
    """routes.py:592-597 and its table row routes.py:1200. `expected_version`
    dropped and two tabs opt the same MCP server in and out blind, the later
    request overwriting the one that mattered (optins.py:37-65 compares it only
    when it is given); a version the handler invented (0) makes every first
    opt-in a conflict. A field the body invents (`actor_kind`, `scopes`) reaching
    the command is the application layer's guard being written by the client, and
    an un-keyed submit makes a replayed POST a second write. The row is what
    keeps an `observe` credential from opting a source in at all."""
    body = {'idempotency_key': 'key-1', 'owner_id': 'acc_1', 'kind': 'mcp', 'name': 'gh',
            'opted_in': True, 'expected_version': 4, 'actor_kind': 'system',
            'scopes': ['admin'], 'role': 'owner'}
    req = Req(body=body)
    status, out = routes.set_opt_in(req)
    assert status == 200 and out == {'ok': True}
    assert len(req.runs.calls) == 1, 'one request submitted more than one command'
    assert req.runs.last.fn is routes.optins.set_opt_in
    assert req.runs.last.keyed is True, 'a replayed opt-in would write twice'
    assert req.runs.last.kwargs == {'owner_id': 'acc_1', 'kind': 'mcp', 'name': 'gh',
                                    'opted_in': True, 'expected_version': 4}
    plain = Req(body={'idempotency_key': 'key-2', 'owner_id': 'prj_1', 'kind': 'plugin',
                      'name': 'fmt', 'opted_in': False})
    routes.set_opt_in(plain)
    assert plain.runs.last.kwargs['expected_version'] is None
    route, _params = routes.match('POST', '/v1/opt-ins')
    assert (route.handler, route.scope, route.idempotent, route.request_schema) == (
        routes.set_opt_in, 'admin', 'required', schemas.SET_OPT_IN)


# 9 ── `execution_stream`: a malformed offset is refused before anything is touched.
def test_a_malformed_output_offset_is_refused_before_the_snapshot_or_the_adapter_is_touched(
        monkeypatch):
    """routes.py:625-631. tests/v1/unit/test_pins_api_routes.py:568 refuses `-1`
    but only asserts the output was not read: nothing there says no snapshot was
    opened and no adapter was trusted. Read the row before parsing the offset and
    every malformed tail read costs a database snapshot (and an entity lookup
    whose harness then names the adapter), which is the cheap flood this route
    needs no reason to be. A repeated `from` is the same read: taking the first
    value rather than the last tails an offset the client has already been shown
    (routes.py:91-93)."""
    seen = {}
    entity = SimpleNamespace(id='exe_1', harness_id='fake')
    reg = Registry(ids=['fake'])
    res = Resources(registry=reg)
    monkeypatch.setattr(routes.executions, 'entity',
                        lambda conn, eid: seen.__setitem__('entity', eid) or entity)
    monkeypatch.setattr(routes.resources, 'homes', lambda *a, **k: SHOWN)
    monkeypatch.setattr(output_module, 'read',
                        lambda e, adapter, offset: seen.__setitem__('read', (e.id, adapter,
                                                                              offset)) or 'RAW')
    monkeypatch.setattr(routes, 'public_output', lambda payload, homes: (payload, homes))
    for bad in ('409x', '', '-1', '1' * 19):
        req = Req(params={'id': 'exe_1'}, query={'from': [bad]}, resources=res)
        with pytest.raises(Invalid) as got:
            routes.execution_stream(req)
        assert (got.value.field, got.value.why) == ('from', 'is an integer >= 0')
        assert req.api.db.reads == 0, 'a malformed tail opened a snapshot'
        assert 'entity' not in seen and 'read' not in seen
        assert reg.ids_calls == 0 and reg.get_calls == [], 'an adapter was resolved for nothing'
    status, out = routes.execution_stream(Req(params={'id': 'exe_1'}, query={'from': ['4096']},
                                              resources=res))
    assert status == 200 and out == ('RAW', SHOWN)
    assert seen['read'] == ('exe_1', 'ADAPTER', 4096)
    # a client that sends the parameter twice means the LAST one (routes.py:91-93):
    # reading the first tails a stale offset, which re-shows output already shown.
    routes.execution_stream(Req(params={'id': 'exe_1'},
                                query={'from': ['0', '8192', '16384']}, resources=res))
    assert seen['read'] == ('exe_1', 'ADAPTER', 16384)


# 10 ── `usage_by`: an unknown grouping, a blank grouping, public keys.
def test_an_unknown_usage_grouping_is_refused_before_any_read_and_a_blank_one_groups_by_account(
        monkeypatch):
    """routes.py:657-665. Drop the `if by not in outcomes.USAGE_BY` guard and the
    application layer's ValueError (outcomes.py:155-156) surfaces as a 500 on a
    public read; drop the `or 'account'` default and `?by=` (which parse_qs keeps
    as the empty string) is a 500 too, not the account view. And an account key
    that is not made public BEFORE the grouping is a home path in the answer —
    `public` has to run inside `usage`, per row, not on its rows afterwards."""
    asked, made_public = [], []

    def usage(conn, by, public=lambda key: key):
        asked.append((conn, by, public('acct_raw')))
        return {'rows': [{'account': 'PUBLIC'}]}

    def system_value(obj, homes, path_keys=()):
        made_public.append((obj, homes, tuple(path_keys)))
        return {'account': 'PUBLIC'} if set(obj) == {'account'} else [{'account': 'PUBLIC'}]

    monkeypatch.setattr(outcomes, 'usage', usage)
    monkeypatch.setattr(routes, 'system_value', system_value)
    monkeypatch.setattr(routes.resources, 'homes', lambda *a, **k: SHOWN)
    for blank in ({}, {'by': ['']}):
        req = Req(query=blank)
        status, out = routes.usage_by(req)
        assert (status, out) == (200, {'by': 'account', 'rows': [{'account': 'PUBLIC'}]})
        assert asked[-1][0] is CONN and asked[-1][1] == 'account'
        assert asked[-1][2] == 'PUBLIC', 'the raw account key reached the grouping'
        assert made_public[0] == ({'account': 'acct_raw'}, SHOWN, ('account',))
        assert req.api.db.reads == 1
    routes.usage_by(Req(query={'by': ['pass']}))
    assert asked[-1][1] == 'pass'
    bad = Req(query={'by': ['model']})
    with pytest.raises(Invalid) as got:
        routes.usage_by(bad)
    assert (got.value.field, got.value.why) == ('by', 'is one of %s' % ', '.join(
        outcomes.USAGE_BY))
    assert bad.api.db.reads == 0 and len(asked) == 3, 'a bad grouping still queried'


# 11 ── `mission_timeline`: `before` keeps its zero, the limit ends are inclusive.
def test_the_timeline_before_cursor_keeps_its_zero_and_the_limit_ends_are_inclusive(monkeypatch):
    """routes.py:670-677 and the two helpers it leans on (routes.py:91-98).
    tests/v1/unit/test_gaps_api_routes.py:566 refuses `limit=MAX+1` and
    `before='x'` and checks the defaults, so `if raw_b` (a truthiness read of a
    value that is legitimately empty) passes: `?before=` would then be answered
    with the newest page instead of a refusal, and a page that silently ignores
    its cursor repeats the newest events forever. A repeated parameter read as
    the FIRST value tails a cursor the client has already moved past. The two
    legal limit ends are never asserted either, so `1 < limit` (a first page of
    one event, or a full page of 100, refused)."""
    asked = []
    monkeypatch.setattr(routes.resources, 'homes', lambda *a, **k: SHOWN)
    monkeypatch.setattr(attention, 'timeline', lambda conn, mid, before=None, limit=50,
                        homes=None: asked.append((mid, before, limit, homes)) or {'events': []})
    req = Req(params={'id': 'msn_1'}, query={'before': ['0'],
                                             'limit': [str(attention.MAX_TIMELINE)]})
    status, out = routes.mission_timeline(req)
    assert (status, out) == (200, {'events': []})
    assert asked[-1] == ('msn_1', 0, attention.MAX_TIMELINE, SHOWN), 'before=0 lost its cursor'
    routes.mission_timeline(Req(params={'id': 'msn_2'}, query={'limit': ['1']}))
    assert asked[-1] == ('msn_2', None, 1, SHOWN)
    # an empty cursor is a bad request, not the first page (routes.py:91-93 hands
    # back '' for `?before=`, and `_cursor` refuses it): answering it with
    # `before=None` repeats the newest events to a client that asked to go back.
    blank = Req(params={'id': 'msn_4'}, query={'before': ['']})
    queried = len(asked)
    with pytest.raises(Invalid) as got:
        routes.mission_timeline(blank)
    assert (got.value.field, got.value.why) == ('before', 'is an integer >= 0')
    assert len(asked) == queried, 'a refused cursor still asked the timeline'
    # a parameter sent twice means the LAST one, so the cursor the client moved to wins
    routes.mission_timeline(Req(params={'id': 'msn_5'},
                               query={'before': ['7', '3'], 'limit': ['50', '2']}))
    assert asked[-1] == ('msn_5', 3, 2, SHOWN)
    for bad, why in (('0', 'is 1..%d' % attention.MAX_TIMELINE),
                     (str(attention.MAX_TIMELINE + 1), 'is 1..%d' % attention.MAX_TIMELINE),
                     ('x', 'is an integer >= 0'), ('1' * 19, 'is an integer >= 0')):
        req = Req(params={'id': 'msn_3'}, query={'limit': [bad]})
        with pytest.raises(Invalid) as got:
            routes.mission_timeline(req)
        assert (got.value.field, got.value.why) == ('limit', why)
        assert req.api.db.reads == 0, 'a refused page opened a snapshot'


# 12 ── `list_harnesses`: one breaker per harness, from one snapshot, copied out.
def test_the_harness_list_asks_the_breaker_for_every_harness_once_and_never_writes_into_a_row(
        monkeypatch):
    """routes.py:599-605. Write the breaker into the row (`h['breaker'] = ...`)
    and the object `resources.harnesses()` hands out is polluted for every later
    request, so a closed breaker is still shown as open after it clears; ask once
    and every harness wears another harness's breaker; read the clock per harness
    and one list straddles a minute boundary and says two contradictory things
    about the same window."""
    rows = [{'id': 'fake'}, {'id': 'other'}]
    res = Resources(harness_list=rows)
    calls = []
    ticks = {'n': 0}

    def clock():
        ticks['n'] += 1
        return 1700000000.0 + ticks['n'] * 0.5          # a clock fine enough to tell two reads apart

    monkeypatch.setattr(routes, 'time', SimpleNamespace(time=clock))
    monkeypatch.setattr(routes.resources, 'breaker',
                        lambda conn, hid, now: calls.append((conn, hid, now))
                        or {'until': 'later'})
    req = Req(resources=res, order=[])
    status, out = routes.list_harnesses(req)
    assert status == 200
    assert out == {'harnesses': [{'id': 'fake', 'breaker': {'until': 'later'}},
                                 {'id': 'other', 'breaker': {'until': 'later'}}]}
    assert [c[1] for c in calls] == ['fake', 'other'], 'one breaker served both harnesses'
    assert {c[0] for c in calls} == {CONN}, 'the harnesses did not come from one snapshot'
    assert {c[2] for c in calls} == {1700000000.5}, 'the clock was read per harness'
    assert req.api.db.reads == 1 and res.harness_calls == 1
    assert rows == [{'id': 'fake'}, {'id': 'other'}], 'the breaker was written into the row'


# ══════════════ supplementary: what the replaced probes left open in the slice ══════════════

def test_the_metrics_window_admits_both_legal_ends_and_refuses_a_non_number_before_any_read(
        monkeypatch):
    """routes.py:645-650. tests/v1/unit/test_gaps_api_routes.py:551 refuses `0`
    and `MAX+1`, so `2 <= days` (a one-day window, or the whole 90, refused as a
    client error) is unseen, and so is the non-numeric path, whose answer must be
    the same refusal, not a traceback out of `int()`."""
    asked = []
    monkeypatch.setattr(metrics, 'daily', lambda conn, days: asked.append((conn, days))
                        or {'days': []})
    for good in ('1', str(metrics.MAX_DAYS)):
        req = Req(query={'days': [good]})
        status, out = routes.metrics_days(req)
        assert (status, out) == (200, {'days': []})
        assert asked[-1] == (CONN, int(good)) and isinstance(asked[-1][1], int)
        assert req.api.db.reads == 1
    for bad in ('abc', '1.0', '1' * 19):
        req = Req(query={'days': [bad]})
        before = len(asked)
        with pytest.raises(Invalid) as got:
            routes.metrics_days(req)
        assert (got.value.field, got.value.why) == ('days', 'is an integer >= 0')
        assert len(asked) == before and req.api.db.reads == 0, 'a bad window still queried'


def test_an_account_that_does_not_exist_is_neither_probed_nor_written(monkeypatch):
    """routes.py:565-569 and 576-581. Probe first and the adapter is asked about
    a harness only the request named — for an account that is not on the ledger,
    spending a real login attempt on nothing, and answering whatever the probe
    said as though an account had been changed. The row is read first, and its
    absence ends the request."""
    def get_account(conn, aid):
        raise NotFound(aid)

    monkeypatch.setattr(routes.queries, 'get_account', get_account)
    res = Resources(probe_ret='PROBE')
    state = Req(params={'id': 'acc_gone'}, body={'enabled': True, 'idempotency_key': 'key-1'},
                resources=res)
    with pytest.raises(NotFound):
        routes.set_account_state(state)
    assert res.probe_calls == [] and state.runs.calls == []
    policy = Req(params={'id': 'acc_gone'}, body={'idempotency_key': 'key-2'}, resources=res)
    with pytest.raises(NotFound):
        routes.set_resource_policy(policy)
    assert res.usage_calls == [] and policy.runs.calls == []


def test_the_public_homes_are_built_from_the_registry_and_its_callers_in_that_order(monkeypatch):
    """routes.py:518-520. `resources.homes(conn, registry, callers)` takes them
    positionally (resources.py:813-821), so a swap treats a caller as a registry
    — every read in the slice is then a 500 — and passing the registry twice makes
    the default accounts of the own-callers invisible, which is a home path that
    no longer gets mapped back out of the answer."""
    reg = Registry(ids=['fake'])
    callers = (SimpleNamespace(id='pi'),)
    res = Resources(registry=reg, callers=callers)
    seen = {}
    monkeypatch.setattr(routes.resources, 'homes',
                        lambda *a, **k: seen.__setitem__('homes', a) or SHOWN)
    monkeypatch.setattr(routes.executions, 'view',
                        lambda conn, eid, homes=None: seen.__setitem__('view', (conn, eid, homes))
                        or {'id': eid})
    req = Req(params={'id': 'exe_1'}, resources=res)
    status, out = routes.get_execution(req)
    assert (status, out) == (200, {'id': 'exe_1'})
    assert seen['homes'] == (CONN, reg, callers)
    assert seen['view'] == (CONN, 'exe_1', SHOWN), 'the read lost its public homes'
    assert req.api.db.reads == 1


def test_the_mission_trace_gives_its_query_the_installed_registry_and_the_public_homes(monkeypatch):
    """routes.py:680-687. Trace without the registry cannot name an execution's
    harness, and trace without `homes` is the read that shows a home path (the
    same projection `resources.homes` exists for): neither is a wrong number, both
    are the leak the public layer was built to stop."""
    reg = Registry(ids=['fake'])
    seen = []
    monkeypatch.setattr(routes.resources, 'homes', lambda *a, **k: SHOWN)
    monkeypatch.setattr(trace_module, 'trace',
                        lambda conn, mid, registry, homes=None: seen.append(
                            (conn, mid, registry, homes)) or {'lanes': []})
    status, out = routes.mission_trace(Req(params={'id': 'msn_1'},
                                           resources=Resources(registry=reg)))
    assert (status, out) == (200, {'lanes': []})
    assert seen == [(CONN, 'msn_1', reg, SHOWN)]


def test_the_mission_replay_read_carries_the_public_homes(monkeypatch):
    """routes.py:689-693. `replay.replay(conn, id)` alone answers with the row
    evidence un-projected: its `seen` homes are exactly what `homes=` strips."""
    seen = []
    monkeypatch.setattr(routes.resources, 'homes', lambda *a, **k: SHOWN)
    monkeypatch.setattr(replay_module, 'replay',
                        lambda conn, mid, homes=None: seen.append((conn, mid, homes))
                        or {'evidence': []})
    status, out = routes.mission_replay(Req(params={'id': 'msn_1'}))
    assert (status, out) == (200, {'evidence': []})
    assert seen == [(CONN, 'msn_1', SHOWN)]


def test_the_provider_terms_answer_for_the_cores_own_callers_and_nothing_the_client_named(
        monkeypatch):
    """routes.py:535-539. Read the harness list from the request (or from
    `req.api.resources.callers`, which is a different list) and a client names a
    harness the answer then claims to describe — `queries.provider_terms`
    invents an `unknown` row for every id it is given (queries.py:306-313), so a
    caller the Core does not run is presented as one whose terms nobody answered."""
    monkeypatch.setattr(routes, 'real_callers',
                        lambda: [SimpleNamespace(id='pi'), SimpleNamespace(id='claude-code')])
    seen = []
    monkeypatch.setattr(routes.queries, 'provider_terms',
                        lambda conn, ids=(): seen.append((conn, tuple(ids))) or [])
    res = Resources(callers=(SimpleNamespace(id='acc_TROJAN'),))
    req = Req(query={'harness_id': ['acc_TROJAN']}, resources=res)
    status, out = routes.list_provider_terms(req)
    assert (status, out) == (200, {'provider_terms': []})
    assert seen == [(CONN, ('pi', 'claude-code'))]
    assert req.api.db.reads == 1


def test_a_provider_terms_answer_is_recorded_for_the_harness_in_the_path_never_the_body():
    """routes.py:541-546. Take `harness_id` from the body and a POST to
    `/v1/provider-terms/pi` records ADR-0021's answer against another harness —
    including an `unknown` one, which is what the router treats as "do not run
    it". A missing note stays a blank string, not a missing key, because the
    command stores what it is given."""
    req = Req(params={'id': 'pi'}, body={'headless': 'permitted', 'harness_id': 'claude-code',
                                         'rotation': 'refused', 'note': None,
                                         'idempotency_key': 'key-1'})
    status, _out = routes.decide_provider_terms(req)
    assert status == 200
    assert req.runs.last.fn is routes.own_calls.decide_provider_terms
    assert req.runs.last.keyed is True
    assert req.runs.last.kwargs == {'harness_id': 'pi', 'headless': 'permitted',
                                    'rotation': 'refused', 'note': ''}
    kept = Req(params={'id': 'pi'}, body={'headless': 'refused', 'note': 'not ours'})
    routes.decide_provider_terms(kept)
    assert kept.runs.last.kwargs['note'] == 'not ours'


def test_a_resource_card_sends_only_the_five_named_preferences_never_a_key_the_body_invented():
    """routes.py:607-614. Read the filter as `if k in b` and a card that answers
    "no ceiling" with `max_cost_band: null` sends None where the command wants no
    key at all, and the mission's ceiling is gone by a form that never asked for
    it. Forward the body itself and `idempotency_key` becomes a command keyword."""
    body = {'idempotency_key': 'key-1', 'preferred_accounts': ['acc_1'], 'max_cost_band': None,
            'forbidden_harnesses': ['ghost'], 'account_id': 'acc_TROJAN', 'actor': 'system'}
    req = Req(params={'id': 'msn_1'}, body=body)
    status, _out = routes.set_mission_resources(req)
    assert status == 200
    assert req.runs.last.fn is routes.resources.set_mission_resources
    assert req.runs.last.keyed is True
    assert req.runs.last.kwargs == {'mission_id': 'msn_1',
                                    'preferences': {'preferred_accounts': ['acc_1'],
                                                    'forbidden_harnesses': ['ghost']}}
    empty = Req(params={'id': 'msn_2'}, body={'idempotency_key': 'key-2'})
    routes.set_mission_resources(empty)
    assert empty.runs.last.kwargs['preferences'] == {}


def test_the_two_stop_commands_take_their_subject_from_the_path_never_the_body():
    """routes.py:709-716. Bind the wrong half (`stop_execution` with
    `mission_id`, or the mission's own command) and either the command raises on
    an unexpected keyword and the user's stop does not happen, or — read the two
    ways round — the execution the user pointed at keeps running while an
    unrelated mission is stopped. `actor` too: the writer takes the actor from the
    credential, never from a posted field."""
    exe = Req(params={'id': 'exe_1'}, body={'idempotency_key': 'key-1', 'execution_id': 'exe_9',
                                            'mission_id': 'msn_9', 'actor': 'system'})
    status, _out = routes.stop_execution(exe)
    assert status == 200
    assert exe.runs.last.fn == 'executions.stop_execution'
    assert exe.runs.last.kwargs == {'execution_id': 'exe_1'}
    assert exe.runs.last.keyed is True
    mission = Req(params={'id': 'msn_1'}, body={'idempotency_key': 'key-2',
                                                'execution_id': 'exe_9', 'mission_id': 'msn_9'})
    routes.stop_mission(mission)
    assert mission.runs.last.fn == 'executions.stop_mission'
    assert mission.runs.last.kwargs == {'mission_id': 'msn_1'}


def test_the_writers_of_the_slice_refuse_the_verb_the_route_does_not_offer():
    """The table rows this slice owns (routes.py:1094-1277): a read is a GET with
    no request schema, so a POSTed body is never read or validated against it,
    and a command is a POST. Answer a POST to `/v1/estop`'s GET twin, or run the
    handler for a verb the row never granted, and a write happens through a route
    that only ever admits reads — and reads carry no `request_schema`, so nothing
    would have checked what came in."""
    reads = ['/v1/metrics', '/v1/usage', '/v1/harnesses',
             '/v1/route-decisions', '/v1/provider-terms', '/v1/executions/exe_1',
             '/v1/executions/exe_1/stream', '/v1/missions/msn_1/timeline',
             '/v1/missions/msn_1/trace', '/v1/missions/msn_1/replay',
             '/v1/tasks/task_1/executions']
    for path in reads:
        route, _params = routes.match('GET', path)
        assert route.request_schema is None and route.idempotent is None, path
        with pytest.raises(routes.Refused) as got:
            routes.match('POST', path)
        assert (got.value.status, got.value.code) == (405, 'method_not_allowed'), path
    writes = {'/v1/estop': routes.estop, '/v1/rearm': routes.rearm,
              '/v1/executions/exe_1/stop': routes.stop_execution,
              '/v1/missions/msn_1/stop': routes.stop_mission,
              '/v1/accounts': routes.register_account,
              '/v1/accounts/acc_1/state': routes.set_account_state,
              '/v1/resource-policies/acc_1': routes.set_resource_policy,
              '/v1/opt-ins': routes.set_opt_in,
              '/v1/provider-terms/pi': routes.decide_provider_terms}
    shared = {'/v1/accounts': routes.list_accounts, '/v1/opt-ins': routes.list_opt_ins}
    for path, handler in writes.items():
        route, _params = routes.match('POST', path)
        assert (route.handler, route.idempotent) == (handler, 'required'), path
        assert route.scope in ('admin', 'control'), path
        if path in shared:                        # the same path, the other verb: a read
            read, _p = routes.match('GET', path)
            assert (read.handler, read.scope, read.request_schema, read.idempotent) == (
                shared[path], 'observe', None, None), path
            continue
        with pytest.raises(routes.Refused) as got:
            routes.match('GET', path)
        assert (got.value.status, got.value.code) == (405, 'method_not_allowed'), path

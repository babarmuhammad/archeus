"""T-1152: the highest-risk uncovered branches of archeus/api/routes.py lines
1-213 (tip 56d53504) — Mission and event inputs rejecting malformed boundaries,
fail-closed and denial first.

The ten final branches (ranked; the ten card probes were started with and the
already-covered or inapplicable ones were replaced, evidence per test):

 1. pause-all vs resume-all dispatch identity, empty kwargs      routes.py:180-186 (probe 9)
 2. pause/resume/start dispatch identity, path id over body     routes.py:166-178 (repl. probe 1)
 3. edit_plan: the path names the plan, the body cannot extend
    the command, a VersionConflict travels through unswallowed   routes.py:150-156 (probe 7)
 4. create_mission: a malformed body dispatches nothing and
    smuggles nothing into the command kwargs                     routes.py:159-163 (probe 8)
 5. an empty Last-Event-ID is a refused cursor and starts no
    stream (it does not fall through to ?after=)                 routes.py:206-208
 6. events: a malformed after-cursor is refused before the
    read connection is opened                                    routes.py:195 (probes 2+3 composed)
 7. events: a zero / over-maximum / nondecimal limit is refused
    before the read connection is opened                        routes.py:196-199 (probes 4+5)
 8. a malformed or empty ?state= narrows list_missions instead
    of widening it to everything                                  routes.py:128-133 (probe 6)
 9. events: the inclusive cursor and limit boundaries are
    accepted and forwarded as integers                            routes.py:195-199 (boundary)
10. the stream filter takes every repeated project/type value
    and narrows by leading prefix only                            routes.py:210 (replaces probe 10)

Replaced probes and why: probe 1 (duplicate singleton query) is pinned by
tests/v1/unit/test_pins_api_routes.py:136-155 and tests/v1/unit/test_gaps_api_routes.py:536;
probes 2/3 (`_cursor('-1')`, `_cursor('x')`) are pinned directly by
test_gaps_api_routes.py:529 and test_pins_api_routes.py:161-181, and the HTTP
answer by tests/v1/integration/test_api_errors.py:34-38 — what no existing test
observes is that the events handler refuses *before opening a read*, so those
probes survive only as that composition (entries 6 and 7); probes 4/5 are the
same composition on the limit side; probe 10's single-value narrowing is
pinned by test_gaps_api_routes.py:685-692, so entry 10 exercises the repeated
values and the prefix position, which no assertion touches.

Seams (the card's, honoured literally): no `tc` and no TempCore — no socket is
started, no worker, thread or Core is constructed, no OS call is made: these
handlers touch the OS only through `req.api.db.read` and `req.run`, both faked
here, and through `resources.homes`, monkeypatched on the seam the existing
tests use. ARCHEUS_HOME is the autouse tmp_path home of tests/v1/conftest.py;
nothing is written to disk at all. The environment is never read or printed.
"""

from types import SimpleNamespace

import pytest

from archeus.api import routes
from archeus.api.schemas import Invalid
from archeus.core.application import errors


class _Rec:
    """A fake collaborator: records every call, returns `ret`, may raise."""

    def __init__(self, ret=None):
        self.calls, self.ret = [], ret

    def __call__(self, *args, **kw):
        self.calls.append((args, kw))
        return self.ret


class _Runs:
    """The writer seam `req.run`: records the one submit a handler makes; the
    submit may lose a race (`raises`), exactly as the real submit does."""

    def __init__(self, raises=None):
        self.calls, self.raises = [], raises

    def __call__(self, fn, kwargs, *, actor_id=None, keyed=True):
        self.calls.append(SimpleNamespace(fn=fn, kwargs=kwargs, actor_id=actor_id,
                                          keyed=keyed))
        if self.raises is not None:
            raise self.raises
        return {'result': 'ok'}


class _Db:
    """The read connection manager, counted: a refusal must leave `reads` at 0."""

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


def _api():
    return SimpleNamespace(
        db=_Db(),
        resources=SimpleNamespace(registry=None, callers=None),
        sse=SimpleNamespace(serve=_Rec(ret=('streamed',))),
        work=SimpleNamespace(edit_plan=_Rec(ret={'plan_id': 'pln_1'})),
        authorization=SimpleNamespace(request_start=_Rec(ret={'requested': True})),
        missions=SimpleNamespace(pause=_Rec(ret={'state': 'PAUSED'}),
                                 resume=_Rec(ret={'state': 'EXECUTING'}),
                                 pause_all=_Rec(ret={'paused': []}),
                                 resume_all=_Rec(ret={'resumed': []}),
                                 reprioritise=_Rec(ret={'priority': 1})))


def _Req(**over):
    """What a handler sees (api/server.py's request object, faked): body, query,
    headers, params and the recorded writer seam. No Handler, no socket."""
    req = SimpleNamespace(body={}, query={}, headers={}, params={},
                          principal={'principal_id': 'prn_u', 'device_id': 'dvc_u',
                                     'scopes': ['observe', 'control', 'approve', 'admin'],
                                     'origin': 'local'},
                          peer=('127.0.0.1', 54321))
    req.api = _api()
    req.runs = _Runs(raises=over.pop('raises', None))
    req.run = req.runs
    for name, value in over.items():
        setattr(req, name, value)
    return req


# ── fail-closed and denial ──

def test_pause_all_and_resume_all_dispatch_two_different_commands_and_no_selectors():
    """routes.py:180-186. Closest existing: tests/v1/integration/test_p195_core.py:50
    (the commands through the rig, never through these handlers) and
    tests/v1/unit/test_api_structure.py:321 (pins (method, path, scope, idempotent)
    only, never the handler or the callable it runs). Swapping the two callables, or
    letting the body name a mission for a workspace-wide command, passes every one of
    those and silently inverts the whole workspace's state."""
    for path, name in (('/v1/missions/pause-all', 'pause_all'),
                       ('/v1/missions/resume-all', 'resume_all')):
        route, params = routes.match('POST', path)
        assert route.handler is getattr(routes, name) and params == {}
        req = _Req(body={'mission_id': 'msn_target', 'expected_version': 7,
                         'idempotency_key': 'k'})
        status, out = getattr(routes, name)(req)
        assert (status, out) == (200, {'result': 'ok'})
        (run,) = req.runs.calls
        assert run.fn is getattr(req.api.missions, name)      # its own command, `is`
        assert run.kwargs == {}                               # the body names nothing
        assert run.keyed is True                              # still an idempotent command
        other = 'resume_all' if name == 'pause_all' else 'pause_all'
        assert getattr(req.api.missions, other).calls == []   # the sibling untouched
    assert req.api.missions.pause_all is not req.api.missions.resume_all


def test_pause_resume_and_start_each_run_their_own_command_with_only_the_paths_id():
    """routes.py:166-178. Closest existing: none calls these handlers (a grep for
    routes.pause_mission/resume_mission/start_mission over tests/ finds no caller;
    test_api_structure.py only reads the table). If pause and resume shared one
    callable, or if a body `mission_id` could aim the command at another mission
    than the path's, no existing assertion would notice."""
    req = _Req(params={'id': 'msn_path'},
               body={'expected_version': 4, 'mission_id': 'msn_body'})
    status, out = routes.pause_mission(req)
    assert (status, out) == (200, {'result': 'ok'})
    (run,) = req.runs.calls
    assert run.fn is req.api.missions.pause
    assert run.kwargs == {'mission_id': 'msn_path', 'expected_version': 4}   # path wins
    assert run.keyed is True

    req2 = _Req(params={'id': 'msn_path'}, body={})
    routes.resume_mission(req2)
    (run2,) = req2.runs.calls
    assert run2.fn is req2.api.missions.resume is not req.api.missions.pause
    assert run2.kwargs == {'mission_id': 'msn_path', 'expected_version': None}

    req3 = _Req(params={'id': 'msn_path'}, body={'mission_id': 'msn_body', 'actor': 'x'})
    routes.start_mission(req3)
    (run3,) = req3.runs.calls
    assert run3.fn is req3.api.authorization.request_start
    assert run3.kwargs == {'mission_id': 'msn_path'}    # exactly: no smuggled keys


def test_edit_plan_obeys_the_path_not_the_body_and_shares_the_version_conflict():
    """routes.py:150-156. Closest existing: tests/v1/unit/test_gaps_core_application_work.py
    (the work command below the route) and tests/v1/unit/test_api_errors.py ROWS (the
    translator maps VersionConflict to 409, but nothing pinned that this route passes it
    through unswallowed, and that the body cannot name a different plan than the path or
    add a key to the command). A handler that read b['plan_id'], or that swallowed the
    conflict into a 200, would edit and approve the wrong plan silently."""
    tasks = [{'name': 't1'}]
    req = _Req(params={'id': 'pln_path'},
               body={'tasks': tasks, 'expected_version': 3, 'plan_id': 'pln_body',
                     'idempotency_key': 'k'})
    status, out = routes.edit_plan(req)
    assert (status, out) == (200, {'result': 'ok'})
    (run,) = req.runs.calls
    assert run.fn is req.api.work.edit_plan
    assert run.kwargs == {'plan_id': 'pln_path', 'tasks': tasks,
                          'expected_version': 3}                       # the path's id
    assert sorted(run.kwargs) == ['expected_version', 'plan_id', 'tasks']  # closed

    req = _Req(params={'id': 'pln_path'}, body={'tasks': tasks})
    routes.edit_plan(req)
    assert req.runs.calls[-1].kwargs['expected_version'] is None       # absent, not dropped

    req = _Req(params={'id': 'pln_path'}, body={})
    with pytest.raises(KeyError):
        routes.edit_plan(req)
    assert req.runs.calls == []                                        # nothing submitted

    req = _Req(params={'id': 'pln_path'}, body={'tasks': tasks, 'expected_version': 3},
               raises=errors.VersionConflict('pln_path', 3, 4))
    with pytest.raises(errors.VersionConflict) as got:
        routes.edit_plan(req)
    assert (got.value.expected, got.value.current) == (3, 4)           # to the translator
    assert len(req.runs.calls) == 1                                    # one submit, no retry


def test_create_mission_with_a_malformed_body_dispatches_no_command_and_smuggles_nothing():
    """routes.py:159-163. Closest existing: tests/v1/unit/test_gaps_api_routes.py:135
    pins only that POST /v1/missions matches this handler; tests/v1/integration/test_api_auth.py:73
    proves the schema layer refuses a missing `scope`, not a missing field. The server
    refuses a missing title before the handler (schemas.py:1043-1047 requires it), but the
    handler's own invariant — a body that still gets to it must never submit a partial
    command, and the command kwargs are a closed set the body cannot extend — is asserted
    nowhere. `{**b, ...}` here would hand the writer an `actor` from the request."""
    for body in ({}, {'title': 't'}, {'objective': 'o'}):
        req = _Req(body=dict(body))
        with pytest.raises(KeyError):
            routes.create_mission(req)
        assert req.runs.calls == []                       # no command from a partial body

    req = _Req(body={'title': 't', 'objective': 'o', 'actor': 'prn_evil',
                     'scopes': ['admin'], 'idempotency_key': 'k'})
    routes.create_mission(req)
    (run,) = req.runs.calls
    assert run.fn is routes.commands.create_mission
    assert run.kwargs == {'title': 't', 'objective': 'o', 'project_id': None,
                          'success_criteria': []}         # the defaults, nothing smuggled
    assert run.keyed is True

    req = _Req(body={'title': 't', 'objective': 'o', 'project_id': 'prj_1',
                     'success_criteria': [{'id': 'c1'}]})
    routes.create_mission(req)
    assert req.runs.calls[-1].kwargs == {'title': 't', 'objective': 'o',
                                         'project_id': 'prj_1',
                                         'success_criteria': [{'id': 'c1'}]}


def test_an_empty_reconnect_header_is_a_refused_cursor_that_starts_no_stream():
    """routes.py:206-208 (`if raw is None`). Closest existing:
    tests/v1/unit/test_gaps_api_routes.py:669 pins that the header beats ?after= and that
    a non-number header is an Invalid cursor — but never that a *present, empty* header is
    a cursor too. `if not raw` instead of `if raw is None` would silently fall through to
    ?after=7 (or to the head), and a client reconnecting with `Last-Event-ID:` would miss
    or replay events while believing it resumed."""
    req = _Req(headers={'Last-Event-ID': ''}, query={'after': ['7']})
    with pytest.raises(Invalid) as got:
        routes.events_stream(req)
    assert (got.value.field, got.value.why) == ('cursor', 'is an integer >= 0')
    assert req.api.sse.serve.calls == []                  # no stream at 7, none at the head


@pytest.mark.parametrize('raw', ['-1', 'x', '1' * 19, '0x10', ' 1', '+1'],
                         ids=['minus', 'letter', 'nineteen', 'hex', 'space', 'plus'])
def test_events_refuses_a_malformed_cursor_before_opening_a_read(raw, monkeypatch):
    """routes.py:195 through the handler. Closest existing:
    tests/v1/unit/test_gaps_api_routes.py:529 and test_pins_api_routes.py:170 call
    routes._cursor directly (never events), and tests/v1/integration/test_api_errors.py:34
    only checks the answered status over the real socket. No assertion pinned the order:
    a refused cursor must open no read connection and reach no query — validating after
    `db.read()` holds a pool slot while rejecting garbage."""
    seen = []
    monkeypatch.setattr(routes.queries, 'events', lambda *a, **k: seen.append(a) or [])
    req = _Req(query={'after': [raw]})
    with pytest.raises(Invalid) as got:
        routes.events(req)
    assert (got.value.field, got.value.why) == ('cursor', 'is an integer >= 0')
    assert req.api.db.reads == 0 and seen == []


@pytest.mark.parametrize('raw,why', [('0', 'is 1..1000'), ('1001', 'is 1..1000'),
                                     ('1000000', 'is 1..1000'),
                                     ('1' * 19, 'is an integer >= 0'),
                                     ('', 'is an integer >= 0'),
                                     ('x', 'is an integer >= 0'),
                                     ('-1', 'is an integer >= 0')],
                         ids=['zero', 'over', 'million', 'nineteen', 'empty', 'letter',
                              'minus'])
def test_events_refuses_a_limit_outside_one_to_one_thousand_before_opening_a_read(raw, why,
                                                                                   monkeypatch):
    """routes.py:196-199 (`500 if raw is None else _cursor(...)` then `not 1 <= limit <=
    1000`). Closest existing: tests/v1/integration/test_api_errors.py:36-38 answers
    limit=0/1001 over the real socket (status only, no ordering observable) and
    tests/v1/unit/test_gaps_api_routes.py:536 only uses a valid 7/500. The two distinct
    refusals (the range check versus the digit check, each with its own `why`) and the
    zero-reads invariant are pinned nowhere."""
    seen = []
    monkeypatch.setattr(routes.queries, 'events', lambda *a, **k: seen.append(a) or [])
    req = _Req(query={'limit': [raw]})
    with pytest.raises(Invalid) as got:
        routes.events(req)
    assert (got.value.field, got.value.why) == ('limit', why)
    assert req.api.db.reads == 0 and seen == []


def test_a_malformed_or_empty_mission_state_narrows_the_list_instead_of_widening_it(
        monkeypatch):
    """routes.py:128-133. Closest existing: tests/v1/unit/test_pins_api_routes.py:145
    forwards only plausible values ('ACTIVE', 'PAUSED'), so a `state or None` coercion —
    the classic bug that turns `?state=` and `?state=bogus` into *every mission in the
    workspace* — passes it. An unknown state must reach the query verbatim (where it
    matches no row, tests/v1/unit/test_gaps_core_application_queries.py:139), never
    become the absent filter."""
    seen = []
    monkeypatch.setattr(routes.queries, 'list_missions',
                        lambda conn, state, project, homes=None:
                        seen.append((state, project, homes)) or [])
    monkeypatch.setattr(routes.resources, 'homes', lambda conn, registry, callers: 'HOMES')
    req = _Req(query={'state': ['NOT_A_STATE'], 'project': ['']})
    status, out = routes.list_missions(req)
    assert (status, out) == (200, {'missions': []})
    assert seen == [('NOT_A_STATE', '', 'HOMES')]         # verbatim — never coerced
    assert req.api.db.reads == 1
    req = _Req(query={'state': [''], 'project': ['prj_1']})
    routes.list_missions(req)
    assert seen[-1][:2] == ('', 'prj_1')    # an empty state still filters: never None


# ── boundaries ──

def test_events_accepts_exactly_its_inclusive_cursor_and_limit_boundaries(monkeypatch):
    """routes.py:195-199: limit 1 and 1000 are inside, leading zeros are decimal, an
    18-digit cursor is the largest accepted, and an empty `after=` is 0 — the `or '0'`
    fallback of l.195. Closest existing: tests/v1/unit/test_gaps_api_routes.py:536 uses
    7/9/500 only, so tightening `<= 1000` to `< 1000`, or dropping the `or '0'`, passes
    it."""
    seen = []
    monkeypatch.setattr(routes.queries, 'events',
                        lambda conn, after, limit, homes=None:
                        seen.append((after, limit, homes())) or [{'seq': 1}])
    monkeypatch.setattr(routes.resources, 'homes', lambda conn, registry, callers: 'HOMES')
    for query, want in (({'after': ['0'], 'limit': ['1']}, (0, 1)),
                        ({'limit': ['1000']}, (0, 1000)),
                        ({'after': ['999999999999999999'], 'limit': ['0500']},
                         (999999999999999999, 500)),
                        ({'after': ['']}, (0, 500))):
        req = _Req(query=query)
        status, out = routes.events(req)
        assert (status, out) == (200, {'events': [{'seq': 1}]})
        assert seen[-1][:2] == want                       # integers, not strings
        assert seen[-1][2] == 'HOMES'                     # the homes seam, lazily
        assert req.api.db.reads == 1


def test_the_stream_filter_takes_every_repeated_value_and_only_a_leading_prefix():
    """routes.py:210: the handler hands `narrowing` the FULL repeated lists (it reads
    req.query.get('project', ()), not `_one`), and a type filter must match at position
    0. Closest existing: tests/v1/unit/test_gaps_api_routes.py:685-692 filters one
    project and one type — replacing l.210 with `_one(req.query, 'project') or ()` (which
    silently drops the subscriber's first `?project=`) or with a substring match passes
    every existing assertion."""
    req = _Req(query={'project': ['prj_1', 'prj_2'], 'type': ['mission.', 'execution.']})
    routes.events_stream(req)
    (_req, cursor, keep) = req.api.sse.serve.calls[0][0]
    assert cursor is None
    assert keep(SimpleNamespace(project='prj_1', type='mission.created'))
    assert keep(SimpleNamespace(project='prj_2', type='execution.output'))
    assert keep(SimpleNamespace(project=None, type='mission.created'))     # no project kept
    assert not keep(SimpleNamespace(project='prj_3', type='mission.created'))
    assert not keep(SimpleNamespace(project='prj_1', type='xmission.created'))   # a
    assert not keep(SimpleNamespace(project='prj_1', type='missionx.created'))   # prefix
    req2 = _Req()                                             # unfiltered keeps everything
    routes.events_stream(req2)
    assert req2.api.sse.serve.calls[0][0][2](
        SimpleNamespace(project='prj_any', type='whatever.happened'))

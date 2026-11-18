"""T-1153 · the ten highest-risk UNCOVERED branches of archeus/api/routes.py
lines 311-517 (inclusive) at tip 56d53504, as units — driven with fake
requests (no Core, no sockets, no threads, no subprocess, no OS state).

Card probe triage (the ten probes the card named, and where they went):
1 repository parent traversal      COVERED (tests/v1/unit/test_gaps_api_routes.py
  `test_a_repository_graph_focus_cannot_walk_or_hide` ids dotdot/walkup;
  tests/v1/unit/test_pins_api_routes.py §14 up-one/dotdot/tail-dotdot) — replaced.
2 repository backslash             COVERED (same two tests, ids backslash/drive)
  — replaced.
3 focus over 1024 characters       COVERED (same, ids huge/over-1024, at-1024)
  — replaced.
4 malformed world focus kind/id    COVERED over HTTP
  (tests/v1/integration/test_graph_routes.py:43-48) — replaced, kept as the
  fail-closed-ORDER composition no existing test makes (refused before the
  read opens, entry 1).
5 depth outside bounds             PARTLY covered (same HTTP test: numeric
  depth 0/3 and limit 0/1001 on the WORLD route only) — kept as the repository
  call-site plus non-numeric depths/limits (entries 2-3).
6 inspections limit outside 1..500 COVERED (tests/v1/unit/test_pins_api_routes.py
  §13, six boundaries both sides) — replaced.
7 duplicate graph query            UNCOVERED (last-wins is pinned only for the
  events list, tests/v1/unit/test_gaps_api_routes.py
  `test_the_last_query_value_wins_and_the_event_default_stays_500`) — kept
  (entry 7).
8 blank/overlong title search      COVERED (tests/v1/unit/test_gaps_api_routes.py
  `test_the_title_search_needs_one_to_two_hundred_characters`) — replaced.
9 context token limit zero         COVERED (same file,
  `test_a_context_preview_budget_below_one_is_refused_before_any_read`) — kept
  only as its uncovered twin: an explicit-null budget must be DROPPED, not
  forwarded (entry 5).
10 forget default dry-run vs false PARTLY covered (default only, over a real
  Core in tests/v1/integration/test_knowledge_http.py n32; the command itself
  in tests/v1/unit/test_gaps_core_application_knowledge.py) — kept (entry 4).

The FINAL TEN, ranked fail-closed/denial first, then boundaries, then error
paths (source line, closest existing test and its miss, and the test name are
in the report /work/QWEN-DONE-T-1153.md):
1 malformed world-graph focus refused before the read and the query
  (routes.py:389-397).
2 non-numeric graph depth/limit refused before the database opens
  (routes.py:373-382, both graph handlers).
3 repository-graph depth/limit outside 1..DEPTH_MAX / 1..LIMIT_MAX refused
  without a read (routes.py:376-381 at the repository call site 405).
4 forget: dry_run False forwarded as False, absent as True; absent mode
  'retract' (routes.py:487-491).
5 context preview: explicit-null query/levels/limit_tokens dropped, falsy-but-
  present kept, zero budget refused before the read (routes.py:431-433).
6 knowledge move forwards falsy-but-present reason/expected_version and drops
  only absent/null ones (routes.py:460-466).
7 world-graph defaults: depth None and the graph's own 500-row page
  (routes.py:385-400); accepted boundary depth 2 / limit 1000.
8 a duplicated graph query parameter answers from the LAST value
  (routes.py:374/378/389 consuming `_one` for the graph family).
9 the digest ack is a command that stores no idempotency key (routes.py:419-421).
10 the status strip reports the e-stop sentinel without inverting it and reads
    it exactly once (routes.py:329-339).

Style: the same in-process fake-request seams as the T-307 gaps file
(_Req/_Db/_Rec fakes defined HERE — this file imports no other test module and
never starts the `tc`/TempCore fixture, which opens real sockets). Every OS
touch the handlers make (the e-stop sentinel behind LocalNode.disarmed) is
faked through the class seam the neighbouring tests already use. Nothing here
reads a real database, filesystem, environment, socket or process; the tested
code performs no writes at all, so nothing needs a tmp_path root.
"""

import pytest

from archeus.api import routes
from archeus.api.schemas import Invalid
from archeus.core.domain import ids
from archeus.node import local

# ── the fake request seams (defined here; this file imports no sibling test) ──


class _Rec:
    """A fake collaborator: records calls, returns `ret`."""

    def __init__(self, ret=None):
        self.calls, self.ret = [], ret

    def __call__(self, *args, **kw):
        self.calls.append((args, kw))
        return self.ret


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


class _Req:
    """The handler-facing half of server.Handler: body/query/params plus the
    writer seam `run`, recorded with its `keyed` flag."""

    def __init__(self, body=None, query=None, params=None):
        self.body = {} if body is None else body
        self.query = {} if query is None else query
        self.params = {} if params is None else params
        self.db = _Db()
        self.api = type('A', (), {})()
        self.api.db = self.db
        self.api.resources = type('R', (), {})()
        self.api.resources.registry = None
        self.api.resources.callers = None
        self.runs = []

    def run(self, fn, kwargs, *, actor_id=None, keyed=True):
        self.runs.append(_Run(fn=fn, kwargs=kwargs, actor_id=actor_id, keyed=keyed))
        return {'ok': True}


class _Run:
    __slots__ = ('fn', 'kwargs', 'actor_id', 'keyed')

    def __init__(self, fn, kwargs, actor_id, keyed):
        self.fn, self.kwargs, self.actor_id, self.keyed = fn, kwargs, actor_id, keyed


def _never(name):
    """A fake that must never be called: the refusal was not fail-closed."""

    def f(*args, **kw):
        raise AssertionError('%s ran for a request that must be refused: %r %r'
                             % (name, args, kw))
    return f


# ═══ fail-closed and denial first ═══

# 1. world_graph focus: refused before the read opens and the query runs
#    (siblings under this entry: the missing-selector probe beside entry 4).


@pytest.mark.parametrize('focus,why', [
    ('device:dev_abc', 'is <kind>:<id> of a graph kind'),
    ('token:x', 'is <kind>:<id> of a graph kind'),
    ('', 'is <kind>:<id> of a graph kind'),
    (':%s' % ids.new_id('mission'), 'is <kind>:<id> of a graph kind'),
    ('mission', 'names a malformed mission id'),            # no colon: fid ''
    ('mission:msn_1', 'names a malformed mission id'),      # prefix, not a ULID
    ('mission:%s:x' % ids.new_id('mission'), 'names a malformed mission id'),
], ids=['device', 'token', 'empty', 'empty-kind', 'no-colon', 'short-id', 'two-colons'])
def test_a_malformed_world_graph_focus_is_refused_before_the_read_and_the_query(
        monkeypatch, focus, why):
    """routes.py:389-397. The HTTP probe (tests/v1/integration/
    test_graph_routes.py:43-48) asserts the 400 body but cannot see that no
    database read opened and no command ran; the repository-side focus refusals
    (test_gaps_api_routes.py, test_pins_api_routes.py §14) assert the graph
    query is not reached, but nothing does this for the world handler."""
    monkeypatch.setattr(routes.graph, 'world_graph', _never('graph.world_graph'))
    req = _Req(query={'focus': [focus]})
    bad = pytest.raises(Invalid, routes.world_graph, req)
    assert (bad.value.field, bad.value.why) == ('focus', why)
    assert req.db.reads == 0                                   # no read opened
    assert req.runs == []                                      # no command either


# 2. both graph handlers: a non-numeric page is refused before db.read().


@pytest.mark.parametrize('handler', [routes.world_graph, routes.repository_graph],
                         ids=['world', 'repository'])
@pytest.mark.parametrize('field,raw', [
    ('depth', 'x'), ('depth', '+1'), ('depth', '1_0'), ('depth', ' 1'),
    ('limit', '7x'), ('limit', '1.'), ('limit', '2,0'),
], ids=['depth-x', 'depth-plus', 'depth-underscore', 'depth-space',
        'limit-suffix', 'limit-dot', 'limit-comma'])
def test_a_graph_page_that_is_not_digits_is_refused_before_the_database_opens(
        monkeypatch, handler, field, raw):
    """routes.py:373-382 (both call sites, 388 and 405). The existing cursor
    pin (test_gaps_api_routes.py `test_a_cursor_is_one_to_eighteen_plain_digits`)
    calls routes._cursor directly and never reaches the graph call sites; the
    HTTP probe only ever sends plain digits, and int(raw) would happily eat
    '+1', '1_0' and ' 1'."""
    monkeypatch.setattr(routes.graph, 'world_graph', _never('graph.world_graph'))
    monkeypatch.setattr(routes.graph, 'repository_graph', _never('graph.repository_graph'))
    req = _Req(query={field: [raw]})
    bad = pytest.raises(Invalid, handler, req)
    assert (bad.value.field, bad.value.why) == (field, 'is an integer >= 0')
    assert req.db.reads == 0


# 3. repository call site: numeric bounds refused without a read (the HTTP
#    probe covered numeric depth/limit for the world route only).


@pytest.mark.parametrize('field,raw', [
    ('depth', '0'), ('depth', '3'), ('limit', '0'), ('limit', '1001'),
], ids=['depth-0', 'depth-3', 'limit-0', 'limit-1001'])
def test_a_repository_graph_page_outside_the_graph_bounds_is_refused_without_a_read(
        monkeypatch, field, raw):
    """routes.py:376-381 at its repository call site (405). The HTTP probe
    (test_graph_routes.py:46-47) only bounds-checks /v1/world/graph; the
    repository handler's own call — with its default depth of 1 — is unprobed,
    and a dropped bound there is an unbounded stored-graph read."""
    monkeypatch.setattr(routes.graph, 'repository_graph', _never('graph.repository_graph'))
    req = _Req(params={'id': 'rep_1'}, query={field: [raw]})
    bad = pytest.raises(Invalid, routes.repository_graph, req)
    want = ('depth', 'is 1..%d' % routes.graph.DEPTH_MAX) if field == 'depth' \
        else ('limit', 'is 1..%d' % routes.graph.LIMIT_MAX)
    assert (bad.value.field, bad.value.why) == want
    assert req.db.reads == 0


# 4. forget: the destructive command's gate — False stays False, absent is the
#    safe True, and an absent mode is 'retract'.


@pytest.mark.parametrize('over,dry,mode', [
    ({}, True, 'retract'),
    ({'dry_run': False}, False, 'retract'),
    ({'dry_run': True}, True, 'retract'),
    ({'mode': None}, True, 'retract'),
    ({'mode': '', 'dry_run': False}, False, 'retract'),          # '' is falsy: still the default
    ({'mode': 'purge', 'dry_run': False}, False, 'purge'),
], ids=['absent', 'false', 'true', 'null-mode', 'empty-mode', 'purge-real'])
def test_a_forget_dry_run_false_is_forwarded_as_false_and_an_absent_mode_is_retract(
        over, dry, mode):
    """routes.py:487-491 (`b.get('mode') or 'retract'`, `True if
    b.get('dry_run') is None else b['dry_run']`). n32
    (tests/v1/integration/test_knowledge_http.py:62) walks only the default
    side, over a real Core; the command-level tests pass dry_run explicitly.
    Read as `b.get('dry_run') or True`, an explicit False becomes a silent
    no-op; read as `b.get('dry_run', True)`, mode-style truthiness, a hostile
    client's False is respected but the absent case forgets for real — both
    are caught here on the exact kwargs."""
    sel = {'project_id': 'prj_1'}
    req = _Req(body=dict({'selector': sel}, **over))
    status, _out = routes.forget_knowledge(req)
    (run,) = req.runs
    assert status == 200 and run.fn is routes.knowledge.forget
    assert run.kwargs == {'selector': sel, 'mode': mode, 'dry_run': dry}
    assert run.keyed is True                                   # a command, always keyed


def test_a_forget_without_a_selector_is_a_refusal_not_an_implicit_everything():
    """routes.py:489 (`'selector': b['selector']`). Nothing probes the missing
    selector: n32 always sends one. Read as `b.get('selector') or {}`, an
    accidental empty selector reaches the command, whose own empty-selector
    rule is what stands between a typo and a workspace-wide retract."""
    req = _Req(body={'dry_run': False})
    pytest.raises(KeyError, routes.forget_knowledge, req)
    assert req.runs == []                                      # no command ran


# 5. context preview: an explicit-null budget is dropped, a falsy-but-present
#    one is kept, a zero budget is refused before the read.


def test_a_context_preview_null_budget_is_dropped_and_a_zero_one_refused_before_the_read(
        monkeypatch):
    """routes.py:431-433 (`if b.get(k) is not None`, then the `< 1` check).
    `test_a_context_preview_budget_below_one_is_refused_before_any_read`
    (test_gaps_api_routes.py) sends limit_tokens=0 only; the null-dropping arm
    is unpinned, and read as `if k in b` a body of explicit nulls dies in
    `None < 1` — a 500 on a legal CONTEXT_PREVIEW body — while read as
    truthiness, `levels: []` and `query: ''` are silently dropped."""
    seen = []
    monkeypatch.setattr(routes.context, 'assemble',
                        lambda conn, kind, xid, **kw: seen.append((kind, xid, kw)) or 'BODY')
    monkeypatch.setattr(routes, 'public_context', lambda body, h: {'preview': body, 'h': h})
    monkeypatch.setattr(routes.resources, 'homes', lambda *a: 'H')
    subject = {'kind': 'mission', 'id': ids.new_id('mission')}

    req = _Req(body={'subject': subject, 'query': None, 'levels': None, 'limit_tokens': None})
    status, out = routes.preview_context(req)
    (kind, xid, kw), = seen                                      # nothing forwarded
    assert status == 200 and (kind, xid) == (subject['kind'], subject['id'])
    assert kw == {'homes': 'H'} and out == {'preview': 'BODY', 'h': 'H'}
    assert req.db.reads == 1

    seen.clear()
    req = _Req(body={'subject': subject, 'query': '', 'levels': [], 'limit_tokens': 5})
    routes.preview_context(req)
    (_kind, _xid, kw), = seen                                    # falsy-but-present kept
    assert kw == {'homes': 'H', 'query': '', 'levels': [], 'limit_tokens': 5}

    seen.clear()
    req = _Req(body={'subject': subject, 'limit_tokens': 0})
    req.db = _Db()
    bad = pytest.raises(Invalid, routes.preview_context, req)
    assert (bad.value.field, bad.value.why) == ('limit_tokens', 'is an integer >= 1')
    assert req.db.reads == 0 and seen == []                      # refused before the read


# ═══ boundaries ═══

# 6. the knowledge moves forward exactly what the body meant, falsy included.


@pytest.mark.parametrize('name', ['confirm', 'reject', 'retract'])
def test_a_knowledge_move_forwards_a_falsy_reason_and_version_and_drops_absent_ones(
        monkeypatch, name):
    """routes.py:461-466 (`if req.body.get(k) is not None`). n32 moves a real
    item over HTTP without either optional field, so the forwarding arms are
    unpinned: read truthy, `reason: ''` and the lost-update gate
    `expected_version: 0` vanish; read always-forward, explicit nulls land on
    the command as extra kwargs. Both are caught on the exact kwargs."""
    fn = {'confirm': routes.knowledge.confirm, 'reject': routes.knowledge.reject,
          'retract': routes.knowledge.retract}[name]
    handler = {'confirm': routes.confirm_knowledge, 'reject': routes.reject_knowledge,
               'retract': routes.retract_knowledge}[name]
    kid = ids.new_id('knowledge_item')

    req = _Req(params={'id': kid}, body={'reason': '', 'expected_version': 0})
    status, _out = handler(req)
    (run,) = req.runs
    assert status == 200 and run.fn is fn and run.keyed is True
    assert run.kwargs == {'knowledge_item_id': kid, 'reason': '', 'expected_version': 0}

    req = _Req(params={'id': kid}, body={'reason': None, 'expected_version': None})
    handler(req)
    (run,) = req.runs
    assert run.kwargs == {'knowledge_item_id': kid}              # nulls absent, not None-valued


# 7. world_graph defaults: no depth (the graph's own workspace-wide), the
#    graph's own default page — and the accepted side of the numeric bounds.


@pytest.mark.parametrize('query,depth,limit', [
    ({}, None, 500),
    ({'depth': ['2'], 'limit': ['1000']}, 2, 1000),
], ids=['defaults', 'accepted-edges'])
def test_the_world_graph_defaults_are_no_depth_and_the_graph_default_page(
        monkeypatch, query, depth, limit):
    """routes.py:385-400 (`_graph_bounds(req, None)` at 388 and the forwarding call).
    The repository default depth of 1 is pinned (test_pins_api_routes.py §14
    `...passed_through_unchanged`), but nothing pins the WORLD default: flip
    `None` to `1` and the workspace overview silently becomes a one-hop
    neighbourhood; flip `<=` to `<` and depth 2 / limit 1000 answer 400."""
    seen = []
    monkeypatch.setattr(routes.graph, 'world_graph',
                        lambda conn, focus, d, l: seen.append((conn, focus, d, l)) or {'nodes': []})
    req = _Req(query=query)
    status, out = routes.world_graph(req)
    assert status == 200 and out == {'nodes': []}
    assert seen == [('conn', None, depth, limit)]
    assert req.db.reads == 1


# 8. a duplicated graph query parameter answers from the LAST value — the
#    graph call sites of `_one`, unprobed by the events-list pin.


def test_a_duplicated_graph_query_parameter_is_answered_from_the_last_value(monkeypatch):
    """routes.py:374, 378 and 389 (the graph family's `_one` call sites; the
    helper's last-wins arm is pinned only for routes.events,
    test_gaps_api_routes.py `test_the_last_query_value_wins_and_the_event_default_stays_500`).
    Read first-wins, a client's stale first `?focus=` (or a poisoned one)
    decides the page, and a refusal that should not happen — or not — does."""
    seen = []
    monkeypatch.setattr(routes.graph, 'world_graph',
                        lambda conn, focus, d, l: seen.append((focus, d, l)) or {'nodes': []})
    mid = ids.new_id('mission')
    req = _Req(query={'focus': ['bogus', 'mission:' + mid], 'depth': ['9', '2'],
                      'limit': ['0', '7']})
    status, _out = routes.world_graph(req)
    assert status == 200 and seen == [(('mission', mid), 2, 7)]
    assert req.db.reads == 1

    seen.clear()
    req = _Req(query={'focus': ['mission:' + mid, 'zzz:1']})    # the LAST one decides the refusal
    bad = pytest.raises(Invalid, routes.world_graph, req)
    assert (bad.value.field, bad.value.why) == ('focus', 'is <kind>:<id> of a graph kind')
    assert seen == [] and req.db.reads == 0


# ═══ error paths ═══

# 9. the digest ack runs unkeyed: nothing stores an idempotency row for it.


def test_the_digest_ack_is_a_command_that_stores_no_idempotency_key():
    """routes.py:419-421 (`req.run(world.ack_digest, ..., keyed=False)`).
    `test_a_launch_redeem_carries_only_the_token_hash_and_no_idempotency_key`
    pins keyed=False for register_device only; the table pin
    (test_api_structure.py:327) pins the route's `idempotent` column, not the
    handler's own keyword — flip it and every ack writes an idempotency_keys
    row from a command the table says carries no key."""
    req = _Req(body={'up_to_seq': 7})
    status, _out = routes.ack_digest(req)
    (run,) = req.runs
    assert status == 200 and run.fn is routes.world.ack_digest
    assert run.kwargs == {'up_to_seq': 7}
    assert run.keyed is False

    req = _Req(body={})                                         # no silent seq 0
    pytest.raises(KeyError, routes.ack_digest, req)
    assert req.runs == []


# 10. the status strip: the e-stop sentinel, un-inverted, consulted once,
#     under one read and no command.


def test_the_status_strip_reports_the_sentinel_without_inverting_it(monkeypatch):
    """routes.py:329-339 (`armed=not LocalNode.disarmed()`, `resumable=
    commands.resumable(conn)[1]`). The e-stop units in test_gaps_api_routes.py
    cover the estop/rearm routes; test_p195_core only source-inspects
    `commands.resumable(conn)`, and the T-144 status test reads
    `knowledge_pass`. Flip the `not` and Health's strip lies about the
    e-stop — the operator believes a live machine is armed, or an armed one
    is safe; read the sentinel twice and the answer can straddle a real flip."""
    seen = []
    armed_state = {'disarmed': False}
    monkeypatch.setattr(local.LocalNode, 'disarmed',
                        staticmethod(lambda: seen.append('sentinel') or armed_state['disarmed']))
    monkeypatch.setattr(routes.world_status, 'status',
                        lambda conn, project, h: {'base': (project, h)})
    monkeypatch.setattr(routes.live, 'live_work', lambda conn, project, h: 'LIVE')
    monkeypatch.setattr(routes.commands, 'resumable', lambda conn: (['msn_a', 'msn_b'], 2))
    monkeypatch.setattr(routes.resources, 'homes', lambda conn, reg, callers: 'H')

    armed_state['disarmed'] = False
    req = _Req(query={'project': ['prj_1']})
    status, out = routes.status(req)
    assert status == 200
    assert out['armed'] is True                                  # sentinel disarmed -> armed
    assert out['live'] == 'LIVE' and out['resumable'] == 2        # [1], not the id list
    assert out['base'] == ('prj_1', 'H')                          # ?project and homes forwarded
    assert seen == ['sentinel'] and req.db.reads == 1 and req.runs == []

    armed_state['disarmed'] = True
    seen.clear()
    req = _Req()
    _status, out = routes.status(req)
    assert out['armed'] is False                                   # sentinel armed -> not armed
    assert seen == ['sentinel'] and req.db.reads == 1              # exactly once per call
    assert out['base'] == (None, 'H')                              # no ?project: workspace-wide


# ═══ family seam probes required by the card (beyond the final ten) ═══

@pytest.mark.parametrize('method,path', [
    ('POST', '/v1/world/graph'),
    ('POST', '/v1/repositories/rep_1/graph'),
    ('POST', '/v1/repositories/rep_1/inspections'),
    ('POST', '/v1/search'),
    ('DELETE', '/v1/knowledge/kno_1'),
    ('DELETE', '/v1/knowledge/forget'),
    ('GET', '/v1/meetings/import'),
    ('POST', '/v1/knowledge/kno_1'),
])
def test_a_verb_the_table_does_not_offer_never_reaches_a_graph_or_knowledge_handler(
        method, path):
    """Route metadata rows 1146-1177 plus `match` (routes.py:1360+): the graph
    reads are GET-only and the knowledge moves POST-only, so the wrong verb
    is a 405 from the table and the handler below is never called. Content-type
    refusal is the server body pipeline — another card's assigned branches —
    and is deliberately NOT probed here."""
    with pytest.raises(routes.Refused) as got:
        routes.match(method, path)
    assert (got.value.status, got.value.code) == (405, 'method_not_allowed')


def test_a_consolidation_ask_without_a_size_gets_the_capped_default():
    """routes.py:494-499 (`b.get('max_items') or 20`). Nothing probes this
    route: test_knowledge_http imports/forgets, and the T-1093 command tests
    call knowledge.request_consolidation directly. Read `b.get('max_items',
    20)`, a client's explicit 0 asks for a zero-item pass instead of the
    contract's default."""
    req = _Req(body={'project_id': 'prj_1'})
    status, _out = routes.consolidate_knowledge(req)
    (run,) = req.runs
    assert status == 200 and run.fn is routes.knowledge.request_consolidation
    assert run.kwargs == {'project_id': 'prj_1', 'max_items': 20}
    assert run.keyed is True

    for asked, want in ((None, 20), (0, 20), (5, 5)):
        req = _Req(body={'project_id': 'prj_1', 'max_items': asked})
        routes.consolidate_knowledge(req)
        (run,) = req.runs
        assert run.kwargs == {'project_id': 'prj_1', 'max_items': want}


def test_feedback_defaults_come_from_the_route_not_from_absence():
    """routes.py:502-506 (`b.get('text') or ''`, `'promote': b.get('promote')`).
    No route-level probe exists: tests/v1/integration/test_knowledge.py runs
    the command directly. Drop the `or ''` and the command receives text
    None; drop the promote key and the record loses the field the command's
    signature expects — both caught on the exact kwargs."""
    subject = {'kind': 'knowledge_item', 'id': ids.new_id('knowledge_item')}
    req = _Req(body={'subject': subject, 'signal': 'positive'})
    status, _out = routes.record_feedback(req)
    (run,) = req.runs
    assert status == 200 and run.fn is routes.knowledge.record_feedback
    assert run.kwargs == {'subject': subject, 'signal': 'positive', 'text': '',
                          'promote': None}
    assert run.keyed is True

    req = _Req(body={'subject': subject, 'signal': 'correction', 'text': '  keep  ',
                     'promote': {'type': 'LESSON', 'title': 't'}})
    routes.record_feedback(req)
    (run,) = req.runs
    assert run.kwargs['text'] == '  keep  '                      # the route does not strip
    assert run.kwargs['promote'] == {'type': 'LESSON', 'title': 't'}

"""P18's two graph routes over a real Core (p18-design-gate A1 (2), A6, A14,
A15): authentication, the refusals, read-only-ness, and the route against the
TUI's list mapper over a mission the engine really ran."""

import time

import pytest

from archeus.cli.tui import present as P
from archeus.core.domain import ids
from v1.judge.http import TempCore


@pytest.fixture
def core(archeus_home):
    tc = TempCore(archeus_home).start()
    yield tc
    tc.stop(kill=True)


def _mission(tc):
    r = tc.http('POST', '/v1/missions', body={'title': 'Graph me', 'objective': 'o',
                                              'idempotency_key': 'g-%f' % time.time()})
    mid = r.json()['id']
    deadline = time.monotonic() + 40
    while tc.http('GET', '/v1/missions/' + mid).json()['state'] != 'COMPLETED':
        assert time.monotonic() < deadline, 'the fake mission never completed'
        time.sleep(0.05)
    return mid


def get(tc, path, **kw):
    r = tc.http('GET', path, **kw)
    return r.status, r.json()


def test_the_graph_needs_a_credential_and_refuses_what_is_not_a_node(core):
    assert core.http('GET', '/v1/world/graph', token=None).status == 401
    assert core.http('GET', '/v1/world/graph', token='dev_' + 'x' * 30).status == 401
    for q, field in (('?focus=device:dev_abc', 'focus'), ('?focus=token:x', 'focus'),
                     ('?focus=principal:' + ids.new_id('principal'), 'focus'),
                     ('?focus=mission:nope', 'focus'), ('?depth=3', 'depth'),
                     ('?depth=0', 'depth'), ('?limit=0', 'limit'), ('?limit=1001', 'limit')):
        s, b = get(core, '/v1/world/graph' + q)
        assert (s, b['error'], b['detail']['field']) == (400, 'invalid_request', field), q
    s, b = get(core, '/v1/world/graph?focus=mission:' + ids.new_id('mission'))
    assert (s, b['error']) == (404, 'not_found')
    for q in ('?focus=../../etc', '?focus=a/../b', '?focus=a%5Cb'):
        s, _ = get(core, '/v1/repositories/%s/graph%s' % (ids.new_id('repository'), q))
        assert s == 400, q
    s, b = get(core, '/v1/repositories/%s/graph' % ids.new_id('repository'))
    assert (s, b['error']) == (404, 'not_found')


def _counts(tc):
    with tc.core.db.read() as conn:
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'")]
        return {t: tuple(conn.execute('SELECT COUNT(*), MAX(rowid) FROM %s' % t).fetchone())
                for t in tables}


def test_the_graph_routes_write_nothing(core):
    """M23: twenty reads of each move no event and no row."""
    mid = _mission(core)
    # the event consumers finish the mission's own events first (their writes
    # are the mission's, not the reads')
    before, deadline = _counts(core), time.monotonic() + 20
    while True:
        time.sleep(0.5)
        now = _counts(core)
        if now == before or time.monotonic() > deadline:
            break
        before = now
    head = get(core, '/v1/status')[1]
    for _ in range(20):
        assert get(core, '/v1/world/graph')[0] == 200
        assert get(core, '/v1/world/graph?focus=mission:' + mid)[0] == 200
        r = core.http("GET", "/v1/repositories/%s/graph" % ids.new_id("repository"))
        assert r.status == 404
    assert _counts(core) == before
    assert get(core, '/v1/status')[1] == head


def test_the_route_answers_with_the_seq_it_reflects(core):
    mid = _mission(core)
    r = core.http('GET', '/v1/world/graph?focus=mission:' + mid)
    assert int(r.headers['X-Archeus-Seq']) <= r.json()['as_of_seq']


def _list_edges(tc, kind, x):
    """What the TUI's Relations list shows for one object, read the way the
    TUI reads it (screens.py)."""
    if kind == 'mission':
        mp = get(tc, '/v1/missions/%s/plan' % x)[1]
        m = get(tc, '/v1/missions/' + x)[1]
        sl = get(tc, '/v1/sessions?mission=' + x)[1]
        return P.mission_edges(m, mp, sl.get('sessions') or [])
    if kind == 'plan':
        return P.plan_edges(get(tc, '/v1/plans/' + x)[1])
    if kind == 'task':
        return []                        # its list edges are its plan's dependency lanes
    if kind == 'execution':
        return P.execution_edges(get(tc, '/v1/executions/' + x)[1])
    if kind == 'verification':
        return P.verification_edges(get(tc, '/v1/verifications/' + x)[1])
    if kind == 'session':
        s = get(tc, '/v1/sessions/' + x)[1]
        return P.session_edges(s, s)
    return None                          # no list function for this kind


def test_the_route_and_the_tui_list_show_the_same_edges(core):
    """A1 (2): over a mission the engine ran, every edge any object's Relations
    list shows is an edge of the graph, and every non-structural graph edge
    between loaded nodes is on some object's list — one edge set, two views."""
    mid = _mission(core)
    s, g = get(core, '/v1/world/graph?focus=mission:%s&depth=2&limit=1000' % mid)
    assert s == 200 and not g['truncated']
    shown = {(n['kind'], n['id']) for n in g['nodes']}
    listed_kinds = {'mission', 'plan', 'execution', 'verification', 'session'}
    from_list = set()
    for kind, x in shown:
        if kind not in listed_kinds:
            continue
        for e in _list_edges(core, kind, x) or []:
            other = (e['to']['kind'], e['to']['id'])
            if other in shown:                 # beyond the depth is not the graph's to show
                from_list.add((e['field'], frozenset({(kind, x), other})))
    from_graph = {(e['field'], frozenset({(e['from']['kind'], e['from']['id']),
                                          (e['to']['kind'], e['to']['id'])}))
                  for e in g['edges'] if not e['structural']
                  and e['from']['kind'] in listed_kinds}
    assert len(from_list) >= 8, from_list          # the mission really ran: a real neighbourhood
    assert from_list == from_graph, (from_list ^ from_graph)

"""P18's two graph routes over a real Core (p18-design-gate A1 (2), A6, A14,
A15): authentication, the refusals, read-only-ness, and — since P19 moved both
clients' Relations lists onto the route (p19-design-gate B1) — each object's
list read from its own one-hop focus over a mission the engine really ran."""

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


def test_a_mission_started_from_something_is_read_over_http_and_by_the_tui(core):
    """The P18 defect found 2026-10-03: a mission with an `origin_ref` (an id)
    made `/v1/world/graph` answer 500. Now the route answers, carries the
    started-from edge, and the TUI's Relations list shows the same edge."""
    from archeus.core.application import commands
    from archeus.core.domain.values import Ref
    msg = ids.new_id('message')
    mid = core.core.db.writer.execute(commands.create_mission, {
        'actor': Ref('user_device', ids.new_id('principal')), 'title': 'From a message',
        'objective': 'o', 'origin': 'conversation', 'origin_ref': msg})['id']
    assert get(core, '/v1/world/graph')[0] == 200
    s, g = get(core, '/v1/world/graph?focus=mission:%s&depth=2&limit=1000' % mid)
    assert s == 200
    assert [(e['to']['kind'], e['to']['id']) for e in g['edges']
            if e['field'] == 'Mission.origin_ref'] == [('message', msg)]
    m = get(core, '/v1/missions/' + mid)[1]
    assert m['origin_ref'] == msg                 # the contract: an id
    one = get(core, '/v1/world/graph?focus=mission:%s&depth=1&limit=1000' % mid)[1]
    rows = P.edge_rows(one['edges'], {'kind': 'mission', 'id': mid})
    assert [(e['rel'], e['to']) for e in rows if e['field'] == 'Mission.origin_ref'] == [
        ('started from', {'kind': 'message', 'id': msg})]


def test_the_route_answers_with_the_seq_it_reflects(core):
    mid = _mission(core)
    r = core.http('GET', '/v1/world/graph?focus=mission:' + mid)
    assert int(r.headers['X-Archeus-Seq']) <= r.json()['as_of_seq']


def test_every_relations_list_is_its_objects_one_hop_of_the_graph(core):
    """B1: what an object's Relations list shows (both clients read it from the
    route focused on the object, depth 1) is drawn from the one edge set: every
    row is a non-structural edge of the mission's wider neighbourhood, every
    edge the object itself holds is a row, and each says the clients' words.
    (A reverse edge is a row where the route's holder lookup reaches it; the
    kinds it does not reach are recorded in p19-design-gate §12.)"""
    from archeus.cli.tui._tables import EDGE_WORDS, INSPECTOR_TABS
    tabbed = {k for k, tabs in INSPECTOR_TABS.items() if 'relations' in tabs}
    mid = _mission(core)
    s, g = get(core, '/v1/world/graph?focus=mission:%s&depth=2&limit=1000' % mid)
    assert s == 200 and not g['truncated']
    full = {(n['kind'], n['id']) for n in g['nodes'] if not n.get('endpoint')}
    listed = 0
    for kind, x in sorted(full):
        if kind not in tabbed:               # no Relations list to compare
            continue
        me = {'kind': kind, 'id': x}
        s, one = get(core, '/v1/world/graph?focus=%s:%s&depth=1&limit=1000' % (kind, x))
        assert s == 200 and one['depth'] == 1 and not one['truncated'], (kind, x)
        rows = P.edge_rows(one['edges'], me)
        wider = {(e['field'], (e['to'] if e['from'] == me else e['from'])['id']) for e in g['edges']
                 if not e['structural'] and me in (e['from'], e['to'])
                 and _ref(e['to'] if e['from'] == me else e['from']) in full}
        held = {(e['field'], e['to']['id']) for e in g['edges']
                if not e['structural'] and e['from'] == me and _ref(e['to']) in full}
        got = {(r['field'], r['to']['id']) for r in rows if _ref(r['to']) in full}
        assert got <= wider, (kind, x, got - wider)          # nothing the graph lacks
        assert held <= got, (kind, x, held - got)            # nothing it holds is missing
        for r in rows:
            assert r['field'].startswith('relations.') or r['field'] in EDGE_WORDS, r
        listed += len(rows)
    assert listed >= 16, listed                    # the mission really ran: a real neighbourhood


def _ref(r):
    return (r['kind'], r['id'])

"""The gaps `test_api_client.py` left in `archeus/cli/_api.py` (T-331): the
fail-closed and denial paths of `_path`/`_q` (an id that must not build, an id
or a filter value that must not escape its segment or its parameter), the
boundary values the absence filter must keep (`0`, `''`), the empty id, and
the builder-line parity the name-set test cannot see. The token is the
client's `Authorization` header (`tui/client.py`), never a builder argument:
a path is what a log line and an error message carry, so nothing secret may
ever be built into one."""

import inspect

import pytest
from archeus.api import routes as R
from archeus.cli._api import _path, endpoints


def test_a_missing_id_fails_closed_before_any_request_is_built():
    # _api.py:19 `if _`: a `{id}` route with no id must raise, not build
    # '/v1/missions/None' and send a request at a route nobody asked for
    with pytest.raises(TypeError):
        endpoints.get_mission(None)


def test_a_non_string_id_fails_closed_before_any_request_is_built():
    # _api.py:19: an int id from a JSON row must raise, not be stringified
    with pytest.raises(TypeError):
        endpoints.get_mission(1234)
    with pytest.raises(TypeError):
        endpoints.get_session(42)


def test_an_id_cannot_escape_the_path_segment_it_is_put_in():
    # _api.py:19 `quote(id_, safe='')`: traversal, a fragment and a smuggled
    # '%2F' all stay inside the one segment the route serves
    assert endpoints.get_mission('../../etc/passwd') == '/v1/missions/..%2F..%2Fetc%2Fpasswd'
    assert endpoints.get_mission('#admin') == '/v1/missions/%23admin'
    assert endpoints.get_mission('%2Fx') == '/v1/missions/%252Fx'


def test_a_query_value_cannot_inject_a_second_parameter():
    # _api.py:14 `quote_via=quote, safe=''`: an unencoded '&' or '=' in a
    # value would arrive as a second parameter the caller never passed
    assert endpoints.events(after='1&limit=9999') == '/v1/events?after=1%26limit%3D9999'
    # and a space is %20 as the SPA's encodeURIComponent says, not a '+'
    assert endpoints.search_titles(q='hello world') == '/v1/search?q=hello%20world'


def test_no_builder_takes_a_secret_so_none_can_ever_reach_a_path():
    # every builder's parameters are (id_, its route's own filters): a
    # `token=`/`key=` argument here would put a secret where logs carry paths
    offenders = []
    for name in vars(endpoints):
        if name.startswith('_'):
            continue
        for p in inspect.signature(getattr(endpoints, name)).parameters:
            if any(s in p.lower() for s in ('token', 'secret', 'password', 'key',
                                            'auth', 'credential', 'bearer')):
                offenders.append('%s.%s' % (name, p))
    assert not offenders, offenders


def test_zero_is_a_value_and_survives_the_absence_filter():
    # _api.py:13 `if v is not None` (not `if v`): after=0 and from_=0 are the
    # first page and a replay from the start; dropping 0 asks Core for more
    # than the caller asked for
    assert endpoints.events(after=0) == '/v1/events?after=0'
    assert endpoints.execution_stream('exe_1', from_=0) == '/v1/executions/exe_1/stream?from=0'
    assert endpoints.metrics_days(days=0) == '/v1/metrics?days=0'


def test_an_explicitly_empty_filter_stays_in_the_query():
    # _api.py:13: only None means absent; an explicit '' stays an explicit ''
    # filter, and the route with the filter never collapses onto the plain one
    assert endpoints.list_missions(state='') == '/v1/missions?state='
    assert endpoints.list_missions(state='') != endpoints.list_missions()


def test_an_empty_id_is_its_own_path_and_never_the_list_route():
    # _api.py:19 `if _`: the guard is the separator, not the id — '' still
    # substitutes, so get_mission('') keeps the trailing slash that keeps it
    # a distinct path from the list route (and never keeps the literal {id})
    assert endpoints.get_mission('') == '/v1/missions/'
    assert endpoints.get_mission('') != endpoints.list_missions()


def test_the_absence_filter_works_in_any_position_and_keeps_the_order():
    # _api.py:13–14: pairs are dropped by being None, wherever they sit, and
    # the survivors keep the builder's own order
    assert endpoints.world_graph(focus=None, depth=2, limit=None) == '/v1/world/graph?depth=2'
    assert endpoints.list_missions(state=None, project='prj_1') == '/v1/missions?project=prj_1'
    assert endpoints.list_approvals(state='pending', mission=None) == '/v1/approvals?state=pending'
    # two survivors keep the builder's order, not an alphabetical one
    assert endpoints.list_missions(state='S', project='p') == '/v1/missions?state=S&project=p'


def test_every_builder_builds_the_path_of_its_row_in_the_route_table():
    """The name-set test cannot see a builder line whose path string went
    stale; a stale path is a silent request at the wrong route — 404 at best,
    another object's data at worst (the module's own claim: a route rename
    fails where it is used)."""
    bad = []
    for r in R.ROUTES:
        if not r.path.startswith('/v1/') or r.path == R.STREAM:
            continue
        build = getattr(endpoints, r.handler.__name__, None)
        if build is None:
            bad.append(('missing', r.handler.__name__, r.path))
            continue
        sig = inspect.signature(build)
        args = ['x1' for p in sig.parameters.values()
                if p.default is p.empty and p.kind == p.POSITIONAL_OR_KEYWORD]
        kw = {p.name: None for p in sig.parameters.values() if p.kind == p.KEYWORD_ONLY}
        try:
            got = build(*args, **kw)
        except Exception as exc:                                    # noqa: BLE001
            bad.append(('raised', r.handler.__name__, r.path, repr(exc)))
            continue
        if got != r.path.replace('{id}', 'x1'):
            bad.append(('stale', r.handler.__name__, r.path, got))
    assert not bad, bad


def test_a_path_without_a_placeholder_never_carries_an_id():
    # _api.py:19 `else r_path`: on a route with no {id} the id argument is
    # ignored outright — nothing a caller passed as an id can join the path
    assert _path('/v1/health', 'x1') == '/v1/health'

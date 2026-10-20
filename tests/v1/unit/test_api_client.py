"""The generated Python client (p19-design-gate B11): `archeus/cli/_api.py`
builds every route's path from `routes.py`, encodes what it puts in a path and
a query, and says the same string the SPA's `paths` says for the same read."""

from archeus.api import routes as R
from archeus.cli._api import STREAM_PATH, endpoints


def test_every_route_has_its_builder_named_after_its_handler():
    want = {r.handler.__name__ for r in R.ROUTES if r.path.startswith('/v1/') and r.path != R.STREAM}
    have = {n for n in vars(endpoints) if not n.startswith('_')}
    assert have == want, have ^ want
    assert STREAM_PATH == R.STREAM


def test_an_id_and_a_query_value_are_encoded_and_an_absent_one_is_left_out():
    assert endpoints.get_mission('msn_1') == '/v1/missions/msn_1'
    assert endpoints.get_mission('a/b?c') == '/v1/missions/a%2Fb%3Fc'
    assert endpoints.list_missions() == '/v1/missions'
    assert endpoints.list_missions(state='EXECUTING', project=None) == '/v1/missions?state=EXECUTING'
    assert endpoints.world_graph(focus='mission:msn_1', depth=1, limit=1000) == \
        '/v1/world/graph?focus=mission%3Amsn_1&depth=1&limit=1000'      # as encodeURIComponent
    assert endpoints.execution_stream('exe_1', from_=3) == '/v1/executions/exe_1/stream?from=3'


def test_a_read_and_a_command_on_one_path_are_two_builders():
    assert endpoints.list_messages('primary') == endpoints.post_message('primary') == \
        '/v1/conversations/primary/messages'
    assert endpoints.pause_mission('m') == '/v1/missions/m/pause'

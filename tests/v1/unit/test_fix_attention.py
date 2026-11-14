"""T-611: the route's explanation is Core-written prose that may name an
account home; the Needs-you item screens it as /v1/route-decisions does."""

import pytest

from archeus.core.application import attention
from archeus.core.homes import Homes
from archeus.infra.db import Database
from v1.integration.test_p21_health import _blocked_mission, _route

HOME = 'C:/T611/Work-Claude'


@pytest.fixture
def db(archeus_home):
    d = Database.open()
    yield d
    d.close()


def test_a_no_resource_reason_does_not_publish_an_account_home(db):
    mid, tid = _blocked_mission(db)
    _route(db, mid, tid, 'blocked', 'Nothing could run this. Not used: Work (%s) at its limit.'
           % HOME, '2999-01-01T15:00:00.000Z')
    homes = Homes([HOME], [('h', 'h:' + HOME.lower(), HOME)], shorts=lambda _: None,
                  path_flavour='windows')
    with db.read() as conn:
        [m] = [i for i in attention.attention(conn, homes=homes)['items']
               if i['kind'] == 'mission']
    assert HOME not in m['reason']
    assert 'its home' in m['reason']

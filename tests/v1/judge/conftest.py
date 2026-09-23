"""Judge fixtures: a `CoreClient` per binding, and the rig.

`client` is parametrized over the bindings that exist. P1 has the in-process
one only; P3.5 adds `http`, after which every scenario runs against both.
"""

import pytest

from .client import InProcessClient
from .support import Rig

BINDINGS = ('inprocess',)


@pytest.fixture(params=BINDINGS)
def client(request, archeus_home):
    if request.param == 'inprocess':
        return InProcessClient(archeus_home)
    raise AssertionError('unknown binding %r' % request.param)


@pytest.fixture
def rig():
    return Rig()

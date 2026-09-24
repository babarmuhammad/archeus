"""Judge fixtures: a `CoreClient` per binding, and the rig.

`client` is parametrized over the bindings that exist. P1 has the in-process
one only; P3.5 adds `http`, after which every scenario runs against both. The
rig drives the same Core the client talks to (restarts), so it is built on it.
"""

import pytest

from .client import InProcessClient
from . import support
from .support import Rig

BINDINGS = ('inprocess',)


@pytest.fixture(params=BINDINGS)
def client(request, archeus_home, monkeypatch):
    if request.param != 'inprocess':
        raise AssertionError('unknown binding %r' % request.param)
    c = InProcessClient(archeus_home)
    monkeypatch.setattr(support, 'idle', c._idle)
    yield c
    c.close()


@pytest.fixture
def rig(client):
    return Rig(client)

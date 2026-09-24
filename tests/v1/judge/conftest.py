"""Judge fixtures: a `CoreClient` per binding, and the rig.

`client` is parametrized over the bindings: `inprocess` (the application layer
pumped in this process) and, since P3.5, `http` (the real Core runtime on a
free port, spoken to over HTTP) — every scenario runs against both. The
rig drives the same Core the client talks to (restarts), so it is built on it.
"""

import pytest

from .client import InProcessClient
from .http import TempCore
from . import support
from .support import Rig

BINDINGS = ('inprocess', 'http')


@pytest.fixture(params=BINDINGS)
def client(request, archeus_home, monkeypatch):
    if request.param == 'inprocess':
        c = InProcessClient(archeus_home)
    elif request.param == 'http':
        c = TempCore(archeus_home).start().client()
    else:
        raise AssertionError('unknown binding %r' % request.param)
    monkeypatch.setattr(support, 'idle', c._idle)
    yield c
    c.close()


@pytest.fixture
def rig(client):
    return Rig(client)

"""Judge fixtures: a `CoreClient` per binding, and the rig.

`client` is parametrized over the bindings: `inprocess` (the application layer
pumped in this process) and, since P3.5, `http` (the real Core runtime on a
free port, spoken to over HTTP) — every scenario runs against both. The
rig drives the same Core the client talks to (restarts), so it is built on it.
"""

import pytest

from archeus.core import ports, runtime
from archeus.harnesses.fake import FakeCaller

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


class GatedCaller(FakeCaller):
    """Scripted like a fake, gated like a real adapter: the provider-terms gate
    exempts only FakeCaller itself (class identity), so this one needs the
    user's ADR-0021 answer before it may be called — the judge's stand-in for
    a real harness without spawning one."""


@pytest.fixture(params=BINDINGS)
def own_calls(request, archeus_home, monkeypatch):
    """`make(harnesses, preference=None) -> (client, rig)`: a Core, on this
    binding, whose own calls are offered only the harnesses described, each a
    dict of FakeCaller arguments (`gated: True` makes it a GatedCaller). The
    scenario states what the harnesses are; it never builds one (the judge
    imports no Core internals)."""
    made = []

    def make(harnesses, preference=None):
        callers = [(GatedCaller if h.pop('gated', False) else FakeCaller)(**h)
                   for h in (dict(x) for x in harnesses)]
        pref = ports.FixedOwnCallPreference(**(preference or {}))
        if request.param == 'inprocess':
            c = InProcessClient(archeus_home, callers=callers, preference=pref)
        else:
            c = TempCore(archeus_home, ports=runtime.Ports(callers=callers,
                                                           preference=pref)).start().client()
        monkeypatch.setattr(support, 'idle', c._idle)
        made.append(c)
        return c, Rig(c)
    yield make
    for c in made:
        c.close()

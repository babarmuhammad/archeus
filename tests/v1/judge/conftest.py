"""Judge fixtures: a `CoreClient` per binding, and the rig.

`client` is parametrized over the bindings: `inprocess` (the application layer
pumped in this process) and, since P3.5, `http` (the real Core runtime on a
free port, spoken to over HTTP) — every scenario runs against both. The
rig drives the same Core the client talks to (restarts), so it is built on it.

Since P7 the default Core's own calls are offered one scripted harness, the
recorded brain (`recorded_brain()`): the plan's "scripted brain and recorded
fixtures" (p7-design-gate D8). It answers the scenarios' messages and notes
from tests/v1/fixtures/brain/recordings.json and fails every other call, which
is how a pass no scenario scripts ends (`failed`, instead of P6's `gated`).
"""

import json
import os

import pytest

from archeus.core import ports, runtime
from archeus.harnesses.fake import FakeCaller

from .client import InProcessClient
from .http import TempCore
from . import support
from .support import Rig

BINDINGS = ('inprocess', 'http')
RECORDINGS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          'fixtures', 'brain', 'recordings.json')


def recorded_brain():
    """A FakeCaller replaying the recordings (exempt from ADR-0021 by class, as
    every scripted adapter is): a harness that declares `headless` and answers
    natively."""
    with open(RECORDINGS, encoding='utf-8') as f:
        rec = json.load(f)
    return FakeCaller('fake_brain', replies={k: v for k, v in rec.items()
                                             if not k.startswith('_')})


@pytest.fixture(params=BINDINGS)
def client(request, archeus_home, monkeypatch):
    if request.param == 'inprocess':
        c = InProcessClient(archeus_home, callers=[recorded_brain()])
    elif request.param == 'http':
        c = TempCore(archeus_home, ports=runtime.Ports(callers=[recorded_brain()])
                     ).start().client()
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

"""T-069 (K-O2): an own call that asks for no tools is routed only to a harness
that declares it can make one. The requirement is recorded before election and
eliminated by the router's existing capability step: pi preferred and unable
falls through to Claude Code by the ordinary ordering, and with no capable
harness the call is unavailable with nothing spawned. Fake callers and a
stand-in model roster only: no CLI, provider or account is touched."""

import pytest

from archeus.core import calls as OC
from archeus.core import ports
from archeus.core.application import resources
from archeus.core.domain import entities
from archeus.core.domain.values import Ref
from archeus.core.routing import router as R
from archeus.harnesses import calls as real
from archeus.harnesses.fake import FakeCaller
from archeus.core.application import commands
from archeus.infra.db import Database, rows


@pytest.fixture
def db():
    d = Database.open()
    yield d
    d.close()


def _own(db, callers, harness=None):
    system = Ref('system', db.writer.execute(commands.register_principal, {
        'kind': 'system', 'scopes': ['system']})['id'])
    return OC.OwnCalls(db, actor=system, callers=callers,
                       preference=ports.FixedOwnCallPreference(harness=harness))


def _ask(own, **kw):
    return own.run(**dict(dict(purpose='knowledge_extraction', workspace_id='ws_global',
                               source={'kind': 'mission', 'id': 'msn_x'}, project_id=None,
                               prompt='p', schema=None, check=lambda p: [], workdir='.'), **kw))


def _callers():
    ok = {'*': [{'parsed': {'ok': True}}]}
    return (FakeCaller('claude_code', replies=ok),
            FakeCaller('pi', replies=ok, no_tools=False))


def _decisions(db):
    with db.read() as c:
        return [r.entity for r in rows.where(c, entities.RouteDecision)]


def _step(rd, harness):
    return next(c['eliminated_at_step'] for c in rd.candidates if c['resource'] == harness)


def test_the_no_tools_requirement_is_recorded_before_election(db):
    claude, pi = _callers()
    own = _own(db, [claude, pi])
    _ask(own, no_tools=True)
    _ask(own, no_tools=False)
    with_, without = _decisions(db)
    assert with_.requirements['capabilities'] == ['headless', 'no_tools']
    assert without.requirements['capabilities'] == ['headless']


def test_pi_preferred_and_unable_falls_through_to_claude_by_the_ordinary_order(db):
    claude, pi = _callers()
    got = _ask(_own(db, [claude, pi], harness='pi'), no_tools=True)
    (rd,) = _decisions(db)
    assert got.state == 'ok' and rd.result == 'selected' and rd.harness_id == 'claude_code'
    assert _step(rd, 'pi') == 'capability' and 'no_tools' in _candidate(rd, 'pi')['reason']
    assert pi.sent == [] and [s.no_tools for s, _ in claude.sent] == [True]


def _candidate(rd, harness):
    return next(c for c in rd.candidates if c['resource'] == harness)


def test_with_no_capable_harness_the_call_is_unavailable_and_nothing_spawns(db):
    _, pi = _callers()
    got = _ask(_own(db, [pi], harness='pi'), no_tools=True)
    (rd,) = _decisions(db)
    assert got.state == 'unavailable' and rd.result == 'blocked' and pi.sent == []
    assert _step(rd, 'pi') == 'capability'


def test_a_forbidden_capable_harness_is_not_forced_back_in(db):
    claude, pi = _callers()
    got = _ask(_own(db, [claude, pi], harness='pi'), no_tools=True,
               forbidden={'harnesses': ['claude_code']})
    assert got.state == 'unavailable' and claude.sent == [] and pi.sent == []


def test_without_no_tools_the_preference_still_wins(db):
    claude, pi = _callers()
    got = _ask(_own(db, [claude, pi], harness='pi'))
    (rd,) = _decisions(db)
    assert got.state == 'ok' and rd.harness_id == 'pi' and claude.sent == []
    assert [s.no_tools for s, _ in pi.sent] == [False]


def test_a_recorded_decision_replays_from_its_own_requirements(db):
    claude, pi = _callers()
    own = _own(db, [claude, pi], harness='pi')
    _ask(own)
    _ask(own, no_tools=True)
    old, new = _decisions(db)
    # a decision recorded before T-069 carries no `no_tools` and replays as it was
    assert resources.replay(old)['selected'] == old.selected == 'pi'
    assert resources.replay(new)['selected'] == new.selected == 'claude_code'


def test_the_router_adds_no_requirement_of_its_own():
    h = lambda id_, *caps: {'id': id_, 'installed': True, 'exempt': True,
                            'capabilities': ['headless', 'structured_output', *caps],
                            'enforcement': 'none', 'structured_output': 'native',
                            'efforts': [], 'models': []}
    own = lambda id_: {'id': None, 'ref': '%s:default' % id_, 'harness': id_, 'label': id_,
                       'registered': False, 'health': None, 'why_not': None, 'policy': None,
                       'usage': None, 'ledger': None}
    snap = {'now': '2026-10-14T10:00:00.000Z', 'harnesses': [h('claude_code', 'no_tools'),
            h('pi')], 'accounts': [own('claude_code'), own('pi')], 'terms': {},
            'affinity': None, 'approved_fallbacks': []}
    req = {'subject': 'archeus_call', 'purpose': 'knowledge_extraction',
           'capabilities': ['headless'], 'structured_output': False, 'min_model_tier': None,
           'models': {}, 'preferred': {'harnesses': ['pi']}, 'forbidden': {},
           'required': {}, 'size': None, 'policy': None}
    assert R.route(req, snap)['selected'] == 'pi'


def test_claude_code_declares_no_tools_and_pi_does_not(monkeypatch):
    monkeypatch.setattr(real, 'claude_models', lambda: ())
    monkeypatch.setattr(real, 'pi_offers', lambda account=None: ((), 'stand-in'))
    assert 'no_tools' in real.ClaudeCodeCaller().capabilities().capabilities
    assert 'no_tools' not in real.PiCaller().capabilities().capabilities


def test_a_fake_caller_states_it_explicitly():
    assert 'no_tools' in FakeCaller('f').capabilities().capabilities
    assert 'no_tools' not in FakeCaller('f', no_tools=False).capabilities().capabilities
    assert 'no_tools' not in FakeCaller('f', headless=False).capabilities().capabilities

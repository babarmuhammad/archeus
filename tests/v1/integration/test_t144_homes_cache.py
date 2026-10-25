"""T-144 follow-up: the `Homes` the scrub builds is cached per Database. What the
RouteDecision history gives it (default accounts, retired registered homes) is
kept with the last row read and extended by the rows after it; the registry, the
callers and the Account rows are read on every call. A stale entry would leave a
home unscrubbed, so every way the history can change is pinned: a new decision, a
decision whose rowid a rolled-back insert had used, another Database."""

import pytest

from archeus.core.application import resources
from archeus.core.domain import entities, ids
from archeus.core.domain.events import new_event
from archeus.core.domain.values import Ref
from archeus.core.homes import scrub_text
from archeus.infra.db import Database
from v1.integration.test_routing import Rig
from v1.integration.test_t144_leak_sweep import HomeCaller


@pytest.fixture(autouse=True)
def no_8dot3_probe(monkeypatch):
    monkeypatch.setattr('archeus.core.homes._win_short', lambda _: None)


def _decision(home, rid=None):
    """A decision whose snapshot names `home` as a default account's home."""
    def run(tx, *, actor):
        rd = entities.RouteDecision(
            id=rid or ids.new_id('route_decision'), subject=Ref('archeus_call', 'lesson'),
            purpose='lesson', decided_by='router', selected='fake', harness_id='fake',
            result='selected', input_snapshot={'accounts': [
                {'registered': False, 'harness': 'fake', 'ref': 'fake:' + home,
                 'home_ref': home}]})
        tx.insert(rd, actor=actor)
        tx.append(new_event('route.decided', Ref('route_decision', rd.id), actor, payload={}))
    return run


def _scrubbed(db, text, registry=None, callers=()):
    with db.read() as conn:
        return scrub_text(text, resources.homes(conn, registry, callers))


def _home(tmp_path, name):
    return str(tmp_path / name)


@pytest.fixture
def decoded(monkeypatch):
    """How many RouteDecision rows the builder has decoded so far."""
    n = []
    real = resources.rows.decode

    def count(cls, record):
        n.append(cls) if cls is entities.RouteDecision else None
        return real(cls, record)
    monkeypatch.setattr(resources.rows, 'decode', count)
    return n


def test_a_warm_call_decodes_no_decision_and_a_new_one_decodes_only_itself(db, tmp_path, decoded):
    r = Rig(db)
    a, b = _home(tmp_path, 'Cache-A'), _home(tmp_path, 'Cache-B')
    r.do(_decision(a))
    r.do(_decision(_home(tmp_path, 'Cache-C')))
    assert _scrubbed(db, 'x ' + a + '/f') == 'x its home/f'
    assert len(decoded) == 2
    assert _scrubbed(db, 'x ' + a + '/f') == 'x its home/f'
    assert len(decoded) == 2, 'a second call with nothing new read the history again'
    r.do(_decision(b))
    assert _scrubbed(db, 'x ' + b + '/f') == 'x its home/f'
    assert len(decoded) == 3, 'a new decision re-read the whole history'
    r.do(lambda tx, *, actor: resources.bound_homes(tx.conn, tx.live) and None)
    assert len(decoded) == 3, 'the writer connection did not use the cache'


def test_a_home_introduced_after_the_cache_filled_is_scrubbed_on_read_and_write(db, tmp_path):
    r = Rig(db)
    old, new = _home(tmp_path, 'Cache-Old'), _home(tmp_path, 'Cache-New')
    r.do(_decision(old))
    assert _scrubbed(db, old) == 'its home'
    assert _scrubbed(db, new) == new
    r.do(_decision(new))
    assert _scrubbed(db, new + '/f') == 'its home/f'

    later = _home(tmp_path, 'Cache-Later')

    def on_writer(tx, *, actor):
        _decision(later)(tx, actor=actor)
        cut = resources.cut_bound(tx, 'z' * 600 + ' ' + later, 601 + len(later) - 3)
        return {'cut': cut}
    assert r.do(on_writer)['cut'] == 'z' * 600 + ' '


def test_the_live_registry_and_callers_are_read_on_every_call(db, tmp_path):
    r = Rig(db)
    r.do(_decision(_home(tmp_path, 'Cache-Hist')))
    live = _home(tmp_path, 'Cache-Live')
    assert _scrubbed(db, live, callers=[HomeCaller(live, 'live-only')]) == 'its home'
    assert _scrubbed(db, live) == live, 'a caller that is gone left its home in the cache'
    assert _scrubbed(db, live, callers=[HomeCaller(live, 'live-only')]) == 'its home'


def test_an_account_registered_after_the_cache_filled_is_scrubbed(db, tmp_path):
    r = Rig(db)
    r.do(_decision(_home(tmp_path, 'Cache-Hist')))
    acct = _home(tmp_path, 'Cache-Account')
    assert _scrubbed(db, acct) == acct
    r.account('Work', home_ref=acct)
    assert _scrubbed(db, acct + '/f') == 'its home/f'


def test_a_decision_that_reuses_the_rowid_of_a_rolled_back_one_is_read(db, tmp_path):
    r = Rig(db)
    r.do(_decision(_home(tmp_path, 'Cache-First')))
    ghost, real = _home(tmp_path, 'Cache-Ghost'), _home(tmp_path, 'Cache-Real')

    def rolled_back(tx, *, actor):
        _decision(ghost)(tx, actor=actor)
        resources.bound_homes(tx.conn, tx.live)
        raise RuntimeError('rolled back')
    with pytest.raises(RuntimeError):
        r.do(rolled_back)
    r.do(_decision(real))
    assert _scrubbed(db, real + '/f') == 'its home/f'
    assert _scrubbed(db, ghost) == ghost, 'a home only a rolled-back decision named is known'


def test_two_databases_never_share_the_cache(db, tmp_path):
    rid = ids.new_id('route_decision')
    mine, theirs = _home(tmp_path, 'Cache-Mine'), _home(tmp_path, 'Cache-Theirs')
    Rig(db).do(_decision(mine, rid))
    other = Database.open(str(tmp_path / 'other' / 'archeus.db'))
    try:
        Rig(other).do(_decision(theirs, rid))
        assert _scrubbed(db, mine) == 'its home' and _scrubbed(db, theirs) == theirs
        assert _scrubbed(other, theirs) == 'its home' and _scrubbed(other, mine) == mine
    finally:
        other.close()

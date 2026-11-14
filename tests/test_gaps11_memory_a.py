"""T-1410 · test gaps in claude_sessions/memory.py forget pass and small helpers
(1315-1381: _enum, _age_days, forget_pass).

Branches, ranked (eviction and refusal first, then the save gate and flag
clearing, then defaults and swallowed errors):

 1. 1361-1366  an invalid non-lesson is dropped only past _INVALID_TTL_DAYS;
               a younger one, or one with no invalidated_at, is kept.
 2. 1362       an invalid lesson is never dropped by this pass.
 3. 1367-1371  stale comes from confirmed_at, then created_at; fresh is not stale.
 4. 1372-1373  a fresh entity loses an old stale flag (checked through a save).
 5. 1379-1380  nothing to change: no save.
 6. 1379       a graph that stays stale is saved on every pass. Fixed.
 7. 1352-1353  an empty graph returns early with the episode count kept.
 8. 1345-1350, 1356-1359  TTL and decay failures are swallowed; the pass goes on.
 9. 1320-1328  _age_days: None for bad input, future stamps clamp to 0.
10. 1315-1317  _enum strips whitespace and falls back to the default.
"""

import copy
import time

import pytest

from claude_sessions import config, lessons, memory, worklog

NOW = 1_800_000_000


def _stamp(days_ago):
    return time.strftime('%Y-%m-%dT%H:%M:%S', time.gmtime(NOW - days_ago * 86400))


@pytest.fixture
def graph(monkeypatch):
    state = {'graph': {'entities': []}, 'saves': []}
    monkeypatch.setattr(memory.time, 'time', lambda: NOW)
    monkeypatch.setattr(memory, 'load_memory',
                        lambda p, f=None: copy.deepcopy(state['graph']))

    def _save(p, f, m):
        state['graph'] = copy.deepcopy(m)
        state['saves'].append(copy.deepcopy(m))
    monkeypatch.setattr(memory, 'save_memory', _save)
    monkeypatch.setattr(memory, '_INVALID_TTL_DAYS', 30)
    monkeypatch.setattr(memory, '_STALE_DAYS', 90)
    monkeypatch.setattr(worklog, 'apply_ttl', lambda p: 0)
    monkeypatch.setattr(config, 'load_settings', lambda: {})
    return state


def _fact(name, **over):
    e = {'id': 'fact:' + name, 'name': name, 'type': 'fact', 'valid': True,
         'created_at': _stamp(1), 'confirmed_at': _stamp(1)}
    e.update(over)
    return e


def test_forget_drops_only_expired_invalid_facts(graph):
    """An invalidation older than 30 days is dropped; a young one and one with no
    invalidated_at are kept. Catches: the TTL comparison at memory.py:1363-1365
    and the 'continue' at 1365."""
    graph['graph']['entities'] = [
        _fact('Old', valid=False, invalidated_at=_stamp(40)),
        _fact('Young', valid=False, invalidated_at=_stamp(5)),
        _fact('NoStamp', valid=False)]
    rep = memory.forget_pass('/p', '/f')
    assert rep['invalid'] == 1
    assert {e['name'] for e in graph['graph']['entities']} == {'Young', 'NoStamp'}


def test_forget_never_drops_invalid_lesson(graph):
    """Lessons are the decay pass's business, so an invalid lesson stays even when
    its invalidation is ancient. Catches: the 'type != lesson' guard at
    memory.py:1362."""
    graph['graph']['entities'] = [
        {'id': 'lesson:s:0', 'name': 'L', 'type': 'lesson', 'status': 'approved',
         'valid': False, 'invalidated_at': _stamp(400), 'last_used': 0}]
    rep = memory.forget_pass('/p', '/f')
    assert rep['invalid'] == 0
    assert [e['name'] for e in graph['graph']['entities']] == ['L']


def test_forget_flags_stale_from_confirmed_at_then_created_at(graph):
    """Staleness reads confirmed_at first and created_at only when confirmed_at is
    absent; a fresh confirmation wins over an old creation. Catches: the 'or' at
    memory.py:1368 and the comparison at 1369."""
    graph['graph']['entities'] = [
        _fact('ByConfirm', confirmed_at=_stamp(100)),
        _fact('ByCreate', confirmed_at=None, created_at=_stamp(100)),
        _fact('Reconfirmed', confirmed_at=_stamp(10), created_at=_stamp(200))]
    rep = memory.forget_pass('/p', '/f')
    flagged = {e['name'] for e in graph['graph']['entities'] if e.get('stale')}
    assert flagged == {'ByConfirm', 'ByCreate'}
    assert rep['stale'] == 2
    assert graph['graph']['stale_count'] == 2


def test_forget_clears_stale_flag_when_fresh(graph):
    """A fact flagged stale by an earlier pass loses the flag once it is fresh.
    The clear is only visible through a save, so an expired invalid fact in the
    same graph forces one. Catches: the pop at memory.py:1373."""
    graph['graph']['entities'] = [
        _fact('Back', stale=True),
        _fact('Gone', valid=False, invalidated_at=_stamp(60))]
    memory.forget_pass('/p', '/f')
    assert len(graph['saves']) == 1
    back = next(e for e in graph['saves'][0]['entities'] if e['name'] == 'Back')
    assert 'stale' not in back


def test_forget_writes_nothing_when_nothing_changed(graph):
    """Fresh, valid facts with no decay and no stale count: no save at all.
    Catches: the gate at memory.py:1379 returning True for a clean graph."""
    graph['graph']['entities'] = [_fact('A'), _fact('B')]
    rep = memory.forget_pass('/p', '/f')
    assert graph['saves'] == []
    assert rep == {'episodes': 0, 'lessons': 0, 'invalid': 0, 'stale': 0}


def test_forget_does_not_rewrite_unchanged_stale_graph(graph):
    """Expected: a second pass over an already-flagged graph writes nothing.
    Current: it writes the same graph again."""
    graph['graph']['entities'] = [_fact('Ancient', stale=True, confirmed_at=_stamp(200))]
    graph['graph']['stale_count'] = 1
    memory.forget_pass('/p', '/f')
    assert graph['saves'] == []


def test_forget_empty_graph_returns_early(graph, monkeypatch):
    """No entities: the episode count is kept and nothing else is touched.
    Catches: the early return at memory.py:1352-1353."""
    monkeypatch.setattr(worklog, 'apply_ttl', lambda p: 3)
    rep = memory.forget_pass('/p', '/f')
    assert rep == {'episodes': 3, 'lessons': 0, 'invalid': 0, 'stale': 0}
    assert graph['saves'] == []


def test_forget_swallows_ttl_and_decay_failures(graph, monkeypatch):
    """A failing episode TTL or lesson decay leaves its counter at 0 and the stale
    pass still runs. Catches: the bare excepts at memory.py:1347-1350 and 1357-1358."""
    def broken(*a, **k):
        raise RuntimeError('disk gone')
    monkeypatch.setattr(worklog, 'apply_ttl', broken)
    monkeypatch.setattr(lessons, 'apply_decay', broken)
    graph['graph']['entities'] = [_fact('Ancient', confirmed_at=_stamp(200))]
    rep = memory.forget_pass('/p', '/f')
    assert rep == {'episodes': 0, 'lessons': 0, 'invalid': 0, 'stale': 1}


def test_age_days_none_and_future_clamp(monkeypatch):
    """Empty, unparseable and non-string stamps give None. A stamp in the future
    reads as age 0 rather than negative. Catches: the guards at memory.py:1321-1323
    and the max(0.0, ...) at 1328. The mktime offset can add an hour in DST zones,
    hence the tolerance."""
    monkeypatch.setattr(memory.time, 'time', lambda: NOW)
    assert memory._age_days(None) is None
    assert memory._age_days('') is None
    assert memory._age_days('not a date') is None
    assert memory._age_days(12345) is None
    assert memory._age_days(_stamp(2)) == pytest.approx(2.0, abs=0.05)
    assert memory._age_days(_stamp(-3)) == 0.0


def test_enum_strips_and_falls_back():
    """Surrounding whitespace is ignored; a value outside allowed, None and '' all
    give the default. Catches: the strip at memory.py:1316 and the membership test
    at 1317."""
    allowed = ('uses', 'calls')
    assert memory._enum(' uses ', allowed, 'calls') == 'uses'
    assert memory._enum('\tcalls\n', allowed, 'uses') == 'calls'
    assert memory._enum('bogus', allowed, 'uses') == 'uses'
    assert memory._enum('   ', allowed, 'uses') == 'uses'
    assert memory._enum(None, allowed, 'uses') == 'uses'

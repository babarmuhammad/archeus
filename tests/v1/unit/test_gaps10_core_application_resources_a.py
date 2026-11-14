"""T-1393: the highest-risk uncovered branches of `archeus/core/application/resources.py`, lines 769-840
(`_decision_homes`, `homes`, `bound_homes`, the start of `cut_bound`).

Selected branches, ranked fail-closed first, then boundaries, then error paths:

 1. resources.py:786-787  _decision_homes: the cache hit returns the cached copy with no full read of
                          route_decisions.
 2. resources.py:788-791  _decision_homes: a cached (rowid, id) that is gone (rowid reused) forces a full
                          re-read; the stale defaults of the vanished row are not kept.
 3. resources.py:792-797  _decision_homes: an incremental read reads only rows after the cached rowid,
                          and the cached dicts are copied, not shared.
 4. resources.py:802-803  _decision_homes: a registered snapshot account with a str home_ref is recorded
                          in historical; a non-str home_ref is ignored.
 5. resources.py:799-801  _decision_homes: a later unregistered account with a ref and a home_ref replaces
                          an earlier default without one; an earlier default that has one is kept.
 6. resources.py:798-800  _decision_homes: an unregistered account without a ref is ignored entirely.
 7. resources.py:804-805  _decision_homes: Homes is rebuilt only when historical grew; an incremental read
                          that adds only defaults reuses the built object.
 8. resources.py:806-810  _decision_homes: a cache write stores key, defaults, historical and homes, and
                          the caller gets a copy of defaults.
 9. resources.py:814-824  homes: the live registered Account home_refs are the registered list; a broken
                          adapter is skipped; registry None with callers only still works.
10. resources.py:825-828  homes: historical patterns and norms are merged into the new Homes, and a live
                          default replaces a decision default only when that default has no home_ref.

The closest existing tests are tests/v1/unit/test_gaps_core_application_queries.py and
tests/v1/unit/test_gaps_infra_db_connection.py (homes_cache), and tests/v1/integration/test_t144_cut_and_consumption.py
(homes through the real database). Those do not call `_decision_homes` with a scripted connection, so the
cache key, the rowid reuse and the copy rules are not pinned by them.

Seams: FakeConn scripts the three SQL shapes the function issues and records every statement; `rows` is
replaced by a FakeRows; `archeus.core.homes.Homes` is replaced by a recording fake (the function imports it
inside its body, so the module attribute is patched). No database, no filesystem, no environment value.
"""

from types import SimpleNamespace

from archeus.core import homes as homes_mod
from archeus.core.application import resources as R


class Cursor:
    def __init__(self, rows_):
        self._rows = list(rows_)

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)

    def __iter__(self):
        return iter(self._rows)


class FakeConn:
    def __init__(self, decisions=()):
        self.decisions = list(decisions)
        self.selects = []
        self.homes_cache = {}

    def execute(self, sql, params=()):
        self.selects.append(sql)
        if sql.startswith('SELECT rowid, id'):
            if not self.decisions:
                return Cursor([])
            rowid, rid, _ = self.decisions[-1]
            return Cursor([(rowid, rid)])
        if sql.startswith('SELECT 1 FROM route_decisions WHERE rowid'):
            rowid, rid = params
            return Cursor([(1,)] if any(r == rowid and i == rid for r, i, _ in self.decisions)
                          else [])
        if sql.startswith('SELECT * FROM route_decisions WHERE rowid >'):
            after = params[0]
            return Cursor([d for d in self.decisions if d[0] > after])
        raise AssertionError('unexpected statement: %s' % sql)


class FakeRows:
    def __init__(self, accounts=(), calls=None):
        self.accounts = list(accounts)
        self.calls = [] if calls is None else calls

    def where(self, conn, cls, **filters):
        self.calls.append(('where', cls.__name__))
        if cls.__name__ == 'RouteDecision':
            return [SimpleNamespace(entity=d[2]) for d in conn.decisions]
        return [SimpleNamespace(entity=a) for a in self.accounts]

    def decode(self, cls, raw):
        self.calls.append(('decode', cls.__name__))
        return SimpleNamespace(entity=raw[2])


class FakeHomes:
    made = []

    def __init__(self, registered_homes=(), default_accounts=(), shorts=None, *, platform=None,
                 path_flavour=None):
        self.registered = list(registered_homes)
        self.defaults = list(default_accounts)
        self.shorts = shorts
        self.platform = platform
        self.patterns = [('p', h) for h in self.registered]
        self.norms = {('n', h) for h in self.registered}
        FakeHomes.made.append(self)


def decision(rowid, rid, accounts):
    entity = SimpleNamespace(input_snapshot={'accounts': list(accounts)})
    return (rowid, rid, entity)


def acct(harness, ref, registered=False, home_ref=None):
    return {'harness': harness, 'ref': ref, 'registered': registered, 'home_ref': home_ref}


def setup(monkeypatch, accounts=(), calls=None):
    FakeHomes.made = []
    monkeypatch.setattr(homes_mod, 'Homes', FakeHomes)
    monkeypatch.setattr(R, 'rows', FakeRows(accounts, calls))


def test_a_cache_hit_returns_the_cached_copy_with_no_full_read(monkeypatch):
    calls = []
    setup(monkeypatch, calls=calls)
    conn = FakeConn([decision(1, 'd1', [acct('h', 'a', registered=True, home_ref='R1')])])
    first_defaults, first_built = R._decision_homes(conn)
    conn.selects.clear()
    calls.clear()
    second_defaults, second_built = R._decision_homes(conn)
    assert conn.selects == ['SELECT rowid, id FROM route_decisions ORDER BY rowid DESC LIMIT 1']
    assert calls == []
    assert second_built is first_built
    assert second_defaults == first_defaults and second_defaults is not first_defaults


def test_a_reused_rowid_with_another_id_forces_a_full_reread_and_drops_the_vanished_row(monkeypatch):
    calls = []
    setup(monkeypatch, calls=calls)
    conn = FakeConn([decision(1, 'd1', [acct('h', 'a-keep', home_ref='K')]),
                     decision(2, 'd2', [acct('h', 'a-gone', home_ref='G')])])
    R._decision_homes(conn)
    conn.decisions = [decision(1, 'd1', [acct('h', 'a-keep', home_ref='K')]),
                      decision(2, 'dX', [acct('h', 'a-new', home_ref='N')])]
    conn.selects.clear()
    calls.clear()
    defaults, _ = R._decision_homes(conn)
    assert not any('rowid >' in s for s in conn.selects)
    assert ('where', 'RouteDecision') in calls
    assert set(defaults) == {'a-keep', 'a-new'}


def test_an_incremental_read_takes_only_the_rows_after_the_cached_rowid_and_copies_the_cache(
        monkeypatch):
    calls = []
    setup(monkeypatch, calls=calls)
    conn = FakeConn([decision(1, 'd1', [acct('h', 'a1', home_ref='H1')])])
    first_defaults, _ = R._decision_homes(conn)
    conn.decisions += [decision(2, 'd2', [acct('h', 'a2', home_ref='H2')]),
                       decision(3, 'd3', [acct('h', 'a3')])]
    conn.selects.clear()
    calls.clear()
    second_defaults, _ = R._decision_homes(conn)
    assert ('where', 'RouteDecision') not in calls
    assert set(second_defaults) == {'a1', 'a2', 'a3'}
    assert set(first_defaults) == {'a1'}
    second_defaults['a1'] = ('x', 'a1', 'mutated')
    assert conn.homes_cache['decisions']['defaults']['a1'] == ('h', 'a1', 'H1')


def test_a_registered_snapshot_account_records_a_str_home_ref_and_ignores_other_values(monkeypatch):
    setup(monkeypatch)
    conn = FakeConn([decision(1, 'd1', [acct('h', None, registered=True, home_ref='R1'),
                                        acct('h', None, registered=True, home_ref=5),
                                        acct('h', None, registered=True, home_ref=None)])])
    _, built = R._decision_homes(conn)
    assert FakeHomes.made[-1].registered == ['R1']
    assert built is FakeHomes.made[-1]


def test_a_later_unregistered_default_with_a_home_ref_replaces_one_without_and_keeps_one_with(
        monkeypatch):
    setup(monkeypatch)
    conn = FakeConn([
        decision(1, 'd1', [acct('h', 'acct', home_ref=None)]),
        decision(2, 'd2', [acct('h', 'acct', home_ref='HOME-A')]),
        decision(3, 'd3', [acct('h', 'acct', home_ref='HOME-B')]),
    ])
    defaults, _ = R._decision_homes(conn)
    assert defaults == {'acct': ('h', 'acct', 'HOME-A')}


def test_an_unregistered_account_without_a_ref_is_ignored_entirely(monkeypatch):
    setup(monkeypatch)
    conn = FakeConn([decision(1, 'd1', [acct('h', None, home_ref='X'),
                                        acct('h', '', registered=False, home_ref='Y')])])
    defaults, _ = R._decision_homes(conn)
    assert defaults == {}
    assert FakeHomes.made[-1].registered == []


def test_homes_is_rebuilt_only_when_historical_grows(monkeypatch):
    setup(monkeypatch)
    conn = FakeConn([decision(1, 'd1', [acct('h', None, registered=True, home_ref='R1')])])
    _, built1 = R._decision_homes(conn)
    conn.decisions.append(decision(2, 'd2', [acct('h', 'plain', home_ref='PLAIN')]))
    _, built2 = R._decision_homes(conn)
    assert built2 is built1 and len(FakeHomes.made) == 1
    conn.decisions.append(decision(3, 'd3', [acct('h', None, registered=True, home_ref='R2')]))
    _, built3 = R._decision_homes(conn)
    assert built3 is not built1 and len(FakeHomes.made) == 2
    assert FakeHomes.made[-1].registered == ['R1', 'R2']


def test_a_cache_write_stores_the_four_parts_and_the_caller_gets_a_copy(monkeypatch):
    setup(monkeypatch)
    conn = FakeConn([decision(1, 'd1', [acct('h', 'a1', home_ref='H1')])])
    returned, built = R._decision_homes(conn)
    stored = conn.homes_cache['decisions']
    assert stored['key'] == (1, 'd1')
    assert stored['defaults'] == {'a1': ('h', 'a1', 'H1')}
    assert stored['historical'] == {}
    assert stored['homes'] is built
    assert returned is not stored['defaults']
    returned['a1'] = None
    assert stored['defaults'] == {'a1': ('h', 'a1', 'H1')}


def test_homes_uses_the_live_account_refs_skips_a_broken_adapter_and_takes_callers_alone(monkeypatch):
    accounts = [SimpleNamespace(home_ref='LIVE-1'), SimpleNamespace(home_ref='LIVE-2')]
    setup(monkeypatch, accounts)

    class Adapter:
        def __init__(self, id_, ref=None, broken=False):
            self.id, self._ref, self._broken = id_, ref, broken

        def default_account(self):
            if self._broken:
                raise RuntimeError('adapter is down')
            return SimpleNamespace(account_id=self._ref, home_ref='CALL-' + self._ref)

    class Registry:
        def __init__(self, items):
            self.items = items

        def ids(self):
            return list(self.items)

        def get(self, i):
            return self.items[i]

    registry = Registry({'bad': Adapter('bad', 'x', broken=True), 'good': Adapter('good', 'g1')})
    out = R.homes(FakeConn(), registry, [Adapter('caller', 'c1')])
    made = FakeHomes.made[-1]
    assert made.registered == ['LIVE-1', 'LIVE-2']
    assert ('good', 'g1', 'CALL-g1') in made.defaults
    assert ('caller', 'c1', 'CALL-c1') in made.defaults
    assert not any(d[0] == 'bad' for d in made.defaults)
    assert out is made

    R.homes(FakeConn(), None, [Adapter('caller', 'c2')])
    assert ('caller', 'c2', 'CALL-c2') in FakeHomes.made[-1].defaults


def test_homes_merges_historical_patterns_and_norms_and_a_live_default_replaces_only_a_homeless_one(
        monkeypatch):
    setup(monkeypatch)
    conn = FakeConn([
        decision(1, 'd1', [acct('h', None, registered=True, home_ref='HIST'),
                           acct('h', 'acct-x', home_ref=None)]),
    ])

    class Caller:
        def __init__(self, id_, ref, home):
            self.id, self._ref, self._home = id_, ref, home

        def default_account(self):
            return SimpleNamespace(account_id=self._ref, home_ref=self._home)

    R.homes(conn, None, [Caller('live1', 'acct-x', 'LIVE'), Caller('live2', 'acct-x', 'LATER')])
    made = FakeHomes.made[-1]
    assert ('live1', 'acct-x', 'LIVE') in made.defaults
    assert ('live2', 'acct-x', 'LATER') not in made.defaults
    assert ('p', 'HIST') in made.patterns
    assert ('n', 'HIST') in made.norms

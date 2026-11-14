"""T-757: the highest-risk uncovered branches of `archeus/infra/db/rows.py`, as tests.

Fail-closed and denial paths first: `where` refuses a filter key that is not a
column and hands no SQL to the connection, an entity with no declared table is
refused before the connection is touched at all, `encode` refuses a field that
collides with the row metadata, a field is stored exactly once, `decode` ignores
row columns that are not entity fields, a promoted column wins over a stale copy
in the body (the body can never forge the version), and a row whose body is
corrupt, whose required field is nowhere or whose metadata column is gone fails
instead of decoding to defaults. Then the boundary values: both sides of the
`if c in data` guard in `encode` (the shape a migration racing a write produces),
the promotion a migration performs with no code change, the placeholder/value
pairing and the `ORDER BY rowid` of `where`, and the byte stability of the body
JSON. Then the error paths around the database: a database whose migrations never
ran, a row written by a command that rolled back, and a reader beside two writer
threads. The one case the codec gets wrong today — a promoted column that is NULL while the
body still carries the value — is a strict xfail (`test_g10`), reported, not worked around.

The closest existing tests of the module are tests/v1/integration/test_db_schema.py
(the structural asserts over TABLES, META and `columns`) and
tests/v1/integration/test_writer.py; the seed shape and the `db` fixture are copied
from tests/v1/unit/test_gaps_core_metrics.py, because tests/v1/unit has no conftest.
The only OS these tests touch is database files under `tmp_path`: the `db` fixture opens one
with `Database.open()` under the home `tests/v1/conftest.py` sets, and the codec fixture
opens a plain one through `connection.connect` and `migrate.migrate` exactly as
tests/v1/integration/test_db_schema.py opens one. The only threads, beyond the writer thread
`Database.open()` starts and `close()` stops, are the two this file starts and joins. No
network, no real process, no sleep, nothing written outside `tmp_path`.
"""

import dataclasses
import json
import sqlite3
import threading

import pytest

from archeus.core.application import commands
from archeus.core.domain import entities, ids
from archeus.core.domain.values import Ref
from archeus.infra.db import Database, connection, migrate, rows

T = '2026-10-30T10:00:00.000Z'
#: `Mission.id` and `Mission.state` are validated (entities.py:92), so the ids these
#: tests hand back on a row must be real ids and the states real mission states.
SEED_ID = ids.new_id('mission')
OTHER_A = ids.new_id('mission')
OTHER_B = ids.new_id('mission')
ACTOR_ID = 'prn_00000000000000000000000000'
#: the row metadata as the database holds it: `decode` reads these by name (rows.py:100)
META_ROW = {'version': 3, 'created_at': T, 'updated_at': T,
            'created_by': ACTOR_ID, 'updated_by': ACTOR_ID}
#: the promoted columns of the real `missions` table (0001_init.sql), META and body aside
MISSION_COLUMNS = ('id', 'workspace_id', 'project_id', 'state')


# ── seeds and seams ──────────────────────────────────────────────────────────

def _mission(mid=None, **kw):
    return entities.Mission(id=mid or ids.new_id('mission'),
                            workspace_id=ids.GLOBAL_WORKSPACE,
                            title='M', objective='o', **kw)


def _seed(conn, name, cols):
    """A hand-made row: a table whose columns are exactly `cols` (in that order),
    holding one record, read back as the `sqlite3.Row` the module really gets."""
    conn.execute('DROP TABLE IF EXISTS %s' % name)
    conn.execute('CREATE TABLE %s (%s)' % (name, ', '.join(cols)))
    conn.execute('INSERT INTO %s (%s) VALUES (%s)'
                 % (name, ', '.join(cols), ', '.join('?' * len(cols))), tuple(cols.values()))
    return conn.execute('SELECT * FROM %s' % name).fetchone()


def _mission_row(conn, *, body='{}', **cols):
    """One `missions` row: `cols` are its promoted columns, `body` its JSON column,
    the metadata filled in with META_ROW."""
    return _seed(conn, 'missions', dict(cols, body=body, **META_ROW))


class _Cursor:
    def __init__(self, records):
        self._records = list(records)

    def fetchone(self):
        return self._records[0] if self._records else None

    def __iter__(self):
        return iter(self._records)


class FakeConn:
    """A connection stand-in for the codec calls that take one. It records every
    `execute` (SQL and parameters), answers `PRAGMA table_info` from `cols` and
    answers a SELECT from `records` whatever its WHERE: what these tests assert is
    what the codec handed over and what it made of what came back, never SQL
    matching, which is SQLite's."""

    def __init__(self, cols=(), records=()):
        self.cols, self.records, self.calls = tuple(cols), list(records), []

    def execute(self, sql, params=()):
        self.calls.append((sql, tuple(params)))
        if sql.lstrip().upper().startswith('PRAGMA'):
            return [(None, c, None) for c in self.cols]        # r[1] is the column name
        return _Cursor(self.records)

    def selects(self):
        return [c for c in self.calls if c[0].lstrip().upper().startswith('SELECT')]


class _Dicts:
    """The bit of `Entity` that `encode` reads: a plain dict of the fields."""

    def to_dict(self):
        return dataclasses.asdict(self)


class _Bag:
    """A codec-shaped object whose `to_dict` keeps the order it was handed: what an
    entity looks like to `encode` when its field dict came from a parsed payload
    instead of from the class (the codec's contract is any `to_dict`)."""

    def __init__(self, data):
        self._data = dict(data)

    def to_dict(self):
        return dict(self._data)


def _entity_carrying(field):
    """An entity with a field of its own called `field`, to aim the clash guard at
    a name the schema uses for its own row metadata."""
    cls = dataclasses.make_dataclass('Clashing', [('id', str), ('title', str),
                                                   (field, int)],
                                     bases=(_Dicts,), frozen=True)
    return cls(id=SEED_ID, title='M', **{field: 7})


class _NotPersisted:
    """An entity of a phase whose row `TABLES` does not declare (rows.py:75-78)."""


@pytest.fixture
def db(archeus_home):                     # as in tests/v1/unit/test_gaps_core_metrics.py
    d = Database.open()
    yield d
    d.close()


@pytest.fixture
def raw(archeus_home, tmp_path):
    """A plain write connection to its own, unmigrated database file, made by the
    seam tests/v1/integration/test_db_schema.py uses, so the hand-made tables these
    tests decode are made over a connection made the way every connection is made."""
    conn = connection.connect(str(tmp_path / 'rows-codec.db'))
    yield conn
    conn.close()


# ── fail-closed and denial paths ─────────────────────────────────────────────

@pytest.mark.parametrize('key', ['state = ? OR 1', 'id) OR (1', '1 = 1', 'body = ?', 'state; --'])
def test_g1_where_refuses_a_filter_that_is_not_a_column_and_hands_over_no_sql(key):
    """rows.py:113-115. `where` interpolates its keys into the SQL TEXT (rows.py:118),
    so this guard is the only thing between a caller's keyword and an injected
    predicate; it must refuse before any SELECT reaches the connection."""
    conn = FakeConn(cols=MISSION_COLUMNS, records=[])
    with pytest.raises(LookupError) as got:
        rows.where(conn, entities.Mission, **{key: 'anything'})
    assert 'missions has no column' in str(got.value) and key in str(got.value)
    assert conn.selects() == [], 'a SELECT ran although the filter was refused'
    assert not [c for c in conn.calls if 'anything' in str(c)], 'the value reached the SQL'


def test_g2_an_entity_with_no_declared_table_is_refused_before_the_connection_is_touched():
    """rows.py:75-78. An entity the current schema does not persist is a refusal,
    not a query: `TABLES` is the one declaration of what is persisted, and a
    missing row there must not become a `SELECT` against a guessed table name —
    nor a `KeyError`, which would leak the registry's own internals to the caller."""
    conn = FakeConn()
    for call in (lambda: rows.table(_NotPersisted),
                 lambda: rows.get(conn, _NotPersisted, SEED_ID),
                 lambda: rows.where(conn, _NotPersisted, state='CREATED')):
        with pytest.raises(LookupError) as got:
            call()
        assert type(got.value) is LookupError        # not KeyError, not OperationalError
        assert str(got.value) == '_NotPersisted has no table in the current schema'
        assert got.value.__suppress_context__ is True        # `raise ... from None`
    assert conn.calls == [], 'the refusal ran SQL'


def test_g2b_only_the_exact_class_tables_declares_has_a_table():
    """rows.py:76: the lookup is by class, so a subclass of a persisted entity has
    no table either — it must not silently share its parent's rows."""
    class _SubMission(entities.Mission):
        pass

    assert rows.table(entities.Mission) == 'missions'
    with pytest.raises(LookupError) as got:
        rows.table(_SubMission)
    assert '_SubMission has no table in the current schema' == str(got.value)


@pytest.mark.parametrize('field', rows.META + ('body',))
def test_g3_encode_refuses_a_field_that_collides_with_the_row_metadata(field):
    """rows.py:88-91. A field named `version`, `created_at`, `created_by` … or
    `body` would be written twice, once by the entity and once by the row: the
    optimistic-concurrency version, the timestamps and the audit pair are the
    writer's, and the body would carry a second, disagreeable copy of each."""
    with pytest.raises(ValueError) as got:
        rows.encode(_entity_carrying(field), ('id', 'state'))
    assert 'Clashing fields collide with row metadata' in str(got.value)
    assert field in str(got.value)
    # the clash is the reason it refused: the same shape with a field outside META encodes
    promoted, body = rows.encode(_entity_carrying('round_seq'), ('id', 'state'))
    assert promoted == {'id': SEED_ID} and json.loads(body) == {'title': 'M', 'round_seq': 7}


def test_g4_a_field_is_stored_exactly_once_in_its_column_or_in_the_body_never_both():
    """rows.py:92-93: `data.pop`, not a read. A promoted field that also rode in the
    body is the second copy the module's whole design forbids ("so the two cannot
    disagree"), and a field that reached neither is a field the next read loses."""
    m = _mission(priority=3, state='EXECUTING')
    promoted, body = rows.encode(m, MISSION_COLUMNS)
    got = json.loads(body)
    assert promoted == {'id': m.id, 'workspace_id': m.workspace_id,
                        'project_id': None, 'state': 'EXECUTING'}
    assert not set(got) & set(promoted), 'a promoted field also rode in the body'
    assert set(got) | set(promoted) == {f.name for f in dataclasses.fields(entities.Mission)}
    assert got['priority'] == 3 and got['title'] == 'M'


def test_g5_decode_ignores_row_columns_that_are_not_entity_fields(raw):
    """rows.py:99 `if k in names`. The row carries `id` and whatever column a
    migration added for infrastructure (here: a `tenant` and a consumer cursor);
    neither is a field, and `from_dict` refuses unknown fields, so without this
    filter every read of a real table would raise."""
    rec = _mission_row(raw, body=json.dumps({'title': 'M', 'objective': 'o'}),
                       id=SEED_ID, workspace_id='ws_global', state='CREATED',
                       tenant='t', consumer_cursor=0)
    row = rows.decode(entities.Mission, rec)
    assert row.entity.id == SEED_ID and row.entity.state == 'CREATED'
    assert row.entity.title == 'M' and not hasattr(row.entity, 'tenant')
    assert (row.version, row.created_by, row.updated_by) == (3, ACTOR_ID, ACTOR_ID)


def test_g6_a_promoted_column_wins_over_the_same_field_carried_by_the_body(raw):
    """rows.py:99: `data.update` of the columns runs LAST, so the column is the
    answer. The only way a promoted field is still in the body is a row written
    before the column existed, so the body copy is by definition the stale one; an
    update that merged in the other direction would resurrect dead state."""
    rec = _mission_row(raw, body=json.dumps({'title': 'M', 'objective': 'o',
                                             'state': 'COMPLETED'}),
                       id=SEED_ID, workspace_id='ws_global', state='EXECUTING')
    assert rows.decode(entities.Mission, rec).entity.state == 'EXECUTING'


def test_g6b_a_body_that_carries_row_metadata_is_refused_not_read_as_the_version(raw):
    """rows.py:99-100 with entities.py:148. The metadata is read off the row (100),
    never out of the body, and a body that names `version` or `created_by` anyway
    does not decode at all: those names are not entity fields, so the column filter
    at 99 will not merge them and `from_dict` refuses the row rather than carrying
    a second version or audit pair inside the entity. That is the read side of the
    rule `encode` enforces on the write side at rows.py:88-91: the body never gets
    a version of its own near the number the writer checks."""
    rec = _mission_row(raw, body=json.dumps({'title': 'M', 'objective': 'o',
                                             'state': 'EXECUTING', 'version': 99,
                                             'created_by': 'someone-else'}),
                       id=SEED_ID, workspace_id='ws_global', state='EXECUTING')
    with pytest.raises(ValueError) as got:
        rows.decode(entities.Mission, rec)
    assert 'unknown fields' in str(got.value)


@pytest.mark.parametrize('body', ['', 'not json', '{"title": "M"', '[', '{title: M}'])
def test_g7_a_row_whose_body_is_not_json_fails_instead_of_reading_as_empty(raw, body):
    """rows.py:98. A truncated or half-written body (the shape a partial write leaves)
    must raise: a codec that swallowed the error would read the row back as an
    entity with nothing but its promoted columns."""
    rec = _mission_row(raw, body=body, id=SEED_ID, workspace_id='ws_global',
                       state='CREATED')
    with pytest.raises(ValueError):
        rows.decode(entities.Mission, rec)


def test_g8_a_row_missing_a_required_field_never_decodes_to_defaults(raw):
    """rows.py:99 into `from_dict` (entities.py:145). `title` and `objective` are
    required fields with no column: a row that has lost them from its body must
    fail, not be filled in."""
    rec = _mission_row(raw, body='{}', id=SEED_ID, workspace_id='ws_global',
                       state='CREATED')
    with pytest.raises(TypeError):
        rows.decode(entities.Mission, rec)


@pytest.mark.parametrize('missing', rows.META + ('body',))
def test_g9_a_row_that_lost_its_metadata_or_body_column_is_refused(raw, missing):
    """rows.py:98 and 100 read `body` and every name in META by key. A row that has
    lost one of them — a restored file, a hand-edited one, a table some migration
    never finished — must not read back as version 0 with an empty body: version 0
    is what the writer would then treat as the current version."""
    cols = dict(id=SEED_ID, workspace_id='ws_global', state='CREATED',
                body=json.dumps({'title': 'M', 'objective': 'o'}), **META_ROW)
    del cols[missing]
    rec = _seed(raw, 'missions', cols)
    with pytest.raises((IndexError, KeyError)):
        rows.decode(entities.Mission, rec)


def test_g10_a_null_promoted_column_does_not_erase_the_value_the_body_carries(raw):
    """rows.py:99: the promotion of a field is decided by the table, but the rows
    written before the column existed still hold the value in `body`. Reading the
    new, NULL column as the answer loses it in silence — the one way a field can
    vanish without either copy disagreeing."""
    rec = _mission_row(raw, body=json.dumps({'title': 'M', 'objective': 'o', 'priority': 3}),
                       id=SEED_ID, workspace_id='ws_global', state='CREATED',
                       priority=None)
    assert rows.decode(entities.Mission, rec).entity.priority == 3


# ── boundary values ──────────────────────────────────────────────────────────

def test_g11_a_column_with_no_field_and_a_field_with_no_column_both_survive_encode():
    """rows.py:92 `if c in data`, both sides — the shape a migration racing a write
    produces, since the writer reads `columns()` and encodes with it a moment later.
    A column the entity has no field for must be left out of the INSERT (never a
    KeyError, never an invented value); a field the table has no column for must
    reach the body and come back."""
    m = _mission(priority=5)
    promoted, body = rows.encode(m, MISSION_COLUMNS + ('brand_new_column',))
    assert 'brand_new_column' not in promoted
    assert rows.decode(entities.Mission, dict(META_ROW, body=body, **promoted)).entity == m
    # the same field, once its column exists, is promoted instead of body-borne
    promoted2, body2 = rows.encode(m, MISSION_COLUMNS + ('priority',))
    assert promoted2['priority'] == 5 and 'priority' not in json.loads(body2)
    assert rows.decode(entities.Mission, dict(META_ROW, body=body2, **promoted2)).entity == m


def test_g12_a_migration_that_adds_a_column_promotes_the_field_with_no_code_change(raw):
    """rows.py:82: which fields are promoted is read from the table itself. Over the
    real schema, before and after an `ALTER TABLE missions ADD COLUMN priority`, the
    same entity moves its `priority` from the body to the column and back again
    without anything here changing — and the row SQLite holds keeps the field once
    and only once either way."""
    migrate.migrate(raw)
    m = _mission(priority=7, state='CREATED')

    def write():
        cols = rows.columns(raw, 'missions')
        promoted, body = rows.encode(m, cols)
        values = dict(promoted, body=body, **META_ROW)
        raw.execute('DELETE FROM missions')
        raw.execute('INSERT INTO missions (%s) VALUES (%s)'
                    % (', '.join(values), ', '.join('?' * len(values))), tuple(values.values()))
        return promoted, body

    assert 'priority' not in rows.columns(raw, 'missions')
    promoted, body = write()
    assert 'priority' not in promoted and json.loads(body)['priority'] == 7
    assert rows.get(raw, entities.Mission, m.id).entity == m

    raw.execute('ALTER TABLE missions ADD COLUMN priority INTEGER')
    assert 'priority' in rows.columns(raw, 'missions')
    promoted, body = write()
    assert promoted['priority'] == 7 and 'priority' not in json.loads(body)
    row = rows.get(raw, entities.Mission, m.id)
    assert row.entity == m and row.version == 3
    assert not set(json.loads(body)) & set(MISSION_COLUMNS)


def test_g13_where_pairs_one_placeholder_with_each_value_and_reads_oldest_first():
    """rows.py:116-119. The WHERE is built from the keys and the parameters from
    the values, in two separate comprehensions: a pairing that drifts silently
    filters one column by another's value. `ORDER BY rowid` is the 'oldest first'
    the docstring promises, and `tuple(eq.values())` must be a tuple — the empty
    filter passes () and not None."""
    conn = FakeConn(cols=MISSION_COLUMNS,
                    records=[dict(META_ROW, id=OTHER_A, workspace_id='ws_global',
                                  state='CREATED', body='{"title": "M", "objective": "o"}'),
                             dict(META_ROW, id=OTHER_B, workspace_id='ws_global',
                                  state='CREATED', body='{"title": "M", "objective": "o"}')])
    got = rows.where(conn, entities.Mission, state='CREATED', project_id=None)
    sql, params = conn.selects()[-1]
    assert sql == ('SELECT * FROM missions WHERE state = ? AND project_id = ?'
                   ' ORDER BY rowid')
    where = sql.split(' WHERE ')[1].split(' ORDER BY')[0]
    assert list(zip([c.split(' = ')[0] for c in where.split(' AND ')], params)) == \
        [('state', 'CREATED'), ('project_id', None)]
    assert sql.endswith(' ORDER BY rowid')
    assert [r.entity.id for r in got] == [OTHER_A, OTHER_B]     # what the DB returned, in order


def test_g13b_where_with_no_filter_scans_the_table_and_binds_nothing():
    """rows.py:117 `if eq:`: without a filter no WHERE is built at all and the
    parameters are the empty tuple, so an absent filter cannot read as a false one."""
    conn = FakeConn(cols=MISSION_COLUMNS,
                    records=[dict(META_ROW, id=OTHER_A, workspace_id='ws_global',
                                  state='CREATED', body='{"title": "M", "objective": "o"}')])
    assert [r.entity.id for r in rows.where(conn, entities.Mission)] == [OTHER_A]
    sql, params = conn.selects()[-1]
    assert sql == 'SELECT * FROM missions ORDER BY rowid' and params == ()


def test_g14_the_body_of_one_content_is_one_byte_string_whatever_order_the_fields_arrived_in():
    """rows.py:93 `sort_keys=True`. The body is the only copy of most of the entity,
    so one content must be one byte string: an encoding that followed the order of
    the dict it was handed would make one logical entity two byte-distinct bodies,
    and anything that compares bodies — a diff, a re-index, a test of what a write
    stored — would see a change that never happened."""
    a = _Bag({'id': SEED_ID, 'alpha': 1, 'beta': 2, 'gamma': 3})
    b = _Bag({'gamma': 3, 'beta': 2, 'alpha': 1, 'id': SEED_ID})
    assert rows.encode(a, ('id',)) == rows.encode(b, ('id',))
    assert rows.encode(a, ('id',))[1] == '{"alpha": 1, "beta": 2, "gamma": 3}'


# ── error paths around the database ──────────────────────────────────────────

def test_g15_a_database_whose_migrations_never_ran_fails_rather_than_reading_as_empty(raw):
    """rows.py:82 with rows.py:105-107 and 116-119. `PRAGMA table_info` answers
    nothing at all for a table that is not there, so an unmigrated, half-migrated
    or wrongly-restored file would otherwise answer `None` for every entity and
    `[]` for every query: the two things a caller cannot tell from an empty
    database. Every read of it must be an error."""
    assert rows.columns(raw, 'missions') == ()
    with pytest.raises(sqlite3.OperationalError, match='no such table'):
        rows.get(raw, entities.Mission, SEED_ID)
    with pytest.raises(sqlite3.OperationalError, match='no such table'):
        rows.where(raw, entities.Mission)
    with pytest.raises(LookupError):         # with no table, every filter is "not a column"
        rows.where(raw, entities.Mission, state='CREATED')


def test_g16_a_row_written_by_a_command_that_rolled_back_is_never_read_back(db):
    """The partial-write path through the transaction (rows.py:103-107 is how
    anyone finds out). `Tx.insert` writes the row on the writer thread; the command
    that raises after it must leave the codec reading nothing — and the raw COUNT is
    read beside it, so a `get` that always answered None cannot stand in for a
    rollback that never happened. The mission a command did commit is read back in
    the same test for the same reason."""
    actor = Ref('user_device', ids.new_id('principal'))
    kept = db.writer.execute(commands.create_mission,
                             {'actor': actor, 'title': 'kept', 'objective': 'o'})
    lost = ids.new_id('mission')

    def half(tx, *, entity):
        tx.insert(entity, actor=actor)
        raise ValueError('changed my mind')

    with pytest.raises(ValueError, match='changed my mind'):
        db.writer.execute(half, {'entity': _mission(lost)})
    with db.read() as r:
        assert rows.get(r, entities.Mission, kept['id']).entity.title == 'kept'
        assert rows.get(r, entities.Mission, lost) is None
        assert r.execute('SELECT COUNT(*) FROM missions').fetchone()[0] == 1


def test_g17_a_reader_beside_two_writers_sees_whole_rows_only_and_all_of_them(db):
    """rows.py:92-93 and 98-100 under concurrent writers: the codec is the one
    place the row is split and re-joined, so a lost or doubled field there shows up
    only here. Every row the loop reads while the two writers run decodes to a
    complete entity (a half row raises on the required fields), and at the end each
    stored row holds each field exactly once — its promoted columns and no copy of
    them in the body — with every mission present once, at its own version."""
    actor = Ref('user_device', ids.new_id('principal'))
    fields = {f.name for f in dataclasses.fields(entities.Mission)}
    wrote = []

    def run(part):
        for i in part:
            wrote.append(db.writer.execute(
                commands.create_mission,
                {'actor': actor, 'title': 't%d' % i, 'objective': 'o'})['id'])

    a = threading.Thread(target=run, args=(range(0, 10),))
    b = threading.Thread(target=run, args=(range(10, 20),))
    a.start()
    b.start()
    read = []
    while a.is_alive() or b.is_alive():
        with db.read() as r:
            read.extend(rows.where(r, entities.Mission))
    a.join()
    b.join()
    assert all(r.entity.title and r.entity.objective for r in read)   # whole rows only
    with db.read() as r:
        cols = set(rows.columns(r, 'missions')) & fields
        seen = list(r.execute('SELECT * FROM missions ORDER BY rowid'))
        assert sorted(x['id'] for x in seen) == sorted(wrote)
        for rec in seen:
            assert not set(json.loads(rec['body'])) & cols, 'a promoted column was body too'
            assert rows.get(r, entities.Mission, rec['id']).entity.title.startswith('t')
            assert rec['version'] == 1 and rec['created_by'] == actor.id

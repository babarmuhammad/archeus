"""T-1389: the highest-risk uncovered branches of `archeus/infra/db/writer.py` lines 105-214
(`_refuse_frozen`, `_principal`, `Tx.__init__`, `Tx.insert_token`, `Tx.revoke_tokens`,
`Tx.get`/`where`, `Tx.insert`, `Tx.update`), as tests.

Selected branches, denial and fail-closed first:
- `_refuse_frozen`: a frozen field in `update` raises ValueError naming the sorted frozen
  fields, and no UPDATE is issued (writer.py `_refuse_frozen`, the `if frozen` raise).
- `update` order: the id/state refusal runs before the frozen refusal (a state field plus a
  frozen field reports the id/state message), and a missing id raises NotFound only after the
  actor check (a bad actor on a missing id reports the actor, not NotFound).
- `update` with a non-principal actor raises before any read: no `get` call.
- `update` with `expected_version` different from the row's version raises VersionConflict
  carrying the current version, before any UPDATE.
- `update(bump=False)` binds step 0 to the version and returns the Row at the unchanged version.
- `insert_token` writes only the given token_hash, scopes as a JSON list, expires_at None
  passed through, and has no token parameter.
- `revoke_tokens` binds the revocation time and principal, returns the rowcount, and a second
  call on the same principal returns the fake rowcount of 0.
- `Tx.insert`: version 1, created_by and updated_by equal the actor, mutated True; a
  non-principal actor is refused before INSERT.

Not selected: the `VersionConflict(entity_id, row.version, None)` report on rowcount != 1
(writer.py:210). tests/v1/unit/test_gaps_infra_db_writer.py test_w1 and test_w2 pin the None
on purpose and the source comment says it is unreachable with one writer, so that premise is
wrong and no strict xfail is kept. The rowcount-0 UPDATE conflict is asserted by test_w2 in
that file and is not repeated here.

Seam: a fake connection that records (sql, params) and returns a scripted rowcount, and
monkeypatched `rows.get`, `rows.table` and `rows.columns` on the writer's rows module. The
entity encoding and the Row type are the real ones. No database file, no OS call, no network.
"""

import dataclasses
import inspect

import pytest

from archeus.core.domain import ids
from archeus.core.domain.values import Ref
from archeus.infra.db import rows, writer


@dataclasses.dataclass(frozen=True)
class Thing:
    id: str
    title: str = ''
    code: str = ''
    locked: str = ''

    @classmethod
    def frozen_fields(cls):
        return {'code', 'locked'}

    @classmethod
    def state_fields(cls):
        return {'state'}

    def to_dict(self):
        return dataclasses.asdict(self)


class FakeCursor:
    def __init__(self, rowcount, lastrowid=None):
        self.rowcount = rowcount
        self.lastrowid = lastrowid


class FakeConn:
    def __init__(self, rowcount=1):
        self.rowcount = rowcount
        self.log = []

    def execute(self, sql, params=()):
        self.log.append((sql, tuple(params)))
        return FakeCursor(self.rowcount)


@pytest.fixture
def actor():
    return Ref('user_device', ids.new_id('principal'))


@pytest.fixture
def seam(monkeypatch):
    s = {'gets': [], 'row': None}

    def get(conn, cls, entity_id):
        s['gets'].append(entity_id)
        return s['row']

    monkeypatch.setattr(rows, 'get', get)
    monkeypatch.setattr(rows, 'table', lambda cls: 'things')
    monkeypatch.setattr(rows, 'columns', lambda conn, name: ('id', 'title', 'code', 'locked'))
    return s


def _row(entity, version=3):
    return rows.Row(entity, version, '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z',
                    ids.new_id('principal'), ids.new_id('principal'))


def _tx(conn):
    return writer.Tx(conn)


def test_a_frozen_field_is_refused_by_name_and_writes_nothing(seam, actor):
    # writer.py _refuse_frozen: `set(fields) & cls.frozen_fields()` raises naming the sorted
    # names; without the raise the UPDATE would overwrite a field frozen at insert
    seam['row'] = _row(Thing(id='t1', title='a'))
    conn = FakeConn()
    with pytest.raises(ValueError, match=r"Thing fields are frozen once recorded: \['code', 'locked'\]"):
        _tx(conn).update(Thing, 't1', {'locked': 'x', 'code': 'y'}, actor=actor)
    assert conn.log == []


def test_the_id_and_state_refusal_runs_before_the_frozen_one(seam, actor):
    # writer.py update: `forbidden` is checked before `_refuse_frozen`, so a state field
    # beside a frozen one reports the id/state message, not the frozen one
    seam['row'] = _row(Thing(id='t1', title='a'))
    conn = FakeConn()
    with pytest.raises(ValueError, match='update may not set the id or the state'):
        _tx(conn).update(Thing, 't1', {'state': 'DONE', 'code': 'y'}, actor=actor)
    assert conn.log == []


def test_a_bad_actor_on_a_missing_id_is_refused_before_the_read(seam):
    # writer.py update: `_principal` is the first statement, so a non-principal never
    # reaches `get`; and with a principal, a missing id raises NotFound after the check
    conn = FakeConn()
    bad = Ref('user_device', ids.new_id('mission'))
    with pytest.raises(ValueError, match='updated_by must be a principal id'):
        _tx(conn).update(Thing, 't9', {'title': 'x'}, actor=bad)
    assert seam['gets'] == [] and conn.log == []


def test_a_missing_row_raises_not_found_naming_the_id(seam, actor):
    # writer.py update: `if row is None: raise NotFound(entity_id)`; no UPDATE follows
    seam['row'] = None
    conn = FakeConn()
    with pytest.raises(writer.NotFound) as err:
        _tx(conn).update(Thing, 't9', {'title': 'x'}, actor=actor)
    assert err.value.args == ('t9',)
    assert conn.log == []


def test_an_expected_version_that_is_stale_conflicts_before_any_update(seam, actor):
    # writer.py update: `expected_version != row.version` raises VersionConflict with the
    # current version (3) before the UPDATE is built
    seam['row'] = _row(Thing(id='t1', title='a'), version=3)
    conn = FakeConn()
    with pytest.raises(writer.VersionConflict) as err:
        _tx(conn).update(Thing, 't1', {'title': 'x'}, actor=actor, expected_version=2)
    assert (err.value.entity_id, err.value.expected, err.value.current) == ('t1', 2, 3)
    assert conn.log == []


def test_bump_false_keeps_the_version_in_the_statement_and_the_row(seam, actor):
    # writer.py update: `step = 1 if bump else 0` binds `version = version + ?` to 0, and the
    # returned Row carries row.version + step, so the version is unchanged
    seam['row'] = _row(Thing(id='t1', title='a'), version=3)
    conn = FakeConn(rowcount=1)
    tx = _tx(conn)
    got = tx.update(Thing, 't1', {'title': 'new'}, actor=actor, bump=False)
    sql, params = conn.log[-1]
    assert 'version = version + ?' in sql
    assert params[-3:] == (0, 't1', 3)
    assert got.version == 3 and got.entity.title == 'new'
    assert tx.mutated is True


def test_insert_token_writes_only_the_given_hash_with_scopes_as_a_json_list(actor):
    # writer.py insert_token: only token_hash reaches the row, scopes are a JSON list, and
    # expires_at None is bound as None; the signature has no token parameter at all
    conn = FakeConn()
    tx = _tx(conn)
    tx.insert_token(token_hash='h' * 64, kind='device', principal_id='p1',
                    scopes=('read', 'write'), actor=actor)
    sql, params = conn.log[-1]
    assert sql.startswith('INSERT INTO tokens')
    assert params == ('h' * 64, 'device', 'p1', '["read", "write"]', tx.now, actor.id, None)
    assert 'token' not in inspect.signature(writer.Tx.insert_token).parameters


def test_revoke_tokens_binds_the_time_and_principal_and_returns_the_rowcount(actor):
    # writer.py revoke_tokens: the WHERE clause only touches live rows and the return is
    # the rowcount; a second revoke on the same principal matches nothing and returns 0
    conn = FakeConn(rowcount=2)
    tx = _tx(conn)
    assert tx.revoke_tokens('p1') == 2
    sql, params = conn.log[-1]
    assert 'revoked_at IS NULL' in sql and params == (tx.now, 'p1')
    conn.rowcount = 0
    assert tx.revoke_tokens('p1') == 0


def test_insert_writes_version_one_stamped_with_the_actor(seam, actor):
    # writer.py Tx.insert: version 1, created_by and updated_by are the actor, mutated is True
    conn = FakeConn()
    tx = _tx(conn)
    got = tx.insert(Thing(id='t2', title='x', code='c'), actor=actor)
    sql, params = conn.log[-1]
    cols = sql.split('(')[1].split(')')[0].split(', ')
    values = dict(zip(cols, params))
    assert values['version'] == 1
    assert (values['created_by'], values['updated_by']) == (actor.id, actor.id)
    assert (got.version, got.created_by, got.updated_by) == (1, actor.id, actor.id)
    assert tx.mutated is True


def test_insert_refuses_a_non_principal_actor_before_the_statement(seam):
    # writer.py Tx.insert: `_principal(actor, 'created_by')` runs before the INSERT
    conn = FakeConn()
    tx = _tx(conn)
    with pytest.raises(ValueError, match='created_by must be a principal id'):
        tx.insert(Thing(id='t2', title='x'), actor=Ref('user_device', ids.new_id('mission')))
    assert conn.log == [] and tx.mutated is False

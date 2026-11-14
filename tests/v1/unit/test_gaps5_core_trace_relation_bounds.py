import json
import sqlite3
from pathlib import Path

import pytest

from archeus.api import schemas
from archeus.core.application import trace
from archeus.core.domain import entities, ids
from archeus.core.domain.events import new_event
from archeus.core.domain.values import Ref
from archeus.infra.db import Database

_RELATIONS_DDL = '0005_knowledge.sql'

LIVE = '{"valid_until": null}'
NO_KEY = '{}'
EXPIRED = '{"valid_until": "2020-01-01T00:00:00Z"}'

MALFORMED = ('', '   ', 'not json', '[', '{', '{"valid_until": null', '"unterminated',
             'null,', '{"a": }', '0x1', ']', '{"valid_until" 1}')

NON_OBJECT = ('[]', 'null', '0', 'true', '"a lesson"', '[{"valid_until": null}]')

MISSION = 'msn_0000000000000000000000000A'
OTHER = 'msn_0000000000000000000000000B'

_POISON_ID = 'kno_zzzzzzzzzzzzzzzzzzzzzzzz'
_POISON = 'past-the-cap'


def _ids(n):
    return sorted(ids.new_id('knowledge_item') for _ in range(n))


class _Poison:
    def __init__(self, at):
        self.at = at

    def __getitem__(self, key):
        raise AssertionError('trace.py:73: the cursor was pulled for row %d, past the '
                             'cap: the break did not fire' % self.at)


class _Supply:
    def __init__(self, pairs):
        self.rows = [{'src_id': s, 'body': _Poison(n) if b is _POISON else b}
                     for n, (s, b) in enumerate(sorted(pairs, key=lambda p: p[0]))]
        self.pulled = 0

    def __iter__(self):
        return self

    def __next__(self):
        if self.pulled >= len(self.rows):
            raise StopIteration
        row = self.rows[self.pulled]
        self.pulled += 1
        return row


class _FakeDB:
    def __init__(self, pairs):
        self.supply = _Supply(pairs)
        self.calls = []

    def execute(self, sql, params):
        self.calls.append((sql, tuple(params)))
        if len(self.calls) > 1:
            raise AssertionError('trace.py:59: lessons issued a second query for one read')
        return self.supply


def _lessons(pairs, mission=MISSION):
    db = _FakeDB(pairs)
    found, more = trace.lessons(db, mission)
    return found, more, db


class _Columns:
    def __init__(self, row):
        self._row = row

    def __getitem__(self, key):
        if key not in ('src_id', 'body'):
            raise AssertionError('trace.py:59-62: lessons read the column %r; the read is '
                                 'owed src_id and body only' % key)
        return self._row[key]


class _Recorder:
    def __init__(self, conn):
        self.conn = conn
        self.calls = []
        self.read = []

    def execute(self, sql, params):
        cur = self.conn.execute(sql, params)
        self.calls.append((sql, tuple(params)))
        rows = [_Columns(r) for r in cur.fetchall()]
        self.read.append(len(rows))
        return iter(rows)


class _Sql:
    def __init__(self):
        ddl = (Path(__file__).parents[3] / 'archeus' / 'infra' / 'db' / 'migrations'
               / _RELATIONS_DDL)
        self.conn = sqlite3.connect(':memory:')
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(ddl.read_text(encoding='utf-8'))
        self.sealed = False
        self.inserted = []

    def add(self, mission, src_id, body=LIVE, *, rel='learned_from',
            src_kind='knowledge_item', dst_kind='mission'):
        if self.sealed:
            raise AssertionError('the rig was sealed for reading before this insert')
        rid = 'rel_%06d' % (len(self.inserted) + 1)
        self.conn.execute(
            'INSERT INTO relations (id, src_kind, src_id, rel, dst_kind, dst_id, '
            'version, created_at, updated_at, created_by, updated_by, body) '
            'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
            (rid, src_kind, src_id, rel, dst_kind, mission, 1,
             '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z', 'prn_rig', 'prn_rig', body))
        self.inserted.append((rid, src_id, body))
        return self

    def seal(self):
        self.conn.execute('PRAGMA query_only = ON')
        self.sealed = True
        return self

    def count(self):
        return self.conn.execute('SELECT COUNT(*) FROM relations').fetchone()[0]

    def close(self):
        self.conn.close()


class _Registry:
    def ids(self):
        return []

    def get(self, hid):
        raise AssertionError('the trace asked the registry for %r' % hid)


@pytest.fixture
def db_world():
    db = Database.open()
    try:
        yield db, Ref('user_device', ids.new_id('principal'))
    finally:
        db.close()


def _witness(who):
    return new_event('principal.created', Ref('principal', ids.new_id('principal')), who,
                     payload={})


def _mission(db, who):
    mid = ids.new_id('mission')

    def run(tx, **_):
        tx.insert(entities.Mission(id=mid, workspace_id=ids.GLOBAL_WORKSPACE, title='M',
                                   objective='o', state='EXECUTING'), actor=who)
        tx.append(_witness(who))
    db.writer.execute(run, {})
    return mid


def _seed(db, who, mid, rows):
    def run(tx, **_):
        for src, body, extra in rows:
            rid = ids.new_id('relation')
            tx.insert(entities.Relation(id=rid, src_kind='knowledge_item', src_id=src,
                                        rel='learned_from', dst_kind='mission',
                                        dst_id=mid, **extra), actor=who)
            if body is not None:
                tx.execute('UPDATE relations SET body = ? WHERE id = ?', (body, rid))
        tx.append(_witness(who))
    db.writer.execute(run, {})
    return [r[0] for r in rows]


def test_a_falsy_but_present_expiry_is_still_an_expiry():
    d0, d1, d2, d3, d4, dead, live1, live2, marker = _ids(9)
    pairs = [(d0, '{"valid_until": 0}'), (d1, '{"valid_until": false}'),
             (d2, '{"valid_until": ""}'), (d3, '{"valid_until": []}'),
             (d4, '{"valid_until": {}}'), (dead, EXPIRED),
             (live1, NO_KEY), (live2, LIVE),
             (marker, '{"valid_until": 0}'), (marker, LIVE)]
    found, more, db = _lessons(pairs)
    assert found == sorted(set(found))
    assert live1 in found and live2 in found and marker in found
    assert not any(d in found for d in (d0, d1, d2, d3, d4, dead))
    assert more is False
    assert db.supply.pulled == len(pairs)


def test_the_query_itself_is_the_filter_so_foreign_rows_never_reach_python():
    rig = _Sql()
    keep = _ids(3)
    written = [keep[2], keep[0], keep[0], keep[1]]
    rig.add(MISSION, written[0], LIVE)
    rig.add(MISSION, written[1], EXPIRED)
    rig.add(MISSION, written[2], LIVE)
    rig.add(MISSION, written[3], LIVE)
    strangers = [dict(rel='relates_to'), dict(src_kind='meeting'), dict(dst_kind='project')]
    for kw in strangers:
        rig.add(MISSION, _ids(1)[0], LIVE, **kw)
    rig.add(OTHER, _ids(1)[0], LIVE)
    assert rig.count() == 8 and written != keep
    rig.seal()
    rec = _Recorder(rig.conn)
    try:
        assert trace.lessons(rec, MISSION) == (keep, False)
        assert rec.read == [4]
        sql, params = rec.calls[0]
        assert params == (MISSION,) and MISSION not in sql
    finally:
        rig.close()


def test_the_mission_filter_is_one_bound_parameter_and_only_two_columns_are_read():
    rig = _Sql()
    a = _ids(1)[0]
    rig.add(MISSION, a, LIVE)
    rig.add(OTHER, _ids(1)[0], LIVE)
    rig.seal()
    rec = _Recorder(rig.conn)
    hostile = "msn_0' OR '1'='1"
    try:
        assert trace.lessons(rec, hostile) == ([], False)
        sql, params = rec.calls[0]
        assert params == (hostile,) and hostile not in sql
        assert sql.count('?') == 1 and MISSION not in sql and OTHER not in sql
        assert trace.lessons(rec, MISSION) == ([a], False)
        assert rec.read == [0, 1]
        assert rig.count() == 2
    finally:
        rig.close()


def test_an_expired_or_unshaped_row_for_an_id_never_becomes_the_last_marker(db_world):
    db, who = db_world
    mid = _mission(db, who)
    a, b, z1, z2 = _ids(4)
    rows = [(a, EXPIRED, {}), (a, '[]', {}), (a, '{"valid_until": ""}', {}), (a, None, {}),
            (z1, None, {'valid_until': '2020-01-01T00:00:00Z'}), (z2, 'not json', {}),
            (b, EXPIRED, {}), (b, None, {})]
    _seed(db, who, mid, rows)
    with db.read() as conn:
        rec = _Recorder(conn)
        before = conn.execute('SELECT COUNT(*) FROM relations').fetchone()[0]
        assert trace.lessons(rec, mid) == ([a, b], False)
        t = trace.trace(conn, mid, _Registry())
        after = conn.execute('SELECT COUNT(*) FROM relations').fetchone()[0]
    assert before == after == len(rows)
    schemas.validate(t, schemas.TYPES['Trace'])
    assert t['lessons'] == [a, b] == sorted(set(t['lessons']))
    assert t['lessons_more'] is False
    text = json.dumps(t)
    assert z1 not in text and z2 not in text


def test_an_invalid_row_between_two_live_copies_of_one_id_does_not_reset_the_marker(db_world):
    db, who = db_world
    mid = _mission(db, who)
    a, b = _ids(2)
    rows = [(a, None, {}), (a, MALFORMED[2], {}), (a, None, {}), (b, None, {})]
    _seed(db, who, mid, rows)
    with db.read() as conn:
        rec = _Recorder(conn)
        assert trace.lessons(rec, mid) == ([a, b], False)
    assert rec.read == [4]


def test_a_run_of_bad_bodies_is_skipped_row_by_row_until_a_live_one_arrives():
    assert trace.LESSONS_MAX == 200
    good, dup = _ids(2)
    pairs = [(junk, MALFORMED[n % len(MALFORMED)]) for n, junk in enumerate(_ids(250))]
    pairs += [(junk, NON_OBJECT[n % len(NON_OBJECT)]) for n, junk in enumerate(_ids(60))]
    pairs += [(good, LIVE), (dup, EXPIRED), (good, MALFORMED[3]), (good, '[]'),
              (good, LIVE)]
    found, more, db = _lessons(pairs)
    assert found == [good] and more is False
    assert db.supply.pulled == len(pairs)
    assert db.calls[0][1] == (MISSION,)


def test_only_live_distinct_ids_count_toward_the_return_cap():
    live = _ids(201)
    junk = _ids(8)
    pairs = [(k, LIVE) for k in live]
    pairs += [(junk[0], MALFORMED[0]), (junk[1], '[]'), (junk[2], EXPIRED),
              (junk[3], EXPIRED), (junk[4], 'null'), (junk[5], MALFORMED[5]),
              (junk[6], '0'), (junk[7], MALFORMED[7])]
    pairs += [(live[3], MALFORMED[1]), (live[3], LIVE),
              (live[7], 'null'), (live[7], LIVE)]
    found, more, db = _lessons(pairs)
    assert found == live[:200] and len(found) == trace.LESSONS_MAX
    assert more is True
    assert not (set(junk) & set(found))
    stream = sorted(pairs, key=lambda p: p[0])
    stopped = next(n for n, (s, _) in enumerate(stream, start=1) if s == live[200])
    assert db.supply.pulled == stopped


def test_the_cursor_is_never_asked_for_the_row_after_the_cap_is_passed():
    live, tail = _ids(201), _ids(400)
    pairs = [(k, LIVE) for k in live] + [(k, EXPIRED) for k in tail]
    pairs.append((_POISON_ID, _POISON))
    found, more, db = _lessons(pairs)
    assert found == live[:200] and more is True
    stream = sorted(pairs, key=lambda p: p[0])
    stopped = next(n for n, (s, _) in enumerate(stream, start=1) if s == live[200])
    assert db.supply.pulled == stopped


def test_exactly_the_cap_of_live_lessons_with_an_expired_tail_is_not_reported_as_more():
    live, tail = _ids(200), _ids(trace.LESSONS_SCAN_MAX - 200)
    pairs = [(k, LIVE) for k in live] + [(k, EXPIRED) for k in tail]
    found, more, _ = _lessons(pairs)
    assert found == live and len(found) == trace.LESSONS_MAX
    assert more is False and type(more) is bool and type(found) is list
    assert tail[0] not in found


def test_a_body_deep_enough_to_outrecursion_the_decoder_is_skipped_like_any_bad_one():
    body = ('[' * 200000) + (']' * 200000)
    with pytest.raises(RecursionError):
        json.loads(body)
    a, c = _ids(2)
    bad = _ids(1)[0]
    pairs = [(a, LIVE), (bad, body), (c, LIVE)]
    found, more, db = _lessons(pairs)
    assert found == [a, c] and more is False
    assert bad not in found
    assert db.supply.pulled == len(pairs)


def test_expired_rows_past_the_scan_cap_are_not_read_and_more_is_flagged():
    cap = trace.LESSONS_SCAN_MAX
    srcs = _ids(cap + 1)
    pairs = [(s, EXPIRED) for s in srcs[:cap]] + [(srcs[cap], _POISON)]
    found, more, db = _lessons(pairs)
    assert (found, more) == ([], True)
    assert db.supply.pulled == cap + 1


def test_a_live_lesson_inside_the_scan_cap_is_still_found():
    cap = trace.LESSONS_SCAN_MAX
    srcs = _ids(cap)
    pairs = [(s, EXPIRED) for s in srcs[:-1]] + [(srcs[-1], LIVE)]
    found, more, _ = _lessons(pairs)
    assert (found, more) == ([srcs[-1]], False)

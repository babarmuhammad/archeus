
import pytest

from archeus.core.application import trace
from archeus.core.domain import entities, ids
from archeus.core.domain.events import new_event
from archeus.core.domain.values import Ref
from archeus.infra.db import Database

VALID = '{"valid_until": null}'
EMPTY = '{}'


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
    mid, pid, tid = (ids.new_id(k) for k in ('mission', 'plan', 'task'))

    def run(tx, **_):
        tx.insert(entities.Mission(id=mid, workspace_id=ids.GLOBAL_WORKSPACE, title='M',
                                   objective='o', state='EXECUTING'), actor=who)
        tx.insert(entities.Plan(id=pid, mission_id=mid, state='APPROVED'), actor=who)
        tx.insert(entities.Task(id=tid, plan_id=pid, mission_id=mid, key='t', title='T',
                                kind='code_change', state='RUNNING', max_attempts=2),
                  actor=who)
        tx.append(_witness(who))
    db.writer.execute(run, {})
    return mid


def _seed_relations(db, who, rows):
    def run(tx, **_):
        for src_kind, src_id, rel, dst_kind, dst_id, body in rows:
            rid = ids.new_id('relation')
            tx.insert(entities.Relation(id=rid, src_kind=src_kind, src_id=src_id,
                                        rel=rel, dst_kind=dst_kind, dst_id=dst_id),
                      actor=who)
            tx.execute('UPDATE relations SET body = ? WHERE id = ?', (body, rid))
        tx.append(_witness(who))
    db.writer.execute(run, {})


def _lesson_rows(dst_id, pairs):
    rows = [('knowledge_item', sid, 'learned_from', 'mission', dst_id, body)
            for sid, body in pairs]
    return rows


class _Counting:

    def __init__(self, cursor):
        self.cursor = cursor
        self.pulled = []

    def __iter__(self):
        for row in self.cursor:
            self.pulled.append(row['src_id'])
            yield row

    def fetchall(self):
        pytest.fail('lessons read every row at once')


class _CountRead:
    def __init__(self, conn):
        self.conn = conn
        self.cursors = []

    def execute(self, sql, params):
        cur = _Counting(self.conn.execute(sql, params))
        self.cursors.append(cur)
        return cur


class _FakeRead:

    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def execute(self, sql, params):
        self.calls.append((sql, params))
        return iter(self.rows)


def _counts(db, table):
    with db.read() as conn:
        return conn.execute('SELECT COUNT(*) FROM %s' % table).fetchone()[0]


@pytest.mark.parametrize('expired_first', [True, False])
def test_an_expired_body_is_refused_and_never_steals_its_srcs_place(expired_first):
    rows = [{'src_id': 'ki_x', 'body': '{"valid_until": "2099-01-01"}'},
            {'src_id': 'ki_x', 'body': VALID},
            {'src_id': 'ki_y', 'body': '{"valid_until": "2099-01-01"}'}]
    if not expired_first:
        rows = [rows[1], rows[0], rows[2]]
    conn = _FakeRead(rows)
    assert trace.lessons(conn, 'msn_test') == (['ki_x'], False)
    (sql, params), = conn.calls
    assert 'FROM relations' in sql and 'ORDER BY src_id' in sql
    assert params == ('msn_test',)


@pytest.mark.parametrize('junk', ['{"valid_until": ', 'not json at all', ''])
def test_a_malformed_row_sharing_a_src_id_does_not_evict_the_valid_one(junk):
    rows = [{'src_id': 'ki_x', 'body': junk}, {'src_id': 'ki_x', 'body': EMPTY}]
    conn = _FakeRead(rows)
    assert trace.lessons(conn, 'msn_test') == (['ki_x'], False)
    (sql, params), = conn.calls
    assert params == ('msn_test',)


def test_the_sql_filter_excludes_other_missions_and_wrong_ends_before_python(db_world):
    db, who = db_world
    mine, theirs = _mission(db, who), _mission(db, who)
    _seed_relations(db, who, [
        ('knowledge_item', 'ki_mine', 'learned_from', 'mission', mine, VALID),
        ('knowledge_item', 'ki_theirs', 'learned_from', 'mission', theirs, VALID),
        ('knowledge_item', 'ki_wrong_rel', 'uses', 'mission', mine, VALID),
        ('knowledge_item', 'ki_wrong_rel2', 'mentions', 'mission', mine, VALID),
        ('mission', 'ki_wrong_src_kind', 'learned_from', 'mission', mine, VALID),
        ('knowledge_item', 'ki_wrong_dst_kind', 'learned_from', 'task', mine, VALID),
        ('knowledge_item', 'ki_null_like', 'learned_from', 'mission', mine + 'x', VALID),
    ])
    before_events, before_relations = _counts(db, 'events'), _counts(db, 'relations')
    with db.read() as conn:
        read = _CountRead(conn)
        assert trace.lessons(read, mine) == (['ki_mine'], False)
        assert trace.lessons(read, theirs) == (['ki_theirs'], False)
    assert [c.pulled for c in read.cursors] == [['ki_mine'], ['ki_theirs']]
    assert _counts(db, 'events') == before_events
    assert _counts(db, 'relations') == before_relations


def test_over_the_cap_only_the_sorted_prefix_is_kept_and_the_read_stops(db_world, monkeypatch):
    db, who = db_world
    mid = _mission(db, who)
    wanted = ['ki_%d' % n for n in range(5)]
    _seed_relations(db, who, _lesson_rows(mid, [(s, EMPTY) for s in reversed(wanted)]))
    monkeypatch.setattr(trace, 'LESSONS_MAX', 2)
    with db.read() as conn:
        read = _CountRead(conn)
        found, more = trace.lessons(read, mid)
    assert found == wanted[:2]
    assert more is True
    assert read.cursors[0].pulled == wanted[:3]


def test_exactly_the_cap_returns_every_lesson_and_says_no_more(db_world):
    db, who = db_world
    mid = _mission(db, who)
    wanted = ['ki_%03d' % n for n in range(trace.LESSONS_MAX)]
    assert len(wanted) == 200 == trace.LESSONS_MAX
    _seed_relations(db, who, _lesson_rows(mid, [(s, VALID) for s in reversed(wanted)]))
    with db.read() as conn:
        found, more = trace.lessons(conn, mid)
    assert found == wanted
    assert more is False


def test_scalar_and_bool_bodies_are_skipped_exactly_like_lists_and_null(db_world):
    db, who = db_world
    mid = _mission(db, who)
    pairs = [('ki_1', '42'), ('ki_2', '3.5'), ('ki_3', 'true'), ('ki_4', 'false'),
             ('ki_5', '"a string"'), ('ki_6', '[]'), ('ki_ok1', VALID),
             ('ki_7', 'null'), ('ki_ok2', EMPTY)]
    _seed_relations(db, who, _lesson_rows(mid, pairs))
    with db.read() as conn:
        found, more = trace.lessons(conn, mid)
    assert found == ['ki_ok1', 'ki_ok2']
    assert more is False


def test_empty_dict_and_null_valid_until_are_lessons_not_junk(db_world):
    db, who = db_world
    mid = _mission(db, who)
    pairs = [('ki_a', EMPTY), ('ki_b', VALID),
             ('ki_c', '{"valid_until": null, "note": "keep me"}'), ('ki_d', '{"note": 1}')]
    _seed_relations(db, who, _lesson_rows(mid, pairs))
    with db.read() as conn:
        found, more = trace.lessons(conn, mid)
    assert found == ['ki_a', 'ki_b', 'ki_c', 'ki_d']
    assert more is False


def test_two_valid_rows_for_one_src_id_return_that_lesson_once(db_world):
    db, who = db_world
    mid = _mission(db, who)
    _seed_relations(db, who, _lesson_rows(mid, [('ki_dup', EMPTY), ('ki_dup', VALID),
                                                 ('ki_solo', '{"note": 1}')]))
    with db.read() as conn:
        found, more = trace.lessons(conn, mid)
    assert found == ['ki_dup', 'ki_solo']
    assert more is False


def test_a_mission_with_no_lessons_answers_the_empty_pair(db_world):
    db, who = db_world
    mid = _mission(db, who)
    before_events, before_relations = _counts(db, 'events'), _counts(db, 'relations')
    with db.read() as conn:
        assert trace.lessons(conn, mid) == ([], False)
        assert trace.lessons(conn, 'ki_absent') == ([], False)
    assert _counts(db, 'events') == before_events
    assert _counts(db, 'relations') == before_relations


def test_a_deeply_nested_body_cannot_kill_the_lessons_read(db_world):
    db, who = db_world
    mid = _mission(db, who)
    deep = '[' * 10000 + ']' * 10000
    _seed_relations(db, who, _lesson_rows(mid, [('ki_deep', deep), ('ki_good', VALID)]))
    with db.read() as conn:
        assert trace.lessons(conn, mid) == (['ki_good'], False)

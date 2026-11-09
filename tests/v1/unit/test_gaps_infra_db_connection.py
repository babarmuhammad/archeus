"""T-755: the ten highest-risk uncovered branches of archeus/infra/db/connection.py.

Fail-closed and denial paths first — a WAL the engine refuses (connection.py:79-81,
which must close the half-set connection, not return it), a file the read-only
inspector must not write even after `query_only` is turned off (:91-93), a version
gate that must fire before a byte is written (:68, :90) — then the boundary values
(the exact 3.31 floor, the late 3.30 patch, the short version tuple, the
call-time `db_path` resolution, the case of the WAL answer), then the error paths
(the URI the inspector builds from a path with spaces, the connect kwargs that
are the writer-transaction and pool-threading contract, and the contended
BEGIN IMMEDIATE that must either commit whole or leave nothing).

Existing coverage: tests/v1/integration/test_db_schema.py checks the pragmas on a
READ connection reached through `Database`, and the gate through `Database.open()`.
Nothing checked the WAL-refusal branch, the write connection's own pragmas, the
`inspect()` denial, the connect kwargs or thread behaviour. Style and the
monkeypatch-the-OS seams follow tests/v1/unit/test_gaps_core_world_inspection.py.

Platform-neutral by construction: nothing shells out, no OS error text is matched
(matching is on SQLite's own fixed-English 'database is locked' / 'readonly' and
on our own exception messages), file names are ASCII with no '?' or ':', bytes are
compared against the file itself, no thread set is inspected (only a worker this
test started is joined with a timeout), and the busy timeout is shortened through
the module's own seam so the contended-lock wait is 0.12 s, never a sleep.
"""

import os
import sqlite3
import threading

import pytest

from archeus.infra.db import connection


# ── the seams ────────────────────────────────────────────────────────────────

class _Answer:
    """One pragma result, without SQLite having to produce it."""

    def __init__(self, value):
        self._value = value

    def fetchone(self):
        return (self._value,)


@pytest.fixture
def fake_pragma(monkeypatch):
    """Answer one PRAGMA with a fixed value on our Connection class; every other
    statement still reaches real SQLite. Neither review box can be made to
    refuse WAL on demand, so the refusal is delivered here."""
    real = sqlite3.Connection.execute
    answers = {}

    def set_answer(fragment, value):
        answers[fragment.lower()] = value

    def patched(self, sql, *a):
        for frag, val in answers.items():
            if frag in sql.lower():
                return _Answer(val)
        return real(self, sql, *a)
    monkeypatch.setattr(connection.Connection, 'execute', patched)
    return set_answer


@pytest.fixture
def opens(monkeypatch):
    """Record every sqlite3.connect() connection.py makes — path, kwargs and the
    connection object — while the real opens still happen."""
    real = sqlite3.connect
    seen = []

    def spy(path, **kw):
        conn = real(path, **kw)
        seen.append({'path': path, 'kw': dict(kw), 'conn': conn})
        return conn
    monkeypatch.setattr(sqlite3, 'connect', spy)
    return seen


def _seed(path):
    """A one-row database written through the real write path, then closed."""
    c = connection.connect(str(path))
    c.execute('CREATE TABLE t (x INTEGER)')
    c.execute('INSERT INTO t VALUES (1)')
    c.close()


# ── fail-closed and denial ───────────────────────────────────────────────────

def test_wal_refusal_fails_closed_and_closes_the_connection(tmp_path, opens, fake_pragma,
                                                            monkeypatch):
    """connection.py:78-81 — SQLite answers journal_mode with 'delete': connect
    must raise, and it must CLOSE the half-configured connection first (an open
    non-WAL connection on the file is the torn-restore scenario ADR-0002 exists
    to prevent)."""
    real_close = sqlite3.Connection.close
    closed = []

    def rec(self):
        closed.append(self)
        real_close(self)
    monkeypatch.setattr(connection.Connection, 'close', rec)
    fake_pragma('journal_mode', 'delete')
    path = str(tmp_path / 'db.sqlite')
    with pytest.raises(RuntimeError) as e:
        connection.connect(path)
    assert 'refused WAL mode' in str(e.value) and 'delete' in str(e.value)
    assert closed == [opens[-1]['conn']]                    # closed exactly once, no leak
    with pytest.raises(sqlite3.ProgrammingError):
        opens[-1]['conn'].execute('SELECT 1')                # it really is closed


def test_inspect_cannot_write_the_file_even_with_query_only_off(tmp_path):
    """connection.py:91-93 — `mode=ro` is a different guarantee from
    `query_only`: a stray `PRAGMA query_only = OFF` on the doctor's connection
    must still not move one byte of a database Core crashed out of."""
    path = tmp_path / 'archeus.db'
    _seed(path)
    before = path.read_bytes()
    c = connection.inspect(str(path))
    assert c.execute('PRAGMA query_only').fetchone()[0] == 1        # line 93 ran
    assert [r[0] for r in c.execute('SELECT x FROM t')] == [1]
    with pytest.raises(sqlite3.OperationalError, match='readonly'):
        c.execute('INSERT INTO t VALUES (2)')
    c.execute('PRAGMA query_only = OFF')
    for stmt in ('INSERT INTO t VALUES (3)', 'DELETE FROM t', 'CREATE TABLE u (y)',
                 'DROP TABLE t'):
        with pytest.raises(sqlite3.OperationalError, match='readonly'):
            c.execute(stmt)
    c.close()
    assert path.read_bytes() == before                      # mode=ro held the whole time


def test_inspect_refuses_a_missing_file_and_creates_nothing(tmp_path):
    """connection.py:91-92 — mode=ro over a missing path inside an existing
    directory: an error, and not the convenience of an empty database (an
    ordinary connect would create the 0-byte file right here, so doctor would
    see 'a database' where Core has never run)."""
    path = tmp_path / 'late.db'
    with pytest.raises(sqlite3.OperationalError):
        connection.inspect(str(path))
    assert not path.exists()
    assert not os.path.exists(str(path) + '-wal')


def test_both_opens_refuse_an_old_sqlite_before_touching_the_disk(tmp_path, monkeypatch):
    """connection.py:68 and :90 — the gate is the FIRST statement of connect()
    and of inspect(): a refused build must leave no archeus.db, no -wal sidecar,
    nothing for the next, newer SQLite to half-recover."""
    monkeypatch.setattr(sqlite3, 'sqlite_version_info', (3, 29, 0))
    path = str(tmp_path / 'gated.db')
    with pytest.raises(connection.SQLiteTooOld):
        connection.connect(path)
    with pytest.raises(connection.SQLiteTooOld):
        connection.inspect(path)
    assert not os.path.exists(path)
    assert not os.path.exists(path + '-wal')


def test_the_write_connection_writes_and_the_read_connection_may_not(tmp_path):
    """connection.py:75-77 — the if/else that decides who may write. Invert it
    and either the writer is query_only (no command ever commits) or the pool
    readers can write (single-writer gate gone): both are caught here, and by
    real writes, not only pragma reads."""
    path = str(tmp_path / 'db.sqlite')
    w = connection.connect(path)
    assert w.execute('PRAGMA query_only').fetchone()[0] == 0
    w.execute('CREATE TABLE p (id INTEGER PRIMARY KEY)')
    w.execute('CREATE TABLE c (p INTEGER REFERENCES p (id))')
    w.execute('INSERT INTO p VALUES (1)')                    # a writer that really writes
    w.execute('INSERT INTO c VALUES (1)')
    with pytest.raises(sqlite3.IntegrityError):              # foreign_keys=ON, enforced
        w.execute('INSERT INTO c VALUES (42)')               # not merely SET
    r = connection.connect(path, readonly=True)
    assert r.execute('PRAGMA query_only').fetchone()[0] == 1
    with pytest.raises(sqlite3.OperationalError, match='readonly'):
        r.execute('DELETE FROM c')
    w.close()
    r.close()


# ── boundary values ──────────────────────────────────────────────────────────

def test_the_version_gate_boundary_is_exact():
    """connection.py:53 — `got < MIN_SQLITE` on tuples: the floor itself passes,
    a 3.30 build with any patch level fails (string comparison or a major.minor
    prefix check would let '3.30.99' through), a 4-tuple build above the floor
    passes, and a SHORTER tuple fails closed rather than guessing."""
    connection.require_sqlite((3, 31, 0))
    connection.require_sqlite((3, 31, 0, 1))
    connection.require_sqlite((4, 0, 0))
    for too_old in ((3, 30, 9999), (3, 30, 1), (2, 99, 99), (3, 31), (3,)):
        with pytest.raises(connection.SQLiteTooOld):
            connection.require_sqlite(too_old)


def test_the_gate_reads_the_live_build_when_no_version_is_given(tmp_path, monkeypatch):
    """connection.py:52 — the `version is None` branch: the live
    sqlite_version_info is the answer, so a monkeypatched build is refused and
    this box's own build is accepted."""
    connection.require_sqlite()
    monkeypatch.setattr(sqlite3, 'sqlite_version_info', (3, 30, 0))
    with pytest.raises(connection.SQLiteTooOld):
        connection.require_sqlite()


def test_wal_answered_in_upper_case_is_accepted(tmp_path, fake_pragma):
    """connection.py:78-79 — `mode.lower() != 'wal'`: some builds answer
    'WAL'. Drop the .lower() and a healthy database is refused at open — the
    other half of the refusal branch, and the refusal of the refusal."""
    fake_pragma('journal_mode', 'WAL')
    c = connection.connect(str(tmp_path / 'db.sqlite'))
    try:
        assert type(c) is connection.Connection
    finally:
        c.close()


def test_db_path_is_resolved_at_call_time(tmp_path, monkeypatch):
    """connection.py:60-61 — no memoised path: the environment and the argument
    are read every call (an import-time freeze would point Core at yesterday's
    home); a relative home becomes abspath(cwd/home), a None home follows
    ARCHEUS_HOME, and the file name is always DB_NAME."""
    a = tmp_path / 'home a'
    monkeypatch.setenv('ARCHEUS_HOME', str(a))
    assert connection.db_path() == os.path.join(str(a), 'archeus.db')
    b = tmp_path / 'home b'
    monkeypatch.setenv('ARCHEUS_HOME', str(b))
    assert connection.db_path() == os.path.join(str(b), 'archeus.db')   # not cached
    monkeypatch.chdir(tmp_path)
    assert connection.db_path('sub dir') == os.path.join(os.path.abspath('sub dir'),
                                                         'archeus.db')
    assert connection.db_path(str(tmp_path)) == os.path.join(str(tmp_path), 'archeus.db')


# ── error and behaviour paths ────────────────────────────────────────────────

def test_inspect_builds_a_readable_uri_from_a_path_with_spaces(tmp_path):
    """connection.py:91 — `as_uri()` + '?mode=ro': drop as_uri() and the raw
    path (with its space, and on Windows its 'C:') is parsed as a malformed URI
    or, worse, opened writable without the mode."""
    home = tmp_path / 'home dir'
    home.mkdir()
    path = home / 'db x.db'
    _seed(path)
    c = connection.inspect(str(path))
    try:
        assert [r[0] for r in c.execute('SELECT x FROM t')] == [1]
        with pytest.raises(sqlite3.OperationalError, match='readonly'):
            c.execute('INSERT INTO t VALUES (9)')
    finally:
        c.close()


def test_every_open_declares_busy_waiting_and_threading(tmp_path, opens, monkeypatch):
    """connection.py:69-70 and :92 — the kwargs ARE the architecture:
    isolation_level=None (the writer issues its own BEGIN IMMEDIATE),
    check_same_thread=not readonly (the pool shares readers, the writer thread
    owns its connection), factory=Connection (homes_cache), and timeout taken
    from BUSY_TIMEOUT_MS — set to 1234 here, because sqlite3's own default is
    5.0 and a dropped `timeout=` must not hide behind it."""
    monkeypatch.setattr(connection, 'BUSY_TIMEOUT_MS', 1234)
    path = str(tmp_path / 'db.sqlite')
    w = connection.connect(path)
    r = connection.connect(path, readonly=True)
    c = connection.inspect(path)
    try:
        w_kw, r_kw, i_kw = (opens[-3]['kw'], opens[-2]['kw'], opens[-1]['kw'])
        assert w_kw['isolation_level'] is None and r_kw['isolation_level'] is None
        assert i_kw['isolation_level'] is None and i_kw['uri'] is True
        assert w_kw['check_same_thread'] is True and r_kw['check_same_thread'] is False
        assert w_kw['factory'] is connection.Connection
        for kw in (w_kw, r_kw, i_kw):
            assert kw['timeout'] == 1234 / 1000
        assert w.execute('PRAGMA busy_timeout').fetchone()[0] == 1234      # line 72
        assert w.isolation_level is None
    finally:
        w.close()
        r.close()
        c.close()


def test_the_write_connection_carries_the_safety_pragmas(tmp_path):
    """connection.py:72-74 and :78 on the WRITE connection — the existing suite
    only ever read these pragmas on a pooled READ connection; FULL synchronous
    and WAL are what the acknowledged command survives, and they live or die on
    the writer's own connection."""
    c = connection.connect(str(tmp_path / 'db.sqlite'))
    try:
        assert c.execute('PRAGMA synchronous').fetchone()[0] == 2           # FULL
        assert c.execute('PRAGMA foreign_keys').fetchone()[0] == 1
        assert c.execute('PRAGMA busy_timeout').fetchone()[0] == connection.BUSY_TIMEOUT_MS
        assert c.execute('PRAGMA journal_mode').fetchone()[0].lower() == 'wal'
        assert c.execute('PRAGMA journal_mode').fetchone()[0].lower() == 'wal'
    finally:
        c.close()
    c2 = connection.connect(str(tmp_path / 'db.sqlite'))                    # it persisted
    try:
        assert c2.execute('PRAGMA journal_mode').fetchone()[0].lower() == 'wal'
    finally:
        c2.close()


def test_connections_are_the_named_factory_with_named_rows(tmp_path):
    """connection.py:43-47, :70 and :71 — factory=Connection is what gives the
    Database its homes_cache onto the connection (`homes_cache = None` until an
    owner hangs one), and row_factory=sqlite3.Row is what every rows.py read
    indexes by column name; lose either and the reader/writer code breaks in a
    place far from here."""
    path = str(tmp_path / 'db.sqlite')
    c = connection.connect(path)
    r = connection.connect(path, readonly=True)
    try:
        assert type(c) is connection.Connection and type(r) is connection.Connection
        assert c.homes_cache is None and r.homes_cache is None               # nobody owns it
        c.homes_cache = {'a': 1}                                             # now something does
        row = c.execute('SELECT 7 AS n').fetchone()
        assert isinstance(row, sqlite3.Row) and row['n'] == 7                # named access
    finally:
        c.close()
        r.close()


def test_a_second_writer_is_locked_and_a_rolled_back_write_leaves_nothing(tmp_path,
                                                                          monkeypatch):
    """connection.py:69 (isolation_level=None) and :70/:72 (busy timeout): the
    writer's BEGIN IMMEDIATE is the ONE gate. While w1 holds it, a competing
    writer must meet SQLITE_BUSY (after the 120 ms busy wait, not a sleep), the
    reader must see nothing of the uncommitted row, and w1's ROLLBACK must
    leave no trace — a partial write is the failure this whole file exists for."""
    monkeypatch.setattr(connection, 'BUSY_TIMEOUT_MS', 120)
    path = str(tmp_path / 'db.sqlite')
    w1 = connection.connect(path)
    w1.execute('CREATE TABLE t (x)')                     # autocommit: no implicit BEGIN
    w1.execute('BEGIN IMMEDIATE')
    w1.execute('INSERT INTO t VALUES (1)')
    r = connection.connect(path, readonly=True)
    assert [row[0] for row in r.execute('SELECT x FROM t')] == []     # no dirty read
    w2 = connection.connect(path)
    with pytest.raises(sqlite3.OperationalError, match='locked'):
        w2.execute('BEGIN IMMEDIATE')
    w1.execute('ROLLBACK')
    w2.execute('BEGIN IMMEDIATE')                        # the lock is free again
    w2.execute('INSERT INTO t VALUES (2)')
    w2.execute('COMMIT')
    assert [row[0] for row in w2.execute('SELECT x FROM t')] == [2]   # only the whole write
    w1.close()
    w2.close()
    r.close()


def test_the_writer_connection_stays_on_its_thread_and_readers_do_not(tmp_path):
    """connection.py:69 — check_same_thread=not readonly, behaviourally: the
    pool may hand a reader to another thread; the write connection used off
    the writer thread must raise sqlite3.ProgrammingError, which is the same
    structural check the writer thread's ownership relies on."""
    path = str(tmp_path / 'db.sqlite')
    _seed(path)
    w = connection.connect(path)
    r = connection.connect(path, readonly=True)
    out = {}

    def work():
        try:
            list(w.execute('SELECT 1'))
            out['w'] = 'accepted'
        except sqlite3.ProgrammingError:
            out['w'] = 'confined'
        try:
            out['r'] = list(r.execute('SELECT x FROM t'))[0][0]
        except sqlite3.Error as e:
            out['r'] = 'error: %s' % type(e).__name__
    t = threading.Thread(target=work)
    t.start()
    t.join(timeout=30)
    try:
        assert out == {'w': 'confined', 'r': 1}
    finally:
        w.close()
        r.close()

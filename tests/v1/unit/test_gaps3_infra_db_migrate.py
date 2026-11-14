"""T-1149: the ten highest-risk uncovered branches of `archeus/infra/db/migrate.py`
lines 1-88 (the whole module at tip 56d53504), as tests. No source file is edited.

The ten selected branches, fail-closed and denial first, then boundaries, then error
paths (risk rank in brackets):

[g1 · 1] migrate.py:75-79 — the version is re-checked INSIDE the write transaction and
    the step is refused with `ROLLBACK` + `continue` when another writer got there
    first. Nothing else ever enters this branch: re-running `migrate` on an open
    database finds `pending` empty at line 71 and never reaches line 77.
[g2 · 2] migrate.py:33-37 — a DUPLICATE number (two files, one number). The existing
    numbering test only makes a GAP (`0001` + `0003`), so the duplicate arm of the
    same guard is untested, and so is "the whole set is refused before the connection
    is touched".
[g3 · 3] migrate.py:18 + 33-34 — the `_NAME.fullmatch` filter's false arm: a migration
    file whose name does not match is ignored, uncounted and never applied. No test
    has ever put a misnamed file in a migrations directory.
[g4 · 4] migrate.py:66 (`latest = ... if steps else 0`) with 68-70 — an EMPTY
    migrations directory against a database that carries a version: `SchemaTooNew`,
    never a downgrade; plus the same `else 0` arm with a fresh database (returns 0).
[g5 · 5] migrate.py:68-70 before 72-73 — the refusal of a newer database is decided
    BEFORE the pre-migration backup hook: the connection is only ever read.
[g6 · 6] migrate.py:72 `have > 0` false arm — a fresh database (version 0) with pending
    steps never calls `before`, so an empty database is never backed up.
[g7 · 7] migrate.py:72-73 true arm — `before(have, latest)` runs exactly once, before
    the first `BEGIN IMMEDIATE`, against a database that is still entirely the old
    schema (the ordering the docstring at lines 10-12 promises).
[g8 · 8] migrate.py:44-49 — the `sqlite3.complete_statement` false arm while a
    semicolon sits inside a string literal or a `CREATE TRIGGER ... BEGIN ... END;`
    body: one statement, applied whole, never split into runnable halves.
[g9 · 9] migrate.py:50-52 — both arms of the comment-only residue test together (a
    comment tail is dropped, a comment-then-code tail raises) and the `[:80]`
    truncation of the reported buffer.
[g10 · 10] migrate.py:84-87 — `except sqlite3.Error` taken while NO transaction is
    open (the false arm of `if conn.in_transaction`): the failure is reported as
    `MigrationError` chained to the SQLite error, no second `ROLLBACK` is attempted,
    and the loop stops so no later migration runs on top of a half-run one.

The probes the card named that were ALREADY covered and were replaced: newer-schema
refusal (`test_a_database_from_a_newer_archeus_is_refused`, replaced by g4/g5, which add
the empty-directory composition and the backup-hook ordering), missing number
(`test_migrations_are_numbered_contiguously`, replaced by g2's duplicate and g3's
misnamed name), backup failure before writes
(`test_the_backup_is_taken_before_any_migration_work`, replaced by g7's direct hook
ordering at the `migrate()` seam), SQL failure rolling back DDL and version
(`test_a_failed_migration_rolls_back_whole_and_recreates_nothing`, replaced by g10's
no-transaction arm), unterminated SQL and trailing comments
(`test_the_statement_splitter_refuses_an_unterminated_statement`, replaced by g9's
mixed comment/code residue and the 80-character boundary).

Unit placement, like tests/v1/unit/test_gaps_infra_db_writer.py: the connection is the
real SQLite one from `infra.db.connection.connect` on a file under `tmp_path`, and the
only faked thing is what SQLite ANSWERS at the seam (one `PRAGMA user_version` read,
logged in order) — no OS call, no network, no real process, no thread, no sleep, no
subprocess, no environment value, nothing written outside `tmp_path`. Filenames are the
portable ASCII set `_NAME` accepts, and every SQL string carries its own `\\n` bytes.
tests/v1/integration/test_db_schema.py is read as coverage context only; no test here
imports another test file.
"""

import sqlite3

import pytest

from archeus.infra.db import connection, migrate

INIT = 'CREATE TABLE alpha (id TEXT PRIMARY KEY);\n'
SECOND = 'CREATE TABLE beta (id TEXT PRIMARY KEY);\n'
THIRD = 'CREATE TABLE gamma (id TEXT PRIMARY KEY);\n'
FOURTH = 'CREATE TABLE delta (id TEXT PRIMARY KEY);\n'
FIFTH = 'CREATE TABLE epsilon (id TEXT PRIMARY KEY);\n'
SIXTH = 'CREATE TABLE zeta (id TEXT PRIMARY KEY);\n'
SEVENTH = 'CREATE TABLE eta (id TEXT PRIMARY KEY);\n'


# ── rigs ────────────────────────────────────────────────────────────────────


def _dir(tmp_path, name, files):
    """A private migrations directory; every file's bytes are written verbatim, so
    the newlines the splitter sees are the ones this file says."""
    d = tmp_path / name
    d.mkdir()
    for fname, sql in files.items():
        (d / fname).write_bytes(sql.encode('utf-8'))
    return str(d)


def _db(request, tmp_path, name='db.sqlite'):
    """The real write connection (infra.db.connection.connect), closed after the
    test, on a file under tmp_path."""
    conn = connection.connect(str(tmp_path / name))
    request.addfinalizer(conn.close)
    return conn


class _Row:
    """The answer to `PRAGMA user_version` that the seam hands back."""

    def __init__(self, value):
        self._value = value

    def fetchone(self):
        return (self._value,)


class _Log:
    """The real write connection with every statement it is given logged, and one
    seam: the FIRST bare `PRAGMA user_version` read (migrate.py:67) may answer from a
    snapshot taken before `race` runs, which is how a competing writer slips its own
    commit in between this process's version read and its own BEGIN IMMEDIATE. Only
    what SQLite answers is faked; nothing here fakes an OS call."""

    def __init__(self, conn, race=None):
        self._conn = conn
        self.log = []
        self._race = race
        self._raced = False

    def execute(self, sql, params=()):
        self.log.append(sql)
        if sql == 'PRAGMA user_version' and self._race is not None and not self._raced:
            self._raced = True
            snapshot = self._conn.execute(sql).fetchone()[0]
            self._race()
            return _Row(snapshot)
        return self._conn.execute(sql, params)

    def __getattr__(self, name):                       # in_transaction and friends
        return getattr(self._conn, name)


def _pragma(conn):
    return conn.execute('PRAGMA user_version').fetchone()[0]


def _names(conn):
    """The user objects in the file: internal `sqlite_*` indexes are not evidence."""
    return {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type IN ('table', 'trigger', 'index')")
        if not r[0].startswith('sqlite_')}


# ── fail-closed and denial ──────────────────────────────────────────────────


def test_g1_competing_writer_is_refused_under_the_write_lock(request, tmp_path):
    # migrate.py:75-79 `conn.execute('BEGIN IMMEDIATE')` / `if version(conn) >=
    # target: conn.execute('ROLLBACK'); continue`. Removing the re-check (or turning
    # `>=` into `>`) re-applies a migration another process already committed: here
    # that is a `CREATE TABLE beta` over the competitor's own row, which SQLite
    # answers with "table beta already exists" inside the transaction.
    only_one = _dir(tmp_path, 'm1', {'0001_init.sql': INIT})
    c = _db(request, tmp_path)
    assert migrate.migrate(c, directory=only_one) == 1
    three = _dir(tmp_path, 'm2', {'0001_init.sql': INIT,
                                  '0002_second.sql': SECOND,
                                  '0003_third.sql': THIRD})

    def competitor():                                   # the other process, committed
        c.execute('BEGIN IMMEDIATE')
        c.execute(SECOND.strip())
        c.execute('PRAGMA user_version = 2')
        c.execute('COMMIT')

    log = _Log(c, race=competitor)
    assert migrate.migrate(log, directory=three) == 3
    assert log.log[0] == 'PRAGMA user_version'          # the read at line 67 ...
    assert log.log[1] == 'BEGIN IMMEDIATE'              # ... is this side of the lock
    assert log.log.count('BEGIN IMMEDIATE') == 2        # 0002's and 0003's, no more
    assert log.log.count('ROLLBACK') == 1               # 0002 refused under the lock
    assert log.log.count('COMMIT') == 1                 # only 0003's
    assert 'CREATE TABLE beta (id TEXT PRIMARY KEY)' not in log.log
    assert 'PRAGMA user_version = 2' not in log.log     # its version is not rewritten
    assert _names(c) >= {'alpha', 'beta', 'gamma'}      # beta came from the competitor
    assert _pragma(c) == 3
    assert not (tmp_path / 'backups').exists()          # no privileged side effect


def test_g2_duplicate_migration_number_refuses_the_whole_set(request, tmp_path):
    # migrate.py:33-37, the duplicate arm of `if [v for v, _f in found] != list(...)`
    # and the "before anything runs" promise of lines 3-4. The existing
    # test_migrations_are_numbered_contiguously only builds a gap, and never touches
    # a connection: an implementation that returned the second file for a repeated
    # number (e.g. a dict keyed by version) would pass it and silently apply one of
    # the two files.
    base = _dir(tmp_path, 'base', {'0001_init.sql': INIT})
    dup = _dir(tmp_path, 'dup', {'0001_init.sql': INIT,
                                 '0002_first.sql': SECOND,
                                 '0002_second.sql': THIRD})
    with pytest.raises(migrate.MigrationError, match='no gap or duplicate') as e:
        migrate.migrations(dup)
    assert "'0002_first.sql'" in str(e.value) and "'0002_second.sql'" in str(e.value)
    c = _db(request, tmp_path)
    assert migrate.migrate(c, directory=base) == 1
    log = _Log(c)
    with pytest.raises(migrate.MigrationError, match='duplicate'):
        migrate.migrate(log, directory=dup)
    assert log.log == []                                # the set died before line 67
    assert _names(c) == {'alpha'}                       # neither file ran
    assert _pragma(c) == 1


def test_g3_a_misnamed_migration_is_ignored_and_never_applied(request, tmp_path):
    # migrate.py:18 `_NAME` and the `if m` filter at 33-34. No existing test puts a
    # name the regex rejects into a migrations directory, so the filter's false arm
    # is untested: with `fullmatch` relaxed to `match`, `0003_next.sql.old` becomes a
    # step and the numbering guard fires on a file nobody asked for; with the filter
    # dropped, `None.group` raises on notes.md; with the regex widened, a table
    # someone thinks is installed is silently not. Every name below is rejected for
    # the same reason on Windows and on Linux, so none of it relies on a
    # case-sensitive filesystem.
    base = _dir(tmp_path, 'base', {'0001_init.sql': INIT})
    odd = _dir(tmp_path, 'odd', {'0001_init.sql': INIT,
                                 '0002_extra.bak.sql': SECOND,     # a doubled extension
                                 '0002-dash.sql': THIRD,           # dash, not underscore
                                 '002_pad.sql': FOURTH,            # three digits
                                 'migrate_0002.sql': FIFTH,        # number not at the start
                                 '0003_next.sql.old': SIXTH,       # an editor leftover
                                 'notes.md': SEVENTH})
    assert [(v, f) for v, f, _s in migrate.migrations(odd)] == [(1, '0001_init.sql')]
    c = _db(request, tmp_path)
    assert migrate.migrate(c, directory=base) == 1
    assert migrate.migrate(c, directory=odd) == 1               # no error, no new step
    assert _names(c) == {'alpha'}                               # and none of them ran
    assert _pragma(c) == 1


def test_g4_empty_migrations_directory_against_a_versioned_database(request, tmp_path):
    # migrate.py:66 `latest = steps[-1][0] if steps else 0` with the refusal at
    # 68-70. The existing too-new test always ships a real 0001, so `latest` is never
    # 0 there: with the `else 0` arm dropped, an emptied directory raises IndexError
    # instead of the contract's SchemaTooNew; with it set to 1, a versioned database
    # is accepted by a build that has no migrations at all.
    base = _dir(tmp_path, 'base', {'0001_init.sql': INIT})
    c = _db(request, tmp_path)
    assert migrate.migrate(c, directory=base) == 1
    empty = tmp_path / 'empty'
    empty.mkdir()
    calls = []
    with pytest.raises(migrate.SchemaTooNew, match='schema 1; this Archeus knows up to 0'):
        migrate.migrate(c, directory=str(empty), before=lambda f, t: calls.append((f, t)))
    assert calls == []                                        # nothing was backed up
    assert _pragma(c) == 1                                    # never downgraded
    fresh = _db(request, tmp_path, 'fresh.sqlite')
    assert migrate.migrate(fresh, directory=str(empty)) == 0   # the other side of 66
    assert _names(fresh) == set()


def test_g5_a_too_new_database_is_refused_before_the_backup_hook(request, tmp_path):
    # migrate.py:68-70 ordered before 72-73. The existing test_a_database_from_a_
    # newer_archeus_is_refused checks the version is preserved but never hands
    # `migrate` a `before`, and test_the_backup_is_taken_before_any_migration_work
    # only proves the backup runs before the STATEMENTS: move the refusal below the
    # hook and both still pass while a database this build cannot read has already
    # been copied into the backups folder under a (99 -> 1) name.
    two = _dir(tmp_path, 'm', {'0001_init.sql': INIT, '0002_second.sql': SECOND})
    c = _db(request, tmp_path)
    c.execute('PRAGMA user_version = 99')
    log = _Log(c)
    calls = []
    with pytest.raises(migrate.SchemaTooNew, match='99'):
        migrate.migrate(log, directory=two, before=lambda f, t: calls.append((f, t)))
    assert calls == []                                        # no backup of a refused db
    assert log.log == ['PRAGMA user_version']                 # the connection was only read
    assert _pragma(c) == 99
    assert not (tmp_path / 'backups').exists()


# ── boundaries ──────────────────────────────────────────────────────────────


def test_g6_a_fresh_database_is_migrated_without_the_backup_hook(request, tmp_path):
    # migrate.py:72 `if pending and have > 0 and before is not None`, the `have > 0`
    # false arm. The existing test_migrating_twice_applies_nothing_twice asserts no
    # backups folder exists, but it goes through Database.open on an already-migrated
    # file, so its assertion also holds when the hook is called and the backup module
    # declines, and when `before` is None for the whole run: it cannot tell the arm
    # apart from a missing argument. Flip `have > 0` to `have >= 0` and THIS test
    # fails on a call the contract forbids.
    two = _dir(tmp_path, 'm', {'0001_init.sql': INIT, '0002_second.sql': SECOND})
    c = _db(request, tmp_path)
    log = _Log(c)
    calls = []
    assert migrate.migrate(log, directory=two,
                           before=lambda f, t: calls.append((f, t))) == 2
    assert calls == []                                        # an empty file is no backup
    assert log.log.count('BEGIN IMMEDIATE') == 2 and log.log.count('COMMIT') == 2
    assert 'ROLLBACK' not in log.log
    assert _names(c) >= {'alpha', 'beta'}
    assert _pragma(c) == 2
    assert not (tmp_path / 'backups').exists()


def test_g7_the_backup_hook_runs_once_with_the_endpoints_before_any_write(request,
                                                                          tmp_path):
    # migrate.py:72-73 (`pending and have > 0 and before is not None` -> `before(have,
    # latest)`) against the docstring's "runs once before anything is applied". The
    # existing ordering test monkeypatches backup.before_migration behind
    # Database.open and only checks that nothing is APPLIED when the hook raises, so
    # it never looks at how often the hook ran or with what numbers: moving the call
    # into the loop at 74 (one backup per step, named (1,2) then (2,3)) or handing it
    # (target, latest) keeps that test green.
    base = _dir(tmp_path, 'base', {'0001_init.sql': INIT})
    c = _db(request, tmp_path)
    assert migrate.migrate(c, directory=base) == 1
    three = _dir(tmp_path, 'm', {'0001_init.sql': INIT,
                                 '0002_second.sql': SECOND,
                                 '0003_third.sql': THIRD})
    log = _Log(c)
    calls = []

    def before(frm, to):
        calls.append((frm, to))
        assert len(log.log) == 1                       # only the line-67 read so far
        assert 'BEGIN IMMEDIATE' not in log.log        # nothing begun
        assert _pragma(c) == 1                         # and the file is still schema 1
        assert _names(c) == {'alpha'}

    assert migrate.migrate(log, directory=three, before=before) == 3
    assert calls == [(1, 3)]                           # once, with the ENDPOINTS
    assert log.log.index('BEGIN IMMEDIATE') >= 1       # the hook preceded the first lock
    assert _pragma(c) == 3


def test_g8_a_semicolon_inside_a_string_or_trigger_body_splits_nothing(request,
                                                                       tmp_path):
    # migrate.py:44-49 `if sqlite3.complete_statement(buf)` — the false arm while a
    # semicolon sits inside a string literal or a trigger body. The existing splitter
    # test only feeds it a plain statement and a comment, so a splitter that counted
    # semicolons would pass it and would run the inner `INSERT` of a trigger by
    # itself, leaving the trigger uncreated and the migration half applied.
    body = ("INSERT INTO t (v) VALUES ('a;b;c');\n"
            'CREATE TRIGGER trg AFTER INSERT ON t\n'
            'BEGIN\n'
            '  INSERT INTO log (v) VALUES (NEW.v);\n'
            'END;\n')
    assert migrate.statements("INSERT INTO t (v) VALUES ('a;b');\n") == [
        "INSERT INTO t (v) VALUES ('a;b');"]
    assert migrate.statements(body) == [
        "INSERT INTO t (v) VALUES ('a;b;c');",
        'CREATE TRIGGER trg AFTER INSERT ON t\nBEGIN\n'
        '  INSERT INTO log (v) VALUES (NEW.v);\nEND;'], 'the splitter cut a statement'
    two = _dir(tmp_path, 'm', {'0001_init.sql': INIT,
                               '0002_trigger.sql':
                                   'CREATE TABLE t (v TEXT);\nCREATE TABLE log (v TEXT);\n'
                                   + body})
    c = _db(request, tmp_path)
    assert migrate.migrate(c, directory=two) == 2                # one whole statement
    c.execute("INSERT INTO t (v) VALUES ('a;b')")
    assert [r[0] for r in c.execute('SELECT v FROM log')] == ['a;b']
    assert 'trg' in _names(c)
    assert _pragma(c) == 2


def test_g9_a_comment_tail_is_dropped_but_a_code_tail_is_unterminated():
    # migrate.py:50-52, both arms of `if buf.strip() and not all(...)` plus the
    # `[:80]` of the reported buffer. The existing
    # test_the_statement_splitter_refuses_an_unterminated_statement covers a comment
    # tail after a finished statement and a bare unterminated statement, so it never
    # mixes the two: with `all` turned into `any`, or the comment allowance deleted,
    # a trailing comment raises, and with the whole tail test inverted a half-written
    # statement is returned as if it had run.
    assert migrate.statements('CREATE TABLE a (x);\n-- a note\n-- another\n') == [
        'CREATE TABLE a (x);']
    with pytest.raises(migrate.MigrationError, match='unterminated statement'):
        migrate.statements('CREATE TABLE a (x);\n-- a note\nCREATE TABLE b (y)')
    wide = 'CREATE TABLE wide (' + ', '.join('c%d TEXT' % i for i in range(40))
    with pytest.raises(migrate.MigrationError) as big:
        migrate.statements(wide)
    msg = str(big.value)
    assert repr(wide[:80]) in msg                     # what it refused is reportable
    assert 'c39 TEXT' not in msg                      # and reported up to 80 characters
    assert msg.startswith('unterminated statement: ')


# ── error paths ─────────────────────────────────────────────────────────────


def test_g10_a_commit_failure_is_reported_once_and_the_loop_stops(request, tmp_path):
    # migrate.py:84-87 `except sqlite3.Error as e: if conn.in_transaction:
    # conn.execute('ROLLBACK'); raise MigrationError(...) from e`, the FALSE arm of
    # the rollback guard: a migration script that commits itself ends the
    # transaction, so the code's own `COMMIT` at line 83 fails with nothing open.
    # The existing test_a_failed_migration_rolls_back_whole_and_recreates_nothing
    # fails a CREATE TABLE INSIDE the transaction, where in_transaction is True, so
    # an unconditional ROLLBACK here passes it and turns this case into "cannot
    # rollback - no transaction is active" raised from the handler, replacing the
    # caller's MigrationError with a bare sqlite3 error. Delete the `raise` and this
    # test fails too: 0003 would then run on top of a half-finished 0002.
    base = _dir(tmp_path, 'base', {'0001_init.sql': INIT})
    c = _db(request, tmp_path)
    assert migrate.migrate(c, directory=base) == 1
    three = _dir(tmp_path, 'm', {'0001_init.sql': INIT,
                                 '0002_self.sql': 'CREATE TABLE beta (id TEXT);\nCOMMIT;\n',
                                 '0003_third.sql': THIRD})
    log = _Log(c)
    with pytest.raises(migrate.MigrationError, match='0002_self.sql failed') as e:
        migrate.migrate(log, directory=three)
    assert isinstance(e.value.__cause__, sqlite3.OperationalError)     # migrate.py:87
    assert 'ROLLBACK' not in log.log                          # nothing was open to roll back
    assert 'CREATE TABLE gamma (id TEXT PRIMARY KEY);' not in log.log  # 0003 never ran
    assert 'gamma' not in _names(c)
    assert log.log.count('COMMIT;') == 1                        # the script's own
    assert log.log.count('COMMIT') == 1                         # ours, the one that failed
    assert not (tmp_path / 'backups').exists()
    # Reported, not asserted away: because the script committed itself, beta and the
    # `PRAGMA user_version = 2` at line 82 sit outside any transaction this code owns,
    # which is the one place lines 6-9's "leaves neither its tables nor its version
    # behind" does not hold. Nothing in this test depends on which way that goes.

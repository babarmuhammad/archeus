"""T-1456: gap probes for archeus/infra/db/migrate.py lines 22-88 that the existing
migrate tests do not assert: the no-op re-run, an empty directory on a fresh
database, and an unterminated statement inside a migration. A real sqlite3
connection on tmp_path; no source file is edited.
"""

import sqlite3

import pytest

from archeus.infra.db import migrate

INIT = 'CREATE TABLE alpha (id TEXT PRIMARY KEY);\n'


def _dir(tmp_path, name, files):
    d = tmp_path / name
    d.mkdir()
    for fname, sql in files.items():
        (d / fname).write_text(sql, encoding='utf-8')
    return str(d)


@pytest.fixture
def conn(tmp_path):
    c = sqlite3.connect(str(tmp_path / 'probe.db'), isolation_level=None)
    yield c
    c.close()


def test_a_database_already_at_latest_is_not_backed_up_and_returns_latest(tmp_path, conn):
    # migrate.py:71-72 pending is empty, so `before` is not called; :88 returns latest
    base = _dir(tmp_path, 'base', {'0001_init.sql': INIT})
    assert migrate.migrate(conn, directory=base) == 1
    calls = []
    assert migrate.migrate(conn, directory=base, before=lambda f, t: calls.append((f, t))) == 1
    assert calls == []
    assert migrate.version(conn) == 1


def test_an_empty_directory_on_a_fresh_database_returns_zero_and_writes_nothing(tmp_path, conn):
    # migrate.py:65-66 no steps gives latest 0; :67 have 0 is not above it; :88 returns 0
    empty = _dir(tmp_path, 'empty', {})
    assert migrate.migrate(conn, directory=empty) == 0
    assert migrate.version(conn) == 0
    assert conn.in_transaction is False


def test_an_unterminated_statement_inside_a_migration_is_refused_and_the_version_stays(tmp_path, conn):
    # migrate.py:80 statements() raises MigrationError; the version write at :82 is
    # never reached, so user_version keeps the previous value
    base = _dir(tmp_path, 'base', {'0001_init.sql': INIT})
    assert migrate.migrate(conn, directory=base) == 1
    bad = _dir(tmp_path, 'bad', {'0001_init.sql': INIT,
                                 '0002_open.sql': 'CREATE TABLE beta (id TEXT)'})
    with pytest.raises(migrate.MigrationError, match='unterminated statement'):
        migrate.migrate(conn, directory=bad)
    assert migrate.version(conn) == 1


def test_an_unterminated_statement_inside_a_migration_leaves_no_transaction_open(tmp_path, conn):
    base = _dir(tmp_path, 'base', {'0001_init.sql': INIT})
    assert migrate.migrate(conn, directory=base) == 1
    bad = _dir(tmp_path, 'bad', {'0001_init.sql': INIT,
                                 '0002_open.sql': 'CREATE TABLE beta (id TEXT)'})
    with pytest.raises(migrate.MigrationError):
        migrate.migrate(conn, directory=bad)
    assert conn.in_transaction is False

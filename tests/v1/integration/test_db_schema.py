"""The database file, its settings, its schema and its migrations (P2)."""

import ast
import os
import re
import sqlite3
import subprocess
import sys

import pytest

from archeus.infra.db import Database, backup, connection, migrate, rows

from .conftest import ROOT

ARCHEUS = os.path.join(ROOT, 'archeus')


def _pragma(conn, name):
    return conn.execute('PRAGMA %s' % name).fetchone()[0]


# ── location and lifecycle ──

def test_the_database_lives_at_archeus_home(archeus_home, db):
    assert db.path == os.path.join(str(archeus_home), 'archeus.db')
    assert os.path.isfile(db.path)
    legacy = os.path.join(os.path.expanduser('~'), '.archeus')
    assert not os.path.normcase(db.path).startswith(os.path.normcase(legacy))


def test_importing_the_persistence_modules_creates_nothing(tmp_path):
    home = tmp_path / 'untouched'
    probe = ('import sys; sys.path.insert(0, %r)\n'
             'import archeus.infra.db, archeus.infra.eventlog.outbox, '
             'archeus.infra.eventlog.consumers, archeus.infra.eventlog.retention, '
             'archeus.infra.artifacts.store, archeus.core.application.commands, '
             'archeus.core.application.queries, archeus.core.application.work, '
             'archeus.core.engine\n' % ROOT)
    r = subprocess.run([sys.executable, '-c', probe], capture_output=True, text=True,
                       env=dict(os.environ, ARCHEUS_HOME=str(home)), timeout=60)
    assert r.returncode == 0, r.stderr
    assert not home.exists()


# ── SQLite version and portability ──

def test_sqlite_older_than_3_31_is_refused(archeus_home, monkeypatch):
    with pytest.raises(connection.SQLiteTooOld):
        connection.require_sqlite((3, 30, 1))
    connection.require_sqlite((3, 31, 0))
    monkeypatch.setattr(sqlite3, 'sqlite_version_info', (3, 30, 0))
    with pytest.raises(connection.SQLiteTooOld):
        Database.open()
    assert not os.path.exists(connection.db_path())


#: Features newer than SQLite 3.31, or absent from some 3.31 builds (json1).
POST_331 = re.compile(r'\bRETURNING\b|\bSTRICT\b|\bjson_\w+\(|->>|\bunixepoch\b|'
                      r'\bDROP\s+COLUMN\b|\bMATERIALIZED\b', re.I)
_SQL_START = re.compile(r'\s*(SELECT|INSERT|UPDATE|DELETE|CREATE|ALTER|DROP|PRAGMA|WITH)\b')


def _sql_texts():
    for d, _s, files in os.walk(ARCHEUS):
        for f in files:
            p = os.path.join(d, f)
            if f.endswith('.sql'):
                text = open(p, encoding='utf-8').read()
                yield p, re.sub(r'--[^\n]*', '', text)
            elif f.endswith('.py'):
                for node in ast.walk(ast.parse(open(p, encoding='utf-8').read())):
                    if isinstance(node, ast.Constant) and isinstance(node.value, str) \
                            and _SQL_START.match(node.value):
                        yield p, node.value


def test_the_schema_and_queries_stay_within_sqlite_3_31():
    texts = list(_sql_texts())
    assert len(texts) >= 20, 'the SQL scan found almost nothing to check'
    bad = ['%s: %s' % (os.path.relpath(p, ROOT), m.group(0))
           for p, t in texts for m in [POST_331.search(t)] if m]
    assert not bad, bad


# ── settings that are architectural invariants ──

def test_every_connection_carries_the_architectural_pragmas(db):
    with db.read() as r:
        assert _pragma(r, 'journal_mode') == 'wal'
        assert _pragma(r, 'foreign_keys') == 1
        assert _pragma(r, 'synchronous') == 2            # FULL
        assert _pragma(r, 'busy_timeout') == connection.BUSY_TIMEOUT_MS
        assert _pragma(r, 'query_only') == 1
        assert r.isolation_level is None


def test_a_read_connection_cannot_write(db):
    with db.read() as r:
        with pytest.raises(sqlite3.OperationalError, match='readonly'):
            r.execute("INSERT INTO consumer_cursors VALUES ('x', 0, 'now')")


def test_only_two_modules_open_sqlite_and_only_writer_commands_write_sql():
    """Structural single-writer gate: a connection is opened by connection.py
    (and by backup.py for backup FILES), and every INSERT/UPDATE/DELETE sits in
    a module whose functions run on the writer thread through a Tx."""
    opens, writes = set(), set()
    for d, _s, files in os.walk(ARCHEUS):
        for f in files:
            if f.endswith('.py'):
                p = os.path.join(d, f)
                rel = os.path.relpath(p, ARCHEUS).replace(os.sep, '/')
                src = open(p, encoding='utf-8').read()
                if 'sqlite3.connect(' in src:
                    opens.add(rel)
                if re.search(r'\b(INSERT INTO|UPDATE \w+ SET|DELETE FROM)\b', src):
                    writes.add(rel)
    assert opens == {'infra/db/connection.py', 'infra/db/backup.py'}
    assert writes == {'infra/db/writer.py', 'infra/eventlog/consumers.py',
                      'infra/eventlog/retention.py'}


# ── schema ──

def test_a_fresh_database_reaches_the_current_schema(db):
    with db.read() as r:
        assert migrate.version(r) == migrate.migrations()[-1][0] == 8
        tables = {x[0] for x in r.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {'principals', 'devices', 'tokens', 'missions', 'events', 'consumer_cursors',
            'consumer_effects', 'idempotency_keys',
            'plans', 'tasks', 'executions', 'verifications', 'reviews',
            'users', 'projects', 'repositories', 'repository_inspections',
            'knowledge_items', 'context_packages', 'relations', 'meetings', 'feedback',
            'route_decisions', 'usage_ledger', 'provider_terms',
            'conversations', 'messages', 'intents', 'ideas',
            'policy_rules', 'policy_decisions', 'approvals'} <= tables


def test_every_persisted_entity_table_has_the_row_shape(db):
    with db.read() as r:
        for cls, name in rows.TABLES.items():
            cols = rows.columns(r, name)
            assert set(rows.META) | {'id', 'body'} <= set(cols), name
            field_names = {f for f in cls.__dataclass_fields__}
            assert not field_names & (set(rows.META) | {'body'}), cls.__name__
            if 'state' in field_names:
                assert 'state' in cols, '%s.state must be a column' % name


def test_no_entity_field_can_collide_with_row_metadata():
    """Checked for EVERY entity, not only the persisted ones, so a clash is
    found before the entity gets a table (Plan's own number is `plan_version`).
    The one known clash, KnowledgeItem's `body`, was resolved when P4 gave it
    a table: the field is `text` (domain-model §5.1)."""
    from archeus.core.domain import entities
    clashes = {cls.__name__: set(cls.__dataclass_fields__) & (set(rows.META) | {'body'})
               for cls in entities.ENTITIES}
    assert {k: v for k, v in clashes.items() if v} == {}
    assert entities.KnowledgeItem in rows.TABLES
    assert 'plan_version' in entities.Plan.__dataclass_fields__


def test_events_seq_is_autoincrement(db):
    with db.read() as r:
        ddl = r.execute("SELECT sql FROM sqlite_master WHERE name='events'").fetchone()[0]
    assert re.search(r'seq\s+INTEGER PRIMARY KEY AUTOINCREMENT', ddl)


# ── migrations ──

def _open(path, d):
    return Database.open(str(path), migrations_dir=str(d))


def _version(path):
    c = sqlite3.connect(str(path))
    try:
        return c.execute('PRAGMA user_version').fetchone()[0]
    finally:
        c.close()


def test_migrations_are_numbered_contiguously(migrations_dir):
    (migrations_dir / '0003_later.sql').write_text('CREATE TABLE later (x);')
    with pytest.raises(migrate.MigrationError, match='gap'):
        migrate.migrations(str(migrations_dir))


def test_an_existing_database_migrates_forward_and_keeps_its_data(tmp_path, migrations_dir,
                                                                   actor):
    from archeus.core.application import commands
    path = tmp_path / 'db' / 'archeus.db'
    d = _open(path, migrations_dir)
    m = d.writer.execute(commands.create_mission,
                         {'actor': actor, 'title': 'kept', 'objective': 'o'})
    d.close()
    assert _version(path) == 1
    (migrations_dir / '0002_extra.sql').write_text(
        '-- a later phase\nCREATE TABLE extra (id TEXT PRIMARY KEY);\n'
        'CREATE INDEX extra_id ON extra (id);\n')
    d = _open(path, migrations_dir)
    try:
        with d.read() as r:
            assert migrate.version(r) == 2
            assert r.execute('SELECT id FROM missions').fetchone()[0] == m['id']
            r.execute('SELECT * FROM extra')
    finally:
        d.close()
    # the pre-migration backup holds the schema-1 database, under its own name
    snaps = os.listdir(backup.backups_dir(str(tmp_path / 'db')))
    assert len(snaps) == 1
    got = backup.MIGRATION_PATTERN.fullmatch(snaps[0])
    assert got and got.group(1, 2) == ('1', '2') and not backup.PATTERN.fullmatch(snaps[0])
    assert _version(tmp_path / 'db' / 'backups' / snaps[0]) == 1


def _add_0002(migrations_dir, sql='CREATE TABLE extra (id TEXT PRIMARY KEY);\n'):
    (migrations_dir / '0002_extra.sql').write_text(sql)


def test_a_migration_never_replaces_a_same_day_backup(tmp_path, migrations_dir, actor):
    """The daily backup and the pre-migration backup share a folder and a day;
    the migration's must not overwrite the daily one."""
    from archeus.core.application import commands
    path = tmp_path / 'archeus.db'
    d = _open(path, migrations_dir)
    d.writer.execute(commands.create_mission, {'actor': actor, 'title': 't', 'objective': 'o'})
    folder = backup.backups_dir(str(tmp_path))
    with d.read() as r:
        daily = backup.daily(r, folder)
    d.writer.execute(commands.create_mission, {'actor': actor, 'title': 'u', 'objective': 'o'})
    d.close()
    before = open(daily, 'rb').read()
    _add_0002(migrations_dir)
    _open(path, migrations_dir).close()
    assert open(daily, 'rb').read() == before              # the daily backup survived
    snaps = sorted(os.listdir(folder))
    assert len(snaps) == 2 and os.path.basename(daily) in snaps
    mig = next(f for f in snaps if backup.MIGRATION_PATTERN.fullmatch(f))
    c = sqlite3.connect(os.path.join(folder, mig))
    try:                                                   # it is the pre-migration state
        assert c.execute('PRAGMA user_version').fetchone()[0] == 1
        assert c.execute('SELECT COUNT(*) FROM missions').fetchone()[0] == 2
    finally:
        c.close()


def test_migration_backups_never_collide_and_never_overwrite(db, tmp_path):
    from datetime import datetime, timezone
    folder = str(tmp_path / 'backups')
    now = datetime(2026, 9, 24, 12, 0, 0, tzinfo=timezone.utc)
    with db.read() as r:
        first = backup.before_migration(r, folder, 1, 2, now=now)
        stamp = os.stat(first).st_mtime_ns, open(first, 'rb').read()
        second = backup.before_migration(r, folder, 1, 2, now=now)   # same second
        with pytest.raises(FileExistsError):
            backup.backup(r, first, replace=False)
    assert first != second and backup.MIGRATION_PATTERN.fullmatch(os.path.basename(second))
    assert (os.stat(first).st_mtime_ns, open(first, 'rb').read()) == stamp
    assert sorted(os.listdir(folder)) == sorted(map(os.path.basename, (first, second)))


def test_the_backup_is_taken_before_any_migration_work(tmp_path, migrations_dir,
                                                       monkeypatch):
    path = tmp_path / 'archeus.db'
    _open(path, migrations_dir).close()
    _add_0002(migrations_dir)

    def refuse(*a, **k):
        raise OSError('disk full')
    monkeypatch.setattr(backup, 'before_migration', refuse)
    with pytest.raises(OSError, match='disk full'):
        _open(path, migrations_dir)
    assert _version(path) == 1                             # no backup, no migration
    c = sqlite3.connect(str(path))
    try:
        assert 'extra' not in {x[0] for x in c.execute('SELECT name FROM sqlite_master')}
    finally:
        c.close()


def test_migrating_twice_applies_nothing_twice(tmp_path, migrations_dir):
    path = tmp_path / 'archeus.db'
    for _ in range(3):
        _open(path, migrations_dir).close()
    assert _version(path) == 1
    assert not (tmp_path / 'backups').exists()      # nothing pending, nothing backed up
    c = connection.connect(str(path))
    try:
        assert migrate.migrate(c, directory=str(migrations_dir)) == 1
    finally:
        c.close()


def test_a_failed_migration_rolls_back_whole_and_recreates_nothing(tmp_path, migrations_dir,
                                                                   actor):
    from archeus.core.application import commands
    path = tmp_path / 'archeus.db'
    d = _open(path, migrations_dir)
    d.writer.execute(commands.create_mission, {'actor': actor, 'title': 't', 'objective': 'o'})
    d.close()
    (migrations_dir / '0002_broken.sql').write_text(
        'CREATE TABLE half_done (x);\nCREATE TABLE principals (x);\n')   # 2nd one fails
    with pytest.raises(migrate.MigrationError, match='0002_broken'):
        _open(path, migrations_dir)
    assert _version(path) == 1
    c = sqlite3.connect(str(path))
    try:
        names = {x[0] for x in c.execute("SELECT name FROM sqlite_master")}
        assert 'half_done' not in names
        assert c.execute('SELECT COUNT(*) FROM missions').fetchone()[0] == 1
    finally:
        c.close()
    # the pre-migration backup outlives the failure, whole
    folder = backup.backups_dir(str(tmp_path))
    snaps = [f for f in os.listdir(folder) if backup.MIGRATION_PATTERN.fullmatch(f)]
    assert len(snaps) == 1
    c = sqlite3.connect(os.path.join(folder, snaps[0]))
    try:
        assert c.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert c.execute('PRAGMA user_version').fetchone()[0] == 1
        assert c.execute('SELECT COUNT(*) FROM missions').fetchone()[0] == 1
    finally:
        c.close()


def test_a_database_from_a_newer_archeus_is_refused(tmp_path, migrations_dir):
    path = tmp_path / 'archeus.db'
    _open(path, migrations_dir).close()
    c = sqlite3.connect(str(path))
    c.execute('PRAGMA user_version = 99')
    c.close()
    with pytest.raises(migrate.SchemaTooNew, match='99'):
        _open(path, migrations_dir)
    assert _version(path) == 99                      # never downgraded


def test_the_statement_splitter_refuses_an_unterminated_statement():
    assert migrate.statements('-- c\nCREATE TABLE a (x);\n-- tail\n') == [
        '-- c\nCREATE TABLE a (x);']
    with pytest.raises(migrate.MigrationError):
        migrate.statements('CREATE TABLE a (x)')

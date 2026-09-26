"""Schema migrations: `migrations/NNNN_name.sql`, tracked by `PRAGMA user_version`.

- Ordered and contiguous: 0001, 0002, … — a gap or a duplicate number is an
  error before anything runs.
- One transaction per migration, and `user_version` is set INSIDE it: SQLite
  DDL is transactional and so is the header write, so a migration that fails
  half-way leaves neither its tables nor its version behind.
- Re-checked under the write lock: a second process that raced this one finds
  the version already moved and applies nothing twice.
- Forward only. A database newer than this code is refused, never downgraded,
  and a failed migration is reported, never answered by recreating the file.
"""

import os
import re
import sqlite3

MIGRATIONS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'migrations')
_NAME = re.compile(r'(\d{4})_[a-z0-9_]+\.sql')


class MigrationError(RuntimeError):
    pass


class SchemaTooNew(MigrationError):
    """The database was written by a newer Archeus."""


def migrations(directory=None):
    """[(version, filename, sql)] in order."""
    directory = directory or MIGRATIONS_DIR
    found = sorted((int(m.group(1)), f) for f in os.listdir(directory)
                   for m in [_NAME.fullmatch(f)] if m)
    if [v for v, _f in found] != list(range(1, len(found) + 1)):
        raise MigrationError('migrations must be numbered 0001.. with no gap or '
                             'duplicate: %s' % [f for _v, f in found])
    return [(v, f, open(os.path.join(directory, f), encoding='utf-8').read())
            for v, f in found]


def statements(sql):
    """Split a script into complete statements (sqlite3 decides where one ends)."""
    out, buf = [], ''
    for line in sql.splitlines(keepends=True):
        buf += line
        if sqlite3.complete_statement(buf):
            out.append(buf.strip())
            buf = ''
    if buf.strip() and not all(ln.strip().startswith('--') or not ln.strip()
                               for ln in buf.splitlines()):
        raise MigrationError('unterminated statement: %r' % buf.strip()[:80])
    return out


def version(conn):
    return conn.execute('PRAGMA user_version').fetchone()[0]


def migrate(conn, *, directory=None, before=None):
    """Bring *conn* (the write connection) to the latest schema; returns the
    version. `before(from_version, to_version)` runs once before anything is
    applied to a database that already has a schema — the pre-migration backup;
    if it raises, nothing is applied."""
    steps = migrations(directory)
    latest = steps[-1][0] if steps else 0
    have = version(conn)
    if have > latest:
        raise SchemaTooNew('the database is at schema %d; this Archeus knows up to %d'
                           % (have, latest))
    pending = [s for s in steps if s[0] > have]
    if pending and have > 0 and before is not None:
        before(have, latest)
    for target, name, sql in pending:
        conn.execute('BEGIN IMMEDIATE')
        try:
            if version(conn) >= target:         # another process got here first
                conn.execute('ROLLBACK')
                continue
            for stmt in statements(sql):
                conn.execute(stmt)
            conn.execute('PRAGMA user_version = %d' % target)
            conn.execute('COMMIT')
        except sqlite3.Error as e:
            if conn.in_transaction:
                conn.execute('ROLLBACK')
            raise MigrationError('%s failed: %s' % (name, e)) from e
    return max(have, latest)

"""Opening a connection: the version gate and the pragmas, in one place.

Every connection to archeus.db is made by `connect()`, so every one gets the
same settings. Each non-default setting is architectural, not taste:

journal_mode=WAL   readers never block the writer and the writer never blocks
                   readers (ADR-0002); persistent in the file, set by the writer.
synchronous=FULL   a command is acknowledged only after COMMIT, and FULL makes
                   that commit survive power loss, not just a process crash
                   (NORMAL in WAL may roll back the last commits on power loss).
                   Measured on the dev box: ~2000 commits/s, against the plan's
                   500 commands/s floor.
foreign_keys=ON    off by default in SQLite and per connection, so it is set on
                   every one.
busy_timeout=5000  readers can still meet SQLITE_BUSY in WAL (recovery after an
                   unclean exit, a checkpoint restart); waiting briefly beats
                   failing a query.
query_only=ON      on every read connection: only the writer thread writes.
isolation_level=None
                   the sqlite3 module's implicit BEGIN is disabled; the writer
                   issues `BEGIN IMMEDIATE`/`COMMIT` itself, so what is one
                   transaction is decided in one visible place.

SQLite older than 3.31 is refused, and the schema uses nothing newer
(no RETURNING, no STRICT, no JSON functions — json1 is not in every 3.31 build).
"""

import os
import sqlite3

from .. import paths

MIN_SQLITE = (3, 31, 0)
DB_NAME = 'archeus.db'
BUSY_TIMEOUT_MS = 5000


class SQLiteTooOld(RuntimeError):
    pass


def require_sqlite(version=None):
    """Refuse a SQLite build older than MIN_SQLITE (plan §31.1 P2)."""
    got = tuple(sqlite3.sqlite_version_info if version is None else version)
    if got < MIN_SQLITE:
        raise SQLiteTooOld('Archeus needs SQLite %s or newer; this Python has %s'
                           % ('.'.join(map(str, MIN_SQLITE)), '.'.join(map(str, got))))


def db_path(home=None):
    """`<ARCHEUS_HOME>/archeus.db` — resolved at call time, like every V1 path."""
    return os.path.join(paths.archeus_home() if home is None else os.path.abspath(home),
                        DB_NAME)


def connect(path, *, readonly=False):
    """A connection with the architectural pragmas. Read connections are
    `query_only` and may be shared across threads by the pool that owns them
    (one thread at a time); the write connection belongs to the writer thread."""
    require_sqlite()
    conn = sqlite3.connect(path, isolation_level=None, check_same_thread=not readonly,
                           timeout=BUSY_TIMEOUT_MS / 1000)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA busy_timeout = %d' % BUSY_TIMEOUT_MS)
    conn.execute('PRAGMA foreign_keys = ON')
    conn.execute('PRAGMA synchronous = FULL')
    if readonly:
        conn.execute('PRAGMA query_only = ON')
    else:
        mode = conn.execute('PRAGMA journal_mode = WAL').fetchone()[0]
        if mode.lower() != 'wal':
            conn.close()
            raise RuntimeError('SQLite refused WAL mode for %s (got %r)' % (path, mode))
    return conn

"""The V1 database: `<ARCHEUS_HOME>/archeus.db` (target-architecture §5, ADR-0002).

connection  the version gate, the pragmas, the one place a connection opens
migrate     `PRAGMA user_version` migrations from migrations/NNNN_*.sql
writer      the single writer thread; the ONLY path that mutates the database
rows        entity <-> row codec and the reads every query shares
backup      `Connection.backup()` snapshots under `<ARCHEUS_HOME>/backups/`

Nothing here runs at import: a database exists once `Database.open()` is called.
"""

import contextlib
import os
import queue

from . import backup, connection, migrate
from .writer import Writer


class Database:
    """One open archeus.db: the writer thread plus a pool of read connections.

    `writer` is the only way to change anything. `read()` lends a `query_only`
    connection inside one read transaction, so everything a query sees comes
    from a single committed snapshot.
    """

    def __init__(self, path, writer):
        self.path = path
        self.writer = writer
        self._idle = queue.LifoQueue()
        self._closed = False

    @classmethod
    def open(cls, path=None, *, migrations_dir=None):
        """Open (creating if absent) and migrate. A database that already has a
        schema is backed up to `<home>/backups/migration-archeus-vA-to-vB-….db`
        before any migration runs; that name never collides with a daily backup
        or an earlier migration backup."""
        path = os.path.abspath(path or connection.db_path())
        os.makedirs(os.path.dirname(path), exist_ok=True)
        backups = backup.backups_dir(os.path.dirname(path))

        def open_write_conn():
            conn = connection.connect(path)
            try:
                migrate.migrate(conn, directory=migrations_dir,
                                before=lambda have, to: backup.before_migration(
                                    conn, backups, have, to))
            except BaseException:
                conn.close()
                raise
            return conn
        return cls(path, Writer(open_write_conn))

    @contextlib.contextmanager
    def read(self):
        if self._closed:
            raise RuntimeError('the database is closed')
        try:
            conn = self._idle.get_nowait()
        except queue.Empty:
            conn = connection.connect(self.path, readonly=True)
        try:
            conn.execute('BEGIN')
            try:
                yield conn
            finally:
                conn.execute('ROLLBACK')        # read-only: ending the snapshot
        finally:
            if self._closed:
                conn.close()
            else:
                self._idle.put(conn)

    def close(self, *, drain=True):
        """drain=False is the in-process stand-in for a kill: queued commands are
        failed, not run. (A real kill is tested with a child process.)"""
        self.writer.close(drain=drain)
        self._closed = True
        while True:
            try:
                self._idle.get_nowait().close()
            except queue.Empty:
                break

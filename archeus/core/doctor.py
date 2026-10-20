"""`archeus doctor` (P21 slice D, p21-design-gate D8, plan section 28).

It lives on Core's side of L1 (test_api_structure): the CLI only dispatches
here. It reads, and nothing else - it has to work with Core down, which is when
a doctor is wanted, so it opens the database itself, read-only at the file.
"""

import datetime as dt
import os
import sqlite3

from ..infra.db import connection, migrate
from .domain import states
from .execution import manager

#: exit codes, one bit per kind of finding (P21 D8)
DOCTOR_DB, DOCTOR_SCHEMA, DOCTOR_LAG, DOCTOR_STUCK, DOCTOR_HOOK = 1, 2, 4, 8, 16
LAG_WARN = 1000                 # events a consumer may trail by before it is a finding
STUCK_S = 6 * 3600              # an unfinished execution untouched this long is stuck


def doctor(now=None):
    """Read-only checks (plan section 28, p21-design-gate D8). It opens the
    database with `connection.inspect` (the file cannot be written; SQLite may
    leave its empty -wal/-shm sidecars beside it), never starts Core, never reads
    a credential and prints only ids, counts and paths."""
    code = 0

    def finding(bit, msg):
        nonlocal code
        code |= bit
        print('FINDING ' + msg)

    path = connection.db_path()
    if not os.path.isfile(path):
        finding(DOCTOR_DB, 'no database at %s (Core has never run here)' % path)
    else:
        conn = connection.inspect(path)
        try:
            check = [r[0] for r in conn.execute('PRAGMA integrity_check')]
            if check == ['ok']:
                print('database: integrity ok (%s)' % path)
            else:
                finding(DOCTOR_DB, 'database integrity: %s' % '; '.join(check[:5]))
            have, latest = migrate.version(conn), migrate.migrations()[-1][0]
            if have != latest:
                finding(DOCTOR_SCHEMA, 'schema %d, this Archeus expects %d%s' % (
                    have, latest, ' (Core migrates it when it starts)' if have < latest else ''))
            head = conn.execute('SELECT COALESCE(MAX(seq), 0) FROM events').fetchone()[0]
            for name, last in conn.execute('SELECT name, last_seq FROM consumer_cursors '
                                           'ORDER BY name'):
                if head - last > LAG_WARN:
                    finding(DOCTOR_LAG, 'consumer %s is %d events behind' % (name, head - last))
            print('consumers: checked against event %d' % head)
            now = now or dt.datetime.now(dt.timezone.utc)
            cutoff = (now - dt.timedelta(seconds=STUCK_S)).isoformat(
                timespec='milliseconds').replace('+00:00', 'Z')
            ended = tuple(states.terminal('execution'))
            for xid, state, at in conn.execute(
                    'SELECT id, state, updated_at FROM executions WHERE state NOT IN (%s) '
                    'AND updated_at < ? ORDER BY updated_at' % ','.join('?' * len(ended)),
                    ended + (cutoff,)):
                finding(DOCTOR_STUCK, 'execution %s %s since %s' % (xid, state, at))
        except sqlite3.DatabaseError as e:     # a malformed or torn file: the case doctor is for
            finding(DOCTOR_DB, 'database %s cannot be read: %s' % (path, e))
        finally:
            conn.close()
    try:
        with open(manager.HOOK, encoding='utf-8') as f:
            compile(f.read(), manager.HOOK, 'exec')
        print('hook: %s' % manager.HOOK)
    except (OSError, SyntaxError) as e:
        finding(DOCTOR_HOOK, 'the execution hook %s: %s' % (manager.HOOK, e))
    print('doctor: %s' % ('nothing found' if code == 0 else 'exit %d' % code))
    return code

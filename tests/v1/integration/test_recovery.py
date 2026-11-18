"""Restart, unclean termination, backup/restore and the artifact store (P2).

The crash tests kill a real child process with `os._exit` — no `finally`, no
close, no WAL checkpoint — at a deterministic point: after an acknowledged
commit, or inside a command's open transaction.
"""

import hashlib
import json
import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import pytest

from archeus.infra.artifacts import store
from archeus.infra.db import Database, backup, connection
from archeus.infra.eventlog import consumers, outbox

from .conftest import ROOT

CHILD = r'''
import json, os, sys
sys.path.insert(0, %(root)r)
from archeus.core.application import commands
from archeus.core.domain import ids
from archeus.core.domain.values import Ref
from archeus.infra.db import Database

mode = sys.argv[1]
db = Database.open()
actor = Ref('user_device', ids.new_id('principal'))
args = {'actor': actor, 'title': 'survivor', 'objective': 'o'}
if mode == 'after_commit':
    print(json.dumps(db.writer.execute(commands.create_mission, args)), flush=True)
    os._exit(9)
if mode == 'inside_transaction':
    def dies(tx, **kw):
        commands.create_mission(tx, **kw)
        print('written, not committed', flush=True)
        os._exit(9)
    db.writer.execute(dies, args)
'''


def _crash(archeus_home, mode):
    r = subprocess.run([sys.executable, '-c', CHILD % {'root': ROOT}, mode],
                       capture_output=True, text=True, timeout=60,
                       env=dict(os.environ, ARCHEUS_HOME=str(archeus_home)))
    assert r.returncode == 9, r.stderr
    return r.stdout.strip().splitlines()


def test_an_acknowledged_command_survives_a_kill(archeus_home):
    (line,) = _crash(archeus_home, 'after_commit')
    acked = json.loads(line)
    wal = connection.db_path() + '-wal'
    assert os.path.getsize(wal) > 0            # the commit is still only in the WAL
    d = Database.open()
    try:
        with d.read() as r:
            assert r.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
            m = r.execute('SELECT state FROM missions WHERE id = ?', (acked['id'],)).fetchone()
            assert m['state'] == 'CREATED'
            assert [e.seq for e in outbox.events_after(r, 0)] == [acked['seq']]
        # "kill between write and consumer": the consumer that never ran gets it now
        seen = []
        consumers.deliver(d, 'late', lambda e: seen.append(e.subject.id))
        assert seen == [acked['id']]
    finally:
        d.close()


def test_a_kill_inside_a_transaction_leaves_no_trace(archeus_home):
    assert _crash(archeus_home, 'inside_transaction') == ['written, not committed']
    d = Database.open()
    try:
        with d.read() as r:
            assert r.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
            assert r.execute('SELECT COUNT(*) FROM missions').fetchone()[0] == 0
            assert outbox.head(r) == 0
    finally:
        d.close()


def test_state_events_and_cursors_survive_a_clean_restart(archeus_home, actor):
    from archeus.core.application import commands
    d = Database.open()
    m = d.writer.execute(commands.create_mission, {'actor': actor, 'title': 't',
                                                   'objective': 'o'}, idempotency_key='k')
    consumers.deliver(d, 'c', lambda e: 'ok')
    d.close()
    d = Database.open()
    try:
        with d.read() as r:
            assert r.execute('SELECT COUNT(*) FROM missions').fetchone()[0] == 1
            assert consumers.cursor(r, 'c') == m['seq']
        again = d.writer.execute(commands.create_mission, {'actor': actor, 'title': 't',
                                                           'objective': 'o'},
                                 idempotency_key='k')
        assert again == m                          # the key outlived the restart
    finally:
        d.close()


# ── backups ──

def test_a_backup_restores_into_a_separate_database_intact(archeus_home, db, new_mission,
                                                           tmp_path):
    made = [new_mission('b%d' % i) for i in range(3)]
    with db.read() as r:
        before = outbox.events_after(r, 0)
    with db.read() as r:
        path = backup.daily(r, backup.backups_dir())
    assert os.path.dirname(path) == os.path.join(str(archeus_home), 'backups')
    new_mission('after the backup')               # the live database is unharmed
    with db.read() as r:
        assert r.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'

    restored = str(tmp_path / 'restored' / 'archeus.db')
    backup.restore(path, restored)
    d = Database.open(restored)
    try:
        with d.read() as r:
            assert outbox.events_after(r, 0) == before
            assert {x[0] for x in r.execute('SELECT id FROM missions')} == {m['id'] for m in made}
    finally:
        d.close()
    with pytest.raises(FileExistsError):
        backup.restore(path, restored)


def test_daily_backups_keep_the_newest_seven_and_nothing_else(db, tmp_path):
    folder = tmp_path / 'backups'
    folder.mkdir()
    (folder / 'notes.txt').write_text('mine')
    (folder / 'archeus-2026.db').write_text('not a daily name')
    day = datetime(2026, 9, 1, tzinfo=timezone.utc)
    with db.read() as r:
        mig = os.path.basename(backup.before_migration(r, str(folder), 1, 2, now=day))
        for i in range(9):
            backup.daily(r, str(folder), today=day + timedelta(days=i))
    kept = sorted(os.listdir(folder))
    assert kept == sorted(['archeus-202609%02d.db' % d for d in range(3, 10)]
                          + ['notes.txt', 'archeus-2026.db', mig])


def test_a_backup_is_a_real_database_not_a_torn_copy(db, new_mission, tmp_path):
    new_mission()
    with db.read() as r:
        path = backup.backup(r, str(tmp_path / 'b.db'))
    c = sqlite3.connect(path)
    try:
        assert c.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert c.execute('SELECT COUNT(*) FROM missions').fetchone()[0] == 1
    finally:
        c.close()
    assert not os.path.exists(path + '.tmp')


# ── artifacts ──

def test_artifacts_are_content_addressed_under_archeus_home(archeus_home):
    data = b'a checkpoint'
    sha = store.put(data)
    assert sha == hashlib.sha256(data).hexdigest()
    assert store.path_for(sha) == os.path.join(str(archeus_home), 'artifacts', sha[:2],
                                               sha[2:4], sha)
    assert store.get(sha) == data
    assert store.put(data) == sha                  # the same bytes are stored once
    with open(store.path_for(sha), 'wb') as f:
        f.write(b'tampered')
    with pytest.raises(ValueError, match='corrupt'):
        store.get(sha)
    for bad in ('../x', 'A' * 64, sha[:-1]):
        with pytest.raises(ValueError):
            store.path_for(bad)

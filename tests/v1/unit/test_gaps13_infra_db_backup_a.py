"""T-1455: the branches of `archeus/infra/db/backup.py` that
test_gaps_infra_db_backup.py leaves open: the home a backup directory is under
(backups_dir 36-37, never the real home), a stale temp file cleared for the
no-overwrite copy as well (backup 47-49), the daily prune's exact name match
against the names a user or a migration can also leave beside it (72-76), and
the message a keep below one carries (70-71). Backups go under tmp_path only.
"""

import os
import sqlite3
from contextlib import closing
from datetime import datetime, timezone

import pytest

from archeus.infra.db import backup


@pytest.fixture
def src(tmp_path):
    con = sqlite3.connect(str(tmp_path / 'src.db'))
    con.execute('CREATE TABLE t (x)')
    con.execute('INSERT INTO t VALUES (1)')
    con.commit()
    yield con
    con.close()


def _rows(path):
    with closing(sqlite3.connect(path)) as con:
        return con.execute('SELECT count(*) FROM t').fetchone()[0]


def test_backups_dir_is_backups_under_the_given_home_or_the_archeus_home(monkeypatch, tmp_path):
    """backup.py:36-37 — an explicit home is used as it is; None asks
    paths.archeus_home(), which is stubbed here so the real home is never read."""
    home = str(tmp_path / 'home')
    monkeypatch.setattr(backup.paths, 'archeus_home', lambda: home)
    assert backup.backups_dir(str(tmp_path / 'given')) == os.path.join(str(tmp_path / 'given'),
                                                                       'backups')
    assert backup.backups_dir() == os.path.join(home, 'backups')
    assert backup.backups_dir(None) == os.path.join(home, 'backups')


@pytest.mark.parametrize('replace', [True, False], ids=['replace', 'no-overwrite'])
def test_a_stale_temp_is_cleared_before_either_kind_of_copy(src, tmp_path, replace):
    """backup.py:47-49 — the crash debris is removed before the copy in both
    branches. The existing test covers only the default replace=True."""
    folder = tmp_path / 'bk'
    folder.mkdir()
    dest = str(folder / 'snap.db')
    with open(dest + '.tmp', 'wb') as f:
        f.write(b'debris from a killed writer')
    backup.backup(src, dest, replace=replace)
    assert not os.path.exists(dest + '.tmp')
    assert _rows(dest) == 1


def test_daily_prunes_only_names_that_fullmatch_the_daily_pattern(src, tmp_path):
    """backup.py:74-76 — `PATTERN.fullmatch`: a '.db.bak' copy of a daily, a
    migration backup and a note are never pruned, however old. Dropping the
    fullmatch for a search, or the anchor, would delete the first of these."""
    folder = tmp_path / 'bk'
    folder.mkdir()
    keep_names = ['archeus-20260101.db.bak', 'migration-archeus-v1-to-v2-20260101-000000.db',
                  'notes.txt']
    for name in ['archeus-20260101.db', 'archeus-20260102.db'] + keep_names:
        (folder / name).write_bytes(b'x')
    path = backup.daily(src, str(folder), today=datetime(2026, 1, 3, tzinfo=timezone.utc),
                        keep=1)
    assert sorted(os.listdir(str(folder))) == sorted(['archeus-20260103.db'] + keep_names)
    assert os.path.basename(path) == 'archeus-20260103.db'


@pytest.mark.parametrize('keep', [0, -1])
def test_a_keep_below_one_is_refused_and_names_the_value(src, tmp_path, keep):
    """backup.py:70-71 — the message names the value given, and nothing is taken
    or removed before the refusal."""
    folder = tmp_path / 'bk'
    folder.mkdir()
    (folder / 'archeus-20260101.db').write_bytes(b'older daily')
    with pytest.raises(ValueError, match='keep must be at least 1, got %d' % keep):
        backup.daily(src, str(folder), today=datetime(2026, 1, 3, tzinfo=timezone.utc),
                     keep=keep)
    assert sorted(os.listdir(str(folder))) == ['archeus-20260101.db']

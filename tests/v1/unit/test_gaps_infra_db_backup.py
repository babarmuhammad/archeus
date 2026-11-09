"""T-754: the highest-risk uncovered branches of `archeus/infra/db/backup.py`.

Fail-closed and denial paths first: the hard link is the real never-overwrite
guarantee of `replace=False`, so a lost race at the link must raise and must
leave the winner's file untouched; `before_migration` must step to the next
`-N` when the LINK (not the pre-check) collides; a taken name is never written;
after a thousand taken names the whole call refuses rather than returning
nothing; a snapshot that dies mid-way leaves no backup and no debris that can
poison the next one; and `restore` refuses an existing destination before it
reads anything at all. Then boundary values: the last migration suffix
(`-999`), the pruning slice at keep=1/3/4, the UTC clock when `today`/`now` is
not given, and the same-day daily retake through `os.replace`. Then the error
paths: pruning to keep=0 (xfail — see the test), restoring from a missing or
non-database source, and backup names that need URI escaping.

Real sqlite connections on `tmp_path`, as in tests/v1/integration/test_recovery.py
and test_db_schema.py (the closest existing tests of this module). The second
concurrent writer is injected at `os.link`, the call `backup.py` itself makes
(`os.link` is used bare by tests/v1/unit/test_repo_store.py too), so no thread,
no sleep and no assertion on OS-localised text is needed; the default-clock
branches replace the module's `datetime` name through the same
`monkeypatch.setattr(backup, ...)` seam test_db_schema.py:311 uses.
"""

import os
import sqlite3
from datetime import datetime, timezone

import pytest

from archeus.infra.db import backup


# ── helpers (no OS calls beyond sqlite3 and tmp_path) ──

@pytest.fixture
def conns(tmp_path):
    """Every connection this file opens is closed here, whatever the test does."""
    live = []

    def connect(path):
        c = sqlite3.connect(str(path))
        live.append(c)
        return c

    yield connect
    for c in live:
        c.close()


def _seed(conns, tmp_path, rows, name='src.db'):
    """A live source database holding *rows* missions (plain ASCII, no newlines)."""
    c = conns(tmp_path / name)
    c.execute('CREATE TABLE IF NOT EXISTS missions (id TEXT PRIMARY KEY, title TEXT)')
    c.executemany('INSERT INTO missions VALUES (?, ?)',
                  [('m%d' % i, 'title %d' % i) for i in range(rows)])
    c.commit()
    return c


def _add(conns, tmp_path, rows, first_index):
    """A second writer commits *rows* more rows into the same source file."""
    c = conns(tmp_path / 'src.db')
    c.executemany('INSERT INTO missions VALUES (?, ?)',
                  [('m%d' % i, 'title %d' % i)
                   for i in range(first_index, first_index + rows)])
    c.commit()
    return c


def _count(path):
    """integrity_check of a finished backup file, then its row count
    ('ok' is sqlite3's own English output, not OS-localised)."""
    c = sqlite3.connect(str(path))
    try:
        assert c.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        return c.execute('SELECT COUNT(*) FROM missions').fetchone()[0]
    finally:
        c.close()


def _mig_stem(now, frm=1, to=2):
    """The name format the module promises, restated here on purpose: a test
    that derived the name FROM the module could not catch the name changing."""
    return 'migration-archeus-v%d-to-v%d-%s' % (frm, to, now.strftime('%Y%m%d-%H%M%S'))


def _mig_name(stem, n):
    return stem + ('-%d' % n if n else '') + '.db'


def _freeze_clock(monkeypatch, instant):
    """Replace the backup module's `datetime` and record every now(tz) call."""
    seen = []

    class Frozen:
        @staticmethod
        def now(tz=None):
            seen.append(tz)
            return instant

    monkeypatch.setattr(backup, 'datetime', Frozen)
    return seen


class _Boom:
    """A source whose snapshot fails mid-way, the way a dying disk read does."""

    def __init__(self, exc):
        self.exc = exc

    def backup(self, target):
        raise self.exc


def _winner_writes(linked, target, watched, sentinel, fired, real_link):
    """Body of the racing `os.link`: the first link aimed at *watched* finds
    another writer's finished file already on the name, so the real link then
    raises FileExistsError exactly as a lost race against a real writer does."""
    if target == watched and not fired:
        fired.append(target)
        with open(target, 'wb') as f:
            f.write(sentinel)
    real_link(linked, target)


# ── fail-closed and denial paths ──

def test_replace_false_refuses_a_taken_name_without_touching_it(conns, tmp_path):
    """backup.py:45-46 — the pre-check denial; and the winner's bytes survive,
    which is what an os.replace inversion would destroy."""
    src = _seed(conns, tmp_path, 2)
    folder = tmp_path / 'bk'
    folder.mkdir()
    dest = folder / 'taken.db'
    sentinel = b'other writer finished this file first'
    dest.write_bytes(sentinel)
    with pytest.raises(FileExistsError):
        backup.backup(src, str(dest), replace=False)
    assert dest.read_bytes() == sentinel
    assert not os.path.exists(str(dest) + '.tmp')


def test_a_link_collision_never_overwrites_the_winning_writer(conns, tmp_path, monkeypatch):
    """backup.py:60-63 — the exists() check says free, another writer lands on
    the name before os.link does: FileExistsError must escape, the winner's file
    must stay byte-for-byte, and the tmp must still be removed by the finally."""
    src = _seed(conns, tmp_path, 3)
    folder = tmp_path / 'bk'
    folder.mkdir()
    dest = str(folder / 'race.db')
    sentinel = b'the winner wrote this file completely'
    fired = []
    real_link = os.link
    monkeypatch.setattr(os, 'link',
                        lambda linked, target: _winner_writes(linked, target, dest,
                                                              sentinel, fired, real_link))
    with pytest.raises(FileExistsError):
        backup.backup(src, dest, replace=False)
    assert fired == [dest]
    assert open(dest, 'rb').read() == sentinel
    assert not os.path.exists(dest + '.tmp')


def test_a_race_lost_at_the_link_retries_under_the_next_suffix(conns, tmp_path, monkeypatch):
    """backup.py:86-89 — before_migration must treat a LINK-time FileExistsError
    (not just the pre-check's) as 'name taken' and deliver a real snapshot under
    the next -N, without ever touching the file it lost to."""
    src = _seed(conns, tmp_path, 2)
    folder = tmp_path / 'bk'
    folder.mkdir()
    now = datetime(2026, 9, 24, 12, 0, 0, tzinfo=timezone.utc)
    first = str(folder / _mig_name(_mig_stem(now), 0))
    sentinel = b'winner'
    fired = []
    real_link = os.link
    monkeypatch.setattr(os, 'link',
                        lambda linked, target: _winner_writes(linked, target, first,
                                                              sentinel, fired, real_link))
    got = backup.before_migration(src, str(folder), 1, 2, now=now)
    assert os.path.basename(got) == _mig_name(_mig_stem(now), 1)
    assert fired == [first]
    assert open(first, 'rb').read() == sentinel          # never overwritten
    assert backup.MIGRATION_PATTERN.fullmatch(os.path.basename(got))
    assert _count(got) == 2                              # the retry is a real snapshot
    assert [f for f in os.listdir(str(folder)) if f.endswith('.tmp')] == []


def test_before_migration_gives_up_after_a_thousand_taken_names(conns, tmp_path):
    """backup.py:90 — every name taken: the call must FAIL (a migration whose
    backup silently went missing is the failure mode this refuses), and it must
    add nothing to the folder while trying."""
    src = _seed(conns, tmp_path, 1)
    folder = tmp_path / 'bk'
    folder.mkdir()
    now = datetime(2026, 9, 24, 12, 0, 0, tzinfo=timezone.utc)
    stem = _mig_stem(now)
    for n in range(1000):
        open(os.path.join(str(folder), _mig_name(stem, n)), 'wb').close()
    before = sorted(os.listdir(str(folder)))
    with pytest.raises(FileExistsError, match='no free migration backup name'):
        backup.before_migration(src, str(folder), 1, 2, now=now)
    assert sorted(os.listdir(str(folder))) == before


@pytest.mark.parametrize('kind', ['boom', 'closed'], ids=['boom', 'closed'])
def test_a_failed_snapshot_leaves_no_backup_and_keeps_the_old_one(conns, tmp_path, kind):
    """backup.py:51-54 — when source.backup dies mid-way (dead disk, dead
    source), no file may appear under the backup's name and an earlier backup
    at the same name must be byte-identical afterwards; the finally must still
    release the target so the next attempt can clear the scratch and succeed."""
    folder = tmp_path / 'bk'
    folder.mkdir()
    dest = str(folder / 'daily.db')
    good = _seed(conns, tmp_path, 1, name='good.db')
    backup.backup(good, dest)
    old = open(dest, 'rb').read()
    if kind == 'boom':
        dead = _Boom(sqlite3.OperationalError('disk I/O error'))
    else:
        dead = _seed(conns, tmp_path, 1, name='dead.db')
        dead.close()                                     # a source that died
    with pytest.raises(sqlite3.Error):
        backup.backup(dead, dest, replace=True)
    assert open(dest, 'rb').read() == old                # os.replace never ran
    later = _seed(conns, tmp_path, 1, name='later.db')
    backup.backup(later, dest, replace=True)             # the stale scratch is cleared
    assert not os.path.exists(dest + '.tmp')
    assert _count(dest) == 1


def test_a_stale_temp_file_from_a_crashed_writer_is_removed_first(conns, tmp_path):
    """backup.py:48-49 — the sequential form of the concurrent-writer race: a
    killed writer leaves `dest.tmp` debris; the next backup must remove it and
    produce a whole database, never adopt it."""
    src = _seed(conns, tmp_path, 2)
    folder = tmp_path / 'bk'
    folder.mkdir()
    dest = str(folder / 'd.db')
    with open(dest + '.tmp', 'wb') as f:
        f.write(b'truncated debris from a killed writer')
    path = backup.backup(src, dest)
    assert path == dest
    assert _count(dest) == 2
    assert not os.path.exists(dest + '.tmp')


def test_restore_refuses_an_existing_destination_before_reading_anything(tmp_path):
    """backup.py:96-97 — the destination check must come FIRST: even with a
    backup source that does not exist, the refusal is FileExistsError and the
    live file at dest is untouched."""
    dest = tmp_path / 'live.db'
    sentinel = b'a live database, must not be touched'
    dest.write_bytes(sentinel)
    with pytest.raises(FileExistsError, match='refusing to restore'):
        backup.restore(str(tmp_path / 'no-such-backup.db'), str(dest))
    assert dest.read_bytes() == sentinel


# ── boundary values ──

def test_the_last_free_migration_suffix_is_still_taken(conns, tmp_path):
    """backup.py:84-87 — with `-998` the last taken name, `-999` is still tried:
    catches range(1000) shrinking to range(999) (which would raise instead)."""
    src = _seed(conns, tmp_path, 1)
    folder = tmp_path / 'bk'
    folder.mkdir()
    now = datetime(2026, 9, 24, 12, 0, 0, tzinfo=timezone.utc)
    stem = _mig_stem(now)
    for n in range(999):
        open(os.path.join(str(folder), _mig_name(stem, n)), 'wb').close()
    got = backup.before_migration(src, str(folder), 1, 2, now=now)
    assert os.path.basename(got) == _mig_name(stem, 999)
    assert _count(got) == 1


def test_retaking_the_daily_the_same_day_refreshes_it(conns, tmp_path):
    """backup.py:55-56 and 70-71 — the day's second daily lands on an existing
    name: os.replace swaps it atomically for the newer snapshot (count goes
    1 -> 4), leaves no tmp, and still produces exactly one file."""
    src = _seed(conns, tmp_path, 1)
    folder = str(tmp_path / 'bk')
    today = datetime(2026, 5, 6, tzinfo=timezone.utc)
    first = backup.daily(src, folder, today=today)
    _add(conns, tmp_path, 3, 1)                          # another writer commits
    second = backup.daily(src, folder, today=today)
    assert first == second
    assert _count(second) == 4
    assert sorted(os.listdir(folder)) == ['archeus-20260506.db']


def test_daily_without_today_names_the_utc_day(conns, tmp_path, monkeypatch):
    """backup.py:70 — the default clock: today=None must stamp the day of
    datetime.now(timezone.utc), not of a local or naive now (a local clock could
    file yesterday's database under tomorrow's name)."""
    src = _seed(conns, tmp_path, 1)
    seen = _freeze_clock(monkeypatch, datetime(2026, 3, 4, 5, 6, 7, tzinfo=timezone.utc))
    folder = str(tmp_path / 'bk')                        # absent: daily creates it
    path = backup.daily(src, folder)
    assert os.path.basename(path) == 'archeus-20260304.db'
    assert seen == [timezone.utc]
    assert os.listdir(folder) == ['archeus-20260304.db']


def test_before_migration_without_now_stamps_the_utc_second(conns, tmp_path, monkeypatch):
    """backup.py:83 — the same default-clock branch on the migration side: a
    naive or local now() lands the second in the wrong name."""
    src = _seed(conns, tmp_path, 1)
    seen = _freeze_clock(monkeypatch, datetime(2026, 3, 4, 5, 6, 7, tzinfo=timezone.utc))
    folder = str(tmp_path / 'bk')
    path = backup.before_migration(src, folder, 1, 2)
    name = os.path.basename(path)
    assert name == _mig_name(_mig_stem(datetime(2026, 3, 4, 5, 6, 7, tzinfo=timezone.utc)), 0)
    assert backup.MIGRATION_PATTERN.fullmatch(name) and not backup.PATTERN.fullmatch(name)
    assert seen == [timezone.utc]
    assert _count(path) == 1


@pytest.mark.parametrize('keep', [1, 3, 4], ids=['keep1', 'keep3', 'keep_all_four'])
def test_pruning_leaves_exactly_the_newest_keep_dailies(conns, tmp_path, keep):
    """backup.py:72-74 — the slice at its boundaries: keep=1 drops everything
    but today, keep=3 drops exactly the oldest, keep=4 (== the number of names)
    drops nothing; names outside PATTERN are never pruned at any keep."""
    src = _seed(conns, tmp_path, 1)
    folder = tmp_path / 'bk'
    folder.mkdir()
    days = ['20260101', '20260102', '20260103']
    for day in days:
        (folder / ('archeus-%s.db' % day)).write_bytes(b'older daily')
    (folder / 'notes.txt').write_bytes(b'mine')
    today = backup.daily(src, str(folder), today=datetime(2026, 1, 4, tzinfo=timezone.utc),
                         keep=keep)
    kept = sorted(os.listdir(str(folder)))
    assert kept == sorted(['notes.txt'] + ['archeus-%s.db' % d
                                           for d in (days + ['20260104'])[len(days) + 1 - keep:]])
    assert _count(today) == 1


# ── error paths ──

@pytest.mark.xfail(strict=True,
                   reason='daily(keep=0) prunes nothing: names[:-keep] becomes names[:0] '
                          'when keep is 0, so every daily file survives a prune to the '
                          'newest zero (backup.py:73)')
def test_pruning_to_zero_removes_the_older_dailies(conns, tmp_path):
    """backup.py:73 — keep=0 must at least clear the days the caller refused to
    keep; today's own file is left out of the assertion so any correct fix
    (prune all, or refuse keep<1) turns this green."""
    src = _seed(conns, tmp_path, 1)
    folder = tmp_path / 'bk'
    folder.mkdir()
    for day in ('20260101', '20260102', '20260103'):
        (folder / ('archeus-%s.db' % day)).write_bytes(b'older daily')
    backup.daily(src, str(folder), today=datetime(2026, 1, 4, tzinfo=timezone.utc), keep=0)
    left = [f for f in os.listdir(str(folder))
            if backup.PATTERN.fullmatch(f) and f != 'archeus-20260104.db']
    assert left == []


@pytest.mark.parametrize('kind', ['missing', 'garbage'], ids=['missing', 'garbage'])
def test_restore_produces_nothing_from_a_source_that_is_not_a_database(conns, tmp_path, kind):
    """backup.py:98-103 — a missing read-only source fails at connect, forged
    bytes fail when the snapshot reads them; either way sqlite3.Error escapes
    (it must not be swallowed into a 'successful' empty restore) and no file
    appears at dest."""
    if kind == 'garbage':
        path = tmp_path / 'not-a-db.db'
        path.write_bytes(b'this is not a sqlite file' * 8)
    else:
        path = tmp_path / 'no-such-backup.db'
    dest = str(tmp_path / 'out' / 'new.db')
    with pytest.raises(sqlite3.Error):
        backup.restore(str(path), dest)
    assert not os.path.exists(dest)


@pytest.mark.parametrize('name', ['snap#shot.db', 'snap%shot.db', 'snap shot.db'],
                         ids=['hash', 'percent', 'space'])
def test_restore_reads_a_backup_name_that_needs_uri_escaping(conns, tmp_path, name):
    """backup.py:98-99 — '#' becomes a URI fragment and '%' a bad escape unless
    quote() runs; dropping safe='/:' would break the drive letter on Windows and
    the leading slash on Linux. All three names are legal on both platforms."""
    src = _seed(conns, tmp_path, 2)
    folder = tmp_path / 'bk'
    folder.mkdir()
    backup_path = folder / name
    backup.backup(src, str(backup_path))
    dest = str(tmp_path / 'out' / 'restored.db')
    backup.restore(str(backup_path), dest)
    assert _count(dest) == 2

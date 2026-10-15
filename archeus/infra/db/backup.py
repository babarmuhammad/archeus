"""Backups through SQLite's online backup API, never a file copy.

Copying `archeus.db` while Core runs can capture a torn file (the WAL holds
committed pages the main file does not have yet); `Connection.backup()` copies a
consistent snapshot under a read lock and never writes to the source. Each copy
is built under a temporary name and moved into place, so a crash mid-backup
never leaves a truncated file with a backup's name.

Two kinds, two names, under `<ARCHEUS_HOME>/backups/` (target-architecture §5):

daily      `archeus-YYYYMMDD.db`. Re-taking it the same day refreshes that day's
           file; `daily()` keeps the newest 7 and prunes only names matching
           `PATTERN`. What triggers it is the scheduler's job (a later phase).
migration  `migration-archeus-vA-to-vB-YYYYMMDD-HHMMSS[-N].db`, taken before a
           schema migration touches anything. It is created without ever
           replacing an existing file (a hard link from the finished temp copy,
           which fails if the name is taken — then the next `-N` is tried), it
           never matches `PATTERN`, so daily retention cannot delete it, and
           nothing here deletes it: a migration backup is kept until the user
           removes it.
"""

import os
import re
import sqlite3
import urllib.parse
from datetime import datetime, timezone

from .. import paths

KEEP = 7
PATTERN = re.compile(r'archeus-(\d{8})\.db')
MIGRATION_PATTERN = re.compile(r'migration-archeus-v(\d+)-to-v(\d+)-(\d{8}-\d{6})(-\d+)?\.db')


def backups_dir(home=None):
    return os.path.join(paths.archeus_home() if home is None else home, 'backups')


def backup(source, dest, *, replace=True):
    """Snapshot the database open on *source* (a sqlite3 connection) to *dest*.
    replace=False never overwrites: an existing *dest* raises FileExistsError,
    atomically (a hard link cannot land on a taken name)."""
    os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)
    if not replace and os.path.exists(dest):
        raise FileExistsError(dest)
    tmp = dest + '.tmp'
    if os.path.exists(tmp):
        os.remove(tmp)
    target = sqlite3.connect(tmp)
    try:
        source.backup(target)
    finally:
        target.close()
    if replace:
        os.replace(tmp, dest)
    else:
        # ponytail: needs hard links (NTFS/ext4/APFS); where they are missing the
        # backup fails loudly and a migration waiting on it does not run.
        try:
            os.link(tmp, dest)
        finally:
            os.remove(tmp)
    return dest


def daily(source, directory, *, today=None, keep=KEEP):
    """Today's `archeus-YYYYMMDD.db` in *directory*, then prune to the newest *keep*.
    Only files matching the daily backup name are ever removed."""
    day = (today or datetime.now(timezone.utc)).strftime('%Y%m%d')
    path = backup(source, os.path.join(directory, 'archeus-%s.db' % day))
    names = sorted(f for f in os.listdir(directory) if PATTERN.fullmatch(f))
    for old in names[:-keep]:
        os.remove(os.path.join(directory, old))
    return path


def before_migration(source, directory, from_version, to_version, *, now=None):
    """The pre-migration snapshot, under a name no other backup can have and
    never over an existing file. Returns its path."""
    stem = 'migration-archeus-v%d-to-v%d-%s' % (
        from_version, to_version,
        (now or datetime.now(timezone.utc)).strftime('%Y%m%d-%H%M%S'))
    for n in range(1000):
        dest = os.path.join(directory, stem + ('-%d' % n if n else '') + '.db')
        try:
            return backup(source, dest, replace=False)
        except FileExistsError:
            continue
    raise FileExistsError('no free migration backup name for %s' % stem)


def restore(backup_path, dest):
    """Materialise a backup as a new database file at *dest*. Refuses to
    overwrite anything: restoring over a live database is not a primitive."""
    if os.path.exists(dest):
        raise FileExistsError('refusing to restore over an existing file: %s' % dest)
    source = sqlite3.connect('file:%s?mode=ro' % urllib.parse.quote(
        os.path.abspath(backup_path).replace(os.sep, '/'), safe='/:'), uri=True)
    try:
        return backup(source, dest, replace=False)
    finally:
        source.close()

"""T-453: copy-only seeding and data import with a hardlink/reparse scan (audit slice 7).

Every destination is a fresh private tree written once (`xb`, no overwrite, no alias
followed): a path that does not exist, or a plain directory Core made and nothing has
been put in, because a launch needs its workspace to exist before it is seeded. And the injected *scan* — the shape of `linkscan.multi_linked_files`, one
root in, the relative paths it refuses out — runs on that tree after the copy and again
through `recheck`. A finding or a scan exception raises `SeedError` naming only the
relative path and removes nothing: this module holds no deletion primitive, so a
refused tree stays exactly as it was, for a human to look at.

UNVERIFIED: every check here precedes the act it guards and is not atomic against a
concurrent same-user writer on the host; the scan is the operator's, not ours.
"""

import hashlib
import os
import stat

from ..infra.paths import refused_component

_CHUNK = 1 << 20
_REPARSE = 0x400
_KINDS = {True: ('directory', (stat.S_IFDIR,)), False: ('file', (stat.S_IFREG,)),
          None: ('plain entry', (stat.S_IFDIR, stat.S_IFREG))}


class SeedError(OSError):
    """The seed or the import is refused or unsafe; nothing that exists is removed."""


def _rel(value):
    if not isinstance(value, str) or value == '':
        raise SeedError('not a relative path: %r' % (value,))
    if value.startswith('/'):
        raise SeedError('absolute path: %s' % value)
    if ':' in value or '\\' in value or '\x00' in value:
        raise SeedError('drive or UNC prefix: %s' % value)
    for part in value.split('/'):
        if part == '..':
            raise SeedError('parent segment: %s' % value)
        if refused_component(part):
            raise SeedError('refused path segment: %s' % value)
    return value


def _fold(rel):
    return os.path.normcase(rel).casefold()


def _root(dest_root):
    return os.path.abspath(os.fspath(dest_root))


def _under(root, rel):
    full = os.path.normpath(os.path.join(root, *rel.split('/')))
    prefix, marked = os.path.normcase(root), os.path.normcase(full)
    if marked != prefix and not marked.startswith(prefix + os.sep):
        raise SeedError('path escapes the destination: %s' % rel)
    return full


def _relative(root, path):
    return os.path.relpath(path, root).replace(os.sep, '/')


def _sig(st):
    return st.st_ino, st.st_dev, st.st_size, st.st_mtime_ns


def _alias(st):
    return stat.S_ISLNK(st.st_mode) or getattr(st, 'st_file_attributes', 0) & _REPARSE


def _source(src, rel):
    try:
        st = os.lstat(src)
    except OSError as err:
        raise SeedError('the source cannot be looked at: %s' % rel) from err
    if _alias(st):
        raise SeedError('an alias, never followed: %s' % rel)
    if not stat.S_ISREG(st.st_mode):
        raise SeedError('not a regular file: %s' % rel)
    return st


def _entry(path, rel, is_dir, missing_ok=False):
    try:
        st = os.lstat(path)
    except OSError as err:
        if missing_ok and isinstance(err, FileNotFoundError):
            return None
        raise SeedError('the destination cannot be looked at: %s' % rel) from err
    if _alias(st):
        raise SeedError('an alias appeared in the destination: %s' % rel)
    name, wanted = _KINDS[is_dir]
    if stat.S_IFMT(st.st_mode) not in wanted:
        raise SeedError('not the %s expected: %s' % (name, rel))
    return st


def _ancestors(path):
    """No directory above *path* up to the drive is an alias: a junction or link there
    redirects every write below it, and the checks of the entries themselves never see it."""
    ancestor = os.path.dirname(path)
    while ancestor != path:
        _entry(ancestor, 'an ancestor', True)
        path, ancestor = ancestor, os.path.dirname(ancestor)


def _list(directory, rel):
    try:
        return list(os.scandir(directory))
    except OSError as err:
        raise SeedError('the destination cannot be listed: %s' % rel) from err


def _sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(_CHUNK), b''):
            h.update(chunk)
    return h.hexdigest()


def _read(src):
    with open(src, 'rb') as f:
        for chunk in iter(lambda: f.read(_CHUNK), b''):
            yield chunk


def _copy(src, dst, rel):
    h = hashlib.sha256()
    try:
        out = open(dst, 'xb')
    except FileExistsError as err:
        raise SeedError('refusing to overwrite: %s' % rel) from err
    with out:
        for chunk in _read(src):
            h.update(chunk)
            out.write(chunk)
    try:
        written = _sha(dst)
    except OSError as err:
        raise SeedError('the copy cannot be read back: %s' % rel) from err
    if written != h.hexdigest():
        raise SeedError('copy differs from its source: %s' % rel)


def _make(root, rel, made):
    parts = rel.split('/')[:-1]
    for depth in range(len(parts)):
        below = '/'.join(parts[:depth + 1])
        current = _under(root, below)
        if os.path.normcase(current) in made:
            continue
        _entry(current, below, True, True)
        try:
            os.mkdir(current)
        except FileExistsError as err:
            raise SeedError('refusing to overwrite: %s' % below) from err
        made.add(os.path.normcase(current))


def _verify_tree(root):
    pending = [root]
    while pending:
        directory = pending.pop()
        for entry in _list(directory, _relative(root, directory)):
            rel = _relative(root, entry.path)
            st = _entry(entry.path, rel, None)
            if stat.S_ISDIR(st.st_mode):
                pending.append(entry.path)


def _scan(root, scan):
    try:
        found = list(scan(root))
    except SeedError:
        raise
    except Exception as err:
        raise SeedError('the scan raised, the tree stands untouched') from err
    if found:
        raise SeedError('the scan refused: %s' % found[0])


def _planned(source_files):
    if isinstance(source_files, (str, bytes)) or not hasattr(source_files, '__iter__'):
        raise SeedError('source files must be a mapping or a list of pairs')
    items = source_files.items() if hasattr(source_files, 'items') else source_files
    return _rows([(rel, src) for rel, src in items], None)


def _pairs(source_root, files):
    if isinstance(files, (str, bytes)) or not hasattr(files, '__iter__'):
        raise SeedError('files must be a list of relative paths')
    root = _root(source_root)
    return _rows([(rel, os.path.join(root, *rel.split('/'))) for rel in files], root)


def _rows(pairs, source_root):
    rows, seen = [], {}
    for rel, src in pairs:
        _rel(rel)
        src = os.path.abspath(os.fspath(src))
        _ancestors(src)
        if source_root is not None:
            prefix, marked = os.path.normcase(source_root), os.path.normcase(src)
            if not marked.startswith(prefix + os.sep):
                raise SeedError('path escapes the source: %s' % rel)
        key = _fold(rel)
        if key in seen:
            raise SeedError('the same destination twice: %s' % rel)
        seen[key] = rel
        rows.append((rel, src, _sig(_source(src, rel))))
    if not rows:
        raise SeedError('nothing to seed')
    return rows


def _fresh(dest_root, scan):
    """(root, whether it exists): an absent path, or a plain directory with nothing in it."""
    if not callable(scan):
        raise SeedError('no scan given')
    root = _root(dest_root)
    _ancestors(root)
    try:
        os.lstat(root)
    except FileNotFoundError:
        return root, False
    except OSError as err:
        raise SeedError('the destination cannot be looked at') from err
    _entry(root, '.', True)
    if _list(root, '.'):
        raise SeedError('the destination already exists and is not empty')
    return root, True


def _seed(rows, dest_root, scan):
    root, exists = _fresh(dest_root, scan)
    for rel, src, sig in rows:
        if _sig(_source(src, rel)) != sig:
            raise SeedError('changed while it was seeded: %s' % rel)
    if not exists:
        os.mkdir(root)
    _entry(root, '.', True)
    made = {os.path.normcase(root)}
    for rel, src, sig in rows:
        _make(root, rel, made)
        dst = _under(root, rel)
        if _sig(_source(src, rel)) != sig:
            raise SeedError('changed while it was copied: %s' % rel)
        _copy(src, dst, rel)
        # _copy's digest is of the bytes it read: a read that ended early matches itself
        if _entry(dst, rel, False).st_size != sig[2]:
            raise SeedError('copy differs from its source: %s' % rel)
    _verify_tree(root)
    _scan(dest_root, scan)
    return dest_root


def seed_copy(source_files, dest_root, scan):
    """*source_files* (a mapping or pairs of relative path -> source file) copied into a
    fresh private tree at *dest_root*, then scanned; nothing existing is touched."""
    return _seed(_planned(source_files), dest_root, scan)


def import_back(source_root, files, dest_root, scan):
    """The data-only way back: *files* (relative paths under *source_root*) copied into a
    fresh private tree at *dest_root*, then scanned; nothing existing is touched."""
    return _seed(_pairs(source_root, files), dest_root, scan)


def recheck(dest_root, scan):
    if not callable(scan):
        raise SeedError('no scan given')
    root = _root(dest_root)
    _entry(root, '.', True)
    _verify_tree(root)
    _scan(dest_root, scan)
    return dest_root

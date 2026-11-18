"""T-815: pins for archeus/node/linkscan.py, one per branch that no other test
would notice if it were inverted, removed or loosened (the verdict table is in
the card report). Every OS call stays on the module's own `os` seam, so nothing
here needs a hardlink, a reparse point, a network or a process: the fixtures are
bytes with explicit content, names without `?` or `:`, and no path is assumed to
be absolute. The walk is checked for receiving absolute paths, never compared to
one invented in the fixture.
"""

import os
import stat
from types import SimpleNamespace

import pytest

from archeus.node import linkscan

REPARSE_POINT = 0x400


class Refusal(Exception):
    """Stand-in grant error, the way StageError and MxcUnavailable are injected."""


class Boom(Exception):
    """A failure that is not the scan's, so `check_grants` must not rewrite it."""


def info(kind, nlink, attributes=0):
    return SimpleNamespace(st_mode=kind, st_nlink=nlink, st_file_attributes=attributes)


def fake_lstat(monkeypatch, by_name):
    """Answer with `by_name[entry name]` for the named entries, really for the rest.
    Matched on the name so the fixture works for a relative and an absolute walk."""
    real = os.lstat
    asked = []

    def lstat(path):
        key = os.fspath(path)
        asked.append(key)
        substitute = by_name.get(os.path.basename(key))
        return real(key) if substitute is None else substitute

    monkeypatch.setattr(linkscan.os, 'lstat', lstat)
    return asked


class Handle:
    """The `os.scandir` result the walk is allowed to hold: closed only if the walk
    uses it as a context manager, and iterable either way."""

    def __init__(self, walk, key, inner):
        self.walk, self.key, self.inner = walk, key, inner
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.closed = True
        self.walk.closed.append(self.key)
        return self.inner.__exit__(*exc)

    def __iter__(self):
        return iter(self.inner)


class Walk:
    """`os.scandir` under observation: every directory it opens is recorded, and a
    second visit or a forbidden path is a failure rather than a longer walk."""

    def __init__(self, forbidden=()):
        self.real = os.scandir
        self.forbidden = {os.path.basename(os.fspath(path)) for path in forbidden}
        self.opened = []
        self.closed = []
        self.handles = []

    def __call__(self, path):
        key = os.fspath(path)
        if os.path.basename(key) in self.forbidden:
            raise AssertionError('the walk entered a path it must never open: %s' % key)
        if key in self.opened:
            raise AssertionError('the walk opened the same directory twice: %s' % key)
        self.opened.append(key)
        handle = Handle(self, key, self.real(key))
        self.handles.append(handle)
        return handle


def test_relative_root_is_resolved_before_anything_is_stat_or_opened(tmp_path, monkeypatch):
    grant = tmp_path / 'grant'
    (grant / 'sub').mkdir(parents=True)
    (grant / 'sub' / 'dup').write_bytes(b'x')
    (grant / 'single').write_bytes(b'x')
    asked = fake_lstat(monkeypatch, {'dup': info(stat.S_IFREG, 2)})
    walk = Walk()
    monkeypatch.setattr(linkscan.os, 'scandir', walk)
    monkeypatch.chdir(tmp_path)
    assert linkscan.multi_linked_files('grant') == ['sub/dup']
    assert sorted(walk.opened) == sorted([os.path.abspath('grant'),
                                          os.path.abspath(os.path.join('grant', 'sub'))])
    assert all(os.path.isabs(path) for path in walk.opened + asked)


def test_every_directory_is_opened_exactly_once(tmp_path, monkeypatch):
    for name in ('d01', 'd02'):
        (tmp_path / name / 'inner').mkdir(parents=True)
        (tmp_path / name / 'inner' / 'leaf').write_bytes(b'x')
        (tmp_path / name / 'flat').write_bytes(b'x')
    fake_lstat(monkeypatch, {'leaf': info(stat.S_IFREG, 2)})
    walk = Walk()
    monkeypatch.setattr(linkscan.os, 'scandir', walk)
    assert linkscan.multi_linked_files(tmp_path) == ['d01/inner/leaf', 'd02/inner/leaf']
    assert len(walk.opened) == 5


def test_every_directory_handle_is_closed(tmp_path, monkeypatch):
    (tmp_path / 'sub').mkdir()
    (tmp_path / 'sub' / 'dup').write_bytes(b'x')
    fake_lstat(monkeypatch, {'dup': info(stat.S_IFREG, 2)})
    walk = Walk()
    monkeypatch.setattr(linkscan.os, 'scandir', walk)
    assert linkscan.multi_linked_files(tmp_path) == ['sub/dup']
    assert [handle.closed for handle in walk.handles] == [True, True]
    assert walk.closed == walk.opened


ALIASES_WITH_A_SECOND_NAME = {
    'reparse-file': info(stat.S_IFREG, 2, REPARSE_POINT),
    'symlink': info(stat.S_IFLNK, 2),
}


@pytest.mark.parametrize('alias', sorted(ALIASES_WITH_A_SECOND_NAME))
def test_alias_entry_is_skipped_even_when_it_carries_a_second_name(tmp_path, monkeypatch, alias):
    link = tmp_path / 'sub' / 'dup'
    link.parent.mkdir(parents=True)
    link.write_bytes(b'x')
    (tmp_path / 'plain').write_bytes(b'x')
    fake_lstat(monkeypatch, {'dup': ALIASES_WITH_A_SECOND_NAME[alias]})
    walk = Walk(forbidden=[link])
    monkeypatch.setattr(linkscan.os, 'scandir', walk)
    assert linkscan.multi_linked_files(tmp_path) == []


@pytest.mark.parametrize('kind', ['fifo', 'sock'])
def test_special_entry_is_never_reported_nor_opened_as_a_directory(tmp_path, monkeypatch, kind):
    odd = tmp_path / 'odd'
    odd.write_bytes(b'x')
    (tmp_path / 'sub').mkdir()
    fake_lstat(monkeypatch, {'odd': info(stat.S_IFIFO if kind == 'fifo' else stat.S_IFSOCK, 2)})
    walk = Walk(forbidden=[odd])
    monkeypatch.setattr(linkscan.os, 'scandir', walk)
    assert linkscan.multi_linked_files(tmp_path) == []


def test_check_grants_scans_every_root_it_is_given(tmp_path, monkeypatch):
    roots = [str(tmp_path / ('g%d' % index)) for index in range(3)]
    for root in roots:
        os.makedirs(os.path.join(root, 'sub'))
    seen = []
    monkeypatch.setattr(linkscan, 'multi_linked_files', lambda root: seen.append(root) or [])
    assert linkscan.check_grants(roots, Refusal) is None
    assert seen == roots


def test_check_grants_refuses_a_later_root_carrying_one_single_second_name(tmp_path, monkeypatch):
    clean = tmp_path / 'clean'
    (clean / 'ok').mkdir(parents=True)
    dirty = tmp_path / 'dirty'
    (dirty / 'dup').mkdir(parents=True)
    fake_lstat(monkeypatch, {'dup': info(stat.S_IFREG, 2)})
    with pytest.raises(Refusal) as caught:
        linkscan.check_grants((str(clean), str(dirty)), Refusal)
    assert str(caught.value) == 'multiple links in grant (a second name): dup'


def test_check_grants_refuses_the_first_offending_root_and_names_one_link(tmp_path, monkeypatch):
    first = tmp_path / 'a-first'
    (first / 'aaa').mkdir(parents=True)
    second = tmp_path / 'b-second'
    (second / 'bbb').mkdir(parents=True)
    fake_lstat(monkeypatch, {'aaa': info(stat.S_IFREG, 2), 'bbb': info(stat.S_IFREG, 3)})
    with pytest.raises(Refusal) as caught:
        linkscan.check_grants((str(first), str(second)), Refusal)
    assert str(caught.value) == 'multiple links in grant (a second name): aaa'
    assert str(tmp_path) not in str(caught.value)


@pytest.mark.parametrize('raised', [Boom, TypeError])
def test_check_grants_lets_an_unrelated_failure_through(tmp_path, monkeypatch, raised):
    def scan(root):
        raise raised('not a scan problem')

    monkeypatch.setattr(linkscan, 'multi_linked_files', scan)
    with pytest.raises(raised):
        linkscan.check_grants((str(tmp_path),), Refusal)


@pytest.mark.parametrize('kind', ['os-error', 'value-error'])
def test_check_grants_refusal_keeps_the_scan_failure_as_its_cause(tmp_path, monkeypatch, kind):
    cause = (PermissionError('denied by fixture') if kind == 'os-error'
             else ValueError('scan root must be a directory'))

    def scan(root):
        raise cause

    monkeypatch.setattr(linkscan, 'multi_linked_files', scan)
    with pytest.raises(Refusal) as caught:
        linkscan.check_grants((str(tmp_path),), Refusal)
    assert str(caught.value) == 'hardlink scan failed; grant refused'
    assert caught.value.__cause__ is cause
    assert str(tmp_path) not in str(caught.value)

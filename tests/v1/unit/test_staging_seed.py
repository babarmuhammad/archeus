"""T-804: the MXC execution folder is seeded, imported and rechecked through the
copy-only seed with the real hardlink scan; any refusal is a StageError.

No Windows API, no network, no process: a link or a reparse point is presented through
a faked `os.lstat`, a second name is a real `os.link` (skipped where the volume has none)."""

import hashlib
import os
import stat
from types import SimpleNamespace

import pytest

from archeus.node import seed, staging

FILES = {'one.txt': b'first\n', 'nested/two.bin': b'\x00\xff\xfe\x01binary'}


class Fake:
    def __init__(self, real, **fields):
        self._real, self._fields = real, fields

    def __getattr__(self, name):
        return self._fields[name] if name in self._fields else getattr(self._real, name)


def tree(root, files=FILES):
    for rel, data in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return {rel: str(root / rel) for rel in files}


@pytest.fixture
def src(tmp_path):
    return tree(tmp_path / 'src')


def lie_about(monkeypatch, victim, **fields):
    real = os.lstat

    def lstat(path, *args, **kwargs):
        st = real(path, *args, **kwargs)
        if os.path.basename(os.fspath(path)) == victim:
            return Fake(st, **fields)
        return st

    monkeypatch.setattr(os, 'lstat', lstat)


def test_seed_copies_bytes_to_new_inodes(src, tmp_path):
    dest = tmp_path / 'exec'
    assert staging.seed_execution(src, dest) == dest
    for rel, data in FILES.items():
        assert (dest / rel).read_bytes() == data
        assert os.stat(dest / rel).st_ino != os.stat(src[rel]).st_ino
        assert os.stat(dest / rel).st_nlink == 1


def test_seed_into_an_existing_folder_with_anything_in_it_refused(src, tmp_path):
    (tmp_path / 'exec').mkdir()
    (tmp_path / 'exec' / 'user.txt').write_bytes(b'user')
    with pytest.raises(staging.StageError, match='already exists'):
        staging.seed_execution(src, tmp_path / 'exec')
    assert os.listdir(tmp_path / 'exec') == ['user.txt']


def test_seed_fills_an_existing_empty_folder_and_scans_it_with_the_real_scan(src, tmp_path):
    dest = tmp_path / 'exec'
    dest.mkdir()
    assert staging.seed_execution(src, dest) == dest
    for rel, data in FILES.items():
        assert (dest / rel).read_bytes() == data
        assert os.stat(dest / rel).st_nlink == 1
    assert staging.recheck_execution(dest) == dest


def test_a_hardlink_in_the_folder_after_an_empty_folder_was_seeded_is_caught(
        src, tmp_path):
    dest = tmp_path / 'exec'
    dest.mkdir()
    staging.seed_execution(src, dest)
    try:
        os.link(dest / 'one.txt', tmp_path / 'outside.txt')
    except OSError:
        pytest.skip('no hardlinks on this volume')
    with pytest.raises(staging.StageError, match='scan refused: one.txt'):
        staging.recheck_execution(dest)


def test_seed_refuses_an_existing_folder_that_is_an_alias_and_writes_nothing(
        src, tmp_path, monkeypatch):
    dest = tmp_path / 'exec'
    dest.mkdir()
    lie_about(monkeypatch, 'exec', st_file_attributes=stat.FILE_ATTRIBUTE_REPARSE_POINT)
    with pytest.raises(staging.StageError, match='alias'):
        staging.seed_execution(src, dest)
    assert os.listdir(dest) == []


def test_seed_refuses_an_existing_folder_that_is_a_file(src, tmp_path):
    (tmp_path / 'exec').write_bytes(b'in the way')
    with pytest.raises(staging.StageError, match='not the directory expected'):
        staging.seed_execution(src, tmp_path / 'exec')


def test_import_back_fills_an_existing_empty_folder(seeded, tmp_path):
    back = tmp_path / 'back'
    back.mkdir()
    assert staging.import_results(seeded, ['one.txt'], back) == back
    assert (back / 'one.txt').read_bytes() == FILES['one.txt']


def test_seed_refuses_a_hardlinked_entry(src, tmp_path, monkeypatch):
    lie_about(monkeypatch, 'two.bin', st_nlink=2)
    with pytest.raises(staging.StageError, match='scan refused: nested/two.bin'):
        staging.seed_execution(src, tmp_path / 'exec')


def test_seed_refuses_a_symlinked_entry(src, tmp_path, monkeypatch):
    lie_about(monkeypatch, 'two.bin', st_mode=stat.S_IFLNK)
    with pytest.raises(staging.StageError, match='alias'):
        staging.seed_execution(src, tmp_path / 'exec')


def test_seed_refuses_a_reparse_entry(src, tmp_path, monkeypatch):
    lie_about(monkeypatch, 'one.txt', st_file_attributes=stat.FILE_ATTRIBUTE_REPARSE_POINT)
    with pytest.raises(staging.StageError, match='alias'):
        staging.seed_execution(src, tmp_path / 'exec')


def test_seed_error_surfaces_only_as_a_stage_error(src, tmp_path, monkeypatch):
    def refuse(*args):
        raise seed.SeedError('fixture refusal')

    monkeypatch.setattr(seed, 'seed_copy', refuse)
    with pytest.raises(staging.StageError, match='fixture refusal') as caught:
        staging.seed_execution(src, tmp_path / 'exec')
    assert type(caught.value) is staging.StageError
    assert isinstance(caught.value.__cause__, seed.SeedError)


@pytest.fixture
def seeded(src, tmp_path):
    staging.seed_execution(src, tmp_path / 'exec')
    return tmp_path / 'exec'


def test_import_back_copies_data_into_a_new_tree(seeded, tmp_path):
    (seeded / 'one.txt').write_bytes(b'edited\n')
    back = tmp_path / 'back'
    assert staging.import_results(seeded, ['one.txt'], back) == back
    assert (back / 'one.txt').read_bytes() == b'edited\n'
    assert not (back / 'nested').exists()


def test_import_back_refuses_a_hardlinked_result(seeded, tmp_path, monkeypatch):
    lie_about(monkeypatch, 'one.txt', st_nlink=2)
    with pytest.raises(staging.StageError):
        staging.import_results(seeded, ['one.txt'], tmp_path / 'back')


def test_import_back_refuses_an_alias_result(seeded, tmp_path, monkeypatch):
    lie_about(monkeypatch, 'two.bin', st_mode=stat.S_IFLNK)
    with pytest.raises(staging.StageError, match='alias'):
        staging.import_results(seeded, ['nested/two.bin'], tmp_path / 'back')


def test_import_back_refuses_an_escaping_name(seeded, tmp_path):
    with pytest.raises(staging.StageError, match='parent segment'):
        staging.import_results(seeded, ['../src/one.txt'], tmp_path / 'back')
    assert not (tmp_path / 'back').exists()


def test_recheck_passes_a_clean_folder(seeded):
    assert staging.recheck_execution(seeded) == seeded


def test_recheck_catches_a_hardlink_made_after_the_seed(seeded, tmp_path):
    try:
        os.link(seeded / 'one.txt', tmp_path / 'outside.txt')
    except OSError:
        pytest.skip('no hardlinks on this volume')
    with pytest.raises(staging.StageError, match='scan refused: one.txt'):
        staging.recheck_execution(seeded)


def test_recheck_catches_an_alias_made_after_the_seed(seeded, monkeypatch):
    lie_about(monkeypatch, 'one.txt', st_file_attributes=stat.FILE_ATTRIBUTE_REPARSE_POINT)
    with pytest.raises(staging.StageError, match='alias'):
        staging.recheck_execution(seeded)


def test_recheck_of_a_missing_folder_refused(tmp_path):
    with pytest.raises(staging.StageError):
        staging.recheck_execution(tmp_path / 'gone')


def test_sdk_staging_never_goes_through_the_seed(tmp_path, monkeypatch):
    root = tmp_path / 'sdk'
    data = {'package.json': b'{"name": "%s", "version": "%s"}' % (
        staging.MXC_PACKAGE.encode(), staging.MXC_VERSION.encode()),
        staging.MXC_EXE: b'launcher'}
    tree(root, data)
    pins = {rel: hashlib.sha256(blob).hexdigest() for rel, blob in data.items()}

    def forbidden(*args):
        raise AssertionError('the SDK copy must not be seeded')

    for name in ('seed_copy', 'import_back', 'recheck'):
        monkeypatch.setattr(seed, name, forbidden)
    dest = staging.stage_mxc(root, tmp_path / 'stage', pins=pins)
    assert (tmp_path / 'stage' / 'package.json').read_bytes() == data['package.json']
    assert dest == str(tmp_path / 'stage')


def test_a_raw_os_error_is_a_stage_error_without_the_os_text(src, tmp_path, monkeypatch):
    def broken(*args):
        raise PermissionError('fixture text with ' + str(tmp_path))

    monkeypatch.setattr(seed, 'seed_copy', broken)
    with pytest.raises(staging.StageError) as caught:
        staging.seed_execution(src, tmp_path / 'exec')
    assert type(caught.value) is staging.StageError
    assert str(tmp_path) not in str(caught.value)
    assert isinstance(caught.value.__cause__, PermissionError)

"""Offline SDK copies and grant gates; no installed SDK or native calls."""

import hashlib
import json
import os
import stat
from types import SimpleNamespace

import pytest

from archeus.node import staging


@pytest.fixture
def sdk(tmp_path):
    root = tmp_path / 'sdk'
    files = {
        'package.json': json.dumps({'name': staging.MXC_PACKAGE,
                                    'version': staging.MXC_VERSION}).encode(),
        staging.MXC_EXE: b'fake x64 launcher',
        'bin/x64/runtime.dll': b'fake runtime',
    }
    for rel, data in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    pins = {rel: hashlib.sha256(data).hexdigest() for rel, data in files.items()}
    return root, pins


def test_offline_copy_verified_and_fresh_only(sdk, tmp_path):
    root, pins = sdk
    dest = tmp_path / 'stage'
    assert staging.stage_mxc(root, dest, pins=pins) == str(dest)
    assert staging.verify_mxc(dest, pins=pins) == str(dest / staging.MXC_EXE)
    assert os.stat(root / staging.MXC_EXE).st_ino != os.stat(dest / staging.MXC_EXE).st_ino
    with pytest.raises(FileExistsError):
        staging.stage_mxc(root, dest, pins=pins)


@pytest.mark.parametrize('change', ['hash', 'extra', 'missing', 'version', 'name'])
def test_refuses_artifact_drift(sdk, tmp_path, change):
    root, pins = sdk
    if change == 'hash':
        (root / staging.MXC_EXE).write_bytes(b'tampered')
    elif change == 'extra':
        (root / 'extra.dll').write_bytes(b'unknown')
    elif change == 'missing':
        (root / staging.MXC_EXE).unlink()
    else:
        package = {'name': staging.MXC_PACKAGE, 'version': staging.MXC_VERSION}
        package[change] = 'different'
        data = json.dumps(package).encode()
        (root / 'package.json').write_bytes(data)
        pins['package.json'] = hashlib.sha256(data).hexdigest()
    dest = tmp_path / 'stage'
    with pytest.raises(staging.StageError):
        staging.stage_mxc(root, dest, pins=pins)
    assert not dest.exists()


def test_refuses_unreviewed_inventory(sdk):
    root, pins = sdk
    for bad in ({}, {**pins, staging.MXC_EXE: 'not a hash'}):
        with pytest.raises(staging.StageError):
            staging.verify_mxc(root, pins=bad)


def test_all_grants_refuse_nested_hardlinks(tmp_path):
    outside = tmp_path / 'outside'
    outside.write_bytes(b'outside')
    grant = tmp_path / 'grant'
    (grant / 'nested').mkdir(parents=True)
    os.link(outside, grant / 'nested' / 'alias')
    with pytest.raises(staging.StageError, match='second name'):
        staging.scan_grants((grant,))
    with pytest.raises(staging.StageError, match='second name'):
        staging.scan_grants((outside,))


def test_sdk_hardlink_refused(sdk, tmp_path):
    root, pins = sdk
    os.link(root / staging.MXC_EXE, tmp_path / 'alias.exe')
    with pytest.raises(staging.StageError, match='second name'):
        staging.stage_mxc(root, tmp_path / 'stage', pins=pins)


def test_reparse_directory_refused_before_walk(tmp_path, monkeypatch):
    grant = tmp_path / 'grant'
    grant.mkdir()
    original = os.lstat

    def lstat(path, *args, **kwargs):
        st = original(path, *args, **kwargs)
        if os.path.abspath(path) == str(grant):
            return SimpleNamespace(st_mode=st.st_mode,
                                   st_file_attributes=stat.FILE_ATTRIBUTE_REPARSE_POINT)
        return st

    monkeypatch.setattr(os, 'lstat', lstat)
    with pytest.raises(staging.StageError, match='alias'):
        staging.scan_grants((grant,))


def test_source_changed_during_copy_is_not_admitted(sdk, tmp_path, monkeypatch):
    root, pins = sdk
    original = staging._write

    def write(path, chunks):
        if str(path).endswith('runtime.dll'):
            (root / 'bin/x64/runtime.dll').write_bytes(b'drift')
        return original(path, chunks)

    monkeypatch.setattr(staging, '_write', write)
    with pytest.raises(staging.StageError, match='changed during copy'):
        staging.stage_mxc(root, tmp_path / 'stage', pins=pins)

"""T-240: the highest-risk uncovered branches of MXC staging and local launch.

Companion to tests/v1/unit/test_pv20_mxc_staging.py and
tests/v1/integration/test_pv20_mxc_local.py, whose fakes and fixtures this file
copies. Offline only: no installed SDK, no MXC module, no native or Windows
call, no process spawning, no network. Everything the source reaches for the
world comes through the injected seams those tests already use.
"""

from dataclasses import dataclass
import hashlib
import io
import json
import os
import stat
from types import SimpleNamespace

import pytest

from archeus.node import local, staging


@dataclass(frozen=True)
class MxcPolicy:
    raw: dict


class FakeProcess:
    pid = 123

    def __init__(self, launcher_exit=0):
        self.launcher_exit = launcher_exit
        self.stdin, self.stdout, self.stderr = io.BytesIO(), io.BytesIO(), io.BytesIO()

    def wait(self, timeout=None):
        return self.launcher_exit

    def terminate(self):
        raise AssertionError('Job teardown belongs to isolation authority')


class FakeMxc:
    def __init__(self, launcher_exit=0):
        self.process = FakeProcess(launcher_exit)
        self.calls = []

    def compile_policy(self, *, workspace, readonly=(), denied=(), cwd,
                        command_line, env=None, timeout_ms, ui=False,
                        egress='deny', proxy_url=None):
        assert ui is False and egress == 'deny' and proxy_url is None
        self.calls.append('compile')
        return MxcPolicy({'filesystem': {'readwritePaths': [workspace],
                                        'readonlyPaths': list(readonly)}})

    def spawn(self, policy, *, exe, job):
        self.calls.append(('spawn', exe, job))
        return self.process


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


@pytest.fixture
def launch_args(tmp_path):
    sdk_root = tmp_path / 'launch-sdk'
    (sdk_root / 'bin/x64').mkdir(parents=True)
    (sdk_root / 'package.json').write_text(json.dumps({
        'name': staging.MXC_PACKAGE, 'version': staging.MXC_VERSION}), encoding='utf-8')
    (sdk_root / staging.MXC_EXE).write_bytes(b'fake launcher')
    pins = {rel: hashlib.sha256((sdk_root / rel).read_bytes()).hexdigest()
            for rel in ('package.json', staging.MXC_EXE)}
    work = tmp_path / 'work'
    work.mkdir()
    runtime = tmp_path / 'runtime'
    runtime.mkdir()
    return dict(sdk_root=sdk_root, pins=pins, workspace=str(work), readonly=(str(runtime),),
                cwd=str(work), command_line='fixture command', env={}, timeout_ms=1000)


# -- branch 1: the reviewed-pins structure guard (staging.py:305-312) ---------
# The named tests exercise only an empty pin map and one wrong-length value;
# the path-shaped key disjuncts and the hex-alphabet value disjunct are dark.

@pytest.mark.parametrize('bad', ['../evil', '..\\evil', 'pkg:x', 'a//b', 'a/./b',
                                 'a/../b', '/lead', 'trail/', 5])
def test_invalid_pin_key_refused_before_the_inventory(sdk, bad):
    root, pins = sdk
    with pytest.raises(staging.StageError, match='invalid reviewed MXC pins'):
        staging.verify_mxc(root, pins={**pins, bad: 'a' * 64})


@pytest.mark.parametrize('bad', ['z' * 64, 'F' * 64, 'g' + '0' * 63])
def test_invalid_pin_value_refused_before_the_inventory(sdk, bad):
    root, pins = sdk
    with pytest.raises(staging.StageError, match='invalid reviewed MXC pins'):
        staging.verify_mxc(root, pins={**pins, 'package.json': bad})


# -- branch 2: hash-pinned package.json that is not valid JSON (staging.py:315-319)


def test_invalid_package_metadata_json_refused(sdk):
    root, pins = sdk
    data = b'{"name": "@microsoft/mxc-sdk", broken'
    (root / 'package.json').write_bytes(data)
    with pytest.raises(staging.StageError, match='invalid MXC package metadata'):
        staging.verify_mxc(root, pins={**pins, 'package.json': hashlib.sha256(data).hexdigest()})


# -- branch 3: package.json is JSON but not an object (staging.py:320-322)


def test_non_object_package_metadata_refused(sdk):
    root, pins = sdk
    data = json.dumps([{'name': staging.MXC_PACKAGE, 'version': staging.MXC_VERSION}]).encode()
    (root / 'package.json').write_bytes(data)
    with pytest.raises(staging.StageError, match='package identity differs'):
        staging.verify_mxc(root, pins={**pins, 'package.json': hashlib.sha256(data).hexdigest()})


# -- branch 4: the staged copy itself is verified against the pins before it is
# accepted (staging.py:344 -> 313-314): never checked by the named tests, which
# only ever drift the SOURCE and so fail at the first verify_mxc.

def test_a_write_that_lies_about_what_it_wrote_is_caught_before_publish(sdk, tmp_path,
                                                                        monkeypatch):
    root, pins = sdk
    dest = tmp_path / 'stage'

    def lying_write(dst, chunks):
        data = b''.join(chunks)
        with open(dst, 'xb') as out:
            out.write(b'tampered')
        return hashlib.sha256(data).hexdigest()

    monkeypatch.setattr(staging, '_write', lying_write)
    with pytest.raises(staging.StageError, match='differ from reviewed hashes'):
        staging.stage_mxc(root, dest, pins=pins)
    assert dest.exists()                      # left for inspection, never deleted
    with pytest.raises(staging.StageError, match='differ from reviewed hashes'):
        staging.verify_mxc(dest, pins=pins)


@pytest.mark.parametrize('change', ['extra', 'missing'])
def test_extra_or_missing_artifact_in_a_staged_copy_refuses_verify(sdk, tmp_path, change):
    root, pins = sdk
    dest = staging.stage_mxc(root, tmp_path / 'stage', pins=pins)
    if change == 'extra':
        (tmp_path / 'stage' / 'bin' / 'x64' / 'undisclosed.dll').write_bytes(b'unknown')
    else:
        (tmp_path / 'stage' / staging.MXC_EXE).unlink()
    with pytest.raises(staging.StageError, match='differ from reviewed hashes'):
        staging.verify_mxc(dest, pins=pins)


# -- branch 5: an SDK entry that is neither a plain file nor a directory
# (staging.py:44-45, reached through scan_grants' walk at staging.py:274-281).
# Without it the fifo below reaches os.listdir and raises a bare OSError.

def test_non_plain_entry_in_the_sdk_refused(sdk, monkeypatch):
    root, pins = sdk
    sneaky = root / 'bin/x64/pipe'
    sneaky.write_bytes(b'x')
    original = os.lstat

    def lstat(path, *args, **kwargs):
        st = original(path, *args, **kwargs)
        if os.path.abspath(path) == str(sneaky):
            return SimpleNamespace(st_mode=stat.S_IFIFO | 0o600)
        return st

    monkeypatch.setattr(os, 'lstat', lstat)
    with pytest.raises(staging.StageError, match='plain entry'):
        staging.verify_mxc(root, pins={**pins, 'bin/x64/pipe':
                                       hashlib.sha256(b'x').hexdigest()})


# -- branch 6: every ancestor of the fresh destination is plain before the copy
# (staging.py:331 -> _ancestors 261-266 -> 42). The named tests never alias a
# destination ancestor.

def test_destination_below_an_aliased_parent_refused(sdk, tmp_path, monkeypatch):
    root, pins = sdk
    below = tmp_path / 'below'
    below.mkdir()
    dest = below / 'stage'
    original = os.lstat

    def lstat(path, *args, **kwargs):
        st = original(path, *args, **kwargs)
        if os.path.abspath(path) == str(below):
            return SimpleNamespace(st_mode=st.st_mode,
                                   st_file_attributes=stat.FILE_ATTRIBUTE_REPARSE_POINT)
        return st

    monkeypatch.setattr(os, 'lstat', lstat)
    with pytest.raises(staging.StageError, match='alias'):
        staging.stage_mxc(root, dest, pins=pins)
    assert not dest.exists()


# -- branch 7: a copy that fails halfway is left whole-ish for inspection and
# is never repaired, replaced or published (staging.py:326-344; _write's 'xb'
# at staging.py:70-76 is the only write mode: no replacement primitive).

def test_a_failed_copy_is_left_for_inspection_and_never_replaced(sdk, tmp_path, monkeypatch):
    root, pins = sdk
    dest = tmp_path / 'stage'
    original = staging._write

    def write(path, chunks):
        if str(path).endswith('wxc-exec.exe'):
            raise OSError('fixture disk failure')
        return original(path, chunks)

    monkeypatch.setattr(staging, '_write', write)
    with pytest.raises(OSError, match='fixture disk failure'):
        staging.stage_mxc(root, dest, pins=pins)
    assert (dest / 'bin' / 'x64' / 'runtime.dll').read_bytes() == b'fake runtime'
    assert not (dest / 'package.json').exists()          # exactly what got that far
    with pytest.raises(staging.StageError, match='differ from reviewed hashes'):
        staging.verify_mxc(dest, pins=pins)               # cannot publish
    with pytest.raises(FileExistsError):                  # nothing was cleaned up
        staging.stage_mxc(root, dest, pins=pins)
    with pytest.raises(FileExistsError):                  # and no name is replaced
        staging._write(dest / 'bin' / 'x64' / 'runtime.dll', [b'replaced'])


def test_staging_exposes_no_deletion_or_replacement_primitive():
    assert not any(hasattr(staging, name) for name in
                   ('shutil', 'rmtree', 'remove', 'unlink', 'replace', 'rename',
                    'clean', 'cleanup', 'purge', 'delete', 'unstage'))


# -- branch 8: MxcLaunch verifies the SDK before ANY backend call
# (local.py:173); the named tests only tamper between init and start.

def test_a_tampered_sdk_is_refused_before_any_backend_call(launch_args):
    backend = FakeMxc()
    (launch_args['sdk_root'] / staging.MXC_EXE).write_bytes(b'tampered')
    with pytest.raises(staging.StageError, match='differ from reviewed hashes'):
        local.MxcLaunch(backend=backend, outcome=lambda p: 0, **launch_args)
    assert backend.calls == []


# -- branch 9: an outcome for a launch that never started is refused
# (local.py:220-221); the named tests only wait after start.

def test_waiting_before_start_refuses(launch_args):
    backend = FakeMxc()
    launch = local.MxcLaunch(backend=backend, outcome=lambda p: 0, **launch_args)
    with pytest.raises(staging.StageError, match='has not started'):
        launch.wait()
    assert backend.calls == ['compile']


# -- branch 10: start re-scans the grants of the COMPILED policy, not the ones
# it was constructed with (local.py:191-195): a backend that compiles a policy
# granting an extra path has that path scanned before spawn, exactly once here
# and again by isolation's own gate.

def test_start_rescans_the_grants_of_the_compiled_policy(launch_args, tmp_path):
    extra = tmp_path / 'policy-extra'
    extra.mkdir()
    outside = tmp_path / 'outside'
    outside.write_bytes(b'outside')
    try:
        os.link(outside, extra / 'alias')
    except OSError as err:
        pytest.skip('hardlinks unavailable: %s' % err)
    backend = FakeMxc()
    compile_ = backend.compile_policy

    def compile_policy(**kwargs):
        policy = compile_(**kwargs)
        policy.raw['filesystem']['readwritePaths'].append(str(extra))
        return policy

    backend.compile_policy = compile_policy
    launch = local.MxcLaunch(backend=backend, outcome=lambda p: 0, **launch_args)
    with pytest.raises(staging.StageError, match='second name'):
        launch.start(job=object())
    assert backend.calls == ['compile']               # spawn never reached
    assert launch.process is None



def test_a_missing_grant_is_a_stage_error_not_a_bare_file_not_found(tmp_path):
    # T-664#3: scan_grants((missing,)) raised FileNotFoundError, outside the StageError contract
    with pytest.raises(staging.StageError, match='unreadable entry'):
        staging.scan_grants((str(tmp_path / 'no' / 'such' / 'path'),))

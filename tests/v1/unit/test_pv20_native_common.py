"""Unit tests for tools/pv20_mxc/native/common.py (card T-460).

The Windows system calls and path grammar sit behind the module-level seams
(_popen, _process_creation_time, _terminate_process, _is_link_or_junction,
_profile_dir, _repo_root, _username, _machine_name, _IS_WINDOWS) which these
tests monkeypatch, so they run on Linux and on Windows. Nothing here
launches a process, kills one, or touches a real profile.
"""

import os
import re
import stat
from types import SimpleNamespace
from uuid import uuid4

import pytest

from tools.pv20_mxc.native import common
from tools.pv20_mxc.native.common import (Children, Recorder, StopRun,
                                          redact, remove_fixture, safe_root)

HEX32 = re.compile(r'\A[0-9a-f]{32}\Z')


def _dir_link(link, target):
    """Real directory link: a symlink, or a junction where symlinks need a privilege."""
    try:
        os.symlink(target, link, target_is_directory=True)
        return
    except OSError as err:
        if os.name != 'nt':
            raise
        symlink_err = err
    try:
        import _winapi
        _winapi.CreateJunction(target, link)
    except (ImportError, OSError, AttributeError):
        pytest.skip('host can create neither symlinks nor junctions: %s' % symlink_err)


@pytest.fixture
def parent(tmp_path, monkeypatch):
    """A real, validated parent directory with profile/repo faked elsewhere."""
    monkeypatch.setattr(common, '_profile_dir',
                        lambda: str(tmp_path / 'profile' / 'amy'))
    monkeypatch.setattr(common, '_repo_root',
                        lambda: str(tmp_path / 'checkouts' / 'archeus'))
    path = tmp_path / 'fixtures' / 'parent'
    path.mkdir(parents=True)
    return str(path)


@pytest.fixture
def procs(monkeypatch):
    """Fakes for Popen, creation time and terminate; records every call."""
    started = []
    killed = []
    ctimes = {}
    counter = {'pid': 4000}

    def fake_popen(argv, **kwargs):
        counter['pid'] += 1
        pid = counter['pid']
        started.append((argv, kwargs))
        ctimes[pid] = 1000000 + pid
        return SimpleNamespace(pid=pid)

    def fake_ctimes(pid):
        return ctimes.get(pid)

    def fake_kill(pid):
        if pid not in ctimes:
            return False
        killed.append(pid)
        return True

    monkeypatch.setattr(common, '_popen', fake_popen)
    monkeypatch.setattr(common, '_process_creation_time', fake_ctimes)
    monkeypatch.setattr(common, '_terminate_process', fake_kill)
    return SimpleNamespace(started=started, killed=killed, ctimes=ctimes)


# ---------------------------------------------------------------- safe_root

def test_safe_root_creates_hex_dir_with_marker(parent):
    root = safe_root(parent)
    assert os.path.dirname(root) == os.path.normpath(parent)
    assert HEX32.match(os.path.basename(root))
    assert os.path.isdir(root)
    marker = os.path.join(root, '.pv20-fixture')
    assert os.path.isfile(marker)


def test_safe_root_two_calls_differ(parent):
    a, b = safe_root(parent), safe_root(parent)
    assert a != b
    assert os.path.isdir(a) and os.path.isdir(b)


@pytest.mark.parametrize('bad', [None, '', 123])
def test_safe_root_refuses_non_string(bad):
    with pytest.raises(ValueError, match='non-empty string'):
        safe_root(bad)


def test_safe_root_refuses_relative(parent):
    rel = os.path.join('fixtures', 'parent')
    assert not os.path.isabs(rel)
    with pytest.raises(ValueError, match='absolute path'):
        safe_root(rel)


def test_safe_root_refuses_filesystem_root(monkeypatch):
    monkeypatch.setattr(common, '_IS_WINDOWS', False)
    with pytest.raises(ValueError, match='drive or filesystem root'):
        safe_root('/')


def test_safe_root_refuses_drive_root_and_short_windows_paths(monkeypatch):
    monkeypatch.setattr(common, '_IS_WINDOWS', True)
    with pytest.raises(ValueError, match='drive or filesystem root'):
        safe_root('C:\\')
    with pytest.raises(ValueError, match='three path components'):
        safe_root('C:\\fixtures')


def test_safe_root_refuses_short_posix_parent(monkeypatch):
    monkeypatch.setattr(common, '_IS_WINDOWS', False)
    with pytest.raises(ValueError, match='three path components'):
        safe_root('/ab')


def test_safe_root_refuses_profile_itself(tmp_path, monkeypatch):
    prof = str(tmp_path / 'profile' / 'amy')
    monkeypatch.setattr(common, '_profile_dir', lambda: prof)
    monkeypatch.setattr(common, '_repo_root',
                        lambda: str(tmp_path / 'checkouts' / 'archeus'))
    os.makedirs(prof)
    with pytest.raises(ValueError, match='user profile'):
        safe_root(prof)


def test_safe_root_refuses_profile_ancestor(tmp_path, monkeypatch):
    prof = str(tmp_path / 'profile' / 'amy')
    monkeypatch.setattr(common, '_profile_dir', lambda: prof)
    monkeypatch.setattr(common, '_repo_root',
                        lambda: str(tmp_path / 'checkouts' / 'archeus'))
    with pytest.raises(ValueError, match='user profile'):
        safe_root(str(tmp_path / 'profile'))


def test_safe_root_refuses_inside_profile(tmp_path, monkeypatch):
    prof = str(tmp_path / 'profile' / 'amy')
    monkeypatch.setattr(common, '_profile_dir', lambda: prof)
    monkeypatch.setattr(common, '_repo_root',
                        lambda: str(tmp_path / 'checkouts' / 'archeus'))
    inside = os.path.join(prof, 'fixtures', 'parent')
    os.makedirs(inside)
    with pytest.raises(ValueError, match='user profile'):
        safe_root(inside)


def test_safe_root_refuses_inside_repository(parent, tmp_path, monkeypatch):
    repo = str(tmp_path / 'checkouts' / 'archeus')
    monkeypatch.setattr(common, '_repo_root', lambda: repo)
    inside = os.path.join(repo, 'tools', 'parent')
    os.makedirs(inside)
    with pytest.raises(ValueError, match='repository'):
        safe_root(inside)


def test_safe_root_refuses_real_symlink_parent(parent, tmp_path):
    real = tmp_path / 'real-parent'
    real.mkdir()
    link = str(tmp_path / 'fixtures' / 'link-parent')
    _dir_link(link, str(real))
    with pytest.raises(ValueError, match='link or junction'):
        safe_root(link)


def test_safe_root_refuses_parent_behind_symlinked_ancestor(parent, tmp_path):
    real = tmp_path / 'deep' / 'parent'
    real.mkdir(parents=True)
    link = str(tmp_path / 'via')
    _dir_link(link, str(tmp_path / 'deep'))
    with pytest.raises(ValueError, match='link or junction'):
        safe_root(os.path.join(link, 'parent'))


def test_safe_root_refuses_fake_junction(parent, monkeypatch):
    junc = os.path.join(parent, 'junc')
    os.makedirs(junc)
    monkeypatch.setattr(common, '_is_link_or_junction',
                        lambda p: os.path.normpath(p) == junc)
    with pytest.raises(ValueError, match='link or junction'):
        safe_root(junc)


def test_safe_root_refuses_missing_parent(parent):
    with pytest.raises(ValueError, match='existing directory'):
        safe_root(os.path.join(parent, 'nope'))


# ----------------------------------------------------------- remove_fixture

def test_remove_fixture_removes_verified_tree(parent):
    root = safe_root(parent)
    remove_fixture(root)
    assert not os.path.exists(root)
    assert os.path.isdir(parent)


@pytest.mark.parametrize('bad', [None, '', 42])
def test_remove_fixture_refuses_non_string(bad):
    with pytest.raises(ValueError, match='non-empty string'):
        remove_fixture(bad)


def test_remove_fixture_refuses_relative(parent):
    root = safe_root(parent)
    with pytest.raises(ValueError, match='absolute path'):
        remove_fixture(os.path.relpath(root, start=os.path.dirname(parent)))


def test_remove_fixture_refuses_bad_name_with_marker(parent):
    bogus = os.path.join(parent, 'notes')
    os.makedirs(bogus)
    with open(os.path.join(bogus, '.pv20-fixture'), 'w') as handle:
        handle.write('x')
    with pytest.raises(ValueError, match='uuid4 hex'):
        remove_fixture(bogus)


def test_remove_fixture_refuses_missing_marker(parent):
    bare = os.path.join(parent, uuid4().hex)
    os.makedirs(bare)
    with pytest.raises(ValueError, match='marker'):
        remove_fixture(bare)


def test_remove_fixture_refuses_marker_as_directory(parent):
    root = os.path.join(parent, uuid4().hex)
    os.makedirs(os.path.join(root, '.pv20-fixture'))
    with pytest.raises(ValueError, match='marker'):
        remove_fixture(root)


def test_remove_fixture_refuses_link_root(parent, tmp_path):
    victim = tmp_path / 'victim-dir'
    victim.mkdir()
    (victim / 'keep.txt').write_text('keep')
    link = os.path.join(parent, uuid4().hex)
    _dir_link(link, str(victim))
    with pytest.raises(ValueError, match='link or junction'):
        remove_fixture(link)
    assert (victim / 'keep.txt').read_text() == 'keep'


def test_remove_fixture_refuses_fake_junction_root(parent, monkeypatch):
    root = safe_root(parent)
    monkeypatch.setattr(common, '_is_link_or_junction',
                        lambda p: os.path.normpath(p) == os.path.normpath(root))
    with pytest.raises(ValueError, match='link or junction'):
        remove_fixture(root)
    assert os.path.isdir(root)


def test_remove_fixture_refuses_nested_deeper(parent):
    root = safe_root(parent)
    inner = os.path.join(root, uuid4().hex)
    os.makedirs(os.path.join(inner, '.pv20-fixture'))
    with pytest.raises(ValueError, match='directly under the validated parent'):
        remove_fixture(inner)
    assert os.path.isdir(inner)


def test_remove_fixture_refuses_unvalidated_parent(tmp_path, monkeypatch):
    prof = tmp_path / 'profile' / 'amy'
    prof.mkdir(parents=True)
    inside = prof / 'fx'
    inside.mkdir()
    root = str(inside / uuid4().hex)
    os.makedirs(os.path.join(root, '.pv20-fixture'))
    monkeypatch.setattr(common, '_profile_dir', lambda: str(prof))
    monkeypatch.setattr(common, '_repo_root',
                        lambda: str(tmp_path / 'checkouts' / 'archeus'))
    with pytest.raises(ValueError, match='user profile'):
        remove_fixture(root)


def test_remove_fixture_refuses_missing_root(parent):
    gone = os.path.join(parent, uuid4().hex)
    with pytest.raises(ValueError, match='does not exist'):
        remove_fixture(gone)


def test_remove_fixture_refuses_file_root(parent):
    path = os.path.join(parent, uuid4().hex)
    with open(path, 'w') as handle:
        handle.write('x')
    with pytest.raises(ValueError, match='real directory'):
        remove_fixture(path)


def test_remove_fixture_does_not_follow_inner_links(parent, tmp_path):
    victim = tmp_path / 'victim-dir'
    victim.mkdir()
    (victim / 'keep.txt').write_text('keep')
    root = safe_root(parent)
    with open(os.path.join(root, 'data.txt'), 'w') as handle:
        handle.write('fixture data')
    _dir_link(os.path.join(root, 'sneaky-link'), str(victim))
    remove_fixture(root)
    assert not os.path.exists(root)
    assert (victim / 'keep.txt').read_text() == 'keep'


def test_remove_fixture_removes_nested_dirs_and_read_only_files(parent):
    root = safe_root(parent)
    deep = os.path.join(root, 'a', 'b')
    os.makedirs(deep)
    os.makedirs(os.path.join(root, 'c'))
    locked = os.path.join(deep, 'ro.txt')
    with open(locked, 'w') as handle:
        handle.write('x')
    os.chmod(locked, stat.S_IREAD)
    remove_fixture(root)
    assert not os.path.exists(root)
    assert os.path.isdir(parent)


def test_children_hold_the_process_handle(procs):
    kids = Children()
    kids.start(['cmd.exe', '/c', 'a'])
    assert len(kids._procs) == 1


def test_safe_root_refuses_device_prefix_and_driveless_windows_paths(monkeypatch):
    monkeypatch.setattr(common, '_IS_WINDOWS', True)
    with pytest.raises(ValueError, match='device path prefix'):
        safe_root('\\\\?\\C:\\fixtures\\parent')
    with pytest.raises(ValueError, match='device path prefix'):
        safe_root('//./C:/fixtures/parent')
    with pytest.raises(ValueError, match='drive or UNC share'):
        safe_root('\\fixtures\\a\\parent')


def test_safe_root_refuses_non_canonical_spelling(parent, monkeypatch):
    monkeypatch.setattr(os.path, 'realpath', lambda p: p + '-elsewhere')
    with pytest.raises(ValueError, match='canonical form'):
        safe_root(parent)


@pytest.mark.skipif(os.name != 'nt', reason='trailing dots are ignored by Win32 only')
def test_safe_root_refuses_trailing_dot_alias(parent):
    with pytest.raises(ValueError, match='canonical form'):
        safe_root(parent + '.')


def test_safe_root_refuses_profile_given_as_realpath_alias(tmp_path, monkeypatch):
    prof = tmp_path / 'profile' / 'amy'
    inside = prof / 'fx'
    inside.mkdir(parents=True)
    monkeypatch.setattr(common, '_profile_dir', lambda: str(prof) + '-alias')
    monkeypatch.setattr(os.path, 'realpath',
                        lambda p: str(prof) if p.endswith('-alias') else p)
    monkeypatch.setattr(common, '_repo_root',
                        lambda: str(tmp_path / 'checkouts' / 'archeus'))
    with pytest.raises(ValueError, match='user profile'):
        safe_root(str(inside))


# --------------------------------------------------------------- Recorder

def test_recorder_rejects_unknown_stage():
    with pytest.raises(ValueError, match='stage'):
        Recorder('NOPE')


def test_recorder_rejects_unknown_case():
    rec = Recorder('N1')
    with pytest.raises(ValueError, match='case'):
        rec.record('not-a-real-case', 'PASS')


def test_recorder_rejects_unknown_status():
    rec = Recorder('N1')
    with pytest.raises(ValueError, match='status'):
        rec.record('positive-controls', 'BLOCKED')


def test_recorder_all_pass_exits_zero(capsys):
    rec = Recorder('N1')
    rec.record('positive-controls', 'PASS', 'ok')
    rec.record('launcher-death', 'PASS')
    assert rec.exit_code() == 0
    out = capsys.readouterr().out
    assert 'N1 positive-controls PASS ok' in out
    assert 'N1 launcher-death PASS' in out


def test_recorder_fail_raises_stoprun_after_printing(capsys):
    rec = Recorder('N1')
    with pytest.raises(StopRun):
        rec.record('positive-controls', 'FAIL', 'boom')
    out = capsys.readouterr().out
    assert 'positive-controls FAIL boom' in out
    assert rec.exit_code() == 1


def test_recorder_stop_at_first_fail_stops_early(capsys):
    rec = Recorder('N1')
    rec.record('positive-controls', 'PASS')
    with pytest.raises(StopRun):
        for case in ('p-q-token-psec', 'launcher-death', 'core-death'):
            rec.record(case, 'FAIL', 'stop here')
    out = capsys.readouterr().out
    assert 'p-q-token-psec FAIL' in out
    assert 'launcher-death' not in out
    assert rec.exit_code() == 1


def test_recorder_inconclusive_exits_two(capsys):
    rec = Recorder('N1')
    rec.record('positive-controls', 'PASS')
    rec.record('p-q-token-psec', 'INCONCLUSIVE', 'info only')
    assert rec.exit_code() == 2
    assert 'INCONCLUSIVE' in capsys.readouterr().out


def test_recorder_fail_outranks_inconclusive():
    rec = Recorder('N1')
    rec.results.append(('positive-controls', 'INCONCLUSIVE'))
    rec.results.append(('core-death', 'FAIL'))
    assert rec.exit_code() == 1


def test_recorder_empty_run_never_passes():
    rec = Recorder('N1')
    assert rec.exit_code() == 2


def test_recorder_prints_redacted_line(monkeypatch, capsys):
    monkeypatch.setattr(common, '_username', lambda: 'octavia')
    monkeypatch.setattr(common, '_machine_name', lambda: 'DESKTOP-ZYX42')
    rec = Recorder('N1')
    rec.record('positive-controls', 'PASS',
               'user octavia on DESKTOP-ZYX42 sid S-1-5-21-4-4-4-500')
    out = capsys.readouterr().out
    assert 'octavia' not in out
    assert 'DESKTOP-ZYX42' not in out
    assert 'S-1-5-21' not in out
    assert '[REDACTED' in out


# ---------------------------------------------------------------- Children

def test_children_start_records_argv_and_kwargs(procs):
    kids = Children()
    pid = kids.start(['cmd.exe', '/c', 'echo'], cwd='X', stdout=-1)
    assert pid == 4001
    assert procs.started[0][0] == ['cmd.exe', '/c', 'echo']
    assert procs.started[0][1] == {'cwd': 'X', 'stdout': -1}


def test_children_start_refuses_shell_string(procs):
    kids = Children()
    with pytest.raises(ValueError, match='argument list'):
        kids.start('cmd.exe /c echo hi')
    with pytest.raises(ValueError, match='argument list'):
        kids.start(['cmd.exe', 5])


def test_children_kill_own_kills_matching_and_second_call_is_zero(procs):
    kids = Children()
    pids = [kids.start(['cmd.exe', '/c', 'a']), kids.start(['cmd.exe', '/c', 'b'])]
    assert kids.kill_own() == 2
    assert procs.killed == pids
    assert kids.kill_own() == 0


def test_children_kill_own_refuses_reused_pid(procs):
    kids = Children()
    pid = kids.start(['cmd.exe', '/c', 'a'])
    procs.ctimes[pid] = 7777777  # pid recycled by an unrelated process
    assert kids.kill_own() == 0
    assert procs.killed == []


def test_children_kill_own_refuses_when_identity_unknown(procs):
    kids = Children()
    pid = kids.start(['cmd.exe', '/c', 'a'])
    del procs.ctimes[pid]  # creation time no longer readable
    assert kids.kill_own() == 0
    assert procs.killed == []


def test_children_kill_own_mixed_ownership(procs):
    kids = Children()
    mine = kids.start(['cmd.exe', '/c', 'mine'])
    theirs = kids.start(['cmd.exe', '/c', 'theirs'])
    procs.ctimes[theirs] = 9999999  # reused: not ours any more
    assert kids.kill_own() == 1
    assert procs.killed == [mine]


def test_children_default_creation_time_is_none_off_windows(monkeypatch):
    monkeypatch.setattr(common, '_IS_WINDOWS', False)
    kids = Children()
    pid = kids.start(['true'])
    assert kids._own[0] == (pid, None)
    assert kids.kill_own() == 0  # unverifiable identity is never killed


# ----------------------------------------------------------------- redact

def test_redact_strips_sids():
    text = 'token S-1-5-21-1004-1500-1234-500 and S-1-5-18 end'
    out = redact(text)
    assert 'S-1-5-21-1004-1500-1234-500' not in out
    assert 'S-1-5-18' not in out
    assert '[REDACTED-SID]' in out


def test_redact_strips_username_and_machine(monkeypatch):
    monkeypatch.setattr(common, '_username', lambda: 'octavia')
    monkeypatch.setattr(common, '_machine_name', lambda: 'DESKTOP-ZYX42')
    out = redact('user octavia logged in on DESKTOP-ZYX42')
    assert 'octavia' not in out and 'DESKTOP-ZYX42' not in out
    assert '[REDACTED-USER]' in out and '[REDACTED-HOST]' in out


def test_redact_case_insensitive_on_windows(monkeypatch):
    monkeypatch.setattr(common, '_IS_WINDOWS', True)
    monkeypatch.setattr(common, '_username', lambda: 'octavia')
    monkeypatch.setattr(common, '_machine_name', lambda: '')
    assert 'Octavia' not in redact('user Octavia did it')


def test_redact_case_sensitive_off_windows(monkeypatch):
    monkeypatch.setattr(common, '_IS_WINDOWS', False)
    monkeypatch.setattr(common, '_username', lambda: 'octavia')
    monkeypatch.setattr(common, '_machine_name', lambda: '')
    assert 'Octavia' in redact('user Octavia did it')  # different-cased word kept
    assert 'octavia' not in redact('user octavia did it')


def test_redact_escapes_regex_metachars(monkeypatch):
    monkeypatch.setattr(common, '_username', lambda: 'weird.user+re*ge')
    monkeypatch.setattr(common, '_machine_name', lambda: '')
    out = redact('path C:\\Users\\weird.user+re*ge\\note.txt')
    assert 'weird.user+re*ge' not in out
    assert '[REDACTED-USER]' in out


def test_redact_ignores_trivial_names(monkeypatch):
    monkeypatch.setattr(common, '_username', lambda: '')
    monkeypatch.setattr(common, '_machine_name', lambda: 'a')
    assert redact('hello world') == 'hello world'


def test_redact_plain_text_unchanged(monkeypatch):
    monkeypatch.setattr(common, '_username', lambda: 'octavia')
    monkeypatch.setattr(common, '_machine_name', lambda: 'DESKTOP-ZYX42')
    assert redact('pv20 N1 positive-controls PASS ok') == \
        'pv20 N1 positive-controls PASS ok'

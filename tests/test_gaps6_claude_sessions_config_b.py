"""T-1267 — close the highest-risk test gaps in claude_sessions/config.py,
lines 738-944 inclusive (tip 6bbd3b44; re-located by reading the source, the
card's line numbers came from an older tip, and the file is 1571 lines at this
worktree's tip).

Slice: `_ensure_dir`, `write_atomic` and `write_json_atomic`, `save_settings`,
`get_config_dir`, `global_claude_md_for`, `named_dirs`, `all_config_dirs` and
`account_env`.

Selected branches, denial/fail-closed first, then boundaries, then error paths:

 1. :790  a bare filename writes its temp beside it in the current directory
          and never asks for a directory to be made
 2. :825  save_settings creates its temp with mode 0600 and O_EXCL, keeps the
          unknown keys, never writes the carrier key, and lets a parked value
          win a name collision
 3. :801  every replace refused: save_settings returns False, the settings
          bytes are the old bytes, no temp is left, and the retry budget is spent
 4. :794  a write fault stops before replace: replace is never called, the
          target keeps its bytes and the temp is gone
 5. :861  a whitespace-only CLAUDE_CONFIG_DIR falls through to the setting; a
          real value beats the setting; an empty value falls through
 6. :874  global_claude_md_for resolves the global file only when no account
          is named
 7. :884  named_dirs puts the default first, drops entries without a dir, names
          an unnamed entry by its dir, and keeps the first of two equal paths
 8. :908  all_config_dirs drops an account whose directory is the default and
          keeps the first of two accounts that share a directory
 9. :924  account_env with a named harness pins that harness's home, pops only
          its own auth keys, and returns a copy of the environment
10. :750  the workdir marker is written once and never overwrites a user's
          .gitignore; a failed marker write is swallowed; a non-workdir gets none

Closest existing tests: tests/test_gaps7_claude_sessions_config_a.py and
tests/test_gaps7_claude_sessions_config_b.py (the replace budget, the backoff,
the lock order, the O_EXCL temp, the cleanup failure and the thread-identity
names of write_atomic), tests/test_config.py (get_config_dir override and
expansion, a settings round-trip) and tests/test_gaps6_claude_sessions_launch_a.py
(account_env with the default harness). These probes do not repeat the replace
loop or the temp naming; they cover the saved-settings composition, the
whitespace env, the named-directory and account-directory dedupe, the named
harness and the marker file.

Seams: `config.time` is a fake clock with no real sleep, `config.os.open`,
`config.os.replace` and `config.os.fdopen` are wrapped or faked per test,
`config.open` is faked for the marker write, `harnesses.descriptor` and
`harnesses.of` are faked, and `config.settings_file` and `config._USERPROFILE`
point at tmp_path. No test reads the real account or the real environment.
"""

import json
import os

import pytest

from claude_sessions import config as c
from claude_sessions import harnesses


class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


class FullDisk:
    def __init__(self, fd):
        self.fd = fd

    def write(self, text):
        raise OSError(28, 'no space')

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        os.close(self.fd)
        return False


@pytest.fixture
def settings_path(tmp_path, monkeypatch):
    p = tmp_path / 'archeus.json'
    monkeypatch.setattr(c, 'settings_file', str(p))
    return p


@pytest.fixture
def clock(monkeypatch):
    fake = FakeClock()
    monkeypatch.setattr(c, 'time', fake)
    return fake


def names(directory):
    return sorted(p.name for p in directory.iterdir())


def test_a_bare_filename_writes_its_temp_beside_it_and_makes_no_directory(
        tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    made = []
    monkeypatch.setattr(c, '_ensure_dir', lambda d: made.append(d))
    assert c.write_atomic('plain.json', '{"a": 1}') is True
    assert made == []
    assert (tmp_path / 'plain.json').read_text(encoding='utf-8') == '{"a": 1}'
    assert names(tmp_path) == ['plain.json']


def test_save_settings_creates_0600_exclusively_keeps_unknowns_and_drops_the_carrier(
        tmp_path, settings_path, monkeypatch):
    opened = []
    real_open = os.open

    def recording_open(path, flags, mode=0o777, *args, **kwargs):
        opened.append((os.path.basename(path), mode, bool(flags & os.O_EXCL)))
        return real_open(path, flags, mode, *args, **kwargs)

    monkeypatch.setattr(c.os, 'open', recording_open)
    s = {'default_permission': 'plan',
         c._UNKNOWN_KEYS: {'future_key': 1, 'default_permission': 'auto'}}

    assert c.save_settings(s) is True

    temps = [o for o in opened if o[0].startswith(settings_path.name + '.')]
    assert temps and all(mode == 0o600 and excl for _, mode, excl in temps)
    data = json.loads(settings_path.read_text(encoding='utf-8'))
    assert c._UNKNOWN_KEYS not in data
    assert data['future_key'] == 1
    # WHY: the parked bucket is written last, so a carried value wins a collision
    assert data['default_permission'] == 'auto'


def test_settings_that_cannot_be_replaced_keep_the_old_bytes_and_leave_no_temp(
        tmp_path, settings_path, clock, monkeypatch):
    settings_path.write_text('{"keep": true}', encoding='utf-8')

    def refuse(src, dst):
        raise PermissionError(13, 'held')

    monkeypatch.setattr(c.os, 'replace', refuse)
    assert c.save_settings({'default_permission': 'plan'}) is False
    assert settings_path.read_text(encoding='utf-8') == '{"keep": true}'
    assert names(tmp_path) == ['archeus.json']
    assert clock.now >= c._REPLACE_BUDGET


def test_a_write_fault_never_reaches_replace_and_the_target_keeps_its_bytes(
        tmp_path, settings_path, monkeypatch):
    settings_path.write_text('{"keep": true}', encoding='utf-8')
    replaced = []
    monkeypatch.setattr(c.os, 'replace', lambda src, dst: replaced.append(dst))
    monkeypatch.setattr(c.os, 'fdopen', lambda fd, *a, **k: FullDisk(fd))

    assert c.save_settings({'default_permission': 'plan'}) is False
    assert replaced == []
    assert settings_path.read_text(encoding='utf-8') == '{"keep": true}'
    assert names(tmp_path) == ['archeus.json']


def test_a_whitespace_only_env_falls_through_and_a_real_value_wins(
        tmp_path, settings_path, monkeypatch):
    settings_path.write_text(json.dumps(
        {'claude_config_dir': str(tmp_path / 'from-setting')}), encoding='utf-8')
    monkeypatch.setenv('CLAUDE_CONFIG_DIR', '   ')
    assert c.get_config_dir() == str(tmp_path / 'from-setting')
    monkeypatch.setenv('CLAUDE_CONFIG_DIR', '')
    assert c.get_config_dir() == str(tmp_path / 'from-setting')
    monkeypatch.setenv('CLAUDE_CONFIG_DIR', str(tmp_path / 'from-env'))
    assert c.get_config_dir() == str(tmp_path / 'from-env')


def test_the_global_claude_md_is_used_only_when_no_account_is_named(tmp_path, monkeypatch):
    global_file = str(tmp_path / 'global' / 'CLAUDE.md')
    monkeypatch.setattr(c, 'global_claude_md', global_file)
    assert c.global_claude_md_for() == global_file
    assert c.global_claude_md_for('') == global_file
    acct = str(tmp_path / 'acct')
    assert c.global_claude_md_for(acct) == os.path.join(acct, 'CLAUDE.md')


def test_named_dirs_puts_the_default_first_and_keeps_the_first_of_equal_paths(tmp_path):
    default = str(tmp_path / 'home' / '.claude')
    work = str(tmp_path / 'work')
    other = str(tmp_path / 'other')
    out = c.named_dirs('default', default, [
        {'name': 'same', 'dir': default + os.sep},
        {'name': 'work', 'dir': work},
        {'name': 'nodir'},
        {'name': 'empty', 'dir': ''},
        {'dir': work},
        {'dir': other},
        'junk',
    ])
    assert out == [('default', default), ('work', work), (other, other)]


def test_all_config_dirs_drops_an_account_that_is_the_default_and_dedupes_accounts(
        tmp_path, settings_path, monkeypatch):
    home = str(tmp_path / 'home')
    monkeypatch.setattr(c, '_USERPROFILE', home)
    default = os.path.join(home, '.claude')
    work = str(tmp_path / 'work')
    settings_path.write_text(json.dumps({'accounts': [
        {'name': 'same', 'dir': default},
        {'name': 'work', 'dir': work},
        {'name': 'work2', 'dir': work},
    ]}), encoding='utf-8')
    assert c.all_config_dirs() == [('default', default), ('work', work)]


def test_account_env_with_a_named_harness_pins_its_home_and_pops_only_its_keys(
        tmp_path, monkeypatch):
    desc = {'home_env': 'SYNTH_HOME', 'env_pops': ('SYNTH_AUTH_A', 'SYNTH_AUTH_B')}
    asked = []

    def descriptor(hid=None):
        asked.append(hid)
        return desc

    def of_must_not_run(cfgdir=None):
        raise AssertionError('a named harness must not be inferred from the home')

    monkeypatch.setattr(harnesses, 'descriptor', descriptor)
    monkeypatch.setattr(harnesses, 'of', of_must_not_run)
    monkeypatch.setenv('SYNTH_AUTH_A', 'synthetic-a')
    monkeypatch.setenv('SYNTH_AUTH_B', 'synthetic-b')
    monkeypatch.setenv('SYNTH_KEEP', 'keep')
    before = dict(os.environ)
    home = str(tmp_path / 'acct')

    env = c.account_env(home, harness='synth')

    assert asked == ['synth']
    assert env['SYNTH_HOME'] == home
    assert 'SYNTH_AUTH_A' not in env and 'SYNTH_AUTH_B' not in env
    assert env['SYNTH_KEEP'] == 'keep'
    assert dict(os.environ) == before
    env['SYNTH_KEEP'] = 'changed'
    assert os.environ['SYNTH_KEEP'] == 'keep'


def test_the_workdir_marker_is_written_once_and_never_overwrites_a_users_gitignore(tmp_path):
    workdir = tmp_path / 'proj' / '.archeus'
    c._ensure_dir(str(workdir))
    marker = workdir / '.gitignore'
    assert marker.read_text(encoding='utf-8').endswith('*\n')
    marker.write_text('custom\n', encoding='utf-8')
    c._ensure_dir(str(workdir))
    assert marker.read_text(encoding='utf-8') == 'custom\n'


def test_a_failed_marker_write_is_swallowed_and_a_non_workdir_gets_no_marker(
        tmp_path, monkeypatch):
    real_open = open

    def refuse_the_marker(path, *args, **kwargs):
        if str(path).endswith('.gitignore'):
            raise PermissionError(13, 'denied')
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(c, 'open', refuse_the_marker, raising=False)
    workdir = tmp_path / 'proj' / '.archeus'
    c._ensure_dir(str(workdir))
    assert workdir.is_dir()
    assert not (workdir / '.gitignore').exists()

    src = tmp_path / 'proj' / 'src'
    c._ensure_dir(str(src))
    assert src.is_dir()
    assert not (src / '.gitignore').exists()

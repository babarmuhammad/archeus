"""T-1390: the highest-risk uncovered branches of `archeus/infra/paths.py` lines 28-135
(`is_absolute`, `archeus_home`, `refused_component`, `task_worktree`, `mission_worktree_path`,
`_worktree`), as tests.

Selected branches, denial and fail-closed first:
- `is_absolute` on the nt branch: a rootless '\\x' and a drive-relative 'C:x' are not absolute,
  'C:\\x' is, and a UNC share '\\\\server\\share\\x' is (paths.py `is_absolute`).
- `archeus_home` refuses a relative ARCHEUS_HOME and quotes at most 80 characters of it
  (`%.80r`), and refuses a `.ARCHEUS` component case-folded on the nt branch.
- `archeus_home` treats a whitespace-only ARCHEUS_HOME as absent and uses the platform default.
- `refused_component` refuses device names with or without an extension, `conin$`/`conout$`
  and a superscript-digit COM name; refuses unsafe characters; refuses a trailing dot or space,
  a `:` stream, `.git`, `.GIT` and `git~1`; allows `confetti` and `a.b` (the device match is on
  the stem only).
- `_worktree` (through `task_worktree`) refuses a bad project id, a bad mission id, and a leaf
  that fails the leaf pattern or `refused_component`, before any filesystem read.

Not selected, because tests/v1/unit/test_paths.py and test_gaps_infra_paths.py already assert
them: the POSIX `.archeus` refusal, the relative XDG_DATA_HOME default, the `_MISSION` key, the
earlier-layout directory and link cases, and the relative-home refusal for `rel`, `./h`, `../h`.

Each test names the source branch whose removal or inversion it catches. The nt branches are
reached through a fake `os` namespace monkeypatched onto `archeus.infra.paths` (ntpath is pure
Python), never by setting `os.name` globally. No symlink, no real home directory, no environment
read: every home is passed as a synthetic dict.
"""

import ntpath
import os
import types

import pytest

from archeus.infra import paths


def _nt(monkeypatch):
    fake = types.SimpleNamespace(name='nt', path=ntpath, environ=os.environ)
    monkeypatch.setattr(paths, 'os', fake)
    return fake


@pytest.mark.parametrize('value,want', [('\\x', False), ('C:x', False), ('C:\\x', True)],
                         ids=['rootless', 'drive-relative', 'drive-absolute'])
def test_is_absolute_on_windows_requires_a_drive_letter_and_a_root(monkeypatch, value, want):
    # paths.py is_absolute, nt branch: `ntpath.isabs(path) and bool(splitdrive(path)[0])`;
    # dropping the drive test lets a rootless '\x' through, and dropping isabs lets 'C:x'
    # through (it has a drive and no root, so it resolves against the drive's cwd)
    _nt(monkeypatch)
    assert paths.is_absolute(value) is want


def test_is_absolute_accepts_a_unc_share_as_a_drive(monkeypatch):
    # paths.py is_absolute, nt branch: splitdrive returns the whole '\\server\share' for a
    # UNC path, so the share counts as the drive and the path is absolute
    _nt(monkeypatch)
    assert paths.is_absolute('\\\\server\\share\\x') is True


def test_a_relative_home_error_quotes_at_most_eighty_characters(monkeypatch):
    # paths.py archeus_home: `'... %.80r' % (explicit,)`; without the 80-character cut a
    # 300-character value is echoed whole into the error and into any log line that carries it
    long = 'r' * 300
    with pytest.raises(ValueError) as err:
        paths.archeus_home({'ARCHEUS_HOME': long, 'HOME': '/h'}, 'linux')
    msg = str(err.value)
    assert 'absolute' in msg
    assert ('%.80r' % (long,)) in msg and long not in msg


def test_a_case_folded_legacy_component_is_refused_on_windows(monkeypatch):
    # paths.py archeus_home: `os.path.normcase(path)` lowercases on nt, so '.ARCHEUS' matches
    # LEGACY_DIRNAME; a case-sensitive compare would let 'C:\\Users\\u\\.ARCHEUS\\v1' through
    _nt(monkeypatch)
    with pytest.raises(ValueError, match='legacy'):
        paths.archeus_home({'ARCHEUS_HOME': 'C:\\Users\\u\\.ARCHEUS\\v1',
                            'USERPROFILE': 'C:\\Users\\u'}, 'win32')


def test_a_whitespace_only_home_is_absent_and_takes_the_platform_default():
    # paths.py archeus_home: `.strip()` runs before `if explicit:`, so '   ' falls through to
    # the XDG default instead of being treated as a relative path to refuse
    got = paths.archeus_home({'ARCHEUS_HOME': '   ', 'HOME': '/h'}, 'linux')
    assert got == os.path.abspath(os.path.join('/h', '.local', 'share', 'archeus'))


@pytest.mark.parametrize('name', ['conin$', 'CONOUT$', 'com\u00b9', 'COM1.log', 'lpt3.txt'],
                         ids=['conin', 'conout', 'superscript-com', 'com-with-ext', 'lpt-ext'])
def test_device_names_are_refused_with_or_without_an_extension(name):
    # paths.py refused_component: `_DEVICE.fullmatch(name.split('.')[0].rstrip(' '))`; the
    # stem is matched, so 'COM1.log' is refused, and the `conin$`/`conout$` and the
    # superscript-digit forms are device names too
    assert paths.refused_component(name) is True


@pytest.mark.parametrize('name', ['a.', 'a ', 'a:b', '.git', '.GIT', 'git~1', 'a<b', 'a|b',
                                  'a"b', 'a\x01b', 'a?'],
                         ids=['trailing-dot', 'trailing-space', 'stream', 'dot-git',
                              'dot-git-upper', 'git-alias', 'angle', 'pipe', 'quote',
                              'control', 'question'])
def test_names_windows_would_resolve_elsewhere_or_git_keeps_are_refused(name):
    # paths.py refused_component: `name[-1] in '. '`, `_UNSAFE`, and `casefold() in
    # ('.git', 'git~1')`; each is a name Windows maps to another entry or git owns
    assert paths.refused_component(name) is True


@pytest.mark.parametrize('name', ['confetti', 'a.b', 'console', 'com10'],
                         ids=['device-prefix', 'dotted', 'console-word', 'com-two-digits'])
def test_names_that_only_contain_a_device_or_git_prefix_are_allowed(name):
    # paths.py refused_component: the device test is fullmatch on the stem, so 'confetti'
    # (begins with 'con') and 'com10' (two digits) are plain names; 'a.b' has no device stem
    assert paths.refused_component(name) is False


@pytest.mark.parametrize('bad_project,bad_mission,bad_leaf', [
    ('prj_bad', 'msn_' + '0' * 26, 't1'),
    ('prj_' + '0' * 26, 'msn_bad', 't1'),
    ('prj_' + '0' * 26, 'msn_' + '0' * 26, 'a:b'),
    ('prj_' + '0' * 26, 'msn_' + '0' * 26, 'CON'),
], ids=['project-id', 'mission-id', 'stream-leaf', 'device-leaf'])
def test_a_bad_id_or_leaf_is_refused_before_any_disk_read(monkeypatch, tmp_path, bad_project,
                                                          bad_mission, bad_leaf):
    # paths.py _worktree: the id and leaf checks run before `_plain_dir`; the fake raises if
    # it is reached, so a refusal that came after a read would fail this test
    def no_read(path):
        raise AssertionError('a disk read before the refusal: %s' % path)
    monkeypatch.setattr(paths, '_plain_dir', no_read)
    with pytest.raises(ValueError):
        paths._worktree(bad_project, bad_mission, bad_leaf)


def test_a_leaf_ending_in_a_dot_is_refused_by_the_component_rule():
    # paths.py refused_component through the _worktree leaf check: a leaf that passes the
    # _LEAF pattern is still refused by the component rule when it ends in a dot
    with pytest.raises(ValueError, match='not a worktree directory name'):
        paths._worktree('prj_' + '0' * 26, 'msn_' + '0' * 26, 'task.')

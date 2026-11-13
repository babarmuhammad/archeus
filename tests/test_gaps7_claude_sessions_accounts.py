"""T-1318 · Close the highest-risk test gaps in claude_sessions/accounts.py (21-33).

Exact source range: ``claude_sessions/accounts.py`` lines 21-33 inclusive at the
current tip. The card's lines were re-located by reading the source: the range
now holds ``same_account_dir`` (21-29, the comparison on line 28) and the start
of ``_accounts`` (32-39); ``_resolved`` (42-43) is read as the context the card
names for probes 4 and 9. No source file is edited here; no new dependency.

Selected branches, ranked fail-closed first, then boundaries, then error paths:

 1. accounts.py:26-29  same_account_dir: different homes with the same basename never match
 2. accounts.py:26-27  an empty side never matches (the default account is the only ACTIVE one)
 3. accounts.py:28     tilde alias and absolute path compare equal after expansion
 4. accounts.py:28     an environment-variable spelling is not expanded here (strict xfail;
                       _resolved at accounts.py:43 expands it, so the two disagree)
 5. accounts.py:28     Windows mixed separators and case, modelled through ntpath
 6. accounts.py:28     case folds only under ntpath; POSIX differing-case paths stay distinct
 7. accounts.py:28     redundant dot component normalises to the same account
 8. accounts.py:28     trailing separator normalises; an unrelated sibling stays inactive
 9. accounts.py:28     non-env spellings agree with _resolved on identity
10. accounts.py:32-39  input settings are not mutated, and a sibling switch recalculates flags

Every path is under tmp_path. The OS path module is replaced per test through
monkeypatch on the accounts module attribute, never on the global os.path.
The home is pointed at tmp_path through both HOME and USERPROFILE, so the
expansion is the same on every platform.
"""

import copy
import ntpath
import os
import posixpath
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest                                     # noqa: E402

from claude_sessions import accounts              # noqa: E402


def _home(monkeypatch, tmp_path):
    home = str(tmp_path / 'u')
    monkeypatch.setenv('HOME', home)
    monkeypatch.setenv('USERPROFILE', home)
    return home


def _rows(active, *named_dirs):
    s = {'claude_config_dir': active,
         'accounts': [{'name': n, 'dir': d} for n, d in named_dirs]}
    return {n: flag for n, _d, flag in accounts._accounts(s)}


# ── 1, 2. different homes and empty sides ─────────────────────────────────

def test_same_basename_in_different_homes_is_not_the_same_account(tmp_path):
    a = str(tmp_path / 'a' / 'work')
    b = str(tmp_path / 'b' / 'work')

    rows = _rows(a, ('a-work', a), ('b-work', b))

    assert rows == {'default': False, 'a-work': True, 'b-work': False}, rows
    assert accounts.same_account_dir(b, a) is False


def test_empty_side_never_matches_even_a_dot_row(tmp_path):
    assert accounts.same_account_dir('', '') is False
    assert accounts.same_account_dir('.', '') is False
    assert accounts.same_account_dir('', '.') is False


# ── 3. tilde alias against absolute path ──────────────────────────────────

def test_tilde_alias_matches_absolute_home_path(monkeypatch, tmp_path):
    home = _home(monkeypatch, tmp_path)
    target = os.path.join(home, '.claude-work')

    assert accounts.same_account_dir('~/.claude-work', target) is True
    assert accounts.same_account_dir(target, '~/.claude-work') is True
    assert accounts.same_account_dir('~/.claude-other', target) is False


# ── 4. environment-variable spelling ──────────────────────────────────────

def test_env_spelling_resolves_to_the_active_path(monkeypatch, tmp_path):
    monkeypatch.setenv('ARCHEUS_T1318_ROOT', str(tmp_path))
    active = os.path.join(str(tmp_path), 'acc')

    assert os.path.normpath(accounts._resolved('$ARCHEUS_T1318_ROOT/acc')) \
        == os.path.normpath(active)


@pytest.mark.xfail(strict=True, reason=(
    'accounts.py:28 compares with expanduser only, while _resolved at '
    'accounts.py:43 also expands variables: a row spelled $VAR/acc resolves to '
    'the active home but is never marked ACTIVE'))
def test_env_spelling_marks_the_same_account_active(monkeypatch, tmp_path):
    monkeypatch.setenv('ARCHEUS_T1318_ROOT', str(tmp_path))
    active = os.path.join(str(tmp_path), 'acc')

    assert accounts.same_account_dir('$ARCHEUS_T1318_ROOT/acc', active) is True


# ── 5, 6. Windows and POSIX comparison through local path seams ───────────

def test_windows_mixed_separators_and_case_compare_equal_under_ntpath(monkeypatch):
    monkeypatch.setattr(accounts, 'os', SimpleNamespace(path=ntpath))

    assert accounts.same_account_dir('C:/Users/x/.acc-w', 'C:\\Users\\x\\.acc-w') is True
    assert accounts.same_account_dir('c:\\users\\X\\.ACC-W', 'C:\\Users\\x\\.acc-w') is True
    assert accounts.same_account_dir('C:\\Users\\x\\.acc-w', 'C:\\Users\\x\\.acc-o') is False


def test_posix_case_differences_stay_distinct(monkeypatch):
    monkeypatch.setattr(accounts, 'os', SimpleNamespace(path=posixpath))

    assert accounts.same_account_dir('/home/u/Acc', '/home/u/acc') is False
    assert accounts.same_account_dir('/home/u/acc', '/home/u/acc') is True


# ── 7, 8. redundant dot and trailing separator ────────────────────────────

def test_redundant_dot_component_is_the_same_account(tmp_path):
    base = str(tmp_path)
    active = os.path.join(base, 'acc')

    assert accounts.same_account_dir(os.path.join(base, '.', 'acc'), active) is True
    assert accounts.same_account_dir(os.path.join(base, 'acc', '.'), active) is True


def test_trailing_separator_is_the_same_account_and_sibling_is_not(tmp_path):
    acc = str(tmp_path / 'acc')
    sep = os.sep
    rows = _rows(acc + sep, ('acc', acc), ('acc-other', acc + '-other'))

    assert rows == {'default': False, 'acc': True, 'acc-other': False}, rows


# ── 9. non-env spellings agree with _resolved ─────────────────────────────

def test_non_env_spellings_agree_with_resolved_identity(monkeypatch, tmp_path):
    home = _home(monkeypatch, tmp_path)
    target = os.path.join(home, '.acc')
    spellings = [target, target + os.sep, '~/.acc', os.path.join(home, '.', '.acc')]

    for spelled in spellings:
        same = accounts.same_account_dir(spelled, target)
        resolved_same = (os.path.normpath(accounts._resolved(spelled))
                         == os.path.normpath(accounts._resolved(target)))
        assert same is resolved_same is True, spelled


# ── 10. inputs are not mutated and a sibling switch recalculates ──────────

def test_listing_leaves_settings_alone_and_sibling_switch_recalculates(tmp_path):
    w = str(tmp_path / 'w')
    w_alias = w + os.sep
    o = str(tmp_path / 'o')
    s = {'claude_config_dir': w_alias,
         'accounts': [{'name': 'work', 'dir': w},
                      {'name': 'other', 'dir': o}]}
    original = copy.deepcopy(s)

    first = accounts._accounts(s)
    assert s == original, 'listing mutated the caller settings'
    assert dict((n, f) for n, _d, f in first) == \
        {'default': False, 'work': True, 'other': False}

    s['claude_config_dir'] = o
    second = accounts._accounts(s)
    assert s['accounts'] == original['accounts']
    assert dict((n, f) for n, _d, f in second) == \
        {'default': False, 'work': False, 'other': True}, second

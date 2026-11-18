"""T-1458: gap probes for archeus/core/homes.py lines 34-101 called directly with an
explicit platform and path_flavour: the non-string and whitespace branches of
_canon, _windows_style, the MSYS flavour gate on linux, dot segments and the bare
drive, the escaping and case helpers, and the keyed public id. The default secret
is monkeypatched; no real home, path or secret is read.
"""

import re

import pytest

from archeus.core import homes as H
from archeus.infra import discovery


def test_canon_refuses_a_non_string_and_strips_surrounding_space():
    # homes.py:40-42 non-str gives None; :42 strips before any pattern is tried
    assert H._canon(7) is None
    assert H._canon('  C:/x  ') == 'C:/x'


@pytest.mark.parametrize('s, want', [
    ('C:/x', True), ('//srv/x', True), (r'\\srv\x', True), ('/a\\b', False), ('relative', False),
])
def test_windows_style_is_a_drive_or_a_leading_double_separator(s, want):
    # homes.py:54-55 only a drive or a leading double separator switches to Windows form
    assert H._windows_style(s) is want


def test_an_msys_path_is_converted_only_when_the_platform_or_flavour_says_windows():
    # homes.py:56-58 path_flavour None and platform 'linux' keeps '/c/Users' literal
    assert H._canon('/c/Users', platform='linux') == '/c/Users'
    assert H.norm_path('/c/Users', platform='linux') == '/c/Users'
    assert H.norm_path('/c/Users', platform='win32') == 'c:/users'


def test_dot_segments_collapse_to_the_root_and_a_bare_msys_drive_gains_a_slash():
    # homes.py:59 normpath; :60-61 a bare 'c:' regains its trailing slash
    assert H.norm_path('/a/../..', path_flavour='posix') == '/'
    assert H.norm_path('/c', path_flavour='windows') == 'c:/'
    assert H.norm_path('C:/', path_flavour='windows') == 'c:/'


@pytest.mark.parametrize('s', ['a.b+c', '(x)|y', 'a?b*', '[z]'])
def test_comp_matches_its_text_literally(s):
    # homes.py:83-85 re.escape of every form, so metacharacters are not patterns
    pat = H._comp(s)
    assert re.fullmatch(pat, s)
    assert re.fullmatch(pat, s + 'X') is None


def test_win_is_case_insensitive_only_when_asked():
    # homes.py:88-89 (?i:...) wraps the pattern only when win is True
    assert re.fullmatch(H._win(True, 'abc'), 'ABC')
    assert re.fullmatch(H._win(False, 'abc'), 'ABC') is None


def test_the_public_account_id_is_a_keyed_hash_that_never_shows_the_key(monkeypatch):
    # homes.py:92-94 'account:' + hex HMAC keyed by the secret; the key text is not in it
    monkeypatch.setattr(discovery, 'public_account_secret', lambda: b'\x01' * 32)
    key = 'claude_code:example-home'
    pid = H.public_account_id(key)
    assert re.fullmatch(r'account:[0-9a-f]{64}', pid)
    assert key not in pid
    monkeypatch.setattr(discovery, 'public_account_secret', lambda: b'\x02' * 32)
    assert H.public_account_id(key) != pid

"""T-726: the highest-risk uncovered branches of archeus/core/homes.py.

Fail-closed and denial first: junk home_refs (non-strings, blanks) are dropped at
construction and never become matchers or norms, a default key padded with spaces
still becomes its handle instead of surviving the projection raw, a tuple projects
its elements like a list, and a default account's unusable home_ref still leaves
its key mapped while contributing nothing matchable. Then the boundaries: `cut_safe`
must keep a whole home cut exactly at its end, must fall back when the Homes has no
default keys at all, and must project list elements under a path key one by one;
a dot-segment collapse to a bare drive is the drive root, not "not a path". Then
the error and OS paths: a bare `~` home adds no literal-`~` matcher, UNC and default
homes are never 8.3-probed (only registered drive homes are), the `file://` host
`LOCALHOST` is localhost whatever its case, a relative registered home is matched
via its absolute resolution, and the short-name probe is a no-op off Windows.

Same style and seams as tests/v1/unit/test_homes.py: homes built from strings with
`shorts` injected (the 8.3 seam), `_win_short` monkeypatched only where the OS
guard itself is the subject, no disk, no network, no real process, nothing that
needs Windows — every value under test is spelled the same way the test spells it.
"""

import sys

import pytest

from archeus.core import homes as H

HOME = r'C:\Users\user1\.claude-work'
KEY = r'claude_code:c:\users\user1\.claude'
DEFAULT = ('claude_code', KEY, r'C:\Users\user1\.claude')
UNC = r'\\srv\share\u\c'
WIN_HOME = {'USERPROFILE': r'C:\Users\user1', 'HOME': r'C:\Users\user1'}


def _homes(*registered, defaults=(), shorts=lambda p: None, **kw):
    kw.setdefault('path_flavour', 'windows')
    return H.Homes(list(registered or (HOME,)), list(defaults), shorts=shorts, **kw)


def _pin_win_env(monkeypatch):
    """Expanduser must not follow the developer/test-runner's real home on any
    platform: pin the spelling every tilde-relative assertion expects."""
    for k, v in WIN_HOME.items():
        monkeypatch.setenv(k, v)


def test_a_junk_registered_home_never_becomes_a_matcher_or_a_norm():
    # homes.py:113 drops non-string / blank registered homes. Without the filter
    # the constructor crashes on None/5 (home.strip()) and a blank home resolves
    # through abspath to the runner's cwd, which would then null any cwd spelling
    # under a path key.
    junk = _homes()  # reference: exactly one registered home, one pattern
    assert len(junk.patterns) == 1 and junk.norms == {'c:/users/user1/.claude-work'}
    h = H.Homes([None, 5, '', '   ', HOME], shorts=lambda p: None, path_flavour='windows')
    assert len(h.patterns) == 1
    assert h.norms == {'c:/users/user1/.claude-work'}
    assert H.scrub_text('x ' + HOME + ' y', h) == 'x its home y'


@pytest.mark.parametrize('bad', [None, '', '   ', 7, ['x'], {}])
def test_a_default_account_with_an_unusable_home_ref_keeps_its_key(bad):
    # homes.py:114 drops unusable home_refs (no crash, nothing matchable added),
    # while account_key_map still maps the key: identity survives a home_ref the
    # projection cannot use, and the dropped ref never probes and never scrubs.
    row_bad = ('h', 'h:/a/bad', bad)
    row_good = ('h', KEY, HOME)
    probes = []
    h = H.Homes([], [row_bad, row_good], shorts=lambda p: probes.append(p) or None,
                path_flavour='windows')
    assert set(h.keys) == {'h:/a/bad', KEY}
    assert h.norms == {'c:/users/user1/.claude-work'}
    assert probes == []                                  # default homes are never probed
    assert H.scrub_text('h:/a/bad', h) == h.keys['h:/a/bad']
    assert H.scrub_text(HOME, h) == 'its home'


def test_a_padded_default_key_still_becomes_its_handle():
    # homes.py:222 looks the whole value up with x.strip(): a stored value with
    # stray whitespace must still be replaced by its public id, or the raw key
    # (home path included) survives the projection.
    h = _homes(defaults=[DEFAULT])
    public = h.keys[KEY]
    assert public == H.public_account_id(KEY)
    for padded in (' ' + KEY, KEY + ' ', '\t' + KEY + '  '):
        assert H.public_value({'account': padded}, h) == {'account': public}
        assert H.public_value({'who': {'reviewer': [padded]}}, h) == {'who': {'reviewer': [public]}}


def test_a_tuple_projects_its_elements_exactly_like_a_list():
    # homes.py:217 recurses into tuples too; if `tuple` were dropped the tuple
    # would hit the non-string fast path and every home/key inside it would be
    # projected nowhere, raw.
    h = _homes(defaults=[DEFAULT])
    out = H.public_value({'reason': [('ran ' + HOME), {'a': KEY}, 4]}, h,
                         text_keys=('reason',))
    assert out == {'reason': ['ran its home', {'a': h.keys[KEY]}, 4]}


@pytest.mark.parametrize('value,want', [
    ('relative/thing', 'relative/thing'),      # not absolute: kept byte-identical
    (r'C:\Other\place', r'C:\Other\place'),    # an absolute non-home: kept
    ('its home', 'its home'),                  # already-projected text: kept
    ('c:/USERS/user1/.CLAUDE-WORK/', None),      # the home, other case/separators
    (HOME, None),
])
def test_only_an_actual_home_is_nulled_under_a_path_key(value, want):
    # homes.py:225 nulls only when norm_path(x) is one of the norms built at
    # homes.py:120-121 (which drops spellings that do not canonicalize): dropping
    # the `in norms` test would None every path-keyed string; widening matching
    # to substrings would null 'relative/thing' too.
    h = _homes(HOME)
    assert H.public_value({'ref': value}, h, path_keys=('ref',)) == {'ref': want}


def test_a_home_with_a_non_canonical_spelling_never_adds_none_to_norms(monkeypatch):
    # homes.py:120-121 keeps spellings that do not canonicalize out of `norms`:
    # a stored '~/.work' canonicalizes to None, and if that None entered norms,
    # every whole non-path string under a path key (norm_path None) would match
    # it and be nulled — the projection would eat relative values wholesale.
    _pin_win_env(monkeypatch)
    h = _homes('~/.work')
    assert None not in h.norms and h.norms == {'c:/users/user1/.work'}
    assert H.public_value({'ref': 'relative/thing'}, h, path_keys=('ref',)) \
        == {'ref': 'relative/thing'}
    assert H.public_value({'ref': 'C:\\Users\\user1\\.work'}, h, path_keys=('ref',)) == {'ref': None}


def test_cut_safe_at_the_exact_home_boundaries_keeps_what_is_visible():
    # homes.py:205 keeps a cut at a span's start or end (`a < cut < b` is strict):
    # a non-strict end test would walk a cut that already keeps the whole home
    # back to its start and lose the visible home; a cut before it is untouched.
    h = _homes(HOME)
    text = 'q ' + HOME + ' tail'
    start, end = 2, 2 + len(HOME)
    assert H.cut_safe(text, h, start) == text[:start]
    assert H.cut_safe(text, h, end) == text[:end]
    assert H.cut_safe(text, h, end + 1) == text[:end + 1]
    assert H.cut_safe(text, h, end - 1) == text[:start]   # a split home falls back


def test_cut_safe_when_the_homes_has_no_default_keys_at_all():
    # homes.py:203 adds `_key_rx` to the span scan only if it exists; removing the
    # conditional passes None into the finditer loop and crashes every cut for a
    # Homes built without default accounts.
    h = _homes(HOME)
    assert h._key_rx is None
    text = 'q ' + HOME + ' tail'
    assert H.cut_safe(text, h, 4) == 'q '
    assert H.cut_safe(text, h, 2 + len(HOME)) == 'q ' + HOME
    assert H.cut_safe('abcdefghij', h, 4) == 'abcd'


def test_a_list_under_a_path_key_is_projected_element_by_element():
    # homes.py:218 hands the current key down the list recursion, so each element
    # of a list sitting under a path key is path-checked on its own; drop `_key`
    # from the recursion and a home stored as a list element leaks through.
    h = _homes(HOME)
    assert H.public_value({'ref': [HOME, 'keepme', 'c:/users/user1/.claude-work']}, h,
                          path_keys=('ref',)) == {'ref': [None, 'keepme', None]}


def test_a_dot_segment_collapse_to_a_drive_is_the_drive_root():
    # homes.py:60-61: normpath can leave a bare 'C:', which is the drive root —
    # without the fix-up `_DRIVE` rejects it, norm_path says "not a path", and a
    # home or path-keyed value spelled with dot segments silently never matches.
    assert H.norm_path(r'C:\a\..', path_flavour='windows') == 'c:/'
    assert H.norm_path('file:///D:/x/../y/..', path_flavour='windows') == 'd:/'
    assert H.norm_path(r'C:\a\..\Users\user1\.claude-work', path_flavour='windows') \
        == 'c:/users/user1/.claude-work'


def test_a_bare_tilde_home_adds_no_literal_tilde_matcher(monkeypatch):
    # homes.py:143-147: a spelling that cannot canonicalize contributes a tilde
    # alternative only when it is `~/sub`; a bare '~' contributes none (the only
    # matcher is the expanded home), and `continue` keeps the None canonical form
    # out of the drive/UNC code below. Weaken the guard and ' ~! ' is scrubbed;
    # drop `continue` and the constructor dies on c=None.
    _pin_win_env(monkeypatch)
    h = _homes('~')
    assert H.scrub_text('hi ~! there', h) == 'hi ~! there'
    assert H.scrub_text('~ ~/ ~/x ~x ~.', h) == '~ ~/ ~/x ~x ~.'
    assert H.scrub_text(r'cd C:\Users\user1\x', h) == r'cd its home\x'


def test_only_a_registered_drive_home_is_probed_for_short_names():
    # homes.py:171 probes only when the canonical form is a drive home (`m`) and
    # the home is registered (`probe`): 8.3 names exist only under drives, and
    # historical identity must never touch the OS. An UNC home, or any default
    # home, must leave `shorts` untouched.
    unc_calls, def_calls = [], []
    assert H.scrub_text(UNC + r'\x', _homes(UNC, shorts=lambda p: unc_calls.append(p) or None)) \
        == 'its home\\x'
    assert unc_calls == []
    h = H.Homes([], [DEFAULT], shorts=lambda p: def_calls.append(p) or None,
                path_flavour='windows')
    assert H.scrub_text(r'C:\Users\user1\.claude\x', h) == 'its home\\x'
    assert def_calls == []
    drive_calls = []
    H.Homes([HOME], shorts=lambda p: drive_calls.append(p) or None, path_flavour='windows')
    assert len(drive_calls) > 1                      # registered drive homes do probe


def test_the_file_url_localhost_host_is_localhost_whatever_its_case():
    # homes.py:46 compares host.lower() against 'localhost': compare case
    # sensitively and 'file://LOCALHOST/C:/x' becomes a UNC to host LOCALHOST, so
    # its home spelling no longer canonicalizes to the home.
    url = 'file://LOCALHOST/C:/Users/user1/.claude-work/x'
    assert H.norm_path(url, path_flavour='windows') == 'c:/users/user1/.claude-work/x'
    assert H.scrub_text('read ' + url + ' now', _homes(HOME)) == 'read its home/x now'


def test_a_relative_registered_home_is_matched_by_its_absolute_resolution(tmp_path, monkeypatch):
    # homes.py:182-183: a home whose only spelling is relative gets an abspath
    # fallback spelling — without it the home canonicalizes to nothing, produces
    # no matcher and no norm, and its real absolute path leaks unscrubbed.
    _pin_win_env(monkeypatch)
    monkeypatch.chdir(tmp_path)
    h = _homes('logs')
    assert h.norms == {H.norm_path(str(tmp_path / 'logs'), path_flavour='windows')}
    assert H.scrub_text('log at ' + str(tmp_path / 'logs') + '/day.txt', h) \
        == 'log at its home/day.txt'


@pytest.mark.skipif(sys.platform == 'win32',
                    reason='the guard is the non-Windows branch; on Windows the probe runs')
def test_the_short_name_probe_is_a_no_op_off_windows(monkeypatch):
    # homes.py:72-73: _win_short returns None before importing ctypes off Windows;
    # without the guard the probe reaches for ctypes.WinDLL, and a short-name probe
    # that should degrade softly would instead be an import error on Linux/macOS.
    # `None` in sys.modules makes any `import ctypes` raise, so the assert below
    # passes only while the guard short-circuits before the import.
    monkeypatch.setitem(sys.modules, 'ctypes', None)
    assert H._win_short(r'C:\Users\user1\.claude-work') is None

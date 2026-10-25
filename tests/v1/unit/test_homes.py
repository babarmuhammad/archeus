"""T-144 slice 1: the home spelling matcher (design §2 vectors). No disk: every
8.3 name is injected through `shorts`."""

import copy
from pathlib import Path
import re
import subprocess
import sys

import pytest

from archeus.core import homes as H

HOME = r'C:\Users\mab\.claude-work'
SHORTS = {'c:/users/mab': 'C:/Users/MAB~1', 'c:/users/mab/.claude-work': 'C:/Users/MAB~1/CLAUDE~1'}
KEY = r'claude_code:c:\users\mab\.claude'
DEFAULT = ('claude_code', KEY, r'C:\Users\mab\.claude')


def _homes(*registered, defaults=(), shorts=SHORTS):
    return H.Homes(list(registered or (HOME,)), list(defaults), shorts=lambda p: shorts.get(p.lower()), path_flavour='windows')


def scrub(v, *registered, **kw):
    return H.scrub_text('read %s now' % v, _homes(*registered, **kw))


MATCH = [
    (HOME, ''),
    (r'c:\Users\mab\.claude-work\projects\a.jsonl', r'\projects\a.jsonl'),
    (r'C:\users\MAB\.CLAUDE-WORK\x', r'\x'),
    ('C:/Users/mab/.claude-work/projects/a.jsonl', '/projects/a.jsonl'),
    (r'C:\Users\mab/.claude-work\x', r'\x'),
    (r'C:\Users\\mab\.claude-work', ''),
    ('/c/Users/mab/.claude-work/projects/a.jsonl', '/projects/a.jsonl'),
    ('/C/Users/mab/.claude-work', ''),
    ('/cygdrive/c/Users/mab/.claude-work/x', '/x'),
    ('/mnt/c/Users/mab/.claude-work/x', '/x'),
    ('file:///C:/Users/mab/.claude-work/x', '/x'),
    ('file:///c%3A/Users/mab/.claude-work/x', '/x'),
    ('file://localhost/C:/Users/mab/.claude-work/x', '/x'),
    (r'\\?\C:\Users\mab\.claude-work\x', r'\x'),
    ('//?/C:/Users/mab/.claude-work/x', '/x'),
    (r'C:\Users\MAB~1\.claude-work\x', r'\x'),
    (r'C:\Users\MAB~1\CLAUDE~1\x', r'\x'),
    ('C:\\Users\\mab\\.claude-work\\', '\\'),
]

NO_MATCH = [
    r'C:\Users\mab\.claude-workshop\x',
    r'C:\Users\mab\.claude-work2',
    r'C:\Users\mab\.claude-work.bak',
    r'C:\Users\mab\.claude-work-old',
    r'D:\Users\mab\.claude-work',
    r'C:\Users\mab2\.claude-work',
    r'C:\Users\mab',
    r'xC:\Users\mab\.claude-work',
    '/x/c/Users/mab/.claude-work',
    r'\\srv\share\Users\mab\.claude-work',
    r'C:\Users\MAB~1\CLAUDE~2\x',
]


@pytest.mark.parametrize('v,suffix', MATCH)
def test_a_spelling_of_the_home_is_replaced_and_its_suffix_kept(v, suffix):
    assert scrub(v) == 'read its home%s now' % suffix


@pytest.mark.parametrize('v', NO_MATCH)
def test_a_look_alike_is_left_byte_identical(v):
    assert scrub(v) == 'read %s now' % v


@pytest.mark.parametrize('v,suffix', [m for m in MATCH if 'MAB~1' not in m[0]])
def test_scrub_and_norm_path_agree_on_every_spelling(v, suffix):
    n, h = H.norm_path(v, path_flavour='windows'), H.norm_path(HOME, path_flavour='windows')
    assert n == h or n.startswith(h + '/')


def test_the_eight_dot_three_form_needs_the_injected_short_name():
    assert scrub(r'C:\Users\MAB~1\CLAUDE~1\x', shorts={}) == r'read C:\Users\MAB~1\CLAUDE~1\x now'


def test_a_failing_short_name_probe_is_soft():
    def boom(_p):
        raise OSError('no such path')
    h = H.Homes([HOME], shorts=boom)
    assert H.scrub_text(HOME + r'\x', h) == r'its home\x'
    assert H.Homes([r'C:\no\such\home'], shorts=boom).patterns


def test_a_sentence_dot_quotes_and_parens_still_match():
    h = _homes()
    assert H.scrub_text('in %s.' % HOME, h) == 'in its home.'
    assert H.scrub_text('"%s" (%s)' % (HOME, HOME), h) == '"its home" (its home)'
    assert H.scrub_text('%s then %s' % (HOME, HOME + r'\y'), h) == r'its home then its home\y'


@pytest.mark.parametrize('prefix', [r'err\n', r'err\t', r'err\r', '-', r'\\'])
def test_escaped_controls_and_punctuation_allow_left_boundary(prefix):
    assert H.scrub_text(prefix + HOME + r'\x', _homes()) == prefix + r'its home\x'


def test_a_typed_tilde_spelling_matches(monkeypatch):
    monkeypatch.setenv('USERPROFILE', r'C:\Users\mab')
    monkeypatch.setenv('HOME', r'C:\Users\mab')
    h = _homes('~/.claude-work')
    assert H.scrub_text('see ~/.claude-work/x', h) == 'see its home/x'
    assert H.scrub_text('see ~/.claude-workshop', h) == 'see ~/.claude-workshop'
    assert H.scrub_text(r'see C:\Users\mab\.claude-work\x', h) == r'see its home\x'


def test_the_sibling_of_a_shorter_home_is_not_taken():
    h = _homes(r'C:\Users\mab\.claude')
    t = r'cd C:\Users\mab\.claude-tools\repo'
    assert H.scrub_text(t, h) == t
    assert H.scrub_text(r'C:\Users\mab\.claude\x', h) == r'its home\x'


@pytest.mark.parametrize('v,suffix', [
    ('//SRV/share/u/c/x', '/x'), ('file://srv/share/u/c/x', '/x'),
    (r'\\?\UNC\srv\share\u\c\x', r'\x'), (r'\\srv\share\u\c', ''),
])
def test_a_unc_home_matches_its_family(v, suffix):
    assert scrub(v, r'\\srv\share\u\c') == 'read its home%s now' % suffix


def test_a_unc_home_is_not_a_drive_home():
    assert scrub(r'C:\srv\share\u\c', r'\\srv\share\u\c') == r'read C:\srv\share\u\c now'


def test_a_posix_home_is_case_sensitive():
    h = H.Homes(['/home/mab/.claude'], shorts=lambda p: None)
    assert H.scrub_text('/home/mab/.claude/x', h) == 'its home/x'
    for t in ('/home/Mab/.claude/x', '/home/mab/.claudex', '/home/mab/.claude-x'):
        assert H.scrub_text(t, h) == t


def test_a_default_key_becomes_its_handle_whole_or_inside_text():
    h = _homes(defaults=[DEFAULT])
    assert H.scrub_text(KEY, h) == H.public_account_id(KEY)
    t = 'task T1 on %s (approval a1)' % KEY
    assert H.scrub_text(t, h) == 'task T1 on %s (approval a1)' % H.public_account_id(KEY)
    assert H.scrub_text(KEY + '-tools', h) == KEY + '-tools'
    assert h.keys == {KEY: H.public_account_id(KEY)}


def test_a_default_home_path_is_scrubbed_too():
    assert H.scrub_text(r'no Claude login in C:\Users\mab\.claude', _homes(defaults=[DEFAULT])) \
        == 'no Claude login in its home'


@pytest.mark.parametrize('text', [
    'plain', '', 'C:\\Users\\mab\\.claude-work\\projects\\a', 'x ' + HOME + ' y ' + KEY,
    'its home\\x', 'account:' + 'a' * 64, 'file:///c%3A/Users/mab/.claude-work/x',
])
def test_scrub_is_idempotent(text):
    h = _homes(defaults=[DEFAULT])
    once = H.scrub_text(text, h)
    assert H.scrub_text(once, h) == once


def test_a_non_string_is_returned_as_is():
    assert H.scrub_text(None, _homes()) is None
    assert H.scrub_text(5, _homes()) == 5


@pytest.mark.parametrize('s,want', [
    (r'C:\a\..\Users\mab\.claude-work' + '\\', 'c:/users/mab/.claude-work'),
    ('/c/Users/./mab/.claude-work', 'c:/users/mab/.claude-work'),
    ('file:///C:/Users/mab/.claude-work/', 'c:/users/mab/.claude-work'),
    ('file:///c%3A/Users/mab/.claude-work', 'c:/users/mab/.claude-work'),
    (r'\\?\C:\Users\mab\.claude-work', 'c:/users/mab/.claude-work'),
    (r'\\?\UNC\srv\share\x', '//srv/share/x'),
    ('file://srv/share/x', '//srv/share/x'),
    (r'\\Srv\Share\x', '//srv/share/x'),
    ('/mnt/c/Users/mab', 'c:/users/mab'),
    ('/home/Mab/.claude/', '/home/Mab/.claude'),
    (r'/home/mab/a\b', r'/home/mab/a\b'),
])
def test_norm_path_gives_one_form_per_place(s, want):
    assert H.norm_path(s, path_flavour='windows') == want


@pytest.mark.parametrize('s', ['relative/path', '~/x', '', None, 'C:foo', 'file://'])
def test_norm_path_refuses_what_is_not_absolute(s):
    assert H.norm_path(s) is None


def test_public_value_maps_keys_and_nulls_home_paths_only_under_path_keys():
    h = _homes(defaults=[DEFAULT])
    body = {'account_ref': HOME, 'home_ref': 'c:/users/mab/.claude-work/', 'title': HOME,
            'root': HOME, 'who': {'reviewer': [KEY, 'x']}, 'n': 3, 'reason': 'no login in ' + HOME,
            'note': 'see ' + HOME, 'account': KEY}
    before = copy.deepcopy(body)
    out = H.public_value(body, h, text_keys=('reason',), path_keys=('account_ref', 'home_ref'))
    assert body == before
    assert out == {'account_ref': None, 'home_ref': None, 'title': HOME, 'root': HOME,
                   'who': {'reviewer': [H.public_account_id(KEY), 'x']}, 'n': 3,
                   'reason': 'no login in its home', 'note': 'see ' + HOME,
                   'account': H.public_account_id(KEY)}
    assert H.public_value(out, h, text_keys=('reason',), path_keys=('account_ref', 'home_ref')) == out


def test_public_value_scrubs_nested_strings_under_a_text_key():
    h = _homes()
    out = H.public_value({'consequences': ['ran ' + HOME, {'a': HOME}], 'other': HOME}, h,
                         text_keys=('consequences',))
    assert out == {'consequences': ['ran its home', {'a': 'its home'}], 'other': HOME}


@pytest.mark.parametrize('home', ['/c/Foo', '/mnt/c/Foo', '/cygdrive/c/Foo'])
@pytest.mark.parametrize('platform', ['linux', 'win32'])
def test_native_posix_msys_names_stay_literal(home, platform):
    h = H.Homes([home], shorts=lambda _: None, platform=platform, path_flavour='posix')
    assert H.norm_path(home, platform=platform, path_flavour='posix') == home
    assert H.scrub_text(home + '/x', h) == 'its home/x'
    for text in (r'C:\Foo\x', home.lower() + '/x', home.replace('/', '\\')):
        assert H.scrub_text(text, h) == text
    assert H.norm_path(home + r'/a\b', path_flavour='posix') == home + r'/a\b'


def test_windows_platform_enables_aliases_without_flavour_override():
    assert H.norm_path('/mnt/c/Foo', platform='win32') == 'c:/foo'
    assert H.norm_path('/mnt/c/Foo') == '/mnt/c/Foo'


@pytest.mark.parametrize('flavour', ['windows', 'msys', 'cygwin', 'wsl'])
@pytest.mark.parametrize('path', ['/c/Foo', '/mnt/c/Foo', '/cygdrive/c/Foo'])
def test_explicit_windows_flavours_reclassify_msys_paths(flavour, path):
    assert H.norm_path(path, path_flavour=flavour) == 'c:/foo'
    h = H.Homes([path], shorts=lambda _: None, path_flavour=flavour)
    assert H.scrub_text(r'C:\FOO\x', h) == r'its home\x'
    assert H.public_value({'ref': r'C:\Foo'}, h, path_keys=('ref',)) == {'ref': None}


@pytest.mark.parametrize('path', ['C:', 'C:foo', 'C:foo/bar'])
def test_drive_relative_paths_are_rejected(path):
    assert H.norm_path(path, path_flavour='windows') is None
    assert H.scrub_text(path, _homes('C:\\')) == path
    assert H.Homes([path], shorts=lambda _: None).patterns == []


def test_localhost_url_prefix_keeps_suffix():
    assert scrub('file://localhost/C:/Users/mab/.claude-work/x') == 'read its home/x now'
    assert H.norm_path('file://localhost/C:/Users/mab/.claude-work/x') == 'c:/users/mab/.claude-work/x'


def test_device_prefix_keeps_suffix():
    assert scrub(r'\\.\C:\Users\mab\.claude-work\x') == r'read its home\x now'
    assert H.norm_path(r'\\.\C:\Users\mab\.claude-work\x') == 'c:/users/mab/.claude-work/x'


def test_url_encoded_space_matches():
    h = _homes(r'C:\Users\Example User\.claude')
    text = 'file:///C:/Users/Example%20User/.claude/x'
    assert H.scrub_text(text, h) == 'its home/x'
    assert H.norm_path(text) == 'c:/users/example user/.claude/x'


@pytest.mark.parametrize('home,text,want', [
    ('C:\\', 'C:\\', 'its home\\'),
    ('C:\\', r'C:\x', r'its home\x'),
    ('C:\\', 'file://localhost/C:/x', 'its home/x'),
    ('C:\\', 'C:/\\x', 'its home/\\x'),
    ('C:\\', 'C:', 'C:'),
    ('C:\\', 'C:foo', 'C:foo'),
    ('\\\\srv\\share\\', '\\\\srv\\share\\', 'its home\\'),
    ('\\\\srv\\share\\', r'\\srv\share\x', r'its home\x'),
    ('\\\\srv\\share\\', r'\\srv\share2\x', r'\\srv\share2\x'),
    ('/', '/', 'its home/'),
    ('/', '/x', 'its home/x'),
    ('/', '//x', 'its home//x'),
])
def test_root_separator_is_structural_and_preserved(home, text, want):
    h = H.Homes([home], shorts=lambda _: None)
    assert H.scrub_text(text, h) == want
    assert H.scrub_text(want, h) == want
    assert H.norm_path(home) is not None


HISTORY = [DEFAULT, ('claude_code', r'claude_code:d:\retired\.claude', r'D:\retired\.claude')]


def test_distinct_exact_stored_keys_have_distinct_public_ids():
    rows = HISTORY + [('claude_code', KEY.upper(), DEFAULT[2])]
    ids = H.account_key_map(rows)
    assert len(set(ids.values())) == len(rows)
    assert H.account_key_map(reversed(rows)) == ids
    h = H.Homes(default_accounts=rows, shorts=lambda _: None)
    for key, public_id in ids.items():
        assert H.scrub_text(key, h) == public_id
        assert H.public_value({'account': key}, h) == {'account': public_id}
    assert H.public_value({'account': 'registered-a1'}, h) == {'account': 'registered-a1'}


def test_path_keys_with_missing_homes_are_opaque():
    rows = [('h', KEY, None), ('h', 'h:/retired/default', ''),
            ('fake', 'fake:fake_local', None)]
    assert H.account_key_map(rows) == {key: H.public_account_id(key)
                                       for _, key, _ in rows[:2]}


def test_same_key_id_survives_restart():
    code = ('import sys; sys.path.insert(0, %r); '
            'from archeus.core.homes import public_account_id; print(public_account_id(%r))'
            % (str(Path(H.__file__).resolve().parents[2]), KEY))
    expected = H.public_account_id(KEY)
    for _ in range(2):
        assert subprocess.check_output([sys.executable, '-I', '-c', code], text=True).strip() == expected
    assert H.Homes(default_accounts=HISTORY, shorts=lambda _: None).keys[KEY] == expected


def test_historical_keys_map_whole_and_embedded_without_mutation():
    rows = copy.deepcopy(HISTORY)
    h = H.Homes(default_accounts=iter(rows), shorts=lambda _: None)
    assert set(h.keys) == {row[1] for row in HISTORY}
    for _, key, _ in HISTORY:
        public_id = H.public_account_id(key)
        body = {'nested': [{'account': key}], 'reason': 'task on ' + key}
        before = copy.deepcopy(body)
        out = H.public_value(body, h, text_keys=('reason',))
        assert out == {'nested': [{'account': public_id}], 'reason': 'task on ' + public_id}
        assert body == before
        assert H.public_value(out, h, text_keys=('reason',)) == out
    assert rows == HISTORY


def test_historical_identity_never_probes_homes(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('historical identity probed a home')
    with monkeypatch.context() as patch:
        patch.setattr(H, '_win_short', forbidden)
        real_stat = H.os.stat

        def stat(path, *args, **kwargs):
            if str(path).lower().replace('\\', '/').startswith(
                    ('c:/users/mab/.claude', 'd:/retired/.claude')):
                forbidden(path)
            return real_stat(path, *args, **kwargs)
        patch.setattr(H.os, 'stat', stat)
        patch.setattr(H.os, 'scandir', forbidden)
        ids = H.account_key_map(HISTORY)
        h = H.Homes(default_accounts=HISTORY)
    assert len(ids) == 2
    assert len(h.keys) == 2
    assert H.scrub_text(HISTORY[1][1], h) == h.keys[HISTORY[1][1]]


def test_public_ids_reveal_no_home_or_key_material():
    for _, key, home in HISTORY:
        public_id = H.public_account_id(key)
        assert re.fullmatch(r'account:[0-9a-f]{64}', public_id)
        for material in (key, home, 'claude', 'users', 'retired', 'mab', '/', '\\'):
            assert material.lower() not in public_id.lower()


def test_public_ids_are_install_specific_hmac(tmp_path, monkeypatch):
    import hashlib
    import hmac
    import os
    import stat

    installs = [tmp_path / name for name in ('install-a', 'install-b')]
    ids = []
    for home in installs:
        monkeypatch.setenv('ARCHEUS_HOME', str(home))
        ids.append(H.public_account_id(KEY))
        path = home / 'run' / 'public-account-secret'
        secret = path.read_bytes()
        assert len(secret) == 32
        assert ids[-1] == 'account:' + hmac.new(secret, KEY.encode(), hashlib.sha256).hexdigest()
        assert H.public_account_id(KEY) == ids[-1]
        assert path.read_bytes() == secret
        if os.name != 'nt':
            assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert ids[0] != ids[1]
    assert all(value != 'account:' + hashlib.sha256(KEY.encode()).hexdigest() for value in ids)

"""T-144 slice 1: the home spelling matcher (design §2 vectors). No disk: every
8.3 name is injected through `shorts`."""

import copy

import pytest

from archeus.core import homes as H

HOME = r'C:\Users\mab\.claude-work'
SHORTS = {'c:/users/mab': 'C:/Users/MAB~1', 'c:/users/mab/.claude-work': 'C:/Users/MAB~1/CLAUDE~1'}
KEY = r'claude_code:c:\users\mab\.claude'
DEFAULT = ('claude_code', KEY, r'C:\Users\mab\.claude')


def _homes(*registered, defaults=(), shorts=SHORTS):
    return H.Homes(list(registered or (HOME,)), list(defaults), shorts=lambda p: shorts.get(p.lower()))


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
    n, h = H.norm_path(v), H.norm_path(HOME)
    assert n == h or n.startswith(h + '/')


def test_the_eight_dot_three_form_needs_the_injected_short_name():
    assert scrub(r'C:\Users\MAB~1\CLAUDE~1\x', shorts={}) == r'read C:\Users\MAB~1\CLAUDE~1\x now'


def test_a_failing_short_name_probe_is_soft():
    def boom(_p):
        raise OSError('no such path')
    h = H.Homes([HOME], shorts=boom)
    assert H.scrub_text(HOME + r'\x', h) == r'its home\x'
    assert H.Homes([r'C:\no\such\home']).patterns


def test_a_sentence_dot_quotes_and_parens_still_match():
    h = _homes()
    assert H.scrub_text('in %s.' % HOME, h) == 'in its home.'
    assert H.scrub_text('"%s" (%s)' % (HOME, HOME), h) == '"its home" (its home)'
    assert H.scrub_text('%s then %s' % (HOME, HOME + r'\y'), h) == r'its home then its home\y'


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
    assert H.scrub_text(KEY, h) == 'claude_code:default'
    t = 'task T1 on %s (approval a1)' % KEY
    assert H.scrub_text(t, h) == 'task T1 on claude_code:default (approval a1)'
    assert H.scrub_text(KEY.upper(), h) == 'claude_code:default'
    assert H.scrub_text(KEY + '-tools', h) == KEY + '-tools'
    assert h.keys == {KEY: 'claude_code:default'}


def test_a_default_home_path_is_scrubbed_too():
    assert H.scrub_text(r'no Claude login in C:\Users\mab\.claude', _homes(defaults=[DEFAULT])) \
        == 'no Claude login in its home'


@pytest.mark.parametrize('text', [
    'plain', '', 'C:\\Users\\mab\\.claude-work\\projects\\a', 'x ' + HOME + ' y ' + KEY,
    'its home\\x', 'claude_code:default', 'file:///c%3A/Users/mab/.claude-work/x',
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
    assert H.norm_path(s) == want


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
                   'who': {'reviewer': ['claude_code:default', 'x']}, 'n': 3,
                   'reason': 'no login in its home', 'note': 'see ' + HOME,
                   'account': 'claude_code:default'}
    assert H.public_value(out, h, text_keys=('reason',), path_keys=('account_ref', 'home_ref')) == out


def test_public_value_scrubs_nested_strings_under_a_text_key():
    h = _homes()
    out = H.public_value({'consequences': ['ran ' + HOME, {'a': HOME}], 'other': HOME}, h,
                         text_keys=('consequences',))
    assert out == {'consequences': ['ran its home', {'a': 'its home'}], 'other': HOME}

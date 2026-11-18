"""Settings hygiene scan of claude_sessions/health.py: branches not covered by the gaps3 and persisted-scrub tests."""

import builtins
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from claude_sessions import health, repos                                   # noqa: E402

S = 'SYNTHhunter2'
CMD = 'Bash(PGPASSWORD=%s psql)' % S
GIT_ARGV = ['ls-files', '-t', '-z', '--cached', '--others', '--exclude-standard', '--']
_REAL_LISTDIR = os.listdir


def _write(root, parts, text):
    p = os.path.join(str(root), '.claude', *[str(x) for x in parts])
    d = os.path.dirname(p)
    if d and not os.path.isdir(d):
        os.makedirs(d)
    with open(p, 'w', encoding='utf-8', newline='\n') as f:
        f.write(text)
    return p


def _write_bytes(root, parts, raw):
    p = os.path.join(str(root), '.claude', *[str(x) for x in parts])
    d = os.path.dirname(p)
    if d and not os.path.isdir(d):
        os.makedirs(d)
    with open(p, 'wb') as f:
        f.write(raw)
    return p


def _project(tmp_path, files):
    root = str(tmp_path)
    d = os.path.join(root, '.claude')
    if not os.path.isdir(d):
        os.makedirs(d)
    for parts, text in files.items():
        _write(root, parts, text)
    return root


def _tree(root):
    out = {}
    for dirpath, _dirs, names in os.walk(str(root)):
        for n in names:
            p = os.path.join(dirpath, n)
            with open(p, 'rb') as f:
                out[os.path.relpath(p, str(root))] = f.read()
    return out


def _allow(text):
    return json.dumps({'permissions': {'allow': [text]}}, indent=2)


@pytest.fixture
def git(monkeypatch):
    """Fake the `_git` seam so no git is spawned. `git['out']` answers the next
    call; `git['calls']` records the argv. The default answer is '' (clean repo)."""
    state = {'out': '', 'calls': []}

    def fake(args, cwd, timeout=15):
        state['calls'].append([list(args), cwd, timeout])
        return state['out']

    monkeypatch.setattr(repos, '_git', fake)
    return state


def test_a_sample_carrying_control_characters_is_cleaned_before_the_card_shows_it(
        tmp_path, git):
    # Only the card boundary strips control characters; the scan's own sample must not.
    rel = os.path.join('.claude', 'rules', 'archeus-mem-esc.md')
    root = _project(tmp_path, {('rules', 'archeus-mem-esc.md'):
                               'token=%s \x1b[31mready\x07\n' % S})
    before = _tree(root)
    found = [f for f in health.settings_hygiene(root) if f['line']]
    assert found == [{'path': rel, 'line': 1, 'rule': 'memory rule',
                      'sample': 'token=[redacted] \x1b[31mready\x07'}], found
    warns = health._check_settings_hygiene(root)
    assert [s for s, _m, _h in warns] == ['warn'], warns
    msg, hint = warns[0][1], warns[0][2]
    assert not any(ord(c) < 0x20 for c in msg), repr(msg)
    assert 'a secret in' in msg and '[redacted]' in msg and 'ready' in msg
    assert 'rotate' in hint
    assert S not in repr(warns)
    assert _tree(root) == before


def test_a_listing_row_that_normalizes_to_an_inspected_path_is_still_a_finding(
        tmp_path, git):
    root = _project(tmp_path, {('settings.json',): _allow(CMD)})
    git['out'] = 'H ./.claude/./settings.json\0'
    before = _tree(root)
    found = health.settings_hygiene(root)
    assert found == [{'path': os.path.join('.claude', 'settings.json'), 'line': 4,
                      'rule': 'permissions.allow',
                      'sample': '"Bash(PGPASSWORD=[redacted] psql)"'},
                     {'path': os.path.join('.claude', 'settings.json'), 'line': 0,
                      'rule': 'tracked by git', 'sample': ''}], found
    assert _tree(root) == before


def test_an_object_shaped_allow_entry_never_ends_the_scan(tmp_path, git):
    # A dict inside the list must not raise on the kind_of lookup and drop the string entry.
    doc = '\n'.join([
        '{',
        '  "permissions": {',
        '    "allow": [',
        '      {',
        '        "tool": "Bash",',
        '        "cmd": "Bash(PGPASSWORD=%s psql)"' % S,
        '      },',
        '      "Bash(curl -u admin:%s https://db.example.com)"' % S,
        '    ]',
        '  }',
        '}',
        '',
    ])
    root = _project(tmp_path, {('settings.json',): doc})
    before = _tree(root)
    found = health.settings_hygiene(root)
    rel = os.path.join('.claude', 'settings.json')
    assert found == [{'path': rel, 'line': 6, 'rule': 'setting',
                      'sample': '"cmd": "Bash(PGPASSWORD=[redacted] psql)"'},
                     {'path': rel, 'line': 8, 'rule': 'permissions.allow',
                      'sample': '"Bash(curl [redacted] https://db.example.com)"'}], found
    assert S not in json.dumps(found)
    assert git['calls'][0][0] == GIT_ARGV + ['.claude/settings.json']
    assert _tree(root) == before


def test_a_settings_file_with_undecodable_bytes_is_still_scanned(tmp_path, git):
    raw = (b'{"note": "\xff\xfe", "permissions": {"allow": ["'
           + ('Bash(PGPASSWORD=%s psql)"]}}\n' % S).encode('utf-8'))
    _write_bytes(tmp_path, ('settings.json',), raw)
    root = str(tmp_path)
    found = health.settings_hygiene(root)
    assert len(found) == 1, found
    f = found[0]
    assert f['path'] == os.path.join('.claude', 'settings.json')
    assert (f['line'], f['rule']) == (1, 'setting'), f
    assert '[redacted]' in f['sample'] and '�' in f['sample'], f
    assert S not in json.dumps(found)
    assert git['calls'][0][0] == GIT_ARGV + ['.claude/settings.json']


def test_a_secret_in_a_non_final_allow_entry_keeps_its_permission_rule_label(
        tmp_path, git):
    # The comma after a non-final entry is only stripped on the line lookup.
    root = _project(tmp_path, {('settings.json',): json.dumps(
        {'permissions': {'allow': [CMD, 'Bash(ls:*)']}}, indent=2)})
    before = _tree(root)
    found = health.settings_hygiene(root)
    assert found == [{'path': os.path.join('.claude', 'settings.json'), 'line': 4,
                      'rule': 'permissions.allow',
                      'sample': '"Bash(PGPASSWORD=[redacted] psql)",'}], found
    assert S not in json.dumps(found)
    assert _tree(root) == before


def test_a_non_ascii_rule_with_a_space_in_its_name_is_reported_untracked_at_line_zero(
        tmp_path, git):
    name = 'archeus-mem-café crème.md'
    rel = os.path.join('.claude', 'rules', name)
    root = _project(tmp_path, {('rules', name): 'token=%s renew it\n' % S})
    git['out'] = '? .claude/rules/%s\0' % name
    before = _tree(root)
    found = health.settings_hygiene(root)
    assert found == [{'path': rel, 'line': 1, 'rule': 'memory rule',
                      'sample': 'token=[redacted] renew it'},
                     {'path': rel, 'line': 0, 'rule': 'not ignored by git',
                      'sample': ''}], found
    assert S not in json.dumps(found)
    assert git['calls'][0][0] == GIT_ARGV + ['.claude/rules/%s' % name]
    assert _tree(root) == before


def test_a_rule_filename_with_an_embedded_newline_matches_only_its_full_nul_row(
        tmp_path, monkeypatch, git):
    # The newline name exists only behind the fake listdir/open seam, so no
    # Windows-invalid filename is ever created on disk.
    evil = 'archeus-mem-a\nb.md'
    rules = os.path.join(str(tmp_path), '.claude', 'rules')
    os.makedirs(rules)
    backing = _write(tmp_path, ('backing.md',), 'token=%s renew\n' % S)
    real_list, real_open = os.listdir, builtins.open

    def listed(path, *a, **k):
        if str(path) == rules:
            return [evil]
        return real_list(path, *a, **k)

    def opened(file, *a, **k):
        if str(file) == os.path.join(rules, evil):
            return real_open(backing, *a, **k)
        return real_open(file, *a, **k)

    monkeypatch.setattr(os, 'listdir', listed)
    monkeypatch.setattr(builtins, 'open', opened)
    rel = os.path.join('.claude', 'rules', evil)
    git['out'] = '? .claude/rules/%s\0' % evil
    found = health.settings_hygiene(str(tmp_path))
    assert found == [{'path': rel, 'line': 1, 'rule': 'memory rule',
                      'sample': 'token=[redacted] renew'},
                     {'path': rel, 'line': 0, 'rule': 'not ignored by git',
                      'sample': ''}], found
    assert S not in json.dumps(found)
    assert git['calls'][0][0] == GIT_ARGV + [rel.replace(os.sep, '/')]
    monkeypatch.undo()
    assert _REAL_LISTDIR(rules) == []
    assert sorted(_REAL_LISTDIR(os.path.join(str(tmp_path), '.claude'))) == \
        ['backing.md', 'rules']


def test_a_missing_project_path_warns_about_nothing_and_never_spawns_git(
        tmp_path, monkeypatch, git):
    monkeypatch.chdir(str(tmp_path))
    assert health.settings_hygiene('') == []
    assert health._check_settings_hygiene('') == []
    assert health._check_settings_hygiene(None) == []
    assert git['calls'] == []


def test_an_unlistable_rules_directory_still_lets_both_settings_files_be_read(
        tmp_path, monkeypatch, git):
    root = _project(tmp_path, {('settings.json',): _allow(CMD),
                               ('settings.local.json',): _allow(CMD),
                               ('rules', 'archeus-mem-x.md'):
                               'token=%s renew\n' % S})
    real_list = os.listdir

    def listed(path, *a, **k):
        if str(path).endswith(os.path.join('.claude', 'rules')):
            raise PermissionError(13, 'the rules directory went away mid-scan')
        return real_list(path, *a, **k)

    monkeypatch.setattr(os, 'listdir', listed)
    found = health.settings_hygiene(root)
    monkeypatch.undo()
    assert found == [{'path': os.path.join('.claude', 'settings.json'), 'line': 4,
                      'rule': 'permissions.allow',
                      'sample': '"Bash(PGPASSWORD=[redacted] psql)"'},
                     {'path': os.path.join('.claude', 'settings.local.json'),
                      'line': 4, 'rule': 'permissions.allow',
                      'sample': '"Bash(PGPASSWORD=[redacted] psql)"'}], found
    assert S not in json.dumps(found)
    assert git['calls'][0][0] == GIT_ARGV + ['.claude/settings.json',
                                             '.claude/settings.local.json']
    assert set(_tree(root)) == {os.path.join('.claude', 'settings.json'),
                                os.path.join('.claude', 'settings.local.json'),
                                os.path.join('.claude', 'rules', 'archeus-mem-x.md')}


def test_a_crash_inside_settings_hygiene_yields_no_warnings(tmp_path, monkeypatch,
                                                            git):
    # Any exception becomes []: the contract is pinned, not endorsed.
    root = _project(tmp_path, {('settings.local.json',): _allow(CMD)})

    def boom(_project_path):
        raise RuntimeError('synthetic settings_hygiene crash')

    monkeypatch.setattr(health, 'settings_hygiene', boom)
    assert health._check_settings_hygiene(root) == []
    assert git['calls'] == []

"""T-1332 — output style front matter parsing and the merged listing in claude_sessions/outputstyles.py, lines 115-157.

Selected branches (highest risk first):
  1. :155-156  PREMISE: a name present in user and project scope marks both rows active (xfail)
  2. :119-120  an unreadable file (a directory named *.md) returns None and is left out
  3. :142-146  a missing scope directory is skipped; user rows come before project rows
  4. :147-149  non-.md files are ignored
  5. :152-154  listing rows carry no body and carry their scope
  6. :121-124  no front matter: the whole text is the body and the name is the file stem
  7. :125-128  quotes are stripped; a value containing a colon keeps everything after the first colon
  8. :129      a front matter name overrides the file stem
  9. :137-141  built-in rows come first with lines 0 and scope 'built-in'
 10. :133-134  lines counts the body's lines (control)

Seams: tmp_path holds the config dir and the project tree; outputstyles.BUILTIN is
monkeypatched to a two-item tuple so the built-in rows are stable. No real config dir,
settings file or environment value is read.
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from claude_sessions import outputstyles


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(text)


@pytest.fixture
def tree(monkeypatch, tmp_path):
    monkeypatch.setattr(outputstyles, 'BUILTIN', [('alpha', 'Alpha desc.'), ('beta', 'Beta desc.')])
    cfg = str(tmp_path / 'cfg')
    proj = str(tmp_path / 'proj')
    return {
        'cfg': cfg,
        'proj': proj,
        'user': os.path.join(cfg, 'output-styles'),
        'pdir': os.path.join(proj, '.claude', 'output-styles'),
    }


@pytest.mark.xfail(strict=True, reason=(
    "claude_sessions/outputstyles.py:155-156 marks every row whose name equals the active "
    "style, so a name in both scopes shows two active rows; only the project file is in "
    "force (active_scope, :262-272)"))
def test_same_name_in_both_scopes_marks_only_the_project_row_active(tree):
    _write(os.path.join(tree['user'], 'Shared.md'), '---\nname: Shared\n---\nuser body\n')
    _write(os.path.join(tree['pdir'], 'Shared.md'), '---\nname: Shared\n---\nproject body\n')
    _write(os.path.join(tree['proj'], '.claude', 'settings.json'),
           json.dumps({'outputStyle': 'Shared'}))
    rows = [s for s in outputstyles.listing(tree['proj'], tree['cfg']) if s['name'] == 'Shared']
    assert {s['scope']: s['active'] for s in rows} == {'user': False, 'project': True}


def test_unreadable_md_returns_none_and_is_left_out_of_listing(tree):
    _write(os.path.join(tree['user'], 'good.md'), '---\nname: good\n---\nbody\n')
    os.makedirs(os.path.join(tree['user'], 'broken.md'))
    assert outputstyles._parse(os.path.join(tree['user'], 'broken.md')) is None
    names = [s['name'] for s in outputstyles.listing(None, tree['cfg']) if not s['builtin']]
    assert names == ['good']


def test_missing_project_dir_is_skipped_and_user_rows_precede_project_rows(tree):
    _write(os.path.join(tree['user'], 'u.md'), '---\nname: u\n---\nu\n')
    rows = outputstyles.listing(tree['proj'], tree['cfg'])
    assert [s['name'] for s in rows if not s['builtin']] == ['u']

    _write(os.path.join(tree['pdir'], 'p.md'), '---\nname: p\n---\np\n')
    rows = outputstyles.listing(tree['proj'], tree['cfg'])
    assert [(s['name'], s['scope']) for s in rows if not s['builtin']] == [
        ('u', 'user'), ('p', 'project')]


def test_non_md_files_are_ignored(tree):
    _write(os.path.join(tree['user'], 'notes.txt'), 'not a style\n')
    _write(os.path.join(tree['user'], 'style.md.bak'), 'not a style\n')
    _write(os.path.join(tree['user'], 'real.md'), '---\nname: real\n---\nbody\n')
    names = [s['name'] for s in outputstyles.listing(None, tree['cfg']) if not s['builtin']]
    assert names == ['real']


def test_listing_rows_carry_scope_and_no_body(tree):
    _write(os.path.join(tree['user'], 'u.md'), '---\nname: u\n---\nthe body text\n')
    _write(os.path.join(tree['pdir'], 'p.md'), '---\nname: p\n---\nthe other body\n')
    rows = {s['name']: s for s in outputstyles.listing(tree['proj'], tree['cfg'])
            if not s['builtin']}
    assert rows['u']['scope'] == 'user' and rows['p']['scope'] == 'project'
    assert rows['u']['file'] == os.path.join(tree['user'], 'u.md')
    for row in rows.values():
        assert 'body' not in row
        assert row['builtin'] is False


def test_no_front_matter_uses_whole_text_as_body_and_stem_as_name(tree):
    path = os.path.join(tree['user'], 'plain-style.md')
    _write(path, 'Just text\nsecond line\n')
    parsed = outputstyles._parse(path)
    assert parsed['name'] == 'plain-style'
    assert parsed['description'] == ''
    assert parsed['body'] == 'Just text\nsecond line'


def test_front_matter_strips_quotes_and_keeps_text_after_first_colon(tree):
    path = os.path.join(tree['user'], 'quoted.md')
    _write(path, '---\nname: "Quoted Name"\ndescription: Explains: the reasoning\n---\nbody\n')
    parsed = outputstyles._parse(path)
    assert parsed['name'] == 'Quoted Name'
    assert parsed['description'] == 'Explains: the reasoning'


def test_front_matter_name_overrides_file_stem(tree):
    _write(os.path.join(tree['user'], 'file-stem.md'), '---\nname: Named Style\n---\nbody\n')
    names = [s['name'] for s in outputstyles.listing(None, tree['cfg']) if not s['builtin']]
    assert names == ['Named Style']


def test_builtin_rows_come_first_with_zero_lines_and_built_in_scope(tree):
    _write(os.path.join(tree['user'], 'u.md'), '---\nname: u\n---\nu\n')
    rows = outputstyles.listing(None, tree['cfg'])
    assert [s['name'] for s in rows[:2]] == ['alpha', 'beta']
    for row in rows[:2]:
        assert row['builtin'] is True
        assert row['scope'] == 'built-in'
        assert row['lines'] == 0
        assert row['file'] == ''
    assert rows[2]['name'] == 'u'


def test_lines_counts_body_lines_not_front_matter(tree):
    path = os.path.join(tree['user'], 'counted.md')
    _write(path, '---\nname: counted\ndescription: x\n---\none\ntwo')
    row = [s for s in outputstyles.listing(None, tree['cfg']) if s['name'] == 'counted'][0]
    assert row['lines'] == 2

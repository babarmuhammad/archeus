"""T-1331 — output style select, save and delete in claude_sessions/outputstyles.py, lines 184-288.

Selected branches (highest risk first):
  1. :198-199      select: failed write returns (False, 'Could not write <path>'), no success
  2. :204-211, :221 hostile name ('../secret') is slugged inside the scope dir (save, read, delete)
  3. :277-278      built-in names are refused before any file lookup
  4. :262-265      a name with no slug characters is refused, nothing written
  5. :270-271      save: failed write returns False with the path, no success
  6. :280-287      delete: user scope before project; an OSError returns its text
  7. :194-197      'default' pops outputStyle and keeps every other key (control)
  8. :241-245      install_starter refuses an unknown starter, writes nothing
  9. :193, :198    PREMISE: select on malformed settings.json overwrites it (xfail)
 10. :268         PREMISE: a description with a newline and 'name:' line renames the style (xfail)

Seams: tmp_path for the config dir and project tree; config.write_json_atomic and
config.write_atomic are monkeypatched to return False for the failure probes; os.remove
is replaced for the OSError probe. No real config dir is touched.
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from claude_sessions import config, outputstyles


def _proj(tmp_path):
    proj = tmp_path / 'proj'
    (proj / '.claude' / 'output-styles').mkdir(parents=True)
    return str(proj)


def _cfg(tmp_path):
    cfg = tmp_path / 'cfg'
    cfg.mkdir()
    return str(cfg)


def _files_under(root):
    out = set()
    for dirpath, _dirs, names in os.walk(root):
        for n in names:
            out.add(os.path.relpath(os.path.join(dirpath, n), root))
    return out


def test_select_failed_write_reports_path_and_no_success(monkeypatch, tmp_path):
    proj = _proj(tmp_path)
    monkeypatch.setattr(config, 'write_json_atomic', lambda *a, **k: False)

    ok, msg = outputstyles.select('Terse', proj, _cfg(tmp_path))

    expected = os.path.join(proj, '.claude', 'settings.json')
    assert ok is False
    assert msg == f'Could not write {expected}'
    assert not os.path.exists(expected)


def test_hostile_style_name_is_slugged_inside_its_scope_dir(tmp_path):
    proj = _proj(tmp_path)
    cfg = _cfg(tmp_path)
    styles = os.path.join(proj, '.claude', 'output-styles')
    (tmp_path / 'cfg' / 'secret.md').write_text(
        '---\nname: secret\n---\n\ntop secret\n', encoding='utf-8')

    ok, _ = outputstyles.save('../../x', 'd', 'body', proj, cfg)
    assert ok
    assert _files_under(str(tmp_path)) == {
        os.path.join('proj', '.claude', 'output-styles', 'x.md'),
        os.path.join('cfg', 'secret.md'),
    }

    assert outputstyles.read('../secret', proj, cfg) == ''
    assert outputstyles.delete('../secret', proj, cfg) == (False, '../secret not found')
    assert os.path.isfile(os.path.join(cfg, 'secret.md'))
    assert os.listdir(styles) == ['x.md']


@pytest.mark.parametrize('name', ['Explanatory', 'Learning', 'default'])
def test_builtin_name_is_refused_and_no_file_is_deleted(tmp_path, name):
    cfg = _cfg(tmp_path)
    user_dir = os.path.join(cfg, 'output-styles')
    os.makedirs(user_dir)
    keep = os.path.join(user_dir, f'{name}.md')
    with open(keep, 'w', encoding='utf-8') as fh:
        fh.write('---\nname: x\n---\n\nbody\n')

    ok, msg = outputstyles.delete(name, None, cfg)

    assert ok is False and 'ships with Claude Code' in msg
    assert os.path.isfile(keep)


@pytest.mark.parametrize('name', ['!!!', '---', '   '])
def test_name_without_slug_characters_is_refused_and_writes_nothing(tmp_path, name):
    cfg = _cfg(tmp_path)

    ok, msg = outputstyles.save(name, 'd', 'body', None, cfg)

    assert (ok, msg) == (False, 'A name is required')
    assert _files_under(str(tmp_path)) == set()


def test_save_failed_write_returns_path_and_no_success(monkeypatch, tmp_path):
    proj = _proj(tmp_path)
    monkeypatch.setattr(config, 'write_atomic', lambda *a, **k: False)

    ok, msg = outputstyles.save('Pair', 'd', 'body', proj, _cfg(tmp_path))

    expected = os.path.join(proj, '.claude', 'output-styles', 'Pair.md')
    assert (ok, msg) == (False, f'Could not write {expected}')
    assert not os.path.exists(expected)


def test_delete_removes_user_match_first_and_keeps_project_copy(tmp_path):
    proj = _proj(tmp_path)
    cfg = _cfg(tmp_path)
    user_file = os.path.join(cfg, 'output-styles', 'Mine.md')
    proj_file = os.path.join(proj, '.claude', 'output-styles', 'Mine.md')
    os.makedirs(os.path.dirname(user_file))
    for path in (user_file, proj_file):
        with open(path, 'w', encoding='utf-8') as fh:
            fh.write('---\nname: Mine\n---\n\nbody\n')

    assert outputstyles.delete('Mine', proj, cfg) == (True, 'Deleted Mine')
    assert not os.path.exists(user_file)
    assert os.path.isfile(proj_file)


def test_delete_oserror_returns_its_text_and_keeps_file(monkeypatch, tmp_path):
    proj = _proj(tmp_path)
    proj_file = os.path.join(proj, '.claude', 'output-styles', 'Mine.md')
    with open(proj_file, 'w', encoding='utf-8') as fh:
        fh.write('---\nname: Mine\n---\n\nbody\n')

    def refuse(path):
        raise OSError('boom')

    monkeypatch.setattr(outputstyles.os, 'remove', refuse)

    assert outputstyles.delete('Mine', proj, _cfg(tmp_path)) == (False, 'boom')
    assert os.path.isfile(proj_file)


def test_select_default_drops_only_outputstyle_and_keeps_other_keys(tmp_path):
    proj = _proj(tmp_path)
    sp = os.path.join(proj, '.claude', 'settings.json')
    with open(sp, 'w', encoding='utf-8') as fh:
        json.dump({'outputStyle': 'Terse',
                   'model': 'x',
                   'permissions': {'allow': ['Bash(git:*)']}}, fh)

    ok, msg = outputstyles.select('default', proj, _cfg(tmp_path))

    assert (ok, msg) == (True, 'Output style for this project: default')
    with open(sp, encoding='utf-8') as fh:
        assert json.load(fh) == {'model': 'x', 'permissions': {'allow': ['Bash(git:*)']}}


def test_install_starter_refuses_unknown_name_and_writes_nothing(tmp_path):
    proj = _proj(tmp_path)
    cfg = _cfg(tmp_path)
    before = _files_under(str(tmp_path))

    assert outputstyles.install_starter('Nope', proj, cfg) == (False, 'Nope is not a starter')
    assert _files_under(str(tmp_path)) == before
    assert not os.path.exists(os.path.join(cfg, 'output-styles'))


@pytest.mark.xfail(strict=True, reason=(
    "claude_sessions/outputstyles.py:170-172 returns {} for a malformed settings.json "
    "and :198 writes over it, so the user's other keys are lost"))
def test_select_refuses_malformed_settings_and_keeps_bytes(tmp_path):
    proj = _proj(tmp_path)
    sp = os.path.join(proj, '.claude', 'settings.json')
    raw = '{"model": "x", "permissions": {"allow": ["Bash(git:*)"]'
    with open(sp, 'w', encoding='utf-8') as fh:
        fh.write(raw)

    ok, _ = outputstyles.select('Learning', proj, _cfg(tmp_path))

    with open(sp, encoding='utf-8') as fh:
        after = fh.read()
    assert (ok, after) == (False, raw)


@pytest.mark.xfail(strict=True, reason=(
    "claude_sessions/outputstyles.py:268 writes the description unescaped, so a "
    "newline and 'name:' line overrides the name when _parse (:128-129) reads it back"))
def test_description_newline_cannot_rename_the_style(tmp_path):
    proj = _proj(tmp_path)
    cfg = _cfg(tmp_path)

    ok, _ = outputstyles.save('Pair', 'Line one\nname: Hijack', 'Body', proj, cfg)
    assert ok

    rows = [s for s in outputstyles.listing(proj, cfg) if s.get('scope') == 'project']
    assert [s['name'] for s in rows] == ['Pair']

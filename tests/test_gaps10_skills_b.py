"""T-1373: claude_sessions/skills.py lines 391-418 (install_skill, delete_skill).

Selected branches, denial and fail-closed first:
  398       install_skill refuses a source without SKILL.md: returns '' and creates nothing
  398       empty src_dir or empty dest_root returns '' with no directory created
  401-407   a source that is already the destination loses its own folder (strict xfail)
  403-405   an existing dest directory is replaced wholesale; a stale file is gone
  406       nested files (references/, scripts/) are copied; the source tree is unchanged
  401-408   dest exists as a regular FILE: copytree raises, except returns '', file untouched
  402-408   dest_root is a regular file: makedirs raises, returns '' and does not raise
  407       success returns dest_root joined with the source basename
  411-417   delete_skill on a missing dir returns False; on an existing dir returns True and removes it
  413-417   delete_skill on a regular file path returns False and the file survives

The trailing-separator premise is covered by tests/test_skills_trailing_sep.py and is not repeated here.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from claude_sessions import skills


def _skill(root, name, body='body\n'):
    d = os.path.join(str(root), name)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, 'SKILL.md'), 'w', encoding='utf-8', newline='\n') as fh:
        fh.write('---\nname: ' + name + '\n---\n\n' + body)
    return d


def _tree(root):
    out = {}
    for dp, _dn, fn in os.walk(str(root)):
        for f in fn:
            p = os.path.join(dp, f)
            with open(p, 'rb') as fh:
                out[os.path.relpath(p, str(root))] = fh.read()
    return out


@pytest.mark.xfail(strict=True, reason=(
    "skills.py:404-406: when src_dir is already dest (dest_root/basename), install_skill "
    "rmtree's dest, which is the source, then copytree fails and the source is lost; "
    "install_personal(personal skill) reaches this with the personal root as parent"))
def test_installing_a_skill_onto_its_own_folder_keeps_the_source(tmp_path):
    root = tmp_path / 'skills'
    src = _skill(root, 'mine', 'precious\n')

    skills.install_skill(src, str(root))

    assert os.path.isfile(os.path.join(src, 'SKILL.md'))


def test_source_without_skill_md_installs_nothing(tmp_path):
    src = tmp_path / 'bare'
    os.makedirs(str(src))
    root = tmp_path / 'skills'

    assert skills.install_skill(str(src), str(root)) == ''

    assert not os.path.exists(str(root))


def test_empty_src_or_dest_root_returns_empty_and_creates_nothing(tmp_path):
    src = _skill(tmp_path / 'lib', 'ok')
    before = set(os.listdir(str(tmp_path)))

    assert skills.install_skill('', str(tmp_path / 'skills')) == ''
    assert skills.install_skill(src, '') == ''

    assert set(os.listdir(str(tmp_path))) == before
    assert not os.path.exists(str(tmp_path / 'skills'))


def test_existing_destination_is_replaced_wholesale(tmp_path):
    src = _skill(tmp_path / 'lib', 's', 'new body\n')
    root = tmp_path / 'skills'
    old = _skill(root, 's', 'old body\n')
    with open(os.path.join(old, 'stale.txt'), 'w', encoding='utf-8') as fh:
        fh.write('only in the old copy')

    dest = skills.install_skill(src, str(root))

    assert dest == os.path.join(str(root), 's')
    assert not os.path.exists(os.path.join(dest, 'stale.txt'))
    with open(os.path.join(dest, 'SKILL.md'), encoding='utf-8') as fh:
        assert fh.read().endswith('new body\n')


def test_nested_files_are_copied_and_source_is_unchanged(tmp_path):
    src = _skill(tmp_path / 'lib', 'tree')
    os.makedirs(os.path.join(src, 'references'))
    os.makedirs(os.path.join(src, 'scripts'))
    with open(os.path.join(src, 'references', 'guide.md'), 'wb') as fh:
        fh.write(b'guide\r\nbytes')
    with open(os.path.join(src, 'scripts', 'run.sh'), 'wb') as fh:
        fh.write(b'echo hi\n')
    before = _tree(src)

    dest = skills.install_skill(src, str(tmp_path / 'skills'))

    assert _tree(dest) == before
    assert _tree(src) == before


def test_destination_that_is_a_regular_file_is_refused_and_untouched(tmp_path):
    src = _skill(tmp_path / 'lib', 's')
    root = tmp_path / 'skills'
    os.makedirs(str(root))
    blocker = root / 's'
    blocker.write_text('keep me', encoding='utf-8')

    assert skills.install_skill(src, str(root)) == ''

    assert blocker.read_text(encoding='utf-8') == 'keep me'


def test_destination_root_that_is_a_regular_file_returns_empty_without_raising(tmp_path):
    src = _skill(tmp_path / 'lib', 's')
    root = tmp_path / 'skills'
    root.write_text('not a dir', encoding='utf-8')

    assert skills.install_skill(src, str(root)) == ''

    assert root.read_text(encoding='utf-8') == 'not a dir'


def test_success_returns_destination_root_joined_with_source_basename(tmp_path):
    src = _skill(tmp_path / 'lib', 'named')
    root = str(tmp_path / 'skills')

    dest = skills.install_skill(src, root)

    assert dest == os.path.join(root, 'named')
    assert os.path.isfile(os.path.join(dest, 'SKILL.md'))


def test_delete_skill_missing_dir_is_false_and_existing_dir_is_removed(tmp_path):
    assert skills.delete_skill(str(tmp_path / 'absent')) is False

    d = _skill(tmp_path, 'present')

    assert skills.delete_skill(d) is True
    assert not os.path.exists(d)


def test_delete_skill_on_a_regular_file_is_false_and_the_file_survives(tmp_path):
    p = tmp_path / 'plain'
    p.write_text('keep', encoding='utf-8')

    assert skills.delete_skill(str(p)) is False

    assert p.read_text(encoding='utf-8') == 'keep'

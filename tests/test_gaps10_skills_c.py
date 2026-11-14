"""T-1374: claude_sessions/skills.py lines 519-580 (install_personal, delete_personal,
personal_accounts, install_project).

Selected branches, denial and fail-closed first:
  535-538  install_personal: a root whose install_skill returns '' is not reported
  575-578  install_project: a root whose install_skill returns '' is omitted; the others install
  550-555  delete_personal: a same-named regular FILE in a root is skipped and not counted
  558-564  personal_accounts: a folder without SKILL.md is not reported
  541-547  delete_personal(all_accounts=False) touches only personal_dir(), not the other roots
  519-538  install_personal copies SKILL.md byte for byte into every root
  558-564  personal_accounts returns [] when no root has the skill, and keeps skill_roots order
  532-538  install_personal with no SKILL.md in the source returns [] and creates no root
  534-535  install_personal(all_accounts=False) installs only into personal_dir()

Roots are tmp_path folders. _harnesses.skill_roots, _harnesses.project_skill_roots and
skills.personal_dir are replaced, so no real CLI home is read or written.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from claude_sessions import skills


def _skill(root, name, data=b'---\nname: s\n---\n\nbody\n'):
    d = os.path.join(str(root), name)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, 'SKILL.md'), 'wb') as fh:
        fh.write(data)
    return d


def _fake_roots(monkeypatch, pairs):
    monkeypatch.setattr(skills._harnesses, 'skill_roots', lambda: list(pairs))


def _fake_personal(monkeypatch, path):
    monkeypatch.setattr(skills, 'personal_dir', lambda cfgdir=None: str(path))


def test_project_root_that_cannot_take_the_skill_is_omitted_and_the_rest_install(tmp_path, monkeypatch):
    lib = tmp_path / 'lib'
    src = _skill(lib, 's')
    a = tmp_path / 'a'
    b = tmp_path / 'b'
    b.write_text('a file, not a skills dir', encoding='utf-8')
    monkeypatch.setattr(skills._harnesses, 'project_skill_roots', lambda p: [str(a), str(b)])

    got = skills.install_project(src, str(tmp_path / 'proj'))

    assert got == [os.path.join(str(a), 's')]
    assert b.read_text(encoding='utf-8') == 'a file, not a skills dir'


def test_install_personal_without_all_accounts_writes_only_personal_dir(tmp_path, monkeypatch):
    src = _skill(tmp_path / 'lib', 's')
    personal = tmp_path / 'personal'
    other = tmp_path / 'other'
    _fake_personal(monkeypatch, personal)
    _fake_roots(monkeypatch, [('other', str(other))])

    got = skills.install_personal(src, all_accounts=False)

    assert got == [('', os.path.join(str(personal), 's'))]
    assert not os.path.exists(str(other))


def test_install_personal_all_accounts_reports_only_roots_that_took_the_copy(tmp_path, monkeypatch):
    src = _skill(tmp_path / 'lib', 's')
    a = tmp_path / 'a'
    b_file = tmp_path / 'b'
    b_file.write_text('blocked', encoding='utf-8')
    _fake_roots(monkeypatch, [('a', str(a)), ('b', str(b_file))])

    got = skills.install_personal(src, all_accounts=True)

    assert got == [('a', os.path.join(str(a), 's'))]
    assert b_file.read_text(encoding='utf-8') == 'blocked'


def test_delete_personal_skips_a_same_named_regular_file(tmp_path, monkeypatch):
    ra = tmp_path / 'a'
    rb = tmp_path / 'b'
    _skill(ra, 'gone')
    rb.mkdir()
    (rb / 'gone').write_text('a file, not a skill', encoding='utf-8')
    _fake_roots(monkeypatch, [('a', str(ra)), ('b', str(rb))])

    got = skills.delete_personal(str(tmp_path / 'lib' / 'gone'))

    assert got == [('a', os.path.join(str(ra), 'gone'))]
    assert not os.path.exists(os.path.join(str(ra), 'gone'))
    assert (rb / 'gone').read_text(encoding='utf-8') == 'a file, not a skill'


def test_personal_accounts_reports_only_roots_with_a_skill_md_file(tmp_path, monkeypatch):
    ra = tmp_path / 'a'
    rb = tmp_path / 'b'
    _skill(ra, 'shared')
    os.makedirs(str(rb / 'shared'))
    _fake_roots(monkeypatch, [('a', str(ra)), ('b', str(rb))])

    assert skills.personal_accounts(str(tmp_path / 'lib' / 'shared')) == ['a']


def test_delete_personal_without_all_accounts_leaves_other_roots_alone(tmp_path, monkeypatch):
    personal = tmp_path / 'personal'
    other = tmp_path / 'other'
    _skill(personal, 'both')
    _skill(other, 'both')
    _fake_personal(monkeypatch, personal)
    _fake_roots(monkeypatch, [('other', str(other))])

    got = skills.delete_personal(str(tmp_path / 'lib' / 'both'), all_accounts=False)

    assert got == [('', os.path.join(str(personal), 'both'))]
    assert not os.path.exists(os.path.join(str(personal), 'both'))
    assert os.path.isfile(os.path.join(str(other), 'both', 'SKILL.md'))


def test_install_personal_copies_skill_md_byte_for_byte_into_every_root(tmp_path, monkeypatch):
    data = b'---\r\nname: x\r\n---\r\n\r\nh\xc3\xa9llo\r\n'
    src = _skill(tmp_path / 'lib', 's', data)
    roots = [tmp_path / 'a', tmp_path / 'b']
    _fake_roots(monkeypatch, [('a', str(roots[0])), ('b', str(roots[1]))])

    got = skills.install_personal(src, all_accounts=True)

    assert [n for n, _d in got] == ['a', 'b']
    for _n, dest in got:
        with open(os.path.join(dest, 'SKILL.md'), 'rb') as fh:
            assert fh.read() == data


def test_personal_accounts_is_empty_or_keeps_skill_roots_order(tmp_path, monkeypatch):
    lib = tmp_path / 'lib' / 'gone'
    rz, ra, rm = tmp_path / 'z', tmp_path / 'a', tmp_path / 'm'
    _fake_roots(monkeypatch, [('z', str(rz)), ('a', str(ra)), ('m', str(rm))])
    assert skills.personal_accounts(str(lib)) == []

    for r in (rz, ra, rm):
        _skill(r, 'gone')

    assert skills.personal_accounts(str(lib)) == ['z', 'a', 'm']


def test_install_personal_with_no_skill_md_returns_empty_and_creates_no_root(tmp_path, monkeypatch):
    src = tmp_path / 'bare'
    os.makedirs(str(src))
    a = tmp_path / 'a'
    b = tmp_path / 'b'
    _fake_roots(monkeypatch, [('a', str(a)), ('b', str(b))])

    assert skills.install_personal(str(src), all_accounts=True) == []

    assert not os.path.exists(str(a))
    assert not os.path.exists(str(b))

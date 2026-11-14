import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from claude_sessions import skills


def _skill(root, name):
    d = os.path.join(root, name)
    os.makedirs(d)
    with open(os.path.join(d, 'SKILL.md'), 'w', encoding='utf-8') as fh:
        fh.write('---\nname: ' + name + '\n---\n\nbody\n')
    return d


def test_install_with_a_trailing_separator_keeps_sibling_skills(tmp_path):
    src = _skill(str(tmp_path / 'lib'), 'new')
    root = str(tmp_path / 'skills')
    keep = _skill(root, 'keep')

    dest = skills.install_skill(src + os.sep, root)

    assert dest == os.path.join(root, 'new')
    assert os.path.isfile(os.path.join(keep, 'SKILL.md'))


def test_delete_personal_with_a_trailing_separator_removes_only_that_skill(tmp_path, monkeypatch):
    roots = [str(tmp_path / 'a'), str(tmp_path / 'b')]
    for r in roots:
        _skill(r, 'gone')
        _skill(r, 'keep')
    monkeypatch.setattr(skills._harnesses, 'skill_roots', lambda: [('a', roots[0]), ('b', roots[1])])

    got = skills.delete_personal(os.path.join(roots[0], 'gone') + os.sep)

    assert [n for n, _d in got] == ['a', 'b']
    for r in roots:
        assert not os.path.exists(os.path.join(r, 'gone'))
        assert os.path.isfile(os.path.join(r, 'keep', 'SKILL.md'))
    assert skills.personal_accounts(os.path.join(roots[0], 'keep') + os.sep) == ['a', 'b']

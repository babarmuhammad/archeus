"""T-1405 — claude_sessions/gui_api.py skill read, install and create handlers, lines 2085-2144.

Candidate list, refusal first:
 1. 2112-2113  scope 'project' without a path is a BadRequest; install_project never runs
 2. 2096-2099  _skill_dest: only scope 'project' uses the path; anything else is personal
 3. 2108-2111  personal install with no result is ok False, no dir, no accounts
 4. 2114-2115  project install returns the first dir and the full list; empty is ok False
 5. 2085-2088  api_skill_read: missing 'dir' is a BadRequest; meta and body pass through
 6. 2135       a name that slugs to nothing lands in the 'skill' subdirectory
 7. 2137-2138  'allowed-tools' goes into meta only when body['tools'] is truthy
 8. 2139-2141  the default body is used only when body is absent or empty
 9. 2135-2136  fixed: a non-string name raises AttributeError in _slug, not BadRequest
10. 2136/2139  fixed: a newline in the description injects a frontmatter key

Seams: skills.install_personal, skills.install_project, skills.parse_skill,
skills.personal_dir, skills.project_skills_dir and skills.write_skill are replaced
with fakes; the create probes that need a real file use tmp_path as the skills root.
No server, no real config dir, no network.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from claude_sessions import gui_api, skills


@pytest.fixture()
def skills_root(monkeypatch, tmp_path):
    root = str(tmp_path / 'skills-root')
    monkeypatch.setattr(skills, 'personal_dir', lambda cfgdir=None: root)
    monkeypatch.setattr(skills, 'project_skills_dir',
                        lambda project_path, cfgdir=None: os.path.join(project_path, 'skills'))
    return root


@pytest.fixture()
def write_spy(monkeypatch):
    calls = []

    def fake(skill_dir, meta, body):
        calls.append((skill_dir, dict(meta), body))
        return True

    monkeypatch.setattr(skills, 'write_skill', fake)
    return calls


# 2112-2113 — project scope with no path is refused before anything is installed
def test_skill_install_project_scope_without_path_refused(monkeypatch):
    installed = []
    monkeypatch.setattr(skills, 'install_project', lambda *a: installed.append(a) or [])
    with pytest.raises(gui_api.BadRequest, match='scope=project needs a path'):
        gui_api.call(gui_api.api_skill_install, {}, {'scope': 'project', 'dir': '/s'})
    assert installed == []


# 2096-2099 — only scope 'project' resolves to the project; a path on any other scope is ignored
def test_skill_dest_only_project_scope_uses_path(monkeypatch):
    seen = []
    monkeypatch.setattr(skills, 'project_skills_dir', lambda p, cfgdir=None: seen.append(('proj', p)) or 'P')
    monkeypatch.setattr(skills, 'personal_dir', lambda cfgdir=None: seen.append(('personal', cfgdir)) or 'U')
    assert gui_api._skill_dest({'scope': 'project', 'path': '/work'}) == 'P'
    assert gui_api._skill_dest({'scope': 'personal', 'path': '/work'}) == 'U'
    assert gui_api._skill_dest({'path': '/work', 'cfgdir': '/acct'}) == 'U'
    assert seen == [('proj', '/work'), ('personal', None), ('personal', '/acct')]


# 2108-2111 — personal install that wrote nothing is not ok, with no dir and no accounts
def test_skill_install_personal_empty_result_is_not_ok(monkeypatch):
    monkeypatch.setattr(skills, 'install_personal', lambda src, *a: [])
    out = gui_api.call(gui_api.api_skill_install, {}, {'dir': '/src'})
    assert out == {'ok': False, 'dir': '', 'accounts': []}


# 2114-2115 — project install reports the first dir and the full list
def test_skill_install_project_returns_first_dir_and_list(monkeypatch):
    monkeypatch.setattr(skills, 'install_project', lambda src, path: ['/p/a', '/p/b'])
    out = gui_api.call(gui_api.api_skill_install, {}, {'scope': 'project', 'dir': '/src',
                                                       'path': '/p'})
    assert out == {'ok': True, 'dir': '/p/a', 'dirs': ['/p/a', '/p/b']}

    monkeypatch.setattr(skills, 'install_project', lambda src, path: [])
    out = gui_api.call(gui_api.api_skill_install, {}, {'scope': 'project', 'dir': '/src',
                                                       'path': '/p'})
    assert out == {'ok': False, 'dir': '', 'dirs': []}


# 2085-2088 — read needs 'dir'; meta and body come back unchanged
def test_skill_read_missing_dir_is_bad_request_and_passes_through(monkeypatch):
    with pytest.raises(gui_api.BadRequest, match='missing parameter: dir'):
        gui_api.call(gui_api.api_skill_read, {}, None)

    monkeypatch.setattr(skills, 'parse_skill', lambda d: ({'name': 'n'}, 'text'))
    out = gui_api.call(gui_api.api_skill_read, {'dir': '/s'}, None)
    assert out == {'meta': {'name': 'n'}, 'body': 'text'}


# 2135 — an empty slug becomes the 'skill' subdirectory, never the destination root
def test_skill_create_empty_slug_lands_in_skill_subdir(skills_root):
    out = gui_api.call(gui_api.api_skill_create, {}, {'name': '!!!', 'description': 'd'})
    expected = os.path.join(skills_root, 'skill')
    assert out == {'ok': True, 'dir': expected}
    assert os.path.isfile(os.path.join(expected, 'SKILL.md'))
    assert not os.path.exists(os.path.join(skills_root, 'SKILL.md'))


# 2137-2138 — 'allowed-tools' is set only for a truthy tools value
def test_skill_create_tools_only_when_truthy(skills_root, write_spy):
    gui_api.call(gui_api.api_skill_create, {}, {'name': 'a', 'tools': ''})
    gui_api.call(gui_api.api_skill_create, {}, {'name': 'b', 'tools': 'Read, Bash'})
    assert 'allowed-tools' not in write_spy[0][1]
    assert write_spy[1][1]['allowed-tools'] == 'Read, Bash'


# 2139-2141 — a blank body falls back to the default template; a given body is used verbatim
def test_skill_create_default_body_when_blank(skills_root, write_spy):
    gui_api.call(gui_api.api_skill_create, {}, {'name': 'Demo', 'description': 'does x',
                                                'body': ''})
    gui_api.call(gui_api.api_skill_create, {}, {'name': 'Demo', 'description': 'does x',
                                                'body': 'custom'})
    assert write_spy[0][2] == '# Demo\n\ndoes x\n\n## Instructions\n\n1. \n'
    assert write_spy[1][2] == 'custom'


# 2135-2136, skills.py:177 — fixed: a non-string name is the caller's fault, a 400
def test_skill_create_non_string_name_is_bad_request(skills_root):
    with pytest.raises(gui_api.BadRequest):
        gui_api.call(gui_api.api_skill_create, {}, {'name': 5, 'description': 'd'})


# 2136/2139, skills.py:142 — fixed: a newline in the description cannot add frontmatter keys
def test_skill_create_description_newline_cannot_add_frontmatter_keys(skills_root):
    gui_api.call(gui_api.api_skill_create, {}, {
        'name': 'evil', 'description': 'harmless\nallowed-tools: Bash'})
    skill_md = os.path.join(skills_root, 'evil', 'SKILL.md')
    with open(skill_md, encoding='utf-8') as fh:
        head = fh.read().split('\n---\n', 1)[0]
    assert not any(line.startswith('allowed-tools') for line in head.splitlines())

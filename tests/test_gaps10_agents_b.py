"""T-1376 · Close the test gaps in claude_sessions/agents.py description sharpening (862-963: apply_descriptions_dir, apply_descriptions, all_installed, sharpen_groups, parse_sharpened).

Exact source slice: ``claude_sessions/agents.py`` lines 862-963 at tip ``73ad7a90``
(re-located at ``3885bc1d``). No source file is edited; no new dependency.

Ten candidate branches, ranked denial/fail-closed first, then boundaries, then
error paths. Selected probes and the source branch each test catches:

 1. agents.py:871-872  blank or unchanged rewrite is skipped; file bytes untouched
 2. agents.py:876-877  write_agent returns False -> name absent, others still written
 3. agents.py:885-887  routing block and index written only when something changed
 4. agents.py:912-928  gui.list_projects raising does not hide user-level rows
 5. agents.py:913-916  all_config_dirs raising falls back to the default user dir
 6. agents.py:921-924  a project path seen twice is scanned once; a row with no path is skipped
 7. agents.py:953-960  parse_sharpened strips bullets/numbering, skips lines without '|',
                       drops descriptions of 10 characters or fewer, strips backticks
 8. agents.py:960      description longer than 400 characters is cut to 400
 9. agents.py:943-946  sharpen_groups keys on (name, desc)
10. agents.py:957-958  partition splits on the first '|' only

Every agent directory lives under tmp_path. Config dirs, the library, gui.list_projects
and write_agent are faked where they would reach the real user home or library.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from claude_sessions import agents
from claude_sessions import config as _c
from claude_sessions import gui


def _agent(path, name, desc):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(f'---\nname: {name}\ndescription: {desc}\n---\n\nbody text\n')


def _no_library(monkeypatch, tmp_path):
    lib = tmp_path / 'library'
    lib.mkdir(exist_ok=True)
    monkeypatch.setattr(agents, 'library_dir', lambda: str(lib))


def _no_accounts(monkeypatch, tmp_path):
    monkeypatch.setattr(_c, 'all_config_dirs', lambda: [])
    monkeypatch.setattr(agents, 'user_agents_dir',
                        lambda cfgdir=None: str(tmp_path / 'home' / 'agents'))


def test_a_blank_or_unchanged_rewrite_never_reaches_the_file(tmp_path, monkeypatch):
    d = tmp_path / 'agents'
    _agent(str(d / 'a.md'), 'a', 'Original description here.')
    _agent(str(d / 'b.md'), 'b', 'Another description here.')
    before = (d / 'a.md').read_bytes(), (d / 'b.md').read_bytes()

    def no_write(*a, **k):
        raise AssertionError('write_agent called for a skipped rewrite')

    monkeypatch.setattr(agents, 'write_agent', no_write)
    done = agents.apply_descriptions_dir(str(d), {'a': '   ', 'b': 'Another description here.'})
    assert done == []
    assert (d / 'a.md').read_bytes() == before[0]
    assert (d / 'b.md').read_bytes() == before[1]


def test_a_failed_write_drops_that_name_and_the_rest_still_apply(tmp_path, monkeypatch):
    d = tmp_path / 'agents'
    _agent(str(d / 'a.md'), 'a', 'Old a description.')
    _agent(str(d / 'b.md'), 'b', 'Old b description.')
    real = agents.write_agent

    def flaky(path, meta, body):
        if os.path.basename(path) == 'a.md':
            return False
        return real(path, meta, body)

    monkeypatch.setattr(agents, 'write_agent', flaky)
    done = agents.apply_descriptions_dir(str(d), {'a': 'New a description.',
                                                  'b': 'New b description.'})
    assert done == ['b']
    assert 'Old a description.' in (d / 'a.md').read_text(encoding='utf-8')
    assert 'New b description.' in (d / 'b.md').read_text(encoding='utf-8')


def test_routing_block_and_index_are_touched_only_when_something_changed(tmp_path, monkeypatch):
    proj = tmp_path / 'proj'
    d = proj / '.claude' / 'agents'
    _agent(str(d / 'a.md'), 'a', 'Same description here.')
    routed, indexed = [], []
    monkeypatch.setattr(agents, 'write_routing_block', lambda p: routed.append(p))
    monkeypatch.setattr(agents, 'write_agent_index', lambda p: indexed.append(p))

    assert agents.apply_descriptions(str(proj), {'a': 'Same description here.'}) == []
    assert routed == [] and indexed == []

    assert agents.apply_descriptions(str(proj), {'a': 'A new description here.'}) == ['a']
    assert routed == [str(proj)] and indexed == [str(proj)]


def test_a_broken_project_list_does_not_hide_user_level_agents(tmp_path, monkeypatch):
    _no_library(monkeypatch, tmp_path)
    user_dir = tmp_path / 'home' / 'agents'
    _agent(str(user_dir / 'mine.md'), 'mine', 'User level agent.')
    monkeypatch.setattr(_c, 'all_config_dirs', lambda: [('acct', str(tmp_path / 'home'))])
    monkeypatch.setattr(agents, 'user_agents_dir', lambda cfgdir=None: str(user_dir))

    def boom():
        raise RuntimeError('projects unreadable')

    monkeypatch.setattr(gui, 'list_projects', boom)
    rows = agents.all_installed()
    assert [(r['scope'], r['name']) for r in rows] == [('user', 'mine')]


def test_a_failing_account_list_falls_back_to_the_default_user_dir_only(tmp_path, monkeypatch):
    _no_library(monkeypatch, tmp_path)
    default = tmp_path / 'default' / 'agents'
    _agent(str(default / 'solo.md'), 'solo', 'Default agent.')
    monkeypatch.setattr(agents, 'user_agents_dir', lambda cfgdir=None: str(default))
    monkeypatch.setattr(gui, 'list_projects', lambda: [])

    def boom():
        raise OSError('no accounts')

    monkeypatch.setattr(_c, 'all_config_dirs', boom)
    rows = agents.all_installed()
    assert [(r['scope'], r['name'], r['dir']) for r in rows] == [('user', 'solo', str(default))]


def test_a_project_seen_twice_is_scanned_once_and_a_row_without_a_path_is_skipped(tmp_path, monkeypatch):
    _no_library(monkeypatch, tmp_path)
    _no_accounts(monkeypatch, tmp_path)
    proj = tmp_path / 'proj'
    _agent(str(proj / '.claude' / 'agents' / 'p.md'), 'p', 'Project agent.')
    monkeypatch.setattr(gui, 'list_projects', lambda: [
        {'path': str(proj), 'name': 'first'},
        {'path': str(proj), 'name': 'second'},
        {'name': 'no-path'},
        {'path': '', 'name': 'empty-path'},
    ])
    rows = [r for r in agents.all_installed() if r['scope'] == 'project']
    assert len(rows) == 1
    assert rows[0]['project_path'] == str(proj)
    assert rows[0]['account'] == 'first'


def test_parse_sharpened_keeps_only_well_formed_lines_and_cleans_them():
    text = '\n'.join([
        '1. `code-review` | Reviews a diff in detail.',
        '- * beta|Helps with the thing.',
        'no pipe on this line at all',
        'short | tenchars!!',
        'edge | elevenchars',
        '',
    ])
    got = agents.parse_sharpened(text)
    assert got == {
        'code-review': 'Reviews a diff in detail.',
        'beta': 'Helps with the thing.',
        'edge': 'elevenchars',
    }


def test_a_description_longer_than_400_characters_is_cut_to_400():
    long = 'x' * 500
    got = agents.parse_sharpened(f'name | {long}')
    assert len(got['name']) == 400
    assert got['name'] == long[:400]


def test_sharpen_groups_keys_on_name_and_description_together():
    rows = [{'name': 'a', 'desc': 'same', 'path': str(i)} for i in range(12)]
    rows.append({'name': 'a', 'desc': 'different', 'path': 'x'})
    groups = agents.sharpen_groups(rows)
    assert len(groups) == 2
    assert len(groups[('a', 'same')]) == 12
    assert len(groups[('a', 'different')]) == 1


def test_partition_splits_on_the_first_pipe_only():
    got = agents.parse_sharpened('alpha | first half | second half here')
    assert got == {'alpha': 'first half | second half here'}

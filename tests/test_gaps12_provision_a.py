"""T-1424: claude_sessions/provision.py:40-92 per-account comparison helpers at 026ea58e.

Selected candidates, not measured coverage.
Closest existing assertions: tests/test_gaps6_claude_sessions_provision_a.py:85-86
(key sets built by dict.fromkeys, no duplicate entries), :119 (n_hooks given as a
fixture). No existing test derives _n_hooks or _hooks_of from raw hook blocks.
"""

import os

import pytest

from claude_sessions import agents, hooks, plugins, provision, skills


def _settings(monkeypatch, settings):
    monkeypatch.setattr(hooks, '_load', lambda *_a: settings)


def test_duplicate_hook_entries_count_twice_and_key_once(monkeypatch):
    entry = {'hooks': [{'type': 'command', 'command': 'run'}]}
    _settings(monkeypatch, {'hooks': {'Stop': [entry, dict(entry)]}})
    assert provision._n_hooks('cfg') == 2
    assert list(provision._hooks_of('cfg')) == [('Stop', ('run',))]


def test_commandless_entries_collapse_per_event(monkeypatch):
    _settings(monkeypatch, {'hooks': {'Stop': [
        {'hooks': []}, {'hooks': []},
        {'hooks': [{'type': 'command', 'command': 'a'}]}]}})
    assert set(provision._hooks_of('cfg')) == {('Stop', ()), ('Stop', ('a',))}
    assert provision._n_hooks('cfg') == 3


@pytest.mark.xfail(strict=True, reason=(
    "claude_sessions/provision.py:50 calls .items() on a list-valued 'hooks'; "
    "the diff caller claude_sessions/gui_api.py:2352-2353 has no guard"))
def test_hooks_value_not_a_mapping_does_not_crash(monkeypatch):
    _settings(monkeypatch, {'hooks': [{'Stop': []}]})
    assert provision._hooks_of('cfg') == {}


def test_plugins_of_reads_key_field(monkeypatch):
    monkeypatch.setattr(plugins, 'installed',
                        lambda *_a: [{'key': 'a@m'}, {'key': 'b@m'}])
    assert provision._plugins_of('cfg') == {'a@m', 'b@m'}


def test_duplicate_marketplace_name_last_wins(monkeypatch):
    monkeypatch.setattr(plugins, 'known_marketplaces', lambda *_a: [
        {'name': 'm', 'repo': 'one'}, {'name': 'm', 'repo': 'two'}])
    assert provision._marketplaces_of('cfg') == {'m': {'name': 'm', 'repo': 'two'}}


def test_agents_of_missing_dir_and_extension_case(monkeypatch, tmp_path):
    d = tmp_path / 'agents'
    monkeypatch.setattr(agents, 'user_agents_dir', lambda *_a: str(d))
    assert provision._agents_of('cfg') == {}
    d.mkdir()
    (d / 'a.md').write_text('x', encoding='utf-8')
    (d / 'B.MD').write_text('x', encoding='utf-8')
    (d / 'c.txt').write_text('x', encoding='utf-8')
    assert provision._agents_of('cfg') == {'a.md': os.path.join(str(d), 'a.md')}


def test_skills_of_empty_or_missing_dir(monkeypatch, tmp_path):
    seen = []
    monkeypatch.setattr(skills, 'personal_dir', lambda cfg: str(tmp_path / cfg))
    monkeypatch.setattr(skills, 'list_skills', lambda d: seen.append(d) or [])
    assert provision._skills_of('cfg') == {}
    assert seen == [str(tmp_path / 'cfg')]


def test_skills_of_keys_by_folder_basename(monkeypatch):
    folder = os.path.join('skills', 'folder-a')
    monkeypatch.setattr(skills, 'personal_dir', lambda *_a: 'skills')
    monkeypatch.setattr(skills, 'list_skills',
                        lambda d: [('Display Name', 'desc', folder)])
    assert provision._skills_of('cfg') == {'folder-a': folder}

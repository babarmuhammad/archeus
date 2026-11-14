"""T-1407 — claude_sessions/gui_api.py history diff and restore handlers, lines 2725-2773.

Candidate list, refusal first:
 1. 2729-2730  diff with a key outside _HISTORY_KEYS is refused before any read
 2. 2768-2769  restore with an unknown or padded key is refused before any restore
 3. 2770-2773  restore failure reports 'error', never 'message'
 4. 2734-2738  an unreadable current file is treated as empty, not raised
 5. 2742-2743  an unparseable snapshot falls through to the line diff
 6. 2750-2753  graph diff header: '--- now' first, '+++ snapshot' second
 7. 2754-2757  at most 60 names per side; overflow line counts the rest
 8. 2758-2759  identical fact sets get the 'same facts' line
 9. 2744-2749  fixed: names() raising gives a false 'same facts' line
10. 2762-2763  text keys: old side is the current file, new side is the snapshot

Seams: gui_api._folder, diffview.read_version, diffview.target_path, diffview.restore
and diffview.unified are replaced with fakes where a probe needs them; the real
diffview.unified runs in probe 10. Files live under tmp_path. No real config dir,
no network, no subprocess.
"""
import builtins
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from claude_sessions import diffview, gui_api


@pytest.fixture()
def env(monkeypatch, tmp_path):
    proj_folder = str(tmp_path / 'folder')
    monkeypatch.setattr(gui_api, '_folder', lambda cfgdir, enc: proj_folder)
    state = {'current': None, 'snapshot': '', 'reads': [], 'targets': []}
    current = tmp_path / 'current.txt'

    def read_version(pr, fo, key, ts):
        state['reads'].append((key, ts))
        return state['snapshot']

    def target_path(pr, fo, key):
        state['targets'].append(key)
        return str(current)

    monkeypatch.setattr(diffview, 'read_version', read_version)
    monkeypatch.setattr(diffview, 'target_path', target_path)
    state['path'] = str(current)
    return state


def _graph(*entities):
    return json.dumps({'entities': list(entities), 'relations': []})


def _diff(env, key, ts='1700000000'):
    if env['current'] is not None:
        with open(env['path'], 'w', encoding='utf-8') as fh:
            fh.write(env['current'])
    return gui_api.call(gui_api.api_history_diff,
                        {'enc': 'proj-1', 'path': '/p', 'key': key, 'ts': ts}, None)


# 2729-2730 — an unknown key is refused before the snapshot or the live file is read
def test_history_diff_unknown_key_reads_nothing(env):
    with pytest.raises(gui_api.BadRequest, match='unknown history key'):
        _diff(env, 'settings')
    assert env['reads'] == []
    assert env['targets'] == []


# 2768-2769 — a padded or missing key is refused before any restore
def test_history_restore_unknown_key_writes_nothing(monkeypatch):
    restored = []
    monkeypatch.setattr(diffview, 'restore', lambda *a: restored.append(a) or (True, 'x'))
    for bad in ('memory_graph ', None):
        with pytest.raises(gui_api.BadRequest, match='unknown history key'):
            gui_api.call(gui_api.api_history_restore, {},
                         {'enc': 'proj-1', 'path': '/p', 'key': bad, 'ts': '1'})
    assert restored == []


# 2770-2773 — a failed restore reports 'error' and no 'message'
def test_history_restore_failure_reports_error_key(monkeypatch):
    monkeypatch.setattr(diffview, 'restore', lambda *a: (False, 'that version is gone'))
    body = {'enc': 'proj-1', 'path': '/p', 'key': 'claude_md', 'ts': '1'}
    out = gui_api.call(gui_api.api_history_restore, {}, body)
    assert out == {'ok': False, 'error': 'that version is gone'}

    monkeypatch.setattr(diffview, 'restore', lambda *a: (True, 'restored'))
    out = gui_api.call(gui_api.api_history_restore, {}, body)
    assert out == {'ok': True, 'message': 'restored'}


# 2734-2738 — a live file that cannot be read counts as empty, nothing is raised
def test_history_diff_unreadable_current_is_empty(env, monkeypatch):
    env['current'] = 'live text'
    env['snapshot'] = 'old text'
    real_open = builtins.open
    target = env['path']

    def failing_open(file, *a, **k):
        mode = a[0] if a else k.get('mode', 'r')
        if os.fspath(file) == target and 'w' not in mode:
            raise OSError('locked')
        return real_open(file, *a, **k)

    monkeypatch.setattr(builtins, 'open', failing_open)
    seen = []
    monkeypatch.setattr(diffview, 'unified', lambda cur, old, label: seen.append((cur, old)) or ['d'])
    out = _diff(env, 'claude_md')
    assert seen == [('', 'old text')]
    assert out == {'title': diffview.TITLES.get('claude_md', 'claude_md'), 'diff': ['d']}


# 2742-2743 — a snapshot that is not JSON falls through to the line diff
def test_history_diff_unparseable_snapshot_uses_line_diff(env, monkeypatch):
    env['current'] = _graph({'name': 'a', 'type': 'person'})
    env['snapshot'] = 'not json'
    seen = []
    monkeypatch.setattr(diffview, 'unified', lambda cur, old, label: seen.append((cur, old)) or ['u'])
    out = _diff(env, 'memory_graph')
    assert seen == [(env['current'], 'not json')]
    assert out['diff'] == ['u']


# 2750-2753 — header order: the live graph is '--- now', the snapshot is '+++ snapshot'
def test_history_graph_diff_header_order(env):
    env['current'] = _graph({'name': 'a', 'type': 'person'})
    env['snapshot'] = _graph({'name': 'b', 'type': 'person'})
    out = _diff(env, 'memory_graph')
    assert out['diff'][0] == '--- now: 1 entities, 0 relations, 0 lessons'
    assert out['diff'][1] == '+++ snapshot: 1 entities, 0 relations, 0 lessons'
    assert out['diff'][2] == '@@ what restoring would change @@'
    assert '+ b' in out['diff'] and '- a' in out['diff']


# 2754-2757 — each side is capped at 60 names; the overflow line counts the rest
def test_history_graph_diff_caps_each_side_at_sixty(env):
    env['current'] = _graph()
    env['snapshot'] = _graph(*({'name': f'n{i:02d}', 'type': 'person'} for i in range(70)))
    out = _diff(env, 'memory_graph')
    added = [line for line in out['diff'] if line.startswith('+ ')]
    assert len(added) == 60
    assert out['diff'][-1] == '@@ …and 10 more @@'


# 2758-2759 — identical fact sets with changed summaries get the 'same facts' line
def test_history_graph_diff_same_facts_line(env):
    env['current'] = _graph({'name': 'a', 'type': 'person', 'summary': 'new'})
    env['snapshot'] = _graph({'name': 'a', 'type': 'person', 'summary': 'old'})
    out = _diff(env, 'memory_graph')
    assert out['diff'][-1] == '  the same facts — only their summaries or counters moved'


# 2744-2749 — fixed: names() raising must not read as 'the same facts'
def test_history_graph_diff_unparseable_names_falls_back(env, monkeypatch):
    env['current'] = _graph({'name': ['x'], 'type': 'person'})
    env['snapshot'] = _graph({'name': 'y', 'type': 'person'})
    seen = []
    monkeypatch.setattr(diffview, 'unified', lambda cur, old, label: seen.append((cur, old)) or ['u'])
    out = _diff(env, 'memory_graph')
    assert seen == [(env['current'], env['snapshot'])]
    assert out['diff'] == ['u']


# 2762-2763 — text keys: old side is the live file, new side is the snapshot
def test_history_text_diff_old_is_current(env):
    env['current'] = 'a\nb\n'
    env['snapshot'] = 'a\nc\n'
    out = _diff(env, 'claude_md')
    assert out['title'] == diffview.TITLES.get('claude_md', 'claude_md')
    assert '-b' in out['diff'] and '+c' in out['diff']
    assert '+b' not in out['diff'] and '-c' not in out['diff']

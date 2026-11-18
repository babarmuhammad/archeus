"""T-1272: claude_sessions/store.py:121-185 at 6bbd3b44 (account session confinement and scratch exclusion).

Selected probes, denial first, then boundaries, then error paths:
183 session_file refuses invalid sid before project_folder (test_session_file_refuses_bad_sid_before_project_folder)
185 session_file resolves inside the named account only (test_session_file_resolves_in_named_account_only)
137 filesystem-root temp disables the filter (test_filesystem_root_temp_disables_filter)
139 user-profile temp disables the filter (test_user_profile_temp_disables_filter_but_real_temp_does_not)
135 gettempdir failure returns no filter, no fallback (test_gettempdir_failure_returns_no_filter_without_fallback)
156 sibling-prefix path stays visible (test_sibling_prefix_is_not_scratch)
153 empty path or disabled root is never scratch (test_empty_path_and_disabled_root_are_never_scratch)
173 scratch projects filtered before sort (test_scratch_projects_are_filtered_before_sort)
176 home tuples keep their fields and deterministic ties (test_all_projects_tuples_keep_fields_and_tie_order)
172 harness discovery failure propagates (test_harness_discovery_failure_propagates_without_fallback)
"""

import os
import tempfile

import pytest

from claude_sessions import config as _c
from claude_sessions import harnesses, store


def test_session_file_refuses_bad_sid_before_project_folder(monkeypatch, tmp_path):
    def refuse(*_a, **_k):
        raise AssertionError('project_folder reached')

    monkeypatch.setattr(store, 'project_folder', refuse)
    for bad in ['', '..', 'a/b', 'x y', 'é']:
        with pytest.raises(ValueError):
            store.session_file(str(tmp_path), 'C-work-a', bad)


def test_session_file_resolves_in_named_account_only(monkeypatch, tmp_path):
    cfg_a, cfg_b = str(tmp_path / 'A'), str(tmp_path / 'B')
    session_b = os.path.join(store.projects_root(cfg_b), 'C-work-a', 's1.jsonl')
    os.makedirs(os.path.dirname(session_b))
    open(session_b, 'w', encoding='utf-8', newline='').close()
    monkeypatch.setattr(_c, 'config_dir', cfg_b)
    got = store.session_file(cfg_a, 'C-work-a', 's1')
    assert got == os.path.join(store.projects_root(cfg_a), 'C-work-a', 's1.jsonl')
    assert not os.path.exists(got)


def test_filesystem_root_temp_disables_filter(monkeypatch):
    root = os.path.abspath(os.sep)
    monkeypatch.setattr(tempfile, 'gettempdir', lambda: root)
    assert store.temp_root() == ''
    assert store.under_temp(os.path.join(root, 'anything')) is False


def test_user_profile_temp_disables_filter_but_real_temp_does_not(monkeypatch, tmp_path):
    profile = tmp_path / 'profile'
    scratch = tmp_path / 'scratch'
    monkeypatch.setattr(_c, '_USERPROFILE', str(profile))
    monkeypatch.setattr(tempfile, 'gettempdir', lambda: str(profile))
    assert store.temp_root() == ''
    monkeypatch.setattr(tempfile, 'gettempdir', lambda: str(scratch))
    assert store.temp_root() == os.path.abspath(str(scratch))


def test_gettempdir_failure_returns_no_filter_without_fallback(monkeypatch, tmp_path):
    def broken():
        raise OSError('no temp')

    fallback = str(tmp_path / 'fallback')
    monkeypatch.setattr(tempfile, 'gettempdir', broken)
    monkeypatch.setattr(_c, '_TEMP', fallback)
    monkeypatch.setattr(_c, '_USERPROFILE', str(tmp_path / 'profile'))
    assert store.temp_root() == ''
    assert store.under_temp(os.path.join(fallback, 'x')) is False


def test_sibling_prefix_is_not_scratch(monkeypatch, tmp_path):
    root = tmp_path / 'tmp'
    monkeypatch.setattr(tempfile, 'gettempdir', lambda: str(root))
    monkeypatch.setattr(_c, '_USERPROFILE', str(tmp_path / 'home'))
    assert store.under_temp(str(tmp_path / 'tmp-other' / 'p')) is False
    assert store.under_temp(str(root)) is True
    assert store.under_temp(str(root / 'x' / 'y')) is True


def test_empty_path_and_disabled_root_are_never_scratch(monkeypatch, tmp_path):
    root = tmp_path / 'tmp'
    root.mkdir()
    monkeypatch.setattr(tempfile, 'gettempdir', lambda: str(root))
    monkeypatch.setattr(_c, '_USERPROFILE', str(tmp_path / 'home'))
    monkeypatch.chdir(root)
    assert store.under_temp('') is False
    monkeypatch.setattr(store, 'temp_root', lambda: '')
    assert store.under_temp(str(root / 'x')) is False


def test_scratch_projects_are_filtered_before_sort(monkeypatch, tmp_path):
    scratch = tmp_path / 'scratch'
    home = str(tmp_path / 'acct')
    rows = [(9.0, str(scratch / 'probe'), 'P'),
            (5.0, str(tmp_path / 'work' / 'a'), 'A'),
            (3.0, str(tmp_path / 'work' / 'b'), 'B')]
    monkeypatch.setattr(tempfile, 'gettempdir', lambda: str(scratch))
    monkeypatch.setattr(_c, '_USERPROFILE', str(tmp_path / 'home'))
    monkeypatch.setattr(harnesses, 'instances', lambda: [('claude', home, 'claude')])
    monkeypatch.setattr(harnesses, 'impl', lambda key, hid=None: lambda h: rows)
    assert store.all_projects() == [
        (5.0, str(tmp_path / 'work' / 'a'), 'A', home),
        (3.0, str(tmp_path / 'work' / 'b'), 'B', home),
    ]


def test_all_projects_tuples_keep_fields_and_tie_order(monkeypatch, tmp_path):
    h1, h2 = str(tmp_path / 'h1'), str(tmp_path / 'h2')
    per_home = {
        'claude': (h1, [(5.0, str(tmp_path / 'w' / 'a'), 'enc-a')]),
        'codex': (h2, [(5.0, str(tmp_path / 'w' / 'a'), 'enc-a'),
                       (7.0, str(tmp_path / 'w' / 'b'), 'enc-b')]),
    }
    monkeypatch.setattr(tempfile, 'gettempdir', lambda: str(tmp_path / 'scratch'))
    monkeypatch.setattr(_c, '_USERPROFILE', str(tmp_path / 'home'))
    monkeypatch.setattr(harnesses, 'instances',
                        lambda: [('claude', h1, 'claude'), ('codex', h2, 'codex')])
    monkeypatch.setattr(harnesses, 'impl',
                        lambda key, hid=None: lambda h: per_home[hid][1])
    assert store.all_projects() == [
        (7.0, str(tmp_path / 'w' / 'b'), 'enc-b', h2),
        (5.0, str(tmp_path / 'w' / 'a'), 'enc-a', h2),
        (5.0, str(tmp_path / 'w' / 'a'), 'enc-a', h1),
    ]


def test_harness_discovery_failure_propagates_without_fallback(monkeypatch, tmp_path):
    def broken():
        raise RuntimeError('discovery failed')

    projected = []
    monkeypatch.setattr(harnesses, 'instances', broken)
    monkeypatch.setattr(harnesses, 'impl',
                        lambda key, hid=None: projected.append(hid) or (lambda h: []))
    with pytest.raises(RuntimeError):
        store.all_projects()
    assert projected == []

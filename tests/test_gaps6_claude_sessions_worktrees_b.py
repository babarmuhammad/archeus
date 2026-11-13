"""T-1291: claude_sessions/worktrees.py:58-142 at 6bbd3b44; same current slice.

Selected probes, not measured coverage; closest test_plugins_worktrees.py:
94 unknown vs empty status plus argv; :529 checks board dirty count only.
111 unknown dirty/diff matrix; :503 checks failed diff through board only.
120 unknown exclusion with case seam; :497 Windows-only, no unknown member.
96 quoted arrow path; :458 tests unquoted rename paths without spaces.
109 empty/main SHA exact argv; :467 tests short-prefix rejection indirectly.
71 spaces/non-head prefix/bare; :202 omits bare and path spaces.
82 unterminated final row once; :202 ends each row with blank terminator.
74 HEAD before worktree; :202 contains only valid porcelain.
129 normalized duplicates/count cap; :489 has unique lowercase names only.
139 ahead/behind malformed boundary; :241 tests board sessions, not counts.
"""

import os
from types import SimpleNamespace

import pytest

from claude_sessions import worktrees as w


def test_status_unknown_distinct_from_successful_empty(monkeypatch):
    calls = []
    outputs = iter([None, ''])

    def git(args, cwd):
        calls.append((args, cwd))
        return next(outputs)

    monkeypatch.setattr(w, '_git', git)
    assert w._dirty_files('tree') is None
    assert w._dirty_files('tree') == []
    assert calls == [(w._PLAIN + ['status', '--porcelain', '-uall'], 'tree')] * 2


def test_changed_files_unknown_matrix_and_known_empty(monkeypatch):
    output = {'text': ''}
    monkeypatch.setattr(w, '_git', lambda *a, **kw: output['text'])
    assert w._changed_files('tree', 'sha', None) is None
    output['text'] = None
    assert w._changed_files('tree', 'sha', ['dirty']) is None
    output['text'] = ''
    assert w._changed_files('tree', 'sha', []) == set()
    output['text'] = 'committed\n\n'
    assert w._changed_files('tree', 'sha', ['dirty', 'committed']) == {'committed', 'dirty'}


def test_unknown_member_excluded_from_casefolded_overlap(monkeypatch):
    monkeypatch.setattr(w, 'os', SimpleNamespace(path=SimpleNamespace(normcase=str.casefold)))
    first, second = os.path.join('Src', 'File'), os.path.join('src', 'file')
    result = w._overlaps({'a': [first], 'unknown': None, 'b': [second], 'empty': []})
    assert result == [{'a': 'a', 'b': 'b', 'count': 1, 'files': [first]}]


def test_quoted_arrow_filename_stays_one_dirty_path(monkeypatch):
    monkeypatch.setattr(w, '_git', lambda *a, **kw: ' M "literal -> file.txt"\n')
    assert w._dirty_files('tree') == ['literal -> file.txt']


def test_main_without_head_skips_diff_full_head_uses_exact_range(monkeypatch):
    calls = []

    def git(args, cwd):
        calls.append((args, cwd))
        return 'committed file\n'

    monkeypatch.setattr(w, '_git', git)
    assert w._changed_files('main', '', ['dirty file']) == {'dirty file'}
    assert calls == []
    sha = 'a' * 40
    assert w._changed_files('tree', sha, ['dirty file']) == {'dirty file', 'committed file'}
    assert calls == [(w._PLAIN + ['diff', '--name-only', '--no-renames', sha + '...HEAD'], 'tree')]


def test_porcelain_spaces_nonhead_prefix_and_independent_flags(monkeypatch, tmp_path):
    path = str(tmp_path / 'tree with spaces')
    output = f'worktree {path}\nHEAD abcdef123456\nbranch refs/remotes/origin/main\nbare\ndetached\n'
    monkeypatch.setattr(w, '_git', lambda *a, **kw: output)
    assert w.list_worktrees('project') == [{
        'path': os.path.normpath(path), 'branch': 'refs/remotes/origin/main',
        'head': 'abcdef12', 'bare': True, 'detached': True, 'main': True}]


def test_unterminated_last_porcelain_record_retained_once(monkeypatch, tmp_path):
    a, b = str(tmp_path / 'a'), str(tmp_path / 'b')
    output = f'worktree {a}\nbranch refs/heads/main\n\nworktree {b}\nbranch refs/heads/next'
    monkeypatch.setattr(w, '_git', lambda *a, **kw: output)
    rows = w.list_worktrees('project')
    assert [r['path'] for r in rows] == [a, b]
    assert [r['branch'] for r in rows] == ['main', 'next']
    assert [r['main'] for r in rows] == [True, False]


def test_orphan_head_cannot_synthesize_worktree(monkeypatch):
    monkeypatch.setattr(w, '_git', lambda *a, **kw: 'HEAD abcdef1234\n\n')
    assert w.list_worktrees('project') == []


def test_overlap_count_deduplicates_normalized_names_before_cap(monkeypatch):
    monkeypatch.setattr(w, 'os', SimpleNamespace(path=SimpleNamespace(normcase=str.casefold)))
    monkeypatch.setattr(w, 'OVERLAP_SHOW', 1)
    assert w._overlaps({'a': ['B', 'A', 'a'], 'b': ['a', 'b']}) == [
        {'a': 'a', 'b': 'b', 'count': 2, 'files': ['a']}]
    assert w._overlaps({'a': [], 'b': []}) == []


@pytest.mark.parametrize('out,expected', [('7 2\n', (2, 7)), (None, (0, 0)),
                                         ('', (0, 0)), ('bad 2', (0, 0)), ('1', (0, 0))])
def test_ahead_behind_maps_sides_and_handles_unknown(monkeypatch, out, expected):
    calls = []

    def git(args, cwd):
        calls.append((args, cwd))
        return out

    monkeypatch.setattr(w, '_git', git)
    assert w.ahead_behind('tree', base='base') == expected
    assert calls == [(['rev-list', '--left-right', '--count', 'base...HEAD'], 'tree')]

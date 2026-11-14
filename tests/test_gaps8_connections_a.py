"""T-1339: the highest-risk uncovered branches of claude_sessions/connections.py
lines 81-108 inclusive (source walk caps, prunes and truncation report), at
tip 4e253ad5 of pv20-fx85g. Denial and fail-closed first, then boundaries,
then error paths.

Selected branches (source line, probe):
1. _walk_source_files 89-91         unreadable root: no files, truncated True, one onerror
2. _walk_source_files 97            SKIP_DIRS and dot-directories are pruned, never listed
3. _walk_source_files 94-96         a dir at MAX_DEPTH keeps its own files, is not descended
4. _walk_source_files 98-102        only SOURCE_EXT kept; SKIP_EXT and unknown extensions dropped
5. _walk_source_files 103-105       reaching max_files returns truncated True and stops
6. _walk_source_files 98            names sorted within each directory, dirs walked in order
7. _walk_source_files 86-87         empty tree returns ([], False); relative root made absolute
8. _walk_source_files 106-107       inner break also stops the outer walk (control)
9. _walk_source_files 102           every returned path lies under the walked root
10. _walk_source_files 103-105      PREMISE: exactly max_files source files, no more, is not
                                    truncated (strict xfail at connections.py:103-105)
extra. SKIP_EXT 27-29 with 100     PREMISE: a .min.js file is skipped by SKIP_EXT
                                    (strict xfail at connections.py:27-29, 100)
"""

import os

import pytest

from claude_sessions import connections


def _touch(base, rel, content='x = 1\n'):
    p = os.path.join(str(base), *rel.split('/'))
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(content)
    return p


def _rel_names(root, paths):
    return [os.path.relpath(p, str(root)).replace(os.sep, '/') for p in paths]


def test_an_unreadable_root_yields_no_files_and_reports_truncation(monkeypatch, tmp_path):
    _touch(tmp_path, 'a.py')
    reported = []

    def fake_walk(top, onerror=None, **kwargs):
        onerror(PermissionError(13, 'denied', top))
        reported.append(top)
        return iter(())

    monkeypatch.setattr(connections.os, 'walk', fake_walk)
    assert connections._walk_source_files(str(tmp_path), 100) == ([], True)
    assert len(reported) == 1


def test_skipped_and_dot_directories_are_pruned_before_listing(tmp_path):
    _touch(tmp_path, 'pkg/ok.py')
    for d in ('node_modules', 'venv', 'build', '.claude', '.hidden', '__pycache__'):
        _touch(tmp_path, f'{d}/inner.py')
    files, truncated = connections._walk_source_files(str(tmp_path), 100)
    assert _rel_names(tmp_path, files) == ['pkg/ok.py'] and truncated is False


def test_a_directory_at_max_depth_keeps_its_files_but_is_not_descended(tmp_path):
    chain = '/'.join(f'd{i}' for i in range(1, 15))
    _touch(tmp_path, 'top.py')
    _touch(tmp_path, '/'.join(f'd{i}' for i in range(1, 14)) + '/at_cap.py')
    _touch(tmp_path, chain + '/too_deep.py')
    files, truncated = connections._walk_source_files(str(tmp_path), 100)
    names = _rel_names(tmp_path, files)
    assert 'top.py' in names
    assert '/'.join(f'd{i}' for i in range(1, 14)) + '/at_cap.py' in names
    assert not [n for n in names if n.endswith('too_deep.py')]
    assert truncated is False


def test_only_source_extensions_are_kept_and_matched_case_insensitively(tmp_path):
    for nm in ('a.py', 'UP.PY', 'notes.md', 'pic.png', 'data.zip', 'build.lock',
               'mystery.xyz', 'noext'):
        _touch(tmp_path, nm)
    files, _ = connections._walk_source_files(str(tmp_path), 100)
    assert _rel_names(tmp_path, files) == ['UP.PY', 'a.py', 'notes.md']


def test_reaching_max_files_reports_truncation_and_stops(tmp_path):
    for i in range(5):
        _touch(tmp_path, f'f{i}.py')
    files, truncated = connections._walk_source_files(str(tmp_path), 3)
    assert _rel_names(tmp_path, files) == ['f0.py', 'f1.py', 'f2.py'] and truncated is True


def test_names_are_sorted_within_a_directory_and_directories_are_walked_in_order(tmp_path):
    for nm in ('c.py', 'a.py', 'b.py'):
        _touch(tmp_path, nm)
    _touch(tmp_path, 'z/x.py')
    _touch(tmp_path, 'm/y.py')
    files, _ = connections._walk_source_files(str(tmp_path), 100)
    assert _rel_names(tmp_path, files) == ['a.py', 'b.py', 'c.py', 'm/y.py', 'z/x.py']


def test_an_empty_tree_returns_no_files_and_a_relative_root_is_made_absolute(monkeypatch, tmp_path):
    (tmp_path / 'empty').mkdir()
    assert connections._walk_source_files(str(tmp_path / 'empty'), 10) == ([], False)
    _touch(tmp_path, 'a.py')
    monkeypatch.chdir(tmp_path)
    files, truncated = connections._walk_source_files('.', 10)
    assert truncated is False and len(files) == 1
    assert os.path.isabs(files[0]) and os.path.samefile(files[0], str(tmp_path / 'a.py'))


def test_the_inner_break_also_stops_the_outer_walk(tmp_path):
    _touch(tmp_path, 'a/1.py')
    _touch(tmp_path, 'a/2.py')
    _touch(tmp_path, 'b/3.py')
    files, truncated = connections._walk_source_files(str(tmp_path), 2)
    assert _rel_names(tmp_path, files) == ['a/1.py', 'a/2.py'] and truncated is True


def test_every_returned_path_lies_under_the_walked_root(tmp_path):
    _touch(tmp_path, 'x.py')
    _touch(tmp_path, 'deep/er/still.ts')
    root = os.path.abspath(str(tmp_path))
    files, _ = connections._walk_source_files(str(tmp_path), 100)
    assert len(files) == 2
    assert all(os.path.commonpath([p, root]) == root for p in files)


@pytest.mark.xfail(strict=True, reason="connections.py:103-105: truncated is set as soon as the cap "
                   "is reached, even when no further source file exists, so exactly max_files files "
                   "reports a truncation that did not happen")
def test_exactly_max_files_with_no_more_is_not_reported_as_truncated(tmp_path):
    for i in range(3):
        _touch(tmp_path, f'f{i}.py')
    files, truncated = connections._walk_source_files(str(tmp_path), 3)
    assert len(files) == 3
    assert truncated is False


@pytest.mark.xfail(strict=True, reason="connections.py:27-29 and 100: SKIP_EXT lists '.min.js', but "
                   "os.path.splitext returns only '.js', so minified bundles are kept as source")
def test_minified_javascript_is_skipped(tmp_path):
    _touch(tmp_path, 'app.js')
    _touch(tmp_path, 'vendor.min.js')
    files, _ = connections._walk_source_files(str(tmp_path), 100)
    assert _rel_names(tmp_path, files) == ['app.js']

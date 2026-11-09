"""T-1102: characterisation of `overlap` / `serialise` on Windows-shaped paths.

Written against archeus/core/planning/validate.py (`_plain`, `_prefix`, `overlap`,
`_reaches`, `serialise`). Style, the parametrised shape and the task-dict
helper are copied from tests/v1/unit/test_gaps_core_planning_validate.py (lines
33-37, 207-241, 244-265) and from tests/v1/unit/test_fix_planning_validate.py
(lines 1-22); neither module is imported here.

What the three functions do, one line each:

- `_plain` — every backslash becomes a slash, empty and `.` segments vanish, `..`
  is resolved with `posixpath.normpath` and case is folded; a bare `.` becomes the
  empty string, which overlaps everything.
- `_prefix` — the literal head of a glob, cut at the first `*?[`.
- `overlap` — empty or equal strings, or `fnmatchcase` either way, or, when at least
  one side is a pattern, one literal prefix starting with the other, else the
  plain-directory rule `a.startswith(b + '/')`.
- `serialise` — for every earlier/later pair with no dependency path
  between them whose `touches` overlap, the later one gains a dependency on the
  earlier one and the reason is recorded.

`overlap` is deliberately conservative: a false YES only costs parallelism, a false
NO lets two tasks write one file at once. So the cases whose answer is correct today
are pinned as passing tests (groups A, B and — where it says yes too often — C,
pinned as today's behaviour, not as a promise). Group D (case folding, `..`, a bare
`.`) and the `serialise` case clash were strict xfails when the card was written; the
fix landed in the pv20-t1103 lineage, so they are plain assertions now. Case folding
assumes a case-insensitive filesystem (NTFS, the Windows default); on a
case-sensitive one a false yes only costs parallelism.

Everything here is a pure function over plain strings: no filesystem, no process, no
network, no clock. The file is therefore platform-neutral — the backslash inputs are
Windows-shaped *strings*, not Windows paths, and the same rows run on Linux.
"""

import pytest

from archeus.core.planning import validate


def t(key, touches=None):
    """A task dict for `serialise`: a key and, when given, the globs it touches.
    `serialise` reads them with `.get('touches', ())`, so a
    task that names no `touches` clashes with nothing."""
    task = {'key': key}
    if touches is not None:
        task['touches'] = tuple(touches)
    return task


# ── A. Windows shapes that CAN name one file: `overlap` says yes, correctly ──

@pytest.mark.parametrize('a, b', [
    pytest.param('src\\a.py', 'src/a.py', id='backslash-file'),
    pytest.param('src\\pkg\\', 'src/pkg/a.py', id='backslash-trailing-dir'),
    pytest.param('src\\*.py', 'src/a.py', id='backslash-glob'),
    pytest.param('src/./a.py', 'src/a.py', id='dot-middle'),
    pytest.param('./src/a.py', 'src/a.py', id='dot-leading'),
    pytest.param('src/.', 'src/a.py', id='dot-trailing'),
    pytest.param('src/', 'src', id='trailing-slash-equal'),
    pytest.param('src/', 'src/a.py', id='trailing-slash-dir-file'),
    pytest.param('src//', 'src/a.py', id='double-slash'),
    pytest.param('C:\\Repo\\a.py', 'C:/Repo/a.py', id='drive-two-slash-styles'),
    pytest.param('C:\\Repo\\', 'C:\\Repo\\a.py', id='drive-dir-file'),
    pytest.param('src', 'src/a.py', id='dir-contains-file'),
    pytest.param('src/a/b', 'src/a', id='dir-inside-dir'),
    pytest.param('src/**', 'src/a/b.py', id='globstar-deep'),
    pytest.param('src/**', 'src', id='globstar-dir-itself'),
    pytest.param('**', 'src/a.py', id='globstar-all'),
    pytest.param('**/*.py', 'src/a.py', id='globstar-ext'),
    pytest.param('**/a.py', 'a.py', id='globstar-top-level'),
    pytest.param('src/**/a.py', 'src/a.py', id='globstar-middle'),
    pytest.param('src/a.py', 'src/a.py', id='identical'),
])
def test_overlap_says_yes_for_paths_that_can_clash(a, b):
    """`_plain` — `glob.replace('\\', '/')` and the
    `p not in ('', '.')` filter. Drop the `replace` and every backslash row stops
    matching its slash spelling (two tasks writing `src\\a.py` and `src/a.py` run in
    parallel on one file); drop the filter and `src/`, `src//`, `src/.` and
    `./src/a.py` stop equaling their plain spelling. The equality check catches the
    rest, and the `a.startswith(b + '/')` rule the directory rows."""
    assert validate.overlap(a, b) is True
    assert validate.overlap(b, a) is True


# ── B. Shapes that CANNOT share a file: `overlap` says no, correctly ──────────

@pytest.mark.parametrize('a, b', [
    pytest.param('src/', 'srcfoo/a.py', id='sibling-prefix'),
    pytest.param('src/a', 'src/a.py', id='literal-prefix'),
    pytest.param('src/**', 'docs/a.md', id='other-tree'),
    pytest.param('src/a.py', 'src/b.py', id='two-files'),
    pytest.param('docs/**', 'src/**', id='two-trees'),
])
def test_overlap_says_no_for_disjoint_paths(a, b):
    """The last two lines of `overlap` — the wildcard guard `(pa != a) or (pb != b)`
    and the directory rule `a.startswith(b + '/') or
    b.startswith(a + '/')`. Without the guard every pair of literals sharing
    a prefix becomes a clash (`src/a` vs `src/a.py`, `src/` vs `srcfoo/a.py` — the
    sibling near miss), and a bare `startswith` on 114 instead of `startswith(b +
    '/')` serialises those same two pairs: parallelism lost for no reason, and the
    planner's `serialised` record full of invented edges."""
    assert validate.overlap(a, b) is False
    assert validate.overlap(b, a) is False


# ── C. Where it says yes although the two cannot share a file (harmless) ──────

@pytest.mark.parametrize('a, b', [
    pytest.param('src/*.py', 'src/a/b.py', id='one-star-crosses-slash'),
    pytest.param('**/*.py', 'docs/a.md', id='empty-prefix-wildcard'),
    pytest.param('src/**/*.py', 'src/a.md', id='wildcard-prefix-only'),
])
def test_overlap_stays_conservative_where_it_says_yes_too_often(a, b):
    """The prefix rule (`pa, pb = _prefix(a), _prefix(b)`,
    the wildcard guard, `pa.startswith(pb) or pb.startswith(pa)`), plus the fact that
    `fnmatch`'s `*` also matches `/`. These are pinned as TODAY's behaviour, not as a
    promise: a false yes costs parallelism and nothing else. Tightening the prefix rule (a
    real glob intersection, or `*` that stops at `/`) may flip these rows, and a fix
    card is free to change them — only a false NO would be a bug."""
    assert validate.overlap(a, b) is True
    assert validate.overlap(b, a) is True


# ── D. Formerly gaps (fixed in the pv20-t1103 lineage): `overlap` must say yes ──

@pytest.mark.parametrize('a, b', [
    pytest.param('C:\\Repo\\a.py', 'c:\\repo\\a.py', id='drive-and-dir-case'),
    pytest.param('C:\\Repo\\a.py', 'c:\\Repo\\a.py', id='drive-letter-case'),
    pytest.param('Src/a.py', 'src/a.py', id='segment-case'),
    pytest.param('Src', 'src/a.py', id='dir-vs-file-case'),
    pytest.param('SRC/*.py', 'src/a.py', id='glob-case'),
])
def test_overlap_folds_case(a, b):
    """`_plain` casefolds, so two spellings of one NTFS file compare equal. Drop the
    `casefold` and every row here turns back into a false NO (two tasks writing one
    file in parallel)."""
    assert validate.overlap(a, b) is True
    assert validate.overlap(b, a) is True


@pytest.mark.parametrize('a, b', [
    pytest.param('src/x/../a.py', 'src/a.py', id='dotdot-middle'),
    pytest.param('src/../docs/a.md', 'docs/a.md', id='dotdot-up-and-over'),
    pytest.param('src/a.py', 'docs/../src/a.py', id='dotdot-other-side'),
])
def test_overlap_resolves_dotdot(a, b):
    """`_plain` runs `posixpath.normpath`, so `x/..` cancels and the two globs name
    one file once the path is resolved."""
    assert validate.overlap(a, b) is True
    assert validate.overlap(b, a) is True


@pytest.mark.parametrize('a, b', [
    pytest.param('.', 'src/a.py', id='bare-dot-names-whole-tree'),
])
def test_overlap_bare_dot_names_the_whole_tree(a, b):
    """`_plain('.')` is `''` and `overlap` treats an empty side as the whole tree.
    Whether the planner ever emits a bare `.` as a `touches` glob is a separate
    question; this row only records the answer."""
    assert validate.overlap(a, b) is True
    assert validate.overlap(b, a) is True


# ── E. `serialise`: the D8 edge it must add ───────────────────────────────────

def test_serialise_adds_the_dependency_for_a_passing_pair():
    """The `clash = next(...overlap(x, y)...)` scan and the
    `deps[b].append(a)` / `added.append(...)` behind it, plus the `_reaches` guard that must not fire here (nothing depends on anything). A Windows-shaped glob
    and a `./`-prefixed one are the same file, so `b` is serialised behind `a` with
    both globs in the reason, and untouched `c` stays free."""
    tasks = [t('a', ('src\\a.py',)), t('b', ('./src/a.py',)), t('c', ('docs/x.md',))]
    out, added = validate.serialise(tasks)
    assert added == [{'task': 'b', 'after': 'a',
                      'because': 'touches overlap: src\\a.py ~ ./src/a.py'}]
    assert {x['key']: x['depends_on'] for x in out} == {'a': (), 'b': ('a',), 'c': ()}


def test_serialise_adds_the_dependency_for_a_case_only_clash():
    """`Src/a.py` and `src/a.py` are one file on NTFS, so `serialise` adds exactly
    one edge and `b` depends on `a`."""
    tasks = [t('a', ('Src/a.py',)), t('b', ('src/a.py',))]
    out, added = validate.serialise(tasks)
    assert len(added) == 1
    assert {x['key']: x['depends_on'] for x in out} == {'a': (), 'b': ('a',)}

"""T-1362: claude_sessions/conventions.py lines 100-145 at tip 10d688c0 (_load_graph
skip, and _candidates: lesson filters, same-rule clustering across projects,
pinned/reviewed folding, confidence maximum, promotion gates, score and sort).

Selected candidates, not measured coverage. Ranked denial/fail-closed first,
then boundaries, then error paths:

1.  129-133    PREMISE, strict xfail: a second cluster member with confidence None
               makes max() raise TypeError and aborts the candidate list
2.  117-119    only approved, pinned or pending lessons count; rejected, blank
               and missing status are excluded
3.  115        lessons whose kind is outside _KINDS are excluded
4.  100-102    a graph that cannot be read or has no entities is None, not raised
5.  120-122    an empty or whitespace summary is skipped
6.  124-126    the same rule twice in one project counts as one project
7.  127-128    pinned and reviewed fold across the cluster with OR
8.  137-139    promotion: pinned always; reviewed needs MIN_PROJECTS; unreviewed
               needs MIN_PROJECTS_UNREVIEWED; one short of each stays unpromoted
9.  129        confidence keeps the maximum across cluster members
10. 142-144    score = projects*10 + 5 if pinned + confidence; sorted descending

Seams: conventions._iter_project_graphs yields synthetic (key, graph, path,
folder) tuples; MIN_PROJECTS and MIN_PROJECTS_UNREVIEWED are set to 2 and 3;
_load_graph is called on tmp_path files. No real project memory is read.
"""

import pytest

from claude_sessions import conventions

RULE = 'always run the linter before committing anything'
OTHER = 'prefer ripgrep over grep for searching code'
THIRD = 'never edit generated files by hand'


@pytest.fixture(autouse=True)
def thresholds(monkeypatch):
    monkeypatch.setattr(conventions, 'MIN_PROJECTS', 2)
    monkeypatch.setattr(conventions, 'MIN_PROJECTS_UNREVIEWED', 3)


def _lesson(summary, status='approved', kind='preference', conf=0.9):
    d = {'type': 'lesson', 'kind': kind, 'summary': summary, 'confidence': conf}
    if status is not None:
        d['status'] = status
    return d


def _graphs(monkeypatch, per_project):
    graphs = [(k, {'entities': ents}, '/w/' + k, '/f/' + k)
              for k, ents in per_project]
    monkeypatch.setattr(conventions, '_iter_project_graphs', lambda: list(graphs))


def _by_text(rows):
    return {r['text']: r for r in rows}


@pytest.mark.xfail(strict=True, reason="claude_sessions/conventions.py:129 max(hit[5], e.get('confidence', 0)) raises TypeError when a second cluster member carries confidence None, aborting the whole candidate list instead of counting it as 0")
def test_null_confidence_counts_as_zero_and_does_not_abort(monkeypatch):
    _graphs(monkeypatch, [
        ('p1', [_lesson(RULE, conf=0.9)]),
        ('p2', [_lesson(RULE, conf=None)]),
        ('p3', [_lesson(OTHER, conf=0.5)]),
    ])
    got = _by_text(conventions._candidates())
    assert got[RULE]['confidence'] == 0.9
    assert got[OTHER]['confidence'] == 0.5


def test_only_approved_pinned_or_pending_lessons_count(monkeypatch):
    _graphs(monkeypatch, [
        ('p1', [_lesson(RULE, status='rejected'), _lesson(RULE, status='')]),
        ('p2', [_lesson(RULE, status=None)]),
        ('p3', [_lesson(RULE, status='draft')]),
    ])
    assert conventions._candidates() == []

    _graphs(monkeypatch, [('p1', [_lesson(RULE)]), ('p2', [_lesson(RULE)]),
                          ('p3', [_lesson(RULE)])])
    assert len(conventions._candidates()) == 1


def test_kinds_outside_the_convention_set_are_excluded(monkeypatch):
    _graphs(monkeypatch, [('p1', [_lesson(RULE, kind='error_fix')]),
                          ('p2', [_lesson(RULE, kind='error_fix')]),
                          ('p3', [_lesson(RULE, kind='error_fix')])])
    assert conventions._candidates() == []

    _graphs(monkeypatch, [('p1', [_lesson(RULE, kind='decision')]),
                          ('p2', [_lesson(RULE, kind='correction')]),
                          ('p3', [_lesson(RULE, kind='preference')])])
    assert len(conventions._candidates()) == 1


def test_an_unreadable_or_entityless_graph_file_is_none(tmp_path):
    bad = tmp_path / 'bad.json'
    bad.write_text('not json{', encoding='utf-8')
    listy = tmp_path / 'list.json'
    listy.write_text('[1, 2]', encoding='utf-8')
    noents = tmp_path / 'noents.json'
    noents.write_text('{"x": 1}', encoding='utf-8')
    assert conventions._load_graph(str(bad)) is None
    assert conventions._load_graph(str(listy)) is None
    assert conventions._load_graph(str(noents)) is None
    assert conventions._load_graph(str(tmp_path / 'missing.json')) is None


def test_empty_or_whitespace_summaries_are_skipped(monkeypatch):
    _graphs(monkeypatch, [
        ('p1', [_lesson(''), _lesson('   ')]),
        ('p2', [_lesson('   ')]),
        ('p3', [{'type': 'lesson', 'kind': 'preference', 'status': 'approved',
                 'confidence': 0.9}]),
    ])
    assert conventions._candidates() == []


def test_one_project_counts_once_however_many_copies_it_holds(monkeypatch):
    _graphs(monkeypatch, [
        ('p1', [_lesson(RULE, status='pending'), _lesson(RULE, status='pending')]),
        ('p2', [_lesson(RULE, status='pending')]),
    ])
    row = _by_text(conventions._candidates())[RULE]
    assert row['projects'] == 2
    assert row['promoted'] is False


def test_one_pinned_copy_pins_the_rule_and_reviewed_folds_across_projects(monkeypatch):
    _graphs(monkeypatch, [
        ('p1', [_lesson(RULE, status='pinned'), _lesson(RULE, status='pending')]),
        ('p2', [_lesson(OTHER, status='pending')]),
        ('p3', [_lesson(OTHER, status='approved')]),
    ])
    got = _by_text(conventions._candidates())
    assert got[RULE]['pinned'] is True and got[RULE]['promoted'] is True
    assert got[RULE]['projects'] == 1
    assert got[OTHER]['reviewed'] is True and got[OTHER]['pinned'] is False
    assert got[OTHER]['projects'] == 2 and got[OTHER]['promoted'] is True


def test_promotion_thresholds_are_inclusive_and_one_short_stays_out(monkeypatch):
    texts = {'rev1': 'use tabs for indentation in makefiles',
             'rev2': 'wrap shell paths in double quotes always',
             'unr2': 'keep changelog entries in plain english',
             'unr3': 'name test files after the module under test',
             'pin1': 'write commit subjects in the imperative mood'}
    _graphs(monkeypatch, [
        ('p1', [_lesson(texts['rev1'], status='approved'),
                _lesson(texts['rev2'], status='approved'),
                _lesson(texts['unr2'], status='pending'),
                _lesson(texts['unr3'], status='pending'),
                _lesson(texts['pin1'], status='pinned')]),
        ('p2', [_lesson(texts['rev2'], status='approved'),
                _lesson(texts['unr2'], status='pending'),
                _lesson(texts['unr3'], status='pending')]),
        ('p3', [_lesson(texts['unr3'], status='pending')]),
    ])
    got = _by_text(conventions._candidates())
    assert got[texts['rev1']]['promoted'] is False
    assert got[texts['rev2']]['promoted'] is True
    assert got[texts['unr2']]['promoted'] is False
    assert got[texts['unr3']]['promoted'] is True
    assert got[texts['pin1']]['promoted'] is True


def test_confidence_keeps_the_maximum_across_members_in_any_order(monkeypatch):
    _graphs(monkeypatch, [
        ('p1', [_lesson(RULE, conf=0.4), _lesson(OTHER, conf=0.9)]),
        ('p2', [_lesson(RULE, conf=0.9), _lesson(OTHER, conf=0.4)]),
        ('p3', [_lesson(RULE, conf=0.7)]),
    ])
    got = _by_text(conventions._candidates())
    assert got[RULE]['confidence'] == 0.9
    assert got[OTHER]['confidence'] == 0.9


def test_score_adds_pin_bonus_and_confidence_and_sorts_descending(monkeypatch):
    _graphs(monkeypatch, [
        ('p1', [_lesson(RULE, status='pinned', conf=0.5),
                _lesson(OTHER, conf=0.9),
                _lesson(THIRD, conf=0.1)]),
        ('p2', [_lesson(RULE, status='approved', conf=0.5),
                _lesson(OTHER, conf=0.9)]),
    ])
    rows = conventions._candidates()
    assert [r['text'] for r in rows] == [RULE, OTHER, THIRD]
    scores = [r['score'] for r in rows]
    assert scores == pytest.approx([25.5, 20.9, 10.1])

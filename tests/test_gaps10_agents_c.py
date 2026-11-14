"""T-1378 · Close the test gaps in claude_sessions/agents.py category helpers (92-125: category_of, installed_categories, _slug).

Exact source slice: ``claude_sessions/agents.py`` lines 92-125 at tip ``73ad7a90``
(re-located at ``3885bc1d``). No source file is edited; no new dependency.

Ten candidate branches, ranked denial/fail-closed first, then boundaries, then
error paths. Selected probes and the source branch each test catches:

 1. agents.py:98       category missing or whitespace-only becomes NO_CATEGORY
                       (and a file that cannot be read gives NO_CATEGORY too)
 2. agents.py:98       category value with surrounding spaces is stripped
 3. agents.py:112-117  rows with '' or NO_CATEGORY are excluded from installed_categories
 4. agents.py:117      output is sorted and de-duplicated
 5. agents.py:120-122  _slug lowercases, collapses runs of other characters to one '-',
                       strips '-' from both ends
 6. agents.py:121      a name with no ASCII letters or digits gives 'agent'
 7. agents.py:121      double underscores and mixed separators collapse: 'a__b c' -> 'a-b-c'
 8. agents.py:98       a category written only in the body is ignored
 9. agents.py:112-117  rows with a None or absent category key do not raise

Not selected: probe 1 of the card (case-sensitive dedupe against the docstring at
112-115). The docstring states the outcome the user should get (the second agent
lands in the same category), not a case-insensitive dedupe, so no strict xfail is
kept; the question goes to the owner in the report.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from claude_sessions import agents


def _write(path, text):
    path.write_text(text, encoding='utf-8')
    return str(path)


def test_a_missing_or_blank_category_is_filed_under_no_category(tmp_path):
    no_key = _write(tmp_path / 'a.md', '---\nname: a\n---\nbody\n')
    blank = _write(tmp_path / 'b.md', '---\nname: b\ncategory:    \n---\nbody\n')
    assert agents.category_of(no_key) == agents.NO_CATEGORY
    assert agents.category_of(blank) == agents.NO_CATEGORY
    assert agents.category_of(str(tmp_path / 'missing.md')) == agents.NO_CATEGORY


def test_a_category_value_is_stripped(tmp_path):
    p = _write(tmp_path / 'a.md', '---\nname: a\ncategory:  Reviewers  \n---\nbody\n')
    assert agents.category_of(p) == 'Reviewers'


def test_empty_and_no_category_rows_are_not_offered(monkeypatch):
    rows = [{'category': ''}, {'category': agents.NO_CATEGORY},
            {'category': 'Reviewers'}]
    monkeypatch.setattr(agents, 'all_installed', lambda: rows)
    assert agents.installed_categories() == ['Reviewers']


def test_installed_categories_are_sorted_and_de_duplicated(monkeypatch):
    rows = [{'category': 'Zeta'}, {'category': 'Alpha'}, {'category': 'Alpha'}]
    monkeypatch.setattr(agents, 'all_installed', lambda: rows)
    assert agents.installed_categories() == ['Alpha', 'Zeta']


@pytest.mark.parametrize('raw, want', [
    ('Code Reviewer!!', 'code-reviewer'),
    ('--  Hello,  World --', 'hello-world'),
    ('already-fine-1', 'already-fine-1'),
])
def test_slug_lowercases_collapses_and_trims(raw, want):
    assert agents._slug(raw) == want


def test_a_name_with_no_ascii_letters_or_digits_becomes_agent():
    assert agents._slug('日本') == 'agent'
    assert agents._slug('!!!') == 'agent'


def test_double_underscores_and_mixed_separators_collapse():
    assert agents._slug('a__b c') == 'a-b-c'


def test_a_category_written_only_in_the_body_is_ignored(tmp_path):
    p = _write(tmp_path / 'a.md', '---\nname: a\n---\ncategory: x\n')
    assert agents.category_of(p) == agents.NO_CATEGORY


def test_rows_without_a_usable_category_do_not_raise(monkeypatch):
    rows = [{'name': 'a', 'category': None}, {'name': 'b'},
            {'name': 'c', 'category': 'Tools'}]
    monkeypatch.setattr(agents, 'all_installed', lambda: rows)
    assert agents.installed_categories() == ['Tools']

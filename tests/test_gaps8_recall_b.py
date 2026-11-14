"""T-1338: the highest-risk uncovered branches of claude_sessions/recall.py
lines 456-515 inclusive (rule front matter and memory surface estimate), at
tip 4e253ad5 of pv20-fx85g. Denial and fail-closed first, then boundaries,
then error paths.

Selected branches (source line, probe):
1. estimate_surfaces 506-519        unreadable rule file: later rules still reported
                                    (PREMISE, strict xfail at recall.py:506-519)
2. estimate_surfaces 506-519        missing rules dir: rules [], no error, nothing created
3. estimate_surfaces 508            only files starting archeus-mem- are counted
4. _rule_frontmatter 474            description without 'archeus memory:' leaves unit ''
5. _rule_frontmatter 472-473        parsing stops at the closing --- once a unit is known
6. _rule_frontmatter 470            PREMISE: paths key on line 9 of the front matter is
                                    declared by the file and read (strict xfail at recall.py:479)
7. _rule_frontmatter 477-481        inline paths value is read with quotes stripped
8. _rule_frontmatter 482-484        list item glob only when scoped and no glob yet
9. _rule_frontmatter 485-487        legacy globs key does not override a glob from paths
10. estimate_surfaces 520-522       hook_budget None unless memory_prompt_hook; then
                                    memory_budget defaults to 600
"""

import builtins
import os

import pytest

from claude_sessions import recall


@pytest.fixture
def quiet_memory(monkeypatch):
    monkeypatch.setattr(recall.memory, 'load_memory', lambda project_path, proj_folder: {})
    monkeypatch.setattr(recall.memory, 'build_digest_micro',
                        lambda mem: pytest.fail('digest built for an empty graph'))


def _rules_dir(project):
    d = os.path.join(str(project), '.claude', 'rules')
    os.makedirs(d, exist_ok=True)
    return d


def _write(directory, name, text):
    with open(os.path.join(directory, name), 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(text)


@pytest.mark.xfail(strict=True, reason="recall.py:506-519: an OSError reading one archeus-mem rule "
                   "file ends the whole loop, so every later rule is dropped from the surface estimate")
def test_an_unreadable_rule_file_does_not_drop_the_rules_after_it(quiet_memory, monkeypatch, tmp_path):
    rules = _rules_dir(tmp_path)
    _write(rules, 'archeus-mem-a.md', '---\ndescription: "archeus memory: app/a"\npaths:\n  - "a/**"\n---\n')
    _write(rules, 'archeus-mem-b.md', '---\ndescription: "archeus memory: app/b"\npaths:\n  - "b/**"\n---\n')
    real_open = builtins.open

    def fake_open(path, *args, **kwargs):
        if os.path.basename(str(path)) == 'archeus-mem-a.md':
            raise OSError(13, 'denied')
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(recall, 'open', fake_open, raising=False)
    est = recall.estimate_surfaces(str(tmp_path), None, {})
    assert [r['file'] for r in est['rules']] == ['archeus-mem-b.md']


def test_a_missing_rules_directory_reads_as_no_rules_and_creates_nothing(quiet_memory, tmp_path):
    est = recall.estimate_surfaces(str(tmp_path), None, {})
    assert est == {'digest_tokens': 0, 'hook_budget': None, 'rules': []}
    assert not os.path.exists(os.path.join(str(tmp_path), '.claude'))


def test_only_archeus_mem_files_are_counted_as_rules(quiet_memory, tmp_path):
    rules = _rules_dir(tmp_path)
    body = '---\ndescription: "archeus memory: app/x"\npaths:\n  - "x/**"\n---\n'
    _write(rules, 'archeus-mem-x.md', body)
    _write(rules, 'archeus-memo.md', body)
    _write(rules, 'archeus-mem.md', body)
    _write(rules, 'notes.md', body)
    est = recall.estimate_surfaces(str(tmp_path), None, {})
    assert [r['file'] for r in est['rules']] == ['archeus-mem-x.md']


def test_a_description_without_the_archeus_memory_prefix_leaves_the_unit_empty():
    unit, glob, scoped = recall._rule_frontmatter(
        '---\ndescription: "Other tool: app/x"\npaths:\n  - "x/**"\n---\n')
    assert (unit, glob, scoped) == ('', 'x/**', True)


def test_parsing_stops_at_the_closing_fence_once_the_unit_is_known():
    text = ('---\ndescription: "archeus memory: app/first"\n---\n'
            'description: "archeus memory: app/later"\npaths: "late/**"\n')
    assert recall._rule_frontmatter(text) == ('app/first', '', False)


@pytest.mark.xfail(strict=True, reason="recall.py:479: _rule_frontmatter reads only the first eight "
                   "lines, so a paths: key declared on line 9 of the front matter is ignored")
def test_a_paths_key_on_line_nine_of_the_front_matter_is_read():
    lines = ['---', 'description: "archeus memory: app/deep"', 'name: deep', 'model: x',
             'alpha: 1', 'beta: 2', 'gamma: 3', 'delta: 4', 'paths:', '  - "svc/**"', '---']
    unit, glob, scoped = recall._rule_frontmatter('\n'.join(lines) + '\n')
    assert unit == 'app/deep'
    assert scoped is True and glob == 'svc/**'


def test_an_inline_paths_value_is_read_without_its_quotes():
    assert recall._rule_frontmatter('---\npaths: "src/**/*.py"\n---\n') == ('', 'src/**/*.py', True)
    assert recall._rule_frontmatter('---\npaths: src/x/**\n---\n') == ('', 'src/x/**', True)


def test_a_list_item_sets_the_glob_only_after_paths_and_only_once():
    _, glob, scoped = recall._rule_frontmatter('---\npaths:\n  - "a/**"\n  - "b/**"\n---\n')
    assert (glob, scoped) == ('a/**', True)
    assert recall._rule_frontmatter('---\n- "x/**"\n---\n') == ('', '', False)


def test_a_legacy_globs_key_does_not_override_a_glob_from_paths():
    text = '---\npaths:\n  - "a/**"\nglobs: "b/**"\n---\n'
    assert recall._rule_frontmatter(text) == ('', 'a/**', True)


def test_hook_budget_needs_the_prompt_hook_and_defaults_to_600(quiet_memory, tmp_path):
    assert recall.estimate_surfaces(str(tmp_path), None, {'memory_budget': 900})['hook_budget'] is None
    assert recall.estimate_surfaces(str(tmp_path), None, {'memory_prompt_hook': False,
                                                          'memory_budget': 900})['hook_budget'] is None
    assert recall.estimate_surfaces(str(tmp_path), None, {'memory_prompt_hook': True})['hook_budget'] == 600
    assert recall.estimate_surfaces(str(tmp_path), None, {'memory_prompt_hook': True,
                                                          'memory_budget': 250})['hook_budget'] == 250

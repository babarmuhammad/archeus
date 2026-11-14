"""T-1450: CLAUDE.md-versus-memory claim checks in claude_sessions/workspace.py
(_claims, _claim_conflicts; source lines 276-337 at worktree 44aaf17f).

Candidates the card ranked as risky are covered by test_workspace.py:316-360 and
test_gaps6_claude_sessions_workspace_a/b.py. The premise on a malformed graph entity
(workspace.py:330, swallowed by _gather_live) is not a strict xfail: the graph writer
reads e.get('name') on every entity and only a hand-edited graph file can hold a
non-dict, so no caller reaches it from a value the user or the model produces.
"""

from claude_sessions import config, workspace


def _manual_and_generated(manual, generated_text):
    return (f'{manual}\n\n{config._MEMORY_START}\n{generated_text}\n'
            f'{config._MEMORY_END}\n')


def test_generated_block_disagreement_is_not_reported():
    md = _manual_and_generated('We ship 32 palettes.', 'We ship 40 skins.')
    mem = {'entities': [{'summary': 'We ship 32 palettes.'},
                        {'summary': 'We ship 7 skins.'}]}
    assert workspace._claim_conflicts(md, mem) == []


def test_ambiguous_graph_noun_is_dropped_not_accused():
    mem = {'entities': [{'summary': 'We have 32 palettes.'},
                        {'summary': 'We have 29 palettes.'}]}
    assert workspace._claim_conflicts('We ship 30 palettes.', mem) == []


def test_agreeing_numbers_report_nothing():
    mem = {'entities': [{'summary': 'We ship 29 palettes.'}]}
    assert workspace._claim_conflicts('We ship 29 palettes and 4 worlds.', mem) == []


def test_conflicts_sorted_by_noun():
    mem = {'entities': [{'summary': 'We ship 3 skins.'},
                        {'summary': 'We ship 32 palettes.'}]}
    got = workspace._claim_conflicts('We ship 7 skins. We ship 29 palettes.', mem)
    assert got == [('palettes', 29, 32), ('skins', 7, 3)]


def test_non_string_summary_values_are_ignored():
    mem = {'entities': [], 'summaries': {'a': ['99 palettes'], 'b': '32 palettes.'}}
    assert workspace._claim_conflicts('We ship 29 palettes.', mem) == [
        ('palettes', 29, 32)]


def test_no_manual_claims_returns_empty_early():
    mem = {'entities': [{'summary': 'We ship 32 palettes.'}]}
    assert workspace._claim_conflicts('We ship several palettes.', mem) == []


def test_past_tense_sentence_skipped_only_for_manual_side():
    text = 'We had 12 palettes.'
    assert workspace._claims(text, present_only=True) == {}
    assert workspace._claims(text) == {'palettes': 12}


def test_thousands_separator_is_parsed():
    assert workspace._claims('We ship 1,000 palettes.') == {'palettes': 1000}

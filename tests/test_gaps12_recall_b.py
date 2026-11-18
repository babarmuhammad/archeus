"""T-1427: claude_sessions/recall.py:70-140 episode retrieval at 026ea58e.

Selected candidates, not measured coverage.
Closest existing assertions: tests/test_recall.py:176 (same-file episode retrieved),
:183 (error outcome outranks an equal episode), :193 (no-signal prompt returns
nothing). No gap test calls _path_segments or score_episodes directly.
"""

import pytest

from claude_sessions import recall

IDX = recall.build_index({'entities': []})


def _ep(sid, summary, files=(), ended='2026-09-15T10:00:00Z', **kw):
    return dict({'session_id': sid, 'ended_at': ended, 'summary': summary,
                 'files': list(files)}, **kw)


def _ids(got):
    return [e['session_id'] for _s, e in got]


def test_error_outcome_ranks_above_equal_clean_episode():
    eps = [_ep('clean', 'wire the parser'),
           _ep('bad', 'wire the parser', outcome='error')]
    got = recall.score_episodes(eps, IDX, 'wire the parser')
    assert _ids(got) == ['bad', 'clean']
    assert got[0][0] == pytest.approx(got[1][0] * 1.15)


def test_tie_break_is_ended_at_ascending_pinned():
    eps = [_ep('late', 'wire the parser', ended='2026-09-16T00:00:00Z'),
           _ep('early', 'wire the parser', ended='2026-09-15T00:00:00Z')]
    assert _ids(recall.score_episodes(eps, IDX, 'wire the parser')) == ['early', 'late']


def test_query_below_min_signal_returns_empty(monkeypatch):
    monkeypatch.setattr(recall, 'MIN_QUERY_SIGNAL', 2)
    assert recall.score_episodes([_ep('a', 'wire the parser')], IDX, 'parser') == []


def test_query_at_min_signal_scores(monkeypatch):
    monkeypatch.setattr(recall, 'MIN_QUERY_SIGNAL', 2)
    got = recall.score_episodes([_ep('a', 'wire the parser')], IDX, 'wire parser')
    assert _ids(got) == ['a']


def test_zero_or_missing_avg_len_does_not_divide_by_zero():
    for idx in ({'idf': {}, 'avg_len': 0}, {'idf': {}}):
        got = recall.score_episodes([_ep('a', 'wire the parser')], idx, 'parser')
        assert len(got) == 1 and got[0][0] > 0


def test_episode_with_no_text_is_skipped_and_file_names_match():
    eps = [_ep('empty', '', []), _ep('file', '', ['src/Auth.py'])]
    assert _ids(recall.score_episodes(eps, IDX, 'auth')) == ['file']


def test_path_segments_lowercase_stem_and_backslash():
    assert recall._path_segments({'source_files': ['src\\Main.PY']}) == \
        {'src', 'main.py', 'main'}


def test_module_split_is_slash_only():
    assert recall._path_segments({'module': 'pkg/Sub'}) == {'pkg', 'sub'}
    assert recall._path_segments({'module': 'pkg\\Sub'}) == {'pkg\\sub'}


def test_no_shared_term_returns_nothing():
    assert recall.score_episodes([_ep('a', 'wire the parser')], IDX, 'kubernetes') == []


def test_top_k_zero_and_oversize():
    eps = [_ep(f's{i}', 'wire the parser') for i in range(3)]
    assert recall.score_episodes(eps, IDX, 'parser', top_k=0) == []
    assert len(recall.score_episodes(eps, IDX, 'parser', top_k=10)) == 3


def test_no_entries_returns_empty_before_tokenising(monkeypatch):
    def boom(_s):
        raise AssertionError('tokenised with no episodes')

    monkeypatch.setattr(recall, '_tokenize', boom)
    assert recall.score_episodes([], IDX, 'anything at all') == []

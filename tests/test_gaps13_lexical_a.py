"""T-1451: tokenisation, query terms, IDF and BM25 in claude_sessions/lexical.py
(source lines 1-85 at worktree 44aaf17f). Pure functions, no seams.

Left out: the Lucene IDF ordering for a term in every document is pinned by
tests/v1/unit/test_gaps_infra_search_bm25.py (it calls this module's idf).
"""

import math

import pytest

from claude_sessions import lexical


def test_idf_clamps_zero_documents():
    assert lexical.idf({'x': 1}, 0) == lexical.idf({'x': 1}, 1)


def test_df_above_n_is_finite_boundary():
    """Boundary, not a defect: no real caller reaches it (recall counts each valid
    entity once), and the Lucene argument stays positive whatever df is."""
    weight = lexical.idf({'x': 5}, 2)['x']
    assert math.isfinite(weight)


def test_bm25_floor_applies_to_unknown_term():
    score = lexical.bm25({'zeta'}, {'zeta'}, {}, 0.5, 3, 3)
    assert score == pytest.approx(0.5)


def test_bm25_zero_average_length_is_safe():
    zero = lexical.bm25({'a'}, {'a'}, {'a': 1.0}, 0.0, 4, 0)
    none = lexical.bm25({'a'}, {'a'}, {'a': 1.0}, 0.0, 4, None)
    unit = lexical.bm25({'a'}, {'a'}, {'a': 1.0}, 0.0, 4, 1.0)
    assert zero == none == unit
    assert math.isfinite(zero)


def test_bm25_no_overlap_is_zero():
    assert lexical.bm25({'a'}, {'b'}, {'a': 1.0, 'b': 1.0}, 0.1, 2, 2) == 0.0


def test_longer_entity_scores_lower_for_same_match():
    short = lexical.bm25({'a'}, {'a'}, {'a': 2.0}, 0.0, 2, 4)
    long = lexical.bm25({'a'}, {'a'}, {'a': 2.0}, 0.0, 8, 4)
    assert long < short


def test_tokenize_camel_and_snake_documented_example():
    assert lexical.tokenize('UserPromptHook') == {
        'userprompthook', 'user', 'prompt', 'hook'}
    assert lexical.tokenize('user_prompt_hook') == {'user', 'prompt', 'hook'}


def test_tokenize_non_ascii_is_split_not_dropped_consistently():
    """Boundary: [a-z0-9] drops the accented letter, so 'café' becomes 'caf'. The
    query and the document pass through the same function, so they still match."""
    assert lexical.tokenize('café') == {'caf'}
    assert lexical.query_tokens('Café') == lexical.query_tokens('café') == {'caf'}


def test_query_tokens_drops_stopwords_and_singles():
    assert lexical.query_tokens('a the cat') == {'cat'}
    assert lexical.query_tokens('thing two cat') == {'cat'}
    assert lexical.query_tokens('x cat') == {'cat'}


def test_tokens_estimate_of_empty_string_is_one():
    assert lexical.tokens_estimate('') == 1

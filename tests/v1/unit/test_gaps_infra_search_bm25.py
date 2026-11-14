"""T-771: the highest-risk uncovered branches of archeus/infra/search/bm25.py.

`normalised()` is the only retrieval gate the context engine has (assemble.py:365
is its single caller in the product), and until now the suite only exercised it
from above, through `select()` in test_context_units.py. Nothing pinned the
paths that decide *whether anything is retrieved at all*: the empty query, the
stop-word-only query, the single-character query word, the untokenisable query,
the empty candidate set, the document with no tokenisable text, the
"nothing matched" division, the per-document (presence-only) document
frequency, the length normalisation of a very long document and the
duplicate-document tie.

Pure functions over strings and numbers only — no database, no model, no
process, no network, no file, no clock, no OS call to fake, and nothing here
that differs between Linux and Windows (the tokeniser is ASCII-only on
purpose, and no assertion reads a path, an environment value or an OS error).
Style and fixtures follow test_context_units.py, the existing test of this
module.
"""

import time

import pytest

from archeus.infra.search import bm25

CORPUS = {'a': 'alpha beta', 'b': 'beta gamma', 'c': 'gamma delta'}


def scores(res):
    return {k: v[0] for k, v in res.items()}


def matched(res):
    return {k: v[1] for k, v in res.items()}


# ── 1. fail-closed: a query with nothing to retrieve on must retrieve nothing ──

@pytest.mark.parametrize('query', [None, '', '   ', '\n\t ', '?!.,'],
                         ids=['none', 'empty', 'spaces', 'newline', 'punctuation'])
def test_an_empty_or_missing_query_retrieves_nothing(query):
    """`query or ''` (bm25.py:17) and `if not s: return set()` (lexical.py:26):
    a missing/blank query is all-zero with no matched words, not a crash and not
    a score. Replace `query or ''` with `query` and drop the tokeniser's guard
    and the None case raises AttributeError here."""
    res = bm25.normalised(query, CORPUS)
    assert scores(res) == {'a': 0.0, 'b': 0.0, 'c': 0.0}
    assert matched(res) == {'a': [], 'b': [], 'c': []}


def test_a_stop_word_only_query_scores_zero_on_documents_full_of_it():
    """The `{t for t in tokenize(q) if t not in STOPWORDS}` half of lexical.py:52.
    The idf docstring records the live bug this stops ("idf('the') measured 2.08
    on the live graph and the query 'the' alone returned 33 entities"): with the
    stop-word filter removed this query — five words, every one of them in
    STOPWORDS and every one of them appearing somewhere in this corpus — is
    verified to score 0.44 / 0.26 / 1.0 instead of 0.0 / 0.0 / 0.0."""
    docs = {'a': 'the quick brown fox is what it is',
            'b': 'the lazy dog was what it was',
            'c': 'the report of the thing is really about things'}
    res = bm25.normalised('the is what of things', docs)
    assert scores(res) == {'a': 0.0, 'b': 0.0, 'c': 0.0}
    assert matched(res) == {'a': [], 'b': [], 'c': []}


def test_single_character_query_words_are_dropped_but_the_real_one_ranks():
    """The `len(t) > 1` half of lexical.py:52. 'x', 'q' and '9' are not stop
    words, so removing the length filter lets them reach bm25() and share the
    normalisation; the pin is that only 'catalyst' is ever matched from this
    query and that its document alone is worth 1.0."""
    res = bm25.normalised('x q 9 catalyst', {'a': 'catalyst x q 9', 'b': 'x q 9'})
    assert matched(res) == {'a': ['catalyst'], 'b': []}
    assert scores(res)['a'] == 1.0 and scores(res)['b'] == 0.0


def test_a_query_in_text_the_tokeniser_cannot_read_retrieves_nothing():
    """`_WORD = re.compile(r'[a-z0-9]+')` (lexical.py:19) keeps the tokeniser
    ASCII: a CJK query and CJK-only documents are untokenisable and must be
    fail-closed (zero, no matched words, no exception, no partial-fuzzy match).
    Widen `_WORD` to \\w with UNICODE and this stops returning all-zero."""
    res = bm25.normalised('日本語 テスト', {'a': '日本語 テスト', 'b': 'テスト only'})
    assert scores(res) == {'a': 0.0, 'b': 0.0}
    assert matched(res) == {'a': [], 'b': []}


def test_a_document_with_no_tokenisable_text_stays_zero_and_keeps_its_key():
    """`if not s: return set()` (lexical.py:26) on the path the product actually
    walks — assemble.py:365 hands over `c['text']`, which can be None — plus the
    `max(1, len(words))` clamp (bm25.py:24) that keeps an empty token set from
    becoming a zero document length. None must not raise, a punctuation-only
    document must not divide by zero, and every key must still come back for
    `lex[i]` at assemble.py:367."""
    docs = {'none': None, 'empty': '', 'punct': '!!! ??? ...', 'real': 'alpha'}
    res = bm25.normalised('alpha', docs)
    assert set(res) == set(docs)
    assert scores(res) == {'none': 0.0, 'empty': 0.0, 'punct': 0.0, 'real': 1.0}
    assert matched(res) == {'none': [], 'empty': [], 'punct': [], 'real': ['alpha']}


# ── 2. the empty candidate set: the two guards that keep the division alive ──

def test_an_empty_candidate_set_returns_an_empty_result_without_dividing():
    """`sum(lens.values()) / len(lens) if lens else 1.0` (bm25.py:25) and
    `max(raw.values(), default=0.0)` (bm25.py:27). Drop the `else 1.0` and this
    is a ZeroDivisionError; drop `default=0.0` and it is a ValueError on the
    empty max — neither is reachable from `select()`, which always has a
    candidate, which is exactly why no existing test covers it."""
    assert bm25.normalised('alpha beta', {}) == {}


def test_every_key_of_the_candidate_set_comes_back_even_at_zero_score():
    """The comprehension `for k in toks` (bm25.py:28) must return one entry per
    input key, zero-scored ones included: assemble.py:367 reads `lex[i]` by
    position for every candidate, so dropping a zero-scoring key is a KeyError
    in the context engine. Filter the result (e.g. `if raw[k] > 0`) and this
    fails while every ranking test still passes."""
    docs = {'hit': 'alpha beta', 'miss': 'zzz', 'blank': '', 'none': None}
    res = bm25.normalised('alpha beta', docs)
    assert list(res) == list(docs)
    for k in docs:
        assert isinstance(res[k][0], float) and isinstance(res[k][1], list)


# ── 3. boundaries of the 0..1 contract ──

def test_the_best_document_is_exactly_one_even_when_it_is_not_the_first_key():
    """`top = max(raw.values())` (bm25.py:27) over the whole set. Take the first
    key's raw score instead of the maximum (`top = raw[next(iter(raw))]`, a
    plausible "same thing" edit on an insertion-ordered dict) and 'a' would be
    1.0 while the better document 'b' scores below it."""
    res = bm25.normalised('alpha beta', {'a': 'alpha', 'b': 'alpha beta', 'c': 'zzz'})
    assert scores(res) == {'a': pytest.approx(0.43467293078718205),
                           'b': 1.0, 'c': 0.0}


def test_scores_stay_inside_the_documented_range_on_a_mixed_corpus():
    """The docstring's "`score` is BM25 divided by the best document's, so 0..1"
    (bm25.py:14) over the corpus that stresses every branch at once: a zero
    document, a None document, a ubiquitous word, a long document and a tie.
    Asserts the range, the finiteness, the sortedness of `matched` and the exact
    1.0 maximum, so a dropped division, a scored-over-the-query term loop
    (lexical.py:82) or a zero-scoring document dropped from the result all land
    here (all three verified to break this test)."""
    query = 'common needle w1'
    docs = {'ubiq': 'common needle', 'all': 'common w1 w2', 'long': 'needle '
            + ' '.join('w%d' % i for i in range(400)), 'none': None, 'punct': '!!!'}
    res = bm25.normalised(query, docs)
    assert set(res) == set(docs)
    for k, (score, words) in res.items():
        assert score == score and -1e-12 <= score <= 1.0, k        # finite, in range
        assert words == sorted(words) and set(words) <= bm25.lexical.query_tokens(query)
    assert max(v[0] for v in res.values()) == 1.0
    assert res['none'] == (0.0, []) and res['punct'] == (0.0, [])


def test_the_matched_words_are_lowercase_deduplicated_and_sorted():
    """`sorted(q & toks[k])` (bm25.py:28) — the shape `select()` prints into the
    candidate's `reason` at assemble.py:376. Drop `sorted` and a set comes back;
    drop the case folding — `_WORD.findall(s.lower())` at lexical.py:28 *and* the
    camel-split's `part.lower()` at lexical.py:30, since either one alone still
    folds 'ALPHA' to 'alpha' — and this query stops retrieving the document's
    own word."""
    res = bm25.normalised('Zeta ALPHA zeta alpha alpha', {'a': 'ALPHA zeta other'})
    assert res['a'] == (1.0, ['alpha', 'zeta'])


# ── 4. duplicate input ──

def test_duplicate_documents_tie_exactly_at_one():
    """Identical texts under different keys must be identical in every field:
    `df` (bm25.py:19-22) counts a word once per document, so the three copies
    are equally common and equally normalised. A tokeniser that returns a list
    instead of a set (lexical.py:28) gives the copies different document lengths
    and splits the tie, and dropping `sorted` at bm25.py:28 returns a set in
    `matched` — both verified to break this test."""
    docs = {'x': 'alpha beta gamma', 'y': 'alpha beta gamma', 'z': 'alpha beta gamma',
            'weak': 'alpha'}
    res = bm25.normalised('alpha beta gamma', docs)
    assert scores(res)['x'] == scores(res)['y'] == scores(res)['z'] == 1.0
    assert matched(res)['x'] == matched(res)['y'] == matched(res)['z'] == \
        ['alpha', 'beta', 'gamma']
    assert scores(res)['weak'] < 1.0


def test_a_word_repeated_in_a_document_changes_nothing_at_all():
    """Presence-only scoring: `tokenize` returns a *set*, so `df` (bm25.py:20-22)
    is a document frequency and `for t in qtok & etok` (lexical.py:82) is a term
    presence, never a term count. The two corpora differ only in repetition, so
    the results must be bit-identical. Verified to die on both realistic edits:
    counting df from the raw text (bm25.py:19-22) and making `tokenize` return a
    list instead of a set (lexical.py:28, term frequency)."""
    once = {'a': 'alpha beta', 'b': 'beta gamma'}
    twice = {'a': 'alpha alpha beta beta', 'b': 'beta gamma gamma'}
    assert bm25.normalised('alpha beta', once) == bm25.normalised('alpha beta', twice)


def test_a_spam_document_of_one_repeated_word_ties_the_real_short_one():
    """The documented consequence of presence-only scoring at its most visible
    boundary: 40 000 repetitions of one filler word are the same token set as
    one occurrence, so the spam document and the honest two-word document are
    worth exactly the same. Pinning it here means a term-frequency scorer has to
    change this test on purpose (lexical.py:74-75: "a term occurs once or not at
    all"); verified to die when `tokenize` returns a list, and when bm25() scores
    over `qtok` or `etok` instead of their intersection."""
    spam = 'needle ' + ' '.join(['filler'] * 40000)
    res = bm25.normalised('needle', {'spam': spam, 'real': 'needle filler', 'other': 'pin'})
    assert res['spam'] == res['real'] == (1.0, ['needle'])
    assert res['other'] == (0.0, [])


# ── 5. very long input ──

def test_a_very_long_document_ranks_below_a_short_one_with_the_same_words():
    """The length normalisation `BM25_B * (elen / avg_len)` (lexical.py:80)
    reached through `avg` (bm25.py:25). A 60 000-word document and a
    two-word document containing the same query word must not tie: setting
    `BM25_B = 0.0`, or replacing the length term by a constant, makes them both
    1.0 and is verified to break this test."""
    long_doc = 'needle ' + ' '.join('w%d' % i for i in range(60000))
    res = bm25.normalised('needle', {'long': long_doc, 'short': 'needle w0'})
    assert res['short'][0] == 1.0 and res['long'] == (pytest.approx(0.4193823092518133),
                                                      ['needle'])
    assert 0.0 < res['long'][0] < res['short'][0]


def test_the_document_length_average_counts_an_empty_document_as_one_word():
    """`lens = {k: max(1, len(words))}` (bm25.py:24) feeds `avg` (bm25.py:25),
    which feeds the length term of every *other* document. The clamp is not
    decorative: with it 'b' is 0.43467 of 'c' (avg 4/3); drop `max(1, ...)` and
    the token-less document drags the average to 1.0 and 'b' becomes 0.45648 —
    verified by mutating that one expression, which kills this test and no
    other. A pin that only needed "no crash" would pass either way."""
    res = bm25.normalised('alpha beta', {'a': '!!!', 'b': 'alpha', 'c': 'alpha beta'})
    assert scores(res) == {'a': 0.0, 'b': pytest.approx(0.43467293078718205), 'c': 1.0}


def test_a_very_long_query_scores_only_the_words_it_actually_matches():
    """A 2 002-word query in which 2 000 words match nothing at all:
    `for t in qtok & etok` (lexical.py:82) is what keeps those 2 000 words out of
    every score. Score over `qtok` instead of the intersection — or over `etok`,
    the other half of that edit — and the mass of unmatched query words lifts the
    empty document off zero and the ordering below collapses."""
    query = ' '.join('fillerword%d' % i for i in range(2000)) + ' needleterm'
    docs = {'hit': 'needleterm fillerword3',
            'noise': 'fillerword7 other words here',
            'blank': ''}
    res = bm25.normalised(query, docs)
    assert res['hit'] == (1.0, ['fillerword3', 'needleterm'])
    assert res['noise'][1] == ['fillerword7'] and 0.0 < res['noise'][0] < 1.0
    assert res['blank'] == (0.0, [])


def test_a_large_candidate_set_comes_back_complete_with_one_clear_winner():
    """400 documents × a 2 000-word query, of which one word is in exactly one
    document: every key must come back (the `for k in toks` at bm25.py:28 —
    verified to die when zero-scoring documents are filtered out, which is a
    KeyError at assemble.py:367) and exactly one document may be worth 1.0
    (verified to die when `top` takes the first raw score instead of the
    maximum, and when bm25() scores over the query or the document instead of
    their intersection). The wall-clock line is a coarse hang guard, not a
    complexity assertion: the measured cost of this call is 0.002 s."""
    docs = {str(i): 'term%d filler word pad' % i for i in range(400)}
    query = 'term17 ' + ' '.join('qword%d' % i for i in range(2000))
    started = time.perf_counter()
    res = bm25.normalised(query, docs)
    assert time.perf_counter() - started < 60.0
    assert set(res) == set(docs)
    assert [k for k, v in res.items() if v[0] == 1.0] == ['17']
    assert all(0.0 <= v[0] <= 1.0 for v in res.values())


# ── 6. error paths ──

@pytest.mark.parametrize('query, docs', [
    (5, {'a': 'alpha'}),
    (['alpha'], {'a': 'alpha'}),
    ('alpha', {'a': 5}),
    ('alpha', {'a': b'alpha'}),
], ids=['int-query', 'list-query', 'int-text', 'bytes-text'])
def test_a_non_string_input_fails_loudly_rather_than_scoring_nothing(query, docs):
    """The interface is `{key: text}` and `str` (bm25.py:11-18): a non-string is
    a programming error and must raise, not be coerced. `str()` coercion at the
    top of `normalised()` — the tempting "make it robust" edit — turns a bytes
    document into the word 'b'alpha'' and a None into 'None', both of which
    score; that is the silent-retrieval bug this catches."""
    with pytest.raises((TypeError, AttributeError)):
        bm25.normalised(query, docs)


def test_a_word_present_in_every_document_weighs_far_less_than_a_rare_one():
    """The Lucene idf is kept on purpose (owner, 14 Nov 2026): a word in every
    document still has a positive weight, so a small store keeps recalling,
    but it counts for much less than a word only one document holds."""
    weights = bm25.lexical.idf({'common': 5, 'rare': 1}, 5)
    assert 0 < weights['common'] < weights['rare'] / 5

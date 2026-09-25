"""Lexical retrieval primitives: tokenisation, stopwords, BM25 and its IDF.

Pure functions over strings and numbers, standard library only. They live here
rather than in `recall` because recall imports `memory` (the headless model
call) at module level, and V1's context engine reuses this scorer behind
`archeus/infra/search/bm25.py` without being allowed to reach a model — the
same seam the P0.5 `llmcall` extraction drew. `recall` imports every name back,
so its behaviour is unchanged.
"""

import math
import re


def tokens_estimate(text):
    return max(1, len(text or '') // 4)


_WORD = re.compile(r'[a-z0-9]+')
_CAMEL = re.compile(r'(?<=[a-z0-9])(?=[A-Z])')


def tokenize(s):
    """Word set incl. camelCase/snake_case splits: 'UserPromptHook' →
    {userprompthook, user, prompt, hook}."""
    if not s:
        return set()
    out = set(_WORD.findall(s.lower()))
    for part in _CAMEL.sub(' ', s).replace('_', ' ').split():
        out.update(_WORD.findall(part.lower()))
    return out


#: Words that carry no retrieval signal. The IDF below already pushes a
#: ubiquitous term to zero, but a stoplist is what stops a two-word prompt made
#: entirely of them from scoring at all — and English stopwords are not
#: project-specific, so nothing is lost by naming them.
STOPWORDS = frozenset("""
a an the this that these those and or but not is are was were be been being am
do does did doing have has had having will would shall should can could may
might must of in on at to from by for with about into over after before under
above then than so if it its it's as at i me my we our you your he she they them
what which who whom how why when where all any both each few more most other
some such only own same too very just now here there
one two three thing things way ways get gets got let lets please ok okay yes
sure thanks again really actually simply basically stuff something anything
""".split())


def query_tokens(query):
    """Tokens worth retrieving on — content words only."""
    return {t for t in tokenize(query) if t not in STOPWORDS and len(t) > 1}


def idf(df, n):
    """Proper BM25 IDF for document frequencies *df* over *n* documents.

    The old `log(1 + n/df)` never reaches zero — it is >= log(2) ~ 0.69 even for
    a token present in EVERY document — and the only gate downstream was
    `score > 0`, so `idf('the')` measured 2.08 on the live graph and the query
    "the" alone returned 33 entities. This form goes negative for a term more
    than half the corpus contains, which is what makes "does this word
    distinguish anything" answerable at all."""
    n = max(1, n)
    return {tok: math.log(1 + (n - c + 0.5) / (c + 0.5)) for tok, c in df.items()}


#: BM25 term-saturation and length-normalisation constants (the standard pair).
BM25_K1 = 1.2
BM25_B = 0.75


def bm25(qtok, etok, idf, floor, elen, avg_len):
    """Sum of BM25 term scores. Presence-only (no term frequency): an entity is
    a name plus one sentence, so a term occurs once or not at all.

    `floor` keeps a common-but-meaningful term contributing a little rather than
    nothing — it ranks below a rare term without vanishing."""
    total = 0.0
    denom_len = BM25_K1 * (1 - BM25_B + BM25_B * (elen / (avg_len or 1.0)))
    for t in qtok & etok:
        w = max(idf.get(t, 0.0), floor)
        total += w * (BM25_K1 + 1) / (1.0 + denom_len)
    return total

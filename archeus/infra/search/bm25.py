"""Lexical relevance over a candidate set (context-and-knowledge §2.2; ADR-0012).

The scorer is the legacy one in `claude_sessions/lexical.py` — tokeniser,
stopwords, BM25 and its IDF — reused, never copied. `infra/search` is the
interface that keeps retrieval swappable; FTS5 and embeddings are not V1's.
"""

from claude_sessions import lexical


def normalised(query, docs):
    """{key: (score, matched)} for *docs* ({key: text}) against *query*.

    `score` is BM25 divided by the best document's, so 0..1 within this set;
    `matched` is the sorted query words the document contains. Every score is 0
    when the query has no content word or nothing matches."""
    q = lexical.query_tokens(query or '')
    toks = {k: lexical.tokenize(text) for k, text in docs.items()}
    df = {}
    for words in toks.values():
        for w in words:
            df[w] = df.get(w, 0) + 1
    idf = lexical.idf(df, len(toks))
    lens = {k: max(1, len(words)) for k, words in toks.items()}
    avg = sum(lens.values()) / len(lens) if lens else 1.0
    raw = {k: lexical.bm25(q, toks[k], idf, 0.0, lens[k], avg) for k in toks}
    top = max(raw.values(), default=0.0)
    return {k: (raw[k] / top if top > 0 else 0.0, sorted(q & toks[k])) for k in toks}

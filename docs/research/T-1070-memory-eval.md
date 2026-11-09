# T-1070 · Memory eval harness: what it measures, what it does not

Harness: `tests/v1/unit/test_memory_eval.py` over
`tests/v1/fixtures/memory_eval/cases.json`. Fake data only.

## What is measured
metric = "retrieval recall@k over CONFIRMED knowledge, lexical BM25 scorer".
It is a retrieval metric, NOT end-to-end question answering: no model reads
the retrieved items and answers anything. The ranker is the real context
engine (`A.gather` + `A.select`, scored by `archeus/infra/search/bm25.py`).

## What is NOT measured
End-to-end answers (no model reads the retrieved items), a real model or any
call path of the knowledge pass itself (tests/v1/integration/test_knowledge.py
covers that path), embeddings, ingest cost, a corpus of real conversations,
anything about LongMemEval or LoCoMo, and no competitor number is quoted.
The 2026-11-09 research reports that some published memory figures are
retrieval scores published under other names [?]; nothing here repeats them.

## Why k is part of the result
Recall without k is not reproducible: k is the number of top-ranked retrieved
items that count as returned. Every case states its own k in cases.json (all
k = 3 in this card) and the printed table header prints it.

## The cases
| id | kind | what it proves |
| --- | --- | --- |
| recall-single | recall | a distinctive-word query returns its one CONFIRMED item; a CANDIDATE on the same words is never returned |
| recall-two-gold | recall | two relevant CONFIRMED items both sit in the top-3 |
| recall-stopword-miss | recall | gold shares only a stop-word with the query: the lexical scorer must miss; the miss is the labelled expectation, not a failure |
| supersede-pair | supersede | K.supersede: B is returned, A is SUPERSEDED, still in the table, excluded with freshness 'superseded' |
| supersede-chain | supersede | a chain A -> B -> C: only C is returned; A and B are excluded, nothing deleted |
| contradiction-recorded | contradiction | K.record_knowledge_pass: E stays CONFIRMED and is returned, F stays CANDIDATE and is never returned, the `contradicts` relation F -> E exists once |
| contradiction-unshown | contradiction | a `contradicts` towards an id outside known_items writes no relation and reports dropped >= 1 |
| verbatim-ranked | verbatim | the legacy lexical scorer (bm25.normalised) ranks the gold raw snippet in the top-3 when words are shared |
| verbatim-paraphrase-miss | verbatim | the same scorer cannot rank a paraphrase with no shared content word into the top-3 |

## Known limits
The lexical scorer misses paraphrase: the two `expect_miss` cases label that
limit instead of hiding it. A CANDIDATE is invisible to retrieval by design
(assemble.py `_knowledge` excludes it as "not confirmed (a candidate)").

## Verbatim fallback finding
The legacy lexical scorer serves a query that shares a content word with the
snippet, and cannot serve a paraphrase that shares none: that is what the two
verbatim cases record.

No headline number is claimed.

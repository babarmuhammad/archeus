"""Retrieval quality, measured — not asserted about.

Scoring changes are the kind that look fine in review and quietly get worse:
every individual weight is defensible, and the only way to know whether the
ranking improved is to run queries whose right answer you already know.

The practice this follows (Zep's memory-testing guidance, and the 2026 critique
of LoCoMo/LongMemEval as aggregate scores) is: separate RETRIEVAL COMPLETENESS
from answer quality, break the result down PER CATEGORY, and pin the harness —
an aggregate that moves two points tells you nothing, while a category that
drops tells you which signal broke.

Deliberately model-free and deterministic: a fixed graph in, a fixed ranking
out. It runs in milliseconds and can gate CI, which an LLM-judged suite cannot.

The ceiling is recorded here on purpose: this is LEXICAL retrieval. A query
sharing no vocabulary with the stored summary will miss, and no amount of
weight tuning changes that — it would take embeddings, which this project
deliberately does not have.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from claude_sessions import recall


def _ent(name, summary, module='app/core', files=(), **kw):
    e = {'name': name, 'type': 'component', 'summary': summary,
         'repo': 'app', 'module': module, 'valid': True, 'rank': 0, 'hits': 0,
         'source_files': list(files) or [f'{module}/{name.lower()}.py']}
    e.update(kw)
    return e


def _lesson(name, summary, confidence=0.9, status='approved'):
    return {'name': name, 'type': 'lesson', 'kind': 'error_fix', 'summary': summary,
            'status': status, 'confidence': confidence, 'valid': True,
            'repo': '', 'module': '(project)', 'source_files': [], 'rank': 0}


#: A small graph with a KNOWN right answer for each query below.
GRAPH = {
    'entities': [
        _ent('TokenBucket', 'Rate limits outgoing requests per account.',
             module='app/limits', rank=40),
        _ent('SessionStore', 'Persists conversation transcripts to disk.',
             module='app/store', rank=90),
        _ent('TranscriptReader', 'Streams JSONL transcripts without loading them.',
             module='app/store', rank=30),
        _ent('OAuthClient', 'Exchanges refresh tokens for access tokens.',
             module='app/auth', rank=20),
        _ent('PermissionGate', 'Decides whether a tool call may run.',
             module='app/auth', rank=60),
        _ent('ThemePalette', 'Colour values for every surface of the interface.',
             module='ui/theme', rank=5),
        _ent('MotionLoop', 'One animation frame loop shared by every gauge.',
             module='ui/theme', rank=5),
        _lesson('Retry with backoff on 429',
                'Rate limit responses need exponential backoff, not an immediate retry.'),
        _lesson('Never log refresh tokens',
                'Refresh tokens must be redacted before any log write.', confidence=1.0),
        _lesson('Unreviewed guess', 'Something nobody approved.', status='pending'),
    ],
    'relations': [
        {'source': 'SessionStore', 'target': 'TranscriptReader', 'rel': 'uses',
         'unit': 'app/store'},
    ],
    'module_edges': [],
    'summaries': {},
}

#: (category, query, must-surface names). A category, not one aggregate number:
#: "recall dropped 4%" is unactionable, "path queries stopped working" is not.
CASES = [
    ('exact-name',  'TokenBucket',                    {'TokenBucket'}),
    ('exact-name',  'PermissionGate',                 {'PermissionGate'}),
    ('descriptive', 'rate limits per account',        {'TokenBucket'}),
    ('descriptive', 'streams transcripts from disk',  {'TranscriptReader'}),
    ('descriptive', 'refresh tokens access tokens',   {'OAuthClient'}),
    ('path',        'app/store',                      {'SessionStore', 'TranscriptReader'}),
    ('path',        'ui/theme palette',               {'ThemePalette'}),
    ('lesson',      'got a 429 rate limit',           {'Retry with backoff on 429'}),
]

#: queries that must return NOTHING. The old scorer's IDF never reached zero and
#: `score > 0` was the only gate, so on the real graph "the" alone returned 33
#: entities — with the prompt hook on, that is memory injected into a prompt
#: that asked for none.
MUST_BE_EMPTY = ['the', 'it', 'and then', 'do that', 'ok', 'this one']


def _top(query, k=6):
    index = recall.build_index(GRAPH)
    return [e.get('name') for _s, e in recall.score_entities(GRAPH, index, query)[:k]]


def test_retrieval_recall_by_category():
    """Recall@6 per category, with the failures named."""
    by_cat = {}
    misses = []
    for cat, query, expect in CASES:
        got = set(_top(query))
        hit = len(expect & got)
        c = by_cat.setdefault(cat, [0, 0])
        c[0] += hit
        c[1] += len(expect)
        if hit < len(expect):
            misses.append(f'[{cat}] {query!r} missed {sorted(expect - got)} '
                          f'(got {sorted(got)[:4]})')
    report = {c: f'{h}/{t}' for c, (h, t) in by_cat.items()}
    for cat, (h, t) in by_cat.items():
        assert h == t, f'{cat} recall {h}/{t}\n  ' + '\n  '.join(misses) + f'\n{report}'


def test_a_contentless_prompt_retrieves_nothing():
    for q in MUST_BE_EMPTY:
        assert _top(q) == [], f'{q!r} injected memory into a prompt that asked for none'


def test_lessons_do_not_crowd_out_the_code_graph():
    """Every lesson got a flat +2.0 while `confidence` was never read at all, so
    a generic query returned lessons and no code."""
    got = _top('transcripts on disk')
    assert 'TranscriptReader' in got or 'SessionStore' in got, got


def test_a_pending_lesson_is_never_retrievable():
    for _cat, q, _e in CASES:
        assert 'Unreviewed guess' not in _top(q, k=20)
    assert 'Unreviewed guess' not in _top('something nobody approved', k=20)


def test_an_invalidated_fact_is_never_retrievable():
    g = dict(GRAPH, entities=list(GRAPH['entities']) + [
        _ent('OldCache', 'Superseded caching layer for transcripts.',
             module='app/store', valid=False, invalidated_at='2026-01-01')])
    index = recall.build_index(g)
    names = [e.get('name') for _s, e in recall.score_entities(g, index, 'caching layer')]
    assert 'OldCache' not in names


def test_the_budget_fits_rather_than_truncating():
    """render_context used to `break` on the first oversized line, so one long
    summary discarded every smaller item behind it."""
    long_one = _ent('Verbose', 'x ' * 400, module='app/limits')
    g = dict(GRAPH, entities=[long_one] + list(GRAPH['entities']))
    index = recall.build_index(g)
    scored = recall.score_entities(g, index, 'rate limits per account')
    text, toks = recall.render_context(scored, g, 120)
    assert 'TokenBucket' in text, 'a long top hit swallowed the whole budget'
    assert toks <= 140, toks


def test_rendering_stays_inside_its_budget():
    index = recall.build_index(GRAPH)
    for budget in (40, 80, 200, 600):
        scored = recall.score_entities(GRAPH, index, 'app/store transcripts')
        _text, toks = recall.render_context(scored, GRAPH, budget)
        assert toks <= budget * 1.2, (budget, toks)


def test_reinforcement_credits_only_what_was_injected():
    """`hits` fed the eviction score, and every prompt credited the whole
    candidate list — including entities the budget had cut."""
    index = recall.build_index(GRAPH)
    scored = recall.score_entities(GRAPH, index, 'app/store transcripts')
    text, _toks = recall.render_context(scored, GRAPH, 40)
    injected = set(recall.render_context.last_included)
    assert injected, 'nothing was rendered'
    assert len(injected) <= len(scored)
    for name in injected:
        assert name in text

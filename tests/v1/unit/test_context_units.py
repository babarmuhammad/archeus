"""P5 context engine, pure half (p5-design-gate §9, C01–C10, C16, C17):
`select()` over synthetic candidates, the relevance formula, conflicts between
checkable constraints, and the structural guards. No database, no model."""

import os
import random
import subprocess
import sys

import pytest

from archeus.core.context import assemble as A
from archeus.core.context import levels as P

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
AS_OF = '2026-09-25T12:00:00.000Z'


def cand(id_, level='L1', store='knowledge', text='x', authority='confirmed', stale=False,
         observed_at=AS_OF, kind='knowledge_item', **extra):
    return A._cand({'kind': kind, 'id': id_}, level, store, 'FACT', kind, id_, observed_at,
                   text, authority, 'because', stale=stale, **extra)


def gathered(cands, excluded=(), query='', missing=()):
    return {'query': query, 'as_of_at': AS_OF, 'candidates': list(cands),
            'excluded': list(excluded), 'missing_information': list(missing)}


def ids_of(pkg):
    return [i['ref']['id'] for i in pkg['items']]


# ── C10 the formula ──

def test_c10_relevance_is_the_weighted_formula_with_every_term_present():
    """Mutation: dropping the stale penalty's sign, or a term from WEIGHTS,
    fails here."""
    assert set(P.WEIGHTS) == {'lex', 'anchor', 'link', 'rec', 'auth', 'conf', 'stale',
                              'useless'}
    assert (P.WEIGHTS['lex'], P.WEIGHTS['auth'], P.WEIGHTS['rec'], P.WEIGHTS['stale']) == (
        1.0, 1.0, 0.5, 0.5)
    assert all(P.WEIGHTS[k] == 0 for k in ('anchor', 'link', 'conf', 'useless'))
    s = {'lex': 0.5, 'anchor': 1, 'link': 1, 'rec': 0.4, 'auth': 0.9, 'conf': 1, 'stale': 1,
         'useless': 1}
    assert P.relevance(s) == pytest.approx(0.5 + 0.9 + 0.5 * 0.4 - 0.5)
    pkg = A.select(gathered([cand('kno_a')]))
    (item,) = pkg['items']
    assert set(item['signals']) == set(P.WEIGHTS)
    assert item['relevance'] == pytest.approx(P.relevance(item['signals']))
    assert pkg['scoring']['weights'] == P.WEIGHTS


def test_c10_recency_is_linear_over_the_history_window():
    assert A._recency(AS_OF, AS_OF) == 1.0
    assert A._recency('2026-09-21T12:00:00.000Z', AS_OF) == pytest.approx(3 / 7)
    assert A._recency('2026-09-01T12:00:00.000Z', AS_OF) == 0.0
    assert A._recency(None, AS_OF) == 0.0


# ── C01, C02, C09 budgets ──

def test_c01_each_level_gets_its_share_and_unused_budget_flows_down():
    pkg = A.select(gathered([cand('kno_a', 'L0', text='a' * 400)]), limit_tokens=1000)
    b = pkg['budget']['levels']
    assert [b[lv]['limit_tokens'] for lv in P.LEVELS] == [400, 300 + 300, 150 + 600,
                                                           100 + 750, 50 + 850]
    assert b['L0']['used_tokens'] == 100
    assert pkg['budget']['used_tokens'] == 100 <= pkg['budget']['limit_tokens']


def test_c02_candidates_over_a_level_budget_are_excluded_with_the_reason():
    """Greedy by relevance: a big item that does not fit is skipped, a smaller
    one after it still gets in. Mutation: `<=` -> `<` on the fit test fails the
    exact-fit case."""
    cs = [cand('kno_first', 'L4', text='a' * 160, authority='explicit'),     # 40 tokens
          cand('kno_big', 'L4', text='b' * 280, authority='confirmed'),      # 70: no room
          cand('kno_small', 'L4', text='c' * 20, authority='inferred')]      # 5: fits
    pkg = A.select(gathered(cs), limit_tokens=100)          # L4 share 5 + carry 95
    assert pkg['budget']['levels']['L4']['limit_tokens'] == 100
    assert ids_of(pkg) == ['kno_first', 'kno_small']
    (cut,) = pkg['excluded']
    assert cut['ref']['id'] == 'kno_big' and cut['reason'] == (
        'over the L4 budget: needs 70 tokens, 60 left')
    assert pkg['budget']['used_tokens'] == 45
    exact = A.select(gathered([cand('kno_e', 'L0', text='e' * 160)]), limit_tokens=100)
    assert ids_of(exact) == ['kno_e']                        # 40 of 40


def test_c09_a_disabled_level_is_excluded_and_its_budget_flows_on():
    cs = [cand('kno_p', 'L1'), cand('kno_g', 'L4')]
    pkg = A.select(gathered(cs), levels=('L0', 'L4'), limit_tokens=1000)
    assert ids_of(pkg) == ['kno_g']
    assert [e['reason'] for e in pkg['excluded']] == ['level L1 is not in scope']
    assert pkg['levels'] == ['L0', 'L4']
    assert pkg['budget']['levels']['L1']['limit_tokens'] == 0


def test_c08_no_candidates_is_a_valid_empty_package():
    pkg = A.select(gathered([], missing=['nothing registered']))
    assert (pkg['items'], pkg['excluded'], pkg['conflicts']) == ([], [], [])
    assert pkg['budget']['used_tokens'] == 0
    assert pkg['missing_information'] == ['nothing registered']


# ── C03 provenance, C05 stale ──

def test_c03_every_item_says_what_it_is_where_it_came_from_and_why():
    pkg = A.select(gathered([cand('kno_a', text='the dashboard ships dark first')],
                            query='dark dashboard'))
    (i,) = pkg['items']
    assert i['ref'] == {'kind': 'knowledge_item', 'id': 'kno_a'}
    assert (i['level'], i['store'], i['source_kind'], i['source_ref']) == (
        'L1', 'knowledge', 'knowledge_item', 'kno_a')
    assert i['reason'].startswith('because; matches dark, dashboard')
    assert i['tokens'] >= 1 and i['observed_at'] == AS_OF


def test_c05_a_stale_item_is_labelled_and_ranked_below_its_fresh_twin():
    pkg = A.select(gathered([cand('kno_a', stale=True), cand('kno_b')]))
    fresh, stale = pkg['items']
    assert (fresh['ref']['id'], fresh['freshness']) == ('kno_b', 'current')
    assert (stale['ref']['id'], stale['freshness']) == ('kno_a', 'stale')
    assert fresh['relevance'] - stale['relevance'] == pytest.approx(P.WEIGHTS['stale'])


# ── C07 ordering ──

def test_c07_order_is_level_then_store_then_relevance_then_id_whatever_the_input_order():
    cs = [cand('kno_z', 'L1', 'history', kind='event'), cand('kno_b', 'L1'),
          cand('kno_a', 'L1'), cand('kno_s', 'L1', 'state', authority='explicit'),
          cand('kno_0', 'L0', 'knowledge'), cand('kno_x', 'L3', 'history', kind='event')]
    want = A.select(gathered(cs))
    assert ids_of(want) == ['kno_0', 'kno_s', 'kno_a', 'kno_b', 'kno_z', 'kno_x']
    rng = random.Random(5)
    for _ in range(20):
        shuffled = cs[:]
        rng.shuffle(shuffled)
        assert A.select(gathered(shuffled)) == want


# ── C06 conflicts ──

def pinned(id_, package, version, at):
    return cand(id_, constraint={'kind': 'framework_pinned',
                                 'spec': {'package': package, 'version': version}},
                created_at=at)


def layering(id_, layers, at):
    return cand(id_, constraint={'kind': 'require_layering', 'spec': {'layers': layers}},
                created_at=at)


def test_c06_two_pins_of_one_package_conflict_and_the_newer_is_preferred():
    cs = [pinned('kno_new', 'pydantic', '2.7', '2026-09-25T10:00:00.000Z'),
          pinned('kno_old', 'pydantic', '1.10', '2026-09-24T10:00:00.000Z')]
    pkg = A.select(gathered(cs))
    (c,) = pkg['conflicts']
    assert (c['items'], c['preferred'], c['kind']) == (
        ['kno_old', 'kno_new'], 'kno_new', 'framework_pinned')
    old = next(i for i in pkg['items'] if i['ref']['id'] == 'kno_old')
    assert old['conflicts_with'] == ['kno_new'] and 'which is preferred' in old['reason']
    new = next(i for i in pkg['items'] if i['ref']['id'] == 'kno_new')
    assert new['conflicts_with'] == []


def test_c06_opposite_layerings_conflict():
    cs = [layering('kno_a', ['api/**', 'core/**'], '2026-09-24T10:00:00.000Z'),
          layering('kno_b', ['core/**', 'db/**', 'api/**'], '2026-09-25T10:00:00.000Z')]
    (c,) = A.select(gathered(cs))['conflicts']
    assert c['preferred'] == 'kno_b' and 'api/** above core/**' in c['reason']


@pytest.mark.parametrize('a,b', [
    ({'kind': 'framework_pinned', 'spec': {'package': 'x', 'version': '1'}},
     {'kind': 'framework_pinned', 'spec': {'package': 'x', 'version': '1'}}),
    ({'kind': 'framework_pinned', 'spec': {'package': 'x', 'version': None}},
     {'kind': 'framework_pinned', 'spec': {'package': 'x', 'version': '2'}}),
    ({'kind': 'framework_pinned', 'spec': {'package': 'x', 'version': '1'}},
     {'kind': 'framework_pinned', 'spec': {'package': 'y', 'version': '2'}}),
    ({'kind': 'require_layering', 'spec': {'layers': ['a/**', 'b/**']}},
     {'kind': 'require_layering', 'spec': {'layers': ['a/**', 'c/**', 'b/**']}}),
    ({'kind': 'forbid_dependency', 'spec': {'from': 'a/**', 'to': 'b/**'}},
     {'kind': 'require_layering', 'spec': {'layers': ['a/**', 'b/**']}}),
    ({'kind': 'module_exists', 'spec': {'path': 'a.py'}},
     {'kind': 'forbid_dependency', 'spec': {'from': 'a.py', 'to': 'b/**'}}),
], ids=['same-pin', 'any-version', 'two-packages', 'same-order', 'two-prohibitions',
        'unrelated'])
def test_c06_constraints_that_can_both_hold_are_not_a_conflict(a, b):
    assert A._clash(a, b) is None and A._clash(b, a) is None


def test_c06_prose_is_never_compared():
    """Two prose items saying opposite things are not detected in P5: that is
    a `contradicts` relation (P6), not a similarity threshold."""
    cs = [cand('kno_a', text='use postgres', created_at='1'),
          cand('kno_b', text='do not use postgres', created_at='2')]
    assert A.select(gathered(cs))['conflicts'] == []


# ── C16, C17 structure ──

def test_c16_the_context_path_cannot_reach_a_model_a_harness_or_execution():
    """A fresh interpreter imports the context engine, the search interface,
    the lexical seam and the application layer that records a package, and
    none of these is loaded. Mutation: `from claude_sessions import recall` in
    bm25.py fails here (recall imports memory)."""
    banned = ('claude_sessions.memory', 'claude_sessions.llmcall', 'claude_sessions.recall',
              'claude_sessions.gui_api', 'claude_sessions.ui', 'claude_sessions.rotate',
              'claude_sessions.quota', 'archeus.harnesses', 'archeus.core.engine',
              'archeus.core.runtime', 'subprocess')
    code = ('import sys\n'
            'import archeus.core.context.assemble, archeus.infra.search.bm25\n'
            'import claude_sessions.lexical, archeus.core.application.commands\n'
            'print([m for m in %r if m in sys.modules])' % (banned,))
    r = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True,
                       cwd=ROOT, timeout=60)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == '[]', r.stdout


def test_c17_recall_uses_the_lexical_seam_rather_than_a_copy():
    from claude_sessions import lexical, recall
    assert recall._tokenize is lexical.tokenize and recall._bm25 is lexical.bm25
    assert recall._idf is lexical.idf and recall.STOPWORDS is lexical.STOPWORDS
    assert recall.query_tokens is lexical.query_tokens
    assert recall.tokens_estimate is lexical.tokens_estimate
    src = open(os.path.join(ROOT, 'claude_sessions', 'lexical.py'), encoding='utf-8').read()
    assert [ln for ln in src.splitlines() if ln.startswith(('import ', 'from '))] == [
        'import math', 'import re']
    for path in ('claude_sessions/recall.py', 'archeus/infra/search/bm25.py'):
        body = open(os.path.join(ROOT, path), encoding='utf-8').read()
        assert 'def _bm25' not in body and 'def bm25' not in body, path

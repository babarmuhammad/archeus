"""T-1070: the memory eval harness (metric, k and the supersede/contradiction
cases), fake data only, no model, no headline number.

WHAT THIS HARNESS MEASURES, in the words the printed table and the note use:
metric = "retrieval recall@k over CONFIRMED knowledge, lexical BM25 scorer".
It is a retrieval metric, NOT end-to-end question answering: no model reads
the retrieved items and answers anything. k is the number of top-ranked
retrieved items that count as returned; every case states its own k in
cases.json (k = 3 for every case in this card; the table prints it).

Cases live in tests/v1/fixtures/memory_eval/cases.json. The harness seeds the
real application commands (`K.supersede`, `K.record_knowledge_pass`) and reads
with the real context engine (`A.gather`, `A.select`); the ranked list is the
package's knowledge items sorted by relevance, and the top-k are the first k.
The `expect_miss` labels document the limit of the lexical scorer (a query
sharing only a stop-word with its gold item must miss): a miss on those
queries is the recorded expectation, not a failure.

No model, no FakeCaller, no harness adapter: the knowledge pass's own call
path is out of scope for this card (tests/v1/integration/test_knowledge.py
covers it); here the pass runs with its end patched at the same seam the
gaps test for this module uses. The table is printed for `-s` and never
written to a file, and no line names a headline score.

The helpers `_seed`, `_run`, `_row`, `_all`, `_project`, `_item` and `called`
are copied from tests/v1/unit/test_gaps_core_application_knowledge.py (no
test module is imported). Platform-neutral: no OS call, no process, no
network, no sleep; ASCII only; the fixture is read with encoding="utf-8".
"""

import json
import os

import pytest

from archeus.core.application import knowledge as K
from archeus.core.context import assemble as A
from archeus.core.domain import entities, ids
from archeus.core.domain.events import new_event
from archeus.core.domain.values import Ref
from archeus.infra.db import Database, rows
from archeus.infra.search import bm25

HERE = os.path.dirname(os.path.abspath(__file__))
CASES_PATH = os.path.join(HERE, os.pardir, 'fixtures', 'memory_eval', 'cases.json')
with open(CASES_PATH, encoding='utf-8') as handle:
    DOC = json.load(handle)
CASES = DOC['cases']

#: the table header, fixed wording (the note and this file's docstring agree)
HEADER = 'metric=recall@k (retrieval, lexical BM25; NOT end-to-end QA) k=3'
#: words a memory table may not print (no headline score is claimed here)
BANNED = ('average', 'mean', 'overall', 'accuracy')

#: a budget so large the level shares never cut a case (each case is tiny)
BIG_BUDGET = 100000

USER = Ref('user_device', ids.new_id('principal'))


# ── the seeds, copied from tests/v1/unit/test_gaps_core_application_knowledge ──

def _seed(db, *ents):
    """Rows the test needs already there. One transaction, and the single event
    the writer's own rule asks a mutation to carry."""
    def work(tx, ents):
        for e in ents:
            tx.insert(e, actor=USER)
        tx.append(new_event('project.created', Ref('project', ids.new_id('project')), USER,
                            payload={}, workspace=ids.GLOBAL_WORKSPACE))
    db.writer.execute(work, {'ents': list(ents)})


def _run(db, command, key=None, actor=None, **kw):
    return db.writer.execute(command, dict(kw, actor=actor or USER), idempotency_key=key)


def _row(db, cls, id_):
    with db.read() as c:
        r = rows.get(c, cls, id_)
    return None if r is None else r.entity


def _all(db, cls, **eq):
    with db.read() as c:
        return [r.entity for r in rows.where(c, cls, **eq)]


def _project(db, name='repo'):
    p = entities.Project(id=ids.new_id('project'), workspace_id=ids.GLOBAL_WORKSPACE,
                         name=name)
    _seed(db, p)
    return p.id


def _item(db, *, type_='FACT', title='untitled', state='CANDIDATE', project_id=None,
          source_kind='user', origin='explicit', supersedes_id=None, constraint=None,
          text='', anchors=(), source_ref=None, route_decision_id=None, purged=False,
          workspace_id=None):
    k = entities.KnowledgeItem(id=ids.new_id('knowledge_item'),
                               workspace_id=workspace_id or ids.GLOBAL_WORKSPACE,
                               type=type_, title=title, text=text, origin=origin,
                               state=state, project_id=project_id, source_kind=source_kind,
                               source_ref=source_ref, supersedes_id=supersedes_id,
                               constraint=constraint, anchors=anchors,
                               route_decision_id=route_decision_id, purged=purged)
    _seed(db, k)
    return k.id


def called(usage=None, rd_id=None, attempts=1):
    """The `called` dict the caller of these commands hands in (the exact shape
    of core/knowledge/passes.py `_called`)."""
    return {'route_decision_id': rd_id or ids.new_id('route_decision'),
            'context_package_id': ids.new_id('context_package'), 'attempts': attempts,
            'account_ref': 'fake:pi', 'usage': usage}


@pytest.fixture(autouse=True)
def ends(monkeypatch):
    """The end of a brain call: recorded, not executed (copied from the gaps
    test of this module). `record_knowledge_pass` ends the call through this
    seam; there is no RouteDecision row to end here."""
    seen = []
    monkeypatch.setattr(K.C, 'end_call', lambda tx, **kw: (seen.append(kw), {'state': 'ok'})[1])
    return seen


@pytest.fixture
def db(archeus_home):
    d = Database.open()
    try:
        yield d
    finally:
        d.close()


# ── the harness: seed one case, retrieve with the real engine ──────────────

def retrieve(db, pid, query):
    """The real read path: one snapshot, the pure package. The ranked list is
    the package's knowledge items sorted by relevance (id breaks ties, as the
    engine's own key does); the top-k are the first k of it. Returns the ids
    in rank order and the excluded list."""
    with db.read() as conn:
        gathered = A.gather(conn, 'project', pid)
        pkg = A.select(gathered, query=query, limit_tokens=BIG_BUDGET)
    mine = [i for i in pkg['items'] if i['ref']['kind'] == 'knowledge_item']
    mine.sort(key=lambda i: (-i['relevance'], i['ref']['id']))
    return [i['ref']['id'] for i in mine], pkg['excluded']


def verbatim_ranked(query, docs):
    """What the legacy lexical scorer (the one the verbatim fallback would use)
    returns for raw snippets: refs in rank order of `bm25.normalised`."""
    lex = bm25.normalised(query, docs)
    return sorted(lex, key=lambda r: (-lex[r][0], r))


def run_case(db, case):
    """Seed one case and hand back what the assertions need: the project, the
    ref -> id map, and (contradiction cases) the pass result. The supersede
    chains go through the REAL K.supersede (never hand-set states), starting
    from a CONFIRMED item. In a contradiction case the CANDIDATE item is the
    entity of a REAL K.record_knowledge_pass; its `supersedes` field names the
    CONFIRMED ref it contradicts, and only that item is handed to the pass as
    `known_items` (the call was shown it): a null `supersedes` still sends the
    contradicts entry but lists nothing, so the pass must drop it."""
    pid = _project(db)
    ref_id, pass_out = {}, None
    kind = case['kind']
    if kind == 'verbatim':
        return {'pid': pid, 'ref_id': {}, 'pass_out': None}
    if kind == 'contradiction':
        for it in case['items']:
            if it['state'] == 'CONFIRMED':
                ref_id[it['ref']] = _item(db, project_id=pid, title=it['title'],
                                          text=it['text'], state='CONFIRMED')
        cands = [it for it in case['items'] if it['state'] == 'CANDIDATE']
        shown = tuple(ref_id[it['supersedes']] for it in cands if it['supersedes'])
        first = next(it['ref'] for it in case['items'] if it['state'] == 'CONFIRMED')
        pass_out = _run(db, K.record_knowledge_pass, called=called(), project_id=pid,
                        workspace_id=ids.GLOBAL_WORKSPACE,
                        inspection_id=ids.new_id('repository_inspection'),
                        result={'entities': [{'name': it['title'], 'summary': it['text']}
                                             for it in cands],
                                'contradicts': [{'entity': it['title'],
                                                 'existing': ref_id[first],
                                                 'why': 'the pass reports the two texts '
                                                        'disagree'} for it in cands]},
                        known_items=shown)
        stored = {r.title: r.id for r in _all(db, entities.KnowledgeItem)}
        for it in cands:
            ref_id[it['ref']] = stored[it['title']]
    elif kind == 'supersede':
        for it in case['items']:
            if not it['supersedes']:
                ref_id[it['ref']] = _item(db, project_id=pid, title=it['title'],
                                          text=it['text'], state='CONFIRMED')
            else:
                out = _run(db, K.supersede, knowledge_item_id=ref_id[it['supersedes']],
                           title=it['title'], text=it['text'])
                ref_id[it['ref']] = out['knowledge_item']['id']
    else:
        for it in case['items']:
            ref_id[it['ref']] = _item(db, project_id=pid, title=it['title'],
                                      text=it['text'], state=it['state'])
    return {'pid': pid, 'ref_id': ref_id, 'pass_out': pass_out}


def ranked_refs(db, case, seeded, query):
    """The refs in rank order for one query, whatever the kind of case."""
    if case['kind'] == 'verbatim':
        docs = {r['ref']: r['text'] for r in case['raw']}
        return verbatim_ranked(query, docs), None
    ids_, excluded = retrieve(db, seeded['pid'], query)
    id_to_ref = {v: k for k, v in seeded['ref_id'].items()}
    assert set(ids_) <= set(id_to_ref), 'a stranger knowledge item reached the package'
    return [id_to_ref[i] for i in ids_], excluded


# ── the metric, pure ───────────────────────────────────────────────────────

def recall_at_k(returned_refs, gold, k):
    """The share of the gold refs sitting in the first k returned ones."""
    return len(set(returned_refs[:k]) & set(gold)) / len(gold)


def test_recall_at_k_is_a_pure_ratio_all_half_none():
    assert recall_at_k(['a', 'b', 'c'], ['a', 'c'], 3) == 1.0
    assert recall_at_k(['a', 'b', 'c'], ['a', 'd'], 3) == 0.5
    assert recall_at_k(['a', 'b', 'c'], ['d', 'e'], 3) == 0.0


# ── the fixture itself is checked, not only trusted ────────────────────────

def test_the_fixture_is_well_formed():
    assert DOC['metric'] == 'recall@k' and DOC['k'] == 3
    assert len(CASES) >= 9
    assert {'recall', 'supersede', 'contradiction', 'verbatim'} <= {c['kind'] for c in CASES}
    for case in CASES:
        assert case['k'] == 3, case['id']
        known = {i['ref'] for i in case['items']} | {r['ref'] for r in case.get('raw', [])}
        assert 2 <= len(known) <= 6, case['id']
        for it in case['items']:
            assert it['supersedes'] is None or it['supersedes'] in known, case['id']
        for qu in case['queries']:
            for ref in list(qu['gold']) + list(qu['absent']):
                assert ref in known, (case['id'], ref)
            assert qu['gold'], case['id']


# ── one parametrised test per case ─────────────────────────────────────────

def _params():
    return [pytest.param(c, id=c['id']) for c in CASES]


@pytest.mark.parametrize('case', _params())
def test_memory_case(db, case):
    k = case['k']
    seeded = run_case(db, case)
    for qu in case['queries']:
        returned, excluded = ranked_refs(db, case, seeded, qu['q'])
        top = returned[:k]
        for ref in qu['absent']:
            assert ref not in returned, (case['id'], qu['q'], ref)
        for ref in qu['gold']:
            if qu.get('expect_miss'):
                # the label says the lexical scorer must miss this query: the
                # gold ref must NOT be in the top-k (a documented limit, the
                # opposite of the other branches: here a hit would be the bug)
                assert ref not in top, (case['id'], qu['q'], ref)
            else:
                assert ref in top, (case['id'], qu['q'], ref)
        if case['kind'] == 'supersede':
            _assert_superseded_rows_and_exclusions(db, case, seeded, excluded)
    if case['kind'] == 'supersede':
        for it in case['items']:
            if not it['supersedes']:
                continue
            old = _row(db, entities.KnowledgeItem, seeded['ref_id'][it['supersedes']])
            # assemble.py _knowledge: a SUPERSEDED item is kept as history
            assert old is not None and old.state == 'SUPERSEDED', it['ref']
        live = [it['ref'] for it in case['items'] if not any(
            o['supersedes'] == it['ref'] for o in case['items'])]
        for ref in live:
            assert _row(db, entities.KnowledgeItem, seeded['ref_id'][ref]).state == \
                'CONFIRMED', ref
    if case['kind'] == 'contradiction':
        _assert_contradiction_rows(db, case, seeded)


def _assert_superseded_rows_and_exclusions(db, case, seeded, excluded):
    """Nothing is deleted: the old row keeps its state and the package names
    it in `excluded` with freshness 'superseded' (assemble.py `_knowledge`)."""
    by_id = {e['ref']['id']: e for e in excluded if e['ref']['kind'] == 'knowledge_item'}
    for it in case['items']:
        if not it['supersedes']:
            continue
        old_id = seeded['ref_id'][it['supersedes']]
        entry = by_id.get(old_id)
        assert entry is not None and entry['freshness'] == 'superseded', it['ref']
        assert 'superseded' in entry['reason'], it['ref']


def _assert_contradiction_rows(db, case, seeded):
    """E stays CONFIRMED and F stays CANDIDATE, nothing rewritten; the pass
    wrote the `contradicts` relation once towards a shown item, and none for
    an item the call was never shown (knowledge.py `record_knowledge_pass`,
    the `known_items` gate)."""
    e_ref = next(it['ref'] for it in case['items'] if it['state'] == 'CONFIRMED')
    e_id = seeded['ref_id'][e_ref]
    f_ref = next(it['ref'] for it in case['items'] if it['state'] == 'CANDIDATE')
    f_id = seeded['ref_id'][f_ref]
    assert _row(db, entities.KnowledgeItem, e_id).state == 'CONFIRMED'
    assert _row(db, entities.KnowledgeItem, f_id).state == 'CANDIDATE'
    links = [r for r in _all(db, entities.Relation) if r.rel == 'contradicts']
    linked = any(it['state'] == 'CANDIDATE' and it['supersedes'] for it in case['items'])
    if linked:
        assert [(r.src_id, r.dst_id) for r in links] == [(f_id, e_id)]
        assert links[0].confidence_tier == 'INFERRED'
    else:
        assert links == []
        assert seeded['pass_out']['dropped'] >= 1


# ── the table: it names its metric and prints no headline ─────────────────

def collect_results(dbs=None):
    """Run every case and every query once, keeping what a row shows. One db
    per case would isolate them; one db with one project per case is what the
    engine scopes by anyway."""
    results = []
    db = dbs
    for case in CASES:
        seeded = run_case(db, case)
        for qu in case['queries']:
            returned, _ = ranked_refs(db, case, seeded, qu['q'])
            k = case['k']
            results.append({
                'case': case['id'], 'kind': case['kind'], 'query': qu['q'],
                'gold': list(qu['gold']), 'top_k': returned[:k], 'k': k,
                'recall': recall_at_k(returned, qu['gold'], k),
                'note': 'expected lexical miss' if qu.get('expect_miss') else ''})
    return results


def format_table(results):
    """One header line, then one row per case/query. No headline number: every
    row is one query's own recall, and nothing here folds the rows together."""
    lines = [HEADER]
    for r in results:
        lines.append(' | '.join([
            r['case'], r['kind'], r['query'], ','.join(r['gold']),
            ','.join(r['top_k']), 'recall=%.2f' % r['recall'], r['note']]))
    return '\n'.join(lines)


def test_the_table_names_its_metric_and_prints_no_headline(db):
    results = collect_results(db)
    table = format_table(results)
    lines = table.split('\n')
    assert lines[0] == HEADER
    assert len(lines) == 1 + sum(len(c['queries']) for c in CASES)
    for line in lines:
        for word in BANNED:
            assert word not in line.lower(), line
    print(table)

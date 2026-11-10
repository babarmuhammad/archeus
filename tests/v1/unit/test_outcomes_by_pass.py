"""`outcomes.by_pass` sums the usage of each learning pass's own calls (knowledge, decisions,
lessons) from the ledger: calls, tokens in and out, cache, cost. An unreported figure stays
None, never 0; `complete` holds only while every call's figures are the harness's total."""

import pytest

from archeus.core.application import outcomes
from archeus.core.domain import entities, ids
from archeus.core.domain.events import new_event
from archeus.core.domain.values import Ref
from archeus.infra.db import Database

ACTOR = Ref('user_device', ids.new_id('principal'))

SOURCES = {'knowledge': ('knowledge_extraction', 'repository_inspection'),
           'decisions': ('knowledge_extraction', 'meeting'), 'lessons': ('lesson', 'mission')}


@pytest.fixture
def db(archeus_home):
    d = Database.open()
    yield d
    d.close()


def put(db, *rows):
    def run(tx, **_):
        for r in rows:
            tx.insert(r, actor=ACTOR)
        tx.append(new_event('mission.updated', Ref('mission', ids.new_id('mission')), ACTOR,
                            payload={}, workspace=ids.GLOBAL_WORKSPACE))
    db.writer.execute(run, {})


def call(db, name=None, *, purpose=None, source_kind=None, basis='reported_total', usage=True,
         **figures):
    """An own call of pass *name* (or of *purpose* and *source_kind*) with a ledger row
    carrying *figures* (no row when *usage* is False: a call that never ran)."""
    if name:
        purpose, source_kind = SOURCES[name]
    rd = ids.new_id('route_decision')
    row = [entities.RouteDecision(id=rd, subject=Ref('archeus_call', purpose), purpose=purpose,
                                  source=Ref(source_kind, ids.new_id(source_kind)))]
    if usage:
        row.append(entities.UsageLedger(id=ids.new_id('usage_ledger'), route_decision_id=rd,
                                        basis=basis, **figures))
    put(db, *row)


def read(db):
    with db.read() as conn:
        return outcomes.by_pass(conn)


def test_each_pass_sums_its_own_calls_and_figures(db):
    call(db, 'knowledge', tokens_in=100, tokens_out=10, cache_read=40, cache_write=4, cost_usd=0.5)
    call(db, 'knowledge', tokens_in=50, tokens_out=5, cache_read=10, cost_usd=0.25)
    call(db, 'lessons', tokens_in=7, tokens_out=3)
    call(db, 'decisions', tokens_in=2)
    assert read(db) == [
        {'pass': 'decisions', 'calls': 1, 'tokens_in': 2, 'tokens_out': None, 'cache_read': None,
         'cache_write': None, 'cost_usd': None, 'complete': True},
        {'pass': 'knowledge', 'calls': 2, 'tokens_in': 150, 'tokens_out': 15, 'cache_read': 50,
         'cache_write': 4, 'cost_usd': 0.75, 'complete': True},
        {'pass': 'lessons', 'calls': 1, 'tokens_in': 7, 'tokens_out': 3, 'cache_read': None,
         'cache_write': None, 'cost_usd': None, 'complete': True}]


def test_nothing_reported_stays_none_never_zero_and_a_reported_zero_is_kept(db):
    call(db, 'knowledge', basis='none')
    call(db, 'lessons', tokens_in=0)
    knowledge, lessons = read(db)
    assert (knowledge['tokens_in'], knowledge['cost_usd'], knowledge['calls']) == (None, None, 1)
    assert lessons['tokens_in'] == 0


def test_one_partial_call_makes_the_pass_incomplete(db):
    call(db, 'knowledge', tokens_in=1)
    call(db, 'knowledge', tokens_in=1, basis='partial')
    call(db, 'lessons', tokens_in=1)
    knowledge, lessons = read(db)
    assert (knowledge['complete'], lessons['complete']) == (False, True)


def test_a_call_that_never_ran_is_not_counted(db):
    call(db, 'knowledge', usage=False)
    assert read(db) == []
    call(db, 'knowledge', tokens_in=3)
    assert [(g['pass'], g['calls']) for g in read(db)] == [('knowledge', 1)]


def test_calls_that_are_not_learning_passes_are_left_out(db):
    call(db, purpose='planner', source_kind='mission', tokens_in=9)
    call(db, purpose='review', source_kind='mission', tokens_in=9)
    call(db, purpose='lesson', source_kind='meeting', tokens_in=9)
    assert read(db) == []


def test_a_consolidation_the_user_asked_for_is_a_pass_of_its_own(db):
    call(db, purpose='knowledge_extraction', source_kind='project', tokens_in=9)
    assert [(g['pass'], g['calls'], g['tokens_in']) for g in read(db)] == [('consolidate', 1, 9)]

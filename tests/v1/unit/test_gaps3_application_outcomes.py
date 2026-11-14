"""T-1126: the ten highest-risk uncovered branches of
`archeus/core/application/outcomes.py` lines 144-286 inclusive: the `usage` / `_band` /
`by_context` / `graph_size` / `recurring_findings` slice at the card's stated HEAD
56d53504, 2026-11-10 (this container has no `git`, so that hash is the card's, not a
fact checked here). No source file is edited here; this file is the whole card.

The ten selected branches — fail-closed and denial first, then boundaries, then error
paths, then the concurrency ordering — each with the mutation whose removal or inversion
the test catches. The full mutation table (18 mutants, and which of them the existing
suite already kills) is in the card report /work/QWEN-DONE-T-1126.md.

 1. outcomes.py:165   the account projection is applied to the KEY, before grouping, and
    only for `by == 'account'`: a mission or a pass key never reaches it, and a
    projection that cannot answer returns nothing at all rather than a half-shown
    raw-key sum (mutants: projection run for every `by`; projection error swallowed) —
    `test_mission_and_pass_grouping_never_run_the_account_projection`
 2. outcomes.py:153-154  `by == 'pass'` delegates to `by_pass` before any account key is
    built (mutant: the delegation removed) — same test, the `pass` arm
 3. outcomes.py:162   an own call about something that is not a mission keeps its source
    id out of the output: the row is kept under None, never keyed by a foreign id and
    never dropped (mutant: the `s.kind == 'mission'` test removed) —
    `test_an_own_call_about_something_that_is_not_a_mission_is_kept_under_none`
 4. outcomes.py:281   a finding that normalises to nothing (nothing but digits and path
    separators) is never a key, so it cannot put an empty-keyed phantom into the
    recurrence baseline (mutant: `if k:` inverted) —
    `test_a_finding_that_normalises_to_nothing_is_never_a_key`
 5. outcomes.py:219   a harness's reported 0 stays 0: the `is not None` test, not a truth
    test (mutant: `if u.tokens_in or u.tokens_out`) —
    `test_a_reported_zero_stays_zero_while_nothing_reported_stays_none`
 6. outcomes.py:220   a cost reported while no token figure was is still a cost and still
    no token figure (mutant: the cost line moved inside the reported test) — same test,
    the `1k to 4k` band
 7. outcomes.py:253   a source that sums to 0 bytes gives `ratio` None, never a division
    by zero (mutant: `if source` widened to `if source is not None`) —
    `test_only_the_latest_completed_observation_is_counted_and_an_empty_source_has_no_ratio`
 8. outcomes.py:245-249  only the LAST COMPLETED inspection of a repository is its source:
    an older payload is shadowed and a repository that never completed contributes
    nothing (mutant: `done[-1]` read as `done[0]`) — same test
 9. outcomes.py:285   equal recurrence counts sort by key, not by the order the findings
    were first seen, and re-reading is identical: the first read does not consume the
    sets (mutant: the key tie-break removed) —
    `test_recurrence_counts_missions_not_reviews_or_finding_categories`
10. outcomes.py:274-275  the window is this project's last RECUR_WINDOW reviews in COMMIT
    order: two writers are forced into one order with Events (no sleep), another
    project's commits landing between them take no window slot, and a reader between two
    commits sees whole reviews only (mutant: the window cut before the project filter) —
    `test_the_recurrence_window_follows_commit_order_never_a_half_written_review`

Kept as reinforcement of the same changed branches (the card's "changed since 0b17a5b4":
public usage aggregation and the recurrence baseline), where the existing suite already
kills the mutation but never with the input this file brings — private homes paths
through the real `Homes` seam, the absent key folded in with them, an unknown total
inside a merged row, and the registered id folded with the historical ref of the same
account: `test_no_private_home_ref_survives_the_account_projection`,
`test_a_merged_account_row_is_never_complete_when_one_source_row_was_not`,
`test_a_registered_id_and_the_historical_ref_of_the_same_account_merge_before_totals`,
and the distinct-missions arm of the recurrence test of branch 9.

Style and fixtures follow tests/v1/unit/test_outcomes_usage.py and
tests/v1/unit/test_gaps_core_application_public.py (the closest existing tests of these
functions): the same `Database.open()` + `archeus_home` fixture, the same injected
`shorts` Homes seam, no OS probing, no process, no network. Platform-neutral: homes are
spelled in one fixed flavour with `path_flavour='windows'`, nothing reads the
environment, no file is written outside the test's own ARCHEUS_HOME (tmp_path) and no
filename holds `?` or `:`. Ordering is forced with threading Events under bounded
waits — never a sleep — and every thread started is joined.
"""

import threading

import pytest

from archeus.core.application import outcomes
from archeus.core.application.public import system_value
from archeus.core.domain import entities, ids
from archeus.core.domain.events import new_event
from archeus.core.domain.values import Ref
from archeus.core.homes import Homes
from archeus.infra.artifacts import store as artifacts
from archeus.infra.db import Database

WS = ids.GLOBAL_WORKSPACE
SYSTEM = Ref('system', ids.new_id('principal'))
ATTEMPTS = iter(range(1, 1000))
VERSIONS = iter(range(1, 100000))
WAIT = 10.0                       # an Event bound, never a sleep

#: one fixed path flavour, never probed: `shorts` is injected, so no OS call is made
HOME_A = 'C:/Gaps3/Private-Alpha'
HOME_B = 'C:/Gaps3/Private-Beta'


@pytest.fixture
def db(archeus_home):
    d = Database.open()
    yield d
    d.close()


# ── fixtures ────────────────────────────────────────────────────────────────────

def put(db, *new):
    """Insert *new* in one command, with the event that says they appeared (the
    writer refuses a command that mutates and records nothing)."""
    def command(tx, **_):
        for r in new:
            tx.insert(r, actor=SYSTEM)
        tx.append(new_event('mission.updated', Ref('mission', ids.new_id('mission')), SYSTEM,
                            payload={}, workspace=WS))
    db.writer.execute(command, {})


def project(db, name='p'):
    pid = ids.new_id('project')
    put(db, entities.Project(id=pid, workspace_id=WS, name=name))
    return pid


def mission(db, project_id):
    """A bare mission of *project_id* (no plan, no task, no package)."""
    mid = ids.new_id('mission')
    put(db, entities.Mission(id=mid, workspace_id=WS, title='m', objective='o',
                             project_id=project_id, state='EXECUTING'))
    return mid


def mission_with_task(db, *, used=None, package=True, budget=True):
    """(mission id, task id): a mission whose context package reports *used* tokens
    (`package`: no package row at all, `budget`: a package with no budget dict)."""
    mid, pid, tid = ids.new_id('mission'), ids.new_id('plan'), ids.new_id('task')
    pkg = ids.new_id('context_package')
    new = []
    if package:
        new.append(entities.ContextPackage(
            id=pkg, workspace_id=WS, subject_kind='mission', subject_id=mid,
            budget={'limit_tokens': 9999, 'used_tokens': used} if budget else None))
    put(db, *new,
        entities.Mission(id=mid, workspace_id=WS, title='M', objective='o', state='EXECUTING',
                         context_package_id=pkg if package else None),
        entities.Plan(id=pid, mission_id=mid, plan_version=1, state='APPROVED'),
        entities.Task(id=tid, plan_id=pid, mission_id=mid, key=tid, title='T',
                      kind='code_change'))
    return mid, tid


def execution(db, mid, tid, *, state='ENDED_OK', charged=None, model='m', effort='high',
              usage=None):
    """One execution of *tid* of (model, effort) in *state*; *usage* is the ledger row's
    figures (None: the execution has no ledger row at all). Returns the execution id."""
    rd, x = ids.new_id('route_decision'), ids.new_id('execution')
    new = [entities.RouteDecision(id=rd, subject=Ref('task', tid), task_id=tid, mission_id=mid,
                                  harness_id='fake', account_ref='A', model=model),
           entities.Execution(id=x, task_id=tid, mission_id=mid, attempt=next(ATTEMPTS),
                              state=state, route_decision_id=rd, model=model, effort=effort,
                              charged=charged)]
    if usage is not None:
        new.append(entities.UsageLedger(id=ids.new_id('usage_ledger'), execution_id=x,
                                        route_decision_id=rd, basis='reported_total', **usage))
    put(db, *new)
    return x


def ledger(db, *, execution_id=None, source=None, subject_id='x', purpose='planner',
           account_id=None, account_ref=None, basis='reported_total', **figures):
    """One ledger row of its own (not an execution's): routed by a decision whose `source`
    is *source* (a (kind, id) pair, None: about nothing) and attributable to
    *account_id* / *account_ref* exactly as the router left them."""
    rd = ids.new_id('route_decision')
    put(db, entities.RouteDecision(id=rd, subject=Ref('archeus_call', subject_id),
                                   purpose=purpose, source=Ref(*source) if source else None),
        entities.UsageLedger(id=ids.new_id('usage_ledger'), execution_id=execution_id,
                            route_decision_id=rd, account_id=account_id,
                            account_ref=account_ref, basis=basis, **figures))
    return rd


def review(db, mission_id, *, requirements_missing=(), regressions=(), risks=()):
    """A review of *mission_id* that found these three lists (a review belongs to a
    plan version, so the plan is inserted with it)."""
    put(db, *_review_rows(mission_id, requirements_missing=requirements_missing,
                          regressions=regressions, risks=risks))


def _review_rows(mission_id, *, requirements_missing=(), regressions=(), risks=()):
    plan = entities.Plan(id=ids.new_id('plan'), mission_id=mission_id,
                        plan_version=next(VERSIONS), summary='p', state='APPROVED')
    found = entities.Review(id=ids.new_id('review'), mission_id=mission_id, reviewer='model',
                            verdict='changes_requested', plan_id=plan.id,
                            requirements_missing=requirements_missing,
                            regressions=regressions, risks=risks)
    return plan, found


def insert_reviews(db, pairs):
    """Every (mission id, finding) of *pairs* in ONE command: all of them commit
    together or none does, which is what the reader between two commits relies on."""
    def command(tx, **_):
        for mid, text in pairs:
            plan, found = _review_rows(mid, risks=(text,))
            for r in (plan, found):
                tx.insert(r, actor=SYSTEM)
            tx.append(new_event('review.requested', Ref('review', found.id), SYSTEM))
    db.writer.execute(command, {})


def read(db, by, public=lambda key: key):
    with db.read() as conn:
        return outcomes.usage(conn, by, public)


def read_context(db):
    with db.read() as conn:
        return outcomes.by_context(conn)


def read_graph(db):
    with db.read() as conn:
        return outcomes.graph_size(conn)


def read_recurring(db, pid):
    with db.read() as conn:
        return outcomes.recurring_findings(conn, pid)


def homes():
    """The one homes seam: two registered private homes, `shorts` injected so nothing
    is probed, one fixed path flavour so the answer never depends on the host OS."""
    return Homes([HOME_A, HOME_B], shorts=lambda _: None, path_flavour='windows')


def shown_by_homes(key):
    """The projection `archeus/api/routes.py:662-663` hands to `usage`: the route's own
    `system_value(..., path_keys=('account',))`, applied to the key alone."""
    return system_value({'account': key}, homes(), path_keys=('account',))['account']


# ── 1-3: the account projection (fail-closed / denial) ──────────────────────────

def test_no_private_home_ref_survives_the_account_projection(db):
    """outcomes.py:164-165 — `public(key(u))` before `_sum`. Two different private home
    refs and the absent key become one shown row whose figures are only partly reported
    (the review lead's absent + private + unknown combination), and no raw home survives
    anywhere in what the caller gets back."""
    ledger(db, account_ref=HOME_A, tokens_in=1)
    ledger(db, account_ref=HOME_B)                           # nothing reported: unknown
    ledger(db, tokens_in=4)                                  # no account at all: shown as None
    ledger(db, account_ref='plain-account', tokens_in=8)     # not a home: shown as itself
    got = read(db, 'account', shown_by_homes)
    assert [g['account'] for g in got] == ['plain-account', None]      # None sorts last
    plain, merged = got
    assert (merged['calls'], merged['tokens_in'], merged['tokens_out'],
            merged['complete']) == (3, 5, None, True)
    assert (plain['calls'], plain['tokens_in']) == (1, 8)
    # the forbidden side effect: the stored private path reaching the caller at all
    assert all(HOME_A not in repr(g) and HOME_B not in repr(g) for g in got)


def test_a_merged_account_row_is_never_complete_when_one_source_row_was_not(db):
    """outcomes.py:165 — the merge happens before `_sum` folds `complete`, so showing
    two accounts alike can never report a partial group as the harness's own total."""
    ledger(db, account_ref='acct-one', tokens_in=1, basis='reported_total')
    ledger(db, account_ref='acct-two', tokens_in=1, basis='partial')
    ledger(db, account_ref='other', tokens_in=1, basis='reported_total')
    before = [(g['account'], g['complete']) for g in read(db, 'account')]
    assert before == [('acct-one', True), ('acct-two', False), ('other', True)]
    got = [(g['account'], g['complete'], g['calls'])
           for g in read(db, 'account', lambda k: {'acct-one': 'shown',
                                                   'acct-two': 'shown'}.get(k, k))]
    assert got == [('other', True, 1), ('shown', False, 2)]


def test_a_registered_id_and_the_historical_ref_of_the_same_account_merge_before_totals(db):
    """outcomes.py:164 — `account_id or account_ref` picks the registered account, and
    the projection then folds that id together with the older row's raw ref: one row,
    one total, and neither stored key shown."""
    acc = ids.new_id('account')
    put(db, entities.Account(id=acc, harness_id='fake', label='A', auth_kind='api_key'))
    ledger(db, account_id=acc, account_ref='stale-ref', tokens_in=1)     # registered call
    ledger(db, account_ref=HOME_A, tokens_in=2)                          # before registration
    shown = 'account:gaps3-one-account'
    got = read(db, 'account', lambda k: shown if k in (acc, HOME_A) else shown_by_homes(k))
    assert [g['account'] for g in got] == [shown]
    assert (got[0]['calls'], got[0]['tokens_in']) == (2, 3)
    assert all(acc not in repr(g) and HOME_A not in repr(g) for g in got)


# ── 4-5: grouping denial and the attribution error paths ────────────────────────

class Projected(Exception):
    """Raised by the projection seam if it is ever run where it must not be."""


def never_projected(key):
    raise Projected('the account projection ran for the key %r' % (key,))


def test_mission_and_pass_grouping_never_run_the_account_projection(db):
    """outcomes.py:153-154 (`by == 'pass'` returns `by_pass` before any key is built)
    and 164-165 (the `else key` arm): a mission id and a pass name are not accounts, so
    the account projection must never touch them, and a row that names neither an
    execution's mission nor a mission source is kept under None, never dropped. A
    projection that cannot answer fails closed: the call raises, no half-shown row."""
    mid, tid = mission_with_task(db)
    execution(db, mid, tid, usage={'tokens_in': 1})
    ledger(db, source=('mission', mid), tokens_in=2)                  # an own call about it
    ledger(db, tokens_in=4)                                            # about nothing: kept
    rin = ids.new_id('repository_inspection')
    ledger(db, source=('repository_inspection', rin), purpose='knowledge_extraction',
           tokens_in=8)                                                # a learning pass
    with pytest.raises(Projected):             # fail closed: a projection that cannot
        read(db, 'account', never_projected)   # show an account sums nothing, half-shown
    with db.read() as conn:
        got = outcomes.usage(conn, 'mission', never_projected)         # raises if it runs
        assert got == outcomes.usage(conn, 'mission')                  # projection changed nothing
        assert [(g['mission'], g['calls'], g['tokens_in']) for g in got] == [
            (mid, 2, 3), (None, 2, 12)]                                # raw id shown, None kept
        passes = outcomes.usage(conn, 'pass', never_projected)
        assert passes == outcomes.by_pass(conn) == [{
            'pass': 'knowledge', 'calls': 1, 'tokens_in': 8, 'tokens_out': None,
            'cache_read': None, 'cache_write': None, 'cost_usd': None, 'complete': True}]


def test_a_ledger_row_whose_execution_row_is_gone_is_still_attributed_to_its_own_call(db):
    """outcomes.py:160-162 — `missions.get(u.execution_id) or …`: a row naming an
    execution the executions table does not hold is not dropped and is never keyed by
    that orphan id; it falls through to the mission its own call was about."""
    m1, t1 = mission_with_task(db)
    execution(db, m1, t1, usage={'tokens_in': 1})                      # its row is there
    m2, _ = mission_with_task(db)
    gone = ids.new_id('execution')                                      # minted, never written
    ledger(db, execution_id=gone, source=('mission', m2), tokens_in=5)
    got = read(db, 'mission')
    assert [(g['mission'], g['calls'], g['tokens_in']) for g in got] == [(m1, 1, 1), (m2, 1, 5)]
    assert gone not in [g['mission'] for g in got]


def test_an_own_call_about_something_that_is_not_a_mission_is_kept_under_none(db):
    """outcomes.py:162 — the `s.kind == 'mission'` arm: a call about a project or an
    inspection names no mission, so it is kept under None. Its source id must never be
    shown as a mission key, and the row must never be dropped with it."""
    m, t = mission_with_task(db)
    execution(db, m, t, usage={'tokens_in': 1})
    pid = project(db)
    rin = ids.new_id('repository_inspection')
    ledger(db, source=('project', pid), tokens_in=5)
    ledger(db, source=('repository_inspection', rin), tokens_in=2)
    got = read(db, 'mission')
    assert [(g['mission'], g['calls'], g['tokens_in']) for g in got] == [(m, 1, 1), (None, 2, 7)]
    keys = [g['mission'] for g in got]
    assert pid not in keys and rin not in keys


# ── 6: the reported-zero boundary ───────────────────────────────────────────────

def test_a_reported_zero_stays_zero_while_nothing_reported_stays_none(db):
    """outcomes.py:219-220 — the `is not None` test (not a truth test) is what keeps a
    harness's own 0 from being read as "nothing reported"; a row that reported nothing
    at all keeps the band's figures None, and only the band with no ledger row at all
    reads incomplete (which is what makes the 0 above a reported 0, not a gap)."""
    m1, t1 = mission_with_task(db, used=500)
    m2, t2 = mission_with_task(db, used=6000)
    m3, t3 = mission_with_task(db, used=None)                # the package reports no figure
    m4, t4 = mission_with_task(db, used=2000)
    execution(db, m1, t1, usage={'tokens_in': 0, 'tokens_out': 0, 'cost_usd': 0.0})
    execution(db, m2, t2, usage={'tokens_in': None, 'tokens_out': None, 'cost_usd': None})
    execution(db, m3, t3)                                    # no ledger row was written
    execution(db, m4, t4, usage={'tokens_in': None, 'tokens_out': None, 'cost_usd': 0.25})
    g = {r['context']: r for r in read_context(db)}
    assert (g['under 1k']['tokens'], g['under 1k']['cost_usd'], g['under 1k']['complete']) == (
        0, 0.0, True)
    assert (g['over 4k']['tokens'], g['over 4k']['cost_usd'], g['over 4k']['complete']) == (
        None, None, True)
    # a cost reported while no token figure was is still a cost, and still not a token
    assert (g['1k to 4k']['tokens'], g['1k to 4k']['cost_usd']) == (None, 0.25)
    assert g[None]['tokens'] is None and g[None]['complete'] is False
    assert g['under 1k']['executions'] == g['over 4k']['executions'] == 1


# ── 7: the graph ratio boundary and its error path ──────────────────────────────

def test_only_the_latest_completed_observation_is_counted_and_an_empty_source_has_no_ratio(db):
    """outcomes.py:245-249 (`done[-1]`, the LAST COMPLETED inspection, and the
    `if art is not None` arm) and 253 (`if source else None`): an older payload is never
    counted behind a newer empty one, a repository that never completed contributes
    nothing, and a 0-byte source gives ratio None instead of dividing by zero."""
    pid = project(db)
    put(db, entities.KnowledgeItem(id=ids.new_id('knowledge_item'), workspace_id=WS,
                                  project_id=pid, type='ENTITY', title='abc', text='',
                                  state='CONFIRMED'))
    old, empty = artifacts.put(b'x' * 20), artifacts.put(b'')
    r1, r2 = ids.new_id('repository'), ids.new_id('repository')
    put(db, entities.Artifact(id=old, media_type='application/json', size=20),
        entities.Artifact(id=empty, media_type='application/json', size=0))
    for rid in (r1, r2):
        put(db, entities.Repository(id=rid, workspace_id=WS, project_id=pid, path=rid,
                                    path_key=rid))
    put(db, entities.RepositoryInspection(id=ids.new_id('repository_inspection'),
                                          repository_id=r1, extractor_version=1,
                                          revision='rev-1', state='COMPLETED', payload_sha256=old))
    put(db, entities.RepositoryInspection(id=ids.new_id('repository_inspection'),
                                          repository_id=r1, extractor_version=1,
                                          revision='rev-2', state='COMPLETED',
                                          payload_sha256=empty))
    put(db, entities.RepositoryInspection(id=ids.new_id('repository_inspection'),
                                          repository_id=r2, extractor_version=1,
                                          revision='rev-3', state='FAILED'))
    (got,) = read_graph(db)
    assert got == {'project_id': pid, 'items': 1, 'graph_bytes': 3, 'source_bytes': 0,
                   'ratio': None}


# ── 8-9: what recurrence counts ─────────────────────────────────────────────────

def test_recurrence_counts_missions_not_reviews_or_finding_categories(db):
    """outcomes.py:282-283 (`g['missions']` is a SET of missions, so a finding repeated
    in two reviews of one mission, or in two categories of one review, is one mission)
    and 284-285 (equal counts sort by key, and re-reading does not consume the sets)."""
    pid = project(db)
    m1, m2, m3 = (mission(db, pid) for _ in range(3))
    # the first wording seen is the one that sorts LAST, so the tie-break is what
    # decides the order, not the order the findings were seen in
    review(db, m1, risks=('Upload may lose the RETRY', 'Flaky database timeout'),
           regressions=('Only one mission says it',))
    review(db, m1, risks=('flaky database  timeout',), regressions=('Upload may lose the retry',),
           requirements_missing=('Only one mission says it',))
    review(db, m2, risks=('Flaky database timeout',), regressions=('Upload may lose the retry',),
           requirements_missing=('Only one mission says it',))
    review(db, m3, risks=('flaky database timeout',), regressions=('upload   may LOSE the retry',))
    got = read_recurring(db, pid)
    assert [g['key'] for g in got] == ['flaky database timeout', 'upload may lose the retry']
    assert [g['missions'] for g in got] == [sorted([m1, m2, m3])] * 2      # 4 findings, 3 missions
    assert [g['finding'] for g in got] == ['Flaky database timeout',
                                           'Upload may lose the RETRY']    # the first wording seen
    assert 'only one mission says it' not in [g['key'] for g in got]       # 2 missions, 3 findings
    assert read_recurring(db, pid) == got                                  # nothing consumed


def test_a_finding_that_normalises_to_nothing_is_never_a_key(db):
    """outcomes.py:281 (`if k:`): a finding of nothing but digits and path separators
    normalises to ” and must be ignored — three missions saying it must not put one
    empty-keyed phantom finding into the baseline the lessons pass is judged against."""
    pid = project(db)
    noise = ('12/34', '\\', '7628', '   ', '')
    for _ in range(3):
        m = mission(db, pid)
        review(db, m, risks=noise, requirements_missing=('Real finding here',))
    got = read_recurring(db, pid)
    assert [(g['key'], g['finding'], len(g['missions'])) for g in got] == [
        ('real finding here', 'Real finding here', 3)]
    assert all(g['key'] for g in got)


# ── 10: the window under two writers, ordered by Events ──────────────────────────

def test_the_recurrence_window_follows_commit_order_never_a_half_written_review(db):
    """outcomes.py:274-275 — the reviews are filtered to this project and THEN cut to
    the last RECUR_WINDOW, in row order, which is commit order. Two writers are forced
    into one order with Events (no sleep): the twelve of our own reviews commit six and
    six, the other project's three commit in between, so exactly the first two of ours
    fall out; and each read between two commits sees whole missions only, never part of
    a command's rows."""
    pid, other = project(db, 'p'), project(db, 'q')
    mine = [mission(db, pid) for _ in range(12)]
    theirs = [mission(db, other) for _ in range(3)]
    first, rest = mine[:6], mine[6:]
    a_done, go_b, b_done, go_c, c_done = (threading.Event() for _ in range(5))
    gates = (go_b, go_c)
    jobs = ((list(zip(first, ['Stable finding'] * len(first))), a_done, None),
            (list(zip(theirs, ['Stable finding'] * len(theirs))), b_done, go_b),
            (list(zip(rest, ['Stable finding'] * len(rest))), c_done, go_c))
    threads = []

    def run(pairs, done, go):
        try:
            if go is not None:
                assert go.wait(WAIT), 'a writer never got its turn'
            insert_reviews(db, pairs)
        finally:
            done.set()

    try:
        for pairs, done, go in jobs:
            t = threading.Thread(target=run, args=(pairs, done, go), name='gaps3-writer')
            t.start()
            threads.append(t)
        assert a_done.wait(WAIT), 'the first writer never committed'
        # between A and B: A's command is whole, B's and C's rows are not there at all
        assert [g['missions'] for g in read_recurring(db, pid)] == [sorted(first)]
        assert read_recurring(db, other) == []
        go_b.set()
        assert b_done.wait(WAIT), 'the second writer never committed'
        # between B and C: the other project's reviews never entered our window
        assert [g['missions'] for g in read_recurring(db, pid)] == [sorted(first)]
        assert [g['missions'] for g in read_recurring(db, other)] == [sorted(theirs)]
        go_c.set()
        assert c_done.wait(WAIT), 'the third writer never committed'
        # all twelve of ours committed: the first two, i.e. the first COMMITTED, fell out
        assert [g['missions'] for g in read_recurring(db, pid)] == [sorted(mine[2:])]
        assert [g['finding'] for g in read_recurring(db, pid)] == ['Stable finding']
    finally:
        for g in gates:
            g.set()
        for t in threads:
            t.join(WAIT)
            assert not t.is_alive(), 'a writer thread was left running'

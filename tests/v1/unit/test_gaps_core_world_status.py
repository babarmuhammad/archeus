"""T-746: the ten highest-risk uncovered branches of archeus/core/world/status.py.

Fail-closed and denial paths first: a scoped status for a project nobody registered
answers nothing at all, `project` and `inspections` refuse a row that is not there
instead of answering "empty", a routing decision whose source is not a repository
inspection never becomes the project's knowledge pass, a finding whose status is
neither violated nor unchecked lands in neither list, and a finding cannot choose
its own repository, revision, staleness or provisional flag. Then the boundary
values: settled-last whatever the timestamps say, "last inspection" meaning the
newest row written, `provisional` from the assessed inspection's `dirty` alone, and
`queued` from an inspection whose state is exactly COMPLETED. Then the error-shaped
paths: an outcome not written yet says `running`, the newest decision is the one
that answers, the reason is scrubbed only when homes are handed in, `as_of_seq` is
the head of the log and survives a prune, a scoped status leaks nothing about
foreign or vanished projects, and the limit cuts the newest-first list exactly.

Seed style, the `db` fixture and the helper names follow
tests/v1/unit/test_gaps_core_metrics.py (the closest gaps test; tests/v1/unit has no
conftest of its own); the reads are the same shape as `h.read(fn, *a)` in
tests/v1/integration/test_world.py, whose W21-W22 scenarios this file deliberately
does not repeat: everything here is raw rows on the test's own ARCHEUS_HOME, in
process. No git, no OS calls, no network, no sleeps, no real process and no test
threads. Every id is a deterministic ULID through `ids.encode`, so the same strings
appear on Linux and on Windows; nothing here is case-sensitive, asserts on OS error
text, needs a POSIX path to be "absolute", or touches the filesystem beyond the
tmp_path the `archeus_home` fixture already uses.
"""

import json

import pytest

from archeus.core.domain import ids
from archeus.core.homes import Homes
from archeus.core.world import status as world_status
from archeus.infra.db import Database
from archeus.infra.db.writer import NotFound
from archeus.infra.eventlog import outbox

WS = 'ws_' + ids.encode(7, 3)
T0 = '2026-11-02T09:00:00.000Z'
T1 = '2026-11-02T10:00:00.000Z'
T2 = '2026-11-02T11:00:00.000Z'
T3 = '2026-11-02T12:00:00.000Z'
SHA = 'a' * 40
META = {'version': 1, 'created_at': T1, 'updated_at': T1, 'created_by': 'p', 'updated_by': 'p'}

VIOLATED = {'constraint_id': 'kno_1', 'constraint': 'core must not import api',
            'kind': 'forbid_dependency', 'status': 'violated', 'reason': None,
            'violations': [['app/core/x.py', 'app/api/__init__.py']], 'violation_count': 1}
UNCHECKED = {'constraint_id': 'kno_2', 'constraint': 'docs describe the api',
             'kind': 'doc_matches_code', 'status': 'unchecked', 'reason': 'graph_truncated',
             'violations': [], 'violation_count': 0}
SATISFIED = {'constraint_id': 'kno_3', 'constraint': 'models exist',
             'kind': 'module_exists', 'status': 'satisfied', 'reason': None,
             'violations': [], 'violation_count': 0}

_MISSING = object()                                  # "no outcome key at all"
_next = iter(range(1, 100000))


def aid(kind):
    """A well-formed id of `kind`, the same string on every run and platform."""
    n = next(_next)
    return '%s_%s' % (ids.PREFIXES[kind], ids.encode(n, n * 7919 + 11))


def project(pid, state='ACTIVE', name='p'):
    return ('projects', dict(META, id=pid, workspace_id=WS, state=state,
                            body=json.dumps({'name': name})))


def mission(mid, pid=None, state='EXECUTING', *, created=T1, updated=T1):
    return ('missions', dict(META, id=mid, workspace_id=WS, project_id=pid, state=state,
                             created_at=created, updated_at=updated,
                             body=json.dumps({'title': 't', 'objective': 'o'})))


def repo(rid, pid, *, arch='CONSISTENT', last_inspection=None, last_revision=SHA,
         findings=(), kind='repo'):
    return ('repositories', dict(
        META, id=rid, workspace_id=WS, project_id=pid, path_key='key/' + rid,
        architecture_state=arch,
        body=json.dumps({'path': '/work/' + rid, 'kind': kind,
                         'last_inspection_id': last_inspection,
                         'last_revision': last_revision, 'findings': list(findings)})))


def insp(iid, rid, state='COMPLETED', *, revision=SHA, inspected_at=T1, complete=True,
         dirty=False, failure=None, attempts=0):
    return ('repository_inspections', dict(
        META, id=iid, repository_id=rid, revision=revision, extractor_version=1, state=state,
        body=json.dumps({'inspected_at': inspected_at, 'complete': complete, 'dirty': dirty,
                         'failure': failure, 'attempts': attempts})))


def decision(did, pid, *, purpose='knowledge_extraction', source='repository_inspection',
             state='completed', items=0, reason=None, outcome=_MISSING):
    body = {'subject': {'kind': 'archeus_call', 'id': did}}
    if source is not None:
        body['source'] = {'kind': source, 'id': aid('repository_inspection')}
    if outcome is _MISSING:
        outcome = {'state': state, 'items': items, 'reason': reason}
    if outcome is not None:
        body['outcome'] = outcome
    return ('route_decisions', dict(META, id=did, purpose=purpose, project_id=pid,
                                    body=json.dumps(body)))


def event(eid):
    return ('events', {'id': 'evt_' + eid, 'type': 'mission.created', 'at': T1,
                       'actor_kind': 'system', 'actor_id': 'p', 'cause_chain': '[]',
                       'subject_kind': 'mission', 'subject_id': aid('mission'),
                       'workspace_id': WS, 'project_id': None, 'visibility': 'user',
                       'payload': '{}'})


def _put(tx, *, rows):
    for table, cols in rows:
        tx.execute('INSERT INTO %s (%s) VALUES (%s)' % (table, ','.join(cols),
                                                        ','.join('?' * len(cols))),
                   list(cols.values()))


def put(db, *rows_):
    db.writer.execute(_put, {'rows': list(rows_)})


def clear(db, table):
    def drop(tx):
        tx.execute('DELETE FROM %s' % table)
    db.writer.execute(drop)


def read(db, fn, *a, **kw):
    with db.read() as conn:
        return fn(conn, *a, **kw)


@pytest.fixture
def db(archeus_home):                     # as in tests/v1/integration/conftest.py
    d = Database.open()
    yield d
    d.close()


# ── fail-closed and denial paths ─────────────────────────────────────────────

def test_g1_a_scoped_status_for_an_unregistered_project_refuses(db):
    # status.py:33-34 `if project_id not in known: raise NotFound(project_id)`.
    # Without that guard the filter on line 35 would answer a typo'd or deleted
    # id with an empty-looking status, indistinguishable from a real project
    # that has no rows yet; the caller could never tell "yours is empty" from
    # "yours does not exist". An empty string is scoped too (`is not None`),
    # so it is refused as well.
    pid = aid('project')
    put(db, project(pid))
    for foreign in (aid('project'), ''):
        with pytest.raises(NotFound):
            read(db, world_status.status, foreign)
    assert [p['id'] for p in read(db, world_status.status, pid)['projects']] == [pid]


def test_g2a_project_of_a_missing_row_raises_and_projects_names_nothing(db):
    # status.py:105-107 `if row is None: raise NotFound(project_id)` (and the
    # `rows.where` sweep of projects.py:113): a view of nothing is a refusal,
    # and the one-project view is a `view()` of the row plus the repositories'
    # own views, so the assessment (findings, architecture_state) rides along.
    with pytest.raises(NotFound):
        read(db, world_status.project, aid('project'))
    assert read(db, world_status.projects) == []
    pid, rid = aid('project'), aid('repository')
    put(db, project(pid), repo(rid, pid, findings=[dict(SATISFIED)]))
    got = read(db, world_status.project, pid)
    assert (got['id'], got['name'], got['version'], got['updated_at']) == (pid, 'p', 1, T1)
    (r,) = got['repositories']
    assert (r['id'], r['architecture_state'], r['project_id']) == (rid, 'CONSISTENT', pid)
    assert r['findings'][0]['constraint'] == 'models exist'
    assert [p['id'] for p in read(db, world_status.projects)] == [pid]


def test_g2b_inspections_of_an_unknown_repository_refuse(db):
    # status.py:118-119 `if rows.get(conn, Repository, repository_id) is None:
    # raise NotFound(repository_id)`: an empty list is a repository with no
    # inspections; a repository nobody registered is a caller error, and
    # answering [] would render "this repository has never been inspected"
    # for an id that was mistyped or deleted.
    pid, rid, iid = aid('project'), aid('repository'), aid('repository_inspection')
    put(db, project(pid), repo(rid, pid), insp(iid, rid))
    assert [i['id'] for i in read(db, world_status.inspections, rid)] == [iid]
    with pytest.raises(NotFound):
        read(db, world_status.inspections, aid('repository'))


@pytest.mark.parametrize('source,purpose', [
    ('context_package', 'knowledge_extraction'),        # a foreign source
    (None, 'knowledge_extraction'),                     # no source at all
    ('repository_inspection', 'planner'),               # right source, wrong purpose
], ids=['wrong-source', 'no-source', 'wrong-purpose'])
def test_g3_a_knowledge_decision_from_elsewhere_is_never_the_pass(db, source, purpose):
    # status.py:87-89 — the `source is not None and source.kind ==
    # 'repository_inspection'` filter (and the `purpose=` column match it
    # shares with the query). Drop it and any route decision filed under the
    # project — a planner call, a context pass, a row with no source at all —
    # reads as the project's knowledge pass, so the queued pass a completed
    # inspection really did earn disappears behind somebody else's decision.
    pid, rid, iid = aid('project'), aid('repository'), aid('repository_inspection')
    put(db, project(pid), repo(rid, pid), insp(iid, rid, state='COMPLETED'),
        decision(aid('route_decision'), pid, source=source, purpose=purpose,
                 state='completed', items=9))
    assert read(db, world_status.knowledge_pass, pid) == {
        'state': 'queued', 'route_decision_id': None, 'items': 0, 'reason': None}


def test_g4_a_finding_lands_only_where_its_own_status_puts_it(db):
    # status.py:61-64 — `if f['status'] == 'violated'` / `elif == 'unchecked'`
    # with no else. A satisfied finding is not "unchecked" (line 63), and near
    # statuses — the same word upper-cased, padded, or empty — are not drift:
    # drift is only ever what a row says it is, never an almost-word.
    pid, rid = aid('project'), aid('repository')
    put(db, project(pid), repo(rid, pid, findings=[
        dict(VIOLATED), dict(UNCHECKED), dict(SATISFIED),
        dict(SATISFIED, constraint_id='kno_4', status='VIOLATED'),
        dict(SATISFIED, constraint_id='kno_5', status='violated '),
        dict(SATISFIED, constraint_id='kno_6', status='')]))
    st = read(db, world_status.status)
    assert [d['constraint_id'] for d in st['drift']] == ['kno_1']
    assert [u['constraint_id'] for u in st['unchecked']] == ['kno_2']


def test_g5_a_finding_cannot_forge_its_origin_or_its_staleness(db):
    # status.py:56-60 — `dict(f, repository_id=..., project_id=..., revision=...,
    # stale=..., provisional=...)`: the five identity keys are written after
    # the finding's own, so a stored finding cannot rename its repository, its
    # project, the revision it was evaluated against, or talk its way out of
    # the `stale` label a STALE repository forces on every one of its findings
    # (`stale=repo.architecture_state == 'STALE'`, line 59). Swap the order
    # (`dict(..., **f)`) and this test reads kno_1 as another project's.
    pid = aid('project')
    ra, rb = aid('repository'), aid('repository')
    put(db, project(pid),
        repo(ra, pid, arch='CONSISTENT', findings=[dict(
            VIOLATED, repository_id=rb, project_id=aid('project'),
            revision='f' * 40, stale=True, provisional=True)]),
        repo(rb, pid, arch='STALE', findings=[dict(VIOLATED, constraint_id='kno_9')]))
    drift = read(db, world_status.status)['drift']
    assert [d['constraint_id'] for d in drift] == ['kno_1', 'kno_9']
    forged = drift[0]
    assert (forged['repository_id'], forged['project_id']) == (ra, pid)
    assert (forged['revision'], forged['stale'], forged['provisional']) == (SHA, False, False)
    assert forged['constraint'] == 'core must not import api'   # its own text survives
    assert drift[1]['stale'] is True                            # the STALE one is labelled


def test_g6_the_answer_survives_an_assessment_row_that_is_gone(db):
    # status.py:50-52 — `if repo.last_inspection_id is not None:` then
    # `rows.get(...).entity` with no check that the row is there. The module's
    # own promise is "nothing in the answer that the rows do not say", so a
    # pointer into a row that is gone must answer like the no-assessment case
    # (provisional False), not crash the whole cross-project status with an
    # AttributeError. The source is wrong here, so the test is xfail(strict):
    # it passes the day status.py guards the `rows.get`, and it fails loudly
    # the day someone "fixes" it by deleting the test.
    pid, rid = aid('project'), aid('repository')
    put(db, project(pid), repo(rid, pid, last_inspection=aid('repository_inspection'),
                               findings=[dict(VIOLATED)]))
    st = read(db, world_status.status)
    (p,) = st['projects']
    (r,) = p['repositories']
    assert r['last_inspection'] is None                          # status.py:21-22 too
    (d,) = st['drift']
    assert (d['repository_id'], d['provisional']) == (rid, False)


# ── boundary values ──────────────────────────────────────────────────────────

def test_g7_settled_missions_wait_until_last_whatever_the_clock_says(db):
    # status.py:39-42 and 73 — the split on `state not in _SETTLED`, the two
    # `sort(key=lambda m: m['updated_at'], reverse=True)` and the `unsettled +
    # settled` concatenation. A COMPLETED mission edited last still waits
    # behind an open one (no ranking beyond settled-last), the settled ones
    # keep newest-first among themselves, and sorting the single list (or by
    # created_at) is caught: A is created first but updated last, C the
    # reverse, so any created_at read flips A and C.
    pid = aid('project')
    a, b, c = aid('mission'), aid('mission'), aid('mission')
    put(db, project(pid),
        mission(a, pid, 'COMPLETED', created=T0, updated=T3),
        mission(b, pid, 'EXECUTING', created=T1, updated=T2),
        mission(c, pid, 'COMPLETED', created=T3, updated=T0))
    st = read(db, world_status.status)
    assert [m['id'] for m in st['missions']] == [b, a, c]
    assert [m['state'] for m in st['missions']] == ['EXECUTING', 'COMPLETED', 'COMPLETED']


def test_g8_the_last_inspection_is_the_last_row_written(db):
    # status.py:20-26 — `rows.where` is ORDER BY rowid and `_last_inspection`
    # takes `got[-1]`: the newest row, not the greatest `inspected_at`. The
    # whole dict is compared so a swapped copy (failure for failed_at, dirty
    # for complete) cannot survive either; reading `got[0]`, or sorting by
    # `inspected_at`, names i1 (older row, newer stamp) and fails.
    pid, rid = aid('project'), aid('repository')
    i1, i2 = aid('repository_inspection'), aid('repository_inspection')
    put(db, project(pid), repo(rid, pid),
        insp(i1, rid, state='COMPLETED', inspected_at=T3, complete=True, dirty=False),
        insp(i2, rid, state='FAILED', inspected_at=T0, complete=None, dirty=True,
             failure='repository_missing', attempts=2))
    (r,) = read(db, world_status.status)['projects'][0]['repositories']
    assert r['last_inspection'] == {
        'id': i2, 'state': 'FAILED', 'revision': SHA, 'inspected_at': T0,
        'complete': None, 'dirty': True, 'failure': 'repository_missing', 'attempts': 2}


def test_g9_provisional_is_the_assessment_s_dirty_flag_and_nothing_else(db):
    # status.py:50-52 and 60 — `bool(a.dirty)` of the row `last_inspection_id`
    # names (`provisional=bool(assessed and assessed['provisional'])`). Three
    # readings of that one expression, three repositories: dirty True gives
    # True; a dirty that was never recorded (`None`) is not True; and the
    # newest inspection row being dirty is irrelevant while the repository
    # has no assessment at all — `assessed` is None, and reading the newest
    # row instead of the assessed one would make r3 provisional too.
    pid = aid('project')
    r1, r2, r3 = aid('repository'), aid('repository'), aid('repository')
    i1, i2, i3 = (aid('repository_inspection') for _ in range(3))
    put(db, project(pid),
        repo(r1, pid, last_inspection=i1, findings=[dict(VIOLATED, constraint_id='kno_a')]),
        insp(i1, r1, dirty=True),
        repo(r2, pid, last_inspection=i2, findings=[dict(VIOLATED, constraint_id='kno_b')]),
        insp(i2, r2, dirty=None),
        repo(r3, pid, findings=[dict(VIOLATED, constraint_id='kno_c')]),
        insp(i3, r3, dirty=True))
    assert [d['provisional'] for d in read(db, world_status.status)['drift']] == \
        [True, False, False]


@pytest.mark.parametrize('states,want', [
    ([], None),                                        # status.py:100 `return None`
    (['SCHEDULED', 'RUNNING'], None),                  # a pass "in progress" is not queued
    (['FAILED'], None),                                # a failure earns nothing
    (['FAILED', 'COMPLETED'], 'queued'),
], ids=['no-rows', 'unfinished', 'failed-only', 'one-completed'])
def test_g10_queued_is_earned_only_by_a_completed_inspection(db, states, want):
    # status.py:96-100 — the `state == 'COMPLETED'` guard inside the repository
    # loop and the fall-through `return None`. Weakening the guard (any state,
    # or `!= 'FAILED'`) would tell the owner a pass is queued when every
    # inspection it had ever earned ended in failure.
    pid, rid = aid('project'), aid('repository')
    rows_ = [project(pid), repo(rid, pid)]
    rows_ += [insp(aid('repository_inspection'), rid, state=s) for s in states]
    put(db, *rows_)
    assert read(db, world_status.knowledge_pass, pid) == (
        None if want is None else
        {'state': 'queued', 'route_decision_id': None, 'items': 0, 'reason': None})


# ── the error-shaped paths ───────────────────────────────────────────────────

def test_g11_the_newest_answer_wins_and_an_open_pass_is_running(db):
    # status.py:90-94 — `d = passes[-1]` (rows are ORDER BY rowid: the newest
    # decision answers, not the first), `o = d.outcome or {}` and
    # `o.get('state', 'running')` / `o.get('items', 0)`: a decision whose call
    # has not written its outcome is `running` with zero items — it must not
    # read as completed, and it must not crash on the missing dict. The second
    # project shows a written outcome passing through untouched.
    px, py = aid('project'), aid('project')
    d1, d2, d3 = (aid('route_decision') for _ in range(3))
    put(db, project(px), project(py),
        decision(d1, px, state='completed', items=9),
        decision(d2, px, outcome=None),
        decision(d3, py, state='completed', items=4))
    assert read(db, world_status.knowledge_pass, px) == {
        'state': 'running', 'route_decision_id': d2, 'items': 0, 'reason': None}
    assert read(db, world_status.knowledge_pass, py) == {
        'state': 'completed', 'route_decision_id': d3, 'items': 4, 'reason': None}


def test_g12_the_reason_is_scrubbed_only_when_a_homes_comes_along(db):
    # status.py:95 — `o.get('reason') if homes is None else scrub_text(...)`
    # with the two halves read separately: without homes the stored text is
    # the answer verbatim (a status that "helpfully" scrubbed with no homes
    # would rewrite rows for a reader who asked for the rows); with a home
    # registered, that home does not appear in the answer at all. The home is
    # a plain slash-separated spelling with `shorts` injected and
    # `path_flavour='posix'`, so the matcher behaves identically on win32.
    pid, rid = aid('project'), aid('repository')
    home = '/agents/riley/keys'
    raw = 'pull of %s failed' % home
    put(db, project(pid), repo(rid, pid), insp(aid('repository_inspection'), rid),
        decision(aid('route_decision'), pid, state='failed', reason=raw))
    assert read(db, world_status.status, pid)['projects'][0]['knowledge_pass']['reason'] == raw
    homes = Homes([home], shorts=lambda p: None, platform='posix', path_flavour='posix')
    reason = read(db, world_status.status, pid, homes)['projects'][0]['knowledge_pass']['reason']
    assert home not in reason and 'its home' in reason


def test_g13_as_of_seq_is_the_head_of_the_log_and_survives_a_prune(db):
    # status.py:72 — `'as_of_seq': outbox.head(conn)`: the highest seq ever
    # assigned, not the highest row still present. Retention prunes the log
    # (`retention.py` deletes events) while the digest's cursor contract keeps
    # `head`, so a status that read `MAX(seq) FROM events` would claim the
    # world stopped at 0 after a prune. The double read is the S13 promise the
    # name makes: the same rows, the same answer, byte for byte.
    put(db, project(aid('project')), event('a'), event('b'))
    st = read(db, world_status.status)
    assert st['source'] == 'deterministic' and st['as_of_seq'] == 2
    assert st == read(db, world_status.status)
    clear(db, 'events')
    with db.read() as conn:
        assert st['as_of_seq'] == outbox.head(conn)
    assert read(db, world_status.status)['as_of_seq'] == 2


def test_g14_a_scoped_status_never_names_a_mission_that_is_not_yours(db):
    # status.py:37-38 and 75-77 — the `mine` filter, the `counts` loop keyed on
    # `m['project_id'] == p.entity.id` (a mission with no project of its own is
    # counted by nobody), and the `'unknown_project': [] if project_id is not
    # None else sorted(...)`: the orphan and the unprojected mission surface
    # unscoped — the orphan by id, the unprojected one in no list at all — and
    # vanish completely from the scoped answer, so scoping can never leak that
    # other projects exist.
    pid = aid('project')
    m_own, m_orphan, m_free = aid('mission'), aid('mission'), aid('mission')
    put(db, project(pid),
        mission(m_own, pid, updated=T3),
        mission(m_orphan, aid('project'), updated=T2),
        mission(m_free, None, updated=T1))
    st = read(db, world_status.status)
    assert st['unknown_project'] == [m_orphan]
    assert {m['id'] for m in st['missions']} == {m_own, m_orphan, m_free}
    scoped = read(db, world_status.status, pid)
    assert [m['id'] for m in scoped['missions']] == [m_own]
    assert scoped['unknown_project'] == []
    assert scoped['projects'][0]['missions'] == {'EXECUTING': 1}


@pytest.mark.parametrize('limit,want', [
    (None, 3), (10, 3), (2, 2), (0, 0),
], ids=['default', 'past-the-end', 'cut', 'nothing'])
def test_g15_inspections_are_newest_first_and_the_limit_cuts_exact(db, limit, want):
    # status.py:120-121 — `reversed(got)` (newest first by rowid) and
    # `[:limit]` with its `limit=50` default: `[:limit]` taken before the
    # reverse hands out the OLDEST inspections under a limit, and dropping the
    # slice hands the whole history to a screen. The entries are `view()`s, so
    # the row metadata is there for the reader too.
    pid, rid = aid('project'), aid('repository')
    ids_ = [aid('repository_inspection') for _ in range(3)]
    put(db, project(pid), repo(rid, pid), *[insp(i, rid) for i in ids_])
    got = read(db, world_status.inspections, rid) if limit is None \
        else read(db, world_status.inspections, rid, limit)
    assert [i['id'] for i in got] == ids_[len(ids_) - want:][::-1]   # newest first, cut short
    assert all(set(('id', 'state', 'version', 'updated_at')) <= set(i) for i in got)

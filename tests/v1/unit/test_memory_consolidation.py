"""T-1093 step 1: the graph size ratio (a read, no model call), the text a project's
`context injection` opt-in adds to an execution's prompt, the user's ask for a
consolidation and the knowledge worker's daily cap on it. No model, no CLI."""

import pytest

from archeus.core.application import authorization as A
from archeus.core.application import knowledge as K
from archeus.core.application import outcomes
from archeus.core.context import assemble
from archeus.core.domain import entities, ids
from archeus.core.domain.events import new_event
from archeus.core.domain.values import Ref
from archeus.core.homes import Homes
from archeus.core.knowledge import worker
from archeus.infra.artifacts import store as artifacts
from archeus.infra.db import Database, rows

WS = ids.GLOBAL_WORKSPACE
USER = Ref('user_device', ids.new_id('principal'))
SYSTEM = Ref('system', ids.new_id('principal'))


@pytest.fixture
def db(archeus_home):
    d = Database.open()
    yield d
    d.close()


def put(db, *new):
    def run(tx, **_):
        for r in new:
            tx.insert(r, actor=SYSTEM)
        tx.append(new_event('mission.updated', Ref('mission', ids.new_id('mission')), SYSTEM,
                            payload={}, workspace=WS))
    db.writer.execute(run, {})


def project(db):
    pid = ids.new_id('project')
    put(db, entities.Project(id=pid, workspace_id=WS, name='p'))
    return pid


def item(db, pid, title='t', text='', state='CONFIRMED', type_='ENTITY', source_ref=None):
    k = entities.KnowledgeItem(id=ids.new_id('knowledge_item'), workspace_id=WS, project_id=pid,
                               type=type_, title=title, text=text, state=state,
                               source_ref=source_ref)
    put(db, k)
    return k.id


def inspection(db, pid, payload, state='COMPLETED'):
    rid = ids.new_id('repository')
    sha = artifacts.put(payload) if payload is not None else None
    new = [entities.Repository(id=rid, workspace_id=WS, project_id=pid, path=rid, path_key=rid)]
    if sha:
        new.append(entities.Artifact(id=sha, media_type='application/json', size=len(payload)))
    iid = ids.new_id('repository_inspection')
    new.append(entities.RepositoryInspection(id=iid, repository_id=rid, extractor_version=1,
                                             revision='rev', state=state, payload_sha256=sha))
    put(db, *new)
    return iid


def read(db, fn, *a):
    with db.read() as conn:
        return fn(conn, *a)


# ── the size ratio: reported, never judged ──

def test_the_ratio_is_live_item_bytes_over_the_latest_inspection_payload(db):
    pid = project(db)
    item(db, pid, 'ab', 'cd')
    item(db, pid, 'é', '', state='CANDIDATE')                  # two bytes in UTF-8
    item(db, pid, 'gone', 'x' * 50, state='RETRACTED')          # not live: not counted
    inspection(db, pid, b'x' * 20)
    assert read(db, outcomes.graph_size) == [{'project_id': pid, 'items': 2, 'graph_bytes': 6,
                                              'source_bytes': 20, 'ratio': 0.3}]


def test_a_project_with_no_inspected_source_has_no_ratio_never_zero(db):
    pid = project(db)
    item(db, pid, 'abc')
    inspection(db, pid, None)                                   # COMPLETED, no payload
    inspection(db, pid, b'y' * 10, state='FAILED')
    (got,) = read(db, outcomes.graph_size)
    assert (got['source_bytes'], got['ratio'], got['graph_bytes']) == (None, None, 3)


def test_a_graph_larger_than_its_source_is_reported_not_refused(db):
    pid = project(db)
    item(db, pid, 'x' * 30)
    inspection(db, pid, b'z' * 10)
    assert read(db, outcomes.graph_size)[0]['ratio'] == 3.0
    item(db, pid, 'still accepted')
    assert read(db, outcomes.graph_size)[0]['items'] == 2


# ── what `context injection` adds to a prompt ──

def package(db, pid, *knowledge_ids, extra=()):
    refs = [{'ref': {'kind': 'knowledge_item', 'id': k}} for k in knowledge_ids]
    pkg = entities.ContextPackage(id=ids.new_id('context_package'), workspace_id=WS,
                                  subject_kind='project', subject_id=pid,
                                  items=tuple(refs + list(extra)))
    put(db, pkg)
    return pkg.id


def test_memory_text_is_the_packages_confirmed_items_in_its_order_secrets_redacted(db):
    pid = project(db)
    a = item(db, pid, 'Layering', 'api above core', type_='STANDARD')
    b = item(db, pid, 'Token', 'use sk-' + 'q' * 30)
    c = item(db, pid, 'Unconfirmed', 'never shown', state='CANDIDATE')
    pkg = package(db, pid, b, c, a, extra=[{'ref': {'kind': 'project', 'id': pid}}])
    text = read(db, assemble.memory_text, pkg, Homes([], []))
    assert text.split('\n') == [assemble.MEMORY_HEADER % pkg, '- ENTITY Token: use [redacted]',
                                '- STANDARD Layering: api above core']


def test_memory_text_is_empty_when_nothing_in_the_package_is_confirmed(db):
    pid = project(db)
    pkg = package(db, pid, item(db, pid, 'x', state='CANDIDATE'))
    assert read(db, assemble.memory_text, pkg, Homes([], [])) == ''
    assert read(db, assemble.memory_text, ids.new_id('context_package'), Homes([], [])) == ''


# ── the user's ask ──

def ask(db, actor=USER, **kw):
    return db.writer.execute(K.request_consolidation, dict(kw, actor=actor))


def test_only_a_user_device_asks_for_a_consolidation_within_the_item_bound(db):
    pid = project(db)
    with pytest.raises(A.NotPermitted):
        ask(db, actor=SYSTEM, project_id=pid)
    for bad in (0, K.CONSOLIDATE_MAX + 1, True, '3'):
        with pytest.raises(ValueError):
            ask(db, project_id=pid, max_items=bad)
    got = ask(db, project_id=pid, max_items=K.CONSOLIDATE_MAX)
    with db.read() as conn:
        evs = [e for e in conn.execute("SELECT type, payload FROM events WHERE type = "
                                       "'project.consolidation_requested'")]
    assert got['max_items'] == K.CONSOLIDATE_MAX and len(evs) == 1


# ── the worker: one call per project per day; a call that reached no model is free ──

class Passes:
    def __init__(self):
        self.asked = []

    def consolidate(self, project_id, max_items):
        self.asked.append((project_id, max_items))
        return 'ok'

    def knowledge(self, source_id):
        self.asked.append(('knowledge', source_id))
        return 'ok'

    decisions = lessons = knowledge


def decision(db, pid, state, source_kind='project'):
    put(db, entities.RouteDecision(
        id=ids.new_id('route_decision'), subject=Ref('archeus_call', 'knowledge_extraction'),
        purpose='knowledge_extraction', project_id=pid, source=Ref(source_kind, pid),
        outcome=None if state is None else {'state': state}))


def dispatch(db, pid, at=None):
    with db.read() as conn:
        at = at or rows.where(conn, entities.Project)[0].created_at
    p = Passes()
    w = worker.Knowledge(db, actor=SYSTEM, passes=p)
    return w._consolidate(pid, 7, at), p.asked


def test_the_first_ask_of_the_day_runs_and_one_already_made_that_day_does_not(db):
    pid = project(db)
    assert dispatch(db, pid) == ('consolidate:ok', [(pid, 7)])
    decision(db, pid, 'ok')
    got, asked = dispatch(db, pid)
    assert 'daily cap' in got and asked == []
    assert dispatch(db, pid, at='2999-01-01T00:00:00Z')[1] == [(pid, 7)]


@pytest.mark.parametrize('state', ['gated', 'unavailable'])
def test_a_call_that_reached_no_model_does_not_count_against_the_cap(db, state):
    pid = project(db)
    decision(db, pid, state)
    assert dispatch(db, pid)[1] == [(pid, 7)]


@pytest.mark.parametrize('state', [None, 'failed', 'invalid'])
def test_a_call_in_flight_or_one_that_failed_counts(db, state):
    pid = project(db)
    decision(db, pid, state)
    assert dispatch(db, pid)[1] == []


def test_another_projects_or_another_passs_calls_do_not_count(db):
    pid, other = project(db), project(db)
    decision(db, other, 'ok')
    decision(db, pid, 'ok', source_kind='repository_inspection')
    assert dispatch(db, pid)[1] == [(pid, 7)]


def test_a_gated_consolidation_is_never_run_again_when_headless_use_is_permitted(db):
    pid = project(db)
    decision(db, pid, 'gated')
    p = Passes()
    worker.Knowledge(db, actor=SYSTEM, passes=p)._rerun_gated()
    assert p.asked == []

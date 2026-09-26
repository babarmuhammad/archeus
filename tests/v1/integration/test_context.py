"""P5 context engine over a real database (p5-design-gate §9, C04–C06, C11–C15,
C18): the package the engine records, what it reads from P4's world, what it
leaves out and why, and that assembling one writes nothing. No model."""

import os
import re
from datetime import datetime, timedelta

import pytest

from archeus.core import ports
from archeus.core.application import commands, lifecycle, queries, world
from archeus.core.context import assemble as A
from archeus.core.domain import entities, ids, states
from archeus.core.domain.events import new_event
from archeus.core.domain.values import Ref
from archeus.infra.db import rows
from v1.integration.test_world import NO_CORE_API, Harness
from v1.integration.test_world_http import _register, _wait
from v1.judge.support import FixtureRepo

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
PIN = {'kind': 'framework_pinned'}


@pytest.fixture
def h(db, tmp_path):
    parent = tmp_path / 'repos'
    parent.mkdir()
    return Harness(db, str(parent))


@pytest.fixture
def fixture_repo(tmp_path):
    parent = tmp_path / 'http-repos'
    parent.mkdir()
    return FixtureRepo.create('layered-python', str(parent))


MS = commands.Missions(policy=ports.AllowAllPolicy())


def gather_ready(h, project_id=None, objective='o'):
    """A mission moved to CONTEXT_GATHERING, the state the engine assembles in."""
    mid = h.run(commands.create_mission, title='Dashboard', objective=objective,
                project_id=project_id)['id']
    for t in ('start', 'understood'):
        h.run(MS.fire, mission_id=mid, trigger=t, reason='test')
    return mid


def package(h, kind, sid, **kw):
    return h.read(lambda c: A.assemble(c, kind, sid, **kw))


def by_type(pkg, type_):
    return [i for i in pkg['items'] if i['type'] == type_]


def counts(h):
    return h.read(lambda c: {name: c.execute('SELECT COUNT(*) FROM %s' % name).fetchone()[0]
                             for name in list(rows.TABLES.values()) + ['events']})


# ── C13 the engine records the package ──

def test_c13_context_ready_records_one_immutable_package_linked_from_the_mission(h):
    mid = gather_ready(h)
    out = h.db.writer.execute(MS.context_ready, {'actor': h.system, 'mission_id': mid})
    assert (out['state'], [t['trigger'] for t in out['transitions']]) == (
        'REASONING', ['context_ready'])
    m = h.read(queries.get_mission, mid)
    pkg = m['context_package']
    assert m['context_package_id'] == out['context_package_id'] == pkg['id']
    assert (pkg['version'], pkg['subject_kind'], pkg['subject_id']) == (1, 'mission', mid)
    (item,) = pkg['items']                           # no project: the mission itself
    assert (item['level'], item['ref']['kind'], item['ref']['id']) == ('L0', 'mission', mid)
    assert pkg['missing_information'] and pkg['budget']['used_tokens'] <= 12000
    (e,) = h.events('context_package.created')
    assert (e['subject']['id'], e['visibility'], e['payload']['items']) == (pkg['id'],
                                                                              'system', 1)
    assert h.read(queries.get_context_package, pkg['id']) == pkg


def test_c13_no_package_is_written_outside_context_gathering(h):
    mid = h.run(commands.create_mission, title='M', objective='o')['id']
    before = counts(h)
    with pytest.raises(lifecycle.IllegalTrigger):
        h.db.writer.execute(MS.context_ready, {'actor': h.system, 'mission_id': mid})
    assert counts(h) == before


def test_c13_nothing_edits_a_package_once_written():
    """Immutable by construction: no state machine, and the only write of a
    ContextPackage anywhere is the insert in `context_ready`."""
    assert entities.ContextPackage._STATE is None
    assert 'context_package' not in states.MACHINES
    built, edited = [], []
    for d, _dirs, files in os.walk(os.path.join(ROOT, 'archeus')):
        for f in files:
            if f.endswith('.py'):
                path = os.path.relpath(os.path.join(d, f), ROOT).replace('\\', '/')
                src = open(os.path.join(d, f), encoding='utf-8').read()
                built += [path] * src.count('ContextPackage(id=')
                if re.search(r'(update|transition)\(\s*entities\.ContextPackage', src):
                    edited.append(path)
    assert built == ['archeus/core/application/commands.py'] and edited == []


# ── C11 determinism, C12 read-only ──

def test_c11_c12_the_same_snapshot_gives_the_same_package_and_assembling_writes_nothing(h):
    repo = h.register('layered-python', [NO_CORE_API])
    h.pump()
    mid = gather_ready(h, repo.project_id, objective='keep core away from the api layer')
    before = counts(h)
    first = package(h, 'mission', mid)
    assert package(h, 'mission', mid) == first
    assert package(h, 'project', repo.project_id, query='api') == package(
        h, 'project', repo.project_id, query='api')
    assert counts(h) == before


# ── C14 P4's world at L1 ──

def test_c14_the_project_inspection_and_drift_are_read_from_p4(h):
    repo = h.register('layered-python', [NO_CORE_API])
    h.pump()
    mid = gather_ready(h, repo.project_id, objective='work on app core')
    pkg = package(h, 'mission', mid)
    assert [i['level'] for i in pkg['items'][:1]] == ['L0']
    (proj,) = by_type(pkg, 'PROJECT')
    (insp,) = by_type(pkg, 'INSPECTION')
    last = h.repo(repo.repository_id).last_inspection_id
    assert (proj['ref']['id'], proj['level']) == (repo.project_id, 'L1')
    assert (insp['source_ref'], insp['freshness'], insp['store']) == (last, 'current', 'state')
    assert not by_type(pkg, 'DRIFT')
    (arch,) = by_type(pkg, 'ARCHITECTURE')
    assert (arch['store'], arch['level'], arch['signals']['auth']) == ('knowledge', 'L1', 1.0)

    repo.commit('core imports api', {'app/core/x.py': 'import app.api\n'})
    h.pump()
    (drift,) = by_type(package(h, 'mission', mid), 'DRIFT')
    assert drift['ref'] == {'kind': 'repository', 'id': repo.repository_id,
                            'version': drift['ref']['version']}
    assert '1 architecture constraint(s) violated' in drift['reason']

    # a new constraint makes the assessment STALE: labelled, and ranked lower
    h.run(world.declare_constraint, project_id=repo.project_id, statement='models exist',
          kind='module_exists', spec={'path': 'app/core/models.py'})
    stale = package(h, 'mission', mid)
    for t in ('DRIFT', 'INSPECTION'):
        (i,) = by_type(stale, t)
        assert (i['freshness'], i['signals']['stale']) == ('stale', 1.0), t
        assert 'stale' in i['reason']


def test_c14_a_repository_never_inspected_is_a_stated_gap(h, monkeypatch):
    repo = h.register('layered-python')
    mid = gather_ready(h, repo.project_id)
    pkg = package(h, 'mission', mid)
    assert not by_type(pkg, 'INSPECTION')
    assert ['%s has no completed inspection' % h.repo(repo.repository_id).path] == [
        g for g in pkg['missing_information'] if 'inspection' in g]


# ── C04 superseded and unconfirmed knowledge ──

def _knowledge(tx, *, actor, project_id, title, supersedes_id=None, confirm=True):
    k = entities.KnowledgeItem(id=ids.new_id('knowledge_item'), workspace_id=ids.GLOBAL_WORKSPACE,
                               type='DECISION', title=title, origin='explicit',
                               project_id=project_id, supersedes_id=supersedes_id)
    tx.insert(k, actor=actor)
    tx.append(new_event('knowledge_item.created', Ref('knowledge_item', k.id), actor,
                        project=project_id))
    if confirm:
        lifecycle.fire(tx, entities.KnowledgeItem, k.id, 'confirm', actor=actor, reason='test')
    if supersedes_id:
        lifecycle.fire(tx, entities.KnowledgeItem, supersedes_id, 'superseded', actor=actor,
                       reason='test')
    return k.id


def test_c04_superseded_and_unconfirmed_items_are_excluded_with_the_reason(h):
    repo = h.register('layered-python')
    pid = repo.project_id
    old = h.run(_knowledge, project_id=pid, title='charts use library A')
    new = h.run(_knowledge, project_id=pid, title='charts use library B', supersedes_id=old)
    cand = h.run(_knowledge, project_id=pid, title='maybe dark mode', confirm=False)
    pkg = package(h, 'project', pid)
    assert [i['ref']['id'] for i in by_type(pkg, 'DECISION')] == [new]
    got = {e['ref']['id']: (e['freshness'], e['reason']) for e in pkg['excluded']}
    assert got[old] == ('superseded', 'superseded by %s' % new)
    assert got[cand] == ('current', 'not confirmed (a candidate)')


# ── C06 conflicts through the real constraint write ──

def test_c06_two_confirmed_pins_of_one_package_are_a_conflict_and_the_newer_wins(h):
    repo = h.register('layered-python')
    first = h.run(world.declare_constraint, project_id=repo.project_id, statement='pydantic 1',
                  kind='framework_pinned', spec={'package': 'pydantic', 'version': '1.10'})
    second = h.run(world.declare_constraint, project_id=repo.project_id, statement='pydantic 2',
                   kind='framework_pinned', spec={'package': 'pydantic', 'version': '2.7'})
    a, b = first['knowledge_item']['id'], second['knowledge_item']['id']
    (c,) = package(h, 'project', repo.project_id)['conflicts']
    assert (c['items'], c['preferred']) == ([a, b], b)


# ── C18 history at L3 ──

def test_c18_recent_project_events_are_history_and_older_ones_are_not(h):
    repo = h.register('layered-python')
    pid = repo.project_id
    head_at = h.read(A.snapshot)[1]
    old_at = (datetime.fromisoformat(head_at.replace('Z', '+00:00')) - timedelta(days=8)
              ).isoformat(timespec='milliseconds').replace('+00:00', 'Z')

    def old_event(tx, *, actor):
        tx.append(new_event('project.changed', Ref('project', pid), actor, project=pid,
                            at=old_at, payload={'why': 'long ago'}))
    h.db.writer.execute(old_event, {'actor': h.user})
    h.run(world.declare_constraint, project_id=pid, statement='a later fact')   # newest event
    mid = gather_ready(h, pid)
    hist = [i for i in package(h, 'mission', mid)['items'] if i['store'] == 'history']
    assert hist and all(i['level'] == 'L3' for i in hist)
    assert all(i['observed_at'] >= old_at and i['observed_at'] != old_at for i in hist)
    assert mid not in {i['source_ref'] for i in hist}       # the subject is L0, not history
    assert all(i['ref']['kind'] == 'event' and i['ref']['seq'] for i in hist)


# ── C15 the routes ──

def test_c15_preview_writes_nothing_and_a_recorded_package_is_readable(tc, fixture_repo):
    pid, _rid = _register(tc, fixture_repo, [NO_CORE_API])
    _wait(lambda: tc.http('GET', '/v1/health').json()['world']['pending'] == 0,
          what='the world to settle')
    events = lambda: tc.http('GET', '/v1/events?limit=1000').json()['events']  # noqa: E731
    before = events()[-1]['seq']
    r = tc.http('POST', '/v1/context/preview',
                body={'subject': {'kind': 'project', 'id': pid}, 'query': 'core api',
                      'levels': ['L1'], 'limit_tokens': 500})
    assert r.status == 200, r.body
    pkg = r.json()
    assert pkg['levels'] == ['L1'] and pkg['budget']['limit_tokens'] == 500
    assert all(i['reason'] and i['source_kind'] for i in pkg['items'])
    # The world worker (Core's system principal) may still append after
    # `pending` reads 0; the preview writes nothing of its own, so nothing new
    # is by the device that asked, and no package was recorded.
    after = [e for e in events() if e['seq'] > before]
    assert all(e['actor']['kind'] == 'system' for e in after), after
    assert not [e for e in after if e['type'] == 'context_package.created']

    mid = tc.http('POST', '/v1/missions', body={'title': 'M', 'objective': 'o', 'project_id': pid,
                                                'idempotency_key': 'm1'}).json()['id']
    got = _wait(lambda: tc.http('GET', '/v1/missions/%s' % mid).json()['context_package'],
                what='the engine to record the package')
    one = tc.http('GET', '/v1/context/%s' % got['id'])
    assert one.status == 200 and one.json() == got
    assert tc.http('GET', '/v1/context/ctx_01J00000000000000000000000').status == 404
    bad = tc.http('POST', '/v1/context/preview', body={'subject': {'kind': 'task', 'id': 'x'}})
    assert bad.status == 400

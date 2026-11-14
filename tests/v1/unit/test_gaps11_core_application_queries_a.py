"""T-1417: the uncovered branches of `archeus/core/application/queries.py` lines 24-135,
the public scrubbing of verification, review and mission bodies: _public_verification,
_public_review, _public_mission, _of_mission, list_verifications, get_verification,
list_reviews and list_missions.

Ten selected probes, denial and fail-closed first, then boundaries, then error paths:

1  _public_verification 25-28   account_ref leaves performed_by, a None performed_by stays None,
                                the other identity keys stay
                                -> test_public_verification_drops_only_account_ref
2  _public_verification 29-31   the exact authored paths handed to system_value
                                -> test_public_verification_scrubs_exactly_the_authored_paths
3  _public_review 35-36         each REVIEW_LIST plus summary and reviewer, nothing else
                                -> test_public_review_scrubs_the_review_lists_and_text
4  _public_mission 47-48        planning_blocked None keeps the same object; otherwise replaced
                                -> test_a_mission_without_planning_blocked_is_returned_as_is
                                -> test_planning_blocked_is_scrubbed_and_the_rest_kept
5  _of_mission 72-75            only this mission's task and plan ids
                                -> test_of_mission_holds_only_this_missions_tasks_and_plans
6  list_verifications 80-81     an unknown mission is NotFound before any verification read
                                -> test_list_verifications_refuses_an_unknown_mission_first
7  list_verifications 88-91     a subject of this mission or of its tasks, sorted by (created_at, id)
                                -> test_list_verifications_keeps_only_this_missions_subjects
8  get_verification 101-104     evidence available only when the hash exists in the store
                                -> test_evidence_is_available_only_when_the_store_holds_it
9  list_missions 126-132        unknown state ValueError; unknown project NotFound; filters exact
                                -> test_list_missions_refuses_an_unknown_state_and_project
                                -> test_list_missions_filters_by_state_and_project_only_when_given
10 list_reviews 109-113         unknown mission NotFound; each review scrubbed with homes resolved once
                                -> test_list_reviews_resolves_homes_once_and_scrubs_each

No database and no artifact store is touched: rows.get/rows.where are replaced, system_value
and _homes are recorded or fixed, and store.path_for points into the test's own tmp_path.
"""

from types import SimpleNamespace

import pytest

from archeus.core.application import queries
from archeus.core.domain import entities, states
from archeus.infra.artifacts import store
from archeus.infra.db import rows
from archeus.infra.db.writer import NotFound


HOMES = ('homes-token',)


class Recorder:
    def __init__(self):
        self.calls = []


@pytest.fixture
def system(monkeypatch):
    """system_value records its arguments and returns its input unchanged."""
    rec = Recorder()

    def fake_system_value(value, homes, authored=()):
        rec.calls.append({'value': value, 'homes': homes, 'authored': authored})
        return value

    monkeypatch.setattr(queries, 'system_value', fake_system_value)
    monkeypatch.setattr(queries, '_homes', lambda conn, homes: HOMES)
    return rec


@pytest.fixture
def db(monkeypatch):
    """rows.get / rows.where answered from a dict of fixtures; every call is logged."""
    state = {'get': {}, 'where': {}, 'get_calls': [], 'where_calls': []}

    def fake_get(conn, cls, eid):
        state['get_calls'].append((cls, eid))
        return state['get'].get((cls, eid))

    def fake_where(conn, cls, **eq):
        state['where_calls'].append((cls, dict(eq)))
        out = state['where'].get(cls, [])
        return [r for r in out if all(getattr(r.entity, k, None) == v for k, v in eq.items())]

    monkeypatch.setattr(rows, 'get', fake_get)
    monkeypatch.setattr(rows, 'where', fake_where)
    return state


def _row(entity, **meta):
    return SimpleNamespace(entity=entity, **meta)


# ── _public_verification (24-31) ────────────────────────────────────────────

def test_public_verification_drops_only_account_ref(system):
    body = {'id': 'v1', 'performed_by': {'harness_id': 'h', 'account_id': 'a',
                                         'account_ref': 'secret-ref'}}
    out = queries._public_verification(body, HOMES)
    assert out['performed_by'] == {'harness_id': 'h', 'account_id': 'a'}
    assert out['id'] == 'v1'
    assert body['performed_by']['account_ref'] == 'secret-ref'       # input not mutated


def test_public_verification_leaves_a_none_performed_by_none(system):
    out = queries._public_verification({'id': 'v2', 'performed_by': None}, HOMES)
    assert out['performed_by'] is None


def test_public_verification_scrubs_exactly_the_authored_paths(system):
    queries._public_verification({'id': 'v3', 'performed_by': None}, HOMES)
    (call,) = system.calls
    assert call['homes'] == HOMES
    assert call['authored'] == (('checks', 'name'), ('checks', 'argv'), ('checks', 'files'),
                                ('criteria', 'text'), ('note',), ('workspace',),
                                ('evidence', 'check'))


# ── _public_review (34-36) ──────────────────────────────────────────────────

def test_public_review_scrubs_the_review_lists_and_text(system):
    queries._public_review({'id': 'r1', 'summary': 's'}, HOMES)
    (call,) = system.calls
    expected = {(k,) for k in entities.REVIEW_LISTS} | {('summary',), ('reviewer',)}
    assert set(call['authored']) == expected
    assert len(call['authored']) == len(expected)
    assert ('mission_id',) not in call['authored'] and ('id',) not in call['authored']


# ── _public_mission (45-48) ─────────────────────────────────────────────────

def test_a_mission_without_planning_blocked_is_returned_as_is(system):
    mission = {'id': 'm1', 'planning_blocked': None}
    assert queries._public_mission(object(), mission, HOMES) is mission
    assert system.calls == []


def test_planning_blocked_is_scrubbed_and_the_rest_kept(system):
    mission = {'id': 'm1', 'state': 'PLANNING', 'planning_blocked': {'kind': 'policy'}}
    out = queries._public_mission(object(), mission, HOMES)
    assert out is not mission
    assert out == {'id': 'm1', 'state': 'PLANNING', 'planning_blocked': {'kind': 'policy'}}
    assert system.calls == [{'value': {'kind': 'policy'}, 'homes': HOMES, 'authored': ()}]
    assert mission['planning_blocked'] == {'kind': 'policy'}


# ── _of_mission (72-75) ─────────────────────────────────────────────────────

def test_of_mission_holds_only_this_missions_tasks_and_plans(db):
    db['where'][entities.Task] = [_row(SimpleNamespace(id='t1', mission_id='m1')),
                                  _row(SimpleNamespace(id='t2', mission_id='m2'))]
    db['where'][entities.Plan] = [_row(SimpleNamespace(id='p1', mission_id='m1')),
                                  _row(SimpleNamespace(id='p2', mission_id='m2'))]
    tasks, plans = queries._of_mission(object(), 'm1')
    assert tasks == {'t1'}
    assert plans == {'p1'}


# ── list_verifications (78-91) ──────────────────────────────────────────────

def test_list_verifications_refuses_an_unknown_mission_first(db, monkeypatch):
    monkeypatch.setattr(queries, '_homes', lambda conn, homes: pytest.fail('homes read first'))
    with pytest.raises(NotFound):
        queries.list_verifications(object(), 'missing')
    assert db['where_calls'] == []


def test_list_verifications_keeps_only_this_missions_subjects(db, monkeypatch):
    monkeypatch.setattr(queries, '_homes', lambda conn, homes: HOMES)
    monkeypatch.setattr(queries, '_public_verification', lambda body, homes: body)
    mission = SimpleNamespace(id='m1')
    db['get'][(entities.Mission, 'm1')] = _row(mission)
    db['where'][entities.Task] = [_row(SimpleNamespace(id='t1', mission_id='m1'))]
    db['where'][entities.Plan] = [_row(SimpleNamespace(id='p1', mission_id='m1'))]

    def v(id_, kind, sid, created):
        return _row(SimpleNamespace(id=id_, plan_id='p1',
                                    subject=SimpleNamespace(kind=kind, id=sid)),
                    version=1, created_at=created, updated_at=created)

    db['where'][entities.Verification] = [
        v('v-late', 'task', 't1', '2026-01-02'),
        v('v-mission', 'mission', 'm1', '2026-01-01'),
        v('v-tie-b', 'task', 't1', '2026-01-02'),
        v('v-other-task', 'task', 't9', '2026-01-01'),
        v('v-other-mission', 'mission', 'm2', '2026-01-01'),
    ]
    monkeypatch.setattr(queries, 'view', lambda r: {'id': r.entity.id,
                                                    'created_at': r.created_at})
    out = queries.list_verifications(object(), 'm1')
    assert out['mission_id'] == 'm1'
    assert [x['id'] for x in out['verifications']] == ['v-mission', 'v-late', 'v-tie-b']


# ── get_verification (94-105) ───────────────────────────────────────────────

def test_evidence_is_available_only_when_the_store_holds_it(db, monkeypatch, tmp_path):
    present = 'a' * 64
    absent = 'b' * 64
    (tmp_path / present).write_text('out', encoding='utf-8')
    asked = []

    def path_for(sha):
        asked.append(sha)
        return str(tmp_path / sha)

    monkeypatch.setattr(store, 'path_for', path_for)
    monkeypatch.setattr(queries, 'view', lambda r: {'id': 'v1'})
    monkeypatch.setattr(queries, '_public_verification', lambda body, homes: body)
    monkeypatch.setattr(queries, '_homes', lambda conn, homes: HOMES)
    checks = [{'name': 'unit', 'output_sha256': present},
              {'name': 'lint', 'output_sha256': absent},
              {'name': 'manual', 'output_sha256': None}]
    db['get'][(entities.Verification, 'v1')] = _row(SimpleNamespace(checks=checks))
    out = queries.get_verification(object(), 'v1')
    assert out['evidence'] == [
        {'check': 'unit', 'output_sha256': present, 'available': True},
        {'check': 'lint', 'output_sha256': absent, 'available': False},
        {'check': 'manual', 'output_sha256': None, 'available': False},
    ]
    assert asked == [present, absent]                    # no path asked for a None hash


def test_get_verification_refuses_an_unknown_id(db):
    with pytest.raises(NotFound):
        queries.get_verification(object(), 'nope')


# ── list_missions (123-133) ─────────────────────────────────────────────────

def test_list_missions_refuses_an_unknown_state_and_project(db, monkeypatch):
    monkeypatch.setattr(queries, '_public_mission', lambda conn, m, homes: m)
    with pytest.raises(ValueError):
        queries.list_missions(object(), state='NOT_A_STATE')
    with pytest.raises(NotFound):
        queries.list_missions(object(), project_id='missing-project')
    assert db['where_calls'] == []


def test_list_missions_filters_by_state_and_project_only_when_given(db, monkeypatch):
    monkeypatch.setattr(queries, 'view', lambda r: dict(r.entity.__dict__))
    monkeypatch.setattr(queries, '_public_mission', lambda conn, m, homes: m)
    state = 'EXECUTING'
    assert state in states.states('mission')
    db['get'][(entities.Project, 'p1')] = _row(SimpleNamespace(id='p1'))
    db['where'][entities.Mission] = [_row(SimpleNamespace(id='m1', state=state, project_id='p1'))]

    queries.list_missions(object())
    queries.list_missions(object(), state=state)
    queries.list_missions(object(), project_id='p1')
    queries.list_missions(object(), state=state, project_id='p1')
    assert [eq for cls, eq in db['where_calls'] if cls is entities.Mission] == [
        {}, {'state': state}, {'project_id': 'p1'}, {'state': state, 'project_id': 'p1'}]


# ── list_reviews (108-113) ──────────────────────────────────────────────────

def test_list_reviews_resolves_homes_once_and_scrubs_each(db, monkeypatch):
    resolved = []

    def homes_once(conn, homes):
        resolved.append(homes)
        return HOMES

    scrubbed = []
    monkeypatch.setattr(queries, '_homes', homes_once)
    monkeypatch.setattr(queries, '_public_review', lambda body, homes: scrubbed.append((body, homes)) or body)
    monkeypatch.setattr(queries, 'view', lambda r: {'id': r.entity.id})
    db['get'][(entities.Mission, 'm1')] = _row(SimpleNamespace(id='m1'))
    db['where'][entities.Review] = [_row(SimpleNamespace(id='r1', mission_id='m1')),
                                    _row(SimpleNamespace(id='r2', mission_id='m1'))]
    out = queries.list_reviews(object(), 'm1', homes='lazy')
    assert out == {'mission_id': 'm1', 'reviews': [{'id': 'r1'}, {'id': 'r2'}]}
    assert resolved == ['lazy']
    assert scrubbed == [({'id': 'r1'}, HOMES), ({'id': 'r2'}, HOMES)]


def test_list_reviews_refuses_an_unknown_mission(db):
    with pytest.raises(NotFound):
        queries.list_reviews(object(), 'missing')
    assert db['where_calls'] == []

"""T-1429: the artifact and task reads of archeus/core/application/executions.py, lines
1275-1334 at tip 026ea58e: artifacts_of, entity, checkpoints, of_task. Ranked, denial
and fail-closed first:

1. 1280 artifacts_of: a record of the same task made by ANOTHER execution is excluded.
2. 1277-1280 artifacts_of: returns exactly artifact_id, kind, label (no mission, task or producer).
3. 1279 artifacts_of: records come back in insertion (rowid) order.
4. 1276 artifacts_of: an execution with no records returns [].
5. 1323-1324 of_task: an unknown task raises NotFound and no execution is read.
6. 1327 of_task: executions of other tasks are not included.
7. 1329-1330 of_task: hook_token_hash and broker_token_hash never leave the module.
8. 1331 of_task: each dict carries 'context' from pressure.view of the row's entity.
9. 1325-1333 of_task: a task with no executions returns [] and pressure is not called.
10. 1310-1314 checkpoints: an unknown execution raises NotFound before any Checkpoint read,
    and a known execution with none returns [].

Fakes: rows.where/rows.get in archeus.infra.db.rows (the module executions.py imports
as `rows`) over in-memory lists; queries.view and pressure.view replaced by fixed dicts.
"""

import types

import pytest

from archeus.core.application import executions, lifecycle
from archeus.core.application import queries
from archeus.core.execution import pressure
from archeus.infra.db import rows


class Row:
    def __init__(self, entity, version=1):
        self.entity, self.version = entity, version


def _artifact(aid, kind, label, task_id, produced_by):
    return Row(types.SimpleNamespace(artifact_id=aid, kind=kind, label=label, task_id=task_id,
                                     mission_id='mission_1', produced_by=types.SimpleNamespace(
                                         id=produced_by)))


def _execution(eid, task_id):
    return types.SimpleNamespace(id=eid, task_id=task_id)


class Store:
    """Insertion-ordered tables; where() filters on the keyword equalities it is given."""

    def __init__(self):
        self.tables = {}
        self.where_calls = []

    def add(self, cls, row):
        self.tables.setdefault(cls, []).append(row)
        return row

    def where(self, conn, cls, **eq):
        self.where_calls.append(cls)
        return [r for r in self.tables.get(cls, [])
                if all(getattr(r.entity, k, object()) == v for k, v in eq.items())]

    def get(self, conn, cls, entity_id):
        for r in self.tables.get(cls, []):
            if r.entity.id == entity_id:
                return r
        return None


@pytest.fixture
def store(monkeypatch):
    s = Store()
    monkeypatch.setattr(rows, 'where', s.where)
    monkeypatch.setattr(rows, 'get', s.get)
    monkeypatch.setattr(pressure, 'view', lambda e: {'pressure_for': e.id})
    monkeypatch.setattr(queries, 'view', lambda r: {
        'id': r.entity.id, 'hook_token_hash': 'h', 'broker_token_hash': 'b'})
    return s


def test_artifacts_of_excludes_records_another_execution_of_the_same_task_made(store):
    e1 = _execution('exec_1', 'task_1')
    store.add(executions.entities.ArtifactRecord, _artifact('a1', 'file', 'f', 'task_1', 'exec_1'))
    store.add(executions.entities.ArtifactRecord, _artifact('a2', 'file', 'g', 'task_1', 'exec_2'))
    assert [r['artifact_id'] for r in executions.artifacts_of(None, e1)] == ['a1']


def test_artifacts_of_returns_exactly_three_keys(store):
    e1 = _execution('exec_1', 'task_1')
    store.add(executions.entities.ArtifactRecord, _artifact('a1', 'diff', 'lbl', 'task_1', 'exec_1'))
    [got] = executions.artifacts_of(None, e1)
    assert set(got) == {'artifact_id', 'kind', 'label'}
    assert got == {'artifact_id': 'a1', 'kind': 'diff', 'label': 'lbl'}


def test_artifacts_of_keeps_insertion_order(store):
    e1 = _execution('exec_1', 'task_1')
    for aid in ('a2', 'a1', 'a3'):
        store.add(executions.entities.ArtifactRecord, _artifact(aid, 'file', aid, 'task_1',
                                                                'exec_1'))
    assert [r['artifact_id'] for r in executions.artifacts_of(None, e1)] == ['a2', 'a1', 'a3']


def test_artifacts_of_an_execution_with_no_records_is_empty(store):
    assert executions.artifacts_of(None, _execution('exec_9', 'task_1')) == []


def test_of_task_unknown_task_refuses_before_reading_executions(store):
    with pytest.raises(lifecycle.NotFound):
        executions.of_task(None, 'task_missing')
    assert executions.entities.Execution not in store.where_calls


def test_of_task_excludes_executions_of_other_tasks(store):
    store.add(executions.entities.Task, Row(types.SimpleNamespace(id='task_1')))
    store.add(executions.entities.Execution, Row(_execution('exec_1', 'task_1')))
    store.add(executions.entities.Execution, Row(_execution('exec_2', 'task_2')))
    assert [d['id'] for d in executions.of_task(None, 'task_1')] == ['exec_1']


def test_of_task_never_returns_the_token_hashes(store):
    store.add(executions.entities.Task, Row(types.SimpleNamespace(id='task_1')))
    store.add(executions.entities.Execution, Row(_execution('exec_1', 'task_1')))
    [d] = executions.of_task(None, 'task_1')
    assert 'hook_token_hash' not in d and 'broker_token_hash' not in d


def test_of_task_carries_the_pressure_context_of_each_execution(store):
    store.add(executions.entities.Task, Row(types.SimpleNamespace(id='task_1')))
    store.add(executions.entities.Execution, Row(_execution('exec_1', 'task_1')))
    [d] = executions.of_task(None, 'task_1')
    assert d['context'] == {'pressure_for': 'exec_1'}


def test_of_task_with_no_executions_is_empty_and_never_asks_pressure(store, monkeypatch):
    asked = []
    monkeypatch.setattr(pressure, 'view', lambda e: asked.append(e) or {})
    store.add(executions.entities.Task, Row(types.SimpleNamespace(id='task_1')))
    assert executions.of_task(None, 'task_1') == []
    assert asked == []


def test_checkpoints_unknown_execution_refuses_before_any_checkpoint_read(store):
    with pytest.raises(lifecycle.NotFound):
        executions.checkpoints(None, 'exec_missing')
    assert executions.entities.Checkpoint not in store.where_calls


def test_checkpoints_known_execution_with_none_is_empty(store):
    store.add(executions.entities.Execution, Row(_execution('exec_1', 'task_1')))
    assert executions.checkpoints(None, 'exec_1') == []

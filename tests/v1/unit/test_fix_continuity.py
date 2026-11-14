from types import SimpleNamespace as NS

from archeus.core.sessions import continuity as C


def _row(**kw):
    return NS(entity=NS(**kw))


def _world(monkeypatch, tasks, checkpoints):
    mission = _row(id='m', title='t', state='ACTIVE')
    plan = _row(id='p', plan_version=1)
    data = {'Task': tasks, 'Checkpoint': checkpoints}

    class Rows:
        get = staticmethod(lambda conn, cls, i: mission)
        where = staticmethod(lambda conn, cls, **kw: data.get(cls.__name__, []))

    monkeypatch.setattr(C, 'rows', Rows)
    monkeypatch.setattr(C, 'active_plan', lambda conn, mid: plan)
    monkeypatch.setattr(C, '_homes', lambda conn, homes: None)
    monkeypatch.setattr(C, 'system_value', lambda v, h: v)


def test_tasks_and_open_problems_read_in_plan_order_past_ten(monkeypatch):
    tasks = [_row(id='k%d' % i, key='t%d' % i, title='x', state='FAILED') for i in range(1, 13)]
    cps = [_row(task_id='k%d' % i, execution_id='e', trigger='crash', open_problems=[],
                next_action='', id='c%d' % i) for i in range(1, 13)]
    _world(monkeypatch, tasks, cps)
    state, _ = C.mission_state(None, 'm')
    want = ['t%d' % i for i in range(1, 13)]
    assert [t['key'] for t in state['tasks']] == want
    assert [p['task_key'] for p in C.open_problems(None, 'm')] == want

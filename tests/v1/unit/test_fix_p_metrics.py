"""`context_tokens_per_task_kind` on rows as the database stores them: a route
decision's `task_id` is a promoted column, so its body does not carry it."""

from .test_gaps_core_metrics import db, figures, mission, pkg, plan, put, route, task  # noqa: F401


def test_a_task_route_decision_is_read_by_its_task_id_column(db):  # noqa: F811
    put(db, mission('m1'), plan('m1', 'p1', 1, {}), task('t1', 'p1', 'm1', {'kind': 'code'}),
        pkg('c1', {'budget': {'used_tokens': 700}}),
        route('r1', {'context_package_id': 'c1'}, task_id='t1'))
    assert figures(db)['context_tokens_per_task_kind'] == {'code': 700}

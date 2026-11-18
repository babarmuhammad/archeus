"""The continuation of a checkpoint hand-off (p12-design-gate §10.1): the next
execution of a task whose execution just handed off, created in the same
transaction as the hand-off's end.

It is an ordinary execution: P9 `check_dispatch` judges the task now, P10
`route` chooses where it runs (affinity dropped when the hand-off was an
account change — `resources._affinity` reads the ended execution's stop
reason), and `work.new_execution` writes it in INTENT. The task stays RUNNING
and the mission EXECUTING. If P9 no longer covers the task, the plan it ran
under is no longer in force, or P10 finds nothing to run it on, there is no
continuation: the task goes back to READY uncharged, and the ordinary dispatch
asks, blocks or waits exactly as it would for any task.
"""

from ..application import authorization, lifecycle
from ..application.commands import active_plan
from ..application.work import PolicyDenied, new_execution
from ..domain import entities
from ..domain.values import Ref


def continue_task(tx, *, actor, policy, missions, router, execution, now):
    """{'execution_id'} of the continuation, or {'refused': why}."""
    e = execution
    m = lifecycle.load(tx, entities.Mission, e.mission_id).entity
    t = lifecycle.load(tx, entities.Task, e.task_id).entity
    why = None
    prow = active_plan(tx.conn, m.id)
    if m.state != 'EXECUTING':
        why = 'the mission is %s' % m.state
    elif prow is None or prow.entity.id != e.plan_id or prow.entity.state != 'APPROVED':
        why = 'the plan it ran under is no longer in force'
    if why is None:
        plan = prow.entity
        try:
            auth = authorization.check_dispatch(tx, actor=actor, policy=policy,
                                                missions=missions, mission=m, plan=plan, task=t)
        except PolicyDenied as denied:
            auth = {'outcome': 'denied (%s)' % denied}
        if auth['outcome'] != 'covered':
            why = 'its authorisation no longer covers it (%s)' % auth['outcome']
    if why is None:
        route = router.route(Ref('task', t.id), now, tx=tx, actor=actor, authorization=auth,
                             mission=m, plan=plan, task=t)
        result = route.result or ('selected' if route.selected else 'blocked')
        if result not in ('selected', 'fallback'):
            why = 'the resource router has nowhere to continue it (%s)' % result
    if why is not None:
        if t.state == 'RUNNING':
            lifecycle.fire(tx, entities.Task, t.id, 'execution_failed_retry', actor=actor,
                           reason='execution %s handed off; no continuation: %s; not charged'
                           % (e.id, why))
        return {'refused': why, 'execution_id': None}
    rd = route.id if route.decided_by == 'router' else None
    return dict(new_execution(tx, actor, m, plan, t, route, auth, rd, handoff_from=e.id),
                refused=None)

"""A mission's trace (P21 slice C; p21-design-gate D3, D14): what Core already
recorded, read together. The mission's events in order, each with its
`cause_chain`; the policy and route decisions about it; and per execution its
checkpoints and its output folded into lanes. A lane is a transcript sidechain
(the tool call that spawned a subagent; `main` for the conversation itself),
and each tool call is paired with its result inside its lane. A read: nothing
here writes, and the output is the same redacted read the execution's own tab
serves. A call's input is not carried: the trace names the tool, never what was
typed into it."""

from ...infra.db import rows
from ..domain import entities
from ..execution import output
from . import attention, executions
from .public import public_output
from .queries import _homes, list_policy_decisions, route_decisions

MAX_EVENTS = 1000
#: the newest executions read per trace: each costs an output read (and a live
#: inspect while it runs), so a mission with many retries stays one bounded read
MAX_EXECUTIONS = 50
MAIN = 'main'
_TEXT = 500


def lanes(events):
    """[{lane, from, steps}] in order of first appearance. A step is
    `{i, type, ...}`; a call gets `result` (its result's index) and a result
    `call` once both are seen; `from` is the index of the call that spawned a
    sidechain lane (None for `main`, or when the spawning call is not read)."""
    out, calls = {}, {}
    for i, e in enumerate(events):
        t = e.get('type')
        if t not in ('assistant', 'tool', 'tool_result'):
            continue
        step = {'i': i, 'type': t}
        if t == 'assistant':
            step['text'] = (e.get('text') or '')[:_TEXT]
        elif t == 'tool':
            step['name'] = e.get('name')
            if e.get('id'):
                calls[e['id']] = step
        else:
            step['is_error'] = bool(e.get('is_error'))
            call = calls.get(e.get('tool_use_id'))
            if call is not None:
                call['result'], step['call'] = i, call['i']
        out.setdefault(e.get('lane') or MAIN, []).append(step)
    return [{'lane': k, 'from': None if k == MAIN else (calls[k]['i'] if k in calls else None),
             'steps': v} for k, v in out.items()]


def trace(conn, mission_id, registry, *, homes=None):
    """The trace of *mission_id* (NotFound when there is no such mission)."""
    homes = _homes(conn, homes)
    t = attention.timeline(conn, mission_id, limit=MAX_EVENTS, homes=homes)
    execs, rs = [], sorted(rows.where(conn, entities.Execution, mission_id=mission_id),
                           key=lambda r: r.entity.id)
    for r in rs[-MAX_EXECUTIONS:]:
        e = r.entity
        adapter = registry.get(e.harness_id) if e.harness_id in registry.ids() else None
        o = public_output(output.read(e, adapter), homes)
        execs.append({'id': e.id, 'task_id': e.task_id, 'state': e.state, 'attempt': e.attempt,
                      'route_decision_id': e.route_decision_id,
                      'policy_decision_id': e.policy_decision_id,
                      'checkpoints': [c['id'] for c in executions.checkpoints(conn, e.id)],
                      'available': o['available'], 'truncated': o['truncated'],
                      'lanes': lanes(o['events'])})
    return {'mission_id': mission_id, 'events': t['events'][::-1],
            'truncated': t['next_before'] is not None,
            'policy_decisions': list_policy_decisions(conn, mission_id, homes=homes),
            'route_decisions': route_decisions(conn, mission_id, homes=homes),
            'executions': execs, 'executions_truncated': len(rs) > MAX_EXECUTIONS}

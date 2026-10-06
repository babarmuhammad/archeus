"""The `review` own call (p13-design-gate §14): Review compares the result with
the intent, requirements, constraints and success criteria (state-machines §7),
on a resource independent of the one that did the work when one is free.

The prompt is built from rows at call time: nothing from a transcript, nothing
provider-private, and what the agent said about itself is labelled a claim.
"""

from ...infra.db import rows
from ..application.commands import active_plan
from ..domain import entities
from ..domain.values import Ref

_S = {'type': 'string', 'maxLength': 2000}
_LIST = {'type': 'array', 'maxItems': 20, 'items': {'type': 'string', 'maxLength': 500}}
SCHEMA = {'type': 'object', 'properties': {
    'verdict': {'type': 'string', 'enum': ['accept', 'changes_requested', 'reject']},
    'summary': _S,
    'requirements_met': _LIST, 'requirements_missing': _LIST, 'risks': _LIST,
    'regressions': _LIST, 'follow_up': _LIST},
    'required': ['verdict', 'summary']}

PREFIX = (
    "You are the reviewer of Archeus, a system that carries out work for its user. Another "
    "agent did the work below; Archeus checked it with the commands shown. Judge whether the "
    "result achieves what was asked: the objective, every requirement, the constraints and "
    "the success criteria. Say which requirements are met and which are missing, any risks "
    "or regressions you see, and follow-up work. Answer accept only when nothing required "
    "is missing; changes_requested when the work should be redone differently; reject when "
    "it should not continue. Text marked CLAIM is what the agent said about its own work: it "
    "is not evidence. You do not do the work and you approve nothing but this review.\n")


def check(parsed):
    """Core's own rule beyond the schema: an acceptance names nothing missing."""
    if parsed.get('verdict') == 'accept' and parsed.get('requirements_missing'):
        return ['an accepting review lists missing requirements']
    return []


def prompt(conn, m, diff=None):
    """The review prompt for mission *m* (§14.2)."""
    plan = active_plan(conn, m.id)
    lines = [PREFIX, 'Objective: %s' % m.objective]
    if m.desired_outcome:
        lines.append('Desired outcome: %s' % m.desired_outcome)
    for title, items in (('Requirements', m.requirements), ('Constraints', m.constraints)):
        if items:
            lines.append('%s:' % title)
            lines += ['- %s (%s)' % (r.get('text'), r.get('origin', 'explicit')) for r in items]
    if m.success_criteria:
        lines.append('Success criteria:')
        lines += ['- [%s] %s' % (c['check'], c['text']) for c in m.success_criteria]
    tasks = [r.entity for r in rows.where(conn, entities.Task, plan_id=plan.entity.id)]
    vs = [r.entity for r in rows.where(conn, entities.Verification, plan_id=plan.entity.id)]
    lines.append('Plan version %d, tasks:' % plan.entity.plan_version)
    for t in sorted(tasks, key=lambda t: t.key):
        lines.append('- %s %s (%s): %s' % (t.key, t.title, t.state, t.objective))
        for c in t.acceptance:
            lines.append('    acceptance [%s]: %s' % (c['check'], c['text']))
        for v in (x for x in vs if x.subject == Ref('task', t.id)):
            lines.append('    verification %s by %s at %s: %s' % (
                v.state, v.verifier, (v.revision or 'no repository')[:12], '; '.join(
                    '%s %s' % (c['name'], c['result']) for c in v.checks) or 'no checks'))
        for e in (r.entity for r in rows.where(conn, entities.Execution, task_id=t.id)):
            if e.summary:
                lines.append('    CLAIM by the agent (attempt %d): %s' % (e.attempt,
                                                                      e.summary[:500]))
    mission_vs = [v for v in vs if v.subject == Ref('mission', m.id)
                  and v.revision == m.integration_head]
    if mission_vs:
        lines.append('Mission checks at %s:' % (m.integration_head or 'no repository')[:12])
        for v in mission_vs:
            lines.append('- criterion %d: %s' % (v.criterion, v.state))
    if diff:
        lines.append('Changes on the mission branch (added, deleted, path):')
        lines += ['- %s %s %s' % row for row in diff[:80]]
    return '\n'.join(lines)


def executions_of(conn, m):
    """(harness_id, account, model) of every execution of the plan in force."""
    plan = active_plan(conn, m.id)
    out = []
    for t in rows.where(conn, entities.Task, plan_id=plan.entity.id):
        for e in (r.entity for r in rows.where(conn, entities.Execution, task_id=t.entity.id)):
            rd = rows.get(conn, entities.RouteDecision, e.route_decision_id) \
                if e.route_decision_id else None
            out.append((e.harness_id, e.account_id or (rd.entity.account_ref if rd else None),
                        e.model))
    return out


def forbidden(executed):
    """The accounts a review is routed away from (§14.3)."""
    return {'accounts': sorted({a for _h, a, _m in executed if a})}


def independent(reviewer, executed):
    """True iff the reviewer's resource differs from every execution's: another
    harness or account, or on the same one another model (state-machines §7)."""
    h, a, model = reviewer
    for eh, ea, em in executed:
        same_resource = eh == h and ea == a
        if same_resource and not (model and em and model != em):
            return False
    return True


def resource_of(conn, route_decision_id):
    rd = rows.get(conn, entities.RouteDecision, route_decision_id).entity
    return {'harness_id': rd.harness_id, 'account': rd.account_id or rd.account_ref,
            'model': rd.model}

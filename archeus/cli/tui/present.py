"""How a row looks, in the terminal (p17-design-gate A2): the Python side of the
SPA's `state/present.ts` and `graph/relations.ts`, function for function. Every
function maps fields Core returned to text; none decides what a state means,
whether an action is allowed, where work runs or whether it is done. The shared
cases in `clients/app/test/fixtures/parity.json` run against both sides.
"""

import datetime
import math

from ._tables import CLASSES, LABELS, PRESENTATION, TRIGGERS


def offers(machine, state, *trigger):
    """Whether the state machine has *trigger* from *state* at all — what a
    command may be offered for. Whether it may fire now is Core's."""
    have = TRIGGERS.get(machine, {}).get(state, [])
    return any(t in have for t in trigger)


def present(machine, state):
    """An unknown state is shown as itself, neutral, never guessed into a class."""
    cls = PRESENTATION.get(machine, {}).get(state)
    if not cls:
        return {'cls': 'neutral', 'glyph': '?', 'role': 'text-2', 'label': state}
    c = CLASSES[cls]
    return {'cls': cls, 'glyph': c['glyph'], 'role': c['role'],
            'label': LABELS.get(machine, {}).get(state, state)}


def badge(machine, state):
    look = present(machine, state)
    return {'glyph': look['glyph'], 'label': look['label'] or state, 'role': look['role'],
            'cls': look['cls']}


def is_done(machine, state):
    """A mission is Done only when COMPLETED — verified and reviewed (P13)."""
    return present(machine, state)['cls'] == 'done'


def presence_label(p):
    """P15 presence: a transport observation, never a person."""
    n = p['connections']
    return {'connected': 'connected (%d %s)' % (n, 'stream' if n == 1 else 'streams'),
            'recent': 'seen in the last minute', 'absent': 'not connected',
            'revoked': 'revoked'}[p['state']]


def _str(v):
    return v if isinstance(v, str) and v else None


def resource_line(r):
    """Harness, model and account as three labelled fields, never merged; a
    missing value is shown as missing, not borrowed from another field."""
    out = [{'key': 'harness', 'label': 'Harness', 'value': _str(r.get('harness_id')) or '—'},
           {'key': 'model', 'label': 'Model', 'value': _str(r.get('model')) or '—'},
           {'key': 'account', 'label': 'Account', 'value': _str(r.get('account_id')) or '—'}]
    if _str(r.get('effort')):
        out.append({'key': 'effort', 'label': 'Effort', 'value': r['effort']})
    return out


def status_line(m):
    """The mission status line, from rows only."""
    tasks = m.get('tasks') or []
    pa = m.get('pending_approval')
    if m['state'] == 'APPROVAL_REQUIRED' and pa:
        if pa['kind'] == 'plan':
            v = m.get('plan_version')
            return 'Waiting: approve plan v%s' % ('?' if v is None else v)
        return 'Waiting: approve a %s step' % pa['kind']
    pb = m.get('planning_blocked')
    if isinstance(pb, dict):
        qs = pb.get('questions') or []
        if pb.get('kind') == 'policy':
            return 'Blocked: the policy denies this plan'
        if qs:
            return 'Waiting: %s' % qs[0]
        return 'Waiting: planning needs your answer (%s)' % pb.get('kind')
    running = [t for t in tasks if t['state'] in ('RUNNING', 'ROUTING')]
    if m['state'] == 'EXECUTING' and running:
        done = sum(1 for t in tasks if t['state'] in ('SUCCEEDED', 'SKIPPED'))
        return '%s · %d of %d tasks done' % (running[0]['title'], done, len(tasks))
    return ''


def explain_state(x):
    """The recorded reasons for a mission's state, most specific first; when no
    row explains it, it says so instead of guessing. No reasoning is read."""
    m = x['mission']
    if m['state'] == 'COMPLETED':
        return [{'text': 'Completed: its result was verified, and a review accepted it.',
                 'source': 'mission.state'}]
    if m['state'] == 'CANCELLED':
        return [{'text': 'Cancelled.', 'source': 'mission.state'}]
    out = []
    pb = m.get('planning_blocked')
    if pb:
        qs = pb.get('questions') or []
        text = ('The policy denies this plan.' if pb.get('kind') == 'policy'
                else 'Planning asks: %s' % '; '.join(qs) if qs
                else 'Planning is blocked (%s).' % pb.get('kind'))
        out.append({'text': text, 'source': 'mission.planning_blocked'})
    a = x.get('approval')
    if a and a['state'] == 'PENDING':
        until = ' until %s' % a['expires_at'] if a.get('expires_at') else ''
        out.append({'text': 'A %s approval waits for you%s.' % (a['kind'], until),
                    'source': 'approval'})
        if a.get('eligible') is False and a.get('eligible_why'):
            out.append({'text': 'It cannot be decided now: %s.' % a['eligible_why'],
                        'source': 'approval.eligible_why'})
    pol = x.get('policy')
    if pol and pol['decision'] == 'DENY':
        out.append({'text': 'Policy: %s' % pol['reason'], 'source': 'policy_decision'})
    route = x.get('route')
    if route and route.get('result') in ('blocked', 'ask'):
        when = ' (retry after %s)' % route['unblock_at'] if route.get('unblock_at') else ''
        explanation = route.get('explanation')
        out.append({'text': 'Routing: %s%s' % (route['result'] if explanation is None
                                              else explanation, when),
                    'source': 'route_decision'})
    e = x.get('execution')
    if e:
        r = e.get('stop_reason') or e.get('exit_reason')
        if r:
            out.append({'text': 'The last execution %s: %s.'
                        % (present('execution', e['state'])['label'].lower(), r),
                        'source': 'execution'})
    v = x.get('verification')
    if v and v['state'] != 'PASSED':
        failed = [c['name'] for c in v.get('checks') or [] if c['result'] != 'pass']
        out.append({'text': 'Verification: %s%s.' % (present('verification', v['state'])['label'],
                                                     ' (%s)' % ', '.join(failed) if failed
                                                     else ''),
                    'source': 'verification'})
    rv = x.get('review')
    if rv and rv['state'] != 'ACCEPTED' and rv.get('verdict'):
        out.append({'text': 'Review verdict: %s.' % rv['verdict'], 'source': 'review'})
    return out or [{'text': 'No recorded reason.', 'source': 'none'}]


def _round(x):
    return math.floor(x + 0.5)            # JavaScript's Math.round, not banker's rounding


def _fmt(s):
    if s < 3600:
        return '%d min' % max(1, _round(s / 60))
    if s < 86400:
        return '%d h' % _round(s / 3600)
    return '%d d' % _round(s / 86400)


def _ms(iso):
    try:
        t = datetime.datetime.fromisoformat(iso.replace('Z', '+00:00'))
    except (AttributeError, ValueError):
        return None
    if t.tzinfo is None:
        t = t.replace(tzinfo=datetime.timezone.utc)
    return t.timestamp() * 1000


def ago(iso, now_ms):
    """Relative time, for display only (never styled as data)."""
    if not iso:
        return '—'
    then = _ms(iso)
    if then is None:
        return '—'
    s = _round((now_ms - then) / 1000)
    if s < 0:
        return 'in %s' % _fmt(-s)
    return 'just now' if s < 45 else '%s ago' % _fmt(s)


# ── relations (the list form of the graph capability, p16 §20) ──────────────
# Every edge is read from the field that records it; an edge whose field is
# empty is not emitted. Nothing is inferred.

def _edge(out, rel, kind, value, field, **extra):
    v = _str(value)
    if v:
        out.append(dict({'rel': rel, 'to': {'kind': kind, 'id': v}, 'field': field}, **extra))


def mission_edges(m, plan=None, sessions=()):
    out = []
    _edge(out, 'in project', 'project', m.get('project_id'), 'missions.project_id')
    _edge(out, 'context used', 'context_package', m.get('context_package_id'),
          'Mission.context_package_id')
    origin = m.get('origin_ref') or {}
    if origin.get('kind'):
        _edge(out, 'started from', origin['kind'], origin.get('id'), 'Mission.origin_ref')
    for v in (plan or {}).get('versions') or []:
        _edge(out, 'plan v%s' % v['plan_version'], 'plan', v['id'], 'plans.mission_id',
              inactive=v['state'] in ('SUPERSEDED', 'REJECTED'))
    _edge(out, 'waiting on approval', 'approval', m.get('pending_approval_id'),
          'approvals.mission_id')
    for x in sessions:
        _edge(out, 'continued in session', 'session', x.get('id'), 'sessions.mission_id')
    return out


def plan_edges(p):
    out = []
    _edge(out, 'of mission', 'mission', p.get('mission_id'), 'plans.mission_id')
    _edge(out, 'replaces', 'plan', p.get('supersedes_plan_id'), 'plans.supersedes_plan_id')
    _edge(out, 'context used', 'context_package', p.get('context_package_id'),
          'Plan.context_package_id')
    _edge(out, 'planned by', 'route_decision', p.get('route_decision_id'),
          'Plan.route_decision_id')
    return out


def task_dependencies(t, by_key):
    out = []
    for k in t.get('depends_on') or []:
        _edge(out, 'after', 'task', (by_key.get(k) or {}).get('id'), 'Task.depends_on')
    return out


def execution_edges(e):
    out = []
    _edge(out, 'attempt of task', 'task', e.get('task_id'), 'executions.task_id')
    _edge(out, 'of mission', 'mission', e.get('mission_id'), 'executions.mission_id')
    _edge(out, 'continues', 'execution', e.get('handoff_from'), 'Execution.handoff_from')
    _edge(out, 'runs in session', 'session', e.get('session_id'), 'Execution.session_id')
    _edge(out, 'routed by', 'route_decision', e.get('route_decision_id'),
          'Execution.route_decision_id')
    _edge(out, 'authorised by', 'policy_decision', e.get('policy_decision_id'),
          'Execution.policy_decision_id')
    return out


def verification_edges(v):
    out = []
    subject = v.get('subject') or {}
    if subject.get('kind'):
        _edge(out, 'verifies', subject['kind'], subject.get('id'), 'Verification.subject')
    _edge(out, 'of plan', 'plan', v.get('plan_id'), 'verifications.plan_id')
    _edge(out, 'checked the work of', 'execution', v.get('execution_id'),
          'Verification.execution_id')
    return out


def session_edges(x, view=None):
    out = []
    _edge(out, 'continues mission', 'mission', x.get('mission_id'), 'sessions.mission_id')
    _edge(out, 'handed off from', 'session', x.get('handoff_from_session_id'),
          'sessions.handoff_from_session_id')
    for t in (view or {}).get('targets') or []:
        _edge(out, 'handed off to', 'session', t.get('id'), 'sessions.handoff_from_session_id')
    _edge(out, 'in project', 'project', x.get('project_id'), 'sessions.project_id')
    return out


def knowledge_edges(k):
    out = []
    me = _str(k.get('id'))
    for r in k.get('relations') or []:
        tier = r.get('confidence_tier')
        tier = 'EXTRACTED' if tier is None else tier
        inactive = bool(r.get('valid_until'))
        if r.get('src_kind') == 'knowledge_item' and r.get('src_id') == me:
            _edge(out, str(r['rel']), str(r['dst_kind']), r.get('dst_id'),
                  'relations.' + str(r['rel']), tier=tier, inactive=inactive)
        else:
            _edge(out, '%s (from)' % r['rel'], str(r['src_kind']), r.get('src_id'),
                  'relations.' + str(r['rel']), tier=tier, inactive=inactive)
    _edge(out, 'replaces', 'knowledge_item', k.get('supersedes_id'), 'KnowledgeItem.supersedes_id')
    _edge(out, 'replaced by', 'knowledge_item', k.get('superseded_by_id'),
          'KnowledgeItem.superseded_by_id', inactive=False)
    _edge(out, 'produced by', 'route_decision', k.get('route_decision_id'),
          'KnowledgeItem.route_decision_id')
    return out


def run_edges(r):
    out = []
    _edge(out, 'run of automation', 'automation', r.get('automation_id'),
          'automation_runs.automation_id')
    _edge(out, 'created mission', 'mission', r.get('mission_id'), 'automation_runs.mission_id')
    return out

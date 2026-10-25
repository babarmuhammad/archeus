"""How a row looks, in the terminal (p17-design-gate A2): the Python side of the
SPA's `state/present.ts` and `graph/relations.ts`, function for function. Every
function maps fields Core returned to text; none decides what a state means,
whether an action is allowed, where work runs or whether it is done. The shared
cases in `clients/app/test/fixtures/parity.json` run against both sides.
"""

import datetime
import math
import re

from ._tables import CLASSES, EDGE_WORDS, LABELS, PRESENTATION, SPINE, TRIGGERS


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


#: a mark that does not depend on the state's own class
_FLAT = {'ahead': 'ahead', 'cancelled': 'none', 'unknown': 'unknown', 'complete': 'passed'}


def spine_of(state, held_from=None):
    """Where a mission is in its life, from its state and held_from only (ADR-0054): the
    SPA's `spineOf`. Never guessed: a hold whose held_from names no station has no
    position, a CANCELLED mission ignores held_from, and a state this client does not
    know is its own word and no stations."""
    look = present('mission', state)
    states = SPINE['states']
    e = states.get(state) if isinstance(state, str) else None
    if e is None:
        return {'marks': [], 'at': None, 'done': False, 'look': None, 'text': look['label']}
    total = len(SPINE['stations'])
    kind, at = e['kind'], e.get('station')
    if kind in ('held', 'resumed'):
        frm = states.get(held_from) if isinstance(held_from, str) else None
        if frm is not None and frm['kind'] == 'current':
            at = frm['station']
        else:
            kind = 'unknown'
    marks = []
    for n in range(1, total + 1):
        if kind in _FLAT:
            marks.append(_FLAT[kind])
        elif at is None:
            marks.append('unknown')
        elif kind == 'passed':
            marks.append('passed' if n <= at else 'ahead')
        elif n < at:
            marks.append('passed')
        elif n > at:
            marks.append('ahead')
        else:
            marks.append(kind if kind in ('held', 'failed') else 'current')
    marked = any(m in ('current', 'held', 'failed') for m in marks)
    words = {'word': look['label'], 'n': str(at), 'total': str(total),
             'station': '' if at is None else SPINE['stations'][at - 1]['label']}
    return {'marks': marks, 'at': at if marked else None, 'done': kind == 'complete',
            'look': {'cls': look['cls'], 'glyph': look['glyph'], 'role': look['role']} if marked else None,
            'text': re.sub(r'\{(\w+)\}', lambda m: words[m.group(1)], SPINE['sentences'][kind])}


def spine_cells(state, held_from=None):
    """One glyph, ASCII glyph and role per station: the mark on the current, held or failed
    station is the glyph of the mission state's own class, the rest are the table's.
    Passed stations are ink until the mission is Done."""
    s = spine_of(state, held_from)
    cells = []
    for kind in s['marks']:
        if kind in ('current', 'held', 'failed'):
            c, role = CLASSES[s['look']['cls']], s['look']['role']
        else:
            c = SPINE['marks'][kind]
            role = 'state.done' if s['done'] and kind == 'passed' else c['role']
        cells.append({'glyph': c['glyph'], 'ascii': c['ascii'], 'role': role})
    return cells


def spine(state, held_from=None, ascii=False):
    """The cluster and the state's own word, as ADR-0054 §7 writes it: `✓✓✓●○○ Executing`."""
    cluster = ''.join(c['ascii' if ascii else 'glyph'] for c in spine_cells(state, held_from))
    return ' '.join(x for x in (cluster, present('mission', state)['label']) if x)


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


def state_sentence(active, needs_you):
    """ADR-0027 §5's state sentence, word for word the SPA's `stateSentence`
    (`state/now.ts`; rulebook §46.4 S-3): two counts in words, no greeting."""
    def count(n, one, many):
        return '%d %s' % (n, one if n == 1 else many)
    doing = ('Archeus is working on %s.' % count(active, 'mission', 'missions')
             if active else 'Archeus is idle.')
    return '%s %s' % (doing, '%s you.' % count(needs_you, 'needs', 'need')
                      if needs_you else 'Nothing needs you.')


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


def reset_text(iso, now_ms):
    """A limited account's reset (P21 D12): "resets in 5 min", or "reset due" once the
    instant has passed while Core still reports LIMITED (the reset worker has not run)."""
    then = _ms(iso)
    if then is not None and then <= now_ms:
        return 'reset due'
    return 'resets %s' % ago(iso, now_ms)


# ── relations (the list form of the graph capability, p16 §20) ──────────────
# Core's graph route assembles every edge (p19-design-gate B1); the TUI only
# says them in the clients' one vocabulary (relations.ts edgeWords/edgeRows).

def consumption_text(led):
    """Today's consumption of an account (ADR-0048 §3, G12): a figure not fully
    reported is a lower bound, and nothing reported is unknown, never 0. Work
    still in flight has not written its usage yet, so it is unknown while it runs."""
    busy = led['running']

    def one(n, done, say, what):
        if done and not busy:
            return say(n)
        if n:
            return 'at least ' + say(n)
        return what + ' unknown' + (' (%d running)' % busy if busy else '')
    return '%s · %s' % (
        one(led['tokens_today'], led['complete']['tokens'], '{:,} tokens'.format, 'tokens'),
        one(led['cost_today'], led['complete']['cost'], lambda n: '$%.2f' % n, 'cost'))


def usage_text(u, now_ms):
    """An account's newest usage reading in words (the SPA's usageText, held
    equal by parity.json): a window not reported is unknown, never 0."""
    if not u:
        return 'not observed'
    resets = u.get('resets_at') or {}
    w = []
    for k, pct in (u.get('windows') or {}).items():
        at = resets.get(k)
        w.append('%s %s%s' % (k.replace('_', ' ').lower(),
                              'unknown' if pct is None else '%s%%' % pct,
                              ' (resets %s)' % ago(at, now_ms) if at else ''))
    observed = u.get('observed_at')
    seen = ''
    if isinstance(observed, (int, float)) and not isinstance(observed, bool):
        iso = datetime.datetime.fromtimestamp(observed, datetime.timezone.utc).isoformat(
            timespec='milliseconds').replace('+00:00', 'Z')
        seen = ', observed %s' % ago(iso, now_ms)
    return '%s%s%s' % (' · '.join(w) or 'no window reported', seen,
                       ' from %s' % u['source'] if u.get('source') else '')


def consumers_text(c):
    """What runs on an account now (ADR-0043 §3, G8): its live work, by name."""
    if not c:
        return 'nothing'
    return '; '.join('an own call for the %s' % (x.get('purpose') or '').replace('_', ' ')
                     if x['kind'] == 'own_call' else '%s attempt %s' % (x.get('task_key'),
                                                                      x.get('attempt'))
                     for x in c)


def edge_words(field, holder, rel=None):
    """An edge's words at the row holding its field, or at the row it names; a
    `Relation` row says its own `rel`."""
    if field.startswith('relations.'):
        return str(rel) if holder else '%s (from)' % rel
    w = EDGE_WORDS.get(field)
    return w[0 if holder else 1] if w else field


def edge_rows(edges, of):
    """The Relations list of *of* from Core's graph read focused on it: every
    edge incident to it, said from its end; containment is the graph's alone."""
    out = []
    for e in edges:
        if e.get('structural'):
            continue
        holder = e['from'] == of
        if not holder and e['to'] != of:
            continue
        row = {'rel': edge_words(e['field'], holder, e.get('rel')),
               'to': e['to'] if holder else e['from'], 'field': e['field']}
        if e.get('tier'):
            row['tier'] = e['tier']
        if e.get('inactive'):
            row['inactive'] = True
        out.append(row)
    return out


#: P20 (ADR-0049): what became of one item an execution's settings sources load
INVENTORY_STATUS = {'excluded': 'excluded', 'opted_in': 'opted in',
                    'not_excludable': 'loaded, not excludable',
                    'recorded_only': 'loaded, recorded only (fallback)',
                    'not_found': 'opted in, not found',
                    'builtin': "loaded, built into the CLI (outside Archeus's controls)"}
INVENTORY_TYPE = {'hook': 'hook', 'permission': 'permission rule', 'plugin': 'plugin',
                  'skill': 'skill', 'mcp_server': 'MCP server', 'claude_md': 'CLAUDE.md',
                  'managed_settings': 'managed settings', 'unreadable': 'unreadable file'}


def inventory_lines(inv):
    """[label, text] rows of an execution's recorded inventory (ADR-0049): the
    flags it was spawned with, then every item and what became of it. Words
    only; what was excluded is Core's record, never decided here."""
    if not inv:
        return [['Inherited settings', 'not recorded for this execution']]
    if inv.get('unavailable'):
        return [['Inherited settings', inv['unavailable']]]
    f = inv.get('flags') or {}

    def names(xs):
        return ', '.join(xs) or 'none'
    rows = [['Settings sources loaded', names(f.get('setting_sources') or [])],
            ['MCP servers', 'only the opted in: ' + names(
                [s['name'] for s in f.get('mcp_servers') or []])],
            ['Skills', 'disabled' if f.get('disable_slash_commands')
             else 'enabled: a skill is opted in'],
            ['Plugins for this session', names([d['name'] for d in f.get('plugin_dirs') or []
                                                if d.get('path')])],
            ['Observed on a real run', 'yes' if inv.get('observed') else
             'no: predicted before the spawn, by the rule PV-19 observed']]
    for i in inv.get('items') or []:
        rows.append(['%s (%s)' % (INVENTORY_TYPE.get(i['type'], i['type']), i['source']),
                     '%s: %s' % (i['name'], INVENTORY_STATUS.get(i['status'], i['status']))])
    if inv.get('truncated'):
        rows.append(['More', 'the record was cut; not every item is listed'])
    return rows

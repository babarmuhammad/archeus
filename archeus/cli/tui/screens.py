"""The TUI's screens (p17-design-gate §3–§5): one function per destination,
Control section and inspector, each the terminal form of the SPA surface of the
same name. A screen reads through the app's cache, writes lines into a `Doc`,
and offers commands only where the SPA does — each one Core command, disabled
with a reason where the row says so. Nothing here decides a state, a policy, a
route, a session or a verdict.
"""

import json

from . import present as P
from . import sync as S
from ._tables import CONTROL_SECTIONS, DESTINATIONS, INSPECTOR_TABS, TABS

# what a digest headline means in words (Now.tsx HEADLINE)
HEADLINE = {'needs_you': 'needs you', 'drift_found': 'drift found', 'failed': 'failed',
            'completed': 'completed', 'drift_cleared': 'drift cleared',
            'progressed': 'progressed'}
SETTLED = ('COMPLETED', 'CANCELLED', 'FAILED', 'BLOCKED', 'PAUSED', 'APPROVAL_REQUIRED')
# design system §7: the TUI's object-kind letters
LETTER = {'mission': 'M', 'project': 'P', 'repository': 'R', 'decision': 'D', 'person': '@',
          'meeting': 'N', 'knowledge_item': 'K', 'idea': 'I', 'automation': 'A',
          'account': '$'}
# objects named as a person would, from their own row (ui.tsx RefLabel)
NAMED = {'mission': (lambda i: '/v1/missions/' + i, lambda r: r.get('title')),
         'project': (lambda i: '/v1/projects/' + i, lambda r: r.get('name')),
         'knowledge_item': (lambda i: '/v1/knowledge/' + i, lambda r: r.get('title')),
         'session': (lambda i: '/v1/sessions/' + i,
                     lambda r: '%s %s session' % (r.get('harness_id'), r.get('mode')))}
WORK_GROUPS = (('needs', 'Needs you', ('needs_you',)),
               ('active', 'Active', ('active', 'verifying', 'reviewing', 'approved')),
               ('planning', 'Planning', ('planning',)), ('blocked', 'Blocked', ('blocked',)),
               ('paused', 'Paused', ('paused',)), ('done', 'Done', ('done',)),
               ('ended', 'Failed or cancelled', ('failed', 'inactive')))
PAGE = 50
ATTENTION_KIND = {'approval': 'Approval', 'verification': 'Waiting for your acceptance',
                  'mission': 'Planning asks you', 'knowledge': 'Knowledge proposal',
                  'drift': 'Architecture drift', 'automation': 'Automation suspended',
                  'account': 'Account needs signing in'}
ATTENTION_MACHINE = {'approval': 'approval', 'verification': 'verification',
                     'mission': 'mission', 'knowledge': 'knowledge_item',
                     'drift': 'architecture', 'automation': 'automation',
                     'account': 'account_health'}
ACTION_CLASSES = ('read', 'web', 'write_repo', 'exec', 'git_commit', 'git_push', 'deploy',
                  'external_comm', 'destructive', 'spend', 'personal_data', 'install',
                  'credential')
TAIL = 200
KNOWLEDGE_STATES = ('', 'CANDIDATE', 'CONFIRMED', 'SUPERSEDED', 'RETRACTED', 'EXPIRED')


def dest(id_):
    return next(d for d in DESTINATIONS if d['id'] == id_)


class Doc:
    """The body of one screen: lines, the rows a cursor can rest on (each with
    where Enter goes and the commands it offers), and the screen's commands."""

    def __init__(self, app, width):
        self.app, self.st, self.width = app, app.st, width
        self.lines, self.acts, self.title = [], [], ''

    def add(self, text='', target=None, acts=None):
        self.lines.append({'text': text, 'target': target, 'acts': list(acts or ())})

    def h(self, title):
        """A section heading; it often carries Core text, so it is cleaned."""
        if self.lines:
            self.add()
        self.add(self.st.t(title, 'text', bold=True))

    def hint(self, text, indent=2):
        from .view import wrap
        for x in wrap(text, self.width - 2, indent):
            self.add(self.st.paint(x, 'text-2'))

    def empty(self, text):
        self.hint(text)

    def para(self, core_text, indent=2, role=None):
        from .view import wrap
        for x in wrap(core_text, self.width - 2, indent):
            self.add(self.st.paint(x, role))

    def kv(self, rows, indent=2):
        w = max((len(k) for k, _ in rows), default=0)
        for k, v in rows:
            self.add(' ' * indent + self.st.paint(k.ljust(w), 'text-2') + '  ' + v)

    def load(self, path, what):
        """Core's answer for *path*, or None after saying why there is none."""
        e = self.app.read(path)
        if e['data'] is None:
            if e['error'] is not None:
                self.add('  ' + self.st.paint('%s is unavailable: ' % what.capitalize(),
                                              'state.blocked')
                         + self.st.t(S.explain(e['error'].refusal()), 'state.blocked'))
            else:
                self.hint('Reading %s…' % what)
            return None
        return e['data']

    def act(self, *a, **k):
        self.acts.append(Act(*a, **k))

    def fresh(self, path):
        f = fresh(self.app, path)
        if f:
            self.add(f)


def Act(key, label, scope, run, *, reread=(), confirm=None, disabled=None, fields=(),
        done=None, ident=None, sent=None):
    """One Core command offered on screen (the SPA's ActionButton): *run* gets
    the action's idempotency key and the values of its *fields*."""
    return {'key': key, 'label': label, 'scope': scope, 'run': run, 'reread': list(reread),
            'confirm': confirm, 'disabled': disabled, 'fields': list(fields), 'done': done,
            'ident': ident or label, 'sent': sent}


# ── shared pieces ────────────────────────────────────────────────────────────

def T(app, s, role=None, bold=False):
    return app.st.t(s, role, bold)


def fresh(app, path):
    """The freshness word, when a view is not current (ui.tsx Fresh)."""
    e = app.cache.get(path)
    if e is None:
        return ''
    f = S.freshness(app.conn, {'gen': e['gen'], 'error': e['error'], 'pending': e['stale'],
                               'hasData': e['data'] is not None})
    text = {'current': None, 'stale': 'updating…', 'reconnecting': 'may be out of date',
            'unavailable': 'unavailable'}[f]
    if not text:
        return ''
    seq = ' · as of event %s' % e['seq'] if e['seq'] is not None and f != 'unavailable' else ''
    return '  ' + app.st.paint(text + seq, 'state.attention')


def ago(app, iso):
    return P.ago(iso, app.now_ms())


def ref_label(app, kind, id_):
    """An object as a person would name it: its title from its own row, else its
    kind and a short id."""
    n = NAMED.get(kind)
    name = None
    if n:
        e = app.read(n[0](id_))
        if e['data'] is not None:
            name = n[1](e['data'])
    lead = (LETTER[kind] + ' ') if kind in LETTER else kind.replace('_', ' ') + ' '
    return T(app, lead, 'text-2') + (T(app, name) if name else T(app, id_[:12] + '…'))


def resources(app, r):
    """Harness, model, account (and effort) as separate labelled fields."""
    return '  '.join(app.st.paint(f['label'], 'text-2') + ' ' + T(app, f['value'])
                     for f in P.resource_line(r))


def open_(kind, id_, tab=None):
    return ('open', kind, id_, tab)


def go(**route):
    return ('go', route)


def relations(app, doc, edges):
    """The Relations tab: an object's authoritative edges as a list grouped by
    relationship, each with the tier as a word and the field it was read from;
    a superseded or ended neighbour is marked, never shown as current."""
    if not edges:
        doc.empty('No recorded relationships.')
        return
    groups = {}
    for e in edges:
        groups.setdefault(e['rel'], []).append(e)
    for rel, es in groups.items():
        doc.add('  ' + T(app, rel, 'text', bold=True))
        for e in es:
            bits = ['    ' + ref_label(app, e['to']['kind'], e['to']['id'])]
            if e.get('tier'):
                bits.append(T(app, e['tier'].lower(), 'text-2'))
            if e.get('inactive'):
                bits.append(app.st.paint('no longer current', 'state.paused'))
            bits.append(T(app, 'from ' + e['field'], 'text-2'))     # it names Core's label
            doc.add('  '.join(bits), target=open_(e['to']['kind'], e['to']['id']))


def mission_row(app, doc, m, waiting=False):
    bits = [app.st.badge('mission', m['state']), T(app, m['title'], 'text')]
    if waiting:
        bits.append(app.st.paint('waiting on you', 'state.attention'))
    line = P.status_line(m)
    if line:
        bits.append(T(app, line, 'text-2'))
    if m.get('origin') == 'automation':
        bits.append(app.st.paint('from an automation', 'text-2'))
    bits.append(app.st.paint(ago(app, m.get('updated_at')), 'text-2'))
    doc.add('  ' + '  '.join(bits), target=open_('mission', m['id']))


def reread_mission(mid):
    return ['/v1/missions/' + mid, '/v1/missions', '/v1/attention']


def post(app, path):
    return lambda key, values, body=None: app.core.post(path, dict(body or {},
                                                                    idempotency_key=key))


# ── Now ──────────────────────────────────────────────────────────────────────

def now(app, doc):
    ml = app.read('/v1/missions')['data'] or {}
    att = app.read('/v1/attention')['data'] or {}
    active = [m for m in ml.get('missions', []) if m['state'] not in SETTLED]
    needs = att.get('count', 0)
    doc.add('  ' + app.st.paint('Archeus · %d %s active · %d %s you' % (
        len(active), 'mission' if len(active) == 1 else 'missions', needs,
        'thing needs' if needs == 1 else 'things need'), 'text-2'))
    g = doc.load('/v1/digest', 'the digest')
    if g and g['count']:
        doc.h('Since you last looked · %d %s' % (g['count'],
                                                 'change' if g['count'] == 1 else 'changes'))
        up_to = g['up_to_seq']
        doc.act('D', 'Dismiss', 'control',
                lambda key, v: app.core.post('/v1/digest/ack', {'up_to_seq': up_to}),
                reread=['/v1/digest'])
        if g.get('truncated'):
            doc.hint('Some older events are no longer kept; this is what remains.')
        for x in g['groups']:
            doc.add('  ' + ref_label(app, x['ref']['kind'], x['ref']['id']) + '  '
                    + T(app, HEADLINE.get(x['headline'], x['headline'])) + ' · %d %s'
                    % (x['count'], 'event' if x['count'] == 1 else 'events'),
                    target=open_(x['ref']['kind'], x['ref']['id']))
    doc.h('Happening now' + fresh(app, '/v1/missions'))
    if doc.load('/v1/missions', 'the missions') is not None:
        if active:
            for m in active:
                mission_row(app, doc, m)
        else:
            doc.empty('Nothing is in progress. Tell Archeus what you want: [M] Message.')
    doc.h('Needs you')
    attention_items(app, doc, limit=3)
    conversation(app, doc)


def conversation(app, doc):
    doc.h('Conversation')
    ml = doc.load('/v1/conversations/primary/messages', 'the conversation')
    doc.act('M', 'Message', 'control',
            lambda key, v: app.core.post('/v1/conversations/primary/messages',
                                         {'text': v['text'], 'idempotency_key': key}),
            fields=[('text', 'Tell Archeus what you want', True)],
            reread=['/v1/conversations/primary/messages'], sent='Sent — Archeus is reading it.')
    if ml is None:
        return
    msgs = ml['messages']
    shown = msgs[-100:]
    if not shown:
        doc.empty('No messages yet. Tell Archeus what you want: [M] Message.')
    if len(msgs) > len(shown):
        doc.hint('%d older messages are not shown.' % (len(msgs) - len(shown)))
    for m in shown:
        who = {'archeus': 'Archeus', 'user': 'You'}.get(m['author'], 'System')
        doc.add('  ' + app.st.paint(who, 'text', bold=True) + '  '
                + app.st.paint(ago(app, m.get('created_at')), 'text-2')
                + ('  ' + app.st.paint('(AI-generated)', 'text-2') if m['author'] == 'archeus'
                   else ''))
        doc.para(m['text'], indent=4)
        for i, c in enumerate(m.get('cards') or []):
            card(app, doc, m, i, c)


def card(app, doc, m, i, c):
    """A card links the live object it names; a challenge or clarification is
    answered through P7's command."""
    kind, id_, type_ = c['ref']['kind'], c['ref']['id'], c['type']
    ident = 'card:%s:%d' % (m['id'], i)
    reread = ['/v1/conversations/primary/messages']
    if type_ in ('challenge', 'clarification') and kind == 'intent':
        path = '/v1/intents/%s/clarify' % id_
        if type_ == 'challenge':
            acts = [Act('Y', 'Proceed anyway', 'control',
                        lambda key, v: app.core.post(path, {'choice': 'proceed',
                                                            'idempotency_key': key}),
                        reread=reread, ident=ident + ':y'),
                    Act('N', 'Drop it', 'control',
                        lambda key, v: app.core.post(path, {'choice': 'drop',
                                                            'idempotency_key': key}),
                        reread=reread, ident=ident + ':n')]
            text = 'Archeus disagrees with what is recorded. Keep going, or drop it?'
        else:
            acts = [Act('W', 'Answer', 'control',
                        lambda key, v: app.core.post(path, {'text': v['answer'],
                                                            'idempotency_key': key}),
                        fields=[('answer', 'Your answer', True)], reread=reread,
                        ident=ident + ':w')]
            text = 'Archeus needs an answer before it can start.'
        doc.add('    ' + T(app, '[' + type_ + '] ', 'state.attention')
                + app.st.paint(text), acts=acts)
        return
    bits = ['    ' + T(app, '[' + type_.replace('_', ' ') + ']', 'text-2'),
            T(app, '%s %s' % (kind, id_))]
    if kind == 'mission':
        e = app.read('/v1/missions/' + id_)
        if e['data']:
            bits += [T(app, e['data']['title']), app.st.badge('mission', e['data']['state'])]
    doc.add('  '.join(bits), target=open_(kind, id_))


# ── Work ─────────────────────────────────────────────────────────────────────

def group_of(m, waiting):
    cls = P.present('mission', m['state'])['cls']
    if m['id'] in waiting and cls not in ('done', 'inactive', 'failed'):
        return 'needs'
    return next((g for g, _t, cs in WORK_GROUPS if cls in cs), 'ended')


def work(app, doc):
    project = app.route.get('project')
    path = '/v1/missions?project=%s' % project if project else '/v1/missions'
    if project:
        doc.hint('Missions of one project · [Esc] all missions')
    doc.fresh(path)
    ml = doc.load(path, 'the missions')
    att = app.read('/v1/attention')['data'] or {}
    waiting = {i.get('mission_id') for i in att.get('items', []) if i.get('mission_id')}
    if ml is not None:
        if not ml['missions']:
            doc.empty('No missions yet. Tell Archeus what you want on Now.')
        for gid, title, _cs in WORK_GROUPS:
            ms = sorted((m for m in ml['missions'] if group_of(m, waiting) == gid),
                        key=lambda m: m['updated_at'], reverse=True)
            if not ms:
                continue
            doc.h('%s · %d' % (title, len(ms)))
            for m in ms[:PAGE]:
                mission_row(app, doc, m, m['id'] in waiting)
            if len(ms) > PAGE:
                doc.hint('%d more not shown.' % (len(ms) - PAGE))
    ideas = (app.read('/v1/ideas')['data'] or {}).get('ideas') or []
    if ideas:
        doc.h('Ideas · %d' % len(ideas))
        for i in ideas:
            target = open_('mission', i['promoted_mission_id']) if i.get('promoted_mission_id') \
                else None
            doc.add('  ' + app.st.badge('idea', i['state']) + '  '
                    + T(app, i.get('title') or i.get('text'))
                    + ('  ' + app.st.paint('its mission', 'text-2') if target else ''),
                    target=target)


# ── World ────────────────────────────────────────────────────────────────────

def world(app, doc):
    if app.route.get('project'):
        return project_page(app, doc, app.route['project'])
    tab = app.ui.get('world', 'projects')
    doc.add('  ' + '   '.join(app.st.paint('[%s]' % n if t == tab else n,
                                           'text' if t == tab else 'text-2', t == tab)
                              for t, n in (('projects', 'Projects'),
                                           ('knowledge', 'Knowledge')))
            + app.st.paint('   [Tab] switch', 'text-2'))
    if tab == 'knowledge':
        return knowledge_list(app, doc)
    doc.fresh('/v1/projects')
    pl = doc.load('/v1/projects', 'the projects')
    if pl is not None:
        if not pl['projects']:
            doc.empty('No project yet. Create one: [N] New project.')
        for x in pl['projects']:
            repos = x.get('repositories') or []
            doc.add('  ' + T(app, x['name'], 'text') + '  '
                    + app.st.paint('%d %s' % (len(repos), 'repository' if len(repos) == 1
                                              else 'repositories'), 'text-2') + '  '
                    + '  '.join(app.st.badge('architecture', r['architecture_state'])
                                for r in repos),
                    target=go(view='world', project=x['id']))
    doc.act('N', 'New project', 'admin',
            lambda key, v: app.core.post('/v1/projects', {'name': v['name'],
                                                         'root_paths': [v['path']],
                                                         'idempotency_key': key}),
            fields=[('name', 'Name', True),
                    ('path', 'Root path on the computer running Archeus', True)],
            reread=['/v1/projects'])


def project_page(app, doc, pid):
    x = doc.load('/v1/projects/' + pid, 'the project')
    if x is None:
        return
    doc.title = clean_title(x['name'])
    doc.fresh('/v1/projects/' + pid)
    doc.add('  ' + app.st.paint('Its missions in Work', 'text'), target=go(view='work',
                                                                             project=pid))
    doc.hint('roots ' + ', '.join(x['root_paths']))
    for r in x.get('repositories') or []:
        doc.h(r['kind'] + ' · ' + r['path'])
        doc.add('  ' + app.st.badge('architecture', r['architecture_state'])
                + ('  ' + T(app, 'at ' + str(r['last_revision'])[:10], 'text-2')
                   if r.get('last_revision') else ''))
        findings = r.get('findings') or []
        if not findings:
            doc.empty('No declared constraint has been checked here.')
        for f in findings:
            doc.add('  ' + T(app, f['constraint'], 'text') + '  ' + T(app, f['status'], 'text-2')
                    + '  ' + T(app, f.get('reason') or '—'))
            for v in f['violations'][:10]:
                doc.add('      ' + T(app, ' → '.join(v), 'text-2'))
        ins = app.read('/v1/repositories/%s/inspections?limit=5' % r['id'])['data']
        if ins:
            doc.add('  ' + app.st.paint('Recent inspections', 'text-2'))
            for i in ins['inspections']:
                doc.add('    ' + app.st.badge('repository_inspection', i['state']) + '  '
                        + T(app, str(i.get('revision') or '')[:10])
                        + (' — ' + T(app, i['failure']) if i.get('failure') else ''))
    doc.act('K', 'Declare constraint', 'control',
            lambda key, v: app.core.post('/v1/projects/%s/constraints' % pid,
                                         {'statement': v['statement'], 'idempotency_key': key}),
            fields=[('statement', 'The rule, in words (a checkable rule needs a kind and '
                                  'spec; the CLI takes those)', True)],
            reread=['/v1/projects/' + pid], ident='constraint:' + pid)


def clean_title(s):
    from .view import clean
    return clean(s)


def knowledge_list(app, doc):
    state = app.ui.get('knowledge_state', '')
    path = '/v1/knowledge?state=%s' % state if state else '/v1/knowledge'
    doc.add('  ' + app.st.paint('State: %s   [F] next filter' % (state.lower() or 'all'),
                                'text-2') + fresh(app, path))
    kl = doc.load(path, 'the knowledge')
    if kl is None:
        return
    if not kl['knowledge']:
        doc.empty('Nothing known yet.')
    for k in kl['knowledge']:
        inactive = k['state'] in ('SUPERSEDED', 'RETRACTED', 'EXPIRED')
        doc.add('  ' + app.st.badge('knowledge_item', k['state']) + '  '
                + T(app, k['title'], 'text-2' if inactive else 'text') + '  '
                + T(app, k['type'].lower(), 'text-2') + '  '
                + T(app, k.get('source_kind') or '', 'text-2'),
                target=open_('knowledge_item', k['id']))


# ── Attention ────────────────────────────────────────────────────────────────

def attention(app, doc):
    doc.fresh('/v1/attention')
    attention_items(app, doc)


def attention_items(app, doc, limit=None):
    a = doc.load('/v1/attention', 'Attention')
    if a is None:
        return
    items = a['items'][:limit] if limit else a['items']
    if not a['items']:
        doc.empty('Nothing waits on you.')
    for i in items:
        entry(app, doc, i)
    if limit and len(a['items']) > limit:
        doc.add('  ' + app.st.paint('All %d items that wait on you' % len(a['items']), 'text'),
                target=go(view='attention'))


def entry(app, doc, item):
    title = ATTENTION_KIND.get(item['kind'], item['kind'])
    head = ('  ' + app.st.badge(ATTENTION_MACHINE.get(item['kind'], item['kind']), item['state'])
            + '  ' + T(app, title, 'text', bold=True) + '  '
            + app.st.paint(ago(app, item.get('since')), 'text-2'))
    if item['kind'] == 'approval':
        return approval_card(app, doc, item['ref']['id'], head)
    if item['kind'] == 'verification':
        return verification_decision(app, doc, item, head)
    if item['kind'] == 'knowledge':
        return knowledge_proposal(app, doc, item, head)
    link = {'mission': open_('mission', item['ref']['id']),
            'drift': go(view='world', project=item.get('project_id')) if item.get('project_id')
            else go(view='world'),
            'automation': go(view='control', section='automations'),
            'account': go(view='control', section='resources')}.get(item['kind'])
    doc.add(head, target=link)
    if item.get('reason'):
        doc.add('    ' + T(app, item['reason']))


def approval_card(app, doc, aid, head=None):
    """The canonical action as Core rendered it, why it asks, what each answer
    does and when it expires (Attention.tsx ApprovalCard)."""
    a = doc.load('/v1/approvals/' + aid, 'the approval')
    sync = app.read('/v1/sync')['data'] or {}
    if a is None:
        if head:
            doc.add(head)
        return
    p = a.get('presented') or {}
    step_up = bool(a.get('step_up'))
    capability = ((sync.get('client') or {}).get('capabilities') or {}).get('step_up')
    needs_pin = step_up and capability == 'pin'
    cannot = ('This client has no PIN: it cannot satisfy a step-up.'
              if step_up and capability == 'none' else None)
    not_eligible = ('This approval is %s.' % a['state'].lower() if a['state'] != 'PENDING'
                    else None if a.get('eligible') else
                    'Not decidable now: %s.' % (a.get('eligible_why') or 'no reason given'))
    reread = ['/v1/approvals', '/v1/attention', '/v1/missions']
    path = '/v1/approvals/%s/decide' % aid
    pin = [('step_up', 'This client’s PIN (step-up)', True)] if needs_pin else []

    def decide(decision):
        return lambda key, v: app.core.post(path, S.decide_body(
            a, decision, key, {k: v[k] for k in ('step_up', 'note') if v.get(k)}))
    cons = p.get('consequences') or {}
    # a decision is final: it is confirmed in prose, in Core's own words when it
    # gave them (p17-design-gate §8, T03)
    acts = [Act('A', 'Approve plan' if a['kind'] == 'plan' else 'Approve', 'approve',
                decide('approve'), reread=reread, disabled=not_eligible or cannot, fields=pin,
                confirm='Approve: ' + clean_title(cons.get('approve')
                                                  or 'the action runs as shown.'),
                ident='approve:' + aid),
            Act('R', 'Reject', 'approve', decide('reject'), reread=reread,
                disabled=not_eligible, ident='reject:' + aid,
                confirm='Reject: ' + clean_title(cons.get('reject')
                                                 or 'the action does not run.'))]
    if a['kind'] == 'plan' and a['state'] == 'PENDING' and app.can('approve'):
        acts.append(Act('C', 'Request changes', 'approve', decide('request_changes'),
                        reread=reread, disabled=None if a.get('eligible')
                        else 'Not decidable now.',
                        fields=[('note', 'What should change? (the planner reads this)', True)],
                        ident='changes:' + aid))
    doc.add(head or ('  ' + app.st.badge('approval', a['state']) + '  '
                     + app.st.paint('Approval', 'text', bold=True)), acts=acts)
    against = p.get('against') or {}
    ask = []
    if p.get('scope'):
        ask.append(app.st.paint('Approve ', 'text', bold=True) + T(app, p['scope'], bold=True))
    if against.get('mission'):
        ask.append(app.st.paint('for ') + T(app, against['mission']['title']))
    if against.get('plan'):
        ask.append(T(app, 'plan v%s' % against['plan']['version']))
    if ask:
        doc.add('    ' + ' · '.join(ask))
    for w in p.get('what') or []:
        target = w.get('target') or ', '.join(w.get('paths') or []) or '—'
        doc.add('    ' + T(app, w['task'] + (' · ' + w['title'] if w.get('title') else ''))
                + '  ' + T(app, w['class'], 'text-2') + '  ' + T(app, target) + '  '
                + T(app, w['decision'] + (' — ' + w['why'] if w.get('why') else ''), 'text-2'))
    doc.kv([('Why it asks', T(app, p.get('why') or '—')),
            ('If you approve', T(app, cons.get('approve') or '—')),
            ('If you reject', T(app, cons.get('reject') or '—')),
            ('Expires', T(app, '%s (%s)' % (a['expires_at'], ago(app, a['expires_at'])))),
            ('Covers', T(app, p.get('reusable') or '—')),
            ('Action hash', T(app, a['action_hash'][:16] + '…'))], indent=4)
    plan = against.get('plan') or {}
    if plan.get('summary'):
        doc.add('    ' + T(app, 'Plan summary, %s: ' % (plan.get('summary_by')
                                                      or 'model-written'), 'text-2')
                + T(app, plan['summary']))
    if a.get('decided_by'):
        me = (sync.get('client') or {}).get('principal_id')
        doc.hint('Decided %s%s' % (ago(app, str(a.get('decided_at'))),
                                   ' on this client' if a['decided_by'] == me
                                   else ' on another client'), indent=4)


def verification_decision(app, doc, item, head):
    human = item['state'] == 'AWAITING_HUMAN'
    vid = item['ref']['id']
    reread = ['/v1/attention', '/v1/verifications', '/v1/missions']
    path = '/v1/verifications/%s/decide' % vid
    note = [('note', 'Note (optional)', False)]
    acts = []
    if human:
        acts = [Act('A', 'Accept result', 'approve',
                    lambda key, v: app.core.post(path, {'decision': 'accept',
                                                        'note': v.get('note', ''),
                                                        'idempotency_key': key}),
                    fields=note, reread=reread, ident='accept:' + vid,
                    confirm='Accept this result as verified by you. It cannot be undone.'),
                Act('R', 'Reject result', 'approve',
                    lambda key, v: app.core.post(path, {'decision': 'reject',
                                                        'note': v.get('note', ''),
                                                        'idempotency_key': key}),
                    fields=note, reread=reread, ident='rejectv:' + vid,
                    confirm='Reject this result. It cannot be undone.')]
    doc.add(head, target=open_('verification', vid), acts=acts)
    doc.add('    ' + (app.st.paint('Nothing deterministic could check this: it waits for you to '
                                   'accept or reject the result.') if human else
                      app.st.paint('The verifier broke (') + T(app, item.get('reason')
                                                               or 'no reason')
                      + app.st.paint(') — this is not a failure of the work.')))
    if item.get('mission_id'):
        doc.add('    ' + app.st.paint('Mission evidence', 'text'),
                target=open_('mission', item['mission_id'], 'evidence'))


def knowledge_proposal(app, doc, item, head):
    kid = item['ref']['id']
    reread = ['/v1/attention', '/v1/knowledge']
    acts = [Act('C', 'Confirm', 'control',
                lambda key, v: app.core.post('/v1/knowledge/%s/confirm' % kid,
                                             {'idempotency_key': key}),
                reread=reread, ident='confirm:' + kid),
            Act('D', 'Dismiss', 'control',
                lambda key, v: app.core.post('/v1/knowledge/%s/reject' % kid,
                                             {'idempotency_key': key}),
                reread=reread, ident='dismiss:' + kid,
                confirm='Dismiss this proposal: Archeus will not remember it.')]
    doc.add(head, target=open_('knowledge_item', kid), acts=acts)
    doc.add('    ' + app.st.paint('Remember: ') + T(app, item.get('reason'), bold=True) + ' '
            + T(app, '(%s)' % (item.get('reason_code') or '').lower(), 'text-2'))


# ── Control ──────────────────────────────────────────────────────────────────

def control(app, doc):
    cur = app.route.get('section') or 'autonomy'
    doc.add('  ' + '  '.join(app.st.paint('[%s]' % s['label'] if s['id'] == cur else s['label'],
                                          'text' if s['id'] == cur else 'text-2',
                                          s['id'] == cur) for s in CONTROL_SECTIONS)
            + app.st.paint('   [Tab] next section', 'text-2'))
    {'autonomy': autonomy, 'automations': automations, 'resources': resources_section,
     'sessions': sessions, 'devices': devices, 'about': about}[cur](app, doc)


def autonomy(app, doc):
    p = doc.load('/v1/policies', 'the policy')
    if p is None:
        return
    doc.h('Your default profile' + fresh(app, '/v1/policies'))
    doc.add('  ' + T(app, p['user_profile'], bold=True) + app.st.paint(' · policy version ')
            + T(app, p['policy_version'][:12]))
    for key, name in (('C', 'careful'), ('S', 'standard'), ('U', 'autonomous')):
        doc.act(key, 'Use ' + name, 'admin',
                lambda k, v, name=name: app.core.post('/v1/policies/profile',
                                                      {'scope': 'user', 'profile': name,
                                                       'idempotency_key': k}),
                disabled='This is the profile in force.' if p['user_profile'] == name else None,
                reread=['/v1/policies'])
    names = list(p['profiles'])
    cell = {(c, n): str(((p['profiles'][n] or {}).get(c) or {}).get('decision') or '—')
            for c in ACTION_CLASSES for n in names}
    w = {n: max([len(n)] + [len(cell[c, n]) for c in ACTION_CLASSES]) + 2 for n in names}
    doc.add('  ' + T(app, 'Action class'.ljust(16) + ''.join(n.ljust(w[n]) for n in names),
                     'text-2'))
    for c in ACTION_CLASSES:
        doc.add('  ' + T(app, c.ljust(16)) + ''.join(T(app, cell[c, n].ljust(w[n]))
                                                     for n in names))
    doc.h('Your rules · %d' % len(p['rules']))
    if not p['rules']:
        doc.empty('No rule of your own: the profile decides.')
    for r in p['rules']:
        acts = [] if r.get('retired_at') else [
            Act('T', 'Retire', 'admin',
                lambda k, v, rid=r['id']: app.core.post('/v1/policies/rules/%s/retire' % rid,
                                                        {'idempotency_key': k}),
                reread=['/v1/policies'], ident='retire:' + r['id'])]
        doc.add('  ' + T(app, '%s · %s → ' % (r['scope_level'], r['action_class']))
                + T(app, r['decision'], bold=True)
                + ('  ' + app.st.paint('locked', 'text-2') if r.get('locked') else '')
                + ('  ' + app.st.paint('retired', 'state.paused') if r.get('retired_at') else ''),
                acts=acts)
    doc.h('What would happen if…')
    got = app.ui.get('simulation')

    def keep(out, values):
        app.ui['simulation'] = out
    doc.act('W', 'Simulate', 'observe',
            lambda k, v: app.core.post('/v1/policies/simulate',
                                       {'action': {'class': v['class'],
                                                   'target': v.get('target') or None}}),
            fields=[('class', 'Action class (%s)' % ', '.join(ACTION_CLASSES), True),
                    ('target', 'Target (optional)', False)],
            done=keep, sent='Simulated — nothing was done.')
    if got:
        doc.add('  ' + app.st.paint('The policy would decide ') + T(app, got['decision'],
                                                                    bold=True)
                + app.st.paint(': ') + T(app, got['reason'])
                + app.st.paint(' (nothing was done)', 'text-2'))
    else:
        doc.empty('[W] asks the policy about one action; nothing is done.')


def automations(app, doc):
    al = doc.load('/v1/automations', 'the automations')
    if al is None:
        return
    if not al['automations']:
        doc.empty('No automation yet. One is written with the CLI (`archeus automation`) or by '
                  'an admin client.')
    for a in al['automations']:
        reread = ['/v1/automations']

        def set_state(action, a=a):
            return lambda k, v: app.core.post('/v1/automations/%s/state' % a['id'], {
                'action': action, 'expected_version': a['version'], 'idempotency_key': k})
        acts = []
        if a['state'] == 'ENABLED':
            acts.append(Act('D', 'Disable', 'admin', set_state('disable'), reread=reread,
                            ident='disable:' + a['id']))
        if a['state'] in ('DRAFT', 'DISABLED', 'SUSPENDED'):
            acts.append(Act('E', 'Enable', 'admin', set_state('enable'), reread=reread,
                            ident='enable:' + a['id']))
        if a['state'] in ('ENABLED', 'DISABLED'):
            acts.append(Act('X', 'Archive', 'admin', set_state('archive'), reread=reread,
                            confirm='Archive this automation: it never fires again. It cannot '
                                    'be undone.', ident='archive:' + a['id']))
        doc.add()
        doc.add('  ' + T(app, a['name'], 'text', bold=True) + '  '
                + app.st.badge('automation', a['state']), acts=acts)
        doc.kv([('When', T(app, json.dumps(a['trigger']))),
                ('Archeus will', T(app, json.dumps(a['template']))),
                ('Depth limit · rate limit', T(app, '%s · %s per hour' % (
                    a.get('max_depth', '—'), a.get('rate_limit', '—'))))], indent=4)
        runs = (app.read('/v1/automations/' + a['id'])['data'] or {}).get('runs') or []
        if not runs:
            doc.hint('It has not fired yet.', indent=4)
        for r in list(reversed(runs[-20:])):
            doc.add('    ' + app.st.badge('automation_run', r['state']) + '  '
                    + T(app, 'run on event %s · depth %s' % (r['triggering_event_seq'],
                                                             r['depth']))
                    + (' · ' + T(app, r['reason']) if r.get('reason') else ''),
                    target=open_('automation_run', r['id']))


def resources_section(app, doc):
    doc.h('Harnesses' + fresh(app, '/v1/harnesses'))
    hl = doc.load('/v1/harnesses', 'the harnesses')
    if hl is not None:
        for x in hl['harnesses']:
            models = ', '.join(str(m.get('id') or m.get('model') or '') for m in x['models']
                               if m.get('id') or m.get('model')) or '—'
            doc.add('  ' + T(app, x['id'], bold=True) + '  ' + app.st.paint(
                'installed %s · runs executions %s · own calls %s · enforcement ' % (
                    'yes' if x['installed'] else 'no', 'yes' if x['execution'] else 'no',
                    'yes' if x['calls'] else 'no'), 'text-2')
                    + T(app, x.get('enforcement') or '—'))
            doc.add('    ' + app.st.paint('models ', 'text-2') + T(app, models))
    doc.h('Accounts')
    al = doc.load('/v1/accounts', 'the accounts')
    if al is not None:
        if not al['accounts']:
            doc.empty('No account registered.')
        for x in al['accounts']:
            rp = x['resource_policy']
            doc.add('  ' + app.st.badge('account_health', x['health']) + '  '
                    + T(app, x['label'], bold=True) + app.st.paint(' · harness ')
                    + T(app, x['harness_id']) + app.st.paint(' · ') + T(app, x['auth_kind']))
            doc.kv([('Priority', T(app, str(rp['priority']))),
                    ('Allocation ceiling', T(app, '%s%% (reserve %s%%, own-call reserve %s%%)'
                                             % (rp['allocation_pct'], rp['reserve_pct'],
                                                rp['brain_reserve_pct']))),
                    ('Fallback to it', T(app, rp['fallback'])),
                    ('Latest usage', T(app, json.dumps(x['usage'])) if x.get('usage')
                     else app.st.paint('not observed'))], indent=4)
    doc.h('Recent routing decisions')
    rl = doc.load('/v1/route-decisions', 'the route decisions')
    if rl is not None:
        if not rl['route_decisions']:
            doc.empty('Nothing was routed yet.')
        for d in list(reversed(rl['route_decisions'][-20:])):
            doc.add('  ' + T(app, str(d.get('purpose') or 'task')) + app.st.paint(' · ')
                    + T(app, str(d.get('result') or '—')) + '  ' + resources(app, d),
                    target=open_('route_decision', d['id']))


def sessions(app, doc):
    doc.h('Sessions' + fresh(app, '/v1/sessions'))
    doc.hint('A session is one provider conversation on one harness and account. It is not a '
             'mission: a mission may continue across several sessions and harnesses.')
    sl = doc.load('/v1/sessions', 'the sessions')
    if sl is None:
        return
    if not sl['sessions']:
        doc.empty('No session is known to Archeus yet.')
    for x in reversed(sl['sessions']):
        doc.add('  ' + app.st.badge('session', x['state']) + '  ' + T(app, x['id']) + '  '
                + T(app, x['mode'], 'text-2') + '  ' + resources(app, x),
                target=open_('session', x['id']))


def devices(app, doc):
    doc.h('Clients' + fresh(app, '/v1/devices'))
    doc.hint('A client is one registered installation of an Archeus app. “Connected” means an '
             'event stream is open — not that someone is using it. The platform is what the '
             'client declared.')
    dl = doc.load('/v1/devices', 'the clients')
    me = ((app.read('/v1/sync')['data'] or {}).get('client') or {})
    if dl is not None:
        groups = {}
        for x in dl['devices']:
            groups.setdefault(x.get('host_label') or 'unlabelled', []).append(x)
        for label, ds in groups.items():
            doc.add('  ' + T(app, label, bold=True))
            for x in ds:
                acts = []
                if x['state'] == 'ACTIVE':
                    def done(out, values, x=x):
                        if x['id'] == me.get('id'):
                            app.signal('self_revoked')
                    acts.append(Act(
                        'V', 'Revoke', 'admin',
                        lambda k, v, did=x['id']: app.core.post('/v1/devices/%s/revoke' % did,
                                                                {'idempotency_key': k}),
                        confirm='This client loses access at once and its open streams close. '
                                'It cannot be undone: the client must be paired again.',
                        reread=['/v1/devices'], done=done, ident='revoke:' + x['id']))
                pres = x['presence']
                doc.add('    ' + T(app, x['name'], bold=True)
                        + ('  ' + app.st.paint('this client', 'state.active')
                           if x['id'] == me.get('id') else '')
                        + app.st.paint(' · ') + T(app, x['client_type'])
                        + app.st.paint(' · platform ') + T(app, x['platform'])
                        + app.st.paint(' (declared) · ')
                        + app.st.paint('paired' if x['origin'] == 'paired'
                                       else 'on this computer'), acts=acts)
                doc.add('      ' + app.st.badge('device', x['state']) + app.st.paint(' · ')
                        + T(app, P.presence_label(pres))
                        + (app.st.paint(' · last seen ') + T(app, ago(app, pres['last_seen_at']))
                           if pres.get('last_seen_at') else '')
                        + app.st.paint(' · scopes ') + T(app, ', '.join(x['scopes']))
                        + app.st.paint(' · step-up ') + T(app, x['capabilities']['step_up'])
                        + (app.st.paint(' · expires ') + T(app, x['expires_at'][:10])
                           if x.get('expires_at') else ''))
    if me.get('origin') != 'local':
        doc.hint('Pairing a new client starts on the computer running Archeus.')
        return
    doc.h('Pair a client')
    code = app.ui.get('pairing')

    def keep(out, values):
        app.ui['pairing'] = dict(out, since=app.now_ms())
    doc.act('P', 'Start pairing', 'admin',
            lambda k, v: app.core.post('/v1/devices/pair/start', {
                'name': v.get('name') or None, 'host_label': v.get('label') or None,
                'scopes': ['observe', 'control', 'approve', 'admin']
                if (v.get('admin') or '').lower().startswith('y')
                else ['observe', 'control', 'approve']}),
            fields=[('name', 'Name (what the new client is called here)', False),
                    ('label', 'Host label (your name for the machine or phone it runs on)',
                     False),
                    ('admin', 'Also grant admin (policy, resources, clients)? y/N', False)],
            done=keep, sent='A pairing code was made.')
    if code:
        left = max(0, round(code['expires_in'] - (app.now_ms() - code['since']) / 1000))
        if not left:
            app.ui.pop('pairing', None)
            doc.empty('[P] makes a code that works once, for two minutes.')
            return
        doc.add('  ' + app.st.paint('Valid for %d s, once. Scopes: ' % left)
                + T(app, ', '.join(code['scopes'])))
        if code.get('url'):
            doc.add('  ' + T(app, code['url'], bold=True))
            doc.hint('The terminal shows no QR code: open this link on the new client.')
        else:
            doc.hint('No remote host is configured, so a phone cannot reach this computer yet: '
                     'start Core with archeus core --remote-host <name> behind an HTTPS tunnel.')
    else:
        doc.empty('[P] makes a code that works once, for two minutes.')


def about(app, doc):
    doc.h('This Core')
    h = doc.load('/v1/health', "Core's health")
    if h is not None:
        doc.kv([('Version', T(app, h['core']['version'])),
                ('Schema', T(app, str(h['core']['schema']))),
                ('Started', T(app, ago(app, h['core']['started_at']))),
                ('Engine', T(app, '%s (%s parked)' % (h['engine']['state'],
                                                      h['engine']['parked']))),
                ('Workers', T(app, 'world %s · knowledge %s · intent %s · plan %s · policy %s' % (
                    h['world']['state'], h['knowledge']['state'], h['intent']['state'],
                    h['plan']['state'], h['policy']['state'])))])
    doc.h('This client')
    s = doc.load('/v1/sync', 'this client')
    if s is not None:
        doc.kv([('Registered as', T(app, '%s (%s)' % (s['client']['name'],
                                                      s['client']['origin']))),
                ('Scopes', T(app, ', '.join(s['client']['scopes']))),
                ('Core instance', T(app, s['core']['instance'])),
                ('Events kept', T(app, '%s – %s' % (s['floor_seq'], s['head_seq'])))])
    doc.h('Motion')
    doc.hint('Nothing in the terminal moves: a change is shown when it is read.')
    doc.h('Emergency stop')
    doc.add('  ' + app.st.paint('Stops every running execution now and refuses new work until '
                                'you re-arm.'))
    doc.act('E', 'Emergency stop', 'control',
            lambda k, v: app.core.post('/v1/estop', {'idempotency_key': k}),
            confirm='Every running execution is killed now and Archeus refuses new work until '
                    'you re-arm it. Missions are not lost; they wait.', reread=['/v1/health'])
    doc.act('R', 'Re-arm', 'control', lambda k, v: app.core.post('/v1/rearm',
                                                                  {'idempotency_key': k}),
            reread=['/v1/health'])


# ── inspectors ───────────────────────────────────────────────────────────────

def inspector(app, doc, kind, id_, tab):
    tabs = INSPECTOR_TABS.get(kind, ['detail'])
    tab = tab if tab in tabs else tabs[0]
    doc.title = clean_title('%s %s' % (kind.replace('_', ' '), id_))    # until its row is read
    fn = {'mission': mission_insp, 'execution': execution_insp, 'session': session_insp,
          'knowledge_item': knowledge_insp}.get(kind)
    if kind == 'approval':
        doc.title = 'Approval'
        return approval_card(app, doc, id_)
    if fn is None and kind not in ROW_PATH:
        doc.title = kind.replace('_', ' ') + ' ' + id_
        doc.empty('This client has no view of a %s yet.' % kind.replace('_', ' '))
        return
    head = len(doc.lines)
    (fn or row_insp)(app, doc, kind, id_, tab)
    if len(tabs) > 1:
        doc.lines.insert(head, {'text': '  ' + '  '.join(
            app.st.paint('[%s] %s' % (TABS[t]['key'], TABS[t]['label']),
                         'text' if t == tab else 'text-2', t == tab) for t in tabs),
            'target': None, 'acts': []})


def _header(app, doc, title, machine, state, path, extra=''):
    doc.title = clean_title(title)
    doc.add('  ' + app.st.badge(machine, state) + ('  ' + extra if extra else '')
            + fresh(app, path))


def mission_insp(app, doc, kind, mid, tab):
    path = '/v1/missions/' + mid
    m = doc.load(path, 'the mission')
    mp = app.read(path + '/plan')['data']
    if m is None:
        return
    line = P.status_line(dict(m, pending_approval={'kind': 'plan'} if m.get('pending_approval_id')
                              else None, tasks=((mp or {}).get('plan') or {}).get('tasks')))
    _header(app, doc, m['title'], 'mission', m['state'], path, T(app, line, 'text-2'))
    if m.get('project_id'):
        doc.add('  ' + app.st.paint('project', 'text'), target=go(view='world',
                                                                   project=m['project_id']))
    reread, v = reread_mission(mid), {'expected_version': m['version']}
    if P.offers('mission', m['state'], 'pause'):
        doc.act('P', 'Pause', 'control', lambda k, _v: app.core.post(
            path + '/pause', dict(v, idempotency_key=k)), reread=reread, ident='pause:' + mid)
    if P.offers('mission', m['state'], 'resume', 'unblock'):
        doc.act('R', 'Resume', 'control', lambda k, _v: app.core.post(
            path + '/resume', dict(v, idempotency_key=k)), reread=reread, ident='resume:' + mid)
    if m['state'] in ('EXECUTING', 'PAUSED'):
        doc.act('S', 'Stop', 'control', lambda k, _v: app.core.post(
            path + '/stop', {'idempotency_key': k}), reread=reread, ident='stop:' + mid,
            confirm='Stop every execution of this mission now. Their processes are killed; the '
                    'mission waits for you, blocked, and resuming it dispatches the work again.')
    {'outcome': outcome, 'plan': plan_tab, 'now': now_tab, 'evidence': evidence, 'why': why,
     'timeline': timeline, 'relations': mission_relations}[tab](app, doc, m, mp)


def outcome(app, doc, m, mp):
    doc.h('Objective')
    doc.para(m['objective'])
    doc.h('Success criteria')
    crit = m.get('success_criteria') or []
    if not crit:
        doc.empty('No success criteria recorded yet.')
    for c in crit:
        doc.add('  ' + T(app, c['text']) + '  ' + T(app, c['check'], 'text-2')
                + ('  ' + app.st.paint('inferred', 'state.thinking')
                   if c.get('origin') == 'inferred' else ''))
    reqs = m.get('requirements') or []
    if reqs:
        doc.h('Requirements')
        for r in reqs:
            doc.add('  ' + T(app, r['text']) + ('  ' + app.st.paint('inferred', 'state.thinking')
                                                if r.get('origin') == 'inferred' else ''))
    doc.h('Scope and control')
    prefs = m.get('resource_preferences') or {}
    doc.kv([('Origin', T(app, str(m.get('origin') or '—'))),
            ('Autonomy profile', T(app, str(m.get('autonomy_profile') or 'the user default'))),
            ('Replans allowed', T(app, str(m.get('max_replans', '—')))),
            ('Mission branch', T(app, str(m.get('integration_branch') or '—'))),
            ('Resource preferences', T(app, json.dumps(prefs)) if prefs else
             app.st.paint('none'))])
    doc.hint('Preferences are for the router (P10). It still checks capability, policy, health '
             'and allocation, and records why it chose what it chose.')

    def lst(s):
        s = (s or '').strip()
        return [x.strip() for x in s.split(',') if x.strip()] if s else None
    doc.act('F', 'Set routing preferences', 'admin',
            lambda k, v: app.core.post('/v1/missions/%s/resources' % m['id'], {
                'idempotency_key': k,
                'preferred_harnesses': lst(v.get('preferred_harnesses')),
                'forbidden_harnesses': lst(v.get('forbidden_harnesses')),
                'preferred_accounts': lst(v.get('preferred_accounts')),
                'forbidden_accounts': lst(v.get('forbidden_accounts')),
                'max_cost_band': (v.get('max_cost_band') or '').strip() or None}),
            fields=[('preferred_harnesses', 'Preferred harnesses (comma-separated ids)', False),
                    ('forbidden_harnesses', 'Forbidden harnesses (comma-separated ids)', False),
                    ('preferred_accounts', 'Preferred accounts (comma-separated ids)', False),
                    ('forbidden_accounts', 'Forbidden accounts (comma-separated ids)', False),
                    ('max_cost_band', 'Cost ceiling: low, medium or high (empty: unchanged)',
                     False)],
            reread=['/v1/missions/' + m['id']], ident='prefs:' + m['id'])


def plan_tab(app, doc, m, mp):
    if mp is None:
        doc.load('/v1/missions/%s/plan' % m['id'], 'the plan')
        return
    p = mp.get('plan')
    if not p:
        doc.empty('No plan yet: the mission is still being understood or planned.')
        return
    by_key = {t['key']: t for t in p['tasks']}
    doc.h('Plan v%s' % p['plan_version'])
    facts = [app.st.badge('plan', p['state'])]
    if p.get('estimated_cost'):
        facts.append(T(app, 'cost band: ' + p['estimated_cost'], 'text-2'))
    facts.append(app.st.paint('in force' if p.get('in_force') else 'not in force', 'text-2'))
    if not p.get('current'):
        facts.append(app.st.paint('planned from context that has changed: ', 'state.attention')
                     + T(app, p.get('current_why'), 'state.attention'))
    doc.add('  ' + '  '.join(facts))
    if isinstance(p.get('summary'), str):
        doc.add('  ' + app.st.paint('Summary (planner, model-written): ', 'text-2')
                + T(app, p['summary']))
    for i, wave in enumerate(p['waves']):
        doc.add('  ' + app.st.paint('Step %d%s' % (i + 1, ' · %d in parallel' % len(wave)
                                                   if len(wave) > 1 else ''), 'text-2'))
        for k in wave:
            t = by_key.get(k)
            if t is None:
                continue
            deps = P.task_dependencies(t, by_key)
            doc.add('    ' + app.st.badge('task', t['state']) + '  ' + T(app, t['key'])
                    + '  ' + T(app, t['title']) + '  ' + T(app, t['kind'], 'text-2')
                    + (app.st.paint('  after ', 'text-2') + T(app, ', '.join(t['depends_on']),
                                                               'text-2') if deps else '')
                    + (app.st.paint('  merge: ', 'text-2')
                       + T(app, t['integration_state'].lower(), 'text-2')
                       if t.get('integration_state') else ''))
    ser = p.get('serialised') or []
    if ser:
        doc.hint('Added by Core so tasks that may touch the same files run one after the '
                 'other: ' + ', '.join('%s → %s' % (s['after'], s['task']) for s in ser))
    doc.h('Versions')
    for v in reversed(mp['versions']):
        inactive = v['state'] in ('SUPERSEDED', 'REJECTED')
        old = next((x['plan_version'] for x in mp['versions']
                    if x['id'] == v.get('supersedes_plan_id')), '?')
        doc.add('  ' + T(app, 'v%s' % v['plan_version'], 'text-2' if inactive else 'text')
                + '  ' + app.st.badge('plan', v['state'])
                + (app.st.paint('  replaces v%s' % old, 'text-2') if v.get('supersedes_plan_id')
                   else '')
                + (app.st.paint('  in force', 'text-2') if v['id'] == p['id'] and p.get('in_force')
                   else ''), target=open_('plan', v['id']))


def now_tab(app, doc, m, mp):
    tasks = ((mp or {}).get('plan') or {}).get('tasks') or []
    live = [t for t in tasks if t['state'] in ('ROUTING', 'RUNNING', 'AWAITING_APPROVAL',
                                               'VERIFYING', 'PAUSED', 'BLOCKED')]
    shown = live or tasks
    if not shown:
        doc.empty('Nothing is running: there is no plan in force yet.')
        return
    if not live:
        doc.hint('Nothing is running now. Every task of the plan in force:')
    for t in shown:
        doc.h(t['key'] + ' · ' + clean_title(t['title']))
        doc.add('  ' + app.st.badge('task', t['state']))
        xl = doc.load('/v1/tasks/%s/executions' % t['id'], 'the executions')
        if xl is None:
            continue
        if not xl['executions']:
            doc.empty('No attempt yet.')
        for e in reversed(xl['executions']):
            execution_row(app, doc, e)


def execution_row(app, doc, e):
    bits = ['  ' + T(app, 'attempt %s' % e['attempt'], 'text'),
            app.st.badge('execution', e['state']), resources(app, e)]
    if e.get('handoff_from'):
        bits.append(app.st.paint('continues an earlier execution (hand-off)', 'text-2'))
    if e.get('stop_reason') or e.get('exit_reason'):
        bits.append(T(app, str(e.get('stop_reason') or e.get('exit_reason')), 'text-2'))
    doc.add('  '.join(bits), target=open_('execution', e['id']))


def evidence(app, doc, m, mp):
    doc.h('Verification')
    vl = doc.load('/v1/missions/%s/verifications' % m['id'], 'the verifications')
    if vl is not None:
        if not vl['verifications']:
            doc.empty('Nothing has been verified yet.')
        for x in vl['verifications']:
            what = ('criterion ' + str(x.get('criterion') or '')) if x['subject']['kind'] == \
                'mission' else 'task check'
            doc.add('  ' + app.st.badge('verification', x['state']) + '  ' + T(app, what) + '  '
                    + T(app, x['verifier'], 'text-2')
                    + (T(app, ' at ' + str(x['revision'])[:10], 'text-2') if x.get('revision')
                       else ''), target=open_('verification', x['id']))
            for c in x['checks']:
                mark = {'pass': '✓', 'fail': '✕'}.get(c['result'], '!')
                doc.add('      ' + app.st.paint(mark) + ' ' + T(app, c['name']) + ' — '
                        + T(app, c['result'])
                        + (T(app, ' (exit %s)' % c['exit_code']) if c.get('exit_code') is not None
                           else ''))
    doc.h('Review')
    rl = doc.load('/v1/missions/%s/reviews' % m['id'], 'the reviews')
    if rl is not None:
        if not rl['reviews']:
            doc.empty('No review yet.')
        for x in rl['reviews']:
            doc.add('  ' + app.st.badge('review', x['state']) + '  ' + T(app, x['reviewer'])
                    + app.st.paint(' · verdict ') + T(app, x.get('verdict') or '—'))
            if not x.get('independent'):
                doc.hint('Reviewed on the same resource — no other was free.', indent=4)
            if x.get('requirements_missing'):
                doc.add('    ' + app.st.paint('Missing: ') + T(app, '; '.join(
                    x['requirements_missing'])))
    if m['state'] == 'REVIEWING':
        doc.hint('Your review is recorded as a review of its own; accepting completes the '
                 'mission (P13).')
        reread, path = reread_mission(m['id']), '/v1/missions/%s/review' % m['id']
        note = [('note', 'Note (optional)', False)]
        for key, label, verdict in (('A', 'Accept result', 'accept'),
                                    ('C', 'Request changes', 'changes_requested'),
                                    ('X', 'Reject', 'reject')):
            doc.act(key, label, 'approve',
                    lambda k, v, verdict=verdict: app.core.post(path, {
                        'verdict': verdict, 'note': v.get('note', ''), 'idempotency_key': k}),
                    fields=note, reread=reread, ident='review:%s:%s' % (m['id'], verdict),
                    confirm={'accept': 'Accept the result: the mission completes. It cannot be '
                                       'undone.',
                             'reject': 'Reject the result. It cannot be undone.'}.get(verdict))


def why(app, doc, m, mp):
    pdl = app.read('/v1/policy-decisions?mission=' + m['id'])['data']
    rdl = app.read('/v1/route-decisions?source=' + m['id'])['data']
    pds = (pdl or {}).get('policy_decisions') or []
    rds = (rdl or {}).get('route_decisions') or []
    last_policy = pds[-1] if pds else None
    # a task's route explains the work; an own call after the end does not
    task_routes = [d for d in rds if (d.get('subject') or {}).get('kind') == 'task']
    last_route = task_routes[-1] if task_routes else None
    reasons = P.explain_state({
        'mission': m,
        'policy': {'decision': last_policy['decision'], 'reason': last_policy['reason']}
        if last_policy else None,
        'route': {'result': last_route.get('result'), 'explanation': last_route.get('explanation'),
                  'unblock_at': last_route.get('unblock_at')} if last_route else None})
    doc.h('Why it is in this state')
    for w in reasons:
        doc.add('  ' + T(app, w['text']) + '  ' + T(app, '(%s)' % w['source'], 'text-2'))
    doc.h('Context used')
    ctx = m.get('context_package')
    if not ctx:
        doc.empty('No context package recorded yet.')
    else:
        doc.add('  ' + app.st.paint('Package ', 'text-2') + T(app, ctx['id'])
                + app.st.paint(' · as of event %s · %s of %s tokens' % (
                    ctx['as_of_seq'], ctx['budget']['used_tokens'],
                    ctx['budget']['limit_tokens']), 'text-2'),
                target=open_('context_package', ctx['id']))
        for it in ctx['items']:
            doc.add('    ' + T(app, str(it['level'])) + '  ' + T(app, it['type']) + '  '
                    + T(app, it['store'], 'text-2') + '  ' + T(app, it['freshness']) + '  '
                    + T(app, it['reason'], 'text-2'), target=open_(it['ref']['kind'],
                                                                   it['ref']['id']))
        if ctx['excluded']:
            doc.add('  ' + app.st.paint('%d excluded' % len(ctx['excluded']), 'text-2'))
            for x in ctx['excluded']:
                doc.add('    ' + T(app, '%s %s (%s): %s' % (x['ref']['kind'], x['ref']['id'],
                                                           x['freshness'], x['reason']),
                                  'text-2'))
        for c in ctx['conflicts']:
            doc.add('  ' + T(app, 'Conflict (%s): %s — preferred %s' % (
                c['kind'], c['reason'], c['preferred']), 'state.attention'))
    doc.h('Policy decisions')
    if pdl is None:
        doc.load('/v1/policy-decisions?mission=' + m['id'], 'the policy decisions')
    elif not pds:
        doc.empty('No policy decision yet.')
    for d in pds:
        doc.add('  ' + T(app, d['stage']) + app.st.paint(' · ') + T(app, d['decision'], bold=True)
                + (T(app, ' (%s)' % d['outcome']) if d.get('outcome') else '')
                + app.st.paint(' — ') + T(app, d['reason']),
                target=open_('policy_decision', d['id']))
    doc.h('Where the work was routed')
    if rdl is None:
        doc.load('/v1/route-decisions?source=' + m['id'], 'the route decisions')
    elif not rds:
        doc.empty('Nothing was routed yet.')
    for d in rds:
        doc.add('  ' + T(app, str(d.get('purpose') or (d.get('subject') or {}).get('kind')
                                  or 'route')) + app.st.paint(' · ')
                + T(app, str(d.get('result') or ('selected' if d.get('selected') else 'none')))
                + '  ' + resources(app, d), target=open_('route_decision', d['id']))
        doc.para(d.get('explanation') or '', indent=4, role='text-2')


def timeline(app, doc, m, mp):
    pages = app.ui.setdefault('timeline:' + m['id'], [None])
    nb = None
    for before in pages:
        path = '/v1/missions/%s/timeline?limit=50%s' % (m['id'], '&before=%s' % before
                                                         if before else '')
        t = doc.load(path, 'the timeline')
        if t is None:
            return
        if not t['events'] and before is None:
            doc.empty('No events yet.')
        for e in t['events']:
            pl = e.get('payload') or {}
            bits = ['  ' + T(app, str(e['seq']), 'text-2'), T(app, e['type']),
                    T(app, e['subject']['kind'])]
            if isinstance(pl.get('reason'), str):
                bits.append(app.st.paint('— ', 'text-2') + T(app, pl['reason'], 'text-2'))
            if isinstance(pl.get('to'), str):
                bits.append(app.st.paint('→ ', 'text-2') + T(app, pl['to'], 'text-2'))
            bits.append(app.st.paint(ago(app, e.get('at')), 'text-2'))
            if e.get('cause_chain'):
                bits.append(app.st.paint('caused by %d earlier event(s)' % len(e['cause_chain']),
                                         'text-2'))
            doc.add(' '.join(bits), target=open_(e['subject']['kind'], e['subject']['id']))
        nb = t.get('next_before')
    if nb:
        doc.act('L', 'Load older events', 'observe',
                lambda k, v: pages.append(nb), sent='Older events read.',
                ident='older:' + m['id'])


def mission_relations(app, doc, m, mp):
    sl = app.read('/v1/sessions?mission=' + m['id'])['data'] or {}
    relations(app, doc, P.mission_edges(m, mp, sl.get('sessions') or []))


def execution_insp(app, doc, kind, eid, tab):
    path = '/v1/executions/' + eid
    x = doc.load(path, 'the execution')
    if x is None:
        return
    _header(app, doc, 'Execution · attempt %s' % x['attempt'], 'execution', x['state'], path)
    doc.add('  ' + app.st.paint('mission', 'text'), target=open_('mission', x['mission_id'],
                                                                'now'))
    doc.add('  ' + resources(app, x))
    if x['state'] in ('STARTING', 'RUNNING', 'PAUSING', 'HANDING_OFF'):
        doc.act('S', 'Stop', 'control', lambda k, v: app.core.post(
            path + '/stop', {'idempotency_key': k}), reread=[path], ident='stopx:' + eid,
            confirm='Stop this execution now: its process is killed. The task and mission '
                    'respond as Core decides (P11).')
    if x['state'] == 'RUNNING':
        doc.act('H', 'Hand off', 'control', lambda k, v: app.core.post(
            path + '/handoff', {'idempotency_key': k}), reread=[path], ident='handoffx:' + eid)
    if tab == 'output':
        o = doc.load(path + '/stream', 'the output')
        if o is None:
            return
        if not o['available']:
            doc.empty('No output yet: the process has not started, or its harness is not '
                      'available here.')
            return
        if o.get('truncated') or len(o['events']) > TAIL:
            doc.hint('Showing the last %d events.' % min(TAIL, len(o['events'])))
        for ev in o['events'][-TAIL:]:
            text = ev['text'] if isinstance(ev.get('text'), str) else json.dumps(ev)
            doc.add('  ' + T(app, str(ev.get('type')), 'text-2') + '  ' + T(app, text))
    elif tab == 'checkpoints':
        cl = doc.load(path + '/checkpoints', 'the checkpoints')
        if cl is None:
            return
        if not cl['checkpoints']:
            doc.empty('No checkpoint: one is derived when an execution that ran ends.')
        for k in cl['checkpoints']:
            doc.kv([('Trigger', T(app, k['trigger'])),
                    ('Next action', T(app, k.get('next_action') or '—')),
                    ('Files changed', T(app, ', '.join(k.get('files_changed') or []) or '—')),
                    ('Open problems', T(app, '; '.join(k.get('open_problems') or []) or '—')),
                    ('As of event', T(app, str(k.get('as_of_seq', '—'))))])
            doc.add()
    else:
        relations(app, doc, P.execution_edges(x))


def session_insp(app, doc, kind, sid, tab):
    path = '/v1/sessions/' + sid
    x = doc.load(path, 'the session')
    if x is None:
        return
    _header(app, doc, 'Session', 'session', x['state'], path,
            T(app, x['id']) + app.st.paint(' · ') + T(app, x['mode']))
    doc.add('  ' + resources(app, x))
    import uuid
    reread = ['/v1/sessions']
    if x['state'] != 'LOST':
        doc.act('R', 'Resume', 'control', lambda k, v: app.core.post(path + '/resume', {
            'request_id': str(uuid.uuid4()), 'deliver_brief': True, 'idempotency_key': k}),
            reread=reread, ident='resumes:' + sid)
    if x['state'] == 'OPEN':
        doc.act('C', 'Close', 'control', lambda k, v: app.core.post(path + '/close', {
            'idempotency_key': k}), reread=reread, ident='close:' + sid)
    harnesses = [h['id'] for h in (app.read('/v1/harnesses')['data'] or {}).get('harnesses', [])]
    doc.act('H', 'Hand off', 'control', lambda k, v: app.core.post(path + '/handoff', {
        'request_id': str(uuid.uuid4()), 'harness_id': v['harness'],
        'account_id': v.get('account') or None, 'model': v.get('model') or None,
        'reason': v.get('reason') or None, 'idempotency_key': k}),
        fields=[('harness', 'Target harness (required): %s' % (', '.join(harnesses) or '—'),
                 True),
                ('account', 'Account (optional)', False),
                ('model', 'Model (optional, in that harness’s own names)', False),
                ('reason', 'Reason', False)],
        reread=reread, ident='handoffs:' + sid)
    doc.hint('Hand off: a new session starts on the harness you choose, with what Core renders '
             'of the current state. This session is not changed.')
    if tab == 'brief':
        session_brief(app, doc, sid)
    elif tab == 'lineage':
        for y in (x.get('lineage') or []) + [x] + (x.get('targets') or []):
            me = y['id'] == x['id']
            doc.add('  ' + (app.st.paint('this session', 'text', bold=True) if me
                            else T(app, y['id'])) + app.st.paint(' · harness ')
                    + T(app, y['harness_id']) + '  ' + app.st.badge('session', y['state']),
                    target=None if me else open_('session', y['id']))
    else:
        relations(app, doc, P.session_edges(x, x))


def session_brief(app, doc, sid):
    b = doc.load('/v1/sessions/%s/brief' % sid, 'the brief')
    if b is None:
        return
    m, ch, ctx = b.get('mission'), b.get('changes') or {}, b.get('context') or {}
    doc.hint('As of event %s. This is rebuilt from current state; the transcript is not '
             'replayed.' % b['as_of_seq'])
    doc.h('What mattered')
    if m:
        doc.add('  ' + T(app, m.get('title')) + app.st.paint(' — ') + T(app, m.get('objective'))
                + ('  ' + app.st.badge('mission', m['state']) if m.get('state') else ''),
                target=open_('mission', m['id']))
    else:
        doc.empty('This session continues no mission.')
    doc.h('What changed since this session last looked')
    if not ch.get('groups'):
        doc.empty('Nothing changed.')
    for g in ch.get('groups') or []:
        doc.add('  ' + T(app, '%s %s · %s · %s' % (g['ref']['kind'], g['ref']['id'],
                                                   g['headline'], g['count'])),
                target=open_(g['ref']['kind'], g['ref']['id']))
    doc.h('What is unresolved')
    if not ctx.get('missing_information'):
        doc.empty('No missing information recorded.')
    for s in ctx.get('missing_information') or []:
        doc.add('  ' + T(app, s))
    if ctx.get('stale'):
        doc.add('  ' + app.st.paint('The context this session had is stale: resuming rebuilds '
                                    'it.', 'state.attention'))
    doc.h('What to see next')
    if m and m.get('id'):
        doc.add('  ' + app.st.paint('Why the mission is where it is', 'text'),
                target=open_('mission', m['id'], 'why'))
    else:
        doc.empty('Nothing waits here.')


def knowledge_insp(app, doc, kind, kid, tab):
    path = '/v1/knowledge/' + kid
    k = doc.load(path, 'the knowledge item')
    if k is None:
        return
    _header(app, doc, str(k.get('title') or k['id']), 'knowledge_item', k['state'], path,
            T(app, str(k.get('type') or '').lower(), 'text-2'))
    reread = ['/v1/knowledge', '/v1/attention']
    ver = {'expected_version': int(k['version'])}
    if k['state'] == 'CANDIDATE':
        doc.act('C', 'Confirm', 'control', lambda key, v: app.core.post(
            path + '/confirm', dict(ver, idempotency_key=key)), reread=reread,
            ident='confirmk:' + kid)
        doc.act('R', 'Reject', 'control', lambda key, v: app.core.post(
            path + '/reject', dict(ver, idempotency_key=key)), reread=reread,
            ident='rejectk:' + kid, confirm='Reject this item: it is never used as context.')
    if k['state'] == 'CONFIRMED':
        doc.act('X', 'Retract', 'control', lambda key, v: app.core.post(
            path + '/retract', dict(ver, idempotency_key=key)), reread=reread,
            confirm='Retract this item: it stops being used as context. The row and its '
                    'provenance are kept.', ident='retract:' + kid)
    if tab != 'detail':
        return relations(app, doc, P.knowledge_edges(k))
    doc.para(str(k.get('text') or ''))
    doc.kv([('Origin', T(app, str(k.get('origin') or '—'))),
            ('Source', T(app, '%s %s' % (k.get('source_kind') or '—',
                                         json.dumps(k['source_ref']) if k.get('source_ref')
                                         else ''))),
            ('Observed', T(app, ago(app, k.get('observed_at')))),
            ('Produced by (route)', T(app, str(k['route_decision_id'])) if k.get(
                'route_decision_id') else app.st.paint('the user or a deterministic pass'))])
    doc.h('Supersession chain (oldest first)')
    for c in k['chain']:
        doc.add('  ' + (T(app, c + ' (this item)', bold=True) if c == kid else T(app, c)),
                target=None if c == kid else open_('knowledge_item', c))


ROW_PATH = {'plan': lambda i: '/v1/plans/' + i,
            'verification': lambda i: '/v1/verifications/' + i,
            'route_decision': lambda i: '/v1/route-decisions/' + i,
            'policy_decision': lambda i: '/v1/policy-decisions/' + i,
            'context_package': lambda i: '/v1/context/' + i,
            'automation_run': lambda i: '/v1/automation-runs/' + i,
            'project': lambda i: '/v1/projects/' + i,
            'repository': lambda i: '/v1/repositories/%s/inspections' % i}
ROW_TITLE = {'plan': 'Plan version', 'verification': 'Verification',
             'route_decision': 'Route decision', 'policy_decision': 'Policy decision',
             'context_package': 'Context package', 'automation_run': 'Automation run'}
ROW_MACHINE = {'plan': 'plan', 'verification': 'verification', 'automation_run': 'automation_run'}


def row_insp(app, doc, kind, id_, tab):
    path = ROW_PATH[kind](id_)
    r = doc.load(path, 'the ' + kind.replace('_', ' '))
    if r is None:
        return
    doc.title = ROW_TITLE.get(kind, kind.replace('_', ' '))
    meta = [app.st.badge(ROW_MACHINE[kind], r['state'])] if isinstance(r.get('state'), str) \
        and kind in ROW_MACHINE else []
    doc.add('  ' + '  '.join(meta + [T(app, id_)]) + fresh(app, path))
    if tab == 'relations':
        edges = {'plan': P.plan_edges, 'verification': P.verification_edges,
                 'automation_run': lambda x: P.run_edges(x['run'])}[kind](r)
        return relations(app, doc, edges)
    {'plan': plan_detail, 'verification': verification_detail,
     'route_decision': route_detail, 'automation_run': run_detail}.get(kind, fields)(app, doc, r)


def plan_detail(app, doc, p):
    doc.kv([('Version', T(app, 'v%s' % p['plan_version'])),
            ('In force', T(app, str(p.get('in_force')))),
            ('Cost band', T(app, str(p.get('estimated_cost') or '—'))),
            ('Digest', T(app, str(p.get('digest') or '—')))])
    for t in p['tasks']:
        doc.add('  ' + app.st.badge('task', t['state']) + '  ' + T(app, t['key']) + '  '
                + T(app, t['title']))


def verification_detail(app, doc, v):
    doc.kv([('Verifier', T(app, v['verifier'])),
            ('Revision checked', T(app, str(v.get('revision') or '—')))])
    if v.get('execution_id'):
        doc.add('  ' + app.st.paint('Of execution ', 'text-2') + T(app, v['execution_id']),
                target=open_('execution', v['execution_id']))
    ev = {e['check']: e for e in v.get('evidence') or []}
    for c in v['checks']:
        doc.add('  ' + T(app, c['name']) + ': ' + T(app, c['result'])
                + (' — ' + T(app, c['detail']) if c.get('detail') else '') + '  '
                + app.st.paint('(evidence kept)' if (ev.get(c['name']) or {}).get('available')
                               else '(no evidence file)', 'text-2'))


def route_detail(app, doc, d):
    """A routing decision as P10 recorded it: what was selected, the result, what
    it fell back from, every candidate with the step that eliminated it and why,
    and Core's own explanation. No model reasoning exists here to show."""
    doc.add('  ' + resources(app, d))
    doc.kv([('Result', T(app, str(d.get('result') or '—'))),
            ('Fell back from', T(app, str(d.get('fallback_from') or '—'))),
            ('Decided by', T(app, str(d.get('decided_by') or '—')))])
    doc.para(d.get('explanation') or '')
    doc.h('Candidates')
    for c in d.get('candidates') or []:
        doc.add('  ' + T(app, json.dumps(c.get('resource') or c.get('candidate') or c)) + '  '
                + T(app, str(c.get('eliminated_at_step') or c.get('eliminated_at') or 'kept'),
                    'text-2') + '  ' + T(app, str(c.get('reason') or '—')))


def run_detail(app, doc, x):
    """An automation run's causal chain, top to bottom: the event and what caused
    it, the automation and the run, and what the run caused."""
    doc.h('Triggering event')
    if x.get('event'):
        doc.kv([('Type', T(app, str(x['event']['type']))),
                ('Event', T(app, str(x['event']['seq']))),
                ('Caused by', T(app, '%d earlier event(s)' % len(x['event'].get('cause_chain')
                                                                 or [])))])
    else:
        doc.empty('The event is no longer kept.')
    doc.h('The run')
    doc.add('  ' + app.st.badge('automation_run', x['run']['state']))
    doc.kv([('Depth', T(app, str(x['run']['depth']))),
            ('Reason', T(app, str(x['run'].get('reason') or '—'))),
            ('Why', T(app, json.dumps(x.get('why'))))])
    doc.h('What it caused')
    if x.get('mission'):
        doc.add('  ' + T(app, str(x['mission'].get('title') or x['mission']['id'])),
                target=open_('mission', str(x['mission']['id'])))
    else:
        doc.empty('No mission.')


def fields(app, doc, row):
    doc.kv([(k, T(app, json.dumps(v) if isinstance(v, (dict, list)) else str(v)))
            for k, v in row.items()])


# ── the navigation table's screens ───────────────────────────────────────────

SCREENS = {'now': now, 'work': work, 'world': world, 'attention': attention, 'control': control}

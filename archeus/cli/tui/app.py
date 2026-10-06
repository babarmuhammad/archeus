"""The TUI shell (p17-design-gate §3, §7, §8): one connection, one cache keyed by
read path, one navigation table, one inspector — the SPA's App.tsx and
data/cache.ts, in a terminal. Every state on screen is a state Core returned;
the stream only says what to read again; a command is sent, then read back,
never assumed.
"""

import queue
import shutil
import sys
import time

from . import client as C
from . import screens as SC
from . import sync as S
from ._tables import DESTINATIONS, INSPECTOR_TABS, TABS
from .view import Style, clean

RESERVED = ('q', '?', ':')
STATUS_S = 4                    # a status-line message lasts 4 s (design system §15)
SETTLE_MS = 4000                # "Back — read again" stays up this long (as the SPA)
MIN_WIDTH = 60
ONCE_WAIT_S = 3


class App:
    def __init__(self, core, style, *, size=None, clock=time.time, stream=True):
        self.core, self.st, self.clock = core, style, clock
        self.size = size or (lambda: tuple(shutil.get_terminal_size((100, 30))))
        self.conn = S.initial(self.now_ms())
        self.cache = {}
        self.q = queue.Queue()
        self.stream = C.Stream(core, self.q) if stream else None
        self.route, self.under = {'view': 'now'}, {'view': 'now'}
        self.cursor = 0
        self.status = None                  # (text, until_ms, error)
        self.mode = None                    # prompt / confirm / help / picker
        self.ui = {}                        # per-screen view state (never Core's state)
        self.keys = {}                      # action ident -> the idempotency key to use next
        self.settle_at = None
        self.quit = False
        self.dirty = True
        self._doc = None

    # ── time and Core ──

    def now_ms(self):
        return self.clock() * 1000

    def read(self, path):
        """The cached answer of GET *path*, read now when it is missing, stale or
        from an older connection generation. Holds Core's answers only."""
        e = self.cache.get(path)
        if e is None or e['stale'] or e['gen'] < self.conn['gen']:
            gen = self.conn['gen']
            try:
                data, seq = self.core.get(path)
                e = {'data': data, 'error': None, 'gen': gen, 'seq': seq, 'stale': False}
            except C.CoreError as err:
                if err.status == 401:
                    self.signal('unauthorized')
                e = {'data': (e or {}).get('data'), 'error': err, 'gen': gen,
                     'seq': (e or {}).get('seq'), 'stale': False}
            self.cache[path] = e
        return e

    def invalidate(self, pred):
        for path, e in self.cache.items():
            if pred(path):
                e['stale'] = True
                self.dirty = True

    def can(self, scope):
        me = (self.read('/v1/sync')['data'] or {}).get('client') or {}
        return scope in (me.get('scopes') or [])

    def signal(self, sig):
        before = self.conn
        self.conn = S.next_state(self.conn, sig, self.now_ms())
        if self.conn is not before:
            self.dirty = True
            if self.conn['gen'] != before['gen']:
                self.invalidate(lambda p: True)
            if self.conn['conn'] == 'resynced':
                self.settle_at = self.now_ms() + SETTLE_MS

    def pump(self):
        """Apply what the stream said: signals move the connection machine, a
        frame only marks the reads it names stale. Returns whether to redraw."""
        while True:
            try:
                kind, v = self.q.get_nowait()
            except queue.Empty:
                break
            if kind == 'signal':
                self.signal(v)
            else:
                self.invalidate(S.stale_by(v))
        now = self.now_ms()
        if self.settle_at is not None and now >= self.settle_at:
            self.settle_at = None
            self.signal('settled')
        if self.status and now >= self.status[1]:
            self.status = None
            self.dirty = True
        return self.dirty

    def say(self, text, error=False):
        self.status = (clean(text), self.now_ms() + STATUS_S * 1000, error)
        self.dirty = True

    # ── navigation ──

    def go(self, route):
        if route.get('view') == 'object':
            if self.route.get('view') != 'object':
                self.under = self.route
        self.route, self.cursor, self.dirty = dict(route), 0, True

    def open(self, kind, id_, tab=None):
        self.go({'view': 'object', 'kind': kind, 'id': id_, 'tab': tab})

    def back(self):
        r = self.route
        if r['view'] == 'object':
            self.go(self.under)
        elif r.get('project'):
            self.go({'view': r['view']})

    # ── one frame ──

    def build(self, width):
        doc = SC.Doc(self, width)
        r = self.route
        if r['view'] == 'object':
            SC.inspector(self, doc, r['kind'], r['id'], r.get('tab'))
        else:
            doc.title = SC.dest(r['view'])['label']
            SC.SCREENS[r['view']](self, doc)
        self._doc = doc
        return doc

    def rows(self):
        return [i for i, x in enumerate(self._doc.lines) if x['target'] or x['acts']]

    def actions(self):
        """The commands on screen now: the focused row's, then the screen's."""
        rows = self.rows()
        focused = self._doc.lines[rows[self.cursor]]['acts'] if rows else []
        return focused + self._doc.acts

    def frame(self):
        width, height = self.size()
        width = max(width, MIN_WIDTH)
        doc = self.build(width - 2)
        rows = self.rows()
        self.cursor = min(self.cursor, max(0, len(rows) - 1))
        focus = rows[self.cursor] if rows else None
        top = [self.top_line(width)]
        banner = S.BANNER[self.conn['conn']]
        if banner:
            top.append(self.st.paint(banner, 'state.attention'))
        top.append(self.st.paint(clean(doc.title), 'text', bold=True))
        acts = self.actions()
        foot = [self.action_line(acts, width), self.status_line(width)]
        body_h = max(3, height - len(top) - len(foot))
        body = []
        for i, x in enumerate(doc.lines):
            # focus is a marker, never reverse video or colour alone (§9)
            body.append((self.st.paint('› ', 'focus', bold=True) if i == focus else '  ')
                        + x['text'])
        start = 0
        if focus is not None and focus >= body_h:
            start = focus - body_h + 1
        body = body[start:start + body_h]
        body += [''] * (body_h - len(body))
        lines = top + body + foot
        if self.mode:
            lines = self.overlay(lines, width, height)
        return [self.st.line(x, width) for x in lines[:height]]

    def top_line(self, width):
        att = (self.cache.get('/v1/attention') or {}).get('data') or {}
        cur = self.route['view'] if self.route['view'] != 'object' else self.under['view']
        parts = [self.st.paint('ARCHEUS', 'text', bold=True)]
        for d in DESTINATIONS:
            if d['id'] == 'attention':
                continue
            label = '%s %s' % (d['tui'], d['label'])
            parts.append(self.st.paint('[%s]' % label, 'text', bold=True) if d['id'] == cur
                         else self.st.paint(label, 'text-2'))
        n = att.get('count', 0)
        a = next(d for d in DESTINATIONS if d['id'] == 'attention')
        parts.append(self.st.paint('%s %s %d attention' % (a['tui'], self.st.glyph(
            {'cls': 'needs_you', 'glyph': '◆'}), n), 'state.attention' if n else 'text-2'))
        parts.append(self.st.paint(time.strftime('%H:%M', time.localtime(self.clock())),
                                   'text-2'))
        return '  '.join(parts)

    def action_line(self, acts, width):
        out = []
        for a in acts:
            why = self.why_not(a)
            out.append(self.st.paint('[%s] %s' % (a['key'], a['label']),
                                     'text-2' if why else 'text'))
        return '  '.join(out)

    def status_line(self, width):
        if self.status:
            return self.st.paint(self.status[0], 'state.blocked' if self.status[2] else 'text')
        where = 'Esc back  ' if self.route['view'] == 'object' or self.route.get('project') \
            else ''
        return self.st.paint('↑↓ move  ⏎ open  %s? help  : command  q quit' % where, 'text-2')

    def overlay(self, lines, width, height):
        m = self.mode
        box = []
        if m['kind'] == 'prompt':
            name, label, required = m['act']['fields'][m['i']]
            # a field label may name Core's values (the harness ids), so it is cleaned
            box = [self.st.paint(m['act']['label'], 'text', bold=True),
                   self.st.t(label + ('' if required else ' (optional)'), 'text-2'),
                   '> ' + clean(m['buf']),
                   self.st.paint('⏎ next  Esc cancel', 'text-2')]
        elif m['kind'] == 'confirm':
            from .view import wrap
            box = [self.st.paint(m['act']['label'], 'text', bold=True)]
            box += [self.st.paint(x) for x in wrap(m['act']['confirm'], width - 2)]
            box.append(self.st.paint('Type y to confirm; any other key cancels.', 'focus'))
        elif m['kind'] == 'help':
            box = self.help_lines()
        elif m['kind'] == 'picker':
            box = [self.st.paint('Go to, or tell Archeus', 'text', bold=True), ': ' + m['q']]
            for i, (label, _t) in enumerate(m['hits'][:max(1, height - 6)]):
                box.append((self.st.paint('› ', 'focus') if i == m['i'] else '  ')
                           + self.st.paint(clean(label)))
            box.append(self.st.paint('↑↓ choose  ⏎ go  Esc cancel', 'text-2'))
        rule = self.st.paint('─' * width, 'line-strong')
        box = [rule] + box
        keep = max(0, min(len(lines), height) - len(box))
        return lines[:keep] + box

    def help_lines(self):
        out = [self.st.paint('Keys', 'text', bold=True)]
        out.append('  ' + '   '.join('%s %s' % (d['tui'], d['label']) for d in DESTINATIONS))
        out.append('  ↑↓ or j k move   ⏎ open   [ ] page   Tab next section   Esc back')
        out.append('  : go to or tell Archeus   ? help   q quit')
        if self.route['view'] == 'object':
            tabs = INSPECTOR_TABS.get(self.route['kind'], ['detail'])
            out.append('  Tabs: ' + '   '.join('%s %s' % (TABS[t]['key'], TABS[t]['label'])
                                              for t in tabs))
        acts = self.actions()
        if acts:
            out.append('  Commands (upper case): ' + '   '.join(
                '%s %s' % (a['key'], a['label']) for a in acts))
        out.append(self.st.paint('Any key closes this.', 'text-2'))
        return out

    # ── keys ──

    def handle(self, ev):
        self.dirty = True
        if self.mode:
            return self.handle_mode(ev)
        k = ev[0]
        rows = self.rows() if self._doc else []
        if k in ('up', 'down'):
            self.move(-1 if k == 'up' else 1, rows)
        elif k == 'enter':
            if rows:
                self.follow(self._doc.lines[rows[self.cursor]]['target'])
        elif k == 'esc':
            self.back()
        elif k == 'tab':
            self.next_part()
        elif k == 'char':
            self.char(ev[1], rows)

    def char(self, c, rows):
        if c in ('q', '\x03'):
            self.quit = True
        elif c == '?':
            self.mode = {'kind': 'help'}
        elif c == ':':
            self.mode = {'kind': 'picker', 'q': '', 'hits': self.hits(''), 'i': 0}
        elif c in ('j', 'k'):
            self.move(1 if c == 'j' else -1, rows)
        elif c in ('[', ']'):
            self.move((-1 if c == '[' else 1) * max(1, self.size()[1] - 8), rows)
        elif c.isupper():
            act = next((a for a in self.actions() if a['key'] == c), None)
            if act:
                self.press(act)
        elif c == 'f' and self.route == {'view': 'world'} and \
                self.ui.get('world') == 'knowledge':
            states = SC.KNOWLEDGE_STATES
            cur = self.ui.get('knowledge_state', '')
            self.ui['knowledge_state'] = states[(states.index(cur) + 1) % len(states)]
        else:
            d = next((d for d in DESTINATIONS if d['tui'] == c), None)
            if d:
                return self.go({'view': d['id']})
            if self.route['view'] == 'object':
                tabs = INSPECTOR_TABS.get(self.route['kind'], ['detail'])
                t = next((t for t in tabs if TABS[t]['key'] == c), None)
                if t:
                    self.route = dict(self.route, tab=t)
                    self.cursor = 0

    def move(self, n, rows):
        if rows:
            self.cursor = max(0, min(len(rows) - 1, self.cursor + n))

    def follow(self, target):
        if not target:
            return
        if target[0] == 'open':
            self.open(target[1], target[2], target[3])
        else:
            self.go(target[1])

    def next_part(self):
        r = self.route
        if r['view'] == 'control':
            ids = [s['id'] for s in SC.CONTROL_SECTIONS]
            cur = r.get('section') or 'autonomy'
            self.go({'view': 'control', 'section': ids[(ids.index(cur) + 1) % len(ids)]})
        elif r == {'view': 'world'}:
            self.ui['world'] = 'knowledge' if self.ui.get('world') != 'knowledge' else 'projects'
            self.cursor = 0
        elif r['view'] == 'object':
            tabs = INSPECTOR_TABS.get(r['kind'], ['detail'])
            cur = r.get('tab') if r.get('tab') in tabs else tabs[0]
            self.route = dict(r, tab=tabs[(tabs.index(cur) + 1) % len(tabs)])
            self.cursor = 0

    # ── the command line (the SPA's command bar) ──

    def hits(self, q):
        """Go to a destination, a loaded mission or a loaded project, or tell
        Archeus: the text goes to the primary conversation unparsed (no client
        grammar, p16 §5)."""
        missions = ((self.cache.get('/v1/missions') or {}).get('data') or {}).get('missions', [])
        projects = ((self.cache.get('/v1/projects') or {}).get('data') or {}).get('projects', [])
        hits = [('Go to ' + d['label'], ('go', {'view': d['id']})) for d in DESTINATIONS]
        hits += [('Mission: ' + clean(m['title']), ('open', 'mission', m['id'], None))
                 for m in missions]
        hits += [('Project: ' + clean(p['name']), ('go', {'view': 'world', 'project': p['id']}))
                 for p in projects]
        needle = q.strip().lower()
        hits = [h for h in hits if not needle or needle in h[0].lower()]
        if needle:
            hits.append(('Tell Archeus: ' + q.strip(), ('tell', q.strip())))
        return hits

    # ── modes ──

    def handle_mode(self, ev):
        m, k = self.mode, ev[0]
        if m['kind'] == 'help':
            self.mode = None
        elif m['kind'] == 'confirm':
            act, values = m['act'], m['values']
            self.mode = None
            if k == 'char' and ev[1] in ('y', 'Y'):
                self.execute(act, values)
            else:
                self.say('Cancelled — nothing was sent.')
        elif m['kind'] == 'prompt':
            self.prompt_key(m, ev)
        elif m['kind'] == 'picker':
            self.picker_key(m, ev)

    def prompt_key(self, m, ev):
        k = ev[0]
        if k == 'esc':
            self.mode = None
            return self.say('Cancelled — nothing was sent.')
        if k == 'back':
            m['buf'] = m['buf'][:-1]
        elif k == 'char' and ev[1] >= ' ':
            m['buf'] += ev[1]
        elif k == 'enter':
            name, label, required = m['act']['fields'][m['i']]
            if required and not m['buf'].strip():
                return self.say('%s: required.' % label, error=True)
            m['values'][name] = m['buf']
            m['i'], m['buf'] = m['i'] + 1, ''
            if m['i'] == len(m['act']['fields']):
                self.mode = None
                self.confirm_or_run(m['act'], m['values'])

    def picker_key(self, m, ev):
        k = ev[0]
        if k == 'esc':
            self.mode = None
        elif k in ('up', 'down'):
            m['i'] = max(0, min(len(m['hits']) - 1, m['i'] + (1 if k == 'down' else -1)))
        elif k == 'back':
            m['q'] = m['q'][:-1]
            m['hits'], m['i'] = self.hits(m['q']), 0
        elif k == 'char' and ev[1] >= ' ':
            m['q'] += ev[1]
            m['hits'], m['i'] = self.hits(m['q']), 0
        elif k == 'enter':
            self.mode = None
            if not m['hits']:
                return
            _label, target = m['hits'][m['i']]
            if target[0] == 'tell':
                self.execute(SC.Act('', 'Tell Archeus', 'control', lambda key, v: self.core.post(
                    '/v1/conversations/primary/messages', {'text': target[1],
                                                           'idempotency_key': key}),
                    reread=['/v1/conversations/primary/messages'], ident='tell:' + target[1],
                    sent='Sent — Archeus is reading it.'), {})
            else:
                self.follow(target)

    # ── commands (the SPA's ActionButton) ──

    def why_not(self, act):
        if not self.can(act['scope']):
            return 'This client does not hold the “%s” scope.' % act['scope']
        if not S.can_command(self.conn['conn']):
            return 'Not connected — nothing is sent while reconnecting.'
        return act['disabled']

    def press(self, act):
        why = self.why_not(act)
        if why:
            return self.say(why, error=True)
        if act['fields']:
            self.mode = {'kind': 'prompt', 'act': act, 'values': {}, 'i': 0, 'buf': ''}
            return None
        return self.confirm_or_run(act, {})

    def confirm_or_run(self, act, values):
        if act['confirm']:
            self.mode = {'kind': 'confirm', 'act': act, 'values': values}
        else:
            self.execute(act, values)

    def execute(self, act, values):
        """Send once; retry once with the same key only when Core asks; never
        assume the result — every read the command may have changed is read again."""
        key = self.keys.get(act['ident']) or S.new_key()
        outcome = 'ok'
        try:
            try:
                out = act['run'](key, values)
            except C.CoreError as e:
                if not S.retryable(e.refusal()):
                    raise
                out = act['run'](key, values)
            if act['done']:
                act['done'](out, values)
            self.say(act['sent'] or 'Sent — reading it again.')
        except C.CoreError as e:
            outcome = 'network' if e.code == 'network' else 'refused'
            self.say(S.explain(e.refusal()), error=True)
        finally:
            self.keys[act['ident']] = S.key_after(key, outcome)
            for p in act['reread']:
                self.invalidate(lambda x, p=p: x == p or x.startswith(p + '/')
                                or x.startswith(p + '?'))


def show(lines, live):
    """A live VT terminal gets the diffed frame; anything else, plain lines (the
    legacy fallback clears with a subprocess on an old console, which this
    client never wants)."""
    if live:
        from claude_sessions import render
        render.render_frame(lines)
    else:
        sys.stdout.write('\n'.join(lines) + '\n')
        sys.stdout.flush()


def run(app, *, live, once=False):
    """The loop: redraw when something changed, read one key when one is there.
    The terminal is restored on every way out."""
    from claude_sessions import render, term
    if live:
        render.screen_init()
    if app.stream is not None:
        app.stream.start()
    if once:
        # one screen, read on a connection that is actually open, not a pretended one
        deadline = time.monotonic() + ONCE_WAIT_S
        while app.conn['conn'] == 'connecting' and time.monotonic() < deadline:
            app.pump()
            time.sleep(0.05)
    size = app.size()
    try:
        while not app.quit:
            now = app.size()
            if now != size:
                size, app.dirty = now, True
            if app.pump():
                app.dirty = False
                show(app.frame(), live)
            if once:
                return
            if term.kbhit():
                ev = term.key_event()           # None: a key this client ignores
                if ev:
                    app.handle(ev)
            else:
                time.sleep(0.03)
    finally:
        if app.stream is not None:
            app.stream.stop()
        if live:
            render.screen_restore()
        term.restore()


NO_CORE = {
    'not_running': (1, 'Archeus Core is not running. Start it with `archeus core`; the '
                       'terminal client never starts it.'),
    'unreadable': (2, 'Core is running, but its discovery file is unreadable; nothing was sent '
                      'to it.'),
    'no_token': (2, 'Core is running, but this home has no local token; nothing was sent.'),
}


def main(argv):
    """`archeus tui [--open kind/id] [--once] [--light]` (p17-design-gate A4)."""
    import argparse
    import os
    from claude_sessions import term
    ap = argparse.ArgumentParser(prog='archeus tui', description='The Archeus terminal client.')
    ap.add_argument('--open', metavar='KIND/ID', help='open an object, e.g. mission/msn_...')
    ap.add_argument('--once', action='store_true', help='print one screen and exit')
    ap.add_argument('--light', action='store_true', help='colours for a light terminal')
    a = ap.parse_args(argv)
    core, why = C.Core.local()
    if core is None:
        code, text = NO_CORE[why]
        print(text)
        return code
    try:
        sys.stdout.reconfigure(errors='replace')
    except (AttributeError, ValueError):
        pass
    tty = sys.stdout.isatty()
    vt = term.enable_vt() if tty else False
    style = Style.detect(os.environ, sys.stdout, vt, 'light' if a.light else None)
    app = App(core, style)
    if a.open:
        kind, _, id_ = a.open.partition('/')
        app.open(kind, id_)
    try:
        run(app, live=tty and vt and not a.once, once=a.once)
    except KeyboardInterrupt:
        return 130
    return 0

"""The TUI's acceptance scenarios (p17-design-gate §12.1, T02-T15) against a real
in-process Core. T01 is the G3 judge function (tests/v1/judge/test_g03_one_model.py);
T07's transport half is in test_client.py."""

import json
import time
from urllib.parse import parse_qs, urlparse

import pytest

from archeus.cli.tui import app as A, client as C, screens as SC
from archeus.cli.tui._tables import CONTROL_SECTIONS, DESTINATIONS, INSPECTOR_TABS, TABS
from archeus.cli.tui.view import Style
from claude_sessions import render
from v1.judge.http import request

from .conftest import (SGR, app_on, drive, harness, mission, plain, press, row, settled, spy,
                       state)


# ── T02 keyboard reach ───────────────────────────────────────────────────────

def test_T02_every_destination_section_and_tab_is_reached_by_its_key(monkeypatch, core):
    mid = mission(core, 'Reach everything')
    settled(core, mid, 'COMPLETED')
    app = app_on(core)
    seen = []
    orig = app.frame

    def frame():
        out = orig()
        seen.append((dict(app.route), render.strip_ansi('\n'.join(out))))
        return out
    app.frame = frame
    script = []
    for d in DESTINATIONS:
        script += harness.typed(d['tui'])
    script += harness.typed('4') + [b'\t'] * len(CONTROL_SECTIONS)
    script += harness.typed('2') + harness.ENTER                        # Work -> the mission
    for t in INSPECTOR_TABS['mission']:
        script += harness.typed(TABS[t]['key'])
    script += harness.typed('?') + harness.typed('x') + harness.ESC
    drive(monkeypatch, app, script)
    views = {r['view'] for r, _ in seen}
    assert {d['id'] for d in DESTINATIONS} <= views
    sections = {r.get('section') or 'autonomy' for r, _ in seen if r['view'] == 'control'}
    assert sections == {s['id'] for s in CONTROL_SECTIONS}
    tabs = {r.get('tab') for r, _ in seen if r['view'] == 'object'} - {None}
    assert tabs == set(INSPECTOR_TABS['mission'])
    # `?` lists exactly the key table, then any key closes it
    help_frames = [s for _r, s in seen if s.count('Keys') and 'Any key closes this.' in s]
    assert help_frames
    for d in DESTINATIONS:
        assert '%s %s' % (d['tui'], d['label']) in help_frames[0]
    assert app.route['view'] == 'work'                       # Esc went back from the inspector


def test_T02_the_key_table_never_overlaps(core):
    """Destinations, reserved keys, a kind's tab keys and every command key on a
    screen never collide, by construction."""
    global_keys = [d['tui'] for d in DESTINATIONS] + list(A.RESERVED)
    assert len(set(global_keys)) == len(global_keys)
    for kind, tabs in INSPECTOR_TABS.items():
        keys = [TABS[t]['key'] for t in tabs]
        assert len(set(keys)) == len(keys) and not set(keys) & set(global_keys), kind
        assert all(k.islower() for k in keys)
    mid = mission(core, 'Keys')
    settled(core, mid, 'COMPLETED')
    app = app_on(core)
    for route in [{'view': d['id']} for d in DESTINATIONS] + [
            {'view': 'control', 'section': s['id']} for s in CONTROL_SECTIONS] + [
            {'view': 'object', 'kind': 'mission', 'id': mid, 'tab': t}
            for t in INSPECTOR_TABS['mission']]:
        app.go(route)
        app.frame()
        for n in range(len(app.rows())):
            app.cursor = n
            keys = [a['key'] for a in app.actions()]
            assert len(set(keys)) == len(keys), (route, keys)
            assert all(k.isupper() for k in keys), (route, keys)


# ── T03 approval ─────────────────────────────────────────────────────────────

def test_T03_a_plan_is_approved_from_attention_confirmed_in_prose_and_read_back(deploy):
    mid = mission(deploy, 'Deploy the docs')
    settled(deploy, mid, 'APPROVAL_REQUIRED')
    app = app_on(deploy)
    s = spy(app)
    app.go({'view': 'attention'})
    screen = plain(app)
    for text in ('Why it asks', 'If you approve', 'If you reject', 'Expires', 'deploy'):
        assert text in screen, text
    row(app, lambda x: any(a['key'] == 'A' for a in x['acts']))
    (aid,) = [a['ident'].split(':', 1)[1] for a in app.actions() if a['key'] == 'A']
    before = app.cache['/v1/approvals/' + aid]['data']
    as_read = json.dumps(before, sort_keys=True)
    shown = press(app, 'A')
    assert 'Approve:' in shown and 'Type y to confirm' in shown      # prose, before sending
    assert not s.posts
    press(app, 'n')                                                    # anything else cancels
    assert not s.posts and 'nothing was sent' in plain(app)
    press(app, 'A')
    app.handle(('char', 'y'))                                         # sends, draws nothing
    ((path, body),) = s.posts
    assert path == '/v1/approvals/%s/decide' % aid
    assert body['decision'] == 'approve' and body['action_hash'] == before['action_hash']
    assert body['expected_version'] == before['version'] and body['idempotency_key']
    # nothing is shown as decided before Core says so: the cached row is Core's
    # answer, untouched, and only marked for a re-read
    assert app.cache['/v1/approvals/' + aid]['data'] is before
    assert json.dumps(before, sort_keys=True) == as_read, 'no optimistic write'
    assert app.cache['/v1/approvals/' + aid]['stale'] and app.cache['/v1/attention']['stale']
    n = len(s.gets)
    app.frame()
    assert '/v1/attention' in s.gets[n:], 'the next frame reads again what the command changed'
    settled(deploy, mid, 'COMPLETED')
    app.invalidate(lambda p: True)                  # what the stream would have said
    assert 'Nothing waits on you.' in plain(app)


def test_T03_the_same_action_keeps_its_key_across_a_network_retry(deploy):
    mid = mission(deploy, 'Deploy again')
    settled(deploy, mid, 'APPROVAL_REQUIRED')
    app = app_on(deploy)
    sent, real = [], app.core.post

    def flaky(path, body):
        sent.append(body)
        if len(sent) == 1:
            raise C.CoreError(0, 'network')
        return real(path, body)
    app.core.post = flaky
    app.go({'view': 'attention'})
    row(app, lambda x: any(a['key'] == 'A' for a in x['acts']))
    press(app, 'A', 'y')
    assert 'could not be reached' in plain(app)
    press(app, 'A', 'y')
    assert sent[0]['idempotency_key'] == sent[1]['idempotency_key'], \
        'a retry after a network failure reuses the key'
    settled(deploy, mid, 'COMPLETED')


# ── T04 pause / resume and a stale version ───────────────────────────────────

def test_T04_pause_then_a_stale_version_is_refused_in_cores_words_and_read_again(slow):
    mid = mission(slow, 'Long work')
    settled(slow, mid, 'EXECUTING')
    app = app_on(slow)
    s = spy(app)
    app.open('mission', mid)
    assert '[P] Pause' in plain(app)
    press(app, 'P')
    assert s.posts[-1][0] == '/v1/missions/%s/pause' % mid
    settled(slow, mid, 'PAUSED')
    assert 'Paused' in plain(app) and '[R] Resume' in plain(app)
    # someone else resumes it; this screen still holds the older version
    r = slow.http('GET', '/v1/missions/' + mid).json()
    slow.http('POST', '/v1/missions/%s/resume' % mid, body={
        'expected_version': r['version'], 'idempotency_key': 'other-client'})
    press(app, 'R')
    shown = plain(app)
    assert 'This changed since you opened it' in shown or 'Not possible from' in shown
    assert app.cache['/v1/missions/' + mid]['gen'] == app.conn['gen']
    assert state(slow, mid) != 'PAUSED'


def test_T04_a_command_the_state_has_no_trigger_for_is_not_offered(core):
    mid = mission(core, 'Done already')
    settled(core, mid, 'COMPLETED')
    app = app_on(core)
    app.open('mission', mid)
    shown = plain(app)
    assert '[P] Pause' not in shown and '[R] Resume' not in shown and '[S] Stop' not in shown


# ── T05 why, without reasoning ───────────────────────────────────────────────

def test_T05_why_and_the_route_decision_show_cores_record_and_no_reasoning(core):
    mid = mission(core, 'Why is it')
    settled(core, mid, 'COMPLETED')
    app = app_on(core)
    app.open('mission', mid, 'why')
    shown = plain(app)
    assert 'Why it is in this state' in shown and 'Completed:' in shown
    assert 'Harness fake' in shown and 'Model' in shown and 'Account' in shown
    route = row(app, lambda x: x['target'] and x['target'][1] == 'route_decision')
    app.follow(route['target'])
    shown = plain(app)
    assert 'Candidates' in shown and 'Result' in shown and 'Fell back from' in shown
    for word in ('reasoning', 'thinking', 'chain of thought'):
        assert word not in shown.lower()


def test_T05_candidates_are_shown_in_the_order_core_recorded_them():
    doc = SC.Doc(_StubApp({}), 100)
    d = {'harness_id': 'fake', 'model': None, 'account_id': None, 'result': 'selected',
         'explanation': 'x', 'candidates': [{'resource': 'zeta', 'reason': 'kept'},
                                            {'resource': 'alpha', 'reason': 'no quota'},
                                            {'resource': 'mid', 'reason': 'policy'}]}
    SC.route_detail(doc.app, doc, d)
    text = '\n'.join(render.strip_ansi(x['text']) for x in doc.lines)
    assert text.index('"zeta"') < text.index('"alpha"') < text.index('"mid"')


# ── T06 the output tail ──────────────────────────────────────────────────────

def test_T06_the_output_tail_is_cores_redacted_text_with_every_control_sequence_removed(
        archeus_home):
    from archeus.core import engine, ports, runtime
    from archeus.harnesses.fake import FakeHarness
    from v1.judge.http import TempCore
    bad = ('\x1b]52;c;cHduZWQ=\x07\x1b]0;pwned\x07\x1b[2J\x1b[8mhidden\x1b[0m'
           ' key sk-abcdefghijklmnop ‮evil')
    tc = TempCore(archeus_home, ports=runtime.Ports(
        brain=ports.FixedPlanBrain(engine.SKELETON_PLAN), executors=[FakeHarness()],
        scenarios={'work': [{'emit': {'type': 'text', 'text': bad}},
                            {'emit': {'type': 'result', 'summary': 'done'}}]})).start()
    try:
        mid = mission(tc, 'Say something')
        settled(tc, mid, 'COMPLETED')
        app = app_on(tc)
        app.open('mission', mid, 'now')
        ex = row(app, lambda x: x['target'] and x['target'][1] == 'execution')
        app.follow(ex['target'])
        frame = app.frame()
    finally:
        tc.stop(kill=True)
    joined = '\n'.join(frame)
    assert 'hidden' in joined, 'the text is shown, inert'
    assert 'sk-abcdefghijklmnop' not in joined, 'Core redacts; the TUI never reads the raw file'
    assert not SGR.sub('', joined).count('\x1b') and '\x07' not in joined
    assert '‮' not in joined


# ── T08 no Core ──────────────────────────────────────────────────────────────

def test_T08_with_no_core_the_tui_says_so_starts_nothing_and_fails(archeus_home, capsys):
    assert A.main(['--once']) == 1
    out = capsys.readouterr().out
    assert 'not running' in out and 'archeus core' in out
    assert C.Core.local() == (None, 'not_running')


# ── T09 monochrome and ASCII ─────────────────────────────────────────────────

class _Tty:
    encoding = 'utf-8'

    def isatty(self):
        return True


@pytest.mark.parametrize('env,vt,tty', [({'NO_COLOR': ''}, True, True),
                                        ({'NO_COLOR': '1'}, True, True),
                                        ({'TERM': 'dumb'}, True, True),
                                        ({}, False, True), ({}, True, False)])
def test_T09_monochrome_whenever_colour_cannot_be_trusted(env, vt, tty):
    stream = _Tty() if tty else type('P', (), {'encoding': 'utf-8', 'isatty': lambda s: False})()
    assert Style.detect(env, stream, vt).colour is False


def test_T09_colour_on_a_capable_terminal_and_ascii_when_the_encoding_needs_it():
    assert Style.detect({}, _Tty(), True).colour is True
    ascii_stream = type('A', (), {'encoding': 'ascii', 'isatty': lambda s: True})()
    assert Style.detect({}, ascii_stream, True).ascii is True
    assert Style.detect({'ARCHEUS_TUI_ASCII': '1'}, _Tty(), True).ascii is True
    assert Style.detect({'ARCHEUS_TUI_THEME': 'light'}, _Tty(), True).theme == 'light'


def test_T09_every_state_reads_without_colour_and_without_unicode(core):
    for mid_title in ('Mono one', 'Mono two'):
        settled(core, mission(core, mid_title), 'COMPLETED')
    for style in (Style(False, 'dark', False), Style(False, 'dark', True)):
        app = app_on(core, style=style)
        for d in DESTINATIONS:
            app.go({'view': d['id']})
            frame = app.frame()
            assert not any('\x1b' in x for x in frame)
            if style.ascii:
                assert all(ord(c) < 128 for x in frame for c in x), d['id']
        app.go({'view': 'work'})
        assert 'Done' in plain(app)                            # the label, not only a glyph
        app.frame()
        assert any(x['target'] for x in app._doc.lines)
        assert '› ' in plain(app) or '> ' in plain(app)       # focus is a marker


# ── T10 widths and resize ────────────────────────────────────────────────────

@pytest.mark.parametrize('width', [60, 80, 120, 200])
def test_T10_no_line_is_wider_than_the_terminal_at_any_width(core, width):
    mid = mission(core, '修复 the flaky date test with a very long title that goes on ' * 3)
    settled(core, mid, 'COMPLETED')
    app = app_on(core, size=(width, 30))
    routes = [{'view': d['id']} for d in DESTINATIONS] + [
        {'view': 'object', 'kind': 'mission', 'id': mid, 'tab': t}
        for t in INSPECTOR_TABS['mission']]
    for r in routes:
        app.go(r)
        frame = app.frame()
        assert len(frame) <= 30
        for x in frame:
            assert render.disp_width(x) == width, (r, x)
    app.go({'view': 'work'})
    assert 'Done' in plain(app)


def test_T10_a_resize_redraws_at_the_new_width(core):
    size = [100, 30]
    app = A.App(C.Core(core.port, core.token), Style(), size=lambda: tuple(size), stream=False)
    app.signal('stream_open')
    assert all(render.disp_width(x) == 100 for x in app.frame())
    size[0] = 70
    assert all(render.disp_width(x) == 70 for x in app.frame())


# ── T11 the command line ─────────────────────────────────────────────────────

def test_T11_the_command_line_goes_to_a_mission_or_tells_archeus_unparsed(core):
    mid = mission(core, 'Find me by title')
    settled(core, mid, 'COMPLETED')
    app = app_on(core)
    s = spy(app)
    app.go({'view': 'work'})
    app.frame()
    press(app, ':', *'find me', 'enter')
    assert app.route == {'view': 'object', 'kind': 'mission', 'id': mid, 'tab': None}
    press(app, ':', *'approve everything now')
    assert [h[1][0] for h in app.mode['hits']] == ['tell'], app.mode['hits']
    app.handle(('enter',))
    ((path, body),) = s.posts
    assert path == '/v1/conversations/primary/messages'
    assert body['text'] == 'approve everything now'           # no verb is parsed here


# ── T12 the automation's causal chain ────────────────────────────────────────

def test_T12_an_automation_run_is_shown_as_its_causal_chain(core):
    trigger = {'type': 'mission.created', 'where': {'title': 'seed'}}
    template = {'title': 'follow up {subject.id}', 'objective': 'look at {event.type}'}
    r = core.http('POST', '/v1/automations', body={'name': 'rule', 'trigger': trigger,
                                                   'template': template,
                                                   'idempotency_key': 'a1'})
    assert r.status == 200, r.body
    aid = r.json()['id']
    a = core.http('GET', '/v1/automations/' + aid).json()
    core.http('POST', '/v1/automations/%s/state' % aid, body={
        'action': 'enable', 'expected_version': a['version'], 'idempotency_key': 'a2'})
    mission(core, 'seed')
    deadline = time.monotonic() + 30
    while not core.http('GET', '/v1/automations/' + aid).json().get('runs'):
        assert time.monotonic() < deadline
        time.sleep(0.1)
    app = app_on(core)
    app.go({'view': 'control', 'section': 'automations'})
    run_row = row(app, lambda x: x['target'] and x['target'][1] == 'automation_run')
    app.follow(run_row['target'])
    shown = plain(app)
    order = [shown.index(t) for t in ('Triggering event', 'The run', 'What it caused')]
    assert order == sorted(order)
    assert 'mission.created' in shown and 'earlier event(s)' in shown


# ── T13 session hand-off ─────────────────────────────────────────────────────

def test_T13_a_hand_off_asks_for_the_harness_and_keeps_every_field_separate(core):
    mid = mission(core, 'Hand me off')
    settled(core, mid, 'COMPLETED')
    sid = core.http('GET', '/v1/sessions').json()['sessions'][0]['id']
    app = app_on(core)
    s = spy(app)
    app.open('session', sid)
    press(app, 'H')
    assert app.mode['kind'] == 'prompt' and 'Target harness (required)' in plain(app)
    press(app, 'enter')
    assert 'required' in plain(app) and not s.posts          # nothing sent without it
    press(app, *'fake', 'enter', 'enter', *'fake-model', 'enter', 'enter')
    ((path, body),) = s.posts
    assert path == '/v1/sessions/%s/handoff' % sid
    assert (body['harness_id'], body['account_id'], body['model']) == ('fake', None,
                                                                       'fake-model')
    app.open('session', sid, 'lineage')
    assert 'harness' in plain(app)


# ── T14 an observe-only client ───────────────────────────────────────────────

def _observe_token(tc):
    url = tc.core.launch_url(['observe'])
    code = parse_qs(urlparse(url).fragment)['launch'][0]
    r = request(tc.base_url, 'POST', '/v1/devices/launch/redeem',
                body={'code': code, 'platform': 'desktop'})
    assert r.status == 200, r.body
    return r.json()['token']


def test_T14_an_observe_only_client_is_shown_cores_scope_reason_and_sends_nothing(core):
    token = _observe_token(core)
    app = app_on(core, token=token)
    s = spy(app)
    app.go({'view': 'now'})
    shown = plain(app)
    assert '[M] Message' in shown                             # offered, not hidden
    press(app, 'M')
    assert 'does not hold the “control” scope' in plain(app)
    assert app.mode is None and not s.posts


# ── T15 a thousand missions ──────────────────────────────────────────────────

class _StubCore:
    def __init__(self, data):
        self.data, self.gets = data, []

    def get(self, path):
        self.gets.append(path)
        if path in self.data:
            return self.data[path], 1
        raise C.CoreError(404, 'not_found')

    def post(self, path, body):
        raise AssertionError('no command in this test')


class _StubApp(A.App):
    def __init__(self, data):
        super().__init__(_StubCore(data), Style(), size=lambda: (120, 40), stream=False)
        self.signal('stream_open')


def _missions(n):
    states = ('EXECUTING', 'COMPLETED', 'PAUSED', 'BLOCKED', 'APPROVAL_REQUIRED', 'FAILED')
    return [{'id': 'msn_%05d' % i, 'title': 'mission %d' % i, 'state': states[i % 6],
             'updated_at': '2026-09-29T12:%02d:00Z' % (i % 60), 'version': 1}
            for i in range(n)]


def test_T15_a_thousand_missions_render_in_budget_with_one_read_per_list():
    data = {'/v1/missions': {'missions': _missions(1000)}, '/v1/attention': {'items': [],
                                                                             'count': 0},
            '/v1/ideas': {'ideas': []},
            '/v1/sync': {'client': {'scopes': ['observe', 'control', 'approve', 'admin']}}}
    app = _StubApp(data)
    app.go({'view': 'work'})
    t0 = time.monotonic()
    app.frame()
    assert time.monotonic() - t0 < 2.0
    for _ in range(5):
        app.frame()
    assert app.core.gets.count('/v1/missions') == 1
    rows = [x for x in app._doc.lines if x['target']]
    per_group = {}
    for x in rows:
        per_group.setdefault(SC.group_of({'id': x['target'][2], 'state': next(
            m['state'] for m in data['/v1/missions']['missions'] if m['id'] == x['target'][2])},
            set()), []).append(x)
    assert all(len(v) <= SC.PAGE for v in per_group.values())
    assert any('more not shown' in x['text'] for x in app._doc.lines)


def test_T15_a_frame_invalidates_by_identity_and_an_unknown_kind_nothing():
    data = {'/v1/missions': {'missions': _missions(3)}, '/v1/attention': {'items': [],
                                                                          'count': 0},
            '/v1/ideas': {'ideas': []}, '/v1/sync': {'client': {'scopes': []}}}
    app = _StubApp(data)
    app.go({'view': 'work'})
    app.frame()
    app.dirty = False
    shown = json.dumps(app.cache['/v1/missions']['data'], sort_keys=True)
    app.q.put(('frame', {'event': 'x', 'data': {'subject': {'kind': 'unknown_kind', 'id': 'u'}}}))
    app.pump()
    assert not any(e['stale'] for e in app.cache.values())
    app.q.put(('frame', {'event': 'approval.state_changed',
                         'data': {'subject': {'kind': 'approval', 'id': 'apr_1'},
                                  'state': 'APPROVED'}}))
    app.pump()
    assert app.cache['/v1/attention']['stale'] and app.cache['/v1/missions']['stale']
    assert json.dumps(app.cache['/v1/missions']['data'], sort_keys=True) == shown, \
        'a frame never writes what is shown; only a re-read does'


def test_relations_say_the_tier_and_the_field_in_words():
    """Monochrome cannot carry a line style: EXTRACTED / INFERRED / AMBIGUOUS
    are words on the row, with the field the edge was read from."""
    k = {'id': 'kn_1', 'title': 'k', 'text': 't', 'state': 'CONFIRMED', 'type': 'FACT',
         'version': 1, 'chain': [], 'superseded_by_id': 'kn_2',
         'relations': [{'src_kind': 'knowledge_item', 'src_id': 'kn_1', 'rel': 'applies_to',
                        'dst_kind': 'project', 'dst_id': 'prj_1', 'confidence_tier': 'INFERRED',
                        'valid_until': '2026-01-01T00:00:00Z'},
                       {'src_kind': 'knowledge_item', 'src_id': 'kn_1', 'rel': 'mentions',
                        'dst_kind': 'repository', 'dst_id': 'rep_1',
                        'confidence_tier': 'AMBIGUOUS'}]}
    app = _StubApp({'/v1/knowledge/kn_1': k, '/v1/attention': {'items': [], 'count': 0},
                    '/v1/sync': {'client': {'scopes': []}}})
    app.open('knowledge_item', 'kn_1', 'relations')
    shown = plain(app)
    assert 'inferred' in shown and 'ambiguous' in shown
    assert 'no longer current' in shown and 'from relations.applies_to' in shown

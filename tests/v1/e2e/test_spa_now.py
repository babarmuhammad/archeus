"""P19.5 R8 in a real browser against a real Core: Now as the operational
surface (ADR-0027 §4-5, rulebook §6 O-4-O-6, §7.2, §9, §19, §22).

The state sentence is two counts in words, equal to Core's own reads, and never
a greeting. Now holds at most seven blocks, in ADR-0027 §4's order. Upcoming
lists the missions Core holds approved or planning; Recent decisions lists the
decided approvals, the route decisions that fell back and the confirmed
DECISION knowledge, newest first, each row naming and linking its object; the
automation line counts the enabled automations. The live map is the graph's own
renderer over the read around each active mission, holding exactly the active
missions and the attempts `/v1/status` lists as live — from 1000 px up, never
on a phone — parked when nothing moves, and every node opens the full graph.
Mutation-verified by tools/mutate_p19_5.py (N181 onward). Check floors keep a
test that silently checks nothing from passing."""

import itertools
import json
import os
import threading

import pytest

from archeus.core import engine, ports, runtime
from archeus.core.application import knowledge
from archeus.core.domain import ids
from v1.judge.http import TempCore

from .conftest import wait
from .motion import advance, canvas_ink, freeze, frames, hear, settle
from .test_spa_copy import DEPLOY
from .test_spa_halo import _running
from .test_spa_marker import FENCE, _frame
from .test_spa_p16 import APP, AXE, Checks, _go, _mission, _open, _settled
from .test_spa_p18 import slow  # noqa: F401 (a fixture)

with open(os.path.join(APP, 'tokens', 'presentation.json'), encoding='utf-8') as _f:
    CLASS = json.load(_f)['machines']['mission']     # a mission state's presentation class
BLOCKS = ['Needs you', 'Happening now', 'Since you last looked', 'Upcoming', 'Recent decisions', 'Live map',
          'Conversation']                               # ADR-0027 §4's order (rulebook §7.2: map over conversation)
SHOWN = 5                                               # recent decisions on Now (state/now.ts DECISIONS_SHOWN)

#: Now's blocks, in reading order, by their heading
_BLOCKS = """() => [...document.querySelectorAll('.now-main > section, .now-side > section')].map(s =>
  (s.querySelector(':scope > header h2, :scope > h2').firstChild.textContent || '').trim())"""


@pytest.fixture
def held(archeus_home):
    """A Core whose brain answers only when the test lets it: until then the
    mission is planning; its plan deploys, so it then asks for approval (P9)."""
    gate = threading.Event()

    class Held(ports.FixedPlanBrain):
        def call(self, schema, prompt, *, context=None):
            gate.wait(60)
            return super().call(schema, prompt, context=context)

    tc = TempCore(archeus_home, ports=runtime.Ports(brain=Held(DEPLOY))).start()
    tc.gate = gate
    yield tc
    gate.set()
    tc.stop()


_KEYS = itertools.count()


def _post(tc, path, body):
    r = tc.http('POST', path, body=dict(body, idempotency_key='now-%d' % next(_KEYS)))
    assert r.status == 200, (path, r.body)
    return r.json()


def _get(tc, path):
    return tc.http('GET', path).json()


def _sentence(tc):
    """The state sentence from Core's own reads: the unsettled missions and the attention count."""
    a = sum(m['state'] not in engine.SETTLED for m in _get(tc, '/v1/missions')['missions'])
    n = _get(tc, '/v1/attention')['count']
    doing = 'Archeus is working on %d %s.' % (a, 'mission' if a == 1 else 'missions') if a else 'Archeus is idle.'
    return '%s %s' % (doing, '%d %s you.' % (n, 'needs' if n == 1 else 'need') if n else 'Nothing needs you.')


def _said(page):
    return page.locator('[data-state-sentence]').inner_text().strip()


def _upcoming(tc):
    return [m['id'] for m in _get(tc, '/v1/missions')['missions'] if CLASS[m['state']] in ('approved', 'planning')]


def _rows(page, which):
    return page.evaluate("w => [...document.querySelectorAll('[data-now=\"' + w + '\"] > li')]"
                         ".map(li => li.dataset.mission ? 'mission:' + li.dataset.mission : li.dataset.ref)", which)


def _decisions(tc):
    out = [(a['decided_at'], 'approval:' + a['id']) for a in _get(tc, '/v1/approvals')['approvals']
           if a.get('decided_at') and a.get('decision')]
    out += [(r['created_at'], 'route_decision:' + r['id']) for r in _get(tc, '/v1/route-decisions')['route_decisions']
            if r.get('result') == 'fallback']
    out += [(k['updated_at'], 'knowledge_item:' + k['id']) for k in _get(tc, '/v1/knowledge?type=DECISION')['knowledge']
            if k['state'] == 'CONFIRMED']
    return [k for _at, k in sorted(out, reverse=True)[:SHOWN]]


def _decision(tx, *, actor, title):
    """A DECISION as a knowledge pass records one (knowledge.new_item): its only
    writer is that pass, which this Core has no model for."""
    return {'id': knowledge.new_item(tx, actor=actor, workspace_id=ids.GLOBAL_WORKSPACE, type='DECISION',
                                     title=title, origin='inferred', source_kind='brain').id}


def _in_order(got):
    if not all(any(g.startswith(b) for b in BLOCKS) for g in got):
        return False
    return [b for b in BLOCKS if any(g.startswith(b) for g in got)] == [b for g in got for b in BLOCKS if g.startswith(b)]


def test_the_sentence_upcoming_decisions_and_the_automation_line(browser, held, archeus_home):
    tc = held
    check = Checks()
    context, page, errors = _open(browser, tc, bypass_csp=True)
    wait(page, lambda: _said(page) == _sentence(tc), what='the sentence equals Core\'s counts (idle)')
    check(_said(page) == 'Archeus is idle. Nothing needs you.', 'idle: %r' % _said(page))
    check(page.locator('.presence').count() == 0 and 'Archeus ·' not in page.inner_text('.now'), 'the presence line is gone')
    check(page.evaluate("() => getComputedStyle(document.querySelector('[data-state-sentence]')).fontSize")
          == page.evaluate("() => { const e = document.createElement('p'); e.style.font = 'var(--type-display)';"
                           " document.body.append(e); const s = getComputedStyle(e).fontSize; e.remove(); return s; }"),
          'the sentence is in the display role')
    check(page.locator('[data-automation-line]').count() == 0, 'no automation watches: no line')
    check(page.locator('[data-now="upcoming"], [data-now="decisions"]').count() == 0, 'nothing upcoming or decided: no block')

    # an enabled automation watches; a draft does not
    watcher = _post(tc, '/v1/automations', {
        'name': 'Watcher', 'trigger': {'kind': 'event', 'type': 'mission.state_changed', 'where': {'to': 'CANCELLED'}},
        'template': {'title': 'Follow up', 'objective': 'Look again'}})['id']
    _post(tc, '/v1/automations', {'name': 'Draft', 'trigger': {'kind': 'event', 'type': 'mission.state_changed',
                                                                'where': {'to': 'CANCELLED'}},
                                  'template': {'title': 'Never', 'objective': 'Never'}})
    _post(tc, '/v1/automations/%s/state' % watcher, {'action': 'enable'})
    enabled = sum(a['state'] == 'ENABLED' for a in _get(tc, '/v1/automations')['automations'])
    line = page.locator('[data-automation-line] a')
    wait(page, lambda: line.count() == 1, what='the automation line')
    check(enabled == 1 and line.inner_text().strip() == '1 automation watching', 'the line counts the enabled one: %r' % line.inner_text())
    check(line.get_attribute('href') == '#/control/automations', 'the line links to the automations')

    # planning: the mission is upcoming, and Archeus is working on it
    acc = _post(tc, '/v1/accounts', {'harness_id': 'fake', 'label': 'Laptop', 'auth_kind': 'api_key'})['id']
    _post(tc, '/v1/resource-policies/%s' % acc, {'fallback': 'allow'})  # a fallback the user allowed (AP-1)
    mid = _mission(tc, 'Deploy the docs')
    _settled(tc, mid, 'REASONING')
    wait(page, lambda: _rows(page, 'upcoming') == ['mission:' + m for m in _upcoming(tc)], what='upcoming equals Core\'s planning missions')
    check(_rows(page, 'upcoming') == ['mission:' + mid], 'the planning mission is upcoming')
    check(page.locator('[data-now="upcoming"] li[data-mission="%s"] .state' % mid).get_attribute('data-cls') == 'planning',
          'it says Planning')
    wait(page, lambda: _said(page) == _sentence(tc), what='the sentence follows (planning)')
    check(_said(page) == 'Archeus is working on 1 mission. Nothing needs you.', 'working: %r' % _said(page))
    titles = page.evaluate(_BLOCKS)
    check(len(titles) <= 7 and _in_order(titles), 'at most seven blocks, in order: %s' % titles)
    check(titles.index('Upcoming') > titles.index('Happening now'), 'upcoming after what is happening')

    # it asks: needs you, nothing upcoming
    tc.gate.set()
    _settled(tc, mid, 'APPROVAL_REQUIRED')
    wait(page, lambda: _said(page) == _sentence(tc), what='the sentence follows (needs you)')
    check(_said(page) == 'Archeus is idle. 1 needs you.', 'needs you: %r' % _said(page))
    wait(page, lambda: page.locator('[data-now="upcoming"]').count() == 0, what='nothing upcoming once it asks')
    check(page.evaluate(_BLOCKS)[0] == 'Needs you', 'needs you comes first')

    # decided: the approval, the route that fell back, and the confirmed decision
    a = _get(tc, '/v1/approvals?mission=%s' % mid)['approvals'][0]
    _post(tc, '/v1/approvals/%s/decide' % a['id'], {'decision': 'approve', 'action_hash': a['action_hash']})
    _settled(tc, mid, 'COMPLETED')
    kept = tc.core.db.writer.execute(_decision, {'actor': tc.core.system, 'title': 'Deploys go out on Fridays'})['id']
    tc.core.db.writer.execute(_decision, {'actor': tc.core.system, 'title': 'Maybe deploy on Mondays'})  # a candidate
    _post(tc, '/v1/knowledge/%s/confirm' % kept, {})
    want = _decisions(tc)
    check(any(k.startswith('route_decision:') for k in want), 'Core recorded a fallback: %s' % want)
    wait(page, lambda: _rows(page, 'decisions') == want, what='recent decisions equal Core\'s records')
    check(_rows(page, 'decisions') == want and len(want) == 3, 'approval, fallback and the confirmed decision: %s' % want)
    rows = page.locator('[data-now="decisions"] > li')
    for i in range(rows.count()):
        r = rows.nth(i)
        kind, oid = r.get_attribute('data-ref').split(':', 1)
        check(r.locator('a').first.get_attribute('href') == '#/o/%s/%s' % (kind, oid), 'the row links its object: %s' % kind)
        check(r.get_attribute('data-thread') is not None, 'the row can carry the change rule: %s' % kind)
    text = rows.all_inner_texts()
    check(any('approved' in t and 'Deploy the docs' in t for t in text), 'the approval says approved, for its mission: %s' % text)
    check(any('fell back' in t for t in text), 'the route says it fell back: %s' % text)
    check(any('Deploys go out on Fridays' in t and 'decision' in t for t in text) and not any('Mondays' in t for t in text),
          'the confirmed decision, not the candidate: %s' % text)
    titles = page.evaluate(_BLOCKS)
    check(len(titles) <= 7 and _in_order(titles), 'still at most seven, in order: %s' % titles)

    # disabled, nothing watches
    _post(tc, '/v1/automations/%s/state' % watcher, {'action': 'disable'})
    wait(page, lambda: page.locator('[data-automation-line]').count() == 0, what='the line leaves with the last watcher')
    check(True, 'no line when nothing watches')
    if os.path.isfile(AXE):
        page.add_script_tag(path=AXE)
        bad = page.evaluate('async () => (await axe.run(".now", {resultTypes: ["violations"]})).violations'
                            '.filter(v => ["serious", "critical"].includes(v.impact)).map(v => v.id)')
        check(not bad, 'axe on Now: %s' % bad)
    check(not errors, errors)
    context.close()
    assert check.n >= 29, 'ran %d checks' % check.n


def _map_keys(page):
    return sorted(page.locator('.live-map [data-graph-mirror] li[data-key]').evaluate_all('els => els.map(e => e.dataset.key)'))


def _core_map(tc):
    active = [m['id'] for m in _get(tc, '/v1/missions')['missions'] if m['state'] not in engine.SETTLED]
    live = {x['id'] for x in _get(tc, '/v1/status')['live']}
    keys = ['mission:' + m for m in active]
    for m in active:
        keys += ['execution:' + n['id'] for n in _get(tc, '/v1/world/graph?focus=mission:%s&depth=1' % m)['nodes']
                 if n['kind'] == 'execution' and n['id'] in live]
    return sorted(set(keys))


def test_the_live_map_holds_live_work_only_and_opens_the_full_graph(browser, slow):  # noqa: F811
    tc = slow
    check = Checks()
    context, page, errors = _open(browser, tc)
    _go(page, '#/now')
    check(page.locator('.live-map').count() == 0, 'nothing active: no map')
    mid = _mission(tc, 'Map me')
    ex = _running(tc, mid)
    m = page.locator('.live-map .graph')
    m.wait_for(timeout=15000)
    wait(page, lambda: _map_keys(page) == _core_map(tc), what='the map equals Core\'s live work')
    check(_map_keys(page) == sorted(['mission:' + mid, 'execution:' + ex['id']]), 'the mission and its running attempt: %s' % _map_keys(page))
    check(int(m.get_attribute('data-graph-nodes')) <= 40, 'at most 40 nodes')
    check(int(m.get_attribute('data-graph-halos')) >= 1, 'the halo marks the live work')
    check(page.locator('.live-map .graph-bar').count() == 0, 'compact: no graph toolbar')
    check(page.locator('.live-map [data-graph-legend]').get_attribute('open') is None, 'the legend is there, closed')
    canvas = page.locator('.live-map canvas.graph-canvas')
    check(canvas.get_attribute('aria-label').startswith('Live work'), 'the map is named for what it holds')
    side = page.evaluate("() => [...document.querySelector('.now-side').children].map(c => c.querySelector('h2')?.textContent.trim())")
    check(side == ['Live map', 'Conversation'], 'the map stands over the conversation: %s' % side)
    check(canvas_ink(page, '.live-map canvas.graph-canvas') > 200, 'the map is drawn')

    # a second mission runs: the map frames the live work it holds now
    before = canvas.get_attribute('data-at')
    other = _mission(tc, 'Map me too')
    _running(tc, other)
    wait(page, lambda: _map_keys(page) == _core_map(tc) and len(_map_keys(page)) == 4, what='the second mission joins the map')
    wait(page, lambda: canvas.get_attribute('data-at') != before, what='the map frames what it holds now')
    box = canvas.bounding_box()
    x, y = (int(v) for v in canvas.get_attribute('data-at').split(','))
    check(0 <= x <= box['width'] and 0 <= y <= box['height'], 'the framed map keeps its nodes on the canvas: %s in %s' % ((x, y), box))
    freeze(page)
    settle(page)
    page.evaluate("() => document.getAnimations().forEach(a => a.finish())")
    f0 = frames(page)
    settle(page, 10_000)
    check(m.get_attribute('data-graph-loop') == 'parked' and frames(page) == f0, 'nothing moves: the map parks')
    # an execution frame re-reads the map's reads; the same live work draws nothing
    hear(page, _frame(ex['id'], FENCE))
    settle(page, 5000)
    check(frames(page) == f0, 'a re-read of the same live work drew %d frames' % (frames(page) - f0))

    # the width rule: from 1000 px, never on a phone (the media change reaches React in its own time)
    def sized(w, h, want):
        page.set_viewport_size({'width': w, 'height': h})
        drawn = lambda: page.locator('.live-map canvas.graph-canvas').count()  # noqa: E731
        wait(page, lambda: (advance(page, 100), drawn())[1] == want, what='%d px: %s' % (w, 'the map' if want else 'no map'))
        check(drawn() == want, '%d px: %s' % (w, 'the map' if want else 'no map'))
    sized(999, 800, 0)
    sized(1000, 800, 1)
    sized(390, 844, 0)
    check(page.evaluate('() => document.documentElement.scrollWidth - innerWidth') <= 0, 'nothing scrolls sideways')
    sized(1280, 720, 1)
    settle(page)

    # click-through: Enter on a node opens the full graph there
    canvas.wait_for()
    at = m.get_attribute('data-graph-at')
    canvas.focus()
    page.keyboard.press('Enter')
    wait(page, lambda: page.evaluate('location.hash').startswith('#/world/graph/'), what='the full graph opens')
    kind, oid = at.split(':', 1)
    check(page.evaluate('location.hash') == '#/world/graph/%s/%s' % (kind, oid), 'the full graph, focused there: %s' % page.evaluate('location.hash'))
    _go(page, '#/now')
    settle(page)

    # the attempt stops: it leaves the map, the mission stays while it is active
    r = tc.http('POST', '/v1/executions/%s/stop' % ex['id'], body={'idempotency_key': 'stop-%s' % ex['id']})
    assert r.status == 200, r.body
    wait(page, lambda: (settle(page, 200), 'execution:' + ex['id'] not in _map_keys(page))[1], what='a stopped attempt leaves the map')
    check(_map_keys(page) == _core_map(tc) or page.locator('.live-map').count() == 0, 'the map still equals Core\'s live work')
    check(not errors, errors)
    context.close()
    assert check.n >= 20, 'ran %d checks' % check.n


def test_the_map_under_reduced_motion_and_forced_colours(browser, slow):  # noqa: F811
    check = Checks()
    mid = _mission(slow, 'Map, plainly')
    _running(slow, mid)
    for ctx in ({'reduced_motion': 'reduce'}, {'forced_colors': 'active'}):
        context, page, errors = _open(browser, slow, **ctx)
        g = page.locator('.live-map .graph')
        g.wait_for(timeout=15000)
        wait(page, lambda g=g: int(g.get_attribute('data-graph-halos') or 0) >= 1, what='the halo (%s)' % ctx)
        wait(page, lambda p=page: canvas_ink(p, '.live-map canvas.graph-canvas') > 200, what='the map is drawn (%s)' % ctx)
        check(int(g.get_attribute('data-graph-halos')) >= 1, 'the halo stays: %s' % ctx)
        check(_said(page) == _sentence(slow), 'the sentence says it in words: %s' % ctx)
        check(not errors, errors)
        context.close()
    assert check.n >= 6

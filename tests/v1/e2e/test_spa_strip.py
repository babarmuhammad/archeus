"""P19.5 R7 in a real browser against a real Core: the mark, its orbit, the
favicon and the operations strip (ADR-0027 §1-3, rulebook §6 O-1, §8, §19,
§21 A-07, §42).

The mark is the credited glyph, once, in the header. Its orbit's node is
Archeus's presence — neutral, active while an attempt runs, attention while
something needs the user, hollow while this client is not connected — and the
favicon says the same, still. A batch of `execution.*` frames turns the node
once round the orbit (900 ms, at most once per 5 s, a CSS transform, no
animation frame), never again for an event already presented, never under
reduced motion. The strip is a navigation landmark on every page whose counts
equal Core's own reads and link to their lists, whose words are said in a
status region at most once per 30 s, and which holds the emergency stop
behind its confirmation and shows when it is engaged. Mutation-verified by
tools/mutate_p19_5.py (N154 onward). Check floors keep a test that silently
checks nothing from passing."""

import json
import math
import os
import re
from urllib.parse import unquote

import pytest

from .conftest import wait
from .motion import advance, freeze, frames, hear, running_animations, settle
from .test_spa_halo import _running
from .test_spa_marker import FENCE, _frame, _heard
from .test_spa_p16 import AXE, Checks, _go, _mission, _open, _settled, deploy  # noqa: F401 (a fixture)
from .test_spa_p18 import slow  # noqa: F401 (a fixture)

TURN_MS = 900       # the registry's presence-orbit max_ms (clients/app/tokens/motion.json)
EVERY_MS = 5000     # its min_interval_ms
SAYS_MS = 30_000    # the strip's words, at most once per 30 s (rulebook §19)
ACTIVE = {'INTENT', 'STARTING', 'RUNNING', 'HANDING_OFF'}   # presentation class `active`
DARK = json.load(open(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'clients', 'app', 'tokens',
                                   'tokens.json'), encoding='utf-8'))['themes']['dark']
#: what the favicon's node is in each presence: its fill, or hollow (the tile's fill, stroked)
NODE = {'idle': DARK['text'], 'active': DARK['state.active'], 'attention': DARK['state.attention'],
        'disconnected': 'hollow'}

#: the node's centre and box, and the orbit's centre, in CSS px
_NODE = """() => { const n = document.querySelector('.top .mark .mark-node').getBoundingClientRect();
  const e = document.querySelector('.top .mark ellipse').getBoundingClientRect();
  return {x: n.x + n.width / 2, y: n.y + n.height / 2, w: n.width, h: n.height,
          cx: e.x + e.width / 2, cy: e.y + e.height / 2}; }"""

#: hold every orbit animation at *ms* into its run (the compositor's clock is not the page's)
_HOLD = """ms => { const a = document.getAnimations().filter(a => a.animationName && a.animationName.startsWith('orbit-'));
  a.forEach(x => { x.pause(); x.currentTime = ms; }); return a.map(x => x.animationName).sort(); }"""

#: the turns that start, by the event each presents (the slow harness's own
#: frames turn the node too, until FENCE makes them history)
_TURNS = """() => { window.__turns = []; document.addEventListener('animationstart', e => {
  if (e.animationName === 'orbit-turn') window.__turns.push(+e.target.dataset.orbit); }); }"""


def _fenced(page):
    return [t for t in page.evaluate('window.__turns') if t >= FENCE]


def _strip(page):
    return page.get_by_role('navigation', name='Operations')


def _fact(page, key):
    a = page.locator('.strip a[data-strip="%s"]' % key)
    return a.inner_text().strip() if a.count() else None


def _presence(page):
    return page.locator('.top .mark').get_attribute('data-presence')


def _icon(page):
    """The favicon's presence as the image itself draws it: its node's fill."""
    href = page.evaluate("() => document.querySelector('link[rel=\"icon\"]').href")
    if not href.startswith('data:image/svg+xml,'):
        return None
    node = re.search(r'<circle [^>]*>', unquote(href)).group(0)
    if 'stroke=' in node:
        return 'disconnected' if 'fill="%s"' % DARK['bg'] in node else None
    fill = re.search(r'fill="([^"]+)"', node).group(1)
    return next((k for k, v in NODE.items() if v == fill), None)


def _core_facts(tc):
    live = tc.http('GET', '/v1/status').json()['live']
    running = len({x['mission_id'] for x in live if x['state'] in ACTIVE})
    needs = tc.http('GET', '/v1/attention').json()['count']
    clients = sum(d['presence']['state'] == 'connected' for d in tc.http('GET', '/v1/devices').json()['devices'])
    return running, needs, clients


def _agrees(page, tc):
    r, n, c = _core_facts(tc)
    want = ['%d running' % r, '%d %s you' % (n, 'needs' if n == 1 else 'need'),
            '%d %s' % (c, 'client' if c == 1 else 'clients')]
    return [_fact(page, k) for k in ('running', 'needs', 'clients')] == want


def test_the_mark_the_strip_and_the_favicon_follow_what_archeus_is_doing(browser, slow):  # noqa: F811
    check = Checks()
    context, page, errors = _open(browser, slow)
    strip = _strip(page)
    check(strip.count() == 1, 'the strip is one navigation landmark named Operations')
    wait(page, lambda: _fact(page, 'clients') is not None, what='the strip reads its counts')
    mark = page.locator('.top .brand .mark')
    box = mark.bounding_box()
    check(mark.count() == 1 and round(box['width']) == 20 and round(box['height']) == 20, 'the mark is 20 px: %s' % box)
    check(page.locator('.top .brand').inner_text().strip() == 'Archeus', 'the mark stands beside "Archeus"')
    check(mark.get_attribute('aria-hidden') == 'true', 'the glyph is decoration: the name and the strip carry it')
    # nowhere else: one mark on every destination, none in an empty state
    for h in ('#/now', '#/work', '#/world', '#/attention', '#/control/about', '#/control/devices'):
        _go(page, h)
        check(page.locator('svg.mark').count() == 1 and strip.count() == 1, '%s: one mark, one strip' % h)
    check(page.evaluate("() => getComputedStyle(document.querySelector('.top .mark')).color")
          == page.evaluate("() => getComputedStyle(document.querySelector('.top .brand')).color"),
          'the mark is drawn in currentColor')

    # idle: nothing runs, nothing needs you
    wait(page, lambda: _agrees(page, slow), what='the counts equal Core\'s reads (idle)')
    check(_fact(page, 'running') == '0 running' and _presence(page) == 'idle', 'idle: 0 running, a neutral node')
    check(_icon(page) == 'idle', 'the favicon shows idle: %s' % _icon(page))
    check(page.locator('[data-strip-said]').inner_text().strip() == '', 'the first reading is not said')
    hrefs = page.evaluate("() => [...document.querySelectorAll('.strip a[data-strip]')].map(a => [a.dataset.strip, a.getAttribute('href')])")
    check(hrefs == [['running', '#/now'], ['needs', '#/attention'], ['clients', '#/control/devices']],
          'every number links to its list: %s' % hrefs)
    page.locator('.strip a[data-strip="clients"]').click()
    page.get_by_role('heading', name='Clients').wait_for()
    check(True, 'the clients count opens Control → Clients')

    # working: an attempt runs
    mid = _mission(slow, 'Orbit')
    ex = _running(slow, mid)
    wait(page, lambda: _presence(page) == 'active', what='the node turns active while an attempt runs')
    wait(page, lambda: _agrees(page, slow), what='the counts equal Core\'s reads (running)')
    check(_fact(page, 'running') == '1 running', 'one mission running')
    check(_icon(page) == 'active', 'the favicon shows working')
    fill = page.evaluate("() => getComputedStyle(document.querySelector('.top .mark-node')).fill")
    active = page.evaluate("""() => { const h = getComputedStyle(document.documentElement).getPropertyValue('--state-active').trim().replace('#', '');
        return 'rgb(' + [0, 2, 4].map(i => parseInt(h.slice(i, i + 2), 16)).join(', ') + ')'; }""")
    check(fill == active, 'the node is state-active: %s vs %s' % (fill, active))

    # the turn: a batch of execution.* frames, once, a CSS transform, no frame
    _go(page, '#/now')
    freeze(page)
    settle(page)
    page.evaluate(_TURNS)
    page.evaluate("() => document.getAnimations().forEach(a => a.finish())")
    rest = page.evaluate(_NODE)
    f0 = frames(page)
    check(page.locator('.orbit-turn[data-orbit="%d"]' % FENCE).count() == 0, 'nothing turns before the event')
    hear(page, _frame(ex['id'], FENCE))
    wait(page, lambda: page.locator('.orbit-turn[data-orbit="%d"]' % FENCE).count() == 1, what='a batch turns the node')
    css = page.evaluate("() => ['.orbit-turn', '.orbit-counter'].map(s => { const c = getComputedStyle(document.querySelector('.top ' + s));"
                        " return [c.animationName, c.animationDuration, c.animationIterationCount, c.animationTimingFunction]; })")
    check(css == [['orbit-turn', '0.9s', '1', 'ease-in-out'], ['orbit-counter', '0.9s', '1', 'ease-in-out']],
          'one 900 ms ease-in-out turn and its counter-turn: %s' % css)
    check(page.evaluate(_HOLD, 0) == ['orbit-counter', 'orbit-turn'], 'both run, and only once each')
    at0 = page.evaluate(_NODE)
    check(math.hypot(at0['x'] - rest['x'], at0['y'] - rest['y']) < 0.5, 'the turn starts where the node rests')
    page.evaluate(_HOLD, TURN_MS / 2)
    mid_ = page.evaluate(_NODE)
    opp = (2 * rest['cx'] - rest['x'], 2 * rest['cy'] - rest['y'])
    check(math.hypot(mid_['x'] - opp[0], mid_['y'] - opp[1]) < 1.0,
          'half way, the node is across the orbit from where it rests: %s vs %s' % ((mid_['x'], mid_['y']), opp))
    page.evaluate(_HOLD, TURN_MS / 4)
    q = page.evaluate(_NODE)
    check(abs(q['w'] - q['h']) < 0.35 and abs(q['w'] - rest['w']) < 0.35, 'the node stays round on the way: %s' % q)
    page.evaluate("() => document.getAnimations().forEach(a => a.finish())")
    wait(page, lambda: not running_animations(page), timeout=5, what='the turn ends')
    end = page.evaluate(_NODE)
    check(math.hypot(end['x'] - rest['x'], end['y'] - rest['y']) < 0.5, 'it parks where it started')
    check(frames(page) == f0, 'a turn runs no animation frame')

    # at most one turn per 5 s
    advance(page, EVERY_MS // 5)
    _heard(page, _frame(ex['id'], FENCE + 1))
    settle(page)
    check(_fenced(page) == [FENCE] and page.locator('.orbit-turn[data-orbit="%d"]' % FENCE).count() == 1,
          'a second batch inside 5 s: no turn')
    advance(page, EVERY_MS)
    hear(page, _frame(ex['id'], FENCE + 2))
    wait(page, lambda: page.locator('.orbit-turn[data-orbit="%d"]' % (FENCE + 2)).count() == 1, what='after 5 s the next batch turns')
    wait(page, lambda: _fenced(page) == [FENCE, FENCE + 2], timeout=5, what='the second turn plays')
    page.evaluate("() => document.getAnimations().forEach(a => a.finish())")

    # nothing presented replays: the same event, an older one, a lost stream, a resync, a route
    advance(page, 3 * EVERY_MS)
    _heard(page, _frame(ex['id'], FENCE + 2))
    _heard(page, _frame(ex['id'], FENCE + 1))
    hear(page, {'event': 'stream-lost'})
    hear(page, {'event': 'stream-open'})
    settle(page, 5000)
    hear(page, {'event': 'resync'})
    settle(page, 5000)
    _go(page, '#/work')
    settle(page)
    check(_fenced(page) == [FENCE, FENCE + 2], 'a historical event, a resync or a route turned the node: %s' % _fenced(page))
    check(not running_animations(page) and frames(page) == f0, 'idle again: nothing runs')
    # an event of another kind turns nothing
    advance(page, 2 * EVERY_MS)
    _heard(page, {'id': FENCE + 20, 'event': 'mission.state_changed', 'data': {'subject': {'kind': 'mission', 'id': mid}}})
    settle(page)
    check(_fenced(page) == [FENCE, FENCE + 2], 'a mission frame turned the node')

    # disconnected: hollow, and the favicon says so
    hear(page, {'event': 'stream-lost'})
    wait(page, lambda: _presence(page) == 'disconnected', what='a lost stream leaves the node hollow')
    check(_icon(page) == 'disconnected', 'the favicon shows disconnected')
    hollow = page.evaluate("() => { const c = getComputedStyle(document.querySelector('.top .mark-node')); return [c.fill, c.stroke !== 'none']; }")
    surface = page.evaluate("() => getComputedStyle(document.querySelector('.top')).backgroundColor")
    check(hollow == [surface, True], 'the node is hollow: %s vs %s' % (hollow, surface))
    hear(page, {'event': 'stream-open'})
    wait(page, lambda: _presence(page) == 'active', what='back: the node is active again')

    # the strip's words: said when they change, at most once per 30 s
    said = page.locator('[data-strip-said]')
    check(said.get_attribute('role') == 'status' and said.inner_text().strip() == '1 running · 0 need you · 1 client',
          'the change to running was said: %r' % said.inner_text())
    other = _mission(slow, 'Orbit, second')
    _running(slow, other)
    settle(page)
    wait(page, lambda: _fact(page, 'running') == '2 running', what='a second mission runs')
    check(said.inner_text().strip() == ' · '.join([_fact(page, k) for k in ('running', 'needs', 'clients')]),
          'a change is said: %r' % said.inner_text())
    first = said.inner_text().strip()
    _stop(slow, other)
    wait(page, lambda: (settle(page, 200), _fact(page, 'running'))[1] == '1 running',
         what='an attempt that stops leaves /v1/status stale: the strip reads it again')
    check(said.inner_text().strip() == first, 'a second change inside 30 s waits')
    advance(page, SAYS_MS)
    check(said.inner_text().strip().startswith('1 running'), 'after 30 s the latest is said: %r' % said.inner_text())
    check(not errors, errors)
    context.close()
    assert check.n >= 38, 'ran %d checks' % check.n


def _stop(tc, mid):
    ex = _running(tc, mid)
    r = tc.http('POST', '/v1/executions/%s/stop' % ex['id'], body={'idempotency_key': 'stop-%s' % ex['id']})
    assert r.status == 200, r.body


def test_reduced_motion_turns_nothing_and_shows_the_colour(browser, slow):  # noqa: F811
    check = Checks()
    mid = _mission(slow, 'Orbit, reduced')
    ex = _running(slow, mid)
    context, page, errors = _open(browser, slow, reduced_motion='reduce')
    wait(page, lambda: _presence(page) == 'active', what='the colour still says working')
    freeze(page)
    settle(page)
    page.evaluate(_TURNS)
    f0 = frames(page)
    _heard(page, _frame(ex['id'], FENCE))
    settle(page)
    check(page.locator('.orbit-turn').count() == 0 and page.evaluate('window.__turns') == [], 'reduced motion: no turn')
    check(frames(page) == f0 and not running_animations(page), 'reduced motion: nothing runs')
    check(_fact(page, 'running') == '1 running', 'the strip says it in words')
    check(not errors, errors)
    context.close()
    assert check.n >= 4


def test_needs_you_the_emergency_stop_and_the_compact_strip(browser, deploy):  # noqa: F811
    check = Checks()
    mid = _mission(deploy, 'Needs you')
    _settled(deploy, mid, 'APPROVAL_REQUIRED')
    context, page, errors = _open(browser, deploy, bypass_csp=True)
    wait(page, lambda: _presence(page) == 'attention', what='something needs you: the attention colour')
    wait(page, lambda: _agrees(page, deploy), what='the counts equal Core\'s reads (needs you)')
    check(_fact(page, 'needs') == '1 needs you', 'one thing needs you')
    check(_icon(page) == 'attention', 'the favicon shows needs you')

    # the emergency stop: behind its confirmation, Cancel first
    stop = page.locator('.strip [data-strip="estop"] .action > button')
    check(stop.count() == 1 and stop.inner_text() == 'Emergency stop', 'the strip holds the emergency stop, by its one name')
    stop.click()
    dialog = page.locator('.strip dialog[open]')
    dialog.wait_for()
    check(page.evaluate('() => document.activeElement.textContent') == 'Cancel', 'the confirmation opens on Cancel')
    dialog.get_by_role('button', name='Cancel').click()
    check(deploy.http('GET', '/v1/health').json()['armed'] is True, 'Cancel sends nothing')
    stop.click()
    page.locator('.strip dialog[open]').get_by_role('button', name='Emergency stop').click()
    wait(page, lambda: deploy.http('GET', '/v1/health').json()['armed'] is False, what='the stop reaches Core')
    engaged = page.locator('.strip [data-strip="estop"] a', has_text='Emergency stop engaged')
    engaged.wait_for()
    check(engaged.get_attribute('href') == '#/control/about', 'the engaged state links to where it is re-armed')
    check(page.locator('.strip [data-strip="estop"] button').count() == 0, 'no second stop while engaged')
    if os.path.isfile(AXE):
        page.add_script_tag(path=AXE)
        bad = page.evaluate('async () => (await axe.run(".top", {resultTypes: ["violations"]})).violations'
                            '.filter(v => ["serious", "critical"].includes(v.impact)).map(v => v.id)')
        check(not bad, 'axe on the header: %s' % bad)
    r = deploy.http('POST', '/v1/rearm', body={'idempotency_key': 'rearm-r7'})
    assert r.status == 200, r.body
    stop.wait_for()
    check(True, 're-armed: the stop is offered again')

    # a phone: the compact strip is the mark and the counts
    page.set_viewport_size({'width': 390, 'height': 844})
    _go(page, '#/now')
    check(_strip(page).is_visible() and page.locator('.top .mark').is_visible(), 'the strip and the mark stay on a phone')
    check(all(page.locator('.strip a[data-strip="%s"]' % k).is_visible() for k in ('running', 'needs', 'clients')),
          'the counts stay')
    check(not page.locator('.strip [data-strip="estop"]').is_visible(), 'the stop stays in Control on a phone')
    check(page.evaluate('() => document.documentElement.scrollWidth - innerWidth') <= 0, 'nothing scrolls sideways')
    check(not errors, errors)
    context.close()
    assert check.n >= 14


def test_the_boot_screen_is_the_mark_and_connecting(browser, slow):  # noqa: F811
    context = browser.new_context()
    page = context.new_page()
    page.route('**/v1/**', lambda route: None)     # hold sign-in: the boot screen stays up
    page.goto(slow.core.launch_url())
    boot = page.locator('main.notice.boot')
    boot.wait_for()
    assert boot.locator('svg.mark').count() == 1
    assert boot.inner_text().strip() == 'Connecting to Archeus…'
    context.close()

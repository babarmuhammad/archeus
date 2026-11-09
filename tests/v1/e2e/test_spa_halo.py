"""P19.5 activity halo in a real browser against a real Core (ADR-0024 §5-6,
P18 A8 as amended): a running execution's node carries a static halo, read
from the canvas's framebuffer; it survives a lost stream, a resync with a
failed re-read and a remount without a frame of animation; reduced motion
keeps it; it clears once Core says the work stopped. The page clock is
frozen (motion.py), so frame counts are exact; the only real waits are on
Core's own state. A check floor keeps a suite that silently checks nothing
from passing."""

import math
import time

from archeus.core.domain import ids

from .conftest import wait
from .motion import advance, freeze, frames, hear, running_animations, settle
from .test_spa_p16 import Checks, _go, _mission, _open
from .test_spa_p18 import _find, _graph, slow  # noqa: F401 (a fixture)

R_EXECUTION = 7     # encoding.radiusOf('triangle')
HALO_INNER = 2      # render.HALO_RINGS[0]: the inner stroke, alpha .70

#: how many of 32 points on the focused node's inner halo radius are halo-blue
#: (-1: no canvas): a framebuffer read, not a screenshot (ADR-0029 §2)
_RING = """([r]) => {
  const c = document.querySelector('canvas.graph-canvas');
  if (!c) return -1;                       // the graph is not drawn at all
  const [x, y] = c.dataset.at.split(',').map(Number);
  const k = Number(c.dataset.zoom), dpr = c.width / c.clientWidth;
  const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data;
  let hits = 0;
  for (let i = 0; i < 32; i++) {
    const a = i * Math.PI / 16;
    let best = 0;
    for (const dr of [-1, -0.5, 0, 0.5, 1]) {
      const px = Math.round((x + Math.cos(a) * (r * k + dr)) * dpr), py = Math.round((y + Math.sin(a) * (r * k + dr)) * dpr);
      const o = (py * c.width + px) * 4;
      best = Math.max(best, d[o + 2] - d[o]);
    }
    if (best > 40) hits++;
  }
  return hits;
}"""


def _ring(page):
    return page.evaluate(_RING, [R_EXECUTION + HALO_INNER])


def _running(tc, mid):
    deadline = time.monotonic() + 30
    while True:
        ex = [x for x in tc.http('GET', '/v1/world/graph?focus=mission:' + mid).json()['nodes']
              if x['kind'] == 'execution' and x.get('state') == 'RUNNING']
        if ex:
            return ex[0]
        assert time.monotonic() < deadline, 'no running execution'
        time.sleep(0.1)


def _live_row(page, key):
    return page.locator('[data-graph-mirror] li[data-key="%s"]' % key).first


def _halo_view(page, mid, label, check, what):
    _go(page, '#/world/graph/mission/%s' % mid)
    g = _graph(page)
    settle(page)
    _find(page, label)
    settle(page)
    return g


def _still(page, check, what):
    before = frames(page)
    advance(page, 10_000)
    check(frames(page) == before, '%s: %d frames while the halo is up' % (what, frames(page) - before))
    check(all(math.isfinite(a['end']) for a in running_animations(page)), '%s: an unbounded animation' % what)


def test_the_halo_marks_live_work_until_core_says_it_stopped(browser, slow):  # noqa: F811
    check = Checks()
    mid = _mission(slow, 'Halo')
    ex = _running(slow, mid)
    key = 'execution:%s' % ex['id']
    context, page, errors = _open(browser, slow)
    freeze(page)
    g = _halo_view(page, mid, ex['label'], check, 'first read')
    check(g.get_attribute('data-graph-at') == key, 'the running execution is focused')
    halos = int(g.get_attribute('data-graph-halos'))
    check(halos >= 1, 'a live object carries a halo (%d)' % halos)
    lit = _ring(page)
    check(lit >= 24, 'the halo is on the canvas: %d/32 ring points' % lit)
    check('live work now' in _live_row(page, key).inner_text(), 'the mirror says it in words')
    check(_live_row(page, key).get_attribute('data-live') == '', 'the mirror row is marked live')
    _still(page, check, 'active')
    pulses = int(g.get_attribute('data-graph-pulses'))
    # a lost stream, then a resync whose re-read of the graph fails: the view
    # keeps the last read it holds, so the halo stays, and nothing replays
    hear(page, {'event': 'stream-lost'})
    settle(page)
    check(_ring(page) == lit and int(g.get_attribute('data-graph-halos')) == halos, 'the halo left with the stream')
    aborted = [0]

    def abort(route):
        aborted[0] += 1
        route.abort()
    page.route('**/v1/world/graph**', abort)
    hear(page, {'event': 'stream-open'})       # back from a drop: every read again
    settle(page, 5000)
    check(aborted[0] >= 1 and _ring(page) == lit, 'a failed re-read cleared the halo (%d)' % _ring(page))
    page.unroute('**/v1/world/graph**')
    hear(page, {'event': 'resync'})
    settle(page, 5000)
    check(_ring(page) == lit and int(g.get_attribute('data-graph-halos')) == halos, 'the resync changed the halo')
    check(int(g.get_attribute('data-graph-pulses')) == pulses, 'the reconnect replayed a pulse')
    _still(page, check, 'after the resync')
    # a remount through a route change: the same halo, no false activity, no loop
    _go(page, '#/now')
    settle(page)
    g = _halo_view(page, mid, ex['label'], check, 'remount')
    check(_ring(page) >= 24 and int(g.get_attribute('data-graph-halos')) == halos, 'the remount lost the halo')
    _still(page, check, 'after the remount')
    # reduced motion: the same semantic state, the same static halo
    rctx, rpage, rerrors = _open(browser, slow, reduced_motion='reduce')
    freeze(rpage)
    rg = _halo_view(rpage, mid, ex['label'], check, 'reduced')
    check(int(rg.get_attribute('data-graph-halos')) == halos and _ring(rpage) >= 24, 'reduced motion lost the halo')
    _still(rpage, check, 'reduced motion')
    check(not rerrors, rerrors)
    rctx.close()
    # Core stops the execution: once a read says so, the halo is gone
    r = slow.http('POST', '/v1/executions/%s/stop' % ex['id'], body={'idempotency_key': ids.new_ulid()})
    check(r.status == 200, r.body)
    deadline = time.monotonic() + 30
    while [x for x in slow.http('GET', '/v1/world/graph?focus=mission:' + mid).json()['nodes']
           if x['id'] == ex['id'] and x.get('state') == 'RUNNING']:
        assert time.monotonic() < deadline, 'Core never stopped the execution'
        time.sleep(0.1)

    def cleared():
        settle(page)
        return _live_row(page, key).get_attribute('data-live') is None
    wait(page, cleared, timeout=30, what='a read shows the execution stopped')
    check(_ring(page) <= 4, 'the halo outlived the work: %d/32 ring points' % _ring(page))
    check('live work now' not in _live_row(page, key).inner_text(), 'the mirror still says live')
    check(g.get_attribute('data-graph-at') == key, 'the stopped execution is still the one focused')
    # the only console errors allowed are the graph reads this test aborted
    check(not [e for e in errors if e != 'Failed to load resource: net::ERR_FAILED'], errors)
    check(errors.count('Failed to load resource: net::ERR_FAILED') <= aborted[0], errors)
    assert check.n >= 22
    context.close()

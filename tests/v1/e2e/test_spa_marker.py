"""P19.5 travelling marker in a real browser against a real Core (ADR-0024
§5-6, rulebook §21 A-04): an `execution.*` frame about a running execution
sends one marker from the execution to its task along Core's recorded edge,
read from the canvas's framebuffer at the start, the midpoint and the end, and
gone after 600 ms; the same event heard again — mid-travel, after it, across a
lost stream and a resync, after a remount — never replays; at most 8 travel at
once; reduced motion draws none and the mirror still says the relation is
live. The page clock is frozen (motion.py), so positions and frame counts are
exact. A check floor keeps a suite that silently checks nothing from passing."""

import math

from .conftest import wait
from .motion import advance, freeze, frames, hear, running_animations, settle
from .test_spa_halo import _running
from .test_spa_p16 import Checks, _go, _mission, _open
from .test_spa_p18 import _find, _graph, slow  # noqa: F401 (a fixture)

MARKER_MS = 600     # the registry's travelling-marker (clients/app/tokens/motion.json)
CAP = 8
FENCE = 10 ** 9     # newer than anything Core has sent: Core's own frames are history after it

#: thread-ink pixels on the canvas now that were not in the baseline: how many,
#: and their centroid in CSS px (a framebuffer read, not a screenshot)
_INK = """([base]) => {
  const c = document.querySelector('canvas.graph-canvas');
  const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data;
  if (base) { window.__markBase = d; return null; }
  const hex = getComputedStyle(c).getPropertyValue('--thread').trim().replace('#', '');
  const ink = [0, 2, 4].map(i => parseInt(hex.slice(i, i + 2), 16));
  const b = window.__markBase, dpr = c.width / c.clientWidth;
  const near = (a, o) => Math.abs(a[o] - ink[0]) + Math.abs(a[o+1] - ink[1]) + Math.abs(a[o+2] - ink[2]) < 90;
  let n = 0, sx = 0, sy = 0;
  for (let o = 0; o < d.length; o += 4) if (near(d, o) && !near(b, o)) {
    n++; sx += (o / 4) % c.width; sy += Math.floor(o / 4 / c.width);
  }
  return { n, x: n ? sx / n / dpr : 0, y: n ? sy / n / dpr : 0 };
}"""


#: deliver a frame and wait until the app has handled it: the app's channel
#: answers a `hello` posted after it (api/stream.ts), and a channel delivers in order
_HEARD = """f => new Promise(r => {
  const rx = new BroadcastChannel('archeus-events');
  rx.onmessage = e => { if (e.data.event === 'stream-open') { rx.close(); r(true); } };
  const tx = new BroadcastChannel('archeus-events');
  tx.postMessage(f); tx.postMessage({ event: 'hello' });
})"""


def _heard(page, frame):
    page.evaluate(_HEARD, frame)


def _at(page):
    return tuple(map(float, page.locator('canvas.graph-canvas').get_attribute('data-at').split(',')))


def _along(page, s, t):
    """Where the new thread ink is, as a fraction of the way from s to t, and
    how far off the line s-t it sits (CSS px); None when there is none."""
    ink = page.evaluate(_INK, [False])
    if not ink['n']:
        return None
    dx, dy = t[0] - s[0], t[1] - s[1]
    ln = math.hypot(dx, dy)
    ox, oy = ink['x'] - s[0], ink['y'] - s[1]
    return (ox * dx + oy * dy) / ln / ln, abs(ox * dy - oy * dx) / ln


def _frame(ex, seq):
    return {'id': seq, 'event': 'execution.progress', 'data': {'subject': {'kind': 'execution', 'id': ex}}}


def _task_edge(tc, mid, ex):
    g = tc.http('GET', '/v1/world/graph?focus=mission:' + mid).json()
    e = [e for e in g['edges'] if e['field'] == 'executions.task_id' and e['from']['id'] == ex][0]
    return e['id'], [n for n in g['nodes'] if n['id'] == e['to']['id']][0]


def test_the_marker_travels_once_from_the_execution_to_its_task(browser, slow):  # noqa: F811
    check = Checks()
    mid = _mission(slow, 'Marker')
    ex = _running(slow, mid)
    edge, task = _task_edge(slow, mid, ex['id'])
    context, page, errors = _open(browser, slow)
    _go(page, '#/world/graph/mission/%s' % mid)
    g = _graph(page)
    wait(page, lambda: int(g.get_attribute('data-graph-live') or 0) >= 1, what='a live edge')
    freeze(page)
    settle(page)
    markers = lambda: int(g.get_attribute('data-graph-markers'))  # noqa: E731
    drawn = lambda: int(page.locator('canvas.graph-canvas').get_attribute('data-markers'))  # noqa: E731
    # the fence: after it every frame Core sends is history, so nothing but this test moves
    n = markers()
    hear(page, _frame(ex['id'], FENCE))
    wait(page, lambda: markers() == n + 1, what='the positive control: a new event sends a marker')
    check(True, 'a new event sends a marker')
    advance(page, 2 * MARKER_MS)
    # the two ends on screen: the execution centred by search, then its task across the drawn edge
    _find(page, ex['label'])
    settle(page)
    s = _at(page)
    for _ in range(8):
        if g.get_attribute('data-graph-selected') == edge:
            break
        page.keyboard.press('ArrowDown')
    check(g.get_attribute('data-graph-selected') == edge, 'the execution\'s task edge is drawn and selectable')
    page.keyboard.press('ArrowRight')
    settle(page)
    t = _at(page)
    check(g.get_attribute('data-graph-at') == 'task:%s' % task['id'], 'crossed to the task')
    page.keyboard.press('ArrowLeft')
    page.keyboard.press('Escape')               # no selected edge drawn in thread ink under the marker
    settle(page)
    check(_at(page) == s, 'the camera did not move while finding the ends')
    check(math.hypot(t[0] - s[0], t[1] - s[1]) > 40, 'the edge is long enough to see travel: %s %s' % (s, t))
    page.evaluate(_INK, [True])
    check(_along(page, s, t) is None, 'no ink to begin with')

    # one marker: at the source, the midpoint, the target, then gone
    seq = FENCE + 10
    f0, n = frames(page), markers()
    hear(page, _frame(ex['id'], seq))
    wait(page, lambda: markers() == n + 1, what='the marker starts')
    # the first frame is drawn, but at progress 0 the marker lies over the execution's own
    # node, already ink-coloured in the baseline: how much of it shows as new depends on the
    # layout, so it may take a frame or two to clear the node (still under 0.1 of the edge)
    a, el = None, 0
    while a is None and el < 48:
        advance(page, 16)
        el += 16
        a = _along(page, s, t)
    check(a is not None and a[0] < 0.1 and a[1] < 6, 'the marker begins at the execution: %s' % (a,))
    advance(page, MARKER_MS // 2 - el)
    a = _along(page, s, t)
    check(a is not None and 0.35 < a[0] < 0.6 and a[1] < 6, 'the marker is half way along the edge: %s' % (a,))
    # the same event again mid-travel, and a stream lost and back (a resync): no restart
    _heard(page, _frame(ex['id'], seq))
    hear(page, {'event': 'stream-lost'})
    hear(page, {'event': 'stream-open'})
    _heard(page, _frame(ex['id'], seq))
    advance(page, MARKER_MS // 2 - 10)
    a = _along(page, s, t)
    check(a is not None and 0.85 < a[0] < 1.05 and a[1] < 6, 'the marker reaches the task, not restarted: %s' % (a,))
    check(markers() == n + 1, 'the event heard again sent a second marker')
    advance(page, 100)
    check(_along(page, s, t) is None, 'the marker outlived its 600 ms')
    ran = frames(page) - f0
    # (the resync's re-reads answer in real time: each may add one redraw frame)
    check(ran <= math.ceil(MARKER_MS / 16) + 6, '%d frames: the marker restarted or kept running' % ran)
    settle(page, 5000)                          # past the resync notice, every re-read drawn
    check(g.get_attribute('data-graph-loop') == 'parked', 'parked after the marker')
    for again in (seq, seq - 1):
        _heard(page, _frame(ex['id'], again))
        advance(page, 1000)
    check(markers() == n + 1, 'a historical event replayed after the reconnect')
    hear(page, _frame(ex['id'], seq + 1))
    wait(page, lambda: markers() == n + 2, what='a newer event sends one new marker')
    check(True, 'a newer event sends one new marker')
    advance(page, 1000)

    # the cap: nine batches 50 ms apart leave eight travelling, the oldest dropped
    seq += 10
    for i in range(CAP + 1):
        m = markers()
        hear(page, _frame(ex['id'], seq + i))
        wait(page, lambda m=m: markers() == m + 1, what='marker %d' % i)
        advance(page, 50)
    check(drawn() == CAP, '%d markers travelling at once' % drawn())
    advance(page, 1000)
    check(drawn() == 0 and _along(page, s, t) is None, 'markers outlived their 600 ms')
    for i in range(CAP + 1):                    # the dropped one included
        _heard(page, _frame(ex['id'], seq + i))
    advance(page, 100)
    check(drawn() == 0, 'a resent batch recreated a marker')

    # an unrelated event: a frame about the task, not the execution
    m = markers()
    _heard(page, {'id': seq + 100, 'event': 'task.progress', 'data': {'subject': {'kind': 'task', 'id': task['id']}}})
    advance(page, 100)
    check(markers() == m and _along(page, s, t) is None, 'an unrelated event sent a marker')

    # the text equivalent: the mirror says the execution's relation to its task is live
    row = page.locator('[data-graph-mirror] li[data-key="execution:%s"] li[data-live]' % ex['id'])
    check(row.count() == 1 and 'live now' in row.inner_text(), 'the mirror says the relation is live')

    # a remount through a route change: the same events never replay
    _go(page, '#/now')
    settle(page)
    _go(page, '#/world/graph/mission/%s' % mid)
    g = _graph(page)
    settle(page)
    _heard(page, _frame(ex['id'], seq + CAP))
    advance(page, 100)
    check(int(g.get_attribute('data-graph-markers')) == 0, 'the remount replayed a marker')
    hear(page, _frame(ex['id'], seq + 200))
    wait(page, lambda: int(g.get_attribute('data-graph-markers')) == 1, what='a new event after the remount')
    check(True, 'a new event after the remount sends one marker')
    advance(page, 1000)

    # idle again: not a frame, not an animation
    before = frames(page)
    advance(page, 10_000)
    check(frames(page) == before, '%d frames after the markers ended' % (frames(page) - before))
    check(all(math.isfinite(x['end']) for x in running_animations(page)), 'an unbounded animation')
    check(not errors, errors)
    assert check.n >= 25
    context.close()


def test_reduced_motion_draws_no_marker_and_says_it_in_words(browser, slow):  # noqa: F811
    check = Checks()
    mid = _mission(slow, 'Marker, reduced')
    ex = _running(slow, mid)
    context, page, errors = _open(browser, slow, reduced_motion='reduce')
    _go(page, '#/world/graph/mission/%s' % mid)
    g = _graph(page)
    wait(page, lambda: int(g.get_attribute('data-graph-live') or 0) >= 1, what='a live edge')
    freeze(page)
    settle(page)
    page.evaluate(_INK, [True])
    f0 = frames(page)
    _heard(page, _frame(ex['id'], FENCE))
    advance(page, MARKER_MS)
    check(int(g.get_attribute('data-graph-markers')) == 0, 'a marker under reduced motion')
    check(frames(page) == f0, '%d frames under reduced motion' % (frames(page) - f0))
    check(page.evaluate(_INK, [False])['n'] == 0, 'thread ink drawn under reduced motion')
    check(int(g.get_attribute('data-graph-live')) >= 1, 'the live edge is still drawn (2 px, static)')
    row = page.locator('[data-graph-mirror] li[data-key="execution:%s"] li[data-live]' % ex['id'])
    check(row.count() == 1 and 'live now' in row.inner_text(), 'the mirror says the relation is live')
    check(not errors, errors)
    assert check.n >= 6
    context.close()

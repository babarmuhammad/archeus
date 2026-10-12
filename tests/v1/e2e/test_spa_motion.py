"""P19.5 motion foundation in a real browser against a real Core (ADR-0024 §2,
§5; ADR-0029): idle Archeus runs zero animation frames and zero animations
on every destination and the graph, through rerenders, route changes and a
reconnect-and-resync; a historical event heard again never replays or
restarts its pulse. Time is the page's frozen clock (motion.py), never a
sleep, so a count is exact. A check floor keeps a suite that silently checks
nothing from passing."""

import math
import time

from .conftest import wait
from .motion import advance, canvas_ink, freeze, frames, hear, running_animations, settle
from .test_spa_p16 import Checks, _go, _mission, _open, _settled
from .test_spa_p18 import _graph, slow  # noqa: F401 (a fixture)

IDLE_MS = 10_000
PULSE_MS = 240      # the registry's execution-pulse (clients/app/tokens/motion.json)
MARKER_MS = 600     # and its travelling-marker
FRAME_MS = 16       # one fake-clock animation frame


def _still(page, check, what):
    """Nothing animates: over IDLE_MS of page time not one frame runs, and no
    Web Animation is running or unbounded."""
    before = frames(page)
    advance(page, IDLE_MS)
    check(frames(page) == before, '%s: %d frames while idle' % (what, frames(page) - before))
    anims = running_animations(page)
    check(all(a['end'] is not None and math.isfinite(a['end']) for a in anims),
          '%s: an unbounded animation %s' % (what, anims))
    wait(page, lambda: not running_animations(page), timeout=5, what='%s: animations end' % what)


def test_idle_archeus_runs_no_frame_and_no_animation(browser, core):
    """The idle invariant on every destination and the graph, then through a
    rerender, a route change and a reconnect-and-resync."""
    check = Checks()
    mid = _mission(core, 'Idle')
    _settled(core, mid, 'COMPLETED')
    context, page, errors = _open(browser, core)
    g = None
    freeze(page)
    for h in ('#/now', '#/work', '#/world', '#/attention', '#/control/autonomy',
              '#/world/graph/mission/%s' % mid):
        _go(page, h)
        settle(page)                            # what arriving at a page owes, drawn
        if 'graph' in h:
            g = _graph(page)
            settle(page)
            check(g.get_attribute('data-graph-loop') == 'parked', 'the graph parks')
            check(canvas_ink(page) > 200, 'the parked graph still shows the graph')
        _still(page, check, h)
    canvas = page.locator('canvas.graph-canvas')
    drawn = int(canvas.get_attribute('data-frames'))
    # a React rerender with nothing new to draw (the pin toolbar re-renders the view)
    page.dispatch_event('.graph', 'mousemove')
    settle(page)
    # a reconnect and resync, heard the way every tab hears the leader's stream
    hear(page, {'event': 'stream-lost'})
    settle(page)
    hear(page, {'event': 'stream-open'})       # back from a drop: a resync, every read again
    settle(page, 5000)                          # past the resync notice (4 s)
    hear(page, {'event': 'resync'})
    settle(page, 5000)
    check(int(canvas.get_attribute('data-frames')) - drawn <= 3,
          'a rerender or resync drew %d frames' % (int(canvas.get_attribute('data-frames')) - drawn))
    _still(page, check, 'after the resync')
    # a route change away and back remounts the view: it draws once, then nothing
    _go(page, '#/now')
    settle(page)
    _go(page, '#/world/graph/mission/%s' % mid)
    settle(page)
    _still(page, check, 'after the remount')
    check(g is not None and not errors, errors)
    assert check.n >= 20
    context.close()


def test_a_historical_event_heard_again_never_replays_or_restarts(browser, slow):  # noqa: F811
    """ADR-0024 §5: a re-sent event (a reconnect, a second tab) is not new. A
    positive control first proves the path pulses at all."""
    check = Checks()
    mid = _mission(slow, 'Still running')
    deadline = time.monotonic() + 30
    ex = None
    while not ex:
        ex = [x for x in slow.http('GET', '/v1/world/graph?focus=mission:' + mid).json()['nodes']
              if x['kind'] == 'execution' and x.get('state') == 'RUNNING']
        assert time.monotonic() < deadline, 'no running execution'
        time.sleep(0.1)
    context, page, errors = _open(browser, slow)
    _go(page, '#/world/graph/mission/%s' % mid)
    g = _graph(page)
    wait(page, lambda: int(g.get_attribute('data-graph-live') or 0) >= 1, what='a live edge')
    freeze(page)
    advance(page, 3000)                         # past any pulse Core's own frames started
    pulses = lambda: int(g.get_attribute('data-graph-pulses'))  # noqa: E731
    seq = 10 ** 9                               # newer than anything Core has sent
    frame = {'id': seq, 'event': 'execution.progress',
             'data': {'subject': {'kind': 'execution', 'id': ex[0]['id']}}}
    n, f0 = pulses(), frames(page)
    hear(page, frame)
    advance(page, 100)
    check(pulses() == n + 1, 'a new event pulses (the positive control)')
    hear(page, frame)                           # the same event again, mid-pulse
    advance(page, PULSE_MS - 100 + 2 * FRAME_MS)  # past its own end, before a restart's
    running = int(page.locator('canvas.graph-canvas').get_attribute('data-pulses'))
    check(running == 0, 'the pulse restarted instead of keeping its start (%d running)' % running)
    advance(page, 1000)
    ran = frames(page) - f0
    check(pulses() == n + 1, 'the event heard again pulsed again')
    # the same frame sends a travelling marker too (600 ms): the loop runs for it, then parks
    check(ran <= math.ceil(MARKER_MS / FRAME_MS) + 3, '%d frames for one pulse and one marker' % ran)
    check(g.get_attribute('data-graph-loop') == 'parked', 'parked after the pulse')
    advance(page, 3000)                         # past the 2 s rate limit: only novelty is left
    for again in (frame, dict(frame, id=seq - 1)):
        hear(page, again)
        advance(page, 1000)
    check(pulses() == n + 1, 'a historical event replayed after the rate window')
    hear(page, dict(frame, id=seq + 1))
    advance(page, 100)
    check(pulses() == n + 2, 'a genuinely new event after them pulses')
    # the reads the heard events started answer in real time, and one answering inside
    # the idle window draws a frame there: settled first, as every other idle check is
    settle(page)
    _still(page, check, 'after the pulses')
    check(not errors, errors)
    assert check.n >= 9
    context.close()

"""Deterministic motion probes for the real SPA (ADR-0024 §2, ADR-0029): a
frozen page clock, a count of every animation frame the page runs, the
running Web Animations, canvas ink and a stream frame injected the way a
second tab hears one. Every visual slice's browser gate uses these instead of
sleeping and hoping: time only moves when a test calls `advance`.

Playwright's clock replaces setTimeout, setInterval, requestAnimationFrame,
Date and performance.now in the page; `advance(page, ms)` runs everything due
in *ms* of page time, at once and in order. The frame counter wraps the fake
requestAnimationFrame, so it counts the callbacks the page actually ran."""

from .conftest import wait

_FLIGHT = {}  # page -> the reads it has in flight (the stream excluded)

_COUNT = """() => {
  if (window.__motion) return;
  const m = window.__motion = { frames: 0 };
  const raf = window.requestAnimationFrame.bind(window);
  window.requestAnimationFrame = (cb) => raf((t) => { m.frames++; cb(t); });
}"""


def freeze(page):
    """Stop the page's clock and start counting frames. Call once the page has
    loaded; from here on nothing time-driven runs unless `advance` is called."""
    page.clock.install()
    page.clock.pause_at(page.evaluate('Date.now()') + 1000)
    page.evaluate(_COUNT)
    flight = _FLIGHT.setdefault(page, set())

    def reads(r):
        return '/events/stream' not in r.url    # the stream stays open by design
    page.on('request', lambda r: flight.add(r) if reads(r) else None)
    page.on('requestfinished', lambda r: flight.discard(r))
    page.on('requestfailed', lambda r: flight.discard(r))


def advance(page, ms):
    page.clock.run_for(ms)


def settle(page, ms=1000, timeout=15):
    """Let what the page owes arrive: run *ms* of page time, wait for every
    read in flight to answer, and repeat until a round starts none. Reads are
    real network, so they answer in real time; this waits on the condition,
    not on a guess of how long it takes."""
    flight = _FLIGHT[page]
    for _ in range(10):
        advance(page, ms)
        if not flight:
            advance(page, ms)                   # a read that answered may batch one more
            if not flight:
                return
        wait(page, lambda: not flight, timeout=timeout, what='the reads in flight answer')
    raise AssertionError('the page never settled: it keeps starting reads')


def frames(page):
    """Animation-frame callbacks run since `freeze`."""
    return page.evaluate('window.__motion.frames')


#: every running Web Animation (CSS animations and transitions included), with
#: how long it lasts: an unbounded one has endTime Infinity
_ANIMS = """() => document.getAnimations().filter(a => a.playState === 'running').map(a => ({
  name: a.animationName || a.transitionProperty || a.id || a.constructor.name,
  end: a.effect ? a.effect.getComputedTiming().endTime : null,
  iterations: a.effect ? a.effect.getComputedTiming().iterations : null }))"""


def running_animations(page):
    return page.evaluate(_ANIMS)


def canvas_ink(page, selector='canvas.graph-canvas'):
    """Pixels differing from the canvas's first pixel: a framebuffer read, not
    a screenshot (ADR-0029 §2)."""
    return page.evaluate("""s => { const c = document.querySelector(s);
        const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data; let n = 0;
        for (let i = 0; i < d.length; i += 4) if (d[i] !== d[0] || d[i+1] !== d[1] || d[i+2] !== d[2]) n++;
        return n; }""", selector)


def hear(page, frame):
    """Deliver *frame* the way a tab that does not hold the stream hears the
    leader's (api/stream.ts: one BroadcastChannel per browser). The app cannot
    tell it from a frame Core sent, which is what lets a test re-send a
    historical event without touching Core."""
    page.evaluate("f => new BroadcastChannel('archeus-events').postMessage(f)", frame)

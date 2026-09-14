"""Measure the stage INSIDE the real Qt shell, which is the only place the
tearing bug exists.

Everything else that measures this scene — tools/smoke_gui.py,
tools/shot_gui.py, tools/inspect_cluster.py — drives headless Chromium with
`--use-angle=swiftshader`. That is the right call for behaviour (it is
deterministic and it runs in CI) and it is worthless for cost: a software
rasteriser has none of the properties the bug is about. notes/cluster-handoff.md
has carried "cost has not been measured on real hardware" as an open queue item
for exactly this long, because there was no way to.

It drives the window through `run_desktop(on_ready=...)` and Qt's own
`page().runJavaScript()`, NOT over CDP. Playwright cannot attach to
QtWebEngine — `connect_over_cdp` needs `Browser.setDownloadBehavior` and Qt
answers "Browser context management is not supported" — and reimplementing the
window here would be a hand-maintained copy of exactly the GPU and compositing
setup the measurement is about.

    py tools/probe_qt.py                       # the graph world, 6 seconds
    py tools/probe_qt.py --world cyber --seconds 10
    py tools/probe_qt.py --tier lite           # the ladder's next rung
    py tools/probe_qt.py --budget 1.5e6        # what a smaller cap would give

WHAT IT PRINTS AND WHY EACH ONE IS HERE

  renderer      The unmasked GL renderer string. READ THIS FIRST. If Qt has
                fallen back to SwiftShader or WARP the scene is being drawn on
                the CPU, no amount of triangle reduction is the fix, and every
                number below is measuring the wrong thing.
  buffer        The drawing buffer, in pixels. This is what STAGE_PIXEL_BUDGET
                caps, and on an uncapped build it is where the frame went.
  triangles     One whole frame off renderer.info with autoReset off. Six of
                the graph scene's meshes are transparent DoubleSide, which
                three draws in two passes, so this already counts them twice.
  p50/p95 ms    The interval between RENDERED frames, which is what a stalled
                buffer swap shows up in — timing the render() call measures
                command submission, and on a saturated GPU that is near zero.
                Compared against `asked`, the interval the fps cap requested. A
                distribution and not a mean, because tearing is a TAIL problem:
                a p50 inside budget with a p95 at three times it is exactly
                what a viewer reports as stutter while an average says fine.
  degraded      Rungs the ladder in STAGE._watch took while we watched.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

#: Wraps STAGE._tick so a sample is taken only on frames that were actually
#: DRAWN — the stage caps its own fps, so most ticks return early and counting
#: those would measure the rAF cadence rather than the scene.
SAMPLER = """
(() => {
  if (window.__probe) return 'already';
  window.__probe = {ms: [], last: 0, raf: [], rlast: 0};
  /* THE CONTROL, and without it this tool measures the wrong thing. A stage
     frame interval only means something next to the interval the PAGE can
     deliver at all: if rAF itself is running at 30fps then a 33ms stage frame
     is the machine's frame rate rather than the scene's cost, and no amount of
     cutting triangles moves it. This is a second rAF chain, which the app
     forbids and a probe needs — it is the baseline, so it must not go through
     MO. */
  (function tick(now) {
    if (window.__probe.rlast) window.__probe.raf.push(now - window.__probe.rlast);
    window.__probe.rlast = now;
    if (window.__probe.raf.length < 4000) requestAnimationFrame(tick);
  })(performance.now());
  /* ...and WHAT is blocking, when something is. A long rAF interval says the
     frame was late; it does not say why, and the two candidates want opposite
     fixes — a saturated GPU is cured by drawing less, a blocked main thread is
     not cured by drawing less at all. longtask entries name the second one. */
  window.__probe.long = [];
  try {
    new PerformanceObserver(l => {
      for (const e of l.getEntries()) window.__probe.long.push(Math.round(e.duration));
    }).observe({entryTypes: ['longtask']});
  } catch (e) {}
  /* ...and how often the SURFACE is torn down and rebuilt under us. resize()
     reallocates the canvas backing store and every composer render target, and
     build() disposes and rebuilds the whole scene. Either one, happening
     repeatedly, is a visible flash that no frame-interval number can show —
     the intervals stay perfect while the thing being presented is being
     reallocated. A viewport that oscillates by a pixel (a scrollbar
     appearing and disappearing) is enough to drive it. */
  window.__probe.resizes = 0; window.__probe.builds = 0; window.__probe.sizes = {};
  const oresize = STAGE.resize.bind(STAGE);
  STAGE.resize = function () {
    window.__probe.resizes++;
    window.__probe.sizes[window.innerWidth + 'x' + window.innerHeight] =
      (window.__probe.sizes[window.innerWidth + 'x' + window.innerHeight] || 0) + 1;
    return oresize();
  };
  const obuild = STAGE.build.bind(STAGE);
  STAGE.build = function () { window.__probe.builds++; return obuild(); };
  /* ...and how often the canvas is HIDDEN. blur() toggles
     `#stage{visibility:hidden}`, which makes the canvas vanish and the static
     CSS wash show through. Qt is documented here as firing spurious focus/blur
     pairs on things that are not really a focus change, and each pair that
     outlasts the 150ms debounce is a visible flash — of exactly the kind being
     reported, and one that every frame-interval number in this tool would call
     perfect while it happened. */
  window.__probe.blurs = 0; window.__probe.hidden = 0;
  const oblur = STAGE.blur.bind(STAGE);
  STAGE.blur = function (on) { if (on) window.__probe.blurs++; return oblur(on); };
  new MutationObserver(() => {
    if (document.documentElement.classList.contains('stage-blur')) {
      window.__probe.hidden++;
    }
  }).observe(document.documentElement, {attributes: true, attributeFilter: ['class']});
  /* ...and the RAW events under all of that, with their arrival times. The
     three counters above see what the page DID; only this sees what Qt SENT,
     and the difference is the whole question: a blur/focus pair that Qt fires
     on something which is not a focus change is a full-screen flash by
     construction, and the 150ms debounce only swallows it if the focus lands
     inside that window. `t0` is the sampler's own start so the gaps read
     directly, and it is the PAIRS that matter, not the totals. */
  window.__probe.ev = []; window.__probe.t0 = performance.now();
  for (const k of ['blur', 'focus']) {
    window.addEventListener(k, () => {
      if (window.__probe.ev.length < 400) {
        window.__probe.ev.push(k[0] + Math.round(performance.now() - window.__probe.t0));
      }
    });
  }
  document.addEventListener('visibilitychange', () => {
    if (window.__probe.ev.length < 400) {
      window.__probe.ev.push((document.hidden ? 'H' : 'V')
        + Math.round(performance.now() - window.__probe.t0));
    }
  });
  const orig = STAGE._tick.bind(STAGE);
  STAGE._tick = function (dt) {
    const before = STAGE._Tw;
    const r = orig(dt);
    if (STAGE._Tw !== before) {
      const now = performance.now();
      if (window.__probe.last) window.__probe.ms.push(now - window.__probe.last);
      window.__probe.last = now;
    }
    return r;
  };
  return 'ok';
})()
"""

REPORT = """
(() => {
  const ms = (window.__probe && window.__probe.ms || []).slice().sort((a, b) => a - b);
  const at = q => ms.length ? ms[Math.min(ms.length - 1, Math.floor(ms.length * q))] : 0;
  const rf = (window.__probe && window.__probe.raf || []).slice().sort((a, b) => a - b);
  const rat = q => rf.length ? rf[Math.min(rf.length - 1, Math.floor(rf.length * q))] : 0;
  const r = STAGE._ren, sc = STAGE._sc;
  let ren = 'unknown';
  try {
    const gl = r.getContext();
    const ext = gl.getExtension('WEBGL_debug_renderer_info');
    if (ext) ren = gl.getParameter(ext.UNMASKED_RENDERER_WEBGL);
  } catch (e) {}
  let tri = 0, calls = 0, gpu = 0;
  if (r && sc) {
    r.info.autoReset = false; r.info.reset();
    if (STAGE._post) STAGE._post.render(0.016); else r.render(sc.scene, sc.camera);
    tri = r.info.render.triangles; calls = r.info.render.calls;
    r.info.autoReset = true; r.info.reset();
    /* WHAT ONE FRAME ACTUALLY COSTS THE GPU, and gl.finish() is the whole
       measurement. Timing render() alone measures command submission, which
       is asynchronous and near zero however loaded the GPU is — the reason
       STAGE._watch samples intervals instead. finish() blocks until the GPU
       has drained, so ten frames wall-clocked around one finish is a real
       per-frame cost. It answers the question the frame-interval numbers
       cannot: is a frame under one vsync, i.e. is running at the display rate
       even an option on this machine? */
    try {
      const gl = r.getContext();
      const t0 = performance.now();
      for (let i = 0; i < 10; i++) {
        if (STAGE._post) STAGE._post.render(0.016); else r.render(sc.scene, sc.camera);
      }
      gl.finish();
      gpu = (performance.now() - t0) / 10;
    } catch (e) {}
  }
  const sz = new (window.THREE.Vector2)();
  if (r) r.getSize(sz);
  const pr = r ? r.getPixelRatio() : 0;
  return {
    renderer: ren, scene: STAGE.scene, tier: STAGE.tier, ok: !!STAGE.ok,
    world: (window.ST || {}).world || '',
    ratio: pr, bufW: Math.round(sz.x * pr), bufH: Math.round(sz.y * pr),
    tri: tri, calls: calls, gpu: gpu, frames: ms.length,
    p50: at(0.50), p95: at(0.95), worst: ms.length ? ms[ms.length - 1] : 0,
    // the SNAPPED target, which is what the stage actually aims at: a whole
    // number of vsyncs. Reporting the unsnapped 1/fps compares the machine
    // against an interval no display can produce, which is how the beat this
    // measures went unnoticed in the first place.
    asked: (() => {
      const fps = 24 + 10 * STAGE._E;
      const vs = Math.min(0.05, Math.max(1 / 144, STAGE._vs || 1 / 60));
      return Math.max(1, Math.ceil(1 / fps / vs)) * vs * 1000;
    })(),
    vsync: (STAGE._vs || 0) * 1000, energy: STAGE._E,
    degraded: STAGE._degraded, budget: STAGE._budget,
    slow: STAGE._slow, strain: STAGE._strain,
    cssW: window.innerWidth, cssH: window.innerHeight,
    rafP50: rat(0.50), rafP95: rat(0.95), rafN: rf.length,
    resizes: window.__probe.resizes, builds: window.__probe.builds,
    sizes: window.__probe.sizes,
    blurs: window.__probe.blurs, hidden: window.__probe.hidden,
    ev: (window.__probe.ev || []).slice(0, 40), evN: (window.__probe.ev || []).length,
    /* WHY THE CHAIN IS PARKED, when it is — and it was, on the first run that
       activated the window: three rendered frames in eight seconds with a
       clean 60Hz rAF floor beside it. A frame count cannot distinguish "the
       scene is slow" from "the job was never called", and those want opposite
       fixes. Six flags, cheapest first: the loop's own switches, then what the
       page believes about focus, then what the DOM says. */
    moVis: !!MO.vis, moOn: !!MO.on, moRaf: !!MO._raf, moJobs: (MO._jobs ? MO._jobs.size : 0),
    docHidden: !!document.hidden, docFocus: document.hasFocus(),
    cls: document.documentElement.className,
    ticks: STAGE._vi || 0,
    long: (window.__probe.long || []).slice().sort((a, b) => b - a).slice(0, 8),
    longN: (window.__probe.long || []).length,
    longMs: (window.__probe.long || []).reduce((t, x) => t + x, 0),
  };
})()
"""


def _render(r, seconds):
    print(f"\n  world      {r['world'] or '(classic)'}  scene={r['scene']}  "
          f"tier={r['tier']}")
    print(f"  renderer   {r['renderer']}")
    print(f"  buffer     {r['bufW']}x{r['bufH']} = "
          f"{r['bufW'] * r['bufH'] / 1e6:.2f}M px   (ratio {r['ratio']:.3f})")
    print(f"  geometry   {r['tri']:,} triangles in {r['calls']} draw calls")
    vs = r['vsync'] or 16.7
    print(f"  gpu cost   {r['gpu']:.1f}ms per frame, drained  "
          f"({r['gpu'] / vs:.2f} vsyncs — full rate needs < 1.00)")
    print(f"  frames     {r['frames']} rendered in {seconds:g}s   "
          f"energy {r['energy']:.2f}")
    print(f"  interval   p50 {r['p50']:.1f}ms   p95 {r['p95']:.1f}ms   "
          f"worst {r['worst']:.1f}ms   (asked {r['asked']:.1f}ms = "
          f"{max(1, round(r['asked'] / (r['vsync'] or 16.7)))} vsync @ "
          f"{r['vsync']:.1f}ms)")
    print(f"  raf floor  p50 {r['rafP50']:.1f}ms   p95 {r['rafP95']:.1f}ms   "
          f"over {r['rafN']} frames  <- the page, with no stage in it")
    print(f"  main jank  {r['longN']} long tasks, {r['longMs']}ms total, "
          f"worst {r['long'] or [0]}")
    print(f"  surface    {r['resizes']} resizes, {r['builds']} rebuilds"
          + (f"  viewports={r['sizes']}" if r['resizes'] else ''))
    print(f"  canvas hid {r['blurs']} blur calls, {r['hidden']} times the canvas "
          f"went visibility:hidden  <- each one is a visible flash")
    print(f"  chain      MO.vis={r['moVis']} MO.on={r['moOn']} raf={r['moRaf']} "
          f"jobs={r['moJobs']}  |  document.hidden={r['docHidden']} "
          f"hasFocus={r['docFocus']}  |  {r['ticks']} stage ticks")
    print(f"  html class {r['cls']}")
    print(f"  qt events  {r['evN']} focus/blur/visibility events"
          + (f": {' '.join(r['ev'])}" if r['ev'] else ' (none — focus held)'))
    print(f"  ladder     degraded={r['degraded']}  "
          f"budget={r['budget'] / 1e6:.2f}M px")
    print(f"  compositor viewport {r['cssW']}x{r['cssH']} css   "
          f"drawing 1 frame in {r['slow']}  (strain {r['strain']})")
    soft = any(s in (r['renderer'] or '').lower()
               for s in ('swiftshader', 'warp', 'llvmpipe', 'software'))
    print()
    if r['rafP50'] > 20:
        print(f"  VERDICT  THE PAGE ITSELF runs at {1000 / r['rafP50']:.0f}fps before the")
        print('           stage draws anything. The scene cannot be faster than the')
        print('           frame it is drawn into, so the cost is not in it — look at')
        print('           the compositor, the display mode and what else animates.')
    elif soft:
        print('  VERDICT  the Qt shell is rendering in SOFTWARE. Nothing in the scene')
        print('           is the cause and nothing in it is the fix — chase the GPU')
        print('           process, not the triangle count.')
    elif r['p95'] > r['asked'] * 1.6:
        print('  VERDICT  over budget. The frame is not keeping the pace it asked for,')
        print('           which is what a mid-composite surface swap looks like. Next')
        print('           rungs: --tier lite, then')
        print('           QTWEBENGINE_CHROMIUM_FLAGS=--disable-gpu-compositing')
    else:
        print('  VERDICT  within budget on this machine.')
    print()


def _shoot(app, n):
    """Grab the composited SCREEN n times and report what moved between frames.

    Everything else in this tool measures the page's opinion of itself, and a
    flicker is precisely the artefact that leaves no trace there — the frame
    intervals stay perfect while something on screen appears and disappears.
    This captures what DWM actually composited, which is what the eye gets.

    Reported per consecutive pair: the mean absolute difference and the
    bounding box of the pixels that changed. A scene that is merely animating
    gives a small diff spread over the whole canvas; something toggling gives a
    large diff with a box around it, and the box says WHAT.
    """
    from PyQt6.QtGui import QGuiApplication
    scr = QGuiApplication.primaryScreen()
    os.makedirs('.qa', exist_ok=True)
    frames = []
    for i in range(n):
        img = scr.grabWindow(0).toImage().convertToFormat(4)   # RGB32
        img.save(f'.qa/flicker-{i:02d}.png')
        w, h = img.width(), img.height()
        ptr = img.constBits()
        ptr.setsize(img.sizeInBytes())
        frames.append((w, h, img.bytesPerLine(), bytes(ptr)))
        app.processEvents()

    print(f"\n  screen     {frames[0][0]}x{frames[0][1]}, {n} grabs -> .qa/flicker-*.png")
    # coarse 32x18 grid: a full-resolution diff of a 2560x1440 frame in pure
    # python is minutes, and a flicker is never one pixel wide
    GX, GY = 32, 18
    for i in range(1, len(frames)):
        w, h, bpl, a_ = frames[i - 1]
        _w, _h, _bpl, b_ = frames[i]
        if (w, h) != (_w, _h):
            print(f"    {i - 1}->{i}: screen size changed")
            continue
        cells, tot = [], 0
        for gy in range(GY):
            for gx in range(GX):
                x = w * gx // GX
                y = h * gy // GY
                d = 0
                for k in range(6):                       # 6 probes per cell
                    px = x + (w // GX) * k // 6
                    o = y * bpl + px * 4
                    d += abs(a_[o] - b_[o]) + abs(a_[o + 1] - b_[o + 1]) \
                        + abs(a_[o + 2] - b_[o + 2])
                tot += d
                if d > 60:
                    cells.append((gx, gy))
        if cells:
            xs = [c[0] for c in cells]
            ys = [c[1] for c in cells]
            box = (f"cols {min(xs)}-{max(xs)}/{GX}, rows {min(ys)}-{max(ys)}/{GY}"
                   f" ({len(cells)} of {GX * GY} cells)")
        else:
            box = 'nothing moved'
        print(f"    {i - 1}->{i}: diff {tot:6d}   {box}")


def _foreground(win):
    """Make the Qt window the FOREGROUND window, which `activateWindow()`
    alone cannot do from here.

    Windows refuses SetForegroundWindow to a process that is not already the
    foreground one — and a tool launched from a terminal never is; the terminal
    is. Measured: after `raise_()` + `activateWindow()` + `setFocus()` the page
    still reported `document.hasFocus() === false`, `MO.vis === false` and
    `win-blur` on <html>, i.e. the app had parked itself exactly as designed
    and the probe was timing a stopped scene (three rendered frames in eight
    seconds beside a clean 60Hz rAF floor).

    The documented way round it is to borrow the input queue of the thread that
    currently owns the foreground window, which makes our call legal for as
    long as we are attached. Best-effort: it is a diagnostic, so a failure
    prints and the run continues (the report says whether focus landed).
    """
    if sys.platform != 'win32':
        return
    import ctypes
    u = ctypes.windll.user32
    hwnd = int(win.winId())
    fg = u.GetForegroundWindow()
    tid = u.GetWindowThreadProcessId(fg, None)
    own = ctypes.windll.kernel32.GetCurrentThreadId()
    if tid and tid != own:
        u.AttachThreadInput(tid, own, True)
    try:
        u.BringWindowToTop(hwnd)
        u.SetForegroundWindow(hwnd)
        u.SetActiveWindow(hwnd)
        u.SetFocus(hwnd)
    finally:
        if tid and tid != own:
            u.AttachThreadInput(tid, own, False)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--world', default='graph')
    ap.add_argument('--tier', default='cinematic', choices=('cinematic', 'lite', 'off'))
    ap.add_argument('--seconds', type=float, default=6.0)
    ap.add_argument('--budget', type=float, default=0,
                    help='override STAGE_PIXEL_BUDGET, to see what a cap buys')
    ap.add_argument('--zen', action='store_true',
                    help='hide the app chrome, so the stage is the whole frame')
    ap.add_argument('--flags', default='',
                    help='extra QTWEBENGINE_CHROMIUM_FLAGS, e.g. '
                         '--flags=--disable-direct-composition. Here rather than '
                         'left to the shell because `VAR=value cmd` is bash '
                         'syntax and this project is Windows-first: in '
                         'PowerShell that line is parsed as a command name.')
    ap.add_argument('--every', type=int, default=0,
                    help='let only every Nth stage frame through. Tests whether '
                         'the COMPOSITOR is the bottleneck rather than the '
                         'renderer: each canvas update forces a full-screen '
                         'recomposite, so if slowing the canvas lifts the '
                         "page's own rAF back to 60Hz, the cost is in "
                         'compositing and not in drawing.')
    ap.add_argument('--shots', type=int, default=0,
                    help='after reporting, grab the SCREEN this many times in a '
                         'row and report what changed between consecutive '
                         'frames. A flicker is a thing that is invisible to '
                         'every in-page number and obvious in a difference '
                         'image; this is the only instrument here that can see '
                         'one. Frames land in .qa/flicker-NN.png')
    ap.add_argument('--hold', action='store_true',
                    help='leave the window OPEN after reporting, so the artifact '
                         'can be looked at. Some things (a flicker in a scanout '
                         'plane) are invisible to every number this tool prints '
                         'and visible to a person in one second.')
    ap.add_argument('--ratio', type=float, default=0,
                    help='pin the render scale, bypassing the pixel budget. '
                         '1.0 gives a canvas whose backing store matches its CSS '
                         'box, which is the one case the compositor does not '
                         'have to resample')
    ap.add_argument('--pin', action='store_true',
                    help="stop the PAGE parking itself when it loses focus, so "
                         "a stolen activation does not end the sample. The app "
                         "pauses everything on blur by design (setVis -> "
                         "win-blur -> the GL surface comes down), and "
                         "SetForegroundWindow is a best-effort grab that "
                         "something else can take back mid-run: measured, an "
                         "8-second sample kept focus for 3.6s of it and the "
                         "other 4.4s counted as zero frames. Comparing two "
                         "flags needs both runs to have drawn for the same "
                         "wall time, so this pins visibility on. The raw Qt "
                         "focus events are still reported — pinning changes "
                         "what the page DOES about them, not what it saw.")
    ap.add_argument('--fullscreen', action='store_true',
                    help='measure FULLSCREEN, which on Windows is a different '
                         'presentation path: a windowed app is composited by DWM '
                         'and DWM is always vsynced, so it cannot tear, while a '
                         'fullscreen one can be handed direct scanout, which can')
    a = ap.parse_args()

    # BEFORE PyQt6 is imported: QtWebEngine reads this when Chromium starts,
    # and run_desktop() deliberately does not override a pre-set value.
    if a.flags:
        cur = os.environ.get('QTWEBENGINE_CHROMIUM_FLAGS', '')
        os.environ['QTWEBENGINE_CHROMIUM_FLAGS'] = (cur + ' ' + a.flags).strip()
        print(f"  flags      QTWEBENGINE_CHROMIUM_FLAGS="
              f"{os.environ['QTWEBENGINE_CHROMIUM_FLAGS']}")

    from PyQt6.QtCore import QTimer
    from claude_sessions.gui_qt import run_desktop

    def ready(view, app):
        page = view.page()
        if a.fullscreen:
            # the WINDOW, not the widget — showFullScreen on the view alone
            # reparents it and the measurement is of something the user never
            # sees. This has to be the same transition they make.
            view.window().showFullScreen()
        # ACTIVATE, always, and this is not cosmetic. The page pauses
        # everything on `blur` (setVis -> win-blur -> the stage's surface comes
        # down), and a tool launched from a terminal leaves focus with the
        # terminal — so the first fullscreen run of this probe reported ZERO
        # rendered frames in six seconds and every number in it was measuring a
        # parked page. The user is looking AT the window when they see the
        # artifact; the measurement has to be too.
        w = view.window()
        w.raise_()
        w.activateWindow()
        view.setFocus()
        _foreground(w)
        # runJavaScript is asynchronous and its callback is the only place a
        # result exists, so the sequence is a chain of timers rather than a
        # loop. Each step waits for the previous one to have LANDED, not for a
        # guessed interval — the settle after a world change matters, because
        # applyTheme rebuilds the whole scene and the first frames after that
        # include a shader compile that is not what we are measuring.
        def step2():
            # the world FIRST and the tier after it, and the order is not
            # cosmetic: applyTheme re-applies the saved settings, so a tier set
            # before it is silently overwritten by whatever is in
            # settings.json. That is not hypothetical — it produced a run that
            # reported `tier: off, ok: false` on a machine where the setting
            # had been switched off by hand, i.e. the tool measured the user's
            # saved preference instead of the flag it was given.
            js = f"ST.world = {json.dumps(a.world)}; applyTheme(ST.theme);"
            js += f" STAGE.setTier({json.dumps(a.tier)});"
            if a.budget:
                js += f" STAGE._budget = {a.budget!r}; STAGE.resize();"
            if a.ratio:
                js += (f" STAGE._ratio = () => {a.ratio!r};"
                       " STAGE.resize();")
            if a.zen:
                js += ' setZen(true);'
            if a.pin:
                js += (' setVis = () => {}; setVisSoon = () => {};'
                       ' MO.vis = true; MO.kick(); if (window.STAGE) STAGE.blur(false);'
                       " document.documentElement.classList.remove('win-blur');")
            if a.every > 1:
                js += (f" (()=>{{const o=STAGE._tick.bind(STAGE);let n=0;"
                       f"STAGE._tick=d=>{{n++;return n % {a.every} ? true : o(d);}};}})();")
            page.runJavaScript(js, lambda _: QTimer.singleShot(1500, step3))

        def step3():
            # AGAIN, immediately before the sample. Once at load is not enough:
            # the grab is best-effort and four seconds of theme application sit
            # between them, and a windowed run that had focus at load reported
            # `hasFocus false` here while the fullscreen one kept it. The
            # report prints the flag, so a run that still lost the race is
            # recognisable rather than silently measuring a parked page.
            _foreground(view.window())
            page.runJavaScript(SAMPLER,
                               lambda _: QTimer.singleShot(int(a.seconds * 1000), step4))

        def step4():
            page.runJavaScript(REPORT, done)

        def done(r):
            if not r or not r.get('ok'):
                print('\n  the stage is not running in the Qt window '
                      f'(got {r!r})\n', file=sys.stderr)
            else:
                _render(r, a.seconds)
            if a.shots:
                _shoot(app, a.shots)
            if a.hold:
                print('  --hold: the window stays open. Close it when done.\n')
            else:
                app.quit()

        # loadFinished means the document loaded, not that the deferred vendor
        # bootstrap has resolved and the stage has mounted — so poll for the
        # thing we are about to drive rather than guessing an interval.
        tries = [0]

        def wait_ready(ok):
            tries[0] += 1
            if ok or tries[0] > 60:
                QTimer.singleShot(300, step2)
            else:
                QTimer.singleShot(250, lambda: page.runJavaScript(
                    '!!(window.STAGE && window.ST && window.THREE)', wait_ready))

        wait_ready(False)

    run_desktop(on_ready=ready)
    return 0


if __name__ == '__main__':
    sys.exit(main())

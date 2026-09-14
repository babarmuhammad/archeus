# The graph world's flicker in the Qt shell — found, measured, fixed

Machine: Windows 11, Intel UHD Graphics (0x A788), PyQt6 / Qt 6.11.0,
QtWebEngine renderer `ANGLE (Intel, Intel(R) UHD Graphics, Direct3D11 vs_5_0
ps_5_0, D3D11)`.

The report: the graph theme flickers, only in the Qt shell, worst in full
screen — and a previous pass of fixes had not stopped it.

## The answer, first

**The scene's own cost, and it was five times larger than any measurement had
shown, because every earlier fullscreen measurement was taken on a PARKED
page.** With the lit cluster (353,566 triangles in 33 draw calls of blended
depth-tested PBR over a 3.0M-pixel buffer) the page's OWN frame delivery
collapsed in full screen; with the flat cluster (24,494 triangles) it holds a
clean 60Hz. Measured, `tools/probe_qt.py --world graph --fullscreen --pin`:

| | lit cluster | flat cluster |
|---|---|---|
| page rAF p50 / p95 | 16.8 / **249.9** ms | 16.7 / **16.8** ms |
| rAF frames in 8s | 138 (~17fps) | 480 (60fps) |
| stage interval p50 | 95.5 ms (asked 33.4) | 50.0 ms (asked 50.1) |
| stage worst frame | 398 ms | 58.9 ms |
| GPU per frame, drained | 0.8 ms | 0.1 ms |
| compositor back-off (`_slow`) | 2 | 1 |
| strain | 62 | 0 |
| long tasks | 0 | 0 |

Zero long tasks in both, so the main thread was never the problem. What a page
that cannot keep up looks like in Chromium is not slowness: it halves its own
frame rate, so the whole app lurches between 60 and ~17Hz — which is what was
being reported as flickering, and why it appeared in full screen and nowhere
else.

## The instrumentation bug that hid it for two sessions

`tools/probe_qt.py` drove the window through `run_desktop(on_ready=...)` but
never ACTIVATED it, and a tool launched from a terminal leaves focus with the
terminal. The app pauses everything on `blur` by design — `setVis(false)` →
`win-blur` on `<html>` → `STAGE.blur(true)` takes the GL surface down — so the
first fullscreen run reported:

```
frames     0 rendered in 8s
raf floor  p50 16.7ms  p95 16.8ms  over 481 frames
chain      MO.vis=False MO.on=True raf=False jobs=2 | hasFocus=False | 0 stage ticks
html class ... win-blur
```

Every number in it was measuring a stopped scene, including the previous
session's "fullscreen and windowed measure identically". Two fixes, both in the
probe:

* `_foreground()` — `raise_()` + `activateWindow()` + `setFocus()` is not
  enough: Windows refuses `SetForegroundWindow` to a process that is not
  already the foreground one. The documented way round it is to attach to the
  input queue of the thread that owns the foreground window for the duration of
  the call. It is called again immediately before the sample, because
  something took focus back mid-run on one windowed attempt (3.6s of an
  8-second window measured, the other 4.4s counted as zero frames).
* `--pin` — neutralises the page's own parking for the duration of a
  measurement, so a stolen activation cannot end the sample. The raw Qt focus
  events are still reported; pinning changes what the page DOES about them.

The report now prints `MO.vis / MO.on / raf / jobs / document.hidden /
hasFocus / stage ticks` and the raw focus/blur/visibility events with arrival
times, so a run that measured a parked page says so.

## What the web says — a real Qt bug exists, and it is not what was happening here

Worth keeping, because it is the thing to reach for if tearing ever returns on
hardware where the cost is already low:

* **Qt forum 156145** — "Flickering of webengineview when showing webGL
  content". Windows + Qt 6 only (not 5.15). Diagnosis in the thread: *"it's not
  properly synchronising the ANGLE part with its HTML render engine"*. Last post
  Oct 2025: *"Still WebGL on Qt 6.xx is a no go."* No flag workaround, no Qt fix.
* **Anki #4470** — same class, and the only report with a flag matrix.
  `--disable-gpu-compositing` fixed it at an unacceptable performance cost;
  `--disable-gpu-rasterization`, `--disable-accelerated-2d-canvas` and
  `--disable-webgl` did nothing; `--use-gl=swiftshader` crashed at startup. The
  same frontend is clean in WebView2 and in Qt WebEngine on Linux.
* **Qt docs, "Qt for Windows — Specific Issues"**: a window with an OpenGL
  surface going *fullscreen* hits DWM compositing that "is not handled
  correctly"; the documented workaround is to resize the window to the desktop
  size instead of using real fullscreen.

Flags tested here, on the lit scene, fullscreen:

| flag | result |
|---|---|
| `--disable-direct-composition` | helps but is not clean — rAF p95 250 → 66ms, and the compositor back-off went to `_slow` 4. It also changes the page's devicePixelRatio (1.5 → 1.0), so the two runs are not measuring the same layout. |
| `--use-angle=gl` | **breaks WebGL entirely** on this driver: `native_skia_output_device.cpp:279 CreateSharedImage failed` on repeat, the stage falls back to `stage-off`, `ok: false`. Do not ship. |
| `QTWEBENGINE_DISABLE_GPU_THREAD=1` | inconclusive (the run lost focus); not needed once the cost came down. |

None of them are applied. `gui_qt.py` still leaves GPU compositing ON and still
does not override a pre-set `QTWEBENGINE_CHROMIUM_FLAGS`, so the
`--disable-gpu-compositing` hatch remains available per-machine without a code
change.

## The order to try things in, if it comes back

1. `py tools/probe_qt.py --world <world> --fullscreen --pin --seconds 8` and
   **read `hasFocus` and `stage ticks` first**. A parked page measures nothing.
2. Read `gpu cost` and `raf floor`. A GPU cost near a vsync means draw less; a
   clean GPU cost with a bad rAF p95 means the compositor or the present path.
3. `--tier lite` (drops `EffectComposer` and its two render targets).
4. `--flags=--disable-direct-composition`.
5. `QTWEBENGINE_CHROMIUM_FLAGS=--disable-gpu-compositing`, which is correct and
   sluggish, and is the last rung for a reason.

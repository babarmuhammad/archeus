'use client';

/**
 * Mounts the journey scene behind the copy.
 *
 * Four rules shape the whole file, and this project has paid for each one:
 *
 *  1. ONE requestAnimationFrame chain, and it PARKS. A loop that runs while
 *     nothing is visible is a bug, not a feature. Parking destroys the Lenis
 *     instance first — a smooth-scroll driver that stops being ticked has
 *     preventDefault-ed the wheel and left you with a frozen page, so a parked
 *     page always falls back to native scrolling.
 *  2. It fails open. No WebGL, a thrown context, a lost context or
 *     prefers-reduced-motion hides the canvas and the static wash in
 *     globals.css is the page's background. `journey-on` goes on <html> only
 *     once GL has actually painted, so a deferred import is never a second of
 *     blank.
 *  3. Progress is derived from window.scrollY and measured panel offsets, never
 *     from Lenis. Lenis smooths what the browser reports; if it fails to load,
 *     is asleep, or is destroyed, the journey is still exactly right.
 *  4. A ROUTE CHANGE re-measures and SNAPS. The GL context is deliberately not
 *     rebuilt when you navigate between two content routes — but the scene was
 *     then still driving the previous page's section offsets and weights, so
 *     leaving a nine-section page for a three-section one left the solids flying
 *     in from index eight. The effect below with `[pathname]` is the fix, and it
 *     is why switching pages stopped tearing the animation.
 *
 * three and lenis are imported inside the effect so neither is in the initial
 * bundle. Every import here is `import type` for the same reason.
 */
import { useEffect, useRef } from 'react';
import { usePathname } from 'next/navigation';
import type * as THREE from 'three';
import type Lenis from 'lenis';
import type { Journey, LayoutName, Slot } from './scene';

/** How fast progress chases the scroll, in e-folds per second. */
const DAMP = 6.5;
/** Seconds the station-01 joint sweep takes on arrival. */
const LIT_SECONDS = 1.4;
/** Anything the pointer might legitimately be aiming at instead of a solid. */
const INTERACTIVE = 'a,button,summary,details,input,textarea,select,label,[role="button"]';

/**
 * `journey` is the landing page: scroll drives the camera from station to
 * station. `ambient` is every other route: the same constellation parked at the
 * finale's pull-back, turning slowly, with no scroll coupling and no Lenis —
 * plus that page's own section solids, placed by the slots its layout leaves.
 *
 * One scene, one branch. The alternative was eleven static pages — the site
 * stopped moving the moment you clicked Features, which is the opposite of the
 * point. It stays quiet on purpose: this project has already learned that drama
 * belongs in the interface and the background has a luminance ceiling.
 */
export function JourneyCanvas({ mode = 'journey' }: { mode?: 'journey' | 'ambient' }) {
  const ref = useRef<HTMLCanvasElement>(null);
  /** The live scene's re-measure hook. A route change calls it; the GL effect
   *  owns it. Held in a ref rather than lifted into state because rebuilding the
   *  renderer on navigation is exactly what this is here to avoid. */
  const sync = useRef<(() => void) | null>(null);
  const pathname = usePathname();

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const html = document.documentElement;
    const ambient = mode === 'ambient';

    /** Fail open: a canvas we cannot drive is worse than no canvas. */
    const drop = () => {
      html.classList.remove('journey-on');
      canvas.style.display = 'none';
    };

    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
    // Reduced motion gets the scene STILL, not removed. Declining motion is not
    // the same as declining the picture, and removing the canvas left the whole
    // site looking like an unstyled document to anyone whose OS has animation
    // effects switched off — which on Windows 11 is one toggle in Accessibility,
    // and is not a rare setting.
    //
    // One frame is drawn and the loop never starts: `awake()` is false while
    // `still`, so nothing reschedules.
    let still = reduced.matches;

    let cancelled = false;
    let lost = false;
    // Optimistic: only a real blur event clears it. A page that happens to load
    // without focus (a screenshot runner, a restored window) still paints.
    let focused = true;
    let painted = false;
    let raf = 0;

    let renderer: THREE.WebGLRenderer | null = null;
    let scene: THREE.Scene | null = null;
    let camera: THREE.PerspectiveCamera | null = null;
    let journey: Journey | null = null;
    let LenisCtor: typeof Lenis | null = null;
    let lenis: Lenis | null = null;

    let progress = 0;
    let sec = 0;
    let clock = 0;
    let lit = 0;
    let prev = 0;
    // Pointer parallax: the raw target from pointermove, and the damped value the
    // scene actually sees. One delegated listener, no per-element handlers.
    let pxT = 0, pyT = 0, px = 0, py = 0;
    // Last pointer position in NDC, for the hover hit test.
    let ndcX = 0, ndcY = 0;
    let hovering = false;

    const awake = () =>
      !cancelled && !lost && !still && !document.hidden && focused;

    /** One frame, then nothing. The still path for reduced motion. */
    const paintOnce = () => {
      lit = 1;
      progress = targetProgress();
      sec = sectionAt();
      frame(performance.now());
    };

    const clamp01 = (x: number) => (x < 0 ? 0 : x > 1 ? 1 : x);

    /* ── where the scroll is ────────────────────────────────────────────────
       Panel offsets, measured on resize and on reflow, never in the frame loop.
       A single division by the container's scroll height would assume the six
       panels are the same height — they are not, station 03 alone is worth two
       of station 02 — and the camera would arrive at a solid while you were
       still three paragraphs above it. */
    let tops: number[] = [];
    let end = 0;

    /** Section tops, for `sectionAt`. The solids' POSITIONS do not come from
     *  here — they come from the slots below. */
    let secTops: number[] = [];
    let secEls: HTMLElement[] = [];

    const measure = () => {
      const host = document.getElementById('journey-stations');
      const y = window.scrollY;
      const panels = host
        ? Array.from(host.querySelectorAll<HTMLElement>('[data-station]'))
        : [];
      tops = panels.map((el) => el.getBoundingClientRect().top + y);
      end = host ? host.getBoundingClientRect().bottom + y - window.innerHeight : 0;

      const secs = Array.from(document.querySelectorAll<HTMLElement>('[data-section]'));
      secEls = secs;
      secTops = secs.map((el) => el.getBoundingClientRect().top + y);

      // The empty box each section's layout leaves for its solid. Document space,
      // so only the scroll offset has to be written per frame — and so the solid
      // tracks its own copy exactly, at any row height, on any page.
      const slots: Slot[] = Array.from(document.querySelectorAll<HTMLElement>('[data-slot]'))
        .map((el) => {
          const r = el.getBoundingClientRect();
          return {
            x: r.left + r.width / 2,
            y: r.top + y + r.height / 2,
            // The half-extent that FITS: a tall narrow rail slot must not draw a
            // solid as wide as the slot is tall.
            r: Math.min(r.width, r.height) / 2,
          };
        });

      // A hidden slot (narrow viewport) measures zero and must not be counted, or
      // every section after it would index the wrong box.
      const usable = slots.length === secs.length && slots.every((s) => s.r > 4);
      journey?.setSlots(usable ? slots : []);

      const layout =
        (document.querySelector<HTMLElement>('[data-spine]')?.dataset.layout as LayoutName) ??
        'beside';
      // Weight is authored per section; a missing one is 1, not a crash.
      journey?.setSections(
        usable ? secs.map((el) => Number(el.dataset.weight) || 1) : [],
        layout,
      );
    };

    /** Continuous section index. A section is "current" from the moment its top
     *  passes the upper third of the viewport, which is where a reader's eye
     *  actually is — using the viewport top makes the solid change one screen
     *  before the heading it belongs to. */
    const sectionAt = () => {
      if (secTops.length < 2) return 0;
      const y = window.scrollY + window.innerHeight * 0.34;
      let i = 0;
      while (i < secTops.length - 1 && y >= secTops[i + 1]) i++;
      const span = i + 1 < secTops.length ? secTops[i + 1] - secTops[i] : 0;
      return i + (span > 0 ? clamp01((y - secTops[i]) / span) : 0);
    };

    /** Target progress in 0..1: which panel the viewport top sits in, and how
     *  far through it. Arriving at a panel parks the camera at its station. */
    const targetProgress = () => {
      // Ambient parks at the finale, where the camera holds the whole
      // constellation. Nothing to measure, nothing to chase.
      if (ambient) return 1;
      const y = window.scrollY;
      if (tops.length < 2) {
        // The panels moved or have not rendered: fall back to the document's
        // own scroll range, so the scene is never stuck at zero.
        const range = document.documentElement.scrollHeight - window.innerHeight;
        return range > 0 ? clamp01(y / range) : 0;
      }
      let i = 0;
      while (i < tops.length - 1 && y >= tops[i + 1]) i++;
      const stop = i + 1 < tops.length ? tops[i + 1] : end;
      const span = stop - tops[i];
      const local = span > 0 ? (y - tops[i]) / span : 0;
      return clamp01((i + local) / (tops.length - 1));
    };

    const resize = () => {
      if (!renderer || !camera || !journey) return;
      const w = window.innerWidth;
      const h = window.innerHeight;
      const pr = Math.min(window.devicePixelRatio || 1, 1.75);
      renderer.setPixelRatio(pr);
      renderer.setSize(w, h, false);
      camera.aspect = w / h;
      // Portrait crops the constellation horizontally, so the vertical fov opens
      // up as the frame narrows. A fixed fov loses the outer solids off the sides
      // of a phone in the finale — 1.5 is the cap that still holds station 02's
      // centre plus its radius at aspect 0.5, which is a 360px-wide viewport.
      camera.fov = 52 * Math.min(1.5, Math.max(1, Math.pow(w / h, -0.7)));
      camera.updateProjectionMatrix();
      // Drawing-buffer pixels for gl_PointSize — a joint drawn from the CSS
      // height shrinks physically on a dense display — and CSS pixels for the
      // slot maths, which is measuring DOM rects.
      journey.resize(w * pr, h * pr, w, h);
    };

    const frame = (now: number) => {
      raf = 0;
      if (!renderer || !camera || !scene || !journey) return;

      // A long frame is not a long time. Clamping keeps a tab that was throttled
      // from teleporting the scene on its first frame back.
      const dt = prev ? Math.min((now - prev) / 1000, 0.05) : 1 / 60;
      prev = now;

      lenis?.raf(now);

      // Frame-rate-independent damping: the camera settles into a station, it
      // never snaps to it.
      progress += (targetProgress() - progress) * (1 - Math.exp(-DAMP * dt));
      // Ambient runs the scene clock at a third speed. It is behind body copy on
      // a page somebody is reading, so it drifts rather than performs.
      clock += ambient ? dt * 0.34 : dt;
      // The station-01 joint sweep is an arrival, not a scroll position — you
      // are already parked at station 01 when the page loads. It is a uniform,
      // so CSS cannot own this one.
      lit = Math.min(1, lit + dt / LIT_SECONDS);
      const k = 1 - Math.exp(-3.5 * dt);
      px += (pxT - px) * k;
      py += (pyT - py) * k;

      // The section index is damped like the camera is: a solid that snapped to
      // the next section mid-scroll would skip its own arrival.
      sec += (sectionAt() - sec) * (1 - Math.exp(-5.5 * dt));

      journey.update(
        camera, clock, progress, lit * lit * (3 - 2 * lit), px, py, sec, window.scrollY,
      );

      renderer.render(scene, camera);

      // Hover is tested here rather than in the pointermove handler: the solids
      // move with the scroll, so what is under a stationary cursor changes
      // without the pointer having moved at all.
      const over = journey.hit(camera, ndcX, ndcY) !== null;
      if (over !== hovering) {
        hovering = over;
        html.classList.toggle('solid-hover', over);
      }

      if (!painted) {
        painted = true;
        html.classList.add('journey-on');
      }
      if (awake()) raf = requestAnimationFrame(frame);
    };

    const sleep = () => {
      if (raf) cancelAnimationFrame(raf);
      raf = 0;
      lenis?.destroy();
      lenis = null;
    };

    const wake = () => {
      if (raf || !renderer || !awake()) return;
      // No smooth-scroll driver on a reading page: it would take the wheel over
      // for a scene that no longer answers to scroll.
      if (LenisCtor && !lenis && !ambient) lenis = new LenisCtor({ lerp: 0.09 });
      prev = 0;
      raf = requestAnimationFrame(frame);
    };

    /* ── every way this parks, and the way back ─────────────────────────────── */
    const off: (() => void)[] = [];
    const on = (t: EventTarget, ev: string, fn: EventListener) => {
      t.addEventListener(ev, fn);
      off.push(() => t.removeEventListener(ev, fn));
    };

    on(document, 'visibilitychange', () => (document.hidden ? sleep() : wake()));
    on(window, 'blur', () => {
      focused = false;
      sleep();
    });
    on(window, 'focus', () => {
      focused = true;
      wake();
    });
    on(window, 'resize', () => {
      resize();
      measure();
    });
    on(window, 'pointermove', (e) => {
      const p = e as PointerEvent;
      pxT = (p.clientX / window.innerWidth) * 2 - 1;
      pyT = 1 - (p.clientY / window.innerHeight) * 2;
      ndcX = pxT;
      ndcY = pyT;
    });
    // A pointer that leaves the window must not park the parallax off-centre.
    on(document, 'pointerleave', () => { pxT = 0; pyT = 0; });

    /* Clicking a solid goes to its section.
       The canvas stays pointer-events:none at z-index -1 — making it clickable
       would put it in front of the copy and end text selection. The document
       hears the click instead, and anything the visitor might actually have been
       aiming at wins: a link, a button, an open <details>, or a selection they
       were dragging. */
    on(document, 'click', (e) => {
      if (!journey || !camera || still) return;
      const t = e.target as HTMLElement | null;
      if (t?.closest(INTERACTIVE)) return;
      if ((window.getSelection()?.toString() ?? '').length > 0) return;
      const p = e as PointerEvent;
      const hit = journey.hit(
        camera,
        (p.clientX / window.innerWidth) * 2 - 1,
        1 - (p.clientY / window.innerHeight) * 2,
      );
      if (!hit) return;
      const target = hit.kind === 'station'
        ? document.querySelector<HTMLElement>(`[data-station="${hit.index}"]`)
        : secEls[hit.index];
      target?.scrollIntoView({
        behavior: reduced.matches ? 'auto' : 'smooth',
        block: hit.kind === 'station' ? 'start' : 'center',
      });
    });

    // three's own constructor already preventDefaults this one, so a restore
    // will follow and three re-uploads everything itself. Until it does, park
    // and fail open — a canvas with a dead context is a black rectangle.
    on(canvas, 'webglcontextlost', () => {
      lost = true;
      sleep();
      drop();
    });
    on(canvas, 'webglcontextrestored', () => {
      lost = false;
      painted = false;
      canvas.style.display = '';
      wake();
    });

    const onReduced = () => {
      still = reduced.matches;
      if (still) {
        sleep();
        paintOnce();
      } else {
        wake();
      }
    };
    reduced.addEventListener('change', onReduced);
    off.push(() => reduced.removeEventListener('change', onReduced));

    // Panels and sections grow when a screenshot loads or the text rewraps; the
    // offsets have to follow or the camera and the solids drift out of step with
    // the copy. Both hosts are observed — watching only the landing page's
    // container meant a shot loading on /features desynchronised everything
    // below it for the rest of the visit.
    const ro = new ResizeObserver(() => measure());
    for (const sel of ['#journey-stations', '[data-spine]']) {
      const el = document.querySelector(sel);
      if (el) ro.observe(el);
    }
    off.push(() => ro.disconnect());

    void (async () => {
      let three: typeof THREE;
      let mod: typeof import('./scene');
      let lenisMod: { default: typeof Lenis } | null;
      try {
        [three, mod, lenisMod] = await Promise.all([
          import('three'),
          import('./scene'),
          // Smooth scroll is a nicety; native scrolling is a fine fallback.
          import('lenis').catch(() => null),
        ]);
      } catch {
        drop();
        return;
      }
      if (cancelled) return;

      try {
        // Opaque on purpose: a transparent surface costs a blend on every
        // composite, and there is nothing behind it worth seeing.
        renderer = new three.WebGLRenderer({ canvas, antialias: true, alpha: false });
      } catch {
        drop();
        return;
      }
      renderer.setClearColor(0x0a0c10, 1);
      /* ACES, and it reaches ONLY the station solids.

         three applies tone mapping per material, to materials that ask for it
         (`toneMapped`), and a raw ShaderMaterial never gets the chunk injected
         — so every scene shader in scene.ts is untouched and the note below
         about not re-encoding raw output still holds exactly. What it does
         reach is the lit MeshPhysicalMaterials the frame is made of, which
         routinely exceed 1.0 once an emissive term meets three lights: without
         a curve every one of them clips to white, channel by channel at a
         different point, and a violet cluster comes out pink. */
      renderer.toneMapping = three.ACESFilmicToneMapping;
      renderer.toneMappingExposure = 1.0;

      scene = new three.Scene();
      camera = new three.PerspectiveCamera(52, 1, 0.1, 220);
      journey = mod.buildJourney();
      // The journey is the landing page. A content route shows only its own
      // section solids — running both at once is what buried the copy.
      journey.setStations(!ambient);
      scene.add(journey.group);
      LenisCtor = lenisMod?.default ?? null;

      /* No post-processing. Bloom went in and came straight back out: with the
         EffectComposer in the chain every dark tone was lifted — the page
         background measured (56, 61, 71) where the clear colour is (10, 12, 16),
         which is linear 0.04 written as if it were sRGB. These are raw
         ShaderMaterials writing final display values, so any pass that re-encodes
         them is wrong by construction, and the glow was never worth two render
         targets on integrated graphics. The joints are bright enough on their
         own. */

      resize();
      measure();
      sec = sectionAt();
      if (still) paintOnce();
      else wake();
    })();

    // Published for the route effect below: re-measure, then SNAP rather than
    // damp, so a new page's first frame is already correct.
    sync.current = () => {
      measure();
      sec = sectionAt();
      progress = targetProgress();
    };

    return () => {
      cancelled = true;
      sync.current = null;
      sleep();
      for (const f of off) f();
      journey?.dispose();
      renderer?.dispose();
      journey = null;
      renderer = null;
      scene = null;
      camera = null;
      html.classList.remove('solid-hover');
      // `journey-on` is deliberately NOT cleared here. This cleanup also runs
      // when only the MODE changes — crossing between the landing page and the
      // rest — and clearing it faded the canvas to nothing and back for a
      // context that was about to be rebuilt anyway. Only drop() clears it, and
      // drop() means the scene genuinely cannot run.
    };
    // Crossing between the landing page and the rest is the only thing that
    // rebuilds the scene. Inner-page to inner-page keeps the same canvas.
  }, [mode]);

  // A client-side navigation swaps the DOM under a scene that is still running.
  // Two frames later the layout has settled, so the re-measure waits for them —
  // measuring during the swap reads the outgoing page's rects.
  useEffect(() => {
    let a = 0, b = 0;
    a = requestAnimationFrame(() => {
      b = requestAnimationFrame(() => sync.current?.());
    });
    return () => {
      cancelAnimationFrame(a);
      cancelAnimationFrame(b);
    };
  }, [pathname]);

  return <canvas id="journey" ref={ref} aria-hidden="true" />;
}

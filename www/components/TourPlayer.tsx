'use client';

import { useCallback, useEffect, useMemo, useSyncExternalStore } from 'react';
import Image from 'next/image';
import { TOUR_LONG, TOUR_SHORT, type TourStep } from '@/lib/tour';

/**
 * The guided tour, as a page you can walk.
 *
 * The same steps the desktop app runs as an overlay and the terminal UI prints
 * as a screen — `claude_sessions/tour.py` is where they are written and
 * `tools/gen_tour.py` brings them here, so a product with three interfaces
 * still has one explanation of itself.
 *
 * What this surface adds, and the others cannot: the screenshot. A reader who
 * has not installed anything cannot be walked through their own app, so each
 * step that has a published capture shows it.
 *
 * Interactive rather than a list, because thirty-five functions read as a wall.
 * The step is in the URL hash, so a step is linkable and the back button walks
 * the tour backwards — which is what people try first.
 */

const TOURS: Record<string, { label: string; blurb: string; steps: TourStep[] }> = {
  short: {
    label: 'First five minutes',
    blurb: 'What you just installed, ending with a session launched.',
    steps: TOUR_SHORT,
  },
  long: {
    label: 'Every function',
    blurb: 'All of it, each with what it does and what it is for.',
    steps: TOUR_LONG,
  },
};

/** Published captures, by the page or tab a step is about. Only a handful of
 *  screens are shot for the site; a step with no capture shows none rather than
 *  an unrelated one. Sizes are the real intrinsic ones — next/image reserves
 *  the box from them and the page does not reflow as each arrives. */
const SHOTS: Record<string, { src: string; w: number; h: number; alt: string }> = {
  home: {
    src: '/img/gui-dashboard.png',
    w: 1600,
    h: 1000,
    alt: 'The archeus dashboard: quota and burn gauges over live sessions, projects and recent sessions.',
  },
  sessions: {
    src: '/img/gui-sessions.png',
    w: 1600,
    h: 1000,
    alt: 'Every session in a project, with topic, message count and age.',
  },
  memory: {
    src: '/img/gui-memory.png',
    w: 1600,
    h: 1000,
    alt: "A project's memory graph: entities, relations and lessons.",
  },
  usage: {
    src: '/img/gui-usage.png',
    w: 1600,
    h: 1000,
    alt: 'Token spend and rate limits across every account, by day.',
  },
  client: {
    src: '/img/gui-claude-code.png',
    w: 1600,
    h: 1000,
    alt: "What Claude Code records about itself: versions, disk and background agents.",
  },
};

function shotFor(s: TourStep) {
  return SHOTS[s.tab] || SHOTS[s.page];
}

/* The step lives in the URL HASH and nowhere else.
 *
 * Not `useState` plus an effect that reads the hash on mount: that is a
 * setState inside an effect body, which `react-hooks/set-state-in-effect`
 * rejects, and it is right to — the hash is an external store, and React has
 * `useSyncExternalStore` for exactly this shape. One source of truth means a
 * link into the middle of the tour opens there, the two never drift, and there
 * is no server/client mismatch to reconcile by hand.
 *
 * `location.hash = …`, deliberately, rather than `replaceState`: it fires
 * `hashchange` (so the store updates) AND it pushes a history entry, so the
 * back button walks the tour backwards, which is the first thing people try.
 */
function subscribe(onChange: () => void) {
  window.addEventListener('hashchange', onChange);
  return () => window.removeEventListener('hashchange', onChange);
}

/** '' on the server: the hash is never sent, so there is nothing to render from
 *  and step one is the honest prerender. */
const serverHash = () => '';

function parseHash(hash: string): { which: 'short' | 'long'; i: number } {
  const m = /^#(short|long)(?:-(\d+))?$/.exec(hash || '');
  if (!m) return { which: 'short', i: 0 };
  const which = m[1] as 'short' | 'long';
  const max = TOURS[which].steps.length - 1;
  return { which, i: Math.max(0, Math.min(max, Number(m[2] || 1) - 1)) };
}

export function TourPlayer() {
  const hash = useSyncExternalStore(subscribe, () => window.location.hash, serverHash);
  const { which, i } = parseHash(hash);
  const steps = TOURS[which].steps;
  const step = steps[Math.min(i, steps.length - 1)];

  const goto = useCallback((w: 'short' | 'long', n: number) => {
    const at = Math.max(0, Math.min(TOURS[w].steps.length - 1, n));
    window.location.hash = `#${w}-${at + 1}`;
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      if (t && /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName)) return;
      if (e.key === 'ArrowRight') goto(which, i + 1);
      else if (e.key === 'ArrowLeft') goto(which, i - 1);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [which, i, goto]);

  const shot = useMemo(() => shotFor(step), [step]);
  const pct = ((i + 1) / steps.length) * 100;

  return (
    <div className="mx-auto max-w-4xl px-5">
      <div className="flex flex-wrap gap-2" role="tablist" aria-label="Which tour">
        {(Object.keys(TOURS) as ('short' | 'long')[]).map((k) => (
          <button
            key={k}
            role="tab"
            aria-selected={which === k}
            onClick={() => goto(k, 0)}
            className={`rounded-full border px-4 py-1.5 text-sm transition-colors ${
              which === k
                ? 'border-cyan bg-cyan/10 text-text'
                : 'border-line text-dim hover:text-text'
            }`}
          >
            {TOURS[k].label}
            <span className="ml-2 font-mono text-[0.7rem] text-dim">{TOURS[k].steps.length}</span>
          </button>
        ))}
      </div>
      <p className="mt-3 text-sm text-dim">{TOURS[which].blurb}</p>

      <div className="panel-solid mt-6 overflow-hidden">
        <div className="h-[3px] w-full bg-line">
          <div
            className="h-full bg-cyan transition-[width] duration-300"
            style={{ width: `${pct}%` }}
          />
        </div>
        <div className="p-6 sm:p-8">
          <p className="font-mono text-[0.7rem] uppercase tracking-[0.16em] text-dim">
            Step {i + 1} of {steps.length}
            {step.key ? (
              <span className="ml-3 rounded border border-line px-1.5 py-0.5 text-cyan">
                {step.key}
              </span>
            ) : null}
          </p>
          <h2 className="mt-3 text-2xl font-semibold tracking-tight text-text">{step.title}</h2>
          <p className="mt-3 text-pretty leading-[1.7] text-dim">{step.body}</p>
          {step.docsUrl ? (
            <a
              className="mt-4 inline-block text-sm text-cyan hover:underline"
              href={step.docsUrl}
              target="_blank"
              rel="noopener"
            >
              Read more in the manual →
            </a>
          ) : null}

          {shot ? (
            <figure className="mt-6 overflow-hidden rounded-lg border border-line">
              <Image
                src={shot.src}
                width={shot.w}
                height={shot.h}
                alt={shot.alt}
                sizes="(min-width: 936px) 856px, 100vw"
              />
            </figure>
          ) : null}

          <div className="mt-7 flex items-center gap-3">
            <button
              onClick={() => goto(which, i - 1)}
              disabled={i === 0}
              className="rounded-md border border-line px-4 py-2 text-sm text-dim transition-colors hover:text-text disabled:opacity-40"
            >
              Back
            </button>
            <button
              onClick={() => goto(which, i + 1)}
              disabled={i + 1 >= steps.length}
              className="rounded-md border border-cyan bg-cyan/10 px-4 py-2 text-sm text-text transition-colors hover:bg-cyan/20 disabled:opacity-40"
            >
              Next
            </button>
            <span className="ml-auto hidden font-mono text-[0.7rem] text-dim sm:inline">
              ← → to move
            </span>
          </div>
        </div>
      </div>

      {/* Every step, listed, because a tour is also a reference and a reader who
          knows what they are looking for should not have to click through
          thirty-five cards to reach it. */}
      <ol className="mt-8 grid gap-1.5 sm:grid-cols-2">
        {steps.map((s, n) => (
          <li key={s.id}>
            <button
              onClick={() => goto(which, n)}
              className={`w-full rounded-md border px-3 py-2 text-left text-sm transition-colors ${
                n === i ? 'border-cyan text-text' : 'border-line text-dim hover:text-text'
              }`}
            >
              <span className="mr-2 font-mono text-[0.7rem] text-dim">{n + 1}</span>
              {s.title}
            </button>
          </li>
        ))}
      </ol>
    </div>
  );
}

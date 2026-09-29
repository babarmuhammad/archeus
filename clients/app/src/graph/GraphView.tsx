// The spatial view (p18-design-gate A4-A13): a mode of World and of every
// Relations tab, never a destination. It draws what one graph read returned —
// Core's recorded relationships around a focus — and nothing else: no write,
// no inferred edge, no second read of its own beyond that one path. Below
// 600 px it is not drawn at all and the Relations list is the view (A12).
import { useEffect, useMemo, useRef, useState } from 'react';
import { announce } from '../a11y/announce';
import { store, useRead } from '../data/cache';
import { objectHref } from '../nav/destinations';
import { present } from '../state/present';
import { Empty, Fresh, Loadable, StateBadge } from '../components/ui';
import { Inspector } from '../surfaces/Inspector';
import { lookOf } from './encoding';
import { fit, layout, type Point } from './layout';
import { browserHost, Loop } from './loop';
import { allExpanded, around, build, inFocus, keyOf, lifted, liveExecutions, path as tracePathKeys, pulseEdge, search, toggle, visible, type GraphData, type Model, type Ref } from './model';
import { draw, type Camera, type DrawStats } from './render';
import { selected as selectedEdge, start, step, type Walk } from './keys';
import { edgeWords } from './relations';
import { mirrorRows } from './mirror';
import { MIN_WIDTH, useWide } from './wide';

const PULSE_MS = 240;
const PULSE_EVERY_MS = 2000;

/** Where a graph view lives (A4): every step is a URL. */
export function graphHref(focus: Ref | null, modules?: string): string {
  if (!focus) return '#/world/graph';
  const base = `#/world/graph/${focus.kind}/${encodeURIComponent(focus.id)}`;
  return modules === undefined ? base : `${base}/modules${modules ? '/' + encodeURIComponent(modules) : ''}`;
}

export function graphPath(focus: Ref | null, modules?: string): string {
  if (modules !== undefined && focus) return `/v1/repositories/${focus.id}/graph${modules ? '?focus=' + encodeURIComponent(modules) : ''}`;
  return focus ? `/v1/world/graph?focus=${focus.kind}:${encodeURIComponent(focus.id)}` : '/v1/world/graph';
}

export function GraphView({ focus, modules }: { focus: Ref | null; modules?: string }) {
  if (!useWide()) return <Narrow focus={focus} modules={modules} />;
  return <Spatial key={graphPath(focus, modules)} focus={focus} modules={modules} />;
}

/** Below 600 px (A12): the list equivalent, never a shrunken graph. */
function Narrow({ focus, modules }: { focus: Ref | null; modules?: string }) {
  const note = <p className="unavailable" data-graph-narrow="">The spatial view needs a window at least {MIN_WIDTH} px wide; the relationships are listed instead.</p>;
  if (focus && modules === undefined && !['project', 'workspace'].includes(focus.kind))
    return (
      <div className="view">
        {note}
        <Inspector kind={focus.kind} id={focus.id} tab="relations" onTab={(t) => location.assign(objectHref(focus.kind, focus.id, t))} />
      </div>
    );
  return (
    <div className="view">
      {note}
      <a href={focus ? (focus.kind === 'project' ? `#/world/${focus.id}` : objectHref(focus.kind, focus.id)) : '#/world'}>Open the list</a>
    </div>
  );
}

// positions per focus, kept for the tab's life: Back returns to the same picture
const POSITIONS = new Map<string, Map<string, Point>>();

function Spatial({ focus, modules }: { focus: Ref | null; modules?: string }) {
  const path = graphPath(focus, modules);
  const snap = useRead<GraphData & { available?: boolean; reason?: string; stale?: boolean; revision?: string; inspected_at?: string }>(path);
  return (
    <div className="view graph-view">
      <h1 tabIndex={-1}>{modules !== undefined ? 'Modules' : focus ? 'Relationships' : 'World'} <span className="graph-mode">graph</span></h1>
      <Fresh snap={snap} />
      <Loadable snap={snap} what="the graph">
        {(d) =>
          !d.nodes?.length && d.available !== false ? (
            <Empty>{focus ? 'Nothing recorded around this object yet.' : 'No project yet. Create one from World.'}</Empty>
          ) : d.available === false ? (
            <Empty>{d.reason === 'not_inspected' ? 'This repository has not been inspected yet.' : 'The stored inspection of this repository is missing.'}</Empty>
          ) : (
            <Canvas data={d} focus={focus} modules={modules} path={path} stale={d.stale ? `From revision ${d.revision ?? '?'}, which is no longer the repository's head.` : null} />
          )
        }
      </Loadable>
    </div>
  );
}

interface Pulse {
  start: number;
}

function Canvas({ data, focus, modules, path, stale }: { data: GraphData; focus: Ref | null; modules?: string; path: string; stale: string | null }) {
  const model = useMemo(() => build(data), [data]);
  const root = focus ? keyOf(modules !== undefined ? { kind: 'path', id: modules } : focus) : null;
  const rootKey = root && model.byKey.has(root) ? root : model.nodes[0] ? keyOf(model.nodes[0]) : '';
  const [expanded, setExpanded] = useState<Set<string>>(() => allExpanded(model));
  const [only, setOnly] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [walk, setWalk] = useState<Walk>(() => start(rootKey));
  const [pathEnds, setPathEnds] = useState<string[]>([]);
  const [pinned] = useState<Set<string>>(() => new Set());
  const canvas = useRef<HTMLCanvasElement>(null);
  const searchBox = useRef<HTMLInputElement>(null);
  const cam = useRef<{ from: Camera; to: Camera; start: number } | null>(null);
  const size = useRef({ w: 800, h: 520 });
  const sized = useRef(false);
  const fitRef = useRef<(animate?: boolean) => void>(() => undefined);
  const pulses = useRef(new Map<string, Pulse>());
  const lastPulse = useRef(new Map<string, number>());
  const statsRef = useRef<DrawStats | null>(null);
  const [loopState, setLoopState] = useState<'running' | 'parked'>('parked');
  const [lod, setLod] = useState<'full' | 'dots'>('full');
  const [pulseCount, setPulseCount] = useState(0);
  const loopRef = useRef<Loop | null>(null);
  const sceneRef = useRef<() => void>(() => undefined);

  // a refresh keeps what the user opened; new parents open too
  useEffect(() => setExpanded((e) => new Set([...e, ...[...allExpanded(model)].filter((k) => !e.has(k) && !seen.current.has(k))])), [model]);
  const seen = useRef(new Set(allExpanded(model)));
  useEffect(() => {
    for (const k of allExpanded(model)) seen.current.add(k);
  }, [model]);

  const vis = useMemo(() => visible(model, expanded), [model, expanded]);
  const keys = useMemo(() => model.nodes.map(keyOf).filter((k) => vis.has(k)), [model, vis]);
  const drawn = useMemo(() => lifted(model, vis, (e) => !only || chipOf(e) === only), [model, vis, only]);
  const pos = useMemo(() => {
    const kept = POSITIONS.get(path) ?? new Map<string, Point>();
    const parentVis = (k: string) => {
      let p = model.parentOf.get(k) ?? null;
      while (p && !vis.has(p)) p = model.parentOf.get(p) ?? null;
      return p;
    };
    const out = layout({
      keys,
      parentOf: parentVis,
      radius: (k) => (lookOf(model.byKey.get(k)!.kind).shape === 'cluster' ? 26 : 8),
      links: drawn.map((d) => [d.a, d.b] as [string, string]),
      seed: path,
      prev: kept,
      pinned,
    });
    const merged = new Map([...kept, ...out]);
    POSITIONS.set(path, merged);
    return merged;
  }, [model, keys, drawn, path, pinned, vis]);

  const live = useMemo(() => {
    const execs = liveExecutions(model, (m, s) => present(m, s).cls === 'active');
    const out = new Set<string>();
    for (const x of execs) {
      const d = pulseEdge(drawn, x);
      if (d) out.add(d.id);
    }
    return out;
  }, [model, drawn]);

  const sel = selectedEdge(walk, drawn);
  const context = useMemo(() => inFocus(drawn, walk.at || null), [drawn, walk.at]);
  const traced = useMemo(() => {
    if (pathEnds.length !== 2) return null;
    const p = tracePathKeys(model, pathEnds[0], pathEnds[1]);
    if (!p) return new Set<string>();
    const ids = new Set<string>();
    for (let i = 0; i + 1 < p.length; i++) {
      const d = drawn.find((x) => (x.a === p[i] && x.b === p[i + 1]) || (x.b === p[i] && x.a === p[i + 1]));
      if (d) ids.add(d.id);
    }
    return ids;
  }, [pathEnds, model, drawn]);

  // the camera: fit once per focus, kept afterwards
  const camera = (now: number): Camera => {
    const c = cam.current;
    if (!c) return { x: 0, y: 0, k: 1 };
    const t = Math.min(1, (now - c.start) / PULSE_MS);
    return { x: c.from.x + (c.to.x - c.from.x) * t, y: c.from.y + (c.to.y - c.from.y) * t, k: c.from.k + (c.to.k - c.from.k) * t };
  };
  const moveTo = (to: Camera, animate: boolean) => {
    const now = performance.now();
    const from = cam.current ? camera(now) : to;
    cam.current = { from, to, start: now };
    if (!animate || !loopRef.current?.animate(PULSE_MS)) cam.current = { from: to, to, start: 0 };
    loopRef.current?.request();
  };
  const fitAll = (animate = true) => moveTo(fit(keys.map((k) => pos.get(k)!).filter(Boolean), size.current.w, size.current.h), animate);
  fitRef.current = fitAll;

  sceneRef.current = () => {
    const c = canvas.current;
    const ctx = c?.getContext('2d');
    if (!c || !ctx) return;
    const now = performance.now();
    const styles = getComputedStyle(c);
    const pulse = new Map<string, number>();
    for (const [id, p] of pulses.current) {
      const t = (now - p.start) / PULSE_MS;
      if (t >= 1) pulses.current.delete(id);
      else pulse.set(id, t);
    }
    const stats = draw(ctx, {
      model,
      keys,
      drawn,
      pos,
      cam: camera(now),
      focus: walk.at || null,
      selected: sel?.edge.id ?? null,
      context,
      path: traced,
      live,
      liveStatic: document.documentElement.dataset.motion === 'reduced' || matchMedia('(prefers-reduced-motion: reduce)').matches,
      pulse,
      colour: (v) => styles.getPropertyValue(v).trim() || '#888',
      width: size.current.w,
      height: size.current.h,
      dpr: Math.min(2, devicePixelRatio || 1),
    });
    statsRef.current = stats;
    c.dataset.zoom = camera(now).k.toFixed(3); // what a test (or a bug report) reads
    c.dataset.frames = String(loopRef.current?.frames ?? 0);
    if (stats.lod !== lod) setLod(stats.lod);
  };

  // the one loop: made once, parked by its host's conditions
  useEffect(() => {
    let loop: Loop | null = null;
    const [host, off] = browserHost(() => loop?.wake());
    loop = new Loop(host, () => sceneRef.current(), setLoopState);
    loopRef.current = loop;
    const c = canvas.current!;
    const lost = () => loop!.setLost(true);
    const restored = () => loop!.setLost(false);
    c.addEventListener('contextlost', lost);
    c.addEventListener('contextrestored', restored);
    const ro = new ResizeObserver(([e]) => {
      const w = Math.max(1, Math.round(e.contentRect.width));
      const h = Math.max(1, Math.round(e.contentRect.height));
      const dpr = Math.min(2, devicePixelRatio || 1);
      const first = !sized.current;
      size.current = { w, h };
      sized.current = true;
      c.width = w * dpr;
      c.height = h * dpr;
      if (first) fitRef.current(false); // the first fit needs the real size
      loop!.request();
    });
    ro.observe(c);
    const stopFrames = store.onFrame((f) => {
      const subject = (f.data as { subject?: Ref } | undefined)?.subject;
      if (!subject || subject.kind !== 'execution' || !f.event.startsWith('execution.')) return;
      const d = pulseEdge(drawnRef.current, keyOf(subject));
      if (!d || !liveRef.current.has(d.id)) return;
      const now = performance.now();
      if (now - (lastPulse.current.get(d.id) ?? -Infinity) < PULSE_EVERY_MS) return;
      if (!loop!.animate(PULSE_MS)) return; // reduced motion: the thick static edge says it instead
      lastPulse.current.set(d.id, now);
      pulses.current.set(d.id, { start: now });
      setPulseCount((n) => n + 1);
    });
    return () => {
      stopFrames();
      ro.disconnect();
      c.removeEventListener('contextlost', lost);
      c.removeEventListener('contextrestored', restored);
      off();
      loop!.dispose();
    };
  }, []);
  const drawnRef = useRef(drawn);
  const liveRef = useRef(live);
  drawnRef.current = drawn;
  liveRef.current = live;

  // one redraw when what is drawn changed — never on a render the loop's own
  // state caused (that would be a loop by another name)
  useEffect(() => {
    if (!cam.current) fitAll(false);
    loopRef.current?.request();
  }, [model, keys, drawn, pos, walk, context, traced, live]);

  // what the keyboard (or a click) says
  useEffect(() => {
    const n = model.byKey.get(walk.at);
    if (!n) return;
    const s = sel ? ` Selected: ${sel.edge.edges[0] ? edgeWords(sel.edge.edges[0].field, keyOf(sel.edge.edges[0].from) === walk.at, sel.edge.edges[0].rel) : ''} → ${model.byKey.get(sel.other)?.label ?? ''}, ${walk.sel + 1} of ${around(drawn, walk.at).length}.` : '';
    announce(`${lookOf(n.kind, n.endpoint, n.type).noun} ${n.label}${n.machine && n.state ? ', ' + present(n.machine, n.state).label : ''}, ${around(drawn, walk.at).length} relationships.${s}`);
  }, [walk.at, walk.sel]);

  const open = (k: string) => {
    const n = model.byKey.get(k);
    if (!n) return;
    if (n.kind === 'more') return location.assign(graphHref(n.parent ?? null));
    if (modules !== undefined) {
      if (n.kind === 'directory' && !n.endpoint) location.assign(graphHref(focus, n.id));
      return;
    }
    if (n.endpoint) return;
    location.assign(n.kind === 'project' && !focus ? graphHref({ kind: 'project', id: n.id }) : objectHref(n.kind, n.id));
  };
  const drill = (k: string) => {
    const n = model.byKey.get(k);
    if (!n || n.endpoint || modules !== undefined) return open(k);
    location.assign(graphHref({ kind: n.kind, id: n.id }));
  };

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === 'f') {
      e.preventDefault();
      return drill(walk.at);
    }
    const { walk: w, command } = step(walk, e.key, drawn, rootKey);
    if (w !== walk || command) e.preventDefault();
    if (w !== walk) setWalk(w);
    const c = camera(performance.now());
    switch (command) {
      case 'open':
        return open(w.at);
      case 'toggle':
        if (model.children.has(w.at)) setExpanded((x) => toggle(x, w.at));
        return;
      case 'zoom-in':
        return moveTo({ ...c, k: Math.min(4, c.k * 1.25) }, true);
      case 'zoom-out':
        return moveTo({ ...c, k: Math.max(0.1, c.k / 1.25) }, true);
      case 'fit':
        return fitAll();
      case 'search':
        return searchBox.current?.focus();
      case 'clear':
        setQuery('');
        setPathEnds([]);
        return;
      case 'path-mark':
        return setPathEnds((p) => (p.length >= 2 ? [w.at] : [...p, w.at]));
    }
  };

  const onSearch = (q: string) => {
    setQuery(q);
    const { hits, expanded: next } = search(model, expanded, q);
    setExpanded(next);
    if (hits[0]) setWalk({ at: hits[0], sel: 0, trail: [...walk.trail, walk.at] });
  };

  // pointer: click selects, double-click opens, drag pans, wheel zooms
  const drag = useRef<{ x: number; y: number; moved: boolean } | null>(null);
  const hit = (e: React.PointerEvent | React.MouseEvent): string | null => {
    const r = canvas.current!.getBoundingClientRect();
    const c = camera(performance.now());
    const wx = (e.clientX - r.left - size.current.w / 2) / c.k + c.x;
    const wy = (e.clientY - r.top - size.current.h / 2) / c.k + c.y;
    let best: string | null = null;
    let bd = (14 / c.k) ** 2;
    for (const k of keys) {
      const p = pos.get(k);
      if (!p) continue;
      const d = (p.x - wx) ** 2 + (p.y - wy) ** 2;
      if (d < bd) {
        bd = d;
        best = k;
      }
    }
    return best;
  };

  const rels = useMemo(() => [...new Set(model.edges.filter((e) => !e.structural).map(chipOf))].sort(), [model]);
  const hiddenCount = (data.hidden ?? []).reduce((a, h) => a + h.count, 0);

  return (
    <div className="graph" data-graph-focus={focus ? `${focus.kind}:${focus.id}` : 'workspace'} data-graph-nodes={keys.length} data-graph-lod={lod} data-graph-loop={loopState} data-graph-at={walk.at} data-graph-live={live.size} data-graph-pulses={pulseCount}>
      <div className="graph-bar" role="toolbar" aria-label="Graph">
        <a className="chip" href={modules !== undefined ? objectHref('repository', focus!.id) : focus ? (focus.kind === 'project' ? `#/world/${focus.id}` : objectHref(focus.kind, focus.id, 'relations')) : '#/world'}>
          List
        </a>
        {focus?.kind === 'repository' && modules === undefined ? (
          <a className="chip" href={graphHref(focus, '')}>
            Modules
          </a>
        ) : null}
        <input ref={searchBox} type="search" className="graph-search" aria-label="Find in this view" placeholder="Find in this view" value={query} onChange={(e) => onSearch(e.target.value)} onKeyDown={(e) => e.key === 'Escape' && canvas.current?.focus()} />
        <button type="button" className="chip" onClick={() => moveTo({ ...camera(performance.now()), k: Math.min(4, camera(performance.now()).k * 1.25) }, true)} aria-label="Zoom in">
          +
        </button>
        <button type="button" className="chip" onClick={() => moveTo({ ...camera(performance.now()), k: Math.max(0.1, camera(performance.now()).k / 1.25) }, true)} aria-label="Zoom out">
          −
        </button>
        <button type="button" className="chip" onClick={() => fitAll()}>
          Fit
        </button>
        {rels.length > 1 ? (
          <span className="chips" role="group" aria-label="Show one relationship">
            <button type="button" className={only ? 'chip' : 'chip on'} aria-pressed={!only} onClick={() => setOnly(null)}>
              All
            </button>
            {rels.map((r) => (
              <button key={r} type="button" className={only === r ? 'chip on' : 'chip'} aria-pressed={only === r} onClick={() => setOnly(r)}>
                {r}
              </button>
            ))}
          </span>
        ) : null}
      </div>
      {stale ? <p className="stale-line">{stale}</p> : null}
      {data.truncated ? <p className="status-line">{hiddenCount} more not shown — open a “+N” node or focus closer.</p> : null}
      <canvas
        ref={canvas}
        className="graph-canvas"
        tabIndex={0}
        role="application"
        aria-roledescription="relationship graph"
        aria-label={`Relationships around ${model.byKey.get(rootKey)?.label ?? 'the world'}. Arrow keys walk the edges, Enter opens, F focuses the graph there.`}
        aria-describedby="graph-keys"
        onKeyDown={onKey}
        onPointerDown={(e) => {
          drag.current = { x: e.clientX, y: e.clientY, moved: false };
          canvas.current?.setPointerCapture(e.pointerId);
        }}
        onPointerMove={(e) => {
          const d = drag.current;
          if (!d) return;
          const dx = e.clientX - d.x;
          const dy = e.clientY - d.y;
          if (Math.abs(dx) + Math.abs(dy) < 3 && !d.moved) return;
          d.moved = true;
          d.x = e.clientX;
          d.y = e.clientY;
          const c = camera(performance.now());
          moveTo({ x: c.x - dx / c.k, y: c.y - dy / c.k, k: c.k }, false);
        }}
        onPointerUp={(e) => {
          const d = drag.current;
          drag.current = null;
          if (d?.moved) return;
          const k = hit(e);
          if (k) setWalk({ at: k, sel: 0, trail: walk.at && walk.at !== k ? [...walk.trail, walk.at] : walk.trail });
        }}
        onDoubleClick={(e) => {
          const k = hit(e);
          if (k) open(k);
        }}
        onWheel={(e) => {
          const c = camera(performance.now());
          moveTo({ ...c, k: Math.max(0.1, Math.min(4, c.k * (e.deltaY < 0 ? 1.1 : 1 / 1.1))) }, false);
        }}
      />
      <p id="graph-keys" className="caption">
        ↑ ↓ choose a relationship · → follow it · ← back · Enter open · F focus here · Space expand or collapse · + − zoom · 0 fit · / find · P mark a path end
      </p>
      <Mirror model={model} />
    </div>
  );
}

/** A relationship chip filters by the words the list says (two fields can
 * share them: "of mission"), read at the holder. */
const chipOf = (e: { field: string; rel?: string | null }) => edgeWords(e.field, true, e.rel);

/** The accessible form (A11): the same loaded graph as a list — every node the
 * read returned (the collapsed ones and the "+N" stubs too), each with its
 * edges in words. Not a second data source: built from the same object. */
export function Mirror({ model }: { model: Model }) {
  return (
    <section className="sr" aria-label="Relationships in this view, as a list" data-graph-mirror="">
      <ul>
        {mirrorRows(model).map(({ k, n, look, edges }) => {
          return (
            <li key={k} data-key={k}>
              {n.endpoint ? (
                <span>
                  {look.noun} {n.label}
                  {n.missing ? ' (not found)' : ''}
                </span>
              ) : (
                <a href={n.kind === 'directory' || n.kind === 'file' ? undefined : objectHref(n.kind, n.id)}>
                  {look.noun} {n.label}
                </a>
              )}
              {n.machine && n.state ? <StateBadge machine={n.machine} state={n.state} /> : null}
              {edges.length ? (
                <ul>
                  {edges.map((e) => (
                    <li key={e.id}>{e.text}</li>
                  ))}
                </ul>
              ) : null}
            </li>
          );
        })}
      </ul>
    </section>
  );
}

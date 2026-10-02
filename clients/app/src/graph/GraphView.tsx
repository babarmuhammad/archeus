// The spatial view (p18-design-gate A4-A13): a mode of World and of every
// Relations tab, never a destination. It draws what one graph read returned —
// Core's recorded relationships around a focus — and nothing else: no write,
// no inferred edge, no second read of its own beyond that one path. Below
// 600 px it is not drawn at all and the Relations list is the view (A12).
import { useEffect, useMemo, useRef, useState } from 'react';
import { announce } from '../a11y/announce';
import { store, useRead } from '../data/cache';
import { objectHref } from '../nav/destinations';
import { MOTIONS } from '../state/motion';
import { present } from '../state/present';
import { timeline } from '../state/timeline';
import { Empty, Fresh, Loadable, StateBadge } from '../components/ui';
import { Inspector } from '../surfaces/Inspector';
import { lookOf } from './encoding';
import { fit, layout, pinchCamera, type Point } from './layout';
import { browserHost, Loop } from './loop';
import { allExpanded, around, build, depthAlphas, haloed, hops, IMPACT_HOPS, impactOf, inFocus, keyOf, lift as liftKey, lifted, liveExecutions, markerFor, markerTarget, path as tracePathKeys, pathStatus, pulseEdge, pulseFor, search, toggle, visible, type GraphData, type Model, type Ref } from './model';
import { drawSwatch, frame, type Camera, type DrawStats, type Layer } from './render';
import { applyLegend, legendRows, type LegendRow } from './legend';
import { doubleTap, selected as selectedEdge, start, step, type Walk } from './keys';
import { edgeWords } from './relations';
import { mirrorRows, type Around } from './mirror';
import { MIN_WIDTH, useWide } from './wide';

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
  const note = <p className="hint" data-graph-narrow="">The spatial view needs a window at least {MIN_WIDTH} px wide; the relationships are listed instead.</p>;
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
// pins per focus (A13): view state, in memory, this tab only — never stored,
// never sent, not in the URL
const PINS = new Map<string, Set<string>>();

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

const CAMERA_MS = MOTIONS['camera-settle'].max_ms;

function Canvas({ data, focus, modules, path, stale }: { data: GraphData; focus: Ref | null; modules?: string; path: string; stale: string | null }) {
  const model = useMemo(() => build(data), [data]);
  const root = focus ? keyOf(modules !== undefined ? { kind: 'path', id: modules } : focus) : null;
  const rootKey = root && model.byKey.has(root) ? root : model.nodes[0] ? keyOf(model.nodes[0]) : '';
  const [expanded, setExpanded] = useState<Set<string>>(() => allExpanded(model));
  const [only, setOnly] = useState<string | null>(null);
  const [hidden, setHidden] = useState<Set<string>>(() => new Set()); // legend rows unticked: view state, never sent
  const [query, setQuery] = useState('');
  const [walk, setWalk] = useState<Walk>(() => start(rootKey));
  const [pathEnds, setPathEnds] = useState<string[]>([]);
  // "What does this affect?" (ADR-0025 §3): view state, about the focused node
  const [impact, setImpact] = useState(false);
  const [impactHops, setImpactHops] = useState<number>(IMPACT_HOPS.default);
  const [pinned, setPinnedState] = useState<Set<string>>(() => PINS.get(path) ?? new Set());
  const pin = (k: string) => {
    if (!k) return;
    const next = toggle(pinned, k);
    PINS.set(path, next);
    setPinnedState(next);
  };
  const canvas = useRef<HTMLCanvasElement>(null);
  const searchBox = useRef<HTMLInputElement>(null);
  const cam = useRef<{ from: Camera; to: Camera; start: number } | null>(null);
  const size = useRef({ w: 800, h: 520 });
  const sized = useRef(false);
  const fitRef = useRef<(animate?: boolean) => void>(() => undefined);
  const lastPulse = useRef(new Map<string, number>());
  const statsRef = useRef<DrawStats | null>(null);
  const layer = useRef<Layer | null>(null);
  const layerDraws = useRef(0);
  const [loopState, setLoopState] = useState<'running' | 'parked'>('parked');
  const [lod, setLod] = useState<'full' | 'dots'>('full');
  const [pulseCount, setPulseCount] = useState(0);
  const [markerCount, setMarkerCount] = useState(0);
  const loopRef = useRef<Loop | null>(null);
  const sceneRef = useRef<() => void>(() => undefined);

  // a refresh keeps what the user opened; new parents open too
  useEffect(() => setExpanded((e) => new Set([...e, ...[...allExpanded(model)].filter((k) => !e.has(k) && !seen.current.has(k))])), [model]);
  const seen = useRef(new Set(allExpanded(model)));
  useEffect(() => {
    for (const k of allExpanded(model)) seen.current.add(k);
  }, [model]);

  const shown = useMemo(() => applyLegend(model, visible(model, expanded), hidden), [model, expanded, hidden]);
  const vis = shown.vis;
  const keys = useMemo(() => model.nodes.map(keyOf).filter((k) => vis.has(k)), [model, vis]);
  const drawn = useMemo(() => lifted(model, vis, (e) => shown.keep(e) && (!only || chipOf(e) === only)), [model, vis, shown, only]);
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

  // the activity halo: Core's state in the read this view holds, nothing else
  const halo = useMemo(() => haloed(model, (m, s) => present(m, s).cls === 'active'), [model]);
  const halos = useMemo(() => keys.filter((k) => halo.has(k)).length, [keys, halo]);

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
  const pathState = useMemo(() => pathStatus(model, pathEnds), [model, pathEnds]);
  const affected = useMemo(() => (impact && vis.has(walk.at) ? impactOf(model, vis, drawn, walk.at, impactHops) : null), [impact, impactHops, model, vis, drawn, walk.at]);
  const lit = useMemo(() => (affected ? new Set([...(traced ?? []), ...affected.edges]) : traced), [traced, affected]);
  // depth by graph distance from the focus (ADR-0025 §4); in the impact view, what it affects
  const depth = useMemo(() => depthAlphas(drawn, keys, walk.at || null, opaque(), affected?.shown), [drawn, keys, walk.at, affected]);
  const steps = useMemo(() => (walk.at && vis.has(walk.at) ? hops(drawn, walk.at) : null), [drawn, walk.at, vis]);

  // the camera: fit once per focus, kept afterwards
  const camera = (now: number): Camera => {
    const c = cam.current;
    if (!c) return { x: 0, y: 0, k: 1 };
    const t = Math.min(1, (now - c.start) / CAMERA_MS);
    return { x: c.from.x + (c.to.x - c.from.x) * t, y: c.from.y + (c.to.y - c.from.y) * t, k: c.from.k + (c.to.k - c.from.k) * t };
  };
  const moveTo = (to: Camera, animate: boolean) => {
    const now = performance.now();
    const from = cam.current ? camera(now) : to;
    cam.current = { from, to, start: now };
    if (!animate || !loopRef.current?.animate('camera-settle')) cam.current = { from: to, to, start: 0 };
    loopRef.current?.request();
  };
  const fitAll = (animate = true) => moveTo(fit(keys.map((k) => pos.get(k)!).filter(Boolean), size.current.w, size.current.h), animate);
  fitRef.current = fitAll;

  sceneRef.current = () => {
    const c = canvas.current;
    const ctx = c?.getContext('2d');
    const l = layer.current;
    if (!c || !ctx || !l) return;
    const now = performance.now();
    const styles = getComputedStyle(c);
    // renderAt(now): the pulses are the timeline's, read at this frame's time
    const pulse = timeline.progress('execution-pulse', now);
    const marker = timeline.progress('travelling-marker', now);
    const stats = frame(ctx, l, {
      model,
      keys,
      drawn,
      pos,
      cam: camera(now),
      focus: walk.at || null,
      root: rootKey || null,
      hover: hoverRef.current,
      selected: sel?.edge.id ?? null,
      context,
      depth,
      path: lit,
      live,
      liveStatic: reducedMotion(),
      halo,
      opaque: opaque(),
      pulse,
      marker,
      colour: (v) => styles.getPropertyValue(v).trim() || '#888',
      width: size.current.w,
      height: size.current.h,
      dpr: Math.min(2, devicePixelRatio || 1),
      degraded: !!loopRef.current?.degraded,
    });
    statsRef.current = stats;
    if (stats.layer) layerDraws.current++;
    c.dataset.layers = String(layerDraws.current); // static-layer redraws (A10 proxy 5)
    const cm = camera(now);
    c.dataset.zoom = cm.k.toFixed(3); // what a test (or a bug report) reads
    const at = pos.get(walk.at);
    c.dataset.at = at ? `${Math.round((at.x - cm.x) * cm.k + size.current.w / 2)},${Math.round((at.y - cm.y) * cm.k + size.current.h / 2)}` : '';
    c.dataset.hover = hoverRef.current ?? '';
    c.dataset.frames = String(loopRef.current?.frames ?? 0);
    c.dataset.pulses = String(pulse.size); // running now, this frame
    c.dataset.markers = String(marker.size); // travelling now, this frame (the cap's reading)
    if (stats.layer) c.dataset.hulls = String(stats.hulls); // project volumes in the static layer
    if (stats.lod !== lod) setLod(stats.lod);
  };

  // the one loop: made once, parked by its host's conditions
  useEffect(() => {
    let loop: Loop | null = null;
    const [host, off] = browserHost(() => loop?.wake());
    loop = new Loop(host, () => sceneRef.current(), setLoopState);
    loopRef.current = loop;
    const c = canvas.current!;
    layer.current = { ctx: document.createElement('canvas').getContext('2d')!, sig: null };
    const lost = () => loop!.setLost(true);
    const restored = () => {
      layer.current!.sig = null; // what the layer held went with the context
      loop!.setLost(false);
    };
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
      layer.current!.ctx.canvas.width = c.width;
      layer.current!.ctx.canvas.height = c.height;
      layer.current!.sig = null;
      if (first) fitRef.current(false); // the first fit needs the real size
      loop!.request();
    });
    ro.observe(c);
    const stopFrames = store.onFrame((f) => {
      const now = performance.now();
      // the travelling marker: the frame's execution to its task, along Core's
      // recorded edge. Under reduced motion the timeline still records the
      // event (it never plays later) and the 2 px static live edge says it.
      const t = markerFor(f, modelRef.current, visRef.current, drawnRef.current, liveRef.current);
      if (t && timeline.start('travelling-marker', markerTarget(t, f.id), f.id, now, host.reduced()) && loop!.animate('travelling-marker'))
        setMarkerCount((n) => n + 1);
      const d = pulseFor(f, drawnRef.current, liveRef.current, lastPulse.current, now, host.reduced());
      // reduced motion: the thick static edge says it instead. The timeline
      // refuses an event it has presented (a reconnect or a second tab re-sending
      // it): a pulse is never replayed, and one running keeps its own start.
      if (!d || !timeline.start('execution-pulse', d.id, f.id, now, host.reduced()) || !loop!.animate('execution-pulse')) return;
      lastPulse.current.set(d.id, now);
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
  const modelRef = useRef(model);
  const visRef = useRef(vis);
  drawnRef.current = drawn;
  liveRef.current = live;
  modelRef.current = model;
  visRef.current = vis;

  // one redraw when what is drawn changed — never on a render the loop's own
  // state caused (that would be a loop by another name)
  useEffect(() => {
    if (!cam.current) fitAll(false);
    loopRef.current?.request();
  }, [model, keys, drawn, pos, walk, context, lit, depth, live, halo]);

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

  // expand all / collapse all (rulebook §12): the same expanded set Space
  // toggles one entry of — view state only; the keyboard moves to what stands
  // for the focused node when a collapse hides it
  const expandAll = () => setExpanded(allExpanded(model));
  const collapseAll = () => {
    const none = new Set<string>();
    setExpanded(none);
    const at = liftKey(model, applyLegend(model, visible(model, none), hidden).vis, walk.at);
    if (at && at !== walk.at) setWalk({ at, sel: 0, trail: [] });
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
      case 'expand-all':
        return expandAll();
      case 'collapse-all':
        return collapseAll();
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
        setImpact(false);
        return;
      case 'path-mark':
        return setPathEnds((p) => (p.length >= 2 ? [w.at] : [...p, w.at]));
      case 'pin':
        return pin(w.at);
    }
  };

  const onSearch = (q: string) => {
    setQuery(q);
    const { hits, expanded: next } = search(model, expanded, q);
    setExpanded(next);
    if (hits[0]) {
      setWalk({ at: hits[0], sel: 0, trail: [...walk.trail, walk.at] });
      setCentreOn({ k: hits[0] });
    }
  };
  // A13: the match is centred, at the current zoom, once the layout has placed it
  const [centreOn, setCentreOn] = useState<{ k: string } | null>(null);
  useEffect(() => {
    const p = centreOn && pos.get(centreOn.k);
    if (!p) return;
    setCentreOn(null);
    moveTo({ x: p.x, y: p.y, k: camera(performance.now()).k }, true);
  }, [centreOn, pos]);

  // pointer: click (or tap) selects, double-click (or double-tap) opens, drag
  // pans, wheel or a two-finger pinch zooms, a mouse hover labels (A10, A12)
  const drag = useRef<{ x: number; y: number; moved: boolean } | null>(null);
  const hoverRef = useRef<string | null>(null);
  const touches = useRef(new Map<number, { x: number; y: number }>());
  const pinch = useRef<{ d0: number; cam: Camera } | null>(null);
  const lastTap = useRef<{ k: string; t: number } | null>(null);
  const lastPointer = useRef('mouse');
  const setHover = (k: string | null) => {
    if (hoverRef.current === k) return;
    hoverRef.current = k;
    loopRef.current?.request();
  };
  const fingers = () => {
    const [a, b] = [...touches.current.values()];
    const r = canvas.current!.getBoundingClientRect();
    return { d: Math.hypot(a.x - b.x, a.y - b.y), mid: { x: (a.x + b.x) / 2 - r.left - size.current.w / 2, y: (a.y + b.y) / 2 - r.top - size.current.h / 2 } };
  };
  const lift = (e: React.PointerEvent) => {
    const pinched = !!pinch.current;
    if (e.pointerType === 'touch') {
      touches.current.delete(e.pointerId);
      if (touches.current.size < 2) pinch.current = null;
    }
    const d = drag.current;
    drag.current = null;
    return pinched || !d || d.moved;
  };
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
    <div className="graph" data-graph-focus={focus ? `${focus.kind}:${focus.id}` : 'workspace'} data-graph-nodes={keys.length} data-graph-lod={lod} data-graph-loop={loopState} data-graph-at={walk.at} data-graph-live={live.size} data-graph-halos={halos} data-graph-pulses={pulseCount} data-graph-markers={markerCount} data-graph-pinned={pinned.size} data-graph-expanded={expanded.size} data-graph-collapsible={model.children.size} data-graph-hidden={hidden.size} data-graph-impact={affected ? affected.steps.size : ''} data-graph-selected={sel?.edge.id ?? ''} data-graph-path={pathState ?? ''}>
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
        <button type="button" className="chip" aria-pressed={pinned.has(walk.at)} onClick={() => pin(walk.at)}>
          {pinned.has(walk.at) ? 'Unpin' : 'Pin'}
        </button>
        <button type="button" className="chip" disabled={!model.children.size} onClick={expandAll}>
          Expand all
        </button>
        <button type="button" className="chip" disabled={!model.children.size} onClick={collapseAll}>
          Collapse all
        </button>
        <button type="button" className={impact ? 'chip on' : 'chip'} aria-pressed={impact} disabled={!vis.has(walk.at)} onClick={() => setImpact((x) => !x)}>
          What does this affect?
        </button>
        {impact ? (
          <select className="chip" aria-label="How many steps" value={impactHops} onChange={(e) => setImpactHops(Number(e.target.value))}>
            {Array.from({ length: IMPACT_HOPS.max }, (_, i) => i + 1).map((h) => (
              <option key={h} value={h}>
                within {h} {h === 1 ? 'step' : 'steps'}
              </option>
            ))}
          </select>
        ) : null}
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
      {affected ? (
        <p className="status-line" role="status" data-graph-impact-line="">
          {model.byKey.get(walk.at)?.label ?? 'This'} affects {affected.steps.size ? `${affected.steps.size} ${affected.steps.size === 1 ? 'object' : 'objects'}` : 'nothing recorded'} within {affected.hops} {affected.hops === 1 ? 'step' : 'steps'} — over recorded relations in this loaded view only.
        </p>
      ) : null}
      {pathState === 'none' ? (
        <p className="status-line" role="status">
          No path within the loaded neighbourhood.
        </p>
      ) : null}
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
          lastPointer.current = e.pointerType;
          if (e.pointerType === 'touch') {
            touches.current.set(e.pointerId, { x: e.clientX, y: e.clientY });
            if (touches.current.size === 2) {
              pinch.current = { d0: fingers().d, cam: camera(performance.now()) };
              drag.current = null; // two fingers zoom; they do not pan or select
              return;
            }
          }
          drag.current = { x: e.clientX, y: e.clientY, moved: false };
          canvas.current?.setPointerCapture(e.pointerId);
        }}
        onPointerMove={(e) => {
          if (e.pointerType === 'touch' && touches.current.has(e.pointerId)) {
            touches.current.set(e.pointerId, { x: e.clientX, y: e.clientY });
            const p = pinch.current;
            if (p && touches.current.size === 2) {
              const { d, mid } = fingers();
              return moveTo(pinchCamera(p.cam, p.d0, d, mid), false);
            }
          }
          const d = drag.current;
          if (!d) return e.pointerType === 'mouse' ? setHover(hit(e)) : undefined;
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
          if (lift(e)) return;
          const k = hit(e);
          if (!k) return;
          if (e.pointerType === 'touch') {
            const t = performance.now();
            const second = doubleTap(lastTap.current, k, t);
            lastTap.current = second ? null : { k, t };
            if (second) return open(k); // A12: double-tap opens
          }
          setWalk({ at: k, sel: 0, trail: walk.at && walk.at !== k ? [...walk.trail, walk.at] : walk.trail });
        }}
        onPointerCancel={(e) => void lift(e)}
        onPointerLeave={(e) => e.pointerType === 'mouse' && setHover(null)}
        onDoubleClick={(e) => {
          if (lastPointer.current === 'touch') return; // a double-tap opened it already
          const k = hit(e);
          if (k) open(k);
        }}
        onWheel={(e) => {
          const c = camera(performance.now());
          moveTo({ ...c, k: Math.max(0.1, Math.min(4, c.k * (e.deltaY < 0 ? 1.1 : 1 / 1.1))) }, false);
        }}
      />
      <p id="graph-keys" className="caption">
        ↑ ↓ choose a relationship · → follow it · ← back · Enter open · F focus here · Space expand or collapse · E expand all · C collapse all · + − zoom · 0 fit · / find · P mark a path end · . pin or unpin · Esc clear
      </p>
      <Legend model={model} hidden={hidden} onToggle={(k) => setHidden((h) => toggle(h, k))} />
      <Mirror model={model} pinned={pinned} halo={halo} around={walk.at && steps ? { focus: walk.at, steps, affected: affected?.steps } : undefined} />
    </div>
  );
}

const GROUPS = [
  ['kind', 'Shapes'],
  ['tier', 'Lines'],
  ['live', 'Live work'],
] as const;
const SWATCH = { w: 28, h: 24 };
const reducedMotion = () => document.documentElement.dataset.motion === 'reduced' || matchMedia('(prefers-reduced-motion: reduce)').matches;
const opaque = () => matchMedia('(forced-colors: active)').matches || matchMedia('(prefers-reduced-transparency: reduce)').matches;

/** The legend (ADR-0025 §2): what each shape and line in this picture means,
 * and the two marks of live work, as a list. Each shape and line row is a real
 * checkbox that hides what it names from the drawing. */
function Legend({ model, hidden, onToggle }: { model: Model; hidden: ReadonlySet<string>; onToggle: (key: string) => void }) {
  const reduced = reducedMotion();
  const solid = opaque();
  const rows = legendRows(model, reduced);
  return (
    <details className="graph-legend" open data-graph-legend="">
      <summary>Legend</summary>
      <p className="hint">Untick a shape or a line to hide it from the drawing.</p>
      {GROUPS.map(([g, title]) => {
        const rs = rows.filter((r) => r.group === g);
        return rs.length ? (
          <ul key={g} className="legend-rows" aria-label={title}>
            {rs.map((r) => (
              <li key={r.key} data-legend={r.key}>
                {r.group === 'live' ? (
                  <>
                    <Swatch row={r} reduced={reduced} solid={solid} /> {r.word}
                  </>
                ) : (
                  <label>
                    <input type="checkbox" checked={!hidden.has(r.key)} onChange={() => onToggle(r.key)} /> <Swatch row={r} reduced={reduced} solid={solid} /> {r.word}
                  </label>
                )}
              </li>
            ))}
          </ul>
        ) : null;
      })}
    </details>
  );
}

function Swatch({ row, reduced, solid }: { row: LegendRow; reduced: boolean; solid: boolean }) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const c = ref.current;
    const ctx = c?.getContext('2d');
    if (!c || !ctx) return;
    const dpr = Math.min(2, devicePixelRatio || 1);
    c.width = SWATCH.w * dpr;
    c.height = SWATCH.h * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const styles = getComputedStyle(c);
    drawSwatch(ctx, row, SWATCH.w, SWATCH.h, (v) => styles.getPropertyValue(v).trim() || '#888', solid, reduced);
  }, [row.key, reduced, solid]);
  return <canvas ref={ref} className="legend-swatch" aria-hidden="true" />;
}

/** A relationship chip filters by the words the list says (two fields can
 * share them: "of mission"), read at the holder. */
const chipOf = (e: { field: string; rel?: string | null }) => edgeWords(e.field, true, e.rel);

/** The accessible form (A11): the same loaded graph as a list — every node the
 * read returned (the collapsed ones and the "+N" stubs too), each with its
 * edges in words. Not a second data source: built from the same object. */
export function Mirror({ model, pinned, halo, around }: { model: Model; pinned?: ReadonlySet<string>; halo?: ReadonlySet<string>; around?: Around }) {
  return (
    <section className="sr" aria-label="Relationships in this view, as a list" data-graph-mirror="">
      <ul>
        {mirrorRows(model, pinned, halo, around).map(({ k, n, look, edges, pinned: isPinned, detail, live, notes }) => {
          return (
            <li key={k} data-key={k} data-live={live ? '' : undefined}>
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
              {isPinned ? ' (pinned)' : ''}
              {detail ? ` — ${detail}` : ''}
              {notes.map((x) => ` — ${x}`).join('')}
              {live ? ' — live work now' : ''}
              {n.machine && n.state ? <StateBadge machine={n.machine} state={n.state} /> : null}
              {edges.length ? (
                <ul>
                  {edges.map((e) => (
                    <li key={e.id} data-live={e.live ? '' : undefined}>
                      {e.text}
                    </li>
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

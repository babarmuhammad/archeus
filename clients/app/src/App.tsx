// The V1 client shell (p16-design-gate §4, §13, §16, §17): sign in (a launch
// code on this computer, a pairing code anywhere), then one connection, one
// cache, one navigation table, one inspector. Every state on screen is a state
// Core returned; the stream only says what to read again.
import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from 'react';
import { paths, api, type Attention, type DeviceList, type Status } from './api/generated';
import { authenticate, redeemPairing, sender, takeFragment, CoreError } from './api/transport';
import { HEARTBEAT, LOST, OPENED, RESYNC, UNAUTHENTICATED, subscribe } from './api/stream';
import { announce, limiter } from './a11y/announce';
import { store, useConn, useRead, type Snapshot } from './data/cache';
import { BANNER, canCommand } from './data/connection';
import { send } from './data/core';
import { setSend } from './data/core';
import { staleBy } from './data/invalidation';
import { DESTINATIONS, href, objectHref, parse, phoneTabs, type Route } from './nav/destinations';
import { AttentionView } from './surfaces/Attention';
import { CommandBar } from './surfaces/CommandBar';
import { ControlView, applyMotion } from './surfaces/Control';
import { Inspector } from './surfaces/Inspector';
import { NowView } from './surfaces/Now';
import { PauseAll, WorkView } from './surfaces/Work';
import { ProjectPage, WorldView } from './surfaces/World';
import { GraphView } from './graph/GraphView';
import { reducedMotion } from './graph/loop';
import { ActionButton, Fresh } from './components/ui';
import { Arrival, needsYou, tabTitle } from './state/arrival';
import { MARK, Orbit, favicon, presence, runningMissions, type Presence } from './state/orbit';
import { timeline } from './state/timeline';
import { TOAST_TTL_MS, Toasts, type Ended } from './state/toast';
import { INSPECTOR_MAX, INSPECTOR_MIN, clampWidth, keyWidth, loadWidth, saveWidth } from './state/inspector';
import { DARK } from './state/tokens';

type Boot = { phase: 'starting' } | { phase: 'pair'; code: string } | { phase: 'out' } | { phase: 'in'; token: string } | { phase: 'failed'; why: string };

export default function App() {
  const [boot, setBoot] = useState<Boot>({ phase: 'starting' });
  useEffect(() => {
    applyMotion();
    const f = takeFragment();
    if (f.pair) return setBoot({ phase: 'pair', code: f.pair });
    authenticate(f.launch).then(
      (token) => setBoot(token ? { phase: 'in', token } : { phase: 'out' }),
      (e) => setBoot({ phase: 'failed', why: String(e) }),
    );
  }, []);
  if (boot.phase === 'starting')
    return (
      <main className="notice boot">
        <Mark />
        <p>Connecting to Archeus…</p>
      </main>
    );
  if (boot.phase === 'failed') return <main className="notice">Archeus could not start: {boot.why}</main>;
  if (boot.phase === 'pair') return <PairRedeem code={boot.code} onPaired={(token) => setBoot({ phase: 'in', token })} />;
  if (boot.phase === 'out')
    return (
      <main className="notice">
        <h1>Archeus</h1>
        <p>
          Open Archeus from the desktop app, or run <code>archeus core --open</code> on the computer running it. On another device, pair it from Control → Clients on that computer.
        </p>
      </main>
    );
  return <Shell token={boot.token} />;
}

/** Redeeming a pairing code (P15 §6.1 step 3). */
function PairRedeem({ code, onPaired }: { code: string; onPaired: (t: string) => void }) {
  const [name, setName] = useState('');
  const [pin, setPin] = useState('');
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  return (
    <main className="notice pair-redeem">
      <h1>Pair this client with Archeus</h1>
      <p>The code in the link you opened works once, for two minutes.</p>
      <form
        className="form"
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          setErr(null);
          try {
            onPaired(await redeemPairing(code, name, pin || undefined));
          } catch (x) {
            const c = x instanceof CoreError ? x.code : 'network';
            setErr(
              c === 'invalid_pairing_code'
                ? 'This code is not valid any more. Start a new pairing on the computer running Archeus.'
                : c === 'pairing_locked'
                  ? 'Pairing is locked for a minute after too many wrong codes. Wait, then start a new pairing.'
                  : c === 'invalid_request'
                    ? 'The PIN is 6 to 12 digits.'
                    : 'Archeus could not be reached.',
            );
          } finally {
            setBusy(false);
          }
        }}
      >
        <label>
          Name for this client (optional)
          <input value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <label>
          PIN, 6–12 digits (optional — used to confirm approvals that need step-up)
          <input inputMode="numeric" autoComplete="off" value={pin} onChange={(e) => setPin(e.target.value.replace(/\D/g, ''))} maxLength={12} />
        </label>
        <button type="submit" className="btn primary" disabled={busy}>
          Pair
        </button>
        {err ? <p role="alert" className="err">{err}</p> : null}
      </form>
    </main>
  );
}

function useRoute(): [Route, Route] {
  const [hash, setHash] = useState(location.hash);
  const under = useRef<Route>(parse(location.hash));
  useEffect(() => {
    const f = () => setHash(location.hash);
    addEventListener('hashchange', f);
    return () => removeEventListener('hashchange', f);
  }, []);
  const r = parse(hash);
  if (r.view !== 'object') under.current = r;
  lastUnder = under.current;
  return [r, under.current];
}

function Shell({ token }: { token: string }) {
  const conn = useConn();
  const [route, under] = useRoute();
  const [cmd, setCmd] = useState(false);
  const [iw, setIw] = useState(() => loadWidth(storage()));
  const main = useRef<HTMLElement>(null);
  const aside = useRef<HTMLElement>(null);
  const att = useRead<Attention>(paths.attentionItems());
  const status = useRead<Status>(paths.status());
  const p = presence(canCommand(conn.conn), att.data?.count ?? 0, status.data?.live ?? []);

  // the favicon shows the presence, still (ADR-0027 §2)
  useEffect(() => {
    const l = document.querySelector<HTMLLinkElement>('link[rel="icon"]');
    if (!l) return;
    l.href = favicon(p, DARK);
    l.dataset.presence = p;
  }, [p]);

  // A-08: a rise in Core's count pulses the badge once and is announced; the
  // tab's name carries the count (rulebook §20)
  const count = att.data?.count ?? 0;
  useEffect(() => {
    if (att.data) arrival.read(att.data.count, att.seq);
    document.title = tabTitle(count);
  }, [att.data, att.seq, count]);
  const arrived = useSyncExternalStore(
    (l) => arrival.subscribe(l),
    () => arrival.current(),
  );

  useEffect(() => {
    const s = sender(token, (path, seq) => store.seqs.set(path, seq));
    store.configure(s);
    setSend(s);
    const onLine = () => store.signal('online');
    const offLine = () => store.signal('offline');
    addEventListener('online', onLine);
    addEventListener('offline', offLine);
    const stop = subscribe(token, (f) => {
      if (f.event === UNAUTHENTICATED) store.signal('unauthorized');
      else if (f.event === OPENED) store.signal('stream_open');
      else if (f.event === LOST) store.signal('stream_lost');
      else if (f.event === RESYNC) store.signal('resync');
      else {
        store.signal('frame');
        if (f.event !== HEARTBEAT) {
          store.invalidate(staleBy(f));
          store.frame(f);
        }
      }
    });
    return () => {
      stop();
      removeEventListener('online', onLine);
      removeEventListener('offline', offLine);
    };
  }, [token]);

  useEffect(() => {
    const t = BANNER[conn.conn];
    if (t) announce(t);
  }, [conn.conn]);

  // focus the view's heading on navigation (§17) — not on the first load, where
  // focus starts at the top of the document and the skip link comes first
  const navigated = useRef(false);
  const fromView = useRef(route.view);
  useEffect(() => {
    // closing an inspector opened over the spatial view returns focus to its
    // canvas, which kept its walk (the same node selected; p18 A11)
    const closed = fromView.current === 'object' && route.view !== 'object';
    fromView.current = route.view;
    if (!navigated.current) {
      navigated.current = true;
      return;
    }
    const t = setTimeout(() => {
      const back = closed ? document.querySelector<HTMLElement>('main .graph-canvas') : null;
      const h = back ?? document.querySelector<HTMLElement>(route.view === 'object' ? '.inspector h1' : 'main h1');
      h?.focus({ preventScroll: false });
    }, 0);
    return () => clearTimeout(t);
  }, [route.view, route.view === 'object' ? route.id : '', route.view === 'object' ? '' : (route as { section?: string }).section]);

  const keys = useCallback((e: KeyboardEvent) => {
    const mod = e.ctrlKey || e.metaKey;
    if (mod && e.key.toLowerCase() === 'k') {
      e.preventDefault();
      setCmd(true);
      return;
    }
    if (mod) {
      const d = DESTINATIONS.find((x) => x.key === e.key.toLowerCase());
      if (d) {
        e.preventDefault();
        location.hash = d.id === 'control' ? '#/control/autonomy' : `#/${d.id}`;
      }
    }
    if (e.key === 'Escape' && location.hash.startsWith('#/o/') && !document.querySelector('dialog[open]')) closeInspector();
  }, []);
  useEffect(() => {
    addEventListener('keydown', keys);
    return () => removeEventListener('keydown', keys);
  }, [keys]);

  const banner = BANNER[conn.conn];
  const current = route.view === 'object' ? under.view : route.view;
  const underView = route.view === 'object' ? under : route;
  return (
    <div
      className="shell"
      data-inspector={route.view === 'object' ? '' : undefined}
      data-conn={conn.conn}
      style={iw ? ({ '--inspector-w': `${iw}px` } as React.CSSProperties) : undefined}
    >
      <a className="skip" href="#main" onClick={(e) => (e.preventDefault(), main.current?.focus())}>
        Skip to content
      </a>
      <header className="top">
        <span className="brand">
          <Mark presence={p} />
          Archeus
        </span>
        <OperationsStrip status={status} count={att.data ? count : undefined} />
        {banner ? (
          <p className="banner" data-conn={conn.conn} role="status">
            {banner}
          </p>
        ) : null}
        <button type="button" className="btn secondary cmd-open" onClick={() => setCmd(true)} aria-keyshortcuts="Control+K">
          Go to or tell… <kbd>Ctrl K</kbd>
        </button>
        <a className="menu-control" href="#/control/autonomy">
          Control
        </a>
      </header>
      <nav className="nav" aria-label="Destinations">
        <ul>
          {DESTINATIONS.map((d) => (
            <li key={d.id} data-phone={phoneTabs().includes(d) ? 'tab' : 'menu'}>
              <a href={d.id === 'control' ? '#/control/autonomy' : `#/${d.id}`} aria-current={current === d.id ? 'page' : undefined} title={d.blurb}>
                <Icon id={d.id} />
                <span className="nav-label">{d.label}</span>
                {d.id === 'attention' && count ? (
                  <span key={arrived} className="badge" data-arrival={arrived || undefined} aria-label={needsYou(count)}>
                    {count}
                  </span>
                ) : null}
              </a>
            </li>
          ))}
        </ul>
      </nav>
      <main id="main" ref={main} tabIndex={-1} className="main">
        <View route={underView} />
      </main>
      {route.view === 'object' ? (
        <InspectorResize
          aside={aside}
          width={iw}
          onWidth={(w, keep) => {
            setIw(w);
            if (keep) saveWidth(storage(), w);
          }}
        />
      ) : null}
      {route.view === 'object' ? (
        <aside className="inspector" aria-label="Inspector" ref={aside}>
          <button type="button" className="btn secondary close" onClick={closeInspector}>
            Close <span className="sr">inspector</span>
          </button>
          <Inspector kind={route.kind} id={route.id} tab={route.tab} onTab={(t) => location.replace(`#/o/${route.kind}/${encodeURIComponent(route.id)}/${t}`)} />
        </aside>
      ) : null}
      <CommandBar open={cmd} onClose={() => setCmd(false)} />
      <ToastRegion />
      <div id="live-polite" className="sr" aria-live="polite" />
      <div id="live-assertive" className="sr" aria-live="assertive" />
    </div>
  );
}

function storage(): Storage | null {
  try {
    return localStorage;
  } catch {
    return null;
  }
}

/** The inspector's divider (rulebook §15): a window splitter at its left edge.
 * Drag it, or focus it and use ←/→ (with or without Alt), Home and End; the
 * width stays within 360–560 px and is remembered in this browser. Alt+←/→
 * are not taken anywhere else: they are the browser's Back and Forward. */
function InspectorResize({ aside, width, onWidth }: { aside: React.RefObject<HTMLElement | null>; width: number | null; onWidth: (w: number, keep: boolean) => void }) {
  const [measured, setMeasured] = useState<number>(INSPECTOR_MIN);
  useEffect(() => setMeasured(Math.round(aside.current?.getBoundingClientRect().width ?? INSPECTOR_MIN)), [aside, width]);
  const now = width ?? clampWidth(measured);
  return (
    <div
      className="insp-resize"
      role="separator"
      aria-orientation="vertical"
      aria-label="Inspector width"
      aria-valuemin={INSPECTOR_MIN}
      aria-valuemax={INSPECTOR_MAX}
      aria-valuenow={now}
      tabIndex={0}
      onKeyDown={(e) => {
        const w = keyWidth(now, e.key);
        if (w === null) return;
        e.preventDefault();
        onWidth(w, true);
      }}
      onPointerDown={(e) => e.currentTarget.setPointerCapture(e.pointerId)}
      onPointerMove={(e) => {
        const r = aside.current?.getBoundingClientRect();
        if (r && e.currentTarget.hasPointerCapture(e.pointerId)) onWidth(clampWidth(r.right - e.clientX), false);
      }}
      onPointerUp={(e) => {
        if (!e.currentTarget.hasPointerCapture(e.pointerId)) return;
        e.currentTarget.releasePointerCapture(e.pointerId);
        onWidth(now, true);
      }}
    />
  );
}

/** Closing goes back to the destination the inspector opened over. */
function closeInspector() {
  location.hash = href(lastUnder);
}

let lastUnder: Route = { view: 'now' };

function View({ route }: { route: Route }) {
  if (route.view === 'object') return null;
  switch (route.view) {
    case 'now':
      return <NowView />;
    case 'work':
      return <WorkView project={route.project} />;
    case 'world':
      if (route.graph) return <GraphView focus={route.graph === 'world' ? null : route.graph} modules={route.modules} />;
      return route.project ? <ProjectPage id={route.project} /> : <WorldView />;
    case 'attention':
      return <AttentionView />;
    case 'control':
      return <ControlView section={route.section ?? 'autonomy'} />;
  }
}

const ICONS: Record<string, string> = {
  now: 'M10 3a7 7 0 1 0 0 14 7 7 0 0 0 0-14zm0 3v4l3 2',
  work: 'M4 5h12M4 10h12M4 15h8',
  world: 'M10 3a7 7 0 1 0 0 14 7 7 0 0 0 0-14zM3 10h14M10 3c2 2 3 4.5 3 7s-1 5-3 7c-2-2-3-4.5-3-7s1-5 3-7z',
  attention: 'M10 3l7 7-7 7-7-7z',
  control: 'M5 4v12M10 4v12M15 4v12M3 8h4M8 13h4M13 7h4',
};

function Icon({ id }: { id: string }) {
  return (
    <svg className="icon" viewBox="0 0 20 20" aria-hidden="true" focusable="false">
      <path d={ICONS[id]} fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

// ── the completion toast (rulebook §17, §21 A-13; D-8) ──

/** Whether a row or the inspector of *mission* or its attempt *execution* is
 * on screen now: then the row's own state change says it, and no toast does. */
function onScreen(mission: string, execution: string): boolean {
  const h = location.hash;
  if (h.startsWith(`#/o/mission/${mission}`) || h.startsWith(`#/o/execution/${execution}`)) return true;
  const sel = `[data-mission="${CSS.escape(mission)}"], [data-execution="${CSS.escape(execution)}"]`;
  return [...document.querySelectorAll(sel)].some((el) => {
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.bottom > 0 && r.top < innerHeight;
  });
}

// the page's one toast queue: every frame, whatever page is open
const toasts = new Toasts(timeline, {
  now: () => performance.now(),
  reduced: reducedMotion,
  read: (id) => api.getExecution(send(), id) as Promise<Ended>,
  title: async (id) => {
    await store.fetch(paths.getMission(id));
    const m = store.snapshot(paths.getMission(id)).data as { title?: string } | undefined;
    return m?.title ?? null;
  },
  onScreen,
});
store.onFrame((f) => void toasts.frame(f));

/** One toast at a time, in a status region mounted at boot (so a screen
 * reader hears it); it fades in, stays 4 s — longer while focus is inside
 * it — and fades out. The mission's row changed too: it is never the only
 * signal, and a failure is never toasted. */
function ToastRegion() {
  const t = useSyncExternalStore(
    (l) => toasts.subscribe(l),
    () => toasts.showing(),
  );
  const [leaving, setLeaving] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    setLeaving(false);
    if (!t) return;
    let timer: ReturnType<typeof setTimeout>;
    const up = () => {
      if (box.current?.contains(document.activeElement)) return void (timer = setTimeout(up, TOAST_TTL_MS));
      if (t.still || reducedMotion()) toasts.dismiss(t.seq);
      else setLeaving(true);
    };
    timer = setTimeout(up, TOAST_TTL_MS);
    return () => clearTimeout(timer);
  }, [t]);
  return (
    <div className="toast-region" role="status" ref={box} data-toasts="">
      {t ? (
        <p key={t.seq} className={`toast${leaving ? ' leaving' : ''}`} data-still={t.still || undefined} data-toast={t.seq} onAnimationEnd={() => leaving && toasts.dismiss(t.seq)}>
          Finished: {t.title ? `“${t.title}”` : 'a mission'}, attempt {t.attempt}. <a href={objectHref('mission', t.mission)}>Open it</a>
        </p>
      ) : null}
    </div>
  );
}

// the page's one attention arrival (A-08): whatever page is open
const arrival = new Arrival(timeline, { now: () => performance.now(), reduced: reducedMotion, announce });

// ── the mark, its orbit and the operations strip (ADR-0027, rulebook §6 O-1, §8) ──

// the page's one orbit: every frame, whatever page is open
const orbit = new Orbit(timeline, { now: () => performance.now(), reduced: reducedMotion });
store.onFrame((f) => orbit.frame(f));

const K = MARK.ry / MARK.rx;

/** The mark (monochrome, `currentColor`). Its node is the presence; a turn
 * plays once per batch of activity, keyed by the event it presents. The orbit
 * is a circle squashed into the ellipse, so the node's own group undoes the
 * squash and the turn, and stays round wherever it is on the way. */
function Mark({ presence: p }: { presence?: Presence }) {
  const turn = useSyncExternalStore(
    (l) => orbit.subscribe(l),
    () => orbit.current(),
  );
  const { letter, tilt, cx, cy, rx, at, r } = MARK;
  return (
    <svg className="mark" viewBox="0 0 32 32" aria-hidden="true" focusable="false" data-presence={p ?? 'idle'}>
      <g fill="currentColor">
        {letter.map((d) => (
          <path key={d} d={d} />
        ))}
      </g>
      <g transform={`rotate(${tilt} ${cx} ${cy})`}>
        <ellipse cx={cx} cy={cy} rx={rx} ry={MARK.ry} fill="none" stroke="currentColor" strokeWidth="1.35" opacity="0.55" />
        <g transform={`translate(${cx} ${cy}) scale(1 ${K}) rotate(${at})`}>
          <g key={turn} className={turn ? 'orbit-turn' : undefined} data-orbit={turn || undefined}>
            <g transform={`translate(${rx} 0)`}>
              <g className={turn ? 'orbit-counter' : undefined}>
                <g transform={`rotate(${-at}) scale(1 ${1 / K})`}>
                  <circle className="mark-node" r={r} />
                </g>
              </g>
            </g>
          </g>
        </g>
      </g>
    </svg>
  );
}

const STRIP_SAYS_EVERY_MS = 30_000;

/** O-1: one line on every page — what runs, what needs you, how many clients
 * are connected, how fresh that is, Pause all (and Resume all while Core says
 * it would resume something), and the emergency stop. Each number links
 * to its list. Its words are the orbit's equivalent, said at most once per
 * 30 s and only when they change. */
function OperationsStrip({ status, count }: { status: Snapshot<Status>; count: number | undefined }) {
  const devices = useRead<DeviceList>(paths.listDevices());
  const running = status.data ? runningMissions(status.data.live) : undefined;
  const clients = devices.data?.devices.filter((d) => d.presence.state === 'connected').length;
  const facts = [
    running === undefined ? null : `${running} running`,
    count === undefined ? null : `${count} ${count === 1 ? 'needs' : 'need'} you`,
    clients === undefined ? null : `${clients} ${clients === 1 ? 'client' : 'clients'}`,
  ];
  const sentence = facts.every((f) => f !== null) ? facts.join(' · ') : null;
  const said = useSaid(sentence);
  return (
    <nav className="strip" aria-label="Operations">
      <ul>
        {facts[0] ? (
          <li>
            <a href="#/now" data-strip="running">{facts[0]}</a>
          </li>
        ) : null}
        {facts[1] ? (
          <li>
            <a href="#/attention" data-strip="needs">{facts[1]}</a>
          </li>
        ) : null}
        {facts[2] ? (
          <li>
            <a href="#/control/devices" data-strip="clients">{facts[2]}</a>
          </li>
        ) : null}
        <li className="strip-more">
          <Fresh snap={status} />
        </li>
        <li className="strip-more" data-strip="pause-all">
          <PauseAll status={status} />
        </li>
        <li className="strip-more" data-strip="estop">
          {status.data?.armed === false ? (
            <a href="#/control/about" className="tag blocked">
              Emergency stop engaged
            </a>
          ) : (
            <ActionButton label="Emergency stop" scope="control" kind="danger" confirm="Every running execution is killed now and Archeus refuses new work until you re-arm it. Missions are not lost; they wait." run={(key) => api.estop(send(), { idempotency_key: key })} reread={['/v1']} />
          )}
        </li>
      </ul>
      <span className="sr" role="status" data-strip-said>
        {said}
      </span>
    </nav>
  );
}

/** What the strip's status region says: a change, at most once per 30 s, the
 * latest winning; never the first reading. */
function useSaid(sentence: string | null): string {
  const lim = useRef(limiter(STRIP_SAYS_EVERY_MS));
  const prev = useRef<string | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [said, setSaid] = useState('');
  useEffect(() => () => clearTimeout(timer.current ?? undefined), []);
  useEffect(() => {
    if (sentence === null || sentence === prev.current) return;
    const first = prev.current === null;
    prev.current = sentence;
    if (first) return;
    const t = lim.current.offer(sentence, Date.now());
    if (t !== null) return setSaid(t);
    // the limiter keeps the latest; one timer says it when the 30 s are up
    timer.current ??= setTimeout(() => {
      timer.current = null;
      const f = lim.current.flush(Date.now());
      if (f !== null) setSaid(f);
    }, STRIP_SAYS_EVERY_MS);
  }, [sentence]);
  return said;
}

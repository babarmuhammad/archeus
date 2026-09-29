// The V1 client shell (p16-design-gate §4, §13, §16, §17): sign in (a launch
// code on this computer, a pairing code anywhere), then one connection, one
// cache, one navigation table, one inspector. Every state on screen is a state
// Core returned; the stream only says what to read again.
import { useCallback, useEffect, useRef, useState } from 'react';
import type { Attention } from './api/generated';
import { authenticate, redeemPairing, sender, takeFragment, CoreError } from './api/transport';
import { HEARTBEAT, LOST, OPENED, RESYNC, UNAUTHENTICATED, subscribe } from './api/stream';
import { announce } from './a11y/announce';
import { store, useConn, useRead } from './data/cache';
import { BANNER } from './data/connection';
import { setSend } from './data/core';
import { staleBy } from './data/invalidation';
import { DESTINATIONS, href, parse, phoneTabs, type Route } from './nav/destinations';
import { AttentionView } from './surfaces/Attention';
import { CommandBar } from './surfaces/CommandBar';
import { ControlView, applyMotion } from './surfaces/Control';
import { Inspector } from './surfaces/Inspector';
import { NowView } from './surfaces/Now';
import { WorkView } from './surfaces/Work';
import { ProjectPage, WorldView } from './surfaces/World';
import { GraphView } from './graph/GraphView';

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
  if (boot.phase === 'starting') return <main className="notice">Connecting…</main>;
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
  const main = useRef<HTMLElement>(null);
  const att = useRead<Attention>('/v1/attention');

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
  useEffect(() => {
    if (!navigated.current) {
      navigated.current = true;
      return;
    }
    const t = setTimeout(() => {
      const h = document.querySelector<HTMLElement>(route.view === 'object' ? '.inspector h1' : 'main h1');
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
  const count = att.data?.count ?? 0;
  const current = route.view === 'object' ? under.view : route.view;
  const underView = route.view === 'object' ? under : route;
  return (
    <div className="shell" data-inspector={route.view === 'object' ? '' : undefined} data-conn={conn.conn}>
      <a className="skip" href="#main" onClick={(e) => (e.preventDefault(), main.current?.focus())}>
        Skip to content
      </a>
      <header className="top">
        <span className="brand">Archeus</span>
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
                  <span className="badge" aria-label={`${count} ${count === 1 ? 'thing needs' : 'things need'} you`}>
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
        <aside className="inspector" aria-label="Inspector">
          <button type="button" className="btn secondary close" onClick={closeInspector}>
            Close <span className="sr">inspector</span>
          </button>
          <Inspector kind={route.kind} id={route.id} tab={route.tab} onTab={(t) => location.replace(`#/o/${route.kind}/${encodeURIComponent(route.id)}/${t}`)} />
        </aside>
      ) : null}
      <CommandBar open={cmd} onClose={() => setCmd(false)} />
      <div id="live-polite" className="sr" aria-live="polite" />
      <div id="live-assertive" className="sr" aria-live="assertive" />
    </div>
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

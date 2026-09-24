// The P3.5b SPA: two read-only lists, Now and Work, over GET /v1/missions,
// kept current by the event stream. It is NOT the P16 information
// architecture — no router, no inspector, no commands (the launch device is
// observe-only). Every state shown is the state Core returned.
import { useCallback, useEffect, useRef, useState } from 'react';
import { api, SETTLED, type Mission } from './api/generated';
import { authenticate, sender } from './api/transport';
import { RESYNC, UNAUTHENTICATED, subscribe } from './api/stream';

type View = 'now' | 'work';

const VIEWS: { id: View; label: string; empty: string }[] = [
  { id: 'now', label: 'Now', empty: 'Nothing is in progress.' },
  { id: 'work', label: 'Work', empty: 'No missions yet.' },
];

function useMissions(token: string | null) {
  const [missions, setMissions] = useState<Mission[] | null>(null);
  const busy = useRef(false);
  const again = useRef(false);

  // re-query on notice; notices during a fetch collapse into one more fetch
  const refresh = useCallback(async () => {
    if (!token) return;
    if (busy.current) {
      again.current = true;
      return;
    }
    busy.current = true;
    try {
      do {
        again.current = false;
        setMissions((await api.listMissions(sender(token))).missions);
      } while (again.current);
    } finally {
      busy.current = false;
    }
  }, [token]);
  return { missions, refresh };
}

export default function App() {
  const [token, setToken] = useState<string | null | undefined>(undefined);
  const [stub, setStub] = useState(false);
  const [view, setView] = useState<View>('now');
  const [problem, setProblem] = useState<string | null>(null);
  const { missions, refresh } = useMissions(token ?? null);

  useEffect(() => {
    authenticate().then(setToken, (e) => setProblem(String(e)));
  }, []);

  useEffect(() => {
    if (!token) return;
    api.health(sender(token)).then((h) => setStub(h.core.ports === 'stub'), () => undefined);
    refresh();
    return subscribe(token, (f) => {
      if (f.event === UNAUTHENTICATED) setToken(null);
      else if (f.event === RESYNC || f.event.startsWith('mission.')) refresh();
    });
  }, [token, refresh]);

  if (problem) return <main className="notice">Archeus could not start: {problem}</main>;
  if (token === undefined) return <main className="notice">Connecting…</main>;
  if (token === null) {
    return (
      <main className="notice">
        <h1>Archeus</h1>
        <p>
          Open Archeus from the desktop app, or run <code>archeus core --open</code>.
        </p>
      </main>
    );
  }

  const shown = (missions ?? []).filter((m) => view === 'work' || !SETTLED.includes(m.state));
  const current = VIEWS.find((v) => v.id === view)!;
  return (
    <div className="app">
      <header>
        <h1>Archeus</h1>
        <nav role="tablist" aria-label="Views">
          {VIEWS.map((v) => (
            <button
              key={v.id}
              role="tab"
              aria-selected={view === v.id}
              className={view === v.id ? 'tab on' : 'tab'}
              onClick={() => setView(v.id)}
            >
              {v.label}
            </button>
          ))}
        </nav>
      </header>
      {stub && (
        <p className="banner" role="status">
          walking skeleton: fake harness, stub policy
        </p>
      )}
      <main role="tabpanel" aria-label={current.label}>
        {missions === null ? (
          <p className="empty">Loading…</p>
        ) : shown.length === 0 ? (
          <p className="empty">{current.empty}</p>
        ) : (
          <ul className="missions">
            {shown.map((m) => (
              <li key={m.id} data-mission={m.id}>
                <span className="title">{m.title}</span>
                <span className="state" data-state={m.state}>
                  {m.state}
                </span>
              </li>
            ))}
          </ul>
        )}
      </main>
    </div>
  );
}

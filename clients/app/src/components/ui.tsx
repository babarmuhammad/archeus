// The product components (design system §11), kept few. Every state is glyph +
// label; every disabled control says why; every command re-reads instead of
// assuming its result.
import { useEffect, useId, useRef, useState, type ReactNode } from 'react';
import { CoreError } from '../api/transport';
import { canCommand, freshness, type Freshness } from '../data/connection';
import { action, explain, keyAfter, retryable } from '../data/commands';
import { store, useConn, useRead, type Snapshot } from '../data/cache';
import { badge, resourceLine } from '../state/present';
import type { Sync } from '../api/generated';

/** A state as glyph + label. When the state changes while on screen (never
 * because it first appeared) the glyph plays one 160 ms transform/opacity step
 * (§18.2): motion reports the change, the label carries it. */
export function StateBadge({ machine, state }: { machine: string; state: string }) {
  const b = badge(machine, state);
  const prev = useRef(state);
  const [changes, setChanges] = useState(0);
  useEffect(() => {
    if (prev.current !== state) {
      prev.current = state;
      setChanges((n) => n + 1);
    }
  }, [state]);
  return (
    <span className="state" data-cls={b.cls} data-machine={machine} data-state={state} style={{ color: `var(--${b.role.replace('.', '-')})` }}>
      <span key={changes} className="glyph" aria-hidden="true" data-changed={changes ? '' : undefined}>
        {b.glyph}
      </span>
      <span className="label">{b.label}</span>
    </span>
  );
}

const FRESH_TEXT: Record<Freshness, string | null> = {
  current: null,
  stale: 'updating…',
  reconnecting: 'may be out of date',
  unavailable: 'unavailable',
};

export function useFreshness(snap: Snapshot<unknown>): Freshness {
  const conn = useConn();
  return freshness(conn, { gen: snap.gen, error: snap.error, pending: snap.pending && snap.data !== undefined, hasData: snap.data !== undefined });
}

export function Fresh({ snap }: { snap: Snapshot<unknown> }) {
  const f = useFreshness(snap);
  const [late, setLate] = useState(false);
  useEffect(() => {
    if (f !== 'stale') return setLate(false);
    const t = setTimeout(() => setLate(true), 1000); // only a slow re-read is worth saying
    return () => clearTimeout(t);
  }, [f]);
  const text = f === 'stale' && !late ? null : FRESH_TEXT[f];
  return text ? (
    <span className="fresh" data-fresh={f} role="status">
      {text}
      {snap.seq !== undefined && f !== 'unavailable' ? ` · as of event ${snap.seq}` : ''}
    </span>
  ) : null;
}

/** Loading / unavailable / content, from one read. */
export function Loadable<T>({ snap, children, what }: { snap: Snapshot<T>; children: (d: T) => ReactNode; what: string }) {
  if (snap.data === undefined) {
    if (snap.error)
      return (
        <p className="unavailable" role="alert">
          {what} is unavailable: {explain(snap.error)}
        </p>
      );
    return <p className="loading">Reading {what}…</p>;
  }
  return <>{children(snap.data)}</>;
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="empty">{children}</p>;
}

// ── who this client is (P15 §4): its scopes decide what to offer; Core decides ──

export function useMe() {
  const s = useRead<Sync>('/v1/sync');
  const me = s.data?.client;
  return {
    me,
    can: (scope: string) => !!me?.scopes.includes(scope),
    local: me?.origin === 'local',
  };
}

/** A command button. It is offered only for an action the row allows; it is
 * disabled, with the reason, when this client lacks the scope or the
 * connection is not live. Core still judges every press. */
export function ActionButton({
  label,
  scope,
  run,
  reread = [],
  disabled,
  kind = 'secondary',
  confirm,
  onDone,
}: {
  label: string;
  scope: 'observe' | 'control' | 'approve' | 'admin';
  run: (key: string) => Promise<unknown>;
  reread?: string[];
  disabled?: string | null;
  kind?: 'primary' | 'secondary' | 'danger';
  confirm?: string;
  onDone?: (out: unknown) => void;
}) {
  const conn = useConn();
  const { can } = useMe();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const key = useRef<string>(action(run).key);
  const dialog = useRef<HTMLDialogElement>(null);
  const errId = useId();
  const why = !can(scope)
    ? `This client does not hold the “${scope}” scope.`
    : !canCommand(conn.conn)
      ? 'Not connected — nothing is sent while reconnecting.'
      : disabled ?? null;

  async function go() {
    setBusy(true);
    setErr(null);
    let outcome: 'ok' | 'refused' | 'network' = 'ok';
    try {
      let out: unknown;
      try {
        out = await run(key.current);
      } catch (e) {
        if (e instanceof CoreError && retryable(e)) out = await run(key.current); // once, same key
        else throw e;
      }
      onDone?.(out);
    } catch (e) {
      const ce = e instanceof CoreError ? e : new CoreError(0, 'network', {});
      outcome = ce.code === 'network' ? 'network' : 'refused';
      setErr(explain(ce));
    } finally {
      key.current = keyAfter(key.current, outcome);
      setBusy(false);
      // never assume the result: read again what the command may have changed
      for (const p of reread) store.invalidate((x) => x === p || x.startsWith(p + '/') || x.startsWith(p + '?'));
    }
  }

  return (
    <span className="action">
      <button
        type="button"
        className={`btn ${kind}`}
        disabled={!!why || busy}
        aria-disabled={!!why || busy}
        title={why ?? undefined}
        aria-describedby={err ? errId : undefined}
        onClick={() => (confirm ? dialog.current?.showModal() : void go())}
      >
        {busy ? `${label}…` : label}
      </button>
      {why ? <span className="why">{why}</span> : null}
      {err ? (
        <span className="err" id={errId} role="alert">
          {err}
        </span>
      ) : null}
      {confirm ? (
        <dialog ref={dialog} className="confirm" aria-labelledby={errId + 'h'}>
          <h2 id={errId + 'h'}>{label}</h2>
          <p>{confirm}</p>
          <div className="row">
            <button type="button" className="btn secondary" onClick={() => dialog.current?.close()} autoFocus>
              Cancel
            </button>
            <button
              type="button"
              className={`btn ${kind === 'danger' ? 'danger' : 'primary'}`}
              onClick={() => {
                dialog.current?.close();
                void go();
              }}
            >
              {label}
            </button>
          </div>
        </dialog>
      ) : null}
    </span>
  );
}

// ── tabs: roving tabindex, ←/→/Home/End (Ship Notes' keyboard pattern, §22) ──

export function Tabs({
  tabs,
  current,
  label,
  onSelect,
}: {
  tabs: { id: string; label: string }[];
  current: string;
  label: string;
  onSelect: (id: string) => void;
}) {
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  const idx = Math.max(0, tabs.findIndex((t) => t.id === current));
  function key(e: React.KeyboardEvent) {
    const n = tabs.length;
    const to = { ArrowRight: (idx + 1) % n, ArrowLeft: (idx - 1 + n) % n, Home: 0, End: n - 1 }[e.key];
    if (to === undefined) return;
    e.preventDefault();
    onSelect(tabs[to].id);
    refs.current[to]?.focus();
  }
  return (
    <div role="tablist" aria-label={label} className="tabs" onKeyDown={key}>
      {tabs.map((t, i) => (
        <button
          key={t.id}
          ref={(el) => {
            refs.current[i] = el;
          }}
          role="tab"
          type="button"
          id={`tab-${t.id}`}
          aria-selected={i === idx}
          aria-controls={`panel-${t.id}`}
          tabIndex={i === idx ? 0 : -1}
          className={i === idx ? 'tab on' : 'tab'}
          onClick={() => onSelect(t.id)}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}

export function KV({ rows }: { rows: [string, ReactNode][] }) {
  return (
    <dl className="kv">
      {rows.map(([k, v]) => (
        <div key={k}>
          <dt>{k}</dt>
          <dd>{v ?? '—'}</dd>
        </div>
      ))}
    </dl>
  );
}

/** Harness, model and account: three fields, never one (§6.4). */
export function Resources({ r }: { r: Parameters<typeof resourceLine>[0] }) {
  return (
    <dl className="resources">
      {resourceLine(r).map((f) => (
        <div key={f.key} data-field={f.key}>
          <dt>{f.label}</dt>
          <dd className="mono">{f.value}</dd>
        </div>
      ))}
    </dl>
  );
}

const NAMED: Record<string, { path: (id: string) => string; name: (r: Record<string, unknown>) => unknown }> = {
  mission: { path: (id) => `/v1/missions/${id}`, name: (r) => r.title },
  project: { path: (id) => `/v1/projects/${id}`, name: (r) => r.name },
  knowledge_item: { path: (id) => `/v1/knowledge/${id}`, name: (r) => r.title },
  session: { path: (id) => `/v1/sessions/${id}`, name: (r) => `${String(r.harness_id)} ${String(r.mode)} session` },
};

/** An object named as a person would: its title when it has one (read from
 * its own row), else its kind and a short id. */
export function RefLabel({ kind, id }: { kind: string; id: string }) {
  const n = NAMED[kind];
  const s = useRead<Record<string, unknown>>(n ? n.path(id) : null);
  const name = n && s.data ? n.name(s.data) : null;
  return (
    <span className="ref">
      <span className="ref-kind">{kind.replace('_', ' ')}</span> {name ? String(name) : <span className="mono">{id.slice(0, 12)}…</span>}
    </span>
  );
}

export function Section({ title, children, actions, id }: { title: string; children: ReactNode; actions?: ReactNode; id?: string }) {
  const h = useId();
  return (
    <section className="section" aria-labelledby={h} id={id}>
      <header>
        <h2 id={h}>{title}</h2>
        {actions ? <div className="actions">{actions}</div> : null}
      </header>
      {children}
    </section>
  );
}

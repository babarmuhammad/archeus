// The product components (design system §11), kept few. Every state is glyph +
// label; every disabled control says why; every command re-reads instead of
// assuming its result.
import { useEffect, useId, useMemo, useRef, useState, useSyncExternalStore, type ReactNode } from 'react';
import { CoreError } from '../api/transport';
import { canCommand, freshness, type Freshness } from '../data/connection';
import { action, explain, keyAfter, retryable } from '../data/commands';
import { store, useConn, useRead, type Snapshot } from '../data/cache';
import { badge, inline, mentions, resourceLine, type Outcome } from '../state/present';
import { objectHref } from '../nav/destinations';
import { paths, api, type AccountList, type Digest, type Sync } from '../api/generated';
import { send } from '../data/core';
import { framesSlow, reducedMotion } from '../graph/loop';
import { RowPulses } from '../state/rowpulse';
import { timeline } from '../state/timeline';

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

// the page's row pulses: every frame, whatever page is open; a row on screen
// is what makes one draw
const rowPulses = new RowPulses(timeline, {
  now: () => performance.now(),
  reduced: reducedMotion,
  degraded: framesSlow,
  read: (id) => api.getExecution(send(), id),
});
store.onFrame((f) => void rowPulses.frame(f));

/** A mission row's pulse (rulebook §21 A-02): a span that plays the row-pulse
 * keyframes once, keyed by the event it presents — and only for a pulse that
 * began while this row was on screen, so a remount replays nothing. */
export function RowPulse({ mission }: { mission: string }) {
  const [since] = useState(() => rowPulses.seq(mission));
  useEffect(() => rowPulses.show(mission), [mission]);
  const seq = useSyncExternalStore(
    (l) => rowPulses.subscribe(l),
    () => rowPulses.seq(mission),
  );
  return seq > since ? <span key={seq} className="row-pulse" data-pulse={seq} aria-hidden="true" /> : null;
}

/** T2 (ADR-0026 §1): whether a row's object is in the digest — changed since
 * the user last looked. The digest is the only source; dismissing it clears
 * every rule at once. */
export function useChanged(): (kind: string, id: string) => boolean {
  const d = useRead<Digest>(paths.digest());
  const groups = d.data?.groups;
  const keys = useMemo(() => new Set((groups ?? []).map((g) => `${g.ref.kind}:${g.ref.id}`)), [groups]);
  return (kind, id) => keys.has(`${kind}:${id}`);
}

/** The left edge of a row belongs to the thread: a row that can carry the
 * rule says so, and a changed one carries it. */
export const thread = (changed: boolean) => ({ 'data-thread': changed ? 'changed' : '' });

/** The rule in words: it is never the only carrier. */
export function Changed({ on }: { on: boolean }) {
  return on ? <span className="sr"> changed since you looked</span> : null;
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

/** Loading (rulebook §21 A-12, Appendix B): static skeleton rows in the shape
 * of a list — no shimmer, nothing moves — and "Reading X…" for a screen
 * reader, the only words while it waits. */
export function Skeleton({ what, rows = 3 }: { what: string; rows?: number }) {
  return (
    <div className="skeleton" role="status" data-skeleton="">
      <span className="sr">Reading {what}…</span>
      {Array.from({ length: rows }, (_, i) => (
        <span key={i} className="sk-row" aria-hidden="true" />
      ))}
    </div>
  );
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
    return <Skeleton what={what} />;
  }
  return <>{children(snap.data)}</>;
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="empty">{children}</p>;
}

// ── who this client is (P15 §4): its scopes decide what to offer; Core decides ──

export function useMe() {
  const s = useRead<Sync>(paths.sync());
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
  report,
}: {
  label: string;
  scope: 'observe' | 'control' | 'approve' | 'admin';
  run: (key: string) => Promise<unknown>;
  reread?: string[];
  disabled?: string | null;
  kind?: 'primary' | 'secondary' | 'danger';
  confirm?: string;
  onDone?: (out: unknown) => void;
  /** the caller says the outcome itself (P20 F7); the button then shows no error of its own */
  report?: (o: Outcome) => void;
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
      report?.({ ok: true, out });
    } catch (e) {
      const ce = e instanceof CoreError ? e : new CoreError(0, 'network', {});
      outcome = ce.code === 'network' ? 'network' : 'refused';
      if (report) report({ ok: false, kind: outcome === 'network' ? 'network' : ce.status >= 500 ? 'failed' : 'refused', why: explain(ce) });
      else setErr(explain(ce));
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

/** Harness, model and account: three fields, never one (§6.4). The account
 * is named by its label; its id is the owning object's Details. */
export function Resources({ r }: { r: Parameters<typeof resourceLine>[0] }) {
  return (
    <dl className="resources">
      {resourceLine(r).map((f) => (
        <div key={f.key} data-field={f.key}>
          <dt>{f.label}</dt>
          <dd className="mono">{f.key === 'account' && f.value !== '—' ? <AccountName id={f.value} /> : f.value}</dd>
        </div>
      ))}
    </dl>
  );
}

/** An account as the user named it, read from the accounts Core holds. */
export function AccountName({ id }: { id: string }) {
  const s = useRead<AccountList>(paths.listAccounts());
  const a = s.data?.accounts.find((x) => x.id === id);
  return <>{a ? a.label : s.data ? 'an account not registered here' : '…'}</>;
}

/** A sentence Core wrote, with every object it names by id shown as that
 * object, linked — the id itself is in that object's Details. */
export function Prose({ text }: { text: unknown }) {
  if (text === null || text === undefined || text === '') return null;
  if (typeof text !== 'string') return <>{inline(text)}</>; // a presented field is untyped (Record<string, unknown>)
  return (
    <>
      {mentions(text).map((p, i) =>
        typeof p === 'string' ? (
          p
        ) : (
          <a key={i} href={objectHref(p.kind, p.id)}>
            {p.kind === 'account' ? <AccountName id={p.id} /> : <RefLabel kind={p.kind} id={p.id} />}
          </a>
        ),
      )}
    </>
  );
}

type Scalar = string | number | boolean | null | undefined;

/** Identifiers behind an explicit disclosure (rulebook §15; R9's Details,
 * the minimum R1 needs): closed by default, so the default view carries none;
 * each row says what the identifier names. Scalars only — a JSON value cannot
 * reach it. */
export function Details({ rows }: { rows: [string, Scalar | Scalar[]][] }) {
  const shown = rows
    .map(([k, v]) => [k, Array.isArray(v) ? v.filter((x) => x !== null && x !== undefined && x !== '').join(', ') : v] as const)
    .filter(([, v]) => v !== null && v !== undefined && v !== '');
  if (!shown.length) return null;
  return (
    <details className="details" data-details="">
      <summary>Details</summary>
      <dl className="kv">
        {shown.map(([k, v]) => (
          <div key={k}>
            <dt>{k}</dt>
            <dd className="mono">{String(v)}</dd>
          </div>
        ))}
      </dl>
    </details>
  );
}

const NAMED: Record<string, { path: (id: string) => string; name: (r: Record<string, unknown>) => unknown }> = {
  mission: { path: (id) => paths.getMission(id), name: (r) => r.title },
  project: { path: (id) => paths.getProject(id), name: (r) => r.name },
  knowledge_item: { path: (id) => paths.getKnowledge(id), name: (r) => r.title },
  session: { path: (id) => paths.getSession(id), name: (r) => `${String(r.harness_id)} ${String(r.mode)} session` },
  execution: { path: (id) => paths.getExecution(id), name: (r) => `attempt ${String(r.attempt)}` },
  plan: { path: (id) => paths.getPlan(id), name: (r) => `v${String(r.plan_version)}` },
  verification: { path: (id) => paths.getVerification(id), name: (r) => r.verifier },
  route_decision: { path: (id) => paths.getRouteDecision(id), name: (r) => r.purpose ?? 'of a task' },
  policy_decision: { path: (id) => paths.getPolicyDecision(id), name: (r) => r.stage },
};

/** RefLabel's words as text, read from the object's own row: what an
 * announcement says. */
export async function refName(kind: string, id: string): Promise<string> {
  const n = NAMED[kind];
  const word = kind.replace('_', ' ');
  if (!n) return word;
  await store.fetch(n.path(id));
  const d = store.snapshot(n.path(id)).data as Record<string, unknown> | undefined;
  const name = d ? n.name(d) : null;
  return name ? `${word} ${String(name)}` : word;
}

/** An object named as a person would: its title when it has one (read from
 * its own row), else its kind alone — its id is in its own Details. */
export function RefLabel({ kind, id }: { kind: string; id: string }) {
  const n = NAMED[kind];
  const s = useRead<Record<string, unknown>>(n ? n.path(id) : null);
  const name = n && s.data ? n.name(s.data) : null;
  return (
    <span className="ref">
      <span className="ref-kind">{kind.replace('_', ' ')}</span>
      {name ? ` ${String(name)}` : null}
    </span>
  );
}

export function Section({ title, children, actions, id, changed }: { title: string; children: ReactNode; actions?: ReactNode; id?: string; changed?: boolean }) {
  const h = useId();
  return (
    <section className="section" aria-labelledby={h} id={id} {...(changed === undefined ? {} : thread(changed))}>
      <header>
        <h2 id={h}>
          {title}
          {changed !== undefined ? <Changed on={changed} /> : null}
        </h2>
        {actions ? <div className="actions">{actions}</div> : null}
      </header>
      {children}
    </section>
  );
}

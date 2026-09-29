// The command bar (Ctrl/⌘+K, p16-design-gate §4.1): jump to a destination or
// a loaded object, or tell Archeus something — the text goes to the primary
// conversation, where Core's grammar and intent pipeline decide what it means.
// The client parses no verb (§5, §19).
import { useEffect, useRef, useState } from 'react';
import { api, type MissionList, type ProjectList } from '../api/generated';
import { store } from '../data/cache';
import { CoreError } from '../api/transport';
import { explain } from '../data/commands';
import { canCommand } from '../data/connection';
import { send } from '../data/core';
import { DESTINATIONS, href, objectHref } from '../nav/destinations';

export function CommandBar({ open, onClose }: { open: boolean; onClose: () => void }) {
  const dlg = useRef<HTMLDialogElement>(null);
  const [q, setQ] = useState('');
  const [msg, setMsg] = useState<string | null>(null);
  useEffect(() => {
    if (open && !dlg.current?.open) dlg.current?.showModal();
    if (!open && dlg.current?.open) dlg.current.close();
  }, [open]);
  const missions = (store.snapshot('/v1/missions').data as MissionList | undefined)?.missions ?? [];
  const projects = (store.snapshot('/v1/projects').data as ProjectList | undefined)?.projects ?? [];
  const needle = q.trim().toLowerCase();
  const hits = [
    ...DESTINATIONS.map((d) => ({ label: `Go to ${d.label}`, to: href({ view: d.id }) })),
    ...missions.map((m) => ({ label: `Mission: ${m.title}`, to: objectHref('mission', m.id) })),
    ...projects.map((p) => ({ label: `Project: ${p.name}`, to: href({ view: 'world', project: p.id }) })),
  ]
    .filter((h) => !needle || h.label.toLowerCase().includes(needle))
    .slice(0, 8);
  const live = canCommand(store.conn.conn);
  async function tell() {
    try {
      await api.postMessage(send(), 'primary', { text: q, idempotency_key: crypto.randomUUID() });
      setMsg('Sent to Archeus — its reply appears on Now.');
      setQ('');
      store.invalidate((p) => p.startsWith('/v1/conversations/'));
    } catch (e) {
      setMsg(explain(e instanceof CoreError ? e : { status: 0, code: 'network', detail: {} }));
    }
  }
  return (
    <dialog ref={dlg} className="command" aria-label="Command bar" onClose={onClose}>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (hits[0] && needle) {
            location.hash = hits[0].to;
            onClose();
          }
        }}
      >
        <label htmlFor="cmd" className="sr">
          Go to, or tell Archeus
        </label>
        <input id="cmd" autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder="Go to… or tell Archeus what you want" autoComplete="off" />
      </form>
      <ul className="hits" role="listbox" aria-label="Results">
        {hits.map((h) => (
          <li key={h.to} role="option" aria-selected={false}>
            <a href={h.to} onClick={onClose}>
              {h.label}
            </a>
          </li>
        ))}
      </ul>
      {needle ? (
        <button type="button" className="btn primary" disabled={!live} title={live ? undefined : 'Not connected'} onClick={() => void tell()}>
          Tell Archeus: “{q}”
        </button>
      ) : null}
      {msg ? <p role="status">{msg}</p> : null}
    </dialog>
  );
}

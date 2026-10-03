// The command palette (Ctrl/⌘+K; p16-design-gate §4.1, rulebook §18; D-12):
// jump to a destination or an object this client has read, act on a mission
// by the same Core verb as its button — each action saying its effect first —
// or tell Archeus something: the text goes to the primary conversation, where
// Core's grammar and intent pipeline decide what it means. The client parses
// no verb (§5, §19) and decides no permission; search is cache-only (P21 owns
// server search).
import { useEffect, useRef, useState } from 'react';
import { paths, api, type KnowledgeList, type MissionList, type ProjectList, type Status } from '../api/generated';
import { store, useConn } from '../data/cache';
import { CoreError } from '../api/transport';
import { explain, keyAfter, newKey, retryable } from '../data/commands';
import { canCommand } from '../data/connection';
import { send } from '../data/core';
import { DESTINATIONS, href } from '../nav/destinations';
import { moveActive, paletteHits, type Hit } from '../state/palette';
import { useMe } from '../components/ui';

const ACT = { pause: (id: string, v: number, key: string) => api.pauseMission(send(), id, { idempotency_key: key, expected_version: v }), resume: (id: string, v: number, key: string) => api.resumeMission(send(), id, { idempotency_key: key, expected_version: v }) };

export function CommandBar({ open, onClose }: { open: boolean; onClose: () => void }) {
  const dlg = useRef<HTMLDialogElement>(null);
  const [q, setQ] = useState('');
  const [active, setActive] = useState(0);
  const [msg, setMsg] = useState<string | null>(null);
  const tellKey = useRef(newKey()); // one key per message the user means, reused on a retry
  const conn = useConn();
  const { can } = useMe();
  useEffect(() => {
    if (open && !dlg.current?.open) dlg.current?.showModal();
    if (!open && dlg.current?.open) dlg.current.close();
  }, [open]);
  const read = <T,>(p: string) => store.snapshot(p).data as T | undefined;
  const hits = paletteHits(
    {
      destinations: DESTINATIONS.map((d) => ({ id: d.id, label: d.label, to: href({ view: d.id }) })),
      missions: read<MissionList>(paths.listMissions())?.missions ?? [],
      projects: read<ProjectList>(paths.listProjects())?.projects ?? [],
      knowledge: (read<KnowledgeList>(paths.listKnowledge())?.knowledge ?? []) as { id: string; title?: string | null }[],
      live: read<Status>(paths.status())?.live ?? [],
    },
    q,
  );
  const at = Math.min(active, Math.max(0, hits.length - 1));
  const live = canCommand(conn.conn);
  const ready = live ? 'live' : conn.conn === 'reconnecting' ? 'reconnecting' : 'off';
  const needle = q.trim();
  const why = !live ? 'Not connected — nothing is sent while reconnecting.' : !can('control') ? 'This client does not hold the “control” scope.' : null;

  async function act(h: Extract<Hit, { act: string }>) {
    const key = newKey(); // one press, one key: a retry Core asked for reuses it
    try {
      try {
        await ACT[h.act](h.mission.id, h.mission.version, key);
      } catch (e) {
        if (e instanceof CoreError && retryable(e)) await ACT[h.act](h.mission.id, h.mission.version, key); // once, same key
        else throw e;
      }
      setMsg(`${h.label} was sent; the mission shows what Core did.`);
    } catch (e) {
      setMsg(explain(e instanceof CoreError ? e : new CoreError(0, 'network', {})));
    } finally {
      // never assume the result: read again what the command may have changed
      for (const p of [paths.getMission(h.mission.id), paths.listMissions(), paths.status(), paths.attentionItems()])
        store.invalidate((x) => x === p || x.startsWith(p + '?'));
    }
  }

  function choose(h: Hit | undefined) {
    if (!h) return;
    if ('go' in h) {
      location.hash = h.go;
      onClose();
    } else if (!why) void act(h);
  }

  async function tell() {
    let outcome: 'ok' | 'refused' | 'network' = 'ok';
    try {
      await api.postMessage(send(), 'primary', { text: q, idempotency_key: tellKey.current });
      setMsg('Sent to Archeus — its reply appears on Now.');
      setQ('');
      store.invalidate((p) => p.startsWith(paths.listMessages('primary')));
    } catch (e) {
      const ce = e instanceof CoreError ? e : new CoreError(0, 'network', {});
      outcome = ce.code === 'network' ? 'network' : 'refused';
      setMsg(explain(ce));
    } finally {
      tellKey.current = keyAfter(tellKey.current, outcome);
    }
  }

  return (
    <dialog ref={dlg} className="command" aria-label="Command bar" onClose={onClose}>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (needle) choose(hits[at]);
        }}
      >
        <label htmlFor="cmd" className="sr">
          Go to, act, or tell Archeus
        </label>
        <input
          id="cmd"
          autoFocus
          value={q}
          data-ready={ready}
          role="combobox"
          aria-expanded={hits.length > 0}
          aria-controls="cmd-hits"
          aria-autocomplete="list"
          aria-activedescendant={hits.length ? `cmd-opt-${at}` : undefined}
          onChange={(e) => {
            setQ(e.target.value);
            setActive(0);
            setMsg(null);
          }}
          onKeyDown={(e) => {
            const to = moveActive(at, hits.length, e.key);
            if (to === null) return;
            e.preventDefault();
            setActive(to);
          }}
          placeholder="Go to… act on a mission… or tell Archeus what you want"
          autoComplete="off"
        />
      </form>
      <ul className="hits" role="listbox" id="cmd-hits" aria-label="Results">
        {hits.map((h, i) => (
          <li
            key={h.key}
            id={`cmd-opt-${i}`}
            role="option"
            aria-selected={i === at}
            aria-disabled={'act' in h && !!why ? true : undefined}
            data-hit={h.key}
            onMouseMove={() => setActive(i)}
            onClick={() => choose(h)}
          >
            <span className="hit-label">{h.label}</span>
            {'act' in h ? <span className="hint"> — {why ?? h.effect}</span> : null}
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

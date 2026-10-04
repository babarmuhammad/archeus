// The offline snapshot (p19-design-gate B7, P16 seam S6): the SPA itself — never
// the service worker, which stays shell-only (§13.5) — keeps the Now
// composition after each successful read, so a cold start with no Core can
// show it read-only. Nothing else is kept: no token, no event, no other read.
import { paths, type Client, type MissionList } from '../api/generated.ts';

const DB = 'archeus-snapshot';
const STORE = 'now';

/** The Now composition: the only reads ever kept. */
export const NOW_READS: readonly string[] = [paths.status(), paths.digest(), paths.attentionItems(), paths.listMissions()];

export interface Kept {
  origin: string; // the Core origin it was read from
  path: string;
  data: unknown;
  seq: number | null; // the event head Core read it at (X-Archeus-Seq)
  at: string; // when it was read
}

/** Never kept on a client paired `observe`-only: Core cannot tell networks
 * apart, and a paired client is one that is not on the computer running it. */
export const mayKeep = (c: Pick<Client, 'origin' | 'scopes'>) => !(c.origin === 'paired' && c.scopes.every((s) => s === 'observe'));

/** The mission states that have ended: nothing about them is Now's. */
export const ENDED: readonly string[] = ['COMPLETED', 'CANCELLED', 'FAILED'];

/** What is kept of a read: the missions that have not ended — the ones Now
 * shows working, and the ones that wait on you (an approval, a pause, a block),
 * whose titles name what Needs you and the digest point at (R13-02). */
export const keptData = (path: string, data: unknown): unknown =>
  path === paths.listMissions() ? { missions: (data as MissionList).missions.filter((m) => !ENDED.includes(m.state)) } : data;

/** When the oldest kept read was taken: what the whole snapshot is "as of". */
export const asOf = (kept: readonly Kept[]): string => kept.map((k) => k.at).sort()[0];

function db<T>(mode: IDBTransactionMode, op: (s: IDBObjectStore) => IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    const open = indexedDB.open(DB, 1);
    open.onupgradeneeded = () => open.result.createObjectStore(STORE);
    open.onerror = () => reject(open.error);
    open.onsuccess = () => {
      const req = op(open.result.transaction(STORE, mode).objectStore(STORE));
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    };
  });
}

export function keep(path: string, data: unknown, seq: number | undefined) {
  if (!NOW_READS.includes(path)) return;
  const k: Kept = { origin: location.origin, path, data: keptData(path, data), seq: seq ?? null, at: new Date().toISOString() };
  db('readwrite', (s) => s.put(k, `${k.origin} ${path}`)).catch(() => undefined);
}

/** This Core origin's snapshot: every Now read, or null when one is missing. */
export async function loadSnapshot(): Promise<Kept[] | null> {
  const all = await db<Kept[]>('readonly', (s) => s.getAll()).catch(() => [] as Kept[]);
  const mine = NOW_READS.map((p) => all.find((k) => k.origin === location.origin && k.path === p));
  return mine.every((k) => k) ? (mine as Kept[]) : null;
}

export const clearSnapshot = () => db('readwrite', (s) => s.clear()).catch(() => undefined);

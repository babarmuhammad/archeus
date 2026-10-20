// How the SPA reaches Core: its device token (IndexedDB), the fetch wrapper the
// generated client sends through, and the two bootstraps — a launch code
// (p3.5b D7) on this machine, a pairing code (P15 §6) anywhere. The token only
// ever travels in the Authorization header — never in a URL.
import { api, type Send } from './generated.ts';
import { clearSnapshot } from '../data/snapshot.ts';
import { newKey } from '../data/commands.ts';

const DB = 'archeus';
const STORE = 'auth';
const KEY = 'device-token';

export class CoreError extends Error {
  readonly status: number;
  readonly code: string;
  readonly detail: Record<string, unknown>;
  constructor(status: number, code: string, detail: Record<string, unknown>) {
    super(`${status} ${code}`);
    this.status = status;
    this.code = code;
    this.detail = detail;
  }
}

function store<T>(mode: IDBTransactionMode, op: (s: IDBObjectStore) => IDBRequest<T>): Promise<T> {
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

// The Qt shell's page (`memory=1`, T-096) keeps its token here and never on disk
// (p20 D1); the flag itself is no secret, and a reload keeps it in the tab.
const MEMORY = 'archeus-token-in-memory';
let held: string | undefined;
export const memoryOnly = () => typeof sessionStorage !== 'undefined' && sessionStorage.getItem(MEMORY) === '1';

const loadToken = () => (memoryOnly() ? Promise.resolve(held) : store<string | undefined>('readonly', (s) => s.get(KEY)));
const saveToken = (t: string) => (memoryOnly() ? Promise.resolve((held = t)) : store('readwrite', (s) => s.put(t, KEY)));
// In memory mode the disk copy is retire()'s alone: a live one it kept must be
// revoked before it goes, never deleted on the side (T-096 review finding 2).
export const clearToken = () => {
  held = undefined;
  return memoryOnly() ? Promise.resolve() : store('readwrite', (s) => s.delete(KEY));
};

/** A token an earlier shell kept on disk (T-096): revoked through itself before
 * it is deleted, because deleted but live it would still be an admin token in
 * the profile - LevelDB keeps a deleted value's bytes until it compacts, and no
 * page can make it, so what stays is a dead token. Core down or refusing: it
 * stays where it is and the next launch tries again. */
async function retire(old: string) {
  const send = sender(old);
  try {
    await api.revokeDevice(send, (await api.sync(send)).client.id, { idempotency_key: newKey() });
  } catch (e) {
    if (!(e instanceof CoreError && e.status === 401)) return; // 401: already dead
  }
  await store('readwrite', (s) => s.delete(KEY));
}

/** `onSeq` hears the `X-Archeus-Seq` Core sent with a read (P15 §13): the event
 * head the answer was read at. */
export function sender(token?: string, onSeq?: (path: string, seq: number) => void): Send {
  return async <T>(method: string, path: string, body?: unknown): Promise<T> => {
    const headers: Record<string, string> = {};
    if (token) headers.Authorization = `Bearer ${token}`;
    if (body !== undefined) headers['Content-Type'] = 'application/json';
    let r: Response;
    try {
      r = await fetch(path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
    } catch {
      throw new CoreError(0, 'network', {});
    }
    const seq = r.headers.get('X-Archeus-Seq');
    if (seq !== null && onSeq) onSeq(path, Number(seq));
    const data = await r.json().catch(() => undefined);
    // a body that never arrived whole (the connection dropped mid-read) is no
    // answer: never data, which a read would show and the snapshot would keep
    if (data === undefined) throw r.ok ? new CoreError(0, 'network', {}) : new CoreError(r.status, 'invalid_response', {});
    if (!r.ok) throw new CoreError(r.status, data.error, data.detail ?? {});
    return data as T;
  };
}

export interface Grant {
  token: string;
  scopes: string[];
}

/** The fragment's bootstrap, read and removed at once. */
export function takeFragment(): { launch?: string; pair?: string } {
  const p = new URLSearchParams(location.hash.slice(1));
  const out = { launch: p.get('launch') ?? undefined, pair: p.get('pair') ?? undefined };
  if (p.get('memory') === '1') sessionStorage.setItem(MEMORY, '1');
  if (out.launch || out.pair || p.has('memory')) history.replaceState(null, '', location.pathname + location.search);
  return out;
}

/** The device token to use, or null when there is none and no launch code.
 * The stored token is tried first; a launch code is redeemed only when there
 * is no token or Core refused it. */
export async function authenticate(launch?: string): Promise<string | null> {
  if (memoryOnly()) {
    const old = await store<string | undefined>('readonly', (s) => s.get(KEY));
    if (old) await retire(old);
    // no launch code: Core down is still the offline snapshot (P19 B7), whose
    // cue is the error a read with no token meets
    if (!launch) await api.version(sender()).catch((e) => {
      if (!(e instanceof CoreError && e.status === 401)) throw e;
    });
  }
  const stored = await loadToken();
  if (stored) {
    try {
      await api.version(sender(stored));
      return stored;
    } catch (e) {
      if (!(e instanceof CoreError && e.status === 401)) throw e;
      // revoked while away: the revocation is read before anything is shown
      await clearToken();
      await clearSnapshot();
    }
  }
  if (!launch) return null;
  try {
    const out = await api.launchRedeem(sender(), { code: launch, platform: 'web' });
    await saveToken(out.token);
    return out.token;
  } catch (e) {
    if (e instanceof CoreError && e.status === 401) return null;
    throw e;
  }
}

/** Redeem a pairing code (P15 §6.1 step 3): the new token replaces any stored one. */
export async function redeemPairing(code: string, name: string, pin?: string): Promise<string> {
  const platform = /android/i.test(navigator.userAgent)
    ? 'android'
    : /iphone|ipad/i.test(navigator.userAgent)
      ? 'ios'
      : 'web';
  const out = await api.pairRedeem(sender(), { code, platform, name: name || null, pin: pin || null });
  await saveToken(out.token);
  return out.token;
}

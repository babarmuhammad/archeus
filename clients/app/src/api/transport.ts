// How the SPA reaches Core: its device token (IndexedDB), the fetch wrapper the
// generated client sends through, and the two bootstraps — a launch code
// (p3.5b D7) on this machine, a pairing code (P15 §6) anywhere. The token only
// ever travels in the Authorization header — never in a URL.
import { api, type Send } from './generated';

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

const loadToken = () => store<string | undefined>('readonly', (s) => s.get(KEY));
const saveToken = (t: string) => store('readwrite', (s) => s.put(t, KEY));
export const clearToken = () => store('readwrite', (s) => s.delete(KEY));

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
    const data = await r.json().catch(() => ({ error: 'invalid_response', detail: {} }));
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
  if (out.launch || out.pair) history.replaceState(null, '', location.pathname + location.search);
  return out;
}

/** The device token to use, or null when there is none and no launch code.
 * The stored token is tried first; a launch code is redeemed only when there
 * is no token or Core refused it. */
export async function authenticate(launch?: string): Promise<string | null> {
  const stored = await loadToken();
  if (stored) {
    try {
      await api.version(sender(stored));
      return stored;
    } catch (e) {
      if (!(e instanceof CoreError && e.status === 401)) throw e;
      await clearToken();
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

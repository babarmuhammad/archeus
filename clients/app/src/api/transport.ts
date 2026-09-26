// How the SPA reaches Core: its device token (IndexedDB), the fetch wrapper the
// generated client sends through, and the launch-code bootstrap (p3.5b D7).
// The token only ever travels in the Authorization header — never in a URL.
import { api, type Send } from './generated';

const DB = 'archeus';
const STORE = 'auth';
const KEY = 'device-token';

export class CoreError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    readonly detail: Record<string, unknown>,
  ) {
    super(`${status} ${code}`);
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
const clearToken = () => store('readwrite', (s) => s.delete(KEY));

export function sender(token?: string): Send {
  return async <T>(method: string, path: string, body?: unknown): Promise<T> => {
    const headers: Record<string, string> = {};
    if (token) headers.Authorization = `Bearer ${token}`;
    if (body !== undefined) headers['Content-Type'] = 'application/json';
    const r = await fetch(path, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    const data = await r.json();
    if (!r.ok) throw new CoreError(r.status, data.error, data.detail ?? {});
    return data as T;
  };
}

/** The device token to use, or null when there is none and no launch code.
 * The stored token is tried first; a launch code is redeemed only when there
 * is no token or Core refused it. The fragment is removed at once either way. */
export async function authenticate(): Promise<string | null> {
  const code = new URLSearchParams(location.hash.slice(1)).get('launch');
  if (location.hash) history.replaceState(null, '', location.pathname + location.search);
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
  if (!code) return null;
  try {
    const out = await api.launchRedeem(sender(), { code, platform: 'web' });
    await saveToken(out.token);
    return out.token;
  } catch (e) {
    if (e instanceof CoreError && e.status === 401) return null;
    throw e;
  }
}

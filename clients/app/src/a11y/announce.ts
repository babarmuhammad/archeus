// Screen-reader announcements (p16-design-gate §17): one polite region,
// rate-limited to one announcement per 5 s (the latest wins), and one
// assertive announcement per new approval. Nothing is announced per stream
// frame. The limiter is pure; the DOM writer is below it.

export const POLITE_EVERY_MS = 5000;

export interface Limiter {
  /** the text to announce now, or null when it must wait (it is kept as the
   * latest pending one and returned by `flush`) */
  offer(text: string, now: number): string | null;
  flush(now: number): string | null;
}

export function limiter(every = POLITE_EVERY_MS): Limiter {
  let last = -Infinity;
  let pending: string | null = null;
  return {
    offer(text, now) {
      if (now - last >= every) {
        last = now;
        pending = null;
        return text;
      }
      pending = text;
      return null;
    },
    flush(now) {
      if (pending !== null && now - last >= every) {
        last = now;
        const t = pending;
        pending = null;
        return t;
      }
      return null;
    },
  };
}

const polite = limiter();
const announcedApprovals = new Set<string>();
let timer: ReturnType<typeof setTimeout> | undefined;

function write(id: string, text: string) {
  const el = typeof document === 'undefined' ? null : document.getElementById(id);
  if (!el) return;
  el.textContent = '';
  setTimeout(() => (el.textContent = text), 30);
}

export function announce(text: string) {
  const now = Date.now();
  const t = polite.offer(text, now);
  if (t) write('live-polite', t);
  else {
    clearTimeout(timer);
    timer = setTimeout(() => {
      const f = polite.flush(Date.now());
      if (f) write('live-polite', f);
    }, POLITE_EVERY_MS);
  }
}

/** Once per approval id, assertively. */
export function announceApproval(id: string, text: string) {
  if (announcedApprovals.has(id)) return;
  announcedApprovals.add(id);
  write('live-assertive', text);
}

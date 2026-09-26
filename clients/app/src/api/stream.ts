// One event stream per browser (ADR-0009, p3.5b D1): the tab holding the Web
// Lock is the leader and owns the SSE connection; every other tab hears the
// frames over a BroadcastChannel. When the leader goes, the next tab in the
// lock's queue takes over. Frames carry identities only: a subscriber
// re-queries what it shows, it never reads state out of a frame.
import { STREAM_PATH } from './generated';

export interface Frame {
  id?: number;
  event: string;
  data?: unknown;
}

const LOCK = 'archeus-stream';
const CHANNEL = 'archeus-events';

/** Frames synthesised here, never sent by Core: re-query everything. */
export const RESYNC = 'resync';
export const UNAUTHENTICATED = 'unauthenticated';

function parse(block: string): Frame | null {
  const f: Frame = { event: 'message' };
  let seen = false;
  for (const line of block.split('\n')) {
    if (!line || line.startsWith(':')) continue;
    const i = line.indexOf(': ');
    const k = i < 0 ? line : line.slice(0, i);
    const v = i < 0 ? '' : line.slice(i + 2);
    seen = true;
    if (k === 'id') f.id = Number(v);
    else if (k === 'event') f.event = v;
    else if (k === 'data') f.data = JSON.parse(v);
  }
  return seen ? f : null;
}

async function read(body: ReadableStream<Uint8Array>, emit: (f: Frame) => void) {
  const reader = body.getReader();
  const text = new TextDecoder();
  let buf = '';
  for (;;) {
    const { value, done } = await reader.read();
    if (done) return;
    buf += text.decode(value, { stream: true });
    let cut: number;
    while ((cut = buf.indexOf('\n\n')) >= 0) {
      const f = parse(buf.slice(0, cut));
      buf = buf.slice(cut + 2);
      if (f) emit(f);
    }
  }
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

async function lead(token: string, emit: (f: Frame) => void, stop: AbortSignal) {
  let last: number | undefined;
  let delay = 250;
  while (!stop.aborted) {
    try {
      const headers: Record<string, string> = { Authorization: `Bearer ${token}` };
      if (last !== undefined) headers['Last-Event-ID'] = String(last);
      const r = await fetch(STREAM_PATH, { headers, signal: stop, cache: 'no-store' });
      if (r.status === 401) {
        emit({ event: UNAUTHENTICATED });
        return;
      }
      if (r.status === 410) {
        last = undefined; // the cursor is gone: re-query, then live from the head
        emit({ event: RESYNC });
      } else if (r.ok && r.body) {
        delay = 250;
        await read(r.body, (f) => {
          if (f.event === 'cursor_expired') {
            last = undefined;
            emit({ event: RESYNC });
          } else if (f.event !== 'shutdown') {
            if (f.id !== undefined) last = f.id;
            emit(f);
          }
        });
      }
    } catch {
      if (stop.aborted) return;
    }
    await sleep(delay);
    delay = Math.min(delay * 2, 8000);
  }
}

/** Receive every frame, from our own stream or the leader tab's. */
export function subscribe(token: string, onFrame: (f: Frame) => void): () => void {
  const channel = new BroadcastChannel(CHANNEL);
  channel.onmessage = (m: MessageEvent<Frame>) => onFrame(m.data);
  const stop = new AbortController();
  navigator.locks
    .request(LOCK, { signal: stop.signal }, async () => {
      onFrame({ event: RESYNC }); // a new leader may have missed frames between leaders
      await lead(token, (f) => {
        onFrame(f);
        channel.postMessage(f);
      }, stop.signal);
    })
    .catch(() => undefined);
  return () => {
    stop.abort();
    channel.close();
  };
}

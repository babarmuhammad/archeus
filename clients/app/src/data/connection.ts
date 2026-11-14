// The app's one connection state and every view's freshness
// (p16-design-gate §13). Derived from what the stream and the reads report —
// never from a guess about Core. Pure: tested and mutated directly.

export type Conn =
  | 'connecting'
  | 'live'
  | 'reconnecting'
  | 'resynced'
  | 'offline'
  | 'unauthenticated'
  | 'revoked';

export type Signal =
  | 'stream_open' // a stream answered 200
  | 'frame' // any frame or heartbeat arrived
  | 'stream_lost' // the stream ended or failed; the leader retries
  | 'resync' // 410 / cursor_expired / a new leader: every key must be re-read
  | 'settled' // the post-resync notice has been shown
  | 'offline' // the browser says it has no network
  | 'online'
  | 'unauthorized' // a 401 on the stream or a read
  | 'self_revoked'; // this client revoked itself

export interface ConnState {
  conn: Conn;
  /** increments every time the app must treat everything it holds as stale:
   * a view read in an older generation is not current */
  gen: number;
  since: number; // when the state was entered (ms)
}

export const initial = (now = Date.now()): ConnState => ({ conn: 'connecting', gen: 0, since: now });

/** The next connection state. A signed-out client stays signed out: only a new
 * credential (a reload) leaves it. */
export function next(s: ConnState, sig: Signal, now = Date.now()): ConnState {
  if (s.conn === 'unauthenticated' || s.conn === 'revoked') return s;
  const to = (conn: Conn, bump = false): ConnState =>
    conn === s.conn && !bump ? s : { conn, gen: s.gen + (bump ? 1 : 0), since: now };
  switch (sig) {
    case 'unauthorized':
      return to('unauthenticated');
    case 'self_revoked':
      return to('revoked');
    case 'offline':
      return to('offline');
    case 'online':
      return s.conn === 'offline' ? to('reconnecting') : s;
    case 'stream_lost':
      return s.conn === 'offline' ? s : to('reconnecting');
    case 'resync':
      // a resync before anything was shown is only a fresh start
      return s.conn === 'connecting' ? to('connecting', true) : to('resynced', true);
    case 'stream_open':
      // coming back from a drop is a resync: what was read before may be old
      return s.conn === 'reconnecting' || s.conn === 'offline' ? to('resynced', true) : s.conn === 'connecting' ? to('live') : s;
    case 'frame':
      return s.conn === 'connecting' ? to('live') : s;
    case 'settled':
      return s.conn === 'resynced' ? to('live') : s;
  }
}

/** Commands are sent only on a live connection (§13.3). */
export const canCommand = (c: Conn) => c === 'live' || c === 'resynced';

export type Freshness = 'current' | 'stale' | 'reconnecting' | 'unavailable';

/** A view's freshness from the connection and when (in which generation) its
 * data was read. */
export function freshness(
  c: ConnState,
  entry: { gen: number; error?: unknown; pending?: boolean; hasData: boolean },
): Freshness {
  if (entry.error && !entry.hasData) return 'unavailable';
  if (c.conn === 'reconnecting' || c.conn === 'connecting') return entry.hasData ? 'reconnecting' : 'unavailable';
  if (c.conn !== 'live' && c.conn !== 'resynced') return entry.hasData ? 'stale' : 'unavailable';
  if (entry.gen < c.gen || entry.pending || entry.error) return 'stale';
  return 'current';
}

export const BANNER: Record<Conn, string | null> = {
  connecting: 'Connecting…',
  live: null,
  reconnecting: 'Reconnecting — what you see may be out of date. Nothing is sent until the connection is back.',
  resynced: 'Back — everything on screen was read again.',
  offline:
    'Offline — nothing you do here is sent. Work on the computer running Archeus continues.',
  unauthenticated:
    'This client is signed out: its access was revoked or has expired. Open Archeus from the computer running it, or pair this client again.',
  revoked: 'This client’s access was revoked. It cannot act any more; pair it again to use it.',
};

"""Reading committed events by cursor.

A cursor is the `seq` of the last event a reader has seen; `events_after(n)`
returns what committed after it, in `seq` order. Because one writer assigns seq
at commit time, that answer is complete: nothing with a lower seq can still
appear later. Run it inside `Database.read()` so the bounds and the rows come
from the same snapshot.

The cursor contract (api-and-realtime §3.4; HTTP arrives in P3.5):
- malformed (not an integer >= 0) raises `ValueError` — the API's `400`;
- a cursor the log can no longer honour raises `CursorExpired` — the API's
  `410 cursor_expired`, answered by a snapshot resync — in both cases:
- `pruned`: retention removed events after it, so replay would skip some;
- `ahead`: it names a seq this database never assigned (a restored backup, a
  reset home), so waiting for it would wait forever.
"""

import json

from ...core.domain.events import Event

DEFAULT_LIMIT = 500
MAX_LIMIT = 1000


class CursorExpired(LookupError):
    def __init__(self, cursor, reason, floor, head):
        super().__init__('cursor %d is %s (retained: %d..%d)' % (cursor, reason, floor, head))
        self.cursor, self.reason, self.floor, self.head = cursor, reason, floor, head


def head(conn):
    """The highest seq ever assigned (survives deletion: AUTOINCREMENT)."""
    r = conn.execute("SELECT seq FROM sqlite_sequence WHERE name = 'events'").fetchone()
    return r[0] if r else 0


def floor(conn):
    """The lowest cursor that still replays completely."""
    low = conn.execute('SELECT MIN(seq) FROM events').fetchone()[0]
    return head(conn) if low is None else low - 1


def decode(r):
    return Event(seq=r['seq'], id=r['id'], type=r['type'], at=r['at'],
                 actor={'kind': r['actor_kind'], 'id': r['actor_id']},
                 subject={'kind': r['subject_kind'], 'id': r['subject_id']},
                 workspace=r['workspace_id'], project=r['project_id'],
                 cause_chain=json.loads(r['cause_chain']), visibility=r['visibility'],
                 payload=json.loads(r['payload']))


def events_after(conn, cursor, *, limit=DEFAULT_LIMIT):
    """Committed events with seq > *cursor*, oldest first, at most *limit*."""
    if isinstance(cursor, bool) or not isinstance(cursor, int) or cursor < 0:
        raise ValueError('a cursor is an integer >= 0, got %r' % (cursor,))
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_LIMIT:
        raise ValueError('limit is 1..%d, got %r' % (MAX_LIMIT, limit))
    low, high = floor(conn), head(conn)
    if cursor < low:
        raise CursorExpired(cursor, 'pruned', low, high)
    if cursor > high:
        raise CursorExpired(cursor, 'ahead', low, high)
    return [decode(r) for r in conn.execute(
        'SELECT * FROM events WHERE seq > ? ORDER BY seq LIMIT ?', (cursor, limit))]

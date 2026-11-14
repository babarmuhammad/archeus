"""Retention (api-and-realtime §3.4): old events and expired idempotency keys.

`prune` is a writer command. It removes a PREFIX of the log — every event
before the first one still inside the window — so `outbox.floor()` stays exact
and a cursor below it gets `410 cursor_expired` instead of a silent gap. It
never removes an event a registered consumer has not passed yet.

Deferred with the missions lifecycle it depends on: keeping the events of an
open mission past the window (until it closes + 30 days).
"""

from datetime import datetime, timedelta, timezone

from ..db.writer import IDEMPOTENCY_TTL, iso
from . import outbox

EVENT_DAYS = 180


def prune(tx, *, now=None, keep_days=EVENT_DAYS):
    now = datetime.fromisoformat(now.replace('Z', '+00:00')) if now else datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError('now must carry a zone')
    if keep_days < 0:
        # a negative window would prune the whole log: remove nothing instead
        return {'events': 0, 'through': 0, 'idempotency_keys': 0}
    cutoff = iso(now - timedelta(days=keep_days))
    first_kept = tx.execute('SELECT MIN(seq) FROM events WHERE at >= ?', (cutoff,)).fetchone()[0]
    through = outbox.head(tx.conn) if first_kept is None else first_kept - 1
    slowest = tx.execute('SELECT MIN(last_seq) FROM consumer_cursors').fetchone()[0]
    if slowest is not None:
        through = min(through, slowest)
    if tx.execute('SELECT 1 FROM consumer_effects WHERE consumer NOT IN '
                  '(SELECT name FROM consumer_cursors) LIMIT 1').fetchone():
        through = 0          # a consumer with effects and no cursor row reads cursor 0
    events = tx.execute('DELETE FROM events WHERE seq <= ?', (through,)).rowcount
    tx.execute('DELETE FROM consumer_effects WHERE event_seq <= ?', (through,))
    keys = tx.execute('DELETE FROM idempotency_keys WHERE created_at < ?',
                      (iso(now - IDEMPOTENCY_TTL),)).rowcount
    return {'events': events, 'through': through, 'idempotency_keys': keys}
